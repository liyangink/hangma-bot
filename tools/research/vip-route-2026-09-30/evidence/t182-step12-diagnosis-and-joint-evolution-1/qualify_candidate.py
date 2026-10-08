"""新作者提案的完整93窗机械／行为门；未过门不给完整桌成绩或线上身份。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t182-step12-diagnosis-and-joint-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import argparse
import ctypes
import fcntl
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
from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents
from prepare_diagnostics import pin, save
from run_diagnostic_sources import canonical

HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT


def main(package):
    """typed图由当前唯一规则模块构建；同输入评分两次，完整数值／解释精确。"""
    os.nice(15)
    assert ctypes.CDLL(None).setiopolicy_np(0, 0, 3) == 0
    package = Path(package).resolve()
    assert package.parent == HERE
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"))
    proposal = load_vip_parents([package], batch)[0]
    assert proposal["artifact_role"] == "candidate_proposal"
    source = proposal["source"]
    executor = ActionValueExecutor(source, max_operations=batch.max_operations,
                                  max_local_collection_size=batch.projection_limits.max_nodes)
    panels = [json.loads((_project_file(_PROJECT_ROOT, HERE / d / "CLOSURE.json")).read_text()) for d in
              ("mechanism-comparison", "mechanism-comparison-supplement")]
    assert all(p["complete"] for p in panels)
    cases = [c for p in panels for c in p["cases"]]
    parent_rows = {r["label"]: r for p in panels for r in p["rows"]}
    assert len(cases) == 93
    out = _project_file(_PROJECT_ROOT, HERE / (package.name + "-qualification"))
    out.mkdir(exist_ok=False)
    files = {str(p): pin(p) for p in (package / "candidate.py", package / "generation.json",
            _project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"), _project_file(_PROJECT_ROOT, HERE / "DIAGNOSIS-CLOSED.json"), Path(__file__))}
    manifest = json.loads((_project_file(_PROJECT_ROOT, HERE / "DIAGNOSTIC-PLAN.json")).read_text())["source_manifest"]
    save(out / "START.json", {"identity": proposal["identity"], "files": files,
        "source_manifest": manifest, "planned_views": 93, "planned_scores": 186,
        "parent_comparison": "same current typed DTO sha plus all existing parent entries",
        "eligibility": "机械全通过且新来源相关行为改变，之后才买桌赛；非强度或时限门"})
    failure, capture_result, rows = None, None, []
    attempts = 0
    raw = (out / "views.jsonl.gz").open("x+b")
    capture = ScoringInputCapture(raw, limits=ScoringInputCaptureLimits(67108864, 536870912, 128))
    with (_project_file(_PROJECT_ROOT, ROOT / ".private/t165-live-watchdog/postprocess.lock")).open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        started = time.monotonic()
        try:
            with (out / "rows.jsonl").open("x") as stream:
                for case in cases:
                    assert time.monotonic() - started < 600
                    row = {"label": case["label"], "root_id": case["root_id"], "status": "unfinished"}
                    try:
                        obs, key = observation_from_json(case["observation"]), window_key_from_json(case["window_key"])
                        analysis = HangmaRules(batch.rule_config).analyze(obs, route_limits=batch.route_limits)
                        assert analysis.completeness.value == "complete"
                        legal = {c.action_key for c in analysis.legal_candidates}
                        request = DecisionRequest(obs, CompetitionContext("t182-qualification", None, None, None, None, (), 0),
                            analysis, case["label"], key.trigger_seq, key, ())
                        view = build_vip_route_scoring_view(request, batch.rule_config, limits=batch.projection_limits)
                        digest = hashlib.sha256(canonical(view.candidate_view())).hexdigest()
                        assert digest == parent_rows[case["label"]]["view_sha256"]
                        receipt = capture.store(view.candidate_view())
                        assert receipt.saved_before_score
                        outputs = []
                        operations = []
                        for _ in range(2):
                            attempts += 1
                            score = executor.score_vip_route(view)
                            assert score.status == "SCORED"
                            entries = sorted([{"action_key": e.action_key, "score": e.score,
                                               "trace": dict(e.trace)} for e in score.entries], key=lambda e: e["action_key"])
                            assert len(entries) == len(legal) and {e["action_key"] for e in entries} == legal
                            assert all(type(e["score"]) in (int, float) and math.isfinite(e["score"]) for e in entries)
                            assert hashlib.sha256(canonical(view.candidate_view())).hexdigest() == digest
                            outputs.append(entries)
                            operations.append(executor.last_operation_count)
                        assert canonical(outputs[0]) == canonical(outputs[1]) and operations[0] == operations[1]
                        first = sorted(outputs[0], key=lambda e: (-e["score"], e["action_key"]))[0]["action_key"]
                        parent = parent_rows[case["label"]]["scores"]["parent"]["first"]
                        p_scores = {e["action_key"]: e["score"] for e in parent_rows[case["label"]]["scores"]["parent"]["entries"]}
                        c_scores = {e["action_key"]: e["score"] for e in outputs[0]}
                        parent_gap = p_scores[parent] - p_scores[first]
                        child_gap = c_scores[first] - c_scores[parent]
                        p_scale = max(1.0, abs(p_scores[parent]), abs(p_scores[first]))
                        c_scale = max(1.0, abs(c_scores[parent]), abs(c_scores[first]))
                        # 比较两个式子的归一化排序差；不把原型浮点尾差当新机制。
                        meaningful = first != parent and (parent_gap / p_scale > 1e-10 or child_gap / c_scale > 1e-10)
                        row.update(status="complete", view_sha256=digest, capture=asdict(receipt),
                            entries=outputs[0], operation_counts=operations, candidate_first=first, parent_first=parent,
                            first_changed=first != parent, meaningful_first_changed=meaningful,
                            parent_normalized_gap=parent_gap / p_scale, child_normalized_gap=child_gap / c_scale,
                            classes=case["classes"], scope=case["scope"])
                    except BaseException as error:
                        failure = {"type": type(error).__name__, "message": str(error), "label": case["label"]}
                        row.update(status="failed", failure=failure)
                    rows.append(row)
                    stream.write(canonical(row).decode() + "\n")
                    stream.flush()
                    print(json.dumps({"case": case["label"], "status": row["status"],
                                      "changed": row.get("first_changed")}), flush=True)
                    if failure is not None:
                        break
        finally:
            try:
                capture_result = capture.finish()
            except BaseException as error:
                failure = failure or {"type": type(error).__name__, "message": str(error)}
            raw.close()
            stable = all(pin(Path(p)) == h for p, h in files.items()) and all(pin(_project_file(_PROJECT_ROOT, ROOT / p)) == h for p, h in manifest.items())
            mechanical = failure is None and len(rows) == 93 and stable and capture_result is not None and capture_result["terminal"]["terminal_valid"]
            changed_roots = sorted({r["root_id"] for r in rows if r.get("meaningful_first_changed") and
                                    r["label"].startswith(("fresh:", "supplement:"))})
            save(out / "CLOSURE.json", {"complete": mechanical, "mechanical_passed": mechanical,
                "source_stable": stable, "identity": proposal["identity"], "failure": failure,
                "actual_score_attempts": attempts, "actual_completed_views": sum(r["status"] == "complete" for r in rows),
                "new_behavior_sources": changed_roots, "changed_windows": sum(r.get("first_changed", False) for r in rows),
                "meaningful_changed_windows": sum(r.get("meaningful_first_changed", False) for r in rows),
                "numerical_tie_audit": pin(_project_file(_PROJECT_ROOT, HERE / "NUMERICAL-TIE-AUDIT.json")),
                "normalized_gap_threshold_research_only_not_production_tie_rule": 1e-10,
                "development_eligible": mechanical and bool(changed_roots), "rows": rows, "capture": capture_result,
                "new_tables_models": 0, "deadline_admission": False, "strength_admission": False,
                "elapsed_monotonic_seconds": time.monotonic() - started})
    if not mechanical:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", required=True)
    main(parser.parse_args().package)
