"""P2 条件公开牌核心：只给公开视图及本人暗牌，不构造条件观察。"""

from dataclasses import replace

import pytest

from hangma_bot.hangma.internal_types import TILE_INDEX
from hangma_bot.hangma.public_tile_counts import (
    PublicClaimEvidence,
    PublicTileView,
    count_public_tiles,
    count_public_tiles_from_view,
    count_unseen_tiles,
    count_unseen_tiles_from_view,
    public_view_from_observation,
)
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.observation import PublicEvent, PublicMeld
from tests.unit.hangma.test_candidate_facts import make_observation


def _view(*, discards=((), (), (), ()), melds=((), (), (), ()),
          hand_counts=(13, 13, 13, 13), wall=None, history=(), claims=()):
    return PublicTileView(
        discards=discards, melds=melds, hand_counts=hand_counts,
        remaining_tile_count=wall, public_history=history,
        snapshot_seq=10, consumed_seq=10, claim_evidence=claims,
    )


def _counts(view, code, *, concealed=(), drawn=None, chain_piao=0):
    result = count_unseen_tiles_from_view(
        view, seat=0, concealed=tuple(Tile(c) for c in concealed),
        drawn_tile=Tile(drawn) if drawn else None, chain_piao=chain_piao,
    )
    index = TILE_INDEX[code]
    return result.public[index], result.unseen[index], result.evidence[index]


def test_observation_projection_preserves_both_legacy_34_tile_vectors():
    """现有观察入口逐牌码等于新核心，官方含摸牌形态也保持相同。"""

    observation = make_observation(
        drawn_tile=Tile("1w"), hand_counts=(14, 13, 13, 13),
        discards=((Tile("白"),), (), (), ()), chain_piao=1,
        rule_state=replace(make_observation().rule_state, chain_count=1),
    )
    for source in (observation, replace(observation, my_hand=observation.my_hand + (Tile("1w"),))):
        view = public_view_from_observation(source)
        assert count_public_tiles(source) == count_public_tiles_from_view(view).counts
        # 旧观察入口负责归一化；新条件入口收到的暗牌不含单列摸牌。
        conditional = count_unseen_tiles_from_view(
            view, seat=source.seat, concealed=observation.my_hand,
            drawn_tile=source.drawn_tile, chain_piao=source.chain_piao,
        )
        assert count_unseen_tiles(source) == conditional.unseen


@pytest.mark.parametrize("retained", [True, False])
def test_peng_claim_retained_or_removed_river_is_counted_once(retained):
    """守恒读数区分留河和移河；两种口径都只有三张物理公开牌。"""

    meld = PublicMeld(0, "peng", (Tile("1w"),) * 3, 1)
    view = _view(
        discards=((), (Tile("1w"),) if retained else (), (), ()),
        melds=((meld,), (), (), ()), hand_counts=(10, 13, 13, 13),
        wall=84,
    )
    assert _counts(view, "1w") == (3, 1, "exact")


def test_chi_claimed_tile_is_the_only_overlapping_shape_member():
    """吃 3w 时只扣被领取的 3w，不能把 1w/2w 当成供牌。"""

    meld = PublicMeld(0, "chi", tuple(Tile(c) for c in ("1w", "2w", "3w")), 3)
    history = (
        PublicEvent(7, "tile_discarded", 3, (Tile("3w"),)),
        PublicEvent(8, "chi", 0, meld.tiles, claimed_tile=Tile("3w")),
    )
    view = _view(discards=((), (), (), (Tile("3w"),)),
                 melds=((meld,), (), (), ()), hand_counts=(10, 13, 13, 13),
                 wall=84, history=history)
    assert _counts(view, "3w") == (1, 3, "exact")
    assert _counts(view, "1w") == (1, 3, "exact")


def test_missing_chi_claim_evidence_marks_capacity_conservative():
    """缺领取牌码不能从副露牌形猜；数值是下界并附证据状态。"""

    meld = PublicMeld(0, "chi", tuple(Tile(c) for c in ("1w", "2w", "3w")), 3)
    view = _view(discards=((), (), (), (Tile("3w"),)),
                 melds=((meld,), (), (), ()), wall=None)
    assert _counts(view, "3w") == (2, 2, "conservative")
    assert _counts(view, "1w") == (1, 3, "conservative")


def test_assumed_claim_evidence_needs_no_fabricated_official_event():
    """给定吃领取证据按副露实例记录，官方历史和序号保持原样。"""

    meld = PublicMeld(0, "chi", tuple(Tile(c) for c in ("1w", "2w", "3w")), 3)
    claim = PublicClaimEvidence(0, 0, 3, Tile("3w"), "assumed", True)
    view = _view(discards=((), (), (), (Tile("3w"),)),
                 melds=((meld,), (), (), ()), claims=(claim,))
    assert view.public_history == ()
    assert _counts(view, "3w") == (1, 3, "exact")


@pytest.mark.parametrize("kind", ["gang_ming", "gang_bu"])
def test_exposed_gang_and_added_gang_inherit_only_one_claim(kind):
    """明杠领取一次；补杠沿用旧碰领取，不产生第五张公开牌。"""

    meld = PublicMeld(1, kind, (Tile("东"),) * 4, 0)
    view = _view(discards=((Tile("东"),), (), (), ()),
                 melds=((), (meld,), (), ()), wall=None,
                 claims=(PublicClaimEvidence(1, 0, 0, Tile("东"), "assumed", True),))
    assert _counts(view, "东") == (4, 0, "exact")


def test_added_gang_uses_original_peng_claim_evidence_once():
    """补杠继承原碰的被领取牌；其余第四张来自本人，不重领弃牌。"""

    meld = PublicMeld(1, "gang_bu", (Tile("东"),) * 4, 0)
    view = _view(discards=((Tile("东"),), (), (), ()),
                 melds=((), (meld,), (), ()),
                 claims=(PublicClaimEvidence(1, 0, 0, Tile("东"), "assumed", True),))
    assert _counts(view, "东") == (4, 0, "exact")


@pytest.mark.parametrize("kind", ["gang_ming", "gang_bu"])
def test_claimed_gang_cannot_explain_another_seats_river_tile(kind):
    """供牌者为座位0，座位2的同码河牌必是额外第五张。"""

    meld = PublicMeld(1, kind, (Tile("东"),) * 4, 0)
    view = _view(discards=((), (), (Tile("东"),), ()),
                 melds=((), (meld,), (), ()))
    assert _counts(view, "东") == (None, None, "unknown")


@pytest.mark.parametrize("kind", ["gang_ming", "gang_bu"])
def test_unproven_gang_river_overlap_is_not_exact(kind):
    """无供牌者、事件和实例证据时，河中同码牌不能自动算成杠的重叠。"""

    meld = PublicMeld(1, kind, (Tile("东"),) * 4, None)
    view = _view(discards=((Tile("东"),), (), (), ()),
                 melds=((), (meld,), (), ()))
    assert _counts(view, "东") == (None, None, "unknown")


def test_chi_containing_code_cannot_explain_a_fifth_river_tile():
    """吃 2w 不会领取 1w；另一个碰三张 1w 后，河中 1w 是第五张。"""

    chi = PublicMeld(1, "chi", tuple(Tile(c) for c in ("1w", "2w", "3w")), 0)
    peng = PublicMeld(2, "peng", (Tile("1w"),) * 3, 0)
    view = _view(
        discards=((), (), (), (Tile("1w"),)),
        melds=((), (chi,), (peng,), ()),
        claims=(
            PublicClaimEvidence(1, 0, 0, Tile("2w"), "assumed", False),
            PublicClaimEvidence(2, 0, 0, Tile("1w"), "assumed", False),
        ),
    )
    assert _counts(view, "1w") == (None, None, "unknown")


def test_mixed_retention_does_not_match_removed_claim_to_old_same_code_discard():
    """同码旧河牌仍在，新碰移河；另一碰留河使总守恒差为一。"""

    one_peng = PublicMeld(1, "peng", (Tile("1w"),) * 3, 0)
    two_peng = PublicMeld(2, "peng", (Tile("2w"),) * 3, 0)
    view = _view(
        discards=((Tile("1w"), Tile("2w")), (), (), ()),
        melds=((), (one_peng,), (two_peng,), ()),
        hand_counts=(13, 10, 10, 13), wall=83,
        claims=(
            PublicClaimEvidence(1, 0, 0, Tile("1w"), "assumed", False),
            PublicClaimEvidence(2, 0, 0, Tile("2w"), "assumed", True),
        ),
    )
    assert _counts(view, "1w") == (4, 0, "exact")
    assert _counts(view, "2w") == (3, 1, "exact")


def test_mixed_retention_without_claim_identity_is_conservative():
    one_peng = PublicMeld(1, "peng", (Tile("1w"),) * 3, 0)
    two_peng = PublicMeld(2, "peng", (Tile("2w"),) * 3, 0)
    view = _view(
        discards=((Tile("1w"), Tile("2w")), (), (), ()),
        melds=((), (one_peng,), (two_peng,), ()),
        hand_counts=(13, 10, 10, 13), wall=83,
        claims=(PublicClaimEvidence(2, 0, 0, Tile("2w"), "assumed", True),),
    )
    assert _counts(view, "1w") == (4, 0, "conservative")


def test_global_retained_readout_without_claim_source_is_still_conservative():
    """守恒能证明总重叠，不能在缺供牌身份时指定哪张同码河牌。"""

    meld = PublicMeld(0, "peng", (Tile("1w"),) * 3, None)
    view = _view(discards=((), (Tile("1w"),), (), ()),
                 melds=((meld,), (), (), ()),
                 hand_counts=(10, 13, 13, 13), wall=84)
    assert _counts(view, "1w") == (4, 0, "conservative")


def test_explicit_retained_claim_missing_from_feeder_is_unknown():
    """明示留河却只有别座同码河牌，不能把别座牌充作领取重叠。"""

    meld = PublicMeld(1, "peng", (Tile("1w"),) * 3, 0)
    view = _view(discards=((), (), (Tile("1w"),), ()),
                 melds=((), (meld,), (), ()),
                 claims=(PublicClaimEvidence(1, 0, 0, Tile("1w"), "assumed", True),))
    assert _counts(view, "1w") == (None, None, "unknown")


def test_conflicting_claim_source_marks_affected_chi_codes_unknown():
    """吃牌供牌座位与上家规则冲突时，受影响牌码不能给伪精确容量。"""

    meld = PublicMeld(0, "chi", tuple(Tile(c) for c in ("1w", "2w", "3w")), 1)
    view = _view(melds=((meld,), (), (), ()))
    for code in ("1w", "2w", "3w"):
        assert _counts(view, code) == (None, None, "unknown")


def test_conflicting_instance_claim_evidence_is_unknown():
    meld = PublicMeld(0, "chi", tuple(Tile(c) for c in ("1w", "2w", "3w")), 3)
    view = _view(melds=((meld,), (), (), ()), claims=(
        PublicClaimEvidence(0, 0, 3, Tile("1w"), "assumed"),
        PublicClaimEvidence(0, 0, 3, Tile("3w"), "assumed"),
    ))
    assert _counts(view, "1w") == (None, None, "unknown")


def test_own_four_and_other_public_four_leave_zero_or_unknown_capacity():
    """本人四张、他家公开杠四张均拒绝再摸；任何第五张都显式未知。"""

    empty = _view()
    assert _counts(empty, "1w", concealed=("1w",) * 3, drawn="1w") == (0, 0, "exact")
    other_gang = PublicMeld(2, "gang_an", (Tile("2w"),) * 4, None)
    view = _view(melds=((), (), (other_gang,), ()))
    assert _counts(view, "2w") == (4, 0, "exact")
    assert _counts(view, "2w", drawn="2w") == (4, None, "unknown")


def test_concealed_gang_plus_river_is_a_fifth_public_tile_for_conditionals():
    """暗杠无供牌来源；同码河牌是确定的第五张，不能沿旧兼容值截为四。"""

    other_gang = PublicMeld(2, "gang_an", (Tile("2w"),) * 4, None)
    view = _view(discards=((Tile("2w"),), (), (), ()),
                 melds=((), (), (other_gang,), ()))
    assert _counts(view, "2w") == (None, None, "unknown")


def test_five_visible_discards_are_unknown_in_conditional_view():
    view = _view(discards=((Tile("3w"),) * 5, (), (), ()))
    assert _counts(view, "3w") == (None, None, "unknown")


def test_unknown_chain_piao_keeps_white_capacity_unknown():
    assert _counts(_view(), "白", chain_piao=None) == (0, None, "unknown")
