"""C_draft_M0 的全动作机械接缝与明确的未校准估值状态。"""

import gzip
import json
from dataclasses import replace

import pytest

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.hangma.interface import RuleIssue
from hangma_bot.hangma.route_frontier import RouteGapKind
from hangma_bot.kernel.actions import WindowPhase
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.serialization import observation_from_json
from hangma_bot.policy.route_vip_draft import RouteDraftError, RouteVipDraftPolicy
from hangma_bot.policy.interface import ScorePart

from .support import make_budget, make_request, rejected, run_choose


@pytest.fixture(scope="module")
def representative_windows():
    """冻结教师账中的行动前观察只作规则/策略接口样本，不读取结局。"""

    path = ("review/vip-route-2026-09-30/evidence/"
            "p3-all-action-teacher-20260930/report.json.gz")
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        rows = json.load(handle)["rows"]
    selected = {}
    for row in rows:
        for action_key in row["legal_action_keys"]:
            family = action_key.split(":")[0]
            if family not in selected:
                selected[family] = row["observation"]
    assert set(selected) == {"discard", "hu", "pass", "chi", "peng", "gang"}
    return selected


@pytest.mark.parametrize("family", ("discard", "hu", "pass", "chi", "peng", "gang"))
def test_all_normal_action_families_have_complete_ranked_plan(representative_windows, family):
    """六族均来自同次规则合法候选；未来估值不冒充精确概率。"""

    observation = observation_from_json(representative_windows[family])
    analysis = HangmaRules(RuleConfig("hangma-mvp-v10-public-counts", 1, False)).analyze(
        observation, route_limits=ValueAnalysisLimits(max_expansions=8192))
    plan = run_choose(RouteVipDraftPolicy(), make_request(
        observation, analysis, phase=WindowPhase(observation.phase)), make_budget())
    assert {item.action_key for item in plan.candidates} == {
        item.action_key for item in analysis.legal_candidates}
    assert [item.rank for item in plan.candidates] == list(range(1, len(plan.candidates) + 1))
    assert any(item.action_key.startswith(family) for item in plan.candidates)
    assert all(item.total_score == pytest.approx(
        sum(part.value for part in item.score_parts)) for item in plan.candidates)
    assert all(item.score_trace["competition"]["stage_no"] is None
               for item in plan.candidates)
    assert all(item.score_trace["value_status"] in ("exact", "uncalibrated_tail")
               for item in plan.candidates)


def test_competition_context_is_audited_without_changing_ranking(representative_windows):
    """首版即携带赛事事实，但名次压力不改变同一牌况的动作顺序。"""

    observation = observation_from_json(representative_windows["hu"])
    rules = HangmaRules(RuleConfig("hangma-mvp-v10-public-counts", 1, False)).analyze(
        observation, route_limits=ValueAnalysisLimits(max_expansions=8192))
    base = make_request(observation, rules)
    pressured = replace(base, competition=replace(
        base.competition, stage_no=3, stage_role="final", participant_rank=4,
        observed_at_unix_ms=123456,
    ))
    policy = RouteVipDraftPolicy()
    before = run_choose(policy, base, make_budget())
    after = run_choose(policy, pressured, make_budget())
    assert [(item.action_key, item.total_score) for item in before.candidates] == [
        (item.action_key, item.total_score) for item in after.candidates]
    assert all(item.score_trace["competition"]["participant_rank"] == 4
               for item in after.candidates)


def test_mechanical_gap_is_not_masked_by_rejected_action(representative_windows):
    """同次任一正常根故障均须停机，不能靠其余合法动作算成完整覆盖。"""

    observation = observation_from_json(representative_windows["peng"])
    rules = HangmaRules(RuleConfig("hangma-mvp-v10-public-counts", 1, False)).analyze(
        observation, route_limits=ValueAnalysisLimits(max_expansions=8192))
    root = rules.conditional_roots[0]
    broken = replace(root, gap_kind=RouteGapKind.MECHANICAL_GAP,
                     issues=(RuleIssue("test", "人工机械缺口"),))
    changed = replace(rules, conditional_roots=(broken,) + rules.conditional_roots[1:])
    with pytest.raises(RouteDraftError) as error:
        run_choose(RouteVipDraftPolicy(), make_request(
            observation, changed, rejected=(rejected(root.action_key),),
            phase=WindowPhase(observation.phase)), make_budget())
    assert error.value.category == "MECHANICAL_GAP"
    assert error.value.action_key == root.action_key


def test_floating_point_near_tie_prefers_confirmed_hu(representative_windows):
    """约 1e-12 的代理尾差不能冒充继续的真实积分优势。"""

    observation = observation_from_json(representative_windows["hu"])
    rules = HangmaRules(RuleConfig("hangma-mvp-v10-public-counts", 1, False)).analyze(
        observation, route_limits=ValueAnalysisLimits(max_expansions=8192))
    exact = next(root.settlement.score_delta[observation.seat]
                 for root in rules.conditional_roots if root.action_key == "hu")
    policy = RouteVipDraftPolicy()
    policy._one_draw._score_discard = lambda request, root: (
        (ScorePart("test_near_tie", float(exact) + 1e-12),), ())
    plan = run_choose(policy, make_request(observation, rules), make_budget())
    assert plan.candidates[0].action_key == "hu"
