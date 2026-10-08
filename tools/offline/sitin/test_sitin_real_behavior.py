"""真实开发面板回归：输入往返、已知盲区、平分排序及未知/篡改拒绝。"""
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

import asyncio
import json
import shutil
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sitin_real_behavior as behavior
import sitin_natural_panel as natural

ROOT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
PANEL = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/real-behavior-panel-v1/panel.json')
PILOT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r9-takeover-2026-09-19/pilot/run/iterations')


def test_real_panel_catches_previously_missed_choices_and_preserves_controls():
    """历史真实反例应检出七个差异；另十二个现场对照不应被源码/trace变化误判。"""
    parent = behavior.evaluate((_project_file(_PROJECT_ROOT, PILOT / "iter-02/generation/candidate.py")).read_text(), PANEL)
    child = behavior.evaluate((_project_file(_PROJECT_ROOT, PILOT / "iter-03/generation/candidate.py")).read_text(), PANEL)
    result = behavior.compare(parent, child)
    selected = json.loads(PANEL.read_text())["windows"]
    expected = {r["candidate_view_sha256"] for r in selected if r["selection"] == "known_disagreement"}
    assert result["verdict"] == "DIFFERENT"
    assert set(result["changed_windows"]) == expected
    assert len(expected) == 7 and len(selected) == 19
    assert behavior.compare(child, parent)["changed_windows"] == result["changed_windows"]
    assert behavior.compare(parent, parent)["verdict"] == "SAME_ON_PANEL"


@pytest.mark.parametrize("source", [
    'def score_actions(view):\n    return {"status": "ABSTAIN", "reason": "没有可用证据"}\n',
    'def score_actions(view):\n    return {"status": "SCORED", "entries": ()}\n',
])
def test_missing_or_invalid_output_never_counts_as_equivalence(source):
    result = behavior.evaluate(source, PANEL)
    assert not result["comparable"] and result["behavior_digest"] is None
    assert behavior.compare(result, result)["verdict"] == "INDETERMINATE"


def test_ties_use_production_action_key_order():
    source = ('def score_actions(view):\n'
              '    return {"status": "SCORED", "entries": '
              '[{"action_key": a["action_key"], "score": 0.0, "trace": {}} for a in reversed(view["actions"])]}\n')
    result = behavior.evaluate(source, PANEL)
    assert result["comparable"]
    for row in result["windows"]:
        assert row["action_key"] == min(row["scores"])


def test_production_plan_excludes_rejected_first_and_tracks_revision():
    """真实请求加显式拒绝历史的回归夹具；不能把已拒绝最高分报为生产首选。"""
    from hangma_bot.policy.interface import RejectedAttempt

    _, requests = behavior.load_panel(PANEL)
    name, request = next((key, request) for key, request in requests
                         if len(request.rules.legal_candidates) >= 3)
    source = ('def score_actions(view):\n'
              '    return {"status": "SCORED", "entries": '
              '[{"action_key": a["action_key"], "score": 0.0, "trace": {}} for a in view["actions"]]}\n')
    scorer = behavior.ActionValueScorer("test", source)
    before = behavior.evaluate_request(scorer, name, request)
    rejected = RejectedAttempt(before["action_key"], "fixture_rejected", 1, request.observation.snapshot_seq)
    after = behavior.evaluate_request(scorer, name, replace(request, rejected_attempts=(rejected,)))
    assert after["raw_action_key"] == before["action_key"]
    assert after["action_key"] == before["ordered_actions"][1]
    assert before["action_key"] not in after["ordered_actions"]
    assert after["revision"] == 2


def test_same_first_choice_different_retry_order_changes_plan_signature():
    _, requests = behavior.load_panel(PANEL)
    name, request = next((key, request) for key, request in requests
                         if len(request.rules.legal_candidates) >= 3)
    template = ('def score_actions(view):\n'
                '    entries = []\n'
                '    for i, a in enumerate(view["actions"]):\n'
                '        score = 1000.0 if i == 0 else SIGN * i\n'
                '        entries.append({"action_key": a["action_key"], "score": score, "trace": {}})\n'
                '    return {"status": "SCORED", "entries": entries}\n')
    rows = [behavior.evaluate_request(behavior.ActionValueScorer("test", template.replace("SIGN", sign)), name, request)
            for sign in ("1", "-1")]
    assert rows[0]["action_key"] == rows[1]["action_key"]
    assert behavior.decision_signature(rows[0]) != behavior.decision_signature(rows[1])


def test_syntax_failure_is_writable_indeterminate_result():
    result = behavior.evaluate("def score_actions(:", PANEL)
    assert not result["comparable"]
    assert all(row["status"] == "FAILED" for row in result["windows"])
    assert behavior.compare(result, result)["verdict"] == "INDETERMINATE"


@pytest.mark.parametrize("change", ["tamper", "duplicate", "traversal", "projection", "purpose"])
def test_panel_rejects_corruption_and_scope_changes(tmp_path, change):
    shutil.copytree(PANEL.parent, tmp_path / "panel")
    path = tmp_path / "panel/panel.json"
    manifest = json.loads(path.read_text())
    row = manifest["windows"][0]
    window_path = path.parent / row["file"]
    data = json.loads(window_path.read_text())
    if change == "tamper":
        data["request_sha256"] = "corrupt"
    elif change == "duplicate":
        manifest["windows"].append(row)
    elif change == "traversal":
        row["file"] = "../outside.json"
    elif change == "projection":
        data["candidate_view_sha256"] = "different"
        row["record_sha256"] = behavior.digest(data)
    else:
        manifest["purpose"] = "confirmation"
    path.write_text(json.dumps(manifest))
    window_path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        behavior.load_panel(path)


def test_different_panel_digest_cannot_be_compared():
    with pytest.raises(ValueError, match="不同面板"):
        behavior.compare({"panel_digest": "a"}, {"panel_digest": "b"})


@pytest.mark.parametrize("change", ["execution", "window_order"])
def test_stale_execution_and_reordered_results_are_rejected(change):
    left = {"panel_digest": "panel", "execution_identity": {"version": 1},
            "comparable": True, "windows": [{"window_id": "a", "action_key": "pass"},
                                              {"window_id": "b", "action_key": "pass"}]}
    right = json.loads(json.dumps(left))
    if change == "execution":
        right["execution_identity"]["version"] = 2
    else:
        right["windows"].reverse()
    with pytest.raises(ValueError):
        behavior.compare(left, right)


def test_observer_returns_exact_policy_plan_and_preserves_failure():
    request, budget, plan = object(), object(), object()
    calls = []

    class Policy:
        policy_id = "probe"

        async def choose(self, received, received_budget):
            assert received is request and received_budget is budget
            return plan

    wrapped = natural.ObservedDecisionPolicy(Policy(), calls.append)
    assert asyncio.run(wrapped.choose(request, budget)) is plan
    assert calls == [request]
    assert wrapped.error is None

    def fail(_):
        raise ValueError("capture failed")

    failed = natural.ObservedDecisionPolicy(Policy(), fail)
    with pytest.raises(ValueError, match="capture failed"):
        asyncio.run(failed.choose(request, budget))
    assert isinstance(failed.error, ValueError)


def test_stage_rejects_observer_failure_even_if_driver_falls_back(monkeypatch):
    """驱动即使吞掉策略异常并报告桌赛完成，采集阶段也必须保持失败。"""
    contract = json.loads((_project_file(_PROJECT_ROOT, ROOT / "contracts/group-dev-v1.json")).read_text())
    plans = natural.build_seat_stage_plans(contract=contract, opponent="H", root_index=1,
                                         focal_seat=0, panel_seed=2026091901)

    def fail(_):
        raise ValueError("capture failed")

    def fake_table(**kwargs):
        observed = next(p for p in kwargs["policies_by_seat"] if isinstance(p, natural.ObservedDecisionPolicy))
        with pytest.raises(ValueError):
            asyncio.run(observed.choose(None, None))
        return {"table_id": kwargs["plan"].table_id, "seed": 1, "match_status": "complete",
                "wall_ms": 0, "scores_by_seat": [0, 0, 0, 0]}

    monkeypatch.setattr(natural, "execute_natural_table", fake_table)
    result = natural.run_arm_stage(arm="baseline", plans=plans, candidate_scorer=None,
        opponent_policies=contract["panel"]["opponent_scenarios"]["H"]["opponent_policies"],
        versions_block=natural.stage.contract_versions_block(contract), step_limit=10,
        value_limits=natural.ValueAnalysisLimits(), decision_observer=fail)
    assert result["status"] == "error" and not result["usable"]
    assert "采集失败" in result["error"]
