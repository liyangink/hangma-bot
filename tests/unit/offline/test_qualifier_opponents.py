"""海选弱对手代理的公开接口测试；结构夹具不冒充服务端一致性证据。"""
import asyncio
from dataclasses import replace

import pytest

from hangma_bot.kernel.actions import Discard, Hu, Pass, Peng, Tile, WindowPhase
from hangma_bot.offline.qualifier_opponents import AutomaticLikePolicy, freeze_qualifier_compositions
from tests.unit.policy.support import candidates_for, make_budget, make_observation, make_request, make_rules, rejected


def choose(obs, actions, *, rejected_keys=(), phase=WindowPhase.DRAW):
    candidates = candidates_for(actions)
    request = make_request(obs, make_rules(candidates, emergency=candidates[-1]),
                           rejected=tuple(rejected(k) for k in rejected_keys), phase=phase)
    return asyncio.run(AutomaticLikePolicy().choose(request, make_budget()))


def test_separate_drawn_white_is_discarded_instead_of_protected():
    obs = make_observation(my_hand=(Tile("1w"),) * 13, drawn_tile=Tile("白"))
    plan = choose(obs, (Discard(Tile("1w")), Discard(Tile("白"))))
    assert plan.candidates[0].action_key == "discard:白"
    assert {c.action_key for c in plan.candidates} == {"discard:1w", "discard:白"}
    assert all(c.action_key != "hu" for c in plan.candidates)


def test_already_in_hand_drawn_metadata_does_not_duplicate_the_tile():
    obs = make_observation(my_hand=(Tile("1w"),) * 13 + (Tile("2w"),), drawn_tile=Tile("1w"))
    assert choose(obs, (Discard(Tile("1w")), Discard(Tile("2w")))).candidates[0].action_key == "discard:2w"


def test_already_in_hand_preserves_observed_order_not_canonical_max():
    obs = make_observation(my_hand=(Tile("白"),) + (Tile("2w"),) * 12 + (Tile("1w"),))
    assert choose(obs, (Discard(Tile("1w")), Discard(Tile("白")))).candidates[0].action_key == "discard:1w"


def test_legal_hu_wins_over_discard_even_for_white():
    obs = make_observation(my_hand=(Tile("1w"),) * 13, drawn_tile=Tile("白"))
    assert choose(obs, (Discard(Tile("白")), Hu())).candidates[0].action_key == "hu"


def test_response_pass_does_not_claim():
    obs = make_observation(phase="response_peng", responding_seats=(0,))
    plan = choose(obs, (Peng(Tile("1w")), Pass()), phase=WindowPhase.RESPONSE_PENG)
    assert plan.candidates[0].action_key == "pass"
    assert len(plan.candidates) == 2


def test_rejected_hu_cannot_reappear():
    obs = make_observation(my_hand=(Tile("1w"),) * 14)
    plan = choose(obs, (Discard(Tile("1w")), Hu()), rejected_keys=("hu",))
    assert [c.action_key for c in plan.candidates] == ["discard:1w"]
    assert plan.revision == 2


def test_missing_rightmost_legal_action_exposes_failure_not_strong_fallback():
    obs = make_observation(my_hand=(Tile("1w"),) * 13, drawn_tile=Tile("白"))
    with pytest.raises(ValueError, match="期望动作"):
        choose(obs, (Discard(Tile("1w")),))


@pytest.mark.parametrize("fraction", [True, -0.1, 1.1, float("nan"), float("inf")])
def test_bad_composition_fraction_rejected(fraction):
    with pytest.raises(ValueError):
        freeze_qualifier_compositions([{"root_id": "x", "seed": 1}], fraction)


def test_three_independent_slots_paired_and_ratio_sensitivity_monotonic():
    roots = [{"root_id": f"r:{i}", "seed": i} for i in range(1000)]
    low = freeze_qualifier_compositions(roots, 0.5)
    mid = freeze_qualifier_compositions(roots, 0.6)
    high = freeze_qualifier_compositions(roots, 0.75)
    assert mid == freeze_qualifier_compositions(roots, 0.6)
    assert all(a["draw_uniforms"] == b["draw_uniforms"] == c["draw_uniforms"] for a,b,c in zip(low,mid,high))
    assert all(a["actual_weak_count"] <= b["actual_weak_count"] <= c["actual_weak_count"] for a,b,c in zip(low,mid,high))
    assert {r["actual_weak_count"] for r in mid} == {0, 1, 2, 3}
    assert {t for r in mid for t in r["opponent_types_logical_1_2_3"]} == {"automatic_like", "normal_v0", "r18"}
    assert all(r["paired_A_C_same_composition"] for r in mid)


def test_duplicate_root_rejected_before_execution():
    with pytest.raises(ValueError, match="重复"):
        freeze_qualifier_compositions([{"root_id": "x", "seed": 1}] * 2, 0.6)
