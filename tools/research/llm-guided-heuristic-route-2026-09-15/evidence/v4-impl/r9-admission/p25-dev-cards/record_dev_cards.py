"""P25 小规模新调用诊断 · **逐卡记录 + 链路判定**生成器（零模型）。

输入：判据产物（criterion.py 的 JSON）、卫生审计/veto（dev_pipeline.py audit 的 JSON）、
无权限通道派发账本（dispatch_headless.py 的 JSON）、卡包 manifest。输出：
  * reports/per-card-record.json —— 机器可读逐卡记录；
  * reports/per-card-record.md   —— 同一份记录的可读版（含链路判定与真实花费）。

记录口径（复审 §3 第 2 步）：
  1. 首答失败根因：具名诊断条（错误码 + 判据出处 + 位置 + 实际结果），不写"其它条"；
  2. 反馈内容：修复提示词里的具名条目（逐字取自 repair-prompts.json 的诊断块）；
  3. 修复是否消除原故障 / **是否引入新故障**：首答与修复的具名失败集合做差；
  4. 行为是否改变：判分器的 code_changed / behavior_changed / text_changed + attempt_change；
  5. 真实花费：token 与耗时只从**会话日志**与**派发账本**实测恢复，缺失即 null，绝不推算。

链路判定（每张卡落到 ①模型能力问题 还是 ②测量/实现问题）只由下面的**机器信号**决定，
信号逐条写进产物：
  测量类信号（存在即判测量问题）：
    * suspect_false_reject —— 归因提示判定失败由「复述后拒绝」「否定语境里的要素线索」造成；
    * control_regression   —— 本轮控制的期望结论与实际不符（等行为控制/阴性控制/误拒探针）；
  模型类信号：
    * contract_violation   —— 冻结判分器判定违规（越权/多候选/硬禁项/自身主张的禁式）；
    * substantive_failure  —— 冻结判据的具名失败条目（值工程语义，且无测量信号）。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-dev-cards'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKAGE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-dev-cards/package')


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8")) if Path(path).is_file() else None


def fault_set(criterion: dict, attempt: str) -> dict:
    """一次尝试的**具名失败集合**（拒绝"其它条"式的聚合表述）。"""
    checks = (criterion or {}).get(attempt + "_criterion") or {}
    failed, informational = {}, {}
    for name, value in checks.items():
        if name == "card_ok" or not isinstance(value, dict):
            continue
        if value.get("informational"):
            informational[name] = value.get("ok")
            continue
        if value.get("ok") is False:
            failed[name] = value
    return {"card_ok": checks.get("card_ok"), "failed_checks": sorted(failed),
            "failed_detail": failed, "informational": informational}


def diagnostic_rows(row: dict, key: str = "diagnostics_first") -> list:
    """具名诊断条（错误码 + 判据出处 + 位置 + 实际结果），逐条进记录。"""
    out = []
    for entry in row.get(key) or ():
        location = entry.get("source_location") or {}
        out.append({
            "code": entry.get("code"),
            "contract_path": entry.get("contract_path"),
            "source_location": (location.get("status") if isinstance(location, dict) else None),
            "source_line": (location.get("line") if isinstance(location, dict) else None),
            "actual_type_or_status": entry.get("actual_type_or_status"),
            "expected_predicate": entry.get("expected_predicate"),
            "public_example": entry.get("public_example"),
            "explanation": entry.get("explanation"),
            "count": entry.get("count"),
        })
    return out


def measurement_signals(card: dict, controls: dict) -> list:
    """测量侧信号：归因提示 + 控制回归。"""
    signals = []
    for attempt in ("first", "repair"):
        detail = ((card.get(attempt) or {}).get("criterion_detail") or {})
        for check, value in detail.items():
            if not isinstance(value, dict):
                continue
            if check in ("no_result_predicate_attribution", "contrary_claim_attribution",
                         "forbidden_hit_attribution"):
                if value.get("ok") is False:
                    signals.append({
                        "kind": "suspect_false_reject", "attempt": attempt, "check": check,
                        "verdict": value.get("verdict"),
                        "hits": value.get("hits") or value.get("rows"),
                    })
            if check == "equivalence_controls" and value.get("ok") is False:
                signals.append({"kind": "control_regression", "attempt": attempt,
                                "check": check,
                                "controls": {name: item.get("verdict")
                                             for name, item in (value.get("controls") or {}).items()
                                             if item.get("ok") is False}})
    # 注意：全局控制（等行为负例 / 阴性控制 / 误拒探针）是**整批测量侧发现**，不是某张卡的
    # 失败原因——把它们算进逐卡信号会把模型侧失败误判成测量问题。它们单列在
    # payload["measurement_findings_global"]，逐卡判定只看该卡自己的检查项。
    return signals


def global_measurement_findings(controls: dict) -> list:
    """整批测量侧发现（控制未达期望），逐条具名；不参与逐卡链路判定的模型/测量归属。"""
    findings = []
    for name, value in (controls or {}).items():
        if isinstance(value, dict) and value.get("ok") is False:
            findings.append({"control": name, "expected": value.get("note") or
                             value.get("predicate"),
                             "detail": value.get("probes") or value.get("message")})
    return findings


def model_signals(card: dict) -> list:
    signals = []
    for attempt in ("first", "repair"):
        block = card.get(attempt) or {}
        if block.get("violations"):
            signals.append({"kind": "contract_violation", "attempt": attempt,
                            "violations": block["violations"]})
        if block.get("problems"):
            signals.append({"kind": "substantive_failure", "attempt": attempt,
                            "problems": block["problems"]})
        faults = (block.get("criterion") or {}).get("failed_checks") or []
        if faults:
            signals.append({"kind": "substantive_failure", "attempt": attempt,
                            "failed_checks": faults})
    return signals


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--criterion", required=True)
    parser.add_argument("--audit", action="append", default=[])
    parser.add_argument("--dispatch-ledger", action="append", default=[])
    parser.add_argument("--repair-prompts", default=str(_project_file(_PROJECT_ROOT, HERE / "repair-prompts.json")))
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-md", required=True)
    parser.add_argument("--verdict-json", default=None,
                        help="链路判定单独产物（每张卡落到 模型 / 测量）")
    args = parser.parse_args()

    report = load(args.criterion) or {}
    manifest = load(_project_file(_PROJECT_ROOT, PACKAGE / "manifest.json")) or {}
    faces = {row["task_id"]: row for row in manifest.get("cards") or []}
    audits_raw = [item for item in (load(p) for p in args.audit) if item]
    ledgers = [item for item in (load(p) for p in args.dispatch_ledger) if item]
    repair_manifest = load(args.repair_prompts) or {}

    # 轮次从**文件名**判定：dispatch_headless 的每文件账本不含 kind 字段（只有 ledger.jsonl
    # 的汇总行有），按内容读会把修复轮当成首答、覆盖首答的耗时与 run_id。
    runs = {}
    for path, ledger in zip([p for p in args.dispatch_ledger], ledgers):
        kind = "repair" if "-repair-" in Path(path).name else "first"
        for call in ledger.get("calls") or ():
            runs[(call.get("task"), kind)] = call

    audit_rows, vetoes = {}, []
    for item in audits_raw:
        vetoes.append({"veto": item.get("veto"), "clean": item.get("audit", {}).get("clean"),
                       "plan_problems": item.get("audit", {}).get("plan_problems"),
                       "authority": item.get("audit", {}).get("prompt_authority"),
                       "expected_prompts": item.get("expected_prompts")})
        for row in item.get("audit", {}).get("rows") or ():
            audit_rows[(row.get("task_id"), row.get("kind") or "first")] = {
                "status": row.get("status"),
                "prompt_authority": row.get("prompt_authority"),
                "expected_prompt_sha256": row.get("expected_prompt_sha256"),
                "prompt_sha256": row.get("prompt_sha256"),
                "protocol_violations": (row.get("protocol") or {}).get("violations"),
                "request_headers": (row.get("protocol") or {}).get("request_headers"),
                "turn_ends": (row.get("protocol") or {}).get("turn_ends"),
                "post_termination_work": (row.get("protocol") or {}).get("post_termination_work"),
                "tool_calls": row.get("tool_calls"),
                "unregistered_context_blocks": row.get("unregistered_context_blocks"),
                "answer_chars": row.get("answer_chars"),
                "session_sha256": row.get("session_sha256"),
            }

    cards = []
    for row in report.get("cards") or []:
        card_id = row["card_id"]
        meta = faces.get(card_id) or {}
        first_faults = fault_set(row, "first")
        repair_faults = fault_set(row, "repair") if row.get("repair_criterion") else None
        removed = introduced = None
        if repair_faults:
            removed = sorted(set(first_faults["failed_checks"])
                             - set(repair_faults["failed_checks"]))
            introduced = sorted(set(repair_faults["failed_checks"])
                                - set(first_faults["failed_checks"]))
        cost = {}
        for attempt in ("first", "repair"):
            usage = (row.get("usage") or {}).get(attempt) or {}
            call = runs.get((card_id, attempt)) or {}
            cost[attempt] = {
                "run_id": usage.get("run_id") or call.get("run_id"),
                "usage": usage.get("usage") or None,
                "elapsed_s": call.get("elapsed_s") or (row.get("elapsed_s") or {}).get(attempt),
                "session_status": usage.get("source_status"),
                "model": (call.get("model") or {}).get("model"),
                "request_config": call.get("request_config"),
                "step_start": call.get("step_start"),
                "tool_calls": call.get("tool_calls"),
            }
        repair_block = {"used": False}
        if repair_faults is not None:
            change = row.get("attempt_change") or {}
            delta = row.get("repair_delta") or {}
            # 「是否引入新故障」要把**逐窗差异**并进来：卡级检查项可能两次都通过，而修复
            # 已经把某个本来可解的窗口改成弃权（TD01 的 fam_discard 就是这种）。
            delta_introduced = sorted(
                ["coverage_regression:" + name
                 for name in delta.get("coverage_regression_views") or []]
                + ["unknown_offside_broken:" + name
                   for name in delta.get("unknown_offside_broken_windows") or []])
            delta_removed = sorted(
                ["unknown_offside_fixed:" + name
                 for name in delta.get("unknown_offside_fixed_windows") or []])
            repair_block = {
                "used": True,
                "frozen_pass": row.get("frozen_repair_pass"),
                "diagnostic_codes": row.get("repair_diagnostic_codes"),
                "faults": repair_faults,
                "faults_removed": sorted(set(removed or []) | set(delta_removed)),
                "faults_introduced": sorted(set(introduced or []) | set(delta_introduced)),
                "fault_removed": bool(set(removed or []) | set(delta_removed))
                                 and not (set(introduced or []) | set(delta_introduced)),
                "attempt_change": {
                    "code_changed": change.get("code_changed"),
                    "behavior_changed": change.get("behavior_changed"),
                    "text_changed": change.get("text_changed"),
                },
                "repair_gate": row.get("repair_gate"),
                "repair_delta": row.get("repair_delta"),
                "problems": row.get("repair_problems"),
                "violations": row.get("repair_violations"),
                "criterion_detail": row.get("repair_criterion"),
            }
        card = {
            "card_id": card_id,
            "capability_face": meta.get("capability_face"),
            "title": meta.get("title"),
            "audit": {kind: audit_rows.get((card_id, kind))
                      for kind in ("first", "repair")},
            "first": {
                "frozen_pass": row.get("frozen_first_pass"),
                "outcome_class": row.get("outcome_class"),
                "evidence_status": row.get("evidence_status"),
                "diagnostic_codes": row.get("diagnostic_codes_first"),
                "diagnostics": diagnostic_rows(row, "diagnostics_first"),
                "problems": row.get("problems_first"),
                "violations": row.get("violations_first"),
                "criterion": {key: value for key, value in first_faults.items()
                              if key != "failed_detail"},
                "criterion_detail": row.get("first_criterion"),
            },
            "repair": repair_block,
            "final_pass": row.get("frozen_final_pass"),
            "cost": cost,
        }
        measurement = measurement_signals(card, report.get("negative_controls"))
        model = model_signals(card)
        if card["final_pass"] and (repair_faults or first_faults).get("card_ok"):
            verdict = "PASS"
        elif measurement:
            verdict = "MEASUREMENT"
        elif model:
            verdict = "MODEL"
        else:
            verdict = "UNDETERMINED"
        card["link_verdict"] = {
            "verdict": verdict,
            "measurement_signals": measurement,
            "model_signals": model,
            "note": ("PASS = 该卡最终通过；MEASUREMENT = 存在测量侧信号（归因提示/控制回归）；"
                     "MODEL = 存在模型侧具名失败而无疑似测量问题；UNDETERMINED = 无信号但未通过"),
        }
        cards.append(card)

    feedback = {row["task_id"]: {
        "diagnostics_available": row.get("diagnostics_available"),
        "diagnostic_source": row.get("diagnostic_source"),
        "diagnostic_codes": (row.get("diagnostic_stats") or {}).get("codes"),
        "redactions": (row.get("diagnostic_stats") or {}).get("redactions"),
        "added_chars": row.get("added_chars"),
        "leak_tokens": row.get("leak_tokens"),
    } for row in (repair_manifest.get("tasks") or [])}

    totals = {"calls": 0, "usage": {}, "elapsed_s": 0.0}
    for card in cards:
        for attempt in ("first", "repair"):
            entry = card["cost"].get(attempt) or {}
            if not entry.get("run_id"):
                continue
            totals["calls"] += 1
            for key, value in (entry.get("usage") or {}).items():
                if isinstance(value, int) and not isinstance(value, bool):
                    totals["usage"][key] = totals["usage"].get(key, 0) + value
            if isinstance(entry.get("elapsed_s"), (int, float)):
                totals["elapsed_s"] = round(totals["elapsed_s"] + entry["elapsed_s"], 2)

    payload = {
        "schema": "sitin-p25-dev-cards-record/1",
        "round_label": report.get("round_label"),
        "grader_identity": report.get("grader_identity"),
        "dev_stop_spec_mirror_check": report.get("dev_stop_spec_mirror_check"),
        "dev_spec_registration": report.get("dev_spec_registration"),
        "measurement_controls": report.get("negative_controls"),
        "hygiene": {"vetoes": vetoes,
                    "note": "题面权威 = frozen_rebuilt；不放宽任何审计项"},
        "measurement_findings_global": global_measurement_findings(
            report.get("negative_controls")),
        "repair_feedback": feedback,
        "cards": cards,
        "totals": totals,
        "note": ("逐卡记录：首答根因 / 反馈 / 修复是否消除原故障 / 是否引入新故障 / 行为是否改变 / "
                 "真实花费（实测）。开发卡不设门槛，不用于任何准入结论。"),
    }
    Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_json).write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                                   encoding="utf-8")

    lines = ["# P25 小规模新调用诊断 · 逐卡记录", "",
             "- 轮次：{0}".format(payload["round_label"]),
             "- 判分器身份：{0}…".format((report.get("grader_identity") or {})
                                         .get("grader_sha256", "")[:16]),
             "- 真实花费合计：{0} 次调用，token {1}，墙钟 {2} 秒".format(
                 totals["calls"], json.dumps(totals["usage"], ensure_ascii=False),
                 totals["elapsed_s"]),
             ""]
    for card in cards:
        lines += ["## {0} · {1}".format(card["card_id"], card["capability_face"]), "",
                  "| 项 | 值 |", "| --- | --- |",
                  "| 首答 | {0}（{1}） |".format(card["first"]["frozen_pass"],
                                                card["first"]["outcome_class"]),
                  "| 首答具名诊断 | {0} |".format(
                      ", ".join(card["first"]["diagnostic_codes"] or []) or "（无）"),
                  "| 修复 | {0} |".format(
                      ("未派发" if not card["repair"]["used"] else
                       "通过={0}；消除={1}；新引入={2}".format(
                           card["repair"]["frozen_pass"],
                           card["repair"]["faults_removed"] or [],
                           card["repair"]["faults_introduced"] or []))),
                  "| 行为改变 | {0} |".format(
                      json.dumps(card["repair"].get("attempt_change"), ensure_ascii=False)
                      if card["repair"]["used"] else "（无修复轮）"),
                  "| 最终 | {0} |".format(card["final_pass"]),
                  "| 链路判定 | **{0}** |".format(card["link_verdict"]["verdict"]),
                  "| 花费 | 首答 {0} / 修复 {1} |".format(
                      json.dumps(card["cost"]["first"].get("usage"), ensure_ascii=False),
                      json.dumps((card["cost"].get("repair") or {}).get("usage"),
                                 ensure_ascii=False)),
                  ""]
    Path(args.out_md).write_text("\n".join(lines) + "\n", encoding="utf-8")

    if args.verdict_json:
        verdict_payload = {
            "schema": "sitin-p25-dev-cards-link-verdict/1",
            "round_label": payload["round_label"],
            "rule": ("PASS = 最终通过且卡级判据通过；MEASUREMENT = 该卡自己的失败带有测量侧信号"
                     "（归因提示：否定语境里的要素线索 / 复述后拒绝 / 描述后果的禁词命中）；"
                     "MODEL = 模型侧具名失败而无疑似测量问题；UNDETERMINED = 无信号但未通过。"
                     "整批控制未达期望另列 measurement_findings_global，不参与逐卡归属。"),
            "cards": [{"card_id": card["card_id"],
                       "capability_face": card["capability_face"],
                       "verdict": card["link_verdict"]["verdict"],
                       "final_pass": card["final_pass"],
                       "measurement_signals": card["link_verdict"]["measurement_signals"],
                       "model_signals": card["link_verdict"]["model_signals"]}
                      for card in cards],
            "measurement_findings_global": payload["measurement_findings_global"],
            "totals": totals,
        }
        Path(args.verdict_json).write_text(
            json.dumps(verdict_payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"cards": len(cards), "totals": totals,
                      "verdicts": {c["card_id"]: c["link_verdict"]["verdict"]
                                   for c in cards},
                      "out_json": args.out_json, "out_md": args.out_md},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
