"""B3 全链装配测试：投影器字段完整性、DecisionPlan 契约与失败降级路径。

权威行为来自 SEARCH-SPACE-REDESIGN-2026-09-16.md §4.1（六步顺序）与
contracts/action-value-v1.json（rank/降级/不拼 V2）。choose 对外签名与
既有决策循环同构（support.run_choose），不改任何冻结契约。
"""

from __future__ import annotations

from typing import Optional

import pytest

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import (
    CandidateFactKind,
    CandidateFacts,
    CandidateValueFacts,
    FamilyId,
    FamilyProgress,
    FollowupBranchFacts,
    ProgressKind,
    RouteStatus,
    RuleCandidate,
    Settlement,
    UsefulTileFact,
    ValueAnalysisLimits,
    ValueConditions,
    ValueCoverage,
    ValueRoute,
)
from hangma_bot.kernel.actions import Discard, Hu, Pass, Tile
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import (
    PlayerObservation,
    PublicDiscard,
    RulePublicState,
)
from hangma_bot.policy.action_value import ActionScore, ScoreBatch
from hangma_bot.policy.action_value_executor import WorkloadExceeded
from hangma_bot.policy.action_value_policy import (
    VALUE_ANALYSIS_SEMANTICS_VERSION,
    ActionValuePolicy,
    build_scoring_view,
)
from hangma_bot.policy.interface import DecisionPlan

from .support import (
    make_budget,
    make_observation,
    make_request,
    make_rules,
    rejected,
    run_choose,
)


# ---------------------------------------------------------------------------
# 夹具：手构事实（字段完整性）与真实引擎载荷（B1 透传）
# ---------------------------------------------------------------------------


def _branch(discard, **overrides):
    base = dict(
        followup_key="peng:2b#" + discard,
        followup_discard=discard,
        combined_shanten=1,
        standard_shanten_after=1,
        seven_pairs_shanten_after=3,
        useful_tiles=(UsefulTileFact("3b", 3),),
        support_remaining=3,
    )
    base.update(overrides)
    return FollowupBranchFacts(**base)


def _progress(family, progress, **overrides):
    base = dict(
        family=family,
        progress=progress,
        route_status=RouteStatus.WITNESSED,
        basis="测试依据：唯一规则源分牌型距离",
    )
    base.update(overrides)
    return FamilyProgress(**base)


def _route():
    return ValueRoute(
        conditional_settlement=Settlement(
            score_delta=(8, -3, -3, -2), fan=4, details=("route-sample",)
        ),
        shanten=0,
        useful_tiles=(UsefulTileFact("3b", 3),),
        followup_discard="2b",
        conditions=ValueConditions(
            draw_kind="normal",
            pre_draw_hand=("1w", "2w", "3w", "4w", "5w", "6w", "7w",
                           "1b", "2b", "3b", "5t", "5t", "5t"),
            meld_count=0,
            chain_count=0,
            chain_piao=0,
            baotou=False,
        ),
    )


def _candidate_facts():
    return CandidateFacts(
        fact_kind=CandidateFactKind.HAND_PROGRESS,
        shanten_after=1,
        best_followup_discard="2b",
        followup_branches=(_branch("2b"), _branch("3b", combined_shanten=2)),
        family_progress=(
            _progress(FamilyId.BRANCH, ProgressKind.ADVANCE),
            _progress(FamilyId.FOUR_WHITE, ProgressKind.RETREAT),
        ),
    )


def _value_facts(*, with_immediate=False, with_routes=True):
    return CandidateValueFacts(
        immediate_settlement=(
            Settlement(score_delta=(8, -3, -3, -2), fan=4, details=("hu-sample",))
            if with_immediate else None
        ),
        routes=(_route(),) if with_routes else (),
        coverage=ValueCoverage.COMPLETE,
    )


def _candidate(key, action, *, facts=None, value_facts=None):
    return RuleCandidate(
        action=action, action_key=key, evidence=(),
        facts=facts, value_facts=value_facts,
    )


class TestBuildScoringView:
    """投影器：RuleAnalysis → ScoringView 的字段完整性与 B1 载荷透传。"""

    def _request(self, candidates, emergency=None):
        return make_request(make_observation(), make_rules(candidates, emergency))

    def test_projects_actions_sorted_with_payload_passthrough(self):
        discard = _candidate(
            "discard:1w", Discard(Tile("1w")),
            facts=_candidate_facts(), value_facts=_value_facts(),
        )
        hu = _candidate(
            "hu", Hu(),
            facts=CandidateFacts(
                fact_kind=CandidateFactKind.WIN, shanten_after=-1,
                family_progress=(_progress(FamilyId.CHAIN, ProgressKind.SAME),),
            ),
            value_facts=_value_facts(with_immediate=True, with_routes=False),
        )
        passthrough = _candidate("pass", Pass())  # facts=None → 载荷 None
        request = self._request((hu, discard, passthrough))  # 乱序输入
        view = build_scoring_view(request)
        assert [item.action_key for item in view.actions] == [
            "discard:1w", "hu", "pass",
        ]
        discard_view = view.actions[0]
        assert discard_view.followup_branches == discard.facts.followup_branches
        assert discard_view.routes == discard.value_facts.routes
        assert discard_view.immediate_settlement is None
        assert discard_view.family_progress == "ADVANCE"  # 显著性坍缩
        hu_view = view.actions[1]
        assert hu_view.immediate_settlement == hu.value_facts.immediate_settlement
        assert hu_view.family_progress == "SAME"
        assert hu_view.followup_branches is None
        assert view.actions[2].followup_branches is None
        assert view.actions[2].routes == ()
        assert view.actions[2].family_progress == "UNKNOWN"  # 空载荷=未分析

    def test_view_holds_observation_profile_and_defaults(self):
        request = self._request((_candidate("pass", Pass()),))
        view = build_scoring_view(request)
        assert view.visible_state is request.observation
        assert view.analysis_profile.semantics_version == VALUE_ANALYSIS_SEMANTICS_VERSION
        assert view.analysis_profile.ruleset_version == request.rules.ruleset_version
        assert view.analysis_profile.max_expansions == 2048
        assert view.analysis_profile.max_routes_per_candidate == 128
        assert view.competition is not None
        assert view.competition.stage_scores is None
        assert view.competition.table_scores is None
        assert view.competition.freshness_masks is None
        assert view.reference_features == ()

    @pytest.mark.parametrize(
        "progresses,expected",
        [
            ((ProgressKind.ADVANCE, ProgressKind.SAME), "ADVANCE"),
            ((ProgressKind.RETREAT, ProgressKind.CLOSE), "RETREAT"),
            ((ProgressKind.CLOSE, ProgressKind.SAME), "CLOSE"),
            ((ProgressKind.SAME, ProgressKind.UNKNOWN), "SAME"),
            ((ProgressKind.UNKNOWN,), "UNKNOWN"),
            ((), "UNKNOWN"),
        ],
    )
    def test_family_progress_collapse_is_deterministic(self, progresses, expected):
        entries = tuple(
            _progress(family, progress)
            for family, progress in zip(FamilyId, progresses)
        )
        facts = CandidateFacts(
            fact_kind=CandidateFactKind.HAND_PROGRESS, shanten_after=1,
            family_progress=entries,
        )
        request = self._request((
            _candidate("discard:1w", Discard(Tile("1w")), facts=facts),
        ))
        view = build_scoring_view(request)
        assert view.actions[0].family_progress == expected


def _peng_observation():
    """真实引擎夹具：碰响应窗口（沿用 hangma 载荷测试的构造口径）。"""
    hand = "5w 5w 1t 2t 3t 4t 5t 6t 7t 8t 9t 2b 3b"
    tiles = tuple(Tile(code) for code in hand.split())
    turn = 3
    return PlayerObservation(
        game_id="av-policy", seat=0, round_no=1, snapshot_seq=10,
        phase="response_peng", dealer_seat=0, turn_seat=turn,
        responding_seats=(0,), my_hand=tiles, drawn_tile=None,
        discards=((), (), (), (Tile("5w"),)), melds=((), (), (), ()),
        hand_counts=(13, 13, 13, 13),
        last_discard=PublicDiscard(turn, Tile("5w"), 10),
        remaining_tile_count=60, scores=(0, 0, 0, 0),
        rule_state=RulePublicState(Tile("白"), False, 0, False),
        public_history=(),
    )


def _engine_analysis():
    rules = HangmaRules(RuleConfig("av-policy-test", 1, False))
    return rules.analyze(_peng_observation(), value_limits=ValueAnalysisLimits())


class TestEnginePayloadPassthrough:
    """B1 载荷经真实规则分析进入视图（T08 的策略侧前半）。"""

    def test_peng_candidate_keeps_all_followup_branches(self):
        analysis = _engine_analysis()
        peng = next(
            c for c in analysis.legal_candidates if c.action_key == "peng:5w"
        )
        assert peng.facts is not None and peng.facts.followup_branches
        view = build_scoring_view(make_request(_peng_observation(), analysis))
        peng_view = next(
            item for item in view.actions if item.action_key == "peng:5w"
        )
        assert peng_view.followup_branches == peng.facts.followup_branches
        assert len(peng_view.followup_branches) >= 2  # 不只读已选最佳分支
        assert peng_view.family_progress in (
            "ADVANCE", "SAME", "RETREAT", "CLOSE", "UNKNOWN"
        )

    def test_candidate_view_maps_payloads_to_plain_values(self):
        analysis = _engine_analysis()
        view = build_scoring_view(make_request(_peng_observation(), analysis))
        mapped = view.candidate_view()["actions"]
        by_key = {item["action_key"]: item for item in mapped}
        peng = by_key["peng:5w"]
        assert peng["followup_branches"]  # 非 None：已分析分支
        branch = peng["followup_branches"][0]
        assert "combined_shanten" in branch and "support_remaining" in branch
        pass_entry = by_key["pass"]
        assert pass_entry["followup_branches"] is None  # 未分析保持 None


# ---------------------------------------------------------------------------
# DecisionPlan 契约与失败降级（桩评分器隔离策略层语义）
# ---------------------------------------------------------------------------


class _StubScorer:
    """鸭子类型评分器：按注入行为返回批或抛错。"""

    def __init__(
        self,
        *,
        batch: Optional[ScoreBatch] = None,
        error: Optional[BaseException] = None,
    ) -> None:
        self.name = "stub_seed"
        self._batch = batch
        self._error = error

    def score(self, view):
        if self._error is not None:
            raise self._error
        return self._batch


def _legal_set():
    discard1 = _candidate(
        "discard:1w", Discard(Tile("1w")),
        facts=CandidateFacts(
            fact_kind=CandidateFactKind.HAND_PROGRESS, shanten_after=1,
            family_progress=(_progress(FamilyId.BRANCH, ProgressKind.ADVANCE),),
        ),
    )
    discard2 = _candidate("discard:2w", Discard(Tile("2w")))
    pass_action = _candidate("pass", Pass())
    emergency = _candidate("discard:2w", Discard(Tile("2w")), facts=None)
    return discard1, discard2, pass_action, emergency


def _request_for(reject=()):
    discard1, discard2, pass_action, emergency = _legal_set()
    rules = make_rules(
        (discard1, discard2, pass_action), emergency=emergency
    )
    return make_request(
        make_observation(), rules, rejected=tuple(reject)
    )


def _batch(scores):
    return ScoreBatch(
        status="SCORED",
        entries=tuple(
            ActionScore(action_key=key, score=score, trace={"basis": "stub"})
            for key, score in scores
        ),
    )


class TestPlanContract:
    def test_scored_plan_filters_rejected_keeps_emergency_and_ranks(self):
        policy = ActionValuePolicy(_StubScorer(batch=_batch([
            ("pass", 5.0), ("discard:1w", 2.0), ("discard:2w", 1.0),
        ])))
        request = _request_for(reject=(rejected("discard:1w"),))
        plan = run_choose(policy, request, make_budget())
        keys = [item.action_key for item in plan.candidates]
        assert keys == ["pass", "discard:2w"]  # 拒绝过滤 + 紧急候选保留
        assert [item.rank for item in plan.candidates] == [1, 2]  # rank 连续
        assert plan.candidates[1].is_emergency is True
        assert plan.candidates[0].is_emergency is False

    def test_scored_plan_marks_emergency_from_batch(self):
        policy = ActionValuePolicy(_StubScorer(batch=_batch([
            ("discard:1w", 2.0), ("discard:2w", 1.0), ("pass", 0.0),
        ])))
        plan = run_choose(policy, _request_for(), make_budget())
        by_key = {item.action_key: item for item in plan.candidates}
        assert by_key["discard:2w"].is_emergency is True

    def test_missing_emergency_appended_at_tail(self):
        # 桩批遗漏紧急动作：策略层仍保证紧急候选保留（纵深防御）。
        policy = ActionValuePolicy(_StubScorer(batch=_batch([
            ("discard:1w", 2.0), ("pass", 1.0),
        ])))
        plan = run_choose(policy, _request_for(), make_budget())
        keys = [item.action_key for item in plan.candidates]
        assert keys == ["discard:1w", "pass", "discard:2w"]
        assert plan.candidates[-1].is_emergency is True
        assert [item.rank for item in plan.candidates] == [1, 2, 3]

    def test_choose_signature_matches_decision_loop_contract(self):
        policy = ActionValuePolicy(_StubScorer(batch=_batch([
            ("discard:1w", 2.0), ("discard:2w", 1.0), ("pass", 0.0),
        ])))
        request = _request_for(reject=(rejected("discard:1w"),))
        plan = run_choose(policy, request, make_budget())
        assert isinstance(plan, DecisionPlan)
        assert plan.decision_id == request.decision_id
        assert plan.window_key == request.window_key
        assert plan.based_on_authoritative_seq == request.observation.snapshot_seq
        assert plan.revision == len(request.rejected_attempts) + 1


class TestFailurePaths:
    def _degraded(self, policy, request):
        plan = run_choose(policy, request, make_budget())
        assert any("action_value_failed" in r for r in plan.degraded_reasons)
        return plan

    def test_value_error_degrades_to_emergency_plus_legal_order(self):
        policy = ActionValuePolicy(
            _StubScorer(error=ValueError("候选执行失败: TypeError: boom"))
        )
        plan = self._degraded(policy, _request_for())
        keys = [item.action_key for item in plan.candidates]
        # 仅紧急候选 + 规则合法顺序（action_key 升序，紧急不重复）。
        assert keys == ["discard:2w", "discard:1w", "pass"]
        assert plan.candidates[0].is_emergency is True
        assert all(item.is_emergency is False for item in plan.candidates[1:])
        assert [item.rank for item in plan.candidates] == [1, 2, 3]
        # 不拼 V2 分数：全部 0 分、单一分项名。
        assert all(item.total_score == 0.0 for item in plan.candidates)
        assert all(
            item.score_parts[0].name == "action_value_v1.degraded"
            for item in plan.candidates
        )

    def test_workload_exceeded_degrades(self):
        policy = ActionValuePolicy(_StubScorer(error=WorkloadExceeded("超限")))
        plan = self._degraded(policy, _request_for())
        assert plan.candidates and plan.candidates[0].is_emergency

    def test_abstain_degrades_with_reason(self):
        batch = ScoreBatch(
            status="ABSTAIN", entries=(), reason="缺必需字段 combined_shanten"
        )
        policy = ActionValuePolicy(_StubScorer(batch=batch))
        plan = self._degraded(policy, _request_for())
        assert any("ABSTAIN" in r for r in plan.degraded_reasons)
        assert any("combined_shanten" in r for r in plan.degraded_reasons)

    def test_degraded_plan_applies_rejected_filter(self):
        policy = ActionValuePolicy(
            _StubScorer(error=ValueError("boom"))
        )
        request = _request_for(reject=(rejected("pass"),))
        plan = self._degraded(policy, request)
        keys = [item.action_key for item in plan.candidates]
        assert "pass" not in keys
        assert keys == ["discard:2w", "discard:1w"]


class TestRealSeedEndToEnd:
    """受限执行器装载真实种子跑通一个引擎窗口（0 桌赛）。"""

    @pytest.mark.parametrize(
        "seed", ["efficiency_seed", "route_value_seed", "hu_first_reference"]
    )
    def test_seed_produces_full_legal_plan(self, seed):
        policy = ActionValuePolicy.from_seed(seed)
        analysis = _engine_analysis()
        request = make_request(_peng_observation(), analysis)
        plan = run_choose(policy, request, make_budget())
        legal = {c.action_key for c in analysis.legal_candidates}
        keys = [item.action_key for item in plan.candidates]
        assert keys
        assert set(keys) <= legal
        assert len(keys) == len(set(keys))
        assert [item.rank for item in plan.candidates] == list(
            range(1, len(keys) + 1)
        )
        # 排序来自候选评分（单一 ScorePart），不拼 V2 底分。
        peng_entry = next(
            item for item in plan.candidates if item.action_key == "peng:5w"
        )
        assert peng_entry.score_parts[0].name == "action_value_v1"

    def test_seed_plan_without_payloads_still_covers_legal_set(self):
        # 无 value_limits 的分析（载荷缺省）不让策略崩溃或拼 V2：
        # 种子按显式未知处理评分，计划仍覆盖完整合法集。
        rules = HangmaRules(RuleConfig("av-policy-test", 1, False))
        analysis = rules.analyze(_peng_observation())
        policy = ActionValuePolicy.from_seed("efficiency_seed")
        request = make_request(_peng_observation(), analysis)
        plan = run_choose(policy, request, make_budget())
        legal = {c.action_key for c in analysis.legal_candidates}
        assert {item.action_key for item in plan.candidates} == legal
