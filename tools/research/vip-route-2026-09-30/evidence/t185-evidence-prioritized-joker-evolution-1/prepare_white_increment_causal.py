"""第四代在原两母窗复核；不重选相容样本或添加有利来源。"""

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
    """保留S02首手与采样键，依据真实第四代资格填写首选。"""
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"))
    package = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-white-increment-model-output")
    proposal = load_vip_parents([package], batch)[0]
    gate_file = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-white-increment-model-output-qualification/CLOSURE.json")
    gate = json.loads(gate_file.read_text())
    assert gate["complete"] and gate["mechanical_passed"] and gate["source_stable"] and gate["identity"] == proposal["identity"]
    rows = {r["label"]: r for r in gate["rows"]}
    original = _project_file(_PROJECT_ROOT, HERE / "CANDIDATE-CAUSAL-PLAN.json")
    plan = copy.deepcopy(json.loads(original.read_text()))
    for t in plan["targets"]:
        row = rows[t["case"]["label"]]
        assert row["parent_first"] == t["parent_first"]
        t.update(package=str(package), candidate_source_file=str(package / "candidate.py"), identity=proposal["identity"],
            candidate_first=row["candidate_first"], selection="第四代在原两母窗与原相容采样键复核；首动作可同父，不按新积分重选")
    for name, src in (("run", "run_candidate_causal.py"), ("close", "close_candidate_causal.py")):
        program = (_project_file(_PROJECT_ROOT, HERE / src)).read_text()
        program = program.replace("CANDIDATE-CAUSAL-PLAN.json", "WHITE-INCREMENT-CAUSAL-PLAN.json")
        program = program.replace("candidate-causal-continuations", "white-increment-causal-continuations")
        program = program.replace("CANDIDATE-CAUSAL-CLOSED.json", "WHITE-INCREMENT-CAUSAL-CLOSED.json")
        with (_project_file(_PROJECT_ROOT, HERE / f"{name}_white_increment_causal.py")).open("x") as f:
            f.write(program)
    plan.update(schema="t185-white-increment-causal/1", C="第四代追加白用途公式持续续打",
        original_sources_and_sample_keys_preserved=True, source_original_causal_mutated=False)
    files = [Path(__file__), original, gate_file, package / "candidate.py", package / "generation.json",
             _project_file(_PROJECT_ROOT, HERE / "run_white_increment_causal.py"), _project_file(_PROJECT_ROOT, HERE / "close_white_increment_causal.py")]
    plan["files"].update({str(p): pin(p) for p in files})
    save(_project_file(_PROJECT_ROOT, HERE / "WHITE-INCREMENT-CAUSAL-PLAN.json"), plan)
    print({"targets": 2, "planned_single_hand_continuations": 24, "new_independent_sources": 0}, flush=True)


if __name__ == "__main__":
    main()
