"""每场一个的动作门：在途互斥、模糊封锁与已响应集合（官方适配器内部实现）。

安全不变量（接口协议 §5）：

- 同一场任意时刻最多一个在途动作 POST；
- SubmitAmbiguous 后相同 WindowKey 零次追加提交，直到权威事件证明窗口迁移；
- 官方明确接收（SubmitAccepted）或窗口关闭后，同窗不再接受任何提交；
- SubmitRejectedRetryable 不封锁窗口：官方确认未执行，同窗允许下一候选。
"""

from __future__ import annotations

from typing import Optional, Tuple

from hangma_bot.kernel.actions import WindowKey


class ActionGate:
    """单场提交门；由持有该场锁的异步任务独占访问。"""

    def __init__(self) -> None:
        self._in_flight = False
        self._responded = set()  # 已终局处理的窗口键（accepted/ambiguous/closed）
        self._blocked = None  # Optional[WindowKey]：模糊结果封锁中的窗口

    @property
    def in_flight(self) -> bool:
        return self._in_flight

    @property
    def blocked_window(self) -> Optional[WindowKey]:
        return self._blocked

    def is_finalized(self, window_key: WindowKey) -> bool:
        """窗口是否已被动作门终结（accepted/ambiguous/closed）。

        会话用它决定活窗是否可重投：终结窗口不再交付，未终结窗口
        在监督重启或 409 刷新后允许 at-least-once 重取。
        """

        return window_key in self._responded

    def try_enter(self, window_key: WindowKey) -> Tuple[bool, str]:
        """尝试进入提交区；返回 (是否允许, 拒绝原因)。

        拒绝时调用方应返回 SubmitNotSent，不得重试同一请求。
        """

        if self._in_flight:
            return False, "in_flight_post"
        if window_key in self._responded:
            if self._blocked is not None and window_key == self._blocked:
                return False, "ambiguous_window_blocked"
            return False, "window_already_finalized"
        return True, ""

    def enter(self) -> None:
        """try_enter 成功后标记在途。"""

        self._in_flight = True

    def leave(self) -> None:
        """提交请求结束（无论结果）后释放在途标志。"""

        self._in_flight = False

    def mark_accepted(self, window_key: WindowKey) -> None:
        """官方明确接收：该窗口完成，禁止任何追加提交。"""

        self._responded.add(window_key)

    def mark_closed(self, window_key: WindowKey) -> None:
        """窗口已权威关闭：同窗不再接受提交。"""

        self._responded.add(window_key)

    def block(self, window_key: WindowKey) -> None:
        """结果模糊：封锁同窗，直到权威事件证明窗口迁移。"""

        self._responded.add(window_key)
        self._blocked = window_key

    def observe_authoritative_window(self, current: Optional[WindowKey]) -> None:
        """每次权威快照归并后调用：窗口已迁移时解除模糊封锁标记。

        解除的只是诊断标记；该窗口仍在已响应集合中，
        "同窗零次追加提交"不变量始终成立。
        """

        if self._blocked is not None and current != self._blocked:
            self._blocked = None

