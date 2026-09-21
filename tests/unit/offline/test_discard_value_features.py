from __future__ import annotations

import json
from dataclasses import replace

import pytest

from hangma_bot.hangma.interface import (
    CandidateFactKind,
    CandidateFacts,
    RuleAnalysis,
    RuleCandidate,
    RuleCompleteness,
    UsefulTileFact,
)
from hangma_bot.kernel.actions import Discard, Pass, Tile, WindowKey, WindowPhase
from hangma_bot.kernel.observation import (
    CompetitionContext,
    PlayerObservation,
    RulePublicState,
)
from hangma_bot.offline.discard_value_features import (
    SCHEMA,
    encode_discard_value_features,
)
from hangma_bot.policy.interface import DecisionRequest


def _tile(code: str) -> Tile:
    return Tile(code)


def _request(seat: int = 0, remaining: int | None = 40) -> DecisionRequest:
    observation = PlayerObservation(
        game_id="hidden-game-id",
        seat=seat,
        round_no=2,
        snapshot_seq=11,
        phase="draw",
        dealer_seat=(seat + 1) % 4,
        turn_seat=seat,
        responding_seats=(),
        my_hand=tuple(_tile(code) for code in (
            "1w", "1w", "2w", "3w", "4w", "5b", "5b",
            "6b", "7b", "2t", "3t", "4t", "白", "白",
        )),
        drawn_tile=_tile("白"),
        discards=((), (), (), ()),
        melds=((), (), (), ()),
        hand_counts=(14, 13, 13, 13),
        last_discard=None,
        remaining_tile_count=remaining,
        scores=(7, 2, -3, -6),
        rule_state=RulePublicState(
            wealth_god=_tile("白"), baotou=False, chain_count=0,
            catch_play=False, catch_play_owner_seat=None,
        ),
        public_history=(),
        consumed_seq=11,
        history_complete=True,
        chain_piao=None,
        gang_draw=None,
        observation_issues=(),
    )
    discard = RuleCandidate(
        action=Discard(_tile("1w")),
        action_key="discard:1w",
        evidence=("test",),
        facts=CandidateFacts(
            fact_kind=CandidateFactKind.HAND_PROGRESS,
            shanten_after=1,
            useful_tiles=(UsefulTileFact("5w", 3), UsefulTileFact("8b", 2)),
            best_followup_discard=None,
            standard_shanten_after=1,
            seven_pairs_shanten_after=2,
            standard_useful_tiles=(UsefulTileFact("5w", 3),),
            seven_pairs_useful_tiles=(UsefulTileFact("8b", 2),),
        ),
    )
    rules = RuleAnalysis(
        legal_candidates=(discard, RuleCandidate(Pass(), "pass", ("test",))),
        emergency_candidate=None,
        completeness=RuleCompleteness.COMPLETE,
        ruleset_version="hangma-v8",
        issues=(),
    )
    return DecisionRequest(
        observation=observation,
        competition=CompetitionContext(
            tournament_id="hidden-tournament-id",
            stage_no=None,
            stage_role=None,
            stage_total=None,
            participant_rank=None,
            ranking=(),
            observed_at_unix_ms=1_800_000_000_000,
        ),
        rules=rules,
        decision_id="hidden-decision-id",
        trigger_seq=11,
        window_key=WindowKey(
            game_id=observation.game_id,
            round_no=2,
            trigger_seq=11,
            phase=WindowPhase.DRAW,
            seat=seat,
        ),
        rejected_attempts=(),
    )


def test_discard_encoder_is_stable_and_excludes_identity() -> None:
    encoded = encode_discard_value_features(_request(), "discard:1w")

    assert encoded["schema"] == SCHEMA
    assert encoded["discard"]["kind"] == "discard"
    assert encoded["discard"]["tile"] == 0
    rendered = json.dumps(encoded, ensure_ascii=False, sort_keys=True)
    assert json.loads(rendered) == encoded
    for forbidden in (
        "hidden-game-id", "hidden-tournament-id", "hidden-decision-id",
        "1800000000000",
    ):
        assert forbidden not in rendered


def test_discard_encoder_keeps_unknown_distinct_from_zero() -> None:
    unknown = encode_discard_value_features(_request(remaining=None), "discard:1w")
    zero = encode_discard_value_features(_request(remaining=0), "discard:1w")

    assert unknown["observation"]["remaining_tile_count"] == {
        "known": False, "value": None,
    }
    assert zero["observation"]["remaining_tile_count"] == {
        "known": True, "value": 0,
    }


def test_discard_encoder_rejects_absent_or_non_discard_action() -> None:
    request = _request()
    with pytest.raises(ValueError, match="不属于当前规则合法候选"):
        encode_discard_value_features(request, "discard:9w")
    with pytest.raises(ValueError, match="只接受合法弃牌"):
        encode_discard_value_features(request, "pass")


def test_discard_encoder_is_invariant_to_irrelevant_request_identity() -> None:
    original = encode_discard_value_features(_request(), "discard:1w")
    changed = replace(
        _request(), decision_id="other", trigger_seq=999,
        competition=replace(_request().competition, tournament_id="other"),
    )

    assert encode_discard_value_features(changed, "discard:1w") == original
