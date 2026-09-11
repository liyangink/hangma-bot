"""方向 B 风险表 v3：庄闲分离 + 绝对支付。

守三条不变量：
1. dealer 为 None 的旧表行为**逐字不变**（v2 表兼容，既有配置不受影响）；
2. dealer 维**真正生效**：庄位窗口只匹配 dealer=True 的 cell，闲位反之，无匹配则不升级；
3. 绝对支付字段替代倍数口径，且庄位支付高于闲位（支付结构不对称：庄胡 +24 番、
   庄输给闲 -8 番；闲胡 +10 番、输给另一闲 -1 番）。
"""

import asyncio
import json
from dataclasses import replace
from pathlib import Path

import pytest

from hangma_bot.application.audit_codec import decision_request_from_json
from hangma_bot.hangma import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.policy.hu_upgrade import UpgradeRiskCell, risk_cell_loss, risk_cell_matches
from hangma_bot.policy.hu_upgrade_calibration import RISK_CELLS_V3, RISK_VERSION_V3
from hangma_bot.policy.v2_hu_upgrade import V2HuUpgradePolicy

from .support import make_budget

ROOT = Path(__file__).resolve().parents[2]
RULES = HangmaRules(RuleConfig("hangma-mvp-v5-four-white", 1, False))


def historical(name="A"):
    original = decision_request_from_json(json.loads(
        (ROOT / "fixtures/policy/one-draw-value" / (name + ".json")).read_text()
    )["request_event"]["payload"]["request"])
    return replace(original, rules=RULES.analyze(original.observation, value_limits=ValueAnalysisLimits()))


def plan_of(policy, request):
    return asyncio.run(policy.choose(request, make_budget()))


def test_legacy_cell_keeps_multiple_semantics():
    """dealer=None 且未设绝对支付时，损失口径仍是 旧倍数 × 立即胡净分。"""

    legacy = UpgradeRiskCell(wall_band=1, threat=False, survival_floor=0.83, loss_ceiling=0.10)
    assert legacy.dealer is None and legacy.loss_absolute is None
    assert risk_cell_loss(legacy, 24.0) == pytest.approx(2.4)
    assert risk_cell_matches(legacy, 1, False, True) is True
    assert risk_cell_matches(legacy, 1, False, False) is True
    assert risk_cell_matches(legacy, 1, True, False) is False
    assert risk_cell_matches(legacy, 2, False, False) is False


def test_absolute_loss_overrides_multiple():
    """设了 loss_absolute 就以绝对支付为准，不再随立即胡分缩放。"""

    cell = UpgradeRiskCell(wall_band=2, threat=False, survival_floor=0.95, loss_ceiling=0.10,
                           dealer=True, loss_absolute=11.5)
    assert risk_cell_loss(cell, 10.0) == pytest.approx(11.5)
    assert risk_cell_loss(cell, 100.0) == pytest.approx(11.5)


def test_dealer_dimension_is_exclusive():
    """dealer 维互斥：庄位/闲位各只匹配自己的 cell。"""

    dealer_cell = UpgradeRiskCell(1, False, 0.83, 0.10, dealer=True, loss_absolute=11.5)
    plain_cell = UpgradeRiskCell(1, False, 0.83, 0.10, dealer=False, loss_absolute=5.2)
    assert risk_cell_matches(dealer_cell, 1, False, True) is True
    assert risk_cell_matches(dealer_cell, 1, False, False) is False
    assert risk_cell_matches(plain_cell, 1, False, False) is True
    assert risk_cell_matches(plain_cell, 1, False, True) is False


def test_invalid_extension_fields_rejected():
    """扩展字段必须类型安全，不把脏值带进评分。"""

    with pytest.raises(ValueError):
        UpgradeRiskCell(1, False, 0.83, 0.10, dealer=1)  # 非 bool
    with pytest.raises(ValueError):
        UpgradeRiskCell(1, False, 0.83, 0.10, loss_absolute=-1.0)
    with pytest.raises(ValueError):
        UpgradeRiskCell(1, False, 0.83, 0.10, loss_absolute=float("nan"))


def test_v3_table_prices_dealer_higher_and_relaxes_band_two():
    """v3 表：庄位支付高于闲位；band 2 生存下侧按实测从 0.92 提到 0.95。"""

    assert RISK_VERSION_V3.startswith("hu-upgrade-risk-v3")
    for band in (1, 2):
        cells = {cell.dealer: cell for cell in RISK_CELLS_V3 if cell.wall_band == band}
        assert set(cells) == {True, False}, band
        assert cells[True].loss_absolute > cells[False].loss_absolute, band
    band1 = next(c for c in RISK_CELLS_V3 if c.wall_band == 1 and c.dealer is False)
    band2 = next(c for c in RISK_CELLS_V3 if c.wall_band == 2 and c.dealer is False)
    assert band1.survival_floor == pytest.approx(0.83)
    assert band2.survival_floor == pytest.approx(0.95)
    assert all(cell.loss_absolute is not None for cell in RISK_CELLS_V3)


def test_reason_text_reports_the_same_pricing_as_the_decision():
    """审计文案必须与决策用同一套定价。

    回归：Tier-B 曾自行拼串，决策已改用绝对支付、文案却仍写"0.1000×当前胡分"，
    并按倍数口径算出保守分值——审计者按文案复算会得到与代码不同的数字。
    现在两类档位共用 upgrade_reason，文案必须出现"绝对支付"且不得再出现倍数口径。
    """

    request = historical("A")
    cells = (UpgradeRiskCell(1, False, 1.0, 0.10, dealer=True, loss_absolute=7.5),
             UpgradeRiskCell(2, False, 1.0, 0.10, dealer=True, loss_absolute=7.5))
    plan = plan_of(V2HuUpgradePolicy(monotonic=lambda: 0, risk_cells=cells,
                                     risk_version="audit-test"), request)
    reason = plan.candidates[0].reasons[-1]
    assert plan.candidates[0].action_key == "discard:5b"
    assert "绝对支付 7.5 分" in reason, reason
    assert "×当前胡分" not in reason, reason
    assert "分组 1/0/庄=1" in reason or "分组 2/0/庄=1" in reason, reason


def test_dealer_window_needs_a_dealer_cell_and_uses_the_absolute_loss():
    """端到端：夹具 A 是庄位窗口。

    只给闲位 cell 时不得升级（无匹配分组）；给出庄位 cell 且支付归零、生存取 1 时才升级。
    这条同时证明 dealer 维确实接进了 choose 的分组匹配。
    """

    request = historical("A")
    seat = request.observation.seat
    assert request.observation.dealer_seat == seat, "夹具 A 应为庄位窗口"

    plain_only = (UpgradeRiskCell(1, False, 1.0, 0.10, dealer=False, loss_absolute=0.0),
                  UpgradeRiskCell(2, False, 1.0, 0.10, dealer=False, loss_absolute=0.0))
    plan = plan_of(V2HuUpgradePolicy(monotonic=lambda: 0, risk_cells=plain_only,
                                     risk_version="test"), request)
    assert plan.candidates[0].action_key != "discard:5b", "只给闲位分组时庄位窗口不应升级"

    with_dealer = (UpgradeRiskCell(1, False, 1.0, 0.10, dealer=True, loss_absolute=0.0),
                   UpgradeRiskCell(2, False, 1.0, 0.10, dealer=True, loss_absolute=0.0))
    plan = plan_of(V2HuUpgradePolicy(monotonic=lambda: 0, risk_cells=with_dealer,
                                     risk_version="test"), request)
    assert plan.candidates[0].action_key == "discard:5b", "庄位分组匹配且支付归零时应升级"


def test_high_absolute_loss_blocks_the_dealer_upgrade():
    """庄位支付足够高时，同一窗口不再升级——绝对支付确实进入了比较式。"""

    request = historical("A")
    expensive = (UpgradeRiskCell(1, False, 1.0, 0.10, dealer=True, loss_absolute=10_000.0),
                 UpgradeRiskCell(2, False, 1.0, 0.10, dealer=True, loss_absolute=10_000.0))
    plan = plan_of(V2HuUpgradePolicy(monotonic=lambda: 0, risk_cells=expensive,
                                     risk_version="test"), request)
    assert plan.candidates[0].action_key != "discard:5b"
