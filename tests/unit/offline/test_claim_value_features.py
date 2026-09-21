from __future__ import annotations

import json
from dataclasses import replace

import pytest

from hangma_bot.hangma.interface import (
    CandidateFactKind,
    CandidateFacts,
    FollowupBranchFacts,
    RuleAnalysis,
    RuleCandidate,
    RuleCompleteness,
    UsefulTileFact,
)
from hangma_bot.kernel.actions import Chi, Pass, Peng, Tile, WindowKey, WindowPhase
from hangma_bot.kernel.observation import (
    CompetitionContext,
    PlayerObservation,
    PublicDiscard,
    PublicEvent,
    PublicMeld,
    RankingEntry,
    RulePublicState,
)
from hangma_bot.offline.claim_value_features import SCHEMA, encode_claim_value_features
from hangma_bot.policy.interface import DecisionRequest


def _tile(code: str) -> Tile:
    return Tile(code)


def _rotate(values: tuple, offset: int) -> tuple:
    """把相对 0—3 的四家向量放到绝对 focal 起点。"""

    result = [None] * 4
    for relative, value in enumerate(values):
        result[(offset + relative) % 4] = value
    return tuple(result)


def _request(focal_seat: int = 0, remaining: int | None = 42) -> DecisionRequest:
    discards = _rotate(
        ((_tile("1w"),), (_tile("2w"),), (_tile("3w"),), (_tile("4w"),)),
        focal_seat,
    )
    melds = _rotate(
        (
            (),
            (PublicMeld(
                seat=(focal_seat + 1) % 4,
                kind="peng",
                tiles=(_tile("东"), _tile("东"), _tile("东")),
                from_seat=(focal_seat + 3) % 4,
            ),),
            (),
            (),
        ),
        focal_seat,
    )
    observation = PlayerObservation(
        game_id="must-not-appear",
        seat=focal_seat,
        round_no=3,
        snapshot_seq=18,
        phase="response_chi",
        dealer_seat=(focal_seat + 2) % 4,
        turn_seat=(focal_seat + 1) % 4,
        responding_seats=(focal_seat,),
        my_hand=tuple(_tile(code) for code in (
            "1w", "1w", "2w", "3w", "5b", "5b", "6b", "7b", "2t", "3t", "4t", "白", "白"
        )),
        drawn_tile=None,
        discards=discards,
        melds=melds,
        hand_counts=_rotate((13, 10, 13, 13), focal_seat),
        last_discard=PublicDiscard(
            seat=(focal_seat + 3) % 4, tile=_tile("2w"), seq=18
        ),
        remaining_tile_count=remaining,
        scores=_rotate((12, -4, 7, 5), focal_seat),
        rule_state=RulePublicState(
            wealth_god=_tile("白"),
            baotou=False,
            chain_count=1,
            catch_play=True,
            catch_play_owner_seat=(focal_seat + 1) % 4,
        ),
        public_history=(
            PublicEvent(
                seq=18,
                kind="discard",
                seat=(focal_seat + 3) % 4,
                tiles=(_tile("2w"),),
                result_scores=_rotate((1, -1, 0, 0), focal_seat),
            ),
        ),
        consumed_seq=18,
        history_complete=True,
        chain_piao=1,
        gang_draw=None,
        observation_issues=("public-history-partial-before-snapshot",),
    )
    followup = FollowupBranchFacts(
        followup_key="chi:1w,2w,3w#5b",
        followup_discard="5b",
        combined_shanten=0,
        standard_shanten_after=0,
        seven_pairs_shanten_after=None,
        useful_tiles=(UsefulTileFact("4t", 3),),
        support_remaining=3,
    )
    chi = RuleCandidate(
        action=Chi((_tile("1w"), _tile("2w"), _tile("3w"))),
        action_key="chi:1w,2w,3w",
        evidence=("test",),
        facts=CandidateFacts(
            fact_kind=CandidateFactKind.HAND_PROGRESS,
            shanten_after=0,
            useful_tiles=(UsefulTileFact("4t", 3),),
            best_followup_discard="5b",
            standard_shanten_after=0,
            seven_pairs_shanten_after=None,
            standard_useful_tiles=(UsefulTileFact("4t", 3),),
            seven_pairs_useful_tiles=None,
            followup_branches=(followup,),
        ),
    )
    rules = RuleAnalysis(
        legal_candidates=(
            RuleCandidate(Pass(), "pass", ("test",)),
            chi,
        ),
        emergency_candidate=None,
        completeness=RuleCompleteness.COMPLETE,
        ruleset_version="hangma-v8",
        issues=(),
    )
    competition = CompetitionContext(
        tournament_id="also-must-not-appear",
        stage_no=2,
        stage_role="qualifier",
        stage_total=3,
        participant_rank=2,
        ranking=(
            RankingEntry("opponent-id", 20, 3, 1, 4, 1),
            RankingEntry("self-id", 12, 2, 0, 4, 2),
        ),
        observed_at_unix_ms=1_800_000_000_000,
    )
    return DecisionRequest(
        observation=observation,
        competition=competition,
        rules=rules,
        decision_id="decision-must-not-appear",
        trigger_seq=18,
        window_key=WindowKey(
            game_id=observation.game_id,
            round_no=3,
            trigger_seq=18,
            phase=WindowPhase.RESPONSE_CHI,
            seat=focal_seat,
        ),
        rejected_attempts=(),
    )


def test_encoder_is_json_stable_and_excludes_identity_and_time() -> None:
    encoded = encode_claim_value_features(_request(), "chi:1w,2w,3w")

    assert encoded["schema"] == SCHEMA
    rendered = json.dumps(encoded, ensure_ascii=False, sort_keys=True)
    assert json.loads(rendered) == encoded
    for forbidden in (
        "must-not-appear",
        "also-must-not-appear",
        "decision-must-not-appear",
        "opponent-id",
        "self-id",
        "1800000000000",
    ):
        assert forbidden not in rendered


def test_encoder_is_invariant_to_absolute_seat_rotation() -> None:
    seat_zero = encode_claim_value_features(_request(0), "chi:1w,2w,3w")
    seat_two = encode_claim_value_features(_request(2), "chi:1w,2w,3w")

    assert seat_zero == seat_two
    assert seat_zero["observation"]["dealer_relative_seat"] == 2
    assert seat_zero["observation"]["scores"] == [12, -4, 7, 5]
    assert seat_zero["observation"]["melds"][1][0]["from_relative_seat"] == {
        "known": True,
        "value": 3,
    }


def test_encoder_preserves_unknown_instead_of_zero_filling() -> None:
    unknown = encode_claim_value_features(_request(remaining=None), "chi:1w,2w,3w")
    zero = encode_claim_value_features(_request(remaining=0), "chi:1w,2w,3w")

    assert unknown["observation"]["remaining_tile_count"] == {
        "known": False,
        "value": None,
    }
    assert zero["observation"]["remaining_tile_count"] == {
        "known": True,
        "value": 0,
    }
    assert unknown["claim"]["facts"]["seven_pairs_useful_tiles"]["known"] is False


def test_encoder_rejects_absent_or_non_claim_action() -> None:
    request = _request()
    with pytest.raises(ValueError, match="不属于当前规则合法候选"):
        encode_claim_value_features(request, "peng:白")
    with pytest.raises(ValueError, match="只接受合法吃或碰"):
        encode_claim_value_features(request, "pass")


def test_encoder_rejects_window_without_legal_pass() -> None:
    request = _request()
    no_pass = replace(
        request,
        rules=replace(request.rules, legal_candidates=request.rules.legal_candidates[1:]),
    )
    with pytest.raises(ValueError, match="存在合法 pass"):
        encode_claim_value_features(no_pass, "chi:1w,2w,3w")


def test_encoder_accepts_peng_and_keeps_action_tile() -> None:
    request = _request()
    peng = RuleCandidate(Peng(_tile("白")), "peng:白", ("test",))
    request = replace(
        request,
        rules=replace(
            request.rules,
            legal_candidates=(request.rules.legal_candidates[0], peng),
        ),
    )

    encoded = encode_claim_value_features(request, "peng:白")

    assert encoded["claim"]["kind"] == "peng"
    assert encoded["claim"]["tiles"] == [33]
