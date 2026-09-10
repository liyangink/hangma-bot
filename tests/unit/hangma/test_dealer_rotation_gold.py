"""庄家轮转金例：用两夜原始官方牌谱校验 next_dealer 与平台一致。

来源：datasets/derived/auto-match-rooms-{20260908,20260910}/hands（**原始官方牌谱**，
2026-09-08 与 2026-09-10 抓取）。夹具只含座位号与流局标记，不含任何令牌。

平台实测规则：非流局由**本局赢家**坐庄；流局庄家保留。指南 1.1 只明文规定了
流局连庄这一支，闲家胡牌之后谁坐庄没有文字规定，因此以平台原始牌谱为准。
"""
from __future__ import annotations

import json
from pathlib import Path

from hangma_bot.hangma.progression import next_dealer

GOLD = (Path(__file__).parents[2] / "fixtures" / "hangma" / "dealer-rotation-gold.json")


def _load():
    return json.loads(GOLD.read_text(encoding="utf-8"))


def test_gold_fixture_shape():
    """夹具本身可用：两夜、每夜若干整局，局号连续且起点齐备。"""

    gold = _load()
    assert set(gold["nights"]) == {"20260908", "20260910"}
    for label, night in gold["nights"].items():
        assert night["games"], label
        for game in night["games"]:
            rounds = game["rounds"]
            assert [r["round_no"] for r in rounds] == list(range(1, len(rounds) + 1)), label
            assert all(0 <= r["dealer"] < 4 for r in rounds), label


def test_next_dealer_reproduces_every_platform_transition():
    """逐局重放：每一处转移都必须由 next_dealer 复现，不允许例外。"""

    gold = _load()
    checked = 0
    for label, night in gold["nights"].items():
        for game in night["games"]:
            rounds = game["rounds"]
            for previous, current in zip(rounds, rounds[1:]):
                expected = next_dealer(previous["dealer"], previous["winner"],
                                       previous["is_draw"])
                assert expected == current["dealer"], (
                    "{0} {1} 局 {2}->{3}：next_dealer 给出 {4}，平台是 {5}".format(
                        label, game["game_id"], previous["round_no"], current["round_no"],
                        expected, current["dealer"]))
                checked += 1
    assert checked > 100, checked


def test_platform_rule_totals_are_recorded():
    """把"平台 100% 赢家坐庄 / 流局保留"的统计写进断言，防止夹具退化成弱样本。"""

    gold = _load()
    non_draw = sum(night["totals"]["non_draw_transitions"] for night in gold["nights"].values())
    winner_moves = sum(night["totals"]["next_dealer_equals_winner"]
                       for night in gold["nights"].values())
    draws = sum(night["totals"]["draw_transitions"] for night in gold["nights"].values())
    keeps = sum(night["totals"]["draw_keeps_dealer"] for night in gold["nights"].values())
    assert non_draw == 1088, non_draw
    assert winner_moves == non_draw, (winner_moves, non_draw)
    assert draws == 32, draws
    assert keeps == draws, (keeps, draws)
