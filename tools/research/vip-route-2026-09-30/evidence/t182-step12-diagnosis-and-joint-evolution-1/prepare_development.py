"""只为已过93窗行为门的最多三候选冻结自然完整桌开发计划；不生成牌山。"""

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
import argparse
import json
from pathlib import Path
from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents
from prepare_diagnostics import pin, save

HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT


def main(packages):
    """同一32来源及四换座比较当前S02与候选，父代只执行并计费一次。"""
    assert 1 <= len(packages) <= 3
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"))
    parent_file = _project_file(_PROJECT_ROOT, HERE / "parent-source.py")
    parent_identity = batch.identity(parent_file.read_text())
    assert parent_identity == json.loads((_project_file(_PROJECT_ROOT, HERE / "CURRENT-RESEARCH-PARENT.json")).read_text())["identity"]
    conditional = json.loads((_project_file(_PROJECT_ROOT, HERE / "CANDIDATE-CAUSAL-CLOSED.json")).read_text())
    assert conditional["complete"]
    assert all(pin(Path(p)) == h for p, h in conditional["files"].items())
    conditional_ids = {r["candidate_id"] for r in conditional["comparisons"]}
    proposals = []
    files = [_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"), _project_file(_PROJECT_ROOT, HERE / "CURRENT-RESEARCH-PARENT.json"), parent_file,
             _project_file(_PROJECT_ROOT, HERE / "DIAGNOSIS-CLOSED.json"), _project_file(_PROJECT_ROOT, HERE / "AUTHOR-SELECTION-CLOSED.json"), _project_file(_PROJECT_ROOT, HERE / "FRESH-ROOTS-BEFORE-AUTHOR.json"),
             _project_file(_PROJECT_ROOT, HERE / "COMPOSITIONS.json"), Path(__file__), _project_file(_PROJECT_ROOT, HERE / "run_development.py"),
             _project_file(_PROJECT_ROOT, HERE / "CANDIDATE-CAUSAL-PLAN.json"), _project_file(_PROJECT_ROOT, HERE / "CANDIDATE-CAUSAL-CLOSED.json"),
             _project_file(_PROJECT_ROOT, HERE / "close_development.py"), _project_file(_PROJECT_ROOT, HERE / "DEVELOPMENT-READOUT-CONTRACT.md")]
    for name in packages:
        package = Path(name).resolve()
        assert package.parent == HERE
        loaded = load_vip_parents([package], batch)[0]
        gate = _project_file(_PROJECT_ROOT, HERE / (package.name + "-qualification/CLOSURE.json"))
        qualification = json.loads(gate.read_text())
        assert qualification["complete"] and qualification["development_eligible"]
        assert qualification["identity"] == loaded["identity"] and qualification["source_stable"]
        assert loaded["identity"]["candidate_id"] in conditional_ids
        proposals.append({"label": package.name, "package": str(package), "source_file": str(package / "candidate.py"),
                          "identity": loaded["identity"], "qualification_file": str(gate)})
        files += [package / "generation.json", package / "candidate.py", gate]
    assert len({p["identity"]["candidate_id"] for p in proposals}) == len(proposals)
    roots = json.loads((_project_file(_PROJECT_ROOT, HERE / "COMPOSITIONS.json")).read_text())["pools"]["development"]
    assert len(roots) == 32
    save(_project_file(_PROJECT_ROOT, HERE / "DEVELOPMENT-PLAN.json"), {"schema": "t182-natural-development/1", "roots": roots,
        "parent": {"label": "current-S02-parent", "source_file": str(parent_file), "identity": parent_identity},
        "candidates": proposals, "files": {str(p): pin(p) for p in files},
        "source_manifest": json.loads((_project_file(_PROJECT_ROOT, HERE / "DIAGNOSTIC-PLAN.json")).read_text())["source_manifest"],
        "rotations": [0, 1, 2, 3], "rounds": 8, "initial_dealer_physical": 0,
        "initial_scores_0_1_2_3": [0, 0, 0, 0], "maximum_new_complete_table_instances": 512,
        "planned_table_instances": 32 * 4 * (1 + len(proposals)), "step_limit": 50000,
        "wall_seconds_per_table": 600, "minimum_free_bytes": 8589934592,
        "capture_limits": {"max_view_json_bytes": 67108864, "max_total_json_bytes": 536870912, "max_unique_views": 4096},
        "planned_readout": "全批原终态后按母源四座均值聚类，积分分账与来源bootstrap95%区间；开发不授确认",
        "selection_rule": "均值净增>0且至少2母来源净增；取均值最高一份，平分按candidate_id排序；开发不授增强",
        "bootstrap": {"replicates": 20000, "seed": 20261004, "cluster": "每母来源四座平均配对差",
                      "interval": "percentile_2.5_and_97.5"},
        "no_early_score_peeking_or_additional_roots": True, "max_independent_confirmed_candidates": 1,
        "new_models_worlds_tables_in_preparation": 0,
        "world_pairing": "同源同牌山同初始庄家及三对手；逻辑席位i映射(i+rotation)%4"})
    print({"candidate_count": len(proposals), "planned_tables": 128 * (1 + len(proposals)), "new_tables": 0})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--packages", nargs="+", required=True)
    main(parser.parse_args().packages)
