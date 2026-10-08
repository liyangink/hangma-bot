"""联合m1资格通过后，固定两个不同模拟来源的三臂条件续打。"""

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
import ast
import json
from pathlib import Path

from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents
from common import HERE, ROOT, OLD, pin, save


def main():
    """按改选窗口的来源/序号取首窗，不按终局、分数或隐藏样本选题。"""
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"))
    package = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-incremental-model-output")
    proposal = load_vip_parents([package], batch)[0]
    gate_path = _project_file(_PROJECT_ROOT, HERE / (package.name + "-qualification/CLOSURE.json"))
    gate = json.loads(gate_path.read_text())
    assert gate["complete"] and gate["development_eligible"] and gate["source_stable"]
    assert gate["identity"] == proposal["identity"]
    original_diagnostic = json.loads((OLD / "DIAGNOSTIC-PLAN.json").read_text())
    roots = {r["root_id"]: r for r in original_diagnostic["roots"]}
    cases = {c["label"]: c for c in json.loads((_project_file(_PROJECT_ROOT, HERE / "CASES.json")).read_text())["cases"]}
    eligible = sorted([r for r in gate["rows"] if r.get("meaningful_first_changed")
        and r["label"].startswith(("fresh:", "supplement:")) and r["root_id"] in roots],
        key=lambda r: (r["root_id"], cases[r["label"]]["window_key"]["round_no"], cases[r["label"]]["window_key"]["trigger_seq"]))
    targets, used = [], set()
    for row in eligible:
        if row["root_id"] in used or len(targets) >= 3:
            continue
        case = cases[row["label"]]
        assert case["source_closure"]
        targets.append({"case": case, "parent_first": row["parent_first"], "candidate_first": row["candidate_first"],
            "package": str(package), "candidate_source_file": str(package / "candidate.py"), "identity": proposal["identity"],
            "selection": "已机械通过实际改选；现有模拟母来源键和窗口序最早，每母一窗，最多三；不看续打结果"})
        used.add(row["root_id"])
    assert targets
    save(_project_file(_PROJECT_ROOT, HERE / "DIAGNOSTIC-PLAN.json"), {"schema": "t185-existing-public-development-recovery/1", "roots": list(roots.values()),
        "source_manifest": json.loads((_project_file(_PROJECT_ROOT, HERE / "PLAN.json")).read_text())["source_manifest"],
        "original_plan_pin": pin(OLD / "DIAGNOSTIC-PLAN.json"), "independent_confirmation": False})
    program = (OLD / "run_candidate_causal.py").read_text()
    for before, after in [('from prepare_diagnostics import pin, save', 'from common import pin, save'),
        ('from run_causal import EndpointEngine, recover, unchanged', 'from reuse_causal_helpers import EndpointEngine, recover, unchanged'),
        ('from run_diagnostic_sources import canonical', 'from common import canonical'),
        ('sample_key = f"t182:', 'sample_key = f"t185:')]:
        assert program.count(before) == 1
        program = program.replace(before, after, 1)
    with (_project_file(_PROJECT_ROOT, HERE / "run_candidate_causal.py")).open("x") as stream:
        stream.write(program)
    source = (OLD / "close_diagnosis.py").read_text()
    tree = ast.parse(source)
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "account")
    with (_project_file(_PROJECT_ROOT, HERE / "accounting.py")).open("x") as stream:
        stream.write('"""复用原逐单局分账，物理座位0—3；不从分账建立规则。"""\n' + ast.get_source_segment(source, function) + "\n")
    program = (OLD / "close_candidate_causal.py").read_text()
    for before, after in [('from close_diagnosis import account', 'from accounting import account'),
        ('from prepare_diagnostics import pin, save', 'from common import pin, save'),
        ('from run_causal import unchanged', 'from reuse_causal_helpers import unchanged')]:
        assert program.count(before) == 1
        program = program.replace(before, after, 1)
    with (_project_file(_PROJECT_ROOT, HERE / "close_candidate_causal.py")).open("x") as stream:
        stream.write(program)
    files = [Path(__file__), _project_file(_PROJECT_ROOT, HERE / "common.py"), _project_file(_PROJECT_ROOT, HERE / "reuse_causal_helpers.py"), _project_file(_PROJECT_ROOT, HERE / "run_candidate_causal.py"),
        _project_file(_PROJECT_ROOT, HERE / "close_candidate_causal.py"), _project_file(_PROJECT_ROOT, HERE / "accounting.py"), _project_file(_PROJECT_ROOT, HERE / "DIAGNOSTIC-PLAN.json"),
        _project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"), _project_file(_PROJECT_ROOT, HERE / "parent-source.py"), gate_path, package / "candidate.py", package / "generation.json",
        OLD / "run_causal.py", OLD / "run_diagnostic_sources.py", OLD / "prepare_diagnostics.py", OLD / "close_diagnosis.py"]
    files += [_project_file(_PROJECT_ROOT, ROOT / t["case"]["source_closure"]) for t in targets]
    save(_project_file(_PROJECT_ROOT, HERE / "CANDIDATE-CAUSAL-PLAN.json"), {"schema": "t185-candidate-causal/1", "targets": targets,
        "files": {str(p): pin(p) for p in files}, "source_manifest": json.loads((_project_file(_PROJECT_ROOT, HERE / "PLAN.json")).read_text())["source_manifest"],
        "worlds_per_target": 4, "maximum_actual_single_hand_continuations": 108,
        "planned_single_hand_continuations": 12 * len(targets), "step_limit": 50000,
        "wall_seconds_per_target": 1800, "capture_limits": {"max_view_json_bytes": 67108864, "max_total_json_bytes": 536870912, "max_unique_views": 4096},
        "A": "S02持续续打", "B": "只改首手，其后S02", "C": "m1联合候选持续续打",
        "sample_key_prefix": "t185; distinct from old t182 samples",
        "sampler_interpretation": "四个等权公开相容隐藏世界仅作条件机制诊断，不是真实后验或自然场频率；模拟现有开发来源不算独立确认",
        "official_anchors_counterfactual_worlds_reconstructed": False,
        "readout": "全目标终态后统一分账B−A、C−A、C−B；负例与未知保留，不用条件积分救完整桌成绩",
        "background_cpu_workers": 1, "source_original_t182_experiment_mutated": False,
        "new_worlds_continuations_model_calls_at_preparation": 0, "strength_or_deadline_admitted": False})
    print({"targets": len(targets), "planned_single_hand_continuations": 12 * len(targets), "new_worlds_or_continuations": 0}, flush=True)


if __name__ == "__main__":
    main()
