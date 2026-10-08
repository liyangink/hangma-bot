"""坐隐 1.5 S0 自测：守住 P4 的真实评测链判据。

**为什么必须守**：P4 初版的通过条件只有 `sd_root is not None`，等于没检查——
16 个根组交替取 -1/+1（均值 0、sd 约 1.03）也能通过。本轮又在预登记里写错一次
（把"`|delta| > 区间半宽`"当成"`|delta| > MDE`"的等价物）。因此判据必须有测试钉住。

本文件只测 P4 的**判定逻辑**，不跑真实桌赛：用合成 results.jsonl 构造已知识别结果。
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/tools'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import importlib.util
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, _REPO / "src")))

_spec_power = importlib.util.spec_from_file_location("sitin_power", _project_file(_PROJECT_ROOT, _HERE / "sitin_power.py"))
sitin_power = importlib.util.module_from_spec(_spec_power)
sys.modules["sitin_power"] = sitin_power
assert _spec_power.loader is not None
_spec_power.loader.exec_module(sitin_power)

_spec = importlib.util.spec_from_file_location("sitin_s0", _project_file(_PROJECT_ROOT, _HERE / "sitin_s0.py"))
s0 = importlib.util.module_from_spec(_spec)
sys.modules["sitin_s0"] = s0
assert _spec.loader is not None
_spec.loader.exec_module(s0)

BASELINE = "p4_baseline_v2"
CHALLENGER = "p4_control_shanten_neg"
OPPONENTS = ["opp-0", "opp-1", "opp-2"]
ROOTS = ["scale-{0}".format(i) for i in range(16)]


def _row(scenario, arm, tested_seat, test_score):
    """构造一条与真实产物同形的结果行；只在被测座位放 arm 身份。"""

    policy_ids = list(OPPONENTS)
    policy_ids.insert(tested_seat, arm)
    scores = [0, 0, 0, 0]
    scores[tested_seat] = test_score
    return {
        "status": "complete",
        "source_kind": "simulation",
        "scenario_id": scenario,
        "pair_id": "{0}:0123".format(scenario),
        "result_id": "r-p4:{0}:0123:{1}".format(scenario, arm),
        "game_key": {"game_id": "p4:{0}:0123:{1}".format(scenario, arm),
                     "source_namespace": "hangma-simulation", "tournament_id": scenario},
        "policy_ids_by_seat": policy_ids,
        "scores_after": scores,
        "scores_before": [0, 0, 0, 0],
        # 本工具要求带换座标识才能校验"同根换座一致性"，缺它整行会被排除
        "seat_permutation": [0, 1, 2, 3],
        "completed_hands": 8,
        "expected_hands": 8,
        "invalid_reasons": [],
        "versions": {"contract_id": "parallel-v1", "driver": "test",
                     "policy_ids": sorted(policy_ids), "rules_hash": "deadbeef",
                     "ruleset_version": "test", "simulation_version": None},
    }


def _write(tmp_path, deltas):
    """写出 results.jsonl 与 experiment.json；deltas 是逐根的（候选减基线）意图值。"""

    rows = []
    for scenario, delta in zip(ROOTS, deltas):
        rows.append(_row(scenario, BASELINE, 0, 0))
        rows.append(_row(scenario, CHALLENGER, 0, int(delta)))
    results = tmp_path / "results.jsonl"
    results.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                       encoding="utf-8")
    experiment = tmp_path / "experiment.json"
    experiment.write_text(json.dumps({
        "kind": "matches",
        "baseline_policy": {"policy_id": BASELINE, "name": "weighted_heuristic_v2", "weights": {}},
        "challenger_policy": {"policy_id": CHALLENGER, "name": "weighted_heuristic_v2",
                              "weights": {"shanten_step": -100.0}},
        "seeds": [{"seed": 2026092000 + i, "scenario_id": s} for i, s in enumerate(ROOTS)],
    }, ensure_ascii=False), encoding="utf-8")
    return results, experiment

def test_missing_results_is_not_executed(tmp_path):
    """产物不存在时必须报 NOT_EXECUTED，不得报 PASS（三态纪律）。"""

    result = s0.check_p4_real_chain(tmp_path / "nope.jsonl", tmp_path / "exp.json")
    assert result["status"] == "NOT_EXECUTED"
    assert result["detail"]


def test_control_clearly_worse_passes_all_criteria(tmp_path):
    deltas = [-40.0, -60.0, -20.0, -80.0, -50.0, -30.0, -70.0, -45.0,
              -55.0, -35.0, -65.0, -25.0, -75.0, -42.0, -58.0, -48.0]
    results, experiment = _write(tmp_path, deltas)
    result = s0.check_p4_real_chain(results, experiment)
    assert result["status"] == "PASS", result
    assert result["criteria"]["R1 方向为负"]["pass"] is True
    assert result["criteria"]["R2 区间排除零"]["pass"] is True
    assert result["criteria"]["R4 多数根组上更差"]["pass"] is True
    assert result["reversed_direction_alarm"] is False


def test_control_better_fails_and_raises_direction_alarm(tmp_path):
    """方向反了说明评测链有系统性错误，必须 FAIL 并报警，不得当成没有差异。"""

    results, experiment = _write(tmp_path, [50.0] * 16)
    result = s0.check_p4_real_chain(results, experiment)
    assert result["status"] == "FAIL"
    assert result["criteria"]["R1 方向为负"]["pass"] is False
    assert result["reversed_direction_alarm"] is True

def test_small_effect_that_old_criterion_would_pass_is_rejected(tmp_path):
    """**本文件存在的理由**：均值非零、sd 存在的小效应必须判 FAIL。

    这正是 P4 初版通过条件（只有 `sd_root is not None`）会放过的形状：
    均值非零、sd 也存在，旧判据照过。新判据要求效应超过本批 MDE，故必须 FAIL。
    """

    # 12 根 -60、4 根 +80 ⇒ 均值 -25、sd≈62.6 ⇒ MDE≈43.8 > 25
    deltas = [-60.0] * 12 + [80.0] * 4
    results, experiment = _write(tmp_path, deltas)
    result = s0.check_p4_real_chain(results, experiment)
    assert result["status"] == "FAIL", result
    assert result["criteria"]["R3b 效应大于 MDE（事后补强，更严格）"]["pass"] is False
    assert result["roots"] == 16


def test_few_roots_fails(tmp_path):
    results, experiment = _write(tmp_path, [-40.0])
    result = s0.check_p4_real_chain(results, experiment)
    assert result["status"] == "FAIL"
    assert "根组数不足" in result["detail"]


def test_root_bootstrap_ci_is_reproducible_and_clusters_on_roots():
    values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
    first = s0._root_bootstrap_ci(values)
    second = s0._root_bootstrap_ci(values)
    assert first == second, "固定种子下区间必须可复现"
    lo, hi = first
    mean = sum(values) / len(values)
    assert lo < mean < hi
    # 单位是根组：区间应明显窄于全体取值范围，而不是把 [min, max] 全包住
    assert (hi - lo) < (max(values) - min(values))
