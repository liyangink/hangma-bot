#!/usr/bin/env python3
"""研究专用逐单局结算旁路：经 SimulationEngine 公开接口采集，不暴露完整世界给策略。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/freematch-deep-dive-20260925'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

from collections.abc import Mapping, Sequence
from typing import Any


class HandAccountingEngine:
    """包装离线模拟引擎，仅在已完成单局后保留结算字段。

    ``drive_match`` 仍只见原引擎公开的 start/frame/advance；旁路读取
    ``export_hand`` 的赛后结算，不把未来墙、他家暗手或 WorldState 传给策略。
    每张完整桌赛新建一个包装实例，避免跨桌混账。
    """

    def __init__(self, engine: Any) -> None:
        self.engine = engine
        self.hands: list[dict[str, Any]] = []

    def start(self, spec: Any) -> Any:
        """建立新桌，并清除前一桌的赛后结算记录。"""

        self.hands.clear()
        return self.engine.start(spec)

    def frame(self, world: Any) -> Any:
        """原样转发玩家可见决策帧。"""

        return self.engine.frame(world)

    def advance(self, world: Any, revision: int, choices: Any) -> Any:
        """原样推进；只有单局已结算才调用公开导出器采集最小字段。"""

        before = self.engine.frame(world).completed_hands
        after_world = self.engine.advance(world, revision, choices)
        after = self.engine.frame(after_world).completed_hands
        if after < before or after > before + 1:
            raise ValueError("单次推进的完成单局数不在 0..1")
        if after > before:
            row = self.engine.export_hand(after_world, after)
            fields = ("round_no", "hand_id", "result_confirmed", "scores_before",
                      "scores_after", "score_delta", "winner_seat", "is_draw",
                      "fan", "details")
            self.hands.append({name: row.get(name) for name in fields})
        return after_world


def summarize_hands(hands: Sequence[Mapping[str, Any]], *, focal_seat: int,
                    initial_scores: Sequence[int], final_scores: Sequence[int],
                    expected_hands: int) -> dict[str, Any]:
    """逐单局对账，按本人纯平胡、特殊胡、他家胡、流局分解本人净积分。

    输入是赛后最小结算字段；积分向量按座位 0..3 排列。任一身份、番数、
    分数守恒或桌内连续性不符都拒绝给出收益拆账。
    """

    if type(focal_seat) is not int or not 0 <= focal_seat < 4:
        raise ValueError("focal_seat 必须是 0..3")
    if type(expected_hands) is not int or expected_hands <= 0 or len(hands) != expected_hands:
        raise ValueError("完整桌赛单局数不符")
    if (len(initial_scores) != 4 or len(final_scores) != 4
            or any(type(value) is not int for value in (*initial_scores, *final_scores))):
        raise ValueError("初末积分必须是四座整数向量")
    current = list(initial_scores)
    values = {"plain_self_win_delta": 0, "special_self_win_delta": 0,
              "other_win_delta": 0, "draw_delta": 0,
              "plain_self_wins": 0, "special_self_wins": 0,
              "other_wins": 0, "draws": 0}
    seen_hands: set[str] = set()
    for index, hand in enumerate(hands, start=1):
        if hand.get("round_no") != index or hand.get("result_confirmed") is not True:
            raise ValueError("单局序号或结算确认不符")
        hand_id = hand.get("hand_id")
        if not isinstance(hand_id, str) or not hand_id or hand_id in seen_hands:
            raise ValueError("单局身份缺失或重复")
        seen_hands.add(hand_id)
        before, after, delta = (hand.get(key) for key in
                                ("scores_before", "scores_after", "score_delta"))
        if (not all(isinstance(item, (tuple, list)) and len(item) == 4
                    and all(type(value) is int for value in item)
                    for item in (before, after, delta))
                or list(before) != current
                or any(before[seat] + delta[seat] != after[seat] for seat in range(4))
                or sum(delta) != 0):
            raise ValueError("逐单局积分向量不守恒或不连续")
        current = list(after)
        is_draw, winner, fan, details = (hand.get(key) for key in
                                         ("is_draw", "winner_seat", "fan", "details"))
        amount = delta[focal_seat]
        if is_draw is True:
            if (winner is not None or fan not in (None, 0)
                    or any(value != 0 for value in delta)):
                raise ValueError("流局结算字段冲突")
            values["draws"] += 1
            values["draw_delta"] += amount
            continue
        if (is_draw is not False or type(winner) is not int or not 0 <= winner < 4
                or type(fan) is not int or fan <= 0
                or not isinstance(details, (list, tuple)) or not details
                or not isinstance(details[0], str)
                or (details[0] not in ("平胡", "七对")
                    and not details[0].startswith("豪华七对×"))):
            raise ValueError("胡牌结算字段缺失")
        if (list(details) == ["平胡"] and fan != 1) or (list(details) != ["平胡"] and fan <= 1):
            raise ValueError("胡牌番数与普通/特殊明细不一致")
        if winner == focal_seat:
            if amount <= 0:
                raise ValueError("本人胡牌却未得到正积分")
            prefix = "plain_self" if list(details) == ["平胡"] else "special_self"
            values[prefix + "_wins"] += 1
            values[prefix + "_win_delta"] += amount
        else:
            if amount >= 0:
                raise ValueError("他家胡牌时本人付分必须为负")
            values["other_wins"] += 1
            values["other_win_delta"] += amount
    if current != list(final_scores):
        raise ValueError("逐单局累计与完整桌终分不符")
    if (values["plain_self_win_delta"] + values["special_self_win_delta"]
            + values["other_win_delta"] + values["draw_delta"]
            != final_scores[focal_seat] - initial_scores[focal_seat]):
        raise ValueError("本人收益分量与完整桌净分不符")
    return {"schema": "g13-hand-accounting/1", "focal_seat": focal_seat,
            "complete_hands": expected_hands, "focal_table_delta":
                final_scores[focal_seat] - initial_scores[focal_seat], **values}
