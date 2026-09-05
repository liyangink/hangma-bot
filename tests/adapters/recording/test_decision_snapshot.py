"""DECISION_PLANNED 决策观察快照契约测试（2026-09-04 审计增强）。

本文件放在 tests/adapters/recording/ 下：它锁定的不是 decision_loop 的
控制流，而是 DECISION_PLANNED 审计 payload 的观察快照词表——被拒动作
可本地复盘的最小可见事实（任务 4/4 的第 2 项）。生产实现见
src/hangma_bot/application/decision_loop.py 的 _observation_snapshot。

信息权限红线（kernel/AGENTS.md + 接口协议 §4.1）：快照只含 PlayerObservation
口径的可见信息——my_hand 保留官方原始顺序、drawn_tile 单列不并入手牌、
不含他家手牌/牌河/事件史/未来牌墙。
"""

import asyncio

from hangma_bot.application.audit import AuditTrail
from hangma_bot.application.contracts import (
    AuditReceipt,
    AuditRecord,
    AuditSummary,
    ObservedActionWindow,
    SubmitAccepted,
    SubmitOutcome,
    SubmitRejectedRetryable,
)
from hangma_bot.application.deadline import BudgetPolicy, ManualClock
from hangma_bot.application.decision_loop import RuntimeServices, run_action_window
from hangma_bot.application.ids import PrefixedUuidIds
from hangma_bot.hangma.interface import ActionValidation, RuleAnalysis, RuleCandidate, RuleCompleteness
from hangma_bot.kernel.actions import (
    Discard,
    Peng,
    Tile,
    WindowKey,
    WindowPhase,
    action_key,
)
from hangma_bot.kernel.observation import (
    CompetitionContext,
    PlayerObservation,
    PublicDiscard,
    PublicMeld,
    RulePublicState,
)
from hangma_bot.kernel.serialization import action_from_json
from hangma_bot.policy.interface import (
    DecisionPlan,
    RankedCandidate,
    ScorePart,
)


class InMemorySink:
    """最小 AuditSink：只收集记录，不做磁盘写。"""

    def __init__(self):
        self.records = []

    def emit(self, record: AuditRecord) -> AuditReceipt:
        self.records.append(record)
        return AuditReceipt(queued=True, audit_degraded=False, reason=None)

    async def aclose(self, timeout_seconds: float) -> AuditSummary:
        return AuditSummary(
            written=len(self.records),
            dropped_low_priority=0,
            missing_high_priority=0,
            serialization_failures=0,
            audit_degraded=False,
        )


class FakeRules:
    """脚本化规则模块：候选与复核可注入（仅测试，不复刻生产规则）。"""

    class _Config:
        ruleset_version = "test-rules-v1"

    def __init__(self, candidates=(), emergency=None):
        self._candidates = tuple(candidates)
        self._emergency = emergency
        self.config = self._Config()

    def emergency_action(self, observation):
        return self._emergency

    def analyze(self, observation) -> RuleAnalysis:
        candidates = tuple(
            item
            if isinstance(item, RuleCandidate)
            else RuleCandidate(action=item, action_key=action_key(item), evidence=("test",))
            for item in self._candidates
        )
        return RuleAnalysis(
            legal_candidates=candidates,
            emergency_candidate=self._emergency,
            completeness=RuleCompleteness.COMPLETE,
            ruleset_version=self.config.ruleset_version,
            issues=(),
        )

    def validate(self, observation, action) -> ActionValidation:
        return ActionValidation(legal=True, reason=None)


class FakePolicy:
    """按规则候选顺序产出计划；记录 request 供断言。"""

    def __init__(self):
        self.calls = []

    async def choose(self, request, budget) -> DecisionPlan:
        self.calls.append(request)
        candidates = tuple(
            RankedCandidate(
                action=candidate.action,
                action_key=candidate.action_key,
                rank=rank,
                total_score=float(rank),
                score_parts=(ScorePart(name="test", value=float(rank)),),
                reasons=("测试原因",),
            )
            for rank, candidate in enumerate(request.rules.legal_candidates, start=1)
        )
        return DecisionPlan(
            decision_id=request.decision_id,
            window_key=request.window_key,
            based_on_authoritative_seq=request.observation.snapshot_seq,
            revision=1,
            candidates=candidates,
            degraded_reasons=(),
        )


class FakeSession:
    """脚本化场次会话：submit 结果可注入。"""

    def __init__(self, handler=None):
        self._handler = handler or (lambda attempt: SubmitAccepted(official_code=None, authoritative_seq=None))
        self.submitted = []

    async def submit(self, attempt) -> SubmitOutcome:
        self.submitted.append(attempt)
        return self._handler(attempt)


def _observation(seq: int = 10, phase: str = "response_peng", responding_seats=(0,)) -> PlayerObservation:
    """构造带刻意"非规范手牌顺序"与目标弃牌的观察。"""

    my_meld = PublicMeld(seat=0, kind="chi", tiles=(Tile("1w"), Tile("2w"), Tile("3w")), from_seat=1)
    other_meld = PublicMeld(seat=1, kind="peng", tiles=(Tile("6w"), Tile("6w"), Tile("6w")), from_seat=3)
    return PlayerObservation(
        game_id="g1",
        seat=0,
        round_no=1,
        snapshot_seq=seq,
        phase=phase,
        dealer_seat=0,
        turn_seat=0,
        responding_seats=tuple(responding_seats),
        # 官方原始顺序（非排序形态）：快照必须原样保留，验证顺序敏感契约。
        my_hand=(Tile("9w"), Tile("1w"), Tile("东"), Tile("2w")),
        drawn_tile=Tile("5w"),
        discards=((), (Tile("2w"),), (), ()),
        melds=((my_meld,), (other_meld,), (), ()),
        hand_counts=(10, 10, 13, 10),
        last_discard=PublicDiscard(seat=1, tile=Tile("2w"), seq=seq),
        remaining_tile_count=40,
        scores=(10, 4, -2, -12),
        rule_state=RulePublicState(
            wealth_god=Tile("白"), baotou=False, chain_count=0, catch_play=False
        ),
        public_history=(),
    )


def _window(observation: PlayerObservation) -> ObservedActionWindow:
    key = WindowKey(
        game_id=observation.game_id,
        round_no=observation.round_no,
        trigger_seq=observation.snapshot_seq,
        phase=WindowPhase.RESPONSE_PENG,
        seat=observation.seat,
    )
    return ObservedActionWindow(
        observation=observation,
        window_key=key,
        authoritative_seq=observation.snapshot_seq,
        received_at_monotonic=100.0,
        timeout_seconds=3.0,
    )


def _competition() -> CompetitionContext:
    return CompetitionContext(
        tournament_id="t1",
        stage_no=1,
        stage_role=None,
        stage_total=None,
        participant_rank=None,
        ranking=(),
        observed_at_unix_ms=1,
    )


async def _run_window(handler=None, rules=None, policy=None, observation=None):
    """驱动一次完整动作窗口，返回 (sink, policy, rules)。"""

    observation = observation if observation is not None else _observation()
    clock = ManualClock(start_monotonic=100.0)
    sink = InMemorySink()
    trail = AuditTrail(
        sink,
        run_id="run-1",
        tournament_id="t1",
        participant_id="P1",
        clock=clock,
    )
    rules = rules if rules is not None else FakeRules(candidates=(Peng(Tile("2w")), Discard(Tile("1w"))))
    policy = policy if policy is not None else FakePolicy()
    services = RuntimeServices(
        rules=rules,
        policy=policy,
        audit=trail,
        clock=clock,
        ids=PrefixedUuidIds(),
        budget_policy=BudgetPolicy(),
    )
    session = FakeSession(handler)
    await run_action_window(
        session=session,
        window=_window(observation),
        services=services,
        competition=_competition(),
        stage_attempt_id="st-1",
    )
    return sink, policy, rules


def _planned(sink: InMemorySink) -> dict:
    records = [r for r in sink.records if r.kind.value == "decision_planned"]
    assert records, "窗口必须产生 DECISION_PLANNED 记录"
    return records[-1].payload


async def test_decision_planned_carries_observation_snapshot():
    """快照含手牌/摸牌/阶段/响应上下文/目标弃牌，且保留官方原始顺序。"""

    sink, *_ = await _run_window()
    payload = _planned(sink)
    snapshot = payload["observation_snapshot"]
    assert snapshot["schema_version"] == 1
    # 官方原始顺序：9w, 1w, 东, 2w（刻意非排序形态）。
    assert snapshot["my_hand"] == ["9w", "1w", "东", "2w"]
    assert snapshot["drawn_tile"] == "5w"  # 摸牌单列，不并入手牌
    assert snapshot["phase"] == "response_peng"
    assert snapshot["seat"] == 0
    assert snapshot["responding"] is True
    assert snapshot["responding_seats"] == [0]
    # 目标弃牌：座位 + 牌 + 触发事件序号（复盘吃/碰归属必需）。
    assert snapshot["target_discard"] == {"seat": 1, "tile": "2w", "seq": 10}
    assert snapshot["rule_state"] == {
        "wealth_god": "白",
        "baotou": False,
        "chain_count": 0,
        "catch_play": False,
    }
    assert snapshot["hand_counts"] == [10, 10, 13, 10]
    assert snapshot["remaining_tile_count"] == 40


async def test_snapshot_holds_only_my_visible_information():
    """信息权限红线：快照不含他家手牌/牌河/事件史，副露只含本人行。"""

    sink, *_ = await _run_window()
    snapshot = _planned(sink)["observation_snapshot"]
    # 不含公开牌河与事件史（这些由 RAW_PROTOCOL_STATE 原文全量保留）。
    assert "discards" not in snapshot
    assert "public_history" not in snapshot
    # 副露只保留本人行：seat 1 的碰牌不得出现。
    assert snapshot["my_melds"] == [
        {"kind": "chi", "tiles": ["1w", "2w", "3w"], "from_seat": 1}
    ]
    # 类型上没有承载他家手牌/未来牌墙的字段。
    for forbidden in ("others_hands", "wall_order", "future_tiles"):
        assert forbidden not in snapshot


async def test_candidates_include_full_action_for_replay():
    """候选动作完整列表：action 可经 kernel 稳定序列化无损还原。"""

    sink, *_ = await _run_window()
    candidates = _planned(sink)["candidates"]
    assert [c["action_key"] for c in candidates] == ["peng:2w", "discard:1w"]
    first = candidates[0]
    assert first["is_emergency"] is False
    assert first["rank"] == 1
    assert first["reasons"] == ["测试原因"]
    restored = action_from_json(first["action"])
    assert isinstance(restored, Peng)
    assert action_key(restored) == "peng:2w"
    assert candidates[1]["action"] == {
        "schema_version": 1,
        "kind": "discard",
        "tile": "1w",
    }


async def test_replan_after_rejection_snapshots_refreshed_authority():
    """409 拒绝重规划：第二次计划的快照基于刷新后的权威序号。"""

    base_observation = _observation(seq=10)

    def handler(attempt):
        if attempt.attempt_no == 1:
            refreshed_observation = _observation(seq=11)
            refreshed = ObservedActionWindow(
                observation=refreshed_observation,
                window_key=attempt.window_key,
                authoritative_seq=11,
                received_at_monotonic=100.5,
                timeout_seconds=3.0,
            )
            return SubmitRejectedRetryable(
                official_code="INVALID_ACTION",
                rejected_action_key=attempt.action_key,
                refreshed_window=refreshed,
            )
        return SubmitAccepted(official_code=None, authoritative_seq=None)

    sink, *_ = await _run_window(handler=handler, observation=base_observation)
    planned = [
        r.payload for r in sink.records if r.kind.value == "decision_planned"
    ]
    assert len(planned) == 2
    assert planned[0]["based_on_authoritative_seq"] == 10
    assert planned[1]["based_on_authoritative_seq"] == 11
    assert planned[1]["observation_snapshot"]["snapshot_seq"] == 11
    # 重规划后的候选排除已拒绝动作：只剩 discard:1w。
    assert [c["action_key"] for c in planned[1]["candidates"]] == ["discard:1w"]
