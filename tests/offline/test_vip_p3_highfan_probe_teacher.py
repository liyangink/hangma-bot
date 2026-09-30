"""预冻结单根高番探针的相关隐藏世界结局可复算。"""

import json
from collections import Counter
from pathlib import Path

import pytest

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.kernel.actions import Hu
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.serialization import observation_from_json
from scripts.vip_p3_highfan_probe_teacher import audit
from scripts.vip_p3_poststate_value_probe import expected_net, features


_BASE = Path("review/vip-route-2026-09-30/evidence/p3-highfan-payoff-20260930")


def test_frozen_probe_recomputes_and_shows_selected_root_mechanism():
    """两臂共享 64 世界；正差只归此根，不能冒充新 VIP 桌赛。"""

    frozen = json.loads((_BASE / "probe-freeze.json").read_text(encoding="utf-8"))
    report = audit(frozen)
    saved = json.loads((_BASE / "probe-outcomes.json").read_text(encoding="utf-8"))
    assert report == saved
    assert report["scope"] == "opened_single_root_paired_teacher_not_VIP_policy_or_population_gain"
    assert report["row_count"] == 64 * 2 * 2
    assert report["summary"]["shape"]["paired_discard_minus_hu_mean_net"] == 96.0
    assert report["summary"]["r18_frozen"]["paired_discard_minus_hu_mean_net"] == 105.0
    for reference, expected in (("shape", {8: 64}), ("r18_frozen", {8: 61, 16: 3})):
        rows = [row for row in report["rows"]
                if row["continuation_reference"] == reference
                and row["first_action_key"] == "discard:6w"]
        assert Counter(row["terminal"]["fan"] for row in rows) == expected
        assert all(row["terminal_category"] == "self_high" for row in rows)


def test_frozen_probe_rejects_selection_source_drift():
    """若结果盲扫描来源摘要变化，不能继续打开成对结局。"""

    frozen = json.loads((_BASE / "probe-freeze.json").read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="来源摘要漂移"):
        audit({**frozen, "selection_report_sha256": "0" * 64})


def test_rejected_poststate_model_still_misses_sixteen_fan_route():
    """规则锚点 194.67 与已否证模型约 49 分分离，当前胡规则分 96。"""

    selection = json.loads((_BASE / "scan-r18-3701-3800.json").read_text(encoding="utf-8"))
    row = next(row for row in selection["selected_roots"] if row["seed"] == 3704)
    observation = observation_from_json(row["observation"])
    rules = HangmaRules(RuleConfig("hangma-mvp-v10-public-counts", 1, False))
    limits = ValueAnalysisLimits(max_expansions=8192)
    analysis = rules.analyze(observation, value_limits=limits, route_limits=limits)
    model = json.loads((Path("review/vip-route-2026-09-30/evidence/") /
                        "p3-poststate-value-20260930/train-model.json").read_text(encoding="utf-8"))
    estimates = {}
    for candidate, root in zip(analysis.legal_candidates, analysis.conditional_roots):
        if candidate.action_key in ("hu", "discard:6w"):
            x, exact = features(candidate, root, observation)
            estimates[candidate.action_key] = (exact if isinstance(candidate.action, Hu)
                                               else expected_net(x, model)[0])
    assert estimates["hu"] == 96.0
    assert estimates["discard:6w"] == pytest.approx(49.37225137440652)
    assert estimates["discard:6w"] < estimates["hu"]
