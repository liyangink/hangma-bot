"""独立来源开桌前冻结三个逻辑对手；不生成牌墙，不查看成绩。"""

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
import json
from collections import Counter
from pathlib import Path

from hangma_bot.offline.qualifier_opponents import QUALIFIER_OPPONENT_VERSION, freeze_qualifier_compositions
from hangma_bot.offline.scoring_sources import source_manifest
from common import HERE, ROOT, canonical, pin, save


def main():
    """60%是抽样情景概率；分池报告实际席位比例，不能冒称实测平台分布。"""
    descriptor = _project_file(_PROJECT_ROOT, HERE / "FRESH-ROOTS-BEFORE-AUTHOR.json")
    plan_path = _project_file(_PROJECT_ROOT, HERE / "PLAN.json")
    seeds, plan = (json.loads(p.read_text()) for p in (descriptor, plan_path))
    assert plan["files"][str(descriptor)] == pin(descriptor)
    assert all(pin(_project_file(_PROJECT_ROOT, ROOT / p)) == h for p, h in plan["source_manifest"].items())
    pools, counts = {}, {}
    for name in ("diagnostic_fresh", "development", "confirmation"):
        inputs = [{"root_id": r["root_id"], "seed": r["world_seed"]} for r in seeds["pools"][name]]
        rows = freeze_qualifier_compositions(inputs, 0.6)
        assert canonical(rows) == canonical(freeze_qualifier_compositions(inputs, 0.6))
        pools[name] = rows
        count = Counter(t for r in rows for t in r["opponent_types_logical_1_2_3"])
        total = len(rows) * 3
        counts[name] = {"types": dict(count), "opponent_slots": total,
                       "actual_weak_fraction": (total - count["r18"]) / total}
    manifest = source_manifest(("hangma_bot.offline.qualifier_opponents",))
    save(_project_file(_PROJECT_ROOT, HERE / "FROZEN-OPPONENT-COMPOSITIONS.json"), {
        "schema": "t185-opponent-composition/1", "pools": pools, "counts": counts,
        "weak_fraction_setting": 0.6, "version": QUALIFIER_OPPONENT_VERSION,
        "files": {str(p): pin(p) for p in (Path(__file__), descriptor, plan_path)},
        "opponent_source_manifest": manifest,
        "pairing": "同一母来源父子与四换座共享三逻辑对手组成；牌山洗牌独立命名空间",
        "scope": "正常V0/自动行为代理为弱席假设，R18为其余席；不是榜前选手实测复制",
        "main_pool_not_selected_by_outcome": True, "walls_or_scores_read": False,
        "sensitivity_50_75_not_main_rescue": True, "worlds_tables_or_model_calls": 0})
    print(counts, flush=True)


if __name__ == "__main__":
    main()
