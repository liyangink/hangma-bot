"""模拟模块公开接口 simulation-v1（parallel-v1 契约 §6 冻结）。

评估线只允许通过 SimulationEngine 的公开方法（start/frame/advance/
export_hand/from_replay）与下列值对象消费模拟能力；WorldState 归模拟线
拥有，调用方视为不可变不透明对象，不读其字段。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from hangma_bot.kernel.actions import Action, WindowKey
from hangma_bot.kernel.config import TournamentConfig
from hangma_bot.kernel.observation import PlayerObservation, ScoreVector


@dataclass(frozen=True)
class MatchSpec:
    """一场完整桌赛的可重复输入；不包含策略、网络或真实时钟。"""

    match_id: str  # 本地实验唯一标识，非官方 game_id
    scenario_id: str  # 同牌山比较组标识，不包含策略版本
    config: TournamentConfig  # rounds_per_game 规定完整单局数；max_games 不控制单个模拟世界
    seed: int  # 发牌随机源种子；与策略随机源分离
    initial_dealer: int  # 座位 0—3，换座实验同步映射
    initial_scores: ScoreVector  # 座位 0—3，单位为桌内积分

    def __post_init__(self) -> None:
        if not isinstance(self.match_id, str) or not self.match_id:
            raise ValueError("MatchSpec.match_id 必须是非空字符串")
        if not isinstance(self.scenario_id, str) or not self.scenario_id:
            raise ValueError("MatchSpec.scenario_id 必须是非空字符串")
        if not isinstance(self.config, TournamentConfig):
            raise ValueError("MatchSpec.config 必须是 TournamentConfig 值对象")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise ValueError("MatchSpec.seed 必须是整数，得到 {0!r}".format(self.seed))
        if (
            isinstance(self.initial_dealer, bool)
            or not isinstance(self.initial_dealer, int)
            or not 0 <= self.initial_dealer <= 3
        ):
            raise ValueError("MatchSpec.initial_dealer 必须是 0-3 的座位下标")
        if not isinstance(self.initial_scores, tuple) or len(self.initial_scores) != 4:
            raise ValueError("MatchSpec.initial_scores 必须是长度 4 的座位向量")
        for score in self.initial_scores:
            if isinstance(score, bool) or not isinstance(score, int):
                raise ValueError("MatchSpec.initial_scores 元素必须是整数")


@dataclass(frozen=True)
class SimulationDecision:
    """同一个模拟状态下该座位可见的决策机会，不含绝对时钟。"""

    window_key: WindowKey
    observation: PlayerObservation
    timeout_seconds: float  # 对应动作窗口秒数；评估器建立本地预算

    def __post_init__(self) -> None:
        if not isinstance(self.window_key, WindowKey):
            raise ValueError("SimulationDecision.window_key 必须是 WindowKey")
        if not isinstance(self.observation, PlayerObservation):
            raise ValueError("SimulationDecision.observation 必须是 PlayerObservation")
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or self.timeout_seconds <= 0
        ):
            raise ValueError("SimulationDecision.timeout_seconds 必须是正的有限秒数")


@dataclass(frozen=True)
class SimulationChoice:
    """评估器为一个窗口选出的动作；座位由 window_key 表达。"""

    window_key: WindowKey
    action: Action

    def __post_init__(self) -> None:
        if not isinstance(self.window_key, WindowKey):
            raise ValueError("SimulationChoice.window_key 必须是 WindowKey")


@dataclass(frozen=True)
class SimulationFrame:
    """一次稳定决策边界；自动摸牌等已推进到下一次需要选择的位置。"""

    revision: int  # 世界内单调递增，旧状态的选择不能用于新状态
    decisions: Tuple[SimulationDecision, ...]  # 同期响应者从同一状态取观察
    completed_hands: int
    final_scores: Optional[ScoreVector]  # 完整桌赛结束才有值
    blocked_reason: Optional[str]  # 不支持的规则/输入时给原因；不能默认为流局

    def __post_init__(self) -> None:
        if isinstance(self.revision, bool) or not isinstance(self.revision, int) or self.revision < 0:
            raise ValueError("SimulationFrame.revision 必须是非负整数")
        if not isinstance(self.decisions, tuple):
            raise ValueError("SimulationFrame.decisions 必须是 tuple")
        if isinstance(self.completed_hands, bool) or not isinstance(self.completed_hands, int) or self.completed_hands < 0:
            raise ValueError("SimulationFrame.completed_hands 必须是非负整数")
        # 契约三类互斥：决策非空 / 终局 / 阻塞，禁止空决策非终态（评估器忙循环）。
        if self.decisions:
            if self.final_scores is not None or self.blocked_reason is not None:
                raise ValueError("决策非空的帧不得携带终局积分或阻塞原因")
        elif self.final_scores is not None:
            if self.blocked_reason is not None:
                raise ValueError("终局帧不得携带阻塞原因")
        elif self.blocked_reason is None:
            raise ValueError("空决策帧必须给出终局积分或阻塞原因（禁止空转）")
