"""四家公开牌去重；只读取当前单局玩家可见的牌河、副露和事件。

官方 v18 连续快照与 v20 明杠快照均保留被鸣牌的牌河记录，同一张牌也在
副露中出现。碰只重叠一张，补杠不再次领取弃牌；四张杠牌已全部公开。
吃的供牌优先采用官方吃事件明确的领取牌；旧事件才用连续弃牌→吃或上家
完整牌河中的唯一可能牌证明。证据冲突或有多种可能时不猜。
"""

from collections import Counter, defaultdict
from typing import Optional, Tuple

from hangma_bot.kernel.observation import PlayerObservation

from .internal_types import TILE_ORDER
from .special_rules import is_passive_observation_event

PublicCounts34 = Tuple[Optional[int], ...]
"""按规范34种牌排列；None表示该牌种的牌河/副露重叠尚无法确定。"""


def _chi_claims(observation: PlayerObservation):
    """按副露所有者及三张组合保存每次吃的供牌证据，不合并同形副露。"""
    claims = defaultdict(list)
    seen = {}
    previous = None
    pending = None
    watermark = observation.consumed_seq
    if watermark is None:
        watermark = observation.snapshot_seq
    for event in observation.public_history:
        if event.seq > watermark:
            continue
        if event.seq in seen:
            if event != seen[event.seq]:
                return {}  # 同序号冲突无法分辨哪一份历史正确，不能选择有利版本。
            continue
        if previous is not None and event.seq < previous:
            return {}
        seen[event.seq] = event
        if previous is None or event.seq != previous + 1:
            pending = None
        previous = event.seq
        if event.kind in ("deal", "round_started", "round_ended", "game_ended"):
            claims.clear()
            pending = None
        elif event.kind == "tile_discarded":
            pending = (event.seat, event.tiles[0].code) if event.seat is not None and len(event.tiles) == 1 else None
        elif event.kind == "chi":
            shape = tuple(sorted(tile.code for tile in event.tiles))
            if event.claimed_tile is not None and event.seat is not None and len(shape) == 3:
                # v18 保存事件已明确给出 chi.tile；它证明这次吃领取的牌，
                # 不要求未收到的前置弃牌事件，也不能复用为另一次同形吃。
                proof = ((event.seat - 1) % 4, event.claimed_tile.code)
                if pending is not None and pending != proof:
                    # 连续弃牌与明确领取牌冲突时，不挑选有利的一份历史；
                    # 与同序号冲突一致，仅允许当前快照的唯一交集另行确证。
                    return {}
                claims[(event.seat, shape)].append(proof)
            elif (pending is not None and event.seat is not None and len(shape) == 3
                    and pending[0] == (event.seat - 1) % 4 and pending[1] in shape):
                claims[(event.seat, shape)].append(pending)
            pending = None
        elif not is_passive_observation_event(event):
            # 他家摸牌、其他鸣牌或未知事件均不能夹在同一次弃牌与吃之间。
            pending = None
    return claims


def count_public_tiles(observation: PlayerObservation) -> PublicCounts34:
    """给候选事实提供去重公开计数；缺证据仅将受影响的牌种标为空。

    不补写原牌河、不读取暗牌；原公开副露中的各张物理牌互不重叠。
    返回值仅在规则模块内部流转，消费未知值时由逐候选边界显式降级。
    """
    rivers = [Counter(tile.code for tile in river) for river in observation.discards]
    river_total = sum(rivers, Counter())
    meld_total = Counter(tile.code for group in observation.melds for meld in group for tile in meld.tiles)
    counts = river_total + meld_total
    overlaps = Counter()
    uncertain = set()
    claims = _chi_claims(observation)
    chi_shapes = Counter((meld.seat, tuple(sorted(t.code for t in meld.tiles)))
                         for group in observation.melds for meld in group if meld.kind == "chi")
    # 历史有更多同形吃而当前副露没有对应实例：不能混用旧单局/冲突证据。
    claims = {key: list(value) for key, value in claims.items() if len(value) <= chi_shapes[key]}
    used_by_source = Counter()

    for group in observation.melds:
        for meld in group:
            codes = tuple(tile.code for tile in meld.tiles)
            if meld.kind == "peng" and len(codes) == 3 and len(set(codes)) == 1:
                code = codes[0]
                available = river_total[code] if meld.from_seat is None else rivers[meld.from_seat][code]
                if available:
                    overlaps[code] += 1
            elif meld.kind == "chi":
                key = (meld.seat, tuple(sorted(codes)))
                proofs = claims.get(key, [])
                proof = proofs.pop(0) if proofs else None
                if proof is not None and not rivers[proof[0]][proof[1]]:
                    # 当前完整牌河否定旧历史供牌时，旧证据失效；仍可由快照
                    # 的唯一交集恢复，不能将矛盾误当作“没有重叠”继续计数。
                    proof = None
                if proof is None:
                    source = meld.from_seat if meld.from_seat is not None else (meld.seat - 1) % 4
                    possible = {code for code in codes if rivers[source][code]}
                    if len(possible) == 1:
                        # 官方吃只来自上家且被吃牌仍留河中；交集唯一就是确证，
                        # 不必为这类缺史快照放弃全部牌效。多实例仍须核对河中张数。
                        proof = (source, next(iter(possible)))
                if proof is not None and (meld.from_seat is None or proof[0] == meld.from_seat):
                    source, code = proof
                    if rivers[source][code]:
                        used_by_source[(source, code)] += 1
                        overlaps[code] += 1
                        if used_by_source[(source, code)] > rivers[source][code]:
                            uncertain.add(code)
                else:
                    source = meld.from_seat if meld.from_seat is not None else (meld.seat - 1) % 4
                    uncertain.update(code for code in codes if rivers[source][code])
            elif not (meld.kind.startswith("gang") and len(codes) == 4 and len(set(codes)) == 1):
                uncertain.update(codes)

    result = []
    for code in TILE_ORDER:
        if meld_total[code] > 4:
            result.append(None)  # 多个副露已超过物理上限，不能用截断掩盖输入冲突。
        elif meld_total[code] == 4:
            # 明/暗/补杠都已展示四张。同码在多个副露中凑齐四张也没有未见牌；
            # 不依赖历史去猜杠种类，更不能把补杠当作第二次吃进弃牌。
            result.append(meld_total[code])
        elif code in uncertain or overlaps[code] > river_total[code]:
            result.append(None)
        else:
            result.append(counts[code] - overlaps[code])
    return tuple(result)
