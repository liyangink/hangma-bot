"""在统一研究槽内评价四个单变量源码；只评分公开原窗，不续打。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t188-joint-score-mechanism-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import fcntl
import gzip
import hashlib
import json
import math
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1')
SOURCE = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t187-family-combination-evolution-1')
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
from hangma_bot.offline.vip_eoh_generate import VipEohBatch


def main():
    """原图逐字节核同，112评分核确定性和单变量影响；不授整体强度。"""
    background_priority()
    preparation_path = _project_file(_PROJECT_ROOT, HERE / "PROBE-PREPARATION.json")
    preparation = json.loads(preparation_path.read_text())
    assert preparation["complete"] and all(
        pin(Path(p)) == h for p, h in preparation["files"].items()
    )
    with gzip.open(_project_file(_PROJECT_ROOT, HERE / "FIRST-CHOICES.jsonl.gz"), "rt") as stream:
        cases = list(map(json.loads, stream))
    assert len(cases) == 14
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, SOURCE / "AUTHOR-BATCH.json"))
    sources = {p["name"]: Path(p["source_file"]).read_text() for p in preparation["probes"]}
    assert all(batch.identity(sources[p["name"]]) == p["identity"] for p in preparation["probes"])
    executors = {
        name: ActionValueExecutor(
            source,
            max_operations=batch.max_operations,
            max_local_collection_size=batch.projection_limits.max_nodes,
        )
        for name, source in sources.items()
    }
    with (OLD / ".resource-scheduling-worker-0.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        out = _project_file(_PROJECT_ROOT, HERE / "probes")
        out.mkdir(exist_ok=False)
        plan_pins = {str(p): pin(p) for p in (Path(__file__), preparation_path)}
        save(out / "START.json", {"files": plan_pins, "actual_scores_planned": 112})
        raw = (out / "views.jsonl.gz").open("x+b")
        capture = ScoringInputCapture(
            raw, limits=ScoringInputCaptureLimits(67108864, 536870912, 64)
        )
        attempts, rows, failure, terminal = 0, [], None, None
        started = time.monotonic()
        try:
            with (out / "rows.jsonl").open("x") as output:
                for case in cases:
                    obs = observation_from_json(case["observation"])
                    key = window_key_from_json(case["window_key"])
                    rules = HangmaRules(batch.rule_config).analyze(obs, route_limits=batch.route_limits)
                    assert rules.completeness.value == "complete"
                    request = DecisionRequest(
                        obs, CompetitionContext("t188-diagnostic", None, None, None, None, (), 0),
                        rules, case["label"], key.trigger_seq, key, (),
                    )
                    view = build_vip_route_scoring_view(
                        request, batch.rule_config, limits=batch.projection_limits
                    )
                    digest = hashlib.sha256(canonical(view.candidate_view())).hexdigest()
                    assert digest == case["view_sha256"]
                    legal = {a.action_key for a in view.actions}
                    cached = {e["action_key"]: e["score"] for e in case["C"]["candidates"]}
                    for name, executor in executors.items():
                        answers, operations = [], []
                        for repeat in range(2):
                            receipt = capture.store(view.candidate_view())
                            assert receipt.saved_before_score
                            attempts += 1
                            answer = executor.score_vip_route(view)
                            assert answer.status == "SCORED"
                            entries = sorted(
                                [{"action_key": e.action_key, "score": e.score, "trace": dict(e.trace)}
                                 for e in answer.entries],
                                key=lambda e: e["action_key"],
                            )
                            assert len(entries) == len(legal) and {e["action_key"] for e in entries} == legal
                            assert all(type(e["score"]) in (int, float) and math.isfinite(e["score"])
                                       for e in entries)
                            if name == "I":
                                assert {e["action_key"]: e["score"] for e in entries} == cached
                            assert hashlib.sha256(canonical(view.candidate_view())).hexdigest() == digest
                            answers.append(entries)
                            operations.append(executor.last_operation_count)
                        assert canonical(answers[0]) == canonical(answers[1])
                        assert operations[0] == operations[1]
                        first = sorted(entries, key=lambda e: (-e["score"], e["action_key"]))[0]["action_key"]
                        duplicates = {
                            e["action_key"]: e["trace"]["portfolio"][-1]
                            for e in entries if "portfolio" in e["trace"]
                        }
                        if name in ("D", "DE"):
                            assert all(v == 0 for v in duplicates.values())
                        row = {
                            "target": case["target"], "label": case["label"], "probe": name,
                            "entries": entries, "operation_counts": operations, "candidate_first": first,
                            "original_C_first": case["C"]["selected_action_key"],
                            "online_A_first": case["A"]["selected_action_key"],
                            "changed_vs_C": first != case["C"]["selected_action_key"],
                            "duplicate_code_widths": duplicates, "view_sha256": digest,
                            "strength_admission": False,
                        }
                        rows.append(row)
                        output.write(canonical(row).decode() + "\n")
                        output.flush()
        except BaseException as error:
            failure = {"type": type(error).__name__, "message": str(error), "completed_rows": len(rows)}
        finally:
            try:
                terminal = capture.finish()
            except BaseException as error:
                failure = failure or {"type": type(error).__name__, "message": str(error)}
            raw.close()
        stable = (
            all(pin(Path(p)) == h for p, h in preparation["files"].items())
            and all(pin(Path(p)) == h for p, h in plan_pins.items())
            and all(batch.identity(sources[p["name"]]) == p["identity"] for p in preparation["probes"])
        )
        complete = (
            failure is None and stable and attempts == 112 and len(rows) == 56
            and terminal["terminal"]["terminal_valid"]
        )
        summary = {}
        for name in sources:
            selected = [r for r in rows if r["probe"] == name]
            summary[name] = {
                "rows": len(selected),
                "changed_vs_C": [r["target"] for r in selected if r["changed_vs_C"]],
                "positive_duplicate_targets": sorted(
                    r["target"] for r in selected if any(v > 0 for v in r["duplicate_code_widths"].values())
                ),
                "maximum_duplicate_codes": max(
                    (v for r in selected for v in r["duplicate_code_widths"].values()), default=0
                ),
                "first_choices": {str(r["target"]): r["candidate_first"] for r in selected},
            }
        result = {
            "complete": complete, "failure": failure, "source_stable": stable,
            "actual_score_calls": attempts, "rows": len(rows), "summary": summary,
            "files": plan_pins, "rows_pin": pin(out / "rows.jsonl"), "capture": terminal,
            "elapsed_monotonic_seconds": time.monotonic() - started,
            "new_worlds_tables_models_HTTP": 0, "original_deadline_or_strength_admission": False,
        }
        save(out / "CLOSED.json", result)
        assert complete, "诊断评分不完整；原件保留，不自动重评分"
        print(json.dumps({k: result[k] for k in ("complete", "actual_score_calls", "summary")}))


if __name__ == "__main__":
    main()
