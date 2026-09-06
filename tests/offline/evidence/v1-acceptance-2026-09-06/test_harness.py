"""验证实验旁路保留真实策略行为，并保留可解码的分歧证据。"""

import asyncio
from collections import Counter
from dataclasses import replace
import importlib.util
from io import StringIO
import json
from pathlib import Path

import pytest

from hangma_bot.application.audit_codec import decision_request_from_json
from hangma_bot.policy import ReliableHeuristicPolicyV1, WeightedHeuristicPolicy
from tests.unit.policy.test_v0_baseline import recorded_request, rows
from tests.unit.policy.support import make_budget


spec = importlib.util.spec_from_file_location("v1_acceptance_harness", Path(__file__).with_name("run_seed.py"))
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)


@pytest.mark.parametrize("missing_facts", [False, True])
def test_shadow_returns_actual_plan_and_serializes_difference(missing_facts):
    request = recorded_request(rows()[0])
    if missing_facts:
        candidates = request.rules.legal_candidates
        request = replace(request, rules=replace(request.rules, legal_candidates=(
            replace(candidates[0], facts=None), *candidates[1:],
        )))
    actual = WeightedHeuristicPolicy(monotonic=lambda: 0)
    actual.policy_id = "v0"
    peer = ReliableHeuristicPolicyV1(monotonic=lambda: 0)
    peer.policy_id = "v1"
    stream = StringIO()
    counts = Counter()
    wrapped = harness.ComparedPolicy(actual, peer, lambda: 0, counts, stream)
    expected = asyncio.run(actual.choose(request, make_budget()))
    assert asyncio.run(wrapped.choose(request, make_budget())) == expected
    assert counts["compared_requests"] == 1
    if missing_facts:
        assert counts["candidate_fact:missing"] == 1
        assert counts["plan_differences"] == 1
        assert decision_request_from_json(json.loads(stream.getvalue())["request"]) == request
    else:
        assert counts["plan_differences"] == 0
        assert stream.getvalue() == ""


def test_peer_error_does_not_replace_actual_plan():
    class FailedPeer:
        policy_id = "failed"

        async def choose(self, request, budget):
            raise RuntimeError("injected")

    actual = WeightedHeuristicPolicy(monotonic=lambda: 0)
    actual.policy_id = "v0"
    request = recorded_request(rows()[0])
    counts = Counter()
    wrapped = harness.ComparedPolicy(actual, FailedPeer(), lambda: 0, counts, StringIO())
    expected = asyncio.run(actual.choose(request, make_budget()))
    assert asyncio.run(wrapped.choose(request, make_budget())) == expected
    assert counts["peer_errors"] == 1
