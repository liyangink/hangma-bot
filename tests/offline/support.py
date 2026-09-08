"""tests/offline 构造辅助：只用公开类型组装决策行 fixture 与 Fake 模拟器。

这是测试构造辅助（evaluation-start §2 明确允许在 tests 内保留构造辅助），
不是生产 codec：request/budget 的编解码用 kernel.serialization 的公开函数
与冻结契约类型组装，RuleAnalysis 的 JSON 形态只服务本目录测试；审计线
交付真实 codec（C1）后生产路径使用组合根注入的解码器，不引用本文件。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Callable, List, Mapping, Optional, Sequence, Tuple

from hangma_bot.hangma.interface import (
    RuleAnalysis,
    RuleCandidate,
    RuleCompleteness,
    RuleIssue,
)
from hangma_bot.kernel.actions import (
    Action,
    Discard,
    Tile,
    WindowKey,
    WindowPhase,
    action_key,
)
from hangma_bot.kernel.observation import (
    CompetitionContext,
    PlayerObservation,
    RulePublicState,
)
from hangma_bot.kernel.serialization import (
    action_from_json,
    action_to_json,
    competition_from_json,
    competition_to_json,
    observation_from_json,
    observation_to_json,
    window_key_from_json,
    window_key_to_json,
)
from hangma_bot.policy.interface import (
    DecisionBudget,
    DecisionPlan,
    DecisionRequest,
    RankedCandidate,
    RejectedAttempt,
)

WEALTH_CODE = "白"

# 契约向量 budget_translation 的旧基准与截止（contract-vectors.json）。
VECTOR_OLD_ORIGIN = 100.0
VECTOR_OLD_DEADLINES = (100.5, 100.7, 100.85)
VECTOR_NEW_ORIGIN = 800.0


# ---------------------------------------------------------------------------
# 观察 / 规则 / 请求构造（只用公开类型）
# ---------------------------------------------------------------------------


def make_observation(**overrides) -> PlayerObservation:
    """构造默认玩家观察；未给字段使用安全的最小默认值。"""

    defaults = dict(
        game_id="g1",
        seat=0,
        round_no=1,
        snapshot_seq=10,
        phase="draw",
        dealer_seat=0,
        turn_seat=0,
        responding_seats=(),
        my_hand=(),
        drawn_tile=None,
        discards=((), (), (), ()),
        melds=((), (), (), ()),
        hand_counts=(13, 13, 13, 13),
        last_discard=None,
        remaining_tile_count=60,
        scores=(0, 0, 0, 0),
        rule_state=RulePublicState(
            wealth_god=Tile(WEALTH_CODE), baotou=False, chain_count=0, catch_play=False
        ),
        public_history=(),
    )
    defaults.update(overrides)
    return PlayerObservation(**defaults)


def candidates_for(actions: Sequence[Action]) -> Tuple[RuleCandidate, ...]:
    """把动作序列变成带规范键的规则候选（facts 为空 = 未生产事实）。"""

    return tuple(
        RuleCandidate(action=action, action_key=action_key(action), evidence=())
        for action in actions
    )


def make_rules(
    candidates: Sequence[RuleCandidate],
    emergency: Optional[RuleCandidate] = None,
    completeness: RuleCompleteness = RuleCompleteness.COMPLETE,
    issues: Sequence[RuleIssue] = (),
    ruleset_version: str = "fixture-rules-v1",
) -> RuleAnalysis:
    """构造规则分析；默认完整，降级用显式参数表达。"""

    return RuleAnalysis(
        legal_candidates=tuple(candidates),
        emergency_candidate=emergency,
        completeness=completeness,
        ruleset_version=ruleset_version,
        issues=tuple(issues),
    )


def make_request(
    observation: PlayerObservation,
    rules: RuleAnalysis,
    decision_id: str = "d1",
    phase: WindowPhase = WindowPhase.DRAW,
    rejected: Sequence[RejectedAttempt] = (),
) -> DecisionRequest:
    """按冻结契约组装决策请求；窗口键与观察保持同场、同局、同座位。"""

    return DecisionRequest(
        observation=observation,
        competition=CompetitionContext(
            tournament_id="t-eval",
            stage_no=None,
            stage_role=None,
            stage_total=None,
            participant_rank=None,
            ranking=(),
            observed_at_unix_ms=0,
        ),
        rules=rules,
        decision_id=decision_id,
        trigger_seq=observation.snapshot_seq,
        window_key=WindowKey(
            game_id=observation.game_id,
            round_no=observation.round_no,
            trigger_seq=observation.snapshot_seq,
            phase=phase,
            seat=observation.seat,
        ),
        rejected_attempts=tuple(rejected),
    )


# ---------------------------------------------------------------------------
# fixture codec：request / budget 的测试编解码（非生产 codec）
# ---------------------------------------------------------------------------


def encode_rules(rules: RuleAnalysis) -> dict:
    def candidate_json(candidate: RuleCandidate) -> dict:
        return {
            "action": action_to_json(candidate.action),
            "action_key": candidate.action_key,
            "evidence": list(candidate.evidence),
            "facts": None,
        }

    return {
        "legal_candidates": [candidate_json(item) for item in rules.legal_candidates],
        "emergency_candidate": (
            None if rules.emergency_candidate is None else candidate_json(rules.emergency_candidate)
        ),
        "completeness": rules.completeness.value,
        "ruleset_version": rules.ruleset_version,
        "issues": [{"area": item.area, "reason": item.reason} for item in rules.issues],
    }


def decode_rules(payload: Mapping) -> RuleAnalysis:
    def candidate_from(data: Mapping) -> RuleCandidate:
        return RuleCandidate(
            action=action_from_json(data["action"]),
            action_key=data["action_key"],
            evidence=tuple(data.get("evidence", [])),
        )

    return RuleAnalysis(
        legal_candidates=tuple(candidate_from(item) for item in payload["legal_candidates"]),
        emergency_candidate=(
            None
            if payload.get("emergency_candidate") is None
            else candidate_from(payload["emergency_candidate"])
        ),
        completeness=RuleCompleteness(payload["completeness"]),
        ruleset_version=payload["ruleset_version"],
        issues=tuple(
            RuleIssue(area=item["area"], reason=item["reason"])
            for item in payload.get("issues", [])
        ),
    )


def encode_request(request: DecisionRequest) -> dict:
    return {
        "observation": observation_to_json(request.observation),
        "competition": competition_to_json(request.competition),
        "rules": encode_rules(request.rules),
        "decision_id": request.decision_id,
        "trigger_seq": request.trigger_seq,
        "window_key": window_key_to_json(request.window_key),
        "rejected_attempts": [
            {
                "action_key": item.action_key,
                "official_code": item.official_code,
                "attempt_no": item.attempt_no,
                "based_on_authoritative_seq": item.based_on_authoritative_seq,
            }
            for item in request.rejected_attempts
        ],
    }


def decode_request(payload: Mapping) -> DecisionRequest:
    return DecisionRequest(
        observation=observation_from_json(payload["observation"]),
        competition=competition_from_json(payload["competition"]),
        rules=decode_rules(payload["rules"]),
        decision_id=payload["decision_id"],
        trigger_seq=payload["trigger_seq"],
        window_key=window_key_from_json(payload["window_key"]),
        rejected_attempts=tuple(
            RejectedAttempt(
                action_key=item["action_key"],
                official_code=item["official_code"],
                attempt_no=item["attempt_no"],
                based_on_authoritative_seq=item["based_on_authoritative_seq"],
            )
            for item in payload.get("rejected_attempts", [])
        ),
    )


def encode_budget(budget: DecisionBudget) -> dict:
    return {
        "enhancement_deadline_monotonic": budget.enhancement_deadline_monotonic,
        "fallback_deadline_monotonic": budget.fallback_deadline_monotonic,
        "latest_send_at_monotonic": budget.latest_send_at_monotonic,
    }


def decode_budget(payload: Mapping, origin: float) -> DecisionBudget:
    return DecisionBudget(
        enhancement_deadline_monotonic=payload["enhancement_deadline_monotonic"],
        fallback_deadline_monotonic=payload["fallback_deadline_monotonic"],
        latest_send_at_monotonic=payload["latest_send_at_monotonic"],
    )


def make_decision_source_row(
    observation: PlayerObservation,
    rules: RuleAnalysis,
    *,
    hand_id: str = "hand-fixture",
    decision_id: str = "d1",
    origin: float = VECTOR_OLD_ORIGIN,
    budget: Optional[DecisionBudget] = None,
    plan_revision: int = 1,
    end_reason: Optional[str] = "submitted",
    decision_complete: bool = True,
) -> dict:
    """按契约 §5.1 组装一行决策记录（fixture 口径，非审计线产物）。"""

    request = make_request(observation, rules, decision_id=decision_id)
    effective_budget = budget or DecisionBudget(*VECTOR_OLD_DEADLINES)
    return {
        "replay_schema_version": 1,
        "hand_id": hand_id,
        "split_group_id": "split-fixture",
        "run_id": "run-fixture",
        "participant_id": "participant-fixture",
        "decision_id": decision_id,
        "plan_revision": plan_revision,
        "request": encode_request(request),
        "budget": encode_budget(effective_budget),
        "budget_origin_monotonic": origin,
        "returned_plan": None,
        "effective_candidates": [],
        "validations": [],
        "attempts": [],
        "end_reason": end_reason,
        "decision_complete": decision_complete,
        "source_refs": [],
    }


# ---------------------------------------------------------------------------
# 测试策略：脚本化选择 / 异常 / 空计划 / 永不返回
# ---------------------------------------------------------------------------


class ScriptedPolicy:
    """脚本化策略：picker 返回 Action（或 None=空计划）；可配置异常/挂起。"""

    def __init__(
        self,
        picker: Callable[[DecisionRequest], Optional[Action]],
        *,
        raise_error: Optional[Exception] = None,
        never_return: bool = False,
    ) -> None:
        self._picker = picker
        self._raise_error = raise_error
        self._never_return = never_return
        self.policy_id = "scripted"
        self.never_event = asyncio.Event()

    async def choose(self, request: DecisionRequest, budget: DecisionBudget) -> DecisionPlan:
        if self._never_return:
            await self.never_event.wait()
        if self._raise_error is not None:
            raise self._raise_error
        action = self._picker(request)
        candidates = ()
        if action is not None:
            candidates = (
                RankedCandidate(
                    action=action,
                    action_key=action_key(action),
                    rank=1,
                    total_score=1.0,
                    score_parts=(),
                    reasons=("scripted",),
                    is_emergency=False,
                ),
            )
        return DecisionPlan(
            decision_id=request.decision_id,
            window_key=request.window_key,
            based_on_authoritative_seq=request.observation.snapshot_seq,
            revision=1,
            candidates=candidates,
            degraded_reasons=(),
        )


def pick_key(key: str) -> Callable[[DecisionRequest], Optional[Action]]:
    """按动作键从规则候选中选动作；不存在返回 None（空计划）。"""

    def picker(request: DecisionRequest) -> Optional[Action]:
        for candidate in request.rules.legal_candidates:
            if candidate.action_key == key:
                return candidate.action
        return None

    return picker


def pick_illegal(code: str) -> Callable[[DecisionRequest], Optional[Action]]:
    """返回一个不在候选中的弃牌（模拟策略 bug）。"""

    def picker(request: DecisionRequest) -> Optional[Action]:
        return Discard(Tile(code))

    return picker


# ---------------------------------------------------------------------------
# Fake 模拟器：只服务编排测试，不实现任何规则推进
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FakeMatchSpec:
    match_id: str
    scenario_id: str
    config: Any
    seed: int
    initial_dealer: int
    initial_scores: Tuple[int, int, int, int]


@dataclass(frozen=True)
class FakeChoice:
    window_key: WindowKey
    action: Action


@dataclass(frozen=True)
class FakeDecision:
    window_key: WindowKey
    observation: PlayerObservation
    timeout_seconds: float = 3.0


@dataclass(frozen=True)
class FakeFrame:
    revision: int
    decisions: Tuple[FakeDecision, ...]
    completed_hands: int
    final_scores: Optional[Tuple[int, int, int, int]] = None
    blocked_reason: Optional[str] = None


@dataclass(frozen=True)
class FakeWorld:
    token: int


class FakeEngine:
    """按 spec 生成脚本帧的 Fake SimulationEngine；advance 做窗口/版本校验。

    frames_factory(spec) -> List[FakeFrame]：每个 start 出的世界一份独立
    脚本，支持同一实例连续跑多场（复式实验）；reject_advance 模拟引擎
    拒绝本帧选择（ValueError）。
    """

    def __init__(
        self,
        frames_factory: Callable[[Any], List[FakeFrame]],
        *,
        reject_advance: bool = False,
    ) -> None:
        self._factory = frames_factory
        self._reject_advance = reject_advance
        self._scripts: dict = {}
        self._cursors: dict = {}
        self._last_frames: dict = {}
        self._next_token = 0
        self.started_specs: List[Any] = []
        self.advance_calls: List[Tuple[int, int, Tuple[Any, ...]]] = []

    def start(self, spec: Any) -> FakeWorld:
        token = self._next_token
        self._next_token += 1
        self.started_specs.append(spec)
        self._scripts[token] = list(self._factory(spec))
        self._cursors[token] = 0
        return FakeWorld(token)

    def frame(self, world: FakeWorld) -> FakeFrame:
        token = world.token
        cursor = self._cursors.get(token, 0)
        script = self._scripts.get(token, [])
        if cursor >= len(script):
            raise AssertionError("脚本帧已耗尽；驱动不应在终态后继续取帧")
        frame = script[cursor]
        self._last_frames[token] = frame
        return frame

    def advance(self, world: FakeWorld, revision: int, choices: Tuple[Any, ...]) -> FakeWorld:
        if self._reject_advance:
            raise ValueError("脚本化拒绝：advance 不可用")
        token = world.token
        last = self._last_frames.get(token)
        if last is None or revision != last.revision:
            raise ValueError("旧 revision 拒绝：{0}".format(revision))
        expected = [item.window_key for item in last.decisions]
        actual = [item.window_key for item in choices]
        if len(actual) != len(expected) or any(
            left != right for left, right in zip(actual, expected)
        ):
            raise ValueError("窗口集合不匹配：期望 {0}，得到 {1}".format(expected, actual))
        self.advance_calls.append((token, revision, tuple(choices)))
        self._cursors[token] = self._cursors.get(token, 0) + 1
        return FakeWorld(token)


class FakeRules:
    """脚本化规则：对每个观察返回同一 RuleAnalysis（编排测试专用）。"""

    def __init__(self, analysis: RuleAnalysis) -> None:
        self.analysis = analysis

    def analyze(self, observation: PlayerObservation) -> RuleAnalysis:
        return self.analysis

    def emergency_action(self, observation: PlayerObservation) -> Optional[RuleCandidate]:
        """编排器在复杂分析前调用的公开紧急路径。"""
        return self.analysis.emergency_candidate


def draw_frame(
    revision: int,
    seats: Sequence[int],
    *,
    completed_hands: int = 0,
    trigger_seq: int = 1,
    timeout_seconds: float = 3.0,
) -> FakeFrame:
    """构造一个每座位各一个摸牌窗口的帧。"""

    decisions = []
    for seat in seats:
        observation = make_observation(
            seat=seat,
            turn_seat=seat,
            snapshot_seq=trigger_seq,
            my_hand=(Tile("1w"), Tile("2w"), Tile("9w")),
            hand_counts=(3, 3, 3, 3),
        )
        decisions.append(
            FakeDecision(
                window_key=WindowKey(
                    game_id="g1",
                    round_no=1,
                    trigger_seq=trigger_seq,
                    phase=WindowPhase.DRAW,
                    seat=seat,
                ),
                observation=observation,
                timeout_seconds=timeout_seconds,
            )
        )
    return FakeFrame(
        revision=revision,
        decisions=tuple(decisions),
        completed_hands=completed_hands,
    )


def final_frame(revision: int, scores: Sequence[int], completed_hands: int) -> FakeFrame:
    return FakeFrame(
        revision=revision,
        decisions=(),
        completed_hands=completed_hands,
        final_scores=(scores[0], scores[1], scores[2], scores[3]),
    )


def blocked_frame(revision: int, reason: str, completed_hands: int = 0) -> FakeFrame:
    return FakeFrame(
        revision=revision,
        decisions=(),
        completed_hands=completed_hands,
        blocked_reason=reason,
    )


# ---------------------------------------------------------------------------
# MatchResult / TournamentConfig 快捷构造（结果与统计测试共用）
# ---------------------------------------------------------------------------


def make_tournament_config(rounds_per_game: int = 8) -> Any:
    from hangma_bot.kernel.config import RuleConfig, TimingConfig, TournamentConfig

    return TournamentConfig(
        max_games=1,
        rounds_per_game=rounds_per_game,
        rules=RuleConfig(ruleset_version="fixture-rules", base_score=1, you_cai_bi_kao=False),
        timing=TimingConfig(peng_timeout_sec=1.0, chi_timeout_sec=1.0, discard_timeout_sec=3.0),
    )


def make_match_result(**overrides) -> Any:
    """构造一个合法 complete 结果行；需要变体时用 overrides 覆盖。"""

    from hangma_bot.offline.evaluation_results import (
        EVALUATION_SCHEMA_VERSION,
        SIMULATION_SOURCE_NAMESPACE,
        GameKey,
        MatchResult,
        RuntimeCounts,
    )

    defaults = dict(
        evaluation_schema_version=EVALUATION_SCHEMA_VERSION,
        result_id="r-1",
        source_kind="simulation",
        scenario_id="sc-1",
        pair_id="p-1",
        game_key=GameKey(SIMULATION_SOURCE_NAMESPACE, "sc-1", "m-1"),
        config=make_tournament_config(),
        policy_ids_by_seat=("stable", "opp-1", "opp-2", "opp-3"),
        seat_permutation=(0, 1, 2, 3),
        expected_hands=8,
        completed_hands=8,
        scores_before=(0, 0, 0, 0),
        scores_after=(10, 0, 0, 0),
        official_ranks=None,
        status="complete",
        invalid_reasons=(),
        runtime_counts=RuntimeCounts(
            timeouts=0, illegal_choices=0, fallbacks=0, auto_actions=0, audit_missing=0
        ),
        versions=(("contract_id", "parallel-v1"),),
        source_refs=(),
    )
    defaults.update(overrides)
    return MatchResult(**defaults)
