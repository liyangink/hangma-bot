"""从官方圈主字段或可见事件确认当前抓打圈归属；与爆头、财飘计番独立。

依据：2026-09-09抓取的v27指南（v26圈主豁免与快照字段修订）。
任意弃白重开当前圈，最新弃白者的下一次非白弃牌结束它；摸牌和杠不结束。
这描述可观察的权限与寿命，不猜测服务端是否保存已经被覆盖的旧圈。
"""

from dataclasses import dataclass
from typing import Optional

from hangma_bot.kernel.observation import PlayerObservation

from .special_rules import is_passive_observation_event


@dataclass(frozen=True)
class CatchPlayContext:
    """本窗口的抓打圈事实；未知归属不能当成本人圈主使用。"""

    active: bool  # 当前动作上下文中的有效圈；终局为 False，官方原标记仍保存在观察中
    owner_seat: Optional[int]  # 最新开圈弃白者，座位 0—3；证据不足或已结束时为空
    started_seq: Optional[int]  # 最新开圈弃白的事件序号；同座续白也更新，非时间戳
    issue: Optional[str] = None  # 活跃但归属无法核验的原因；不包含协议私密信息
    source: Optional[str] = None  # official-snapshot及其连续后缀，或旧版事件/白板对账；未知时为空

    def restricts(self, seat: int) -> bool:
        """是否应用其他家摸切/禁吃碰约束；圈主未知时保守限制。"""
        return self.active and self.owner_seat != seat


def analyze_catch_play(observation: PlayerObservation) -> CatchPlayContext:
    """核对连续可见后缀，返回原始圈标记与能证明的最新开圈座位。

    仅扫描事件序号、种类、公开弃牌；不读取他家手牌或推演牌型。
    快照标记只覆盖 snapshot_seq：即使该时点无圈，也须消费后续开圈事件。
    连续后缀不足时，仅在当前权威快照的全部白板弃牌均能与本单局历史
    对账时恢复；否则保持圈主未知，不能把旧无圈状态当作当前不受限。
    """
    active = observation.rule_state.catch_play
    current_seq = observation.consumed_seq
    if current_seq is None:
        current_seq = observation.snapshot_seq
    if observation.phase in ("deal", "settled", "finished", "ended", "match_end"):
        return CatchPlayContext(False, None, None)
    if not active and current_seq == observation.snapshot_seq:
        return CatchPlayContext(False, None, None)

    official = _from_official_owner(observation)
    if official is not None and official.issue is None:
        return official
    context = _from_contiguous_suffix(observation)
    if official is not None:
        # 官方快照之后的冲突/缺口不能用快照前的旧开圈覆盖。只有后续新弃白
        # 到当前水位连续，才足以重新证明权限；旧牌河对账同样不能降格替代它。
        if context.started_seq is not None and context.started_seq > observation.snapshot_seq:
            return context
        return official
    if context.owner_seat is not None:
        return context
    return _from_white_accounting(observation) or context


def _from_official_owner(observation: PlayerObservation) -> Optional[CatchPlayContext]:
    """从快照圈态推进连续后缀；有圈须知圈主，无圈也可以作为可靠起点。"""
    active = observation.rule_state.catch_play
    # 无圈快照中即使带旧圈主值，也不保留该座权限；后续弃白重新建立归属。
    owner = observation.rule_state.catch_play_owner_seat if active else None
    if active and owner is None:
        return None
    current_seq = observation.consumed_seq
    if current_seq is None:
        current_seq = observation.snapshot_seq
    expected = observation.snapshot_seq + 1
    started_seq = None
    source = "official-snapshot"

    def unknown(reason: str) -> CatchPlayContext:
        return CatchPlayContext(True, None, None, reason)

    for event in observation.public_history:
        if event.seq <= observation.snapshot_seq:
            continue
        if event.seq != expected or event.seq > current_seq:
            return unknown("官方圈主快照之后存在序号缺口，不能沿用旧圈主权限")
        expected += 1
        source = "official-snapshot+continuous-events"
        if event.kind == "tile_discarded":
            if event.seat is None or len(event.tiles) != 1:
                return unknown("圈主快照之后的弃牌缺少座位或牌值")
            if event.tiles[0] == observation.rule_state.wealth_god:
                active, owner, started_seq = True, event.seat, event.seq
            elif event.seat == owner:
                active, owner, started_seq = False, None, None
            if event.catch_play is not None and event.catch_play != active:
                return unknown("圈主快照与连续弃牌的抓打标记冲突")
        elif event.kind in ("tile_drawn", "gang", "chi", "peng") or is_passive_observation_event(event):
            continue
        else:
            return unknown("圈主快照之后遇到未知规则动作，不能沿用旧圈主权限")
    if expected != current_seq + 1:
        return unknown("官方圈主快照与当前水位之间缺少连续事件")
    return CatchPlayContext(active, owner, started_seq, source=source)


def _from_contiguous_suffix(observation: PlayerObservation) -> CatchPlayContext:
    """最新弃白到当前水位连续即可证明归属；无需补齐更早前缀。"""

    def unknown(reason: str) -> CatchPlayContext:
        return CatchPlayContext(True, None, None, reason)

    history = observation.public_history
    expected = observation.consumed_seq
    if expected is None:
        expected = observation.snapshot_seq
    if not history or history[-1].seq != expected:
        return unknown("抓打圈活跃，但缺少对齐当前水位的开圈事件后缀")

    discarded_nonwhite = set()
    for event in reversed(history):
        if event.seq != expected:
            return unknown("抓打圈开圈事件之后存在序号缺口，圈主未知")
        expected -= 1
        if event.kind == "tile_discarded":
            if event.seat is None or len(event.tiles) != 1:
                return unknown("公开弃牌缺少座位或牌值，无法核验圈主")
            if event.catch_play is False:
                return unknown("当前抓打标记与连续后缀中的关圈事件冲突")
            if event.tiles[0] == observation.rule_state.wealth_god:
                if event.seat in discarded_nonwhite:
                    return unknown("最近弃白者随后已弃非白，与当前抓打标记冲突")
                return CatchPlayContext(True, event.seat, event.seq, source="continuous-events")
            discarded_nonwhite.add(event.seat)
        elif event.kind in ("tile_drawn", "gang", "chi", "peng"):
            # 吃碰动作是否可达由权威响应窗口及规则族核验；动作本身不换圈。
            continue
        elif not is_passive_observation_event(event):
            return unknown("开圈前遇到跨单局、未知或未确认自动动作，圈主未知")
    return unknown("当前连续历史中没有开圈弃白，圈主未知")


def _from_white_accounting(observation: PlayerObservation) -> Optional[CatchPlayContext]:
    """用当前快照排除所有未见弃白；缺一张白的事件都不能恢复圈主。

    财神不能被吃碰杠，白板弃牌永久留在对应牌河。每座白板总数与当前
    单局历史中的不同弃白事件完全一致，便能证明没有漏记换圈；快照中
    最新弃白者的牌河仍以白结尾，证明其尚未以非白结束当前圈。
    只用于水位相同的权威快照，不用过时牌河为增量观察推断身份。
    """
    current_seq = observation.consumed_seq
    if current_seq is not None and current_seq != observation.snapshot_seq:
        return None
    known_whites = [0, 0, 0, 0]
    river_cursors = [0, 0, 0, 0]
    last_white = None
    closed_after_white = False
    previous_seq = -1
    for event in observation.public_history:
        if event.seq <= previous_seq or event.seq > observation.snapshot_seq:
            return None  # 重复序号不能伪装成另一张白板，未来事件也不能参与证明。
        previous_seq = event.seq
        if event.kind == "tile_discarded":
            if event.seat is None or len(event.tiles) != 1:
                return None
            river = observation.discards[event.seat]
            cursor = river_cursors[event.seat]
            while cursor < len(river) and river[cursor] != event.tiles[0]:
                cursor += 1
            if cursor == len(river):
                return None  # 可见弃牌必须与该座权威牌河顺序兼容，不能混用别手历史。
            river_cursors[event.seat] = cursor + 1
            if event.tiles[0] == observation.rule_state.wealth_god:
                if event.catch_play is False:
                    return None
                known_whites[event.seat] += 1
                last_white = event
                closed_after_white = False
            elif last_white is not None and (
                event.catch_play is False or event.seat == last_white.seat
            ):
                closed_after_white = True
        elif event.kind in ("tile_drawn", "gang", "chi", "peng", "pass"):
            continue
        elif event.kind == "timeout" and event.detail_kind in ("response", "discard"):
            # 自动动作通知不替代快照牌河；所有已执行弃白仍必须逐张对上。
            continue
        else:
            return None
    if last_white is None or closed_after_white:
        return None
    actual_whites = [
        sum(tile == observation.rule_state.wealth_god for tile in river)
        for river in observation.discards
    ]
    if known_whites != actual_whites:
        return None
    river = observation.discards[last_white.seat]
    if not river or river[-1] != observation.rule_state.wealth_god:
        return None
    return CatchPlayContext(True, last_white.seat, last_white.seq, source="snapshot-white-accounting")
