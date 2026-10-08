"""95个当前公开typed输入逐根实测；保存前输入、完整重复输出和所有失败。"""

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
import ctypes
import hashlib
import json
import math
import os
import time
from dataclasses import asdict
from pathlib import Path

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.kernel.observation import CompetitionContext
from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
from hangma_bot.policy.action_value_executor import ActionValueExecutor
from hangma_bot.policy.interface import DecisionRequest
from hangma_bot.policy.route_vip_heuristic import build_vip_route_scoring_view
from hangma_bot.offline.scoring_input_capture import ScoringInputCapture, ScoringInputCaptureLimits
from hangma_bot.offline.vip_eoh_generate import VipEohBatch
from common import HERE, ROOT, canonical, pin, save


def main():
    """单后台CPU进程，不访问HTTP或活房审计，不占用续赛所有者。"""
    os.nice(15)
    assert ctypes.CDLL(None).setiopolicy_np(0, 0, 3) == 0
    plan = json.loads((_project_file(_PROJECT_ROOT, HERE / "PLAN.json")).read_text())
    prototypes = json.loads((_project_file(_PROJECT_ROOT, HERE / "PROTOTYPES.json")).read_text())
    files = {**plan["files"], **prototypes["files"], str(Path(__file__)): pin(Path(__file__)), str(_project_file(_PROJECT_ROOT, HERE / "LEGACY-COMPATIBILITY-REPAIR.json")): pin(_project_file(_PROJECT_ROOT, HERE / "LEGACY-COMPATIBILITY-REPAIR.json"))}
    assert all(pin(Path(p)) == h for p, h in files.items())
    assert all(pin(_project_file(_PROJECT_ROOT, ROOT / p)) == h for p, h in plan["source_manifest"].items())
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"))
    paths = {"parent": _project_file(_PROJECT_ROOT, HERE / "parent-source.py"), **{n: _project_file(_PROJECT_ROOT, HERE / "prototypes" / (n + ".py")) for n in plan["first_prototypes"]}}
    executors = {n: ActionValueExecutor(p.read_text(), max_operations=batch.max_operations,
        max_local_collection_size=batch.projection_limits.max_nodes) for n, p in paths.items()}
    cases = json.loads((_project_file(_PROJECT_ROOT, HERE / "CASES.json")).read_text())["cases"]
    out = _project_file(_PROJECT_ROOT, HERE / "mechanism-comparison-v2")
    out.mkdir(exist_ok=False)
    save(out / "START.json", {"files": files, "source_manifest": plan["source_manifest"],
        "planned_views": 95, "planned_actual_scores": 760, "no_strength_or_deadline_admission": True})
    raw = (out / "views.jsonl.gz").open("x+b")
    capture = ScoringInputCapture(raw, limits=ScoringInputCaptureLimits(67108864, 536870912, 128))
    started = time.monotonic()
    rows, attempts, failure, capture_result = [], 0, None, None
    try:
        with (out / "rows.jsonl").open("x") as stream:
            for case in cases:
                row = {"label": case["label"], "root_id": case["root_id"], "classes": case["classes"], "status": "unfinished"}
                try:
                    assert time.monotonic() - started < 900, "单后台诊断超过预留900秒"
                    obs = observation_from_json(case["observation"])
                    key = window_key_from_json(case["window_key"])
                    analysis = HangmaRules(batch.rule_config).analyze(obs, route_limits=batch.route_limits)
                    assert analysis.completeness.value == "complete"
                    legal = {c.action_key for c in analysis.legal_candidates}
                    expected_keys = case.get("legal_action_keys")
                    if expected_keys is None:
                        assert case["label"] in {"historical:old:public:12", "historical:old:public:13", "historical:old:public:14", "historical:old:public:15"}
                        expected_keys = [e["action_key"] for e in case["expected_actual_parent_entries"]]
                        assert len(expected_keys) == len(set(expected_keys))
                    assert legal == set(expected_keys)
                    request = DecisionRequest(obs, CompetitionContext("t185-mechanism", None, None, None, None, (), 0),
                        analysis, case["label"], key.trigger_seq, key, ())
                    view = build_vip_route_scoring_view(request, batch.rule_config, limits=batch.projection_limits)
                    digest = hashlib.sha256(canonical(view.candidate_view())).hexdigest()
                    if case["expected_parent_view_sha256"] is not None:
                        assert digest == case["expected_parent_view_sha256"], "旧开发DTO漂移"
                    receipt = capture.store(view.candidate_view())
                    assert receipt.saved_before_score
                    scores = {}
                    for name, executor in executors.items():
                        outputs, operations = [], []
                        for _ in range(2):
                            attempts += 1
                            score = executor.score_vip_route(view)
                            assert score.status == "SCORED"
                            entries = sorted([{"action_key": e.action_key, "score": e.score, "trace": dict(e.trace)}
                                for e in score.entries], key=lambda e: e["action_key"])
                            assert len(entries) == len(legal) and {e["action_key"] for e in entries} == legal
                            assert all(type(e["score"]) in (int, float) and math.isfinite(e["score"]) for e in entries)
                            assert hashlib.sha256(canonical(view.candidate_view())).hexdigest() == digest
                            outputs.append(entries)
                            operations.append(executor.last_operation_count)
                        assert canonical(outputs[0]) == canonical(outputs[1]) and operations[0] == operations[1]
                        first = sorted(entries, key=lambda e: (-e["score"], e["action_key"]))[0]["action_key"]
                        scores[name] = {"entries": entries, "first": first, "operation_counts": operations}
                    expected = sorted([{"action_key": e["action_key"], "score": e["score"]}
                        for e in case["expected_actual_parent_entries"]], key=lambda e: e["action_key"])
                    actual = [{"action_key": e["action_key"], "score": e["score"]} for e in scores["parent"]["entries"]]
                    assert canonical(expected) == canonical(actual), "父代重算原分不精确"
                    changes = {}
                    for name in plan["first_prototypes"]:
                        pfirst, cfirst = scores["parent"]["first"], scores[name]["first"]
                        p = {e["action_key"]: e["score"] for e in scores["parent"]["entries"]}
                        c = {e["action_key"]: e["score"] for e in scores[name]["entries"]}
                        pgap = (p[pfirst] - p[cfirst]) / max(1.0, abs(p[pfirst]), abs(p[cfirst]))
                        cgap = (c[cfirst] - c[pfirst]) / max(1.0, abs(c[cfirst]), abs(c[pfirst]))
                        changes[name] = {"changed": cfirst != pfirst,
                            "meaningful": cfirst != pfirst and (pgap > 1e-10 or cgap > 1e-10),
                            "parent_normalized_gap": pgap, "prototype_normalized_gap": cgap}
                    row.update(status="complete", view_sha256=digest, capture=asdict(receipt),
                        scores=scores, changes=changes, original_parent_scores_exact=True)
                except BaseException as error:
                    failure = {"type": type(error).__name__, "message": str(error), "label": case["label"]}
                    row.update(status="failed", failure=failure)
                rows.append(row)
                stream.write(canonical(row).decode() + "\n")
                stream.flush()
                print(json.dumps({"case": case["label"], "status": row["status"],
                                  "first": {n: s["first"] for n, s in row.get("scores", {}).items()}}), flush=True)
                if failure is not None:
                    break
    finally:
        try:
            capture_result = capture.finish()
        except BaseException as error:
            failure = failure or {"type": type(error).__name__, "message": str(error)}
        raw.close()
        stable = all(pin(Path(p)) == h for p, h in files.items()) and all(pin(_project_file(_PROJECT_ROOT, ROOT / p)) == h for p, h in plan["source_manifest"].items())
        complete = failure is None and len(rows) == 95 and stable and capture_result["terminal"]["terminal_valid"]
        summary = {name: {"changed": sum(r.get("changes", {}).get(name, {}).get("changed", False) for r in rows),
            "meaningful": sum(r.get("changes", {}).get(name, {}).get("meaningful", False) for r in rows),
            "changed_sources": sorted({r["root_id"] for r in rows if r.get("changes", {}).get(name, {}).get("meaningful", False)})}
            for name in plan["first_prototypes"]}
        save(out / "CLOSURE.json", {"schema": "t185-mechanism-comparison/1", "complete": complete,
            "source_stable": stable, "failure": failure, "actual_score_attempts": attempts,
            "actual_completed_views": sum(r["status"] == "complete" for r in rows),
            "files": files, "source_manifest": plan["source_manifest"], "summary": summary,
            "rows": rows, "capture": capture_result, "elapsed_monotonic_seconds": time.monotonic() - started,
            "normalized_meaningful_change_threshold_is_diagnostic_not_production_tie_rule": 1e-10,
            "strength_or_deadline_admitted": False, "new_model_calls_worlds_tables": 0})
    print({"complete": complete, "failure": failure, "summary": summary}, flush=True)
    if not complete:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
