"""32目标全部自然结束后核原件；历史世界和条件抽样分账，不授总体强度。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t186-incremental-opportunity-repair-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import fcntl
import importlib.util
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1')
sys.path.insert(0, str(PRIOR))
from common import pin, save
from evaluation_sharding import resource_slot_paths
from t185_prepare_confirmation import background_priority, postprocess_lock
from reuse_causal_helpers import unchanged

# 复用已经闭合的输入逐字节核对和规则结算分账，不实现另一套评分或番型。
SPEC = importlib.util.spec_from_file_location("closed_condition_audit", _project_file(_PROJECT_ROOT, HERE / "close_opportunity_probe-v2.py"))
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


def category(delta):
    """仅表示同一起点父子净分差的正负，不称作策略胜率。"""
    return "positive" if delta > 0 else "negative" if delta < 0 else "equal"


def summarize(pairs):
    """目标等权与来源分组均保留；换座和多窗口相关，不给独立样本区间。"""
    sums, outcomes, groups = Counter(), Counter(), defaultdict(list)
    for row in pairs:
        sums.update(row["C_minus_A"])
        outcomes[category(row["C_minus_A"]["net"])] += 1
        groups[row["root_id"]].append(row)
    roots = []
    for root, rows in sorted(groups.items()):
        totals = Counter()
        for row in rows:
            totals.update(row["C_minus_A"])
        roots.append({"root_id": root, "paired_continuations": len(rows),
            "targets": sorted(set(r["target"] for r in rows)), "sum_C_minus_A": dict(totals),
            "mean_C_minus_A": {k: v / len(rows) for k, v in totals.items()}})
    return {"paired_continuations": len(pairs), "sum_C_minus_A": dict(sums),
        "outcomes": dict(outcomes), "source_groups": roots,
        "equal_source_mean_C_minus_A": {k: sum(r["mean_C_minus_A"].get(k, 0) for r in roots) / len(roots)
            for k in sums} if roots else {},
        "natural_population_estimate": False, "independent_strength_admission": False}


def main():
    """闭合资源、实际评分与全部结果后只读分析；不补抽、不启动桌赛。"""
    background_priority()
    planpath = _project_file(_PROJECT_ROOT, HERE / "JOINT-REVISION-CONDITION-PLAN.json")
    plan = json.loads(planpath.read_text())
    out = _project_file(_PROJECT_ROOT, HERE / "joint-revision-condition")
    output = _project_file(_PROJECT_ROOT, HERE / "JOINT-REVISION-CONDITION-CLOSED.json")
    assert not output.exists()
    dispatch = json.loads((out / "DISPATCH-CLOSED.json").read_text())
    assert dispatch["complete"] and dispatch["worker_returncodes"] == [0] * 4
    assert dispatch["all_processes_naturally_waited"] and dispatch["plan_pin"] == pin(planpath)
    assert unchanged(plan) and len(plan["targets"]) == 32
    for path in resource_slot_paths(AUDIT.OLD, 4):
        with path.open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    files = {str(out / "DISPATCH.json"): pin(out / "DISPATCH.json"),
             str(out / "DISPATCH-CLOSED.json"): pin(out / "DISPATCH-CLOSED.json")}
    for slot in range(4):
        directory = out / f"worker-{slot}"
        start, close = (json.loads((directory / name).read_text()) for name in ("START.json", "CLOSE.json"))
        assert close["complete"] and close["failure"] is None
        assert close["completed"] == close["attempted"] == start["targets"] == list(range(slot + 1, 33, 4))
        assert start["pid"] == close["pid"] == dispatch["children"][slot]
        assert start["plan_pin"] == pin(planpath)
        for name in ("START.json", "CLOSE.json"):
            files[str(directory / name)] = pin(directory / name)
    counts, pairs, targets = Counter(), [], []
    for index, target in enumerate(plan["targets"], 1):
        directory = out / f"target-{index:03d}"
        start, closure = (json.loads((directory / name).read_text()) for name in ("START.json", "CLOSURE.json"))
        assert start["plan_pin"] == pin(planpath) and start["target"] == closure["target"] == target
        assert closure["complete"] and closure["source_stable"] and closure["failure"] is None
        assert closure["counts"]["new_origin_worlds"] == 1
        assert closure["counts"]["hidden_samples"] == 4 and closure["counts"]["single_hand_dispatched"] == 10
        assert len(closure["results"]) == 10
        assert json.loads((directory / "RECOVERY.json").read_text())["full_public_observation_and_legal_set_exact"]
        checked = AUDIT.verify_scores(directory, closure, plan)
        counts.update(closure["counts"])
        local = []
        for sample in range(5):
            results = [r for r in closure["results"] if r["sample"] == sample]
            assert len(results) == 2 and {r["arm"] for r in results} == {"A", "C"}
            assert len({r["sample_key"] for r in results}) == 1
            accounts = {}
            for result in results:
                arm = result["arm"]
                assert result["forced_count"] == 0
                assert result["first_actual"] == target["parent_first" if arm == "A" else "candidate_first"]
                raw = json.loads((directory / f"sample-{sample}-{arm}-OUTCOME.json").read_text())
                assert raw["status"] == "complete"
                assert raw["completed_hands"] == target["case"]["window_key"]["round_no"]
                assert all(type(v) is int and v == 0 for v in raw["runtime_counts"].values())
                accounts[arm] = AUDIT.account(result, target["focal_seat"])
            row = {"target": index, "root_id": target["case"]["root_id"], "label": target["case"]["label"],
                "classes": target["case"]["classes"], "sample": sample,
                "world_kind": "historical_exposed" if sample == 0 else "public_compatible_uniform",
                "accounts": accounts, "C_minus_A": {k: accounts["C"][k] - accounts["A"][k] for k in accounts["A"]},
                "actual_focal_fans": {r["arm"]: r["settlement"]["fan"] if r["settlement"]["winner_seat"] == target["focal_seat"] else None
                    for r in results}}
            local.append(row)
            pairs.append(row)
        targets.append({"target": index, "root_id": target["case"]["root_id"], "label": target["case"]["label"],
            "selection": target["selection"], "classes": target["case"]["classes"],
            "parent_first": target["parent_first"], "candidate_first": target["candidate_first"],
            "historical": local[0], "four_conditional": summarize(local[1:]), "audit": checked})
        for path in directory.iterdir():
            if path.is_file():
                files[str(path)] = pin(path)
    assert counts["new_origin_worlds"] == 32 and counts["hidden_samples"] == 128
    assert counts["single_hand_dispatched"] == plan["planned_single_hand_continuations"] == 320
    assert len(pairs) == 160 and unchanged(plan) and dispatch["plan_pin"] == pin(planpath)
    historical = summarize([r for r in pairs if r["sample"] == 0])
    conditional = summarize([r for r in pairs if r["sample"] > 0])
    wait_lost = [r for r in pairs if "wait_lost" in r["classes"]]
    save(output, {"schema": "t186-joint-revision-condition-closed/1", "complete": True,
        "plan_pin": pin(planpath), "reader_pin": pin(Path(__file__)),
        "reused_reader_pin": pin(_project_file(_PROJECT_ROOT, HERE / "close_opportunity_probe-v2.py")),
        "counts": dict(counts), "target_summaries": targets, "comparisons": pairs, "files": files,
        "historical_exposed": historical, "public_compatible_uniform": conditional,
        "historical_wait_lost_controls": summarize([r for r in wait_lost if r["sample"] == 0]),
        "conditional_wait_lost_controls": summarize([r for r in wait_lost if r["sample"] > 0]),
        "source_stable": True, "actual_cpu_workers": 4, "resources_released": True,
        "official_deadline_or_natural_strength_admission": False,
        "historical_and_conditional_not_pooled": True, "multiple_rotations_windows_not_independent": True,
        "additional_scores_worlds_tables_models_HTTP_at_readback": 0,
        "automatic_next_phase_dispatch": False})
    print(json.dumps({"complete": True, "counts": dict(counts),
        "historical": {k: historical[k] for k in ("paired_continuations", "sum_C_minus_A", "outcomes")},
        "conditional": {k: conditional[k] for k in ("paired_continuations", "sum_C_minus_A", "outcomes")}}, ensure_ascii=False))


if __name__ == "__main__":
    with postprocess_lock("T186-joint-revision-condition-readback"):
        main()
