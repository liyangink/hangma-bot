"""公开自摸后继生产接口：规则边界、覆盖、确定性与资源回归。"""

from __future__ import annotations

import gc
import time
import tracemalloc
from dataclasses import replace

import pytest

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import (
    PublicSuccessorCoverage,
    PublicSuccessorEnvelopeKind,
)
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import (
    PlayerObservation,
    PublicDiscard,
    RulePublicState,
)


def _observation(**overrides) -> PlayerObservation:
    hand_codes = overrides.pop(
        "hand_codes",
        (
            "1w", "2w", "3w", "4w", "5w", "6w", "7w",
            "8w", "9w", "1b", "2b", "3b", "东",
        ),
    )
    values = dict(
        game_id="public-successor-test",
        seat=0,
        round_no=1,
        snapshot_seq=10,
        phase="draw",
        dealer_seat=0,
        turn_seat=0,
        responding_seats=(),
        my_hand=tuple(Tile(code) for code in hand_codes),
        drawn_tile=Tile("南"),
        discards=((), (), (), ()),
        melds=((), (), (), ()),
        hand_counts=(13, 13, 13, 13),
        last_discard=None,
        remaining_tile_count=60,
        scores=(0, 0, 0, 0),
        rule_state=RulePublicState(Tile("白"), False, 0, False),
        public_history=(),
    )
    values.update(overrides)
    return PlayerObservation(**values)


def _rules(*, you_cai_bi_kao: bool = False) -> HangmaRules:
    return HangmaRules(
        RuleConfig("public-successor-test", 1, you_cai_bi_kao)
    )


def test_all_34_positive_capacity_edges_include_non_useful_draws() -> None:
    """全 34 容量边不能再次退化成只枚举 useful_tiles。"""

    rules = _rules()
    observation = _observation()
    result = rules.analyze_public_self_draw_successors(observation)

    assert result.coverage is PublicSuccessorCoverage.COMPLETE
    assert result.roots
    root = next(item for item in result.roots if item.action_key == "discard:东")
    assert len(root.edges) == 34
    assert {edge.draw_tile.code for edge in root.edges} == {
        "1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w",
        "1b", "2b", "3b", "4b", "5b", "6b", "7b", "8b", "9b",
        "1t", "2t", "3t", "4t", "5t", "6t", "7t", "8t", "9t",
        "东", "南", "西", "北", "中", "发", "白",
    }
    assert any(not edge.is_currently_useful for edge in root.edges)
    assert root.edge_capacity_mask.bit_count() == len(root.edges)
    assert root.edge_capacity_total == sum(
        edge.draw_tile.remaining_estimate for edge in root.edges
    )


def test_complete_root_rejects_deleted_positive_capacity_edge() -> None:
    """容量承诺使策略侧能识别删边，不能把坏图当成较优搜索结果。"""

    root = _rules().analyze_public_self_draw_successors(_observation()).roots[0]
    with pytest.raises(ValueError, match="边集合与规则承诺不一致"):
        replace(root, edges=root.edges[1:])


def test_two_envelopes_preserve_drawn_only_and_full_discard_frontiers() -> None:
    rules = _rules()
    observation = _observation()
    result = rules.analyze_public_self_draw_successors(observation)
    edge = result.roots[0].edges[0]

    assert edge.restricted.kind is PublicSuccessorEnvelopeKind.RESTRICTED_DRAWN_ONLY
    assert edge.restricted.legal_discard_count == 1
    assert all(
        leaf.action_key == "discard:" + edge.draw_tile.code
        for leaf in edge.restricted.discard_frontier
    )
    assert edge.unrestricted.kind is PublicSuccessorEnvelopeKind.UNRESTRICTED
    assert edge.unrestricted.legal_discard_count >= edge.restricted.legal_discard_count
    assert len(edge.unrestricted.discard_frontier) <= edge.unrestricted.legal_discard_count


def test_future_concealed_gang_is_conditional_on_future_wall_gt_20() -> None:
    rules = _rules()
    observation = _observation(
        hand_codes=(
            "1w", "1w", "1w", "2w", "3w", "4w", "5w",
            "6w", "7w", "8w", "9w", "东", "南",
        ),
        drawn_tile=Tile("西"),
        remaining_tile_count=60,
    )
    result = rules.analyze_public_self_draw_successors(observation)
    root = next(item for item in result.roots if item.action_key == "discard:西")
    edge = next(item for item in root.edges if item.draw_tile.code == "1w")

    for envelope in (edge.restricted, edge.unrestricted):
        gang = next(item for item in envelope.gang_leaves if item.action_key == "gang:concealed:1w")
        assert gang.replacement_draw_unknown
        assert gang.requires_future_wall_gt20


def test_future_gang_is_absent_when_current_wall_is_already_reserved() -> None:
    rules = _rules()
    observation = _observation(
        hand_codes=(
            "1w", "1w", "1w", "2w", "3w", "4w", "5w",
            "6w", "7w", "8w", "9w", "东", "南",
        ),
        drawn_tile=Tile("西"),
        remaining_tile_count=20,
    )
    result = rules.analyze_public_self_draw_successors(observation)
    root = next(item for item in result.roots if item.action_key == "discard:西")
    edge = next(item for item in root.edges if item.draw_tile.code == "1w")
    assert not edge.restricted.gang_leaves
    assert not edge.unrestricted.gang_leaves


def test_future_gang_wall_boundary_21_excludes_and_22_keeps_condition() -> None:
    """下一次普通摸牌至少耗一张：当前 21 不可能，22 才可能未来 >20。"""

    hand_codes = (
        "1w", "1w", "1w", "2w", "3w", "4w", "5w",
        "6w", "7w", "8w", "9w", "东", "南",
    )
    rules = _rules()
    by_wall = {}
    for wall in (21, 22):
        observation = _observation(
            hand_codes=hand_codes,
            drawn_tile=Tile("西"),
            remaining_tile_count=wall,
        )
        result = rules.analyze_public_self_draw_successors(observation)
        root = next(item for item in result.roots if item.action_key == "discard:西")
        edge = next(item for item in root.edges if item.draw_tile.code == "1w")
        by_wall[wall] = edge.unrestricted.gang_leaves
    assert by_wall[21] == ()
    assert any(item.action_key == "gang:concealed:1w" for item in by_wall[22])


def test_response_window_explicitly_falls_back_to_v2() -> None:
    rules = _rules()
    observation = _observation(
        phase="response_peng",
        turn_seat=2,
        responding_seats=(0,),
        drawn_tile=None,
        last_discard=PublicDiscard(2, Tile("5w"), 9),
    )
    result = rules.analyze_public_self_draw_successors(observation)
    assert result.coverage is PublicSuccessorCoverage.UNAVAILABLE
    assert result.roots == ()
    assert result.issues[0].area == "public_successor.phase"
    assert "V2" in result.issues[0].reason


def test_you_cai_bi_kao_future_baotou_unknown_fails_closed() -> None:
    rules = _rules(you_cai_bi_kao=True)
    observation = _observation()
    result = rules.analyze_public_self_draw_successors(observation)
    assert result.coverage is PublicSuccessorCoverage.UNAVAILABLE
    assert result.roots == ()
    assert result.issues[0].area == "public_successor.you_cai_bi_kao"
    assert "爆头" in result.issues[0].reason


def test_white_and_seven_pairs_are_kept_in_rule_owned_leaf_facts() -> None:
    rules = _rules()
    observation = _observation(
        hand_codes=(
            "1w", "1w", "2w", "2w", "3w", "3w", "4w",
            "4w", "5w", "5w", "6w", "7w", "白",
        ),
        drawn_tile=Tile("东"),
    )
    result = rules.analyze_public_self_draw_successors(observation)
    assert result.coverage is PublicSuccessorCoverage.COMPLETE
    leaves = (
        leaf
        for root in result.roots
        for edge in root.edges
        for leaf in edge.unrestricted.discard_frontier
    )
    assert any(leaf.seven_pairs_shanten_after is not None for leaf in leaves)
    assert any(
        bool(leaf.useful_mask & (1 << 33))
        for leaf in (
            leaf
            for root in result.roots
            for edge in root.edges
            for leaf in edge.unrestricted.discard_frontier
        )
    )


def test_projection_is_deterministic_and_repeated_call_does_not_retain_objects() -> None:
    """相同输入逐字段相等；独立内存检查不混入性能计时。"""

    rules = _rules()
    observation = _observation(
        rule_state=RulePublicState(
            Tile("白"), False, 0, True, catch_play_owner_seat=1
        )
    )
    first = rules.analyze_public_self_draw_successors(observation)
    second = rules.analyze_public_self_draw_successors(observation)
    assert first == second
    del first, second

    tracemalloc.start()
    try:
        gc.collect()
        baseline, _ = tracemalloc.get_traced_memory()
        for _ in range(12):
            value = rules.analyze_public_self_draw_successors(observation)
            assert value.coverage is PublicSuccessorCoverage.COMPLETE
            del value
        gc.collect()
        retained, _ = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert retained - baseline < 256 * 1024


def test_repeated_single_root_runtime_stays_below_online_hard_limit() -> None:
    """默认 GC 开启的单根重复回归；226 窗 p99 门由证据脚本负责。"""

    assert gc.isenabled()
    rules = _rules()
    observation = _observation(
        rule_state=RulePublicState(
            Tile("白"), False, 0, True, catch_play_owner_seat=1
        )
    )
    elapsed = []
    for _ in range(8):
        started = time.perf_counter()
        result = rules.analyze_public_self_draw_successors(observation)
        elapsed.append((time.perf_counter() - started) * 1000.0)
        assert result.coverage is PublicSuccessorCoverage.COMPLETE
    assert max(elapsed) <= 500.0
