"""官方场次的串行观察同步状态机。

当前牌面来自权威快照及可证明的后续增量；当前单局已收到的可见历史
独立保存，不因快照刷新被删除，也不重复应用到牌面。未知关键事件、序号
缺口与冲突重复须恢复；恢复不能补造缺失历史或自动学习未知事件语义。
所有窗口和提交复核使用 current_observation 的同一份不可变观察。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Optional, Tuple

from hangma_bot.kernel.actions import Action, Tile, WindowKey, WindowPhase
from hangma_bot.kernel.config import TimingConfig
from hangma_bot.kernel.observation import PlayerObservation, PublicDiscard, PublicEvent
from hangma_bot.hangma.observation_rules import (
    enrich_observation, reconcile_observation, recompute_draw_rule_state, compare_observation_transition,
)

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
        self.history = []  # 当前单局已接收的可见历史；快照吸收不删除
        self.history_complete = False
        self.history_origin_known = False
        # 排除式下界：本手需核对的已知历史范围为 (floor, snapshot.seq]。
        # 中途首次接入取当前水位作锚点，但 origin_known=False 保留未知前缀。
        self.history_floor_seq: Optional[int] = None
        self._history_query_floor = 0  # 补领已放弃的排除式水位；不代表原事件已收到
        self._observation_issues = set()
        self.last_transition_checks = ()  # 本次快照与可推导前态的核对结果，供审计
        self._trigger_is_estimated = False
        self.finished = False
        self._observation_cache = None  # 延迟构造的权威观察缓存
        # 只保留本场最近观察及一个已明确接受的动作前态；规则模块核对新
        # 快照后才能衔接派生事实，不把HTTP成功当作已收到官方动作事件。
        self._fact_observation: Optional[PlayerObservation] = None
        self._confirmed_action: Optional[Tuple[PlayerObservation, Action]] = None
        # 跨重建存活的触发弃牌记忆 (round_no, seq, 牌码, 座位)。
        # 应用全量快照不清空它（仅局号变化时重置）：全量重建会清空事件
        # 历史，而测试房响应阶段 last_discard 是纯牌码字符串（无 seq），
        # 此记忆是纯牌码场景下 WindowKey.trigger_seq 身份稳定的唯一来源
        # （集成阶段第二轮加固 R2）。来源：apply_events 见到 tile_discarded、
        # current_window 三级解析命中。
        self._response_trigger: Optional[Tuple[int, int, str, int]] = None
        # 本人是否已对当前响应周期表态（F2，2026-09-05 取证修复）：官方
        # responding_seats 不随 pass 收缩（取证：全员 pass 后快照仍列
        # [1,2,3]），"已表态"只能由本人 pass 事件回显（pass 事件带座位，
        # 实证 pass@4 s2）或本人 POST pass 接受回执得知。新弃牌/新局/draw
        # 阶段重置。
        self._self_responded = False
        self._frozen_response_trigger = None

    @property
    def has_snapshot(self) -> bool:
        return self.snapshot is not None

    def history_query_seq(self) -> int:
        """下一次普通查询顺带补当前单局缺史；当前状态水位 last_seq 不回退。

        seq=0 只能取快照，不能领取 seq1；未知前缀不猜起点。落后快照超过
        官方256条保留范围的缺口不反复追逐，缺口账本仍如实保留。
        """
        if self.snapshot is None or self.finished:
            return self.last_seq
        for start, end in self.history_missing_ranges():
            cursor = max(start - 1, self._history_query_floor, 1)
            if cursor < end and self.last_seq - cursor <= 256:
                return cursor
        return self.last_seq

    def abandon_history_query(self, through_seq: int) -> None:
        """服务端未能补领时跳过该覆盖范围；不清缺口、不谎报历史完整。"""
        self._history_query_floor = max(self._history_query_floor, through_seq)

    def recover_snapshot_history(
        self, events: Tuple[ParsedEvent, ...], *, after_seq: int, round_no: int,
    ) -> Tuple[ParsedEvent, ...]:
        """验证旧游标批次并只补快照已吸收的部分，返回其后的正常增量。

        不重放手牌/牌河，不重建已交付窗口身份。断链、未知旧事件、冲突、
        越界或私有牌由 DtoError 交会话恢复；跨单局需权威快照证明归属。
        """
        if self.snapshot is None or self.snapshot.round_no != round_no:
            raise DtoError("补史请求与当前单局不一致")
        if not 0 < after_seq < self.last_seq:
            raise DtoError("补史游标必须早于已消费状态水位")
        expected = after_seq
        unique = {}
        retained = {event.seq: event for event in self.history}
        for event in sorted(events, key=lambda item: item.seq):
            if event.seq in unique:
                if unique[event.seq] != event:
                    raise DtoError("补史响应存在冲突重复")
                continue
            if event.seq != expected + 1:
                raise DtoError("补史响应存在序号缺口")
            if event.seq in retained and retained[event.seq] != projector.public_event(event):
                raise DtoError("补史响应与已消费事件冲突")
            unique[event.seq] = event
            expected = event.seq
        old = tuple(event for event in unique.values() if event.seq <= self.snapshot.seq)
        self.merge_history(old, round_no=round_no)
        # 已消费的快照后增量也可能随旧游标再次返回，只核对，不让它们再次
        # 触发刷新、动作时钟或窗口交付。真正的新事件仍交 apply_events 校验。
        return tuple(event for event in unique.values() if event.seq > self.last_seq)

    def apply_full_snapshot(self, snapshot: ParsedSnapshot, *, finished: bool = False, events=()) -> None:
        """快照替换桌面，保留同单局已接收历史；缺失历史不能由快照补造。"""
        previous = self.snapshot
        previous_round_end = max((e.seq for e in self.history if e.kind == "round_ended"), default=None)
        new_round = previous is None or previous.round_no != snapshot.round_no
        if previous is not None and snapshot.seq < self.last_seq:
            raise DtoError("snapshot.seq 早于已消费水位")
        # 全量报文可同时带事件。先校验整批，再仅补历史。
        # 快照前事件绝不能再推进手牌/牌河；快照水位不代表事件已经接收。
        incoming = {}
        for event in events:
            if event.seq > snapshot.seq:
                raise DtoError("快照附带事件超出快照水位")
            public = projector.public_event(event)
            if public.kind == "tile_drawn" and public.seat != snapshot.seat and public.tiles:
                public = replace(public, tiles=())
            if public.seq in incoming and incoming[public.seq] != public:
                raise DtoError("快照附带事件存在冲突重复")
            incoming[public.seq] = public
        if (not finished and snapshot.phase not in ("finished", "settled")
                and any(event.kind == "game_ended" for event in incoming.values())):
            raise DtoError("活动快照与场次终局事件矛盾")
        scope_unknown = False
        if new_round:
            # 事件没有单局标识：只能用公开终局边界隔开，不能把上一手混进新手。
            endings = sorted(seq for seq, event in incoming.items() if event.kind == "round_ended")
            terminal = finished or snapshot.phase in ("finished", "settled")
            if endings:
                boundary = (endings[-2] if len(endings) > 1 else None) if terminal else endings[-1]
                if boundary is not None:
                    incoming = {seq: event for seq, event in incoming.items() if seq > boundary}
                elif terminal:
                    # 终态只有一个终局标识，终局之前的事件不能可靠归属。
                    incoming = {seq: event for seq, event in incoming.items() if seq >= endings[-1]}
                    scope_unknown = True
            elif incoming:
                initial_contiguous = (previous is None and snapshot.round_no == 1
                                      and min(incoming) == 1 and len(incoming) == snapshot.seq)
                if not initial_contiguous:
                    incoming = {}
                    scope_unknown = True
        retained = {} if new_round else {event.seq: event for event in self.history}
        for seq, public in incoming.items():
            if seq in retained and retained[seq] != public:
                raise DtoError("快照附带事件与已接收历史冲突")
        old_trigger = self._response_trigger
        self.last_transition_checks = ()
        if not new_round:
            retained.update(incoming)
            self.history = [retained[seq] for seq in sorted(retained)]
        if previous is not None and not new_round and not finished:
            before = replace(projector.observation(previous, tuple(e for e in self.history if e.seq <= previous.seq), self.game_id), consumed_seq=previous.seq)
            after = replace(projector.observation(snapshot, tuple(self.history), self.game_id), consumed_seq=snapshot.seq)
            self.last_transition_checks = compare_observation_transition(
                before, tuple(e for e in self.history if e.seq > previous.seq), after)
            self._observation_issues.update(check for check in self.last_transition_checks if check.startswith("god_mismatch:"))
        if new_round:
            self._history_query_floor = 0
            self.history = [incoming[seq] for seq in sorted(incoming)]
            self._fact_observation = None
            self._confirmed_action = None
            self._observation_issues.clear()
            # 无弃牌/副露、无链且处于发牌或庄家初始摸牌，才可证明单局起点。
            self.history_complete = (
                not any(snapshot.discards) and not any(snapshot.melds_raw)
                and snapshot.god_chain_count == 0
                and (snapshot.phase == "deal" or
                     (snapshot.phase == "draw" and snapshot.turn == snapshot.dealer))
            )
            initial_position = self.history_complete
            origin = None
            raw_endings = sorted({e.seq for e in events if e.type == "round_ended"})
            terminal = finished or snapshot.phase in ("finished", "settled")
            if raw_endings and not terminal:
                origin = raw_endings[-1]
            elif len(raw_endings) > 1 and terminal:
                origin = raw_endings[-2]
            elif previous is None and snapshot.round_no == 1 and incoming and min(incoming) == 1 and len(incoming) == snapshot.seq:
                origin = 0
            if (origin is None and previous is not None
                    and snapshot.round_no == previous.round_no + 1):
                if previous_round_end is not None:
                    origin = previous_round_end
            self.history_origin_known = origin is not None or initial_position
            self.history_floor_seq = origin if origin is not None else snapshot.seq
        elif snapshot.seq > self.last_seq:
            covered = {seq for seq in incoming if self.last_seq < seq <= snapshot.seq}
            if len(covered) != snapshot.seq - self.last_seq:
                self.history_complete = False
                self._observation_issues.add("history_gap_snapshot")

        if scope_unknown:
            self.history_complete = False
            self._observation_issues.add("new_round_event_scope_unknown")

        # 结构化触发序号能证明新周期；纯牌码则结合牌河变化识别同座同码再弃。
        raw = snapshot.last_discard
        new_trigger = None
        if isinstance(raw, tuple):
            new_trigger = (snapshot.round_no, raw[2], raw[1], raw[0])
            self._trigger_is_estimated = False
        elif isinstance(raw, str) and snapshot.phase in ("response_peng", "response_chi"):
            same_board = previous is not None and previous.discards == snapshot.discards and previous.melds_raw == snapshot.melds_raw
            if (old_trigger is not None and old_trigger[0] == snapshot.round_no
                    and old_trigger[2:] == (raw, snapshot.turn) and same_board):
                new_trigger = old_trigger
            else:
                matching = self._last_discarded_event()
                if matching is not None and matching[1:] == (raw, snapshot.turn) and matching[0] > (old_trigger[1] if old_trigger else -1):
                    new_trigger = (snapshot.round_no,) + matching
                    self._trigger_is_estimated = False
                else:
                    new_trigger = (snapshot.round_no, snapshot.seq, raw, snapshot.turn)
                    self._trigger_is_estimated = True
        frozen = self._frozen_response_trigger
        same_cycle = (previous is not None and previous.round_no == snapshot.round_no
                      and previous.discards == snapshot.discards
                      and previous.melds_raw == snapshot.melds_raw
                      and snapshot.phase in ("response_peng", "response_chi"))
        if frozen is not None and same_cycle and new_trigger is not None and new_trigger[2:] == frozen[2:]:
            new_trigger = frozen
            self._trigger_is_estimated = True
        elif not same_cycle or (new_trigger is not None and frozen is not None and new_trigger[2:] != frozen[2:]):
            self._frozen_response_trigger = None
        if new_round or snapshot.phase == "draw" or (new_trigger is not None and new_trigger != old_trigger):
            self._self_responded = False
        if (
            self._response_trigger is not None
            and self._response_trigger[0] != snapshot.round_no
        ):
            self._response_trigger = None  # 局号变化：旧局记忆失效
        # 响应周期结束（进入 draw/新局）时清除本人表态标记；响应阶段内的
        # 计划性刷新（边界定时/409 刷新）不清除。此前显式碰阶段 pass
        # 后吃提交曾遇到 409，因此新路径不在碰阶段发送 pass；不能只靠
        # 切换 phase 清标记并假定官方重新授予动作权。
        if snapshot.phase == "draw" or (
            self.snapshot is not None and snapshot.round_no != self.snapshot.round_no
        ):
            self._self_responded = False
        if any(e.type == "tile_drawn" and e.seat != snapshot.seat and e.tiles for e in events):
            self.history_complete = False
            self._observation_issues.add("unexpected_other_draw")
        if any(e.type not in KNOWN_EVENT_TYPES for e in events):
            self.history_complete = False
            self._observation_issues.add("unknown_snapshot_event")
        for public in incoming.values():
            if (public.kind == "chi" and len(public.tiles) != 3) or (
                    public.kind in ("gang", "timeout") and public.detail_kind is None):
                self._observation_issues.add("event_detail_incomplete:" + public.kind)
        self.snapshot = snapshot
        self.last_seq = snapshot.seq
        if new_trigger is not None:
            self._response_trigger = new_trigger
        self._restore_current_pass()
        self._observation_cache = None
        self.finished = self.finished or finished
        self._refresh_history_completeness()

    def history_missing_ranges(self) -> Tuple[Tuple[int, int], ...]:
        """返回当前快照已吸收但未收到原事件的闭区间，不遍历大段序号。

        未知前缀由 history_origin_known 单独表达；本方法空结果不代表完整。
        晚于快照的正常增量尚未被快照吸收，不属于此补史账本。
        """
        if self.snapshot is None or self.history_floor_seq is None:
            return ()
        cursor = self.history_floor_seq + 1
        upper = self.snapshot.seq
        ranges = []
        for seq in sorted({e.seq for e in self.history if cursor <= e.seq <= upper}):
            if seq > cursor:
                ranges.append((cursor, seq - 1))
            cursor = seq + 1
        if cursor <= upper:
            ranges.append((cursor, upper))
        return tuple(ranges)

    def _refresh_history_completeness(self) -> None:
        """只有真实补齐且起点可证明时恢复完整性，其他降级原因不可洗掉。"""
        missing = self.history_missing_ranges()
        other_issues = self._observation_issues - {"history_gap_snapshot"}
        if missing:
            self._observation_issues.add("history_gap_snapshot")
            self.history_complete = False
        elif self.history_origin_known and not other_issues:
            self._observation_issues.discard("history_gap_snapshot")
            self.history_complete = True
        else:
            self.history_complete = False

    def merge_history(self, events: Tuple[ParsedEvent, ...], *, round_no: int) -> None:
        """补入调用方已证明属于当前手、且不晚于快照的事件；不重放牌面。

        全批验证后才提交。未知事件、冲突、越界或私有牌泄漏抛 DtoError，
        交会话恢复；原始证据由调用方审计保存。仅补齐当前弃牌的本人pass
        动作权事实，禁止借补史重新建立已发出的窗口身份。
        """
        if self.snapshot is None or round_no != self.snapshot.round_no:
            raise DtoError("补史单局与当前权威快照不一致")
        retained = {e.seq: e for e in self.history}
        incoming = {}
        issues = set()
        for event in events:
            if event.seq <= 0 or event.seq > self.snapshot.seq:
                raise DtoError("补史事件不在当前快照已吸收范围")
            if self.history_origin_known and self.history_floor_seq is not None and event.seq <= self.history_floor_seq:
                raise DtoError("补史事件早于已证明的本手起点")
            if event.type not in KNOWN_EVENT_TYPES:
                raise DtoError("未知补史事件:" + event.type)
            public = projector.public_event(event)
            if public.kind == "tile_drawn" and public.seat != self.snapshot.seat and public.tiles:
                raise DtoError("补史事件包含他家私有摸牌")
            if (event.seq in retained and retained[event.seq] != public) or (event.seq in incoming and incoming[event.seq] != public):
                raise DtoError("补史事件存在冲突重复")
            incoming[event.seq] = public
            if (public.kind == "chi" and len(public.tiles) != 3) or (public.kind in ("gang", "timeout") and public.detail_kind is None):
                issues.add("event_detail_incomplete:" + public.kind)
        merged = {**retained, **incoming}
        ordered = [merged[seq] for seq in sorted(merged)]
        ended = False
        game_ended = False
        for event in ordered:
            if game_ended or (ended and event.kind != "game_ended"):
                raise DtoError("补史终局边界后仍有活动事件")
            ended = ended or event.kind == "round_ended"
            game_ended = event.kind == "game_ended"
        if self.snapshot.phase not in ("settled", "finished") and any(e.kind in ("round_ended", "game_ended") for e in incoming.values()):
            raise DtoError("活动快照与补史终局事件矛盾")
        if self._trigger_is_estimated and self._response_trigger is not None:
            self._frozen_response_trigger = self._response_trigger
        self.history = ordered
        self._observation_issues.update(issues)
        self._restore_current_pass()
        self._refresh_history_completeness()
        self._observation_cache = None

    def _restore_current_pass(self) -> None:
        """由完整的当前弃牌后缀恢复本人表态，窗口身份仍使用原冻结序号。"""
        if self.snapshot is None:
            return
        trigger = self._response_trigger
        if trigger is not None and self.snapshot.phase in ("response_peng", "response_chi"):
            # 最后的当前弃牌事件可能刚补到，比估算触发序号更早；仅用于绑定pass。
            fact = self._last_discarded_event()
            trigger_seq = trigger[1]
            tail_complete = (fact is not None and
                             sum(fact[0] <= e.seq <= self.snapshot.seq for e in self.history) == self.snapshot.seq - fact[0] + 1)
            if self._trigger_is_estimated and fact is not None and tail_complete and fact[1:] == trigger[2:] and fact[0] <= trigger_seq:
                trigger_seq = fact[0]
            if any(e.kind == "pass" and e.seat == self.snapshot.seat and e.seq > trigger_seq for e in self.history):
                self._self_responded = True

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
        seen = {event.seq: event for event in self.history}
        ended = False
        game_ended = False
        for event in ordered:
            if game_ended or (ended and event.type != "game_ended"):
                return SyncResult(SyncDecision.NEEDS_REBUILD, ("events_after_round_ended",))
            try:
                public = projector.public_event(event)
            except (ValueError, DtoError) as exc:
                return SyncResult(SyncDecision.NEEDS_REBUILD, ("projection_failed:" + str(exc)[:80],))
            if event.seq <= expected:
                if event.seq in seen and seen[event.seq] != public:
                    return SyncResult(SyncDecision.NEEDS_REBUILD, ("conflicting_duplicate:{}".format(event.seq),))
                duplicates.append(event.seq)  # 重复 seq 幂等忽略
                continue
            if event.seq != expected + 1:
                return SyncResult(
                    SyncDecision.NEEDS_REBUILD,
                    ("seq_gap:{}".format(event.seq),),
                    tuple(duplicates),
                )
            if event.type not in KNOWN_EVENT_TYPES:
                # 未知关键事件每次都需权威吸收；一次恢复不证明该类型安全
                return SyncResult(
                    SyncDecision.NEEDS_REBUILD,
                    ("unknown_event:{}".format(event.type),),
                    tuple(duplicates),
                )
            try:
                # 投影构造在预检内完成：构造失败（非法牌码/座位等）整批
                # 拒绝且游标不推进，保持事务性
                projected.append((event, public))
                seen[event.seq] = public
            except (ValueError, DtoError) as exc:
                return SyncResult(
                    SyncDecision.NEEDS_REBUILD,
                    ("projection_failed:" + str(exc)[:80],),
                    tuple(duplicates),
                )
            expected = event.seq
            ended = ended or event.type == "round_ended"
            game_ended = event.type == "game_ended"
        for event, public in projected:  # 预检全通过后统一应用
            if public.kind == "tile_drawn" and public.seat != self.snapshot.seat and public.tiles:
                # 玩家端不应收到他家摸牌的牌值；空牌值摸牌合法，私有牌不可送给策略。
                self.history_complete = False
                self._observation_issues.add("unexpected_other_draw")
            else:
                self.history.append(public)
            if (public.kind == "chi" and len(public.tiles) != 3) or (
                public.kind in ("gang", "timeout") and public.detail_kind is None
            ):
                self.history_complete = False
                self._observation_issues.add("event_detail_incomplete:" + public.kind)
            self.last_seq = event.seq
            if public.kind == "tile_discarded":
                discard = self._event_discard_fact(public)
                if discard is not None:
                    # 新一轮弃牌出现：覆盖跨重建触发记忆（R2 加固来源 (a)）
                    self._response_trigger = (self.snapshot.round_no,) + discard
                    self._trigger_is_estimated = False
                    self._frozen_response_trigger = None
                # 新弃牌开启新响应周期：本人表态标记重置（F2）
                self._self_responded = False
            if public.kind == "pass" and public.seat == self.snapshot.seat:
                # 本人 pass 事件回显（官方事件带座位，2026-09-05 实证）：
                # 本响应周期对我关闭（F2）
                self._self_responded = True
            if event.type == "game_ended":
                self.finished = True
        self._observation_cache = None  # 历史变化使观察缓存失效
        return SyncResult(SyncDecision.ACCEPTED, (), tuple(duplicates))

    def note_rebuild_absorbed(self, event_type: str) -> None:
        """只记录未知类型已被快照吸收；不能据一次成功将类型升级为可忽略。"""
        self.history_complete = False
        self._observation_issues.add("unknown_event:" + event_type)
        self._observation_cache = None

    def incremental_response_observation(self) -> Optional[PlayerObservation]:
        """连续普通他家摸/弃/过事件可直接投影碰窗口，无需再 GET 快照。

        只处理明确 catch_play=false 且本人暗牌/god 未变化的后缀；
        吃碰杠、本人动作、抓打圈、缺少标记或超时阶段变化仍交权威快照。
        snapshot_seq 保持真实快照水位，consumed_seq 记录已消费的增量水位。
        """
        snapshot = self.snapshot
        if snapshot is None or self.finished or snapshot.god_catch_play or snapshot.drawn_tile:
            return None
        suffix = tuple(e for e in self.history if e.seq > snapshot.seq)
        if not suffix or suffix[-1].seq != self.last_seq:
            return None
        base = projector.observation(snapshot, tuple(self.history), self.game_id)
        rows = [list(row) for row in base.discards]
        counts = list(base.hand_counts)
        remaining = base.remaining_tile_count
        last_discard = None
        # 不能把旧快照水位与跨缺口事件拼成当前响应状态。
        for expected, event in enumerate(suffix, snapshot.seq + 1):
            if event.seq != expected:
                return None
            if event.kind == "pass":
                continue
            if event.seat is None or event.seat == snapshot.seat:
                return None
            if event.kind == "tile_drawn" and not event.tiles:
                counts[event.seat] += 1
                remaining = None if remaining is None else remaining - 1
                last_discard = None
            elif event.kind == "tile_discarded" and len(event.tiles) == 1 and event.catch_play is False:
                rows[event.seat].append(event.tiles[0])
                counts[event.seat] -= 1
                last_discard = PublicDiscard(event.seat, event.tiles[0], event.seq)
            else:
                return None
        if last_discard is None or min(counts) < 0 or (remaining is not None and remaining < 0):
            return None
        return enrich_observation(replace(
            base, phase="response_peng", turn_seat=last_discard.seat,
            responding_seats=tuple(seat for seat in range(4) if seat != last_discard.seat),
            drawn_tile=None, last_discard=last_discard, discards=tuple(tuple(row) for row in rows),
            hand_counts=tuple(counts), remaining_tile_count=remaining, consumed_seq=self.last_seq,
            history_complete=self.history_complete,
            observation_issues=tuple(sorted(self._observation_issues - {"history_gap_snapshot"})),
        ))

    def incremental_response_window(self):
        """普通弃牌的响应身份直接取原事件序号；阶段截止由会话计时处理。"""
        observation = self.incremental_response_observation()
        if observation is None:
            return None
        discard = observation.last_discard
        return projector.DetectedWindow(
            window_key=WindowKey(self.game_id, observation.round_no, discard.seq,
                                 WindowPhase.RESPONSE_PENG, observation.seat),
            timeout_seconds=self.timing.peng_timeout_sec,
            trigger_projection_note=None,
            trigger_discard=(discard.seq, discard.tile.code, discard.seat),
        )

    def events_need_authoritative_refresh(self, events) -> bool:
        """只在当前实现不能完整推进必要事实时查询快照。

        弃牌后的响应资格、所有人的副露/牌河变化、超时及单局边界仍由
        权威快照确认。正常 pass 不刷新；本人普通摸牌仅在完整前态能
        通过 hangma 重算规则状态时直接交付，否则恢复。减少请求不能以
        丢失牌面或陈旧 god 为代价。
        """

        projected = self.incremental_response_observation()
        if projected is not None:
            self._observation_cache = projected
            return False
        my_seat = self.snapshot.seat if self.snapshot is not None else None
        for event in events:
            if event.type == "tile_drawn" and event.seat != my_seat and event.tiles:
                # 违规他家摸牌可能证明此前本人的窗口已结束；不可只脱敏后继续决策。
                return True
            if event.type not in KNOWN_EVENT_TYPES:
                # P2-N3：见 docstring——已学习未知类型的行为不可知，保守刷新。
                return True
            if event.type in ("tile_discarded", "timeout", "round_ended", "game_ended"):
                return True
            if event.type in ("chi", "peng", "gang"):
                return True
            if (
                event.type == "tile_drawn"
                and event.seat == my_seat
                and len(event.tiles) != 1
            ):
                return True
        if self.incremental_draw_window() is not None:
            try:
                self._observation_cache = self.incremental_draw_observation()
            except ValueError:
                # 前态不完整或补牌来源不足，不能把猜测的 god 交给应用层。
                return True
        return False

    def note_self_response(self) -> None:
        """本人对当前响应周期已表态（POST pass 被官方接受后由会话层调用）。"""

        self._self_responded = True

    def note_accepted_action(self, action: Action, before: PlayerObservation) -> None:
        """登记官方已明确成功的本人动作；调用方不得用于拒绝或结果不确定。

        保留提交前的不可变观察供新快照核对。此处不推进牌面、不修改
        官方god，也不提前更新链次数；作用域仅限持有本状态机的场次。
        """
        if before.game_id != self.game_id:
            raise ValueError("成功动作前态必须属于当前场次")
        self._confirmed_action = (before, action)
        # 同场GET和POST可并发：新快照可能先于成功回执到达并已缓存。
        # 新确认必须使同水位观察也重新核对，不等下一次HTTP或改写已投递值。
        self._observation_cache = None

    @property
    def response_suppressed_for_self(self) -> bool:
        """当前响应周期是否已收到本人表态（pass 事件回显或接受回执）。"""

        return self._self_responded

    @property
    def response_cycle_key(self):
        """当前弃牌周期身份，供适配器内部边界计时使用；不传给策略。"""
        return self._response_trigger

    def incremental_draw_window(self):
        """增量路径判定的本人摸牌窗口；事件流末条不是本人摸牌时返回 None。

        官方 draw 且 turn==seat 可出牌/胡/杠；v17 实测他家摸牌保留事件但
        隐藏牌值。仅当事件流最后一条是本人且牌值完整的 tile_drawn，
        才把它作为当前本人摸牌窗口；后续弃牌、超时等必须先刷新。触发序号直接取摸牌事件 seq：与快照路径同值（摸牌
        窗口期间无其他事件推进水位），且是真正的触发事件序号。
        """

        snapshot = self.snapshot
        if snapshot is None or self.finished or snapshot.seat < 0:
            return None
        if not self.history:
            return None
        last = self.history[-1]
        if (
            last.seq <= snapshot.seq or last.seq != self.last_seq
            or last.kind != "tile_drawn"
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
        当前手牌；drawn_tile 仅取本人摸牌事件牌码，他家摸牌不得提供牌值。牌河按事件流追加公开弃牌，保持估算口径与真实
        牌河一致；phase/turn/responding_seats 由摸牌语义推导（draw 阶段、
        本人行动、无响应成员）。
        """

        base = self._snapshot_observation()
        if base is None or self.snapshot is None or not self.history:
            return None
        last = self.history[-1]
        if (
            last.seq <= self.snapshot.seq or last.seq != self.last_seq
            or last.kind != "tile_drawn"
            or last.seat != self.snapshot.seat
            or len(last.tiles) != 1
        ):
            return None
        drawn = last.tiles[0]
        # 最新弃牌以事件流增量事实为准；无增量弃牌时退回快照投影
        fact = self._last_discarded_event()
        if fact is not None and fact[0] > self.snapshot.seq:
            seq, code, seat = fact
            last_discard = PublicDiscard(seat=seat, tile=Tile(code), seq=seq)
        else:
            last_discard = base.last_discard
        discards = base.discards
        rows = None
        for event in self.history:
            if event.seq <= self.snapshot.seq:
                continue  # 已吸收的历史只供规则与审计，不重复追加牌河
            if event.kind != "tile_discarded" or len(event.tiles) != 1:
                continue
            if rows is None:
                rows = [list(row) for row in discards]
            rows[event.seat].append(event.tiles[0])
        if rows is not None:
            discards = tuple(tuple(row) for row in rows)
        # N-2：观察自洽性——快照 hand_counts[本人]/墙余以"含刚摸牌"口径计数，
        # 增量送达把新摸的 drawn 单列进观察时，本人手数 +1、墙余 -1；
        # 基础快照已是本人摸牌形态（base.drawn_tile 非空）时不变
        # （换牌等量，正常流程不可达，防御性处理）。
        counts = list(base.hand_counts)
        remaining = base.remaining_tile_count
        if base.drawn_tile is None:
            counts[self.snapshot.seat] += 1
            if remaining is not None:
                remaining -= 1
        drawn_observation = enrich_observation(replace(
            base,
            phase="draw",
            turn_seat=self.snapshot.seat,
            responding_seats=(),
            drawn_tile=drawn,
            last_discard=last_discard,
            discards=discards,
            hand_counts=tuple(counts),
            remaining_tile_count=remaining,
        ))
        return replace(drawn_observation, rule_state=recompute_draw_rule_state(
            base, drawn, replacement=drawn_observation.gang_draw))

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
        incremental = self.incremental_draw_window()
        if incremental is not None:
            return incremental
        response = self.incremental_response_window()
        if response is not None:
            return response
        if self._masked_draws_since_snapshot():
            # 他家开始摸牌已证明旧响应结束；不能继续使用快照里的我方响应资格。
            return None
        detected = projector.detect_window(
            self.snapshot,
            self.timing,
            self.game_id,
            event_stream_discard=self._current_discard_event(),
            remembered_trigger=self._response_trigger,
        )
        if detected is not None and detected.trigger_discard is not None:
            frozen = self._frozen_response_trigger
            if frozen is not None and frozen[0] == self.snapshot.round_no and detected.trigger_discard[1:] == frozen[2:]:
                detected = replace(detected,
                                   window_key=replace(detected.window_key, trigger_seq=frozen[1]),
                                   trigger_discard=(frozen[1], frozen[2], frozen[3]))
            self._response_trigger = (
                self.snapshot.round_no,
            ) + detected.trigger_discard
        if detected is not None and self._trigger_is_estimated and detected.window_key.phase in (WindowPhase.RESPONSE_PENG, WindowPhase.RESPONSE_CHI):
            self._frozen_response_trigger = self._response_trigger
            detected = replace(detected, trigger_projection_note="response 触发序号使用首次匹配快照 seq={} 估计；缺少官方弃牌序号".format(detected.window_key.trigger_seq))
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
        """当前事实的统一观察入口；快照、增量及新成功确认均使缓存失效。"""

        if self.snapshot is None:
            return None
        if self._observation_cache is None:
            if self.incremental_draw_window() is not None:
                self._observation_cache = self.incremental_draw_observation()
            else:
                self._observation_cache = (self.incremental_response_observation()
                                           or enrich_observation(self._snapshot_observation()))
        observation = self._observation_cache
        if observation is not self._fact_observation:
            if self._confirmed_action is not None:
                before, action = self._confirmed_action
                observation = reconcile_observation(before, observation, confirmed_action=action)
                # 增量可先推进水位但仍待权威快照确认；只能在新快照吸收
                # 该动作后消费一次确认，避免用陈旧牌面提前丢掉核对依据。
                if (observation.round_no != before.round_no or
                        observation.snapshot_seq > (before.consumed_seq if before.consumed_seq is not None else before.snapshot_seq)):
                    self._confirmed_action = None
            elif self._fact_observation is not None:
                observation = reconcile_observation(self._fact_observation, observation)
            self._observation_cache = observation
            self._fact_observation = observation
        return self._observation_cache

    def _snapshot_observation(self) -> Optional[PlayerObservation]:
        """快照牌面与已收历史的基底；尚未重复应用快照前事件。"""
        if self.snapshot is None:
            return None
        base = projector.observation(self.snapshot, tuple(self.history), self.game_id)
        masked = self._masked_draws_since_snapshot()
        if masked:
            counts = list(base.hand_counts)
            for event in masked:
                counts[event.seat] += 1
            base = replace(base, phase="draw", turn_seat=masked[-1].seat,
                           responding_seats=(), drawn_tile=None,
                           hand_counts=tuple(counts),
                           remaining_tile_count=(None if base.remaining_tile_count is None
                                                 else base.remaining_tile_count - len(masked)))
        return replace(base, consumed_seq=self.last_seq, history_complete=self.history_complete,
                       observation_issues=tuple(sorted(self._observation_issues - {"history_gap_snapshot"})))

    def _masked_draws_since_snapshot(self):
        """只推进快照之后的他家公开摸牌数量，绝不需要或推测其牌值。"""
        if self.snapshot is None:
            return ()
        return tuple(e for e in self.history if e.seq > self.snapshot.seq
                     and e.kind == "tile_drawn" and e.seat != self.snapshot.seat and not e.tiles)

    def _current_discard_event(self) -> Optional[Tuple[int, str, int]]:
        """只让与当前触发身份一致的历史参与窗口识别；旧历史不能覆盖新快照。"""
        fact = self._last_discarded_event()
        if fact is None or self.snapshot is None:
            return None
        raw = self.snapshot.last_discard
        if isinstance(raw, tuple):
            return fact if fact == (raw[2], raw[1], raw[0]) or fact[0] > self.snapshot.seq else None
        if isinstance(raw, str) and fact[1:] == (raw, self.snapshot.turn):
            if self._response_trigger is None or fact[0] >= self._response_trigger[1]:
                return fact
        return None

    def final_scores(self) -> Optional[Tuple[int, int, int, int]]:
        """终局积分，固定按座位 0-3；仅终局快照有效。"""

        if self.snapshot is None:
            return None
        return self.snapshot.scores
