"""共享提交的跨线验收：真实经验生产器 → 目标计算 → choose → 生产审计。

积分情景均为人工构造，不是官方规则金例或策略强度证据。
"""

import asyncio
import json
from dataclasses import fields, replace

import pytest

from hangma_bot.application.audit_codec import decision_plan_from_json, decision_plan_to_json, decision_request_from_json, decision_request_to_json
from hangma_bot.bootstrap import build_outcome_policy
from hangma_bot.competition.outcome_utility import expected_utility
from hangma_bot.kernel.actions import Chi, Discard, Gang, GangKind, Hu, Pass, Peng, Tile, action_key
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.outcome_codec import observation_key, outcome_batch_from_json, outcome_batch_to_json, objective_from_json, objective_to_json
from hangma_bot.kernel.outcome_codec import rules_context_key
from hangma_bot.kernel.outcomes import CandidateOutcome, HandObjectiveKind, HandOutcomeObjective, JointOutcome, MeanOutcome, OutcomeAtom, OutcomeBatch, OutcomeModelVersion
from hangma_bot.learning.outcome_model import CandidateOutcomeSample, EmpiricalOutcomeModel, OutcomeQuery
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2
from hangma_bot.policy.interface import DecisionBudget, RejectedAttempt
from tests.unit.policy.support import candidates_for, make_observation, make_request, make_rules


def make_candidate(action):
    return candidates_for((action,))[0]


@pytest.fixture
def version():
    return OutcomeModelVersion(
        model_id="contract-empirical-v1", ruleset_version="test-rules", rules_hash=rules_context_key(RuleConfig("test-rules", 1, False), "fixture-rules-source"),
        feature_schema_version="exact-visible-binding-v1", action_schema_version="action-v1",
        training_data_id="synthetic-contract-v1", continuation_policy_id="fixed-baseline",
        opponent_pool_id="fixture-pool", sampler_version="synthetic", calibration_version="uncalibrated",
        engine_commit="fixture-source", guide_api_version="fixture-no-official-claim",
    )


@pytest.fixture
def request_case():
    a, b = make_candidate(Discard(Tile("1w"))), make_candidate(Discard(Tile("2w")))
    return make_request(make_observation(my_hand=(Tile("1w"), Tile("2w"))), make_rules((a, b), emergency=a))


@pytest.fixture
def budget():
    return DecisionBudget(10.0, 11.0, 12.0)


def make_model(request, version, output="joint"):
    """A 半数 +12/半数 -12，B 必得 +3；固定目标与净分目标应不同。"""
    key = observation_key(request.observation)
    a, b = request.rules.legal_candidates
    return EmpiricalOutcomeModel((
        CandidateOutcomeSample(key, a.action_key, (12, -4, -4, -4)),
        CandidateOutcomeSample(key, a.action_key, (-12, 4, 4, 4)),
        CandidateOutcomeSample(key, b.action_key, (3, -1, -1, -1)),
    ), version, output=output)


def build_policy(version, predictor, objective=None, clock=lambda: 0.0, baseline=None):
    return build_outcome_policy(
        baseline=baseline or ComparableHeuristicPolicyV2(monotonic=clock), predictor=predictor,
        expected_version=version, monotonic=clock,
        rule_config=RuleConfig("test-rules", 1, False), rules_source_hash="fixture-rules-source",
        objective=objective or (lambda request: HandOutcomeObjective(HandObjectiveKind.EXPECTED_SCORE, request.observation.seat, "synthetic-net-score-v1")),
    )


@pytest.mark.parametrize("output", ["mean", "joint"])
async def test_real_producer_utility_policy_and_audit(request_case, version, budget, output):
    model = make_model(request_case, version, output)
    policy = build_policy(version, model.predict)
    plan = await policy.choose(request_case, budget)
    assert [c.action_key for c in plan.candidates] == ["discard:2w", "discard:1w"]
    assert [c.total_score for c in plan.candidates] == [3, 0]
    assert plan.candidates[1].is_emergency
    assert plan.outcome_trace.status == "applied"
    for c in plan.candidates:
        assert c.total_score == sum(p.value for p in c.score_parts)
    encoded = json.loads(json.dumps(decision_plan_to_json(plan), allow_nan=False))
    assert decision_plan_from_json(encoded) == plan
    assert plan.outcome_trace.batch == outcome_batch_from_json(outcome_batch_to_json(plan.outcome_trace.batch))


async def test_nonlinear_target_requires_joint_distribution(request_case, version, budget):
    objective = lambda _: HandOutcomeObjective(HandObjectiveKind.TARGET_PROBABILITY, 0, "synthetic-target-v1", 10)
    joint = await build_policy(version, make_model(request_case, version).predict, objective).choose(request_case, budget)
    assert joint.candidates[0].action_key == "discard:1w"
    assert joint.candidates[0].total_score == .5
    mean = await build_policy(version, make_model(request_case, version, "mean").predict, objective).choose(request_case, budget)
    baseline = await ComparableHeuristicPolicyV2(monotonic=lambda: 0).choose(request_case, budget)
    assert mean.candidates == baseline.candidates
    assert mean.outcome_trace.reason == "result_or_objective_incompatible"
    with pytest.raises(ValueError, match="joint_distribution_required"):
        expected_utility(MeanOutcome((0, 0, 0, 0)), objective(None))


async def test_outputs_match_keys_not_array_position(request_case, version, budget):
    model = make_model(request_case, version)
    async def reversed_output(query):
        batch = await model.predict(query)
        return replace(batch, candidates=tuple(reversed(batch.candidates)))
    plan = await build_policy(version, reversed_output).choose(request_case, budget)
    assert plan.candidates[0].action_key == "discard:2w"
    assert plan.candidates[0].total_score == 3


@pytest.mark.parametrize("field", [f.name for f in fields(OutcomeModelVersion)])
async def test_each_provenance_field_is_checked(request_case, version, budget, field):
    model = make_model(request_case, version)
    async def changed_version(query):
        batch = await model.predict(query)
        return replace(batch, version=replace(version, **{field: "mismatched"}))
    plan = await build_policy(version, changed_version).choose(request_case, budget)
    assert plan.outcome_trace.reason == "model_version_mismatch"


@pytest.mark.parametrize("mutation,reason", [
    ("stale", "stale_observation"), ("missing", "candidate_coverage_mismatch"),
    ("extra", "candidate_coverage_mismatch"), ("wrong_type", "model_result_invalid"),
])
async def test_invalid_batch_cannot_partially_rerank(request_case, version, budget, mutation, reason):
    model = make_model(request_case, version)
    async def changed(query):
        batch = await model.predict(query)
        if mutation == "stale":
            return replace(batch, observation_key="older-observation")
        if mutation == "missing":
            return replace(batch, candidates=batch.candidates[:1])
        if mutation == "extra":
            return replace(batch, candidates=batch.candidates + (CandidateOutcome("pass", MeanOutcome((0, 0, 0, 0))),))
        return None
    plan = await build_policy(version, changed).choose(request_case, budget)
    baseline = await ComparableHeuristicPolicyV2(monotonic=lambda: 0).choose(request_case, budget)
    assert plan.candidates == baseline.candidates
    assert plan.outcome_trace.reason == reason


async def test_missing_model_and_unknown_objective_restore_baseline(request_case, version, budget):
    missing = await build_policy(version, None).choose(request_case, budget)
    assert missing.outcome_trace.reason == "model_missing"
    async def never(query):
        pytest.fail("目标未知时不应运行模型")
    unknown = lambda _: HandOutcomeObjective(HandObjectiveKind.UNAVAILABLE, 0, "context-v1", reason="ranking_stale")
    plan = await build_policy(version, never, unknown).choose(request_case, budget)
    assert plan.candidates == missing.candidates
    assert plan.outcome_trace.reason == "objective_unavailable"
    assert decision_plan_from_json(decision_plan_to_json(plan)) == plan


async def test_expired_budget_uses_emergency_without_model(request_case, version, budget):
    async def never(query):
        pytest.fail("预算已耗尽时不应运行模型")
    plan = await build_policy(version, never, clock=lambda: 10).choose(request_case, budget)
    assert plan.outcome_trace.reason == "budget_exhausted"
    assert len(plan.candidates) == 1 and plan.candidates[0].is_emergency


async def test_late_result_cannot_extend_original_deadline(request_case, version, budget):
    now = [0.0]
    model = make_model(request_case, version)
    async def late(query):
        batch = await model.predict(query)
        now[0] = 10.0
        return batch
    plan = await build_policy(version, late, clock=lambda: now[0]).choose(request_case, budget)
    assert plan.outcome_trace.reason == "model_timeout"
    assert budget == DecisionBudget(10, 11, 12)


async def test_model_timeout_and_exception_restore_baseline(request_case, version, budget):
    async def timed_out(query):
        raise TimeoutError
    async def broken(query):
        raise RuntimeError("private details must not enter audit")
    for predictor, reason in ((timed_out, "model_timeout"), (broken, "model_or_objective_error")):
        plan = await build_policy(version, predictor).choose(request_case, budget)
        assert plan.outcome_trace.reason == reason
        assert "private details" not in json.dumps(decision_plan_to_json(plan))


async def test_external_cancellation_is_not_swallowed(request_case, version, budget):
    entered = asyncio.Event()
    async def pending(query):
        entered.set()
        await asyncio.Event().wait()
    task = asyncio.create_task(build_policy(version, pending).choose(request_case, budget))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_retry_filters_rejected_candidates_before_prediction(request_case, version, budget):
    request_case = replace(request_case, rejected_attempts=(RejectedAttempt("discard:1w", "409", 1, 10),))
    model = make_model(request_case, version)
    seen = []
    async def predict(query):
        seen.extend(c.action_key for c in query.candidates)
        return await model.predict(query)
    plan = await build_policy(version, predict).choose(request_case, budget)
    assert seen == ["discard:2w"]
    assert [c.action_key for c in plan.candidates] == seen
    assert plan.revision == 2


async def test_immediate_hu_and_old_plan_codec(request_case, version, budget):
    hu = make_candidate(Hu())
    request_case = replace(request_case, rules=replace(request_case.rules, legal_candidates=(hu,) + request_case.rules.legal_candidates))
    async def never(query):
        pytest.fail("合法立即胡由基线处理")
    plan = await build_policy(version, never).choose(request_case, budget)
    assert isinstance(plan.candidates[0].action, Hu)
    assert plan.outcome_trace.reason == "immediate_hu"
    old_plan = replace(plan, outcome_trace=None)
    encoded = decision_plan_to_json(old_plan)
    assert "outcome_trace" not in encoded
    assert decision_plan_from_json(encoded) == old_plan
    assert decision_request_from_json(decision_request_to_json(request_case)) == request_case


@pytest.mark.parametrize("action", [Discard(Tile("1w")), Pass(), Peng(Tile("1w")), Chi((Tile("1w"), Tile("2w"), Tile("3w"))), Gang(Tile("1w"), GangKind.CONCEALED), Hu()])
async def test_model_query_covers_all_action_families(request_case, version, action):
    candidate = make_candidate(action)
    key = observation_key(request_case.observation)
    model = EmpiricalOutcomeModel((CandidateOutcomeSample(key, action_key(action), (3, -1, -1, -1)),), version)
    batch = await model.predict(OutcomeQuery(request_case.observation, (candidate,), "test-rules"))
    assert batch.candidates[0].action_key == action_key(action)


def test_observation_binding_covers_public_context_and_no_teacher_fields(request_case):
    obs = request_case.observation
    key = observation_key(obs)
    assert key == observation_key(replace(obs))
    for change in ({"snapshot_seq": 11}, {"discards": ((Tile("3w"),), (), (), ())}, {"history_complete": True}, {"remaining_tile_count": 59}):
        assert key != observation_key(replace(obs, **change))
    assert {f.name for f in fields(OutcomeQuery)} == {"observation", "candidates", "ruleset_version"}


@pytest.mark.parametrize("scores", [(float("nan"), 0, 0, 0), (float("inf"), 0, 0, 0), (True, -1, 0, 0), (1, 0, 0, 0), (0, 0, 0)])
def test_nonfinite_or_nonzero_sum_outcomes_rejected(scores):
    with pytest.raises(ValueError):
        MeanOutcome(scores)


def test_joint_probabilities_and_tagged_codec_are_strict(version, request_case):
    for probabilities in ((.3, .3), (-.1, 1.1), (float("nan"),), (True,)):
        with pytest.raises(ValueError):
            JointOutcome(tuple(OutcomeAtom((0, 0, 0, 0), p) for p in probabilities))
    batch = OutcomeBatch(observation_key(request_case.observation), version, (CandidateOutcome("pass", MeanOutcome((0, 0, 0, 0))),))
    for wrong in (True, 0, 2):
        encoded = outcome_batch_to_json(batch)
        encoded["schema_version"] = wrong
        with pytest.raises(ValueError):
            outcome_batch_from_json(encoded)
    encoded = outcome_batch_to_json(batch)
    encoded["candidates"][0]["estimate"]["kind"] = "independent_marginals"
    with pytest.raises(ValueError):
        outcome_batch_from_json(encoded)
    with pytest.raises(ValueError):
        replace(batch, candidates=batch.candidates * 2)


@pytest.mark.parametrize("seat", range(4))
def test_physical_seat_order_and_objective_roundtrip(seat):
    estimate = MeanOutcome((6, -1, -2, -3))
    objective = HandOutcomeObjective(HandObjectiveKind.EXPECTED_SCORE, seat, "synthetic")
    assert expected_utility(estimate, objective) == estimate.score_delta[seat]
    assert objective_from_json(objective_to_json(objective)) == objective


@pytest.mark.parametrize("kind", ["empty", "stale", "wrong_action", "error"])
async def test_bad_baseline_retains_prebuilt_emergency(request_case, version, budget, kind):
    baseline = await ComparableHeuristicPolicyV2(monotonic=lambda: 0).choose(request_case, budget)
    class BrokenBaseline:
        async def choose(self, request, budget):
            if kind == "error":
                raise RuntimeError("broken")
            if kind == "empty":
                return replace(baseline, candidates=())
            if kind == "stale":
                return replace(baseline, based_on_authoritative_seq=9)
            return replace(baseline, candidates=(replace(baseline.candidates[0], action=Pass()),))
    result = await build_policy(version, None, baseline=BrokenBaseline()).choose(request_case, budget)
    assert result.outcome_trace.reason == ("baseline_error" if kind == "error" else "baseline_invalid")
    assert len(result.candidates) == 1 and result.candidates[0].is_emergency


async def test_rules_and_target_identity_mismatch(request_case, version, budget):
    model = make_model(request_case, version)
    wrong_rules = replace(request_case, rules=replace(request_case.rules, ruleset_version="other"))
    result = await build_policy(version, model.predict).choose(wrong_rules, budget)
    assert result.outcome_trace.reason == "rules_version_mismatch"
    other_seat = lambda _: HandOutcomeObjective(HandObjectiveKind.EXPECTED_SCORE, 1, "fixture")
    result = await build_policy(version, model.predict, other_seat).choose(request_case, budget)
    assert result.outcome_trace.reason == "objective_seat_mismatch"


def test_joint_payload_work_is_bounded():
    from hangma_bot.kernel.outcomes import MAX_OUTCOME_ATOMS
    with pytest.raises(ValueError, match="工作量上限"):
        JointOutcome(tuple(OutcomeAtom((0, 0, 0, 0), 1 / (MAX_OUTCOME_ATOMS + 1)) for _ in range(MAX_OUTCOME_ATOMS + 1)))


@pytest.mark.parametrize("value", [True, float("nan"), None])
def test_target_cannot_guess_missing_numeric_value(value):
    with pytest.raises(ValueError):
        HandOutcomeObjective(HandObjectiveKind.TARGET_PROBABILITY, 0, "fixture", value)


@pytest.mark.parametrize("config,source", [(RuleConfig("test-rules", 2, False), "fixture-rules-source"),
                                           (RuleConfig("test-rules", 1, True), "fixture-rules-source"),
                                           (RuleConfig("test-rules", 1, False), "changed-source")])
async def test_runtime_configuration_is_checked_independently_of_artifact(request_case, version, budget, config, source):
    model = make_model(request_case, version)
    policy = build_outcome_policy(baseline=ComparableHeuristicPolicyV2(monotonic=lambda: 0),
                                  predictor=model.predict, expected_version=version,
                                  rule_config=config, rules_source_hash=source, monotonic=lambda: 0,
                                  objective=lambda r: HandOutcomeObjective(HandObjectiveKind.EXPECTED_SCORE, 0, "fixture"))
    plan = await policy.choose(request_case, budget)
    assert plan.outcome_trace.reason == "runtime_rules_mismatch"
