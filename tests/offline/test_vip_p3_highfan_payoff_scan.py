"""高番支付机会根只按当前本座观察与规则事实选择。"""

import hashlib
import json
from pathlib import Path

import pytest

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.serialization import observation_from_json
from scripts.vip_p3_highfan_payoff_scan import scan
from scripts.vip_p3_payoff_frontier import (
    extract_payoff_frontier, ordinary_discard_one_draw_component,
)


_BASE = Path("review/vip-route-2026-09-30/evidence/p3-highfan-payoff-20260930")


def test_seed_3007_eight_fan_selection_is_pre_outcome_and_reproducible():
    """固定自然牌山只靠当前观察保留首个八番支付根。"""

    report = scan(start_seed=3007, seeds=1, minimum_fan=8)
    assert report["scope"] == "pre_outcome_highfan_payoff_selection_not_outcome_or_probability"
    assert report["scenario_prefix"] == "vip-p3-highfan-payoff"
    root, = report["selected_roots"]
    assert (root["seed"], root["own_draw_index"], root["white_count"]) == (3007, 9, 3)
    assert root["root_id"] == hashlib.sha256(
        repr(observation_from_json(root["observation"])).encode()).hexdigest()
    assert any(action["highest_fan"] == 8
               and action["highest_own_net"] == 192
               and action["high_fan_public_capacity"] == 1
               for action in root["opportunities"])
    saved = json.loads((_BASE / "scan-3001-3100.json").read_text(encoding="utf-8"))
    assert root == next(row for row in saved["selected_roots"] if row["seed"] == 3007)


def test_r18_seed_3704_exposes_rule_anchored_sixteen_fan_wait():
    """自然正控：当前胡 96；弃 6w 后下一普通摸条件均值 194.67。"""

    report = scan(start_seed=3704, seeds=1, minimum_fan=8,
                  reference="r18_frozen")
    root, = report["selected_roots"]
    saved = json.loads((_BASE / "scan-r18-3701-3800.json").read_text(encoding="utf-8"))
    assert root == next(row for row in saved["selected_roots"] if row["seed"] == 3704)
    observation = observation_from_json(root["observation"])
    rules = HangmaRules(RuleConfig("hangma-mvp-v10-public-counts", 1, False))
    limits = ValueAnalysisLimits(max_expansions=8192)
    analysis = rules.analyze(observation, value_limits=limits, route_limits=limits)
    by_key = {candidate.action_key: (candidate, branch)
              for candidate, branch in zip(analysis.legal_candidates,
                                           analysis.conditional_roots)}
    assert extract_payoff_frontier(*by_key["hu"], observation.seat).immediate_hu_net == 96
    candidate, branch = by_key["discard:6w"]
    path, = extract_payoff_frontier(candidate, branch, observation.seat).paths
    assert path.public_capacity_sum == 72
    assert {cell.fan for cell in path.cells} == {8, 16}
    assert sum(cell.public_unseen_count for cell in path.cells if cell.fan == 16) == 1
    assert max(cell.own_net for cell in path.cells) == 384
    component = ordinary_discard_one_draw_component(candidate, branch, observation.seat)
    assert (component.total_public_unseen, component.direct_hu_capacity,
            component.capacity_weighted_own_net) == (72, 72, 14016)
    assert component.conditional_exchangeable_direct_hu_net == pytest.approx(14016 / 72)


def test_probe_freeze_binds_pre_outcome_selection_and_two_actions():
    """反事实结果生成前，根身份、选根文件和两条首动作已经锁定。"""

    frozen = json.loads((_BASE / "probe-freeze.json").read_text(encoding="utf-8"))
    source = Path(frozen["selection_report"])
    assert hashlib.sha256(source.read_bytes()).hexdigest() == frozen["selection_report_sha256"]
    selected = next(row for row in json.loads(source.read_text(encoding="utf-8"))["selected_roots"]
                    if row["seed"] == frozen["seed"])
    assert selected["root_id"] == frozen["root_id"]
    assert frozen["forced_first_actions"] == ["hu", "discard:6w"]
    assert frozen["worlds_per_root"] == 64
    assert frozen["before_outcome_rule_payoff"]["discard_6w_highest_fan"] == 16


@pytest.mark.parametrize("changes", (
    {"start_seed": -1}, {"seeds": 0}, {"reference": "unknown"},
    {"minimum_fan": 2}, {"max_own_draw_index": 0},
))
def test_invalid_scan_scope_is_rejected(changes):
    """配置错误不可静默产生空机会层。"""

    args = {"start_seed": 3007, "seeds": 1, "minimum_fan": 8}
    args.update(changes)
    with pytest.raises(ValueError, match="参数无效"):
        scan(**args)
