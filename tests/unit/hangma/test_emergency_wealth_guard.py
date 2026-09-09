"""公开紧急入口的保财退路：普通窗口优先非白，强制摸切保留白板。"""

from __future__ import annotations

import pytest

from hangma_bot.hangma import HangmaRules
from hangma_bot.kernel.actions import Discard, Tile
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import PlayerObservation, PublicMeld, RulePublicState


def _observation(
    hand: str,
    *,
    drawn: str | None = None,
    catch_play: bool = False,
    melds: tuple[PublicMeld, ...] = (),
) -> PlayerObservation:
    """构造本人出牌窗口；手牌顺序保留输入，摸牌可以已包含或另列。"""

    tiles = tuple(Tile(code) for code in hand.split())
    return PlayerObservation(
        game_id="emergency-wealth-guard",
        seat=0,
        round_no=1,
        snapshot_seq=1,
        phase="draw",
        dealer_seat=0,
        turn_seat=0,
        responding_seats=(),
        my_hand=tiles,
        drawn_tile=Tile(drawn) if drawn is not None else None,
        discards=((), (), (), ()),
        melds=(melds, (), (), ()),
        hand_counts=(len(tiles), 13, 13, 13),
        last_discard=None,
        remaining_tile_count=60,
        scores=(0, 0, 0, 0),
        rule_state=RulePublicState(Tile("白"), False, 0, catch_play),
        public_history=(),
    )


@pytest.fixture
def rules() -> HangmaRules:
    """仅调用紧急公开接口，不启动牌型搜索或模拟。"""

    return HangmaRules(
        RuleConfig(ruleset_version="emergency-wealth-guard", you_cai_bi_kao=True, base_score=1)
    )


def test_ordinary_emergency_skips_trailing_whites(rules):
    observation = _observation(
        "1w 2w 3w 4w 5w 6w 7w 8w 9w 东 南 西 白 白", drawn="白"
    )

    candidate = rules.emergency_action(observation)

    assert candidate is not None
    assert candidate.action == Discard(Tile("西"))


def test_ordinary_emergency_keeps_rightmost_nonwhite(rules):
    observation = _observation(
        "1w 2w 3w 4w 5w 6w 7w 8w 9w 东 南 西 白 5b", drawn="5b"
    )

    assert rules.emergency_action(observation).action == Discard(Tile("5b"))


@pytest.mark.parametrize(("drawn", "expected"), [("白", "西"), ("发", "发")])
def test_separate_draw_has_same_emergency_as_included_draw(rules, drawn, expected):
    """13+1 与官方含摸牌的 14 张观察代表同一手牌，应选择相同退路。"""

    before_draw = "1w 2w 3w 4w 5w 6w 7w 8w 9w 东 南 西 白"
    separate = _observation(before_draw, drawn=drawn)
    included = _observation(before_draw + " " + drawn, drawn=drawn)

    assert rules.emergency_action(separate).action == Discard(Tile(expected))
    assert rules.emergency_action(included).action == Discard(Tile(expected))


def test_forced_draw_discard_keeps_white_without_baotou(rules):
    observation = _observation(
        "1w 2w 3w 4w 5w 6w 7w 8w 9w 东 南 西 北 白",
        drawn="白",
        catch_play=True,
    )

    assert rules.emergency_action(observation).action == Discard(Tile("白"))


def test_all_white_concealed_tiles_keep_a_legal_fallback(rules):
    """四副露后只余两白，无非白可选时仍必须给出弃牌。"""

    melds = tuple(
        PublicMeld(0, "peng", (Tile(code),) * 3, 1)
        for code in ("1w", "2w", "3w", "4w")
    )
    observation = _observation("白 白", drawn="白", melds=melds)

    assert rules.emergency_action(observation).action == Discard(Tile("白"))


@pytest.mark.parametrize("drawn", ["白", "5b"])
def test_only_drawn_tile_keeps_existing_fallback(rules, drawn):
    observation = _observation("", drawn=drawn)

    assert rules.emergency_action(observation).action == Discard(Tile(drawn))


def test_unavailable_main_analysis_does_not_remove_nonwhite_fallback(rules, monkeypatch):
    """主分析入口不可用时，紧急决策仍独立返回非白退路。"""

    def unavailable_analysis(self, observation):
        raise RuntimeError("主规则分析暂不可用")

    monkeypatch.setattr(HangmaRules, "analyze", unavailable_analysis)
    observation = _observation(
        "1w 2w 3w 4w 5w 6w 7w 8w 9w 东 南 西 白 白", drawn="白"
    )

    assert rules.emergency_action(observation).action == Discard(Tile("西"))
