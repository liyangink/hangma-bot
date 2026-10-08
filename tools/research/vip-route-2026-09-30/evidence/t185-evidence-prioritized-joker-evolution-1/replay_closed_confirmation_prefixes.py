"""只复算两批已闭合历史来源前缀，检查小样本筛选的风险；不启动评分或桌赛。"""

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
import math
from pathlib import Path

import numpy as np

from common import HERE, pin, save


HISTORICAL_BATCHES = (
    "t103-joint-breadth-fresh-confirmation-1",
    "t112-fixed-t110-s02-fresh-confirmation-1",
)
PREFIX_SIZES = (8, 16, 32, 64)
BOOTSTRAP_REPLICATES = 20_000
BOOTSTRAP_SEED = 2026100502


def replay():
    """读取固定历史终态并排他保存探索性统计，不改原终态或当前确认判据。

    观测单位是同一母来源四换座的平均积分差，单位为分/完整桌赛。
    前缀按历史冻结顺序选取；反复查看的普通区间没有序贯覆盖保证。
    输出不构成淘汰、增强、上线或真实未来误选概率证明。
    """
    rows = []
    for batch_index, name in enumerate(HISTORICAL_BATCHES):
        source = _project_file(_PROJECT_ROOT, HERE.parent / name / "CAMPAIGN-CLOSURE.json")
        source_pin = pin(source)
        closed = json.loads(source.read_text())
        assert closed["whole_batch_valid"] and not closed["issues"]
        assert closed["planned_independent_roots"] == 128
        values = closed["root_mean_deltas"]
        assert len(values) == 128
        assert all(type(v) in (int, float) and math.isfinite(v) for v in values)
        assert sum(values) / 128 == closed["net_score_delta_per_table"]
        assert closed["planned_actual_tables"] == 128 * 4 * 2
        prefixes = []
        for count in PREFIX_SIZES:
            sample = np.asarray(values[:count], dtype=float)
            rng = np.random.default_rng(BOOTSTRAP_SEED + batch_index * 1000 + count)
            boot = sample[rng.integers(0, count, size=(BOOTSTRAP_REPLICATES, count))].mean(axis=1)
            interval = np.quantile(boot, [0.025, 0.975]).tolist()
            prefixes.append({
                "mother_sources": count,
                "paired_complete_tables": count * 4,
                "actual_table_instances_in_prefix": count * 4 * 2,
                "mean_net_delta_per_table": float(sample.mean()),
                "exploratory_percentile_95": interval,
                "positive_sources": int(np.sum(sample > 0)),
                "negative_sources": int(np.sum(sample < 0)),
                "zero_sources": int(np.sum(sample == 0)),
                "time_uniform_coverage_or_strength_claim": False,
            })
        assert pin(source) == source_pin
        rows.append({
            "batch": name,
            "closed_source_pin": source_pin,
            "original_full_128_mean": closed["net_score_delta_per_table"],
            "original_full_128_interval": closed["root_cluster_percentile_95"],
            "original_positive_lower_bound": closed["root_cluster_percentile_95"][0] > 0,
            "baseline": "R18",
            "prefixes": prefixes,
        })
    return {
        "schema": "t185-closed-historical-prefix-replay/1",
        "complete": True,
        "script_pin": pin(Path(__file__)),
        "bootstrap_replicates": BOOTSTRAP_REPLICATES,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "historical_order_only": True,
        "repeated_intervals_are_exploratory": True,
        "current_confirmation_scores_read": False,
        "original_result_files_changed": False,
        "actual_new_scores": 0,
        "actual_new_worlds": 0,
        "actual_new_table_calls": 0,
        "actual_new_model_calls": 0,
        "actual_new_HTTP_calls": 0,
        "strength_deadline_or_release_admission": False,
        "batches": rows,
    }


if __name__ == "__main__":
    result = replay()
    save(_project_file(_PROJECT_ROOT, HERE / "HISTORICAL-PREFIX-REPLAY.json"), result)
    print(json.dumps({"complete": True, "historical_batches": len(result["batches"]),
                      "new_scores_worlds_tables_models_HTTP": 0}))
