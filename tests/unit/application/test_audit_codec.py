"""application/audit_codec 的往返与错误契约测试。

契约（方案 §3.3）：*_to_json/_from_json 纯函数；缺字段、错误类型、
不兼容主版本、非有限浮点抛 ValueError；未知可选扩展键容忍；
胡/吃/碰/杠/过/弃牌候选与 CandidateFacts 完整往返。
"""

from __future__ import annotations

import pytest

from hangma_bot.application.audit_codec import (
    DECISION_CODEC_VERSION,
    candidate_facts_from_json,
    candidate_facts_to_json,
    decision_budget_from_json,
    decision_budget_to_json,
    decision_plan_from_json,
    decision_plan_to_json,
    decision_request_from_json,
    decision_request_to_json,
    rule_analysis_from_json,
    rule_analysis_to_json,
    translate_monotonic_deadlines,
)
from hangma_bot.hangma.interface import (
    CandidateFactKind,
    CandidateFacts,
    RuleAnalysis,
    RuleCandidate,
    RuleCompleteness,
    RuleIssue,
    UsefulTileFact,
)
from hangma_bot.kernel.actions import (
    Chi,
    Discard,
    Gang,
    GangKind,
    Hu,
    Pass,
    Peng,
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
from hangma_bot.policy.interface import (
    DecisionBudget,
    DecisionPlan,
    DecisionRequest,
    RankedCandidate,
    RejectedAttempt,
    ScorePart,
)
from fakes import make_observation


def _analysis_with(candidates, emergency=None):
    return RuleAnalysis(
        legal_candidates=tuple(candidates),
        emergency_candidate=emergency,
        completeness=RuleCompleteness.DEGRADED,
        ruleset_version="rules-v1",
        issues=(RuleIssue(area="engine", reason="注入降级"),),
    )


def _candidate(action, facts=None):
    return RuleCandidate(
        action=action,
        action_key=action_key(action),
        evidence=("官方金例", "本地复核"),
        facts=facts,
    )


def _window_key():
    return WindowKey(
        game_id="g1", round_no=2, trigger_seq=7, phase=WindowPhase.RESPONSE_PENG, seat=1
    )


def _request(candidates=(), rejected=()):
    return DecisionRequest(
        observation=make_observation(game_id="g1", round_no=2, seq=7, phase="response_peng"),
        competition=CompetitionContext(
            tournament_id="t1", stage_no=1, stage_role="main", stage_total=2,
            participant_rank=2, ranking=(), observed_at_unix_ms=123,
        ),
        rules=_analysis_with(candidates, candidates[0] if candidates else None),
        decision_id="dec-1",
        trigger_seq=7,
        window_key=_window_key(),
        rejected_attempts=tuple(rejected),
    )


def test_request_round_trip_all_action_families():
    """胡/吃/碰/杠/过/弃牌候选与拒绝历史完整往返。"""

    candidates = [
        _candidate(Hu(), CandidateFacts(
            fact_kind=CandidateFactKind.WIN, shanten_after=-1,
            completeness=RuleCompleteness.COMPLETE,
        )),
        _candidate(Chi((Tile("1w"), Tile("2w"), Tile("3w"))),
                   CandidateFacts(
                       fact_kind=CandidateFactKind.HAND_PROGRESS,
                       shanten_after=1,
                       useful_tiles=(UsefulTileFact(code="4w", remaining_estimate=2),),
                       best_followup_discard="5b",
                   )),
        _candidate(Peng(Tile("东"))),
        _candidate(Gang(Tile("中"), GangKind.CONCEALED),
                   CandidateFacts(
                       fact_kind=CandidateFactKind.HAND_PROGRESS,
                       shanten_after=2,
                       replacement_draw_unknown=True,
                       completeness=RuleCompleteness.COMPLETE,
                   )),
        _candidate(Pass(), CandidateFacts(
            fact_kind=CandidateFactKind.NOT_APPLICABLE, shanten_after=None
        )),
        _candidate(Discard(Tile("9t")), None),
    ]
    request = _request(candidates=candidates, rejected=(
        RejectedAttempt(action_key="discard:1w", official_code="CONFLICT",
                        attempt_no=1, based_on_authoritative_seq=5),
    ))
    encoded = decision_request_to_json(request)
    assert encoded["codec_version"] == DECISION_CODEC_VERSION
    restored = decision_request_from_json(encoded)
    assert restored == request
    # 手牌顺序保留：不排序不重排（观察权限契约）。
    assert [tile.code for tile in restored.observation.my_hand] == [
        tile.code for tile in request.observation.my_hand
    ]


def test_budget_round_trip_and_order_check():
    budget = DecisionBudget(10.5, 11.0, 11.7)
    restored = decision_budget_from_json(decision_budget_to_json(budget))
    assert restored == budget
    broken = decision_budget_to_json(budget)
    broken["latest_send_at_monotonic"] = 9.0  # 违反先后关系
    with pytest.raises(ValueError):
        decision_budget_from_json(broken)


def test_plan_round_trip_scores_and_parts():
    plan = DecisionPlan(
        decision_id="dec-1",
        window_key=_window_key(),
        based_on_authoritative_seq=7,
        revision=2,
        candidates=(
            RankedCandidate(
                action=Discard(Tile("3w")),
                action_key="discard:3w",
                rank=1,
                total_score=1.5,
                score_parts=(ScorePart(name="speed", value=0.8), ScorePart(name="safety", value=0.7)),
                reasons=("策略评分",),
                is_emergency=False,
            ),
        ),
        degraded_reasons=("规则降级",),
    )
    restored = decision_plan_from_json(decision_plan_to_json(plan))
    assert restored == plan


def test_analysis_failed_facts_round_trip():
    candidate = _candidate(Discard(Tile("1w")), CandidateFacts(
        fact_kind=CandidateFactKind.ANALYSIS_FAILED,
        shanten_after=None,
        completeness=RuleCompleteness.DEGRADED,
        note="手牌分析异常",
    ))
    restored = candidate_facts_from_json(candidate_facts_to_json(candidate.facts))
    assert restored == candidate.facts


def test_missing_required_field_raises():
    encoded = decision_budget_to_json(DecisionBudget(1.0, 2.0, 3.0))
    del encoded["latest_send_at_monotonic"]
    with pytest.raises(ValueError):
        decision_budget_from_json(encoded)


def test_wrong_type_raises():
    encoded = decision_budget_to_json(DecisionBudget(1.0, 2.0, 3.0))
    encoded["enhancement_deadline_monotonic"] = "1.0"
    with pytest.raises(ValueError):
        decision_budget_from_json(encoded)


def test_non_finite_float_rejected():
    with pytest.raises(ValueError):
        decision_budget_from_json(
            {"codec_version": 1, "enhancement_deadline_monotonic": float("nan"),
             "fallback_deadline_monotonic": 2.0, "latest_send_at_monotonic": 3.0}
        )
    with pytest.raises(ValueError):
        decision_budget_from_json(
            {"codec_version": 1, "enhancement_deadline_monotonic": 1.0,
             "fallback_deadline_monotonic": float("inf"), "latest_send_at_monotonic": 3.0}
        )


def test_unknown_codec_version_rejected():
    encoded = decision_budget_to_json(DecisionBudget(1.0, 2.0, 3.0))
    encoded["codec_version"] = 99
    with pytest.raises(ValueError):
        decision_budget_from_json(encoded)


def test_unknown_optional_key_tolerated():
    encoded = decision_budget_to_json(DecisionBudget(1.0, 2.0, 3.0))
    encoded["future_extension"] = {"anything": True}
    assert decision_budget_from_json(encoded) == DecisionBudget(1.0, 2.0, 3.0)


def test_rule_analysis_round_trip_none_emergency():
    analysis = _analysis_with([_candidate(Pass())], emergency=None)
    restored = rule_analysis_from_json(rule_analysis_to_json(analysis))
    assert restored == analysis
    assert restored.emergency_candidate is None


def test_translate_monotonic_deadlines_preserves_offsets():
    translated = translate_monotonic_deadlines(100.0, [100.5, 100.7, 100.85], 800.0)
    assert translated == (800.5, 800.7, 800.85)
    with pytest.raises(ValueError):
        translate_monotonic_deadlines(float("nan"), [1.0], 2.0)
    with pytest.raises(ValueError):
        translate_monotonic_deadlines(1.0, [1.0], float("inf"))
