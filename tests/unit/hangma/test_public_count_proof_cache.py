"""公开计数重复历史解析的公开接缝回归；不缓存条件未见容量。"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import gc
from types import SimpleNamespace
import weakref

import pytest

import hangma_bot.hangma.public_tile_counts as counts_module
from hangma_bot.hangma.internal_types import TILE_INDEX
from hangma_bot.hangma.public_tile_counts import (
    PublicClaimEvidence,
    PublicTileView,
    count_public_tiles_from_view,
    count_unseen_tiles_from_view,
)
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.observation import PublicEvent, PublicMeld


def _view():
    shape = tuple(Tile(code) for code in ("1w", "2w", "3w"))
    history = (
        PublicEvent(1, "tile_discarded", 3, (Tile("3w"),)),
        PublicEvent(2, "chi", 0, shape),
    )
    return PublicTileView(
        discards=((), (), (), (Tile("3w"),)),
        melds=((PublicMeld(0, "chi", shape, 3),), (), (), ()),
        hand_counts=(10, 13, 13, 13), remaining_tile_count=84,
        public_history=history, snapshot_seq=0, consumed_seq=2,
    )


def _fact(view, code="3w", *, concealed=(), drawn=None, chain_piao=0):
    result = count_unseen_tiles_from_view(
        view, seat=0, concealed=tuple(Tile(code) for code in concealed),
        drawn_tile=Tile(drawn) if drawn else None, chain_piao=chain_piao,
    )
    index = TILE_INDEX[code]
    return result.public[index], result.unseen[index], result.evidence[index]


def _scan_counter(monkeypatch):
    """仅以扫描次数核工程工作量；所有正确性断言仍经过公开计数接缝。"""

    scans = []
    original = counts_module._scan_claim_proofs

    def record(history, watermark):
        scans.append((history, watermark))
        return original(history, watermark)

    monkeypatch.setattr(counts_module, "_scan_claim_proofs", record)
    return scans


def test_repeated_public_calls_reuse_history_but_recalculate_hidden_capacity(monkeypatch):
    view = _view()
    scans = _scan_counter(monkeypatch)
    assert _fact(view) == (1, 3, "exact")
    assert _fact(view, concealed=("3w",)) == (1, 2, "exact")
    assert _fact(view, drawn="3w") == (1, 2, "exact")
    assert _fact(view, concealed=("3w",) * 3, drawn="3w") == (1, None, "unknown")
    assert _fact(view, code="白", chain_piao=None) == (0, None, "unknown")
    assert _fact(view, code="白", chain_piao=2) == (0, 2, "exact")
    assert _fact(view) == (1, 3, "exact")
    assert len(scans) == 1


def test_equal_history_in_a_different_tuple_is_parsed_independently(monkeypatch):
    view = _view()
    copy = replace(view, public_history=tuple(list(view.public_history)))
    assert view.public_history == copy.public_history
    assert view.public_history is not copy.public_history
    scans = _scan_counter(monkeypatch)
    assert _fact(view) == _fact(copy) == (1, 3, "exact")
    assert len(scans) == 2


def test_effective_watermark_is_part_of_the_cache_key(monkeypatch):
    view = _view()
    scans = _scan_counter(monkeypatch)
    before_claim = replace(view, consumed_seq=1)
    snapshot_only = replace(view, snapshot_seq=2, consumed_seq=None)
    assert _fact(before_claim) == (2, 2, "conservative")
    assert _fact(view) == (1, 3, "exact")
    assert _fact(snapshot_only) == (1, 3, "exact")
    assert _fact(before_claim) == (2, 2, "conservative")
    assert len(scans) == 2


@pytest.mark.parametrize("problem", ["conflict", "reordered", "reset", "gap", "intervening_draw"])
def test_history_conflict_order_reset_and_gap_are_not_reused(problem):
    view = _view()
    discard, claim = view.public_history
    bad_histories = {
        "conflict": (discard, replace(discard, tiles=(Tile("2w"),)), claim),
        "reordered": (claim, discard),
        "reset": (discard, claim, PublicEvent(3, "round_started", None)),
        "gap": (discard, replace(claim, seq=3)),
        "intervening_draw": (discard, PublicEvent(2, "tile_drawn", 1), replace(claim, seq=3)),
    }
    bad = replace(view, public_history=bad_histories[problem], consumed_seq=3)
    assert _fact(view) == (1, 3, "exact")
    assert _fact(bad) == (2, 2, "conservative")
    assert _fact(bad) == (2, 2, "conservative")
    assert _fact(view) == (1, 3, "exact")


def test_duplicate_notifications_do_not_create_duplicate_claims():
    view = _view()
    discard, claim = view.public_history
    repeat = replace(view, public_history=(discard, discard, claim, claim))
    for _ in range(3):
        assert _fact(repeat) == (1, 3, "exact")


def test_filtering_and_consuming_proofs_cannot_modify_a_later_call():
    view = _view()
    shape = view.melds[0][0].tiles
    history = view.public_history + (
        PublicEvent(3, "tile_discarded", 3, (Tile("3w"),)),
        PublicEvent(4, "chi", 0, shape),
    )
    one_meld = replace(view, public_history=history, consumed_seq=4)
    two_melds = replace(
        one_meld, melds=((view.melds[0][0], view.melds[0][0]), (), (), ()),
        discards=((), (), (), (Tile("3w"), Tile("3w"))),
        hand_counts=(7, 13, 13, 13),
    )
    for _ in range(4):
        # 两条历史证据与一个副露对不上时，旧逻辑整组放弃证据。
        assert _fact(one_meld) == (2, 2, "conservative")
        assert _fact(two_melds) == (2, 2, "exact")


def test_changed_river_and_conservation_are_recomputed_with_shared_history():
    view = _view()
    removed = replace(view, discards=((), (), (), ()))
    unknown_wall = replace(view, remaining_tile_count=None)
    for _ in range(3):
        assert _fact(view) == (1, 3, "exact")
        assert _fact(removed) == (1, 3, "exact")
        assert _fact(unknown_wall) == (2, 2, "conservative")
    other_river = replace(removed, discards=((Tile("3w"),), (), (), ()))
    assert _fact(other_river) == (None, None, "unknown")


def test_direct_claim_evidence_and_conflicts_are_not_cached_as_history():
    view = _view()
    known = replace(view, remaining_tile_count=None, claim_evidence=(
        PublicClaimEvidence(0, 0, 3, Tile("3w"), "assumed", True),
    ))
    conflict = replace(known, claim_evidence=(
        PublicClaimEvidence(0, 0, 3, Tile("2w"), "assumed", True),
    ))
    for _ in range(3):
        assert _fact(known) == (1, 3, "exact")
        assert _fact(conflict) == (None, None, "unknown")
        assert _fact(view) == (1, 3, "exact")


def test_mutable_history_container_bypasses_reuse(monkeypatch):
    view = _view()
    history = list(view.public_history)
    mutable = replace(view, public_history=history)
    scans = _scan_counter(monkeypatch)
    assert _fact(mutable) == (1, 3, "exact")
    history.insert(1, replace(history[0], tiles=(Tile("2w"),)))
    assert _fact(mutable) == (2, 2, "conservative")
    history.pop(1)
    assert _fact(mutable) == (1, 3, "exact")
    assert len(scans) == 3


def test_mutable_event_object_in_tuple_bypasses_reuse(monkeypatch):
    view = _view()
    events = tuple(SimpleNamespace(**event.__dict__) for event in view.public_history)
    mutable = replace(view, public_history=events)
    scans = _scan_counter(monkeypatch)
    assert _fact(mutable) == (1, 3, "exact")
    events[0].tiles = (Tile("9w"),)
    assert _fact(mutable) == (2, 2, "conservative")
    events[0].tiles = (Tile("3w"),)
    assert _fact(mutable) == (1, 3, "exact")
    assert len(scans) == 3


def test_mutable_field_comparison_in_a_frozen_event_bypasses_reuse(monkeypatch):
    """事件本身 frozen 不足够；未被解析的终局明细也参与同 seq 冲突比较。"""

    class MutableText(str):
        def __new__(cls, value):
            instance = super().__new__(cls, value)
            instance.matches = True
            return instance

        def __eq__(self, other):
            return self.matches and str.__eq__(self, other)

    view = _view()
    text = MutableText("same")
    discard, claim = view.public_history
    mutable = replace(view, public_history=(
        replace(discard, result_details=(text,)),
        replace(discard, result_details=("same",)), claim,
    ))
    scans = _scan_counter(monkeypatch)
    assert _fact(mutable) == (1, 3, "exact")
    text.matches = False
    assert _fact(mutable) == (2, 2, "conservative")
    text.matches = True
    assert _fact(mutable) == (1, 3, "exact")
    assert len(scans) == 3


def test_cached_history_is_retained_until_bounded_eviction():
    """强引用防止 tuple 身份被回收复用；超过容量后旧事件可以被回收。"""

    view = _view()
    event_reference = weakref.ref(view.public_history[0])
    assert _fact(view) == (1, 3, "exact")
    del view
    gc.collect()
    assert event_reference() is not None
    for _ in range(9):
        other = _view()
        assert _fact(other) == (1, 3, "exact")
    gc.collect()
    assert event_reference() is None


def test_overlong_history_bypasses_reuse(monkeypatch):
    view = _view()
    history = view.public_history + tuple(PublicEvent(index, "pass", 1) for index in range(3, 4100))
    long = replace(view, public_history=history)
    scans = _scan_counter(monkeypatch)
    assert _fact(long) == _fact(long) == (1, 3, "exact")
    assert len(scans) == 2


def test_cache_eviction_does_not_change_public_results(monkeypatch):
    view = _view()
    scans = _scan_counter(monkeypatch)
    assert _fact(view) == (1, 3, "exact")
    for seq in range(3, 12):
        other = replace(view, public_history=view.public_history + (PublicEvent(seq, "pass", 1),))
        assert _fact(other) == (1, 3, "exact")
    assert _fact(view) == (1, 3, "exact")
    assert len(scans) == 11


def test_parallel_public_calls_keep_proofs_and_capacities_independent():
    view = _view()
    variants = [view, replace(view, remaining_tile_count=None), replace(view, discards=((), (), (), ()))]
    expected = [count_public_tiles_from_view(source) for source in variants]
    with ThreadPoolExecutor(max_workers=4) as executor:
        actual = list(executor.map(count_public_tiles_from_view, variants * 30))
    assert actual == expected * 30
