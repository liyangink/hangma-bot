"""两个独立开发块全闭后累计来源分账；不把旧确认或条件题混入。"""

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
    """验证来源无重漏、身份一致和原读回，再按16母源报告开发区间与费用判断。"""
    background_priority()
    plan, plan_pin, _ = validate(path)
    paths = [Path(p) for p in plan["prior_stage_plans"]] + [Path(path)]
    files, sources, blocks, total, scores, tables = {}, [], [], Counter(), 0, 0
    for p in paths:
        stage, stage_pin, _ = validate(p)
        assert stage["candidates"][0]["identity"] == plan["candidates"][0]["identity"] and stage["parent"]["identity"] == plan["parent"]["identity"]
        assert stage["rounds"] == plan["rounds"] and stage["execution_backend"] == plan["execution_backend"]
        d = Path(stage["dispatch_directory"])
        summary = json.loads((d / "SUMMARY.json").read_text())
        readout = json.loads((d / "READOUT-CLOSED.json").read_text())
        assert summary["complete"] and summary["plan_pin"] == stage_pin and summary["readout_pin"] == pin(d / "READOUT-CLOSED.json")
        assert all(pin(Path(f)) == h for f,h in readout["files"].items()) and readout["complete"] and readout["source_stable"]
        assert [s["root"] for s in summary["sources"]] == stage["root_indices"]
        sources += summary["sources"]
        scores += summary["actual_focal_scores"]
        tables += summary["actual_complete_tables"]
        blocks.append({"plan":str(p),"mean_delta_per_complete_table":summary["mean_delta_per_complete_table"],
            "source_sign_counts":summary["source_sign_counts"]})
        for f in [p, d/"SUMMARY.json", d/"READOUT-CLOSED.json", d/"CLOSED.json"]:
            files[str(f)] = pin(f)
    assert [s["root"] for s in sources] == list(range(1,17)) and len({s["root_id"] for s in sources}) == 16 and tables == 128
    for s in sources:
        total.update(s["four_seat_delta_sums"])
    means = {k:v/64 for k,v in total.items()}
    values = [s["four_seat_delta_sums"]["net"] for s in sources]
    rng = random.Random(plan["bootstrap"]["seed"])
    draws = sorted(sum(values[rng.randrange(16)] for _ in range(16))/64 for _ in range(plan["bootstrap"]["replicates"]))
    interval = [draws[int(len(draws)*.025)],draws[int(len(draws)*.975)]]
    eligible = means["net"] > 0 or (means["large_hu_income"] > 0 and means["net"] >= -10)
    result = {"schema":"t186-cumulative-development/1","complete":True,"plan_pin":plan_pin,"files":files,
        "candidate_identity":plan["candidates"][0]["identity"],"independent_roots":16,"actual_complete_tables":128,
        "actual_single_hands":1024,"actual_focal_scores":scores,"mean_delta_per_complete_table":means,
        "net_exploratory_source_bootstrap95":interval,"sources":sources,"blocks":blocks,
        "exploratory_next_stage_budget_eligible":eligible,"new_block_net_direction":blocks[-1]["mean_delta_per_complete_table"]["net"],
        "natural_strength_or_online_admission":False,"new_scores_worlds_tables_models_HTTP":0,
        "next_stage_auto_dispatch":False}
    save(Path(plan["dispatch_directory"]) / "CUMULATIVE-SUMMARY.json",result)
    print(json.dumps({k:v for k,v in result.items() if k not in {"files","sources","candidate_identity","blocks"}},ensure_ascii=False))


if __name__ == "__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--plan",type=Path,required=True)
    main(p.parse_args().plan)
