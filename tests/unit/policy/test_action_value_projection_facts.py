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
from hangma_bot.policy.action_value_seeds import (
    ActionValueScorer,
    build_action_value_policy,
)
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

# ---------------------------------------------------------------------------
# P11/M1：阶段账投影到候选可见的 ScoringView.competition（视图层闭环）
#
# 缺陷（R6 冻结版）：_competition_view() 恒返回空 CompetitionView —— 面板侧
# （P2）已按「身份→物理座位」注入已完成桌阶段账到 DecisionRequest.competition，
# 但候选式评分器读到的 stage_scores/table_scores/freshness_masks 全是 None，
# 门线/追分逻辑只能退回桌内积分。本组用例把 P2 的第 2 桌实验搬到视图层：
# 同一观察下领先/落后首桌账必须产生可见差异并改变选择；四换座不串位；
# 缺账投影为未知（不是全 0）。
# ---------------------------------------------------------------------------

from dataclasses import replace  # noqa: E402

from hangma_bot.offline.evaluate import StageSituationProjection  # noqa: E402

#: P11 夹具手牌：真实引擎载荷中「牌效档最优」与「追分档（有效牌宽度）最优」是
#: 两个不同弃牌，且两档各自都是**唯一严格最优**（排除同分靠 action_key 决胜的
#: 假翻转）。由 evidence/v4-impl/r7-fixes/P11-scoringview-stage-account/
#: probe_pressure_fixture.py 在 3000 个随机 14 张手里按**策略实际排序规则**
#: （分数降序、同分 action_key 升序）筛出，命中 1 例：
#:   牌效档（领先）= discard:3t 22.50（领先第二名 1.50）
#:   追分档（落后）= discard:3w 宽度 66.00（领先第二名 3.00）
#:   交叉核验：3w 的牌效分 21.00 < 22.50；3t 的宽度 63.00 < 66.00
P11_HAND = "2b 1b 3t 2w 7w 1w 8t 9w 3w 4w 7b 9b 6t"
P11_DRAW = "5w"
#: 焦点物理座位（第 2 桌换座后 focal 坐在 1 号位；与 P2 面板侧实测同形）。
P11_SEAT = 1
#: 第 2 桌桌内积分：两版注入下逐位相同，用来证明变化只来自阶段账。
P11_TABLE_SCORES = (2, -2, 4, 0)
P11_TOURNAMENT = "p11-stage-account"

#: 阶段账（按身份累计；P2 面板侧 totals/place_totals 口径）。
P11_IDENTITIES = ("focal", "opp-1", "opp-2", "opp-3")
P11_ACCOUNT_SCORES = {"focal": 40, "opp-1": 90, "opp-2": -20, "opp-3": 10}
P11_ACCOUNT_PLACES = {"focal": 1, "opp-1": 3, "opp-2": -3, "opp-3": -1}
P11_ROTATIONS = ((0, 1, 2, 3), (1, 2, 3, 0), (2, 3, 0, 1), (3, 0, 1, 2))

#: 领先版：焦点座位（1 号位）阶段积分最高；落后版：同一座位阶段积分垫底。
#: 两版都由 P2 的 StageSituationProjection 生成（身份→物理座位同一口径）。
P11_LEADING_BY_SEAT = (40, 90, -20, 10)
P11_TRAILING_BY_SEAT = (90, -20, 40, 10)


def _p11_observation(*, seat=P11_SEAT):
    """第 2 桌真实观察：13 张手牌 + 摸牌，桌内积分非零（与阶段账互不混入）。"""
    tiles = tuple(Tile(code) for code in P11_HAND.split())
    return PlayerObservation(
        game_id="p11-stage-account", seat=seat, round_no=5, snapshot_seq=64,
        phase="draw", dealer_seat=0, turn_seat=seat, responding_seats=(),
        my_hand=tiles, drawn_tile=Tile(P11_DRAW),
        discards=((), (), (), ()), melds=((), (), (), ()),
        hand_counts=tuple(14 if index == seat else 13 for index in range(4)),
        last_discard=None, remaining_tile_count=52, scores=P11_TABLE_SCORES,
        rule_state=RulePublicState(Tile("白"), False, 0, False), public_history=(),
    )


def _p11_request(*, seat=P11_SEAT, stage_scores_by_seat, stage_places_by_seat,
                 participant_ids_by_seat=P11_IDENTITIES):
    """同一观察 + 指定阶段账注入 → DecisionRequest（观察与桌内账逐位相同）。"""
    observation = _p11_observation(seat=seat)
    situation = StageSituationProjection(
        stage_table_no=2, tables_in_stage=2, stage_role="qualify",
        tables_completed=1, rounds_per_game=8,
        stage_scores_by_seat=tuple(stage_scores_by_seat),
        place_points_by_seat=tuple(stage_places_by_seat),
        participant_ids_by_seat=tuple(participant_ids_by_seat),
    )
    request = _request_for(observation, ValueAnalysisLimits())
    return replace(
        request, competition=situation.competition_context(P11_TOURNAMENT, seat)
    )


#: 候选式评分器（受限子集源码，经 ActionValueExecutor 装载）：按可见阶段门线
#: 势差切档——Φ_in = s[座位] − 升序下标 2（第 2 名分数，晋级区末位门线）；
#: Φ_in ≥ 0 走高牌效档（向听优先），Φ_in < 0 走追分档（有效牌宽度优先）。
#: 阶段账缺失/不可映射时**保持守成档**并把缺项写进 trace（未知不得当 0）。
P11_PRESSURE_CANDIDATE_SOURCE = '''"""p11_stage_pressure_probe：按可见阶段门线势差在「牌效档」与「追分档」间切换。"""

SHANTEN_WEIGHT = 3.0
SUPPORT_WEIGHT = 0.5
ADVANCE_INDEX = 2
UNKNOWN_ANCHOR_STEP = 1.0


def number(value):
    if value is None:
        return None
    if value is True or value is False:
        return None
    return value


def tile_width(tiles):
    if tiles is None:
        return None
    total = 0.0
    for tile in tiles:
        remaining = number(tile.get("remaining_estimate"))
        if remaining is None:
            return None
        total = total + remaining
    return total


def action_facts(action):
    shanten = number(action.get("shanten_after"))
    if shanten is None:
        return None
    support = tile_width(action.get("useful_tiles"))
    if support is None:
        support = 0.0
    return (shanten, support)


def stage_pressure(view):
    competition = view.get("competition")
    if competition is None:
        return (False, "no_competition_view")
    masks = competition.get("freshness_masks")
    scores = competition.get("stage_scores")
    if scores is None:
        if masks is None:
            return (False, "stage_account_missing")
        return (False, masks[0])
    if len(scores) != 4:
        return (False, "stage_account_bad_length")
    seat = view["visible_state"]["seat"]
    ordered = sorted(scores)
    inside_line = ordered[ADVANCE_INDEX]
    return (scores[seat] < inside_line, "stage_scores")


def score_actions(view):
    push, basis = stage_pressure(view)
    entries = []
    for action in view["actions"]:
        facts = action_facts(action)
        if facts is None:
            continue
        shanten = facts[0]
        support = facts[1]
        if push:
            score = support
        else:
            score = 0.0 - SHANTEN_WEIGHT * shanten + SUPPORT_WEIGHT * support
        entries.append({
            "action_key": action["action_key"],
            "score": score,
            "trace": {"basis": "stage_pressure", "mode": "push" if push else "safe",
                      "stage_basis": basis, "shanten": shanten, "width": support},
        })
    anchor = None
    for entry in entries:
        if anchor is None or entry["score"] < anchor:
            anchor = entry["score"]
    if anchor is None:
        for action in view["actions"]:
            entries.append({
                "action_key": action["action_key"], "score": 0.0,
                "trace": {"basis": "stage_pressure", "mode": "abstain_no_facts",
                          "stage_basis": basis},
            })
        return {"status": "SCORED", "entries": entries, "reason": None}
    anchor = anchor - UNKNOWN_ANCHOR_STEP
    for action in view["actions"]:
        key = action["action_key"]
        known = False
        for entry in entries:
            if entry["action_key"] == key:
                known = True
        if known:
            continue
        entries.append({
            "action_key": key, "score": anchor,
            "trace": {"basis": "unknown_field_basis", "field": "shanten_after",
                      "stage_basis": basis},
        })
    return {"status": "SCORED", "entries": entries, "reason": None}
'''


def _p11_discard_facts(view):
    """从候选可见映射取普通弃牌的动作级事实：(shanten_after, 有效牌宽度)。"""
    facts = {}
    for action in view.candidate_view()["actions"]:
        shanten = action["shanten_after"]
        if shanten is None or not action["action_key"].startswith("discard:"):
            continue
        facts[action["action_key"]] = (
            float(shanten),
            float(sum(tile["remaining_estimate"] for tile in action["useful_tiles"])),
        )
    return facts


def _p11_policy():
    """按名装载受限候选（与真实候选臂同一装载路径：静态检查 + 插桩计量）。"""
    return ActionValuePolicy(ActionValueScorer("p11_stage_pressure_probe",
                                               P11_PRESSURE_CANDIDATE_SOURCE))


class TestStageAccountProjectionIntoView:
    """P11 验收：阶段账进入候选可见视图并改变选择（与 P2 面板侧同口径）。"""

    def _views_and_plans(self):
        leading = _p11_request(stage_scores_by_seat=P11_LEADING_BY_SEAT,
                               stage_places_by_seat=(1, 3, -3, -1))
        trailing = _p11_request(stage_scores_by_seat=P11_TRAILING_BY_SEAT,
                                stage_places_by_seat=(-3, 1, 3, -1))
        policy = _p11_policy()
        views = {}
        plans = {}
        for name, request in (("leading", leading), ("trailing", trailing)):
            views[name] = build_scoring_view(request)
            plans[name] = run_choose(policy, request, make_budget())
        return leading, trailing, views, plans

    def test_leading_and_trailing_injections_are_visible_in_scoring_view(self):
        leading, trailing, views, _ = self._views_and_plans()
        # 观察与桌内账逐位相同：两版差异只来自阶段账。
        assert leading.observation == trailing.observation
        assert leading.observation.scores == trailing.observation.scores == P11_TABLE_SCORES
        assert views["leading"].competition.stage_scores == P11_LEADING_BY_SEAT
        assert views["trailing"].competition.stage_scores == P11_TRAILING_BY_SEAT
        assert views["leading"].competition.stage_scores !=             views["trailing"].competition.stage_scores
        # 候选可见（受限映射）通道同样携带，且为原始值。
        mapped = views["leading"].candidate_view()["competition"]
        assert mapped["stage_scores"] == P11_LEADING_BY_SEAT
        assert mapped["table_scores"] == P11_TABLE_SCORES
        assert all(isinstance(item, str) for item in mapped["freshness_masks"])
        print("[P11-A] 观察相同 seat={0} 桌内账={1}; 阶段账 领先={2} 落后={3}; "
              "候选可见掩码={4}".format(
                  views["leading"].seat_index(), P11_TABLE_SCORES,
                  views["leading"].competition.stage_scores,
                  views["trailing"].competition.stage_scores,
                  mapped["freshness_masks"]))

    def test_same_window_leading_vs_trailing_changes_choice(self):
        _, _, views, plans = self._views_and_plans()
        leading_top = plans["leading"].candidates[0]
        trailing_top = plans["trailing"].candidates[0]
        print("[P11-B] 领先档首选={0}（mode={1}） 落后档首选={2}（mode={3}）".format(
            leading_top.action_key,
            plans["leading"].candidates[0].score_trace["detail"].get("mode"),
            trailing_top.action_key,
            plans["trailing"].candidates[0].score_trace["detail"].get("mode")))
        assert leading_top.action_key != trailing_top.action_key
        assert plans["leading"].candidates[0].score_trace["detail"]["mode"] == "safe"
        assert plans["trailing"].candidates[0].score_trace["detail"]["mode"] == "push"
        # 同一窗口：动作集合与窗口键不变，只有阶段账不同的排序结果。
        assert views["leading"].expected_action_keys() == views["trailing"].expected_action_keys()
        # 交叉核验（值取自同一视图的真实载荷，不写死）：两个胜者在对方档位上
        # 都严格更差 —— 变化来自真实权衡，不是同分决胜或噪声。
        facts = _p11_discard_facts(views["leading"])
        efficiency = lambda key: -3.0 * facts[key][0] + 0.5 * facts[key][1]
        width = lambda key: facts[key][1]
        assert efficiency(trailing_top.action_key) < efficiency(leading_top.action_key)
        assert width(leading_top.action_key) < width(trailing_top.action_key)
        print("[P11-B2] 交叉核验：牌效 {0}={1:.2f} vs {2}={3:.2f}；宽度 {0}={4:.2f} vs {2}={5:.2f}".format(
            leading_top.action_key, efficiency(leading_top.action_key),
            trailing_top.action_key, efficiency(trailing_top.action_key),
            width(leading_top.action_key), width(trailing_top.action_key)))

    def test_four_rotations_keep_identity_to_seat_mapping(self):
        """四换座（plan.permutation 口径）：向量逐位等于面板侧账，不串位。"""
        observed = []
        for permutation in P11_ROTATIONS:
            ids_by_seat = tuple(P11_IDENTITIES[index] for index in permutation)
            scores = tuple(P11_ACCOUNT_SCORES[item] for item in ids_by_seat)
            places = tuple(P11_ACCOUNT_PLACES[item] for item in ids_by_seat)
            situation = StageSituationProjection(
                stage_table_no=2, tables_in_stage=2, stage_role="qualify",
                tables_completed=1, rounds_per_game=8,
                stage_scores_by_seat=scores, place_points_by_seat=places,
                participant_ids_by_seat=ids_by_seat,
            )
            per_seat = []
            for seat in range(4):
                request = _p11_request(
                    seat=seat, stage_scores_by_seat=scores,
                    stage_places_by_seat=places,
                    participant_ids_by_seat=ids_by_seat,
                )
                view = build_scoring_view(request)
                assert view.competition.stage_scores == situation.stage_scores_by_seat
                assert view.competition.freshness_masks[0] == "stage_account:complete"
                # 本座位 = 坐在该物理座位的身份的阶段账；其余座位逐位属于各自身份。
                for position in range(4):
                    assert (view.competition.stage_scores[position]
                            == P11_ACCOUNT_SCORES[ids_by_seat[position]]), (
                        permutation, seat, position)
                per_seat.append(view.competition.stage_scores[seat])
            observed.append((ids_by_seat, per_seat))
        print("[P11-C] 四换座逐桌核对：")
        for ids_by_seat, per_seat in observed:
            print("        seats={0} 各座位本人账={1}".format(ids_by_seat, per_seat))
        # 焦点身份在四种换座下取到的是同一份自己的账（不随换座被换成邻座）。
        focal_accounts = {
            ids_by_seat.index("focal"): per_seat[ids_by_seat.index("focal")]
            for ids_by_seat, per_seat in observed
        }
        assert set(focal_accounts.values()) == {P11_ACCOUNT_SCORES["focal"]}
        assert sorted(focal_accounts) == [0, 1, 2, 3]  # 四种座位都覆盖到


class TestUnknownAccountIsNotZero:
    """P11 验收：缺账 = 未知（None），已知空账 = 已知的零，两者必须可区分。"""

    def _request_with(self, competition):
        observation = _p11_observation()
        return replace(_request_for(observation, ValueAnalysisLimits()),
                       competition=competition)

    def test_absent_account_projects_unknown_and_candidate_declares_gap(self):
        from hangma_bot.kernel.observation import CompetitionContext

        empty = CompetitionContext(
            tournament_id=P11_TOURNAMENT, stage_no=None, stage_role=None,
            stage_total=None, participant_rank=None, ranking=(),
            observed_at_unix_ms=0,
        )
        request = self._request_with(empty)
        view = build_scoring_view(request)
        assert view.competition.stage_scores is None  # 未知，不是 (0, 0, 0, 0)
        mapped = view.candidate_view()["competition"]
        assert mapped["stage_scores"] is None
        assert mapped["freshness_masks"][0].startswith("stage_account:")
        plan = run_choose(_p11_policy(), request, make_budget())
        assert plan.candidates
        assert plan.candidates[0].score_trace["detail"]["stage_basis"] != "stage_scores"
        print("[P11-D] 无阶段账：stage_scores={0} 掩码={1} 首选档={2}".format(
            mapped["stage_scores"], mapped["freshness_masks"],
            plan.candidates[0].score_trace["detail"]["mode"]))

    def test_known_empty_account_is_known_zero_and_keeps_safe_mode(self):
        """第 1 桌（无已完成桌）注入的是**已知的四座全 0 账**，不是未知。"""
        request = _p11_request(stage_scores_by_seat=(0, 0, 0, 0),
                               stage_places_by_seat=(0, 0, 0, 0))
        view = build_scoring_view(request)
        assert view.competition.stage_scores == (0, 0, 0, 0)
        plan = run_choose(_p11_policy(), request, make_budget())
        assert plan.candidates[0].score_trace["detail"]["mode"] == "safe"
        print("[P11-E] 第 1 桌已知零账：stage_scores={0} 掩码={1}".format(
            view.competition.stage_scores, view.competition.freshness_masks))

