"""application 工作包的 Fake 端口与测试脚手架；仅测试使用，不进入生产包。"""

from __future__ import annotations

import asyncio
from typing import Optional

from hangma_bot.application.contracts import (
    ActionAttempt,
    AuditReceipt,
    AuditRecord,
    AuditSummary,
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
    SubmitAccepted,
    SubmitOutcome,
    TournamentSessionPort,
    TournamentSnapshot,
    TournamentStatus,
)
from hangma_bot.application.ids import IdGenerator
from hangma_bot.application.deadline import ManualClock
from hangma_bot.application.participant_runtime import ParticipantRuntime
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import (
    ActionValidation,
    RuleAnalysis,
    RuleCandidate,
    RuleCompleteness,
)
from hangma_bot.kernel.actions import Discard, Pass, Tile, WindowKey, WindowPhase, action_key
from hangma_bot.kernel.config import RuleConfig, TimingConfig, TournamentConfig
from hangma_bot.kernel.observation import (
    CompetitionContext,
    PlayerObservation,
    RulePublicState,
)
from hangma_bot.policy.interface import (
    BotPolicy,
    DecisionPlan,
    RankedCandidate,
    ScorePart,
)


RULE_CONFIG = RuleConfig(ruleset_version="test-rules", base_score=100, you_cai_bi_kao=False)
DISCARD_3W = Discard(Tile("3w"))
PASS = Pass()


def make_config(max_games: int = 2, rounds: int = 1) -> TournamentConfig:
    return TournamentConfig(
        max_games=max_games,
        rounds_per_game=rounds,
        rules=RULE_CONFIG,
        timing=TimingConfig(peng_timeout_sec=1.0, chi_timeout_sec=1.0, discard_timeout_sec=3.0),
    )


def make_observation(
    game_id: str = "g1",
    seat: int = 0,
    round_no: int = 1,
    seq: int = 10,
    phase: str = "draw",
    hand=("1w", "2w", "3w"),
) -> PlayerObservation:
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
        remaining_tile_count=None,
        scores=(0, 0, 0, 0),
        rule_state=RulePublicState(
            wealth_god=Tile("1w"), baotou=False, chain_count=0, catch_play=False
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


def make_refreshed_window(
    base: ObservedActionWindow,
    *,
    seq: int,
    received_at: float = None,
) -> ObservedActionWindow:
    """同一窗口 seq=0 刷新后的新窗口：保留原窗口键，权威序号更新。"""

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
        received_at_monotonic=received_at
        if received_at is not None
        else base.received_at_monotonic + 0.5,
        timeout_seconds=base.timeout_seconds,
    )


def make_competition(stage_no=None) -> CompetitionContext:
    return CompetitionContext(
        tournament_id="t1",
        stage_no=stage_no,
        stage_role=None,
        stage_total=None,
        participant_rank=None,
        ranking=(),
        observed_at_unix_ms=1,
    )


def make_snapshot(
    status=TournamentStatus.RUNNING,
    *,
    stage_no=None,
    revision: int = 1,
    qualified=None,
    crashed: bool = False,
    my_games=(),
    active_games=None,
) -> TournamentSnapshot:
    """构造快照；active_games 缺省与 my_games 相同，便于历史调用方。

    官方语义：active_games 是 /api/me 的当前运行集合（编排权威），
    my_games 是跨阶段累计历史（仅审计）。需要区分二者时显式传 active_games。
    """

    active = tuple(active_games if active_games is not None else my_games)
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
        active_games=active,
        my_games=tuple(my_games),
        competition=make_competition(stage_no),
        observed_at_unix_ms=123,
    )


def make_bootstrap(
    snapshot: TournamentSnapshot,
    *,
    config: TournamentConfig = None,
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


def make_target(
    known_guide_version: int = 8,
    mode: RuntimeMode = RuntimeMode.TEST_TOURNAMENT,
) -> RuntimeTarget:
    """测试目标缺省用官方测试赛事语义（finished=终态）；

    测试房间跨轮复用场景显式传 mode=RuntimeMode.TEST_ROOM。
    """

    return RuntimeTarget(
        mode=mode,
        expected_tournament_id="t1",
        known_guide_version=known_guide_version,
    )


class FakeGameSession:
    """脚本化单场会话：按序吐出条目并记录提交与关闭。"""

    def __init__(self, items=None, submit_handler=None) -> None:
        self._items = list(items or [])
        self._handler = submit_handler or (
            lambda attempt: SubmitAccepted(
                official_code="200",
                authoritative_seq=attempt.based_on_authoritative_seq + 1,
            )
        )
        self.submitted = []
        self.close_reasons = []
        self.closed = False
        self.drained = False  # 脚本耗尽后再被拉取即为窗口已处理完的可观测信号
        self._idle = asyncio.Event()

    async def next_item(self):
        if self.closed:
            raise RuntimeError("会话已关闭")
        if self._items:
            item = self._items.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        self.drained = True
        await self._idle.wait()  # 脚本耗尽后挂起，直到被取消

    async def submit(self, attempt: ActionAttempt) -> SubmitOutcome:
        if self.closed:
            raise RuntimeError("会话已关闭")
        self.submitted.append(attempt)
        outcome = self._handler(attempt)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    async def aclose(self, reason: str) -> None:
        self.closed = True
        self.close_reasons.append(reason)


class FakeTournamentSession:
    """脚本化赛事会话：update 按授权逐条发放，便于确定性并发测试。"""

    def __init__(
        self,
        *,
        bootstrap,
        updates=(),
        register_results=None,
        ready_results=None,
        game_factory=None,
    ) -> None:
        self._bootstrap = bootstrap
        self._updates = list(updates)
        self._register_results = list(
            register_results or [RegistrationResult(status=OperationStatus.ACCEPTED)]
        )
        self._ready_results = list(ready_results or [ReadyResult(status=OperationStatus.ACCEPTED)])
        self._game_factory = game_factory
        self.initialize_calls = []
        self.register_calls = 0
        self.ready_calls = []
        self.next_update_calls = 0
        self.game_opens = []
        self.game_open_attempts = []  # 含失败尝试的 open_game 调用记录
        self.opened_games = {}
        self.closed = False
        self._grants = 0
        self._grant_event = asyncio.Event()

    def grant_updates(self, count: int = 1) -> None:
        """放行 count 条下一条 update；不放行时 next_update 挂起。"""

        self._grants += count
        self._grant_event.set()

    async def initialize(self, target: RuntimeTarget):
        self.initialize_calls.append(target)
        return self._bootstrap

    async def register(self):
        self.register_calls += 1
        if not self._register_results:
            return RegistrationResult(status=OperationStatus.ALREADY_DONE)
        item = self._register_results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def ready(self, expected_stage: StageIdentity):
        self.ready_calls.append(expected_stage)
        if not self._ready_results:
            return ReadyResult(status=OperationStatus.ALREADY_DONE)
        item = self._ready_results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def next_update(self):
        self.next_update_calls += 1
        while True:
            if self._grants <= 0:
                self._grant_event.clear()
                if self._grants <= 0:
                    await self._grant_event.wait()
                    continue
            if not self._updates:
                await asyncio.Future()  # 脚本耗尽后挂起，直到被取消
            self._grants -= 1
            item = self._updates.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

    def open_game(self, game_id: str) -> GameSessionPort:
        self.game_open_attempts.append(game_id)
        session = self._game_factory(game_id) if self._game_factory else FakeGameSession()
        self.game_opens.append(game_id)
        self.opened_games[game_id] = session
        return session

    async def aclose(self) -> None:
        self.closed = True


class FakeRules(HangmaRules):
    """脚本化规则模块：候选、紧急路径与复核行为可注入。"""

    def __init__(
        self,
        *,
        config: RuleConfig = None,
        candidates=(),
        emergency=None,
        illegal_keys=(),
        analyze_error: bool = False,
        emergency_error: bool = False,
    ) -> None:
        super().__init__(config if config is not None else RULE_CONFIG)
        self._candidates = tuple(candidates)
        self._emergency = emergency
        self._illegal = frozenset(illegal_keys)
        self._analyze_error = analyze_error
        self._emergency_error = emergency_error
        self.analyze_calls = 0
        self.emergency_calls = 0
        self.validate_calls = []

    def analyze(self, observation) -> RuleAnalysis:
        self.analyze_calls += 1
        if self._analyze_error:
            raise RuntimeError("analyze 故障注入")
        candidates = tuple(
            item
            if isinstance(item, RuleCandidate)
            else RuleCandidate(action=item, action_key=action_key(item), evidence=("fake",))
            for item in self._candidates
        )
        return RuleAnalysis(
            legal_candidates=candidates,
            emergency_candidate=self._emergency_candidate(),
            completeness=RuleCompleteness.COMPLETE,
            ruleset_version=self.config.ruleset_version,
            issues=(),
        )

    def emergency_action(self, observation):
        self.emergency_calls += 1
        return self._emergency_candidate()

    def _emergency_candidate(self):
        if self._emergency_error:
            raise RuntimeError("emergency 故障注入")
        if self._emergency is None:
            return None
        if isinstance(self._emergency, RuleCandidate):
            return self._emergency
        return RuleCandidate(
            action=self._emergency,
            action_key=action_key(self._emergency),
            evidence=("fake",),
        )

    def validate(self, observation, action) -> ActionValidation:
        key = action_key(action)
        self.validate_calls.append(key)
        if key in self._illegal:
            return ActionValidation(legal=False, reason="复核不合法（注入）")
        return ActionValidation(legal=True, reason=None)

    def score(self, win):
        raise NotImplementedError


class FakePolicy:
    """默认按规则候选顺序产出计划；可注入异常、挂起或外部候选。"""

    def __init__(
        self,
        *,
        plan_factory=None,
        hang: bool = False,
        error: Optional[Exception] = None,
        extra_first_candidate=None,
    ) -> None:
        self.calls = []
        self.budgets = []
        self._plan_factory = plan_factory
        self._hang = hang
        self._error = error
        self._extra_first = extra_first_candidate

    async def choose(self, request, budget) -> DecisionPlan:
        self.calls.append(request)
        self.budgets.append(budget)
        if self._hang:
            await asyncio.Future()
        if self._error is not None:
            raise self._error
        if self._plan_factory is not None:
            return self._plan_factory(request)
        rejected = {item.action_key for item in request.rejected_attempts}
        candidates = []
        rank = 1
        for candidate in request.rules.legal_candidates:
            if candidate.action_key in rejected:
                continue
            candidates.append(
                RankedCandidate(
                    action=candidate.action,
                    action_key=candidate.action_key,
                    rank=rank,
                    total_score=float(rank),
                    score_parts=(ScorePart(name="fake", value=float(rank)),),
                    reasons=(),
                )
            )
            rank += 1
        if self._extra_first is not None:
            candidates.insert(
                0,
                RankedCandidate(
                    action=self._extra_first,
                    action_key=action_key(self._extra_first),
                    rank=0,
                    total_score=99.0,
                    score_parts=(),
                    reasons=(),
                ),
            )
        return DecisionPlan(
            decision_id=request.decision_id,
            window_key=request.window_key,
            based_on_authoritative_seq=request.observation.snapshot_seq,
            revision=1,
            candidates=tuple(candidates),
            degraded_reasons=(),
        )


class BarrierPolicy(FakePolicy):
    """第一个 choose 阻塞到第二个到达：证明多场窗口真正并发。"""

    def __init__(self) -> None:
        super().__init__()
        self._arrivals = 0
        self._second = asyncio.Event()

    async def choose(self, request, budget):
        self.calls.append(request)
        self.budgets.append(budget)
        self._arrivals += 1
        if self._arrivals == 1:
            await self._second.wait()
        else:
            self._second.set()
        # 第一个请求被释放后复用默认排序逻辑。
        return await FakePolicy.choose(self, request, budget)


class SequencedIds:
    """确定性标识：run-N / dec-N / sa-{stage}-N。"""

    def __init__(self) -> None:
        self.counter = 0

    def new_run_id(self) -> str:
        self.counter += 1
        return "run-{}".format(self.counter)

    def new_decision_id(self, window_key: WindowKey) -> str:
        self.counter += 1
        return "dec-{}".format(self.counter)

    def new_stage_attempt_id(self, stage_no) -> str:
        self.counter += 1
        return "sa-{}-{}".format(stage_no if stage_no is not None else "x", self.counter)


class InMemoryAuditSink:
    """内存审计槽：记录全部信封，可注入失败与降级。"""

    def __init__(self, *, fail: bool = False, degraded: bool = False) -> None:
        self.records = []
        self.fail = fail
        self.degraded = degraded
        self.closed = False

    def emit(self, record: AuditRecord) -> AuditReceipt:
        if self.fail:
            raise RuntimeError("sink 故障注入")
        self.records.append(record)
        if self.degraded:
            return AuditReceipt(queued=False, audit_degraded=True, reason="注入降级")
        return AuditReceipt(queued=True, audit_degraded=False)

    async def aclose(self, timeout_seconds: float) -> AuditSummary:
        self.closed = True
        return AuditSummary(
            written=len(self.records),
            dropped_low_priority=0,
            missing_high_priority=0,
            serialization_failures=0,
            audit_degraded=self.fail or self.degraded,
        )

    def kinds(self):
        return [record.kind for record in self.records]

    def find(self, kind):
        return [record for record in self.records if record.kind is kind]

    def lifecycle_events(self):
        events = []
        for record in self.records:
            if record.kind.value == "lifecycle_changed":
                events.append(record.payload["event"])
        return events


def make_fake_sleep():
    """记录退避延迟并立即让步的 sleep 替身。"""

    delays = []

    async def _sleep(seconds: float) -> None:
        delays.append(seconds)
        await asyncio.sleep(0)

    _sleep.delays = delays
    return _sleep


async def wait_for_condition(condition, *, limit: int = 5000) -> None:
    """在事件循环内轮询条件；用于跨任务的确定性等待。

    条件在依赖对象就绪前可能抛 KeyError/IndexError，视为未满足继续轮询。
    """

    for _ in range(limit):
        try:
            if condition():
                return
        except (KeyError, IndexError):
            pass
        await asyncio.sleep(0)
    raise AssertionError("等待条件超时（事件循环内轮询）")


def build_runtime(
    *,
    session,
    sink=None,
    policy=None,
    rules=None,
    clock=None,
    ids=None,
    target=None,
    sleep=None,
    supervision=None,
) -> tuple:
    """组装带默认替身的 ParticipantRuntime。

    返回 (runtime, sink, policy, rules, clock, ids, sleep)；
    sleep 供退避序列断言使用。
    """

    sink = sink if sink is not None else InMemoryAuditSink()
    policy = policy if policy is not None else FakePolicy()
    rules = rules if rules is not None else FakeRules(candidates=(DISCARD_3W, PASS), emergency=PASS)
    clock = clock if clock is not None else ManualClock()
    ids = ids if ids is not None else SequencedIds()
    sleep = sleep if sleep is not None else make_fake_sleep()
    runtime = ParticipantRuntime(
        session=session,
        policy=policy,
        audit_sink=sink,
        target=target if target is not None else make_target(),
        rules_factory=lambda _config: rules,
        clock=clock,
        ids=ids,
        supervision=supervision,
        sleep=sleep,
    )
    return runtime, sink, policy, rules, clock, ids, sleep

