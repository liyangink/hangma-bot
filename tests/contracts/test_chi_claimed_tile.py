"""吃供牌贯穿官方事件、玩家观察和审计；v18 原文加合成缺史边界。"""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from hangma_bot.adapters.official.dto import parse_state_response
from hangma_bot.adapters.official.projector import observation, public_event
from hangma_bot.hangma import HangmaRules
from hangma_bot.hangma.interface import CandidateFactKind
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import PublicEvent
from hangma_bot.kernel.serialization import (
    observation_from_json,
    observation_to_json,
    public_event_to_json,
)

FIXTURE = Path(__file__).parents[1] / "fixtures/official/v18/action-chain/chi-gang-draw.json"


def chi_observation():
    """原样读取本人可见快照和吃事件，仅合成额外牌河交集与缺失前史。"""
    saved = json.loads(FIXTURE.read_text())
    raw = next(e for e in saved["events"] if e["type"] == "chi")
    parsed = parse_state_response({"events": [raw]}).events[0]
    snapshot = parse_state_response(saved["snapshots"]["2267"]).snapshot
    obs = observation(snapshot, (public_event(parsed),), "chi-claimed-contract")
    rivers = list(obs.discards)
    rivers[2] += (Tile("7t"),)
    return replace(obs, discards=tuple(rivers), consumed_seq=2267, history_complete=False)


def test_explicit_chi_claim_survives_audit_and_repairs_missing_history_facts():
    """相同吃组合和歧义牌河，只有官方供牌字段能在无弃牌前史时恢复牌效。"""
    obs = chi_observation()
    encoded = observation_to_json(obs)
    restored = observation_from_json(json.loads(json.dumps(encoded)))
    assert restored == obs
    assert encoded["public_history"][0]["claimed_tile"] == "9t"
    assert public_event_to_json(obs.public_history[0])["claimed_tile"] == "9t"
    assert restored.public_history[0].claimed_tile == Tile("9t")

    rules = HangmaRules(RuleConfig("chi-claimed-contract", 1, False))
    analysis = rules.analyze(restored)
    facts = next(c.facts for c in analysis.legal_candidates if c.action_key == "discard:白")
    assert facts.fact_kind is CandidateFactKind.HAND_PROGRESS
    assert next(t.remaining_estimate for t in facts.useful_tiles if t.code == "9t") == 3
    assert restored.history_complete is False

    # 旧审计仍可读取；不能凭三张牌的排列位置补出缺失供牌。
    encoded["public_history"][0].pop("claimed_tile")
    legacy = observation_from_json(encoded)
    assert legacy.public_history[0].claimed_tile is None
    degraded = rules.analyze(legacy)
    old_facts = next(c.facts for c in degraded.legal_candidates if c.action_key == "discard:白")
    assert old_facts.fact_kind is CandidateFactKind.ANALYSIS_FAILED
    assert {c.action_key for c in degraded.legal_candidates} == {
        c.action_key for c in analysis.legal_candidates
    }
    assert degraded.emergency_candidate == analysis.emergency_candidate


@pytest.mark.parametrize("claim", ["9t", 9, True, Tile("1w")])
def test_claimed_tile_rejects_invalid_type_or_tile_outside_combination(claim):
    with pytest.raises(ValueError, match="claimed_tile"):
        PublicEvent(7, "chi", 0, (Tile("7t"), Tile("8t"), Tile("9t")), claimed_tile=claim)


def test_claimed_tile_cannot_attach_to_another_event_or_unknown_seat():
    for kind, seat in (("tile_drawn", 0), ("chi", None)):
        with pytest.raises(ValueError, match="claimed_tile"):
            PublicEvent(7, kind, seat, (Tile("9t"),), claimed_tile=Tile("9t"))


@pytest.mark.parametrize("claim", [None, "9t", "1w", 9, True, {}])
def test_audit_claimed_tile_checks_supplied_value_and_accepts_null(claim):
    encoded = observation_to_json(chi_observation())
    encoded["public_history"][0]["claimed_tile"] = claim
    if claim is None or claim == "9t":
        decoded = observation_from_json(encoded)
        assert decoded.public_history[0].claimed_tile == (None if claim is None else Tile(claim))
    else:
        with pytest.raises(ValueError, match="claimed_tile"):
            observation_from_json(encoded)
