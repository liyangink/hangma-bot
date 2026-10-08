"""坐隐 1.3 / 1.4 工具自测。

重点守两件事：
  1. 事实清单里的字段名必须与源码一致（防止清单漂移成"看起来对"）。
  2. 配置快照的指纹必须只对**参与实验语义**的字段敏感，
     机器与仓库状态变化不得改变指纹。
"""

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

import importlib.util
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_REPO = _PROJECT_ROOT


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _project_file(_PROJECT_ROOT, _HERE / (name + ".py")))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


config = _load("sitin_config")
facts = _load("sitin_facts")


# ---------------------------------------------------------------------------
# 1.4 事实清单：字段名与源码一致
# ---------------------------------------------------------------------------

HANGMA_INTERFACE = _project_file(_PROJECT_ROOT, _REPO / "src/hangma_bot/hangma/interface.py")
OBSERVATION = _project_file(_PROJECT_ROOT, _REPO / "src/hangma_bot/kernel/observation.py")
EVALUATION_V1 = _project_file(_PROJECT_ROOT, _REPO / "src/hangma_bot/policy/evaluation_v1.py")


@pytest.mark.parametrize("field", sorted(facts.OBSERVATION_FIELDS))
def test_observation_fields_exist_in_source(field):
    """盘点表里的观察字段必须真的在 PlayerObservation/PublicEvent 里出现。"""

    text = OBSERVATION.read_text(encoding="utf-8")
    assert field + ":" in text or field + " = " in text or field in text, field


@pytest.mark.parametrize("field", sorted(facts.CANDIDATE_FACT_FIELDS))
def test_candidate_fact_fields_exist_in_source(field):
    assert field + ":" in HANGMA_INTERFACE.read_text(encoding="utf-8"), field


@pytest.mark.parametrize("field", sorted(facts.BASE_CONTEXT_FIELDS))
def test_base_context_fields_exist_in_source(field):
    assert field + ":" in EVALUATION_V1.read_text(encoding="utf-8"), field


@pytest.mark.parametrize("field", sorted(facts.RULE_STATE_FIELDS))
def test_rule_state_fields_exist_in_source(field):
    assert field + ":" in OBSERVATION.read_text(encoding="utf-8"), field


def test_unclassified_facts_are_explicit_and_frozen():
    """不属于任何已知事实层的事实必须被**显式列出**，且清单固定。

    当前唯一一项是 `fan`：总番只在结算层产生，动作前不可得。若将来把某项
    接入某层却忘了更新本清单，这个断言会失败——这正是它的用途。
    """

    report = facts.build_inventory()
    known = set(facts.OBSERVATION_FIELDS) | set(facts.RULE_STATE_FIELDS) | \
        set(facts.CANDIDATE_FACT_FIELDS) | set(facts.BASE_CONTEXT_FIELDS) | \
        set(facts.VALUE_FACT_FIELDS) | set(facts.VALUE_ROUTE_FIELDS)
    unclassified = report["summary"]["unclassified_facts"]
    # 初版误把 fan 标为"任何层都不提供"；核实后它经 Settlement 可达，
    # 因此当前不应有任何事实落在"未归类"里。
    assert unclassified == [], unclassified
    for row in report["mechanisms"]:
        for side in ("pre", "post"):
            for item in row[side]:
                if item["layer"] is None:
                    assert item["fact"] in unclassified


def test_ungraspable_facts_are_not_silently_marked_present():
    """已知不可得/需接入的事实不得被标成 present。"""

    report = facts.build_inventory()
    # 同一字段可能同时出现在动作前与动作后（如 catch_play），
    # 状态必须**按 side 区分**——全局覆盖会把动作前的分类冲掉。
    pre_status, post_status = {}, {}
    for row in report["mechanisms"]:
        for item in row["pre"]:
            pre_status[item["fact"]] = item["status"]
        for item in row["post"]:
            post_status[item["fact"]] = item["status"]
    # fan 经 value_facts 的 Settlement 可达，但默认关闭——不是"任何层都不提供"
    assert post_status.get("fan") == facts.NEEDS_VALUE_ANALYSIS
    # 未接入基础评分上下文的字段（**动作前**状态）
    for name in ("chain_count", "baotou", "catch_play_owner_seat", "remaining_tile_count"):
        assert pre_status.get(name) == facts.NEEDS_CONTEXT, name
    # value_facts 默认关闭
    assert post_status.get("immediate_settlement") == facts.NEEDS_VALUE_ANALYSIS


def test_post_action_state_is_not_classified_as_current_observation():
    """动作后状态不得因为**字段同名**就被当成当前观察（审查 S5-6）。"""

    report = facts.build_inventory()
    post = {}
    for row in report["mechanisms"]:
        for item in row["post"]:
            post[item["fact"]] = item
    # 当前 M3 的**动作后**事实是圈状态两项；chain_count/baotou 目前只在动作前列出
    for name in ("catch_play", "catch_play_owner_seat"):
        assert name in post, name
        assert post[name]["determination"] == "rule_transition", name
        assert post[name]["status"] == "needs_rule_transition", name
    assert report["summary"]["needs_rule_transition_facts"] == [
        "catch_play", "catch_play_owner_seat"]


def test_fan_note_states_it_is_available_before_the_action():
    """番值消费说明不得再写"动作前只能用代理量"（审查 S5-5）。"""

    m1 = [r for r in facts.MECHANISMS if r["id"] == "M1"][0]
    note = m1["note"]
    assert "动作选择之前" in note
    assert "不得再用 chain_count/baotou 作粗糙代理" in note


# ---------------------------------------------------------------------------
# 1.3 配置快照：指纹语义
# ---------------------------------------------------------------------------

def _snapshot(**over):
    kwargs = dict(
        ruleset_version="hangma-mvp-v10-public-counts",
        base_score=1,
        you_cai_bi_kao=False,
        rounds_per_game=8,
        opponents=["a", "a", "a"],
        clock_mode="logical",
    )
    kwargs.update(over)
    return config.build_snapshot(_REPO, **kwargs)


def test_fingerprint_ignores_host_and_repo_state():
    """指纹只对实验语义敏感；机器与 git 状态不得改变它。"""

    snap = _snapshot()
    fp = config.fingerprint(snap)
    tampered = dict(snap)
    tampered["host"] = {"platform": "other", "machine": "x", "python": "0"}
    tampered["repo"] = dict(snap["repo"])
    tampered["repo"]["commit"] = "0" * 40
    tampered["repo"]["dirty"] = not snap["repo"]["dirty"]
    tampered["repo"]["dirty_file_count"] = 999
    assert config.fingerprint(tampered) == fp


@pytest.mark.parametrize("field,value", [
    ("base_score", 2),
    ("you_cai_bi_kao", True),
    ("rounds_per_game", 4),
    ("ruleset_version", "other"),
    ("opponents", ["b", "b", "b"]),
])
def test_fingerprint_changes_when_semantics_change(field, value):
    base = config.fingerprint(_snapshot())
    assert config.fingerprint(_snapshot(**{field: value})) != base


def test_fingerprint_covers_policy_source_not_just_rules():
    """指纹必须同时覆盖**策略侧源码**。

    初版只哈希了 `src/hangma_bot/hangma/`（规则模块），改权重或改评分函数
    不会改变指纹——而"改了什么策略"正是实验身份最容易漂移的地方。
    """

    snap = _snapshot()
    assert snap["repo"]["rules_source_sha256"]
    assert snap["repo"]["policy_source_sha256"], "策略源码指纹不得为空"
    assert snap["repo"]["rules_source_sha256"] != snap["repo"]["policy_source_sha256"]


def test_snapshot_requires_explicit_ruleset_version():
    """规则语义版本必须显式给出，不推断。"""

    with pytest.raises(TypeError):
        config.build_snapshot(_REPO, base_score=1, you_cai_bi_kao=False,
                              rounds_per_game=8, opponents=[], clock_mode="logical")


def test_snapshot_rejects_invalid_inputs():
    with pytest.raises(ValueError):
        _snapshot(base_score=0)
    with pytest.raises(ValueError):
        _snapshot(clock_mode="wall")
