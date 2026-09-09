"""普通弃牌的短暂缓发计算；只用本机已知时间和用户查询用量，不访问外部状态。"""

from dataclasses import dataclass
from math import isfinite
from hangma_bot.application.contracts import DEFAULT_POST_NETWORK_RESERVE_SEC


STATE_PRESSURE_THRESHOLD = 10
TARGET_DRAW_AGE_SEC = 1.0
POST_RESERVE_SEC = DEFAULT_POST_NETWORK_RESERVE_SEC + 0.20
SEND_SLACK_SEC = 0.10


@dataclass(frozen=True)
class DiscardPacing:
    """一次弃牌的固定等待目标；不重新计算窗口起点、不因等待反复延期。"""

    target_at_monotonic: float  # 本机单调秒；立即提交时等于本次检查时刻
    reason: str  # 审计用途：压力补时或跳过原因，不改变策略选牌
    latest_send_at_monotonic: float | None = None  # 实际等待时收紧的发送截止；跳过时为空


def plan_discard_pacing(*, now: float, state_used: int, start_lower_bound: float,
                        expires_lower_bound: float, latest_send: float) -> DiscardPacing:
    """有压力且能完整补到保守起点后1秒才等待，否则立即走原提交路径。

    输入时间均为本机单调秒。起点/截止来自会话已验证的摸牌增量时序，
    可能只是保守下界，不要求毫秒精确；调用方负责排除快照恢复与特殊动作。
    不消费查询额度，不延长应用层原始latest_send，并为唤醒和POST留余量。
    """
    if state_used < STATE_PRESSURE_THRESHOLD:
        return DiscardPacing(now, "quota_available")
    if not all(isfinite(value) for value in (now, start_lower_bound, expires_lower_bound, latest_send)):
        return DiscardPacing(now, "invalid_timing")
    if start_lower_bound > now or expires_lower_bound <= start_lower_bound:
        return DiscardPacing(now, "invalid_timing")
    target = start_lower_bound + TARGET_DRAW_AGE_SEC
    if target <= now:
        return DiscardPacing(now, "target_age_reached")
    safe_latest = min(latest_send, expires_lower_bound - POST_RESERVE_SEC)
    if target + SEND_SLACK_SEC >= safe_latest:
        return DiscardPacing(now, "insufficient_margin")
    return DiscardPacing(target, "state_pressure", safe_latest)
