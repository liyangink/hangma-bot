"""重建24公开评分图，复核人工仪器与原c70全部分值精确一致。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t189-online-issue-ledger-and-offer-diagnosis-1'

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
from pathlib import Path

HERE = Path(__file__).resolve().parent
PREVIOUS = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t188-joint-score-mechanism-1')
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, HERE.parent / "t185-evidence-prioritized-joker-evolution-1")))
from common import OLD, canonical, pin, save
from t185_prepare_confirmation import background_priority
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.kernel.observation import CompetitionContext
from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
from hangma_bot.policy.interface import DecisionRequest
from hangma_bot.policy.action_value_executor import ActionValueExecutor
from hangma_bot.policy.route_vip_heuristic import build_vip_route_scoring_view
from hangma_bot.offline.scoring_input_capture import ScoringInputCapture, ScoringInputCaptureLimits
from hangma_bot.offline.vip_eoh_generate import VipEohBatch


def main():
    """一研究槽内记录评分前完整输入、原分值对照与新解释，不续打。"""
    background_priority()
    planpath = _project_file(_PROJECT_ROOT, HERE / "DIAGNOSTIC-PLAN.json")
    plan = json.loads(planpath.read_text())
    assert plan["complete"] and all(pin(Path(p)) == h for p, h in plan["files"].items())
    cases = json.loads(Path(plan["source_cases_file"]).read_text())["cases"]
    cases += json.loads(Path(plan["later_cases_file"]).read_text())["cases"]
    cases = {c["label"]: c for c in cases}
    cached = {r["label"]: r for r in map(json.loads, Path(plan["cached_rows_file"]).read_text().splitlines())}
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, PREVIOUS / "AUTHOR-BATCH.json"))
    source = Path(plan["instrument_file"]).read_text()
    executor = ActionValueExecutor(source, max_operations=batch.max_operations,
        max_local_collection_size=batch.projection_limits.max_nodes)
    with (OLD / ".resource-scheduling-worker-0.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        out = _project_file(_PROJECT_ROOT, HERE / "diagnostic")
        out.mkdir(exist_ok=False)
        files = {str(p): pin(p) for p in (Path(__file__), planpath)}
        save(out / "START.json", {"files": files, "plan_pin": pin(planpath),
            "planned_actual_score_calls": plan["planned_actual_score_calls"]})
        raw = (out / "views.jsonl.gz").open("x+b")
        capture = ScoringInputCapture(raw, limits=ScoringInputCaptureLimits(67108864, 536870912, 64))
        attempts, rows, failure, terminal = 0, [], None, None
        started = time.monotonic()
        try:
            with (out / "rows.jsonl").open("x") as stream:
                for label in plan["case_labels"]:
                    case, original = cases[label], cached[label]
                    obs = observation_from_json(case["observation"])
                    key = window_key_from_json(case["window_key"])
                    rules = HangmaRules(batch.rule_config).analyze(obs, route_limits=batch.route_limits)
                    assert rules.completeness.value == "complete"
                    request = DecisionRequest(obs, CompetitionContext("t189-diagnostic", None, None, None, None, (), 0),
                        rules, label, key.trigger_seq, key, ())
                    view = build_vip_route_scoring_view(request, batch.rule_config, limits=batch.projection_limits)
                    digest = hashlib.sha256(canonical(view.candidate_view())).hexdigest()
                    assert digest == case["view_sha256"] == original["view_sha256"]
                    legal = {a.action_key for a in view.actions}
                    expected = {e["action_key"]: e for e in original["entries"]}
                    answers, operations = [], []
                    for repeat in range(plan["repeats_per_case"]):
                        receipt = capture.store(view.candidate_view())
                        assert receipt.saved_before_score
                        attempts += 1
                        answer = executor.score_vip_route(view)
                        assert answer.status == "SCORED"
                        entries = sorted([{"action_key": e.action_key, "score": e.score, "trace": dict(e.trace)}
                            for e in answer.entries], key=lambda e: e["action_key"])
                        assert len(entries) == len(legal) and {e["action_key"] for e in entries} == legal
                        for e in entries:
                            assert type(e["score"]) in (int, float) and math.isfinite(e["score"])
                            assert e["score"] == expected[e["action_key"]]["score"]
                            oldtrace = {k: v for k, v in e["trace"].items() if not k.startswith("diagnostic_")}
                            assert canonical(oldtrace) == canonical(expected[e["action_key"]]["trace"])
                        assert hashlib.sha256(canonical(view.candidate_view())).hexdigest() == digest
                        answers.append(entries)
                        operations.append(executor.last_operation_count)
                    assert canonical(answers[0]) == canonical(answers[1]) and operations[0] == operations[1]
                    first = sorted(entries, key=lambda e: (-e["score"], e["action_key"]))[0]["action_key"]
                    assert first == original["candidate_first"]
                    row = {"label": label, "root_id": case["root_id"], "view_sha256": digest,
                        "candidate_first": first, "entries": entries, "operation_counts": operations,
                        "all_original_scores_traces_and_choices_exact": True, "model_proposal": False}
                    rows.append(row)
                    stream.write(canonical(row).decode() + "\n")
                    stream.flush()
        except BaseException as error:
            failure = {"type": type(error).__name__, "message": str(error), "completed_rows": len(rows)}
        finally:
            try:
                terminal = capture.finish()
            except BaseException as error:
                failure = failure or {"type": type(error).__name__, "message": str(error)}
            raw.close()
        stable = all(pin(Path(p)) == h for p, h in plan["files"].items())
        stable = stable and all(pin(Path(p)) == h for p, h in files.items())
        complete = failure is None and stable and attempts == 48 and len(rows) == 24 and terminal["terminal"]["terminal_valid"]
        result = {"complete": complete, "source_stable": stable, "failure": failure,
            "actual_score_calls": attempts, "public_states": len(rows), "plan_pin": pin(planpath),
            "files": files, "rows_pin": pin(out / "rows.jsonl"), "capture": terminal,
            "all_original_scores_traces_and_choices_exact": complete,
            "elapsed_monotonic_seconds": time.monotonic() - started,
            "model_proposal": False, "new_worlds_tables_models_HTTP": 0,
            "natural_strength_or_original_deadline_admission": False}
        save(out / "CLOSED.json", result)
        assert complete, "解释仪器未完整核同，保留失败，不自动重跑"
    print(json.dumps({"complete": complete, "public_states": len(rows), "actual_score_calls": attempts,
        "all_original_scores_traces_and_choices_exact": complete}))


if __name__ == "__main__":
    main()
