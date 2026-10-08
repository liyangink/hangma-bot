"""action-value-v1 机器合同与实现的一致性契约测试。

权威材料：review/llm-guided-heuristic-route-2026-09-15/contracts/action-value-v1.json。
限额与白名单的数值一律从合同 JSON 读取后与实现逐条对账，不在测试里
再硬编码第二份；实现侧的常量是唯一代码来源。
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'tests/contracts'

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
from pathlib import Path
from typing import Any, Mapping

import pytest

from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.kernel.observation import PlayerObservation

from hangma_bot.policy import action_value as av
from hangma_bot.policy import action_value_executor as exe
from hangma_bot.policy.action_value_seeds import (
    SEED_NAMES,
    build_action_value_policy,
    build_sample_view,
    ActionValueScorer,
)


def test_explicit_scorer_budget_changes_execution_and_identity():
    """默认装配不变；显式大额度只放宽操作计数，身份不能伪报实际配置。"""
    source = ('def score_actions(view):\n    for i in range(60000):\n        x = i\n'
              '    return {"status": "SCORED", "entries": '
              '[{"action_key": a["action_key"], "score": 0.0, "trace": {}} for a in view["actions"]]}\n')
    default = ActionValueScorer("test", source)
    research = ActionValueScorer("test", source, max_operations=200000)
    with pytest.raises(exe.WorkloadExceeded): default.score(build_sample_view())
    assert default.last_operation_count > default.max_operations == 100000
    assert research.score(build_sample_view()).status == "SCORED"
    assert 100000 < research.last_operation_count < research.max_operations == 200000
    assert default.candidate_identity("contract", deps_digest="deps") != research.candidate_identity("contract", deps_digest="deps")
    assert default.candidate_identity("contract", deps_digest="deps") == exe.compute_candidate_identity(
        source, "contract", None, exe.EXECUTOR_VERSION, "deps")
    for name in SEED_NAMES:
        assert build_action_value_policy(name).max_operations == 100000
    for params in ({"candidate_max_operations": 100000},
                   {"candidate_execution_profile": {"max_operations": 100000}}):
        with pytest.raises(ValueError): research.candidate_identity("contract", params=params)


@pytest.mark.parametrize("limit", [True, False, 0, -1, 200000.5, "200000", None])
def test_scorer_rejects_invalid_execution_budget(limit):
    with pytest.raises(ValueError): ActionValueScorer("test", "", max_operations=limit)

CONTRACT_PATH = (
    _project_file(_PROJECT_ROOT, Path(__file__).resolve().parents[2]
    / "review/llm-guided-heuristic-route-2026-09-15/contracts/action-value-v1.json")
)


@pytest.fixture(scope="module")
def contract() -> Mapping[str, Any]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def contract_sha256() -> str:
    return hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# 合同标识与 schema
# ---------------------------------------------------------------------------


def test_contract_identity_fields(contract: Mapping[str, Any]) -> None:
    assert contract["schema"] == "sitin-action-value-contract/1"
    assert contract["contract_id"] == "action-value-v1"
    assert contract["candidate_kind"] == av.CANDIDATE_KIND


def test_scoring_view_schema_version_matches(contract: Mapping[str, Any]) -> None:
    assert contract["scoring_view"]["schema_version"] == av.SCORING_VIEW_SCHEMA_VERSION
    # /2：competition 投影（stage_scores/table_scores/freshness_masks）进入候选视图；
    # /3（R8 E3/M1）：加入第三概念 current_stage_scores（= 已完成账 + 当前桌账）
    # 与 residual_gaps（剩余赛程未投影的显式登记）。/1 = 阶段账未进入视图的冻结版。
    # /4（R18）：加入由规则分析产生的 actions[].baotou_after。
    # 结构面变化必须先登记再升版本（R7 P11b；登记表见 TestScoringViewVersionGuard）。
    assert av.SCORING_VIEW_SCHEMA_VERSION == "sitin-scoring-view/4"


def test_route_and_progress_states_match(contract: Mapping[str, Any]) -> None:
    assert tuple(contract["scoring_view"]["route_states"]) == av.ROUTE_STATES
    assert tuple(contract["scoring_view"]["progress_states"]) == av.PROGRESS_STATES


def test_status_values_match(contract: Mapping[str, Any]) -> None:
    assert tuple(contract["output_contract"]["status_values"]) == av.STATUS_VALUES


# ---------------------------------------------------------------------------
# 限额与白名单逐条对账（数值只来自 JSON）
# ---------------------------------------------------------------------------


def test_candidate_limits_match_executor(contract: Mapping[str, Any]) -> None:
    limits = contract["limits"]["candidate"]
    assert limits["max_counted_operations"] == exe.MAX_COUNTED_OPERATIONS
    assert limits["max_local_collection_size"] == exe.MAX_LOCAL_COLLECTION_SIZE
    assert limits["max_source_bytes"] == exe.MAX_SOURCE_BYTES
    # trace 上限定义在 ScoreBatch（构造期序列化测长），执行器再导出对账。
    assert limits["max_trace_bytes"] == av.MAX_TRACE_BYTES
    assert exe.MAX_TRACE_BYTES == av.MAX_TRACE_BYTES
    # R9/S1：结构遍历上限进入合同逐键对账（此前只在执行器侧、由 deps 摘要
    # 间接覆盖；单元口径已补齐为「容器节点 + 标量叶」同口径）。
    assert limits["max_string_chars"] == exe.MAX_STRING_CHARS
    assert limits["max_data_depth"] == exe.MAX_DATA_DEPTH
    assert limits["max_data_cells"] == exe.MAX_DATA_CELLS


#: R9/S1、R9/S1b：结构遍历计费口径必须逐条出现在合同 metering_rules 里（防合同
#: 与实现再次分叉：结构单元口径是执行安全的可观察断言，不是实现细节）。
METERING_RULES_EXPECTED_SUBSTRINGS = (
    "结构遍历按展开节点计费",
    "共享引用按出现次数累积而不去重",
    "结构单元超过 max_data_cells 或深度超过 max_data_depth",
    # R9/S1b：视图分派、未知类型兜底、返回值与 trace、字符串产出速率。
    "集合式字典视图按底层键/键值对展开",
    "分派之外的未知类型保守兜底",
    "候选返回值与 trace 在序列化之前计费并做体积预判",
    "字符串产出（拼接、重复、f-string 与 % 格式化结果）按 64 字符一段计费",
)


def test_contract_registers_structure_unit_metering(
    contract: Mapping[str, Any]
) -> None:
    rules = contract["limits"]["metering_rules"]
    for needle in METERING_RULES_EXPECTED_SUBSTRINGS:
        assert any(needle in rule for rule in rules), needle


def test_rule_analysis_limits_match_rules_module(contract: Mapping[str, Any]) -> None:
    limits = contract["limits"]["rule_analysis"]
    default = ValueAnalysisLimits()
    assert limits["max_expansions"] == default.max_expansions
    assert limits["max_routes_per_candidate"] == default.max_routes_per_candidate
    # 样例视图的上限快照也必须与合同一致。
    assert build_sample_view().analysis_profile.max_expansions == limits["max_expansions"]
    assert (
        build_sample_view().analysis_profile.max_routes_per_candidate
        == limits["max_routes_per_candidate"]
    )


def test_whitelist_builtins_match(contract: Mapping[str, Any]) -> None:
    expected = frozenset(contract["whitelist"]["builtins"])
    assert expected == exe.ALLOWED_BUILTINS
    # 白名单内建在受限运行时中全部有计费包装。
    executor = build_action_value_policy("efficiency_seed")._executor
    assert expected <= set(executor._runtime)


def test_whitelist_methods_match(contract: Mapping[str, Any]) -> None:
    raw: list = contract["whitelist"]["methods_readonly"]
    parsed = {item.split("(", 1)[0].lstrip(".").strip() for item in raw}
    assert parsed == set(exe.ALLOWED_METHODS)
    # "仅局部构造期" 注记的两个方法只允许出现在受限局部容器上：
    # 候选映射（dict 投影）本身没有 append/add 通道。
    mapping = build_sample_view().candidate_view()
    assert not hasattr(mapping, "append")
    assert not hasattr(mapping["actions"][0], "add")


def test_power_exponent_rule_matches(contract: Mapping[str, Any]) -> None:
    rules = contract["limits"]["metering_rules"]
    power_rule = next(rule for rule in rules if "**" in rule)
    assert "<= 4" in power_rule or "<=4" in power_rule
    assert exe.MAX_POWER_EXPONENT == 4


def test_modules_whitelist_empty(contract: Mapping[str, Any]) -> None:
    assert contract["whitelist"]["modules"] == []
    source = """import math

def score_actions(view):
    return {}
"""
    with pytest.raises(exe.StaticCheckError, match="模块级只允许"):
        exe.ActionValueExecutor(source)


# ---------------------------------------------------------------------------
# 入口合同与种子要求
# ---------------------------------------------------------------------------


def test_entry_point_signature_enforced(contract: Mapping[str, Any]) -> None:
    assert "score_actions" in contract["entry_point"]["signature"]
    with pytest.raises(exe.StaticCheckError, match="score_actions"):
        exe.ActionValueExecutor("def helper(view):\n    return {}\n")
    with pytest.raises(exe.StaticCheckError, match="view"):
        exe.ActionValueExecutor("def score_actions(v):\n    return {}\n")


def test_hu_mode_is_compare_legal(contract: Mapping[str, Any]) -> None:
    assert contract["entry_point"]["hu_mode"] == "compare_legal"


def test_required_seeds_registered(contract: Mapping[str, Any]) -> None:
    required = contract["seeds_required"]
    names = set(SEED_NAMES)
    assert "efficiency_seed" in required and "efficiency_seed" in names
    assert "route_value_seed" in required and "route_value_seed" in names
    # 合同以中文描述对照实现；注册表以 hu_first_reference 承接。
    assert any("立即胡优先" in item for item in required)
    assert "hu_first_reference" in names


def test_batch_failure_conditions_each_enforced(contract: Mapping[str, Any]) -> None:
    """output_contract.batch_failure_conditions 逐条有执行路径覆盖。"""
    view = build_sample_view()
    keys = list(view.expected_action_keys())

    def run_with(entries: Any) -> av.ScoreBatch:
        return av.run_scoring_skeleton(
            view, lambda _v: {"status": "SCORED", "entries": entries, "reason": None}
        )

    # 抛出异常
    with pytest.raises(ValueError, match="候选执行失败"):
        av.run_scoring_skeleton(view, lambda _v: (_ for _ in ()).throw(RuntimeError("x")))
    # 非有限数
    with pytest.raises(ValueError):
        run_with([{"action_key": k, "score": float("nan"), "trace": {}} for k in keys])
    # 布尔冒充数
    with pytest.raises(ValueError):
        run_with([{"action_key": k, "score": True, "trace": {}} for k in keys])
    # 遗漏
    with pytest.raises(ValueError, match="遗漏"):
        run_with([{"action_key": k, "score": 1.0, "trace": {}} for k in keys[:-1]])
    # 重复
    duplicated = [{"action_key": k, "score": 1.0, "trace": {}} for k in keys]
    duplicated.append(dict(duplicated[0]))
    with pytest.raises(ValueError, match="重复"):
        run_with(duplicated)
    # 越界
    extra = [{"action_key": k, "score": 1.0, "trace": {}} for k in keys]
    extra.append({"action_key": "nope", "score": 1.0, "trace": {}})
    with pytest.raises(ValueError, match="越界"):
        run_with(extra)
    # 超工作量（受限执行器）
    overwork = (
        "def score_actions(view):\n"
        "    for i in range(200000):\n"
        "        pass\n"
        "    return {'status': 'ABSTAIN', 'reason': 'overwork'}\n"
    )
    with pytest.raises(exe.WorkloadExceeded):
        exe.ActionValueExecutor(overwork).score(view)
    # 缺必需字段：候选必须以 ABSTAIN 显式给出原因，而不是补零。
    abstain = av.run_scoring_skeleton(
        view, lambda _v: {"status": "ABSTAIN", "reason": "缺必需字段 X"}
    )
    assert abstain.entries == () and abstain.reason


# ---------------------------------------------------------------------------
# 信息权限（ScoringView 不含 WorldState/种子/token 属性）
# ---------------------------------------------------------------------------

_FORBIDDEN_FIELD_MARKERS = ("worldstate", "world_state", "seed", "token", "experiment")
_TYPE_FAMILY = (
    av.ScoringView,
    av.ActionView,
    av.CompetitionView,
    av.AnalysisProfileView,
    av.ReferenceFeature,
    av.ActionScore,
    av.ScoreBatch,
)


@pytest.mark.parametrize("cls", _TYPE_FAMILY, ids=[c.__name__ for c in _TYPE_FAMILY])
def test_scoring_view_family_has_no_forbidden_fields(cls: type) -> None:
    import dataclasses

    assert dataclasses.is_dataclass(cls)
    for field in dataclasses.fields(cls):
        lowered = field.name.lower()
        for marker in _FORBIDDEN_FIELD_MARKERS:
            assert marker not in lowered, "{0}.{1}".format(cls.__name__, field.name)
    for name, annotation in cls.__annotations__.items():
        text = str(annotation).lower()
        for marker in _FORBIDDEN_FIELD_MARKERS:
            assert marker not in text, "{0}.{1} 注解 {2}".format(cls.__name__, name, annotation)


def test_visible_state_is_player_observation_projection() -> None:
    view = build_sample_view()
    assert isinstance(view.visible_state, PlayerObservation)
    # 只读访问器不暴露可变内部状态。
    hand = view.hand_codes()
    assert isinstance(hand, tuple)


def test_candidate_view_contains_only_primitive_values() -> None:
    """受限映射递归只含 dict/tuple/str/int/float/bool/None，无对象逃逸。"""
    mapping = build_sample_view().candidate_view()
    assert set(mapping) == {
        "schema_version",
        "visible_state",
        "competition",
        "actions",
        "analysis_profile",
        "reference_features",
    }

    def check(value: Any) -> None:
        assert value is None or isinstance(
            value, (dict, tuple, str, int, float, bool)
        ), "非法类型 {0}".format(type(value).__name__)
        if isinstance(value, dict):
            for key, item in value.items():
                assert isinstance(key, str)
                check(item)
        elif isinstance(value, tuple):
            for item in value:
                check(item)

    check(mapping)


def test_scoring_view_contract_fields_present(contract: Mapping[str, Any]) -> None:
    fields = set(contract["scoring_view"]["fields"])
    assert fields == set(build_sample_view().candidate_view()) - {"schema_version"}


# ---------------------------------------------------------------------------
# RankedCandidate 适配不变量
# ---------------------------------------------------------------------------


def test_ranked_candidate_adaptation_invariants() -> None:
    view = build_sample_view()
    batch = build_action_value_policy("hu_first_reference").score(view)
    ranked = av.batch_to_ranked_candidates(batch, view.actions)
    assert ranked
    assert [item.rank for item in ranked] == list(range(1, len(ranked) + 1))
    for item in ranked:
        assert item.total_score == sum(part.value for part in item.score_parts)
        assert len(item.score_parts) == 1
        assert item.score_parts[0].name == av.CANDIDATE_KIND
    scores = [item.total_score for item in ranked]
    assert scores == sorted(scores, reverse=True)


def test_abstain_batch_adapts_to_empty_candidate_list() -> None:
    view = build_sample_view()
    abstain = av.ScoreBatch(status="ABSTAIN", entries=(), reason="缺必需字段")
    assert av.batch_to_ranked_candidates(abstain, view.actions) == ()


# ---------------------------------------------------------------------------
# 身份
# ---------------------------------------------------------------------------


def test_candidate_identity_binds_contract(contract_sha256: str) -> None:
    scorer = build_action_value_policy("efficiency_seed")
    base = scorer.candidate_identity(contract_sha256)
    assert len(base) == 64
    # 合同内容变化（sha256 变化）必须使身份失效。
    assert scorer.candidate_identity("0" * 64) != base
    # 参数进入身份。
    assert scorer.candidate_identity(contract_sha256, params={"k": 1}) != base
    # 同输入恒等。
    assert scorer.candidate_identity(contract_sha256, params={"k": 1}) == (
        scorer.candidate_identity(contract_sha256, params={"k": 1})
    )


def test_deps_digest_tracks_whitelist_and_limits() -> None:
    digest = exe.compute_deps_digest()
    assert digest == exe.compute_deps_digest()
    assert len(digest) == 64
    # 摘要材料覆盖白名单与限额：手工重算同一材料得到同一哈希，
    # 证明任一依赖变化都会改变摘要（identity.recovery_policy 的基础）。
    material = {
        "executor_version": exe.EXECUTOR_VERSION,
        "whitelist_builtins": sorted(exe.ALLOWED_BUILTINS),
        "whitelist_methods": sorted(exe.ALLOWED_METHODS),
        "limits": {
            "max_counted_operations": exe.MAX_COUNTED_OPERATIONS,
            "max_local_collection_size": exe.MAX_LOCAL_COLLECTION_SIZE,
            "max_source_bytes": exe.MAX_SOURCE_BYTES,
            "max_trace_bytes": av.MAX_TRACE_BYTES,
            "max_int_magnitude": exe.MAX_INT_MAGNITUDE,
            "max_power_exponent": exe.MAX_POWER_EXPONENT,
            # 结构上限（R6/S1 引入；R9/S1 起同时逐键登记在合同 JSON
            # limits.candidate）：字符串长度、嵌套深度、结构单元上限。
            # 单元口径 = 容器节点 + 标量叶同口径各计 1。
            "max_string_chars": exe.MAX_STRING_CHARS,
            "max_data_depth": exe.MAX_DATA_DEPTH,
            "max_data_cells": exe.MAX_DATA_CELLS,
        },
        "view_types": exe._types_digest_material(),
    }
    manual = hashlib.sha256(
        json.dumps(material, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    assert manual == digest


def test_executor_version_is_versioned() -> None:
    assert exe.EXECUTOR_VERSION == build_action_value_policy(
        "route_value_seed"
    ).executor_version
    assert exe.EXECUTOR_VERSION.startswith("action-value-executor/")


# ---------------------------------------------------------------------------
# R1/S4：离线装配层（sitin_gates）身份绑定实际第一方实现与实际分析配置
# ---------------------------------------------------------------------------

_TOOLS_DIR = (
    _project_file(_PROJECT_ROOT, Path(__file__).resolve().parents[2]
    / "review/llm-guided-heuristic-route-2026-09-15/tools")
)


def _load_gates():
    import sys

    if str(_TOOLS_DIR) not in sys.path:
        sys.path.insert(0, str(_TOOLS_DIR))
    import sitin_gates

    return sitin_gates


def test_gates_identity_binds_first_party_file_contents() -> None:
    """仅改任一第一方文件方法体 → candidate_id 变 → 旧准入记录失效。"""
    gates = _load_gates()
    source = "def score_actions(view):\n    return {}\n"
    base = gates.av_identity_binding(source)
    assert base["deps_digest_basis"] == "first_party_file_contents(S4)"
    assert base["deps_digest"] == exe.compute_deps_digest(gates.av_first_party_contents())

    contents = dict(gates.av_first_party_contents())
    contents["hangma_bot.policy.action_value"] += "# body-only tweak\n"
    tweaked_id = exe.compute_candidate_identity(
        source,
        hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest(),
        gates.av_default_identity_params(),
        exe.EXECUTOR_VERSION,
        exe.compute_deps_digest(contents),
    )
    assert tweaked_id != base["candidate_id"]


def test_gates_identity_params_bind_actual_analysis_config() -> None:
    gates = _load_gates()
    binding = gates.av_identity_binding("def score_actions(view):\n    return {}\n")
    limits = binding["params"]["value_analysis_limits"]
    assert limits == {"max_expansions": 2048, "max_routes_per_candidate": 128}
    assert limits["max_expansions"] == ValueAnalysisLimits().max_expansions


def test_gates_record_match_rejects_stale_identity() -> None:
    """依赖变化（deps_digest 变）使旧准入记录拒绝续写（T07）。"""
    gates = _load_gates()
    source = "def score_actions(view):\n    return {}\n"
    record = {
        "schema": gates.AV_ADMISSION_SCHEMA,
        "identity": gates.av_identity_binding(source),
        "layers": {"execution_safety": {"status": "PASS"}},
    }
    ok, reason = gates.av_record_identity_matches(record, source)
    assert ok, reason
    stale = dict(record)
    stale["identity"] = dict(record["identity"])
    stale["identity"]["deps_digest"] = "0" * 64
    ok2, reason2 = gates.av_record_identity_matches(stale, source)
    assert not ok2 and "deps_digest" in reason2
