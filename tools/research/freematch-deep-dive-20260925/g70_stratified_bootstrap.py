#!/usr/bin/env python3
"""G70 探索性描述：按起手白板、庄位、标准型初始向听做同房配对标准化。"""

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

import gzip
import hashlib
import json
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g69-same-room-route-chain-20260928/initial_shape_rounds.jsonl.gz')
OUT = SOURCE.with_name("initial_shape_standardized_bootstrap.json")
SEED = 20260928
DRAWS = 20000
METRICS = ("any_ready", "high_ready", "win", "high_win",
           "high_win_with_prior_high", "high_win_without_prior_high")


def stratum(row: dict) -> tuple[int, int, int]:
    """只从事前起手事实取有限分层；不按后摸白板或赛果切片。"""

    shanten = row["initial_standard_best"]
    return (int(row["start_white"] > 0), int(row["dealer"]),
            0 if shanten <= 2 else 1 if shanten == 3 else 2)


def outcomes(row: dict) -> tuple[int, ...]:
    win = row["status"] == "win"
    high_win = win and row["fan"] >= 2
    high_ready = row["first_high_ready"] is not None
    return (int(row["first_any_ready"] is not None), int(high_ready),
            int(win), int(high_win), int(high_win and high_ready),
            int(high_win and not high_ready))


def main() -> None:
    if OUT.exists():
        raise SystemExit("G70 标准化区间已存在，拒绝覆盖")
    rows = [json.loads(line) for line in gzip.open(SOURCE, "rt", encoding="utf-8")]
    if len(rows) != 5120:
        raise ValueError("G70 双方同房起手牌形总数不完整")
    rng = np.random.default_rng(SEED)
    summary = {}
    strata = [(white, dealer, shape)
              for white in (0, 1) for dealer in (0, 1) for shape in (0, 1, 2)]
    cell_index = {cell: index for index, cell in enumerate(strata)}
    actor_index = {"us": 0, "peer": 1}
    for peer, nrooms in (("xuanwu_2346", 15), ("tengshe_0638", 17)):
        subset = [row for row in rows if row["peer"] == peer]
        rooms = sorted({row["room"] for row in subset})
        if len(rooms) != nrooms or len(subset) != 160 * nrooms:
            raise ValueError("G70 房间/同房单局分母不一致")
        room_index = {room: index for index, room in enumerate(rooms)}
        total = np.zeros((nrooms, 2, len(strata)), dtype=np.int64)
        positive = np.zeros((nrooms, 2, len(strata), len(METRICS)), dtype=np.int64)
        for row in subset:
            i, j, k = room_index[row["room"]], actor_index[row["actor"]], cell_index[stratum(row)]
            total[i, j, k] += 1
            positive[i, j, k] += np.array(outcomes(row), dtype=np.int64)
        if not np.all(total.sum(axis=(0, 2)) == 80 * nrooms):
            raise ValueError("G70 同房双方每房八十单局不一致")
        weights = total.sum(axis=(0, 1)).astype(float)
        weights /= weights.sum()
        observed_den = total.sum(axis=0)
        if np.any(observed_den == 0):
            raise ValueError("G70 事前分层某方没有观测")
        observed_rates = positive.sum(axis=0) / observed_den[:, :, None]
        observed = (observed_rates[1] - observed_rates[0]).T @ weights
        sampled = rng.integers(0, nrooms, size=(DRAWS, nrooms))
        replicate_den = total[sampled].sum(axis=1)
        replicate_pos = positive[sampled].sum(axis=1)
        valid = np.all(replicate_den > 0, axis=(1, 2))
        if valid.sum() < DRAWS * .99:
            raise ValueError("G70 房级重采样分层空单元过多")
        rates = replicate_pos[valid] / replicate_den[valid, :, :, None]
        replicates = ((rates[:, 1] - rates[:, 0]) * weights[None, :, None]).sum(axis=1)
        metric_summary = {}
        for m, name in enumerate(METRICS):
            metric_summary[name] = {
                "standardized_peer_minus_us_per_hand": float(observed[m]),
                "room_bootstrap_95pct": [float(np.quantile(replicates[:, m], .025)),
                                           float(np.quantile(replicates[:, m], .975))],
            }
        summary[peer] = {"metrics": metric_summary,
                         "pooled_stratum_weights": {str(cell): float(weights[k])
                                                    for k, cell in enumerate(strata)},
                         "valid_replicates": int(valid.sum()),
                         "rooms": nrooms}
    result = {"schema": "g70-initial-shape-standardized-descriptive/1",
              "exploratory": True, "seed": SEED, "draws": DRAWS,
              "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
              "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "strata": "起手白板 0/≥1 × 庄位否/是 × 起手标准型最好弃牌向听≤2/3/≥4",
              "peers": summary,
              "boundary": "只消除这三个粗起手维度的分布差；其他手牌质量、对手行动和赛程仍混杂，区间仅描述房间间波动。"}
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({peer: data["metrics"] for peer, data in summary.items()}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
