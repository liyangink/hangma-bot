"""为同速前沿首代补唯一非锚点改选的条件诊断；不使用官方未来墙。"""

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
    """固定已有模拟001末手开局，不因续打积分挑来源；四样本三臂共12条。"""
    package = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-speed-model-output")
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"))
    proposal = load_vip_parents([package], batch)[0]
    gate_file = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-speed-model-output-qualification/CLOSURE.json")
    gate = json.loads(gate_file.read_text())
    assert gate["complete"] and gate["mechanical_passed"] and gate["source_stable"] and gate["identity"] == proposal["identity"]
    changed = [r for r in gate["rows"] if r["meaningful_first_changed"] and not r["label"].startswith("anchor:")]
    assert len(changed) == 1 and changed[0]["label"] == "last-control:001"
    row = changed[0]
    case = next(c for c in json.loads((_project_file(_PROJECT_ROOT, HERE / "CASES.json")).read_text())["cases"] if c["label"] == row["label"])
    base = json.loads((_project_file(_PROJECT_ROOT, HERE / "CANDIDATE-CAUSAL-PLAN.json")).read_text())
    plan = copy.deepcopy(base)
    plan["targets"] = [{"case": case, "parent_first": row["parent_first"], "candidate_first": row["candidate_first"],
        "package": str(package), "candidate_source_file": str(package / "candidate.py"), "identity": proposal["identity"],
        "selection": "首代115窗唯一非官方锚点实质改选；当前已公开开发模拟末手首摸，未用续打结果"}]
    plan.update(schema="t185-speed-causal/1", planned_single_hand_continuations=12,
        C="首代同速前沿候选持续续打", source_original_causal_mutated=False)
    for name, original in (("run", "run_candidate_causal.py"), ("close", "close_candidate_causal.py")):
        text = (_project_file(_PROJECT_ROOT, HERE / original)).read_text()
        text = text.replace("CANDIDATE-CAUSAL-PLAN.json", "SPEED-CAUSAL-PLAN.json")
        text = text.replace("candidate-causal-continuations", "speed-causal-continuations")
        text = text.replace("CANDIDATE-CAUSAL-CLOSED.json", "SPEED-CAUSAL-CLOSED.json")
        with (_project_file(_PROJECT_ROOT, HERE / f"{name}_speed_causal.py")).open("x") as f:
            f.write(text)
    files = [Path(__file__), _project_file(_PROJECT_ROOT, HERE / "CANDIDATE-CAUSAL-PLAN.json"), _project_file(_PROJECT_ROOT, HERE / "run_speed_causal.py"), _project_file(_PROJECT_ROOT, HERE / "close_speed_causal.py"),
             gate_file, package / "candidate.py", package / "generation.json"]
    plan["files"].update({str(p): pin(p) for p in files})
    # Case源路径是仓库相对路径，须按项目根而不是当前shell目录解释。
    source = _project_file(_PROJECT_ROOT, HERE.parents[3] / case["source_closure"])
    plan["files"][str(source)] = pin(source)
    save(_project_file(_PROJECT_ROOT, HERE / "SPEED-CAUSAL-PLAN.json"), plan)
    print({"targets": 1, "planned_single_hand_continuations": 12, "new_independent_sources": 0}, flush=True)


if __name__ == "__main__":
    main()
