"""有界研究配置接线检查：20个开发桌实例，工程控制源码，不是算法效果试验。"""

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
import sitin_execution_profile as profiles
import sitin_gates as gates
import sitin_natural_panel as natural
import sitin_real_behavior as behavior
from sitin_process import run_supervised

HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/research-execution-profile-20260920')
SOURCE = ('def score_actions(view):\n    for i in range(60000):\n        unused = i\n'
          '    return {"status": "SCORED", "entries": '
          '[{"action_key": a["action_key"], "score": 0.0, "trace": {}} for a in view["actions"]]}\n')


def prepare():
    """执行前冻结源码、两种配置、已曝光开发根、费用及进程隔离上限。"""
    if OUT.exists():
        raise ValueError("目录已存在，拒绝覆盖或隐式重跑")
    OUT.mkdir()
    (_project_file(_PROJECT_ROOT, OUT / "control.py")).write_text(SOURCE)
    prior = _project_file(_PROJECT_ROOT, HERE / "support-competition-20260920/support-competition-terra-max/run/iterations/iter-01/conditional/evaluation.json")
    prior_result = batch.read(prior)
    if prior_result["panel"]["panel_seed"] != 2026092001 or prior_result["panel"]["prefix_attempts"]["total"] != 1:
        raise ValueError("已曝光的条件来源不符")
    accounts = {"tables_full": 20, "tables_partial": 1, "prefix_generation": 1}
    auth = batch.unified_document(batch_label=OUT.name, authorization_id="r10-research-profile-check",
        accounts=accounts, issued_by="lead", issued_at_utc=batch.search.utc_now(), legacy_alias=False)
    auth.update(candidate_execution_profile=profiles.RESEARCH_NAME,
        scope="有界研究配置工程验收；16自然桌+4条件续打桌实例+1前缀；非强度或确认",
        max_model_calls=0, issuance_basis="用户持续进化监督及放宽离线性能研究授权")
    batch.write(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), auth)
    batch.search.ActionValueLedger.load(_project_file(_PROJECT_ROOT, OUT / "ledger.json"), authorized_budgets=accounts).save()
    contract_path = natural.REPO / natural.DEFAULT_CONTRACT
    behavior_panel = _project_file(_PROJECT_ROOT, HERE / "real-behavior-panel-v1/panel.json")
    dependencies = identity.capture(source_paths=[Path(__file__), Path(full.__file__),
        Path(full.verify_panel.__code__.co_filename), Path(batch.__file__), contract_path,
        _project_file(_PROJECT_ROOT, OUT / "control.py"), _project_file(_PROJECT_ROOT, OUT / "authorization.json"), behavior_panel])
    batch.write(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {"schema": "research-execution-profile-check/1",
        "purpose": "development_engineering_only", "source_sha256": batch.digest(SOURCE.encode()),
        "dependencies": dependencies, "contract_path": str(contract_path),
        "rules_hash": natural.compute_rules_hash(natural.REPO),
        "panel_seed": 2026092001, "natural_root_indices": [1], "natural_seats": 4,
        "conditional_predicate": "branch_open", "conditional_attempts_cap": 1,
        "profile": profiles.resolve(profiles.RESEARCH_NAME), "accounts": accounts,
        "worker_timeout_seconds": 600, "concurrency": 1, "models_called": 0,
        "confirmation_roots": 0, "release_eligible": False,
        "conditional_previous_exposure": {"path": str(prior), "sha256": batch.digest(prior.read_bytes())},
        "note": "恒等分加固定计数负担由监督者编写，只检验默认失败/研究成功；成绩无算法价值"})


def worker():
    """一次性执行；前后核对冻结依赖，已有开始标记时拒绝自动重跑。"""
    plan = batch.read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    identity.verify(plan["dependencies"])
    with (_project_file(_PROJECT_ROOT, OUT / "worker-start.json")).open("x") as handle:
        json.dump({"started_at_utc": batch.search.utc_now()}, handle)
    source = (_project_file(_PROJECT_ROOT, OUT / "control.py")).read_text()
    records = {}
    for name in (profiles.DEFAULT_NAME, profiles.RESEARCH_NAME):
        record = gates.admit_action_value(source, execution_profile=name,
            facts_panel={"generator": "research-profile-engineering-control", "legal": True},
            timing_config={"repeats": 1})
        batch.write(_project_file(_PROJECT_ROOT, OUT / (name + "-admission.json")), record)
        records[name] = record
    if records[profiles.DEFAULT_NAME]["execution_safety_pass"]:
        raise ValueError("控制源码未在默认计数下失败")
    admission = records[profiles.RESEARCH_NAME]
    if not admission["controlled_research_eligible"]:
        raise ValueError("研究配置未通过受控研究准入")
    replay = behavior.evaluate(source, _project_file(_PROJECT_ROOT, HERE / "real-behavior-panel-v1/panel.json"), execution_profile=plan["profile"])
    batch.write(_project_file(_PROJECT_ROOT, OUT / "behavior.json"), replay)
    if not replay["comparable"]:
        raise ValueError("研究配置真实输入回放失败")
    auth = batch.read(_project_file(_PROJECT_ROOT, OUT / "authorization.json"))
    contract = batch.read(Path(plan["contract_path"]))
    panel = natural.run_natural_panel(candidate_source=source, opponent="H", root_indices=[1],
        seats_per_root=4, min_roots=1, contract=contract, out_dir=_project_file(_PROJECT_ROOT, OUT / "natural-H"),
        authorization=auth, admission=admission, panel_seed=plan["panel_seed"],
        ledger_path=_project_file(_PROJECT_ROOT, OUT / "ledger.json"), ledger_authorized_budgets=plan["accounts"])
    if panel["identity"]["candidate_id"] != admission["identity"]["candidate_id"]:
        raise ValueError("准入与实际研究自然评分身份不符")
    checked = full.verify_full_panel(batch.read(_project_file(_PROJECT_ROOT, OUT / "natural-H/panel.json")), contract,
        expected_identity=panel["identity"], expected_root_indices=[1], expected_rules_hash=plan["rules_hash"])
    batch.write(_project_file(_PROJECT_ROOT, OUT / "natural-verified.json"), checked)
    print("自然16桌已核验", flush=True)
    ledger = batch.search.ActionValueLedger.load(_project_file(_PROJECT_ROOT, OUT / "ledger.json"), authorized_budgets=plan["accounts"])
    conditional = batch.search.run_av_evaluation(_project_file(_PROJECT_ROOT, OUT / "conditional"), source,
        predicate=plan["conditional_predicate"], opponent="H", prefix_source="v2_behavior",
        authorization=auth, admission=admission, ledger=ledger,
        attempts_cap=plan["conditional_attempts_cap"], panel_seed=plan["panel_seed"])
    restored = batch.read(_project_file(_PROJECT_ROOT, OUT / "conditional/evaluation.json"))
    opportunity = batch.read(_project_file(_PROJECT_ROOT, OUT / "conditional/panel-branch_open/panel.json"))
    verdict = batch.search.admit_evaluation_result(restored, panel=opportunity)
    batch.write(_project_file(_PROJECT_ROOT, OUT / "conditional-verified.json"), verdict)
    if not conditional["ok"] or not verdict["ok"]:
        raise ValueError("真实条件续打或持久化审计核验失败")
    reviews = {name: audit.review_tables(arm["tables"])
               for name, arm in restored["double_arm"]["arms"].items()}
    if not checked["execution_review"]["zero_internal_failures_verified"] or not all(
            review["zero_internal_failures_verified"] for review in reviews.values()):
        raise ValueError("控制策略在研究额度下存在内部失败或审计缺口")
    identity.verify(plan["dependencies"])
    if any(ledger.spent(key) != value for key, value in plan["accounts"].items()):
        raise ValueError("实际执行账目未与冻结清单对齐")
    batch.write(_project_file(_PROJECT_ROOT, OUT / "verified.json"), {"status": "PASS_RESEARCH_PROFILE_ENGINEERING",
        "natural_tables": 16, "conditional_table_instances": 4, "prefix_instances": 1,
        "natural_execution_review": checked["execution_review"], "conditional_execution_reviews": reviews,
        "candidate_id": admission["identity"]["candidate_id"], "execution_profile": plan["profile"],
        "accounts": {key: ledger.spent(key) for key in plan["accounts"]},
        "models_called": 0, "confirmation_roots": 0, "release_eligible": False,
        "strength_evidence": False, "automatic_archive_profile_supported": False})


def run():
    """用可终止进程组运行一次，失败保留现场，不自动追加预算或重试。"""
    plan = batch.read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    identity.verify(plan["dependencies"])
    with (_project_file(_PROJECT_ROOT, OUT / "begin.json")).open("x") as handle:
        json.dump({"started_at_utc": batch.search.utc_now()}, handle)
    process = run_supervised([sys.executable, str(Path(__file__).resolve()), "worker"],
        cwd=natural.REPO, timeout_sec=plan["worker_timeout_seconds"], max_output_chars=10000)
    batch.write(_project_file(_PROJECT_ROOT, OUT / "process.json"), process.to_json())
    print(json.dumps(process.to_json(), ensure_ascii=False), flush=True)
    if process.returncode != 0 or process.timed_out or process.group_still_alive:
        raise SystemExit(1)
    identity.verify(plan["dependencies"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run", "worker"))
    args = parser.parse_args()
    {"prepare": prepare, "run": run, "worker": worker}[args.operation]()
