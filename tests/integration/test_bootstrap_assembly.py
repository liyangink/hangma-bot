"""组装层契约（C1）：配置校验、对象图装配、Token 掩码与审计目录布局。

全部通过 bootstrap 公开接口验证；不连接网络（默认官方会话只在关闭时
释放连接池，不发请求）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hangma_bot.adapters.recording import JsonlAuditSink
from hangma_bot.application.contracts import RuntimeMode
from hangma_bot.application.participant_runtime import ParticipantRuntime
from hangma_bot.bootstrap import (
    RuntimeConfig,
    TokenKind,
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


class TestAssembly:
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
