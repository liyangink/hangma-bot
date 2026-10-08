"""只续做研究配置验收的条件步骤；冻结自然16桌及失败现场，禁止重新执行自然面板。"""

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

import check_research_execution_profile as check
import sitin_opportunities as opportunities
from hangma_bot.kernel.config import RuleConfig

OUT = check.OUT
RESUME = OUT / "conditional-resume-manifest.json"


def prepare():
    """核验原冻结身份仍有效；剩余费用来自原授权，不扩大额度。"""
    if RESUME.exists() or (OUT / "conditional/evaluation.json").exists():
        raise ValueError("已有续做清单或条件结果，拒绝重复")
    plan = check.batch.read(OUT / "manifest.json")
    check.identity.verify(plan["dependencies"])
    ledger = check.batch.search.ActionValueLedger.load(OUT / "ledger.json")
    if ledger.spent("tables_full") != 16 or ledger.spent("tables_partial") or ledger.spent("prefix_generation"):
        raise ValueError("失败前实际账目不是仅完成自然16桌")
    process = check.batch.read(OUT / "process.json")
    if process["returncode"] != 1 or "RuntimeAssemblyError" not in process["stderr_tail"]:
        raise ValueError("续做原因与保存的失败不符")
    paths = [Path(__file__), Path(check.__file__), OUT / "manifest.json", OUT / "process.json",
        OUT / "natural-H/panel.json", OUT / "natural-verified.json",
        OUT / (check.profiles.RESEARCH_NAME + "-admission.json")]
    check.batch.write(RESUME, {"schema": "research-profile-conditional-resume/1",
        "dependencies": check.identity.capture(source_paths=paths),
        "reason": "原验收脚本漏传真实运行时，在条件模拟与费用预留前拒绝；补装配后只续做条件",
        "natural_tables_reused": 16, "remaining_table_instances": 4,
        "remaining_prefix_instances": 1, "additional_model_calls": 0,
        "worker_timeout_seconds": 600, "automatic_retry": False})


def worker():
    """真实组合根装配后执行剩余条件双臂；重读验收结果和账目。"""
    resume = check.batch.read(RESUME)
    check.identity.verify(resume["dependencies"])
    with (OUT / "conditional-resume-worker-start.json").open("x") as handle:
        json.dump({"started_at_utc": check.batch.search.utc_now()}, handle)
    plan = check.batch.read(OUT / "manifest.json")
    check.identity.verify(plan["dependencies"])
    source = (OUT / "control.py").read_text()
    admission = check.batch.read(OUT / (check.profiles.RESEARCH_NAME + "-admission.json"))
    if not check.gates.av_record_identity_matches(admission, source, execution_profile=plan["profile"])[0]:
        raise ValueError("原准入身份漂移")
    panel = check.batch.read(OUT / "natural-H/panel.json")
    verified = check.full.verify_full_panel(panel, check.batch.read(Path(plan["contract_path"])),
        expected_identity=panel["identity"], expected_root_indices=[1], expected_rules_hash=plan["rules_hash"])
    if verified != check.batch.read(OUT / "natural-verified.json"):
        raise ValueError("原自然验收重核不符")
    runtime = opportunities.build_real_runtime(
        rules_config=RuleConfig(check.batch.search.AV_CONDITIONAL_RULESET_VERSION, 1, False),
        rounds_per_game=check.batch.search.AV_CONDITIONAL_ROUNDS_PER_GAME)
    ledger = check.batch.search.ActionValueLedger.load(OUT / "ledger.json", authorized_budgets=plan["accounts"])
    result = check.batch.search.run_av_evaluation(OUT / "conditional", source,
        predicate=plan["conditional_predicate"], opponent="H", prefix_source="v2_behavior",
        authorization=check.batch.read(OUT / "authorization.json"), admission=admission,
        ledger=ledger, runtime=runtime, attempts_cap=1, panel_seed=plan["panel_seed"])
    restored = check.batch.read(OUT / "conditional/evaluation.json")
    opportunity = check.batch.read(OUT / "conditional/panel-branch_open/panel.json")
    verdict = check.batch.search.admit_evaluation_result(restored, panel=opportunity)
    check.batch.write(OUT / "conditional-verified.json", verdict)
    if not result["ok"] or not verdict["ok"]:
        raise ValueError("条件双臂或审计未通过")
    reviews = {name: check.audit.review_tables(arm["tables"])
               for name, arm in restored["double_arm"]["arms"].items()}
    if not verified["execution_review"]["zero_internal_failures_verified"] or not all(
            review["zero_internal_failures_verified"] for review in reviews.values()):
        raise ValueError("研究控制存在内部评分失败")
    if any(ledger.spent(key) != value for key, value in plan["accounts"].items()):
        raise ValueError("费用未与冻结清单对齐")
    check.identity.verify(resume["dependencies"])
    check.batch.write(OUT / "verified.json", {"status": "PASS_RESEARCH_PROFILE_ENGINEERING",
        "natural_tables": 16, "conditional_table_instances": 4, "prefix_instances": 1,
        "natural_tables_rerun_on_resume": 0,
        "natural_execution_review": verified["execution_review"], "conditional_execution_reviews": reviews,
        "candidate_id": admission["identity"]["candidate_id"], "execution_profile": plan["profile"],
        "accounts": {key: ledger.spent(key) for key in plan["accounts"]},
        "models_called": 0, "confirmation_roots": 0, "release_eligible": False,
        "strength_evidence": False, "automatic_archive_profile_supported": False})


def run():
    """隔离运行剩余一步；原失败进程和新进程分别留证。"""
    resume = check.batch.read(RESUME)
    check.identity.verify(resume["dependencies"])
    with (OUT / "conditional-resume-begin.json").open("x") as handle:
        json.dump({"started_at_utc": check.batch.search.utc_now()}, handle)
    process = check.run_supervised([sys.executable, str(Path(__file__).resolve()), "worker"],
        cwd=check.natural.REPO, timeout_sec=resume["worker_timeout_seconds"], max_output_chars=10000)
    check.batch.write(OUT / "conditional-resume-process.json", process.to_json())
    print(json.dumps(process.to_json(), ensure_ascii=False), flush=True)
    if process.returncode != 0 or process.timed_out or process.group_still_alive:
        raise SystemExit(1)
    check.identity.verify(resume["dependencies"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run", "worker"))
    args = parser.parse_args()
    {"prepare": prepare, "run": run, "worker": worker}[args.operation]()
