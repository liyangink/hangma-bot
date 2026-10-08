"""只读闭合T155四身份审计；按实际HTTP、唯一桌赛和完整合法评分统计。

仅在四身份自然终态、赛后下载完成后执行。没有HTTP、策略评分或续打。
不会导入旧批次统计脚本；只存决策的动作键和预算，避免保存巨量完整请求。
时间差使用审计中的单调时钟，毫秒输出；积分向量使用官方0至3座位顺序。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t155-pruned-s02-engineering-testroom-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import statistics

ROOT = _PROJECT_ROOT
HERE = Path(__file__).resolve().parent
BASE = _project_file(_PROJECT_ROOT, ROOT / "artifacts/sessions/t155-vip-s02-testroom-v5")


def load(path):
    """读取本批次JSON，不读取凭证或其他批次。"""
    return json.loads(path.read_text())


def stats(values):
    """统计实际观察耗时；p95取排序后的最近秩，不推断未观测窗口。"""
    values = sorted(values)
    if not values:
        return {"count": 0}
    return {"count": len(values), "mean_ms": statistics.mean(values),
            "p95_ms": values[math.ceil(len(values) * .95) - 1], "max_ms": values[-1]}


def source_rows(path, sources):
    """流式读取并记录原件字节摘要；不修改官方或审计原件。"""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for line_number, raw in enumerate(stream, 1):
            digest.update(raw)
            yield line_number, json.loads(raw)
    sources[str(path.relative_to(BASE))] = digest.hexdigest()


def audit_run(run, sources):
    """统计一个已关闭身份的全部规范审计流；RAW不重复计为HTTP。"""
    assert (run / "summary.json").exists(), f"身份尚未关闭：{run}"
    counts, http, ends, outcomes, not_sent, purposes = (Counter() for _ in range(6))
    inputs, failed, mismatch, errors, coverage = {}, [], [], [], []
    started, finished, planned_keys = set(), set(), set()
    rule_ms, policy_ms, complete_ms, queue_ms, state_ms = ([] for _ in range(5))
    phase_rule, phase_policy, phase_local_total = {}, {}, {}
    waiter_max = plans = full = outputs = 0
    files = sorted({*run.glob("lifecycle.jsonl"), *run.glob("participants/*/decisions.jsonl"),
                    *run.glob("participants/*/games/*.jsonl")})
    for path in files:
        for line, record in source_rows(path, sources):
            kind, payload, context = record["kind"], record["payload"], record["context"]
            counts[kind] += 1
            if kind == "http_request":
                rid = payload["request_id"]
                if payload.get("phase") == "started":
                    assert rid not in started, f"重复规范HTTP开始：{rid}"
                    started.add(rid)
                if payload.get("phase") == "finished":
                    assert rid not in finished, f"重复规范HTTP结束：{rid}"
                    finished.add(rid)
                    endpoint = payload.get("endpoint", "")
                    category = ("state" if "/api/games/" in endpoint and "/state" in endpoint else
                                "action" if "/api/games/" in endpoint and "/action" in endpoint else
                                "guide" if "/guide" in endpoint else "lifecycle")
                    http[category, str(payload.get("http_status"))] += 1
                    if category == "state":
                        timing = payload.get("request_timing", {})
                        for low, high, target in (
                            ("queued_at_monotonic", "granted_at_monotonic", queue_ms),
                            ("transport_started_at_monotonic", "completed_at_monotonic", state_ms)):
                            if timing.get(low) is not None and timing.get(high) is not None:
                                target.append((timing[high] - timing[low]) * 1000)
                        waiter_max = max(waiter_max, timing.get("state_queue_at_grant", {}).get("waiters_total", 0))
                        purposes[str(timing.get("query_purpose"))] += 1
            if kind == "decision_input":
                key = context["decision_id"], payload["plan_revision"]
                assert key not in inputs, f"重复决策输入：{key}"
                inputs[key] = {"legal": sorted(c["action_key"] for c in payload["request"]["rules"]["legal_candidates"]),
                               "phase": payload["window"]["phase"], "rule_ms": payload["rule_elapsed_ms"],
                               "input_monotonic": record["monotonic_ns"] / 1e9,
                               "budget_origin_monotonic": payload["budget_origin_monotonic"],
                               "budget": payload["budget"], "window_deadline": payload["window_deadline"],
                               "source": str(path.relative_to(BASE)), "line": line}
                rule_ms.append(payload["rule_elapsed_ms"])
                phase_rule.setdefault(payload["window"]["phase"], []).append(payload["rule_elapsed_ms"])
            if kind == "decision_planned":
                key = context["decision_id"], payload["plan_revision"]
                assert key in inputs and key not in planned_keys
                planned_keys.add(key)
                plans += 1
                policy_ms.append(payload["policy_elapsed_ms"])
                phase = inputs[key]["phase"]
                phase_policy.setdefault(phase, []).append(payload["policy_elapsed_ms"])
                phase_local_total.setdefault(phase, []).append(
                    (record["monotonic_ns"] / 1e9 - inputs[key]["budget_origin_monotonic"]) * 1000)
                returned = payload.get("returned_plan")
                if returned is None:
                    failed.append({"context": context, "input": inputs[key], "plan_source": str(path.relative_to(BASE)),
                                   "plan_line": line, "policy_elapsed_ms": payload["policy_elapsed_ms"],
                                   "degraded_reasons": payload.get("degraded_reasons"),
                                   "returned_plan_encode_error": payload.get("returned_plan_encode_error")})
                else:
                    full += 1
                    complete_ms.append(payload["policy_elapsed_ms"])
                    candidates = returned["candidates"]
                    actual = sorted(c["action_key"] for c in candidates)
                    if actual != inputs[key]["legal"]:
                        mismatch.append({"context": context, "legal": inputs[key]["legal"], "actual": actual})
                    assert all(type(c["total_score"]) in (int, float) and math.isfinite(c["total_score"]) for c in candidates)
                    outputs += len(candidates)
                    coverage.append({"phase": inputs[key]["phase"], "legal_count": len(candidates)})
            if kind == "protocol_recovered":
                reasons = [x for x in payload.get("reasons", []) if "策略异常" in x]
                if reasons:
                    errors.append({"context": context, "reasons": reasons})
            if kind == "decision_ended":
                ends[str(payload.get("end_reason"))] += 1
            if kind == "submission_outcome" and "outcome_type" in payload:
                outcomes[payload["outcome_type"]] += 1
                if payload["outcome_type"] == "SubmitNotSent":
                    not_sent[str(payload.get("reason"))] += 1
    return {"run_id": run.name, "plans": plans, "complete_plans": full, "complete_legal_outputs": outputs,
            "inputs_without_plan_count": len(set(inputs) - planned_keys), "failed_plans": failed,
            "full_plan_legal_key_mismatches": mismatch, "policy_errors": errors, "kind_counts": dict(counts),
            "decision_end": dict(ends), "attempt_outcomes": dict(outcomes), "not_sent": dict(not_sent),
            "http_started": len(started), "http_finished": len(finished),
            "http_categories": {c: {s: n for (k, s), n in http.items() if k == c} for c in sorted({k for k, s in http})},
            "rule_elapsed": stats(rule_ms), "policy_elapsed": stats(policy_ms), "complete_policy_elapsed": stats(complete_ms),
            "state_queue_wait": stats(queue_ms), "state_transport_elapsed": stats(state_ms),
            "queue_waiters_at_grant_max": waiter_max, "state_purposes": dict(purposes),
            "complete_plans_by_phase": dict(Counter(c["phase"] for c in coverage)),
            "elapsed_by_phase": {phase: {"rule": stats(phase_rule[phase]), "policy": stats(phase_policy.get(phase, [])),
                                         "local_until_plan_record": stats(phase_local_total.get(phase, []))}
                                 for phase in phase_rule},
            "actual_audit_summary": load(run / "summary.json")}


def main():
    """实际完成四身份和赛后诊断后，独占写本批次汇总；错误退出而非伪造通过。"""
    assert load(_project_file(_PROJECT_ROOT, HERE / "ROOM-RUNNER-CHILD-TERMINAL.json"))["exit_code"] == 0
    assert load(_project_file(_PROJECT_ROOT, HERE / "POSTGAME-CHILD-TERMINAL.json"))["exit_code"] == 0
    assert load(_project_file(_PROJECT_ROOT, HERE / "ALL-TABLES-OFFICIAL-TOOL-TERMINAL.json"))["actual_exit_code"] == 0
    sources = {}
    runs = sorted(BASE.glob("audit/slot-*/runs/*"))
    assert len(runs) == 4
    audit = [audit_run(run, sources) for run in runs]
    terminals = []
    terminal = None
    for line in (_project_file(_PROJECT_ROOT, HERE / "ROOM-STDOUT-STDERR.log")).read_text().splitlines():
        match = re.match(r"\[([^]]+)\] (\w+) \| 终态: ([^|]+)\| .*exit=(-?\d+)$", line)
        if match:
            terminal = {"slot": match[1], "outcome": match[2], "terminal_reason": match[3].strip(),
                        "exit_code": int(match[4]), "origin": "实际子进程RESULT经run_test_room.report_lines转换；非原始RESULT原文"}
            terminals.append(terminal)
        elif terminal is not None and line.strip().startswith("run_id:"):
            terminal["run_id"] = line.split(":", 1)[1].strip()
        elif terminal is not None and "计算服务退出:" in line:
            terminal["decision_compute"] = json.loads(line[line.index("{"):])
    assert len(terminals) == 4 and {t["run_id"] for t in terminals} == {r.name for r in runs}
    assert all(t["exit_code"] == 0 and t["outcome"] == "completed" and "decision_compute" in t for t in terminals)
    tables, timeouts, event_counts = [], [], Counter()
    for path in sorted(BASE.glob("official/dl-*/events.json")):
        if (path.parent / "download-error.json").exists() or not (path.parent / "source.json").exists():
            continue
        body = load(path)
        sources[str(path.relative_to(BASE))] = hashlib.sha256(path.read_bytes()).hexdigest()
        assert body["status"] == "finished"
        events = {}
        for block in body["blocks"]:
            for event in block["events"]:
                if event["seq"] in events:
                    assert events[event["seq"]] == event
                events[event["seq"]] = event
        finals = [e["data"]["final_scores"] for e in events.values() if e["type"] == "game_ended"]
        assert len(finals) == 1
        tables.append({"game_id": body["game_id"], "rounds": len(body["rounds"]), "scores_seat_order": finals[0]})
        for event in events.values():
            event_counts[event["type"]] += 1
            if event["type"] == "timeout":
                timeouts.append({"game_id": body["game_id"], "event": event})
    assert len(tables) == 10 and len({t["game_id"] for t in tables}) == 10
    assert sum(t["rounds"] for t in tables) == 80
    latest = load(_project_file(_PROJECT_ROOT, BASE / "latest-postgame.json"))
    postgame = load(_project_file(_PROJECT_ROOT, BASE / latest["job"] / "report.json"))
    rule_checks = load(_project_file(_PROJECT_ROOT, HERE / "ALL-TABLES-OFFICIAL-RULE-READBACK.json"))["checks"]
    checked = Counter(s for r in rule_checks for s in (x["status"] for x in r.get("rounds", [])))
    conflicts = [x for r in rule_checks for x in r.get("origin_conflicts", [])]
    summary = {"room_id": load(_project_file(_PROJECT_ROOT, HERE / "ROOM-CREATED-REDACTED.json"))["room_id"], "scope": "engineering_only",
               "all_four_same_configuration": True, "unique_tables": 10, "unique_hands": 80,
               "all_slots": audit, "participant_terminal_records": terminals, "all_tables": tables,
               "official_unique_event_counts": dict(event_counts), "official_timeouts": timeouts,
               "official_discard_timeouts": [t for t in timeouts if t["event"].get("data", {}).get("kind") == "discard"],
               "official_rule_statuses": dict(checked), "official_origin_conflicts": conflicts,
               "official_final_scores_match": [r.get("final_scores_match") for r in rule_checks],
               "postgame_audit_complete": postgame["audit_complete"],
               "first_postgame_official_tables": postgame["official_documents"],
               "full_observation_views_official_field_recheck": False,
               "strict_full_plan_zero_fault_gate": (all(a["plans"] == a["complete_plans"] for a in audit)
                    and all(t["decision_compute"]["faults"] == t["decision_compute"]["policy_failures"] == 0 for t in terminals)),
               "causal_strength_admission": False, "formal_release": False,
               "interpretation": "四身份是同一10桌的四视角，不能当40独立桌；纯工程实验不授相对R18改进。降级完整保留，后续须结合合法选择、截止时间与官方结果判断影响。",
               "source_sha256": sources}
    with (_project_file(_PROJECT_ROOT, HERE / "ROOM-AUDIT-SUMMARY.json")).open("x") as stream:
        json.dump(summary, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"tables": 10, "hands": 80, "plans": sum(a["plans"] for a in audit),
                      "complete_plans": sum(a["complete_plans"] for a in audit),
                      "discard_timeouts": len(summary["official_discard_timeouts"]),
                      "rule_statuses": dict(checked), "strict_full_plan_zero_fault_gate": summary["strict_full_plan_zero_fault_gate"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
