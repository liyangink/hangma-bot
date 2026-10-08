"""机械面板不变，只将执行包绑定唯一非执行字段修复后的源码身份。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t187-family-combination-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1')
sys.path.insert(0, str(PRIOR))
from common import pin, save
from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents


def main():
    """原回复/源码/修复证明全部核齐才派生新计划；不覆盖旧机械计划。"""
    original = _project_file(_PROJECT_ROOT, HERE / "QUALIFICATION-PLAN.json")
    plan = json.loads(original.read_text())
    assert plan["complete"] and all(pin(Path(p)) == h for p, h in plan["files"].items())
    package = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-family-metadata-repaired")
    proof = json.loads((package / "DERIVATION.json").read_text())
    assert proof["complete"] and proof["executable_source_unchanged"] and proof["new_API_calls"] == 0
    assert proof["original_generation_pin"] == pin(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-family-model-output/generation.json"))
    assert proof["original_reply_pin"] == pin(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-family-model-output/reply.txt"))
    assert proof["derived_generation_pin"] == pin(package / "generation.json")
    assert proof["derived_reply_pin"] == pin(package / "reply.txt")
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"))
    proposal = load_vip_parents([package], batch)[0]
    plan["candidate_package"] = str(package)
    plan["candidate_identity"] = proposal["identity"]
    plan["identity_missing_until_standard_author_return"] = False
    plan["original_case_plan_pin"] = pin(original)
    plan["same_cases_count_and_order"] = True
    for p in (Path(__file__), original, _project_file(_PROJECT_ROOT, HERE / "run_qualification_repaired.py"), package / "DERIVATION.json",
              package / "candidate.py", package / "generation.json"):
        plan["files"][str(p)] = pin(p)
    save(_project_file(_PROJECT_ROOT, HERE / "QUALIFICATION-REPAIRED-PLAN.json"), plan)
    print(json.dumps({"complete": True, "cases": len(plan["cases"]),
        "candidate_id": proposal["identity"]["candidate_id"], "new_scores_models_HTTP": 0}))


if __name__ == "__main__":
    main()
