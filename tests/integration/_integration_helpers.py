"""integration 测试自包含脚手架：只通过公开契约类型组装脚本化端口。

设计边界（tests/AGENTS.md）：测试只通过模块公开接口验证行为；
本文件不导入任何生产模块的私有符号。脚本化会话实现四个冻结接缝：

- ScriptedTournamentSession：报名/到位/更新序列可编排；更新在上一
  轮场次未排空前不返回终态快照，保证终局前窗口处理完成（确定性）；
- ScriptedGameSession：窗口/终局条目序列 + 提交结果序列（或按
  attempt 动态决策的 handler）；可挂载审计发射，复刻官方适配器
  「双层记录」形态（无 stage_attempt_id），验证验证器对真实运行
  目录的判定。
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Callable, Optional, Sequence

from hangma_bot.application.contracts import (
    AuditContext,
    AuditKind,
    AuditRecord,
    AuditSink,
    GameFinished,
    GameSessionPort,
    GuideVersion,
    ObservedActionWindow,
    OperationStatus,
    ParticipantTerminal,
    ReadyResult,
    RegistrationResult,
    RuntimeMode,
    RuntimeTarget,
    SessionBootstrap,
    StageIdentity,
    SubmitOutcome,
    TournamentSessionPort,
    TournamentSnapshot,
    TournamentStatus,
)
from hangma_bot.kernel.actions import Tile, WindowKey, WindowPhase
from hangma_bot.kernel.config import RuleConfig, TimingConfig, TournamentConfig
from hangma_bot.kernel.observation import (
    CompetitionContext,
    PlayerObservation,
    RulePublicState,
)


def make_rule_config() -> RuleConfig:
    return RuleConfig(ruleset_version="test-rules", base_score=100, you_cai_bi_kao=False)


def make_config(max_games: int = 1, rounds: int = 1) -> TournamentConfig:
    return TournamentConfig(
        max_games=max_games,
        rounds_per_game=rounds,
        rules=make_rule_config(),
        timing=TimingConfig(peng_timeout_sec=1.0, chi_timeout_sec=1.0, discard_timeout_sec=3.0),
    )


def make_observation(
    game_id: str = "g1",
    seat: int = 0,
    round_no: int = 1,
    seq: int = 10,
    phase: str = "draw",
    hand: Sequence[str] = ("1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "1b", "2b", "3b", "东"),
) -> PlayerObservation:
    """构造普通摸牌出牌窗口的玩家观察；与 hangma 模块测试同形态。"""

    return PlayerObservation(
        game_id=game_id,
        seat=seat,
        round_no=round_no,
        snapshot_seq=seq,
        phase=phase,
        dealer_seat=0,
        turn_seat=seat,
        responding_seats=(),
        my_hand=tuple(Tile(code) for code in hand),
        drawn_tile=None,
        discards=((), (), (), ()),
        melds=((), (), (), ()),
        hand_counts=(13, 13, 13, 13),
        last_discard=None,
        remaining_tile_count=60,
        scores=(0, 0, 0, 0),
        rule_state=RulePublicState(
            wealth_god=Tile("白"), baotou=False, chain_count=0, catch_play=False
        ),
        public_history=(),
    )


def make_window(
    observation: PlayerObservation,
    *,
    phase: WindowPhase = WindowPhase.DRAW,
    timeout: float = 3.0,
    received_at: float = 100.0,
) -> ObservedActionWindow:
    window_key = WindowKey(
        game_id=observation.game_id,
        round_no=observation.round_no,
        trigger_seq=observation.snapshot_seq,
        phase=phase,
        seat=observation.seat,
    )
    return ObservedActionWindow(
        observation=observation,
        window_key=window_key,
        authoritative_seq=observation.snapshot_seq,
        received_at_monotonic=received_at,
        timeout_seconds=timeout,
    )


def make_refreshed_window(base: ObservedActionWindow, *, seq: int) -> ObservedActionWindow:
    """同一窗口 seq=0 权威刷新后的新窗口：键不变，权威序号更新。"""

    observation = make_observation(
        game_id=base.window_key.game_id,
        seat=base.window_key.seat,
        round_no=base.window_key.round_no,
        seq=seq,
    )
    return ObservedActionWindow(
        observation=observation,
        window_key=base.window_key,
        authoritative_seq=seq,
        received_at_monotonic=base.received_at_monotonic + 0.5,
        timeout_seconds=base.timeout_seconds,
    )


def make_snapshot(
    status: TournamentStatus,
    *,
    stage_no: Optional[int] = None,
    revision: int = 1,
    qualified: Optional[bool] = None,
    crashed: bool = False,
    active_games: Sequence[str] = (),
    my_games: Optional[Sequence[str]] = None,
) -> TournamentSnapshot:
    return TournamentSnapshot(
        tournament_id="t1",
        participant_id="p1",
        status=status,
        stage=StageIdentity(stage_no=stage_no, observed_revision=revision),
        stage_role=None,
        stage_total=None,
        stage_crashed=crashed,
        qualified=qualified,
        qualify_role=None,
        active_games=tuple(active_games),
        my_games=tuple(active_games if my_games is None else my_games),
        competition=CompetitionContext(
            tournament_id="t1",
            stage_no=stage_no,
            stage_role=None,
            stage_total=None,
            participant_rank=None,
            ranking=(),
            observed_at_unix_ms=1,
        ),
        observed_at_unix_ms=123,
    )


def make_bootstrap(
    snapshot: TournamentSnapshot,
    *,
    config: Optional[TournamentConfig] = None,
    guide_version: int = 8,
    breaking: bool = False,
    tournament_id: str = "t1",
) -> SessionBootstrap:
    return SessionBootstrap(
        guide=GuideVersion(
            version=guide_version,
            updated_at="2026-09-03",
            has_unknown_breaking_change=breaking,
        ),
        participant_id="p1",
        tournament_id=tournament_id,
        config=config if config is not None else make_config(),
        initial_snapshot=snapshot,
    )


def make_target(known_guide_version: int = 8) -> RuntimeTarget:
    return RuntimeTarget(
        mode=RuntimeMode.TEST_ROOM,
        expected_tournament_id="t1",
        known_guide_version=known_guide_version,
    )


class ScriptedGameSession:
    """脚本化单场会话：条目序列 + 提交结果序列/处理器。

    条目耗尽即挂起（等待监督层关闭取消）；可选挂载审计，按官方适配器
    形态发射「双层记录」：窗口权威状态无 stage_attempt_id（适配器契约）。
    """

    def __init__(self, *, items: Sequence, submit_outcomes: Sequence | Callable):
        self._items = list(items)
        self._outcomes = list(submit_outcomes) if not callable(submit_outcomes) else submit_outcomes
        self._handler = submit_outcomes if callable(submit_outcomes) else None
        self.submitted = []
        self.closed = False
        self.drained = asyncio.Event()
        self._audit: Optional[AuditSink] = None
        self._context_builder: Optional[Callable[[], AuditContext]] = None

    def attach_audit(
        self,
        audit: AuditSink,
        context_builder: Callable[[], AuditContext],
    ) -> None:
        """挂载组合根审计（integration 复刻官方适配器的双层记录接线）。"""

        self._audit = audit
        self._context_builder = context_builder

    def _emit_adapter(self, kind: AuditKind, payload: dict, **extra) -> None:
        """官方适配器形态：基础上下文（无 stage_attempt_id）+ 场级字段。"""

        if self._audit is None or self._context_builder is None:
            return
        context = replace(self._context_builder(), **extra)
        self._audit.emit(AuditRecord(
            schema_version=1,
            kind=kind,
            context=context,
            wall_time_unix_ms=1000,
            monotonic_ns=1,
            payload=payload,
        ))

    async def next_item(self):
        if self.closed:
            raise RuntimeError("会话已关闭")
        if self._items:
            item = self._items.pop(0)
            if isinstance(item, BaseException):
                raise item
            if isinstance(item, ObservedActionWindow):
                self._emit_adapter(
                    AuditKind.AUTHORITATIVE_STATE,
                    {
                        "seq": item.authoritative_seq,
                        "phase": item.window_key.phase.value,
                        "turn": item.observation.turn_seat,
                        "window": {
                            "game_id": item.window_key.game_id,
                            "round_no": item.window_key.round_no,
                            "trigger_seq": item.window_key.trigger_seq,
                            "phase": item.window_key.phase.value,
                            "seat": item.window_key.seat,
                        },
                    },
                    game_id=item.window_key.game_id,
                    round_no=item.window_key.round_no,
                    trigger_seq=item.window_key.trigger_seq,
                )
            if not self._items:
                self.drained.set()
            return item
        self.drained.set()
        await asyncio.Future()  # 挂起直到监督层关闭取消

    async def submit(self, attempt) -> SubmitOutcome:
        if self.closed:
            raise RuntimeError("会话已关闭")
        self.submitted.append(attempt)
        if self._handler is not None:
            outcome = self._handler(attempt)
        elif self._outcomes:
            outcome = self._outcomes.pop(0)
        else:
            raise RuntimeError("脚本耗尽：无更多提交结果")
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    async def aclose(self, reason: str) -> None:
        self.closed = True


class ScriptedTournamentSession:
    """脚本化赛事会话：更新序列耗尽后挂起；终态快照前等待场次排空。"""

    def __init__(
        self,
        *,
        bootstrap: SessionBootstrap,
        updates: Sequence = (),
        register_results: Optional[Sequence] = None,
        ready_results: Optional[Sequence] = None,
        game_sessions: Optional[dict] = None,
    ):
        self._bootstrap = bootstrap
        self._updates = list(updates)
        self._register_results = list(register_results or [RegistrationResult(status=OperationStatus.ACCEPTED)])
        self._ready_results = list(ready_results or [])
        self._games = dict(game_sessions or {})
        self.initialize_calls = []
        self.register_calls = 0
        self.ready_calls = []
        self.next_update_calls = 0
        self.opened_games = []
        self.closed = False
        # 可选更新闸门：非空时 next_update 在弹出更新前等待条件满足，
        # 用于确定性编排「先注册+到位、再发放下一快照」的时序场景。
        self.update_gate = None

    async def initialize(self, target: RuntimeTarget):
        self.initialize_calls.append(target)
        return self._bootstrap

    async def register(self):
        self.register_calls += 1
        if not self._register_results:
            return RegistrationResult(status=OperationStatus.ALREADY_DONE)
        item = self._register_results.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    async def ready(self, expected_stage: StageIdentity):
        self.ready_calls.append(expected_stage)
        if not self._ready_results:
            return ReadyResult(status=OperationStatus.ALREADY_DONE)
        item = self._ready_results.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    async def next_update(self):
        self.next_update_calls += 1
        if not self._updates:
            await asyncio.Future()  # 挂起直到监督层关闭取消
        while self.update_gate is not None and not self.update_gate():
            await asyncio.sleep(0)
        item = self._updates.pop(0)
        if isinstance(item, BaseException):
            raise item
        if self._requires_drain(item):
            for game in self._games.values():
                await asyncio.wait_for(game.drained.wait(), timeout=10.0)
        return item

    @staticmethod
    def _requires_drain(item) -> bool:
        """终态或空 active_games 的快照必须等场次处理完，保证确定性。"""

        if isinstance(item, ParticipantTerminal):
            return True
        if isinstance(item, TournamentSnapshot):
            return not item.active_games
        return False

    def open_game(self, game_id: str) -> GameSessionPort:
        self.opened_games.append(game_id)
        return self._games[game_id]

    async def aclose(self) -> None:
        self.closed = True
