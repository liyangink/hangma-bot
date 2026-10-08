"""确认分析反例：纯合成终端样本，零模型、零桌赛、零真实确认根。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import copy
import math

import pytest

import confirmation_draft as confirm


def fixture(n=100, candidate=(1.0, 1.0), baseline=(0.0, 0.0)):
    """构造相互独立的 H/M 合成来源与四换座输入；不代表真实来源证明。"""
    roots, ledger, samples = [], [], []
    for i in range(n):
        root = {"source_root_id": f"synthetic-{i}", "root_content_digest": confirm.digest(i),
                "independence_id": f"draw-{i}", "opponent_mix": "H" if i % 2 == 0 else "M"}
        roots.append(root)
        ledger.append({**root, "usage": "confirmation", "exposures": []})
        for seat in range(4):
            arms = {}
            for name, identity, interval in (("candidate", "C", candidate), ("baseline", "V2", baseline)):
                arms[name] = {"candidate_id": identity, "status": "complete", "usable": True,
                              "u_low": interval[0], "u_high": interval[1], "error": None}
            samples.append({**root, "candidate_id": "C", "focal_anchor_seat": seat,
                            "scenario": "normal", "root_usage": "confirmation",
                            "root_expected": {"seats": 4, "arms": ["baseline", "candidate"],
                                              "tables_per_arm": 2},
                            "arms": arms, "completeness": "complete", "invalid_reasons": []})
    plan = {"schema": "sitin-confirmation-analysis-draft/1", "analysis_identity": confirm.analysis_identity(),
            "source_ledger_digest": confirm.digest(ledger), "metric": "group_advance_v1",
            "direction": "higher_is_better", "null_threshold": 0, "minimum_effect": 0.1,
            "method": "one_sided_hoeffding_root_lower_v1", "stopping": "fixed_complete_no_optional_stopping",
            "mixture_weights": {"H": 0.5, "M": 0.5}, "seats": [0, 1, 2, 3], "tables_per_arm": 2,
            "candidate_id": "C", "baseline_id": "V2", "execution_identity": "test-runtime",
            "stage_format_identity": "synthetic-only", "multiplicity": {"campaign_id": "test-campaign",
            "allocations": [0.05], "slot": 0}, "alpha": 0.05, "roots": roots, "n_roots": n}
    return plan, ledger, samples


def analyze(plan, ledger, samples, frozen_digest=None, execution_identity="test-runtime"):
    return confirm.analyze(plan, samples, frozen_digest=frozen_digest or confirm.digest(plan),
                           source_ledger=ledger, execution_identity=execution_identity)


def test_formula_and_seats_are_not_independent_samples():
    plan, ledger, samples = fixture()
    result = analyze(plan, ledger, samples)
    assert result["n_independent_roots"] == 100  # 400 座位行仍然只算 100 根
    assert result["lower_confidence_bound"] == pytest.approx(1 - math.sqrt(2 * math.log(20) / 100))
    assert result["analysis_status"] == "PASS_ANALYSIS_ONLY"
    assert result["release_eligible"] is False


def test_conservative_interval_uses_lower_not_midpoint():
    plan, ledger, samples = fixture(candidate=(0.4, 1), baseline=(0, 0.5))
    result = analyze(plan, ledger, samples)
    assert result["mean_lower_delta"] == pytest.approx(-0.1)
    assert not result["statistical_pass"]


def test_strata_balanced_and_order_invariant():
    plan, ledger, samples = fixture()
    for row in samples:
        if row["opponent_mix"] == "M":
            row["arms"]["candidate"]["u_low"] = 0
            row["arms"]["candidate"]["u_high"] = 0
    result = analyze(plan, ledger, samples)
    assert result["mean_lower_delta"] == 0.5
    reverse = analyze(plan, ledger, list(reversed(samples)))
    assert result["root_rows"] == reverse["root_rows"]
    assert result["lower_confidence_bound"] == reverse["lower_confidence_bound"]


def test_small_sample_does_not_pass_even_with_best_observed_score():
    plan, ledger, samples = fixture(n=2)
    assert analyze(plan, ledger, samples)["analysis_status"] == "INCONCLUSIVE"


def test_minimum_effect_is_required_of_lower_bound():
    plan, ledger, samples = fixture()
    plan["minimum_effect"] = 0.8
    result = analyze(plan, ledger, samples)
    assert result["statistical_pass"]
    assert not result["minimum_effect_pass"]
    assert result["analysis_status"] == "INCONCLUSIVE"


@pytest.mark.parametrize("mutation", [
    lambda rows: rows.pop(),
    lambda rows: rows.__delitem__(slice(0, 4)),
    lambda rows: rows.append(copy.deepcopy(rows[0])),
    lambda rows: rows[0].update(focal_anchor_seat=1),
    lambda rows: rows[0].update(focal_anchor_seat=False),
    lambda rows: rows[0].update(source_root_id="unexpected"),
    lambda rows: rows[0].update(root_content_digest="0" * 64),
    lambda rows: rows[0].update(opponent_mix="M"),
    lambda rows: rows[0].update(root_usage="development_core"),
    lambda rows: rows[0].update(candidate_id="other"),
    lambda rows: rows[0].update(self_comparison=True),
    lambda rows: rows[0].update(completeness="invalid"),
    lambda rows: rows[0]["root_expected"].update(seats=1),
    lambda rows: rows[0]["root_expected"].update(seats=4.0),
    lambda rows: rows[0]["arms"].pop("baseline"),
    lambda rows: rows[0]["arms"]["baseline"].update(candidate_id="other"),
    lambda rows: rows[0]["arms"]["candidate"].update(status="error"),
    lambda rows: rows[0]["arms"]["candidate"].update(usable=False),
    lambda rows: rows[0]["arms"]["candidate"].update(u_low=float("nan")),
    lambda rows: rows[0]["arms"]["candidate"].update(u_high=float("inf")),
    lambda rows: rows[0]["arms"]["candidate"].update(u_low=True),
    lambda rows: rows[0]["arms"]["candidate"].update(u_high=-0.1),
    lambda rows: rows[0]["arms"]["candidate"].update(u_high=1.1),
    lambda rows: rows[0]["arms"]["candidate"].update(u=0),
    lambda rows: rows[0]["arms"]["candidate"].pop("u_low"),
])
def test_bad_samples_refused_instead_of_dropping_rows(mutation):
    plan, ledger, samples = fixture(n=2)
    mutation(samples)
    with pytest.raises(ValueError):
        analyze(plan, ledger, samples)


@pytest.mark.parametrize("field,value", [
    ("minimum_effect", -1), ("minimum_effect", True), ("n_roots", 3),
    ("null_threshold", -0.1), ("alpha", 0.01), ("tables_per_arm", True),
    ("method", "normal_approx"), ("stopping", "keep_going_until_pass"),
    ("mixture_weights", {"H": 0.9, "M": 0.1}), ("seats", [False, 1, 2, 3]),
])
def test_invalid_preregistration(field, value):
    plan, ledger, samples = fixture(n=2)
    plan[field] = value
    with pytest.raises(ValueError):
        analyze(plan, ledger, samples)


def test_analysis_config_and_runtime_identity_changes_are_refused():
    plan, ledger, samples = fixture(n=2)
    before = confirm.digest(plan)
    plan["minimum_effect"] = 0
    with pytest.raises(ValueError, match="预登记摘要漂移"):
        analyze(plan, ledger, samples, before)
    with pytest.raises(ValueError, match="运行身份漂移"):
        analyze(plan, ledger, samples, execution_identity="new-runtime")
    plan["analysis_identity"] = {}
    with pytest.raises(ValueError, match="分析实现漂移"):
        analyze(plan, ledger, samples)


@pytest.mark.parametrize("alias", [False, True])
@pytest.mark.parametrize("exposure", ["development_core", "development_refresh", "confirmation"])
def test_used_root_rejected_even_when_renamed(alias, exposure):
    plan, ledger, samples = fixture(n=2)
    item = copy.deepcopy(ledger[0])
    item.update(usage=exposure, exposures=["previous-use"])
    if alias:
        item["source_root_id"] = "old-name"
        ledger.append(item)
    else:
        ledger[0] = item
    plan["source_ledger_digest"] = confirm.digest(ledger)
    with pytest.raises(ValueError, match="别名重复" if alias else "已有开发或确认消费"):
        analyze(plan, ledger, samples)


@pytest.mark.parametrize("field", ["source_root_id", "root_content_digest", "independence_id"])
def test_roots_cannot_duplicate_or_share_randomness(field):
    plan, ledger, samples = fixture(n=2)
    plan["roots"][1][field] = plan["roots"][0][field]
    with pytest.raises(ValueError, match="重复根"):
        analyze(plan, ledger, samples)


def test_unbalanced_strata_refused():
    plan, ledger, samples = fixture(n=2)
    plan["roots"][1]["opponent_mix"] = "H"
    ledger[1]["opponent_mix"] = "H"
    plan["source_ledger_digest"] = confirm.digest(ledger)
    with pytest.raises(ValueError, match="数量必须均衡"):
        analyze(plan, ledger, samples)


@pytest.mark.parametrize("mix", ["M", None, "unknown"])
def test_stratum_must_match_independent_source_ledger(mix):
    plan, ledger, samples = fixture(n=2)
    ledger[0]["opponent_mix"] = mix
    plan["source_ledger_digest"] = confirm.digest(ledger)
    with pytest.raises(ValueError, match="情景"):
        analyze(plan, ledger, samples)


@pytest.mark.parametrize("duplicate", ["content", "draw", "both"])
def test_unused_alias_also_rejected_in_source_ledger(duplicate):
    plan, ledger, samples = fixture(n=2)
    alias = copy.deepcopy(ledger[0])
    alias["source_root_id"] = "unused-alias"
    if duplicate == "content":
        alias["independence_id"] = "different-draw"
    if duplicate == "draw":
        alias["root_content_digest"] = confirm.digest("different-content")
    ledger.append(alias)
    plan["source_ledger_digest"] = confirm.digest(ledger)
    with pytest.raises(ValueError, match="别名重复"):
        analyze(plan, ledger, samples)


def test_alpha_spending_is_more_conservative_and_cannot_exceed_total():
    plan, ledger, samples = fixture()
    plan["multiplicity"].update(allocations=[0.025, 0.025], slot=1)
    plan["alpha"] = 0.025
    result = analyze(plan, ledger, samples)
    assert result["hoeffding_penalty"] == pytest.approx(math.sqrt(2 * math.log(40) / 100))
    plan["multiplicity"]["allocations"] = [0.05, 0.025]
    with pytest.raises(ValueError, match="总误报预算"):
        analyze(plan, ledger, samples)


def test_source_ledger_drift_and_missing_usage_fail_closed():
    plan, ledger, samples = fixture(n=2)
    ledger[0]["exposures"].append("late-consumption")
    with pytest.raises(ValueError, match="来源台账漂移"):
        analyze(plan, ledger, samples)
    ledger[0].pop("exposures")
    plan["source_ledger_digest"] = confirm.digest(ledger)
    with pytest.raises(ValueError, match="台账消费记录缺失"):
        analyze(plan, ledger, samples)
