"""每 game_id 的序号与快照同步状态机（官方适配器内部实现）。

核心语义（接口协议 §8 与模块规范）：

- 重复 seq 幂等忽略；
- seq 缺口、gap=true、未知关键事件 → 返回 NEEDS_REBUILD，由调用方用 seq=0 全量重建；
- 全量快照是规范真相：apply_full_snapshot 整体替换本地状态与公开历史；
- 未知事件类型采取"保守重建一次 + 学习忽略"策略：第一次出现按关键事件处理
  （权威快照会吸收其效果，不丢状态），之后同类型仅记录，避免重建风暴。
  这是工程决策：官方未提供未知事件的可忽略性判据（API 文档 §2.3）。
- 官方哨兵值（如事件 seat=-1）能通过 DTO 校验但会被 kernel 值对象拒绝：
  事务性预检中的投影构造将其转为 NEEDS_REBUILD，连续出现收敛到
  rebuild_loop 分类故障（安全，不会裸抛）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple

from hangma_bot.kernel.actions import WindowKey
from hangma_bot.kernel.config import TimingConfig
from hangma_bot.kernel.observation import PlayerObservation, PublicEvent

from . import projector
from .dto import ParsedEvent, ParsedSnapshot, StateResponse
from .errors import DtoError

# 官方门户已确认处理的事件类型（API 文档 §2.3）；新增官方事件进入"未知"路径。
KNOWN_EVENT_TYPES = frozenset({
    "tile_drawn",
    "tile_discarded",
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

    @property
    def has_snapshot(self) -> bool:
        return self.snapshot is not None

    def apply_full_snapshot(self, snapshot: ParsedSnapshot, *, finished: bool = False) -> None:
        """seq=0 权威快照整体替换：历史重置，序号对齐。"""

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
            if event.type == "game_ended":
                self.finished = True
        self._observation_cache = None  # 历史变化使观察缓存失效
        return SyncResult(SyncDecision.ACCEPTED, (), tuple(duplicates))

    def note_rebuild_absorbed(self, event_type: str) -> None:
        """权威重建完成后登记"已吸收的未知事件类型"，后续不再触发重建。"""

        self.learned_event_types.add(event_type)

    def current_window(self):
        """当前权威快照判定的我方动作窗口；无快照或无动作权时为 None。"""

        if self.snapshot is None:
            return None
        return projector.detect_window(self.snapshot, self.timing, self.game_id)

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

