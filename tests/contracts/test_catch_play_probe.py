"""测试策略不能放开规则限制或以赛事、自由赛模式启动。"""

import pytest

from hangma_bot.bootstrap import runtime_config_from_mapping
from hangma_bot.hangma import HangmaRules
from hangma_bot.kernel.actions import Discard, Pass, Peng, Tile, WindowPhase
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import PublicDiscard, PublicEvent, RulePublicState
from hangma_bot.policy import CatchPlayProbePolicy, ComparableHeuristicPolicyV2
from tests.unit.policy.support import make_budget, make_observation, make_request, run_choose


@pytest.mark.parametrize("owner", [0, 1, None])
def test_circle_identity_remains_a_rule_constraint_when_probe_wants_to_peng(owner):
    history = () if owner is None else (
        PublicEvent(8, "tile_discarded", owner, (Tile("白"),), catch_play=True),
        PublicEvent(9, "tile_drawn", 3, ()),
        PublicEvent(10, "tile_discarded", 3, (Tile("东"),), catch_play=True),
    )
    observation = make_observation(
        phase="response_peng", turn_seat=3, responding_seats=(0,), consumed_seq=10,
        my_hand=tuple(Tile(code) for code in "东 东 1w 2w 3w 4w 5w 6w 7b 8b 9b 南 白".split()),
        last_discard=PublicDiscard(3, Tile("东"), 10),
        public_history=history, rule_state=RulePublicState(Tile("白"), False, 0, True),
    )
    rules = HangmaRules(RuleConfig("probe-contract", 1, False))
    request = make_request(observation, rules.analyze(observation), phase=WindowPhase.RESPONSE_PENG)
    plan = run_choose(CatchPlayProbePolicy(ComparableHeuristicPolicyV2(monotonic=lambda: 0)), request, make_budget())

    assert plan.candidates[0].action == (Peng(Tile("东")) if owner == 0 else Pass())
    assert all(rules.validate(observation, c.action).legal for c in plan.candidates)
    assert any(c.is_emergency for c in plan.candidates)


def test_held_white_cannot_override_other_owners_forced_nonwhite_draw():
    observation = make_observation(
        drawn_tile=Tile("北"),
        my_hand=tuple(Tile(code) for code in "东 东 1w 2w 3w 4w 5w 6w 7b 8b 9b 南 白".split()),
        public_history=(PublicEvent(9, "tile_discarded", 3, (Tile("白"),), catch_play=True),
                        PublicEvent(10, "tile_drawn", 0, (Tile("北"),))),
        rule_state=RulePublicState(Tile("白"), False, 0, True), consumed_seq=10,
    )
    rules = HangmaRules(RuleConfig("probe-contract", 1, False))
    request = make_request(observation, rules.analyze(observation))
    plan = run_choose(CatchPlayProbePolicy(ComparableHeuristicPolicyV2(monotonic=lambda: 0)), request, make_budget())
    assert plan.candidates[0].action == Discard(Tile("北"))
    assert all(c.action != Discard(Tile("白")) for c in plan.candidates)


@pytest.mark.parametrize("mode,token_kind", [
    ("test_tournament", "test"), ("official_tournament", "official"), ("auto_match", "official"),
])
def test_probe_strategy_is_rejected_outside_test_room(mode, token_kind):
    with pytest.raises(ValueError, match="仅允许 mode=test_room"):
        runtime_config_from_mapping({
            "mode": mode, "token_kind": token_kind, "token": "fake-test-token",
            "base_url": "https://platform.invalid", "expected_tournament_id": "test-only",
            "known_guide_version": 23, "audit_root": "/tmp/probe-contract",
            "strategy": "catch_play_probe",
        })
