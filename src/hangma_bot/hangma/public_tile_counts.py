"""四家公开牌去重；只读取当前单局玩家可见的牌河、副露和事件。

**2026-09-18 口径修订（重要）**：平台并非始终保留被鸣弃牌的牌河记录。

- 2026-09-10 之前的实测快照**保留**：同一张物理牌同时出现在供牌者的牌河数组与副露里，
  此时必须按同一张物理牌去重一次（v18 连续快照、v20 明杠快照均如此）。
- 2026-09-14 之后的实测快照**移除**：被吃/碰/明杠领走的那张牌不再出现在牌河数组里，
  此时再去重就会把公开张数少算 1（2026-09-17 本场 5246 处、33 个牌种）。
- 官方指南更新日志（v1—v34）**没有**这条变更的记录，因此不能按版本号分派。

所以本模块不再假设任一口径，改为「逐副露实证 + 牌张守恒守卫」：

1. 扣重叠的唯一条件是**该供牌被直接证明仍在供牌者牌河中**（当前权威快照原文）；
2. 供牌来源只采信两类强证据：官方 ``chi`` 事件的 ``claimed_tile``（报文原文给出），
   或「紧邻弃牌 → 鸣牌」的事件配对（官方事件序，中间只允许被动事件）；
3. **无证据不猜**：不扣、不伪造。方向落在保守侧——公开张数可能多算 1，使剩余张数少估 1；
   合法动作与胡牌分解不依赖这份估计（见 hangma/RULES_EVIDENCE.md）；
4. 只有输入自相矛盾时才返回 ``None``：同码副露超过物理上限、实证重叠数超过河中实存张数、
   同一牌种在同一快照内出现互相矛盾的实证；
5. **牌张守恒守卫**：``Σ手牌张数 + Σ牌河张数 + Σ副露张数 + 牌墙剩余`` 与 136 的差
   直接给出「本快照是否已移除被鸣牌」。判定为已移除（差为 0）时整批否决扣除，
   用来挡住「同一牌种被同一家弃了两次、其中一张被鸣」造成的误扣。

2026-09-14 口径变化与两代平台行为的证据链见 review/llm-guided-heuristic-route 之外的
review/test-tournament-20260917/probes/discard-river-accounting-evidence.md。

本模块只读玩家可见字段，不读取暗牌，不发起网络请求，不改写原始记录。
"""

from collections import Counter, defaultdict
from typing import Optional, Tuple

from hangma_bot.kernel.observation import PlayerObservation

from .internal_types import TILE_ORDER
from .special_rules import is_passive_observation_event

PublicCounts34 = Tuple[Optional[int], ...]
"""按规范34种牌排列；None表示该牌种的公开计数因输入自相矛盾而无法确定。"""

_PHYSICAL_LIMIT = 4
_TOTAL_TILES = 136
"""136 张牌的全量：四家手牌 + 四家牌河 + 全部副露 + 牌墙剩余。"""

def _conservation_excess(observation: PlayerObservation) -> Optional[int]:
    """牌张守恒读数：>0 表示本快照仍把被鸣牌留在牌河中；0 表示已被移除。

    只用公开可见的计数（四家手牌张数、牌河、副露、牌墙剩余），不涉及任何牌值或暗牌。
    官方未提供牌墙剩余时返回 None，调用方退回逐副露实证。
    """

    wall = observation.remaining_tile_count
    if wall is None:
        return None
    hands = sum(observation.hand_counts)
    river = sum(len(row) for row in observation.discards)
    melds = sum(len(meld.tiles) for group in observation.melds for meld in group)
    return hands + river + melds + int(wall) - _TOTAL_TILES


def _claim_proofs(observation: PlayerObservation):
    """按事件顺序收集鸣牌的供牌者证据，键为 (副露种类, 副露所有者, 排序后牌形)。

    每个键的值是按事件顺序排列的列表，元素为 (供牌者座位, 被领取牌码) 或 None；
    None 表示这次鸣牌没有可直接采信的供牌证据（缺史、配对不上或与明确领取牌冲突），
    调用方对这类实例一律不扣重叠。同一序号出现冲突记录、或事件序号回退时，
    无法分辨哪一份历史正确，沿用既有哲学：整体放弃证据（返回空表），不挑选有利的一份。
    """

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
                return {}
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
            if event.seat is None or len(shape) != 3:
                pending = None
                continue
            proof = None
            if event.claimed_tile is not None:
                explicit = ((event.seat - 1) % 4, event.claimed_tile.code)
                if pending is None or pending == explicit:
                    proof = explicit
            elif (pending is not None and pending[0] == (event.seat - 1) % 4
                    and pending[1] in shape):
                proof = pending
            claims[("chi", event.seat, shape)].append(proof)
            pending = None
        elif event.kind in ("peng", "gang"):
            # 碰/明杠事件只带被领取的那一张牌（官方 tile 字段），不带整组副露。
            codes = tuple(tile.code for tile in event.tiles)
            if event.kind == "peng":
                kind = "peng" if len(set(codes)) == 1 else None
            else:
                # 只有明杠领取他家弃牌；暗杠与补杠不领取新弃牌，也无牌河重叠可言。
                kind = "gang_ming" if event.detail_kind == "ming" and len(set(codes)) == 1 else None
            paired = pending  # 先取紧邻弃牌，再清空；顺序反了会让第二类证据永远为空。
            pending = None
            if kind is None or event.seat is None or not codes:
                continue
            code = codes[0]
            claims[(kind, event.seat, code)].append(_pending_proof(paired, code))
        elif not is_passive_observation_event(event):
            # 他家摸牌、其他鸣牌或未知事件均不能夹在一次弃牌与鸣牌之间。
            pending = None
    return claims


def _pending_proof(pending, code):
    """仅当紧邻的上一次弃牌就是同一张牌时，才承认这次鸣牌的供牌来源。"""

    if pending is not None and pending[1] == code:
        return (pending[0], code)
    return None


def _is_inherited_claim(meld) -> bool:
    """补杠：四张同码，牌河里的重叠来自它之前的碰，不在本副露重新领取。"""

    codes = tuple(tile.code for tile in meld.tiles)
    return meld.kind == "gang_bu" and len(codes) == 4 and len(set(codes)) == 1


def _claim_token(meld):
    """把一个副露折算成证据键；不是会领取弃牌的副露时返回 None。"""

    codes = tuple(tile.code for tile in meld.tiles)
    if meld.kind == "chi" and len(codes) == 3:
        return ("chi", meld.seat, tuple(sorted(codes)))
    if meld.kind in ("peng", "gang_ming") and len(set(codes)) == 1 and len(codes) in (3, 4):
        return (meld.kind, meld.seat, codes[0])
    return None


def _claim_vote(meld, proof, fixed_code, removed_regime, all_overlaps_retained, rivers):
    """把一次鸣牌折算成 (受影响牌种, 是否仍在河中)；无法判定时返回 None。

    None 表示「无证据」——调用方既不扣重叠，也不把它当作矛盾证据。
    牌张守恒若证明「本快照每个鸣牌的重叠都还在」，则对牌种唯一确定的副露
    （碰/明杠/补杠）直接按实证处理：这是守恒等式给出的证据，不是对供牌来源的猜测。
    """

    if proof is None:
        if fixed_code is not None and all_overlaps_retained:
            return (fixed_code, True)
        return None
    feeder, claimed = proof
    code = fixed_code if fixed_code is not None else claimed
    if code is None:
        return None
    present = (not removed_regime) and rivers[feeder][code] > 0
    return (code, present)


def count_public_tiles(observation: PlayerObservation) -> PublicCounts34:
    """给候选事实提供去重后的公开张数；仅在输入自相矛盾时把受影响牌种标为空。

    不补写原牌河、不读取暗牌；原公开副露中的各张物理牌互不重叠。
    返回值仅在规则模块内部流转，消费未知值时由逐候选边界显式降级。
    """

    rivers = [Counter(tile.code for tile in river) for river in observation.discards]
    river_total = sum(rivers, Counter())
    meld_total = Counter(tile.code for group in observation.melds for meld in group for tile in meld.tiles)
    counts = river_total + meld_total
    overlaps = Counter()
    uncertain = set()
    proofs = _claim_proofs(observation)

    # 证据条数超过当前副露实例数时，无法确定哪一条对应哪一次鸣牌，整体不作数。
    for key in list(proofs):
        kind, seat, token = key
        instances = sum(
            1 for group in observation.melds for meld in group
            if _claim_token(meld) == (kind, seat, token)
        )
        if len(proofs[key]) > instances:
            proofs[key] = []

    excess = _conservation_excess(observation)
    removed_regime = excess == 0
    # 守恒等式：保留口径下每个「领取过弃牌」的副露恰好贡献 1 张重叠。
    claim_melds = sum(
        1 for group in observation.melds for meld in group
        if _claim_token(meld) is not None or _is_inherited_claim(meld)
    )
    all_overlaps_retained = excess is not None and excess > 0 and excess == claim_melds
    votes = defaultdict(list)

    for group in observation.melds:
        for meld in group:
            codes = tuple(tile.code for tile in meld.tiles)
            key = _claim_token(meld)
            if key is not None:
                claim_kind = key[0]
                fixed = None if claim_kind == "chi" else codes[0]
                if claim_kind == "chi" and meld.from_seat is not None and meld.from_seat != (meld.seat - 1) % 4:
                    # 吃只能来自上家；自带供牌者与规则不符即为输入矛盾，受影响牌种标空。
                    uncertain.update(codes)
                    continue
                proof = proofs[key].pop(0) if proofs.get(key) else None
                if proof is None and meld.from_seat is not None and claim_kind != "chi":
                    # 自带供牌者座位的观察（模拟/回放）可直接采用，无需事件配对。
                    proof = (meld.from_seat, codes[0])
                vote = _claim_vote(meld, proof, fixed, removed_regime, all_overlaps_retained, rivers)
                if vote is not None:
                    votes[vote[0]].append(vote[1])
            elif _is_inherited_claim(meld):
                # 补杠继承原碰在牌河里的那一次重叠；新口径下平台已把它移除，故只在
                # 守恒等式仍显示保留时才扣。
                if all_overlaps_retained:
                    votes[codes[0]].append(True)
            elif not (meld.kind.startswith("gang") and len(set(codes)) == 1):
                # 未知副露种类：无法证明其是否领取弃牌，受影响牌种一律标空。
                uncertain.update(codes)

    for code, code_votes in votes.items():
        if len(set(code_votes)) > 1:
            # 同一牌种在同一快照内出现互相矛盾的实证：输入不可信，整体标空。
            uncertain.add(code)
            continue
        if code_votes[0]:
            overlaps[code] += len(code_votes)

    result = []
    for code in TILE_ORDER:
        if meld_total[code] > _PHYSICAL_LIMIT:
            result.append(None)  # 多个副露已超过物理上限，不能用截断掩盖输入冲突。
        elif meld_total[code] == _PHYSICAL_LIMIT:
            # 明/暗/补杠都已展示四张。同码在多个副露中凑齐四张也没有未见牌；
            # 不依赖历史去猜杠种类，更不能把补杠当作第二次吃进弃牌。
            result.append(meld_total[code])
        elif code in uncertain or overlaps[code] > river_total[code]:
            result.append(None)
        else:
            result.append(counts[code] - overlaps[code])
    return tuple(result)
