"""R18 机会优先档案：逐目标 Pareto、隐藏准入和完整桌安全门。"""

from hangma_bot.offline.opportunity_archive import (
    OpportunityArchiveCandidate,
    OpportunityObjectiveScore,
    TableSafetyEvidence,
    build_opportunity_archive,
    lexicase_survivors,
)


OBJECTIVES = (
    "multi_wealth_baotou/four-piao",
    "multi_wealth_baotou/four-keep",
)


def _score(objective_id, gain, *, status="MEASURED", regret=0.0):
    return OpportunityObjectiveScore(
        objective_id=objective_id,
        family="multi_wealth_baotou",
        admission_status=status,
        mean_gain=gain,
        conservative_gain=gain,
        candidate_regret=regret,
        scored_base_scenarios=8,
        expected_base_scenarios=8,
        regression_count=0,
        paired_counterfactual_supported=status == "SPECIALIST_PASS",
        evidence="冻结隐藏摘要",
    )


def _table(status="PASS_NONINFERIOR", *, failures=0):
    return TableSafetyEvidence(
        status=status,
        source_units=16,
        complete_tables=64,
        paired_score_delta_mean=0.0,
        execution_failure_count=failures,
        evidence="冻结完整桌摘要",
    )


def _candidate(candidate_id, gains, *, statuses=None, table=None):
    statuses = statuses or ("MEASURED", "MEASURED")
    return OpportunityArchiveCandidate(
        candidate_id=candidate_id,
        source_sha256=(candidate_id[0].lower() if candidate_id[0].lower() in "abcdef" else "a") * 64,
        objectives=tuple(
            _score(objective_id, gain, status=status)
            for objective_id, gain, status in zip(OBJECTIVES, gains, statuses)
        ),
        table_safety=table or _table(),
    )


def test_pareto_preserves_complementary_specialists_without_scalar_average():
    baseline = _candidate(
        "V2", (0.0, 0.0), statuses=("BASELINE_ANCHOR", "BASELINE_ANCHOR"),
        table=_table("BASELINE_ANCHOR"),
    )
    piao = _candidate("P4", (180.0, 0.0), statuses=("SPECIALIST_PASS", "MEASURED"))
    keep = _candidate("K4", (0.0, 12.0), statuses=("MEASURED", "SPECIALIST_PASS"))

    result = build_opportunity_archive(
        (baseline, piao, keep),
        active_objective_ids=OBJECTIVES,
        baseline_candidate_id="V2",
    )

    assert result.pareto_elite_ids == ("K4", "P4")
    assert result.lexicase_parent_ids == ("K4", "P4")
    v2 = next(item for item in result.decisions if item.candidate_id == "V2")
    assert v2.dominated_by == ("K4", "P4")


def test_no_hidden_specialist_or_missing_objective_cannot_enter_archive():
    baseline = _candidate(
        "V2", (0.0, 0.0), statuses=("BASELINE_ANCHOR", "BASELINE_ANCHOR"),
        table=_table("BASELINE_ANCHOR"),
    )
    no_hidden = _candidate("K3", (0.0, 0.0))
    missing = OpportunityArchiveCandidate(
        candidate_id="MISSING",
        source_sha256="d" * 64,
        objectives=(_score(OBJECTIVES[0], 50.0, status="SPECIALIST_PASS"),),
        table_safety=_table(),
    )

    result = build_opportunity_archive(
        (baseline, no_hidden, missing),
        active_objective_ids=OBJECTIVES,
        baseline_candidate_id="V2",
    )
    decisions = {item.candidate_id: item for item in result.decisions}

    assert decisions["K3"].eligible is False
    assert "NO_HIDDEN_SPECIALIST_PASS" in decisions["K3"].exclusion_reasons
    assert decisions["MISSING"].eligible is False
    assert any(
        reason.startswith("MISSING_ACTIVE_OBJECTIVES:")
        for reason in decisions["MISSING"].exclusion_reasons
    )


def test_material_table_degradation_and_execution_failure_are_hard_exits():
    baseline = _candidate(
        "V2", (0.0, 0.0), statuses=("BASELINE_ANCHOR", "BASELINE_ANCHOR"),
        table=_table("BASELINE_ANCHOR"),
    )
    degraded = _candidate(
        "D1", (100.0, 0.0), statuses=("SPECIALIST_PASS", "MEASURED"),
        table=_table("FAIL_MATERIAL_DEGRADATION"),
    )
    failed = _candidate(
        "F1", (100.0, 0.0), statuses=("SPECIALIST_PASS", "MEASURED"),
        table=_table(failures=1),
    )

    result = build_opportunity_archive(
        (baseline, degraded, failed),
        active_objective_ids=OBJECTIVES,
        baseline_candidate_id="V2",
    )

    assert result.pareto_elite_ids == ("V2",)
    decisions = {item.candidate_id: item for item in result.decisions}
    assert "TABLE_SAFETY:FAIL_MATERIAL_DEGRADATION" in decisions["D1"].exclusion_reasons
    assert "TABLE_EXECUTION_FAILURES" in decisions["F1"].exclusion_reasons


def test_lexicase_order_selects_the_corresponding_specialist():
    piao = _candidate("P4", (180.0, 0.0), statuses=("SPECIALIST_PASS", "MEASURED"))
    keep = _candidate("K4", (0.0, 12.0), statuses=("MEASURED", "SPECIALIST_PASS"))

    assert lexicase_survivors((piao, keep), OBJECTIVES) == ("P4",)
    assert lexicase_survivors((piao, keep), tuple(reversed(OBJECTIVES))) == ("K4",)


def test_specialist_pass_requires_paired_counterfactual_support():
    baseline = _candidate(
        "V2", (0.0, 0.0), statuses=("BASELINE_ANCHOR", "BASELINE_ANCHOR"),
        table=_table("BASELINE_ANCHOR"),
    )
    unsupported_score = OpportunityObjectiveScore(
        objective_id=OBJECTIVES[0],
        family="multi_wealth_baotou",
        admission_status="SPECIALIST_PASS",
        mean_gain=100.0,
        conservative_gain=100.0,
        candidate_regret=0.0,
        scored_base_scenarios=8,
        expected_base_scenarios=8,
        regression_count=0,
        paired_counterfactual_supported=False,
        evidence="只有条件代理，没有配对反事实",
    )
    candidate = OpportunityArchiveCandidate(
        candidate_id="NO-CF",
        source_sha256="e" * 64,
        objectives=(unsupported_score, _score(OBJECTIVES[1], 0.0)),
        table_safety=_table(),
    )

    result = build_opportunity_archive(
        (baseline, candidate),
        active_objective_ids=OBJECTIVES,
        baseline_candidate_id="V2",
    )
    decision = next(item for item in result.decisions if item.candidate_id == "NO-CF")

    assert decision.eligible is False
    assert any(
        reason.startswith("SPECIALIST_WITHOUT_COUNTERFACTUAL_SUPPORT:")
        for reason in decision.exclusion_reasons
    )
