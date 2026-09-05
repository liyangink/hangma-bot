"""结果文件层测试：MatchResult 校验、results.jsonl 读写、manifest 与渲染。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hangma_bot.offline.evaluation_results import (
    EVALUATION_SCHEMA_VERSION,
    CONTRACT_ID,
    EvaluationManifest,
    GameKey,
    ManifestInput,
    check_complete_consistency,
    compute_rules_hash,
    count_by_source_kind,
    count_by_status,
    excluded_summary,
    filter_complete,
    group_by_scenario,
    match_result_from_json,
    new_evaluation_manifest,
    read_results_jsonl,
    render_report_md,
    write_manifest,
    write_results_jsonl,
)

from support import make_match_result, make_tournament_config


def test_match_result_rejects_bad_seat_permutation():
    with pytest.raises(ValueError):
        make_match_result(seat_permutation=(0, 1, 2, 2))


def test_match_result_rejects_bad_status_and_source_kind():
    with pytest.raises(ValueError):
        make_match_result(status="finished")
    with pytest.raises(ValueError):
        make_match_result(source_kind="random_guess")


def test_match_result_allows_negative_scores():
    result = make_match_result(scores_before=(-5, 0, 0, 0), scores_after=(-20, 0, 0, 0))
    assert result.scores_before == (-5, 0, 0, 0)


def test_match_result_rejects_out_of_range_official_ranks():
    with pytest.raises(ValueError):
        make_match_result(official_ranks=(1, 2, 3, 5))


def test_match_result_json_round_trip():
    result = make_match_result()
    restored = match_result_from_json(result.to_json())
    assert restored == result


def test_results_jsonl_write_read_round_trip(tmp_path):
    path = tmp_path / "results.jsonl"
    results = [
        make_match_result(result_id="r-a"),
        make_match_result(result_id="r-b", status="partial", scores_after=None),
    ]
    write_results_jsonl(path, results)
    restored = read_results_jsonl(path)
    assert restored == results


def test_results_jsonl_unknown_version_rejected(tmp_path):
    path = tmp_path / "results.jsonl"
    path.write_text(
        json.dumps({"evaluation_schema_version": 99, "result_id": "r-x"}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        read_results_jsonl(path)


def test_results_jsonl_malformed_json_rejected(tmp_path):
    path = tmp_path / "results.jsonl"
    path.write_text("not-json\n", encoding="utf-8")
    with pytest.raises(ValueError):
        read_results_jsonl(path)


def test_complete_consistency_checks():
    good = make_match_result()
    assert check_complete_consistency(good) == []
    assert check_complete_consistency(make_match_result(completed_hands=3)) != []
    assert check_complete_consistency(make_match_result(scores_after=None)) != []
    assert check_complete_consistency(make_match_result(expected_hands=None)) != []
    assert check_complete_consistency(make_match_result(invalid_reasons=("x",))) != []


def test_group_by_scenario_uses_sentinel_for_missing():
    results = [
        make_match_result(result_id="r-a", scenario_id="sc-1"),
        make_match_result(result_id="r-b", scenario_id="sc-1"),
        make_match_result(result_id="r-c", scenario_id=None),
    ]
    grouped = group_by_scenario(results)
    assert len(grouped["sc-1"]) == 2
    assert len(grouped[""]) == 1


def test_status_and_source_counts_and_exclusions():
    results = [
        make_match_result(result_id="r-ok"),
        make_match_result(result_id="r-mock", source_kind="mock"),
        make_match_result(result_id="r-void", status="void"),
        make_match_result(result_id="r-partial", status="partial", completed_hands=2),
    ]
    assert count_by_status(results)["complete"] == 2
    assert count_by_source_kind(results)["mock"] == 1
    assert len(filter_complete(results)) == 2
    summary = excluded_summary(results)
    assert summary["void"] == 1
    assert summary["partial"] == 1


def test_manifest_creation_and_json_fields():
    manifest = new_evaluation_manifest(
        source_namespace="hangma-simulation",
        producer_commit="abc123",
        dirty=False,
        inputs=(ManifestInput(path="decisions.jsonl", sha256="a" * 64),),
        rules_hash="b" * 64,
        config=make_tournament_config(),
        missing_fields=("guide_version", "guide_captured_at"),
        versions=(("clock_mode", "logical"),),
    )
    payload = manifest.to_json()
    assert payload["manifest_schema_version"] == 1
    assert payload["contract_id"] == CONTRACT_ID
    assert payload["evaluation_schema_version"] == EVALUATION_SCHEMA_VERSION
    assert len(payload["dataset_id"]) == 36
    assert payload["versions"]["clock_mode"] == "logical"


def test_manifest_rejects_bad_sha():
    with pytest.raises(ValueError):
        ManifestInput(path="x", sha256="short")


def test_manifest_rejects_wrong_contract_id():
    manifest = new_evaluation_manifest(source_namespace=None, producer_commit=None, dirty=None)
    payload = manifest.to_json()
    payload["contract_id"] = "parallel-v999"
    with pytest.raises(ValueError):
        EvaluationManifest(
            manifest_schema_version=payload["manifest_schema_version"],
            contract_id=payload["contract_id"],
            evaluation_schema_version=payload["evaluation_schema_version"],
            dataset_id=payload["dataset_id"],
            created_at_unix_ms=payload["created_at_unix_ms"],
            source_namespace=payload["source_namespace"],
            producer_commit=payload["producer_commit"],
            dirty=payload["dirty"],
            inputs=(),
            rules_hash=None,
            guide_version=None,
            guide_captured_at=None,
            config=None,
            missing_fields=(),
            versions=(),
        )


def test_write_manifest_round_trip_readable(tmp_path):
    manifest = new_evaluation_manifest(
        source_namespace="hangma-simulation", producer_commit="abc", dirty=True
    )
    path = tmp_path / "manifest.json"
    write_manifest(path, manifest)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["dataset_id"] == manifest.dataset_id
    assert payload["dirty"] is True


def test_compute_rules_hash_stable_and_64_hex():
    first = compute_rules_hash(Path(__file__).resolve().parents[2])
    second = compute_rules_hash(Path(__file__).resolve().parents[2])
    assert first == second
    assert len(first) == 64
    int(first, 16)


def test_render_report_md_renders_tables():
    report = {
        "title": "T",
        "intro": ["第一段"],
        "sections": [
            {
                "heading": "表",
                "table": {"columns": ["a", "b"], "rows": [[1, 2], [None, "x"]]},
            }
        ],
    }
    markdown = render_report_md(report)
    assert "# T" in markdown
    assert "| a | b |" in markdown
    assert "| 1 | 2 |" in markdown
    assert "|  | x |" in markdown


def test_game_key_validation():
    with pytest.raises(ValueError):
        GameKey("", "t", "g")
