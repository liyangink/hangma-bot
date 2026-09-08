"""v23 四白差异的公开入口回归；官方原始响应采集于 2026-09-08。"""

from dataclasses import replace
import json

import pytest

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import RuleCompleteness, WinDescription
from hangma_bot.hangma.progression import attach_draw, baotou_after_draw, deal_state, resolve
from hangma_bot.kernel.actions import Discard, Hu, Tile
from hangma_bot.kernel.config import RuleConfig
from tests.unit.hangma.official_fan_tools import FIXTURE_DIR
from tests.unit.hangma.test_action_chain_lifecycle import _next_own_draw
from tests.unit.hangma.test_youcai_integration import make_observation


TAGS = {
    "v23-four-white-baotou-check",
    "v23-four-white-luxury-check",
    "luxury-east-discard-red-draw-白",
}
CASES = [row for row in map(json.loads, (FIXTURE_DIR / "cases.jsonl").read_text().splitlines())
         if TAGS.intersection(row["tags"])]


def _dealt(hand):
    """隔离本人规则转移；其余三家为不参与此断言的合成占位手牌。"""
    other = tuple(Tile(t) for t in "1t 2t 3t 4t 5t 6t 7t 8t 9t 南 南 西 西".split())
    return deal_state(1, 0, (tuple(Tile(t) for t in hand), other, other, other),
                      (0, 0, 0, 0), 0, 1, 60, 80)


def test_three_original_differences_are_all_replayed():
    assert len(CASES) == 3
    assert {tag for row in CASES for tag in row["tags"] if tag in TAGS} == TAGS


@pytest.mark.parametrize("row", CASES, ids=lambda row: row["tags"][0])
@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("hand_includes_draw", [False, True])
def test_four_white_progression_gate_and_settlement(row, enabled, hand_includes_draw):
    """同一官方牌例贯通摸牌推进、两种观察表示、配置门槛及庄闲结算。"""
    request, official = row["request"], row["response"]
    state = attach_draw(_dealt(request["hand"]), Tile(request["draw"])).state
    assert state.seats[0].baotou == official["baotou"]
    obs = make_observation(request["hand"], request["draw"], baotou=state.seats[0].baotou)
    if hand_includes_draw:
        obs = replace(obs, my_hand=obs.my_hand + (obs.drawn_tile,))
    rules = HangmaRules(RuleConfig("v23-four-white", 1, enabled))
    allowed = not enabled or official["baotou"]  # 三例均成牌且手留四白。
    analysis = rules.analyze(obs)
    assert analysis.completeness is RuleCompleteness.COMPLETE
    assert any(c.action_key == "hu" for c in analysis.legal_candidates) == allowed
    assert rules.validate(obs, Hu()).legal == allowed
    assert rules.validate(obs, analysis.emergency_candidate.action).legal
    for dealer in (0, 1):
        scored = rules.score(WinDescription(replace(obs, dealer_seat=dealer), 0))
        assert scored.fan == official["fan"]
        assert list(scored.details) == official["detail"]
        assert scored.score_delta[0] == official["scores"]["dealer_hu" if dealer == 0 else "nondealer_hu"]["win"]
        assert sum(scored.score_delta) == 0


def test_four_white_baotou_can_piao_and_keep_four_white_bonus():
    """四白爆头弃一白应计飘，下一次胡按手留三白加链内一白计四白。"""
    hand = "1w 2w 3w 4w 5w 6w 7b 8b 9b 白 白 白 白".split()
    initial = _dealt(hand)
    assert initial.seats[0].baotou
    drawn = attach_draw(initial, Tile("东")).state
    discarded = resolve(drawn, ((0, Discard(Tile("白"))),)).state
    assert discarded.seats[0].baotou
    assert (discarded.seats[0].chain_count, discarded.seats[0].chain_piao) == (1, 1)
    next_draw = _next_own_draw(discarded, "北")
    result = resolve(next_draw, ((0, Hu()),)).state.hand_result
    assert result.details == ("平胡", "财飘", "4个白板", "爆头")
    assert result.fan == 8
    assert result.score_delta == (192, -64, -64, -64)  # 座位0为庄家；顺序0—3。


@pytest.mark.parametrize("replacement", [False, True, None])
def test_four_white_inheritance_keeps_draw_source_boundary(replacement):
    """合成继承边界：四白不抹掉有效旧状态，来源未知仍不能猜测。

    此手摸前非任意听、摸第四白成普通型；已有一副露。不是官方连续轨迹。
    普通摸牌重新判定，杠补继承，缺少补牌来源则显式请求权威恢复。
    """
    hand = tuple(Tile(t) for t in "1w 1w 1w 4b 4b 2t 5t 白 白 白".split())
    if replacement is None:
        with pytest.raises(ValueError, match="摸牌来源未知"):
            baotou_after_draw(True, hand, 1, Tile("白"), replacement=replacement)
    else:
        assert baotou_after_draw(True, hand, 1, Tile("白"), replacement=replacement) is replacement
