"""全部候选条件续打闭合后分账，明确首动作与后继贡献以及样本边界。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t182-step12-diagnosis-and-joint-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import json
from pathlib import Path
from close_diagnosis import account
from prepare_diagnostics import pin, save
from run_causal import unchanged

HERE = Path(__file__).resolve().parent


def main():
    """条件等权样本只解释机制；不计算自然桌强度或正式准入。"""
    plan_path = _project_file(_PROJECT_ROOT, HERE / "CANDIDATE-CAUSAL-PLAN.json")
    plan = json.loads(plan_path.read_text())
    assert unchanged(plan)
    files = {str(plan_path): pin(plan_path), str(Path(__file__)): pin(Path(__file__))}
    comparisons, counts = [], {}
    for index, target in enumerate(plan["targets"], 1):
        path = _project_file(_PROJECT_ROOT, HERE / "candidate-causal-continuations" / f"target-{index:03d}" / "CLOSURE.json")
        closure = json.loads(path.read_text())
        started = json.loads((path.parent / "START.json").read_text())
        assert started["plan_pin"] == pin(plan_path) and started["target"] == target == closure["target"]
        assert closure["complete"] and closure["source_stable"] and closure["capture"]["terminal"]["terminal_valid"]
        files[str(path)] = pin(path)
        files[str(path.parent / "START.json")] = pin(path.parent / "START.json")
        for key, value in closure["counts"].items():
            counts[key] = counts.get(key, 0) + value
        for sample in range(1, plan["worlds_per_target"] + 1):
            results = {r["arm"]: r for r in closure["results"] if r["sample"] == sample}
            assert set(results) == {"A", "B", "C"}
            baseline, first_only, ongoing = (account(results[a]) for a in ("A", "B", "C"))
            comparisons.append({"target": index, "root_id": target["case"]["root_id"],
                "case": target["case"]["label"], "candidate_id": target["identity"]["candidate_id"],
                "sample": sample, "A": baseline, "B": first_only, "C": ongoing,
                "B_minus_A": {k: first_only[k] - baseline[k] for k in baseline},
                "C_minus_A": {k: ongoing[k] - baseline[k] for k in baseline},
                "C_minus_B": {k: ongoing[k] - first_only[k] for k in baseline}})
    assert counts["single_hand_dispatched"] == plan["planned_single_hand_continuations"] <= 108
    save(_project_file(_PROJECT_ROOT, HERE / "CANDIDATE-CAUSAL-CLOSED.json"), {"schema": "t182-candidate-causal-closed/1",
        "complete": True, "files": files, "counts": counts, "comparisons": comparisons,
        "mother_sources": len({t["case"]["root_id"] for t in plan["targets"]}),
        "sampler_interpretation": plan["sampler_interpretation"], "new_model_calls": 0,
        "official_deadline_or_strength_admission": False})
    print({"complete": True, "actual_counts": counts, "targets": len(plan["targets"])})


if __name__ == "__main__":
    main()
