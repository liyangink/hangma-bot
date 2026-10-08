#!/usr/bin/env python3
"""G18 离线两次本人自摸条件树；规则复用生产实现，不模拟对手。"""

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
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from hangma_bot.hangma import action_families, hand_analysis, progression, settlement, special_rules
from hangma_bot.hangma.candidate_facts import FactsAnalysisError, _remaining
from hangma_bot.hangma.engine import _build_context
from hangma_bot.hangma.internal_types import TILE_INDEX, TILE_ORDER, WindowContext, counts_from_tiles
from hangma_bot.hangma.public_tile_counts import count_public_tiles
from hangma_bot.kernel.actions import Discard, Tile
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import PlayerObservation


@dataclass(frozen=True)
class SecondDrawLeaf:
    """第一摸后合法弃牌叶；分值是第二次本人自摸的公开容量乘本人结算。"""

    discard: str
    mass: int
    capacity: int
    win_tile_types: int
    whites_held: int
    ordinary_natural_need: int
    ordinary_natural_progress_capacity: int
    seven_natural_need: int | None
    seven_natural_progress_capacity: int | None
    baotou_after: bool


def _drop(hand: tuple[Tile, ...], code: str) -> tuple[Tile, ...]:
    """机械去一张合法弃牌；规则合法性另由生产动作族确认。"""

    held = list(hand)
    for index, tile in enumerate(held):
        if tile.code == code:
            del held[index]
            return tuple(held)
    raise ValueError("弃牌不在暗手")


def _first_hu_routes(action: dict[str, Any], seat: int) -> dict[str, tuple[int, int]]:
    """生产一次摸牌完整结算：牌码 → (本人净分, 公开容量)。"""

    value = action.get("value_facts") or {}
    if value.get("coverage") != "complete":
        raise ValueError("一次摸牌价值事实非完整覆盖")
    routes = {}
    for route in value.get("routes") or []:
        if (route.get("followup_discard") is not None or
                (route.get("conditions") or {}).get("draw_kind") != "normal"):
            raise ValueError("一次摸牌路线不是普通自摸即时胡")
        delta = (route.get("conditional_settlement") or {}).get("score_delta")
        if (not isinstance(delta, list) or len(delta) != 4 or
                type(delta[seat]) is not int or delta[seat] <= 0):
            raise ValueError("一次摸牌结算缺少本人正净分")
        for useful in route.get("useful_tiles") or []:
            code, capacity = useful.get("code"), useful.get("remaining_estimate")
            if (not isinstance(code, str) or code in routes or
                    type(capacity) is not int or not 0 <= capacity <= 4):
                raise ValueError("一次摸牌路线牌码重复或容量未知")
            routes[code] = (delta[seat], capacity)
    return routes


def _first_context(current: WindowContext, root: tuple[Tile, ...],
                   draw_code: str, restricted: bool) -> WindowContext:
    """条件本人摸牌窗口；未来抓打圈用受限/不受限两种包络。"""

    return WindowContext(
        seat=current.seat, phase="draw", turn_seat=current.seat,
        responding_seats=(), hand_tiles=root, drawn_tile=Tile(draw_code),
        my_chi_count=current.my_chi_count, my_peng_codes=current.my_peng_codes,
        last_discard=None, catch_play=restricted,
        remaining_tile_count=current.remaining_tile_count,
    )


def evaluate_root(observation: PlayerObservation, action: dict[str, Any],
                  config: RuleConfig) -> dict[str, Any]:
    """评估一个已合法弃牌根，返回两种抓打包络的条件二摸胡价值。

    不读取未来墙、他家暗手或赛果。第一次摸牌的立即胡结算直接读取
    `hangma.value_analysis` 已生产的互斥路线；第二次摸牌复用生产胡牌
    分解、爆头/飘链转移、有财必拷响和结算函数。公开未见容量只作上界，
    不解释为实际自摸概率。未知容量或链状态必须向调用者抛错弃权。
    """

    key = action.get("action_key")
    if not isinstance(key, str) or not key.startswith("discard:"):
        raise ValueError("G18 只接受生产合法弃牌根")
    if observation.phase != "draw" or observation.turn_seat != observation.seat:
        raise ValueError("G18 只接受本人摸牌动作窗")
    if config.you_cai_bi_kao:
        raise ValueError("有财必拷响开启时未来权威爆头资格未覆盖，保守弃权")
    if observation.remaining_tile_count is None or observation.remaining_tile_count <= 20:
        raise ValueError("无可证明的下一次本人普通摸牌墙余边界")
    context = _build_context(observation)
    meld_count = len(observation.melds[observation.seat])
    discard_code = key.split(":", 1)[1]
    full = context.full_hand()
    if len(full) != 14 - 3 * meld_count:
        raise ValueError("动作前暗牌张数与副露不符")
    root = _drop(full, discard_code)
    root_baotou = progression.baotou_after_discard(root, meld_count)
    root_chain, root_piao = progression.chain_after_action(
        observation.rule_state.chain_count, observation.chain_piao,
        observation.rule_state.baotou, Discard(Tile(discard_code)),
    )
    if root_piao is None:
        raise ValueError("根弃牌后链内飘数未知")
    public = count_public_tiles(observation)
    own_visible_whites = sum(tile.code == "白" for tile in observation.discards[observation.seat])
    missing_own_piao = max(0, (observation.chain_piao or 0) - own_visible_whites)
    root_new_public = {discard_code: 1}
    root_counts = counts_from_tiles(root)
    first_routes = _first_hu_routes(action, observation.seat)
    first_capacities = {}
    for code in TILE_ORDER:
        amount = _remaining(code, root_counts, public, root_new_public)
        if code == "白":
            amount -= missing_own_piao
        if amount < 0:
            raise ValueError("本人链内飘白与公开剩余白板数矛盾")
        if amount > 0:
            first_capacities[code] = amount
    if not first_capacities:
        raise ValueError("公开容量无下一摸牌")
    for code, (_, amount) in first_routes.items():
        if first_capacities.get(code) != amount:
            raise ValueError("G18 一摸容量与生产 value_facts 不一致")
    first_mass = sum(first_capacities[code] * value for code, (value, _) in first_routes.items())
    first_baotou = progression.baotou_after_draw(
        root_baotou, root, meld_count, Tile(next(iter(first_capacities))), replacement=False,
    )

    @lru_cache(maxsize=None)
    def second_leaf(draw_code: str, first_discard: str) -> SecondDrawLeaf:
        """固定第一次条件摸牌与合法弃牌，枚举第二次摸牌立即胡。"""

        first_full = root + (Tile(draw_code),)
        waiting = _drop(first_full, first_discard)
        chain, piao = progression.chain_after_discard(
            root_chain, root_piao, first_baotou, Tile(first_discard)
        )
        after_baotou = progression.baotou_after_discard(waiting, meld_count)
        second_baotou = progression.baotou_after_draw(
            after_baotou, waiting, meld_count, Tile(draw_code), replacement=False,
        )
        new_public = Counter(root_new_public)
        new_public[first_discard] += 1
        waiting_counts = counts_from_tiles(waiting)
        ordinary_natural_need = hand_analysis._need_std(
            waiting_counts[:33], 0, 4 - meld_count, True
        )
        seven_natural_need = (
            7 - hand_analysis._chiitoi_pairs(waiting_counts[:33], 0)
            if meld_count == 0 else None
        )
        mass = capacity = win_types = 0
        ordinary_progress = seven_progress = 0
        for code in TILE_ORDER:
            remaining = _remaining(code, waiting_counts, public, dict(new_public))
            if code == "白":
                remaining -= missing_own_piao
            if remaining < 0:
                raise ValueError("第二摸白板容量与已知链内飘白矛盾")
            if remaining == 0:
                continue
            capacity += remaining
            if code != "白":
                index = TILE_INDEX[code]
                next_natural = (waiting_counts[:index] + (waiting_counts[index] + 1,)
                                + waiting_counts[index + 1:33])
                if hand_analysis._need_std(next_natural, 0, 4 - meld_count, True) < ordinary_natural_need:
                    ordinary_progress += remaining
                if (seven_natural_need is not None and
                        7 - hand_analysis._chiitoi_pairs(next_natural, 0) < seven_natural_need):
                    seven_progress += remaining
            split = hand_analysis.win_split(waiting + (Tile(code),), meld_count)
            if split is None or special_rules.you_cai_bi_kao_block(
                config.you_cai_bi_kao, split, second_baotou
            ):
                continue
            result = settlement.settle_win(
                split, chain, piao, second_baotou, config.base_score,
                observation.seat, observation.dealer_seat,
            )
            own_gain = result.score_delta[observation.seat]
            if own_gain <= 0:
                raise ValueError("生产条件胡的本人结算非正")
            mass += remaining * own_gain
            win_types += 1
        return SecondDrawLeaf(
            discard=first_discard, mass=mass, capacity=capacity,
            win_tile_types=win_types,
            whites_held=waiting_counts[33],
            ordinary_natural_need=ordinary_natural_need,
            ordinary_natural_progress_capacity=ordinary_progress,
            seven_natural_need=seven_natural_need,
            seven_natural_progress_capacity=(seven_progress if seven_natural_need is not None else None),
            baotou_after=after_baotou,
        )

    edges = []
    for draw_code, first_capacity in first_capacities.items():
        choices = {}
        for restricted in (False, True):
            future = _first_context(context, root, draw_code, restricted)
            legal, issues = action_families.discard_tile_codes(future)
            if issues or not legal:
                raise ValueError("第一次本人摸牌后的弃牌资格未知")
            leaves = tuple(second_leaf(draw_code, discard) for discard in legal)
            best = min(leaves, key=lambda leaf: (-leaf.mass, -leaf.win_tile_types, leaf.discard))
            best_natural = min(
                leaves,
                key=lambda leaf: (leaf.ordinary_natural_need,
                                  -leaf.ordinary_natural_progress_capacity,
                                  -leaf.mass, leaf.discard),
            )
            choices["restricted" if restricted else "unrestricted"] = {
                "best_second_hu": best.__dict__,
                "best_natural_progress": best_natural.__dict__,
                "legal_discard_count": len(leaves),
            }
        edges.append({
            "draw": draw_code, "capacity": first_capacity,
            "first_hu_score": first_routes.get(draw_code, (None, None))[0],
            "best_second": choices,
        })
    return {
        "action": key, "first_draw_public_capacity": sum(first_capacities.values()),
        "first_hu_mass": first_mass, "root_whites_held": root_counts[33],
        "root_baotou": root_baotou, "root_chain_count": root_chain,
        "edges": edges,
        "boundary": "两次本人摸牌均以单局继续、公开容量可得为条件；未来抓打圈分别给出受限与不受限包络，不估计对手先胡或真实牌墙概率。",
    }
