"""policy 测试夹具：只通过公开接口构造 DecisionRequest 输入。

夹具不依赖 hangma 真实实现——候选合法性属于规则模块，
这里按冻结契约直接构造 RuleAnalysis（与应用层 Fake 同思路）。
"""

from __future__ import annotations

import asyncio
from typing import Iterable, Optional, Sequence, Tuple

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
    PublicDiscard,
    RulePublicState,
)
from hangma_bot.policy.interface import (
    DecisionBudget,
    DecisionPlan,
    DecisionRequest,
    RejectedAttempt,
)

WEALTH_CODE = "白"


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


def make_rules(
    candidates: Sequence[RuleCandidate],
    emergency: Optional[RuleCandidate] = None,
    completeness: RuleCompleteness = RuleCompleteness.COMPLETE,
    issues: Sequence[RuleIssue] = (),
) -> RuleAnalysis:
    """构造规则分析；默认完整，降级用显式参数表达。"""

    return RuleAnalysis(
        legal_candidates=tuple(candidates),
        emergency_candidate=emergency,
        completeness=completeness,
        ruleset_version="test-rules",
        issues=tuple(issues),
    )


def make_request(
    observation: PlayerObservation,
    rules: RuleAnalysis,
    rejected: Sequence[RejectedAttempt] = (),
    decision_id: str = "d1",
    phase: WindowPhase = WindowPhase.DRAW,
) -> DecisionRequest:
    """按冻结契约组装决策请求；窗口键与观察保持同场、同局、同座位。"""

    return DecisionRequest(
        observation=observation,
        competition=CompetitionContext(
            tournament_id="t1",
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


def make_budget(
    enhancement: float = 100.0,
    fallback: float = 200.0,
    latest: float = 300.0,
) -> DecisionBudget:
    """构造远期预算，配合注入时钟避免真实等待。"""

    return DecisionBudget(enhancement, fallback, latest)


def candidates_for(actions: Iterable[Action]) -> Tuple[RuleCandidate, ...]:
    """把动作序列变成带规范键的规则候选。"""

    return tuple(
        RuleCandidate(action=action, action_key=action_key(action), evidence=())
        for action in actions
    )


def discards_for(codes: Iterable[str]) -> Tuple[RuleCandidate, ...]:
    """按牌码生成弃牌候选。"""

    return candidates_for(Discard(Tile(code)) for code in codes)


def rejected(key: str, attempt_no: int = 1) -> RejectedAttempt:
    """构造一条官方明确拒绝且确认未执行的尝试。"""

    return RejectedAttempt(
        action_key=key,
        official_code="INVALID_ACTION",
        attempt_no=attempt_no,
        based_on_authoritative_seq=10,
    )


def run_choose(policy, request: DecisionRequest, budget: DecisionBudget) -> DecisionPlan:
    """同步驱动异步 choose，便于 unittest 断言。"""

    return asyncio.run(policy.choose(request, budget))


def ranks_by_key(plan: DecisionPlan) -> dict:
    """动作键到排名的映射，便于断言相对顺序。"""

    return {item.action_key: item.rank for item in plan.candidates}
