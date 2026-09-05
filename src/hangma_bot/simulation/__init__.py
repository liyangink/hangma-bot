"""本地确定性模拟环境：完整世界、规则推进、完整桌赛、导入导出与历史核对。

公开面 = parallel-v1 契约 §6：SimulationEngine.start/frame/advance/
export_hand/from_replay + MatchSpec/SimulationDecision/SimulationFrame/
SimulationChoice；WorldState 归本模块所有，调用方视为不透明不可变对象。
历史核对入口（契约 §6）为 offline.replay_check.check_hand。
"""

from .artifacts import GUIDE_CAPTURED_AT, GUIDE_VERSION, compute_rules_hash
from .engine import SimulationEngine
from .identity import (
    hand_id,
    simulation_hand_id,
    simulation_split_group_id,
    split_group_id,
)
from .interface import (
    MatchSpec,
    SimulationChoice,
    SimulationDecision,
    SimulationFrame,
)
from .shuffle import DEAL_ALGORITHM, RESERVE_TILES
from .state import RoundRecord, WorldState

__all__ = [
    "DEAL_ALGORITHM",
    "GUIDE_CAPTURED_AT",
    "GUIDE_VERSION",
    "MatchSpec",
    "RESERVE_TILES",
    "RoundRecord",
    "SimulationChoice",
    "SimulationDecision",
    "SimulationEngine",
    "SimulationFrame",
    "WorldState",
    "compute_rules_hash",
    "hand_id",
    "simulation_hand_id",
    "simulation_split_group_id",
    "split_group_id",
]
