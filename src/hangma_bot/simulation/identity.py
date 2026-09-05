"""跨进程稳定标识算法（parallel-v1 契约 §4.1 冻结实现）。

单局标识（hand_id）与划分组标识（split_group_id）按契约向量
（doc/implementation/contracts/contract-vectors.json）逐例对拍：

- 编码：JSON 数组，ensure_ascii=False、separators=(comma,colon)、
  allow_nan=False，再取 UTF-8 SHA-256 全长十六进制；
- 前缀：hand- / split-；
- hand_id 输入三项非空字符串（不 strip/不改写），round_no 为排除 bool 的
  正整数，非法输入抛 ValueError；
- official split 字段 [source_namespace, tournament_id]；simulation split
  字段 [source_namespace, scenario_id]。

注意：审计线（offline/replay 读写入）与模拟线导出都消费同一算法；集成时
由主审决定是否提升到共享位置，本文件保持与契约文本逐字对应的单一实现。
"""

from __future__ import annotations

import hashlib
import json
from typing import Sequence


def _digest(value) -> str:
    """契约 §4.1 编码 + SHA-256 全长十六进制。"""
    payload = json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def hand_id(source_namespace: str, tournament_id: str, game_id: str, round_no: int) -> str:
    """从权威场次身份生成跨机器稳定单局标识，不包含本地 run/attempt。

    将四项按给定顺序编码为 JSON 数组：ensure_ascii=False、
    separators=(comma,colon)、allow_nan=False，再取 UTF-8 SHA-256 全长
    十六进制，前缀 hand-。前三项是非空字符串且不做 strip/大小写改写；
    round_no 是排除 bool 的正整数，牌谱缺失时不得猜测；错误输入抛 ValueError。
    """
    for field_name, field in (
        ("source_namespace", source_namespace),
        ("tournament_id", tournament_id),
        ("game_id", game_id),
    ):
        if not isinstance(field, str) or not field:
            raise ValueError("{0} 必须是非空字符串".format(field_name))
    if isinstance(round_no, bool) or not isinstance(round_no, int) or round_no < 1:
        raise ValueError("round_no 必须是排除 bool 的正整数，得到 {0!r}".format(round_no))
    return "hand-" + _digest([source_namespace, tournament_id, game_id, round_no])


def split_group_id(fields: Sequence[str]) -> str:
    """同一编码/哈希算法处理字段数组，前缀 split-；不跨训练划分的组键。"""
    return "split-" + _digest(list(fields))


def simulation_hand_id(scenario_id: str, match_id: str, round_no: int) -> str:
    """模拟导出固定 source_namespace=hangma-simulation、tournament_id=scenario_id。"""
    return hand_id("hangma-simulation", scenario_id, match_id, round_no)


def simulation_split_group_id(scenario_id: str) -> str:
    """模拟划分组：simulation split 字段 [source_namespace, scenario_id]。"""
    return split_group_id(["hangma-simulation", scenario_id])
