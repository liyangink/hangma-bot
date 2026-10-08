"""核对T185阶段闭合证据与费用分母；不读活模型结果或T182中途分。"""

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
from common import HERE, ROOT, pin, save


def main():
    """只能确认机械与存档，不能把计划预算变成已经完成的比赛。"""
    checks, closed, count = {}, [], 0
    for name, views, scores in (("mechanism-comparison", 56, 448), ("mechanism-comparison-v2", 95, 760),
                                ("mechanism-comparison-supplement", 20, 160), ("AUTHOR-speed-model-output-qualification", 115, 230)):
        path = _project_file(_PROJECT_ROOT, HERE / name / "CLOSURE.json")
        value = json.loads(path.read_text())
        assert value["actual_score_attempts"] == scores and value["actual_completed_views"] == views
        if name == "mechanism-comparison":
            assert value["complete"] is False and value["failure"]["type"] == "KeyError"
        else:
            assert value["complete"] and value["source_stable"]
            assert value["capture"]["terminal"]["terminal_valid"]
        assert all(pin(Path(p)) == h for p, h in value["files"].items())
        assert all(pin(_project_file(_PROJECT_ROOT, ROOT / p)) == h for p, h in value["source_manifest"].items())
        count += scores
        closed.append(path)
        checks[name] = True
    assert count == 1598
    r = json.loads((_project_file(_PROJECT_ROOT, HERE / "mechanism-comparison-v2/CLOSURE.json")).read_text())
    rows = {x["label"]: x for x in r["rows"]}
    assert rows["anchor:early-one-white-route-speed"]["scores"]["joint"]["first"] == "discard:9b"
    assert rows["anchor:mature-baotou-current-hu"]["scores"]["joint"]["first"] == "hu"
    # 这是结果一致性核对，不是给未来候选强制指定金标。
    checks["closed_anchor_readout_consistent_not_future_gold_action"] = True
    supplement = json.loads((_project_file(_PROJECT_ROOT, HERE / "SUPPLEMENT-CASES.json")).read_text())
    assert len(supplement["cases"]) == 20 and len({c["root_id"] for c in supplement["cases"]}) == 2
    assert len({(c["observation"]["game_id"], c["window_key"]["trigger_seq"]) for c in supplement["cases"]}) == 20
    fresh = json.loads((_project_file(_PROJECT_ROOT, HERE / "FRESH-ROOTS-BEFORE-AUTHOR.json")).read_text())["pools"]
    seeds = [x["world_seed"] for pool in fresh.values() for x in pool]
    assert len(seeds) == len(set(seeds)) == 168
    checks["new_sources_reserved_and_disjoint_not_generated_worlds"] = True
    for name in ("prepare.py", "prepare_prototypes.py", "compare_prototypes_v2.py", "prepare_official_supplement_v3.py",
                 "compare_official_supplement.py", "prepare_author.py", "qualify_candidate.py", "run_incremental_author.py"):
        ast.parse((_project_file(_PROJECT_ROOT, HERE / name)).read_bytes(), filename=name)
    checks["current_research_scripts_parse"] = True
    save(_project_file(_PROJECT_ROOT, HERE / "CHECKS-001.json"), {"schema": "t185-phase-one-checks/1", "success": all(checks.values()),
        "checks": checks, "actual_score_attempts_including_preserved_failure": count,
        "files": {str(p): pin(p) for p in [Path(__file__), _project_file(_PROJECT_ROOT, HERE / "PROGRESS-001.md"), *closed]},
        "new_table_instances": 0, "strength_or_deadline_admitted": False,
        "pending_second_author_not_reconciled_by_this_check": True})
    print({"success": True, "actual_score_attempts": count, "new_complete_tables": 0}, flush=True)


if __name__ == "__main__":
    main()
