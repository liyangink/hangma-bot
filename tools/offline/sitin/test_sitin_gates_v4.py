# -*- coding: utf-8 -*-
"""D 包门禁测试（test_sitin_gates_v4.py，新文件；不改现有测试）。

覆盖：T06（监管装载下抛错/超量/NaN/缺动作/非法键 → 拒绝或整批保底、进程
正确终止）、T07（身份失效/装载前监管/旧 schema 拒绝）、五层门禁
（sitin-action-value-admission/1）、工作进程上限 12、子进程凭据剔除、
预算余量夹具。全部离线运行（不调真实 LLM、不跑真实桌赛）。
"""

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
import json
import os
import sys
import uuid
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import sitin_gates as gates  # noqa: E402
from hangma_bot.policy.action_value_seeds import SEEDS  # noqa: E402

GOOD_SOURCE = SEEDS["efficiency_seed"].source


def _tmp_out(tmp_path):
    out = tmp_path / ("av-" + uuid.uuid4().hex[:8])
    out.mkdir(parents=True, exist_ok=True)
    return out


# ============================================================ T06 门禁版


def test_t06_raise_error_probe_rejected_and_group_terminated(tmp_path):
    """抛错样例：整批保底（batch_invalid）且进程组正确终止、宿主不污染。"""
    item = gates._av_probe_item("raise_error")
    assert item["status"] == "PASS", item
    execution = item["execution_tail"]
    assert execution.get("group_still_alive") is False
    assert execution.get("returncode") == 0  # 子进程结构化报告，不是裸崩


def test_t06_over_workload_terminates_with_workload_exceeded(tmp_path):
    """超量样例：计数限额触发 WorkloadExceeded 正确终止（受限子集无 while，
    超量大循环即等价死循环样例）。"""
    item = gates._av_probe_item("over_workload", views=("sample", "max_input"))
    assert item["status"] == "PASS", item
    for name, view in item["per_view"].items():
        assert view["rejected"] and view["failure_kind"] == "workload_exceeded", (name, view)


def test_t06_non_finite_output_rejected(tmp_path):
    """NaN/Inf 样例：非有限浮点使整批失效（不补零、不悄悄钳制）。"""
    item = gates._av_probe_item("non_finite")
    assert item["status"] == "PASS", item
    assert all(view["rejected"] for view in item["per_view"].values())


def test_t06_missing_action_illegal_key_bool_score_rejected(tmp_path):
    """缺动作/非法键/布尔冒充数：输出合同完整性拒绝（整批失效）。"""
    for probe in ("missing_action", "illegal_key", "bool_score"):
        item = gates._av_probe_item(probe)
        assert item["status"] == "PASS", (probe, item)
        assert all(view["failure_kind"] == "batch_invalid"
                   for view in item["per_view"].values()), probe


def test_t06_supervised_load_fallback_emergency_available(tmp_path):
    """整批失败后紧急计划仍可用（保底测试的装载侧验证）。"""
    report = gates.load_candidate_supervised(
        gates.AV_PROBE_RAISE, "sample")
    assert report["ok"] is False
    assert report["results"]["sample"]["failure_kind"] in ("batch_invalid",
                                                           "workload_exceeded")
    assert report["emergency"]["available"] is True
    assert report["emergency"]["action_key"]


# ============================================================ T07 身份与装载前监管


def test_t07_executor_version_change_invalidates_identity():
    """工具/依赖改动使身份失效：executor 版本变 → candidate_id 变 → 旧记录不放行。"""
    base = gates.av_candidate_identity(GOOD_SOURCE)
    mutated = gates.av_candidate_identity(GOOD_SOURCE,
                                          executor_version="action-value-executor/test-x")
    assert base != mutated
    record = {"schema": gates.AV_ADMISSION_SCHEMA,
              "identity": gates.av_identity_binding(
                  GOOD_SOURCE, executor_version="action-value-executor/test-x"),
              "layers": {"execution_safety": {"status": "PASS"}}}
    ok, reason = gates.av_record_identity_matches(record, GOOD_SOURCE)
    # 失配会浮现在首个不一致字段（candidate_id 先于 executor_version 逐项比对）。
    assert not ok and "拒绝续写" in reason


def test_t07_contract_change_invalidates_identity():
    """合同 sha 变（白名单/限额改动等价物）→ 身份失效，旧记录拒绝续写。"""
    record = {"schema": gates.AV_ADMISSION_SCHEMA,
              "identity": gates.av_identity_binding(GOOD_SOURCE),
              "layers": {"execution_safety": {"status": "PASS"}}}
    ok, _ = gates.av_record_identity_matches(record, GOOD_SOURCE)
    assert ok
    tampered = dict(record)
    tampered["identity"] = dict(record["identity"])
    tampered["identity"]["contract_sha256"] = "0" * 64
    ok2, reason2 = gates.av_record_identity_matches(tampered, GOOD_SOURCE)
    assert not ok2 and "contract_sha256" in reason2


def test_t07_static_failure_never_enters_subprocess(monkeypatch, tmp_path):
    """装载前监管：静态检查失败**不进子进程**（run_supervised 不得被调用）。"""
    def _boom(*args, **kwargs):
        raise AssertionError("静态失败不得创建子进程（装载前监管被绕过）")
    monkeypatch.setattr(gates.process_guard, "run_supervised", _boom)
    bad_source = "import os\n\ndef score_actions(view):\n    return {}\n"
    report = gates.load_candidate_supervised(bad_source, "sample")
    assert report["ok"] is False
    assert report["stage"] == "static"
    assert report["supervised"] is False
    assert "静态子集检查未通过" in report["message"]


def test_t07_legacy_gate_schema_cannot_admit_new_candidate():
    """旧 delta admitted schema（sitin-gates/1，admitted=true）不能放行新候选。"""
    legacy = {"schema": "sitin-gates/1", "admitted": True,
              "candidate_identity": gates.av_candidate_identity(GOOD_SOURCE),
              "identity": gates.av_identity_binding(GOOD_SOURCE)}
    ok, reason = gates.av_record_identity_matches(legacy, GOOD_SOURCE)
    assert not ok
    assert "sitin-gates/1" in reason and "action_value_v1" in reason


# ============================================================ 五层门禁记录


def test_admit_action_value_five_layers_all_pass(tmp_path):
    """好候选：执行安全/覆盖/受控研究资格逐层 PASS；效果与发布显式 NOT_EVALUATED。"""
    record = gates.admit_action_value(
        GOOD_SOURCE,
        facts_panel={"generator": "scripted-prefix-fixture-v1", "legal": True,
                     "record_dir": str(_tmp_out(tmp_path))},
        timing_config={"repeats": 2})
    assert record["schema"] == "sitin-action-value-admission/1"
    assert record["layers"]["execution_safety"]["status"] == "PASS"
    for name in ("static_subset", "supervised_load", "limits_full_chain",
                 "output_contract", "isolation_fault", "fallback", "audit"):
        assert record["layers"]["execution_safety"]["items"][name]["status"] == "PASS", name
    coverage = record["layers"]["coverage"]
    assert coverage["status"] == "PASS"
    for family in ("fam_hu", "fam_pass", "fam_chi", "fam_peng", "fam_gang",
                   "fam_discard", "route_combo", "unknown_missing"):
        assert coverage["views"][family]["status"] == "PASS", family
    assert record["layers"]["controlled_research"]["status"] == "ELIGIBLE"
    assert record["effect"]["status"] == "NOT_EVALUATED"
    assert record["release"]["status"] == "NOT_EVALUATED"
    # 整链计时：五段 + 全链分位数 + 预算夹具 + 固定网络余量。
    timing = record["timing"]
    assert timing["status"] == "PASS"
    for segment in ("emergency", "rule_analysis", "fact_build", "scoring",
                    "plan_output"):
        block = timing["segments_ms"][segment]
        assert set(block) >= {"p50", "p95", "p99", "max", "n"}
        assert block["n"] == 2
    assert timing["full_chain_ms"]["n"] == 2
    assert timing["budget_fixture"]["over_budget_refused"] is True
    assert timing["network_margin_ms"] == gates.AV_NETWORK_MARGIN_MS


def test_admit_action_value_static_fail_blocks_all_layers(tmp_path):
    """静态失败：安全层 FAIL、覆盖层标 FAIL 未运行、无研究资格。"""
    bad = "import os\n\n\ndef score_actions(view):\n    return {}\n"
    record = gates.admit_action_value(bad)
    assert record["layers"]["execution_safety"]["status"] == "FAIL"
    assert record["layers"]["execution_safety"]["items"]["static_subset"]["status"] == "FAIL"
    coverage = record["layers"]["coverage"]
    assert coverage["status"] == "FAIL"
    assert "没跑不等于通过" in coverage["reason"]
    assert record["layers"]["controlled_research"]["status"] == "NOT_ELIGIBLE"
    assert record["timing"]["status"] == "SKIP"


def test_admit_coverage_insufficient_not_flattened():
    """样本不足标 INSUFFICIENT：子进程超时 → 逐视图 INSUFFICIENT，不汇总抹平。"""
    gates.AVWorkerSlots.reset_for_test()
    record = gates.admit_action_value(
        GOOD_SOURCE, executor_config={"timeout_sec": 0.0},
        timing_config={"repeats": 1})
    coverage = record["layers"]["coverage"]
    if coverage["status"] in ("INSUFFICIENT", "FAIL"):
        insufficient = [name for name, item in coverage["views"].items()
                        if item["status"] == "INSUFFICIENT"]
        assert insufficient, "执行不可得时必须逐类标 INSUFFICIENT，不许汇总抹平"
    assert record["layers"]["execution_safety"]["status"] == "FAIL"
    gates.AVWorkerSlots.reset_for_test()


# ============================================================ 上限与环境红线


def test_t17_worker_cap_thirteenth_request_rejected():
    """全机工作进程上限 12：第 13 个并发请求拒绝（T17）。"""
    gates.AVWorkerSlots.reset_for_test()
    slots = gates.AVWorkerSlots()
    for index in range(12):
        slots.acquire("worker-{0}".format(index))
    with pytest.raises(gates.WorkerCapExceeded):
        slots.acquire("worker-13")
    assert gates.AVWorkerSlots.active_count() == 12
    slots.release("worker-0")
    slots.acquire("worker-13")  # 释放后可再取
    gates.AVWorkerSlots.reset_for_test()


def test_child_env_strips_all_credentials(monkeypatch):
    """工作子进程环境不含任何凭据类变量（不注入凭据红线）。"""
    for name in ("SITIN_LLM_API_KEY", "DEEPSEEK_API_KEY", "SITIN_LLM_CONFIG",
                 "DSH_HOME", "SOME_TOKEN", "SECRET_VALUE", "PASSWORD_X"):
        monkeypatch.setenv(name, "leak-me")
    env = gates.av_child_env()
    assert "leak-me" not in set(env.values())
    assert not any("KEY" in key.upper() or "TOKEN" in key.upper()
                   or "SECRET" in key.upper() for key in env)


def test_budget_fixture_over_budget_refused():
    """DecisionBudget 剩余额度夹具：增强截止已过 → 拒绝进入增强评分。"""
    from hangma_bot.policy.interface import DecisionBudget
    now = 100.0
    over = DecisionBudget(enhancement_deadline_monotonic=now - 0.001,
                          fallback_deadline_monotonic=now + 1.0,
                          latest_send_at_monotonic=now + 2.0)
    ok, reason = gates.av_budget_headroom(now, over)
    assert not ok and "增强截止已过" in reason
    tight = DecisionBudget(enhancement_deadline_monotonic=now + 0.05,
                           fallback_deadline_monotonic=now + 1.0,
                           latest_send_at_monotonic=now + 2.0)
    ok2, reason2 = gates.av_budget_headroom(now, tight)
    assert not ok2 and "网络余量" in reason2
    fine = DecisionBudget(enhancement_deadline_monotonic=now + 1.0,
                          fallback_deadline_monotonic=now + 2.0,
                          latest_send_at_monotonic=now + 3.0)
    ok3, _ = gates.av_budget_headroom(now, fine)
    assert ok3


def test_admission_record_written_to_independent_file(tmp_path):
    """新门禁独立记录文件：record_dir 落盘且可回读、schema 正确。"""
    out = _tmp_out(tmp_path)
    record = gates.admit_action_value(GOOD_SOURCE, timing_config={"repeats": 1},
                                      facts_panel={"generator": "x", "legal": True,
                                                   "record_dir": str(out)})
    data = json.loads((out / "admission.json").read_text(encoding="utf-8"))
    assert data["schema"] == gates.AV_ADMISSION_SCHEMA
    assert data["identity"]["candidate_id"] == record["identity"]["candidate_id"]
