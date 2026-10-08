"""候选在95个旧诊断及20个新房首摸的完整机械与行为检查。"""

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
import argparse
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
from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents
from common import HERE, ROOT, canonical, pin, save


def source_unit(root):
    """官方按房聚合；模拟沿用母来源，不把同房的不同桌算独立来源。"""
    return root.split("_r1_")[0] if root.startswith("a_") else root


def main(package):
    """同一typed图两次全评分；行为资格与积分/时限门分开。"""
    os.nice(15)
    assert ctypes.CDLL(None).setiopolicy_np(0, 0, 3) == 0
    package = Path(package).resolve()
    assert package.parent == HERE
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"))
    proposal = load_vip_parents([package], batch)[0]
    assert proposal["artifact_role"] == "candidate_proposal"
    plans = [json.loads((_project_file(_PROJECT_ROOT, HERE / name)).read_text()) for name in ("PLAN.json", "SUPPLEMENT-PLAN.json")]
    panels = [json.loads((_project_file(_PROJECT_ROOT, HERE / name / "CLOSURE.json")).read_text()) for name in
              ("mechanism-comparison-v2", "mechanism-comparison-supplement")]
    assert all(p["complete"] and p["source_stable"] for p in panels)
    cases = [c for name in ("CASES.json", "SUPPLEMENT-CASES.json") for c in json.loads((_project_file(_PROJECT_ROOT, HERE / name)).read_text())["cases"]]
    parents = {r["label"]: r for p in panels for r in p["rows"]}
    assert len(cases) == len(parents) == 115
    files = {str(p): pin(p) for p in [Path(__file__), _project_file(_PROJECT_ROOT, HERE / "common.py"), _project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"), package / "generation.json", package / "candidate.py",
        _project_file(_PROJECT_ROOT, HERE / "PLAN.json"), _project_file(_PROJECT_ROOT, HERE / "SUPPLEMENT-PLAN.json"), _project_file(_PROJECT_ROOT, HERE / "CASES.json"), _project_file(_PROJECT_ROOT, HERE / "SUPPLEMENT-CASES.json"),
        *[_project_file(_PROJECT_ROOT, HERE / n / "CLOSURE.json") for n in ("mechanism-comparison-v2", "mechanism-comparison-supplement")]]}
    manifest = plans[0]["source_manifest"]
    assert manifest == plans[1]["source_manifest"]
    assert all(pin(_project_file(_PROJECT_ROOT, ROOT / p)) == h for p, h in manifest.items())
    executor = ActionValueExecutor(proposal["source"], max_operations=batch.max_operations,
        max_local_collection_size=batch.projection_limits.max_nodes)
    out = _project_file(_PROJECT_ROOT, HERE / (package.name + "-qualification"))
    out.mkdir(exist_ok=False)
    save(out / "START.json", {"files": files, "source_manifest": manifest, "identity": proposal["identity"],
        "planned_views": 115, "planned_actual_scores": 230, "strength_or_deadline_admission": False})
    raw = (out / "views.jsonl.gz").open("x+b")
    capture = ScoringInputCapture(raw, limits=ScoringInputCaptureLimits(67108864, 536870912, 128))
    rows, attempts, failure, capture_result = [], 0, None, None
    started = time.monotonic()
    try:
        with (out / "rows.jsonl").open("x") as stream:
            for case in cases:
                row = {"label": case["label"], "root_id": case["root_id"], "source_unit": source_unit(case["root_id"]), "classes": case["classes"], "status": "unfinished"}
                try:
                    assert time.monotonic() - started < 900
                    obs, key = observation_from_json(case["observation"]), window_key_from_json(case["window_key"])
                    analysis = HangmaRules(batch.rule_config).analyze(obs, route_limits=batch.route_limits)
                    assert analysis.completeness.value == "complete"
                    legal = {c.action_key for c in analysis.legal_candidates}
                    request = DecisionRequest(obs, CompetitionContext("t185-qualification", None, None, None, None, (), 0), analysis,
                        case["label"], key.trigger_seq, key, ())
                    view = build_vip_route_scoring_view(request, batch.rule_config, limits=batch.projection_limits)
                    digest = hashlib.sha256(canonical(view.candidate_view())).hexdigest()
                    assert digest == parents[case["label"]]["view_sha256"]
                    receipt = capture.store(view.candidate_view())
                    assert receipt.saved_before_score
                    outputs, operations = [], []
                    for _ in range(2):
                        attempts += 1
                        batch_scores = executor.score_vip_route(view)
                        assert batch_scores.status == "SCORED"
                        entries = sorted([{"action_key": e.action_key, "score": e.score, "trace": dict(e.trace)} for e in batch_scores.entries], key=lambda e: e["action_key"])
                        assert len(entries) == len(legal) and {e["action_key"] for e in entries} == legal
                        assert all(type(e["score"]) in (int, float) and math.isfinite(e["score"]) for e in entries)
                        assert hashlib.sha256(canonical(view.candidate_view())).hexdigest() == digest
                        outputs.append(entries)
                        operations.append(executor.last_operation_count)
                    assert canonical(outputs[0]) == canonical(outputs[1]) and operations[0] == operations[1]
                    first = sorted(entries, key=lambda e: (-e["score"], e["action_key"]))[0]["action_key"]
                    parent = parents[case["label"]]["scores"]["parent"]
                    oldfirst = parent["first"]
                    old = {e["action_key"]: e["score"] for e in parent["entries"]}
                    new = {e["action_key"]: e["score"] for e in entries}
                    assert set(old) == legal
                    pgap = (old[oldfirst] - old[first]) / max(1.0, abs(old[oldfirst]), abs(old[first]))
                    cgap = (new[first] - new[oldfirst]) / max(1.0, abs(new[first]), abs(new[oldfirst]))
                    row.update(status="complete", view_sha256=digest, capture=asdict(receipt), entries=entries,
                        operation_counts=operations, candidate_first=first, parent_first=oldfirst,
                        first_changed=first != oldfirst, meaningful_first_changed=first != oldfirst and (pgap > 1e-10 or cgap > 1e-10),
                        parent_normalized_gap=pgap, child_normalized_gap=cgap)
                except BaseException as error:
                    failure = {"type": type(error).__name__, "message": str(error), "label": case["label"]}
                    row.update(status="failed", failure=failure)
                rows.append(row)
                stream.write(canonical(row).decode() + "\n")
                stream.flush()
                print(json.dumps({"label": row["label"], "status": row["status"], "changed": row.get("meaningful_first_changed")}), flush=True)
                if failure:
                    break
    finally:
        try:
            capture_result = capture.finish()
        except BaseException as error:
            failure = failure or {"type": type(error).__name__, "message": str(error)}
        raw.close()
        stable = all(pin(Path(p)) == h for p, h in files.items()) and all(pin(_project_file(_PROJECT_ROOT, ROOT / p)) == h for p, h in manifest.items())
        mechanical = failure is None and len(rows) == 115 and stable and capture_result["terminal"]["terminal_valid"]
        nonanchor_sources = sorted({r["source_unit"] for r in rows if r.get("meaningful_first_changed") and not r["label"].startswith("anchor:")})
        opening_changes = [r["label"] for r in rows if r.get("meaningful_first_changed") and r["label"].startswith("new-official:")]
        save(out / "CLOSURE.json", {"schema": "t185-candidate-qualification/1", "complete": mechanical,
            "mechanical_passed": mechanical, "source_stable": stable, "failure": failure,
            "identity": proposal["identity"], "files": files, "source_manifest": manifest,
            "actual_score_attempts": attempts, "actual_completed_views": sum(r["status"] == "complete" for r in rows),
            "changed_windows": sum(r.get("first_changed", False) for r in rows),
            "meaningful_changed_windows": sum(r.get("meaningful_first_changed", False) for r in rows),
            "nonanchor_changed_sources": nonanchor_sources, "new_official_opening_changes": opening_changes,
            "development_eligible": mechanical and bool(nonanchor_sources), "rows": rows, "capture": capture_result,
            "elapsed_monotonic_seconds": time.monotonic() - started,
            "new_worlds_tables_model_calls": 0, "strength_or_deadline_admitted": False,
            "eligibility_not_independent_strength_confirmation": True})
    print({"mechanical_passed": mechanical, "failure": failure, "nonanchor_changed_sources": nonanchor_sources, "new_opening_changes": opening_changes}, flush=True)
    if not mechanical:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", required=True)
    main(parser.parse_args().package)
