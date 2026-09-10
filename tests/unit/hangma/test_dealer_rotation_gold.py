"""庄家轮转金例：用两夜原始官方牌谱校验 next_dealer 与平台一致。

来源：datasets/derived/auto-match-rooms-{20260908,20260910}/hands（**原始官方牌谱**，
2026-09-08 与 2026-09-10 抓取）。夹具只含座位号与流局标记，不含任何令牌。
实际固化 24 个完整八局桌赛的 168 次转移；两夜全样本统计仅作来源元数据。

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
    """两夜各 12 个完整八局桌赛；座位合法、流局标记与赢家一致。"""

    gold = _load()
    assert set(gold["nights"]) == {"20260908", "20260910"}
    for label, night in gold["nights"].items():
        assert len(night["games"]) == 12, label
        assert len({game["game_id"] for game in night["games"]}) == 12, label
        for game in night["games"]:
            rounds = game["rounds"]
            assert [r["round_no"] for r in rounds] == list(range(1, 9)), label
            assert all(0 <= r["dealer"] < 4 for r in rounds), label
            for row in rounds:
                assert isinstance(row["is_draw"], bool), label
                if row["is_draw"]:
                    assert row["winner"] is None, label
                else:
                    assert row["winner"] in range(4), label


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
    assert checked == 168, checked


def test_fixture_covers_winner_rotation_and_draw_retention():
    """重算固化记录的覆盖，不用全样本 totals 元数据冒充已执行金例。"""

    counts = {}
    non_dealer_wins = 0
    distinguishes_next_seat = 0
    for label, night in _load()["nights"].items():
        non_draw = draws = 0
        for game in night["games"]:
            for previous, current in zip(game["rounds"], game["rounds"][1:]):
                if previous["is_draw"]:
                    draws += 1
                    assert current["dealer"] == previous["dealer"]
                else:
                    non_draw += 1
                    assert current["dealer"] == previous["winner"]
                    if previous["winner"] != previous["dealer"]:
                        non_dealer_wins += 1
                        distinguishes_next_seat += (
                            previous["winner"] != (previous["dealer"] + 1) % 4
                        )
        counts[label] = (non_draw, draws)
    assert counts == {"20260908": (84, 0), "20260910": (83, 1)}
    assert non_dealer_wins == 125
    assert distinguishes_next_seat > 0
