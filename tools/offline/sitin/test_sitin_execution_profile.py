"""研究额度贯通验收：真实插桩、监管准入、自然装配和条件续打，零模型调用。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/tools'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import copy
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sitin_execution_profile as profiles
import sitin_execution_audit as audit
import sitin_gates as gates
import sitin_natural_panel as natural
import sitin_real_behavior as behavior
import sitin_search as search
from test_sitin_execution_audit import SOURCES, install_scripted_world

SOURCE = SOURCES["scored"].replace("def score_actions(view):\n",
    "def score_actions(view):\n    for i in range(60000):\n        unused = i\n")
PANEL = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/real-behavior-panel-v1/panel.json')


@pytest.fixture(scope="module")
def research_admission():
    """同一合法工程源码实测超100k、低于200k；所有安全探针仍真实启动。"""
    return gates.admit_action_value(SOURCE, execution_profile=profiles.RESEARCH_NAME,
        facts_panel={"generator": "test-profile-control", "legal": True},
        timing_config={"repeats": 1})


@pytest.mark.parametrize("bad", [True, 200000, "research-unbounded", {},
    dict(profiles.resolve(profiles.RESEARCH_NAME), max_operations=True),
    dict(profiles.resolve(profiles.RESEARCH_NAME), research_only=False)])
def test_unknown_or_spoofed_profile_rejected(bad):
    with pytest.raises(ValueError): profiles.resolve(bad)


def test_identity_never_overwrites_conflicting_declaration():
    original = {"candidate_execution_profile": profiles.resolve()}
    with pytest.raises(ValueError): profiles.identity_params(original, profiles.RESEARCH_NAME)
    assert original == {"candidate_execution_profile": profiles.resolve()}
    with pytest.raises(ValueError):
        gates.admit_action_value(SOURCE, executor_config={"max_operations": 200000})


def test_actual_admission_and_timing_use_same_research_budget(research_admission):
    record = research_admission
    assert record["execution_safety_pass"] and record["controlled_research_eligible"]
    assert record["layers"]["coverage"]["status"] == "PASS"
    views = record["layers"]["execution_safety"]["load_report"]["results"]
    assert all(100000 < view["operations"] < 200000 for view in views.values())
    assert record["timing"]["status"] == "PASS"
    assert record["timing"]["max_operations"] == 200000
    assert record["release"]["status"] == "NOT_EVALUATED"
    assert gates.av_record_identity_matches(record, SOURCE, execution_profile=profiles.RESEARCH_NAME)[0]
    assert not gates.av_record_identity_matches(record, SOURCE)[0]
    forged = copy.deepcopy(record)
    del forged["execution_profile"]
    assert not gates.av_record_identity_matches(forged, SOURCE, execution_profile=profiles.RESEARCH_NAME)[0]


def test_same_source_still_fails_default_admission_and_timing(research_admission):
    record = gates.admit_action_value(SOURCE,
        facts_panel={"generator": "test-profile-control", "legal": True},
        timing_config={"repeats": 1})
    assert not record["execution_safety_pass"] and not record["controlled_research_eligible"]
    assert record["timing"]["status"] == "FAIL"
    assert record["timing"]["max_operations"] == 100000
    assert record["identity"]["candidate_id"] != research_admission["identity"]["candidate_id"]


def _current_projection_panel(tmp_path: Path) -> Path:
    """从冻结原始请求生成临时当前投影；额度测试不借旧规则摘要判成败。"""

    frozen = json.loads(PANEL.read_text())
    source_path = _project_file(_PROJECT_ROOT, PANEL.parent / frozen["windows"][0]["file"])
    source = json.loads(source_path.read_text())
    request = behavior.decision_request_from_json(source["request"])
    record = behavior.capture_request(request)
    window_name = record["candidate_view_sha256"]
    windows = tmp_path / "windows"
    windows.mkdir()
    window_path = windows / (window_name + ".json")
    window_path.write_text(json.dumps(record, ensure_ascii=False, sort_keys=True))
    manifest = {
        "schema": "sitin-real-behavior-panel/1",
        "purpose": "development_behavior",
        "selection_eligible": False,
        "windows": [{
            "candidate_view_sha256": window_name,
            "file": "windows/" + window_path.name,
            "record_sha256": behavior.digest(record),
            "selection": "execution_profile_unit_test",
        }],
    }
    panel = tmp_path / "panel.json"
    panel.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True))
    return panel


def test_behavior_comparison_rejects_different_actual_budgets(tmp_path):
    panel = _current_projection_panel(tmp_path)
    default = behavior.evaluate(SOURCE, panel)
    research = behavior.evaluate(SOURCE, panel, execution_profile=profiles.RESEARCH_NAME)
    assert not default["comparable"] and research["comparable"]
    with pytest.raises(ValueError): behavior.compare(default, research)
    assert behavior.compare(research, research)["verdict"] == "SAME_ON_PANEL"


def natural_args(tmp_path):
    return dict(candidate_source=SOURCE, opponent="H", roots=1, seats_per_root=4, min_roots=1,
        contract=json.loads((natural.REPO / natural.DEFAULT_CONTRACT).read_text()),
        out_dir=tmp_path / "panel", authorization={"authorized": True, "batch": 7,
            "candidate_execution_profile": profiles.RESEARCH_NAME, "budgets": {"tables_full": 16}})


def test_research_natural_requires_matching_admission_before_work(tmp_path):
    kwargs = natural_args(tmp_path)
    with pytest.raises(ValueError, match="准入记录"): natural.run_natural_panel(**kwargs)
    assert not kwargs["out_dir"].exists()
    with pytest.raises(ValueError, match="配置漂移"):
        natural.run_natural_panel(**kwargs, execution_profile=profiles.DEFAULT_NAME)
    assert not kwargs["out_dir"].exists()


def test_natural_actual_budget_and_independent_recovery_checks(monkeypatch, tmp_path, research_admission):
    install_scripted_world(monkeypatch)
    kwargs = natural_args(tmp_path)
    panel = natural.run_natural_panel(**kwargs, admission=research_admission)
    assert panel["research_only"] and panel["release_eligible"] is False
    assert panel["automatic_archive_profile_supported"] is False
    assert panel["identity"]["candidate_id"] == research_admission["identity"]["candidate_id"]
    assert panel["execution_review"]["recorded_counts"]["action_value_scored"] == 8
    assert panel["execution_review"]["zero_internal_failures_verified"]
    sys.path.insert(0, str(_project_file(_PROJECT_ROOT, HERE.parent / "evidence/r10-supervised-evolution")))
    from verify_full_natural_results import verify_full_panel
    table = panel["samples"][0]["raw_arms"]["candidate"]["tables"][0]
    expected = copy.deepcopy(panel["identity"])
    def verify(value):
        return verify_full_panel(value, kwargs["contract"], expected_identity=expected,
            expected_root_indices=[1], expected_rules_hash=table["result"]["versions"]["rules_hash"])
    stored = json.loads((kwargs["out_dir"] / "panel.json").read_text())
    assert verify(stored)["full_results_verified"] == 16
    # 只改宣称的实际额度，完整终局和原评分摘要都不变，独立核验仍须拒绝。
    for key in list(table["result"]["versions"]):
        if key.startswith("natural_seat_max_operations:"):
            table["result"]["versions"][key] = "100000"
    with pytest.raises(ValueError, match="评分额度"): verify(panel)


def test_conditional_cut_and_remaining_table_audits_have_actual_budget(research_admission, tmp_path):
    import sitin_opportunities as opportunities
    from hangma_bot.hangma.engine import HangmaRules
    from hangma_bot.hangma.interface import ValueAnalysisLimits
    from hangma_bot.kernel.config import RuleConfig

    runtime = opportunities.build_test_runtime_double(
        rules=HangmaRules(RuleConfig(opportunities.DEFAULT_RULESET_VERSION, 1, False)),
        value_limits=ValueAnalysisLimits())
    result = search.run_av_evaluation(tmp_path / "conditional", SOURCE,
        admission=research_admission, prefix_source="v2_behavior", test_runtime=runtime,
        attempts_cap=1, authorization={"authorized": True, "batch": 7,
            "candidate_execution_profile": profiles.RESEARCH_NAME,
            "budgets": {"prefix_generation": 1}})
    assert result["ok"], result.get("refused")
    assert result["research_only"] and not result["selection_eligible"]  # 显式测试替身
    assert result["identity"]["candidate_id"] == research_admission["identity"]["candidate_id"]
    for name, arm in result["double_arm"]["arms"].items():
        assert len(arm["tables"]) == 2
        assert arm["execution_review"] == audit.review_tables(arm["tables"])
        assert arm["execution_review"]["recorded_counts"]["decision_count"] == arm["decisions_total"]
        assert arm["tables"][0]["partial"] and not arm["tables"][1]["partial"]
        for table in arm["tables"]:
            profiles.verify_table(table, profile=profiles.RESEARCH_NAME,
                                  candidate_seat=0 if name == "candidate" else None)
    table = result["double_arm"]["arms"]["candidate"]["tables"][0]
    stored = json.loads(json.dumps(table))
    stored["policy_execution_binding"]["max_operations_by_seat"][0] = 100000
    with pytest.raises(ValueError): profiles.verify_table(stored, profile=profiles.RESEARCH_NAME, candidate_seat=0)
    # 重签本地摘要仍不能把默认实际额度伪装成研究配置。
    stored["policy_execution_binding"]["record_sha256"] = audit.digest({
        "table_id": stored["table_id"],
        "max_operations_by_seat": stored["policy_execution_binding"]["max_operations_by_seat"],
        "policy_execution": stored["policy_execution"]})
    with pytest.raises(ValueError, match="评分额度"):
        profiles.verify_table(stored, profile=profiles.RESEARCH_NAME, candidate_seat=0)


def test_automatic_loop_and_fixture_cannot_silently_ignore_research_profile(tmp_path):
    auth = {"candidate_execution_profile": profiles.RESEARCH_NAME}
    with pytest.raises(ValueError, match="自动档案循环尚未接线"):
        search.av_start_iteration(tmp_path / "run", authorization=auth)
    assert not (tmp_path / "run").exists()
    with pytest.raises(ValueError, match="v2_behavior"):
        search.run_av_evaluation(tmp_path / "eval", SOURCE, authorization=auth)
    assert not (tmp_path / "eval").exists()


def test_feedback_keeps_profile_evidence_and_rejects_cross_budget_binding(tmp_path):
    """只在复制的旧产物上构造配置反例；相同源码也不能混入不同额度的成绩。"""
    import shutil
    import sitin_feedback as feedback
    fixture = _project_file(_PROJECT_ROOT, HERE.parent / "evidence/v4-impl/r6-e-revalidation")
    shutil.copytree(fixture, tmp_path / "fixture")
    root = tmp_path / "fixture/eval"
    conditional = root / "i1-conditional/evaluation.json"
    evaluation = json.loads(conditional.read_text())
    candidate = evaluation["identity"]["candidate_id"]
    selected = profiles.resolve(profiles.RESEARCH_NAME)
    evaluation["candidate_execution_profile"] = selected
    conditional.write_text(json.dumps(evaluation))
    with pytest.raises(feedback.FeedbackInputError, match="执行配置"):
        feedback.collect_feedback_inputs(root, parent_cid=None, candidate_cid=candidate)
    for mix in ("H", "M"):
        path = root / ("i1-natural-" + mix) / "panel.json"
        panel = json.loads(path.read_text())
        panel["identity"]["candidate_execution_profile"] = selected
        path.write_text(json.dumps(panel))
    inputs = feedback.collect_feedback_inputs(root, parent_cid=None, candidate_cid=candidate)
    projection = feedback.build_feedback_projection(inputs)
    records = [row for row in projection["reconciliation"] if row["key"] == "execution.profile"]
    assert len(records) == 3 and all(row["value"] == selected for row in records)
    assert "研究成绩不代表发布通过" in "\n".join(projection["facts"])
