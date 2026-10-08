"""一次完整旧公开面板资格；复用逐字核同的图，不生成条件世界。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import ctypes
import fcntl
import gzip
import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t188-joint-score-mechanism-1')
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, HERE / "mechanical/tools")))
from minimal_mechanisms import canonical, pin, save, typed
from hangma_bot.offline.vip_eoh_generate import VipEohBatch
from hangma_bot.policy.action_value_executor import ActionValueExecutor


def main():
    """真实合法根、确定性与原输入逐项核查；不授强度或官方时限。"""
    if os.getpriority(os.PRIO_PROCESS, 0) < 15:
        os.nice(15 - os.getpriority(os.PRIO_PROCESS, 0))
    assert ctypes.CDLL(None).setiopolicy_np(0, 0, 3) == 0
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "EXECUTION-BATCH.json"))
    source_file = _project_file(_PROJECT_ROOT, HERE / "candidates/speed/source.py")
    source = source_file.read_text()
    identity = batch.identity(source)
    gate_file = source_file.parent / "MECHANICAL-CLOSED.json"
    gate = json.loads(gate_file.read_text())
    assert gate["mechanical_passed"] and gate["identity"] == identity
    case_file = _project_file(_PROJECT_ROOT, HERE.parent / "t187-family-combination-evolution-1/EXPLORATION-QUALIFICATION-PLAN.json")
    later_file = _project_file(_PROJECT_ROOT, PRIOR / "LATER-QUALIFICATION-CASES.json")
    cache_file = _project_file(_PROJECT_ROOT, PRIOR / "qualification/views.jsonl.gz")
    old_closed = json.loads((_project_file(_PROJECT_ROOT, PRIOR / "qualification/CLOSED.json")).read_text())
    assert old_closed["complete"] and old_closed["source_stable"] and old_closed["actual_completed_views"] == 363
    assert pin(cache_file)["sha256"] == old_closed["capture"]["terminal"]["compressed_sha256"]
    cases = json.loads(case_file.read_text())["cases"] + json.loads(later_file.read_text())["cases"]
    assert len(cases) == len({c["label"] for c in cases}) == 363
    files = [Path(__file__), _project_file(_PROJECT_ROOT, HERE / "mechanical/tools/minimal_mechanisms.py"), _project_file(_PROJECT_ROOT, HERE / "EXECUTION-BATCH.json"),
        source_file, gate_file, _project_file(_PROJECT_ROOT, HERE / "parent-source.py"), case_file, later_file, cache_file, _project_file(_PROJECT_ROOT, PRIOR / "qualification/CLOSED.json")]
    frozen = {str(p): pin(p) for p in files}
    with (_project_file(_PROJECT_ROOT, HERE.parent / "t182-step12-diagnosis-and-joint-evolution-1/.resource-scheduling-worker-0.lock")).open("r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        out = _project_file(_PROJECT_ROOT, HERE / "speed-qualification")
        out.mkdir(exist_ok=False)
        save(out / "START.json", {"identity": identity, "files": frozen, "planned_views": 363,
            "planned_candidate_scores": 726, "planned_parent_scores": 363, "CPU_nice": os.getpriority(os.PRIO_PROCESS, 0),
            "reuse_complete_public_graphs": True, "new_worlds_or_tables": 0})
        views = {}
        with gzip.open(cache_file, "rt") as stream:
            for line in stream:
                item = json.loads(line)
                if item.get("schema") == "vip-scoring-input-view/1":
                    digest = hashlib.sha256(canonical(item["view"])).hexdigest()
                    assert digest == item["view_sha256"] and digest not in views
                    views[digest] = item["view"]
        candidate = ActionValueExecutor(source, max_operations=batch.max_operations,
            max_local_collection_size=batch.projection_limits.max_nodes)
        parent = ActionValueExecutor((_project_file(_PROJECT_ROOT, HERE / "parent-source.py")).read_text(), max_operations=batch.max_operations,
            max_local_collection_size=batch.projection_limits.max_nodes)
        rows, calls, failed, operations, failure = [], 0, 0, [], None
        started = time.monotonic()

        def score(executor, view):
            nonlocal calls, failed
            calls += 1
            answer = executor.score_vip_route(view)
            if answer.status != "SCORED":
                failed += 1
                raise ValueError("实际评分失败:" + answer.status)
            entries = sorted([{"action_key": e.action_key, "score": e.score, "trace": dict(e.trace)}
                for e in answer.entries], key=lambda e: e["action_key"])
            assert {e["action_key"] for e in entries} == {a.action_key for a in view.actions}
            assert len(entries) == len(view.actions) and all(type(e["score"]) in (int, float) and math.isfinite(e["score"]) for e in entries)
            return entries, executor.last_operation_count

        try:
            with (out / "rows.jsonl").open("x") as result:
                for case in cases:
                    digest = case["view_sha256"]
                    view = typed(views[digest], case, batch)
                    before = canonical(view.candidate_view())
                    original, _ = score(parent, view)
                    first, count = score(candidate, view)
                    repeat, count2 = score(candidate, view)
                    assert first == repeat and count == count2 and count <= batch.max_operations
                    assert canonical(view.candidate_view()) == before
                    operations.append(count)
                    chosen = lambda data: sorted(data, key=lambda e: (-e["score"], e["action_key"]))[0]["action_key"]
                    row = {"label": case["label"], "root_id": case["root_id"], "view_sha256": digest,
                        "parent_first": chosen(original), "candidate_first": chosen(first), "entries": first,
                        "changed": chosen(original) != chosen(first), "operations": count}
                    rows.append(row)
                    result.write(canonical(row).decode() + "\n")
        except BaseException as error:
            failure = {"type": type(error).__name__, "message": str(error)}
        stable = all(pin(Path(p)) == expected for p, expected in frozen.items())
        complete = failure is None and stable and len(rows) == 363 and calls == 1089 and failed == 0
        save(out / "CLOSED.json", {"complete": complete, "mechanical_passed": complete, "source_stable": stable,
            "failure": failure, "identity": identity, "files": frozen, "rows_pin": pin(out / "rows.jsonl"),
            "actual_public_views": len(rows), "actual_score_calls": calls, "actual_failed_score_calls": failed,
            "minimum_operations": min(operations) if operations else None, "maximum_operations": max(operations) if operations else None,
            "changed_views": sum(r["changed"] for r in rows),
            "changed_sources": sorted({r["root_id"] for r in rows if r["changed"]}),
            "elapsed_monotonic_seconds": time.monotonic() - started,
            "new_worlds_tables_models_HTTP": 0, "strength_or_original_deadline_or_online_admission": False})
        assert complete, failure
        print(json.dumps({"complete": True, "public_views": len(rows), "actual_scores": calls,
            "changed_views": sum(r["changed"] for r in rows), "maximum_operations": max(operations)}))


if __name__ == "__main__":
    main()
