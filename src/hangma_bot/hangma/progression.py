"""杭麻单局推进规则：动作窗口、裁决、链/爆头/抓打圈状态转移与结算。

本文件是模拟世界推进的唯一规则来源。simulation 只做发牌、牌墙物理顺序与
机械应用（见 simulation/state.py、shuffle.py、engine.py），不得实现第二套
规则；本文件把“一个动作窗口内全部选择的裁决”映射为确定的事件流、状态转移
与单局结果。

规则依据与证据级别：RULES_EVIDENCE.md §1/§2/§3/§4/§5/§6/§8；官方指南
v15/2026-09-05 快照（doc/references/official-guide-v15.txt），夹具为
v14/2026-09-05。逐项证据与“未确认即 blocked”口径见各函数 docstring 与
doc/implementation/handoffs/simulation.md 支持矩阵。
爆头生命周期按 RULES_EVIDENCE.md 的 v18 修订实现；四白例外按
v23/2026-09-08 官方计算器结果移除，保留既有连续动作继承语义。
抓打圈窗口按 v26 修复（v27 全文 §1.1/§2.4，2026-09-09 核验）：
圈主可碰/明杠，仅为弃牌者下家时可吃；不再沿用 v24 跳过全部响应的缺陷。

设计（engine 与 progression 的分工）：

- ProgressionState 是推进输入/输出的最小值对象（hangma 内部，不依赖
  simulation.WorldState）；牌墙只保留张数（wall_drawable/wall_total），
  牌墙的物理牌值由 simulation 持有并在摸牌步骤注入（attach_draw）。
- 状态只会停在四类位置：决策窗口（draw/response_peng/response_chi）、
  待摸牌（pending_draw，engine 注入牌值后继续）、单局结束（ended，engine
  结算并开下一局或终局）、桌赛结束（match_end）。
- 本模块的所有函数都是纯函数：不访问网络、文件、时钟或随机源。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional, Tuple

from hangma_bot.kernel.actions import (
    SEAT_COUNT,
    Action,
    Chi,
    Discard,
    Gang,
    GangKind,
    Hu,
    Pass,
    Peng,
    Tile,
)
from hangma_bot.kernel.observation import PublicDiscard, ScoreVector

from . import hand_analysis, settlement
from .internal_types import is_wealth


@dataclass(frozen=True)
class MeldRecord:
    """副露的内部推进记录；kind 只有 chi/peng/gang 三种（对观察投影的
    PublicMeld.kind 直接透传），杠种细节保留在 gang_kind。"""

    kind: str  # "chi" | "peng" | "gang"
    gang_kind: Optional[str]  # kind=="gang" 时 "an"|"ming"|"bu"
    tiles: Tuple[Tile, ...]  # chi/peng 3 张，gang 4 张
    from_seat: Optional[int]  # 供牌者座位；暗杠为空


@dataclass(frozen=True)
class SeatProgression:
    """一个座位的全部推进事实；hand 为不含当前摸牌的暗牌（获得顺序）。"""

    hand: Tuple[Tile, ...]
    melds: Tuple[MeldRecord, ...]
    discards: Tuple[Tile, ...]
    drawn: Optional[Tile]
    catch_play: bool  # 当前唯一圈主标记；他家弃白撤销，本人弃非白结束该圈
    chain_count: int  # 动作链次数（飘/杠各计 1，断链清零）
    chain_piao: int  # 链内飘出白板数（结算精确口径）
    baotou: bool  # 该座位持续爆头状态；吃碰杠继承，弃牌更新听牌态


@dataclass(frozen=True)
class DrawRequest:
    """待摸牌请求；engine 从牌墙取牌后调用 attach_draw 落地。"""

    seat: int
    replacement: bool  # True=杠后补牌（牌墙补牌端），False=普通摸牌
    seq: Optional[int]  # 摸牌事件的 seq；庄家直抽无事件为 None
    emit_event: bool  # 庄家直抽不发 tile_drawn 事件（官方 v10 口径）
    consumes_wall: bool  # 庄家直抽已在发牌时从牌墙扣除，不重复扣


@dataclass(frozen=True)
class HandResult:
    """一次单局结束的确定结果；流局 fan=0、details 为空、全零增量。"""

    winner_seat: Optional[int]
    is_draw: bool
    fan: int
    details: Tuple[str, ...]
    score_delta: ScoreVector


@dataclass(frozen=True)
class ProgressionState:
    """推进状态的最小快照；全部不可变，advance 分叉共享同一旧状态。"""

    round_no: int
    dealer_seat: int
    base_score: int
    seats: Tuple[SeatProgression, SeatProgression, SeatProgression, SeatProgression]
    scores: ScoreVector  # 桌内积分（四家累计）
    wall_drawable: int  # 牌墙可摸区剩余张数（不含保留区）
    wall_total: int  # 牌墙剩余总张数（含保留区 20 张；观察 remaining_tile_count 口径）
    seq: int  # 最近事件 seq（无事件为 0）
    window: str  # draw | response_peng | response_chi | pending_draw | ended | match_end
    turn_seat: Optional[int]
    responding: Tuple[int, ...]
    trigger_seq: int  # 当前窗口触发事件 seq（无事件窗口为 seq 水位）
    last_discard: Optional[PublicDiscard]
    pending_draw: Optional[DrawRequest]
    hand_result: Optional[HandResult]  # window=="ended"/"match_end" 时非空


@dataclass(frozen=True)
class EventRecord:
    """一条已定 seq 的世界事件；data 用二元组序列保持不可变。"""

    seq: int
    kind: str
    seat: Optional[int]
    tile: Optional[Tile]
    data: Tuple[Tuple[str, object], ...] = ()


@dataclass(frozen=True)
class Transition:
    """一次裁决的确定结果；engine 机械应用。blocked 非空时不产生事件。"""

    events: Tuple[EventRecord, ...]
    state: ProgressionState
    blocked: Optional[str] = None


_WINDOW_DRAW = "draw"
_WINDOW_RESPONSE_PENG = "response_peng"
_WINDOW_RESPONSE_CHI = "response_chi"
_WINDOW_PENDING_DRAW = "pending_draw"
_WINDOW_ENDED = "ended"
_WINDOW_MATCH_END = "match_end"

# 官方事件 type 原样透传值（doc/official-platform-api-v2.md §2.3 与
# tests/fixtures/hangma/archived-rooms 实测）。
EVENT_KIND_DRAWN = "tile_drawn"
EVENT_KIND_DISCARDED = "tile_discarded"
EVENT_KIND_PASS = "pass"
EVENT_KIND_PENG = "peng"
EVENT_KIND_CHI = "chi"
EVENT_KIND_GANG = "gang"
EVENT_KIND_ROUND_ENDED = "round_ended"
EVENT_KIND_GAME_ENDED = "game_ended"

_MULTI_CLAIM_BLOCK = (
    "两家及以上同时响应同一弃牌的碰/明杠：官方指南（v15/2026-09-05 快照）"
    "未定义裁决优先级，契约 §6 禁止默认先到先得——模拟引擎按 blocked 报告"
    "且不做任何裁决。"
)


def _ev(
    seq: int, kind: str, seat: Optional[int], tile: Optional[Tile] = None,
    data: Tuple[Tuple[str, object], ...] = (),
) -> EventRecord:
    return EventRecord(seq=seq, kind=kind, seat=seat, tile=tile, data=data)


def _other_three(seat: int) -> Tuple[int, int, int]:
    """弃牌者之外的三个座位，按弃牌者下家起的座位序（固定序，保证确定性）。"""
    return ((seat + 1) % SEAT_COUNT, (seat + 2) % SEAT_COUNT, (seat + 3) % SEAT_COUNT)


def _replace_seat(state: ProgressionState, seat: int, new_seat: SeatProgression) -> ProgressionState:
    seats = list(state.seats)
    seats[seat] = new_seat
    return replace(state, seats=(seats[0], seats[1], seats[2], seats[3]))


# ---------------------------------------------------------------------------
# 纯规则判定助手（simulation 与 replay_check 复用，不构成第二套规则）
# ---------------------------------------------------------------------------


def chain_after_discard(
    chain_count: int, chain_piao: int, baotou: bool, tile: Tile
) -> Tuple[int, int]:
    """一次弃牌后的链状态：爆头态打白=飘（链+1、piao+1）；其余弃牌断链清零。

    【官方】指南 1.3 / RULES_EVIDENCE §8：飘与杠每个动作 ×2、可连续可组合；
    打出非飘非杠的牌（含非爆头态打白板）→ 链断重新计数。判定复用
    special_rules.is_piao_discard 同据（爆头 ∧ 白）。
    """
    if baotou and is_wealth(tile):
        return (chain_count + 1, chain_piao + 1)
    return (0, 0)


def chain_after_gang(chain_count: int, chain_piao: int) -> Tuple[int, int]:
    """杠（任意种类）后的链状态：链 +1，piao 不变。

    【官方】指南 1.3：杠每个动作 ×2，可连续可组合。
    """
    return (chain_count + 1, chain_piao)


def recompute_baotou(
    pre_draw_hand: Tuple[Tile, ...], meld_count: int, whites_after_draw: int
) -> bool:
    """计算静态爆头条件；持续状态须经 baotou_after_draw 或弃牌边界更新。

    【官方 v23，2026-09-08 对拍】指南 1.2 / RULES_EVIDENCE §5：摸前暗牌
    接任意物理可得牌均成胡（hand_analysis.any_tile_win，含副露折算）即爆头。
    whites_after_draw 为摸后暗牌白板数，保留调用兼容；四白不再排除爆头。
    """
    return hand_analysis.any_tile_win(pre_draw_hand, meld_count)


def baotou_after_draw(
    previous: bool, pre_draw_hand: Tuple[Tile, ...], meld_count: int,
    drawn: Tile, *, replacement: Optional[bool] = False,
) -> bool:
    """普通摸牌计算听牌条件，杠补继承连续动作状态并允许形成新爆头。

    指南v23 §1.2及计算器实测：四白同样按任意听判断，不清除已成立的爆头。
    飘杠连续、普通弃牌断链，沿用v18生命周期。
    连续动作继承按本项目确认口径，不把吃碰后的暂态暗牌当作退出依据。
    replacement未知且会改变结果时拒绝猜测，交官方适配器恢复快照。
    """
    whites = sum(is_wealth(tile) for tile in pre_draw_hand) + is_wealth(drawn)
    static = recompute_baotou(pre_draw_hand, meld_count, whites)
    if replacement is None and previous and not static:
        raise ValueError("摸牌来源未知，无法确定爆头是否继承；须恢复权威快照")
    return static or (bool(replacement) and previous)


def next_dealer(dealer_seat: int, winner_seat: Optional[int], is_draw: bool) -> int:
    """单局结束后的庄家轮转。

    【官方】指南 1.1（v15/2026-09-05 快照）：“连庄：直上三连庄——首局即按
    ×8 计（不从平庄 ×2、二连庄 ×4 递增）；流局庄家连庄。”据此：流局连庄
    （明文）、庄家胡牌连庄（“连庄”语义本身）、闲家胡牌换庄（连庄的反面）。
    庄家倍率恒 ×8 已在 settlement.settle_scores 实现，此处只管座位轮转。
    """
    if is_draw or winner_seat is None or winner_seat == dealer_seat:
        return dealer_seat
    return (dealer_seat + 1) % SEAT_COUNT


# ---------------------------------------------------------------------------
# 状态构造与摸牌落地
# ---------------------------------------------------------------------------


def deal_state(
    round_no: int,
    dealer_seat: int,
    hands: Tuple[Tuple[Tile, ...], ...],
    scores: ScoreVector,
    seq: int,
    base_score: int,
    wall_drawable: int,
    wall_total: int,
) -> ProgressionState:
    """新单局的起点状态：四家 13 张起手已发，庄家直抽待摸（pending_draw）。

    起手四家暗牌 13 张；庄家第 14 张为发牌直抽（官方 v10：无摸牌事件），
    由 engine 注入牌值后进入庄家摸牌窗口。
    """
    # 闲家可能首次摸牌前就吃碰杠；起手已任意听时不能等待 attach_draw 才初始化。
    seats = tuple(
        SeatProgression(
            hand=hand, melds=(), discards=(), drawn=None,
            catch_play=False, chain_count=0, chain_piao=0,
            baotou=recompute_baotou(hand, 0, sum(is_wealth(tile) for tile in hand)),
        )
        for hand in hands
    )
    return ProgressionState(
        round_no=round_no,
        dealer_seat=dealer_seat,
        base_score=base_score,
        seats=seats,
        scores=scores,
        wall_drawable=wall_drawable,
        wall_total=wall_total,
        seq=seq,
        window=_WINDOW_PENDING_DRAW,
        turn_seat=None,
        responding=(),
        trigger_seq=seq,
        last_discard=None,
        pending_draw=DrawRequest(
            seat=dealer_seat, replacement=False, seq=None,
            emit_event=False, consumes_wall=False,
        ),
        hand_result=None,
    )


def attach_draw(state: ProgressionState, tile: Tile) -> Transition:
    """摸牌落地：drawn置位，按普通摸牌或连续杠补更新爆头，进入动作窗口。

    仅允许在 pending_draw 状态调用；庄家直抽（emit_event=False）不发
    tile_drawn 事件，窗口触发序号取当前 seq 水位。
    """
    if state.window != _WINDOW_PENDING_DRAW or state.pending_draw is None:
        raise ValueError("attach_draw 只能在待摸牌状态调用")
    request = state.pending_draw
    seat = request.seat
    s = state.seats[seat]
    events: Tuple[EventRecord, ...] = ()
    new_seq = state.seq
    if request.emit_event:
        if request.seq is None:
            raise ValueError("摸牌事件缺少预留 seq")
        events = (_ev(request.seq, EVENT_KIND_DRAWN, seat, tile),)
        new_seq = request.seq
    # hand 恒为「不含当前摸牌」的暗牌：摸牌只置 drawn，弃/杠时合并（摸牌置尾）。
    new_seat = replace(
        s,
        drawn=tile,
        baotou=baotou_after_draw(s.baotou, s.hand, len(s.melds), tile, replacement=request.replacement),
    )
    return Transition(
        events=events,
        state=replace(
            _replace_seat(state, seat, new_seat),
            seq=new_seq,
            window=_WINDOW_DRAW,
            turn_seat=seat,
            responding=(),
            trigger_seq=new_seq,
            last_discard=None,
            pending_draw=None,
        ),
    )


def end_as_draw(state: ProgressionState) -> ProgressionState:
    """牌墙可摸区耗尽且无人胡牌 → 流局。

    【官方】指南 1.1（v15）：“摸完无人胡则流局”；保留区 20 张不摸。
    流局番 0、无支付（settlement 口径），庄家连庄（next_dealer）。
    """
    if state.window != _WINDOW_PENDING_DRAW:
        raise ValueError("end_as_draw 只能在待摸牌状态调用")
    return replace(
        state,
        window=_WINDOW_ENDED,
        turn_seat=None,
        responding=(),
        last_discard=None,
        pending_draw=None,
        hand_result=HandResult(
            winner_seat=None, is_draw=True, fan=0, details=(), score_delta=(0, 0, 0, 0)
        ),
    )


# ---------------------------------------------------------------------------
# 动作裁决
# ---------------------------------------------------------------------------


def _exactly_one(choices: Tuple[Tuple[int, Action], ...], seat: int) -> Action:
    """本窗口恰好该座位一个选择；其余形状是 engine 装配错误，立即失败。"""
    matched = [action for choice_seat, action in choices if choice_seat == seat]
    if len(matched) != 1 or len(choices) != 1:
        raise ValueError(
            "draw 窗口期望恰好座位 {0} 的一个选择，得到 {1} 个".format(seat, len(choices))
        )
    return matched[0]


def _remove_from_hand(
    s: SeatProgression, tile: Tile
) -> Tuple[Tuple[Tile, ...], Optional[Tile]]:
    """弃掉一张牌：从「暗牌 + 刚摸牌（置尾）」取首个同码实例，摸牌并入手牌。

    弃牌后 drawn 恒清空：被弃的若是摸牌则直接消失，否则摸牌并入暗牌尾。
    """
    combined = list(s.hand)
    if s.drawn is not None:
        combined.append(s.drawn)
    for index, held in enumerate(combined):
        if held.code == tile.code:
            del combined[index]
            return (tuple(combined), None)
    raise ValueError(
        "弃牌 {0} 不在该座位暗牌中（合法性验证与推进状态不一致）".format(tile.code)
    )


def _remove_n_from_hand(
    s: SeatProgression, tile: Tile, count: int
) -> Tuple[Tuple[Tile, ...], Optional[Tile]]:
    """杠移除 count 张同码牌（暗牌优先，随后刚摸牌）；drawn 恒清空。"""
    combined = list(s.hand)
    if s.drawn is not None:
        combined.append(s.drawn)
    removed = 0
    kept = []
    for held in combined:
        if removed < count and held.code == tile.code:
            removed += 1
        else:
            kept.append(held)
    if removed != count:
        raise ValueError(
            "杠移除 {0}×{1} 张失败（合法性验证与推进状态不一致）".format(tile.code, count)
        )
    return (tuple(kept), None)


def _settle_win_exact(state: ProgressionState, winner: int) -> HandResult:
    """胡牌结算：同一 settlement 规则源，链/piao/爆头取推进状态的精确值。

    线上 score() 只接受可见连续历史或已知字段确认的精确 piao；模拟世界
    持有精确链状态，直接传入。未知链内飘数不能用于确定结算。
    分解失败属内部不一致（胡候选已通过 hand_analysis 验证），立即失败。
    """
    s = state.seats[winner]
    concealed = s.hand + ((s.drawn,) if s.drawn is not None else ())
    split = hand_analysis.win_split(concealed, len(s.melds))
    if split is None:
        raise ValueError(
            "胡牌选择已通过合法性验证但 win_split 分解失败（内部不一致）"
        )
    fan_result = settlement.compute_fan(split, s.chain_count, s.chain_piao, s.baotou)
    score_delta = settlement.settle_scores(
        fan_result.fan, state.base_score, winner, state.dealer_seat
    )
    return HandResult(
        winner_seat=winner,
        is_draw=False,
        fan=fan_result.fan,
        details=fan_result.details,
        score_delta=score_delta,
    )


def resolve(state: ProgressionState, choices: Tuple[Tuple[int, Action], ...]) -> Transition:
    """裁决一个动作窗口的全部选择；输入必须已经过 HangmaRules 合法性验证。

    同一帧的所有响应都来自推进前观察；本函数只按窗口语义裁决，选择数组
    顺序不改变结果（pass 事件按固定座位序发出）。两家及以上同时响碰/明杠
    无官方优先级依据 → blocked（契约 §6，不默认先到先得）。选择座位集必须
    与窗口成员完全一致（缺少/重复/多余 → ValueError，防御 engine 装配错误）。
    """
    if state.window == _WINDOW_DRAW:
        expected = (state.turn_seat,) if state.turn_seat is not None else ()
    elif state.window == _WINDOW_RESPONSE_PENG or state.window == _WINDOW_RESPONSE_CHI:
        expected = state.responding
    else:
        raise ValueError("resolve 只能在决策窗口调用（当前 {0}）".format(state.window))
    choice_seats = [seat for seat, _ in choices]
    if sorted(choice_seats) != sorted(expected) or len(set(choice_seats)) != len(choice_seats):
        raise ValueError(
            "选择座位集 {0} 与窗口成员 {1} 不一致（缺少/重复/多余窗口）".format(
                sorted(choice_seats), sorted(expected),
            )
        )
    if state.window == _WINDOW_DRAW:
        return _resolve_draw(state, choices)
    if state.window == _WINDOW_RESPONSE_PENG:
        return _resolve_peng_window(state, choices)
    return _resolve_chi_window(state, choices)


def _resolve_draw(state: ProgressionState, choices: Tuple[Tuple[int, Action], ...]) -> Transition:
    """摸牌窗口（出牌 / 暗杠 / 补杠 / 自摸胡）。"""
    seat = state.turn_seat
    if seat is None:
        raise ValueError("摸牌窗口缺少行动座位")
    action = _exactly_one(choices, seat)
    s = state.seats[seat]

    if isinstance(action, Hu):
        return Transition((), replace(
            state,
            window=_WINDOW_ENDED,
            turn_seat=None,
            responding=(),
            last_discard=None,
            pending_draw=None,
            hand_result=_settle_win_exact(state, seat),
        ))

    if isinstance(action, Gang):
        return _resolve_gang(state, seat, action, s)

    if isinstance(action, Discard):
        new_hand, new_drawn = _remove_from_hand(s, action.tile)
        wealth_discard = is_wealth(action.tile)
        # 本次是否飘取动作前爆头；弃后可新入爆头，但不能反向把本次打白算飘。
        chain_count, chain_piao = chain_after_discard(
            s.chain_count, s.chain_piao, s.baotou, action.tile,
        )
        new_seat = replace(
            s,
            hand=new_hand,
            drawn=new_drawn,
            discards=s.discards + (action.tile,),
            catch_play=wealth_discard,
            baotou=recompute_baotou(new_hand, len(s.melds), sum(is_wealth(t) for t in new_hand)),
            chain_count=chain_count,
            chain_piao=chain_piao,
        )
        state = _replace_seat(state, seat, new_seat)
        if wealth_discard:
            # 2026-09-08 官方换圈轨迹：包括被迫摸切白在内，每次弃白均换主。
            # 仅撤销旧圈主标记，不改变他家的爆头或飘杠链。
            state = replace(state, seats=tuple(
                replace(other, catch_play=False)
                if index != seat and other.catch_play else other
                for index, other in enumerate(state.seats)
            ))
        seq = state.seq + 1
        circle_active = any(other.catch_play for other in state.seats)
        events = (_ev(
            seq, EVENT_KIND_DISCARDED, seat, action.tile,
            (("catch_play", circle_active),),
        ),)
        if wealth_discard:
            # 白板本身不能被吃碰杠；此次弃白已原子换主/续圈，直接下家摸牌。
            return Transition(events, replace(
                state,
                seq=seq,
                window=_WINDOW_PENDING_DRAW,
                turn_seat=None,
                responding=(),
                trigger_seq=seq,
                last_discard=None,
                pending_draw=DrawRequest(
                    seat=(seat + 1) % SEAT_COUNT, replacement=False,
                    seq=seq + 1, emit_event=True, consumes_wall=True,
                ),
            ))
        # v26：圈内普通弃牌只给最新圈主碰/明杠响应权，窗口仍固定走满。
        # 圈主本次非白已关圈，此时与普通状态一样恢复三家响应。
        responders = tuple(index for index, other in enumerate(state.seats) if other.catch_play)
        return Transition(events, replace(
            state,
            seq=seq,
            window=_WINDOW_RESPONSE_PENG,
            turn_seat=seat,
            responding=responders if circle_active else _other_three(seat),
            trigger_seq=seq,
            last_discard=PublicDiscard(seat=seat, tile=action.tile, seq=seq),
        ))

    raise ValueError("摸牌窗口不允许该动作类型：{0!r}".format(type(action)))


def _resolve_gang(
    state: ProgressionState, seat: int, action: Gang, s: SeatProgression
) -> Transition:
    """暗杠/补杠：移牌、入副露、链+1、杠上补牌。抓打圈旗标不因杠改变。

    白不参与任何杠由合法性验证保证（analyze 同据 §1）；杠后补牌张数边界
    （最后 10 墩禁杠）同样在 analyze 侧把关（§6），此处只执行。
    """
    seq = state.seq + 1
    if action.kind is GangKind.CONCEALED:
        new_hand, new_drawn = _remove_n_from_hand(s, action.tile, 4)
        meld = MeldRecord(kind="gang", gang_kind="an", tiles=(action.tile,) * 4, from_seat=None)
        events = (_ev(seq, EVENT_KIND_GANG, seat, action.tile, (("kind", "an"),)),)
    elif action.kind is GangKind.ADDED:
        peng_index = next(
            (
                index
                for index, meld in enumerate(s.melds)
                if meld.kind == "peng" and meld.tiles[0].code == action.tile.code
            ),
            None,
        )
        if peng_index is None:
            raise ValueError("补杠缺少既有碰副露（合法性验证与推进状态不一致）")
        new_hand, new_drawn = _remove_n_from_hand(s, action.tile, 1)
        melds = list(s.melds)
        old = melds[peng_index]
        melds[peng_index] = MeldRecord(
            kind="gang", gang_kind="bu", tiles=(action.tile,) * 4, from_seat=old.from_seat
        )
        events = (_ev(seq, EVENT_KIND_GANG, seat, action.tile, (("kind", "bu"),)),)
    else:
        raise ValueError("摸牌窗口不允许明杠")
    chain_count, chain_piao = chain_after_gang(s.chain_count, s.chain_piao)
    new_seat = replace(
        s,
        hand=new_hand,
        drawn=new_drawn,
        melds=tuple(melds) if action.kind is GangKind.ADDED else s.melds + (meld,),
        chain_count=chain_count,
        chain_piao=chain_piao,
    )
    return Transition(events, replace(
        _replace_seat(state, seat, new_seat),
        seq=seq,
        window=_WINDOW_PENDING_DRAW,
        turn_seat=None,
        responding=(),
        trigger_seq=seq,
        last_discard=None,
        pending_draw=DrawRequest(
            seat=seat, replacement=True, seq=seq + 1,
            emit_event=True, consumes_wall=True,
        ),
    ))


def _resolve_peng_window(
    state: ProgressionState, choices: Tuple[Tuple[int, Action], ...]
) -> Transition:
    """碰（含明杠）窗口：普通三家、抓打圈仅圈主，收集窗口成员后裁决。

    两家及以上同时碰/明杠 → blocked（无官方优先级依据）。一家的碰/明杠
    生效，其余座位过；全部过后，只有下家不受抓打限制时才开吃窗口。
    pass 事件按固定座位序发出（选择数组顺序不影响结果）。
    """
    discarder = state.turn_seat
    if discarder is None or state.last_discard is None:
        raise ValueError("碰窗口缺少弃牌事实")
    responders = state.responding
    claims = [
        (seat, action)
        for seat, action in choices
        if isinstance(action, (Peng, Gang))
    ]
    if len(claims) >= 2:
        return Transition((), state, blocked=_MULTI_CLAIM_BLOCK)

    seq = state.seq
    events = []
    claim_seat = claims[0][0] if claims else None
    for responder in responders:
        if claim_seat is not None and responder == claim_seat:
            continue
        seq += 1
        events.append(_ev(seq, EVENT_KIND_PASS, responder))

    if not claims:
        next_seat = (discarder + 1) % SEAT_COUNT
        if any(other.catch_play for other in state.seats) and not state.seats[next_seat].catch_play:
            # v26：圈主不是下家时没有合法吃响应方，继续正常顺序摸牌。
            return Transition(tuple(events), replace(
                state,
                seq=seq,
                window=_WINDOW_PENDING_DRAW,
                turn_seat=None,
                responding=(),
                trigger_seq=seq,
                last_discard=None,
                pending_draw=DrawRequest(
                    seat=next_seat, replacement=False,
                    seq=seq + 1, emit_event=True, consumes_wall=True,
                ),
            ))
        # 普通状态或下家恰为圈主：碰窗口全过后，吃仅对下家开放。
        return Transition(tuple(events), replace(
            state,
            seq=seq,
            window=_WINDOW_RESPONSE_CHI,
            responding=(next_seat,),
        ))

    seat, action = claims[0]
    tile = state.last_discard.tile
    s = state.seats[seat]
    if isinstance(action, Peng):
        seq += 1
        events.append(_ev(seq, EVENT_KIND_PENG, seat, tile))
        new_hand, _ = _remove_n_from_hand(s, tile, 2)
        meld = MeldRecord(kind="peng", gang_kind=None, tiles=(tile,) * 3, from_seat=discarder)
        # v26：碰本身保留爆头与飘杠链；随后打白续飘、打非白断链关圈。
        # 不能在尚待弃牌的暂态暗牌上重算爆头，或在碰时先清空旧链。
        new_seat = replace(
            s, hand=new_hand, drawn=None, melds=s.melds + (meld,)
        )
        # 碰后、摸牌前的出牌窗口：drawn 为空（v1「碰后禁止胡牌」门禁的载体）。
        return Transition(tuple(events), replace(
            _replace_seat(state, seat, new_seat),
            seq=seq,
            window=_WINDOW_DRAW,
            turn_seat=seat,
            responding=(),
            trigger_seq=seq,
            last_discard=None,
        ))
    if isinstance(action, Gang):
        seq += 1
        events.append(_ev(seq, EVENT_KIND_GANG, seat, tile, (("kind", "ming"),)))
        new_hand, _ = _remove_n_from_hand(s, tile, 3)
        meld = MeldRecord(kind="gang", gang_kind="ming", tiles=(tile,) * 4, from_seat=discarder)
        chain_count, chain_piao = chain_after_gang(s.chain_count, s.chain_piao)
        new_seat = replace(
            s,
            hand=new_hand,
            drawn=None,
            melds=s.melds + (meld,),
            chain_count=chain_count,
            chain_piao=chain_piao,
        )
        return Transition(tuple(events), replace(
            _replace_seat(state, seat, new_seat),
            seq=seq,
            window=_WINDOW_PENDING_DRAW,
            turn_seat=None,
            responding=(),
            trigger_seq=seq,
            last_discard=None,
            pending_draw=DrawRequest(
                seat=seat, replacement=True, seq=seq + 1,
                emit_event=True, consumes_wall=True,
            ),
        ))
    raise ValueError("碰窗口不允许该动作类型：{0!r}".format(type(action)))


def _resolve_chi_window(
    state: ProgressionState, choices: Tuple[Tuple[int, Action], ...]
) -> Transition:
    """吃窗口（仅弃牌者下家）：吃 → 吃后出牌窗口；过 → 下家摸牌。"""
    discarder = state.turn_seat
    if discarder is None or state.last_discard is None:
        raise ValueError("吃窗口缺少弃牌事实")
    seat = state.responding[0] if state.responding else None
    if seat is None:
        raise ValueError("吃窗口缺少响应座位")
    action = _exactly_one(choices, seat)
    seq = state.seq + 1

    if isinstance(action, Pass):
        events = (_ev(seq, EVENT_KIND_PASS, seat),)
        return Transition(events, replace(
            state,
            seq=seq,
            window=_WINDOW_PENDING_DRAW,
            turn_seat=None,
            responding=(),
            trigger_seq=seq,
            last_discard=None,
            pending_draw=DrawRequest(
                seat=(discarder + 1) % SEAT_COUNT, replacement=False,
                seq=seq + 1, emit_event=True, consumes_wall=True,
            ),
        ))

    if isinstance(action, Chi):
        x = state.last_discard.tile
        partners = [t for t in action.tiles if t.code != x.code]
        s = state.seats[seat]
        hand = list(s.hand)
        for partner in partners:
            for index, held in enumerate(hand):
                if held.code == partner.code:
                    del hand[index]
                    break
            else:
                raise ValueError(
                    "吃组合 {0} 缺手牌 {1}（合法性验证与推进状态不一致）".format(
                        [t.code for t in action.tiles], partner.code
                    )
                )
        meld = MeldRecord(kind="chi", gang_kind=None, tiles=action.tiles, from_seat=discarder)
        # 与碰一致：吃不独立增加或清空链，续飘/断链由下一次弃牌统一处理。
        new_seat = replace(
            s, hand=tuple(hand), drawn=None, melds=s.melds + (meld,)
        )
        events = (_ev(
            seq, EVENT_KIND_CHI, seat, x,
            (("tiles", tuple(t.code for t in action.tiles)),),
        ),)
        return Transition(events, replace(
            _replace_seat(state, seat, new_seat),
            seq=seq,
            window=_WINDOW_DRAW,
            turn_seat=seat,
            responding=(),
            trigger_seq=seq,
            last_discard=None,
        ))

    raise ValueError("吃窗口不允许该动作类型：{0!r}".format(type(action)))
