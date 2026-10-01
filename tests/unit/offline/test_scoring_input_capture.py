"""仅人工结构fixture验证记录接缝；真实score/rules/model/world/table调用均0。"""
from __future__ import annotations

import asyncio
import copy
import gzip
import hashlib
import io
import json
import sys
from types import SimpleNamespace

import pytest

from hangma_bot.offline.scoring_input_capture import ScoringInputCapture, ScoringInputCaptureLimits
from hangma_bot.offline.vip_route_development import VipDevelopmentAuditPolicy
from hangma_bot.policy.action_value_executor import WorkloadExceeded
from hangma_bot.kernel.actions import Pass
from tests.unit.policy.support import candidates_for, make_budget, make_observation, make_request, make_rules


@pytest.fixture(autouse=True)
def forbid_real_research_calls(monkeypatch):
    """整套draft测试封死真实研究入口；替身调用单独使用fixture标签。"""
    from hangma_bot.hangma.engine import HangmaRules
    from hangma_bot.policy.action_value_executor import ActionValueExecutor
    from hangma_bot.simulation.engine import SimulationEngine
    def forbidden(*args, **kwargs):
        raise AssertionError("draft tests禁止真实score/rules/world/table")
    monkeypatch.setattr(HangmaRules, "analyze", forbidden)
    monkeypatch.setattr(ActionValueExecutor, "__init__", forbidden)
    monkeypatch.setattr(ActionValueExecutor, "score", forbidden)
    monkeypatch.setattr(ActionValueExecutor, "score_vip_route", forbidden)
    monkeypatch.setattr(SimulationEngine, "start", forbidden)
    monkeypatch.setattr(SimulationEngine, "advance", forbidden)


def fixture_dto():
    """未经过规则的人工记录形状；只用于JSON完整保真，不冒充真实数学图。"""
    return {"schema_version": "vip-route-scoring-view/2", "graph_schema_version": "vip-route-action-graph/2",
        "fixture_kind": "synthetic_capture_shape_not_rule_or_score_measurement",
        "visible_state": {"seat": 0, "remaining_tile_count": None}, "binding": {"base_score": 1},
        "actions": [{"action_key": "pass", "node_key": "fixture"}],
        "nodes": [{"node_key": "fixture", "children": [], "waiting": {
            "normal_draw_hu_payments": None, "legal_hu_draw_codes": [], "unseen_capacities": [None, 0, 2],
            "qualification_unknown_codes": ["1w"], "known_zero": 0, "known_empty": []}}]}


def capture(stream=None, **overrides):
    limits = {"max_view_json_bytes": 4096, "max_total_json_bytes": 16384, "max_unique_views": 8}
    limits.update(overrides)
    stream = io.BytesIO() if stream is None else stream
    return ScoringInputCapture(stream, limits=ScoringInputCaptureLimits(**limits)), stream


def saved_rows(stream):
    return [json.loads(line) for line in gzip.decompress(stream.getvalue()).splitlines()]


class FixtureTypedView:
    """人工typed-view形状；仅暴露待记录字段，不生成规则或隐藏世界。"""
    def __init__(self, dto=None):
        self.dto = fixture_dto() if dto is None else dto
        self.candidate_view_calls = 0
        self.actions = (SimpleNamespace(action_key="pass"),)
        self.nodes = ()
        self.waiting_draw_witness_count = self.target_distance_evaluation_count = 0

    def candidate_view(self):
        self.candidate_view_calls += 1
        return copy.deepcopy(self.dto)


class FixtureExecutor:
    """人工score故障入口；其调用数不是生产候选评分费用。"""
    def __init__(self, exception=None):
        self.last_operation_count = None
        self.fixture_score_calls = 0
        self.exception = exception

    def score_vip_route(self, view):
        self.fixture_score_calls += 1
        self.last_operation_count = 17
        if self.exception is not None:
            raise self.exception
        return SimpleNamespace(status="SCORED", entries=(SimpleNamespace(action_key="pass"),))


class FixtureInnerPolicy:
    """只接收公开请求，不推进世界；替身分数没有实际效果信用。"""
    def __init__(self, executor, view):
        self.executor, self.view = executor, view
        self.fixture_executor = executor  # 故障注入绑定原人工替身，不指向后来包装器

    async def choose(self, request, budget):
        self.executor.score_vip_route(self.view)
        return SimpleNamespace(candidates=(SimpleNamespace(rank=1, action_key="pass", total_score=0.0,
            score_trace={"fixture": True}, is_emergency=False),), degraded_reasons=())


def request():
    return make_request(make_observation(), make_rules(candidates_for((Pass(),))))


def fixture_policy(recorder, executor=None, view=None):
    executor = FixtureExecutor() if executor is None else executor
    view = FixtureTypedView() if view is None else view
    rows = []
    inner = FixtureInnerPolicy(executor, view)
    policy = VipDevelopmentAuditPolicy(inner, "fixture-C", lambda: {"match_id": "fixture", "pool": "H",
        "root_id": "fixture-root", "permutation": [0, 1, 2, 3], "source_kind": "mock"}, rows.append,
        challenger=True, capture=recorder)
    return policy, rows, executor, view


def test_same_view_stored_once_receipt_per_fixture_score():
    recorder, stream = capture()
    policy, rows, executor, view = fixture_policy(recorder)
    for _ in range(2):
        asyncio.run(policy.choose(request(), make_budget()))
    receipts = [row["scoring_calls"][0]["input_capture"] for row in rows]
    assert [r["status"] for r in receipts] == ["stored", "deduplicated"]
    assert receipts[0]["view_sha256"] == receipts[1]["view_sha256"]
    assert [row["scoring_calls"][0]["call_no"] for row in rows] == [1, 2]
    assert all(row["scoring_calls"][0]["actual_score_calls"] == 1 for row in rows)
    assert all(row["scoring_calls"][0]["score_monotonic_seconds"] >= 0 for row in rows)
    assert all(row["timing_scope"] == "policy_choose_with_input_capture_observed_not_official_runtime" for row in rows)
    assert executor.fixture_score_calls == view.candidate_view_calls == 2
    final = recorder.finish()
    assert final["terminal"]["terminal_valid"] and final["store_calls"] == 2
    assert final["unique_views_saved"] == 1 and len(saved_rows(stream)) == 1
    assert final["encode_attempts"] == 2 and final["verification_encode_attempts"] == 1
    assert all(row["c_self_scored"] for row in rows)


def test_none_empty_zero_entire_dto_roundtrip():
    recorder, stream = capture()
    original = fixture_dto()
    receipt = recorder.store(original)
    final = recorder.finish()
    saved = saved_rows(stream)[0]
    assert saved["view"] == original
    raw = json.dumps(original, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    assert receipt.view_sha256 == saved["view_sha256"] == hashlib.sha256(raw).hexdigest()
    assert receipt.json_bytes == saved["json_bytes"] == len(raw)
    assert saved["view"]["nodes"][0]["waiting"]["normal_draw_hu_payments"] is None
    assert saved["view"]["nodes"][0]["waiting"]["legal_hu_draw_codes"] == []
    assert saved["view"]["nodes"][0]["waiting"]["unseen_capacities"] == [None, 0, 2]
    assert final["terminal"]["compressed_sha256"] == hashlib.sha256(stream.getvalue()).hexdigest()


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_capture_rejected_real_score_blocked(value):
    recorder, stream = capture()
    dto = fixture_dto()
    dto["not_finite"] = value
    policy, rows, executor, _ = fixture_policy(recorder, view=FixtureTypedView(dto))
    with pytest.raises(ValueError, match="捕获失败"):
        asyncio.run(policy.choose(request(), make_budget()))
    call = rows[0]["scoring_calls"][0]
    assert executor.fixture_score_calls == 0 and call["actual_score_calls"] == 0
    assert call["input_capture"]["view_sha256"] is None
    assert call["input_capture"]["json_bytes"] is None
    assert not call["score_completed"] and rows[0]["candidate_operations"] is None
    assert recorder.finish()["terminal"]["terminal_valid"] is False


class WriteFailure(io.BytesIO):
    def write(self, raw):
        raise OSError("fixture write failure")


class ToggleWriteFailure(io.BytesIO):
    fail = False

    def write(self, raw):
        if self.fail:
            raise OSError("fixture next-window write failure")
        return super().write(raw)


def test_io_failure_zero_fixture_score_small_receipt_preserved():
    recorder, _ = capture(WriteFailure())
    policy, rows, executor, _ = fixture_policy(recorder)
    with pytest.raises(ValueError, match="捕获失败"):
        asyncio.run(policy.choose(request(), make_budget()))
    call = rows[0]["scoring_calls"][0]
    assert executor.fixture_score_calls == call["actual_score_calls"] == 0
    assert call["input_capture"]["status"] == "failed" and call["input_capture"]["view_sha256"]
    assert rows[0]["status"] == "failed" and not rows[0]["c_self_scored"]
    assert not recorder.finish()["terminal"]["terminal_valid"]


def test_prior_success_then_io_failure_never_reuses_operation_count():
    stream = ToggleWriteFailure()
    recorder, _ = capture(stream)
    policy, rows, executor, view = fixture_policy(recorder)
    asyncio.run(policy.choose(request(), make_budget()))
    assert rows[0]["candidate_operations"] == 17
    # 新图强制实际写入；不能以同图去重绕过故障入口。
    view.dto["different_window"] = 1
    stream.fail = True
    with pytest.raises(ValueError, match="捕获失败"):
        asyncio.run(policy.choose(request(), make_budget()))
    call = rows[1]["scoring_calls"][0]
    assert executor.fixture_score_calls == 1 and call["actual_score_calls"] == 0
    assert call["candidate_operations"] is None and rows[1]["candidate_operations"] is None
    assert call["score_monotonic_seconds"] is None
    assert rows[1]["scoring_cumulative_failed_calls"] == 1 and rows[0]["c_self_scored"]
    assert recorder.finish()["terminal"]["terminal_valid"] is False


def test_score_entry_failure_resets_old_public_operation_count():
    class EntryFailure(FixtureExecutor):
        fail = False

        def score_vip_route(self, view):
            if self.fail:
                self.fixture_score_calls += 1
                raise WorkloadExceeded("fixture before new meter result")
            return super().score_vip_route(view)
    recorder, _ = capture()
    executor = EntryFailure()
    policy, rows, _, _ = fixture_policy(recorder, executor=executor)
    asyncio.run(policy.choose(request(), make_budget()))
    executor.fail = True
    with pytest.raises(WorkloadExceeded):
        asyncio.run(policy.choose(request(), make_budget()))
    assert rows[0]["candidate_operations"] == 17
    assert rows[1]["candidate_operations"] is None
    assert rows[1]["scoring_calls"][0]["candidate_operations"] is None
    assert rows[1]["scoring_calls"][0]["actual_score_calls"] == 1


def test_workload_baseexception_keeps_view_and_failed_call_receipt():
    recorder, stream = capture()
    error = WorkloadExceeded("fixture operation ceiling")
    policy, rows, executor, _ = fixture_policy(recorder, executor=FixtureExecutor(error))
    with pytest.raises(WorkloadExceeded) as caught:
        asyncio.run(policy.choose(request(), make_budget()))
    assert caught.value is error  # 原BaseException，不转成成功或吞掉
    call = rows[0]["scoring_calls"][0]
    assert executor.fixture_score_calls == call["actual_score_calls"] == 1
    assert call["candidate_operations"] == 17 and not call["score_completed"]
    assert call["score_monotonic_seconds"] >= 0
    assert call["input_capture"]["saved_before_score"] and call["status"] == "failed"
    recorder.finish()
    assert saved_rows(stream)[0]["view_sha256"] == call["input_capture"]["view_sha256"]
    assert rows[0]["scoring_cumulative_failed_calls"] == 1


@pytest.mark.parametrize("error_type", [KeyboardInterrupt, SystemExit])
def test_header_interrupt_keeps_store_and_score_failure_denominator(error_type):
    error = error_type("fixture first header interrupted")
    class InterruptOnce(io.BytesIO):
        interrupted = False

        def write(self, raw):
            if not self.interrupted:
                self.interrupted = True
                raise error
            return super().write(raw)
    recorder, stream = capture(InterruptOnce())
    policy, rows, executor, _ = fixture_policy(recorder)
    with pytest.raises(error_type) as caught:
        asyncio.run(policy.choose(request(), make_budget()))
    assert caught.value is error
    call = rows[0]["scoring_calls"][0]
    assert call["input_capture"]["status"] == "failed"
    assert call["input_capture"]["view_sha256"] and not call["input_capture"]["saved_before_score"]
    assert executor.fixture_score_calls == call["actual_score_calls"] == 0
    assert call["candidate_operations"] is rows[0]["candidate_operations"] is None
    assert rows[0]["scoring_cumulative_failed_calls"] == 1
    final = recorder.finish()
    assert final["store_calls"] == final["failed_store_calls"] == 1
    assert final["unique_views_saved"] == 0 and final["gzip_write_result_uncertain_attempts"] == 1
    assert final["terminal"]["store_calls_reconciled"]
    assert not final["terminal"]["terminal_valid"]


@pytest.mark.parametrize("error_type", [KeyboardInterrupt, SystemExit])
def test_score_interrupt_then_sink_failure_preserves_original_and_view(error_type):
    recorder, stream = capture()
    error = error_type("fixture score interrupted")
    policy, rows, executor, _ = fixture_policy(recorder, executor=FixtureExecutor(error))
    def fail_sink(row):
        rows.append(row)
        raise OSError("fixture sink secondary failure")
    policy.sink = fail_sink
    with pytest.raises(error_type) as caught:
        asyncio.run(policy.choose(request(), make_budget()))
    assert caught.value is error and any("小收据写入再次失败" in note for note in error.__notes__)
    call = rows[0]["scoring_calls"][0]
    assert call["status"] == "failed" and not call["score_completed"]
    assert executor.fixture_score_calls == call["actual_score_calls"] == 1
    assert call["candidate_operations"] == rows[0]["candidate_operations"] == 17
    assert policy.scoring.failed_calls == policy.scoring.audit_sink_failed_calls == 1
    final = recorder.finish()
    assert final["terminal"]["terminal_valid"]  # 仅存储完整；批次另由评分失败否决
    assert saved_rows(stream)[0]["view_sha256"] == call["input_capture"]["view_sha256"]


@pytest.mark.parametrize("phase", ["write", "read", "close"])
def test_finish_interrupt_invalid_closes_stream_and_preserves_original(phase):
    error = KeyboardInterrupt("fixture terminal " + phase + " interrupted")
    class TerminalInterrupt(io.BytesIO):
        armed = False
        interrupted = False

        def interrupt(self, method):
            if self.armed and phase == method and not self.interrupted:
                self.interrupted = True
                raise error

        def write(self, raw):
            self.interrupt("write")
            return super().write(raw)

        def read(self, size=-1):
            self.interrupt("read")
            return super().read(size)

        def close(self):
            self.interrupt("close")
            return super().close()
    stream = TerminalInterrupt()
    recorder, _ = capture(stream)
    assert recorder.store(fixture_dto()).saved_before_score
    stream.armed = True
    if phase == "close":
        # finish正常保留调用者stream；用读中断触发尽力关闭，再叠加close中断。
        original_read = stream.read
        def interrupt_read(size=-1):
            raise error
        stream.read = interrupt_read
    with pytest.raises(KeyboardInterrupt) as caught:
        recorder.finish()
    assert caught.value is error
    final = recorder.costs
    assert final["terminal"]["interrupted"] and not final["terminal"]["terminal_valid"]
    assert final["terminal"]["store_calls_reconciled"]
    if phase == "close":
        assert any("binary_stream" in item for item in final["terminal"]["errors"])
        stream.close()  # 一次中断之后测试显式关闭；不能冒充先前关闭成功
    assert stream.closed and recorder.finish() == final


def test_earlier_capture_failure_not_erased_by_next_successful_window():
    recorder, stream = capture()
    bad = fixture_dto()
    bad["invalid"] = float("nan")
    policy, rows, executor, view = fixture_policy(recorder, view=FixtureTypedView(bad))
    with pytest.raises(ValueError):
        asyncio.run(policy.choose(request(), make_budget()))
    view.dto = fixture_dto()
    asyncio.run(policy.choose(request(), make_budget()))
    assert rows[0]["status"] == "failed" and rows[1]["c_self_scored"]
    assert rows[1]["scoring_cumulative_failed_calls"] == 1
    assert executor.fixture_score_calls == 1 and len(rows) == 2
    final = recorder.finish()
    assert final["failed_store_calls"] == 1 and not final["terminal"]["terminal_valid"]
    assert len(saved_rows(stream)) == 1


@pytest.mark.parametrize("overrides", [
    {"max_view_json_bytes": 5}, {"max_unique_views": 1},
    {"max_view_json_bytes": 4096, "max_total_json_bytes": 4096},
])
def test_explicit_capture_ceiling_failure_keeps_denominator(overrides):
    recorder, _ = capture(**overrides)
    dto = fixture_dto()
    if overrides.get("max_view_json_bytes") != 5:
        assert recorder.store(dto).saved_before_score
        dto["different"] = "x" * (3000 if "max_total_json_bytes" in overrides else 1)
    failed = recorder.store(dto)
    if "max_total_json_bytes" in overrides:
        # 第二个图仍未达单图4096，累计原图+本图越过4096。
        if failed.saved_before_score:
            dto["different"] = "x" * 3400
            failed = recorder.store(dto)
    assert not failed.saved_before_score
    assert recorder.costs["failed_store_calls"] == 1
    assert not recorder.finish()["terminal"]["terminal_valid"]


def test_finish_verifies_corrupted_stream_and_is_idempotent():
    recorder, stream = capture()
    assert recorder.store(fixture_dto()).saved_before_score
    stream.seek(0)
    stream.write(b"BAD")
    stream.seek(0, 2)
    first = recorder.finish()
    assert first["terminal"]["terminal_valid"] is False
    assert recorder.finish() == first


@pytest.mark.parametrize("metadata", ["float_bytes", "bool_bytes", "invalid_sha"])
def test_finish_rejects_tampered_metadata_type(metadata):
    class MetadataRewrite(io.BytesIO):
        armed = False

        def seek(self, position, whence=0):
            if self.armed and position == 0 and whence == 0:
                self.armed = False
                row = json.loads(gzip.decompress(self.getvalue()))
                if metadata == "float_bytes":
                    row["json_bytes"] = float(row["json_bytes"])
                elif metadata == "bool_bytes":
                    row["json_bytes"] = True
                else:
                    row["view_sha256"] = 0
                replacement = gzip.compress(json.dumps(row).encode() + b"\n", mtime=0)
                super().seek(0)
                super().truncate(0)
                super().write(replacement)
            return super().seek(position, whence)
    recorder, stream = capture(MetadataRewrite())
    assert recorder.store(fixture_dto()).saved_before_score
    stream.armed = True
    final = recorder.finish()
    assert not final["terminal"]["terminal_valid"]
    assert any("类型不符" in error for error in final["terminal"]["errors"])


def test_new_policy_requires_explicit_capture_injection():
    with pytest.raises(ValueError, match="显式注入"):
        VipDevelopmentAuditPolicy(FixtureInnerPolicy(FixtureExecutor(), FixtureTypedView()), "fixture-C",
            lambda: {}, lambda _: None, challenger=True)


def test_fixtures_do_not_invoke_real_rule_executor_or_world(monkeypatch):
    """本测试会把真实副作用入口封死；人工Interface测试仍能通过。"""
    from hangma_bot.hangma.engine import HangmaRules
    from hangma_bot.policy.action_value_executor import ActionValueExecutor
    from hangma_bot.simulation.engine import SimulationEngine
    def forbidden(*args, **kwargs):
        raise AssertionError("draft fixture禁止真实评分/规则/世界")
    monkeypatch.setattr(HangmaRules, "analyze", forbidden)
    monkeypatch.setattr(ActionValueExecutor, "score_vip_route", forbidden)
    monkeypatch.setattr(SimulationEngine, "start", forbidden)
    monkeypatch.setattr(SimulationEngine, "advance", forbidden)
    recorder, _ = capture()
    policy, rows, _, _ = fixture_policy(recorder)
    asyncio.run(policy.choose(request(), make_budget()))
    assert rows[0]["c_self_scored"] and recorder.finish()["terminal"]["terminal_valid"]


@pytest.mark.parametrize("failure", ["score", "close", "interrupt", "interrupt_then_cost_io"])
def test_public_mock_orchestration_invalidates_both_pool_estimates(tmp_path, monkeypatch, failure):
    """真实编排函数+人工所有依赖，只验证失败传播；没有实际桌实例。"""
    import hangma_bot.offline.vip_route_development as development
    from hangma_bot.kernel.config import RuleConfig, TimingConfig, TournamentConfig
    from hangma_bot.hangma.interface import ValueAnalysisLimits
    from hangma_bot.offline.evaluate import PolicyDeclaration
    from hangma_bot.offline.vip_evaluation import FrozenRoot
    from hangma_bot.policy.action_value_executor import ActionValueExecutor
    from hangma_bot.hangma.engine import HangmaRules
    from hangma_bot.simulation.engine import SimulationEngine
    def forbidden(*a, **k):
        raise AssertionError("人工编排测试禁止真实score/rules/world/table")
    monkeypatch.setattr(ActionValueExecutor, "score_vip_route", forbidden)
    monkeypatch.setattr(HangmaRules, "analyze", forbidden)
    monkeypatch.setattr(SimulationEngine, "start", forbidden)
    monkeypatch.setattr(SimulationEngine, "advance", forbidden)
    package = tmp_path / "fixture-package"
    package.mkdir()
    (package / "generation.json").write_text('{"fixture_only":true}')
    contract = tmp_path / "fixture-contract.md"
    contract.write_text("synthetic orchestration fixture, no measured candidate")
    generation_path, probe_path = tmp_path / "fixture-generation.json", tmp_path / "fixture-probe.json"
    generation_path.write_text('{}')
    probe_path.write_text('{}')
    permutations = ((0, 1, 2, 3), (1, 2, 3, 0), (2, 3, 0, 1), (3, 0, 1, 2))
    root = FrozenRoot("fixture-root", permutations, ("all_natural",) * 4, (0.0,) * 4)
    rules = RuleConfig("fixture-no-rule-analysis", 1, False)
    config = TournamentConfig(1, 8, rules, TimingConfig(1, 1, 3))
    identity = {"source_manifest": {}, "contract_path": contract.name, "candidate_id": "fixture-only"}
    generation = SimpleNamespace(raw=b"fixture-generation", rule_config=rules,
        route_limits=ValueAnalysisLimits(max_expansions=8192), identity=lambda _: identity)
    batch = SimpleNamespace(batch_id="fixture-capture-only", generation_batch_file=generation_path,
        candidate_package=package, behavior_probe_summary_file=probe_path, raw=b"fixture-batch-2",
        frozen_files={}, seeds=((root, 0),), pools=("H", "M"), table_instance_limit=16,
        wall_clock_limit_seconds=1000, step_limit=1, scoring_input_capture=ScoringInputCaptureLimits(4096, 16384, 8))
    monkeypatch.setattr(development.VipDevelopmentBatch, "read", classmethod(lambda *a, **k: batch))
    monkeypatch.setattr(development.VipEohBatch, "read", classmethod(lambda *a, **k: generation))
    monkeypatch.setattr(development, "load_vip_parents", lambda *a, **k: [{"source": "fixture-not-executable", "identity": identity}])
    monkeypatch.setattr(development, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(development, "source_manifest", lambda *_: {})
    monkeypatch.setattr(development, "write_code_snapshot", lambda *a, **k: None)
    monkeypatch.setattr(development, "backend_info", lambda: {"native_path": None})
    monkeypatch.setattr(development, "compute_rules_hash", lambda *_: "fixture-no-rule-source-calculation")
    monkeypatch.setattr(development, "build_research_candidate_scorer", lambda _: SimpleNamespace(source="fixture-not-executable"))
    declarations = {label: PolicyDeclaration(label, "fixture") for label in ("A", "C", "H1", "H2", "H3", "M1", "M2", "M3")}
    def runtime(*_):
        policies = {"C": FixtureInnerPolicy(FixtureExecutor(), FixtureTypedView()), "A": object()}
        return SimpleNamespace(engine=object(), rules=object(), config=config, declarations=declarations,
            policy_metadata={"fixture_only": True}, baseline_policy_id="A", challenger_policy_id="C", policies_by_id=policies)
    monkeypatch.setattr(development, "build_vip_development_runtime", runtime)
    def synthetic_summary(*a, **k):
        # 故意提供非空哨兵，检查终态失败会同时清空两个池；不作效果断言。
        return {"estimate_natural_score_delta": 1.0, "positive_tail": ["fixture"], "negative_tail": [],
            "development_complete": True, "extra_failures": []}
    monkeypatch.setattr(development, "_pool_summary", synthetic_summary)
    interruption = KeyboardInterrupt("fixture run interrupted")
    secondary_armed = False
    original_write = development._write
    if failure == "interrupt_then_cost_io":
        def write_with_secondary(path, value):
            if secondary_armed and path.name == "costs.json":
                raise OSError("fixture terminal costs secondary failure")
            return original_write(path, value)
        monkeypatch.setattr(development, "_write", write_with_secondary)
    if failure == "close":
        class SyntheticCloseFailure(ScoringInputCapture):
            def finish(self):
                result = super().finish()
                return dict(result, terminal=dict(result["terminal"], terminal_valid=False, closed=False,
                    errors=["fixture gzip terminal close failure"]))
        monkeypatch.setattr(development, "ScoringInputCapture", SyntheticCloseFailure)
    async def runner(experiment, *, policies_by_id, **kwargs):
        nonlocal secondary_armed
        if failure == "score" and ":H" in experiment.match_id_prefix:
            policies_by_id["C"].inner.fixture_executor.exception = WorkloadExceeded("fixture score ceiling")
        if failure.startswith("interrupt"):
            secondary_armed = True
            policies_by_id["C"].inner.fixture_executor.exception = interruption
        await policies_by_id["C"].choose(request(), make_budget())
        return SimpleNamespace(results=(), match_records=(), excluded=())
    output = tmp_path / "fixture-output"
    if failure.startswith("interrupt"):
        with pytest.raises(KeyboardInterrupt) as caught:
            asyncio.run(development.run_vip_route_development(tmp_path / "fixture-batch.json", output, match_runner=runner))
        assert caught.value is interruption and not (output / "M").exists()
        assert not (output / "summary.json").exists()
        terminal = json.loads((output / "manifest.json").read_bytes())["scoring_input_capture"]["terminal_verification"]
        assert not terminal["terminal_valid"] and terminal["scoring_audit_failed_calls"] == 1
        assert terminal["pending_run_exception"].startswith("KeyboardInterrupt:")
        if failure == "interrupt_then_cost_io":
            assert any("再次失败" in note for note in interruption.__notes__)
            assert any("小收据落盘失败" in item for item in terminal["errors"])
        else:
            costs = json.loads((output / "costs.json").read_bytes())
            assert costs["entries"][0]["actual_started_table_instances"] == 0
            assert costs["entries"][0]["status"] == "interrupted_cost_retained"
        return
    result = asyncio.run(development.run_vip_route_development(tmp_path / "fixture-batch.json", output, match_runner=runner))
    assert result["source_kind"] == "mock" and result["status"] == "unfinished_or_invalid_development"
    assert result["timing_scope"] == "policy_choose_with_input_capture_observed_not_official_runtime"
    assert all(pool["estimate_natural_score_delta"] is None and not pool["development_complete"] for pool in result["pools"].values())
    assert all(pool["positive_tail"] == [] for pool in result["pools"].values())
    terminal = result["scoring_input_capture"]["terminal"]
    assert terminal["terminal_valid"] is False
    if failure == "score":
        assert terminal["storage_valid"] and terminal["scoring_audit_failed_calls"] == 4
    else:
        assert terminal["closed"] is False
    assert all(entry["actual_started_table_instances"] == 0 for entry in json.loads((output / "costs.json").read_bytes())["entries"])


@pytest.mark.parametrize("schema", ["vip-route-development-batch/1", "vip-route-development-batch/2"])
def test_public_batch_reader_keeps_historical_bytes_and_explicit_new_budget(tmp_path, monkeypatch, schema):
    """只验配置Interface；候选装载/行为核验为显式替身，无真实评分或规则。"""
    import hangma_bot.offline.vip_route_development as development
    files = {"generation.json": b"{}", "candidate/generation.json": b"{}",
        "candidate/candidate.py": b"fixture-not-executable", "probe.json": b"{}"}
    for name, raw in files.items():
        path = tmp_path / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(raw)
    sha = lambda name: hashlib.sha256(files[name]).hexdigest()
    data = {"schema": schema, "batch_id": "fixture-reader-only", "generation_batch_file": "generation.json",
        "generation_batch_sha256": sha("generation.json"), "candidate_package": "candidate",
        "candidate_generation_sha256": sha("candidate/generation.json"), "candidate_source_sha256": sha("candidate/candidate.py"),
        "behavior_probe_summary_file": "probe.json", "behavior_probe_summary_sha256": sha("probe.json"),
        "seeds": [{"root_id": "fixture-root", "seed": 0, "permutations": [[0,1,2,3],[1,2,3,0],[2,3,0,1],[3,0,1,2]]}],
        "pools": ["H", "M"], "rounds": 8, "initial_dealer_physical": 0, "initial_scores": [0]*4,
        "table_instance_limit": 16, "wall_clock_limit_seconds": 1, "step_limit": 1}
    if schema.endswith("/2"):
        data["scoring_input_capture"] = {"max_view_json_bytes": 4096, "max_total_json_bytes": 16384, "max_unique_views": 8}
        data["behavior_reference_policy"] = None  # 此测试行为验证为显式替身；真实/2另验。
        data["behavior_exploration"] = None
    batch_path = tmp_path / "batch.json"
    raw = json.dumps(data).encode()
    batch_path.write_bytes(raw)
    monkeypatch.setattr(development.VipEohBatch, "read", classmethod(lambda *a, **k: SimpleNamespace(route_limits=SimpleNamespace(max_expansions=8192))))
    monkeypatch.setattr(development, "load_vip_parents", lambda *a, **k: [{"source_sha256": sha("candidate/candidate.py"), "record_sha256": sha("candidate/generation.json")}])
    monkeypatch.setattr(development, "_require_complete_behavior_difference", lambda *a, **k: None)
    result = development.VipDevelopmentBatch.read(batch_path, allow_mock_behavior_fixture=True)
    assert result.raw == raw and batch_path.read_bytes() == raw
    assert (result.scoring_input_capture is None) == schema.endswith("/1")


def test_fresh_run_rejects_historical_batch_before_runtime_or_output(tmp_path, monkeypatch):
    import hangma_bot.offline.vip_route_development as development
    monkeypatch.setattr(development.VipDevelopmentBatch, "read", classmethod(lambda *a, **k: SimpleNamespace(scoring_input_capture=None)))
    def forbidden(*a, **k):
        raise AssertionError("旧batch不得进入新装配或评分")
    monkeypatch.setattr(development, "build_vip_development_runtime", forbidden)
    output = tmp_path / "never-created"
    with pytest.raises(ValueError, match="batch/1仅供历史读取"):
        asyncio.run(development.run_vip_route_development(tmp_path / "historical.json", output))
    assert not output.exists()
