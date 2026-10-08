"""完整结果核验的反例测试；只构造契约夹具，零模型和零模拟桌赛。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import copy
import json

import pytest

from verify_full_natural_results import natural, stage, verify_full_table
from hangma_bot.kernel.serialization import tournament_config_to_json


def fixture():
    """构造与冻结赛程一致的合成完整结果，不标成真实执行证据。"""
    contract = json.loads((natural.REPO / natural.DEFAULT_CONTRACT).read_text())
    versions = stage.contract_versions_block(contract)
    plan = natural.build_seat_stage_plans(contract=contract, opponent="H", root_index=1,
             focal_seat=2, panel_seed=2026091913)[0]
    config = natural.TournamentConfig(max_games=1, rounds_per_game=versions["rounds_per_game"],
        rules=natural.RuleConfig(ruleset_version=versions["ruleset_version"],
              base_score=versions["base_score"], you_cai_bi_kao=versions["you_cai_bi_kao"]),
        timing=natural.TimingConfig(**dict(stage.DEFAULT_TIMING)))
    result = {"evaluation_schema_version": 1, "result_id": "r-" + plan.match_id,
        "source_kind": "simulation", "scenario_id": plan.scenario_id, "pair_id": plan.pair_id,
        "game_key": {"source_namespace": "hangma-simulation", "tournament_id": plan.scenario_id,
                     "game_id": plan.match_id}, "config": tournament_config_to_json(config),
        "policy_ids_by_seat": list(plan.seats()), "seat_permutation": list(plan.permutation),
        "expected_hands": versions["rounds_per_game"], "completed_hands": versions["rounds_per_game"],
        "scores_before": [0, 0, 0, 0], "scores_after": [12, -4, -4, -4], "official_ranks": None,
        "status": "complete", "invalid_reasons": [], "runtime_counts": {
            "timeouts": 0, "illegal_choices": 0, "fallbacks": 0, "auto_actions": 0, "audit_missing": 0},
        "versions": {"rules_hash": "fixture-rules", "clock_mode": versions["clock_mode"]},
        "source_refs": [{"note": "synthetic unit fixture, not executed"}]}
    return {"scores_by_seat": [12, -4, -4, -4], "result": result}, plan, contract


def test_complete_fixture_and_nonzero_runtime_counts_are_reported():
    table, plan, contract = fixture()
    table["result"]["runtime_counts"]["fallbacks"] = 2
    result = verify_full_table(table, plan, contract, "fixture-rules")
    assert result["runtime_counts"]["fallbacks"] == 2


@pytest.mark.parametrize("path,value", [
    (("result",), None), (("result",), {}),
    (("result", "status"), "partial"),
    (("result", "source_kind"), "mock"),
    (("result", "expected_hands"), 1),
    (("result", "completed_hands"), 0),
    (("result", "completed_hands"), 999),
    (("result", "completed_hands"), True),
    (("result", "invalid_reasons"), ["interrupted"]),
    (("result", "scores_before"), [1, -1, 0, 0]),
    (("result", "scores_after"), [0, 0, 0, 0]),
    (("result", "scores_after"), [True, 0, 0, -1]),
    (("result", "policy_ids_by_seat"), ["wrong"] * 4),
    (("result", "seat_permutation"), [1, 2, 3, 0]),
    (("result", "result_id"), "wrong-result"),
    (("result", "pair_id"), "wrong-pair"),
    (("result", "game_key", "game_id"), "wrong-match"),
    (("result", "versions", "rules_hash"), "wrong-rules"),
    (("result", "versions", "clock_mode"), "wall"),
    (("result", "runtime_counts"), None),
    (("result", "runtime_counts", "timeouts"), True),
    (("result", "runtime_counts", "timeouts"), None),
    (("result", "official_ranks"), [1, 2, 3, 4]),
    (("result", "config"), None),
    (("result", "config", "max_games"), 2),
    (("result", "config", "timing", "discard_timeout_sec"), 30.0),
    (("result", "config", "rules", "base_score"), 2),
    (("result", "config", "rules", "you_cai_bi_kao"), True),
])
def test_bad_full_results_rejected(path, value):
    table, plan, contract = fixture()
    target = table
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = copy.deepcopy(value)
    with pytest.raises((ValueError, TypeError)):
        verify_full_table(table, plan, contract, "fixture-rules")


def test_complete_result_cannot_shorten_both_plan_and_actual_counts():
    table, plan, contract = fixture()
    table["result"].update(expected_hands=1, completed_hands=1)
    with pytest.raises(ValueError):
        verify_full_table(table, plan, contract, "fixture-rules")
