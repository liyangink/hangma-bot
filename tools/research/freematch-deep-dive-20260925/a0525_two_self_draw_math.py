#!/usr/bin/env python3
"""四白板单局的理想化两次本人摸牌算术上界；仅用 hangma 规则数学。"""

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
from hangma_bot.hangma.hand_analysis import analyse_counts_progress, win_split
from hangma_bot.hangma.internal_types import TILE_INDEX, TILE_ORDER, counts_from_tiles
from hangma_bot.hangma.public_tile_counts import count_unseen_tiles
from hangma_bot.hangma.settlement import compute_fan
from hangma_bot.kernel.actions import Tile

AUDIT = Path(
    "artifacts/sessions/r18-sse-freematch-campaign-20260925b/audit/runs/"
    "run-147bb0adc21e47e783abb465f6b68388/participants/"
    "u_13495c3d79c8/decisions.jsonl"
)
GAME = "a_0525f4514164_r1_b1_t0"


@lru_cache(maxsize=100_000)
def _summary(counts: tuple[int, ...], melds: int):
    """复用规则层同一牌效数学，不实现第二套向听。"""
    return analyse_counts_progress(counts, melds)


def _replace(counts: tuple[int, ...], index: int, delta: int):
    updated = list(counts)
    updated[index] += delta
    return tuple(updated)


@lru_cache(maxsize=100_000)
def _plain_fan(counts: tuple[int, ...], melds: int) -> int:
    """只读规则结算：固定无新杠飘/爆头，隔离胡牌分支及四白番差。"""
    hand = tuple(Tile(code) for index, code in enumerate(TILE_ORDER)
                 for _ in range(counts[index]))
    split = win_split(hand, melds)
    if split is None:
        raise ValueError("规则向听与胡牌分解不一致")
    return compute_fan(split, chain_count=0, piao=0, baotou=False).fan


def _two_draw_numerator(after_discard: tuple[int, ...], unseen: tuple[int, ...], melds: int):
    """未知池均匀抽两张、两次本人摸牌间可选一次最优弃牌的胡牌容量分子。"""
    n = sum(unseen)
    numerator = 0
    fan_numerator = 0
    first_draw_capacity = 0
    first_draw_routes = 0
    for draw_index, available in enumerate(unseen):
        if not available:
            continue
        drawn = _replace(after_discard, draw_index, 1)
        first = _summary(drawn, melds)
        if first.is_win:
            numerator += available * (n - 1)
            fan_numerator += available * (n - 1) * _plain_fan(drawn, melds)
            first_draw_capacity += available
            continue
        next_unseen = list(unseen)
        next_unseen[draw_index] -= 1
        best_win_capacity = 0
        best_fan_capacity = 0
        for discard_index, held in enumerate(drawn):
            if not held:
                continue
            successor = _summary(_replace(drawn, discard_index, -1), melds)
            if successor.shanten != 0:
                continue
            capacity = sum(next_unseen[TILE_INDEX[code]] for code in successor.useful_codes)
            fan_capacity = sum(
                next_unseen[TILE_INDEX[code]] * _plain_fan(
                    _replace(_replace(drawn, discard_index, -1), TILE_INDEX[code], 1), melds
                ) for code in successor.useful_codes if next_unseen[TILE_INDEX[code]]
            )
            if capacity > best_win_capacity:
                best_win_capacity = capacity
            if fan_capacity > best_fan_capacity:
                best_fan_capacity = fan_capacity
        if best_win_capacity:
            first_draw_routes += available
        numerator += available * best_win_capacity
        fan_numerator += available * best_fan_capacity
    return numerator, fan_numerator, first_draw_capacity, first_draw_routes, n


def main() -> int:
    if not AUDIT.is_file():
        raise SystemExit("官方审计输入缺失")
    requests = {}
    for line in AUDIT.open(encoding="utf-8"):
        if '"decision_input"' not in line:
            continue
        record = json.loads(line)
        context = record.get("context") or {}
        seq = context.get("trigger_seq")
        if (record.get("kind") == "decision_input" and context.get("game_id") == GAME
                and context.get("round_no") == 6 and seq in (1274, 1350)):
            requests[seq] = decision_request_from_json(record["payload"]["request"])
    if len(requests) != 2:
        raise SystemExit("目标观察不完整")
    for seq, request in sorted(requests.items()):
        observation = request.observation
        unseen = count_unseen_tiles(observation)
        if any(value is None for value in unseen):
            raise SystemExit(f"seq={seq} 可见未见牌容量不完整")
        hand = list(observation.my_hand)
        melds = len(observation.melds[observation.seat])
        print(f"seq={seq} 未知池={sum(unseen)}；两次摸牌均假设无对手动作、未知池均匀且可最优弃牌")
        for code in ("西", "1b", "4w", "4b"):
            if Tile(code) not in hand:
                continue
            after = list(hand)
            after.remove(Tile(code))
            counts = counts_from_tiles(tuple(after))
            numerator, fan_numerator, immediate, second_routes, total = _two_draw_numerator(counts, unseen, melds)
            print(f"  弃{code}: 首摸直接胡容量={immediate}, 首摸可转听容量={second_routes}, "
                  f"两摸胡牌容量分子={numerator}, 理想化比例={numerator/(total*(total-1)):.6f}, "
                  f"无新杠飘/爆头的番加权分子={fan_numerator}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
