"""完整typed规则/图上比较父代和三种机制；先重现新来源真实父评分再裁行为差异。"""

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
import ctypes
import fcntl
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import time
from dataclasses import asdict

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.kernel.observation import CompetitionContext
from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
from hangma_bot.policy.action_value_executor import ActionValueExecutor
from hangma_bot.policy.interface import DecisionRequest
from hangma_bot.policy.route_vip_heuristic import build_vip_route_scoring_view
from hangma_bot.offline.scoring_input_capture import ScoringInputCapture, ScoringInputCaptureLimits
from hangma_bot.offline.vip_eoh_generate import VipEohBatch
from prepare_diagnostics import pin, save
from run_diagnostic_sources import canonical, stable

HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT


def assemble_cases():
    """整批新来源必须自然终态；不拿中途结果选题或删失败来源。"""
    cases = []
    pins = {}
    roots = set()
    diagnostics = json.loads((_project_file(_PROJECT_ROOT, HERE / "DIAGNOSTIC-PLAN.json")).read_text())
    for index, root in enumerate(diagnostics["roots"], 1):
        path = _project_file(_PROJECT_ROOT, HERE / "diagnostic-sources" / f"root-{index:03d}" / "CLOSURE.json")
        closed = json.loads(path.read_text())
        assert closed["complete"] and closed["source_stable"]
        assert closed["outcome"]["status"] == "complete" and closed["outcome"]["completed_hands"] == 8
        assert closed["score_failures"] == 0 and closed["capture"]["terminal"]["terminal_valid"]
        pins[str(path)] = pin(path)
        roots.add(root["root_id"])
        for ordinal, row in enumerate(closed["selected_windows"], 1):
            assert row["selected_before_choice"] and row["status"] == "complete"
            assert row["scoring"]["capture"]["saved_before_score"]
            cases.append({"label": f"fresh:{index:03d}:{ordinal:02d}", "root_id": root["root_id"],
                "scope": "fresh_before-choice_opportunity_selected_development",
                "observation": row["observation"], "window_key": row["window_key"],
                "legal_action_keys": row["legal_action_keys"], "classes": row["classes"],
                "expected_parent_view_sha256": row["scoring"]["capture"]["view_sha256"],
                "expected_actual_parent_entries": row["scores"],
                "source_closure": str(path.relative_to(ROOT))})
        if index <= 2:
            # 事先固定来源1/2末单局第一本人摸牌作无后续庄权对照，不按终分选题。
            archive = path.parent / "decisions.jsonl.gz"
            pins[str(archive)] = pin(archive)
            with gzip.open(archive, "rt") as stream:
                row = next(json.loads(line) for line in stream
                           if json.loads(line)["window_key"]["round_no"] == 8
                           and json.loads(line)["window_key"]["phase"] == "draw")
            assert row["status"] == "complete"
            cases.append({"label": f"last-control:{index:03d}", "root_id": root["root_id"],
                "scope": "predeclared_root_1_2_first_draw_last_hand_control",
                "observation": row["observation"], "window_key": row["window_key"],
                "legal_action_keys": row["legal_action_keys"], "classes": ["last_hand_control"],
                "expected_parent_view_sha256": None,
                "expected_actual_parent_entries": row["scores"],
                "source_closure": str(path.relative_to(ROOT))})
    historical_path = _project_file(_PROJECT_ROOT, HERE / "HISTORICAL-PANEL-FROZEN.json")
    historical = json.loads(historical_path.read_text())
    assert all(pin(Path(p)) == h for p, h in historical["files"].items())
    pins[str(historical_path)] = pin(historical_path)
    for row in historical["cases"]:
        roots.add(row["root_id"])
        cases.append({"label": "historical:" + row["label"], "root_id": row["root_id"],
            "scope": row["role"], "observation": row["observation"], "window_key": row["window_key"],
            "classes": ["historical_natural_route_control"],
            "expected_parent_view_sha256": None, "expected_actual_parent_entries": None})
    original_path = _project_file(_PROJECT_ROOT, HERE / "ORIGINAL-SCORE-FIELDS.json")
    if original_path.exists():
        original = json.loads(original_path.read_text())
        assert original["complete"]
        pins[str(original_path)] = pin(original_path)
        for row in original["cases"]:
            records = row["records"]
            inp, planned = records["decision_input"], records["decision_planned"]
            candidates = planned["returned_plan"]["candidates"]
            assert not planned["degraded_reasons"]
            entries = [{"action_key": c["action_key"], "score": c["total_score"],
                        "trace": c["score_trace"]["detail"]} for c in candidates]
            cases.append({"label": f"official:{row['round_no']}:{row['trigger_seq']}",
                "root_id": row["game_id"], "scope": "exposed_official_target_original_score_fields",
                "observation": inp["observation"], "window_key": inp["window_key"],
                "legal_action_keys": [c["action_key"] for c in inp["legal_candidates"]],
                "classes": ["official_hu_wait_control"], "expected_parent_view_sha256": None,
                "expected_actual_parent_entries": entries,
                "original_trace_redacted": True})
    assert len(roots) >= 12 and len(cases) >= 24
    assert len(cases) <= 128
    return cases, pins, len(roots)


def visible_trace_equal(expected, actual):
    """原线上审计脱敏位置保留未知；完整存活字段仍逐值核对。"""
    if expected == "[REDACTED]":
        return True
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            k == "[REDACTED]" or k in actual and visible_trace_equal(v, actual[k])
            for k, v in expected.items())
    if isinstance(expected, (list, tuple)):
        return isinstance(actual, (list, tuple)) and len(expected) == len(actual) and all(
            visible_trace_equal(a, b) for a, b in zip(expected, actual))
    return expected == actual


def main():
    """持共用锁、低优先级；评分失败是未完成，不放宽额度/丢根/回退。"""
    os.nice(15)
    assert ctypes.CDLL(None).setiopolicy_np(0, 0, 3) == 0
    cases, input_pins, root_count = assemble_cases()
    plan = json.loads((_project_file(_PROJECT_ROOT, HERE / "DIAGNOSTIC-PLAN.json")).read_text())
    assert stable(plan)
    frozen = json.loads((_project_file(_PROJECT_ROOT, HERE / "PROTOTYPES-FROZEN.json")).read_text())
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "DIAGNOSTIC-EXECUTION-BATCH.json"))
    sources = {"parent": (_project_file(_PROJECT_ROOT, HERE / "parent-source.py")).read_text()}
    for prototype in frozen["prototypes"]:
        path = _project_file(_PROJECT_ROOT, HERE / prototype["source_file"])
        assert pin(path) == prototype["source_pin"]
        sources[prototype["name"]] = path.read_text()
        assert batch.identity(sources[prototype["name"]]) == prototype["identity"]
    executors = {name: ActionValueExecutor(source, max_operations=batch.max_operations,
                max_local_collection_size=batch.projection_limits.max_nodes) for name, source in sources.items()}
    out = _project_file(_PROJECT_ROOT, HERE / "mechanism-comparison")
    out.mkdir(exist_ok=False)
    save(out / "START.json", {"cases": cases, "source_roots": root_count,
        "input_pins": input_pins, "prototype_file_pin": pin(_project_file(_PROJECT_ROOT, HERE / "PROTOTYPES-FROZEN.json")),
        "runner_pin": pin(Path(__file__)), "source_manifest": plan["source_manifest"],
        "planned_scores": len(cases) * 4, "logical_mechanical_not_deadline_strength_evidence": True})
    queued_at = time.monotonic()
    counts = {"rules_analyze": 0, "view_build": 0, "score_attempts": {n: 0 for n in sources}}
    rows = []
    primary = None
    capture_result = None
    raw = (out / "views.jsonl.gz").open("x+b")
    capture = ScoringInputCapture(raw, limits=ScoringInputCaptureLimits(67108864, 536870912, 128))
    with (_project_file(_PROJECT_ROOT, ROOT / ".private/t165-live-watchdog/postprocess.lock")).open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        began = time.monotonic()
        try:
            with (out / "rows.jsonl").open("x") as output:
                for case in cases:
                    row = {"label": case["label"], "root_id": case["root_id"],
                           "classes": case["classes"], "status": "unfinished", "scores": {}}
                    try:
                        assert time.monotonic() - began < 600
                        obs = observation_from_json(case["observation"])
                        key = window_key_from_json(case["window_key"])
                        counts["rules_analyze"] += 1
                        analysis = HangmaRules(batch.rule_config).analyze(obs, route_limits=batch.route_limits)
                        assert analysis.completeness.value == "complete"
                        legal = {c.action_key for c in analysis.legal_candidates}
                        if "legal_action_keys" in case:
                            assert legal == set(case["legal_action_keys"])
                        request = DecisionRequest(obs, CompetitionContext("t182-mechanisms", None, None, None, None, (), 0),
                                                  analysis, case["label"], key.trigger_seq, key, ())
                        counts["view_build"] += 1
                        view = build_vip_route_scoring_view(request, batch.rule_config, limits=batch.projection_limits)
                        dto = view.candidate_view()
                        digest = hashlib.sha256(canonical(dto)).hexdigest()
                        if case["expected_parent_view_sha256"] is not None:
                            assert digest == case["expected_parent_view_sha256"], "完整真实父输入不一致"
                        receipt = capture.store(dto)
                        assert receipt.saved_before_score
                        row.update(view_sha256=digest, capture=asdict(receipt), legal_actions=sorted(legal))
                        for name, executor in executors.items():
                            counts["score_attempts"][name] += 1
                            score = executor.score_vip_route(view)
                            assert score.status == "SCORED"
                            entries = [{"action_key": e.action_key, "score": e.score, "trace": dict(e.trace)} for e in score.entries]
                            assert len(entries) == len(legal) and {e["action_key"] for e in entries} == legal
                            assert all(type(e["score"]) in (int, float) and math.isfinite(e["score"]) for e in entries)
                            entries.sort(key=lambda e: e["action_key"])
                            expected = case["expected_actual_parent_entries"]
                            if name == "parent" and expected is not None:
                                ordered_expected = sorted(expected, key=lambda e: e["action_key"])
                                if case.get("original_trace_redacted"):
                                    assert len(entries) == len(ordered_expected)
                                    for old, new in zip(ordered_expected, entries):
                                        assert (old["action_key"], old["score"]) == (new["action_key"], new["score"]), "原线上数值评分未复现"
                                        assert visible_trace_equal(old["trace"], new["trace"]), "原线上存活解释字段未复现"
                                else:
                                    assert canonical(entries) == canonical(ordered_expected), "真实父完整评分/解释未复现"
                            row["scores"][name] = {"entries": entries, "operations": executor.last_operation_count,
                                "first": sorted(entries, key=lambda e: (-e["score"], e["action_key"]))[0]["action_key"]}
                            assert hashlib.sha256(canonical(view.candidate_view())).hexdigest() == digest
                        parent_first = row["scores"]["parent"]["first"]
                        row.update(status="complete", first_changed={n: row["scores"][n]["first"] != parent_first
                                  for n in sources if n != "parent"}, original_parent_full_scores_verified=expected is not None,
                                  original_trace_verification="visible_fields_only_redacted_parts_unknown" if case.get("original_trace_redacted") else "full_trace_exact" if expected is not None else "no_original_score_credit")
                    except BaseException as error:
                        primary = {"type": type(error).__name__, "message": str(error), "label": case["label"]}
                        row.update(status="failed", error=primary)
                    rows.append(row)
                    output.write(canonical(row).decode() + "\n")
                    output.flush()
                    print(json.dumps({"label": row["label"], "status": row["status"],
                                      "changed": row.get("first_changed"), "error": row.get("error")}), flush=True)
                    if primary is not None:
                        break
        finally:
            try:
                capture_result = capture.finish()
            except BaseException as error:
                primary = primary or {"type": type(error).__name__, "message": str(error)}
            raw.close()
            unchanged = stable(plan) and all(pin(Path(p)) == h for p, h in input_pins.items())
            complete = (primary is None and unchanged and len(rows) == len(cases)
                        and capture_result is not None and capture_result["terminal"]["terminal_valid"])
            save(out / "CLOSURE.json", {"complete": complete, "source_stable": unchanged,
                "cases": cases, "rows": rows, "counts": counts, "failure": primary,
                "capture": capture_result, "mother_roots": root_count, "model_calls_worlds_tables": 0,
                "changed_windows": {n: sum(r.get("first_changed", {}).get(n, False) for r in rows)
                                    for n in sources if n != "parent"},
                "elapsed_monotonic_seconds": time.monotonic() - began,
                "lock_wait_monotonic_seconds": began - queued_at,
                "source_scope": "development_mechanics_and_behavior_not_strength_or_admission"})
    if not complete:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
