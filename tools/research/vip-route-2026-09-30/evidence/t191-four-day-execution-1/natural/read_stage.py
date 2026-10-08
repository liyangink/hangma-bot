"""仅在整块自然退出后验原输入及分账；不重评分，不自动买下一块。"""

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
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1')
sys.path.insert(0, str(PRIOR))
from common import pin, save
import t185_close_development as dev
from readout_compat import function_copy, metadata_adapter
from four_worker_campaign import validate
from source_helpers import preflight, account
from t185_prepare_confirmation import background_priority


def interval(values, settings):
    """母来源四座净差和共同重抽；探索区间不用于声明正式显著。"""
    n = len(values)
    rng = random.Random(settings["seed"])
    draws = sorted(sum(values[rng.randrange(n)] for _ in range(n)) / (4 * n)
        for _ in range(settings["replicates"]))
    result = []
    for quantile in (0.025, 0.975):
        x = (len(draws) - 1) * quantile
        lo = int(x)
        hi = min(lo + 1, len(draws) - 1)
        result.append(draws[lo] + (draws[hi] - draws[lo]) * (x - lo))
    return result


def main(path):
    """完整性、配对与逐窗真实评分均核清才读分；未知不填零。"""
    background_priority()
    plan, plan_pin, lanes = validate(path)
    directory = Path(plan["dispatch_directory"])
    closed = json.loads((directory / "CLOSED.json").read_text())
    dev.require(closed["complete"] and closed["resources_released"] and
        closed["worker_returncodes"] == [0] * 4 and closed["plan_pin"] == plan_pin and
        closed["actual_table_calls"] == closed["verified_complete_table_calls"] == plan["planned_table_instances"],
        "整块资源或真实费用未闭合")
    tables = preflight(plan, plan_pin)
    context = dict(dev.__dict__)
    context["decision_metadata"] = metadata_adapter(dev.decision_metadata)
    receipts = function_copy(dev.score_receipts, context)
    table_rows, files, actual_scores = {}, {str(path): pin(path), str(directory / "CLOSED.json"): pin(directory / "CLOSED.json")}, 0
    for table in tables:
        closure = json.loads((table.directory / "CLOSURE.json").read_text())
        audit, audit_files = receipts(table, closure, plan)
        ledger, scores = account(closure["settlements"], table.rotation, closure["root"]["root_id"])
        dev.require(scores == closure["outcome"]["final_scores"], "终分与结算不符")
        table_rows[(table.index, table.rotation, table.arm_index)] = {"ledger": ledger, "audit": audit,
            "wall_seconds": closure["elapsed_monotonic_seconds"]}
        actual_scores += audit["actual_score_calls"]
        files.update(audit_files)
        files.update({str(table.directory / name): pin(table.directory / name)
            for name in ("START.json", "CLOSURE.json", "PAIRING-IDENTITY.json")})
    comparisons = []
    for arm_index, candidate in enumerate(plan["candidates"], 1):
        sources = []
        for index in plan["root_indices"]:
            pairs = []
            for rotation in range(4):
                parent = table_rows[(index, rotation, 0)]["ledger"]
                child = table_rows[(index, rotation, arm_index)]["ledger"]
                delta = {key: child[key] - value for key, value in parent.items()}
                dev.require(delta["net"] == delta["ordinary_hu_income"] + delta["large_hu_income"] + delta["payments"], "配对分账不符")
                pairs.append({"rotation": rotation, "delta": delta})
            total = {key: sum(p["delta"][key] for p in pairs) for key in pairs[0]["delta"]}
            sources.append({"root": index, "root_id": plan["roots"][index - 1]["root_id"], "paired_tables": pairs,
                "four_seat_delta_sums": total})
        n = len(sources)
        mean = {key: sum(s["four_seat_delta_sums"][key] for s in sources) / (4 * n)
            for key in sources[0]["four_seat_delta_sums"]}
        values = [s["four_seat_delta_sums"]["net"] for s in sources]
        comparisons.append({"identity": candidate["identity"], "sources": sources,
            "mean_delta_per_complete_table": mean, "exploratory_net_bootstrap95": interval(values, plan["bootstrap"]),
            "positive_net_sources": sum(v > 0 for v in values), "negative_net_sources": sum(v < 0 for v in values),
            "independent_strength_or_online_admission": False})
    dev.frozen(plan)
    dev.require(pin(path) == plan_pin and all(pin(Path(p)) == h for p, h in files.items()), "读回后原件漂移")
    save(directory / "SUMMARY.json", {"schema": "t191-natural-stage-readout/1", "complete": True,
        "source_stable": True, "plan_pin": plan_pin, "files": files, "actual_complete_tables": len(tables),
        "actual_single_hands": 8 * len(tables), "actual_focal_scores": actual_scores,
        "comparisons": comparisons, "total_table_wall_seconds": sum(r["wall_seconds"] for r in table_rows.values()),
        "maximum_table_wall_seconds": max(r["wall_seconds"] for r in table_rows.values()),
        "all_resources_naturally_released": True, "new_scores_worlds_tables_models_HTTP": 0,
        "independent_strength_or_online_admission": False})
    print(json.dumps({"complete": True, "actual_complete_tables": len(tables), "actual_focal_scores": actual_scores,
        "comparisons": [{"candidate": c["identity"]["candidate_id"], "mean": c["mean_delta_per_complete_table"],
            "interval": c["exploratory_net_bootstrap95"]} for c in comparisons]}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    main(parser.parse_args().plan.resolve())
