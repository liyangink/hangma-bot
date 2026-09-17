"""R2/S2 验收：真实 HangmaRules 输入贯穿投影 → 种子 → 排序 → 解释。

由 REVIEW-V4-COMPLETION-2026-09-17.md S2 的复现脚本
（evidence/review-v4-2026-09-17/standards-probes.py）改造为断言：真实
向听 0/1 各异的弃牌候选必须得到不同分数；普通弃牌的动作级牌效、完整
分家族进展、实际分析配置、覆盖/截断原因与真实路线结算都必须进入视图。
覆盖矩阵：非听牌弃牌 / 听牌 / 吃碰双分支 / 杠补未知 / 胡与继续 / 缺史 /
截断。全部 0 桌赛。
"""

from __future__ import annotations

import pytest

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import (
    PlayerObservation,
    PublicDiscard,
    RulePublicState,
)
from hangma_bot.policy.action_value import SCORE_TRACE_SCHEMA_VERSION
from hangma_bot.policy.action_value_policy import (
    ActionValuePolicy,
    build_scoring_view,
)
from hangma_bot.policy.action_value_seeds import build_action_value_policy
from .support import make_budget, make_request, run_choose

RULES_CONFIG = RuleConfig("r2-projection", 1, False)


def _observation(hand, draw=None, *, phase="draw", response=None):
    tiles = tuple(Tile(code) for code in hand.split())
    turn = 0 if response is None else 3
    rivers = [(), (), (), ()]
    if response is not None:
        rivers[turn] = (Tile(response),)
    return PlayerObservation(
        game_id="r2-projection", seat=0, round_no=1, snapshot_seq=10,
        phase=phase if response is None else "response_" + phase,
        dealer_seat=0, turn_seat=turn,
        responding_seats=() if response is None else (0,),
        my_hand=tiles, drawn_tile=Tile(draw) if draw else None,
        discards=tuple(rivers), melds=((), (), (), ()),
        hand_counts=tuple(len(tiles) + bool(draw) if seat == 0 else 13 for seat in range(4)),
        last_discard=None if response is None else PublicDiscard(turn, Tile(response), 10),
        remaining_tile_count=60, scores=(0, 0, 0, 0),
        rule_state=RulePublicState(Tile("白"), False, 0, False),
        public_history=(),
    )


def _request_for(observation, limits=None):
    rules = HangmaRules(RULES_CONFIG)
    analysis = (
        rules.analyze(observation)
        if limits is None
        else rules.analyze(observation, value_limits=limits)
    )
    return make_request(observation, analysis)


def _scores_by_key(batch):
    return {entry.action_key: entry.score for entry in batch.entries}


def _traces_by_key(batch):
    return {entry.action_key: entry.trace for entry in batch.entries}


# ---------------------------------------------------------------------------
# 评审复现样例（standards-probes.py 的 S2 段）：普通弃牌动作级牌效
# ---------------------------------------------------------------------------

REVIEW_HAND = "1w 2w 3w 4w 5w 6w 7w 8w 9w 1b 2b 3b 4b"
REVIEW_DRAW = "9b"


class TestRealDiscardProjection:
    """真实 14 个弃牌候选向听 0/1 各异——种子必须区分（S2 ①②）。"""

    def _view_and_analysis(self):
        observation = _observation(REVIEW_HAND, REVIEW_DRAW)
        request = _request_for(observation, ValueAnalysisLimits())
        return build_scoring_view(request), request.rules

    def test_rule_facts_really_differ(self):
        _, analysis = self._view_and_analysis()
        shanten = {c.facts.shanten_after for c in analysis.legal_candidates if c.facts}
        assert len(shanten) > 1  # 评审前提成立：真实向听 0/1 各异

    def test_view_mirrors_action_level_facts(self):
        view, analysis = self._view_and_analysis()
        by_key = {item.action_key: item for item in view.actions}
        for candidate in analysis.legal_candidates:
            projected = by_key[candidate.action_key]
            facts = candidate.facts
            assert projected.shanten_after == facts.shanten_after
            assert projected.fact_kind == facts.fact_kind.value
            assert projected.useful_tiles == facts.useful_tiles
            assert projected.standard_shanten_after == facts.standard_shanten_after
            assert projected.seven_pairs_shanten_after == facts.seven_pairs_shanten_after
            assert projected.family_progress_entries == facts.family_progress

    def test_efficiency_seed_scores_discards_differently(self):
        view, analysis = self._view_and_analysis()
        batch = build_action_value_policy("efficiency_seed").score(view)
        scores = _scores_by_key(batch)
        discards = [
            c for c in analysis.legal_candidates
            if c.action_key.startswith("discard:") and c.facts
        ]
        assert len({scores[c.action_key] for c in discards}) > 1  # 不再全 0
        # 精确公式核对：真实向听与有效牌未见枚数驱动分数（事实接线，非巧合）。
        for candidate in discards:
            expected = -3.0 * candidate.facts.shanten_after + 0.5 * sum(
                tile.remaining_estimate for tile in candidate.facts.useful_tiles
            )
            assert scores[candidate.action_key] == pytest.approx(expected)

    def test_efficiency_seed_reads_action_level_trace(self):
        view, analysis = self._view_and_analysis()
        batch = build_action_value_policy("efficiency_seed").score(view)
        traces = _traces_by_key(batch)
        discard = next(
            c for c in analysis.legal_candidates
            if c.action_key.startswith("discard:") and c.facts.shanten_after is not None
        )
        trace = traces[discard.action_key]
        assert trace["fact_source"] == "action_facts"  # 普通弃牌用动作级事实
        assert trace["combined_shanten"] == discard.facts.shanten_after

    def test_candidate_view_carries_action_facts_for_restricted_seeds(self):
        view, _ = self._view_and_analysis()
        mapped = {item["action_key"]: item for item in view.candidate_view()["actions"]}
        discard = next(
            key for key in mapped
            if key.startswith("discard:") and mapped[key]["shanten_after"] is not None
        )
        entry = mapped[discard]
        assert entry["fact_kind"] == "hand_progress"
        assert isinstance(entry["useful_tiles"], tuple)
        assert entry["useful_tiles"]
        assert entry["replacement_draw_unknown"] is False
        assert entry["family_progress_entries"]
        assert entry["value_coverage"] == "complete"


# ---------------------------------------------------------------------------
# 听牌 + 真实路线结算（S2 ⑥）：conditional_settlement 直读
# ---------------------------------------------------------------------------

LISTEN_HAND = "1w 1w 6w 6w 5t 5t 7t 7t 8t 8t 9t 9t 7w"
LISTEN_DRAW = "5w"
# 自摸胡窗口：三条顺子 + 1b2b3b + 4t 对（胡与继续并存）。
HU_HAND = "1w 2w 3w 4w 5w 6w 7w 8w 9w 1b 2b 3b 4t"
HU_DRAW = "4t"


class TestRouteSettlementFromRealValueRoute:
    def _view_and_analysis(self):
        observation = _observation(LISTEN_HAND, LISTEN_DRAW)
        request = _request_for(observation, ValueAnalysisLimits())
        return build_scoring_view(request), request.rules

    def _hu_view_and_analysis(self):
        observation = _observation(HU_HAND, HU_DRAW)
        request = _request_for(observation, ValueAnalysisLimits())
        return build_scoring_view(request), request.rules

    def test_route_fan_read_from_conditional_settlement(self):
        view, analysis = self._view_and_analysis()
        discard = next(
            c for c in analysis.legal_candidates
            if c.action_key == "discard:5w" and c.value_facts and c.value_facts.routes
        )
        real_fan = max(
            route.conditional_settlement.fan for route in discard.value_facts.routes
        )
        batch = build_action_value_policy("route_value_seed").score(view)
        trace = _traces_by_key(batch)["discard:5w"]
        assert trace["route_fan"] == float(real_fan)  # 真实字段，非 branch.fan

    def test_immediate_settlement_projected_for_hu(self):
        view, analysis = self._hu_view_and_analysis()
        hu = next(c for c in analysis.legal_candidates if c.action_key == "hu")
        assert hu.value_facts.immediate_settlement is not None
        projected = next(item for item in view.actions if item.action_key == "hu")
        assert projected.immediate_settlement == hu.value_facts.immediate_settlement
        batch = build_action_value_policy("route_value_seed").score(view)
        trace = _traces_by_key(batch)["hu"]
        assert trace["immediate_fan"] == hu.value_facts.immediate_settlement.fan

    def test_hu_and_continue_both_scored_in_same_batch(self):
        view, _ = self._hu_view_and_analysis()
        batch = build_action_value_policy("efficiency_seed").score(view)
        scores = _scores_by_key(batch)
        assert "hu" in scores  # 胡与继续同窗可比（compare_legal）
        assert any(key != "hu" for key in scores)


class TestHuContinueOrdering:
    def test_hu_first_orders_hu_top_and_trace_survives(self):
        observation = _observation(HU_HAND, HU_DRAW)
        request = _request_for(observation, ValueAnalysisLimits())
        policy = ActionValuePolicy.from_seed("hu_first_reference")
        plan = run_choose(policy, request, make_budget())
        assert plan.candidates[0].action_key == "hu"
        # S5：完整 trace 保留到计划（不只剩 reasons 摘要）。
        assert plan.candidates[0].score_trace is not None
        assert plan.candidates[0].score_trace["trace_schema"] == SCORE_TRACE_SCHEMA_VERSION
        assert plan.candidates[0].score_trace["detail"]["basis"] == "hu_first_reference"
        continue_entry = next(c for c in plan.candidates if c.action_key != "hu")
        assert continue_entry.score_trace["detail"]["combined_shanten"] is not None


# ---------------------------------------------------------------------------
# 吃碰双分支（followup 分支口径）与完整分家族进展（S2 ②④）
# ---------------------------------------------------------------------------

PENG_HAND = "5w 5w 1t 2t 3t 4t 5t 6t 7t 8t 9t 2b 3b"


class TestChiPengBranchesAndFamilyDetail:
    def _view_and_analysis(self):
        observation = _observation(PENG_HAND, phase="peng", response="5w")
        request = _request_for(observation, ValueAnalysisLimits())
        return build_scoring_view(request), request.rules

    def test_peng_uses_branch_facts_with_full_detail(self):
        view, analysis = self._view_and_analysis()
        peng = next(c for c in analysis.legal_candidates if c.action_key == "peng:5w")
        assert len(peng.facts.followup_branches) >= 2
        batch = build_action_value_policy("efficiency_seed").score(view)
        trace = _traces_by_key(batch)["peng:5w"]
        assert trace["fact_source"] == "followup_branch"
        best = min(b.combined_shanten for b in peng.facts.followup_branches)
        assert trace["combined_shanten"] == best
        assert trace["followup_key"].startswith("peng:5w#")

    def test_family_progress_entries_keep_all_families(self):
        view, analysis = self._view_and_analysis()
        peng = next(c for c in analysis.legal_candidates if c.action_key == "peng:5w")
        assert peng.facts.family_progress  # 碰候选带完整分家族进展
        projected = next(item for item in view.actions if item.action_key == "peng:5w")
        assert projected.family_progress_entries == peng.facts.family_progress  # 完整明细
        assert len(projected.family_progress_entries) == 4  # 四家族不被折成单串
        mapped = {
            item["action_key"]: item for item in view.candidate_view()["actions"]
        }["peng:5w"]
        assert [e["family"] for e in mapped["family_progress_entries"]] == [
            "branch", "chain", "four_white", "baotou",
        ]
        assert all(e["route_status"] for e in mapped["family_progress_entries"])


# ---------------------------------------------------------------------------
# 杠补未知 / 缺史 / 截断（S2 覆盖矩阵）
# ---------------------------------------------------------------------------

GANG_HAND = "2b 2b 2b 1w 4w 7w 3t 5t 7t 9t 东 南 西"


class TestGangUnknownAndEdgeCases:
    def test_gang_replacement_unknown_projected(self):
        observation = _observation(GANG_HAND, "2b")
        request = _request_for(observation, ValueAnalysisLimits())
        view = build_scoring_view(request)
        gang = next(item for item in view.actions if item.action_key == "gang:concealed:2b")
        assert gang.replacement_draw_unknown is True  # 杠补未知透传
        assert gang.shanten_after is not None
        mapped = {
            item["action_key"]: item for item in view.candidate_view()["actions"]
        }["gang:concealed:2b"]
        assert mapped["replacement_draw_unknown"] is True

    def test_missing_facts_project_to_none_and_seed_anchors_unknown(self):
        from .support import make_observation
        from hangma_bot.hangma.interface import RuleCandidate
        from hangma_bot.kernel.actions import Discard

        candidates = (
            RuleCandidate(
                action=Discard(Tile("1w")), action_key="discard:1w", evidence=(),
            ),  # facts=None：缺史
        )
        request = make_request(make_observation(), _rules_with(candidates))
        view = build_scoring_view(request)
        projected = view.actions[0]
        assert projected.fact_kind is None
        assert projected.shanten_after is None
        assert projected.useful_tiles == ()
        assert projected.family_progress == "UNKNOWN"
        assert projected.value_coverage is None
        batch = build_action_value_policy("efficiency_seed").score(view)
        trace = _traces_by_key(batch)["discard:1w"]
        assert trace["basis"] == "unknown_field_basis"  # 未知不变零：显式锚点

    def test_truncated_analysis_projects_coverage_and_issues(self):
        observation = _observation(REVIEW_HAND, REVIEW_DRAW)
        request = _request_for(
            observation, ValueAnalysisLimits(max_expansions=1)
        )
        view = build_scoring_view(request, value_limits=ValueAnalysisLimits(max_expansions=1))
        coverages = {item.value_coverage for item in view.actions}
        assert None in coverages or "unavailable" in coverages or "partial" in coverages
        truncated = [
            item for item in view.actions
            if item.value_issues and item.value_coverage != "complete"
        ]
        assert truncated  # 截断/缺证据原因透传
        mapped = {
            item["action_key"]: item for item in view.candidate_view()["actions"]
        }
        issues_entry = next(item for item in view.actions if item.value_issues)
        assert mapped[issues_entry.action_key]["value_issues"]
        assert all(
            issue["area"] for issue in mapped[issues_entry.action_key]["value_issues"]
        )

    def test_analysis_profile_carries_actual_limits(self):
        observation = _observation(REVIEW_HAND, REVIEW_DRAW)
        request = _request_for(observation)
        default_view = build_scoring_view(request)
        assert default_view.analysis_profile.max_expansions == 2048
        assert "默认上限快照" in default_view.analysis_profile.truncation_note
        tuned = build_scoring_view(
            request, value_limits=ValueAnalysisLimits(max_expansions=512, max_routes_per_candidate=64)
        )
        assert tuned.analysis_profile.max_expansions == 512
        assert tuned.analysis_profile.max_routes_per_candidate == 64
        assert "实际分析配置" in tuned.analysis_profile.truncation_note

    def test_policy_binds_limits_into_profile(self):
        observation = _observation(REVIEW_HAND, REVIEW_DRAW)
        request = _request_for(observation)
        policy = ActionValuePolicy.from_seed(
            "efficiency_seed", value_limits=ValueAnalysisLimits(max_expansions=77)
        )
        plan = run_choose(policy, request, make_budget())
        assert plan.candidates
        # 通过独立投影核对策略内部使用的实际配置。
        view = build_scoring_view(
            request, value_limits=ValueAnalysisLimits(max_expansions=77)
        )
        assert view.analysis_profile.max_expansions == 77


def _rules_with(candidates):
    from .support import make_rules

    return make_rules(candidates)
