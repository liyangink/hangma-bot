"""已曝光开发根上的正式审计集成检查；工程控制策略，不是新提案或强度证据。"""

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
from pathlib import Path
import argparse
import json
import sys

import strong_seed_batch as batch
import confirmation_execution_identity as identity
import verify_full_natural_results as full
import sitin_execution_audit as audit
import sitin_natural_panel as natural
from sitin_process import run_supervised

HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/formal-execution-audit-20260920')
SOURCES = {
    "scored": 'def score_actions(view):\n    return {"status": "SCORED", "entries": [{"action_key": a["action_key"], "score": 0.0, "trace": {}} for a in view["actions"]]}\n',
    "operation_limit": 'def score_actions(view):\n    for i in range(100001):\n        x = i\n    return {"status": "ABSTAIN", "reason": "unreachable"}\n',
}


def prepare():
    """冻结32桌、两个工程控制及已曝光来源，不调用作者或消耗确认根。"""
    if OUT.exists():
        raise ValueError("审计检查目录已存在，不覆盖或隐式重跑")
    prior_path = _project_file(_PROJECT_ROOT, HERE / "strong-seeds-20260920/parent-b/natural-H/panel.json")
    prior = batch.read(prior_path)
    if prior["identity"]["panel_seed"] != 2026092001 or not any(row["root_index"] == 1 for row in prior["samples"]):
        raise ValueError("已曝光开发根依据不符")
    OUT.mkdir()
    contract_path = natural.REPO / natural.DEFAULT_CONTRACT
    for name, source in SOURCES.items():
        (_project_file(_PROJECT_ROOT, OUT / f"{name}.py")).write_text(source)
    auth = batch.unified_document(batch_label="formal-execution-audit-20260920",
        authorization_id="r10-formal-execution-audit", accounts={"tables_full": 32},
        issued_by="lead", issued_at_utc=batch.search.utc_now(), legacy_alias=False)
    auth.update(scope="评分执行审计工程检查；32桌已曝光开发来源，不作强度或确认",
                max_model_calls=0, issuance_basis="用户持续监督进化及修复测量缺陷授权")
    batch.write(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), auth)
    batch.search.ActionValueLedger.load(_project_file(_PROJECT_ROOT, OUT / "ledger.json"), authorized_budgets={"tables_full": 32}).save()
    frozen = identity.capture(source_paths=[Path(__file__), Path(full.__file__),
        Path(full.verify_panel.__code__.co_filename), Path(batch.__file__), contract_path,
        *[_project_file(_PROJECT_ROOT, OUT / f"{name}.py") for name in SOURCES]])
    batch.write(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "formal-execution-audit-check/1", "purpose": "development_engineering_only",
        "rules_hash": natural.compute_rules_hash(natural.REPO), "contract_path": str(contract_path),
        "dependencies": frozen, "panel_seed": 2026092001, "root_indices": [1],
        "opponent": "H", "seats_per_root": 4, "tables_per_control": 16, "full_tables_limit": 32,
        "worker_timeout_seconds": 600, "concurrency": 1, "controls": list(SOURCES),
        "previous_exposure": {"path": str(prior_path), "sha256": batch.digest(prior_path.read_bytes())},
        "models_called": 0, "confirmation_roots": 0, "release_eligible": False,
        "note": "恒等分和强制超额是监督者编写的测试控制，不能当作LLM算法提案"})
    print("prepared 32-table audit engineering check", flush=True)


def worker(name):
    """运行一个完整四换座自然开发根；费用与表级审计由正式入口持久化。"""
    manifest = batch.read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    identity.verify(manifest["dependencies"])
    target = _project_file(_PROJECT_ROOT, OUT / name)
    if name not in manifest["controls"] or target.exists():
        raise ValueError("未知控制或已有产物，拒绝重跑")
    contract = batch.read(Path(manifest["contract_path"]))
    panel = natural.run_natural_panel(candidate_source=(_project_file(_PROJECT_ROOT, OUT / f"{name}.py")).read_text(),
        opponent="H", root_indices=[1], seats_per_root=4, min_roots=1,
        contract=contract, out_dir=target, authorization=batch.read(_project_file(_PROJECT_ROOT, OUT / "authorization.json")),
        panel_seed=manifest["panel_seed"], ledger_path=_project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        ledger_authorized_budgets={"tables_full": 32})
    identity.verify(manifest["dependencies"])
    checked = full.verify_full_panel(panel, contract, expected_identity=panel["identity"],
        expected_root_indices=[1], expected_rules_hash=manifest["rules_hash"])
    # 运行后重读独立核验；这里的expected_identity来自产物，只验证内部一致性。
    # 候选/执行依赖与预定根则由上方冻结清单、worker固定装配及前后身份守卫绑定。
    reread = batch.read(target / "panel.json")
    if reread != panel:
        raise ValueError("面板落盘内容漂移")
    review = checked["execution_review"]
    counts = review["recorded_counts"]
    if checked["full_results_verified"] != 16 or review["recorded_tables"] != 16:
        raise ValueError("完整桌赛或审计数量不符")
    if name == "scored":
        if review["status"] != "complete" or counts["action_value_scored"] <= 0:
            raise ValueError("评分成功控制未完整执行")
    else:
        if (review["status"] != "requires_review" or counts["action_value_failed"] <= 0
                or review["recorded_failure_kinds"]["operation_limit"] != counts["action_value_failed"]):
            raise ValueError("超额控制未被逐窗识别")
    if checked["runtime_counts"]["fallbacks"] != 0:
        raise ValueError("预期合法内部保底应与驱动fallbacks分开")
    batch.write(target / "verified.json", checked)
    print(json.dumps({"control": name, "tables": 16, "review": review}, ensure_ascii=False), flush=True)


def run():
    """按固定进程组时限顺序执行，不自动重试；失败保留现场及费用。"""
    manifest = batch.read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    identity.verify(manifest["dependencies"])
    with (_project_file(_PROJECT_ROOT, OUT / "begin.json")).open("x") as handle:
        json.dump({"started_at_utc": batch.search.utc_now()}, handle)
    for name in manifest["controls"]:
        result = run_supervised([sys.executable, str(Path(__file__).resolve()), "worker", "--control", name],
            cwd=natural.REPO, timeout_sec=manifest["worker_timeout_seconds"], max_output_chars=12000)
        batch.write(_project_file(_PROJECT_ROOT, OUT / f"{name}-process.json"), result.to_json())
        print(name, result.to_json(), flush=True)
        if result.returncode != 0 or result.timed_out or result.group_still_alive:
            raise SystemExit(1)
    identity.verify(manifest["dependencies"])
    ledger = batch.search.ActionValueLedger.load(_project_file(_PROJECT_ROOT, OUT / "ledger.json"))
    if ledger.spent("tables_full") != 32:
        raise ValueError("工程检查实际桌赛费用不符")
    batch.write(_project_file(_PROJECT_ROOT, OUT / "summary.json"), {"status": "PASS_FORMAL_AUDIT_INTEGRATION",
        "full_tables": 32, "models_called": 0, "confirmation_roots": 0,
        "controls": {name: batch.read(_project_file(_PROJECT_ROOT, OUT / name / "verified.json"))["execution_review"] for name in SOURCES},
        "release_eligible": False, "not_strength_evidence": True,
        "remaining": ["离线研究额度配置贯通", "条件通道审计", "真实新提案循环", "正式确认与发布门禁"]})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run", "worker"))
    parser.add_argument("--control", choices=list(SOURCES))
    args = parser.parse_args()
    if args.operation == "prepare": prepare()
    elif args.operation == "run": run()
    else: worker(args.control)
