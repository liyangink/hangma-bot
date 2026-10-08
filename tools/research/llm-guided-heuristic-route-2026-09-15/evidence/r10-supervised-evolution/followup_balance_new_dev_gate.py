"""原信用组合候选进入未见开发的前置门禁；第二清单结论优先于历史核心通过。"""

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
import followup_balance_second_panel as second


def require_unseen_development():
    """仅核验资格并返回原身份；拒绝必须早于新来源生成、目录创建与费用预留。"""
    b = second.b
    plan = b.read(second.OUT / "evaluation-plan.json")
    second.verify_inputs(plan)
    decision = b.read(second.OUT / "development-decision.json")
    gate = b.read(second.OUT / "next-stage-prerequisite.json")
    assert gate["development_decision_sha256"] == b.digest((second.OUT / "development-decision.json").read_bytes())
    assert decision["candidate_id"] == gate["candidate_id"] == plan["candidate_id"]
    if not (decision["continue_unseen_development"] and gate["unseen_development_allowed"]):
        raise RuntimeError("第二已见清单未通过：" + decision["status"] + "；禁止用历史核心通过状态签发未见开发")
    assert all(decision[k] for k in ("effect_condition_passed", "clean_prototype_execution", "driver_reliable_in_logical_time"))
    return plan["candidate_id"]


if __name__ == "__main__":
    # 专门记录当前结案的真实前置拒绝；没有生成新随机来源或执行新桌赛。
    b = second.b
    try:
        identity = require_unseen_development()
    except RuntimeError as error:
        result = {"status": "REFUSED_BEFORE_SOURCE_OR_SPEND", "reason": str(error)}
    else:
        result = {"status": "QUALIFIED_ONLY_NOT_STARTED", "candidate_id": identity}
    result.update({"source_sha256": b.digest(b.Path(__file__).read_bytes()), "at_utc": b.search.utc_now(),
        "new_sources_generated": 0, "new_tables": 0, "model_calls": 0, "confirmation_roots": 0, "release_eligible": False})
    b.write(second.OUT / "new-development-entry-check.json", result)
    print(result, flush=True)
