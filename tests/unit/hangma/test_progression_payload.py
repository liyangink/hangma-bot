"""分支进展载荷契约测试：吃碰后续弃牌分支（T02）、未知与关闭（T03）、
联合结算与有效牌去重（T04）、接口校验与旧构造零破坏。

依据 SEARCH-SPACE-REDESIGN-2026-09-16.md §3.1/§4.2/§5.1/§7.3 与
contracts/action-value-v1.json 的 scoring_view 字段（冻结接口规格）。
只通过 HangmaRules.analyze 公开接口与 interface 类型校验验证行为。
"""

from dataclasses import replace

import pytest

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma import hand_analysis, settlement
from hangma_bot.hangma.interface import (
    CandidateFactKind,
    CandidateFacts,
    FamilyId,
    FamilyProgress,
    FollowupBranchFacts,
    ProgressKind,
    RouteStatus,
    UsefulTileFact,
    ValueAnalysisLimits,
)
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import (
    PlayerObservation,
    PublicDiscard,
    PublicMeld,
    RulePublicState,
)


def _tiles(codes):
    return tuple(Tile(code) for code in codes.split())


def _observation(hand, draw=None, *, phase="draw", response=None, seat=0,
                 melds=(), discards=None, baotou=False, chain=0, piao=0,
                 piao_none=False, hand_counts=None):
    """构造合法 PlayerObservation；默认座位 0 摸牌出牌窗口。"""

    own_melds = [(), (), (), ()]
    own_melds[seat] = tuple(melds)
    rivers = [(), (), (), ()]
    turn = seat if response is None else (seat + 3) % 4
    if response is not None:
        rivers[turn] = (Tile(response),)
    if discards is not None:
        rivers = list(discards)
    holding = _tiles(hand)
    return PlayerObservation(
        game_id="progression-payload", seat=seat, round_no=1, snapshot_seq=10,
        phase=phase if response is None else ("response_chi" if phase == "response_chi" else "response_peng"),
        dealer_seat=0, turn_seat=turn,
        responding_seats=() if response is None else (seat,),
        my_hand=holding, drawn_tile=Tile(draw) if draw else None,
        discards=tuple(rivers), melds=tuple(own_melds),
        hand_counts=hand_counts
        or tuple(len(holding) + bool(draw) if player == seat else 13 for player in range(4)),
        last_discard=None if response is None else PublicDiscard(turn, Tile(response), 10),
        remaining_tile_count=60, scores=(0, 0, 0, 0),
        rule_state=RulePublicState(Tile("白"), baotou, chain, False),
        public_history=(), chain_piao=None if piao_none else piao,
    )


def _rules():
    return HangmaRules(RuleConfig("progression-payload-test", 1, False))


def _candidate(observation, key, rules=None, limits=None):
    analysis = (rules or _rules()).analyze(
        observation, value_limits=limits or ValueAnalysisLimits()
    )
    return next(c for c in analysis.legal_candidates if c.action_key == key)


# ---------------------------------------------------------------------------
# T02：吃碰后两个合法弃牌分支都保留
# ---------------------------------------------------------------------------


def test_t02_peng_keeps_efficiency_branch_and_structure_branch():
    """碰 5w 后：牌效最佳分支（弃 1t）与保留 112233 连对结构的分支（弃 6t）
    都必须作为独立 FollowupBranchFacts 保留，不得预合并成最佳分支。"""

    observation = _observation(
        "5w 5w 1t 1t 2t 2t 3t 3t 4t 5t 6t 7t 8t",
        response="5w",
    )
    candidate = _candidate(observation, "peng:5w")
    facts = candidate.facts

    assert facts.fact_kind is CandidateFactKind.HAND_PROGRESS
    branches = facts.followup_branches
    assert branches is not None
    by_discard = {branch.followup_discard: branch for branch in branches}
    # 牌效最佳分支：弃 1t（向听 0、支持计数 12）。
    assert facts.best_followup_discard == "1t"
    assert by_discard["1t"].combined_shanten == 0
    assert by_discard["1t"].support_remaining == 12
    # 结构分支：弃 6t 保留 1t1t2t2t3t3t 连对结构，向听劣化为 1，仍完整保留。
    assert "6t" in by_discard
    assert by_discard["6t"].combined_shanten == 1
    assert by_discard["6t"].combined_shanten > by_discard["1t"].combined_shanten
    # 分支数 = 吃碰后暗牌的 distinct 牌值数（11 张 → 8 种）。
    assert len(branches) == 8
    # followup_key 稳定：<action_key>#<followup_discard>。
    for branch in branches:
        assert branch.followup_key == "peng:5w#{0}".format(branch.followup_discard)
    # 按 followup_discard 规范牌序排列。
    from hangma_bot.hangma.internal_types import TILE_INDEX

    order = [branch.followup_discard for branch in branches]
    assert order == sorted(order, key=TILE_INDEX.get)


def test_t02_branch_keys_are_stable_across_runs():
    """同一观察反复分析：分支键、排序与内容逐位一致（确定性）。"""

    observation = _observation("5w 5w 1t 1t 2t 2t 3t 3t 4t 5t 6t 7t 8t", response="5w")
    first = _candidate(observation, "peng:5w").facts.followup_branches
    second = _candidate(observation, "peng:5w").facts.followup_branches
    assert first == second
    assert tuple(b.followup_key for b in first) == tuple(b.followup_key for b in second)


def test_t02_chi_branches_cover_all_legal_followup_discards():
    """吃候选同样保留全部分支；最佳分支仍是牌效口径的既有选择。"""

    observation = _observation(
        "1w 2w 1t 2t 3t 4t 5t 6t 7t 8t 9t 2b 2b",
        response="3w", phase="response_chi",
    )
    candidate = _candidate(observation, "chi:1w,2w,3w")
    facts = candidate.facts

    assert facts.best_followup_discard == "1t"
    branches = facts.followup_branches
    assert branches is not None
    hand_after = set(code for code in ("1t", "2t", "3t", "4t", "5t", "6t", "7t", "8t", "9t", "2b"))
    assert {b.followup_discard for b in branches} == hand_after


# ---------------------------------------------------------------------------
# T03：UNANALYZED 不产出数值；未知 ≠ 0；七对关闭 CLOSED_PROVEN
# ---------------------------------------------------------------------------


def test_t03_complete_coverage_with_empty_routes_is_open_not_closed():
    """下一摸 COMPLETE + 空路线不代表未来不可能胡：branch 家族对可达路线
    报 OPEN_UNCERTAIN（不是 CLOSED_PROVEN，也不是数值机会 0）。"""

    observation = _observation(
        "1w 4w 7w 2b 5b 8b 3t 6t 9t 东 南 西 北", draw="中",
    )
    candidate = _candidate(observation, "discard:1w")
    value_facts = candidate.value_facts

    assert value_facts.coverage.value == "complete"
    assert value_facts.routes == ()
    progress = {entry.family: entry for entry in candidate.facts.family_progress}
    assert progress[FamilyId.BRANCH].route_status is RouteStatus.OPEN_UNCERTAIN
    assert progress[FamilyId.BRANCH].progress is ProgressKind.SAME
    # 空路线不是零机会：证据状态未关闭，也未冒充已见证。
    assert progress[FamilyId.BRANCH].route_status is not RouteStatus.CLOSED_PROVEN
    assert progress[FamilyId.BRANCH].route_status is not RouteStatus.WITNESSED


def test_t03_unknown_count_branch_reports_none_support_not_zero():
    """分支计数未知：support_remaining=None 且 useful_tiles 为空，不得写 0。

    构造：座位 3 两副 5t 碰使 5t 公开计数冲突（None）；弃 1t/4t/5t/6t/9t
    分支的一步推进牌含 5t，计数未知；最佳分支（弃 2b）不涉及 5t，照常
    给出数值——候选本身不因非最佳分支缺证据而失败。
    """

    double_peng = PublicMeld(3, "peng", _tiles("5t 5t 5t"), 0)
    observation = _observation(
        "5w 5w 1t 2t 3t 4t 5t 6t 7t 8t 9t 2b 3b",
        response="5w",
        melds=(), discards=((), (), (), ()),
        hand_counts=None,
    )
    # 手动放置他家副露：座位 3 两副 5t 碰（melds 参数只注入本人）。
    observation = replace(observation, melds=((), (), (), (double_peng, double_peng)),
                          hand_counts=(13, 13, 13, 7))
    candidate = _candidate(observation, "peng:5w")
    facts = candidate.facts

    assert facts.fact_kind is CandidateFactKind.HAND_PROGRESS
    branches = {b.followup_discard: b for b in facts.followup_branches}
    # 最佳分支已知计数：7 = 3b 3 张 + 白 4 张。
    assert facts.best_followup_discard == "2b"
    assert branches["2b"].support_remaining == 7
    assert branches["2b"].useful_tiles
    # 涉及 5t 的分支计数未知：None ≠ 0，且不携带部分计数冒充完整。
    for unknown_code in ("1t", "4t", "5t", "6t", "9t"):
        assert branches[unknown_code].support_remaining is None
        assert branches[unknown_code].support_remaining != 0
        assert branches[unknown_code].useful_tiles == ()
    # 未涉及未知牌种的分支照常给出数值。
    assert branches["2t"].support_remaining is not None
    assert branches["2t"].support_remaining > 0


def test_t03_seven_pairs_closed_by_meld_is_closed_proven_not_unknown():
    """开门吃碰使七对路线规则性关闭：branch 报 CLOSE + CLOSED_PROVEN，
    不是 UNKNOWN；七对向听字段为 None 表示已关闭而非未分析。"""

    observation = _observation("5w 5w 1t 2t 3t 4t 5t 6t 7t 8t 9t 2b 3b", response="5w")
    candidate = _candidate(observation, "peng:5w")
    facts = candidate.facts

    assert facts.seven_pairs_shanten_after is None
    for branch in facts.followup_branches:
        assert branch.seven_pairs_shanten_after is None
    progress = {entry.family: entry for entry in facts.family_progress}
    entry = progress[FamilyId.BRANCH]
    assert entry.progress is ProgressKind.CLOSE
    assert entry.route_status is RouteStatus.CLOSED_PROVEN
    assert entry.route_status is not RouteStatus.UNANALYZED
    assert "七对" in entry.basis


def test_t03_without_value_analysis_payload_stays_unanalyzed():
    """未开启分值分析（value_limits=None）：family_progress 空元组=未分析，
    不产出任何数值进展；吃碰分支是机械事实仍随基础事实生产。"""

    rules = _rules()
    observation = _observation("5w 5w 1t 2t 3t 4t 5t 6t 7t 8t 9t 2b 3b", response="5w")
    plain = rules.analyze(observation)

    assert plain.completeness.value == "complete"
    for candidate in plain.legal_candidates:
        assert candidate.facts is None or candidate.facts.family_progress == ()
    peng = next(c for c in plain.legal_candidates if c.action_key == "peng:5w")
    # 分支载荷属于基础事实（机械枚举），与分值分析无关。
    assert peng.facts.followup_branches is not None
    assert len(peng.facts.followup_branches) == 11
    pass_candidate = next(c for c in plain.legal_candidates if c.action_key == "pass")
    assert pass_candidate.facts.followup_branches is None


def test_t03_budget_limit_downgrades_to_unknown_not_fake_numbers():
    """超工作量上限：四家族全部 UNKNOWN + UNANALYZED 并带 progression_payload
    RuleIssue，不截断后冒充完整；合法候选原样保留。"""

    observation = _observation(
        "1w 4w 7w 2b 5b 8b 3t 6t 9t 东 南 西 北", draw="中",
    )
    rules = _rules()
    analysis = rules.analyze(observation, value_limits=ValueAnalysisLimits(max_expansions=1))

    assert analysis.legal_candidates
    checked = 0
    for candidate in analysis.legal_candidates:
        facts = candidate.facts
        if facts is None or not facts.family_progress:
            continue
        checked += 1
        assert [entry.family for entry in facts.family_progress] == list(FamilyId)
        for entry in facts.family_progress:
            assert entry.progress is ProgressKind.UNKNOWN
            assert entry.route_status is RouteStatus.UNANALYZED
        assert any(
            issue.area == "progression_payload.limit"
            for issue in candidate.value_facts.issues
        )
    assert checked > 0


# ---------------------------------------------------------------------------
# T04：联合终点按唯一结算函数结算；有效牌重叠不重复计数
# ---------------------------------------------------------------------------


def test_t04_conditional_settlements_come_from_the_unique_settlement_function():
    """吃碰两分支的一次摸牌成胡路线均由唯一结算函数（settlement.settle_win
    对 hand_analysis.win_split 的分解）给出；不出现第二套计番。"""

    observation = _observation("5w 5w 1t 2t 3t 4t 5t 6t 7t 8t 9t 2b 3b", response="5w")
    candidate = _candidate(observation, "peng:5w")
    routes = candidate.value_facts.routes

    assert len(routes) == 2
    for route in routes:
        assert route.followup_discard in ("2b", "3b")
        winning_hand = tuple(route.conditions.pre_draw_hand) + (next(
            tile.code for tile in route.useful_tiles if tile.code != "白"
        ),)
        split = hand_analysis.win_split(_tiles(" ".join(winning_hand)), route.conditions.meld_count)
        assert split is not None
        expected = settlement.settle_win(
            split,
            route.conditions.chain_count,
            route.conditions.chain_piao,
            route.conditions.baotou,
            1,
            observation.seat,
            observation.dealer_seat,
        )
        assert route.conditional_settlement == expected
        assert route.conditional_settlement.fan > 0
        assert sum(route.conditional_settlement.score_delta) == 0


def test_t04_overlapping_useful_tiles_are_not_double_counted():
    """两分支的有效牌重叠（本例共享 白）：各分支 support_remaining 只按本
    分支牌码去重求和一次；分支之间互不合并、互不重复计数。"""

    observation = _observation("5w 5w 1t 2t 3t 4t 5t 6t 7t 8t 9t 2b 3b", response="5w")
    facts = _candidate(observation, "peng:5w").facts
    branches = {b.followup_discard: b for b in facts.followup_branches}

    first, second = branches["2b"], branches["3b"]
    # 两分支都等待 白（重叠牌码），各自只计一次。
    assert {tile.code for tile in first.useful_tiles} == {"3b", "白"}
    assert {tile.code for tile in second.useful_tiles} == {"2b", "白"}
    assert first.support_remaining == 3 + 4
    assert second.support_remaining == 3 + 4
    # 去重定义：support_remaining == 本分支 useful_tiles 估计值之和（牌码唯一）。
    for branch in facts.followup_branches:
        if branch.support_remaining is not None:
            codes = [tile.code for tile in branch.useful_tiles]
            assert len(set(codes)) == len(codes)
            assert branch.support_remaining == sum(
                tile.remaining_estimate for tile in branch.useful_tiles
            )
    # 分支保持独立：不因重叠而合并为单一路线。
    assert first.followup_discard != second.followup_discard
    assert first.followup_key != second.followup_key


# ---------------------------------------------------------------------------
# 接口校验与旧构造零破坏
# ---------------------------------------------------------------------------


def _branch(discard="2b", key=None, **kw):
    fields = dict(
        combined_shanten=0,
        standard_shanten_after=0,
        seven_pairs_shanten_after=None,
    )
    fields.update(kw)
    return FollowupBranchFacts(
        followup_key=key or "peng:5w#{0}".format(discard),
        followup_discard=discard,
        **fields,
    )


def _progress(family=FamilyId.BRANCH, progress=ProgressKind.ADVANCE,
              status=RouteStatus.WITNESSED):
    return FamilyProgress(family=family, progress=progress, route_status=status,
                          basis="测试依据")


class TestInterfaceValidation:
    """冻结规格的 __post_init__ 校验：违规 ValueError 带字段名。"""

    def test_followup_branches_reject_non_hand_progress(self):
        with pytest.raises(ValueError, match="followup_branches"):
            CandidateFacts(
                fact_kind=CandidateFactKind.WIN,
                shanten_after=-1,
                followup_branches=(_branch(),),
            )

    def test_followup_branches_require_best_followup_discard(self):
        with pytest.raises(ValueError, match="best_followup_discard"):
            CandidateFacts(
                fact_kind=CandidateFactKind.HAND_PROGRESS,
                shanten_after=0,
                followup_branches=(_branch(),),
            )

    def test_followup_branches_reject_duplicate_discards(self):
        with pytest.raises(ValueError, match="followup_discard"):
            CandidateFacts(
                fact_kind=CandidateFactKind.HAND_PROGRESS,
                shanten_after=0,
                best_followup_discard="2b",
                followup_branches=(_branch("2b"), _branch("2b")),
            )

    def test_followup_branches_reject_best_outside_branches(self):
        with pytest.raises(ValueError, match="followup_branches"):
            CandidateFacts(
                fact_kind=CandidateFactKind.HAND_PROGRESS,
                shanten_after=0,
                best_followup_discard="9t",
                followup_branches=(_branch("2b"),),
            )

    def test_family_progress_rejects_duplicate_family(self):
        with pytest.raises(ValueError, match="family"):
            CandidateFacts(
                fact_kind=CandidateFactKind.HAND_PROGRESS,
                shanten_after=0,
                family_progress=(_progress(), _progress()),
            )

    def test_followup_branch_facts_validates_key_and_codes(self):
        with pytest.raises(ValueError, match="followup_key"):
            _branch(key="not-a-branch-key")
        with pytest.raises(ValueError, match="followup_discard"):
            _branch(discard="99w")
        with pytest.raises(ValueError, match="support_remaining"):
            _branch(support_remaining=-1)
        with pytest.raises(ValueError, match="combined_shanten"):
            _branch(combined_shanten=-2)

    def test_family_progress_requires_enum_and_basis(self):
        with pytest.raises(ValueError, match="family"):
            FamilyProgress(family="branch", progress=ProgressKind.ADVANCE,
                           route_status=RouteStatus.WITNESSED, basis="x")
        with pytest.raises(ValueError, match="basis"):
            FamilyProgress(family=FamilyId.BRANCH, progress=ProgressKind.ADVANCE,
                           route_status=RouteStatus.WITNESSED, basis="")


class TestLegacyCompatibility:
    """旧 CandidateFacts 构造零破坏；编解码升级后载荷字段参与事实相等性。"""

    def test_old_construction_equals_explicit_defaults(self):
        old = CandidateFacts(fact_kind=CandidateFactKind.HAND_PROGRESS, shanten_after=1)
        explicit = CandidateFacts(
            fact_kind=CandidateFactKind.HAND_PROGRESS, shanten_after=1,
            followup_branches=None, family_progress=(),
        )
        assert old == explicit
        assert old.followup_branches is None
        assert old.family_progress == ()

    def test_payload_fields_participate_in_equality(self):
        """编解码升级后载荷参与相等性：载荷不同即事实不同；
        剥离两载荷字段后与未携带载荷的旧事实相等（旧字段零变化）。"""

        plain = CandidateFacts(
            fact_kind=CandidateFactKind.HAND_PROGRESS, shanten_after=0,
            best_followup_discard="2b",
        )
        enriched = CandidateFacts(
            fact_kind=CandidateFactKind.HAND_PROGRESS, shanten_after=0,
            best_followup_discard="2b",
            followup_branches=(_branch("2b", useful_tiles=(UsefulTileFact("3b", 3),), support_remaining=3),),
            family_progress=(_progress(),),
        )
        assert plain != enriched
        assert enriched.followup_branches is not None
        assert enriched.family_progress
        assert replace(enriched, followup_branches=None, family_progress=()) == plain

    def test_old_consumer_fields_identical_with_and_without_value_analysis(self):
        """heuristic_adapter 依赖的既有字段在开/关分值分析时逐位一致。"""

        observation = _observation(
            "1w 2w 3w 4w 5w 6w 7w 8w 9w 1b 2b 3b 5t", draw="6t",
        )
        rules = _rules()
        plain = rules.analyze(observation)
        enriched = rules.analyze(observation, value_limits=ValueAnalysisLimits())
        plain_by_key = {c.action_key: c for c in plain.legal_candidates}
        assert plain.issues == enriched.issues
        assert plain.completeness == enriched.completeness
        assert plain.emergency_candidate == enriched.emergency_candidate
        for candidate in enriched.legal_candidates:
            baseline = plain_by_key[candidate.action_key]
            old_fields = (
                "fact_kind", "shanten_after", "useful_tiles",
                "best_followup_discard", "replacement_draw_unknown",
                "completeness", "note", "standard_shanten_after",
                "seven_pairs_shanten_after", "standard_useful_tiles",
                "seven_pairs_useful_tiles", "pattern_progress_note",
            )
            for name in old_fields:
                assert getattr(candidate.facts, name) == getattr(baseline.facts, name)
            # 编解码升级后载荷参与相等性：开/关分值分析产生不同载荷即不同
            # 事实；剥离两载荷字段后仍逐位相等（旧消费者字段零变化）。
            assert replace(
                candidate.facts, followup_branches=None, family_progress=(),
                baotou_after=None,
            ) == baseline.facts
            assert candidate.action == baseline.action
            assert candidate.evidence == baseline.evidence


def test_payload_order_follows_family_declaration_order():
    """family_progress 按 FamilyId 声明序（branch/chain/four_white/baotou）。"""

    observation = _observation(
        "1w 4w 7w 2b 5b 8b 3t 6t 9t 东 南 西 北", draw="中",
    )
    candidate = _candidate(observation, "discard:1w")
    assert [entry.family for entry in candidate.facts.family_progress] == list(FamilyId)


def test_branch_records_sorted_in_canonical_tile_order():
    """followup_branches 按 followup_discard 规范牌序排列。"""

    observation = _observation("5w 5w 1t 1t 2t 2t 3t 3t 4t 5t 6t 7t 8t", response="5w")
    facts = _candidate(observation, "peng:5w").facts
    from hangma_bot.hangma.internal_types import TILE_INDEX

    order = [branch.followup_discard for branch in facts.followup_branches]
    assert order == sorted(order, key=TILE_INDEX.get)
