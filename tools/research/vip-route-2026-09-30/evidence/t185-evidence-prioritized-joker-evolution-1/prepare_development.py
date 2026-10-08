"""T185开发准备：候选门、对手组成和32来源冻结；不执行模拟。"""

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
import argparse
import json
from pathlib import Path

from hangma_bot.offline.scoring_sources import source_manifest
from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents
from common import HERE, ROOT, pin, save


def build_plan(packages):
    """返回固定父子配对计划；重复ID、缺资格或任何原件漂移时拒绝。"""
    assert 1 <= len(packages) <= 3
    initial_file, comps_file = _project_file(_PROJECT_ROOT, HERE / "PLAN.json"), _project_file(_PROJECT_ROOT, HERE / "FROZEN-OPPONENT-COMPOSITIONS.json")
    initial, comps = (json.loads(p.read_text()) for p in (initial_file, comps_file))
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"))
    parent_file = _project_file(_PROJECT_ROOT, HERE / "parent-source.py")
    identity = batch.identity(parent_file.read_text())
    assert identity == initial["baseline_identity"]
    tools_file = _project_file(_PROJECT_ROOT, HERE / "FULL-TABLE-TOOLS-PREPARED.json")
    tools = json.loads(tools_file.read_text())
    assert tools["complete"] and all(pin(Path(p)) == h for p, h in tools["files"].items())
    assert all(pin(Path(p)) == h for p, h in comps["files"].items())
    files = [Path(__file__), initial_file, comps_file, tools_file, _project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"), parent_file,
        _project_file(_PROJECT_ROOT, HERE / "FRESH-ROOTS-BEFORE-AUTHOR.json"), _project_file(_PROJECT_ROOT, HERE / "common.py"), _project_file(_PROJECT_ROOT, HERE / "DEVELOPMENT-READOUT-CONTRACT.md"),
        _project_file(_PROJECT_ROOT, HERE / "t185_run_development.py"), _project_file(_PROJECT_ROOT, HERE / "t185_close_development.py"), _project_file(_PROJECT_ROOT, HERE / "run_development_workers.py"),
        _project_file(_PROJECT_ROOT, HERE / "check_full_table_tools.py")]
    proposals = []
    for name in packages:
        package = Path(name).resolve()
        assert package.parent == HERE
        loaded = load_vip_parents([package], batch)[0]
        gate_file = _project_file(_PROJECT_ROOT, HERE / (package.name + "-qualification/CLOSURE.json"))
        gate = json.loads(gate_file.read_text())
        assert gate["complete"] and gate["mechanical_passed"] and gate["development_eligible"] and gate["source_stable"]
        assert gate["identity"] == loaded["identity"] and gate["actual_completed_views"] == 115
        assert all(pin(Path(p)) == h for p, h in gate["files"].items())
        proposals.append({"label": package.name, "package": str(package), "source_file": str(package / "candidate.py"),
            "identity": loaded["identity"], "qualification_file": str(gate_file)})
        files.extend([package / "generation.json", package / "candidate.py", gate_file])
    assert len({p["identity"]["candidate_id"] for p in proposals}) == len(proposals)
    manifest = dict(initial["source_manifest"])
    for extra in (comps["opponent_source_manifest"], source_manifest(("hangma_bot.offline.evaluate", "hangma_bot.offline.scoring_input_capture", "hangma_bot.offline.vip_route_development"))):
        for p, h in extra.items():
            assert p not in manifest or manifest[p] == h
            manifest[p] = h
    assert all(pin(_project_file(_PROJECT_ROOT, ROOT / p)) == h for p, h in manifest.items())
    return {"schema": "t185-natural-development/1", "roots": comps["pools"]["development"],
        "parent": {"label": "current-S02-parent", "source_file": str(parent_file), "identity": identity},
        "candidates": proposals, "files": {str(p): pin(p) for p in files}, "source_manifest": manifest,
        "rotations": [0, 1, 2, 3], "rounds": 8, "initial_dealer_physical": 0, "initial_scores_0_1_2_3": [0, 0, 0, 0],
        "maximum_new_complete_table_instances": 512, "planned_table_instances": 32 * 4 * (1 + len(proposals)),
        "step_limit": 50000, "wall_seconds_per_table": 600, "minimum_free_bytes": 8589934592,
        "capture_limits": {"max_view_json_bytes": 67108864, "max_total_json_bytes": 536870912, "max_unique_views": 4096},
        "planned_readout": "全批闭合后按母源四座均值配对、分普通/大牌/支付/庄闲并报来源区间；开发不授增强",
        "selection_rule": "均值净增>0且至少2母来源正增，最高配对总净分一份，平分按candidate_id；开发不授增强",
        "bootstrap": {"replicates": 20000, "seed": 20261005, "cluster": "每母来源四座平均配对差", "interval": "percentile_2.5_and_97.5"},
        "no_early_score_peeking_or_additional_roots": True, "max_independent_confirmed_candidates": 1,
        "new_models_worlds_tables_in_preparation": 0,
        "world_pairing": "同源同牌山同初始庄家及三对手；逻辑席位i映射(i+rotation)%4"}


def main(packages):
    """仅验证固定计划并新建；启动由独立worker的资源检查控制。"""
    from t185_close_development import validate_plan, frozen
    check_path = _project_file(_PROJECT_ROOT, HERE / "FULL-TABLE-TOOLS-CHECKED.json")
    checked = json.loads(check_path.read_text())
    assert checked["success"] and checked["actual_focal_scores_checked"] == 1686
    assert all(v["rejected"] for v in checked["negative_checks"].values())
    # 检查器本身只是在完成后增加这个前置条件，旧实际收据/读回器摘要须一致。
    for p, h in checked["files"].items():
        if Path(p).resolve() != Path(__file__).resolve():
            assert pin(Path(p)) == h
    plan = build_plan(packages)
    plan["files"][str(check_path)] = pin(check_path)
    validate_plan(plan)
    frozen(plan)
    save(_project_file(_PROJECT_ROOT, HERE / "DEVELOPMENT-PLAN.json"), plan)
    print({"candidates": len(packages), "planned_complete_tables": plan["planned_table_instances"], "new_tables": 0}, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--packages", nargs="+", required=True)
    main(parser.parse_args().packages)
