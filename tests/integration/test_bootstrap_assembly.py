"""组装层契约（C1）：配置校验、对象图装配、Token 掩码与审计目录布局。

全部通过 bootstrap 公开接口验证；不连接网络（默认官方会话只在关闭时
释放连接池，不发请求）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hangma_bot.adapters.recording import JsonlAuditSink
from hangma_bot.application.auto_match_runtime import AutoMatchRuntime, AutoMatchSettings
from hangma_bot.application.contracts import RuntimeMode
from hangma_bot.application.participant_runtime import ParticipantRuntime
from hangma_bot.bootstrap import (
    RuntimeConfig,
    TokenKind,
    build_auto_match_runtime,
    build_runtime,
    runtime_config_from_mapping,
)
from hangma_bot.policy.safe_fallback import SafeFallbackPolicy
from hangma_bot.policy.weighted_heuristic import WeightedHeuristicPolicy

SECRET = "secret-token-0123456789abcdef0123456789abcdef"


def _valid(**overrides) -> dict:
    data = {
        "mode": "test_room",
        "base_url": "https://platform.invalid",
        "expected_tournament_id": "t1",
        "known_guide_version": 8,
        "token": SECRET,
        "token_kind": "test",
        "audit_root": "/tmp/audit",
    }
    data.update(overrides)
    return data


class TestConfigValidation:
    def test_valid_mapping_builds_config(self):
        config = runtime_config_from_mapping(_valid(insecure_hosts=["h1.internal"]))
        assert config.mode is RuntimeMode.TEST_ROOM
        assert config.base_url == "https://platform.invalid"
        assert config.expected_tournament_id == "t1"
        assert config.known_guide_version == 8
        assert config.token == SECRET
        assert config.token_kind is TokenKind.TEST
        assert config.audit_root == Path("/tmp/audit")
        assert config.strategy == "weighted_heuristic"
        assert config.insecure_hosts == frozenset({"h1.internal"})

    def test_token_env_resolution(self):
        data = _valid()
        del data["token"]
        data["token_env"] = "HM_TEST_TOKEN"
        config = runtime_config_from_mapping(
            data, environ={"HM_TEST_TOKEN": "env-secret-abc123456789"}
        )
        assert config.token == "env-secret-abc123456789"

    def test_missing_token_env_rejected_without_leaking_value(self):
        data = _valid()
        del data["token"]
        data["token_env"] = "HM_MISSING"
        with pytest.raises(ValueError, match="HM_MISSING"):
            runtime_config_from_mapping(data, environ={})

    def test_token_and_env_conflict_rejected(self):
        with pytest.raises(ValueError, match="二选一"):
            runtime_config_from_mapping(_valid(token_env="HM_X"))

    def test_unknown_field_rejected(self):
        with pytest.raises(ValueError, match="未知字段"):
            runtime_config_from_mapping(_valid(tokken=SECRET))

    def test_mode_token_kind_mismatch_rejected(self):
        with pytest.raises(ValueError, match="不匹配"):
            runtime_config_from_mapping(
                _valid(mode="official_tournament", token_kind="test")
            )
        with pytest.raises(ValueError, match="不匹配"):
            runtime_config_from_mapping(_valid(mode="test_room", token_kind="official"))

    def test_bad_base_url_rejected(self):
        with pytest.raises(ValueError, match="http"):
            runtime_config_from_mapping(_valid(base_url="platform.invalid"))

    def test_unknown_strategy_rejected(self):
        with pytest.raises(ValueError, match="策略"):
            runtime_config_from_mapping(_valid(strategy="neural_super_bot"))

    def test_repr_masks_token(self):
        config = runtime_config_from_mapping(_valid())
        assert "<redacted>" in repr(config)
        assert SECRET not in repr(config)
        assert SECRET not in str(config)

    def test_audit_raw_gzip_defaults_off(self):
        """F-08：新配置项默认关闭/默认 32MB，旧配置零改动兼容。"""

        config = runtime_config_from_mapping(_valid())
        assert config.audit_raw_gzip is False
        assert config.audit_raw_rotate_bytes == 32 * 1024 * 1024

    def test_audit_raw_gzip_parsed(self):
        config = runtime_config_from_mapping(
            _valid(audit_raw_gzip=True, audit_raw_rotate_bytes=4096)
        )
        assert config.audit_raw_gzip is True
        assert config.audit_raw_rotate_bytes == 4096

    def test_audit_raw_gzip_type_rejected(self):
        with pytest.raises(ValueError, match="audit_raw_gzip"):
            runtime_config_from_mapping(_valid(audit_raw_gzip="true"))
        with pytest.raises(ValueError, match="audit_raw_rotate_bytes"):
            runtime_config_from_mapping(_valid(audit_raw_rotate_bytes=0))

    def test_source_namespace_default_and_override(self):
        config = runtime_config_from_mapping(_valid())
        assert config.source_namespace == "hangma-official"
        custom = runtime_config_from_mapping(_valid(source_namespace="hangma-test-internal"))
        assert custom.source_namespace == "hangma-test-internal"

    def test_source_namespace_empty_rejected(self):
        with pytest.raises(ValueError, match="source_namespace"):
            runtime_config_from_mapping(_valid(source_namespace=""))


class TestAssembly:
    def test_probe_strategy_is_explicitly_assembled_without_white_guard(self, tmp_path):
        from hangma_bot.policy import CatchPlayProbePolicy, ComparableHeuristicPolicyV2

        config = runtime_config_from_mapping(_valid(
            audit_root=str(tmp_path), strategy="catch_play_probe",
        ))
        assembled = build_runtime(config, session_factory=lambda: _StubSession())
        assert isinstance(assembled.policy, CatchPlayProbePolicy)
        assert isinstance(assembled.policy.base_policy, ComparableHeuristicPolicyV2)

    def test_build_runtime_object_graph(self, tmp_path):
        config = runtime_config_from_mapping(_valid(audit_root=str(tmp_path)))
        assembled = build_runtime(
            config,
            session_factory=lambda: _StubSession(),
        )
        assert isinstance(assembled.runtime, ParticipantRuntime)
        assert isinstance(assembled.sink, JsonlAuditSink)
        assert isinstance(assembled.policy, WeightedHeuristicPolicy)
        # run_id 在组装期固定：运行时与审计目录一致。
        assert assembled.sink.run_dir == tmp_path / "runs" / assembled.run_id
        assert assembled.config is config
        assert SECRET not in repr(assembled)

    def test_strategy_selection(self, tmp_path):
        config = runtime_config_from_mapping(
            _valid(audit_root=str(tmp_path), strategy="safe_fallback")
        )
        assembled = build_runtime(config, session_factory=lambda: _StubSession())
        assert isinstance(assembled.policy, SafeFallbackPolicy)

    def test_strategy_selection_claim_if_legal(self, tmp_path):
        """claim_if_legal 经 bootstrap 可配置实例化（官方测试房验收冒烟）。"""

        from hangma_bot.policy.claim_if_legal import ClaimIfLegalPolicy
        from hangma_bot.policy.legacy_pass import LegacyClaimIfLegalPolicy

        config = runtime_config_from_mapping(
            _valid(audit_root=str(tmp_path), strategy="claim_if_legal")
        )
        assembled = build_runtime(config, session_factory=lambda: _StubSession())
        assert isinstance(assembled.policy, ClaimIfLegalPolicy)
        assert isinstance(assembled.policy, LegacyClaimIfLegalPolicy)
        # 默认策略仍为 weighted_heuristic，claim_if_legal 只按配置启用
        default = runtime_config_from_mapping(_valid(audit_root=str(tmp_path)))
        assert isinstance(
            build_runtime(default, session_factory=lambda: _StubSession()).policy,
            WeightedHeuristicPolicy,
        )

    def test_policy_factory_override(self, tmp_path):
        config = runtime_config_from_mapping(_valid(audit_root=str(tmp_path)))
        marker = _StubPolicy()
        assembled = build_runtime(
            config,
            session_factory=lambda: _StubSession(),
            policy_factory=lambda: marker,
        )
        assert assembled.policy is marker

    async def test_default_official_session_builds_and_closes(self, tmp_path):
        """默认组装路径创建官方会话与连接池；关闭释放资源，不发请求。"""

        config = runtime_config_from_mapping(_valid(audit_root=str(tmp_path)))
        assembled = build_runtime(config)
        assert isinstance(assembled.policy, WeightedHeuristicPolicy)
        await assembled.session.aclose()


class TestAutoMatchAssembly:
    """AUTO_MATCH 组合根（parallel-v1 §3.3 受控扩展）：只服务自动匹配模式。"""

    def _auto_config(self, tmp_path, **overrides) -> RuntimeConfig:
        data = {
            "mode": "auto_match",
            "base_url": "https://platform.invalid",
            "known_guide_version": 15,
            "token": SECRET,
            "token_kind": "official",
            "audit_root": str(tmp_path),
        }
        data.update(overrides)
        return runtime_config_from_mapping(data)

    def test_rejects_non_auto_match_mode(self, tmp_path):
        config = runtime_config_from_mapping(_valid(audit_root=str(tmp_path)))
        with pytest.raises(ValueError, match="auto_match"):
            build_auto_match_runtime(config, AutoMatchSettings())

    def test_empty_target_allowed_only_for_auto_match(self, tmp_path):
        config = self._auto_config(tmp_path, expected_tournament_id="")
        assert config.expected_tournament_id == ""
        assembled = build_auto_match_runtime(
            config, AutoMatchSettings(), session_factory=lambda: _StubSession()
        )
        assert isinstance(assembled.runtime, AutoMatchRuntime)

    def test_object_graph(self, tmp_path):
        config = self._auto_config(tmp_path)
        settings = AutoMatchSettings(declared_max_games=10, declared_rounds=8)
        assembled = build_auto_match_runtime(
            config, settings, session_factory=lambda: _StubSession()
        )
        assert isinstance(assembled.runtime, AutoMatchRuntime)
        assert isinstance(assembled.sink, JsonlAuditSink)
        assert isinstance(assembled.policy, WeightedHeuristicPolicy)
        assert assembled.settings is settings
        # run_id 在组装期固定：运行时与审计目录一致。
        assert assembled.sink.run_dir == tmp_path / "runs" / assembled.run_id
        assert assembled.config is config
        assert SECRET not in repr(assembled)

    async def test_default_auto_match_session_builds_and_closes(self, tmp_path):
        """默认组装路径创建自动匹配会话与连接池；关闭释放资源，不发请求。"""

        config = self._auto_config(tmp_path)
        assembled = build_auto_match_runtime(config, AutoMatchSettings())
        assert isinstance(assembled.runtime, AutoMatchRuntime)
        await assembled.session.aclose()


class TestAuditRawGzipWiring:
    """F-08 回归：RuntimeConfig 的 gzip 开关真实透传到组合根的 JsonlAuditSink。"""

    async def test_raw_gzip_wired_into_assembled_sink(self, tmp_path):
        from hangma_bot.adapters.recording import build_state_response_payload
        from hangma_bot.application.contracts import (
            AuditContext,
            AuditKind,
            AuditRecord,
        )

        config = runtime_config_from_mapping(
            _valid(audit_root=str(tmp_path), audit_raw_gzip=True, audit_raw_rotate_bytes=4096)
        )
        assembled = build_runtime(config, session_factory=lambda: _StubSession())
        record = AuditRecord(
            schema_version=1,
            kind=AuditKind.RAW_PROTOCOL_STATE,
            context=AuditContext(
                run_id=assembled.run_id,
                tournament_id="t1",
                participant_id="P1",
                game_id="G1",
            ),
            wall_time_unix_ms=1_750_000_000_000,
            monotonic_ns=1_750_000_000_000_000_000,
            payload=build_state_response_payload(
                endpoint="GET /api/games/G1/state",
                http_status=200,
                seq_requested=0,
                seq_observed=1,
                request_no=1,
                raw='{"seq": 1, "snapshot": {}}',
            ),
        )
        assert assembled.sink.emit(record).queued
        await assembled.sink.aclose(timeout_seconds=5.0)
        raw_dir = assembled.sink.run_dir / "participants" / "P1" / "raw"
        gz_segments = list(raw_dir.glob("*.jsonl.gz"))
        assert len(gz_segments) == 1  # gzip 接线生效：落盘为压缩段而非 .jsonl

    async def test_raw_gzip_off_keeps_plain_jsonl(self, tmp_path):
        from hangma_bot.adapters.recording import build_state_response_payload
        from hangma_bot.application.contracts import (
            AuditContext,
            AuditKind,
            AuditRecord,
        )

        config = runtime_config_from_mapping(_valid(audit_root=str(tmp_path)))
        assert config.audit_raw_gzip is False
        assembled = build_runtime(config, session_factory=lambda: _StubSession())
        record = AuditRecord(
            schema_version=1,
            kind=AuditKind.RAW_PROTOCOL_STATE,
            context=AuditContext(
                run_id=assembled.run_id,
                tournament_id="t1",
                participant_id="P1",
                game_id="G1",
            ),
            wall_time_unix_ms=1_750_000_000_000,
            monotonic_ns=1_750_000_000_000_000_000,
            payload=build_state_response_payload(
                endpoint="GET /api/games/G1/state",
                http_status=200,
                seq_requested=0,
                seq_observed=1,
                request_no=1,
                raw='{"seq": 1, "snapshot": {}}',
            ),
        )
        assert assembled.sink.emit(record).queued
        await assembled.sink.aclose(timeout_seconds=5.0)
        raw_dir = assembled.sink.run_dir / "participants" / "P1" / "raw"
        assert list(raw_dir.glob("*.jsonl.gz")) == []
        assert (raw_dir / "G1.jsonl").exists()


def test_version_fact_helpers(tmp_path):
    """审计版本事实助手：git 状态与策略生效权重快照（2026-09-06 集成）。"""

    from hangma_bot.bootstrap import _effective_weights_snapshot, _git_state
    from hangma_bot.policy.weighted_heuristic import WeightedHeuristicPolicy

    commit, dirty = _git_state()
    assert isinstance(commit, str) and len(commit) == 40
    assert isinstance(dirty, bool)

    snapshot = _effective_weights_snapshot(WeightedHeuristicPolicy())
    assert snapshot is not None
    assert snapshot["win_now"] == 1000.0
    assert snapshot["shanten_step"] == 100.0
    assert _effective_weights_snapshot(SafeFallbackPolicy()) is None


class _StubSession:
    """最小端口占位：只验证组装接线，不运行任何生命周期。"""

    async def initialize(self, target):
        raise NotImplementedError

    async def register(self):
        raise NotImplementedError

    async def ready(self, expected_stage):
        raise NotImplementedError

    async def next_update(self):
        raise NotImplementedError

    def open_game(self, game_id):
        raise NotImplementedError

    async def aclose(self):
        return None


class _StubPolicy:
    async def choose(self, request, budget):
        raise NotImplementedError


if __name__ == "__main__":
    pytest.main([__file__])


def test_v1_is_opt_in_and_v0_default_is_preserved(tmp_path):
    """同一运行框架分别装配两个实现，不通过覆盖默认工厂切换策略。"""
    from hangma_bot.policy import ReliableHeuristicPolicyV1
    from hangma_bot.policy.legacy_pass import LegacyWeightedHeuristicPolicy
    v1 = build_runtime(runtime_config_from_mapping(_valid(
        audit_root=str(tmp_path/'v1'), strategy='weighted_heuristic_v1',
    )), session_factory=lambda: _StubSession())
    v0 = build_runtime(runtime_config_from_mapping(_valid(
        audit_root=str(tmp_path/'v0'),
    )), session_factory=lambda: _StubSession())
    assert isinstance(v1.policy, ReliableHeuristicPolicyV1)
    assert isinstance(v0.policy, WeightedHeuristicPolicy)
    assert isinstance(v0.policy, LegacyWeightedHeuristicPolicy)
    assert v1.sink.run_dir != v0.sink.run_dir


def test_v2_can_be_selected_without_changing_default(tmp_path):
    """V2 通过原策略名配置接入组合根，默认仍为 V0。"""
    from hangma_bot.policy import ComparableHeuristicPolicyV2
    runtime=build_runtime(runtime_config_from_mapping(_valid(
        audit_root=str(tmp_path/'v2'),strategy='weighted_heuristic_v2',
    )),session_factory=lambda:_StubSession())
    assert isinstance(runtime.policy,ComparableHeuristicPolicyV2)
    assert runtime_config_from_mapping(_valid()).strategy=='weighted_heuristic'


def test_white_guard_is_explicitly_assembled_with_v2_weights(tmp_path):
    """新候选在统一组合根接线，记录底层实际权重，旧 V2 仍可单独选择。"""
    from hangma_bot.bootstrap import DEFAULT_RULESET_VERSION, _effective_weights_snapshot
    from hangma_bot.policy import ComparableHeuristicPolicyV2, WhiteDiscardGuardPolicy

    runtime = build_runtime(runtime_config_from_mapping(_valid(
        audit_root=str(tmp_path / "guard"), strategy="weighted_heuristic_v2_white_guard",
    )), session_factory=lambda: _StubSession())

    assert isinstance(runtime.policy, WhiteDiscardGuardPolicy)
    assert isinstance(runtime.policy.base_policy, ComparableHeuristicPolicyV2)
    assert _effective_weights_snapshot(runtime.policy) == _effective_weights_snapshot(ComparableHeuristicPolicyV2())
    assert DEFAULT_RULESET_VERSION == "hangma-mvp-v10-public-counts"
    assert runtime_config_from_mapping(_valid()).strategy == "weighted_heuristic"
