"""每 game_id 的序号与快照同步状态机（官方适配器内部实现）。

核心语义（接口协议 §8 与模块规范）：

- 重复 seq 幂等忽略；
- seq 缺口、gap=true、未知关键事件 → 返回 NEEDS_REBUILD，由调用方用 seq=0 全量重建；
- 全量快照是规范真相：apply_full_snapshot 整体替换本地状态与公开历史；
  唯一例外是跨重建存活的触发弃牌记忆 _response_trigger（(round_no, seq,
  牌码, 座位)）：测试房响应阶段 last_discard 为纯牌码字符串（无 seq）且
  每次交付前全量重建清空事件历史，该记忆是响应窗口 WindowKey.trigger_seq
  身份稳定的兜底来源（集成阶段第二轮加固 R2）；仅在局号变化时重置。
- 增量优先的摸牌窗口（游标纪律修复）：客户端局面 = 快照 + 后续增量事件
  （指南 v14 §2.1），事件流只含自己的摸牌。本人 tile_drawn 是事件流最后
  一条时，摸牌窗口直接由增量事实送达（incremental_draw_window /
  incremental_draw_observation），不再逐批 seq=0 刷新；快照刷新只在事件
  流无法推导权威事实时发生（见 events_need_authoritative_refresh 的
  「为什么」），因此增量送达时 my_hand 与最后快照必然一致（本人改牌动作
  全部落入刷新触发集），无需本地推演手牌。
- 未知事件类型采取"保守重建一次 + 学习忽略"策略：第一次出现按关键事件处理
  （权威快照会吸收其效果，不丢状态），之后同类型仅记录，避免重建风暴。
  这是工程决策：官方未提供未知事件的可忽略性判据（API 文档 §2.3）。
- 官方哨兵值（如事件 seat=-1）能通过 DTO 校验但会被 kernel 值对象拒绝：
  事务性预检中的投影构造将其转为 NEEDS_REBUILD，连续出现收敛到
  rebuild_loop 分类故障（安全，不会裸抛）。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Optional, Tuple

from hangma_bot.kernel.actions import Tile, WindowKey, WindowPhase
from hangma_bot.kernel.config import TimingConfig
from hangma_bot.kernel.observation import PlayerObservation, PublicDiscard, PublicEvent

from . import projector
from .dto import ParsedEvent, ParsedSnapshot, StateResponse
from .errors import DtoError

# 官方门户已确认处理的事件类型（API 文档 §2.3 与 2026-09 测试房间实测）；
# 新增官方事件进入"未知"路径。pass 是响应窗口他家弃权事件：实测牌谱中
# pass 事件推进权威 seq（182->183/184/185），缺它会把高频常规事件误判为
# 未知关键事件，触发全量重建抖动（集成阶段第二轮 R3）。
KNOWN_EVENT_TYPES = frozenset({
    "tile_drawn",
    "tile_discarded",
    "pass",
    "chi",
    "peng",
    "gang",
    "timeout",
    "round_ended",
    "game_ended",
})


class SyncDecision(Enum):
    """一次增量应用后的同步决策。"""

    ACCEPTED = "accepted"
    NEEDS_REBUILD = "needs_rebuild"


@dataclass
class SyncResult:
    """增量应用结果；reasons 供审计记录，不含任何敏感信息。"""

    decision: SyncDecision
    reasons: Tuple[str, ...] = ()
    ignored_duplicate_seqs: Tuple[int, ...] = ()


class ProtocolSyncState:
    """单个官方场次的 seq 与权威快照状态。

    按"每场一个异步任务"的并发模型使用（API 文档 §5.5），
    由持有该场的任务独占访问。
    """

    def __init__(self, game_id: str, timing: TimingConfig) -> None:
        self.game_id = game_id
        self.timing = timing
        self.last_seq = 0
        self.snapshot = None  # Optional[ParsedSnapshot]
        self.history = []  # PublicEvent 列表；全量快照替换时重置
        self.finished = False
        self.learned_event_types = set()  # 重建后学习到的可忽略未知事件类型
        self._observation_cache = None  # 延迟构造的权威观察缓存
        # 跨重建存活的触发弃牌记忆 (round_no, seq, 牌码, 座位)。
        # 应用全量快照不清空它（仅局号变化时重置）：全量重建会清空事件
        # 历史，而测试房响应阶段 last_discard 是纯牌码字符串（无 seq），
        # 此记忆是纯牌码场景下 WindowKey.trigger_seq 身份稳定的唯一来源
        # （集成阶段第二轮加固 R2）。来源：apply_events 见到 tile_discarded、
        # current_window 三级解析命中。
        self._response_trigger: Optional[Tuple[int, int, str, int]] = None

    @property
    def has_snapshot(self) -> bool:
        return self.snapshot is not None

    def apply_full_snapshot(self, snapshot: ParsedSnapshot, *, finished: bool = False) -> None:
        """seq=0 权威快照整体替换：历史重置，序号对齐。

        触发弃牌记忆跨重建存活，仅当局号变化时重置（新一轮弃牌出现前
        旧局记忆不得串局参与第三级解析）。
        """

        if (
            self._response_trigger is not None
            and self._response_trigger[0] != snapshot.round_no
        ):
            self._response_trigger = None  # 局号变化：旧局记忆失效
        self.snapshot = snapshot
        self.last_seq = snapshot.seq
        self.history = []
        self._observation_cache = None
        self.finished = self.finished or finished

    def apply_events(self, events, *, gap: bool = False) -> SyncResult:
        """按序归并增量事件；返回同步决策，绝不抛出网络/协议异常。

        事务性：先对整批做连续性与未知事件预检，任一失败则整批拒绝
        （NEEDS_REBUILD）且不应用任何事件——避免"部分应用后重建失败"
        留下与权威状态不一致的本地游标。
        """

        duplicates = []
        if gap:
            return SyncResult(SyncDecision.NEEDS_REBUILD, ("gap=true",))
        if self.snapshot is None:
            # 尚无权威快照：任何增量都不可靠，直接重建
            return SyncResult(SyncDecision.NEEDS_REBUILD, ("no_snapshot",))
        ordered = sorted(events, key=lambda e: e.seq)
        expected = self.last_seq
        projected = []
        for event in ordered:
            if event.seq <= expected:
                duplicates.append(event.seq)  # 重复 seq 幂等忽略
                continue
            if event.seq != expected + 1:
                return SyncResult(
                    SyncDecision.NEEDS_REBUILD,
                    ("seq_gap:{}".format(event.seq),),
                    tuple(duplicates),
                )
            if event.type not in KNOWN_EVENT_TYPES and event.type not in self.learned_event_types:
                # 未知关键事件：保守重建一次，重建成功后学习忽略该类型
                return SyncResult(
                    SyncDecision.NEEDS_REBUILD,
                    ("unknown_event:{}".format(event.type),),
                    tuple(duplicates),
                )
            try:
                # 投影构造在预检内完成：构造失败（非法牌码/座位等）整批
                # 拒绝且游标不推进，保持事务性
                projected.append((event, projector.public_event(event)))
            except (ValueError, DtoError) as exc:
                return SyncResult(
                    SyncDecision.NEEDS_REBUILD,
                    ("projection_failed:" + str(exc)[:80],),
                    tuple(duplicates),
                )
            expected = event.seq
        for event, public in projected:  # 预检全通过后统一应用
            self.history.append(public)
            self.last_seq = event.seq
            if public.kind == "tile_discarded":
                discard = self._event_discard_fact(public)
                if discard is not None:
                    # 新一轮弃牌出现：覆盖跨重建触发记忆（R2 加固来源 (a)）
                    self._response_trigger = (self.snapshot.round_no,) + discard
            if event.type == "game_ended":
                self.finished = True
        self._observation_cache = None  # 历史变化使观察缓存失效
        return SyncResult(SyncDecision.ACCEPTED, (), tuple(duplicates))

    def note_rebuild_absorbed(self, event_type: str) -> None:
        """权威重建完成后登记"已吸收的未知事件类型"，后续不再触发重建。"""

        self.learned_event_types.add(event_type)

    def events_need_authoritative_refresh(self, events) -> bool:
        """增量事件是否需要紧跟一次权威快照刷新才能继续投递窗口。

        为什么（官方依据，指南 v14 §2.1）：快照是规范真相，阶段
        （phase/responding_seats/turn）、神位状态（baotou/chain_count/
        catch_play）与本人手牌张数的权威表达只在快照中出现；事件流只含
        自己的摸牌与公开动作。以下事件改变无法从增量可靠推导的权威事实：

        - 任意 tile_discarded：响应窗口（peng/chi 成员与相位）随弃牌开启，
          且本人爆头/动作链/抓打圈状态都只在弃牌动作上变化（无对应增量
          字段）——必须刷新才能给出合法窗口与新鲜神位状态；
        - 任意 timeout：官方自动代打（自动胡/自动出最右一张/自动弃权）
          改变的手牌与阶段无法从事件流推导；
        - 本人 chi/peng/gang：副露消耗的本人手牌张数与牌面不进入事件流，
          不刷新则后续摸牌窗口的 my_hand 不可信；
        - 本人 tile_drawn 缺牌码：畸形事件无法构造 drawn_tile，快照兜底。

        其余事件（他家摸牌、pass、round_ended、game_ended）不触发刷新：
        摸牌窗口由增量事实直接送达（游标纪律目标：正常事件流零重建）。
        """

        my_seat = self.snapshot.seat if self.snapshot is not None else None
        for event in events:
            if event.type in ("tile_discarded", "timeout"):
                return True
            if event.type in ("chi", "peng", "gang") and event.seat == my_seat:
                return True
            if (
                event.type == "tile_drawn"
                and event.seat == my_seat
                and len(event.tiles) != 1
            ):
                return True
        return False

    def incremental_draw_window(self):
        """增量路径判定的本人摸牌窗口；事件流末条不是本人摸牌时返回 None。

        官方依据（指南 v14 §2.1）：draw 且 turn==seat 可出牌/胡/杠；事件流
        只含自己的摸牌；本人摸牌事件产生后，直到本人出牌/超时前不会有任何
        其他事件。因此「事件流最后一条是本人 tile_drawn」等价于「当前处于
        本人摸牌窗口」。触发序号直接取摸牌事件 seq：与快照路径同值（摸牌
        窗口期间无其他事件推进水位），且是真正的触发事件序号。
        """

        snapshot = self.snapshot
        if snapshot is None or self.finished or snapshot.seat < 0:
            return None
        if not self.history:
            return None
        last = self.history[-1]
        if (
            last.kind != "tile_drawn"
            or last.seat != snapshot.seat
            or len(last.tiles) != 1
        ):
            return None
        return projector.DetectedWindow(
            window_key=WindowKey(
                game_id=self.game_id,
                round_no=snapshot.round_no,
                trigger_seq=last.seq,
                phase=WindowPhase.DRAW,
                seat=snapshot.seat,
            ),
            timeout_seconds=self.timing.discard_timeout_sec,
            trigger_projection_note=None,
            trigger_discard=None,
        )

    def incremental_draw_observation(self) -> Optional[PlayerObservation]:
        """本人摸牌窗口的增量观察：快照权威字段 + 增量摸牌/弃牌事实。

        只允许在 incremental_draw_window 命中时使用。为什么 my_hand 可以
        直接沿用快照：本人一切改牌动作（弃牌/副露/超时）都在
        events_need_authoritative_refresh 的刷新触发集内，摸牌事件成为事件
        流末条时，自最后快照以来本人未发生任何改牌动作，快照 my_hand 即
        当前手牌；drawn_tile 取本人摸牌事件牌码（指南 v14 §2.1：事件流
        只含自己的摸牌）。牌河按事件流追加公开弃牌，保持估算口径与真实
        牌河一致；phase/turn/responding_seats 由摸牌语义推导（draw 阶段、
        本人行动、无响应成员）。
        """

        base = self.current_observation()
        if base is None or self.snapshot is None or not self.history:
            return None
        last = self.history[-1]
        if (
            last.kind != "tile_drawn"
            or last.seat != self.snapshot.seat
            or len(last.tiles) != 1
        ):
            return None
        drawn = last.tiles[0]
        # 最新弃牌以事件流增量事实为准；无增量弃牌时退回快照投影
        fact = self._last_discarded_event()
        if fact is not None:
            seq, code, seat = fact
            last_discard = PublicDiscard(seat=seat, tile=Tile(code), seq=seq)
        else:
            last_discard = base.last_discard
        discards = base.discards
        rows = None
        for event in self.history:
            if event.kind != "tile_discarded" or len(event.tiles) != 1:
                continue
            if rows is None:
                rows = [list(row) for row in discards]
            rows[event.seat].append(event.tiles[0])
        if rows is not None:
            discards = tuple(tuple(row) for row in rows)
        return replace(
            base,
            phase="draw",
            turn_seat=self.snapshot.seat,
            responding_seats=(),
            drawn_tile=drawn,
            last_discard=last_discard,
            discards=discards,
        )

    def current_window(self):
        """当前权威快照判定的我方动作窗口；无快照或无动作权时为 None。

        响应窗口触发序号四级解析（projector._response_trigger）：事件流
        tile_discarded -> 结构化 last_discard -> 跨重建记忆 -> 快照 seq。
        解析命中（tier-1/2/3）时把触发弃牌事实写回跨重建记忆
        （R2 加固来源 (b)：纯牌码场景下即使本次命中，也要为后续
        重建后的事件历史空窗期保存稳定身份）。
        """

        if self.snapshot is None:
            return None
        detected = projector.detect_window(
            self.snapshot,
            self.timing,
            self.game_id,
            event_stream_discard=self._last_discarded_event(),
            remembered_trigger=self._response_trigger,
        )
        if detected is not None and detected.trigger_discard is not None:
            self._response_trigger = (
                self.snapshot.round_no,
            ) + detected.trigger_discard
        return detected

    def _last_discarded_event(self) -> Optional[Tuple[int, str, int]]:
        """已应用事件流中最近一次弃牌事实 (seq, 牌码, 座位)；无记录时为 None。

        PublicEvent.kind 保持官方事件名原样（projector.public_event），
        故直接以官方名 "tile_discarded" 匹配。形状不合规（缺座位或
        非单牌）时不采用——不伪造弃牌事实。
        """

        for event in reversed(self.history):
            if event.kind != "tile_discarded":
                continue
            if not isinstance(event.seat, int) or isinstance(event.seat, bool):
                continue
            if len(event.tiles) != 1:
                continue
            # PublicEvent.tiles 元素是 kernel Tile 值对象，记忆存规范牌码
            # 字符串（与 ParsedSnapshot.last_discard 纯牌码形态同构）
            return (event.seq, event.tiles[0].code, event.seat)
        return None

    @staticmethod
    def _event_discard_fact(public) -> Optional[Tuple[int, str, int]]:
        """事件流弃牌 PublicEvent 转记忆事实 (seq, 牌码, 座位)；形状不合规为 None。"""

        if not isinstance(public.seat, int) or isinstance(public.seat, bool):
            return None
        if len(public.tiles) != 1:
            return None
        return (public.seq, public.tiles[0].code, public.seat)

    def current_observation(self) -> Optional[PlayerObservation]:
        """当前权威观察（构造后缓存）；public_history 为最近全量快照之后的连续增量事件。"""

        if self.snapshot is None:
            return None
        if self._observation_cache is None:
            self._observation_cache = projector.observation(
                self.snapshot, tuple(self.history), self.game_id
            )
        return self._observation_cache

    def final_scores(self) -> Optional[Tuple[int, int, int, int]]:
        """终局积分，固定按座位 0-3；仅终局快照有效。"""

        if self.snapshot is None:
            return None
        return self.snapshot.scores

