"""复式统计测试：配对、scenario 聚类与聚类 Bootstrap 置信区间。"""

from __future__ import annotations

import pytest

from hangma_bot.offline.evaluation_statistics import (
    METRIC_TABLE_FIRST_RATE,
    METRIC_TABLE_SCORE_DELTA,
    clustered_bootstrap_ci,
    metric_fn_for,
    pair_matches,
    summarize_results,
    table_first_indicator,
    table_score_delta,
)

from support import make_match_result


def test_table_score_delta_uses_correct_seat():
    result = make_match_result(
        policy_ids_by_seat=("opp-1", "stable", "opp-2", "opp-3"),
        scores_before=(0, 5, 0, 0),
        scores_after=(0, 25, 0, 0),
    )
    assert table_score_delta(result, "stable") == 20.0


def test_table_score_delta_none_without_scores():
    result = make_match_result(scores_after=None)
    assert table_score_delta(result, "stable") is None


def test_first_indicator_strict_and_inclusive():
    strict = make_match_result(scores_after=(10, 10, 0, 0))
    assert table_first_indicator(strict, "stable", tie_method="strict") == 0.0
    assert table_first_indicator(strict, "stable", tie_method="inclusive") == 1.0
    clear_win = make_match_result(scores_after=(10, 5, 0, 0))
    assert table_first_indicator(clear_win, "stable", tie_method="strict") == 1.0


def test_metric_fn_for_unknown_metric_raises():
    with pytest.raises(ValueError):
        metric_fn_for("win_rate")


def test_pair_matches_valid_pair_and_consistency_checks():
    baseline = make_match_result(
        result_id="r-b", pair_id="p-1", scenario_id="sc-1",
        policy_ids_by_seat=("stable", "opp-1", "opp-2", "opp-3"),
        scores_after=(5, 0, 0, 0),
    )
    challenger = make_match_result(
        result_id="r-c", pair_id="p-1", scenario_id="sc-1",
        policy_ids_by_seat=("candidate", "opp-1", "opp-2", "opp-3"),
        scores_after=(9, 0, 0, 0),
    )
    outcome = pair_matches(
        [baseline, challenger],
        baseline_policy_id="stable",
        challenger_policy_id="candidate",
    )
    assert len(outcome.pairs) == 1
    assert outcome.unpaired_reasons == ()


def test_pair_matches_rejects_scenario_mismatch():
    baseline = make_match_result(
        result_id="r-b", pair_id="p-1", scenario_id="sc-1",
        policy_ids_by_seat=("stable", "opp-1", "opp-2", "opp-3"),
    )
    challenger = make_match_result(
        result_id="r-c", pair_id="p-1", scenario_id="sc-2",
        policy_ids_by_seat=("candidate", "opp-1", "opp-2", "opp-3"),
    )
    outcome = pair_matches(
        [baseline, challenger],
        baseline_policy_id="stable",
        challenger_policy_id="candidate",
    )
    assert outcome.pairs == ()
    assert any("scenario_id 不一致" in reason for reason in outcome.unpaired_reasons)


def test_pair_matches_excludes_mock_and_incomplete_with_reasons():
    mock_row = make_match_result(
        result_id="r-mock", pair_id="p-1", source_kind="mock",
        policy_ids_by_seat=("candidate", "opp-1", "opp-2", "opp-3"),
    )
    partial_row = make_match_result(
        result_id="r-partial", pair_id="p-1", status="partial", completed_hands=2,
        policy_ids_by_seat=("candidate", "opp-1", "opp-2", "opp-3"),
    )
    baseline = make_match_result(
        result_id="r-b", pair_id="p-1",
        policy_ids_by_seat=("stable", "opp-1", "opp-2", "opp-3"),
    )
    outcome = pair_matches(
        [baseline, mock_row, partial_row],
        baseline_policy_id="stable",
        challenger_policy_id="candidate",
    )
    assert outcome.pairs == ()
    reasons = "；".join(outcome.unpaired_reasons)
    assert "mock" in reasons
    assert "partial" in reasons


def test_bootstrap_is_scenario_unit_not_pair_unit():
    """同一 scenario 的 100 个相同配对不能把区间缩到单点之外：抽样单位是 scenario。"""

    flat = []
    for index in range(100):
        baseline = make_match_result(
            result_id="r-b-{0}".format(index), pair_id="p-{0}".format(index),
            scenario_id="sc-only", scores_before=(0, 0, 0, 0), scores_after=(1, 0, 0, 0),
        )
        challenger = make_match_result(
            result_id="r-c-{0}".format(index), pair_id="p-{0}".format(index),
            scenario_id="sc-only",
            policy_ids_by_seat=("candidate", "opp-1", "opp-2", "opp-3"),
            scores_before=(0, 0, 0, 0), scores_after=(2, 0, 0, 0),
        )
        flat.extend([baseline, challenger])
    outcome = pair_matches(flat, baseline_policy_id="stable", challenger_policy_id="candidate")
    result = clustered_bootstrap_ci(
        outcome.pairs,
        "stable",
        "candidate",
        table_score_delta,
        metric_name=METRIC_TABLE_SCORE_DELTA,
        n_resamples=500,
        seed=7,
    )
    assert result.n_scenarios == 1
    assert result.n_pairs == 100
    assert result.point_estimate == 1.0
    assert result.ci_low == 1.0 and result.ci_high == 1.0


def test_bootstrap_deterministic_with_same_seed():
    def build_pair(index, delta):
        baseline = make_match_result(
            result_id="r-b-{0}".format(index), pair_id="p-{0}".format(index),
            scenario_id="sc-{0}".format(index % 4),
            scores_before=(0, 0, 0, 0), scores_after=(1, 0, 0, 0),
        )
        challenger = make_match_result(
            result_id="r-c-{0}".format(index), pair_id="p-{0}".format(index),
            scenario_id="sc-{0}".format(index % 4),
            policy_ids_by_seat=("candidate", "opp-1", "opp-2", "opp-3"),
            scores_before=(0, 0, 0, 0), scores_after=(1 + delta, 0, 0, 0),
        )
        return baseline, challenger

    flat = []
    for index in range(20):
        baseline, challenger = build_pair(index, index % 3 - 1)
        flat.extend([baseline, challenger])
    outcome = pair_matches(flat, baseline_policy_id="stable", challenger_policy_id="candidate")
    first = clustered_bootstrap_ci(
        outcome.pairs, "stable", "candidate", table_score_delta,
        metric_name=METRIC_TABLE_SCORE_DELTA, n_resamples=2000, seed=42,
    )
    second = clustered_bootstrap_ci(
        outcome.pairs, "stable", "candidate", table_score_delta,
        metric_name=METRIC_TABLE_SCORE_DELTA, n_resamples=2000, seed=42,
    )
    assert first == second
    assert first.n_scenarios == 4
    # deltas: i%3-1（i=0..19）求和为 -1；4 个 scenario 各 5 对，
    # scenario 均值再做平均等于总体均值 -1/20。
    assert first.point_estimate == pytest.approx(-1.0 / 20.0)
    assert first.ci_low <= first.ci_high


def test_bootstrap_requires_pairs():
    with pytest.raises(ValueError):
        clustered_bootstrap_ci(
            (), "stable", "candidate", table_score_delta, metric_name=METRIC_TABLE_SCORE_DELTA
        )


def test_summarize_isolates_mock_from_conclusions():
    mock_rows = [
        make_match_result(result_id="r-m-{0}".format(index), source_kind="mock", pair_id="p-{0}".format(index))
        for index in range(4)
    ]
    report = summarize_results(mock_rows, baseline_policy_id="stable", challenger_policy_id="candidate")
    conclusion = "；".join(report["sections"][-1]["paragraphs"])
    assert "数据不足" in conclusion or "未证明" in conclusion
    samples = report["sections"][0]["table"]["rows"]
    mock_count_row = [row for row in samples if "mock" in str(row[0])]
    assert mock_count_row and mock_count_row[0][1] == 4


def test_summarize_reports_unproven_when_ci_includes_zero():
    rows = []
    for index in range(8):
        baseline = make_match_result(
            result_id="r-b-{0}".format(index), pair_id="p-{0}".format(index),
            scenario_id="sc-{0}".format(index % 4),
            scores_after=(5, 0, 0, 0),
        )
        challenger = make_match_result(
            result_id="r-c-{0}".format(index), pair_id="p-{0}".format(index),
            scenario_id="sc-{0}".format(index % 4),
            policy_ids_by_seat=("candidate", "opp-1", "opp-2", "opp-3"),
            scores_after=(4 if index % 2 else 6, 0, 0, 0),
        )
        rows.extend([baseline, challenger])
    report = summarize_results(
        rows, baseline_policy_id="stable", challenger_policy_id="candidate",
        n_resamples=2000, resample_seed=3,
    )
    conclusion = "；".join(report["sections"][-1]["paragraphs"])
    assert "未证明改进" in conclusion
    assert "无差异" in conclusion


def test_summarize_positive_direction_with_gates_note():
    rows = []
    for index in range(8):
        baseline = make_match_result(
            result_id="r-b-{0}".format(index), pair_id="p-{0}".format(index),
            scenario_id="sc-{0}".format(index % 4),
            scores_after=(1, 0, 0, 0),
        )
        challenger = make_match_result(
            result_id="r-c-{0}".format(index), pair_id="p-{0}".format(index),
            scenario_id="sc-{0}".format(index % 4),
            policy_ids_by_seat=("candidate", "opp-1", "opp-2", "opp-3"),
            scores_after=(10, 0, 0, 0),
        )
        rows.extend([baseline, challenger])
    report = summarize_results(
        rows, baseline_policy_id="stable", challenger_policy_id="candidate",
        n_resamples=2000, resample_seed=3,
    )
    conclusion = "；".join(report["sections"][-1]["paragraphs"])
    assert "支持候选版本" in conclusion
    assert "人工审核" in conclusion


def test_completed_match_runtime_failures_are_visible_in_report():
    """complete 不代表策略正常执行；汇总必须显示运行故障而非只报零排除。"""
    from hangma_bot.offline.evaluation_results import RuntimeCounts
    result = make_match_result(runtime_counts=RuntimeCounts(timeouts=3,illegal_choices=1,fallbacks=5,auto_actions=0,audit_missing=0))
    report = summarize_results([result])
    section = next(s for s in report['sections'] if s['heading']=='运行可靠性（全部结果行）')
    values = dict(section['table']['rows'])
    assert values['timeouts'] == 3
    assert values['fallbacks'] == 5
    assert values['illegal_choices'] == 1
    assert '不能仅凭 complete' in ' '.join(section['paragraphs'])
