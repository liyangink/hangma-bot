"""动作门测试：在途互斥、模糊封锁、已响应与窗口迁移。"""
from __future__ import annotations

from hangma_bot.adapters.official.action_gate import ActionGate
from hangma_bot.kernel.actions import WindowKey, WindowPhase


def _key(trigger: int, phase: WindowPhase = WindowPhase.DRAW) -> WindowKey:
    return WindowKey(game_id="g", round_no=1, trigger_seq=trigger, phase=phase, seat=2)


def test_in_flight_blocks_second_enter() -> None:
    gate = ActionGate()
    allowed, _ = gate.try_enter(_key(101))
    assert allowed
    gate.enter()
    allowed, reason = gate.try_enter(_key(101))
    assert not allowed and reason == "in_flight_post"
    gate.leave()
    assert gate.try_enter(_key(101))[0]  # 离开后新窗口可进入


def test_accepted_window_never_reopened() -> None:
    gate = ActionGate()
    key = _key(101)
    gate.mark_accepted(key)
    allowed, reason = gate.try_enter(key)
    assert not allowed and reason == "window_already_finalized"


def test_ambiguous_block_persists_until_migration_proved() -> None:
    gate = ActionGate()
    blocked = _key(101)
    gate.block(blocked)
    # 同窗尝试：被 ambiguous 封锁拒绝
    allowed, reason = gate.try_enter(blocked)
    assert not allowed and reason == "ambiguous_window_blocked"
    # 权威状态仍是同窗：封锁保持
    gate.observe_authoritative_window(blocked)
    assert gate.blocked_window == blocked
    # 权威状态迁移到新窗口：诊断封锁解除，但同窗仍拒绝（零次追加）
    gate.observe_authoritative_window(_key(105, WindowPhase.RESPONSE_PENG))
    assert gate.blocked_window is None
    allowed, reason = gate.try_enter(blocked)
    assert not allowed and reason == "window_already_finalized"


def test_rejected_retryable_keeps_window_open() -> None:
    """409 可重试不封锁：同窗允许下一候选（门不介入，由会话层刷新确认）。"""

    gate = ActionGate()
    key = _key(101)
    gate.enter()
    gate.leave()
    assert gate.try_enter(key)[0]
