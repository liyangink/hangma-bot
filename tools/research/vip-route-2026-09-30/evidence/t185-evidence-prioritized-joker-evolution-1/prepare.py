"""首作者调用前冻结95窗、比较基线、初批额度与互不重复的新来源种子。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import json
import secrets
from collections import Counter
from pathlib import Path

from hangma_bot.offline.vip_eoh_generate import VipEohBatch
from hangma_bot.policy.action_value_executor import ActionValueExecutor
from common import HERE, ROOT, OLD, canonical, pin, save


def official_case(path, seq, label, classes):
    """只取指定原输入与原完整评分，不用未来事件构造线上特征。"""
    records = [json.loads(line) for line in path.open()]
    inputs = [r for r in records if r["kind"] == "decision_input" and r["payload"]["request"]["trigger_seq"] == seq]
    assert len(inputs) == 1
    request = inputs[0]["payload"]["request"]
    plans = [r for r in records if r["kind"] == "decision_planned" and r["payload"]["trigger_seq"] == seq]
    assert len(plans) == 1 and not plans[0]["payload"]["filter_reasons"] and not plans[0]["payload"]["degraded_reasons"]
    scores = plans[0]["payload"]["returned_plan"]["candidates"]
    assert scores and all(type(c["total_score"]) in (float, int) for c in scores)
    return {"label": label, "root_id": request["observation"]["game_id"].split("_r1_")[0],
        "scope": "deliberate_official_diagnostic_anchor_not_confirmation",
        "classes": classes, "observation": request["observation"], "window_key": request["window_key"],
        "legal_action_keys": sorted(c["action_key"] for c in scores),
        "expected_parent_view_sha256": None,
        "expected_actual_parent_entries": [{"action_key": c["action_key"], "score": c["total_score"]} for c in scores],
        "source_closure": str(path), "source_pin": pin(path)}


def main():
    """不生成世界、不评分、不调用API；预留完整桌来源与选优判据。"""
    old_batch = json.loads((OLD / "AUTHOR-BATCH.json").read_text())
    old_batch["batch_id"] = "t185-four-author-joker-realization-20261005"
    old_batch["budgets"] = {"model_calls": 4, "input_tokens": 4 * 1048576,
                            "output_tokens": 4 * 65536, "table_instances": 0,
                            "wall_clock_seconds": 4 * 900}
    save(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"), old_batch)
    source = (OLD / "parent-source.py").read_bytes()
    with (_project_file(_PROJECT_ROOT, HERE / "parent-source.py")).open("xb") as stream:
        stream.write(source)
    with (_project_file(_PROJECT_ROOT, HERE / "glm_max_transport.py")).open("xb") as stream:
        stream.write((OLD / "glm_max_transport.py").read_bytes())
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"))
    identity = batch.identity(source.decode())
    ActionValueExecutor(source.decode(), max_operations=batch.max_operations,
                        max_local_collection_size=batch.projection_limits.max_nodes)
    files = [_project_file(_PROJECT_ROOT, HERE / n) for n in ("README.md", "common.py", "prepare.py", "AUTHOR-BATCH.json", "parent-source.py", "glm_max_transport.py")]
    cases = []
    for name in ("mechanism-comparison", "mechanism-comparison-supplement"):
        path = OLD / name / "CLOSURE.json"
        panel = json.loads(path.read_text())
        assert panel["complete"] and panel["source_stable"]
        rows = {r["label"]: r for r in panel["rows"]}
        for c in panel["cases"]:
            case = dict(c)
            case["expected_parent_view_sha256"] = rows[c["label"]]["view_sha256"]
            case["expected_actual_parent_entries"] = rows[c["label"]]["scores"]["parent"]["entries"]
            cases.append(case)
        files.append(path)
    assert len(cases) == 93
    cases.append(official_case(_project_file(_PROJECT_ROOT, HERE.parent / "t184-white-strata-and-strong-gap-1/OPENING-ORIGINAL-AUDIT.jsonl"), 0,
        "anchor:early-one-white-route-speed", ["early_one_white", "route_speed_opportunity"]))
    cases.append(official_case(_project_file(_PROJECT_ROOT, HERE.parent / "t183-baotou-wait-case-a40864715552-1/WINDOW-AUDIT.jsonl"), 644,
        "anchor:mature-baotou-current-hu", ["current_hu", "mature_same_pay_continuation"]))
    assert len({c["label"] for c in cases}) == 95
    for c in cases[-2:]:
        files.append(Path(c["source_closure"]))
    save(_project_file(_PROJECT_ROOT, HERE / "CASES.json"), {"cases": cases, "selection": "93 frozen development windows plus two explicitly targeted original-audit anchors",
        "hidden_or_future_labels_in_author_input": False, "confirmation": False})
    files.append(_project_file(_PROJECT_ROOT, HERE / "CASES.json"))
    # 保留全部旧数字作碰撞排除；不读取旧世界、终态或收益。
    old_roots_file = OLD / "FRESH-ROOTS-BEFORE-AUTHOR.json"
    old_roots = json.loads(old_roots_file.read_text())
    occupied = set()
    def numbers(v):
        if type(v) is int:
            occupied.add(v)
        elif isinstance(v, dict):
            for item in v.values():
                numbers(item)
        elif isinstance(v, list):
            for item in v:
                numbers(item)
    numbers(old_roots)
    pools = {}
    for name, count in (("diagnostic_fresh", 8), ("development", 32), ("confirmation", 128)):
        pools[name] = []
        for index in range(count):
            seed = secrets.randbits(63)
            while seed in occupied:
                seed = secrets.randbits(63)
            occupied.add(seed)
            pools[name].append({"root_id": f"t185-{name}-{index + 1:03d}", "world_seed": seed})
    save(_project_file(_PROJECT_ROOT, HERE / "FRESH-ROOTS-BEFORE-AUTHOR.json"), {"pools": pools,
        "scope": "source_descriptors_only_no_world_generated", "old_roots_pin": pin(old_roots_file),
        "old_scores_or_walls_read": False, "all_pools_disjoint": True})
    files.append(_project_file(_PROJECT_ROOT, HERE / "FRESH-ROOTS-BEFORE-AUTHOR.json"))
    save(_project_file(_PROJECT_ROOT, HERE / "PLAN.json"), {"schema": "t185-joker-realization-plan/1", "baseline_identity": identity,
        "files": {str(p): pin(p) for p in files}, "source_manifest": identity["source_manifest"],
        "diagnostic_windows": 95, "diagnostic_sources": len({c["root_id"] for c in cases}),
        "classes": dict(Counter(k for c in cases for k in c["classes"])),
        "original_anchor_selection_deliberate": True, "development_not_confirmation": True,
        "first_prototypes": ["speed", "incremental_wait", "joint"], "maximum_model_calls": 4,
        "development": {"roots": 32, "rotations": [0, 1, 2, 3], "rounds_per_table": 8, "maximum_candidates": 3,
            "max_table_instances": 512, "weak_opponent_fraction": 0.6,
            "selection": "highest positive paired-root-mean with at least two positive roots; tie by candidate_id"},
        "confirmation": {"roots": 128, "rotations": [0, 1, 2, 3], "rounds_per_table": 8, "candidates": 1,
            "table_instances": 1024, "minimum_mean_points_per_complete_table": 0.5,
            "bootstrap": {"replicates": 20000, "seed": 20261005, "cluster": "source four-seat mean", "lower_bound_strictly_above": 0.0},
            "ordinary_loss_can_be_covered_by_high_pay_net_gain": True},
        "resources": {"light_diagnostic_cpu_workers": 1, "cpu_nice": 15, "macos_io_policy": 3,
            "new_full_table_workers_before_t182_closed_and_resources_released": 0, "later_max_full_table_workers": 2,
            "official_live_owner_unchanged": True},
        "failure": "freeze original error, inspect decomposition and evidence before another bounded batch; no blind calls",
        "new_calls_scores_worlds_tables": 0, "new_candidate_admitted": False})
    print({"prepared": True, "windows": 95, "fresh_sources_reserved": 168, "new_model_calls": 0}, flush=True)


if __name__ == "__main__":
    main()
