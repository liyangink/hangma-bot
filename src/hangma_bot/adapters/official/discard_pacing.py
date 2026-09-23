"""普通弃牌的短暂缓发计算；只用本机观察时刻和共享查询队列，不访问外部状态。"""

from dataclasses import dataclass
from math import isfinite
from hangma_bot.application.contracts import DEFAULT_POST_NETWORK_RESERVE_SEC


MIN_OBSERVED_AGE_SEC = 0.5
MAX_OBSERVED_AGE_SEC = 1.0
POST_RESERVE_SEC = DEFAULT_POST_NETWORK_RESERVE_SEC + 0.20
SEND_SLACK_SEC = 0.10


@dataclass(frozen=True)
class DiscardPacing:
    """一次弃牌的固定等待目标；不重新计算窗口起点、不因等待反复延期。"""

    target_at_monotonic: float  # 本机单调秒；立即提交时等于本次检查时刻
    reason: str  # 审计用途：压力补时或跳过原因，不改变策略选牌
    latest_send_at_monotonic: float | None = None  # 实际等待时收紧的发送截止；跳过时为空


def plan_discard_pacing(*, now: float, observed_at: float, backlog_delay_sec: float,
                        expires_lower_bound: float, latest_send: float) -> DiscardPacing:
    """正常弃牌至少距本机见到动作窗0.5秒；拥堵可补至1秒。

    ``observed_at`` 是本机单调秒，实际摸牌不晚于此刻。队列工作量只
    决定额外等待，最多0.5秒；安全截止不足时先退回0.5秒，再退回立即
    提交。绝不延长原动作截止；等待不占HTTP槽或state额度。
    """
    if not all(isfinite(value) for value in (
            now, observed_at, backlog_delay_sec, expires_lower_bound, latest_send)):
        return DiscardPacing(now, "invalid_timing")
    if observed_at > now or backlog_delay_sec < 0 or expires_lower_bound <= observed_at:
        return DiscardPacing(now, "invalid_timing")
    safe_latest = min(latest_send, expires_lower_bound - POST_RESERVE_SEC)
    baseline = observed_at + MIN_OBSERVED_AGE_SEC
    if baseline + SEND_SLACK_SEC >= safe_latest:
        return DiscardPacing(now, "insufficient_margin")
    target = observed_at + min(MAX_OBSERVED_AGE_SEC,
                               MIN_OBSERVED_AGE_SEC + backlog_delay_sec)
    reason = "state_backlog" if target > baseline else "baseline"
    if target + SEND_SLACK_SEC >= safe_latest:
        target, reason = baseline, "backlog_margin_fallback"
    if target <= now:
        return DiscardPacing(now, "target_age_reached")
    return DiscardPacing(target, reason, safe_latest)
