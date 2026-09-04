"""运行时审计标识生成；全部标识只在本机审计目录内有意义。

关联键要求见接口协议第 7 节：run_id / decision_id / stage_attempt_id
分别在不同层级生成，均不发送给官方平台。
"""

from __future__ import annotations

import uuid
from typing import Protocol

from hangma_bot.kernel.actions import WindowKey


class IdGenerator(Protocol):
    """审计标识的唯一来源；测试可注入确定性序列。"""

    def new_run_id(self) -> str:
        """每次 ParticipantRuntime 启动生成一次。"""

        ...

    def new_decision_id(self, window_key: WindowKey) -> str:
        """每个动作窗口生成一次；同一窗口的重新规划保持不变。"""

        ...

    def new_stage_attempt_id(self, stage_no: int | None) -> str:
        """每次阶段实际运行尝试开始时生成；stage_crashed 后必须换新。"""

        ...


class PrefixedUuidIds:
    """生产实现：uuid 全长 hex 加前缀，无截断碰撞风险，也不含敏感信息。"""

    def new_run_id(self) -> str:
        return "run-{}".format(uuid.uuid4().hex)

    def new_decision_id(self, window_key: WindowKey) -> str:
        return "dec-{}".format(uuid.uuid4().hex)

    def new_stage_attempt_id(self, stage_no: int | None) -> str:
        return "sa-{}-{}".format(
            stage_no if stage_no is not None else "x", uuid.uuid4().hex
        )
