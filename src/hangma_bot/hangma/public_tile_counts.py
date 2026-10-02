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
from dataclasses import dataclass, fields
from functools import lru_cache
from typing import Optional, Tuple

from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.observation import PlayerObservation, PublicEvent, PublicMeld

from .internal_types import TILE_ORDER
from .special_rules import is_passive_observation_event

PublicCounts34 = Tuple[Optional[int], ...]
"""按规范34种牌排列；None表示该牌种的公开计数因输入自相矛盾而无法确定。"""

UnseenCounts34 = Tuple[Optional[int], ...]
"""按规范34种牌排列；已知张数含本人暗牌、当前摸牌与全部去重公开牌。"""

_PHYSICAL_LIMIT = 4
_TOTAL_TILES = 136
"""136 张牌的全量：四家手牌 + 四家牌河 + 全部副露 + 牌墙剩余。"""

_CLAIM_HISTORY_CACHE_SIZE = 8
_CLAIM_HISTORY_EVENT_LIMIT = 4096
_PUBLIC_EVENT_FIELDS = tuple(field.name for field in fields(PublicEvent))


@dataclass(frozen=True, eq=False)
class _HistoryIdentity:
    """以不可变历史原件身份作常数时间键，并强持有原件以防对象编号复用。"""

    history: Tuple[PublicEvent, ...]

    def __hash__(self) -> int:
        return id(self.history)

    def __eq__(self, other) -> bool:
        return type(other) is _HistoryIdentity and self.history is other.history


class _MutableHistory(Exception):
    """非规范不可变输入不进入缓存；调用方仍按原逻辑解析，不拒绝输入。"""


def _immutable_event_field(value) -> bool:
    """只允许规范不可变值，排除带可变比较语义的容器或值对象子类。"""

    if value is None or type(value) in (bool, int, str):
        return True
    if type(value) is Tile:
        return type(value.code) is str
    if type(value) is tuple:
        return all(_immutable_event_field(item) for item in value)
    return False


@lru_cache(maxsize=_CLAIM_HISTORY_CACHE_SIZE)
def _cached_claim_proofs(identity: _HistoryIdentity, watermark: int):
    """最多保留八份历史的纯解析结果；LRU 自带并发维护保护。

    每份历史首次纳入时验证所有字段；命中后只比较 tuple 身份与实际官方
    水位，不再次散列或扫描事件。返回值全为不可变元组；不可变性不足时
    抛内部异常，LRU 不缓存异常，外层继续原解析路径。
    """

    history = identity.history
    if not all(type(event) is PublicEvent and all(
            _immutable_event_field(getattr(event, name)) for name in _PUBLIC_EVENT_FIELDS
    ) for event in history):
        raise _MutableHistory
    claims = _scan_claim_proofs(history, watermark)
    return (isinstance(claims, defaultdict),
            tuple((key, tuple(proofs)) for key, proofs in claims.items()))


@dataclass(frozen=True)
class PublicClaimEvidence:
    """某座位第 ``meld_index`` 个副露的领取证据，不承载官方序号。

    ``provenance`` 区分已见与给定事实；``feeder_seat`` 是供牌座位，
    ``claimed_tile`` 是被领取的那张牌。``retained_in_river`` 只在能证明
    这一次被领取的物理牌是否仍留河时填写；同码旧弃牌不能充当该证明。
    补杠沿用原碰的这份证据。
    """

    seat: int
    meld_index: int
    feeder_seat: int
    claimed_tile: Tile
    provenance: str
    retained_in_river: Optional[bool] = None

    def __post_init__(self) -> None:
        if self.seat not in range(4) or self.feeder_seat not in range(4):
            raise ValueError("领取证据座位须在 0—3")
        if self.meld_index < 0:
            raise ValueError("副露实例序号不能为负")
        if self.provenance not in ("observed", "assumed"):
            raise ValueError("领取证据来源须为 observed 或 assumed")
        if self.retained_in_river is not None and not isinstance(self.retained_in_river, bool):
            raise ValueError("领取牌留河证据须为布尔值或空")


@dataclass(frozen=True)
class PublicTileView:
    """单局公开牌视图；四座向量按座位 0—3，绝不承载他家暗牌。

    ``public_history`` 只含已见官方事件；两个水位都是官方序号，不能填条件
    分支的本地步号。``remaining_tile_count`` 是官方含保留区的墙余张数，
    缺证据时为空。给定条件分支应在推进公开事实后构造新视图。
    """

    discards: Tuple[Tuple[Tile, ...], ...]
    melds: Tuple[Tuple[PublicMeld, ...], ...]
    hand_counts: Tuple[int, int, int, int]
    remaining_tile_count: Optional[int]
    public_history: Tuple[PublicEvent, ...] = ()
    snapshot_seq: int = 0
    consumed_seq: Optional[int] = None
    claim_evidence: Tuple[PublicClaimEvidence, ...] = ()

    def __post_init__(self) -> None:
        if len(self.discards) != 4 or len(self.melds) != 4 or len(self.hand_counts) != 4:
            raise ValueError("公开牌视图须含座位 0—3 的四座向量")
        if self.snapshot_seq < 0 or (self.consumed_seq is not None
                                      and self.consumed_seq < self.snapshot_seq):
            raise ValueError("已见官方水位不得早于快照水位")
        for claim in self.claim_evidence:
            if claim.meld_index >= len(self.melds[claim.seat]):
                raise ValueError("领取证据须指向当前公开副露实例")


@dataclass(frozen=True)
class PublicTileCounts:
    """公开张数及逐牌码证据状态；顺序均为规范34牌。

    ``exact`` 可作为精确容量，``conservative`` 表示缺领取证据而未扣
    可能重叠的牌，``unknown`` 表示相互矛盾或物理超量。状态不是摸牌概率。
    """

    counts: PublicCounts34
    evidence: Tuple[str, ...]


@dataclass(frozen=True)
class ConditionalTileCounts:
    """条件分支的公开张数与未见容量；逐牌码状态对应规范34牌顺序。"""

    public: PublicCounts34
    unseen: UnseenCounts34
    evidence: Tuple[str, ...]


def public_view_from_observation(observation: PlayerObservation) -> PublicTileView:
    """只投影玩家观察中的公开事实，不复制本人暗牌或决策上下文。"""

    return PublicTileView(
        discards=observation.discards, melds=observation.melds,
        hand_counts=observation.hand_counts,
        remaining_tile_count=observation.remaining_tile_count,
        public_history=observation.public_history,
        snapshot_seq=observation.snapshot_seq,
        consumed_seq=observation.consumed_seq,
    )


def _conservation_excess(view: PublicTileView) -> Optional[int]:
    """牌张守恒读数：>0 表示本快照仍把被鸣牌留在牌河中；0 表示已被移除。

    只用公开可见的计数（四家手牌张数、牌河、副露、牌墙剩余），不涉及任何牌值或暗牌。
    官方未提供牌墙剩余时返回 None，调用方退回逐副露实证。
    """

    wall = view.remaining_tile_count
    if wall is None:
        return None
    hands = sum(view.hand_counts)
    river = sum(len(row) for row in view.discards)
    melds = sum(len(meld.tiles) for group in view.melds for meld in group)
    return hands + river + melds + int(wall) - _TOTAL_TILES


def _claim_proofs(view: PublicTileView):
    """按事件顺序收集鸣牌的供牌者证据，键为 (副露种类, 副露所有者, 排序后牌形)。

    每个键的值是按事件顺序排列的列表，元素为 (供牌者座位, 被领取牌码) 或 None；
    None 表示这次鸣牌没有可直接采信的供牌证据（缺史、配对不上或与明确领取牌冲突），
    调用方对这类实例一律不扣重叠。同一序号出现冲突记录、或事件序号回退时，
    无法分辨哪一份历史正确，沿用既有哲学：整体放弃证据（返回空表），不挑选有利的一份。
    """

    watermark = view.consumed_seq
    if watermark is None:
        watermark = view.snapshot_seq
    history = view.public_history
    # 条件公开分支共享完整历史，但河、副露、守恒读数及直接领取证据仍会改变。
    # 所以只缓存历史解析，绝不缓存公开计数、未见容量或对当前副露的匹配结果。
    if (type(history) is tuple and len(history) <= _CLAIM_HISTORY_EVENT_LIMIT
            and type(watermark) is int):
        try:
            was_defaultdict, frozen = _cached_claim_proofs(_HistoryIdentity(history), watermark)
        except _MutableHistory:
            pass
        else:
            # 下游会过滤并 pop；每次给独占字典和列表，不能消费缓存中的原证据。
            result = {key: list(proofs) for key, proofs in frozen}
            return defaultdict(list, result) if was_defaultdict else result
    return _scan_claim_proofs(history, watermark)


def _scan_claim_proofs(history, watermark):
    """逐事件解析公开领取证据；冲突、缺口及跨单局清理沿用原有语义。"""

    claims = defaultdict(list)
    seen = {}
    previous = None
    pending = None
    for event in history:
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


def _claim_vote(meld, proof, fixed_code, removed_regime, all_overlaps_retained, rivers,
                *, retained_in_river=None, strict=False):
    """把一次鸣牌折算成 (受影响牌种, 是否仍在河中)；无法判定时返回 None。

    None 表示「无证据」——调用方既不扣重叠，也不把它当作矛盾证据。
    牌张守恒若证明「本快照每个鸣牌的重叠都还在」，则对牌种唯一确定的副露
    （碰/明杠/补杠）直接按实证处理：这是守恒等式给出的证据，不是对供牌来源的猜测。
    """

    if proof is None:
        if fixed_code is not None and all_overlaps_retained and not strict:
            return (fixed_code, True)
        return None
    feeder, claimed = proof
    code = fixed_code if fixed_code is not None else claimed
    if code is None:
        return None
    if strict:
        if retained_in_river is not None:
            return (code, retained_in_river)
        if not removed_regime and not all_overlaps_retained:
            # 只有同码河牌而无物理身份凭据，在混合口径下不足以证明重叠。
            return None
    present = (not removed_regime) and rivers[feeder][code] > 0
    return (code, present)


def _count_public_tiles_from_view(view: PublicTileView, *, legacy_four_meld: bool) -> PublicTileCounts:
    """从公开视图和已见证据计算34牌张数，不读取任何暗牌。

    证据不足时沿用保守不扣重叠的计数，并逐牌码标为 ``conservative``；
    真冲突返回空计数及 ``unknown``。调用方不能把保守容量当成精确值。
    """

    rivers = [Counter(tile.code for tile in river) for river in view.discards]
    river_total = sum(rivers, Counter())
    meld_total = Counter(tile.code for group in view.melds for meld in group for tile in meld.tiles)
    counts = river_total + meld_total
    overlaps = Counter()
    uncertain = set()
    conservative = set()
    proofs = _claim_proofs(view)
    claims_by_instance = defaultdict(list)
    for claim in view.claim_evidence:
        claims_by_instance[(claim.seat, claim.meld_index)].append(claim)

    # 证据条数超过当前副露实例数时，无法确定哪一条对应哪一次鸣牌，整体不作数。
    for key in list(proofs):
        kind, seat, token = key
        instances = sum(
            1 for group in view.melds for meld in group
            if _claim_token(meld) == (kind, seat, token)
        )
        if len(proofs[key]) > instances:
            proofs[key] = []

    excess = _conservation_excess(view)
    removed_regime = excess == 0
    # 守恒等式：保留口径下每个「领取过弃牌」的副露恰好贡献 1 张重叠。
    claim_melds = sum(
        1 for group in view.melds for meld in group
        if _claim_token(meld) is not None or _is_inherited_claim(meld)
    )
    all_overlaps_retained = excess is not None and excess > 0 and excess == claim_melds
    votes = defaultdict(list)
    overlap_sources = Counter()

    for seat, group in enumerate(view.melds):
        for meld_index, meld in enumerate(group):
            codes = tuple(tile.code for tile in meld.tiles)
            key = _claim_token(meld)
            direct_claims = claims_by_instance.get((seat, meld_index), ())
            direct_proofs = {(claim.feeder_seat, claim.claimed_tile.code)
                             for claim in direct_claims}
            retention_votes = {claim.retained_in_river for claim in direct_claims
                               if claim.retained_in_river is not None}
            direct_conflict = (
                len(direct_proofs) > 1
                or len(retention_votes) > 1
                or (meld.seat != seat and (direct_claims or not legacy_four_meld))
                or any(claim.claimed_tile.code not in codes for claim in direct_claims)
                or (meld.from_seat is not None
                    and any(claim.feeder_seat != meld.from_seat for claim in direct_claims))
                or (direct_proofs and meld.kind == "chi"
                    and any(feeder != (meld.seat - 1) % 4 for feeder, _ in direct_proofs))
            )
            if direct_conflict:
                uncertain.update(codes)
                continue
            direct_proof = next(iter(direct_proofs)) if direct_proofs else None
            direct_retained = next(iter(retention_votes)) if retention_votes else None
            if not legacy_four_meld and direct_retained is not None:
                if (direct_retained and (direct_proof is None
                                         or rivers[direct_proof[0]][direct_proof[1]] == 0)
                        or direct_retained and removed_regime
                        or not direct_retained and all_overlaps_retained):
                    uncertain.update(codes)
                    continue
            if direct_proof is not None and key is None and not _is_inherited_claim(meld):
                uncertain.update(codes)
                continue
            if key is not None:
                claim_kind = key[0]
                fixed = None if claim_kind == "chi" else codes[0]
                if claim_kind == "chi" and meld.from_seat is not None and meld.from_seat != (meld.seat - 1) % 4:
                    # 吃只能来自上家；自带供牌者与规则不符即为输入矛盾，受影响牌种标空。
                    uncertain.update(codes)
                    continue
                proof = proofs[key].pop(0) if proofs.get(key) else None
                if direct_proof is not None:
                    if proof is not None and proof != direct_proof:
                        uncertain.update(codes)
                        continue
                    proof = direct_proof
                if proof is None and meld.from_seat is not None and claim_kind != "chi":
                    # 自带供牌者座位的观察（模拟/回放）可直接采用，无需事件配对。
                    proof = (meld.from_seat, codes[0])
                if (not legacy_four_meld and all_overlaps_retained and proof is not None
                        and rivers[proof[0]][proof[1]] == 0):
                    uncertain.add(proof[1])
                    continue
                vote = _claim_vote(
                    meld, proof, fixed, removed_regime, all_overlaps_retained, rivers,
                    retained_in_river=direct_retained, strict=not legacy_four_meld,
                )
                if vote is not None:
                    votes[vote[0]].append(vote[1])
                    if vote[1] and proof is not None:
                        overlap_sources[(proof[0], vote[0])] += 1
                elif not removed_regime and (not all_overlaps_retained or not legacy_four_meld):
                    # 被领取牌种未知的吃，三种组成牌都不能宣称容量精确。
                    conservative.update(codes if fixed is None else (fixed,))
            elif _is_inherited_claim(meld):
                # 补杠继承原碰在牌河里的那一次重叠；新口径下平台已把它移除，故只在
                # 守恒等式仍显示保留时才扣。
                inherited_proof = direct_proof
                if inherited_proof is None and meld.from_seat is not None:
                    inherited_proof = (meld.from_seat, codes[0])
                if inherited_proof is not None:
                    if (not legacy_four_meld and all_overlaps_retained
                            and rivers[inherited_proof[0]][codes[0]] == 0):
                        uncertain.add(codes[0])
                        continue
                    vote = _claim_vote(
                        meld, inherited_proof, codes[0], removed_regime,
                        all_overlaps_retained, rivers,
                        retained_in_river=direct_retained, strict=not legacy_four_meld,
                    )
                    if vote is not None:
                        votes[vote[0]].append(vote[1])
                        if vote[1]:
                            overlap_sources[(inherited_proof[0], vote[0])] += 1
                elif all_overlaps_retained and legacy_four_meld:
                    votes[codes[0]].append(True)
                elif not removed_regime:
                    conservative.add(codes[0])
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

    if not legacy_four_meld:
        for (feeder, code), overlap_count in overlap_sources.items():
            if overlap_count > rivers[feeder][code]:
                uncertain.add(code)

    result = []
    evidence = []
    for code in TILE_ORDER:
        if meld_total[code] > _PHYSICAL_LIMIT:
            result.append(None)  # 多个副露已超过物理上限，不能用截断掩盖输入冲突。
            evidence.append("unknown")
        elif meld_total[code] == _PHYSICAL_LIMIT:
            # 明/暗/补杠都已展示四张。同码在多个副露中凑齐四张也没有未见牌；
            # 不依赖历史去猜杠种类，更不能把补杠当作第二次吃进弃牌。
            # 只有逐次证明的重叠才能解释四张副露之外的同码河牌；吃副露中
            # “包含该牌码”不等于“领取了该牌码”。旧观察入口沿用历史兼容值。
            if (code in uncertain or (code in conservative and river_total[code] > 0)
                    or overlaps[code] != river_total[code]) and not legacy_four_meld:
                result.append(None)
                evidence.append("unknown")
            else:
                result.append(meld_total[code])
                evidence.append("exact")
        elif code in uncertain or overlaps[code] > river_total[code]:
            result.append(None)
            evidence.append("unknown")
        else:
            public_count = counts[code] - overlaps[code]
            if public_count > _PHYSICAL_LIMIT and not legacy_four_meld:
                result.append(None)
                evidence.append("unknown")
            else:
                result.append(public_count)
                evidence.append("conservative" if code in conservative else "exact")
    return PublicTileCounts(tuple(result), tuple(evidence))


def count_public_tiles_from_view(view: PublicTileView) -> PublicTileCounts:
    """计算条件分支公开计数及证据；明确的第五张公开牌标为空。"""

    return _count_public_tiles_from_view(view, legacy_four_meld=False)


def count_public_tiles(observation: PlayerObservation) -> PublicCounts34:
    """保留玩家观察入口的逐牌码结果；内部只向核心传公开事实。"""

    return _count_public_tiles_from_view(
        public_view_from_observation(observation), legacy_four_meld=True,
    ).counts


def count_unseen_tiles_from_view(
    view: PublicTileView, *, seat: int, concealed: Tuple[Tile, ...],
    drawn_tile: Optional[Tile], chain_piao: Optional[int] = 0,
) -> ConditionalTileCounts:
    """计算条件分支本人视角的未见容量，暗牌与单列摸牌各扣恰好一次。

    ``concealed`` 必须不含 ``drawn_tile``；他家暗牌没有输入位置。飘白次数
    缺失时白牌容量为空，避免把未记录的飘白当成零。输出是容量而非墙内概率。
    """

    return _count_unseen_tiles_from_view(
        view, seat=seat, concealed=concealed, drawn_tile=drawn_tile,
        chain_piao=chain_piao, legacy_four_meld=False,
    )


def _count_unseen_tiles_from_view(
    view: PublicTileView, *, seat: int, concealed: Tuple[Tile, ...],
    drawn_tile: Optional[Tile], chain_piao: Optional[int], legacy_four_meld: bool,
) -> ConditionalTileCounts:
    """复用逐牌码容量计算；旧观察入口保留四张副露的历史兼容语义。"""

    if seat not in range(4):
        raise ValueError("本人座位须在 0—3")
    hidden = Counter(tile.code for tile in concealed)
    if drawn_tile is not None:
        hidden[drawn_tile.code] += 1
    public = _count_public_tiles_from_view(view, legacy_four_meld=legacy_four_meld)
    own_visible_whites = sum(tile.code == "白" for tile in view.discards[seat])
    missing_chain_whites = (None if chain_piao is None else
                            max(0, chain_piao - own_visible_whites))
    unseen = []
    evidence = list(public.evidence)
    for index, code in enumerate(TILE_ORDER):
        public_count = public.counts[index]
        if public_count is None or (code == "白" and missing_chain_whites is None):
            unseen.append(None)
            evidence[index] = "unknown"
            continue
        known = hidden[code] + public_count + (missing_chain_whites if code == "白" else 0)
        if known < 0 or known > _PHYSICAL_LIMIT:
            unseen.append(None)
            evidence[index] = "unknown"
        else:
            unseen.append(_PHYSICAL_LIMIT - known)
    return ConditionalTileCounts(public.counts, tuple(unseen), tuple(evidence))


def count_unseen_tiles(observation: PlayerObservation) -> UnseenCounts34:
    """计算玩家视角逐牌码未知容量；当前摸牌恰好扣除一次。

    该函数供离线机会 oracle 与规则诊断共用，避免题库各自重建一套牌张
    守恒。它兼容官方 ``my_hand`` 已含单列摸牌和契约 ``my_hand`` 不含摸牌
    两种形态，归一化判据与规则引擎一致。公开牌先由
    :func:`count_public_tiles` 去重；任一牌码自相矛盾或已知张数超过四张时，
    该牌码返回 ``None``，不能截断为零冒充可计算。
    """

    concealed = list(observation.my_hand)
    drawn = observation.drawn_tile
    if drawn is not None:
        expected_with_drawn = 14 - 3 * len(observation.melds[observation.seat])
        if len(concealed) == expected_with_drawn:
            for index in range(len(concealed) - 1, -1, -1):
                if concealed[index].code == drawn.code:
                    del concealed[index]
                    break
            else:
                # 长度声称是官方“已含摸牌”形态，却找不到该摸牌；整个暗牌
                # 形状不可判定，不能猜它其实是契约形态。
                return (None,) * len(TILE_ORDER)
        concealed.append(drawn)

    return _count_unseen_tiles_from_view(
        public_view_from_observation(observation), seat=observation.seat,
        concealed=tuple(concealed), drawn_tile=None,
        chain_piao=observation.chain_piao or 0, legacy_four_meld=True,
    ).unseen
