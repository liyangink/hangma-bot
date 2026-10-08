"""固定阶段全闭后累计分账与费用判定；开发区间不授正式增强。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t186-incremental-opportunity-repair-1'

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
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1')
sys.path.insert(0, str(PRIOR))
from common import pin, save
from four_worker_campaign import validate
from t185_prepare_confirmation import background_priority


def summarize(sources, blocks, bootstrap):
    """按母来源四座均差算探索区间，返回下一笔费用资格，不自动购买。"""
    n = len(sources)
    assert n in (16, 32, 64)
    assert [s["root"] for s in sources] == list(range(1, n + 1))
    assert len({s["root_id"] for s in sources}) == n
    total = Counter()
    for source in sources:
        pairs = source["paired_tables"]
        assert [p["rotation"] for p in pairs] == list(range(4))
        check = Counter()
        for pair in pairs:
            delta = pair["delta"]
            assert delta["net"] == delta["ordinary_hu_income"] + delta["large_hu_income"] + delta["payments"]
            check.update(delta)
        assert dict(check) == source["four_seat_delta_sums"]
        total.update(check)
    means = {k:v / (4*n) for k,v in total.items()}
    values = [s["four_seat_delta_sums"]["net"] for s in sources]
    rng = random.Random(bootstrap["seed"])
    draws = sorted(sum(values[rng.randrange(n)] for _ in range(n))/(4*n)
        for _ in range(bootstrap["replicates"]))
    interval = [draws[int(len(draws)*.025)], draws[int(len(draws)*.975)]]
    maximum = max(range(n), key=lambda i:values[i])
    excluding_max = (sum(values)-values[maximum]) / (4*(n-1))
    big_positive = [s["root"] for s in sources if s["four_seat_delta_sums"]["large_hu_income"] > 0]
    criteria = {"at_least_32_sources":n >= 32, "mean_net_at_least_5":means["net"] >= 5,
        "exploratory_interval_lower_positive":interval[0] > 0,
        "latest_block_net_positive":blocks[-1]["mean_delta_per_complete_table"]["net"] > 0,
        "excluding_maximum_net_source_still_positive":excluding_max > 0,
        "cumulative_large_income_nonnegative":means["large_hu_income"] >= 0,
        "two_distinct_large_income_positive_sources":len(big_positive) >= 2}
    confirmation_budget = all(criteria.values())
    optional_64 = n == 32 and not confirmation_budget and means["net"] > 0 and len(big_positive) >= 2
    next_budget = (means["net"] > 0 or (means["large_hu_income"] > 0 and means["net"] >= -10)) if n == 16 else (confirmation_budget or optional_64)
    if n == 64:
        next_budget = confirmation_budget
    return {"independent_roots":n, "mean_delta_per_complete_table":means,
        "net_exploratory_source_bootstrap95":interval,
        "net_mean_excluding_maximum_positive_source":excluding_max,
        "maximum_positive_source_excluded_for_sensitivity":sources[maximum]["root"],
        "positive_large_income_sources":big_positive, "stronger_development_budget_criteria":criteria,
        "independent_confirmation_budget_eligible":confirmation_budget,
        "optional_64_source_development_budget_eligible":optional_64,
        "exploratory_next_stage_budget_eligible":next_budget,
        "new_block_net_direction":blocks[-1]["mean_delta_per_complete_table"]["net"]}


def main(path):
    """每阶段资源、身份和逐评分原件核齐后，允许计算原事前费用条件。"""
    background_priority()
    plan, plan_pin, _ = validate(path)
    paths = [Path(p) for p in plan["prior_stage_plans"]] + [Path(path)]
    assert len(set(paths)) == len(paths)
    files, sources, blocks, scores, tables = {}, [], [], 0, 0
    for p in paths:
        stage, stage_pin, _ = validate(p)
        assert stage["candidates"] == plan["candidates"] and stage["parent"] == plan["parent"]
        for key in ("rounds", "execution_backend", "source_manifest", "roots", "capture_limits"):
            assert stage[key] == plan[key]
        directory = Path(stage["dispatch_directory"])
        closed = json.loads((directory / "CLOSED.json").read_text())
        summary = json.loads((directory / "SUMMARY.json").read_text())
        readout = json.loads((directory / "READOUT-CLOSED.json").read_text())
        assert closed["complete"] and closed["resources_released"] and closed["worker_returncodes"] == [0]*4
        assert closed["plan_pin"] == readout["plan_pin"] == summary["plan_pin"] == stage_pin
        assert closed["actual_table_calls"] == readout["actual_tables"] == summary["actual_complete_tables"] == stage["planned_table_instances"]
        assert summary["complete"] and summary["readout_pin"] == pin(directory / "READOUT-CLOSED.json")
        assert readout["complete"] and readout["source_stable"] and readout["actual_cpu_workers"] == 4
        assert all(pin(Path(f)) == h for f,h in readout["files"].items())
        assert [s["root"] for s in summary["sources"]] == stage["root_indices"]
        sources += summary["sources"]
        scores += summary["actual_focal_scores"]
        tables += summary["actual_complete_tables"]
        blocks.append({"plan":str(p), "mean_delta_per_complete_table":summary["mean_delta_per_complete_table"],
            "source_sign_counts":summary["source_sign_counts"]})
        for f in (p, directory/"SUMMARY.json", directory/"READOUT-CLOSED.json", directory/"CLOSED.json"):
            files[str(f)] = pin(f)
    assert tables == plan["cumulative_planned_complete_tables"] == len(sources)*8
    statistics = summarize(sources, blocks, plan["bootstrap"])
    assert all(pin(Path(f)) == h for f,h in files.items())
    result = {"schema":"t186-cumulative-development/2", "complete":True, "plan_pin":plan_pin, "files":files,
        "candidate_identity":plan["candidates"][0]["identity"], "actual_complete_tables":tables,
        "actual_single_hands":tables*plan["rounds"], "actual_focal_scores":scores,
        "sources":sources, "blocks":blocks, **statistics, "all_stage_audits_and_resources_closed":True,
        "natural_strength_or_online_admission":False, "new_scores_worlds_tables_models_HTTP":0,
        "next_stage_auto_dispatch":False, "notes":"事前开发费用资格；区间反复读回不授正式覆盖或显著增强。"}
    target = Path(plan["dispatch_directory"]) / "CUMULATIVE-SUMMARY.json"
    assert not target.exists()
    save(target, result)
    print(json.dumps({k:v for k,v in result.items() if k not in {"files","sources","candidate_identity","blocks"}},ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    main(parser.parse_args().plan)
