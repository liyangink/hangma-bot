"""跨快照链事实的行为回归；依据 v20 实测及已确认的飘/杠生命周期。"""

from dataclasses import replace

import pytest

from hangma_bot.hangma import observation_rules
from hangma_bot.kernel.actions import Chi, Discard, Gang, GangKind, Pass, Peng, Tile
from hangma_bot.kernel.observation import PlayerObservation, PublicDiscard, PublicMeld, RulePublicState


def tiles(*codes):
    return tuple(Tile(code) for code in codes)


def observation(**changes):
    values = dict(
        game_id="snapshot-chain", seat=0, round_no=2, snapshot_seq=80,
        consumed_seq=100, phase="response_peng", dealer_seat=1, turn_seat=3,
        responding_seats=(0, 1, 2), my_hand=tiles("9t", "9t", "9t", "1w", "2w", "3w", "4w", "5w", "6w", "7b", "8b", "9b", "白"),
        drawn_tile=None, discards=((), (), (), tiles("9t")), melds=((), (), (), ()),
        hand_counts=(13, 13, 13, 13), last_discard=PublicDiscard(3, Tile("9t"), 100),
        remaining_tile_count=60, scores=(0, 0, 0, 0),
        rule_state=RulePublicState(Tile("白"), False, 2, False),
        public_history=(), history_complete=False, chain_piao=1, gang_draw=False,
    )
    values.update(changes)
    return PlayerObservation(**values)


def gang_pair(kind=GangKind.EXPOSED, *, split_draw=False):
    """三种已确认杠的完整前后牌面；before 水位高于旧快照基线。"""
    before = observation()
    if kind is GangKind.CONCEALED:
        before = replace(before, phase="draw", turn_seat=0, responding_seats=(),
                         my_hand=before.my_hand + tiles("9t"), drawn_tile=Tile("9t"),
                         hand_counts=(14, 13, 13, 13), last_discard=None)
    elif kind is GangKind.ADDED:
        meld = PublicMeld(0, "peng", tiles("9t", "9t", "9t"), 3)
        before = replace(before, phase="draw", turn_seat=0, responding_seats=(),
                         my_hand=before.my_hand[3:] + tiles("9t"), drawn_tile=Tile("9t"),
                         hand_counts=(11, 13, 13, 13), last_discard=None,
                         melds=((meld,), (), (), ()))
    if split_draw and before.drawn_tile is not None:
        before = replace(before, my_hand=before.my_hand[:-1])
    gang = PublicMeld(0, "gang", tiles("9t", "9t", "9t", "9t"), None if kind is GangKind.CONCEALED else 3)
    after_hand = tiles("1w", "2w", "3w", "4w", "5w", "6w", "7b", "8b", "9b", "白")
    after = replace(before, snapshot_seq=102, consumed_seq=102, phase="draw",
                    turn_seat=0, responding_seats=(), drawn_tile=Tile("东"),
                    my_hand=after_hand if split_draw else after_hand + tiles("东"),
                    hand_counts=(11, 13, 13, 13), last_discard=None,
                    remaining_tile_count=59, melds=((gang,), (), (), ()),
                    rule_state=replace(before.rule_state, chain_count=3),
                    chain_piao=None, gang_draw=None)
    return before, after, Gang(Tile("9t"), kind)


def reconcile(before, after, action=None):
    return observation_rules.reconcile_observation(before, after, confirmed_action=action)


@pytest.mark.parametrize("kind", list(GangKind))
@pytest.mark.parametrize("split_draw", [False, True])
def test_confirmed_gang_reconciles_full_snapshot_without_events(kind, split_draw):
    before, after, action = gang_pair(kind, split_draw=split_draw)
    result = reconcile(before, after, action)
    assert (result.chain_piao, result.gang_draw) == (1, True)
    assert result.rule_state == after.rule_state
    assert result.public_history == after.public_history == ()
    assert result.history_complete is False
    assert result.snapshot_seq == result.consumed_seq == 102
    assert result.my_hand == after.my_hand


def test_confirmed_gang_does_not_guess_unknown_old_piao():
    before, after, action = gang_pair()
    result = reconcile(replace(before, chain_piao=None), after, action)
    assert result.chain_piao is None
    assert result.gang_draw is True


@pytest.mark.parametrize("kind,official_kind", [
    (GangKind.EXPOSED, "gang_ming"), (GangKind.CONCEALED, "gang_an"),
    (GangKind.ADDED, "gang_bu"),
])
def test_official_meld_kind_and_missing_optional_source_are_compatible(kind, official_kind):
    before, after, action = gang_pair(kind)
    meld = replace(after.melds[0][0], kind=official_kind, from_seat=None)
    after = replace(after, melds=((meld,), (), (), ()))
    result = reconcile(before, after, action)
    assert (result.chain_piao, result.gang_draw) == (1, True)


def test_confirmed_new_gang_with_official_zero_old_chain_can_prove_zero_piao():
    before, after, action = gang_pair()
    before = replace(before, rule_state=replace(before.rule_state, chain_count=0), chain_piao=None)
    after = replace(after, rule_state=replace(after.rule_state, chain_count=1))
    assert reconcile(before, after, action).chain_piao == 0


def test_new_gang_without_success_confirmation_stays_unknown():
    before, after, _ = gang_pair()
    result = reconcile(before, after)
    assert result.chain_piao is None
    assert result.gang_draw is None


@pytest.mark.parametrize("change", [
    dict(game_id="other-game"), dict(seat=1), dict(round_no=3), dict(dealer_seat=2),
    dict(snapshot_seq=99, consumed_seq=99), dict(snapshot_seq=100, consumed_seq=100),
    dict(snapshot_seq=101, consumed_seq=101), dict(consumed_seq=None),
    dict(my_hand=tiles("1w", "2w", "3w", "4w", "5w", "6w", "7b", "8b", "9b", "南", "东")),
    dict(my_hand=tiles("1w", "东")), dict(drawn_tile=Tile("南")),
    dict(drawn_tile=None), dict(turn_seat=1),
    dict(discards=(tiles("白"), (), (), tiles("9t"))),
    dict(melds=((), (), (), ())),
])
def test_gang_confirmation_requires_matching_identity_watermark_and_cards(change):
    before, after, action = gang_pair()
    result = reconcile(before, replace(after, **change), action)
    assert result.chain_piao is None
    assert result.gang_draw is not True


def test_gang_confirmation_checks_old_watermark_and_exact_chain_increment():
    before, after, action = gang_pair()
    for old in (replace(before, consumed_seq=None), replace(before, consumed_seq=102)):
        assert reconcile(old, after, action).chain_piao is None
    for count in (2, 4):
        wrong = replace(after, rule_state=replace(after.rule_state, chain_count=count))
        result = reconcile(before, wrong, action)
        assert result.chain_piao is None
        assert result.gang_draw is None


@pytest.mark.parametrize("kind", list(GangKind))
def test_gang_confirmation_requires_correct_meld_source_and_tiles(kind):
    before, after, action = gang_pair(kind)
    meld = after.melds[0][0]
    for wrong in (replace(meld, from_seat=2), replace(meld, tiles=tiles("9t", "9t", "9t")),
                  replace(meld, kind="peng"), replace(meld, seat=2)):
        result = reconcile(before, replace(after, melds=((wrong,), (), (), ())), action)
        assert (result.chain_piao, result.gang_draw) == (None, None)


def test_authoritative_facts_and_god_are_never_overwritten_or_mixed_with_conflict():
    before, after, action = gang_pair()
    explicit = replace(after, chain_piao=2)
    result = reconcile(before, explicit, action)
    assert result.chain_piao == 2
    assert result.gang_draw is None
    assert result.rule_state == explicit.rule_state
    result = reconcile(before, replace(after, gang_draw=False), action)
    assert result.gang_draw is False
    assert result.chain_piao is None


def test_unchanged_repeated_snapshot_preserves_piao_and_same_draw_source():
    before, after, action = gang_pair()
    known = reconcile(before, after, action)
    for seq in (102, 106):
        refreshed = replace(after, snapshot_seq=seq, consumed_seq=seq)
        result = reconcile(known, refreshed)
        assert (result.chain_piao, result.gang_draw) == (1, True)


@pytest.mark.parametrize("wall", [58, None])
def test_old_gang_draw_is_not_carried_to_unproven_later_draw(wall):
    _, after, _ = gang_pair()
    known = replace(after, chain_piao=1, gang_draw=True)
    refreshed = replace(after, snapshot_seq=120, consumed_seq=120, remaining_tile_count=wall)
    result = reconcile(known, refreshed)
    assert result.chain_piao == 1
    assert result.gang_draw is None


def test_same_watermark_with_changed_public_cards_cannot_carry_old_facts():
    _, after, _ = gang_pair()
    known = replace(after, chain_piao=1, gang_draw=True)
    refreshed = replace(after, remaining_tile_count=58)
    result = reconcile(known, refreshed)
    assert (result.chain_piao, result.gang_draw) == (None, None)


def test_piao_survives_later_normal_draw_without_inheriting_old_draw_source():
    before = observation()
    after = replace(before, snapshot_seq=111, consumed_seq=111, phase="draw", turn_seat=0,
                    my_hand=before.my_hand + tiles("东"), drawn_tile=Tile("东"),
                    remaining_tile_count=56, chain_piao=None, gang_draw=None)
    result = reconcile(before, after)
    assert result.chain_piao == 1
    assert result.gang_draw is None


def test_piao_survives_other_seats_moves_but_old_gang_draw_does_not():
    _, after, _ = gang_pair()
    known = replace(after, chain_piao=1, gang_draw=True)
    refreshed = replace(after, snapshot_seq=120, consumed_seq=120,
                        discards=((), tiles("7t"), (), tiles("9t")))
    result = reconcile(known, refreshed)
    assert result.chain_piao == 1
    assert result.gang_draw is None


def test_multiple_unobserved_own_actions_cannot_reuse_old_same_chain_count():
    _, after, _ = gang_pair()
    known = replace(after, chain_piao=1, gang_draw=True)
    refreshed = replace(after, snapshot_seq=150, consumed_seq=150,
                        discards=(tiles("白", "2w", "白"), (), (), tiles("9t")))
    result = reconcile(known, refreshed)
    assert (result.chain_piao, result.gang_draw) == (None, None)


def test_mismatched_confirmation_does_not_fall_back_to_unchanged_snapshot():
    _, after, action = gang_pair()
    known = replace(after, chain_piao=1, gang_draw=True)
    result = reconcile(known, after, action)
    assert (result.chain_piao, result.gang_draw) == (None, None)


@pytest.mark.parametrize("tile,baotou,old_piao,expected", [
    ("白", True, 1, (3, 2)), ("白", True, None, (3, None)),
    ("白", False, 1, (0, 0)), ("东", True, 1, (0, 0)),
    ("东", False, None, (0, 0)),
])
def test_confirmed_discard_uses_same_chain_lifecycle(tile, baotou, old_piao, expected):
    before = observation(phase="draw", turn_seat=0, responding_seats=(),
                         my_hand=observation().my_hand + tiles("东"), drawn_tile=Tile("东"),
                         chain_piao=old_piao, rule_state=RulePublicState(Tile("白"), baotou, 2, False))
    hand = list(before.my_hand)
    hand.remove(Tile(tile))
    after = replace(before, snapshot_seq=101, consumed_seq=101, phase="response_peng", turn_seat=0,
                    responding_seats=(1, 2, 3), my_hand=tuple(hand), drawn_tile=None,
                    discards=(tiles(tile), (), (), tiles("9t")),
                    last_discard=PublicDiscard(0, Tile(tile), 101),
                    rule_state=replace(before.rule_state, chain_count=expected[0], baotou=False),
                    chain_piao=None, gang_draw=None)
    result = reconcile(before, after, Discard(Tile(tile)))
    assert result.chain_piao == expected[1]
    assert result.gang_draw is False
    assert result.rule_state == after.rule_state


def test_unconfirmed_piao_or_wrong_discard_cards_remain_unknown():
    before = observation(phase="draw", turn_seat=0, my_hand=observation().my_hand + tiles("东"),
                         drawn_tile=Tile("东"), rule_state=RulePublicState(Tile("白"), True, 2, False))
    after = replace(before, snapshot_seq=101, consumed_seq=101, phase="response_peng", drawn_tile=None,
                    my_hand=before.my_hand[:-2] + tiles("东"), discards=(tiles("白"), (), (), tiles("9t")),
                    rule_state=replace(before.rule_state, chain_count=3), chain_piao=None, gang_draw=None)
    assert reconcile(before, after).chain_piao is None
    assert reconcile(before, after, Discard(Tile("东"))).chain_piao is None


@pytest.mark.parametrize("action", [Peng(Tile("9t")), Chi(tiles("7t", "8t", "9t"))])
def test_confirmed_claim_keeps_piao_without_becoming_replacement_draw(action):
    before = observation()
    hand = list(before.my_hand)
    if isinstance(action, Peng):
        taken = tiles("9t", "9t")
        meld_tiles = tiles("9t", "9t", "9t")
        kind = "peng"
    else:
        before = replace(before, phase="response_chi", responding_seats=(0,),
                         my_hand=tiles("7t", "8t") + before.my_hand[2:])
        hand = list(before.my_hand)
        taken = tiles("7t", "8t")
        meld_tiles, kind = action.tiles, "chi"
    for tile in taken:
        hand.remove(tile)
    meld = PublicMeld(0, kind, meld_tiles, 3)
    after = replace(before, snapshot_seq=101, consumed_seq=101, phase="draw", turn_seat=0,
                    responding_seats=(), my_hand=tuple(hand), drawn_tile=None,
                    melds=((meld,), (), (), ()), last_discard=None, chain_piao=None, gang_draw=None)
    result = reconcile(before, after, action)
    assert result.chain_piao == 1
    assert result.gang_draw is False
    wrong = replace(after, my_hand=after.my_hand[:-1] + tiles("南"))
    assert reconcile(before, wrong, action).chain_piao is None


def test_pass_without_a_new_own_action_keeps_piao_but_does_not_prove_a_new_draw():
    before = observation()
    after = replace(before, snapshot_seq=104, consumed_seq=104,
                    chain_piao=None, gang_draw=None)
    result = reconcile(before, after, Pass())
    assert (result.chain_piao, result.gang_draw) == (1, False)
