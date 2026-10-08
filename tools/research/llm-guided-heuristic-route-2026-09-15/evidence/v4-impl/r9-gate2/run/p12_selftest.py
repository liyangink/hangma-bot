#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""P12 纯数据自测：状态词表 / 授权双形态 / 摘要 schema / 预算口径 / 逐键对账。

全部为**纯数据**断言（0 桌、0 模型调用、0 网络）；解释器用仓库 `.venv/bin/python`。
任一断言失败即返回非零并打印反例，便于在评审里直接复跑。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-gate2/run'

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
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import p12_authorization as AUTH     # noqa: E402
import p12_budget as BUDGET          # noqa: E402
import p12_reconcile as REC          # noqa: E402
import p12_status as STATUS          # noqa: E402

RESULTS: List[Dict[str, Any]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append({"name": name, "ok": bool(ok), "detail": detail})


def test_status_vocabulary() -> None:
    rows = [{"name": "a", "ok": True},
            {"name": "b", "ok": False, "insufficient": True},
            {"name": "c", "ok": False},
            {"name": "d", "ok": True, "applicable": False}]
    words = [STATUS.check_status(row) for row in rows]
    record("status_four_words",
           words == [STATUS.PASS, STATUS.INSUFFICIENT, STATUS.FAIL,
                     STATUS.NOT_APPLICABLE], json.dumps(words))
    record("status_not_applicable_is_not_pass",
           STATUS.check_status({"ok": True, "applicable": False})
           == STATUS.NOT_APPLICABLE)
    record("status_insufficient_is_not_fail",
           STATUS.check_status({"ok": False, "insufficient": True})
           == STATUS.INSUFFICIENT)
    empty = STATUS.rollup([])
    record("status_empty_group_is_not_pass", empty["status"] == STATUS.NOT_APPLICABLE,
           json.dumps(empty, ensure_ascii=False))
    worst = STATUS.worst(STATUS.PASS, STATUS.INSUFFICIENT, STATUS.NOT_APPLICABLE)
    record("status_worst_is_insufficient", worst == STATUS.INSUFFICIENT)
    # 分项签收：四项不变量全绿 + 六步有一组 INSUFFICIENT ⇒ 整链不得是 PASS
    signoff = STATUS.sign_off(
        reconciliation_rows=[{"name": name, "ok": True}
                             for name, _ in STATUS.RECONCILIATION_INVARIANTS],
        capability_rows={1: [{"name": "x", "ok": False, "insufficient": True}],
                         2: [{"name": "y", "ok": True}]})
    record("signoff_partial_pass_is_not_chain_pass",
           signoff["reconciliation_invariants"]["status"] == STATUS.PASS
           and signoff["chain"]["status"] == STATUS.INSUFFICIENT,
           json.dumps(signoff["chain"], ensure_ascii=False))


def test_authorization_forms() -> None:
    accounts = {"tables_full": 216.0, "tables_partial": 122.0,
                "prefix_generation": 101.0, "tokens_input": 0.0,
                "tokens_output": 0.0, "confirm_reserved": 0.0}
    legacy = {"authorized": True, "batch": 7, "budgets": dict(accounts)}
    unified = AUTH.unified_document(batch_label="gate2-20260918",
                                    authorization_id="auth-1", accounts=accounts,
                                    issued_at_utc="2026-09-18T00:00:00Z",
                                    legacy_alias=False)
    dual = AUTH.unified_document(batch_label="gate2-20260918",
                                 authorization_id="auth-1", accounts=accounts,
                                 issued_at_utc="2026-09-18T00:00:00Z",
                                 legacy_alias=True)
    ok_legacy = AUTH.validate(legacy, expected_batch_label="gate2-20260918")
    ok_unified = AUTH.validate(unified, expected_batch_label="gate2-20260918",
                               required_operations=AUTH.ALLOWED_OPERATIONS)
    ok_dual = AUTH.validate(dual, expected_batch_label="gate2-20260918",
                            required_operations=AUTH.ALLOWED_OPERATIONS)
    record("auth_legacy_accepted",
           ok_legacy["ok"] and ok_legacy["authorization_form"] == AUTH.FORM_LEGACY,
           ok_legacy["authorization_form"])
    record("auth_unified_accepted",
           ok_unified["ok"] and ok_unified["authorization_form"] == AUTH.FORM_UNIFIED,
           ok_unified["authorization_form"])
    record("auth_dual_accepted",
           ok_dual["ok"] and ok_dual["authorization_form"] == AUTH.FORM_DUAL,
           ok_dual["authorization_form"])
    record("auth_budgets_consistent_across_forms",
           ok_dual["budgets"] == accounts, json.dumps(ok_dual["budgets"]))
    # 失败关闭：任一必需元素缺失/不实都必须拒绝
    bad_cases = {
        "trusted_false": dict(unified, trusted=False),
        "missing_account": dict(unified, allowed_accounts={k: v for k, v in
                                                           accounts.items()
                                                           if k != "tables_full"}),
        "unknown_operation": dict(unified, allowed_operations=["natural_panel", "evil"]),
        "bad_iso": dict(unified, issued_at_utc="2026/09/18"),
        "empty_operations": dict(unified, allowed_operations=[]),
        "legacy_batch_wrong": dict(legacy, batch=8),
        "dual_budget_clash": dict(dual, allowed_accounts=dict(
            dual["allowed_accounts"], tables_full=1.0)),
    }
    failures = {name: AUTH.validate(doc, expected_batch_label="gate2-20260918")["ok"]
                for name, doc in bad_cases.items()}
    record("auth_fail_closed", not any(failures.values()),
           json.dumps(failures, ensure_ascii=False))
    record("auth_unknown_form_rejected",
           not AUTH.validate({"hello": 1})["ok"])


def test_digest_schemas() -> None:
    """嵌套样本摘要 vs 整文件摘要：两种 schema 各自重算，不混用。"""
    import tempfile
    arm = {"u": 1.0, "status": "complete", "candidate_id": "cand-A"}
    nested = REC.sha256_bytes(REC.canonical_json(arm).encode("utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
        panel = Path(tmp) / "panel.json"
        panel.write_text(json.dumps({"samples": [
            {"source_root_id": "np-H-1-root01", "focal_anchor_seat": 0,
             "arms": {"candidate": arm}}]}, ensure_ascii=False), encoding="utf-8")
        row = {"source_root_id": "np-H-1-root01", "seat": 0, "arm": "candidate",
               "candidate_id": "cand-A"}
        good = REC.verify_result_digest(channel=REC.CHANNEL_NATURAL, row=row,
                                        attempt={"result_digest": nested,
                                                 "result_path": str(panel)})
        record("digest_nested_verified", good["state"] == "verified",
               json.dumps(good, ensure_ascii=False))
        # 改内容不改摘要 ⇒ 必须 mismatch（全文件摘要参与进来也不能补上）
        panel.write_text(json.dumps({"samples": [
            {"source_root_id": "np-H-1-root01", "focal_anchor_seat": 0,
             "arms": {"candidate": dict(arm, u=0.0)}}]}, ensure_ascii=False),
            encoding="utf-8")
        tampered = REC.verify_result_digest(channel=REC.CHANNEL_NATURAL, row=row,
                                            attempt={"result_digest": nested,
                                                     "result_path": str(panel)})
        record("digest_nested_tamper_red", tampered["state"] == "mismatch",
               tampered["detail"])
        record("digest_schema_is_nested_not_whole_file",
               good["schema"] == REC.DIGEST_SCHEMA_NESTED_ARM)
        # 家族：整文件摘要
        fam = Path(tmp) / "evaluation.json"
        fam.write_text(json.dumps({"ok": True, "samples": []}), encoding="utf-8")
        whole = REC.sha256_file(fam)
        fam_good = REC.verify_result_digest(
            channel=REC.CHANNEL_FAMILY, row={},
            attempt={"result_digest": whole, "result_path": str(fam)})
        record("digest_whole_file_verified", fam_good["state"] == "verified"
               and fam_good["schema"] == REC.DIGEST_SCHEMA_WHOLE_FILE)
    record("digest_conditional_is_insufficient_not_pass",
           REC.verify_result_digest(channel=REC.CHANNEL_CONDITIONAL, row={},
                                    attempt={})["state"] == "no_recorded_digest")


def test_natural_counting() -> None:
    case = BUDGET.reference_case_check()
    record("natural_formula_reference_case_128", case["ok"],
           json.dumps(case, ensure_ascii=False))
    record("natural_formula_not_256_when_scenarios_already_bucketed",
           case["authoritative_tables"] == 128
           and case["conservative_upper_bound"] == 256,
           json.dumps(case, ensure_ascii=False))


def test_reconcile_on_run(run_root: Optional[Path], plan_path: Optional[Path]) -> None:
    if not run_root or not plan_path or not Path(run_root).is_dir():
        record("reconcile_real_run", False, "缺少 --run-root/--plan（跳过即不可签收）")
        return
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    join = REC.reconcile_instances(Path(run_root), plan)
    checks = {row["name"]: row for row in REC.check_rows(join)}
    lost = checks["zero_lost_instances_by_key"]
    record("reconcile_no_unaccounted_missing", not lost.get("unaccounted_count"),
           json.dumps(lost.get("unaccounted_missing"), ensure_ascii=False))
    record("reconcile_digest_no_mismatch",
           checks["zero_fake_completions"].get("mismatch_count") == 0)
    cost_rows = checks["cost_joined_per_channel"].get("cost_rows") or []
    record("reconcile_cost_join_balances",
           all(abs(float(row.get(key) or 0.0)) < 1e-6
               for row in cost_rows for key in ("delta", "delta_full", "delta_partial")
               if key in row), json.dumps(cost_rows, ensure_ascii=False))
    record("reconcile_channels_are_separate",
           set(REC.CHANNELS) <= set((join.get("channels") or {}).keys()),
           json.dumps(sorted((join.get("channels") or {}).keys())))
    record("reconcile_terminal_classes_registered",
           all(str(item.get("terminal")) in {
               REC.TERMINAL_COMPLETED, REC.TERMINAL_FAILED, REC.TERMINAL_BUDGET,
               REC.TERMINAL_UNFINISHED, REC.TERMINAL_DIGEST_MISMATCH}
               for channel in REC.CHANNELS
               for item in ((join.get("channels") or {}).get(channel) or {}).get(
                   "items") or ()))
    reuse = join.get("reuse_references") or []
    record("reconcile_reuse_is_reference_only",
           all(row.get("reference_only") for row in reuse),
           "复用条目 {0} 条，全部只记引用".format(len(reuse)))


def test_requirement_digest_split(run_root: Optional[Path]) -> None:
    """Q3：`_requirement_digest_verdict` 必须把"可重算"与"已对拍一致"分成两个结论。"""

    if not run_root or not Path(run_root).is_dir():
        record("requirement_digest_split", False, "缺少 --run-root")
        return
    import gate2_run as G
    runner = G.Gate2Runner.__new__(G.Gate2Runner)   # 只调纯数据方法，不跑任何步骤
    runner.run_root = Path(run_root)
    cond = None
    fam = None
    for iter_dir in REC.iter_dirs(Path(run_root)):
        payload = REC.read_json(iter_dir / "conditional" / "evaluation.json") or {}
        for sample in (payload.get("samples") or ()):
            if sample.get("root_descriptor"):
                cond = sample
                break
        for path in (iter_dir / "family").glob("*/evaluation.json"):
            data = REC.read_json(path) or {}
            for sample in (data.get("samples") or ()):
                if sample.get("root_requirement_digest"):
                    fam = sample
                    break
            if fam:
                break
        if cond and fam:
            break
    if cond is None or fam is None:
        record("requirement_digest_split", False, "运行产物里找不到条件/家族样本")
        return
    cond_verdict = runner._requirement_digest_verdict(cond)
    fam_verdict = runner._requirement_digest_verdict(fam)
    fake_verdict = runner._requirement_digest_verdict(
        dict(fam, root_requirement_digest="deadbeef"))
    # Q3：条件样本自身不带要求摘要字段；若该运行的 **RootWitness**（P11 附属文件）
    # 已落地，验收器必须用见证把它判成"已对拍一致"；没有见证才记 INSUFFICIENT。
    witness_index = REC.witnesses_by_root(Path(run_root))
    if witness_index:
        record("requirement_digest_matched_via_root_witness",
               cond_verdict["recomputable"] and cond_verdict["matched"]
               and cond_verdict["status"] == STATUS.PASS
               and bool(cond_verdict.get("witness_source")),
               json.dumps({k: cond_verdict.get(k) for k in
                           ("recomputable", "matched", "status", "witness_source")},
                          ensure_ascii=False))
    else:
        record("requirement_digest_recomputable_is_not_matched",
               cond_verdict["recomputable"] and not cond_verdict["matched"]
               and cond_verdict["status"] == STATUS.INSUFFICIENT,
               json.dumps({k: cond_verdict[k] for k in
                           ("recomputable", "matched", "status", "reason")},
                          ensure_ascii=False))
    record("requirement_digest_matched_on_real_product",
           fam_verdict["recomputable"] and fam_verdict["matched"]
           and fam_verdict["status"] == STATUS.PASS,
           json.dumps({k: fam_verdict[k] for k in
                       ("recomputable", "matched", "status")}, ensure_ascii=False))
    record("requirement_digest_mismatch_is_fail",
           not fake_verdict["matched"] and fake_verdict["status"] == STATUS.FAIL)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="P12 纯数据自测")
    parser.add_argument("--run-root", default=None)
    parser.add_argument("--plan", default=None)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)
    test_status_vocabulary()
    test_authorization_forms()
    test_digest_schemas()
    test_natural_counting()
    test_reconcile_on_run(Path(args.run_root) if args.run_root else None,
                          Path(args.plan) if args.plan else None)
    test_requirement_digest_split(Path(args.run_root) if args.run_root else None)
    passed = sum(1 for row in RESULTS if row["ok"])
    payload = {"schema": "sitin-gate2-p12-selftest/1",
               "n_tests": len(RESULTS), "n_passed": passed,
               "ok": passed == len(RESULTS), "results": RESULTS,
               "note": "纯数据自测：0 桌、0 模型调用、0 网络"}
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                       encoding="utf-8")
    for row in RESULTS:
        print("  {0:<5} {1:<52} {2}".format(
            "PASS" if row["ok"] else "FAIL", row["name"], str(row["detail"])[:110]))
    print("P12 自测：{0}/{1} 通过{2}".format(passed, len(RESULTS),
                                             "" if payload["ok"] else "（有失败）"))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
