"""生产组合根按配置接通 SSE；关闭时保留原状态轮询。"""

import json
from types import SimpleNamespace

import pytest

import hangma_bot.bootstrap as bootstrap
from hangma_bot.application.auto_match_runtime import AutoMatchSettings
from hangma_bot.adapters.recording.redact import redact_json_line, redact_value


@pytest.mark.parametrize("mode", ['test_room', 'test_tournament', 'official_tournament', 'auto_match'])
@pytest.mark.parametrize("requested", [False, True])
@pytest.mark.parametrize("pacing", [False, True])
def test_production_assembly_uses_independent_sync_and_pacing(
    monkeypatch, tmp_path, mode, requested, pacing,
):
    captured = {}
    auto_match = mode == 'auto_match'

    def official_session(**kwargs):
        captured["session"] = kwargs
        return SimpleNamespace()

    def runtime(**kwargs):
        captured["runtime"] = kwargs
        return SimpleNamespace()

    # 在公开构造边界记录参数：不访问会话/运行时的私有实现，也不创建连接池。
    monkeypatch.setattr(bootstrap, "OfficialAutoMatchSession" if auto_match else "OfficialTournamentSession", official_session)
    monkeypatch.setattr(bootstrap, "AutoMatchRuntime" if auto_match else "ParticipantRuntime", runtime)
    config = bootstrap.runtime_config_from_mapping({
        "mode": mode,
        "base_url": "https://platform.invalid",
        "expected_tournament_id": "" if auto_match else "t1",
        "known_guide_version": 15,
        "token": "isolated-fixture-token",
        "token_kind": "test" if mode.startswith('test_') else "official",
        "audit_root": str(tmp_path),
        "sse_enabled": requested,
        "discard_pacing_enabled": pacing,
    })
    if auto_match:
        bootstrap.build_auto_match_runtime(config, settings=AutoMatchSettings())
    else:
        bootstrap.build_runtime(config)
    assert captured["session"]["sse_enabled"] is requested
    assert (captured["session"]["sse_budget"] is not None) is requested
    assert captured["session"]["discard_pacing_enabled"] is pacing
    manifest = captured["runtime"]["manifest_extra"]
    assert manifest["official_sync_mode"] == ("sse_only" if requested else "state")
    assert manifest["sse_requested"] is requested
    assert manifest["sse_effective"] is requested
    assert manifest["discard_pacing_enabled"] is pacing
    assert manifest["discard_pacing_profile"] == "fixed_1000"
    assert manifest["budget_policy_version"] == 'fixed-post-reserve-v1'
    assert manifest["post_network_reserve_sec"] == .1
    assert manifest["state_arrival_guard_sec"] == .05
    assert manifest["state_min_spacing_sec"] == pytest.approx(1 / 14.5)
    assert manifest["state_scheduler_version"] == "sse-stale-recovery-v8"
    # 清单走结构与 JSONL 两层脱敏；版本名必须在真实审计中仍可直接辨认。
    assert redact_value(manifest)["state_scheduler_version"] == "sse-stale-recovery-v8"
    assert json.loads(redact_json_line(json.dumps(manifest)))[
        "state_scheduler_version"] == "sse-stale-recovery-v8"
    policy = captured["runtime"]["budget_policy"]
    assert policy.build(100, 1, 101).latest_send_at_monotonic == pytest.approx(100.9)
    assert policy.build(100, 3, 103).latest_send_at_monotonic == pytest.approx(102.9)
