"""条件弃牌无官方序号时，三类响应仍复用生产动作族。"""

from dataclasses import replace

import pytest

from hangma_bot.hangma.candidate_facts import attach_facts
from hangma_bot.hangma.action_families import generate_candidates
from hangma_bot.hangma.internal_types import WindowContext
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.observation import PublicDiscard


@pytest.mark.parametrize("phase,code,hand,expected", (
    ("response_peng", "6w", ("6w", "6w"), ("peng:6w", "pass")),
    ("response_peng", "6w", ("6w", "6w", "6w"),
     ("peng:6w", "gang:exposed:6w", "pass")),
    ("response_chi", "1w", ("2w", "3w"),
     ("chi:1w,2w,3w", "pass")),
))
def test_conditional_trigger_has_same_legal_actions_without_fake_seq(
        phase, code, hand, expected):
    """给定公开弃牌只需座位和牌码，不能虚构官方事件序号。"""

    context = WindowContext(
        seat=1, phase=phase, turn_seat=0, responding_seats=(1,),
        hand_tiles=tuple(Tile(item) for item in hand), drawn_tile=None,
        my_chi_count=0, my_peng_codes=(), last_discard=None,
        catch_play=False, remaining_tile_count=60,
        conditional_discard=(0, Tile(code)),
    )
    official = replace(
        context, conditional_discard=None,
        last_discard=PublicDiscard(0, Tile(code), 42),
    )
    assert context.last_discard is None
    assert context.response_trigger() == (0, Tile(code))
    for source in (context, official):
        result = generate_candidates(source)
        assert tuple(item.action_key for item in result.candidates) == expected
        assert result.issues == ()


def test_conditional_trigger_cannot_masquerade_as_official_or_wrong_window():
    base = WindowContext(
        seat=1, phase="response_peng", turn_seat=0, responding_seats=(1,),
        hand_tiles=(Tile("6w"), Tile("6w")), drawn_tile=None,
        my_chi_count=0, my_peng_codes=(), last_discard=None,
        catch_play=False, remaining_tile_count=60,
        conditional_discard=(0, Tile("6w")),
    )
    with pytest.raises(ValueError, match="不能同时"):
        replace(base, last_discard=PublicDiscard(0, Tile("6w"), 42))
    with pytest.raises(ValueError, match="条件触发弃牌"):
        replace(base, phase="draw")
    with pytest.raises(ValueError, match="条件触发弃牌"):
        replace(base, conditional_discard=(2, Tile("6w")))


def test_chi_followup_facts_match_official_trigger_without_seq():
    """同一吃候选的后续全部弃牌事实不依赖虚构事件序号。"""

    context = WindowContext(
        seat=0, phase="response_chi", turn_seat=3, responding_seats=(0,),
        hand_tiles=tuple(Tile(code) for code in (
            "1w", "2w", "1t", "2t", "3t", "4t", "5t",
            "6t", "7t", "8t", "9t", "2b", "2b")),
        drawn_tile=None, my_chi_count=0, my_peng_codes=(),
        last_discard=None, catch_play=False, remaining_tile_count=60,
        conditional_discard=(3, Tile("3w")),
    )
    official = replace(
        context, conditional_discard=None,
        last_discard=PublicDiscard(3, Tile("3w"), 42),
    )
    results = []
    for source in (context, official):
        legal = generate_candidates(source)
        enriched, issues = attach_facts(source, (0,) * 34, 0, legal.candidates)
        assert issues == ()
        results.append(tuple((item.action_key, item.facts) for item in enriched))
    assert results[0] == results[1]
