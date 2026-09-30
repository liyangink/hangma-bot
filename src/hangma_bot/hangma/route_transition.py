"""P2 条件转移的内部研究量具；只移动已知本人牌与复用规则生命周期。

本文件不判断动作合法性。调用者须传入同一观察的 ``RuleCandidate``；
响应动作是否最终获裁决、下一张牌和他家动作都保留为条件，不填假事实。
返回的机械状态不是 ``PlayerObservation``，不能直接当作官方快照计番。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from collections import Counter
from typing import Optional, Tuple

from hangma_bot.kernel.actions import (
    Action, Chi, Discard, Gang, GangKind, Hu, Pass, Peng, Tile, action_key,
)
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import (
    PlayerObservation, PublicDiscard, PublicEvent, PublicMeld,
)

from . import action_families, hand_analysis, progression, settlement
from .catch_play import analyze_catch_play
from .interface import RuleCandidate, RuleIssue, Settlement, ValueCoverage
from .internal_types import TILE_INDEX, WindowContext, is_wealth
from .observation_rules import enrich_observation
from .public_tile_counts import (
    PublicClaimEvidence, PublicTileView, UnseenCounts34, count_unseen_tiles_from_view,
    public_view_from_observation,
)
from .route_frontier import RouteGapKind


class ConditionalPhase(str, Enum):
    """机械状态的下一事件要求；不是官方 ``phase`` 字段。"""

    RESPONSE_RESOLUTION = "response_resolution"
    CLAIM_DISCARD = "claim_discard"
    NORMAL_DRAW = "normal_draw"
    REPLACEMENT_DRAW = "replacement_draw"
    DRAW_ACTION = "draw_action"
    PUBLIC_WAIT = "public_wait"
    TERMINAL = "terminal"


@dataclass(frozen=True)
class ConditionalIdentity:
    """本地条件分支身份；path 不是官方 seq，绝不写入公开事件水位。"""

    game_id: str
    round_no: int
    root_action_key: str
    path: Tuple[str, ...] = ()
    ruleset_version: Optional[str] = None  # 根规则实例身份；旧手工公开前缀可空

    def __post_init__(self) -> None:
        if self.ruleset_version is not None and not self.ruleset_version:
            raise ValueError("条件根规则版本不得为空串")

    def step(self, label: str) -> "ConditionalIdentity":
        if not label:
            raise ValueError("条件步骤标签不得为空")
        return replace(self, path=self.path + (label,))


@dataclass(frozen=True)
class ConditionalRouteState:
    """本人可见条件状态；暗牌只含本座，墙余单位为张，空值表示未知。"""

    concealed: Tuple[Tile, ...]
    meld_count: int
    phase: ConditionalPhase
    baotou: bool
    chain_count: int
    chain_piao: Optional[int]
    wall_remaining: Optional[int]
    drawn_tile: Optional[Tile] = None
    my_chi_count: int = 0
    my_peng_codes: Tuple[str, ...] = ()
    catch_restricted: bool = False
    last_draw_replacement: Optional[bool] = None
    unseen_capacities: Optional[UnseenCounts34] = None  # 根时点公开未见容量；34 牌规范序，非墙内概率
    unseen_evidence: Optional[Tuple[str, ...]] = None  # 每码 exact/conservative/unknown
    root_public_view: Optional[PublicTileView] = None  # 根时点已见公开事实，非后继权威快照
    public_view: Optional[PublicTileView] = None  # 当前条件公开事实；每个给定事件后重算容量
    catch_circle: Optional[progression.CatchPlayState] = None  # 当前条件圈主；未来未投影时为空
    identity: Optional[ConditionalIdentity] = None
    seat: Optional[int] = None
    dealer_seat: Optional[int] = None  # 根观察公开庄家，后续结算不可由调用方改写
    response_window: Optional[str] = None
    response_trigger: Optional[Tuple[int, Tile]] = None  # 座位、牌码；无本地伪 seq
    response_public_discard: Optional[PublicDiscard] = None  # 仅已有官方弃牌带原 seq
    expected_draw_seat: Optional[int] = None  # 已裁决下一普通摸牌座位，非牌墙预言
    expected_discard_seat: Optional[int] = None  # 已获吃碰或摸牌后应行动的他座
    expected_replacement_draw: bool = False  # 他座已给定杠后下一摸须为补牌
    other_draw_replacement: Optional[bool] = None  # 他座当前已摸来源：False普通/True杠补；None未摸或已被动作消费
    terminal_result: Optional[progression.HandResult] = None  # 已确认局末；四座积分顺序 0—3
    structural_only: bool = False  # 未裁决吃碰的预列弃牌分支，禁止作为已生效事件状态
    local_witness_only: bool = False  # 无完整公开事件前缀的旧一次摸牌见证
    claim_awarded: bool = False  # 吃碰成功条件需经给定裁决确认

    def __post_init__(self) -> None:
        if self.dealer_seat is not None and self.dealer_seat not in range(4):
            raise ValueError("条件状态庄家座位无效")
        if self.seat is not None and self.dealer_seat is None:
            raise ValueError("带本人座位的条件状态必须绑定根观察庄家")
        if self.chain_piao is not None and self.chain_piao > self.chain_count:
            raise ValueError("链内飘白数不能超过链动作数")
        if self.phase in (ConditionalPhase.NORMAL_DRAW, ConditionalPhase.REPLACEMENT_DRAW):
            if self.drawn_tile is not None:
                raise ValueError("待摸状态不能预填未来牌")
        if self.expected_replacement_draw and (
            self.phase is not ConditionalPhase.PUBLIC_WAIT
            or self.expected_draw_seat is None
            or self.expected_discard_seat is not None
        ):
            raise ValueError("他座杠补待摸必须有唯一待摸座位且不能已进入弃牌")
        if self.other_draw_replacement is not None and (
            type(self.other_draw_replacement) is not bool
            or self.phase is not ConditionalPhase.PUBLIC_WAIT
            or self.expected_discard_seat is None
            or self.expected_draw_seat is not None
            or self.expected_replacement_draw
        ):
            raise ValueError("他座已摸来源必须绑定唯一当前行动座位")
        if (self.phase is ConditionalPhase.TERMINAL) != (self.terminal_result is not None):
            raise ValueError("条件终局阶段和局末结果必须同时成立")
        if self.unseen_capacities is not None and len(self.unseen_capacities) != 34:
            raise ValueError("条件状态的未见容量必须按规范牌序含 34 项")
        if self.unseen_capacities is not None and any(
            value is not None and (type(value) is not int or value < 0 or value > 4)
            for value in self.unseen_capacities
        ):
            raise ValueError("条件状态的未见容量须为每码 0—4 张或未知")
        if self.unseen_evidence is not None and (
            len(self.unseen_evidence) != 34 or any(
                item not in ("exact", "conservative", "unknown")
                for item in self.unseen_evidence
            )
        ):
            raise ValueError("未见容量证据必须按规范牌序含 34 项状态")


@dataclass(frozen=True)
class ConditionalBranch:
    """一条确定动作分支；followup_key 仅用于吃碰后独立弃牌。"""

    state: ConditionalRouteState
    followup_key: Optional[str] = None
    followup_discard: Optional[str] = None


@dataclass(frozen=True)
class ConditionalRoot:
    """合法根的当前机械投影；未来待给定条件与已知故障分别记录。"""

    action_key: str
    branches: Tuple[ConditionalBranch, ...]
    settlement: Optional[Settlement] = None
    claim_state: Optional[ConditionalRouteState] = None
    proposal_state: Optional[ConditionalRouteState] = None  # 吃碰尚未获裁决，暗牌未移
    pending_condition: Optional[ConditionalPhase] = None  # 下一待给定事件，不表示机械故障或已认证闭包
    gap_kind: Optional[RouteGapKind] = None
    gap_kinds: Tuple[RouteGapKind, ...] = ()  # 双轴审计：机械与输入可同时缺失
    issues: Tuple[RuleIssue, ...] = ()


@dataclass(frozen=True)
class GivenDrawAnalysis:
    """给定本人摸牌后的合法动作与当前胡结算；分数按座位 0—3。"""

    source_state: ConditionalRouteState
    legal_candidates: Tuple[RuleCandidate, ...]
    immediate_settlement: Optional[Settlement]
    issues: Tuple[RuleIssue, ...] = ()
    local_witness_only: bool = False


@dataclass(frozen=True)
class GivenClaimAnalysis:
    """吃碰获裁决、尚未摸牌时的全部合法本人动作；胡按规则关闭。"""

    source_state: ConditionalRouteState
    legal_candidates: Tuple[RuleCandidate, ...]
    issues: Tuple[RuleIssue, ...] = ()


@dataclass(frozen=True)
class GivenResponseTransition:
    """完整选择集合的公开裁决；unready/blocked 不推进条件状态。"""

    resolution: progression.PublicResponseResolution
    state: ConditionalRouteState
    gap_kinds: Tuple[RouteGapKind, ...] = ()
    issues: Tuple[RuleIssue, ...] = ()


class _MissingObservationEvidence(ValueError):
    """当前观察确实缺少响应归属等必要公开字段。"""


def _remove(concealed: Tuple[Tile, ...], code: str, amount: int) -> Tuple[Tile, ...]:
    """只做物理移牌；动作合法性已由同次规则候选确认。"""

    removed = 0
    kept = []
    for tile in concealed:
        if tile.code == code and removed < amount:
            removed += 1
        else:
            kept.append(tile)
    if removed != amount:
        raise ValueError("条件转移的动作与本人暗牌矛盾: " + code)
    return tuple(kept)


def _replace_four(rows: tuple, seat: int, value) -> tuple:
    updated = list(rows)
    updated[seat] = value
    return tuple(updated)


def _append_discard(view: PublicTileView, seat: int, tile: Tile) -> PublicTileView:
    """给定弃牌已生效：只写公开河与四座剩余手牌数，不制造事件序号。"""

    if view.hand_counts[seat] <= 0:
        raise ValueError("公开手牌数不足以执行弃牌")
    return replace(
        view,
        discards=_replace_four(view.discards, seat, view.discards[seat] + (tile,)),
        hand_counts=_replace_four(view.hand_counts, seat, view.hand_counts[seat] - 1),
    )


def _refresh_public(state: ConditionalRouteState, view: PublicTileView) -> ConditionalRouteState:
    """按当前公开视图与本人现有暗牌重算每码容量，绝不复用根时点数值。"""

    if state.seat is None:
        raise ValueError("条件状态缺本人座位，不能重算公开容量")
    counts = count_unseen_tiles_from_view(
        view, seat=state.seat, concealed=state.concealed,
        drawn_tile=None, chain_piao=state.chain_piao,
    )
    return replace(
        state, public_view=view,
        unseen_capacities=counts.unseen,
        unseen_evidence=counts.evidence,
    )


def _claim_public_view(
    view: PublicTileView, *, claimant: int, action: Action,
    feeder: int, tile: Tile, retained_in_river: bool,
) -> PublicTileView:
    """把获裁决鸣牌写入条件公开视图；河留/移须显式给定。"""

    if not view.discards[feeder] or view.discards[feeder][-1] != tile:
        raise ValueError("触发弃牌不在供牌者当前牌河末项")
    if isinstance(action, Chi):
        kind, tiles, taken = "chi", action.tiles, 2
    elif isinstance(action, Peng):
        kind, tiles, taken = "peng", (tile,) * 3, 2
    elif isinstance(action, Gang) and action.kind is GangKind.EXPOSED:
        kind, tiles, taken = "gang_ming", (tile,) * 4, 3
    else:
        raise ValueError("公开裁决没有可应用的鸣牌动作")
    if view.hand_counts[claimant] < taken:
        raise ValueError("公开手牌数不足以完成鸣牌")
    rivers = view.discards
    if not retained_in_river:
        rivers = _replace_four(rivers, feeder, rivers[feeder][:-1])
    old_melds = view.melds[claimant]
    meld = PublicMeld(claimant, kind, tuple(tiles), feeder)
    return replace(
        view,
        discards=rivers,
        melds=_replace_four(view.melds, claimant, old_melds + (meld,)),
        hand_counts=_replace_four(
            view.hand_counts, claimant, view.hand_counts[claimant] - taken),
        claim_evidence=view.claim_evidence + (
            PublicClaimEvidence(
                claimant, len(old_melds), feeder, tile, "assumed",
                retained_in_river=retained_in_river),
        ),
    )


def _seat_gang_public_view(
    view: PublicTileView, seat: int, action: Gang,
) -> PublicTileView:
    """已执行暗杠/补杠的公开副露；补杠保留原碰供牌归属。"""

    if action.kind is GangKind.EXPOSED:
        raise ValueError("明杠必须经公开响应裁决入口")
    amount = 4 if action.kind is GangKind.CONCEALED else 1
    if view.hand_counts[seat] < amount:
        raise ValueError("公开手牌数不足以执行杠")
    melds = list(view.melds[seat])
    if action.kind is GangKind.CONCEALED:
        melds.append(PublicMeld(
            seat, "gang_an", (action.tile,) * 4, None))
    else:
        matching = [index for index, meld in enumerate(melds)
                    if meld.kind.startswith("peng")
                    and meld.tiles[0].code == action.tile.code]
        if len(matching) != 1:
            raise ValueError("补杠缺唯一原碰副露")
        index = matching[0]
        old = melds[index]
        melds[index] = PublicMeld(
            seat, "gang_bu", (action.tile,) * 4, old.from_seat)
    return replace(
        view, melds=_replace_four(view.melds, seat, tuple(melds)),
        hand_counts=_replace_four(
            view.hand_counts, seat, view.hand_counts[seat] - amount),
    )


def _other_claim_capacity_gap(
    state: ConditionalRouteState, action: Action, claimed_tile: Tile,
) -> Optional[str]:
    """他座鸣牌所需暗牌只作公开容量守卫；不读取或构造他家暗牌。"""

    if isinstance(action, Chi):
        needed = Counter(tile.code for tile in action.tiles)
        needed[claimed_tile.code] -= 1
    elif isinstance(action, Peng):
        needed = Counter({claimed_tile.code: 2})
    elif isinstance(action, Gang) and action.kind is GangKind.EXPOSED:
        needed = Counter({claimed_tile.code: 3})
    else:
        raise ValueError("他座获裁决动作没有公开容量核验口径")
    if state.unseen_capacities is None or state.unseen_evidence is None:
        return "他座鸣牌缺逐码公开容量证据"
    for code, amount in needed.items():
        if amount <= 0:
            continue
        index = TILE_INDEX[code]
        if state.unseen_evidence[index] != "exact":
            return "他座鸣牌所需牌码公开容量证据不精确: " + code
        capacity = state.unseen_capacities[index]
        if capacity is None:
            return "他座鸣牌所需牌码公开容量未知: " + code
        if capacity < amount:
            raise ValueError("他座鸣牌与已知公开容量冲突: " + code)
    return None


def advance_given_response(
    root: ConditionalRoot, *, window: str, discard_seat: int,
    discarded_tile: Tile, responding: Tuple[int, ...],
    choices: Tuple[Tuple[int, Action], ...],
    retained_in_river: Optional[bool] = None,
) -> GivenResponseTransition:
    """给定完整响应选择后调用公开裁决；只在获裁决时生效鸣牌。

    输入是已列入同次合法表的根与明示选择，不查询他家暗牌。鸣牌
    后牌河留/移由调用者给定，绝不按版本猜测；条件路径只添本地标签，
    ``PublicTileView.snapshot_seq/consumed_seq`` 保持原官方水位。
    """

    base = root.proposal_state or (root.branches[0].state if root.branches else None)
    if base is None or base.public_view is None or base.catch_circle is None:
        raise ValueError("响应根缺当前公开视图或圈主证据")
    if base.structural_only:
        raise ValueError("未裁决吃碰的预列弃牌分支仅供结构诊断")
    if base.response_trigger != (discard_seat, discarded_tile):
        raise ValueError("给定响应与根的触发弃牌不一致")
    if base.response_window is not None and base.response_window != window:
        raise ValueError("给定响应窗口与根窗口不一致")
    if base.seat is None or base.identity is None:
        raise ValueError("响应根缺本人座位或本地条件身份")
    if base.seat in responding and root.proposal_state is not None:
        own_choice = next((action for seat, action in choices if seat == base.seat), None)
        if own_choice is not None and action_key(own_choice) != root.action_key:
            raise ValueError("给定本人响应选择与合法根动作键不一致")
    resolution = progression.resolve_public_response(
        window, discard_seat, discarded_tile, responding, choices, base.catch_circle)
    if resolution.status == "unready":
        return GivenResponseTransition(
            resolution, base, (RouteGapKind.INPUT_EVIDENCE_GAP,),
            (RuleIssue("route_transition.response_input",
                       resolution.reason or "响应选择或圈主证据不足"),),
        )
    if resolution.status == "blocked":
        return GivenResponseTransition(
            resolution, base, (),
            (RuleIssue("route_transition.response_blocked",
                       resolution.reason or "多人响应裁决缺官方优先级"),),
        )
    view = base.public_view
    if resolution.claim_action is not None:
        if resolution.claim_seat != base.seat:
            gap = _other_claim_capacity_gap(
                base, resolution.claim_action, discarded_tile)
            if gap is not None:
                return GivenResponseTransition(
                    progression.PublicResponseResolution("unready", reason=gap),
                    base, (RouteGapKind.INPUT_EVIDENCE_GAP,),
                    (RuleIssue("route_transition.other_claim_capacity", gap),))
        if retained_in_river is None:
            return GivenResponseTransition(
                progression.PublicResponseResolution(
                    "unready", reason="鸣牌后牌河留存口径未给定"),
                base, (RouteGapKind.INPUT_EVIDENCE_GAP,),
                (RuleIssue("route_transition.public_river",
                           "鸣牌后须给定被领弃牌留河或移河的公开事实"),),
            )
        view = _claim_public_view(
            view, claimant=resolution.claim_seat,
            action=resolution.claim_action,
            feeder=discard_seat, tile=discarded_tile,
            retained_in_river=retained_in_river,
        )
    if resolution.claim_seat == base.seat:
        if root.claim_state is not None:
            state = root.claim_state
        elif root.branches and isinstance(resolution.claim_action, Gang):
            state = root.branches[0].state
        else:
            raise ValueError("本人鸣牌获裁决但根缺成功条件状态")
    else:
        state = base
    if resolution.next_window == "response_chi":
        phase = ConditionalPhase.RESPONSE_RESOLUTION
    elif resolution.claim_seat == base.seat and isinstance(resolution.claim_action, (Chi, Peng)):
        phase = ConditionalPhase.CLAIM_DISCARD
    elif resolution.claim_seat == base.seat and isinstance(resolution.claim_action, Gang):
        phase = ConditionalPhase.REPLACEMENT_DRAW
    elif resolution.next_draw_seat == base.seat:
        phase = ConditionalPhase.NORMAL_DRAW
    else:
        phase = ConditionalPhase.PUBLIC_WAIT
    state = replace(
        state, phase=phase,
        structural_only=False,
        claim_awarded=(resolution.claim_seat == base.seat),
        identity=state.identity.step("response:" + window + ":resolved"),
        response_window=("response_chi" if resolution.next_window == "response_chi" else None),
        response_trigger=(
            (discard_seat, discarded_tile)
            if resolution.next_window == "response_chi" else None),
        response_public_discard=(
            state.response_public_discard
            if resolution.next_window == "response_chi" else None),
        expected_draw_seat=(
            resolution.claim_seat
            if phase is ConditionalPhase.PUBLIC_WAIT
            and isinstance(resolution.claim_action, Gang)
            else (resolution.next_draw_seat if phase in (
                ConditionalPhase.NORMAL_DRAW, ConditionalPhase.PUBLIC_WAIT) else None)),
        expected_discard_seat=(
            resolution.claim_seat
            if phase is ConditionalPhase.PUBLIC_WAIT
            and isinstance(resolution.claim_action, (Chi, Peng)) else None),
        expected_replacement_draw=(
            phase is ConditionalPhase.PUBLIC_WAIT
            and isinstance(resolution.claim_action, Gang)),
        other_draw_replacement=None,
    )
    state = _refresh_public(state, view)
    return GivenResponseTransition(resolution, state)


def _successful_claim_from_state(
    state: ConditionalRouteState, action: Action, claimed_tile: Tile,
) -> ConditionalRouteState:
    """只为经同源动作族确认的本人鸣牌建立成功条件状态。"""

    if isinstance(action, Chi):
        required = tuple(tile.code for tile in action.tiles
                         if tile.code != claimed_tile.code)
        if len(required) != 2:
            raise ValueError("吃牌组合与当前触发弃牌矛盾")
    elif isinstance(action, Peng):
        required = (action.tile.code,) * 2
    elif isinstance(action, Gang) and action.kind is GangKind.EXPOSED:
        required = (action.tile.code,) * 3
    else:
        raise ValueError("给定响应没有可执行的本人鸣牌")
    hand = state.concealed
    for code in required:
        hand = _remove(hand, code, 1)
    count, piao = progression.chain_after_action(
        state.chain_count, state.chain_piao, state.baotou, action)
    baotou = progression.baotou_after_action(
        state.baotou, action, state.concealed, state.meld_count)
    if baotou is None:
        raise ValueError("鸣牌后爆头状态无法确定")
    return replace(
        state, concealed=hand, meld_count=state.meld_count + 1,
        phase=(ConditionalPhase.REPLACEMENT_DRAW
               if isinstance(action, Gang) else ConditionalPhase.CLAIM_DISCARD),
        baotou=baotou, chain_count=count, chain_piao=piao,
        my_chi_count=state.my_chi_count + int(isinstance(action, Chi)),
        my_peng_codes=(state.my_peng_codes + (action.tile.code,)
                       if isinstance(action, Peng) else state.my_peng_codes),
        identity=state.identity.step("claim-success") if state.identity else None,
    )


def advance_response_state(
    state: ConditionalRouteState, *, window: str, discard_seat: int,
    discarded_tile: Tile, responding: Tuple[int, ...],
    choices: Tuple[Tuple[int, Action], ...],
    retained_in_river: Optional[bool] = None,
) -> GivenResponseTransition:
    """从上一步条件状态继续下一个响应窗，绝不回到根时点视图。"""

    if state.phase is not ConditionalPhase.RESPONSE_RESOLUTION:
        raise ValueError("当前条件状态不是待裁决响应窗口")
    if ((state.response_window is not None and state.response_window != window)
            or state.response_trigger != (discard_seat, discarded_tile)):
        raise ValueError("后续响应窗口或触发弃牌与当前条件状态不一致")
    if state.seat is None:
        raise ValueError("后续响应状态缺本人座位")
    own_choice = next((action for seat, action in choices if seat == state.seat), None)
    success = None
    key = "external-response"
    if own_choice is not None:
        context = WindowContext(
            seat=state.seat, phase=window, turn_seat=discard_seat,
            responding_seats=responding, hand_tiles=state.concealed,
            drawn_tile=None, my_chi_count=state.my_chi_count,
            my_peng_codes=state.my_peng_codes,
            last_discard=state.response_public_discard,
            catch_play=state.catch_circle.active and state.catch_circle.owner != state.seat,
            remaining_tile_count=state.wall_remaining,
            conditional_discard=(
                state.response_trigger
                if state.response_public_discard is None else None),
        )
        outcome = action_families.generate_candidates(context, None)
        key = action_key(own_choice)
        if key not in {candidate.action_key for candidate in outcome.candidates}:
            raise ValueError("后续本人响应不在同源动作族合法候选中")
        if isinstance(own_choice, (Chi, Peng, Gang)):
            success = _successful_claim_from_state(state, own_choice, discarded_tile)
    conditional_root = ConditionalRoot(
        key, (), claim_state=success, proposal_state=state)
    return advance_given_response(
        conditional_root, window=window, discard_seat=discard_seat,
        discarded_tile=discarded_tile, responding=responding,
        choices=choices, retained_in_river=retained_in_river)


def advance_given_other_draw(
    state: ConditionalRouteState, *, seat: int, replacement: bool = False,
) -> ConditionalRouteState:
    """给定他座普通摸或杠补已发生；只更新公开张数，不填其暗牌值。"""

    if state.phase is not ConditionalPhase.PUBLIC_WAIT:
        raise ValueError("他座摸牌只能接在公开等待状态之后")
    if state.seat is None or state.public_view is None or state.identity is None:
        raise ValueError("条件状态缺公开视图、本人座位或身份")
    if seat not in range(4) or seat == state.seat:
        raise ValueError("给定他座摸牌座位无效")
    if state.expected_draw_seat != seat:
        raise ValueError("给定他座摸牌与已裁决的下一摸座位不一致")
    if replacement is not state.expected_replacement_draw:
        raise ValueError("给定他座摸牌来源与待摸阶段不一致")
    if (state.wall_remaining is None
            or state.wall_remaining <= action_families.WALL_RESERVE_TILES):
        raise ValueError("缺可摸墙余或已进入保留区")
    view = state.public_view
    if view.remaining_tile_count != state.wall_remaining:
        raise ValueError("条件视图墙余与状态不一致")
    view = replace(
        view,
        hand_counts=_replace_four(view.hand_counts, seat, view.hand_counts[seat] + 1),
        remaining_tile_count=state.wall_remaining - 1,
    )
    next_state = replace(
        state, wall_remaining=state.wall_remaining - 1,
        expected_draw_seat=None, expected_discard_seat=seat,
        expected_replacement_draw=False,
        other_draw_replacement=replacement,
        identity=state.identity.step(
            ("other-replacement-draw:" if replacement else "other-draw:")
            + str(seat)),
    )
    return _refresh_public(next_state, view)


def advance_given_other_gang(
    state: ConditionalRouteState, *, seat: int, action: Gang,
) -> ConditionalRouteState:
    """给定他座已发生的暗杠/补杠公开事件，保留其暗牌内容未知。"""

    if state.phase is not ConditionalPhase.PUBLIC_WAIT:
        raise ValueError("他座杠只能接在公开等待状态之后")
    if state.seat is None or state.public_view is None or state.identity is None:
        raise ValueError("条件状态缺公开视图、本人座位或身份")
    if seat not in range(4) or seat == state.seat or state.expected_discard_seat != seat:
        raise ValueError("他座杠与已裁决当前行动座位不一致")
    if action.kind not in (GangKind.CONCEALED, GangKind.ADDED) or is_wealth(action.tile):
        raise ValueError("他座公开杠事件只接受非白暗杠或补杠")
    if state.catch_circle is None:
        raise ValueError("他座杠缺抓打圈主证据")
    if (action.kind is GangKind.ADDED and state.catch_circle.active
            and state.catch_circle.owner != seat):
        raise ValueError("抓打圈内受限他座不能补杠")
    if (state.wall_remaining is None
            or state.wall_remaining <= action_families.WALL_RESERVE_TILES):
        raise ValueError("缺可杠墙余或已进入保留区")
    amount = 4 if action.kind is GangKind.CONCEALED else 1
    index = TILE_INDEX[action.tile.code]
    if (state.unseen_capacities is None or state.unseen_evidence is None
            or state.unseen_evidence[index] != "exact"):
        raise ValueError("他座杠所需牌码的公开容量证据不精确")
    capacity = state.unseen_capacities[index]
    if capacity is None or capacity < amount:
        raise ValueError("他座杠与已知公开容量冲突")
    if state.public_view.remaining_tile_count != state.wall_remaining:
        raise ValueError("条件视图墙余与状态不一致")
    view = _seat_gang_public_view(state.public_view, seat, action)
    next_state = replace(
        state, expected_discard_seat=None, expected_draw_seat=seat,
        expected_replacement_draw=True,
        other_draw_replacement=None,
        identity=state.identity.step("other-gang:" + str(seat) + ":" + action_key(action)),
    )
    return _refresh_public(next_state, view)


def finish_given_exhaustive_draw(state: ConditionalRouteState) -> ConditionalRouteState:
    """响应已裁决且下一普通摸牌因可摸区耗尽而流局，不预结束响应窗。"""

    if state.public_view is None or state.identity is None:
        raise ValueError("流局条件状态缺公开视图或本地身份")
    if state.phase not in (ConditionalPhase.NORMAL_DRAW, ConditionalPhase.PUBLIC_WAIT):
        raise ValueError("流局只能接已裁决的下一普通摸牌请求")
    if (state.expected_draw_seat is None or state.expected_discard_seat is not None
            or state.expected_replacement_draw):
        raise ValueError("流局仍有未完成动作或杠补摸请求")
    if state.wall_remaining != action_families.WALL_RESERVE_TILES:
        raise ValueError("可摸区边界不是精确保留张数")
    if state.public_view.remaining_tile_count != state.wall_remaining:
        raise ValueError("条件视图墙余与流局状态不一致")
    return replace(
        state, phase=ConditionalPhase.TERMINAL,
        expected_draw_seat=None, terminal_result=progression.exhaustive_draw_result(),
        identity=state.identity.step("exhaustive-draw"),
    )


def finish_given_official_other_win(
    state: ConditionalRouteState, event: PublicEvent, *,
    game_id: str, round_no: int,
) -> ConditionalRouteState:
    """给定他座自摸胡的已公开官方结果，终止条件链而不复算其暗牌。

    只消费当前应行动他座的完整 ``round_ended``；官方番数与四座增量
    是赛后/事件已公开事实，不作为动作前的预测标签。保留根快照水位。
    """

    if (state.phase is not ConditionalPhase.PUBLIC_WAIT
            or state.seat is None or state.identity is None
            or state.public_view is None):
        raise ValueError("他座胡缺已给定的公开行动状态")
    if (state.identity.game_id != game_id
            or state.identity.round_no != round_no):
        raise ValueError("他座胡事件身份与条件单局不一致")
    if (state.expected_discard_seat is None
            or state.expected_draw_seat is not None
            or state.expected_replacement_draw
            or state.other_draw_replacement is None):
        raise ValueError("他座胡尚未到合法的已摸牌行动点")
    if (event.kind != "round_ended" or event.result_draw is not False
            or event.seat != state.expected_discard_seat
            or event.seat == state.seat):
        raise ValueError("公开终局不是当前行动他座的自摸胡")
    if (event.result_fan is None or event.result_details is None
            or event.result_scores is None):
        raise ValueError("他座胡的官方番数、明细或四座积分缺失")
    official_watermark = (state.public_view.consumed_seq
                          if state.public_view.consumed_seq is not None
                          else state.public_view.snapshot_seq)
    if event.seq <= official_watermark:
        raise ValueError("他座胡事件不晚于条件根已消费官方水位")
    return replace(
        state, phase=ConditionalPhase.TERMINAL,
        expected_discard_seat=None,
        other_draw_replacement=None,
        terminal_result=progression.HandResult(
            winner_seat=event.seat, is_draw=False,
            fan=event.result_fan, details=event.result_details,
            score_delta=event.result_scores),
        identity=state.identity.step("official-other-hu:" + str(event.seat)),
    )


def advance_given_other_discard(
    state: ConditionalRouteState, *, seat: int, tile: Tile,
) -> ConditionalRouteState:
    """给定他座弃牌已发生，更新河、逐码容量及圈主并开启响应裁决。"""

    if state.phase is not ConditionalPhase.PUBLIC_WAIT:
        raise ValueError("他座弃牌只能接在公开等待状态之后")
    if state.seat is None or state.public_view is None or state.identity is None:
        raise ValueError("条件状态缺公开视图、本人座位或身份")
    if seat not in range(4) or seat == state.seat:
        raise ValueError("给定他座弃牌座位无效")
    if state.expected_discard_seat != seat:
        raise ValueError("给定他座弃牌与已裁决的当前行动座位不一致")
    if state.catch_circle is None:
        raise ValueError("条件状态缺抓打圈主证据")
    index = TILE_INDEX[tile.code]
    if sum(own.code == tile.code for own in state.concealed) == 4:
        raise ValueError("本人暗牌已持同码四张，他座弃牌与物理上限冲突")
    if (state.unseen_evidence is not None
            and state.unseen_evidence[index] == "exact"
            and state.unseen_capacities is not None
            and state.unseen_capacities[index] == 0):
        raise ValueError("给定他座弃牌码公开未见容量为零")
    circle = progression.catch_play_after_discard(state.catch_circle, seat, tile)
    next_seat = (seat + 1) % 4
    # 他座弃白不经过吃碰窗口；下一座若正是本人，就已到本人普通摸牌点。
    if is_wealth(tile):
        phase = (ConditionalPhase.NORMAL_DRAW if next_seat == state.seat
                 else ConditionalPhase.PUBLIC_WAIT)
    else:
        phase = ConditionalPhase.RESPONSE_RESOLUTION
    next_state = replace(
        state, phase=phase,
        catch_circle=circle,
        catch_restricted=circle.active and circle.owner != state.seat,
        response_window=None if is_wealth(tile) else "response_peng",
        response_trigger=None if is_wealth(tile) else (seat, tile),
        response_public_discard=None,
        expected_draw_seat=(next_seat if is_wealth(tile) else None),
        expected_discard_seat=None,
        other_draw_replacement=None,
        identity=state.identity.step("other-discard:" + str(seat) + ":" + tile.code),
    )
    return _refresh_public(next_state, _append_discard(state.public_view, seat, tile))


def _state(
    observation: PlayerObservation, context: WindowContext, phase: ConditionalPhase,
    *, concealed: Optional[Tuple[Tile, ...]] = None, meld_count: Optional[int] = None,
    action=None,
) -> ConditionalRouteState:
    hand = context.full_hand() if concealed is None else concealed
    count, piao = progression.chain_after_action(
        observation.rule_state.chain_count, observation.chain_piao,
        observation.rule_state.baotou, action,
    ) if action is not None else (observation.rule_state.chain_count, observation.chain_piao)
    baotou = progression.baotou_after_action(
        observation.rule_state.baotou, action, context.full_hand(),
        len(observation.melds[observation.seat]),
    ) if action is not None else observation.rule_state.baotou
    if baotou is None:
        raise ValueError("动作后爆头无法由当前观察确定")
    public_view = public_view_from_observation(observation)
    tile_counts = count_unseen_tiles_from_view(
        public_view, seat=observation.seat,
        concealed=context.hand_tiles, drawn_tile=context.drawn_tile,
        chain_piao=observation.chain_piao,
    )
    circle_fact = analyze_catch_play(observation)
    circle = progression.CatchPlayState(circle_fact.active, circle_fact.owner_seat)
    if isinstance(action, Discard):
        circle = progression.catch_play_after_discard(circle, observation.seat, action.tile)
    return ConditionalRouteState(
        concealed=hand, meld_count=(len(observation.melds[observation.seat])
                                     if meld_count is None else meld_count),
        phase=phase, baotou=baotou, chain_count=count, chain_piao=piao,
        wall_remaining=observation.remaining_tile_count,
        my_chi_count=context.my_chi_count,
        my_peng_codes=context.my_peng_codes,
        catch_restricted=circle.active and circle.owner != observation.seat,
        unseen_capacities=tile_counts.unseen,
        unseen_evidence=tile_counts.evidence,
        root_public_view=public_view,
        public_view=public_view,
        catch_circle=circle,
        seat=observation.seat,
        dealer_seat=observation.dealer_seat,
        response_window=(
            observation.phase if observation.phase.startswith("response_") else
            ("response_peng" if isinstance(action, Discard)
             and not is_wealth(action.tile) else None)),
        response_trigger=(
            (observation.seat, action.tile) if isinstance(action, Discard) else
            ((observation.last_discard.seat, observation.last_discard.tile)
             if observation.last_discard is not None else None)
        ),
        response_public_discard=(
            observation.last_discard
            if observation.phase.startswith("response_") else None),
        expected_draw_seat=(
            (observation.seat + 1) % 4
            if isinstance(action, Discard) and is_wealth(action.tile) else None),
    )


def project_legal_roots(
    observation: PlayerObservation,
    context: WindowContext,
    candidates: Tuple[RuleCandidate, ...],
    *, config: RuleConfig,
) -> Tuple[ConditionalRoot, ...]:
    """保留同次全部合法根和吃碰后的全部弃牌，不择优、不推断裁决。

    ``context`` 须由规则模块从 ``observation`` 生成；此入口和
    ``HangmaRules.analyze`` 使用同一可见事实富集，避免同批合法候选
    与裸快照的链内飘白/杠补来源不同步。富集不改手牌或官方序号，
    因而不重建官方归一化手牌。杠根只到待补牌，胡根仅使用已有结算事实。
    不能形成状态时仍保留根并标明机械或输入证据缺口。
    """

    observation = enrich_observation(observation)
    if config.base_score != 1 or config.you_cai_bi_kao:
        raise ValueError("条件转移首版只绑定 BaseScore=1、YouCaiBiKao=false")
    if len({item.action_key for item in candidates}) != len(candidates):
        raise ValueError("同次合法候选出现重复动作键")
    roots = []
    for candidate in candidates:
        action = candidate.action
        try:
            if isinstance(action, Hu):
                settlement = (candidate.value_facts.immediate_settlement
                              if candidate.value_facts is not None else None)
                if settlement is None:
                    facts = candidate.value_facts
                    kind = (
                        RouteGapKind.SEARCH_TRUNCATED
                        if facts is not None and facts.coverage is ValueCoverage.PARTIAL
                        else RouteGapKind.INPUT_EVIDENCE_GAP
                        if facts is not None and any(
                            issue.area == "value_analysis.missing_evidence"
                            for issue in facts.issues)
                        else RouteGapKind.MECHANICAL_GAP)
                    roots.append(ConditionalRoot(candidate.action_key, (),
                        gap_kind=kind,
                        issues=(RuleIssue("route_transition.settlement",
                                          "合法胡缺当前结算事实；来源: " +
                                          "; ".join(issue.reason for issue in facts.issues)
                                          if facts is not None and facts.issues
                                          else "合法胡缺当前结算事实"),)))
                    continue
                current = replace(
                    _state(observation, context, ConditionalPhase.DRAW_ACTION),
                    identity=ConditionalIdentity(
                        observation.game_id, observation.round_no,
                        candidate.action_key,
                        ruleset_version=config.ruleset_version))
                ended = _terminal_hu_state(current, settlement)
                roots.append(ConditionalRoot(
                    candidate.action_key, (ConditionalBranch(ended),), settlement))
                continue
            if isinstance(action, Pass):
                state = _state(observation, context, ConditionalPhase.RESPONSE_RESOLUTION,
                               concealed=context.full_hand(), action=action)
                roots.append(ConditionalRoot(candidate.action_key, (ConditionalBranch(state),),
                    proposal_state=state,
                    pending_condition=ConditionalPhase.RESPONSE_RESOLUTION))
                continue
            if isinstance(action, Discard):
                hand = _remove(context.full_hand(), action.tile.code, 1)
                state = _state(observation, context,
                               (ConditionalPhase.PUBLIC_WAIT if is_wealth(action.tile)
                                else ConditionalPhase.RESPONSE_RESOLUTION),
                               concealed=hand, action=action)
                # 这是“本人弃牌已生效”的条件分支。公开河、手牌数与逐码
                # 容量须在此步更新；正式裁决仍须后续完整响应选择集合。
                state = _refresh_public(state, _append_discard(
                    state.public_view, observation.seat, action.tile))
                roots.append(ConditionalRoot(candidate.action_key, (ConditionalBranch(state),),
                    pending_condition=state.phase))
                continue
            if isinstance(action, (Chi, Peng)):
                if observation.last_discard is None:
                    raise _MissingObservationEvidence("吃碰缺触发弃牌")
                claim_code = observation.last_discard.tile.code
                if isinstance(action, Chi):
                    required = tuple(tile.code for tile in action.tiles if tile.code != claim_code)
                    if len(required) != 2:
                        raise ValueError("吃牌组合与触发弃牌矛盾")
                else:
                    required = (action.tile.code, action.tile.code)
                claimed = context.full_hand()
                for code in required:
                    claimed = _remove(claimed, code, 1)
                claim_state = _state(
                    observation, context, ConditionalPhase.CLAIM_DISCARD,
                    concealed=claimed,
                    meld_count=len(observation.melds[observation.seat]) + 1,
                    action=action,
                )
                proposal_state = _state(
                    observation, context, ConditionalPhase.RESPONSE_RESOLUTION,
                    concealed=context.full_hand(), action=None)
                claim_state = replace(
                    claim_state,
                    my_chi_count=context.my_chi_count + int(isinstance(action, Chi)),
                    my_peng_codes=context.my_peng_codes +
                                  ((action.tile.code,) if isinstance(action, Peng) else ()),
                )
                # 全部分支由 candidate_facts 唯一产出，不在路线量具里再造一套
                # 吃碰后的弃牌合法性。缺事实时根仍保留，不能只挑最佳分支。
                facts = candidate.facts
                if facts is None or facts.followup_branches is None:
                    roots.append(ConditionalRoot(candidate.action_key, (),
                        gap_kind=RouteGapKind.MECHANICAL_GAP,
                        issues=(RuleIssue("route_transition.followup_branches",
                                          "吃碰根缺全部后续弃牌事实"),)))
                    continue
                branches = []
                for followup in facts.followup_branches:
                    code = followup.followup_discard
                    after = _remove(claimed, code, 1)
                    discard = Discard(Tile(code))
                    # 吃碰继承爆头与链，随后弃牌必须独立判定。不得把最佳
                    # 弃牌的资格复制到其他分支。依据 RULES_EVIDENCE §158—170。
                    count, piao = progression.chain_after_action(
                        observation.rule_state.chain_count, observation.chain_piao,
                        observation.rule_state.baotou, discard)
                    baotou = progression.baotou_after_discard(
                        after, len(observation.melds[observation.seat]) + 1)
                    circle = progression.catch_play_after_discard(
                        claim_state.catch_circle, observation.seat, discard.tile)
                    state = ConditionalRouteState(
                        after, len(observation.melds[observation.seat]) + 1,
                        ConditionalPhase.RESPONSE_RESOLUTION, baotou, count, piao,
                        observation.remaining_tile_count,
                        my_chi_count=context.my_chi_count + int(isinstance(action, Chi)),
                        my_peng_codes=context.my_peng_codes +
                                      ((action.tile.code,) if isinstance(action, Peng) else ()),
                        catch_restricted=circle.active and circle.owner != observation.seat,
                        unseen_capacities=claim_state.unseen_capacities,
                        unseen_evidence=claim_state.unseen_evidence,
                        root_public_view=claim_state.root_public_view,
                        catch_circle=circle,
                        seat=observation.seat,
                        dealer_seat=observation.dealer_seat,
                        structural_only=True)
                    branches.append(ConditionalBranch(
                        state, followup.followup_key, code))
                roots.append(ConditionalRoot(candidate.action_key, tuple(branches),
                    claim_state=claim_state,
                    proposal_state=proposal_state,
                    pending_condition=ConditionalPhase.RESPONSE_RESOLUTION))
                continue
            if isinstance(action, Gang):
                amount = {GangKind.CONCEALED: 4, GangKind.EXPOSED: 3,
                          GangKind.ADDED: 1}[action.kind]
                hand = _remove(context.full_hand(), action.tile.code, amount)
                melds = len(observation.melds[observation.seat]) + (
                    0 if action.kind is GangKind.ADDED else 1)
                state = _state(observation, context, ConditionalPhase.REPLACEMENT_DRAW,
                               concealed=hand, meld_count=melds, action=action)
                proposal_state = None
                if action.kind is not GangKind.EXPOSED:
                    state = _refresh_public(state, _seat_gang_public_view(
                        state.public_view, observation.seat, action))
                else:
                    proposal_state = _state(
                        observation, context, ConditionalPhase.RESPONSE_RESOLUTION,
                        concealed=context.full_hand())
                    state = replace(state, structural_only=True)
                if action.kind is GangKind.ADDED:
                    upgraded = list(state.my_peng_codes)
                    upgraded.remove(action.tile.code)
                    state = replace(state, my_peng_codes=tuple(upgraded))
                roots.append(ConditionalRoot(candidate.action_key, (ConditionalBranch(state),),
                    proposal_state=proposal_state,
                    pending_condition=(ConditionalPhase.RESPONSE_RESOLUTION
                                       if proposal_state is not None
                                       else ConditionalPhase.REPLACEMENT_DRAW)))
                continue
            raise ValueError("未知合法动作类型")
        except _MissingObservationEvidence as exc:
            roots.append(ConditionalRoot(candidate.action_key, (),
                gap_kind=RouteGapKind.INPUT_EVIDENCE_GAP,
                issues=(RuleIssue("route_transition.input", str(exc)),)))
        except (ValueError, KeyError) as exc:
            # 同次合法候选与上下文的移牌/状态冲突不等于观察缺字段。
            # 常规完整输入上这属于实现或装配错误，必须重开机械门。
            roots.append(ConditionalRoot(candidate.action_key, (),
                gap_kind=RouteGapKind.MECHANICAL_GAP,
                issues=(RuleIssue("route_transition.mechanical",
                                  "条件转移与同次合法事实冲突: " + str(exc)),)))
    checked = []
    for root in roots:
        local_id = ConditionalIdentity(
            observation.game_id, observation.round_no, root.action_key,
            ruleset_version=config.ruleset_version)
        branches = tuple(replace(
            branch,
            state=replace(branch.state,
                identity=local_id.step(
                    branch.followup_key or
                    ("hu" if branch.state.phase is ConditionalPhase.TERMINAL
                     else "root-success"))),
        ) for branch in root.branches)
        root = replace(
            root, branches=branches,
            claim_state=(replace(root.claim_state,
                                 identity=local_id.step("claim-success"))
                         if root.claim_state is not None else None),
            proposal_state=(replace(root.proposal_state,
                                    identity=local_id.step("proposal"))
                            if root.proposal_state is not None else None),
        )
        gap_kinds = [root.gap_kind] if root.gap_kind is not None else []
        input_reasons = list(observation.observation_issues)
        if (observation.rule_state.chain_count > 0 and observation.chain_piao is None
                and (root.settlement is not None
                     or any(branch.state.chain_count > 0 for branch in root.branches))):
            input_reasons.append("当前动作链内飘白次数未进入观察，保链资格无法核验")
        if observation.gang_draw is None and root.settlement is not None:
            input_reasons.append("当前胡牌的摸牌来源未知，杠开番数无法核验")
        if input_reasons:
            if RouteGapKind.INPUT_EVIDENCE_GAP not in gap_kinds:
                gap_kinds.append(RouteGapKind.INPUT_EVIDENCE_GAP)
            # 无任何条件状态的机械故障不能被同时存在的观察缺项覆盖；
            # 两种原因都写入 issues，供审计分别计数。
            primary_gap = (
                root.gap_kind
                if root.gap_kind is RouteGapKind.MECHANICAL_GAP
                and not root.branches and root.settlement is None
                else RouteGapKind.INPUT_EVIDENCE_GAP
            )
            root = replace(
                root, gap_kind=primary_gap,
                issues=root.issues + tuple(
                    RuleIssue("route_transition.input_evidence", reason)
                    for reason in input_reasons),
            )
        root = replace(root, gap_kinds=tuple(gap_kinds))
        checked.append(root)
    return tuple(checked)


def apply_given_draw(state: ConditionalRouteState, tile: Tile, *, replacement: bool) -> ConditionalRouteState:
    """给定确实发生的一张本人摸牌，更新暗牌与爆头；不声称未来会摸到它。

    普通摸牌和杠补来源必须与待摸状态相符。给定牌码至少须有正的
    公开未见容量；此容量不是墙内概率，且他家后续公开事件尚须另行投影。
    墙余只在已知时减一张；
    合法动作与番数仍须由规则模块对该条件观察再次分析。
    """

    if state.structural_only:
        raise ValueError("未裁决的结构预列分支不能给定摸牌")
    expected = (ConditionalPhase.REPLACEMENT_DRAW if replacement
                else ConditionalPhase.NORMAL_DRAW)
    if state.phase is not expected:
        raise ValueError("条件摸牌来源与待摸阶段不符")
    if (state.wall_remaining is not None
            and state.wall_remaining <= action_families.WALL_RESERVE_TILES):
        raise ValueError("已进入保留区，不能假定继续摸牌")
    if state.unseen_capacities is None:
        raise ValueError("给定摸牌缺公开未见容量证据")
    index = TILE_INDEX[tile.code]
    if state.unseen_evidence is None or state.unseen_evidence[index] != "exact":
        raise ValueError("给定摸牌的公开未见容量证据不精确")
    capacity = state.unseen_capacities[index]
    if capacity is None:
        raise ValueError("给定摸牌的公开未见容量不确定")
    if capacity <= 0:
        raise ValueError("给定摸牌码公开未见容量为零，不可条件摸入")
    baotou = progression.baotou_after_draw(
        state.baotou, state.concealed, state.meld_count, tile,
        replacement=replacement)
    next_state = ConditionalRouteState(
        state.concealed + (tile,), state.meld_count,
        ConditionalPhase.DRAW_ACTION, baotou,
        state.chain_count, state.chain_piao,
        None if state.wall_remaining is None else state.wall_remaining - 1,
        drawn_tile=tile,
        my_chi_count=state.my_chi_count,
        my_peng_codes=state.my_peng_codes,
        catch_restricted=state.catch_restricted,
        last_draw_replacement=replacement,
        catch_circle=state.catch_circle,
        unseen_evidence=state.unseen_evidence,
        root_public_view=state.root_public_view,
        public_view=state.public_view,
        identity=(state.identity.step("draw:" + tile.code)
                  if state.identity is not None else None),
        seat=state.seat,
        dealer_seat=state.dealer_seat,
        structural_only=state.structural_only,
        local_witness_only=state.local_witness_only,
        claim_awarded=state.claim_awarded,
        unseen_capacities=tuple(
            capacity - 1 if index == TILE_INDEX[tile.code] else capacity
            for index, capacity in enumerate(state.unseen_capacities)
        ))
    if state.public_view is not None and state.seat is not None:
        view = replace(
            state.public_view,
            hand_counts=_replace_four(
                state.public_view.hand_counts, state.seat,
                state.public_view.hand_counts[state.seat] + 1),
            remaining_tile_count=(
                None if state.public_view.remaining_tile_count is None
                else state.public_view.remaining_tile_count - 1),
        )
        return _refresh_public(next_state, view)
    return next_state


def given_next_normal_draw(
    state: ConditionalRouteState, tile: Tile, *,
    wall_remaining_before_draw: int, catch_restricted: bool,
    allow_local_witness: bool = False,
) -> ConditionalRouteState:
    """构造旧的一摸局部见证；不得冒充完整公开事件链的下一自摸。

    墙余（张）与抓打限制须由未来权威公开事件或假设条件显式传入；
    该函数不推断响应结果、圈主或对手动作。它沿用根时点未见容量，
    只能构造局部条件见证；其它公开牌变化会影响有效牌容量，须另用
    完整公开事件投影计算，不能由本状态估算或用于 P2 完成判定。
    调用方必须显式接受 ``local_witness_only``；完整路径应在本次响应
    获裁决及全部中间公开事件给定后，从 ``NORMAL_DRAW`` 调用
    ``apply_given_draw``。旧路径曾有裁决不能证明当前响应已裁决。
    """

    if state.phase is not ConditionalPhase.RESPONSE_RESOLUTION:
        raise ValueError("下一普通自摸必须接在待响应裁决状态之后")
    if not allow_local_witness:
        raise ValueError("旧下一摸入口只允许显式局部见证；完整路径须推进当前响应")
    if type(wall_remaining_before_draw) is not int or wall_remaining_before_draw < 0:
        raise ValueError("给定摸牌前墙余必须是非负整数")
    if type(catch_restricted) is not bool:
        raise ValueError("给定抓打限制必须是布尔值")
    waiting = replace(
        state, phase=ConditionalPhase.NORMAL_DRAW,
        wall_remaining=wall_remaining_before_draw,
        catch_restricted=catch_restricted,
        catch_circle=None,  # 期间公开事件未投影，不能继承旧圈主
        structural_only=False,
        local_witness_only=True,
    )
    return apply_given_draw(waiting, tile, replacement=False)


def analyze_given_self_draw(
    state: ConditionalRouteState, *, seat: int, dealer_seat: int,
    config: RuleConfig,
) -> GivenDrawAnalysis:
    """给定本人摸牌，复用动作族、分解和结算求立即合法动作。

    杠补紧接已确认的杠；完整普通自摸须先沿已裁决的公开事件链到
    ``NORMAL_DRAW``，再用 ``apply_given_draw`` 给定本人实际摸牌。
    旧 ``given_next_normal_draw`` 仅产生标记过的局部见证。这里只读取
    本座暗牌和已给定公开事实，不读他家暗牌或未来墙序。
    """

    if config.base_score != 1 or config.you_cai_bi_kao:
        raise ValueError("条件转移首版只绑定 BaseScore=1、YouCaiBiKao=false")
    if (state.identity is None
            or state.identity.ruleset_version != config.ruleset_version):
        raise ValueError("给定摸牌的规则版本与条件根不一致")
    if (seat not in range(4) or dealer_seat != state.dealer_seat
            or (state.seat != seat
                and not (state.seat is None and state.local_witness_only))):
        raise ValueError("给定摸牌的本人或庄家座位与条件状态不一致")
    if state.phase is not ConditionalPhase.DRAW_ACTION or state.last_draw_replacement is None:
        raise ValueError("必须先给定已发生的本人摸牌")
    if state.drawn_tile is None:
        raise ValueError("给定杠补状态缺摸入牌")
    context = WindowContext(
        seat=seat, phase="draw", turn_seat=seat, responding_seats=(),
        hand_tiles=state.concealed[:-1], drawn_tile=state.drawn_tile,
        my_chi_count=state.my_chi_count, my_peng_codes=state.my_peng_codes,
        last_discard=None, catch_play=state.catch_restricted,
        remaining_tile_count=state.wall_remaining,
    )
    if context.full_hand() != state.concealed:
        raise ValueError("杠补牌必须是暗牌末项")
    summary = hand_analysis.analyse_hand(state.concealed, state.meld_count)
    outcome = action_families.generate_candidates(context, summary)
    immediate = None
    if any(isinstance(candidate.action, Hu) for candidate in outcome.candidates):
        if state.chain_piao is None:
            return GivenDrawAnalysis(state, outcome.candidates, None, outcome.issues + (
                RuleIssue("route_transition.input_evidence", "链内飘白次数未知，不能结算给定补牌胡"),
            ), state.local_witness_only)
        split = hand_analysis.win_split(state.concealed, state.meld_count)
        if split is None:
            return GivenDrawAnalysis(state, outcome.candidates, None, outcome.issues + (
                RuleIssue("route_transition.mechanical", "胡候选无法还原同源成胡分解"),
            ), state.local_witness_only)
        immediate = settlement.settle_win(
            split, state.chain_count, state.chain_piao, state.baotou,
            config.base_score, seat, dealer_seat)
    return GivenDrawAnalysis(
        state, outcome.candidates, immediate, outcome.issues,
        state.local_witness_only)


def analyze_waiting_draw_witness(
    state: ConditionalRouteState, tile: Tile, *,
    wall_remaining_before_draw: int, catch_restricted: bool, config: RuleConfig,
) -> GivenDrawAnalysis:
    """对本人合法弃后等待手牌作一次局部摸牌见证，绝不承诺能走到该点。

    只支持已完成本人弃牌的 ``13-3m`` 张暗牌；吃碰预列分支须先获裁决，
    再依法弃牌后进入本入口。响应裁决、他家先胡、途中公开变化及圈主
    尚未展开，故结果永久标记 ``local_witness_only=True``，不能用于 P2
    机械闭包或到达概率。墙余单位为张、抓打限制由调用方明示为局部条件。
    公开容量仍需精确且为正；保守或未知容量抛出输入证据错误，调用方须
    保留该牌码的未知分支，不能删除它或伪造精确证据。无副作用。
    """

    if state.structural_only:
        raise ValueError("未裁决的结构预列分支不能建立等待摸牌见证")
    if state.phase not in (ConditionalPhase.RESPONSE_RESOLUTION, ConditionalPhase.PUBLIC_WAIT):
        raise ValueError("局部摸牌见证只接受本人合法弃后等待状态")
    if (state.seat is None or state.dealer_seat is None or state.identity is None
            or state.public_view is None):
        raise ValueError("局部摸牌见证缺本人、庄家、规则身份或公开视图")
    if (type(state.seat) is not int or state.seat not in range(4)
            or type(state.dealer_seat) is not int or state.dealer_seat not in range(4)):
        raise ValueError("局部摸牌见证的本人和庄家座位须为0—3整数")
    if (state.drawn_tile is not None or state.expected_discard_seat is not None
            or state.expected_replacement_draw
            or len(state.concealed) != 13 - 3 * state.meld_count
            or state.public_view.hand_counts[state.seat] != len(state.concealed)):
        raise ValueError("局部摸牌见证不是本人13-3m张合法弃后等待手牌")
    if type(wall_remaining_before_draw) is not int or wall_remaining_before_draw < 0:
        raise ValueError("局部摸牌见证的墙余必须是非负整数张数")
    if type(catch_restricted) is not bool:
        raise ValueError("局部摸牌见证的抓打限制必须是布尔值")
    if (config.base_score != 1 or config.you_cai_bi_kao
            or state.identity.ruleset_version != config.ruleset_version):
        raise ValueError("局部摸牌见证的规则配置与条件根不一致")
    waiting = replace(
        state, phase=ConditionalPhase.NORMAL_DRAW,
        wall_remaining=wall_remaining_before_draw,
        public_view=replace(state.public_view,
                            remaining_tile_count=wall_remaining_before_draw),
        expected_draw_seat=state.seat, expected_discard_seat=None,
        expected_replacement_draw=False, other_draw_replacement=None,
        response_window=None, response_trigger=None, response_public_discard=None,
        catch_restricted=catch_restricted, catch_circle=None,
        local_witness_only=True,
        identity=state.identity.step("local-waiting-draw-witness"),
    )
    landed = apply_given_draw(waiting, tile, replacement=False)
    return analyze_given_self_draw(
        landed, seat=state.seat, dealer_seat=state.dealer_seat, config=config)


def analyze_given_claim_action(
    state: ConditionalRouteState, *, seat: int, config: RuleConfig,
) -> GivenClaimAnalysis:
    """复用动作族分析吃碰后未摸的弃牌和暗/补杠，不强制立即弃牌。

    官方 v18 的吃→暗杠→杠补轨迹证明此暂态可以先杠。未给定该鸣牌
    已获裁决时不能调用；胡牌族由同源 ``drawn_tile=None`` 门禁关闭。
    """

    if config.base_score != 1 or config.you_cai_bi_kao:
        raise ValueError("条件转移首版只绑定 BaseScore=1、YouCaiBiKao=false")
    if (state.identity is None
            or state.identity.ruleset_version != config.ruleset_version):
        raise ValueError("吃碰后动作的规则版本与条件根不一致")
    if state.seat != seat:
        raise ValueError("吃碰后动作的本人座位与条件状态不一致")
    if state.phase is not ConditionalPhase.CLAIM_DISCARD or state.drawn_tile is not None:
        raise ValueError("必须是吃碰已获裁决且尚未摸牌的本人动作状态")
    if not state.claim_awarded:
        raise ValueError("吃碰成功条件尚未由完整响应裁决确认")
    context = WindowContext(
        seat=seat, phase="draw", turn_seat=seat, responding_seats=(),
        hand_tiles=state.concealed, drawn_tile=None,
        my_chi_count=state.my_chi_count, my_peng_codes=state.my_peng_codes,
        last_discard=None, catch_play=state.catch_restricted,
        remaining_tile_count=state.wall_remaining,
    )
    outcome = action_families.generate_candidates(
        context, hand_analysis.analyse_hand(state.concealed, state.meld_count))
    if any(isinstance(candidate.action, Hu) for candidate in outcome.candidates):
        raise ValueError("未摸牌暂态不得出现胡候选")
    return GivenClaimAnalysis(state, outcome.candidates, outcome.issues)


def apply_legal_claim_discard(
    analysis: GivenClaimAnalysis, action_key_value: str,
) -> ConditionalRouteState:
    """吃碰获裁决后执行同次合法弃牌，逐项更新圈主、牌河和容量。"""

    candidate = next((item for item in analysis.legal_candidates
                      if item.action_key == action_key_value), None)
    if candidate is None or not isinstance(candidate.action, Discard):
        raise ValueError("弃牌不在本次吃碰后未摸动作全集")
    return _apply_legal_self_discard(analysis.source_state, candidate.action)


def apply_legal_draw_discard(
    analysis: GivenDrawAnalysis, action_key_value: str,
) -> ConditionalRouteState:
    """给定本人普通或杠补摸牌后，执行同次动作族确认的弃牌。"""

    candidate = next((item for item in analysis.legal_candidates
                      if item.action_key == action_key_value), None)
    if candidate is None or not isinstance(candidate.action, Discard):
        raise ValueError("弃牌不在本次给定摸牌合法动作全集")
    if analysis.source_state.phase is not ConditionalPhase.DRAW_ACTION:
        raise ValueError("给定摸牌分析的源状态不是本人摸牌动作窗口")
    return _apply_legal_self_discard(analysis.source_state, candidate.action)


def apply_legal_draw_hu(analysis: GivenDrawAnalysis) -> ConditionalRouteState:
    """给定本人摸牌后按同次合法胡及已证结算进入条件终局。"""

    if not any(isinstance(item.action, Hu) for item in analysis.legal_candidates):
        raise ValueError("胡不在本次给定摸牌合法动作全集")
    if analysis.immediate_settlement is None:
        raise ValueError("给定摸牌合法胡缺已证四座结算")
    return _terminal_hu_state(analysis.source_state, analysis.immediate_settlement)


def _terminal_hu_state(
    state: ConditionalRouteState, result: Settlement,
) -> ConditionalRouteState:
    """把同源合法胡结算转换为条件终局；根胡和给定摸牌胡共用。"""

    if (state.phase is not ConditionalPhase.DRAW_ACTION or state.seat is None
            or state.identity is None):
        raise ValueError("合法胡缺本人动作状态、座位或本地身份")
    return replace(
        state, phase=ConditionalPhase.TERMINAL,
        terminal_result=progression.HandResult(
            winner_seat=state.seat, is_draw=False, fan=result.fan,
            details=result.details, score_delta=result.score_delta),
        identity=state.identity.step("hu"),
    )


def _apply_legal_self_discard(
    state: ConditionalRouteState, action: Discard,
) -> ConditionalRouteState:
    """复用本人弃牌的物理与公开状态转移；合法性由各入口先核对。"""

    if state.seat is None or state.public_view is None or state.catch_circle is None:
        raise ValueError("本人弃牌状态缺公开视图、座位或圈主")
    hand = _remove(state.concealed, action.tile.code, 1)
    count, piao = progression.chain_after_action(
        state.chain_count, state.chain_piao, state.baotou, action)
    baotou = progression.baotou_after_discard(hand, state.meld_count)
    circle = progression.catch_play_after_discard(
        state.catch_circle, state.seat, action.tile)
    next_state = replace(
        state, concealed=hand,
        phase=(ConditionalPhase.PUBLIC_WAIT if is_wealth(action.tile)
               else ConditionalPhase.RESPONSE_RESOLUTION),
        drawn_tile=None, last_draw_replacement=None,
        baotou=baotou, chain_count=count, chain_piao=piao,
        catch_circle=circle,
        catch_restricted=circle.active and circle.owner != state.seat,
        response_window=(None if is_wealth(action.tile) else "response_peng"),
        response_trigger=(None if is_wealth(action.tile)
                          else (state.seat, action.tile)),
        response_public_discard=None,
        expected_draw_seat=((state.seat + 1) % 4 if is_wealth(action.tile) else None),
        expected_discard_seat=None,
        identity=(state.identity.step("discard:" + action.tile.code)
                  if state.identity is not None else None),
    )
    return _refresh_public(next_state, _append_discard(
        state.public_view, state.seat, action.tile))


def analyze_given_replacement_draw(
    state: ConditionalRouteState, *, seat: int, dealer_seat: int,
    config: RuleConfig,
) -> GivenDrawAnalysis:
    """仅杠补来源的便捷入口，防止普通摸牌误用补牌资格。"""

    if state.last_draw_replacement is not True:
        raise ValueError("必须先给定已发生的杠补牌")
    return analyze_given_self_draw(
        state, seat=seat, dealer_seat=dealer_seat, config=config)


def apply_legal_followup_gang(
    analysis: GivenDrawAnalysis | GivenClaimAnalysis, action_key: str,
) -> ConditionalRouteState:
    """只执行本次给定补牌或已获裁决鸣牌暂态确认的杠。"""

    candidate = next((item for item in analysis.legal_candidates
                      if item.action_key == action_key), None)
    if candidate is None or not isinstance(candidate.action, Gang):
        raise ValueError("再杠动作不在同次给定补牌合法候选中")
    state = analysis.source_state
    action = candidate.action
    amount = {GangKind.CONCEALED: 4, GangKind.EXPOSED: 3,
              GangKind.ADDED: 1}[action.kind]
    hand = _remove(state.concealed, action.tile.code, amount)
    count, piao = progression.chain_after_action(
        state.chain_count, state.chain_piao, state.baotou, action)
    baotou = progression.baotou_after_action(
        state.baotou, action, state.concealed, state.meld_count)
    if baotou is None:
        raise ValueError("再杠后爆头状态未知")
    peng_codes = list(state.my_peng_codes)
    if action.kind is GangKind.ADDED:
        peng_codes.remove(action.tile.code)
    next_state = ConditionalRouteState(
        hand, state.meld_count + (0 if action.kind is GangKind.ADDED else 1),
        ConditionalPhase.REPLACEMENT_DRAW, baotou, count, piao,
        state.wall_remaining,
        my_chi_count=state.my_chi_count,
        my_peng_codes=tuple(peng_codes),
        catch_restricted=state.catch_restricted,
        unseen_capacities=state.unseen_capacities,
        unseen_evidence=state.unseen_evidence,
        root_public_view=state.root_public_view,
        public_view=state.public_view,
        catch_circle=state.catch_circle,
        identity=(state.identity.step("gang:" + action_key)
                  if state.identity is not None else None),
        seat=state.seat,
        dealer_seat=state.dealer_seat,
        local_witness_only=state.local_witness_only,
        claim_awarded=state.claim_awarded,
    )
    if state.public_view is not None and state.seat is not None:
        return _refresh_public(next_state, _seat_gang_public_view(
            state.public_view, state.seat, action))
    return next_state
