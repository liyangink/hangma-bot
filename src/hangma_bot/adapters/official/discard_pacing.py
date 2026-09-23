"""普通弃牌的固定缓发计算；只用本机观察时刻与原动作截止。"""

from dataclasses import dataclass
from math import isfinite
from hangma_bot.application.contracts import DEFAULT_POST_NETWORK_RESERVE_SEC


MIN_OBSERVED_AGE_SEC = 1.0
POST_RESERVE_SEC = DEFAULT_POST_NETWORK_RESERVE_SEC + 0.20
SEND_SLACK_SEC = 0.10


@dataclass(frozen=True)
class DiscardPacing:
    """一次弃牌的固定等待目标；不重新计算窗口起点、不因等待反复延期。"""

    target_at_monotonic: float  # 本机单调秒；立即提交时等于本次检查时刻
    reason: str  # 审计用途：固定缓发或跳过原因，不改变策略选牌
    latest_send_at_monotonic: float | None = None  # 实际等待时收紧的发送截止；跳过时为空


def plan_discard_pacing(*, now: float, observed_at: float,
                        expires_lower_bound: float, latest_send: float) -> DiscardPacing:
    """正常弃牌在本机首次见到动作窗满1秒时提交。

    ``observed_at`` 是本机单调秒，实际摸牌不晚于此刻。安全截止不足
    时立即提交。绝不延长原动作截止；
    等待不占HTTP槽或state额度。
    """
    if not all(isfinite(value) for value in (
            now, observed_at, expires_lower_bound, latest_send)):
        return DiscardPacing(now, "invalid_timing")
    if observed_at > now or expires_lower_bound <= observed_at:
        return DiscardPacing(now, "invalid_timing")
    safe_latest = min(latest_send, expires_lower_bound - POST_RESERVE_SEC)
    baseline = observed_at + MIN_OBSERVED_AGE_SEC
    if baseline + SEND_SLACK_SEC >= safe_latest:
        return DiscardPacing(now, "insufficient_margin")
    if baseline <= now:
        return DiscardPacing(now, "target_age_reached")
    return DiscardPacing(baseline, "baseline", safe_latest)
