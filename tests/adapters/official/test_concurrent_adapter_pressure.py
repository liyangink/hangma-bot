"""十场生产会话共用默认额度的组合压力测试，不运行桌赛或访问网络。"""

import pytest

from _concurrent_adapter_harness import run_scenario, verify_safety
from test_default_state_budget import GAMES


@pytest.mark.parametrize("latency,stagger", [(.04, 0), (.04, .025), (.15, 0), (.15, .025)])
async def test_ten_real_sessions_mix_draw_chi_recovery_and_action_conflict(monkeypatch, latency, stagger):
    server, audit, outcomes = await run_scenario(monkeypatch, latency=latency, stagger=stagger)
    verify_safety(server, audit)
    assert len(server.accepted) == 9
    assert sum(r[1] == "chi" for r in server.accepted) == 6
    assert server.cancelled, "必须实际触发边界取消，不能只让十场各查询一次"
    assert {f[1] for f in server.faults} == {"gap", "409"}
    paced = [r for r in audit.records if r.payload.get("discard_pacing_status") == "scheduled"]
    # 三场普通弃牌（两场增量摸牌、一场断序恢复）均可按首次见窗缓发；
    # 缓发不再以共享 state 用量达到 10 为前提。
    assert len(paced) <= 3
    assert {r.context.game_id for r in paced} <= {GAMES[0], GAMES[1], GAMES[9]}
    assert all(r.payload["target_at_monotonic"] > r.payload["started_at_monotonic"]
               for r in paced)
    assert all(any(e["game"] == r.context.game_id and e["method"] == "POST"
                   and e["start"] >= r.payload["target_at_monotonic"] - .02
                   for e in server.exchanges) for r in paced), "已调度缓发不得提前发送本场POST"


async def test_ten_sessions_keep_chi_windows_while_one_429_retries(monkeypatch):
    server, audit, outcomes = await run_scenario(monkeypatch, cooldown=True)
    verify_safety(server, audit)
    expired = [r for r in audit.records if r.payload.get("state_query_cancel_reason") == "expired_window_purpose"]
    assert not expired, "其他桌不能因被拒请求的 Retry-After 而错过原吃窗"
    assert sum(row[1] == "chi" for row in server.accepted) == 6
    assert sum(row[1] == "discard" for row in server.accepted) == 3
    rate_limited_at = next(at for _, kind, at in server.faults if kind == "429")
    during_retry = [e for e in server.exchanges if e["method"] == "GET"
                    and rate_limited_at + 1e-9 < e["start"] < server.cooldown_until - 1e-9]
    assert during_retry and all(e["game"] != GAMES[9] for e in during_retry)
    assert any(e["game"] == GAMES[9] and e["method"] == "GET"
               and e["start"] >= server.cooldown_until - 1e-9 for e in server.exchanges)


async def test_ambiguous_post_stays_blocked_while_other_nine_games_progress(monkeypatch):
    server, audit, outcomes = await run_scenario(monkeypatch, ambiguous=True)
    verify_safety(server, audit)
    assert server.posts[GAMES[2]] == 1
    assert any("SubmitAmbiguous" in row for row in outcomes[GAMES[2]])
    assert len(server.accepted) == 9


async def test_slow_chi_read_times_out_then_other_games_and_current_window_continue(monkeypatch):
    server, audit, outcomes = await run_scenario(monkeypatch, slow_boundary=True)
    verify_safety(server, audit)
    assert len(server.timeouts) == 1 and server.timeouts[0][0] == GAMES[3]
    expired = [r for r in audit.records if r.payload.get("state_query_cancel_reason") == "expired_window_purpose"]
    assert len(expired) == 1 and expired[0].context.game_id == GAMES[3]
    assert sum(row[1] == "chi" for row in server.accepted) == 5
    assert sum(row[1] == "discard" for row in server.accepted) == 4
    timeout_at = server.timeouts[0][1]
    read = next(e for e in server.exchanges if e["game"] == GAMES[3] and e["budget"] is not None)
    assert timeout_at == pytest.approx(read["start"] + read["budget"])


async def test_only_our_discard_pacing_changes_while_opponent_windows_stay_fixed(monkeypatch):
    pairs = []
    for enabled in (False, True):
        with monkeypatch.context() as isolated:
            server, audit, outcomes = await run_scenario(isolated, pacing=enabled)
        verify_safety(server, audit)
        pairs.append(server)
        scheduled = [r for r in audit.records if r.payload.get("discard_pacing_status") == "scheduled"]
        assert len(scheduled) <= (3 if enabled else 0)
        assert {r.context.game_id for r in scheduled} <= {GAMES[0], GAMES[1], GAMES[9]}
    for game in GAMES[:2]:
        without = next(row[2] for row in pairs[0].accepted if row[0] == game)
        with_pacing = next(row[2] for row in pairs[1].accepted if row[0] == game)
        assert with_pacing >= without - .02, "缓发开关不能显著提前本方弃牌"
    assert pairs[0].epochs == pairs[1].epochs
    assert pairs[0].draw_at == pairs[1].draw_at
    # 对手推动的六场响应窗口和交付轨迹不随我方开关变慢；这里不模拟
    # 我方弃牌之后的完整续打，因此不能把安全对照称为缓发收益证明。
    assert [w for w in pairs[0].windows if w["game"] in GAMES[3:9]] == [
        w for w in pairs[1].windows if w["game"] in GAMES[3:9]]
