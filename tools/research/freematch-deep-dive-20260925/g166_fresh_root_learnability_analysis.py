#!/usr/bin/env python3
"""G166：按独立根与相关隐藏世界拆分连续配对收益的可学习性描述。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/freematch-deep-dive-20260925'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

from collections import Counter
import json
import math
from pathlib import Path
import random
from statistics import mean, variance

import g166_fresh_root_two_arm_teacher as teacher


BASE = teacher.OUT
OUT = BASE / "analysis.json"
BOOTSTRAP_SEED = 20260928166
BOOTSTRAP_REPLICATES = 20_000


def interval(values: list[float], seed: int) -> list[float] | None:
    """一个池×根只贡献一个窗口；按根等权抽样，不抽同窗世界。"""
    if not values:
        return None
    rng = random.Random(seed)
    estimates = sorted(mean(rng.choice(values) for _ in values)
                       for _ in range(BOOTSTRAP_REPLICATES))
    return [estimates[int(0.025 * BOOTSTRAP_REPLICATES)],
            estimates[int(0.975 * BOOTSTRAP_REPLICATES)]]


def correlation(left: list[float], right: list[float]) -> float | None:
    """量具重复性描述；不把两半的符号当候选最优标签。"""
    if len(left) != len(right) or len(left) < 3:
        return None
    lm, rm = mean(left), mean(right)
    num = sum((a - lm) * (b - rm) for a, b in zip(left, right))
    den_l = sum((a - lm) ** 2 for a in left)
    den_r = sum((b - rm) ** 2 for b in right)
    if den_l == 0 or den_r == 0:
        return None
    return num / math.sqrt(den_l * den_r)


def group(rows: list[dict], seed: int) -> dict:
    """分清历史世界、重采样世界、终局分量及同窗噪声。"""
    if len({(row["mix"], row["root_index"]) for row in rows}) != len(rows):
        raise ValueError("G166 同池同根超过一个窗口")
    continuous = []
    historical = []
    resampled = []
    split_a, split_b = [], []
    sampling_variances = []
    components = {name: [] for name in teacher.COMPONENTS}
    next_action = Counter()
    for row in rows:
        pairs = row["world_pairs"]
        if [pair["sample_key"] for pair in pairs] != list(teacher.WORLD_KEYS):
            raise ValueError("G166 世界键顺序或数量漂移")
        all_values = [float(pair["focal_delta_alt_minus_parent"]) for pair in pairs]
        sampled = all_values[1:]
        continuous.append(mean(all_values))
        historical.append(all_values[0])
        resampled.append(mean(sampled))
        split_a.append(mean(sampled[:8]))
        split_b.append(mean(sampled[8:]))
        sampling_variances.append(variance(sampled) / 16)
        for name in teacher.COMPONENTS:
            components[name].append(mean(
                float(pair["component_alt_minus_parent"][name]) for pair in pairs))
        for pair in pairs:
            for arm in ("parent", "alternate"):
                next_action[(arm, pair[arm]["terminal_before_next_focal_action"])] += 1
    component_means = {name: mean(values) if values else None
                       for name, values in components.items()}
    if rows and abs(sum(component_means.values()) - mean(continuous)) > 1e-9:
        raise ValueError("G166 四主分量及剩余分量没有还原配对积分")
    return {
        "windows": len(rows),
        "independent_pool_roots": len({(row["mix"], row["root_index"])
                                       for row in rows}),
        "related_world_pairs": len(rows) * len(teacher.WORLD_KEYS),
        "window_equal_mean": mean(continuous) if rows else None,
        "root_bootstrap_95": interval(continuous, seed),
        "historical_mean": mean(historical) if rows else None,
        "resampled_mean": mean(resampled) if rows else None,
        "component_window_means": component_means,
        "split_eight_eight_window_mean_correlation": correlation(split_a, split_b),
        "mean_sampling_variance_of_resampled_window_mean": (
            mean(sampling_variances) if rows else None),
        "between_window_mean_sample_variance": (
            variance(resampled) if len(rows) >= 2 else None),
        "terminal_before_next_focal_action": {
            arm: {"yes": next_action[(arm, True)],
                  "no": next_action[(arm, False)]}
            for arm in ("parent", "alternate")},
    }


def main() -> None:
    """只读完整教师来源并写一次固定分析；不优化算子参数。"""
    if OUT.exists():
        raise FileExistsError("G166 分析已存在，不覆盖")
    result = json.loads((BASE / "result.json").read_text(encoding="utf-8"))
    rows_path = BASE / "rows.jsonl"
    if (result["status"] != "complete"
            or result["windows_completed"] != 64
            or result["rows_sha256"] != teacher.source.g160.sha(rows_path)):
        raise ValueError("G166 双臂教师尚未完成或字节摘要漂移")
    rows = [json.loads(line) for line in rows_path.read_text(
        encoding="utf-8").splitlines()]
    groups = {}
    for mix in ("H", "M"):
        for white in (0, 1):
            key = f"{mix}/{white}"
            subset = [row for row in rows if row["mix"] == mix
                      and row["white_before"] == white]
            if len(subset) != 16:
                raise ValueError("G166 固定分层覆盖不是十六个独立根")
            groups[key] = group(subset, BOOTSTRAP_SEED + len(groups))
        groups[mix] = group([row for row in rows if row["mix"] == mix],
                            BOOTSTRAP_SEED + 10 + len(groups))
    payload = {
        "schema": "g166-fresh-root-learnability-analysis/1",
        "source_rows_sha256": teacher.source.g160.sha(rows_path),
        "source_result_sha256": teacher.source.g160.sha(BASE / "result.json"),
        "analysis_script_sha256": teacher.source.g160.sha(Path(__file__)),
        "bootstrap_seed": BOOTSTRAP_SEED,
        "bootstrap_replicates": BOOTSTRAP_REPLICATES,
        "groups": groups,
        "boundary": "相关同世界单局诊断；置信区间只描述根级采样，不构成发布门。",
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False,
                              sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: {name: value[name] for name in (
        "windows", "window_equal_mean", "root_bootstrap_95",
        "component_window_means", "split_eight_eight_window_mean_correlation")}
        for key, value in groups.items()}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
