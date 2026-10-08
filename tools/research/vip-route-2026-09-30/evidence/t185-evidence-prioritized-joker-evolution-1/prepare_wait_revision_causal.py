"""第三提案机械合格后，在原两条件母窗和原采样键复核修订。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import copy
import json
from pathlib import Path

from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents
from common import HERE, pin, save


def main():
    """固定母窗不按新分数换题；首动作允许保持S02，用相同样本报告全部结果。"""
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"))
    package = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-wait-revision-model-output")
    parent = load_vip_parents([package], batch)[0]
    gate_file = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-wait-revision-model-output-qualification/CLOSURE.json")
    gate = json.loads(gate_file.read_text())
    old_plan_file, old_closed_file = _project_file(_PROJECT_ROOT, HERE / "CANDIDATE-CAUSAL-PLAN.json"), _project_file(_PROJECT_ROOT, HERE / "CANDIDATE-CAUSAL-CLOSED.json")
    old_plan, old_closed = (json.loads(p.read_text()) for p in (old_plan_file, old_closed_file))
    assert gate["complete"] and gate["mechanical_passed"] and gate["source_stable"]
    assert gate["identity"] == parent["identity"] and gate["actual_completed_views"] == 115
    assert old_closed["complete"] and all(pin(Path(p)) == h for p, h in old_closed["files"].items())
    rows = {r["label"]: r for r in gate["rows"]}
    plan = copy.deepcopy(old_plan)
    for t in plan["targets"]:
        row = rows[t["case"]["label"]]
        assert row["parent_first"] == t["parent_first"]
        t.update(package=str(package), candidate_source_file=str(package / "candidate.py"), identity=parent["identity"],
                 candidate_first=row["candidate_first"], selection="冻结原两母窗/采样键，不按修订后的改选或积分重选；首手可与S02相同")
    for name in ("run", "close"):
        original = _project_file(_PROJECT_ROOT, HERE / ("run_candidate_causal.py" if name == "run" else "close_candidate_causal.py"))
        program = original.read_text()
        assert "CANDIDATE-CAUSAL-PLAN.json" in program and "candidate-causal-continuations" in program
        program = program.replace("CANDIDATE-CAUSAL-PLAN.json", "WAIT-REVISION-CAUSAL-PLAN.json")
        program = program.replace("candidate-causal-continuations", "wait-revision-causal-continuations")
        program = program.replace("CANDIDATE-CAUSAL-CLOSED.json", "WAIT-REVISION-CAUSAL-CLOSED.json")
        with (_project_file(_PROJECT_ROOT, HERE / f"{name}_wait_revision_causal.py")).open("x") as s:
            s.write(program)
    plan["schema"] = "t185-wait-revision-conditional/1"
    plan["C"] = "第三份等待增量修订候选持续续打"
    plan["fixed_cases_and_samples_before_third_author"] = True
    plan["fresh_independent_confirmation"] = False
    plan["source_original_second_causal_mutated"] = False
    # 旧固定证据保持不变；追加当前新身份与工具，原工具虽不再执行也仍核原摘要。
    files = [Path(__file__), old_plan_file, old_closed_file, gate_file, package / "candidate.py", package / "generation.json",
             _project_file(_PROJECT_ROOT, HERE / "run_wait_revision_causal.py"), _project_file(_PROJECT_ROOT, HERE / "close_wait_revision_causal.py")]
    plan["files"].update({str(p): pin(p) for p in files})
    save(_project_file(_PROJECT_ROOT, HERE / "WAIT-REVISION-CAUSAL-PLAN.json"), plan)
    print({"targets": len(plan["targets"]), "planned_single_hand_continuations": plan["planned_single_hand_continuations"],
           "same_original_hidden_sample_keys": True, "new_independent_full_tables": 0}, flush=True)


if __name__ == "__main__":
    main()
