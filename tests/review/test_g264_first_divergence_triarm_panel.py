"""G264 离线三臂：桌级重置、首次身份、保底和冻结清单的轻量行为核验。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'tests/review'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import asyncio
from argparse import Namespace
from dataclasses import dataclass, replace
from hashlib import sha256
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]
REVIEW = _project_file(_PROJECT_ROOT, ROOT / "review/freematch-deep-dive-20260925")
if str(REVIEW) not in sys.path:
    sys.path.insert(0, str(REVIEW))

import g264_first_divergence_triarm_panel as subject  # noqa: E402
import g49_official_behavior as official  # noqa: E402
from hangma_bot.application.audit_codec import decision_request_from_json  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.kernel.config import RuleConfig  # noqa: E402
from hangma_bot.policy.r18_integrated_positive_v2_release import (  # noqa: E402
    R18IntegratedPositiveV2ReleasePolicy,
    R18_INTEGRATED_POSITIVE_V2_VALUE_ANALYSIS_SHA256,
)


@dataclass(frozen=True)
class Candidate:
    """仅供 G49 冻结重排逻辑使用的合法候选公开形状。"""

    action_key: str
    rank: int
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class Plan:
    """保留父代完整计划的公开排序和候选身份。"""

    candidates: tuple[Candidate, ...]


class Parent:
    """每次返回相同合法 R18 计划，记录是否重复调用。"""

    def __init__(self) -> None:
        self.calls = 0
        self.plan = Plan((Candidate("discard:1w", 1), Candidate("discard:2w", 2)))

    async def choose(self, _request, _budget):
        """返回预置合法排序，不访问规则和模拟器。"""

        self.calls += 1
        return self.plan


def request(number: int) -> SimpleNamespace:
    """给定同桌决策序号，构造含两张合法弃牌的可见请求。"""

    return SimpleNamespace(
        decision_id=f"same-table:decision-{number}", trigger_seq=number,
        window_key=SimpleNamespace(game_id="same-table", round_no=number),
        rules=SimpleNamespace(legal_candidates=(
            SimpleNamespace(action_key="discard:1w"),
            SimpleNamespace(action_key="discard:2w"))),
    )


def test_b_once_per_complete_table_c_continues_and_first_action_matches(monkeypatch) -> None:
    """B 的一次性标志随完整桌实例重置；C 后续仍调用冻结 G49。"""

    monkeypatch.setattr(subject.frozen_g49, "select",
                        lambda _request, _plan: ("discard:2w", {"reason": "test"}))
    b_parent, c_parent = Parent(), Parent()
    b = subject.FirstDivergencePolicy(arm=subject.ARMS[1], baseline=b_parent,
                                      table_id="same-table")
    c = subject.FirstDivergencePolicy(arm=subject.ARMS[2], baseline=c_parent,
                                      table_id="same-table")
    b_actions = [asyncio.run(b.choose(request(index), None)).candidates[0].action_key
                 for index in (1, 2)]
    c_actions = [asyncio.run(c.choose(request(index), None)).candidates[0].action_key
                 for index in (1, 2)]
    assert b_actions == ["discard:2w", "discard:1w"]
    assert c_actions == ["discard:2w", "discard:2w"]
    assert b.summary()["first_divergence"] == c.summary()["first_divergence"]
    assert b.summary()["changed_count"] == 1
    assert c.summary()["changed_count"] == 2
    assert b_parent.calls == c_parent.calls == 2
    next_table = subject.FirstDivergencePolicy(arm=subject.ARMS[1],
                                                baseline=Parent(), table_id="next-table")
    assert asyncio.run(next_table.choose(request(3), None)).candidates[0].action_key == (
        "discard:2w")
    assert next_table.summary()["changed_count"] == 1


def test_selector_exception_uses_parent_and_records_fallback(monkeypatch) -> None:
    """G49 选择器异常不得使本窗失去父代合法保底。"""

    def fail(_request, _plan):
        raise RuntimeError("test-selector-failure")

    monkeypatch.setattr(subject.frozen_g49, "select", fail)
    policy = subject.FirstDivergencePolicy(arm=subject.ARMS[1], baseline=Parent(),
                                            table_id="same-table")
    plan = asyncio.run(policy.choose(request(1), None))
    assert plan.candidates[0].action_key == "discard:1w"
    assert policy.summary()["changed_count"] == 0
    assert policy.summary()["first_divergence"] is None
    assert policy.summary()["events"][0]["status"] == "fallback"
    assert policy.summary()["events"][0]["reason"] == "selector_exception"


def test_illegal_g49_reorder_fails_closed(monkeypatch) -> None:
    """若冻结包装器声称改弃但结果不在规则合法集，研究单元拒绝记成功。"""

    monkeypatch.setattr(subject.frozen_g49, "select",
                        lambda _request, _plan: ("discard:2w", {"reason": "test"}))
    invalid = request(1)
    invalid.rules.legal_candidates = (SimpleNamespace(action_key="discard:1w"),)
    policy = subject.FirstDivergencePolicy(arm=subject.ARMS[2], baseline=Parent(),
                                            table_id="same-table")
    with pytest.raises(ValueError, match="合法性"):
        asyncio.run(policy.choose(invalid, None))


def test_manifest_binds_frozen_g49_current_rules_and_keeps_release_guard() -> None:
    """新清单绑定源码和规则；旧发布包的坏摘要仍拒绝装配。"""

    args = Namespace(panel_seed=2026122964, root_start=1, roots_per_mix=1)
    manifest = subject.manifest(args)
    assert manifest["arms"] == list(subject.ARMS)
    assert manifest["planned_complete_tables"] == 48
    assert manifest["r18_v2_release_id"] is None
    assert manifest["parent_algorithm_sha256"] == sha256(
        subject.R18_INTEGRATED_POSITIVE_V2_SOURCE.encode()).hexdigest()
    assert manifest["g49_selector_sha256"] == subject.digest(
        ROOT / "tools/research/freematch-deep-dive-20260925/g49_natural_route_policy.py")
    assert manifest["rules_source_hash"] == subject.panel.natural.compute_rules_hash(ROOT)
    assert manifest["input_identity"][subject.INPUTS[1]] == subject.digest(
        _project_file(_PROJECT_ROOT, REVIEW / "g264_first_divergence_triarm_panel.py"))
    with pytest.raises(RuntimeError, match="完整规则源摘要漂移"):
        R18IntegratedPositiveV2ReleasePolicy(
            rules_source_hash="not-published-rules",
            value_analysis_sha256=R18_INTEGRATED_POSITIVE_V2_VALUE_ANALYSIS_SHA256)


def test_run_unit_binds_one_wrapper_to_each_table(monkeypatch) -> None:
    """只经公开工厂核逐桌装配；无需执行真实完整牌局。"""

    plans = [SimpleNamespace(table_id="table-1"), SimpleNamespace(table_id="table-2")]
    monkeypatch.setattr(subject.panel.natural, "build_seat_stage_plans",
                        lambda **_kwargs: plans)
    monkeypatch.setattr(subject.panel.natural.stage, "contract_versions_block",
                        lambda _contract: {"ruleset_version": "current"})
    monkeypatch.setattr(subject.current, "research_parent_factory",
                        lambda _monotonic: Parent())

    def fake_stage(**kwargs):
        policies = [kwargs["candidate_policy_factory"](lambda: 800.0)
                    for _ in plans]
        assert [policy.table_id for policy in policies] == ["table-1", "table-2"]
        assert policies[0] is not policies[1]
        return {"status": "not-executed", "tables": []}

    monkeypatch.setattr(subject.panel.accounted, "run_accounted_stage", fake_stage)
    row = subject.run_unit(("H", 1, 0, subject.ARMS[1], 2026122964))
    assert [item["table_id"] for item in row["stage"]["route_tables"]] == (
        ["table-1", "table-2"])


def test_triplet_uses_stable_first_identity_and_rejects_untriggered_score_gap() -> None:
    """三臂配对允许决策日志 ID 差别，但同墙动作与无触发零效应强约束。"""

    rows = {arm: {"table_id": "table-1", "seed": 7,
                  "result": {"game_key": {"game_id": "game-1"},
                             "versions": {"rules_hash": "current"}},
                  "scores_by_seat": [0, 0, 0, 0],
                  "hand_records": [{"round_no": 1}]}
            for arm in subject.ARMS}
    routes = {arm: {"first_divergence": None} for arm in subject.ARMS}
    assert subject.verify_triplet(rows, routes) is None
    rows[subject.ARMS[2]]["scores_by_seat"] = [1, -1, 0, 0]
    with pytest.raises(ValueError, match="未触发桌"):
        subject.verify_triplet(rows, routes)
    rows[subject.ARMS[2]]["scores_by_seat"] = [0, 0, 0, 0]
    first = {"table_id": "table-1", "game_id": "game-1", "round_no": 2,
             "trigger_seq": 9, "parent_action": "discard:1w",
             "action": "discard:2w", "decision_id": "B-log-id"}
    routes[subject.ARMS[1]]["first_divergence"] = first
    routes[subject.ARMS[2]]["first_divergence"] = {**first,
                                                    "decision_id": "C-log-id"}
    assert subject.verify_triplet(rows, routes) == first
    routes[subject.ARMS[2]]["first_divergence"]["action"] = "discard:3w"
    with pytest.raises(ValueError, match="首次改弃"):
        subject.verify_triplet(rows, routes)


@pytest.mark.parametrize("field", ["illegal_choices", "fallbacks", "timeouts",
                                    "auto_actions"])
def test_unit_rejects_executed_action_departure(monkeypatch, field: str) -> None:
    """只有实际执行等于计划首选时，首次计划分歧才可用于精确拆账。"""

    monkeypatch.setattr(subject.panel, "verify_unit", lambda *_args, **_kwargs: None)
    account = {"complete_hands": 8, "focal_seat": 0, "focal_table_delta": 0}
    monkeypatch.setattr(subject.panel.accounted, "summarize_hands",
                        lambda *_args, **_kwargs: account)
    counts = {name: 0 for name in ("illegal_choices", "fallbacks", "timeouts",
                                  "auto_actions")}
    table = {"table_id": "table-1", "hand_account": account,
             "hand_records": [{} for _ in range(8)], "scores_by_seat": [0, 0, 0, 0],
             "result": {"runtime_counts": counts}}
    route = {"table_id": "table-1", "events": [],
             "changed_count": 0, "first_divergence": None}
    row = {"stage": {"tables": [table], "route_tables": [route]}}
    unit = ("H", 1, 0, subject.ARMS[0], 2026122964)
    subject.verify_unit(row, unit=unit, tables_per_stage=1)
    counts[field] = 1
    with pytest.raises(ValueError, match=field):
        subject.verify_unit(row, unit=unit, tables_per_stage=1)


def test_frozen_official_g49_change_rebuilds_under_current_rules() -> None:
    """冻结官方真实改弃窗按当前规则重算后，A/B/C 的首动作仍与 G49 一致。"""

    result_path = official.OUT
    frozen_path = official.atlas.FROZEN
    if not result_path.is_file() or not frozen_path.is_file():
        pytest.skip("本地冻结官方观察材料不可用")
    frozen_result = json.loads(result_path.read_text(encoding="utf-8"))
    assert frozen_result["candidate_source_sha256"] == subject.digest(
        ROOT / "tests/fixtures/research/freematch-deep-dive-20260925/g49_natural_route_policy.py")
    example = frozen_result["changed"][0]
    freeze = json.loads(frozen_path.read_text(encoding="utf-8"))
    room = next(row for row in freeze["rooms"] if row["room_id"] == example["room_id"])
    audit = official.atlas.source.ROOT / room["audit_dir"]
    if not audit.is_dir():
        pytest.skip("本地官方动作审计不可用")
    decision_file = (audit / "participants" / official.atlas.source.ACTOR /
                     "decisions.jsonl")
    assert decision_file.stat().st_size == room["decision_bytes"]
    manifest = json.loads((audit / "manifest.json").read_text(encoding="utf-8"))[
        "payload"]
    assert manifest["policy_release"]["candidate_source_sha256"] == (
        freeze["parent_source_sha256"])
    target = (example["game_id"], example["round_no"], example["trigger_seq"])
    raw = next(raw for context, raw, _plan in
               official.atlas.source.screen._iter_decisions(audit)
               if (context.get("game_id"), context.get("round_no"),
                   context.get("trigger_seq")) == target)
    decoded = decision_request_from_json(raw)
    rules = HangmaRules(RuleConfig(
        manifest["ruleset_version"], manifest["base_score"],
        manifest["you_cai_bi_kao"]))
    current_rules = rules.analyze(decoded.observation,
                                  value_limits=subject.panel.paired.LIMITS)
    request_now = replace(decoded, rules=current_rules)
    parent = subject.current.research_parent_factory(lambda: 800.0)
    a = asyncio.run(parent.choose(request_now, None))
    assert a.candidates[0].action_key == example["parent_action"]
    selected, evidence = subject.frozen_g49.select(request_now, a)
    assert evidence["reason"] == "g49_novel_ordinary_route"
    assert selected == example["candidate_action"]
    assert selected in {candidate.action_key for candidate in current_rules.legal_candidates}
    b = subject.FirstDivergencePolicy(
        arm=subject.ARMS[1], baseline=subject.current.research_parent_factory(lambda: 800.0),
        table_id=example["game_id"])
    c = subject.FirstDivergencePolicy(
        arm=subject.ARMS[2], baseline=subject.current.research_parent_factory(lambda: 800.0),
        table_id=example["game_id"])
    assert asyncio.run(b.choose(request_now, None)).candidates[0].action_key == selected
    assert asyncio.run(c.choose(request_now, None)).candidates[0].action_key == selected
    assert b.summary()["first_divergence"] == c.summary()["first_divergence"]
    assert b.summary()["changed_count"] == c.summary()["changed_count"] == 1
