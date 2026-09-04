"""启动后不可变的规则、时间和赛事配置。

本文件是第一阶段共享接口基线：不得单方面改名、删除字段或改变语义。
构造函数只做廉价结构校验（正数、有限秒数、非空字符串），让错误配置
在组合阶段失败，而不是进入 1 秒/3 秒动作窗口后才暴露。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .actions import _require_non_empty_str


def _require_positive_int(value: object, field_name: str) -> None:
    """正整数校验；`bool` 是 `int` 子类，必须显式排除。"""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("{0} 必须是正整数，得到 {1!r}".format(field_name, value))


def _require_positive_seconds(value: object, field_name: str) -> None:
    """正的有限秒数校验；NaN 会绕过普通比较，必须显式排除。"""
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError("{0} 必须是正的有限秒数，得到 {1!r}".format(field_name, value))


@dataclass(frozen=True)
class RuleConfig:
    """规则引擎实例绑定的官方规则配置。"""

    ruleset_version: str  # 本地规则语义版本，不等同于指南 API 版本
    base_score: int  # 官方 ``BaseScore``；计分底分
    you_cai_bi_kao: bool  # 官方 ``YouCaiBiKao``；有财必拷响开关

    def __post_init__(self) -> None:
        _require_non_empty_str(self.ruleset_version, "RuleConfig.ruleset_version")
        _require_positive_int(self.base_score, "RuleConfig.base_score")
        if not isinstance(self.you_cai_bi_kao, bool):
            raise ValueError(
                "RuleConfig.you_cai_bi_kao 必须是布尔值，得到 {0!r}".format(self.you_cai_bi_kao)
            )


@dataclass(frozen=True)
class TimingConfig:
    """官方动作窗口配置，所有持续时间单位均为秒。"""

    peng_timeout_sec: float
    chi_timeout_sec: float
    discard_timeout_sec: float

    def __post_init__(self) -> None:
        _require_positive_seconds(self.peng_timeout_sec, "TimingConfig.peng_timeout_sec")
        _require_positive_seconds(self.chi_timeout_sec, "TimingConfig.chi_timeout_sec")
        _require_positive_seconds(self.discard_timeout_sec, "TimingConfig.discard_timeout_sec")


@dataclass(frozen=True)
class TournamentConfig:
    """当前赛事返回的运行配置；一个身份最多维护 ``max_games`` 场。"""

    max_games: int  # 官方 ``config.M``
    rounds_per_game: int  # 官方 ``config.Rounds``，表示每场包含的单局数
    rules: RuleConfig
    timing: TimingConfig

    def __post_init__(self) -> None:
        _require_positive_int(self.max_games, "TournamentConfig.max_games")
        _require_positive_int(self.rounds_per_game, "TournamentConfig.rounds_per_game")
        if not isinstance(self.rules, RuleConfig):
            raise ValueError("TournamentConfig.rules 必须是 RuleConfig 值对象")
        if not isinstance(self.timing, TimingConfig):
            raise ValueError("TournamentConfig.timing 必须是 TimingConfig 值对象")
