"""官方v34真实快照流 → 正式规则与模型；不把事件归档覆盖当准入条件。"""
import json
from pathlib import Path
import time

import pytest

pytest.importorskip("torch")

from hangma_bot.adapters.official.dto import parse_state_response
from hangma_bot.adapters.official.sync_state import ProtocolSyncState, SyncDecision
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import RuleCompleteness
from hangma_bot.kernel.config import RuleConfig, TimingConfig
from hangma_bot.learning.sequence_model_artifact import load_sequence_model
from hangma_bot.policy.interface import DecisionBudget
from hangma_bot.policy.sequence_model_policy import SequenceModelPolicy
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2
from hangma_bot.policy.safe_fallback import SafeFallbackPolicy
from tests.unit.policy.support import make_request

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads((ROOT / "tests/fixtures/official/v34/snapshot-model-input.json").read_text())


@pytest.mark.asyncio
@pytest.mark.parametrize("candidate", ("2048-projected", "4096-direct", "4096-projected"))
@pytest.mark.parametrize("case", FIXTURE["cases"], ids=lambda case: case["name"])
async def test_official_snapshot_stream_reaches_actual_model(candidate, case):
    """首弃已由快照吸收时三份原权重照常排序，不改标志或伪造事件。"""
    state = ProtocolSyncState(case["game_id"], TimingConfig(1., 1., 3.))
    for capture in case["responses"]:
        response = parse_state_response(capture["response"])
        if response.snapshot is not None:
            state.apply_full_snapshot(response.snapshot, events=response.events)
        else:
            events = response.events
            if 0 < capture["requested_seq"] < state.last_seq:
                events = state.recover_snapshot_history(
                    events, after_seq=capture["requested_seq"], round_no=state.snapshot.round_no,
                )
            assert state.apply_events(events).decision is SyncDecision.ACCEPTED
    observation = state.current_observation()
    assert observation.phase == "draw" and observation.turn_seat == observation.seat
    assert observation.history_complete is False and not observation.observation_issues
    assert observation.round_no == (1 if case["name"] == "first_hand" else 2)
    network, artifact = load_sequence_model(ROOT / "prebuilt/sequence-policy-models" / candidate)
    config = RuleConfig(**artifact.rule_config)
    analysis = HangmaRules(config).analyze(observation)
    assert analysis.completeness is RuleCompleteness.COMPLETE
    assert len(analysis.legal_candidates) > 1
    request = make_request(observation, analysis)
    policy = SequenceModelPolicy(
        baseline=ComparableHeuristicPolicyV2(), fallback=SafeFallbackPolicy(),
        network=network, artifact=artifact, runtime_rules=config, monotonic=time.monotonic,
    )
    now = time.monotonic()
    plan = await policy.choose(request, DecisionBudget(now + 30., now + 40., now + 50.))
    assert plan.degraded_reasons == ()
    assert all(c.score_parts[0].name == "sequence_model_logit" for c in plan.candidates)
    assert {c.action_key for c in plan.candidates} == {c.action_key for c in analysis.legal_candidates}
    assert request.observation == observation
