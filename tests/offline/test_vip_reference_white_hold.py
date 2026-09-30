"""离线双白敏感性参考者的边界；它不是可发布策略。"""

from types import SimpleNamespace

import pytest

from hangma_bot.kernel.actions import Discard, Hu, Tile
from hangma_bot.offline.vip_reference import choose_reference_action


def _decision(*, whites: int = 2, wall: int = 35):
    observation = SimpleNamespace(
        phase="draw", my_hand=(Tile("白"),) * whites,
        drawn_tile=Tile("1w"), remaining_tile_count=wall,
    )
    return SimpleNamespace(observation=observation)


def _rules(*, fan: int = 2, settlement: bool = True):
    hu = SimpleNamespace(
        action=Hu(), value_facts=SimpleNamespace(
            immediate_settlement=(SimpleNamespace(fan=fan) if settlement else None),
            coverage=SimpleNamespace(value="unavailable"), issues=(),
        ),
    )
    narrow = SimpleNamespace(
        action=Discard(Tile("2w")), action_key="discard:2w",
        facts=SimpleNamespace(shanten_after=0, useful_tiles=()),
    )
    white = SimpleNamespace(
        action=Discard(Tile("白")), action_key="discard:白",
        facts=SimpleNamespace(shanten_after=0, useful_tiles=()),
    )

    class Rules:
        def analyze(self, observation, *, value_limits=None):
            del observation
            # 未索取价值分析时，Hu 结算不可凭空存在；参考者只有在
            # 双白且仍可摸牌时才应额外请求同源分值载荷。
            if value_limits is None:
                bare_hu = SimpleNamespace(action=Hu(), value_facts=None)
                return SimpleNamespace(legal_candidates=(bare_hu, narrow, white))
            return SimpleNamespace(legal_candidates=(hu, narrow, white))

    return Rules()


def test_two_whites_can_defer_low_fan_hu_without_discarding_white():
    chosen = choose_reference_action(_rules(), _decision(), mode="shape_white_hold")
    assert chosen == Discard(Tile("2w"))


@pytest.mark.parametrize("decision,rules", [
    (_decision(whites=1), _rules()),
    (_decision(wall=20), _rules()),
    (_decision(), _rules(fan=4)),
])
def test_no_wait_without_two_whites_wall_or_low_fan(decision, rules):
    assert choose_reference_action(rules, decision, mode="shape_white_hold") == Hu()


def test_eligible_win_missing_same_rule_settlement_stops_teacher():
    with pytest.raises(ValueError, match="缺同源结算"):
        choose_reference_action(_rules(settlement=False), _decision(),
                                mode="shape_white_hold")
