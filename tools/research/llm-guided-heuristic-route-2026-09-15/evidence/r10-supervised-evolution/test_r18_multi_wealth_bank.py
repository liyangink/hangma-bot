"""R18 多财神题库的身份、完整性与控制分离回归。"""

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

import hashlib
import json

import r18_multi_wealth_bank as bank


def test_generated_bank_is_unique_complete_and_bound_to_current_generator():
    manifest = json.loads((bank.OUT / "manifest.json").read_text(encoding="utf-8"))
    cases = bank.load_cases()

    assert manifest["cases"] == 32
    assert manifest["unique_base_scenarios"] == 32
    assert manifest["development_cases"] == 24
    assert manifest["hidden_cases"] == 8
    assert manifest["generator_sha256"] == hashlib.sha256(
        bank.Path(bank.__file__).read_bytes()
    ).hexdigest()
    assert len({case.case_id for case in cases}) == 32
    assert all(case.oracle_complete for case in cases)
    assert all(
        {item.action_key for item in case.action_values}
        == {item.action_key for item in case.request.rules.legal_candidates}
        for case in cases
    )


def test_hidden_split_covers_easy_and_hard_decision_types_before_candidates_run():
    payload = json.loads((bank.OUT / "hidden.json").read_text(encoding="utf-8"))
    kinds = {row["decision_type"] for row in payload["cases"]}
    wealth_counts = {row["wealth_count"] for row in payload["cases"]}

    assert kinds == {"take_hu", "keep_wealth", "piao"}
    assert wealth_counts == {1, 2, 3, 4}


def test_measurement_controls_separate_and_v2_has_real_hidden_failures():
    score = json.loads((bank.OUT / "score.json").read_text(encoding="utf-8"))
    summaries = score["summaries"]

    assert summaries["positive_control"]["hidden"]["candidate_optimal_hit_rate"] == 1.0
    assert summaries["positive_control"]["hidden"]["mean_candidate_regret"] == 0.0
    assert summaries["negative_control"]["hidden"]["candidate_optimal_hit_rate"] == 0.0
    assert summaries["negative_control"]["hidden"]["mean_candidate_regret"] > 0.0
    assert summaries["v2"]["hidden"]["candidate_optimal_hit_rate"] == 0.5
    assert summaries["v2"]["hidden"]["mean_candidate_regret"] > 0.0
