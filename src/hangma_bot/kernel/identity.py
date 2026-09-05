"""跨机器稳定标识算法（parallel-v1 契约 §4.1 的唯一冻结实现）。

集成裁定（2026-09-05，见 doc/implementation/handoffs/*.md）：hand_id /
split_group_id 全仓只有本文件一份实现；审计线（offline.replay 读写入）、
模拟线（simulation 导出）与评估线（结果文件）一律从这里导入或转导出，
不再保留同义副本。修改本文件即变更共享标识算法，必须按契约 §4.2 升级
版本并通知全部消费方。

编码口径（与契约文本逐字对应）：

- 将字段按给定顺序编码为 JSON 数组：ensure_ascii=False、
  separators=(",", ":")、allow_nan=False，再取 UTF-8 SHA-256 全长
  十六进制；前缀 hand- / split-；
- hand_id 前三项是非空字符串且不做 strip/大小写改写，round_no 是排除
  bool 的正整数，牌谱缺失时不得猜测；错误输入抛 ValueError；
- split 字段固定两个：[source_namespace, tournament_id]（官方）或
  [source_namespace, scenario_id]（模拟）。

本模块无文件、网络、时钟或业务依赖，符合 kernel 边界。
"""

from __future__ import annotations

import hashlib
import json
from typing import Sequence

__all__ = ["hand_id", "identity_digest", "split_group_id"]


def identity_digest(parts: Sequence[object]) -> str:
    """按契约 §4.1 的编码与摘要算法对 JSON 数组取 SHA-256 全长十六进制。

    编码固定：UTF-8、ensure_ascii=False、separators=(",", ":")、
    allow_nan=False。任何消费方的实现必须与本函数逐字节一致。
    """
    payload = json.dumps(
        list(parts), ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _require_identity_str(value: object, field_name: str) -> str:
    """身份字段必须是原样保留的非空字符串，不做 strip/大小写改写。"""
    if not isinstance(value, str) or not value:
        raise ValueError("{0} 必须是非空字符串且原样保留，得到 {1!r}".format(field_name, value))
    return value


def hand_id(source_namespace: str, tournament_id: str, game_id: str, round_no: int) -> str:
    """从权威场次身份生成跨机器稳定单局标识，不包含本地 run/attempt。

    将四项按给定顺序编码为 JSON 数组后取摘要，前缀 hand-。前三项是非空
    字符串且不做 strip/大小写改写；round_no 是排除 bool 的正整数；
    错误输入抛 ValueError。
    """
    fields = (
        _require_identity_str(source_namespace, "source_namespace"),
        _require_identity_str(tournament_id, "tournament_id"),
        _require_identity_str(game_id, "game_id"),
    )
    if isinstance(round_no, bool) or not isinstance(round_no, int) or round_no < 1:
        raise ValueError("round_no 必须是排除 bool 的正整数，得到 {0!r}".format(round_no))
    return "hand-" + identity_digest((*fields, round_no))


def split_group_id(fields: Sequence[str]) -> str:
    """按契约 §4.1 生成数据划分组标识（前缀 split-）。

    固定两个字段：官方取 [source_namespace, tournament_id]，模拟取
    [source_namespace, scenario_id]；键序固定，分组不包含策略版本。
    """
    if len(fields) != 2:
        raise ValueError("split_group_id 必须恰好两个字段，得到 {0} 项".format(len(fields)))
    cleaned = [_require_identity_str(item, "split 字段") for item in fields]
    return "split-" + identity_digest(cleaned)
