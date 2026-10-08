"""P80 自然暴露顺序恢复：保留原冻结谓词与来源，只替换被 SIGTERM 的进程池编排。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import hashlib
import json
from pathlib import Path
import shutil

import confirmation_execution_identity as guard
import r18_p80_high_wealth_near_seven_claim_exposure as p80
import sitin_natural_panel as natural
import sitin_search as search
import strong_seed_batch as batch


OUT = p80.OUT
RECOVERY_AUTH = OUT / "recovery-authorization.json"
RECOVERY_MANIFEST = OUT / "recovery-manifest.json"
INITIAL_SUMMARY = OUT / "initial-run-summary.json"
RECOVERY_LEDGER = OUT / "recovery-ledger.json"
RECOVERY_RESULT = OUT / "recovery-result.json"


def digest(path: Path) -> str:
    """返回文件字节的 SHA-256 摘要。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _successful_source_count() -> int:
    """只接受已落盘且恰好完成两桌的来源。"""

    completed = 0
    for source in p80.sources():
        path = p80.source_path(source)
        if not path.exists():
            continue
        document = json.loads(path.read_text(encoding="utf-8"))
        if (document.get("status") != "complete"
                or document.get("tables") != p80.TABLES_PER_SOURCE
                or document.get("audit", {}).get("problems")):
            raise ValueError("P80 已落盘来源不完整：" + str(path))
        completed += 1
    return completed


def prepare() -> None:
    """从失败账派生独立恢复额度；不修改 P80 冻结清单和谓词。"""

    p80.verify()
    if any(path.exists() for path in (
        RECOVERY_AUTH, RECOVERY_MANIFEST, INITIAL_SUMMARY, RECOVERY_LEDGER,
    )):
        raise SystemExit("P80 恢复批次已准备；拒绝覆盖")
    failed = json.loads((OUT / "run-summary.json").read_text(encoding="utf-8"))
    completed = _successful_source_count()
    if (not failed.get("failures") or failed.get("actual_tables") != 2 * completed
            or completed <= 0 or completed >= len(p80.sources())):
        raise ValueError("P80 原始进程池失败证据与已成来源不一致")
    shutil.copy2(OUT / "run-summary.json", INITIAL_SUMMARY)
    pending = len(p80.sources()) - completed
    additional_tables = pending * p80.TABLES_PER_SOURCE
    authorization = batch.unified_document(
        batch_label=OUT.name + "-sequential-recovery",
        authorization_id="r18-p80-sequential-recovery-01",
        accounts={"tables_full": additional_tables},
        issued_by="lead", issued_at_utc=search.utc_now(), legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": (
            "原P80进程池的工作进程收到SIGTERM并按使用量未知保守计满512桌；"
            "原样重用冻结来源和谓词，以顺序执行补完未落盘来源"
        ),
        "scope": f"只补 {pending} 个原冻结来源、每来源两桌；不生成收益标签",
        "max_model_calls": 0,
        "confirmation_roots": 0,
        "prior_charge_tables_full": p80.PLANNED_TABLES,
    })
    p80.write_json(RECOVERY_AUTH, authorization)
    tracked = [
        Path(__file__), Path(p80.__file__), OUT / "manifest.json",
        OUT / "sources.json", INITIAL_SUMMARY, RECOVERY_AUTH,
    ]
    p80.write_json(RECOVERY_MANIFEST, {
        "schema": "r18-p80-sequential-recovery-manifest/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(source_paths=tracked),
        "p80_manifest_sha256": digest(OUT / "manifest.json"),
        "initial_summary_sha256": digest(INITIAL_SUMMARY),
        "recovery_authorization_sha256": digest(RECOVERY_AUTH),
        "completed_sources_before_recovery": completed,
        "pending_sources": pending,
        "additional_authorized_tables_full": additional_tables,
        "execution_mode": "single_process_sequential",
        "outcome_blind": True,
        "selection_eligible": False,
    })
    print(json.dumps({"status": "PREPARED", "completed_sources": completed,
                      "pending_sources": pending, "additional_tables": additional_tables},
                     ensure_ascii=False), flush=True)


def verify() -> dict:
    """核对冻结恢复批次与 P80 原批次均未漂移。"""

    p80.verify()
    manifest = json.loads(RECOVERY_MANIFEST.read_text(encoding="utf-8"))
    guard.verify(manifest["runtime"])
    if (manifest["p80_manifest_sha256"] != digest(OUT / "manifest.json")
            or manifest["initial_summary_sha256"] != digest(INITIAL_SUMMARY)
            or manifest["recovery_authorization_sha256"] != digest(RECOVERY_AUTH)):
        raise ValueError("P80 顺序恢复输入摘要漂移")
    return manifest


def run() -> None:
    """每来源先预留两桌额度、完成后立刻写证据与结算，可安全从来源边界续跑。"""

    manifest = verify()
    authorization = json.loads(RECOVERY_AUTH.read_text(encoding="utf-8"))
    natural.require_authorization(authorization)
    ledger = search.ActionValueLedger.load(
        RECOVERY_LEDGER,
        authorized_budgets=search.av_ledger_budgets_from_authorization(authorization),
    )
    completed = _successful_source_count()
    for source in p80.sources():
        path = p80.source_path(source)
        if path.exists():
            continue
        reservation = ledger.reserve(
            step_id="r18:p80:sequential-recovery:" + source["source_id"],
            account="tables_full", amount=p80.TABLES_PER_SOURCE,
            note="原冻结自然来源顺序重放；不读取收益",
        )
        try:
            result = p80.execute_source(source)
            if (result["status"] != "complete"
                    or result["tables"] != p80.TABLES_PER_SOURCE
                    or result["audit"]["problems"]):
                raise RuntimeError("自然来源未完整或重评分异常：" + str(source["source_id"]))
            p80.write_json(path, result)
            ledger.settle(reservation, actual=p80.TABLES_PER_SOURCE,
                          note="两桌完整且结果盲筛选成功")
        except BaseException:
            ledger.settle(reservation, usage_unknown=True,
                          note="顺序恢复来源异常；保守结算两桌")
            raise
        completed += 1
        if completed % 8 == 0 or completed == len(p80.sources()):
            print(json.dumps({"completed_sources": completed,
                              "total_sources": len(p80.sources())},
                             ensure_ascii=False), flush=True)
    if completed != len(p80.sources()):
        raise RuntimeError("P80 顺序恢复来源未跑满")
    files = list((OUT / "sources").glob("*.json"))
    if len(files) != len(p80.sources()):
        raise RuntimeError("P80 顺序恢复来源文件数量不符")
    p80.write_json(RECOVERY_RESULT, {
        "schema": "r18-p80-sequential-recovery-result/1",
        "status": "COMPLETE",
        "initial_summary_sha256": manifest["initial_summary_sha256"],
        "completed_sources": completed,
        "actual_tables": p80.PLANNED_TABLES,
        "recovery_spent": ledger.account_summary(),
        "outcome_blind": True,
    })
    p80.write_json(OUT / "run-summary.json", {
        "schema": "r18-p80-high-wealth-near-seven-run-summary/1",
        "source_files": completed,
        "actual_tables": p80.PLANNED_TABLES,
        "failures": [],
        "prior_failed_attempt": str(INITIAL_SUMMARY.name),
        "recovery_result": str(RECOVERY_RESULT.name),
        "prior_charge_tables_full": p80.PLANNED_TABLES,
        "recovery_spent": ledger.account_summary(),
    })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "run", "verify"))
    args = parser.parse_args()
    if args.command == "prepare":
        prepare()
    elif args.command == "run":
        run()
    else:
        print(json.dumps(verify(), ensure_ascii=False)[0:240], flush=True)


if __name__ == "__main__":
    main()
