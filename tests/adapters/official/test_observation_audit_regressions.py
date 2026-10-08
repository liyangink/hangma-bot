"""2026-09-06 已确认缺陷的正式回归。

原始红色证据保存在 review/official-adapter；此文件加入默认门禁。仅调用模块公开方法；不联网。
官方事实基线：v15/2026-09-05；实测事件来自仓库 archived-rooms。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'tests/adapters/official'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import asyncio
import copy
import json
from pathlib import Path
import sys
from dataclasses import replace

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "tests/adapters/official")))
from _official_testkit import FakeClock, FakeTransport, TIMING, load_fixture
from hangma_bot.adapters.official.game import OfficialGameSession
from hangma_bot.adapters.official.scheduler import RequestScheduler
from hangma_bot.adapters.official.dto import parse_state_response
from hangma_bot.adapters.official.projector import public_event
from hangma_bot.application.contracts import ActionAttempt, ObservedActionWindow, SubmitAccepted
from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.kernel.actions import Pass
from hangma_bot.kernel.config import RuleConfig


def archived_events():
    """只读已脱敏官方赛后事件，不将隐藏摸牌用于线上输入。"""
    path = _project_file(_PROJECT_ROOT, ROOT / "tests/fixtures/hangma/archived-rooms/t_6c121bfda7e8_b0.json")
    return [event for block in json.loads(path.read_text())["blocks"] for event in block["events"]]


def test_real_official_empty_tile_pass_is_parseable():
    """真实 pass 的空 tile 是无牌，不应使整批事件解析失败。"""
    event = next(e for e in archived_events() if e["type"] == "pass")
    parsed = parse_state_response({"events": [event]})
    assert len(parsed.events) == 1 and parsed.events[0].tiles == ()


def test_real_official_chi_combination_survives_projection():
    """吃牌已公开三张组合应完整进入观察事件，不能只剩被吃牌。"""
    event = next(e for e in archived_events() if e["type"] == "chi")
    projected = public_event(parse_state_response({"events": [event]}).events[0])
    assert sorted(t.code for t in projected.tiles) == sorted(event["data"]["tiles"])


async def deliver(documents):
    """通过正式会话入口投递脚本化官方响应；返回全部首次可交付窗口。"""
    transport, clock = FakeTransport(), FakeClock()
    pending = list(documents)
    transport.handler = lambda **kw: (200, json.dumps(pending.pop(0)))
    async def pending_timer(seconds):
        # 注入未到期定时器；本文件中的事件立即返回，定时器应被会话取消。
        await asyncio.Future()
    session = OfficialGameSession(game_id="g_room1_batch1", transport=transport,
        scheduler=RequestScheduler(clock=clock.monotonic, poll_interval=0),
        timing=TIMING, monotonic_clock=clock.monotonic, wall_clock_unix_ms=clock.wall_ms,
        retry_sleep=pending_timer)
    return session, transport, clock


@pytest.mark.asyncio
@pytest.mark.parametrize('enabled', [False, True])
async def test_snapshot_refresh_preserves_gang_draw_and_room_hu_restriction(enabled):
    """刷新保留杠补来源，但非爆头有财胡只在房规开关关闭时允许。"""
    pre = load_fixture("state_response_snapshot_peng.json")
    pre["seq"] = 100
    hand = ["1w", "2w", "白", "4w", "5w", "6w", "7b", "8b", "9b", "东"]
    pre["snapshot"].update(seat=2, turn=1, responding_seats=[0, 2, 3],
        my_hand=hand + ["9t"] * 3, drawn_tile=None,
        last_discard={"seat": 1, "tile": "9t", "seq": 100},
        melds=[[], [], [], []], hand_counts=[13, 13, 13, 13],
        god={"baotou": False, "chain_count": 0, "catch_play": False})
    post = copy.deepcopy(pre)
    post["seq"] = 102
    post["snapshot"].update(phase="draw", turn=2, responding_seats=[],
        my_hand=hand + ["东"], drawn_tile="东", hand_counts=[13, 13, 11, 13],
        melds=[[], [], [{"kind": "gang", "tiles": ["9t"] * 4, "from_seat": 1}], []],
        god={"baotou": False, "chain_count": 1, "catch_play": False})
    events = {"events": [
        {"seq": 101, "type": "gang", "seat": 2, "tile": "9t", "data": {"kind": "ming"}},
        {"seq": 102, "type": "tile_drawn", "seat": 2, "tile": "东"},
    ]}
    session, _, _ = await deliver([pre, events, post])
    try:
        assert isinstance(await session.next_item(), ObservedActionWindow)
        window = await asyncio.wait_for(session.next_item(), 1)
        assert isinstance(window, ObservedActionWindow)
        rules = HangmaRules(RuleConfig(ruleset_version="audit-v18", base_score=1, you_cai_bi_kao=enabled))
        control = replace(window.observation, public_history=tuple(
            public_event(e) for e in parse_state_response(events).events))
        assert ("hu" in [c.action_key for c in rules.analyze(control).legal_candidates]) is (not enabled)
        assert window.observation.gang_draw is True
        analysis = rules.analyze(window.observation)
        assert ("hu" in [c.action_key for c in analysis.legal_candidates]) is (not enabled), (
            window.observation.public_history, analysis.issues)
    finally:
        await session.aclose("audit_done")


@pytest.mark.asyncio
async def test_incremental_draw_updates_baotou_for_fourth_white():
    """v23：摸前任意听，增量摸第四白仍须保留爆头。"""
    pre = load_fixture("state_response_snapshot_draw.json")
    pre["seq"] = 100
    pre["snapshot"].update(turn=1, drawn_tile=None, responding_seats=[],
        my_hand=["1w", "2w", "3w", "4w", "5w", "6w", "7b", "8b", "9b", "东", "白", "白", "白"],
        melds=[[], [], [], []], hand_counts=[13, 13, 13, 13],
        god={"baotou": True, "chain_count": 0, "catch_play": False})
    # 基础快照处于前家响应结束后的边界；这里只注入本人的可见摸牌。
    pre["snapshot"].update(phase="response_chi", turn=1, responding_seats=[2])
    event = {"events": [{"seq": 101, "type": "tile_drawn", "seat": 2, "tile": "白"}]}
    session, _, _ = await deliver([pre, event])
    try:
        await session.next_item()
        window = await asyncio.wait_for(session.next_item(), 1)
        assert isinstance(window, ObservedActionWindow)
        assert window.observation.rule_state.baotou is True
    finally:
        await session.aclose("audit_done")


@pytest.mark.asyncio
async def test_response_budget_uses_remaining_official_deadline():
    """收到响应快照时只剩 100ms，交付预算不能重新给完整 1 秒。"""
    pre = load_fixture("state_response_snapshot_peng.json")
    pre["snapshot"]["window_deadline_ms"] = FakeClock().wall_ms() + 100
    session, _, clock = await deliver([pre])
    try:
        window = await session.next_item()
        assert isinstance(window, ObservedActionWindow)
        budget = BudgetPolicy().build(window.received_at_monotonic, window.timeout_seconds, window.expires_at_monotonic)
        assert budget.latest_send_at_monotonic <= clock.monotonic() + 0.1
    finally:
        await session.aclose("audit_done")


@pytest.mark.asyncio
async def test_new_discard_snapshot_clears_previous_pass():
    """同一单局内缺口快照已证明是新弃牌，旧响应周期的 pass 不应继续屏蔽。"""
    pre = load_fixture("state_response_snapshot_peng.json")
    pre["snapshot"]["phase"] = "response_chi"  # 真实发送pass只发生在吃阶段
    later = copy.deepcopy(pre)
    later.update(seq=500, gap=True)
    later["snapshot"].update(last_discard={"seat": 1, "tile": "6w", "seq": 500})
    later["snapshot"]["discards"][1].append("6w")
    finished = copy.deepcopy(later)
    finished.update(seq=600, finished=True)
    finished["snapshot"]["phase"] = "finished"
    session, _, clock = await deliver([pre, {}, later, finished])
    try:
        window = await session.next_item()
        outcome = await session.submit(ActionAttempt(decision_id="audit-pass", attempt_no=1,
            plan_revision=1, window_key=window.window_key,
            based_on_authoritative_seq=window.authoritative_seq, action=Pass(), action_key="pass",
            latest_send_at_monotonic=clock.monotonic() + 0.5))
        assert isinstance(outcome, SubmitAccepted)
        next_window = await asyncio.wait_for(session.next_item(), 1)
        assert isinstance(next_window, ObservedActionWindow), next_window
        assert next_window.window_key.trigger_seq == 500
    finally:
        await session.aclose("audit_done")
