"""官方竞赛平台适配器（协议基线 v8 快照 + 指南 v9–v14 已审查变更，2026-09-05）。

公开面：OfficialTournamentSession（TournamentSessionPort）与
OfficialGameSession（GameSessionPort）。传输、调度器、同步状态与动作门
均为内部实现，应用层不得依赖（接口协议 §1）。Token 只经由构造参数进入，
不会出现在任何导出类型的日志、异常或审计输出中。
"""

from .participant import OfficialTournamentSession
from .game import OfficialGameSession
from .transport import OfficialTransport, TransportConfig
from .scheduler import Priority, RequestScheduler

__all__ = [
    "OfficialTournamentSession",
    "OfficialGameSession",
    "OfficialTransport",
    "TransportConfig",
    "Priority",
    "RequestScheduler",
]
