"""T187多父提案的全公开机械筛选；复用父代原评分，只新增子代两次评分。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t187-family-combination-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import fcntl
import hashlib
import json
import math
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1')
sys.path.insert(0, str(PRIOR))
from common import OLD, canonical, pin, save
from t185_prepare_confirmation import background_priority
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.kernel.observation import CompetitionContext
from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
from hangma_bot.policy.interface import DecisionRequest
from hangma_bot.policy.action_value_executor import ActionValueExecutor
from hangma_bot.policy.route_vip_heuristic import build_vip_route_scoring_view
from hangma_bot.offline.scoring_input_capture import ScoringInputCapture, ScoringInputCaptureLimits
from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents


def main():
    """统一研究槽内全图评分，核根完整、确定性、输入不变与预算；不授强度。"""
    background_priority()
    planpath = _project_file(_PROJECT_ROOT, HERE / "QUALIFICATION-PLAN.json")
    plan = json.loads(planpath.read_text())
    assert plan["complete"] and all(pin(Path(p)) == h for p, h in plan["files"].items())
    assert plan["planned_actual_child_scores"] == 2 * len(plan["cases"])
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"))
    proposal = load_vip_parents([_project_file(_PROJECT_ROOT, HERE / "AUTHOR-family-model-output")], batch)[0]
    assert [p["identity"] for p in load_vip_parents([Path(x) for x in json.loads((_project_file(_PROJECT_ROOT, HERE / "AUTHOR-PREPARATION.json")).read_text())["parent_paths"]], batch)] == plan["formal_parent_identities"]
    with (OLD / ".resource-scheduling-worker-0.lock").open("a+") as owner:
        fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        out = _project_file(_PROJECT_ROOT, HERE / "qualification")
        out.mkdir(exist_ok=False)
        save(out / "START.json", {"plan_pin": pin(planpath), "identity": proposal["identity"],
            "package_pins": {str(p): pin(p) for p in (_project_file(_PROJECT_ROOT, HERE / "AUTHOR-family-model-output/candidate.py"), _project_file(_PROJECT_ROOT, HERE / "AUTHOR-family-model-output/generation.json"))},
            "planned_public_views": len(plan["cases"]), "planned_score_attempts": plan["planned_actual_child_scores"],
            "cached_parent_scores": True, "no_strength_or_deadline_admission": True})
        executor = ActionValueExecutor(proposal["source"], max_operations=batch.max_operations,
            max_local_collection_size=batch.projection_limits.max_nodes)
        raw = (out / "views.jsonl.gz").open("x+b")
        capture = ScoringInputCapture(raw, limits=ScoringInputCaptureLimits(67108864, 1073741824, 512))
        rows, attempts, failure, terminal = [], 0, None, None
        started = time.monotonic()
        try:
            with (out / "rows.jsonl").open("x") as output:
                for case in plan["cases"]:
                    obs = observation_from_json(case["observation"])
                    key = window_key_from_json(case["window_key"])
                    analysis = HangmaRules(batch.rule_config).analyze(obs, route_limits=batch.route_limits)
                    assert analysis.completeness.value == "complete"
                    request = DecisionRequest(obs, CompetitionContext("t187-family-qualification", None, None, None,
                        None, (), 0), analysis, case["label"], key.trigger_seq, key, ())
                    view = build_vip_route_scoring_view(request, batch.rule_config, limits=batch.projection_limits)
                    digest = hashlib.sha256(canonical(view.candidate_view())).hexdigest()
                    assert digest == case["view_sha256"]
                    legal = {a.action_key for a in view.actions}
                    outputs, operations, durations = [], [], []
                    for repeat in range(2):
                        receipt = capture.store(view.candidate_view())
                        assert receipt.saved_before_score
                        attempts += 1
                        clock = time.monotonic()
                        answer = executor.score_vip_route(view)
                        durations.append(time.monotonic() - clock)
                        assert answer.status == "SCORED"
                        entries = sorted([{"action_key": e.action_key, "score": e.score, "trace": dict(e.trace)}
                                          for e in answer.entries], key=lambda e: e["action_key"])
                        assert len(entries) == len(legal) and {e["action_key"] for e in entries} == legal
                        assert all(type(e["score"]) in (int, float) and math.isfinite(e["score"]) for e in entries)
                        assert hashlib.sha256(canonical(view.candidate_view())).hexdigest() == digest
                        outputs.append(entries)
                        operations.append(executor.last_operation_count)
                    assert canonical(outputs[0]) == canonical(outputs[1]) and operations[0] == operations[1]
                    first = sorted(entries, key=lambda e: (-e["score"], e["action_key"]))[0]["action_key"]
                    row = {"label": case["label"], "root_id": case["root_id"], "classes": case["classes"],
                        "view_sha256": digest, "entries": entries, "operation_counts": operations,
                        "score_monotonic_seconds": durations, "parent_first": case["parent_first"],
                        "candidate_first": first, "first_changed": first != case["parent_first"],
                        "cached_parent_first": case["cached_parent_first"]}
                    rows.append(row)
                    output.write(canonical(row).decode() + "\n")
                    output.flush()
        except BaseException as error:
            failure = {"type": type(error).__name__, "message": str(error), "actual_views": len(rows)}
        finally:
            try:
                terminal = capture.finish()
            except BaseException as error:
                failure = failure or {"type": type(error).__name__, "message": str(error)}
            raw.close()
        stable = (all(pin(Path(p)) == h for p, h in plan["files"].items())
                  and batch.identity(proposal["source"]) == proposal["identity"]
                  and json.loads((out / "START.json").read_text())["package_pins"] == {str(p): pin(p) for p in (_project_file(_PROJECT_ROOT, HERE / "AUTHOR-family-model-output/candidate.py"), _project_file(_PROJECT_ROOT, HERE / "AUTHOR-family-model-output/generation.json"))})
        complete = failure is None and stable and len(rows) == len(plan["cases"]) and terminal["terminal"]["terminal_valid"]
        changed = [r for r in rows if r["first_changed"]]
        result = {"complete": complete, "mechanical_passed": complete, "failure": failure,
            "source_stable": stable, "identity": proposal["identity"], "formal_parent_identities": plan["formal_parent_identities"], "plan_pin": pin(planpath),
            "actual_completed_views": len(rows), "actual_score_attempts": attempts, "cached_parent_new_scores": 0,
            "changes_vs_cached_6876": sum(r["cached_parent_first"]["6876"] is not None and r["candidate_first"] != r["cached_parent_first"]["6876"] for r in rows),
            "changed_windows": len(changed), "changed_sources": sorted({r["root_id"] for r in changed}),
            "changes_by_class": dict(Counter(c for r in changed for c in r["classes"])),
            "rows_pin": pin(out / "rows.jsonl"), "capture": terminal,
            "elapsed_monotonic_seconds": time.monotonic() - started,
            "actual_max_score_monotonic_seconds": max((d for r in rows for d in r["score_monotonic_seconds"]), default=None),
            "maximum_operations": max((max(r["operation_counts"]) for r in rows), default=None),
            "new_worlds_tables_models_HTTP": 0, "strength_or_original_deadline_admission": False}
        save(out / "CLOSED.json", result)
        assert complete, "机械筛选失败，原输入、评分和费用保留，不自动重试"
        print(json.dumps({k: result[k] for k in ("complete", "actual_completed_views", "actual_score_attempts",
            "changed_windows", "maximum_operations", "actual_max_score_monotonic_seconds")}))


if __name__ == "__main__":
    main()
