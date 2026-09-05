"""历史完整请求的 V0 回归；事实从固定输入读取，不随当前规则重算。"""

from dataclasses import asdict
import json
from pathlib import Path

import pytest

from hangma_bot.hangma.interface import CandidateFacts, CandidateFactKind, RuleCandidate, RuleAnalysis, RuleCompleteness, RuleIssue, UsefulTileFact
from hangma_bot.kernel.actions import WindowPhase
from hangma_bot.kernel.serialization import observation_from_json, action_from_json
from hangma_bot.policy import WeightedHeuristicPolicy, ReliableHeuristicPolicyV1
from .support import make_request, make_budget, run_choose

FIXTURE = Path(__file__).resolve().parents[2] / 'fixtures/policy/v0-decisions.jsonl'


def recorded_candidate(data):
    """仅供测试恢复固定公开类型，不建立生产端第二套牌谱 codec。"""
    if data is None:
        return None
    facts = data['facts']
    if facts is not None:
        facts = dict(facts)
        facts['fact_kind'] = CandidateFactKind(facts['fact_kind'])
        facts['completeness'] = RuleCompleteness(facts['completeness'])
        facts['useful_tiles'] = tuple(UsefulTileFact(**u) for u in facts['useful_tiles'])
        facts = CandidateFacts(**facts)
    return RuleCandidate(action_from_json(data['action']),data['action_key'],tuple(data['evidence']),facts)


def recorded_request(row):
    rules = row['rules']
    analysis = RuleAnalysis(
        tuple(recorded_candidate(c) for c in rules['legal_candidates']),
        recorded_candidate(rules['emergency_candidate']),
        RuleCompleteness(rules['completeness']),rules['ruleset_version'],
        tuple(RuleIssue(**i) for i in rules['issues']),
    )
    return make_request(observation_from_json(row['observation']),analysis,phase=WindowPhase(row['phase']))


def rows():
    return [json.loads(line) for line in FIXTURE.read_text().splitlines()]


@pytest.mark.parametrize('row',rows(),ids=lambda r:r['name'])
def test_frozen_v0_plan_is_unchanged(row):
    request = recorded_request(row)
    plan = run_choose(WeightedHeuristicPolicy(monotonic=lambda:0),request,make_budget())
    assert json.loads(json.dumps(asdict(plan),ensure_ascii=False,allow_nan=False)) == row['expected_plan']


@pytest.mark.parametrize('row',[r for r in rows() if r['complete_facts']],ids=lambda r:r['name'])
def test_v1_keeps_baseline_scores_for_complete_real_requests(row):
    request = recorded_request(row)
    plan = run_choose(ReliableHeuristicPolicyV1(monotonic=lambda:0),request,make_budget())
    assert [(c.action_key,c.total_score) for c in plan.candidates] == [
        (c['action_key'],c['total_score']) for c in row['expected_plan']['candidates']
    ]
