"""双白机会结局账必须保留缺口、自然种子聚类与逐世界结算守恒。"""

import copy
import gzip
import json
from pathlib import Path

import pytest

from scripts.vip_p3_multi_opportunity_analysis import analyze


_ROOT = Path("review/vip-route-2026-09-30/evidence/p3-multi-opportunity-20260930")
_FREEZE = _ROOT / "pre-outcome-freeze.json"


def _evidence():
    with gzip.open(_ROOT / "paired-outcomes.json.gz", "rt", encoding="utf-8") as stream:
        teacher = json.load(stream)
    frozen = json.loads(_FREEZE.read_text(encoding="utf-8"))
    return teacher, frozen


def test_opened_teacher_has_complete_paired_roots_and_model_gaps():
    """锁定动作不能只统计跑通的模型根，且不把世界当独立自然桌。"""

    teacher, frozen = _evidence()
    result = analyze(teacher, frozen, _FREEZE)
    assert result == json.loads((_ROOT / "analysis.json").read_text(encoding="utf-8"))
    assert (result["root_count"], result["natural_seed_count"],
            result["teacher_action_worlds"]) == (36, 31, 2432)
    assert result["rule_payoff_checks"] == {"normal_draw_checked": 1606,
                                            "direct_hu_checked": 605}
    assert result["segments"]["all"]["model_gap_roots"] == 4
    assert result["segments"]["all"]["model_gap_seeds"] == 3
    assert result["changed_action_reference_signs"] == {
        "same_sign": 5, "opposite": 4, "one_zero": 4, "both_zero": 0,
    }


def test_opened_teacher_rejects_missing_world_and_false_root_mean():
    """输出摘要不能覆盖逐世界记录里的遗漏或均值不一致。"""

    teacher, frozen = _evidence()
    missing = copy.deepcopy(teacher)
    missing["rows"].pop()
    with pytest.raises(ValueError, match="总数不守恒"):
        analyze(missing, frozen, _FREEZE)
    false_mean = copy.deepcopy(teacher)
    root = false_mean["root_summaries"][0]
    key = root["roles"]["r18"]
    root["references"]["shape"]["actions"][key]["mean_own_net"] += 1
    with pytest.raises(ValueError, match="结算摘要"):
        analyze(false_mean, frozen, _FREEZE)
