#!/usr/bin/env python3
"""G7a：同一合法观察下比较三次本人自摸内可达胡牌的理想化容量。"""

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

from functools import lru_cache
import json
from pathlib import Path

from hangma_bot.application.audit_codec import decision_request_from_json
from hangma_bot.hangma.hand_analysis import analyse_counts_progress
from hangma_bot.hangma.internal_types import TILE_INDEX, counts_from_tiles
from hangma_bot.hangma.public_tile_counts import count_unseen_tiles
from hangma_bot.kernel.actions import Tile

AUDIT = Path(
    "artifacts/sessions/r18-sse-freematch-campaign-20260925b/audit/runs/"
    "run-147bb0adc21e47e783abb465f6b68388/participants/"
    "u_13495c3d79c8/decisions.jsonl"
)
GAME = "a_0525f4514164_r1_b1_t0"
SEQ = 1350


@lru_cache(maxsize=500_000)
def summary(counts: tuple[int, ...], melds: int):
    """唯一规则数学入口；本脚本只枚举条件未来，不重写胡牌/向听。"""
    return analyse_counts_progress(counts, melds)


def changed(counts: tuple[int, ...], index: int, delta: int):
    values = list(counts)
    values[index] += delta
    return tuple(values)


def falling(n: int, length: int) -> int:
    result = 1
    for used in range(length):
        result *= n-used
    return result


@lru_cache(maxsize=500_000)
def favorable(counts: tuple[int, ...], unseen: tuple[int, ...], melds: int, depth: int) -> int:
    """最优中间弃牌下的有序抽牌成功序列容量分子；不取赛后牌墙。"""
    current = summary(counts, melds)
    if current.shanten >= depth:
        return 0
    if depth == 1:
        if current.shanten != 0:
            return 0
        return sum(unseen[TILE_INDEX[code]] for code in current.useful_codes)
    total = 0
    unseen_total = sum(unseen)
    for drawn_index, available in enumerate(unseen):
        if available <= 0:
            continue
        drawn = changed(counts, drawn_index, 1)
        next_unseen = changed(unseen, drawn_index, -1)
        if summary(drawn, melds).is_win:
            best = falling(unseen_total-1, depth-1)
        else:
            best = 0
            for discard_index, held in enumerate(drawn):
                if held <= 0:
                    continue
                after = changed(drawn, discard_index, -1)
                if summary(after, melds).shanten >= depth-1:
                    continue
                value = favorable(after, next_unseen, melds, depth-1)
                if value > best:
                    best = value
        total += available * best
    return total


def main() -> int:
    request = None
    for line in AUDIT.open(encoding="utf-8"):
        if '"decision_input"' not in line:
            continue
        record = json.loads(line)
        context = record.get("context") or {}
        if (record.get("kind") == "decision_input" and context.get("game_id") == GAME
                and context.get("round_no") == 6 and context.get("trigger_seq") == SEQ):
            request = decision_request_from_json(record["payload"]["request"])
            break
    if request is None:
        raise SystemExit("目标官方观察缺失")
    observation = request.observation
    unseen = count_unseen_tiles(observation)
    if any(value is None for value in unseen):
        raise SystemExit("公开未见牌容量不完整")
    melds = len(observation.melds[observation.seat])
    n = sum(unseen)
    print(f"seq={SEQ}, 未知池={n}, 无他家动作/保留区条件，按全未知池均匀无放回抽牌")
    for discard in ("西", "4w"):
        hand = list(observation.my_hand)
        hand.remove(Tile(discard))
        counts = counts_from_tiles(tuple(hand))
        for depth in (2, 3):
            numerator = favorable(counts, unseen, melds, depth)
            print(f"弃{discard} depth={depth}: 容量分子={numerator}, "
                  f"理想化比例={numerator/falling(n, depth):.8f}")
    print("缓存:", "规则摘要", summary.cache_info(), "续打状态", favorable.cache_info())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
