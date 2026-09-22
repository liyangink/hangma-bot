"""B3 全链装配测试：投影器字段完整性、DecisionPlan 契约与失败降级路径。

权威行为来自 SEARCH-SPACE-REDESIGN-2026-09-16.md §4.1（六步顺序）与
contracts/action-value-v1.json（rank/降级/不拼 V2）。choose 对外签名与
既有决策循环同构（support.run_choose），不改任何冻结契约。
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
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
    CompetitionContext,
    PlayerObservation,
    PublicDiscard,
    RankingEntry,
    RulePublicState,
)
from hangma_bot.policy.action_value import (
    SCORING_VIEW_SCHEMA_VERSION,
    ActionScore,
    ScoreBatch,
    ScoringView,
)
from hangma_bot.policy.action_value_executor import WorkloadExceeded
from hangma_bot.policy.action_value_seeds import build_sample_view
from hangma_bot.policy.action_value_policy import (
    COMPETITION_MASK_BASES,
    COMPETITION_MASK_VALUES,
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
        # P11：缺省夹具的 ranking 为空（无阶段账事实）→ 阶段基准未知；但桌内
        # 基准是已知事实，不得报成未知（旧断言「competition 三个字段恒 None」
        # 正是本包修复的缺陷本身，见 FIX-REPORT §1）。
        assert view.competition is not None
        assert view.competition.stage_scores is None
        assert view.competition.stage_scores != (0, 0, 0, 0)
        assert view.competition.table_scores == tuple(request.observation.scores)
        assert view.competition.freshness_masks == (
            "stage_account:absent", "table_account:live",
        )
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


# ---------------------------------------------------------------------------
# P11：阶段账 → CompetitionView 投影契约（身份映射 / 单位 / 顺序 / 可空 / 未知≠零）
#
# R6 冻结版 _competition_view() 恒返回空 CompetitionView；本组用例固定投影契约：
#   - 座位向量语义 = 物理座位 0—3（与本桌观察同序）；
#   - 阶段账只承认「桌内座位序账」（ranking[i] = 坐在物理座位 i 的身份的
#     已完成桌账；由 offline StageSituationProjection.competition_context 逐位
#     构造，位置 i 与 participant_ids_by_seat[i] 一一对应）；
#   - 我方身份的锚点是 CompetitionContext.participant_rank（我方名次，按座位
#     发布）：ranking[我方座位].rank must == participant_rank；
#   - 任何不满足的必要条件一律投影 None（未知），绝不补零、绝不默认无账。
# ---------------------------------------------------------------------------


def _entry(participant_id, *, total, places, rank, god=0, games=0):
    """构造一条排名条目（单位：积分点 / 名次分；rank 从 1 起）。"""
    return RankingEntry(
        participant_id=participant_id, total_score=total, place_points=places,
        god_count=god, games_played=games, rank=rank,
    )


def _context(*, ranking, participant_rank, seat_tournament="p11-t", **overrides):
    base = dict(
        tournament_id=seat_tournament, stage_no=2, stage_role="qualify",
        stage_total=2, participant_rank=participant_rank, ranking=tuple(ranking),
        observed_at_unix_ms=0,
    )
    base.update(overrides)
    return CompetitionContext(**base)


def _seat_ordered_account(*, totals=(40, 90, -20, 10), places=(1, 3, -3, -1),
                          ids=("focal", "opp-1", "opp-2", "opp-3"), games=8,
                          ranks=(2, 1, 4, 3), participant_rank=None):
    """标准桌内座位序账：四条同 games_played、名次与已知键一致。

    participant_rank 缺省按「请求方坐在 0 号位」（make_observation 默认座位）
    取 0 号位条目的名次；换座位请求时由调用方按座位传入。
    """
    return _context(
        ranking=tuple(
            _entry(pid, total=total, places=place, rank=rank, games=games)
            for pid, total, place, rank in zip(ids, totals, places, ranks)
        ),
        participant_rank=ranks[0] if participant_rank is None else participant_rank,
    )


class TestCompetitionViewProjection:
    """投影器：CompetitionContext → CompetitionView 的座位序与可空语义。"""

    def _view_for(self, context, *, observation=None):
        observation = observation if observation is not None else make_observation()
        request = make_request(observation, make_rules(()))
        return build_scoring_view(replace(request, competition=context))

    def test_seat_ordered_account_projects_both_bases(self):
        view = self._view_for(_seat_ordered_account())
        assert view.competition.stage_scores == (40, 90, -20, 10)
        assert view.competition.table_scores == tuple(view.visible_state.scores)
        assert view.competition.freshness_masks == (
            "stage_account:complete", "table_account:live",
        )
        # 受限候选可见通道携带同一份事实（原始值）。
        mapped = view.candidate_view()["competition"]
        assert mapped["stage_scores"] == (40, 90, -20, 10)
        assert mapped["table_scores"] == tuple(view.visible_state.scores)

    def test_seat_vector_follows_own_seat_not_rank_order(self):
        """座位序账不是名次序：1 号位的 90 分必须落在下标 1，哪怕它是第 1 名。"""
        totals = (40, 90, -20, 10)
        ranks = (2, 1, 4, 3)
        for seat in range(4):
            observation = make_observation(seat=seat)
            # 我方名次按座位发布：请求座位不同，锚点名次随之不同（同一份账）。
            view = self._view_for(
                _seat_ordered_account(totals=totals, participant_rank=ranks[seat]),
                observation=observation,
            )
            assert view.competition.stage_scores == totals
            assert view.competition.stage_scores[seat] == totals[seat]

    def test_absent_account_projects_unknown_not_zero(self):
        empty = _context(ranking=(), participant_rank=None, stage_no=None,
                         stage_role=None, stage_total=None)
        view = self._view_for(empty)
        assert view.competition.stage_scores is None
        assert view.competition.stage_scores != (0, 0, 0, 0)
        assert view.competition.freshness_masks == (
            "stage_account:absent", "table_account:live",
        )
        # 阶段基准缺失不得用桌内基准顶替（合同 baseline-uniqueness）。
        assert view.competition.table_scores == tuple(view.visible_state.scores)

    @pytest.mark.parametrize(
        "name,context_factory",
        [
            ("阶段级榜单（5 条，非本桌四座）",
             lambda: _context(
                 ranking=[_entry("p{0}".format(i), total=i, places=0, rank=i + 1)
                          for i in range(5)],
                 participant_rank=1)),
            ("身份重复（一席一身份被破坏）",
             lambda: _seat_ordered_account(ids=("focal", "focal", "opp-2", "opp-3"))),
            ("我方名次与座位不一致（ranking[seat].rank != participant_rank）",
             lambda: _context(
                 ranking=(
                     _entry("a", total=40, places=1, rank=2, games=8),
                     _entry("b", total=90, places=3, rank=1, games=8),
                     _entry("c", total=-20, places=-3, rank=4, games=8),
                     _entry("d", total=10, places=-1, rank=3, games=8),
                 ),
                 participant_rank=3)),  # 我方坐在 0 号位，但 0 号位条目名次是 2
            ("已完成局数不一致（不是同一批已完成桌）",
             lambda: _context(
                 ranking=(
                     _entry("a", total=40, places=1, rank=2, games=8),
                     _entry("b", total=90, places=3, rank=1, games=8),
                     _entry("c", total=-20, places=-3, rank=4, games=4),
                     _entry("d", total=10, places=-1, rank=3, games=8),
                 ),
                 participant_rank=2)),
            ("名次与已知键矛盾（更低分却名次更高）",
             lambda: _context(
                 ranking=(
                     _entry("a", total=40, places=1, rank=1, games=8),
                     _entry("b", total=90, places=3, rank=4, games=8),
                     _entry("c", total=-20, places=-3, rank=3, games=8),
                     _entry("d", total=10, places=-1, rank=2, games=8),
                 ),
                 participant_rank=1)),
            ("我方名次缺失（无法锚定身份）",
             lambda: _context(
                 ranking=(
                     _entry("a", total=40, places=1, rank=2, games=8),
                     _entry("b", total=90, places=3, rank=1, games=8),
                     _entry("c", total=-20, places=-3, rank=4, games=8),
                     _entry("d", total=10, places=-1, rank=3, games=8),
                 ),
                 participant_rank=None)),
        ],
    )
    def test_unmappable_shapes_project_unknown(self, name, context_factory):
        view = self._view_for(context_factory())
        assert view.competition.stage_scores is None, name
        assert view.competition.freshness_masks == (
            "stage_account:unmappable", "table_account:live",
        ), name
        # 未知不得被桌内基准顶替或补零。
        assert view.competition.table_scores == tuple(view.visible_state.scores)

    def test_masks_are_positionally_aligned_with_bases(self):
        for context in (_seat_ordered_account(),
                        _context(ranking=(), participant_rank=None)):
            view = self._view_for(context)
            masks = view.competition.freshness_masks
            assert masks is not None and len(masks) == 2
            assert masks[0].startswith("stage_account:")
            assert masks[1] == "table_account:live"
            assert (view.competition.stage_scores is None) == (
                masks[0] != "stage_account:complete")

    def test_projection_is_deterministic_and_input_independent(self):
        context = _seat_ordered_account()
        first = self._view_for(context)
        second = self._view_for(_seat_ordered_account())
        assert first.competition == second.competition
        assert context.ranking[0].total_score == 40  # 投影不改写输入

    def test_stage_account_vocabulary_matches_machine_contract(self):
        """掩码词表以代码常量为准，机器合同逐字一致（合同节 competition_bases）。"""
        path = (
            Path(__file__).resolve().parents[3]
            / "review/llm-guided-heuristic-route-2026-09-15/contracts/action-value-v1.json"
        )
        contract = json.loads(path.read_text(encoding="utf-8"))
        block = contract["scoring_view"].get("competition_bases")
        assert block is not None, "机器合同缺少 scoring_view.competition_bases 节"
        declared = tuple(block["freshness_masks"]["values"])
        assert declared == COMPETITION_MASK_VALUES
        assert tuple(block["freshness_masks"]["order"]) == COMPETITION_MASK_BASES


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

# ---------------------------------------------------------------------------
# P11b：ScoringView 结构版本升位与「静默漂移」守卫
#
# 背景：P11 扩写了合同 `scoring_view.fields.competition` 并新增 `competition_bases`，
# 但版本串仍是 /1 —— 合同内容已变而版本未变属于静默漂移，R7 重验收不允许。
# 本组用例：（1）版本串与结构面登记一致；（2）**守卫**：结构面变化必须同时升版本，
# 否则失败（并用一个合成漂移用例自证守卫确实会拦住）。
# ---------------------------------------------------------------------------

#: 结构版本 → 合同 `scoring_view` 的**结构面**指纹（冻结登记表）。
#: 结构面 = 字段名集合 + `competition_bases` 顶层键 + `freshness_masks` 词表；
#: 任何结构面变化都必须新增一条登记并同步升级 `schema_version`。
_SCORING_VIEW_STRUCTURE_BY_VERSION = {
    "sitin-scoring-view/1": {
        "fields": (
            "actions", "analysis_profile", "competition",
            "reference_features", "visible_state",
        ),
        "competition_bases_keys": None,   # /1：competition 只有一句「无权/陈旧为空」
        "mask_values": None,
    },
    "sitin-scoring-view/2": {
        "fields": (
            "actions", "analysis_profile", "competition",
            "reference_features", "visible_state",
        ),
        "competition_bases_keys": (
            "admission_conditions", "freshness_masks", "identity_mapping",
            "residual_risk", "seat_order", "stage_scores", "staleness",
            "table_scores", "units", "unknown_is_not_zero",
        ),
        # 位置序 [stage_scores, table_scores] 的闭集词表（与代码常量同源）。
        "mask_values": COMPETITION_MASK_VALUES,
    },
    "sitin-scoring-view/3": {
        "fields": (
            "actions", "analysis_profile", "competition",
            "reference_features", "visible_state",
        ),
        # /3（R8 E3/M1）：新增第三概念 current_stage_scores（已完成账 + 当前桌账 =
        # 当前阶段合计）与 residual_gaps（剩余赛程未投影的显式登记）。
        "competition_bases_keys": (
            "admission_conditions", "current_stage_scores", "freshness_masks",
            "identity_mapping", "residual_gaps", "residual_risk", "seat_order",
            "stage_scores", "staleness", "table_scores", "units",
            "unknown_is_not_zero",
        ),
        "mask_values": COMPETITION_MASK_VALUES,
    },
    "sitin-scoring-view/4": {
        "fields": (
            "actions", "analysis_profile", "competition",
            "reference_features", "visible_state",
        ),
        # /4（R18）：动作表新增 hangma 同源的 baotou_after；顶层结构与
        # competition 子结构不变，动作字段由公开接口附录逐字段守卫。
        "competition_bases_keys": (
            "admission_conditions", "current_stage_scores", "freshness_masks",
            "identity_mapping", "residual_gaps", "residual_risk", "seat_order",
            "stage_scores", "staleness", "table_scores", "units",
            "unknown_is_not_zero",
        ),
        "mask_values": COMPETITION_MASK_VALUES,
    },
}


def _contract_scoring_view() -> dict:
    path = (
        Path(__file__).resolve().parents[3]
        / "review/llm-guided-heuristic-route-2026-09-15/contracts/action-value-v1.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))["scoring_view"]


def _scoring_view_structure(scoring_view: dict) -> dict:
    """提取合同 `scoring_view` 的结构面（忽略纯散文措辞）。"""
    bases = scoring_view.get("competition_bases")
    return {
        "fields": tuple(sorted(scoring_view["fields"])),
        "competition_bases_keys": (None if bases is None else tuple(sorted(bases))),
        "mask_values": (
            None if bases is None else tuple(bases["freshness_masks"]["values"])
        ),
    }


class TestScoringViewVersionGuard:
    """P11b：版本升位与防静默漂移守卫。"""

    def test_schema_version_matches_code_constant_and_is_registered(self):
        contract = _contract_scoring_view()
        assert contract["schema_version"] == SCORING_VIEW_SCHEMA_VERSION
        # /4（R18）：动作后爆头事实进入候选视图。
        assert SCORING_VIEW_SCHEMA_VERSION == "sitin-scoring-view/4"
        assert SCORING_VIEW_SCHEMA_VERSION in _SCORING_VIEW_STRUCTURE_BY_VERSION

    def test_contract_structure_matches_declared_version(self):
        """守卫：合同结构面必须与「已声明版本」的登记指纹逐项一致。"""
        contract = _contract_scoring_view()
        declared = contract["schema_version"]
        expected = _SCORING_VIEW_STRUCTURE_BY_VERSION.get(declared)
        assert expected is not None, (
            "合同声明的版本 {0!r} 未登记结构面：结构面变更必须先登记并升版本".format(
                declared)
        )
        assert _scoring_view_structure(contract) == expected, (
            "合同 scoring_view 结构面与版本 {0!r} 的登记不一致——"
            "扩写 competition 字段/新增 competition_bases 必须同时升级 schema_version".format(
                declared)
        )

    def test_guard_rejects_extended_competition_without_version_bump(self):
        """自证守卫有效：把新结构面贴到旧版本号上必须被判为漂移。

        两段边界都验：/2 结构面贴 /1（P11b 边界）与 /3 结构面贴 /2（R8 E3 边界）。
        """
        for historical in ("sitin-scoring-view/1", "sitin-scoring-view/2"):
            drifted = dict(_contract_scoring_view())
            drifted["schema_version"] = historical
            assert _scoring_view_structure(drifted) != (
                _SCORING_VIEW_STRUCTURE_BY_VERSION[historical]
            ), historical

    def test_runtime_rejects_previous_versions(self):
        """运行时拒绝全部历史版本：/1 与 /2 视图都不得通过完整性验证。"""
        for historical in ("sitin-scoring-view/1", "sitin-scoring-view/2"):
            with pytest.raises(ValueError, match="schema_version"):
                ScoringView(
                    schema_version=historical,
                    visible_state=build_sample_view().visible_state,
                    actions=build_sample_view().actions,
                    analysis_profile=build_sample_view().analysis_profile,
                )
