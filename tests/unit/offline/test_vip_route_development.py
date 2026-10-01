"""VIP完整桌开发计划用假驱动，并验证一个生产单局的立即失败；不调用模型。"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.offline.evaluate import MatchDecisionRecord, MatchExperimentOutcome, MatchRunOutcome
from hangma_bot.offline.evaluation_results import (
    EVALUATION_SCHEMA_VERSION,
    SIMULATION_SOURCE_NAMESPACE,
    GameKey,
    MatchResult,
    RuntimeCounts,
)
from hangma_bot.offline.vip_eoh_generate import (
    VIP_EOH_BATCH_SCHEMA,
    VipEohBatch,
    load_vip_parents,
    write_vip_seed_parent,
)
from hangma_bot.policy.action_value_policy import ActionValuePolicy
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2
from hangma_bot.policy.route_vip_heuristic import (
    VIP_ROUTE_HEURISTIC_SEED_SOURCE,
    VipRouteProjectionLimits,
)
from hangma_bot.policy.v2_hu_upgrade import V2HuUpgradePolicy


PERMUTATIONS = ((0, 1, 2, 3), (1, 2, 3, 0), (2, 3, 0, 1), (3, 0, 1, 2))


def write_json(path: Path, value: object) -> None:
    """写入独立临时测试材料；不读取运行配置或凭据。"""

    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def scoring_input_capture():
    """实际公开Interface的临时记录流；预算仅为测试，不是自然开发批次默认。"""
    from hangma_bot.offline.scoring_input_capture import ScoringInputCapture, ScoringInputCaptureLimits
    capture = ScoringInputCapture(io.BytesIO(), limits=ScoringInputCaptureLimits(16 * 1024 * 1024, 512 * 1024 * 1024, 100000))
    yield capture
    capture.finish()


@pytest.fixture
def generation_batch_file(tmp_path):
    path = tmp_path / "generation-batch.json"
    write_json(path, {
        "schema": VIP_EOH_BATCH_SCHEMA,
        "batch_id": "synthetic-development-input",
        "budgets": {"model_calls": 0, "input_tokens": 0, "output_tokens": 0,
                    "table_instances": 0, "wall_clock_seconds": 1000},
        "per_call": {"input_tokens": 1, "max_tokens": 1, "timeout_seconds": 1},
        "max_operations": 100_000,
        "projection_limits": asdict(VipRouteProjectionLimits()),
        "rule_config": asdict(RuleConfig("hangma-mvp-v10-public-counts", 2, True)),
        "route_limits": asdict(ValueAnalysisLimits(max_expansions=8192)),
        "input_bound": None,
        "sampling": {"temperature": None, "top_p": None, "seed": None},
    })
    return path


@pytest.fixture
def development_file(tmp_path, generation_batch_file):
    """两根两池共32张桌；行为摘要为明确人工结构fixture，所有开发驱动仍mock。"""

    package = tmp_path / "manual-candidate"
    parent_package = tmp_path / "manual-parent"
    write_vip_seed_parent(parent_package, generation_batch_file)
    write_vip_seed_parent(package, generation_batch_file)
    batch = VipEohBatch.read(generation_batch_file)
    source = VIP_ROUTE_HEURISTIC_SEED_SOURCE.replace("proposal = 3.0", "proposal = 4.0")
    (package / "candidate.py").write_text(source, encoding="utf-8")
    record = json.loads((package / "generation.json").read_bytes())
    record.update(artifact_role="candidate_proposal", source_sha256=sha(package / "candidate.py"),
                  identity=batch.identity(source), test_fixture_only=True)
    write_json(package / "generation.json", record)
    parent, candidate = load_vip_parents((parent_package, package), batch)
    probe_file = tmp_path / "behavior-probe-summary.json"
    write_json(probe_file, {
        "schema": "vip-eoh-development-probe/1", "status": "probe_complete_not_admitted",
        "development_only": True, "confirmation": False, "admitted": False,
        "complete_table_claim": False, "strength_claim": False, "release_claim": False,
        "identity_stable": True, "drift": [], "window_count": 3,
        "planned_package_windows": 6, "scored_package_windows": 6, "unfinished_package_windows": 0,
        "fixture_kind": "synthetic_structure_not_measured_behavior_for_mock_driver_only",
        "packages": [{"index": index, "role": role, "path": material["path"], "loaded": True,
            **{key: material[key] for key in ("identity", "source_sha256", "record_sha256")}}
            for index, role, material in ((0, "parent", parent), (1, "candidate", candidate))],
        "comparisons": [{"candidate_index": 1, "parent_index": 0, "planned_windows": 3,
            "paired_scored_windows": 3, "unfinished_windows": 0, "comparison_complete": True,
            "preferred_action_changed_windows": 1, "observed_behavior_difference": True,
            "score_changed_windows": 1, "nonpreferred_order_only_changed_windows": 0}],
    })
    path = tmp_path / "development-batch.json"
    write_json(path, {
        "schema": "vip-route-development-batch/2",
        "scoring_input_capture": {"max_view_json_bytes": 16 * 1024 * 1024,
            "max_total_json_bytes": 512 * 1024 * 1024, "max_unique_views": 100000},
        "batch_id": "synthetic-development-plan",
        "generation_batch_file": generation_batch_file.name,
        "generation_batch_sha256": sha(generation_batch_file),
        "candidate_package": package.name,
        "candidate_generation_sha256": sha(package / "generation.json"),
        "candidate_source_sha256": sha(package / "candidate.py"),
        "behavior_probe_summary_file": probe_file.name,
        "behavior_probe_summary_sha256": sha(probe_file),
        "seeds": [{"root_id": f"synthetic-root-{seed}", "seed": seed,
                   "permutations": [list(permutation) for permutation in PERMUTATIONS]}
                  for seed in (701, 702)],
        "pools": ["H", "M"],
        "rounds": 8,
        "initial_dealer_physical": 0,
        "initial_scores": [0, 0, 0, 0],
        "table_instance_limit": 32,
        "wall_clock_limit_seconds": 1000,
        "step_limit": 8000,
    })
    return path


def fake_result(experiment, *, declaration, source_kind="mock"):
    """生成结构完整的假结果；明确mock来源，永不冒充真实模拟效果。"""

    root = experiment.seeds[0]
    permutation = experiment.seat_permutations[0]
    logical_ids = (declaration.policy_id,) + tuple(item.policy_id for item in experiment.opponents)
    by_seat = tuple(logical_ids[permutation.index(seat)] for seat in range(4))
    scores = [0, 0, 0, 0]
    scores[permutation[0]] = 3 if declaration == experiment.challenger else 1
    scores[permutation[1]] = -scores[permutation[0]]
    match_id = f"{experiment.match_id_prefix}:{root.scenario_id}:{''.join(map(str, permutation))}:{declaration.policy_id}"
    return MatchResult(
        evaluation_schema_version=EVALUATION_SCHEMA_VERSION,
        result_id="r-" + match_id,
        source_kind=source_kind,
        scenario_id=root.scenario_id,
        pair_id=f"{root.scenario_id}:{''.join(map(str, permutation))}",
        game_key=GameKey(SIMULATION_SOURCE_NAMESPACE, root.scenario_id, match_id),
        config=experiment.tournament_config,
        policy_ids_by_seat=by_seat,
        seat_permutation=permutation,
        expected_hands=8,
        completed_hands=8,
        scores_before=(0, 0, 0, 0),
        scores_after=tuple(scores),
        official_ranks=None,
        status="complete",
        invalid_reasons=(),
        runtime_counts=RuntimeCounts(0, 0, 0, 0, 0),
        versions=(("rules_hash", "synthetic-fake-rules-hash"),
                  ("ruleset_version", experiment.tournament_config.rules.ruleset_version),
                  ("simulation_version", "synthetic-fake-simulator/1")),
        source_refs=({"producer": "unit-test-fake-match-runner"},),
    )


def fake_outcome(experiment, rows):
    """保留假结果对应的运行记录，不调用任何策略或引擎方法。"""

    records = tuple((row.game_key.game_id, MatchRunOutcome(
        status="complete", completed_hands=8, final_scores=row.scores_after,
        blocked_reason=None, error_reason=None, steps=1, decisions=(),
        runtime_counts=RuntimeCounts(0, 0, 0, 0, 0),
    )) for row in rows)
    return MatchExperimentOutcome(tuple(rows), (), records)


def test_runtime_uses_actual_rules_and_full_frozen_opponents(generation_batch_file):
    """仅装配公开运行时；R18与V2两家保留正式实现及实际规则配置。"""

    from hangma_bot.offline.vip_route_development import build_vip_development_runtime

    batch = VipEohBatch.read(generation_batch_file)
    runtime = build_vip_development_runtime(batch, VIP_ROUTE_HEURISTIC_SEED_SOURCE, clock=lambda: 800.0)
    assert runtime.config.rules == batch.rule_config
    assert runtime.rules.config == batch.rule_config
    assert runtime.config.rounds_per_game == 8
    assert set(runtime.declarations) == {"A", "C", "H1", "H2", "H3", "M1", "M2", "M3"}
    assert runtime.baseline_policy_id != runtime.challenger_policy_id
    baseline = runtime.policies_by_id[runtime.baseline_policy_id]
    assert isinstance(baseline, ActionValuePolicy)
    assert baseline.scorer_name == "r18_integrated_positive_v2"
    for role in ("H1", "H2", "H3", "M1"):
        policy = runtime.policies_by_id[runtime.declarations[role].policy_id]
        assert isinstance(policy, ActionValuePolicy)
        assert policy.scorer_name == "r18_integrated_positive_v2"
    assert isinstance(runtime.policies_by_id[runtime.declarations["M2"].policy_id], ComparableHeuristicPolicyV2)
    assert isinstance(runtime.policies_by_id[runtime.declarations["M3"].policy_id], V2HuUpgradePolicy)


def test_fake_driver_preserves_full_plan_physical_dealer_and_strict_limits(development_file, tmp_path):
    """每根两池四映射都执行两臂；逻辑庄位逆映射保证物理庄始终为0。"""

    from hangma_bot.offline.vip_route_development import run_vip_route_development

    calls = []

    async def runner(experiment, **kwargs):
        calls.append((experiment, kwargs))
        assert len(experiment.seeds) == len(experiment.seat_permutations) == 1
        permutation = experiment.seat_permutations[0]
        assert experiment.initial_dealer == permutation.index(0)
        assert permutation[experiment.initial_dealer] == 0
        assert experiment.initial_scores == (0, 0, 0, 0)
        assert experiment.tournament_config.rounds_per_game == 8
        assert experiment.tournament_config.rules == RuleConfig("hangma-mvp-v10-public-counts", 2, True)
        assert kwargs["strict_challenger"] is True
        assert kwargs["value_limits"] == ValueAnalysisLimits(max_expansions=8192)
        assert kwargs["challenger_route_limits"] == kwargs["value_limits"]
        rows = [fake_result(experiment, declaration=declaration)
                for declaration in (experiment.baseline, experiment.challenger)]
        return fake_outcome(experiment, rows)

    result = asyncio.run(run_vip_route_development(development_file, tmp_path / "complete-fake", match_runner=runner))
    assert len(calls) == 16
    for root_id in ("synthetic-root-701", "synthetic-root-702"):
        root_calls = [experiment for experiment, _ in calls if experiment.seeds[0].scenario_id == root_id]
        assert len(root_calls) == 8
        assert all(sum(experiment.seat_permutations[0] == permutation for experiment in root_calls) == 2
                   for permutation in PERMUTATIONS)
    assert result["planned_table_instances"] == result["charged_table_instances"] == 32
    assert result["development_only"] is True
    assert result["confirmation_claim"] is False
    assert result["published"] is False
    assert set(result["pools"]) == {"H", "M"}
    for pool in result["pools"].values():
        assert pool["planned_rows"] == pool["observed_rows"] == 16
        assert pool["estimate_natural_score_delta"] is None


def test_missing_arm_retains_planned_denominator(development_file, tmp_path):
    """首次映射缺一臂只减观察行数，不减少计划或其余根／池的执行。"""

    from hangma_bot.offline.vip_route_development import run_vip_route_development

    calls = []

    async def runner(experiment, **kwargs):
        calls.append(experiment)
        declarations = (experiment.baseline,) if len(calls) == 1 else (experiment.baseline, experiment.challenger)
        return fake_outcome(experiment, [fake_result(experiment, declaration=item) for item in declarations])

    result = asyncio.run(run_vip_route_development(development_file, tmp_path / "missing-fake", match_runner=runner))
    assert len(calls) == 16
    assert result["planned_table_instances"] == result["charged_table_instances"] == 32
    assert sum(pool["planned_rows"] for pool in result["pools"].values()) == 32
    assert sum(pool["observed_rows"] for pool in result["pools"].values()) == 31
    assert sorted(pool["observed_rows"] for pool in result["pools"].values()) == [15, 16]
    assert all(pool["estimate_natural_score_delta"] is None for pool in result["pools"].values())


@pytest.mark.parametrize("field,value", [
    ("schema", "vip-route-development-batch/unknown"),
    ("rounds", 1),
    ("initial_dealer_physical", 1),
    ("initial_scores", [1, 0, 0, 0]),
    ("pools", ["H"]),
    ("pools", ["H", "H"]),
    ("table_instance_limit", 0),
    ("wall_clock_limit_seconds", 0),
    ("step_limit", 0),
    ("generation_batch_sha256", "0" * 64),
    ("candidate_generation_sha256", "0" * 64),
    ("candidate_source_sha256", "0" * 64),
    ("behavior_probe_summary_sha256", "0" * 64),
])
def test_invalid_public_configuration_is_rejected(development_file, field, value):
    """固定格式、预算与三份独立摘要错误均须在开跑前拒绝。"""

    from hangma_bot.offline.vip_route_development import VipDevelopmentBatch

    data = json.loads(development_file.read_bytes())
    data[field] = value
    write_json(development_file, data)
    with pytest.raises(ValueError):
        VipDevelopmentBatch.read(development_file, allow_mock_behavior_fixture=True)


@pytest.mark.parametrize("permutations", [
    PERMUTATIONS[:3],
    (PERMUTATIONS[0],) * 4,
    ((0, 1, 2, 3), (0, 1, 3, 2), (0, 2, 1, 3), (0, 2, 3, 1)),
])
def test_each_frozen_root_requires_four_distinct_focal_seats(development_file, permutations):
    """根的四座映射不能缺席或重复，保证计划分母在运行前完整。"""

    from hangma_bot.offline.vip_route_development import VipDevelopmentBatch

    data = json.loads(development_file.read_bytes())
    data["seeds"][0]["permutations"] = [list(item) for item in permutations]
    write_json(development_file, data)
    with pytest.raises(ValueError):
        VipDevelopmentBatch.read(development_file, allow_mock_behavior_fixture=True)


def test_duplicate_root_identity_is_rejected(development_file):
    """根是统计聚类单位；重复身份不能重复占用计划或被当成新证据。"""

    from hangma_bot.offline.vip_route_development import VipDevelopmentBatch

    data = json.loads(development_file.read_bytes())
    data["seeds"][1]["root_id"] = data["seeds"][0]["root_id"]
    write_json(development_file, data)
    with pytest.raises(ValueError):
        VipDevelopmentBatch.read(development_file, allow_mock_behavior_fixture=True)


def test_consistent_package_with_wrong_analysis_limits_is_rejected(
    development_file, generation_batch_file, tmp_path,
):
    """即使包与其生成批摘要一致，2048分析档也不能冒充声明的8192开发档。"""

    from hangma_bot.offline.vip_route_development import VipDevelopmentBatch

    generation = json.loads(generation_batch_file.read_bytes())
    generation["route_limits"]["max_expansions"] = 2048
    write_json(generation_batch_file, generation)
    wrong_package = tmp_path / "manual-candidate-2048"
    write_vip_seed_parent(wrong_package, generation_batch_file)
    data = json.loads(development_file.read_bytes())
    data.update(
        generation_batch_sha256=sha(generation_batch_file),
        candidate_package=wrong_package.name,
        candidate_generation_sha256=sha(wrong_package / "generation.json"),
        candidate_source_sha256=sha(wrong_package / "candidate.py"),
    )
    write_json(development_file, data)
    with pytest.raises(ValueError):
        VipDevelopmentBatch.read(development_file, allow_mock_behavior_fixture=True)


def test_existing_output_is_preserved_before_driver_dispatch(development_file, tmp_path):
    """新批次不得覆盖已有证据，也不能先消耗假驱动桌数再发现目录存在。"""

    from hangma_bot.offline.vip_route_development import run_vip_route_development

    out_dir = tmp_path / "existing-output"
    out_dir.mkdir()
    sentinel = out_dir / "sentinel.txt"
    sentinel.write_text("既有证据", encoding="utf-8")

    async def forbidden_runner(*args, **kwargs):
        pytest.fail("已有目录时不得调用完整桌驱动")

    with pytest.raises(FileExistsError):
        asyncio.run(run_vip_route_development(development_file, out_dir, match_runner=forbidden_runner))
    assert sentinel.read_text(encoding="utf-8") == "既有证据"
    assert tuple(out_dir.iterdir()) == (sentinel,)


@pytest.mark.parametrize("target", ["development_batch", "generation_batch", "candidate_generation", "candidate_source", "behavior_summary", "behavior_parent_source", "behavior_parent_record"])
def test_frozen_public_file_drift_invalidates_entire_development(
    development_file, generation_batch_file, tmp_path, target,
):
    """首尾任何一份公开冻结材料漂移都保留费用、失效全部池，不删除诊断行。"""

    from hangma_bot.offline.vip_route_development import run_vip_route_development

    data = json.loads(development_file.read_bytes())
    package = development_file.parent / data["candidate_package"]
    target_path = {"development_batch": development_file, "generation_batch": generation_batch_file,
                   "candidate_generation": package / "generation.json",
                   "candidate_source": package / "candidate.py",
                   "behavior_summary": development_file.parent / data["behavior_probe_summary_file"],
                   "behavior_parent_source": development_file.parent / "manual-parent/candidate.py",
                   "behavior_parent_record": development_file.parent / "manual-parent/generation.json"}[target]
    calls = 0

    async def runner(experiment, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            target_path.write_bytes(target_path.read_bytes() + b"\n")
        rows = [fake_result(experiment, declaration=item)
                for item in (experiment.baseline, experiment.challenger)]
        return fake_outcome(experiment, rows)

    out_dir = tmp_path / ("drift-" + target)
    result = asyncio.run(run_vip_route_development(development_file, out_dir, match_runner=runner))
    assert calls == 16
    assert result["identity_stable"] is False
    assert result["planned_table_instances"] == result["charged_table_instances"] == 32
    assert sum(pool["observed_rows"] for pool in result["pools"].values()) == 32
    for pool in result["pools"].values():
        assert pool["estimate_natural_score_delta"] is None
        assert pool["development_complete"] is False
        assert pool["positive_tail"] == pool["negative_tail"] == []
        assert any("漂移" in reason for reason in pool["extra_failures"])
    assert json.loads((out_dir / "end-freeze.json").read_bytes())["identity_stable"] is False
    assert json.loads((out_dir / "summary.json").read_bytes()) == json.loads(json.dumps(result))


def test_driver_exception_keeps_precharged_cost_and_full_denominator(development_file, tmp_path):
    """驱动抛错前两臂费用已持久化；异常不退费，缺行不缩减预冻结分母。"""

    from hangma_bot.offline.vip_route_development import run_vip_route_development

    out_dir = tmp_path / "driver-exception"
    calls = 0

    async def runner(experiment, **kwargs):
        nonlocal calls
        calls += 1
        costs = json.loads((out_dir / "costs.json").read_bytes())
        assert costs["entries"][-1]["status"] == "reserved"
        assert costs["entries"][-1]["charged_table_instances"] == 2
        if calls == 1:
            raise RuntimeError("synthetic match driver failure")
        return fake_outcome(experiment, [fake_result(experiment, declaration=item)
                                       for item in (experiment.baseline, experiment.challenger)])

    result = asyncio.run(run_vip_route_development(development_file, out_dir, match_runner=runner))
    assert calls == 16
    assert result["planned_table_instances"] == result["charged_table_instances"] == 32
    assert sum(pool["planned_rows"] for pool in result["pools"].values()) == 32
    assert sum(pool["observed_rows"] for pool in result["pools"].values()) == 30
    costs = json.loads((out_dir / "costs.json").read_bytes())
    failed = [entry for entry in costs["entries"] if entry["status"] == "failed_cost_retained"]
    assert len(failed) == 1 and failed[0]["charged_table_instances"] == 2
    assert "synthetic match driver failure" in failed[0]["error"]
    assert any("桌组异常" in reason for pool in result["pools"].values() for reason in pool["extra_failures"])


@pytest.mark.parametrize("internally_degraded", [False, True])
def test_emergency_key_flag_does_not_hide_internal_scoring_degradation(
    development_file, tmp_path, internally_degraded,
):
    """正常独立评分可与紧急动作同键；内部降级原因即使计数全零仍须另账失效。"""

    from hangma_bot.offline.vip_route_development import run_vip_route_development

    async def runner(experiment, **kwargs):
        rows = [fake_result(experiment, declaration=item)
                for item in (experiment.baseline, experiment.challenger)]
        outcome = fake_outcome(experiment, rows)
        records = []
        for match_id, table in outcome.match_records:
            challenger = match_id == rows[1].game_key.game_id
            reasons = ("action_value_failed: 人工内部降级夹具",) if internally_degraded else ()
            decision = MatchDecisionRecord(
                decision_id=match_id + ":decision", seat=experiment.seat_permutations[0][0],
                policy_id=experiment.challenger.policy_id if challenger else experiment.baseline.policy_id,
                window_key={"game_id": match_id, "round_no": 1}, action_key="discard:1w",
                legal=True, is_emergency=True, fallback_reason=None, plan_revision=1,
                degraded_reasons=reasons, elapsed_ms=None,
            )
            records.append((match_id, replace(table, decisions=(decision,))))
        return replace(outcome, match_records=tuple(records))

    result = asyncio.run(run_vip_route_development(
        development_file, tmp_path / ("internal-degraded" if internally_degraded else "normal-emergency-key"),
        match_runner=runner,
    ))
    for pool in result["pools"].values():
        assert pool["estimate_natural_score_delta"] is None  # 假驱动始终无效果信用。
        degradation = [reason for reason in pool["extra_failures"] if "内部R18评分回退" in reason]
        assert bool(degradation) is internally_degraded
        assert not any("运行计数非全零" in reason for reason in pool["extra_failures"])


def test_real_single_hand_abstention_stops_and_preserves_action_before_failure(generation_batch_file, scoring_input_capture):
    """只启动一个自然单局，首窗ABSTAIN立即停止；不把机械失败补成流局。"""

    from hangma_bot.application.deadline import BudgetPolicy
    from hangma_bot.offline.evaluate import MatchDriverConfig, drive_match
    from hangma_bot.offline.vip_route_development import (
        VipDevelopmentAuditEngine, VipDevelopmentAuditPolicy, build_vip_development_runtime,
    )
    from hangma_bot.simulation import MatchSpec, SimulationChoice

    public = json.loads(generation_batch_file.read_bytes())
    public["rule_config"] = asdict(RuleConfig("hangma-mvp-v10-public-counts", 1, False))
    write_json(generation_batch_file, public)
    batch = VipEohBatch.read(generation_batch_file)
    runtime = build_vip_development_runtime(batch, '''
def score_actions(view):
    return {"status": "ABSTAIN", "entries": [], "reason": "人工故障"}
''')
    spec = MatchSpec("synthetic-single-hand-fault", "synthetic-single-hand-fault",
        replace(runtime.config, rounds_per_game=1), 703, 0, (0, 0, 0, 0))
    rows = []
    engine = VipDevelopmentAuditEngine(runtime.engine)
    engine.context = {"pool": "H", "focal_physical_seat": 0}
    policy = VipDevelopmentAuditPolicy(runtime.policies_by_id[runtime.challenger_policy_id],
        runtime.challenger_policy_id, lambda: dict(engine.context), rows.append, challenger=True, capture=scoring_input_capture)
    outcome = asyncio.run(drive_match(engine=engine, spec=spec, policies_by_seat=(policy,) * 4,
        rules=runtime.rules, choice_factory=lambda key, action: SimulationChoice(key, action),
        config=MatchDriverConfig(clock_mode="logical", step_limit=10, budget_policy=BudgetPolicy(),
            competition_tournament_id=spec.scenario_id, strict_policy=True, route_limits=batch.route_limits),
        now_monotonic=lambda: 800.0, wall_clock=None, value_limits=batch.route_limits))
    assert engine.started_table_instances == 1
    assert outcome.status == "error" and outcome.completed_hands == 0
    assert outcome.final_scores is None and engine.settlements == []
    assert len(rows) == 1 and len(outcome.decisions) == 1
    row = rows[0]
    assert row["status"] == "failed" and row["c_self_scored"] is False
    assert row["legal_action_keys"] and "ABSTAIN" in row["error"]
    assert row["scoring_execution"]["status"] == "ABSTAIN"
    assert row["scoring_cumulative_failed_calls"] == 1
    assert row["scoring_execution"]["actual_score_calls"] == 1
    assert row["scoring_execution"]["input_capture"]["saved_before_score"] is True
    assert row["scoring_execution"]["status"] == "ABSTAIN"
    assert row["candidate_operations"] is not None
    assert row["current_opportunity"]["future_qualification"] == "unknown"
    assert "selected_action_key" not in row


def test_actual_scored_emergency_key_keeps_full_keys_and_current_only_opportunity(generation_batch_file, scoring_input_capture):
    """同源真实数学视图独立评分；首选与紧急键相同也保持成功评分信用。"""

    from hangma_bot.hangma.engine import HangmaRules
    from hangma_bot.kernel.actions import Tile
    from hangma_bot.offline.vip_route_development import VipDevelopmentAuditPolicy
    from hangma_bot.policy.route_vip_heuristic import RouteVipHeuristicPolicy
    from tests.unit.policy.support import make_budget, make_observation, make_request

    public = json.loads(generation_batch_file.read_bytes())
    public["rule_config"] = asdict(RuleConfig("hangma-mvp-v10-public-counts", 1, False))
    write_json(generation_batch_file, public)
    batch = VipEohBatch.read(generation_batch_file)
    hand = tuple(Tile(code) for code in ("1w", "2w", "3w", "1t", "2t", "3t", "1b", "2b", "3b", "7w", "8w", "白", "白"))
    observation = make_observation(my_hand=hand, drawn_tile=Tile("东"), hand_counts=(14, 13, 13, 13),
        chain_piao=0, gang_draw=False)
    analysis = HangmaRules(batch.rule_config).analyze(observation,
        value_limits=batch.route_limits, route_limits=batch.route_limits)
    request = make_request(observation, analysis)
    emergency_key = analysis.emergency_candidate.action_key
    source = '''
def score_actions(view):
    entries = []
    for action in view["actions"]:
        key = action["action_key"]
        score = 1.0 if key == TARGET else 0.0
        entries.append({"action_key": key, "score": score, "trace": {"unit": "heuristic_rank_points"}})
    return {"status": "SCORED", "entries": entries, "reason": None}
'''.replace("TARGET", repr(emergency_key))
    inner = RouteVipHeuristicPolicy(batch.rule_config, source=source)
    rows = []
    policy = VipDevelopmentAuditPolicy(inner, "synthetic-c", lambda: {"match_id": "fixture", "pool": "H"},
        rows.append, challenger=True, capture=scoring_input_capture)
    plan = asyncio.run(policy.choose(request, make_budget()))
    assert plan.candidates[0].action_key == emergency_key
    assert plan.candidates[0].is_emergency is True and plan.degraded_reasons == ()
    assert len(rows) == 1 and rows[0]["status"] == "chosen" and rows[0]["c_self_scored"] is True
    assert set(rows[0]["scoring_execution"]["scored_action_keys"]) == set(rows[0]["legal_action_keys"])
    assert rows[0]["candidate_operations"] <= batch.max_operations
    opportunity = rows[0]["current_opportunity"]
    assert opportunity["future_qualification"] == "unknown"
    assert opportunity["legal_hu"] == any(key.split(":")[0] == "hu" for key in rows[0]["legal_action_keys"])
    assert "winner_seat" not in opportunity and "chain_success" not in opportunity


def test_public_settlement_export_once_and_missing_evidence_stays_unknown(generation_batch_file):
    """公开frame决定完成分母；世界不透明且不重复导出，缺番不猜他家先胡。"""

    from hangma_bot.offline.vip_route_development import (
        VipDevelopmentAuditEngine, summarize_vip_natural_settlements,
    )
    from hangma_bot.kernel.config import TimingConfig, TournamentConfig
    from hangma_bot.simulation import MatchSpec
    from hangma_bot.simulation.interface import SimulationFrame

    opaque_world = object()
    calls = []

    class PublicFakeEngine:
        """只提供公开出口的假适配器；用于编排，不是自然积分证据。"""

        def start(self, spec):
            return opaque_world

        def frame(self, world):
            assert world is opaque_world
            return SimulationFrame(10, (), 4, (0, 0, 0, 0), None)

        def export_hand_settlement(self, world, round_no):
            assert world is opaque_world
            calls.append(round_no)
            if round_no == 4:
                raise ValueError("公开证据不足")
            return {"coverage": "settlement_only", "round_no": round_no,
                "winner_seat": 2 if round_no != 2 else None, "is_draw": round_no == 2,
                "fan": 8 if round_no == 1 else None, "score_delta": [0, 0, 0, 0]}

    batch = VipEohBatch.read(generation_batch_file)
    spec = MatchSpec("table:synthetic-c", "synthetic-root", TournamentConfig(1, 4, batch.rule_config,
        TimingConfig(1, 1, 3)), 0, 0, (0, 0, 0, 0))
    engine = VipDevelopmentAuditEngine(PublicFakeEngine())
    engine.context = {"focal_physical_seat": 2}
    world = engine.start(spec)
    engine.frame(world)
    engine.frame(world)
    assert calls == [1, 2, 3, 4] and len(engine.settlements) == 4
    ledger = summarize_vip_natural_settlements(engine.settlements,
        challenger_policy_id="synthetic-c", planned_hands_by_arm={"A": 32, "C": 32})
    c = ledger["counts_by_arm"]["C"]
    assert c["observed_completed_hands"] == 4
    assert c["focal_hu"] == c["focal_ge4"] == c["focal_ge8"] == 1
    assert c["draw"] == 1 and c["unknown_settlement"] == 2
    assert c.get("opponent_first_hu", 0) == 0
    assert ledger["planned_hands_by_arm"] == {"A": 32, "C": 32}
    assert ledger["chain_success_label"] == "unknown_not_inferred"
    assert all("current_opportunity" not in row for row in ledger["rows"])


def test_duplicate_results_are_retained_and_invalidate_pool(development_file, tmp_path):
    """核验器拒绝多行时仍保存原始重复行和计划分母，不让异常丢掉整个汇总。"""

    from hangma_bot.offline.vip_route_development import run_vip_route_development

    calls = 0

    async def runner(experiment, **kwargs):
        nonlocal calls
        calls += 1
        rows = [fake_result(experiment, declaration=item) for item in (experiment.baseline, experiment.challenger)]
        if calls == 1:
            rows.append(rows[0])
        return fake_outcome(experiment, rows)

    out = tmp_path / "duplicate-results"
    result = asyncio.run(run_vip_route_development(development_file, out, match_runner=runner))
    assert result["pools"]["H"]["planned_rows"] == 16
    assert result["pools"]["H"]["observed_rows"] == 17
    assert result["pools"]["H"]["estimate_natural_score_delta"] is None
    assert any("核验失败" in reason for reason in result["pools"]["H"]["extra_failures"])
    assert len((out / "H/results.jsonl").read_text(encoding="utf-8").splitlines()) == 17


def test_wall_budget_before_first_group_keeps_all_planned_rows_without_dispatch(development_file, tmp_path):
    """已耗尽预算不启动新桌；计划桌／单局分母不随着零观察缩成零。"""

    from hangma_bot.offline.vip_route_development import run_vip_route_development

    data = json.loads(development_file.read_bytes())
    data["wall_clock_limit_seconds"] = 1e-9
    write_json(development_file, data)

    async def forbidden_runner(experiment, **kwargs):
        raise AssertionError("预算耗尽后不可调用驱动")

    out = tmp_path / "wall-budget"
    result = asyncio.run(run_vip_route_development(development_file, out, match_runner=forbidden_runner))
    assert result["planned_table_instances"] == 32 and result["charged_table_instances"] == 0
    assert all(pool["planned_rows"] == 16 and pool["observed_rows"] == 0
               and pool["estimate_natural_score_delta"] is None for pool in result["pools"].values())
    assert json.loads((out / "costs.json").read_bytes())["entries"] == []
    assert json.loads((out / "H/natural-settlement-ledger.json").read_bytes())["planned_hands_by_arm"] == {"A": 64, "C": 64}


@pytest.mark.parametrize("field,value", [
    ("schema", "wrong-profile/1"), ("status", "probe_unfinished_not_admitted"),
    ("identity_stable", False), ("drift", [{"reason": "漂移"}]),
    ("development_only", False), ("admitted", True), ("strength_claim", True),
    ("release_claim", True), ("confirmation", True), ("window_count", 0),
    ("scored_package_windows", 5), ("unfinished_package_windows", 1),
])
def test_invalid_behavior_summary_claims_are_rejected_before_runner(development_file, field, value):
    """即便摘要已重新冻结，失败、漂移、缺行或越界声明也不能进入完整桌。"""

    from hangma_bot.offline.vip_route_development import VipDevelopmentBatch

    data = json.loads(development_file.read_bytes())
    probe_file = development_file.parent / data["behavior_probe_summary_file"]
    probe = json.loads(probe_file.read_bytes())
    probe[field] = value
    write_json(probe_file, probe)
    data["behavior_probe_summary_sha256"] = sha(probe_file)
    write_json(development_file, data)
    with pytest.raises(ValueError):
        VipDevelopmentBatch.read(development_file, allow_mock_behavior_fixture=True)


@pytest.mark.parametrize("field,value", [
    ("candidate_index", 0), ("parent_index", 1),
    ("comparison_complete", False), ("observed_behavior_difference", False),
    ("preferred_action_changed_windows", 0), ("preferred_action_changed_windows", 4),
    ("preferred_action_changed_windows", True), ("paired_scored_windows", 2),
    ("planned_windows", 2), ("unfinished_windows", 1),
])
def test_noncomplete_or_nonpreferred_behavior_is_rejected(development_file, field, value):
    """首选变化与完整共同分母缺一不可；大量分数或尾序变化不补信用。"""

    from hangma_bot.offline.vip_route_development import VipDevelopmentBatch

    data = json.loads(development_file.read_bytes())
    probe_file = development_file.parent / data["behavior_probe_summary_file"]
    probe = json.loads(probe_file.read_bytes())
    comparison = probe["comparisons"][0]
    comparison[field] = value
    comparison.update(score_changed_windows=3, nonpreferred_order_only_changed_windows=3)
    write_json(probe_file, probe)
    data["behavior_probe_summary_sha256"] = sha(probe_file)
    write_json(development_file, data)
    with pytest.raises(ValueError):
        VipDevelopmentBatch.read(development_file, allow_mock_behavior_fixture=True)


@pytest.mark.parametrize("role,field,value", [
    ("candidate", "identity", {}), ("candidate", "source_sha256", "0" * 64),
    ("candidate", "record_sha256", "0" * 64), ("candidate", "loaded", False),
    ("parent", "identity", {}), ("parent", "record_sha256", "0" * 64),
    ("parent", "loaded", False), ("parent", "path", "missing-parent"),
])
def test_behavior_summary_must_bind_real_loaded_packages(development_file, role, field, value):
    """自报ID与loaded标记不足；当前候选完整身份和实际父包都要逐字节核验。"""

    from hangma_bot.offline.vip_route_development import VipDevelopmentBatch

    data = json.loads(development_file.read_bytes())
    probe_file = development_file.parent / data["behavior_probe_summary_file"]
    probe = json.loads(probe_file.read_bytes())
    package = next(p for p in probe["packages"] if p["role"] == role)
    package[field] = value
    write_json(probe_file, probe)
    data["behavior_probe_summary_sha256"] = sha(probe_file)
    write_json(development_file, data)
    with pytest.raises(ValueError):
        VipDevelopmentBatch.read(development_file, allow_mock_behavior_fixture=True)


def test_default_production_reader_rejects_explicit_structure_fixture(development_file):
    """CLI默认生产路径没有假行为豁免；结构fixture只能用于mock编排测试。"""

    from hangma_bot.offline.vip_route_development import VipDevelopmentBatch

    with pytest.raises(ValueError, match="fixture只准假驱动"):
        VipDevelopmentBatch.read(development_file)
    batch = VipDevelopmentBatch.read(development_file, allow_mock_behavior_fixture=True)
    assert any(path.endswith("manual-parent/candidate.py") for path in batch.frozen_files)


@pytest.fixture
def measured_behavior_file(tmp_path, generation_batch_file):
    """只在一个真实数学窗口运行公开probe；不完成桌赛、不调用模型或虚构行为差异。"""

    from hangma_bot.hangma.engine import HangmaRules
    from hangma_bot.kernel.actions import Tile
    from hangma_bot.kernel.serialization import observation_to_json, window_key_to_json
    from hangma_bot.offline.vip_eoh_probe import build_vip_eoh_panel, run_vip_eoh_probe
    from tests.unit.offline.test_vip_eoh_probe import (
        TIE_SOURCE, CHANGED_SOURCE, audit, package,
    )
    from tests.unit.policy.support import make_budget, make_observation, make_request
    from hangma_bot.policy.route_vip_heuristic import RouteVipHeuristicPolicy

    public = json.loads(generation_batch_file.read_bytes())
    public["rule_config"] = asdict(RuleConfig("hangma-mvp-v10-public-counts", 1, False))
    write_json(generation_batch_file, public)
    batch = VipEohBatch.read(generation_batch_file)
    hand = tuple(Tile(c) for c in ("1w", "2w", "3w", "1t", "2t", "3t", "1b", "2b", "3b", "7w", "8w", "白", "白"))
    observation = make_observation(my_hand=hand, drawn_tile=Tile("东"), hand_counts=(14, 13, 13, 13),
        chain_piao=0, gang_draw=False)
    analysis = HangmaRules(batch.rule_config).analyze(observation, route_limits=batch.route_limits)
    request = make_request(observation, analysis)
    plan = asyncio.run(RouteVipHeuristicPolicy(batch.rule_config).choose(request, make_budget()))
    record = {"schema": "vip-heuristic-smoke-decision/1", "observation": observation_to_json(observation),
        "window_key": window_key_to_json(request.window_key), "legal_action_keys": [c.action_key for c in analysis.legal_candidates],
        "status": "scored", "selected_action_key": plan.candidates[0].action_key}
    audit_dir = audit(tmp_path / "measured-audit", generation_batch_file, [record])
    panel_dir = tmp_path / "measured-panel"
    build_vip_eoh_panel(audit_dir, panel_dir, manifest_sha256=sha(audit_dir / "manifest.json"),
        decisions_sha256=sha(audit_dir / "decisions.jsonl.gz"), max_windows=1)
    parent_path = package(tmp_path / "measured-parent", generation_batch_file, TIE_SOURCE)
    candidate_path = package(tmp_path / "measured-candidate", generation_batch_file, CHANGED_SOURCE)
    probe_dir = tmp_path / "measured-probe"
    probe = run_vip_eoh_probe(panel_dir / "panel.json", generation_batch_file, probe_dir,
        parent_paths=[parent_path], candidate_paths=[candidate_path])
    assert probe["comparisons"][0]["preferred_action_changed_windows"] == 1
    path = tmp_path / "measured-development.json"
    write_json(path, {
        "schema": "vip-route-development-batch/1", "batch_id": "measured-window-not-table-test",
        "generation_batch_file": str(generation_batch_file), "generation_batch_sha256": sha(generation_batch_file),
        "candidate_package": str(candidate_path), "candidate_generation_sha256": sha(candidate_path / "generation.json"),
        "candidate_source_sha256": sha(candidate_path / "candidate.py"),
        "behavior_probe_summary_file": str(probe_dir / "summary.json"), "behavior_probe_summary_sha256": sha(probe_dir / "summary.json"),
        "seeds": [{"root_id": "measured-fixture-root", "seed": 0, "permutations": [list(p) for p in PERMUTATIONS]}],
        "pools": ["H", "M"], "rounds": 8, "initial_dealer_physical": 0, "initial_scores": [0] * 4,
        "table_instance_limit": 16, "wall_clock_limit_seconds": 1000, "step_limit": 1000,
    })
    return path


def test_real_probe_reader_binds_inputs_producer_and_parent_files(measured_behavior_file):
    """真实小probe通过公开入口，原始审计、面板、生产源码、父包均进入首尾冻结。"""

    from hangma_bot.offline.vip_route_development import VipDevelopmentBatch

    batch = VipDevelopmentBatch.read(measured_behavior_file)
    assert any(p.endswith("measured-audit/decisions.jsonl.gz") for p in batch.frozen_files)
    assert any(p.endswith("measured-audit/manifest.json") for p in batch.frozen_files)
    assert any(p.endswith("measured-panel/panel.json") for p in batch.frozen_files)
    assert any(p.endswith("measured-parent/candidate.py") for p in batch.frozen_files)
    assert any(p.endswith("offline/vip_eoh_probe.py") for p in batch.frozen_files)


@pytest.mark.parametrize("field,value,error", [
    ("batch_sha256", "0" * 64, "生成批次字节"),
    ("implementation_manifest", {}, "生产源码"),
    ("panel_sha256", "0" * 64, "面板字节摘要"),
    ("input_sha256s", ["0" * 64], "窗口ID序列"),
])
def test_real_shaped_probe_wrong_binding_is_rejected(measured_behavior_file, field, value, error):
    """真实probe输出改错绑定即便重冻summary SHA也拒绝，拒因不被fixture门遮蔽。"""

    from hangma_bot.offline.vip_route_development import VipDevelopmentBatch

    data = json.loads(measured_behavior_file.read_bytes())
    summary_file = Path(data["behavior_probe_summary_file"])
    summary = json.loads(summary_file.read_bytes())
    summary[field] = value
    write_json(summary_file, summary)
    data["behavior_probe_summary_sha256"] = sha(summary_file)
    write_json(measured_behavior_file, data)
    with pytest.raises(ValueError, match=error):
        VipDevelopmentBatch.read(measured_behavior_file)
