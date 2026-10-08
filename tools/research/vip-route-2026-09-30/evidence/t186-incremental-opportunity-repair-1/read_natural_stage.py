"""已完整读回的自然小批按独立母来源分账，不把阶段区间当正式增强。"""

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


def main(path):
    """必须先有全评分/同物理牌山读回终态，再生成配对开发分数；不自动派发。"""
    background_priority()
    plan, plan_pin, _ = validate(path)
    closed_path = Path(plan["dispatch_directory"]) / "READOUT-CLOSED.json"
    closed = json.loads(closed_path.read_text())
    assert closed["complete"] and closed["source_stable"] and closed["plan_pin"] == plan_pin
    assert closed["actual_tables"] == plan["planned_table_instances"] and closed["actual_cpu_workers"] == 4
    assert all(pin(Path(p)) == h for p, h in closed["files"].items())
    by_task = {(r["root"], r["rotation"], r["arm"]): r for r in closed["tables"]}
    assert len(by_task) == len(closed["tables"])
    sources, total, signs = [], Counter(), Counter()
    for i in plan["root_indices"]:
        paired, summed = [], Counter()
        for rotation in range(4):
            a, c = (by_task[(i, rotation, arm)]["account"] for arm in range(2))
            assert set(a) == set(c)
            delta = {k: c[k] - a[k] for k in a}
            assert delta["net"] == delta["ordinary_hu_income"] + delta["large_hu_income"] + delta["payments"]
            paired.append({"rotation": rotation, "baseline": a, "candidate": c, "delta": delta})
            summed.update(delta)
        sources.append({"root": i, "root_id": plan["roots"][i - 1]["root_id"], "four_seat_delta_sums": dict(summed), "paired_tables": paired})
        total.update(summed)
        signs["positive" if summed["net"] > 0 else "negative" if summed["net"] < 0 else "zero"] += 1
    n = len(sources)
    means = {k: v / (4 * n) for k, v in total.items()}
    generator = random.Random(plan["bootstrap"]["seed"])
    values = [s["four_seat_delta_sums"]["net"] for s in sources]
    samples = sorted(sum(values[generator.randrange(n)] for _ in range(n)) / (4 * n) for _ in range(plan["bootstrap"]["replicates"]))
    interval = [samples[int(len(samples) * .025)], samples[int(len(samples) * .975)]]
    exploratory_continue = means["net"] > 0 or (means["large_hu_income"] > 0 and means["net"] >= -10)
    summary = {"schema": "t186-natural-stage-summary/1", "complete": True, "plan_pin": plan_pin,
        "readout_pin": pin(closed_path), "candidate_identity": plan["candidates"][0]["identity"],
        "actual_complete_tables": closed["actual_tables"], "actual_single_hands": closed["actual_tables"] * plan["rounds"],
        "actual_focal_scores": closed["actual_focal_score_calls"], "independent_roots": n,
        "mean_delta_per_complete_table": means, "source_sign_counts": dict(signs), "sources": sources,
        "net_exploratory_source_bootstrap95": interval, "exploratory_next_stage_budget_eligible": exploratory_continue,
        "natural_strength_or_online_admission": False, "new_scores_worlds_tables_models_HTTP": 0,
        "notes": "阶段开发与反复读回，不授正式95%覆盖或总体显著增强；预算通过不自动派发后续。"}
    save(Path(plan["dispatch_directory"]) / "SUMMARY.json", summary)
    print(json.dumps({k:v for k,v in summary.items() if k not in {"sources", "candidate_identity"}}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    main(parser.parse_args().plan)
