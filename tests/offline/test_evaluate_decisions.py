"""固定决策比较测试：recorded_request / recomputed_rules 的分离与保底计数。"""

from __future__ import annotations

import asyncio
import json

import pytest

from hangma_bot.kernel.actions import Discard, Tile
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.offline.evaluate import (
    DecisionExperiment,
    PolicyDeclaration,
    build_decision_report,
    compare_decision_row,
    read_decision_rows,
    run_decisions_comparison,
    translate_budget,
    write_decision_rows,
)
from hangma_bot.policy.interface import DecisionBudget

from support import (
    FakeRules,
    ScriptedPolicy,
    VECTOR_NEW_ORIGIN,
    candidates_for,
    decode_budget,
    decode_request,
    make_decision_source_row,
    make_observation,
    make_rules,
    pick_illegal,
    pick_key,
)

NOW = lambda: VECTOR_NEW_ORIGIN


def make_experiment(
    decision_mode: str = "recorded_request",
    rules_config: RuleConfig = None,
    exclusions: tuple = (),
) -> DecisionExperiment:
    return DecisionExperiment(
        kind="decisions",
        decision_mode=decision_mode,
        clock_mode="logical",
        baseline=PolicyDeclaration("baseline", "scripted"),
        challenger=PolicyDeclaration("challenger", "scripted"),
        input_sha256=None,
        source_namespace=None,
        rules_config=rules_config,
        tournament_config=None,
        exclusions=exclusions,
    )


def two_discard_rules():
    candidates = candidates_for([Discard(Tile("1w")), Discard(Tile("2w"))])
    return make_rules(candidates, emergency=candidates[0])


def run_row(row, experiment, baseline_policy, challenger_policy, recompute_rules=None):
    return asyncio.run(
        compare_decision_row(
            row,
            experiment=experiment,
            baseline_policy=baseline_policy,
            challenger_policy=challenger_policy,
            decode_request=decode_request,
            decode_budget=decode_budget,
            recompute_rules=recompute_rules,
            now_monotonic=NOW,
            wall_clock=None,
        )
    )


def test_translate_budget_matches_vector():
    budget = DecisionBudget(100.5, 100.7, 100.85)
    translated = translate_budget(budget, 100.0, 800.0)
    assert translated == DecisionBudget(800.5, 800.7, 800.85)


def test_recorded_request_captures_policy_difference():
    row = make_decision_source_row(make_observation(), two_discard_rules())
    result = run_row(
        row,
        make_experiment(),
        ScriptedPolicy(pick_key("discard:1w")),
        ScriptedPolicy(pick_key("discard:2w")),
    )
    assert result.mode == "recorded_request"
    assert result.baseline.action_key == "discard:1w"
    assert result.challenger.action_key == "discard:2w"
    assert result.baseline.legal is True
    assert result.challenger.legal is True
    assert result.baseline.fallback_reason is None
    assert result.budget["new_origin_monotonic"] == VECTOR_NEW_ORIGIN
    assert result.budget["fallback_deadline_monotonic"] == 800.7
    assert result.rules.recomputed is False
    assert result.rules.old_candidate_keys == ("discard:1w", "discard:2w")
    assert result.rules.new_candidate_keys == ("discard:1w", "discard:2w")
    assert result.end_reason == "submitted"
    assert result.decision_complete is True
    assert result.seat == 0


def test_same_request_rerun_is_stable():
    row = make_decision_source_row(make_observation(), two_discard_rules())
    experiment = make_experiment()
    first = run_row(
        row, experiment,
        ScriptedPolicy(pick_key("discard:1w")),
        ScriptedPolicy(pick_key("discard:2w")),
    )
    second = run_row(
        row, experiment,
        ScriptedPolicy(pick_key("discard:1w")),
        ScriptedPolicy(pick_key("discard:2w")),
    )
    assert first.to_json() == second.to_json()


def _write_dataset(dataset, rows):
    (dataset / "decisions.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def test_missing_request_row_excluded_and_others_compared(tmp_path):
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    rows = [
        make_decision_source_row(make_observation(), two_discard_rules(), hand_id="h-1", decision_id="d1"),
        make_decision_source_row(make_observation(), two_discard_rules(), hand_id="h-2", decision_id="d2"),
    ]
    del rows[1]["request"]
    _write_dataset(dataset, rows)
    outcome = asyncio.run(
        run_decisions_comparison(
            dataset,
            make_experiment(),
            baseline_policy=ScriptedPolicy(pick_key("discard:1w")),
            challenger_policy=ScriptedPolicy(pick_key("discard:2w")),
            decode_request=decode_request,
            decode_budget=decode_budget,
            now_monotonic=NOW,
            wall_clock=None,
        )
    )
    assert len(outcome.rows) == 1
    assert len(outcome.excluded) == 1
    assert "第 2 行" in outcome.excluded[0]
    assert "request" in outcome.excluded[0]
    assert len(outcome.input_sha256) == 64


def test_policy_error_falls_back_to_emergency():
    row = make_decision_source_row(make_observation(), two_discard_rules())
    result = run_row(
        row,
        make_experiment(),
        ScriptedPolicy(pick_key("discard:1w"), raise_error=RuntimeError("boom")),
        ScriptedPolicy(pick_key("discard:2w")),
    )
    assert result.baseline.fallback_reason == "error"
    assert result.baseline.action_key == "discard:1w"
    assert result.baseline.is_emergency is True
    assert result.baseline.legal is True
    assert "boom" in result.baseline.error


def test_empty_plan_uses_emergency_candidate():
    row = make_decision_source_row(make_observation(), two_discard_rules())
    result = run_row(
        row,
        make_experiment(),
        ScriptedPolicy(pick_key("discard:9w")),
        ScriptedPolicy(pick_key("discard:2w")),
    )
    assert result.baseline.fallback_reason == "empty_plan"
    assert result.baseline.action_key == "discard:1w"
    assert result.baseline.is_emergency is True
    assert result.baseline.rank is None


def test_no_emergency_and_empty_plan_is_not_pass():
    candidates = candidates_for([Discard(Tile("1w")), Discard(Tile("2w"))])
    rules = make_rules(candidates, emergency=None)
    row = make_decision_source_row(make_observation(), rules)
    result = run_row(
        row,
        make_experiment(),
        ScriptedPolicy(pick_key("discard:9w")),
        ScriptedPolicy(pick_key("discard:2w")),
    )
    assert result.baseline.action_key is None
    assert "不静默换成 Pass" in result.baseline.legality_reason


def test_illegal_choice_reported_not_corrected():
    row = make_decision_source_row(make_observation(), two_discard_rules())
    result = run_row(
        row,
        make_experiment(),
        ScriptedPolicy(pick_illegal("9w")),
        ScriptedPolicy(pick_key("discard:2w")),
    )
    assert result.baseline.action_key == "discard:9w"
    assert result.baseline.legal is False
    assert "不在本实验所用 RuleAnalysis" in result.baseline.legality_reason


def test_recomputed_rules_separated_from_policy_diff():
    new_candidates = candidates_for(
        [Discard(Tile("1w")), Discard(Tile("2w")), Discard(Tile("3w"))]
    )
    new_analysis = make_rules(new_candidates, emergency=new_candidates[0], ruleset_version="fixture-rules-v2")
    row = make_decision_source_row(make_observation(), two_discard_rules())
    experiment = make_experiment(
        decision_mode="recomputed_rules",
        rules_config=RuleConfig(ruleset_version="fixture-rules-v2", base_score=1, you_cai_bi_kao=False),
    )
    result = run_row(
        row,
        experiment,
        ScriptedPolicy(pick_key("discard:1w")),
        ScriptedPolicy(pick_key("discard:3w")),
        recompute_rules=FakeRules(new_analysis),
    )
    assert result.rules.recomputed is True
    assert result.rules.old_ruleset_version == "fixture-rules-v1"
    assert result.rules.new_ruleset_version == "fixture-rules-v2"
    assert result.rules.old_candidate_keys == ("discard:1w", "discard:2w")
    assert result.rules.new_candidate_keys == ("discard:1w", "discard:2w", "discard:3w")
    assert result.challenger.action_key == "discard:3w"


def test_experiment_exclusions_excluded_with_reason(tmp_path):
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    row = make_decision_source_row(make_observation(), two_discard_rules(), hand_id="hand-x")
    _write_dataset(dataset, [row])
    outcome = asyncio.run(
        run_decisions_comparison(
            dataset,
            make_experiment(exclusions=("hand-x",)),
            baseline_policy=ScriptedPolicy(pick_key("discard:1w")),
            challenger_policy=ScriptedPolicy(pick_key("discard:2w")),
            decode_request=decode_request,
            decode_budget=decode_budget,
            now_monotonic=NOW,
            wall_clock=None,
        )
    )
    assert outcome.rows == ()
    assert "排除清单" in outcome.excluded[0]


def test_reversed_budget_row_excluded(tmp_path):
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    row = make_decision_source_row(make_observation(), two_discard_rules())
    row["budget"] = {
        "enhancement_deadline_monotonic": 100.85,
        "fallback_deadline_monotonic": 100.7,
        "latest_send_at_monotonic": 100.5,
    }
    _write_dataset(dataset, [row])
    outcome = asyncio.run(
        run_decisions_comparison(
            dataset,
            make_experiment(),
            baseline_policy=ScriptedPolicy(pick_key("discard:1w")),
            challenger_policy=ScriptedPolicy(pick_key("discard:2w")),
            decode_request=decode_request,
            decode_budget=decode_budget,
            now_monotonic=NOW,
            wall_clock=None,
        )
    )
    assert outcome.rows == ()
    assert "ValueError" in outcome.excluded[0] or "必须" in outcome.excluded[0]


def test_decision_rows_file_round_trip(tmp_path):
    row = make_decision_source_row(make_observation(), two_discard_rules())
    result = run_row(
        row,
        make_experiment(),
        ScriptedPolicy(pick_key("discard:1w")),
        ScriptedPolicy(pick_key("discard:2w")),
    )
    path = tmp_path / "decisions.jsonl"
    write_decision_rows(path, [result])
    rows, problems = read_decision_rows(path)
    assert problems == []
    assert len(rows) == 1
    assert rows[0]["evaluation_schema_version"] == 1
    assert rows[0]["baseline"]["action_key"] == "discard:1w"


def test_decision_report_lists_change_matrix():
    row = make_decision_source_row(make_observation(), two_discard_rules())
    result = run_row(
        row,
        make_experiment(),
        ScriptedPolicy(pick_key("discard:1w")),
        ScriptedPolicy(pick_key("discard:2w")),
    )
    report = build_decision_report(
        type("Outcome", (), {"rows": (result,), "excluded": ()})(), make_experiment()
    )
    assert report["sections"][1]["table"]["rows"][0][1] == 1
    matrix = report["sections"][2]["table"]["rows"]
    assert ["discard:1w", "discard:2w", 1] in matrix


def test_policy_deadline_error_is_timeout_in_decision_comparison():
    from hangma_bot.policy.errors import PolicyTimeoutError
    row = make_decision_source_row(make_observation(),two_discard_rules())
    result = run_row(row,make_experiment(),
        ScriptedPolicy(pick_key('discard:2w'),raise_error=PolicyTimeoutError('deadline')),
        ScriptedPolicy(pick_key('discard:2w')))
    assert result.baseline.fallback_reason == 'timeout'
    assert result.baseline.action_key == 'discard:1w'
