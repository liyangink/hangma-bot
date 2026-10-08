"""合并已闭开发块的配对分账；不重评分，不自动派发后续评测。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1/natural'

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

from read_stage import interval

HERE = Path(__file__).resolve().parent
import sys
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, HERE.parent / "evaluation")))
from abc_support import background_priority, pin, require, save


def main(args):
    """先验完整原件与来源互斥，再合计；探索区间不授上线或独立确认。"""
    background_priority()
    summaries, plans, sources, files = [], [], [], {}
    identity = settings = None
    for name in args.stages:
        require(name in ("speed-stage-001", "speed-stage-002", "speed-stage-003"), "非冻结开发块")
        plan_path = _project_file(_PROJECT_ROOT, HERE / (name + "-PLAN.json"))
        plan = json.loads(plan_path.read_text())
        path = Path(plan["dispatch_directory"]) / "SUMMARY.json"
        summary = json.loads(path.read_text())
        require(summary["complete"] and summary["source_stable"] and
            summary["all_resources_naturally_released"] and summary["plan_pin"] == pin(plan_path), "开发块未闭")
        require(len(summary["comparisons"]) == 1, "非单候选最小筛选")
        comparison = summary["comparisons"][0]
        require(comparison["identity"] == plan["candidates"][0]["identity"], "身份不符")
        if identity is None:
            identity, settings = comparison["identity"], plan["bootstrap"]
        require(identity == comparison["identity"] and settings == plan["bootstrap"], "跨块身份或统计方法漂移")
        block = comparison["sources"]
        require([s["root"] for s in block] == plan["root_indices"], "来源不符")
        require(summary["actual_complete_tables"] == 8 * len(block) and
            summary["actual_single_hands"] == 8 * summary["actual_complete_tables"], "实际费用不符")
        for source in block:
            require(source["root_id"] == plan["roots"][source["root"] - 1]["root_id"], "母来源身份不符")
            pairs = source["paired_tables"]
            require([p["rotation"] for p in pairs] == [0, 1, 2, 3], "四换座不完整")
            total = source["four_seat_delta_sums"]
            require(all(sum(p["delta"][k] for p in pairs) == v for k, v in total.items()), "四座分账不符")
            require(total["net"] == total["ordinary_hu_income"] + total["large_hu_income"] + total["payments"], "净账不符")
        for original, expected in summary["files"].items():
            require(pin(Path(original)) == expected, "原件漂移")
        summaries.append(summary)
        plans.append(plan)
        sources.extend(block)
        files[str(path)] = pin(path)
        files[str(plan_path)] = pin(plan_path)
    n = len(sources)
    require(len({s["root"] for s in sources}) == n and len({s["root_id"] for s in sources}) == n, "重复来源")
    require(sorted(s["root"] for s in sources) == list(range(1, n + 1)), "不是连续冻结开发前缀")
    values = [s["four_seat_delta_sums"]["net"] for s in sources]
    mean = {key: sum(s["four_seat_delta_sums"][key] for s in sources) / (4 * n)
        for key in sources[0]["four_seat_delta_sums"]}
    result = {"schema": "t191-cumulative-development-readout/1", "complete": True,
        "source_stable": True, "all_resources_naturally_released": True, "identity": identity,
        "blocks": args.stages, "source_count": n, "sources": sources, "files": files,
        "actual_complete_tables": sum(s["actual_complete_tables"] for s in summaries),
        "actual_single_hands": sum(s["actual_single_hands"] for s in summaries),
        "actual_focal_scores": sum(s["actual_focal_scores"] for s in summaries),
        "mean_delta_per_complete_table": mean, "exploratory_net_bootstrap95": interval(values, settings),
        "positive_net_sources": sum(v > 0 for v in values), "negative_net_sources": sum(v < 0 for v in values),
        "mean_net_excluding_largest_positive_source": (sum(values) - max(values)) / (4 * (n - 1)),
        "new_scores_worlds_tables_models_HTTP": 0, "independent_strength_or_online_admission": False,
        "next_stage_auto_dispatch": False}
    require(all(pin(Path(p)) == h for p, h in files.items()), "合并期间摘要漂移")
    save(args.output.resolve(), result)
    print(json.dumps({k: result[k] for k in ("complete", "source_count", "actual_complete_tables",
        "actual_focal_scores", "mean_delta_per_complete_table", "exploratory_net_bootstrap95")}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stages", nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    main(parser.parse_args())
