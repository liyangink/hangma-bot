"""分支进展载荷与分值分析的集成测试：四家族进展标签矩阵、路线证据状态、
预算超限降级与故障注入（v4 §7.3 / §5.2 / §14 T06 口径）。

矩阵口径说明（来源表 §7.3 的可定义边界）：

- branch 四态 + CLOSE 全部可构造；UNKNOWN 由预算超限给出。
- chain 只有 增加/相同/减少（ADVANCE/SAME/RETREAT）；CLOSE 无规则语义。
- four_white 距离 4−(手留白+链内飘白) 在单个动作内不可能减少（吃碰杠过
  不改手留白与飘白；飘白使 白−1/飘+1 净持平；其余弃牌只减不增），故
  ADVANCE 不可构造——以文档化测试固化该边界，不伪造样例。
- baotou 无 CLOSE（True→False 记 RETREAT）；终局（胡）转移未知记 UNKNOWN。
"""

from unittest import mock

from hangma_bot.hangma import progression_payload
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import (
    FamilyId,
    ProgressKind,
    RouteStatus,
    ValueAnalysisLimits,
    ValueCoverage,
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


def _observation(hand, draw=None, *, phase="draw", response=None, melds=(),
                 baotou=False, chain=0, piao=0, piao_none=False, hand_counts=None):
    own_melds = [(), (), (), ()]
    own_melds[0] = tuple(melds)
    rivers = [(), (), (), ()]
    turn = 0 if response is None else 3
    if response is not None:
        rivers[turn] = (Tile(response),)
    holding = _tiles(hand)
    return PlayerObservation(
        game_id="value-progress", seat=0, round_no=1, snapshot_seq=10,
        phase=phase, dealer_seat=0, turn_seat=turn,
        responding_seats=() if response is None else (0,),
        my_hand=holding, drawn_tile=Tile(draw) if draw else None,
        discards=tuple(rivers), melds=tuple(own_melds),
        hand_counts=hand_counts
        or tuple(len(holding) + bool(draw) if player == 0 else 13 for player in range(4)),
        last_discard=None if response is None else PublicDiscard(turn, Tile(response), 10),
        remaining_tile_count=60, scores=(0, 0, 0, 0),
        rule_state=RulePublicState(Tile("白"), baotou, chain, False),
        public_history=(), chain_piao=None if piao_none else piao,
    )


def _rules():
    return HangmaRules(RuleConfig("value-progress-test", 1, False))


def _progress_map(observation, key, rules=None, limits=None):
    rules = rules or _rules()
    analysis = rules.analyze(observation, value_limits=limits or ValueAnalysisLimits())
    candidate = next(c for c in analysis.legal_candidates if c.action_key == key)
    return {
        entry.family: (entry.progress, entry.route_status)
        for entry in candidate.facts.family_progress
    }, candidate


# ---------------------------------------------------------------------------
# 进展标签矩阵：四家族 × 可定义标签各至少一例
# ---------------------------------------------------------------------------


def test_branch_advance_same_retreat_close_unknown_matrix():
    """branch：ADVANCE（已有副露的吃进）、SAME/RETREAT（摸牌窗口弃牌）、
    CLOSE（开门关七对，另见 test_progression_payload）、UNKNOWN（超限）。"""

    # ADVANCE：已有 9w 碰副露，吃 2w3w4w 使普通型向听 1→0。
    meld = PublicMeld(0, "peng", _tiles("9w 9w 9w"), 2)
    observation = _observation(
        "2w 3w 5w 6w 1t 2t 3t 4t 5t 6t",
        phase="response_chi", response="4w",
        melds=(meld,), hand_counts=(10, 13, 13, 13),
    )
    progress, candidate = _progress_map(observation, "chi:2w,3w,4w")
    assert progress[FamilyId.BRANCH] == (ProgressKind.ADVANCE, RouteStatus.WITNESSED)
    assert candidate.value_facts.routes  # 吃进后听牌，一次摸牌成胡路线见证
    # 对照：过牌保持 1→1（SAME、未见证），证明 ADVANCE 来自吃进而非口径漂移。
    pass_progress, pass_candidate = _progress_map(observation, "pass")
    assert pass_progress[FamilyId.BRANCH] == (ProgressKind.SAME, RouteStatus.OPEN_UNCERTAIN)
    assert not pass_candidate.value_facts.routes

    # SAME / RETREAT：摸牌窗口 14 张最优向听 0；弃 6t 维持 0，弃 1b 劣化为 1。
    draw_obs = _observation(
        "1w 2w 3w 4w 5w 6w 7w 8w 9w 1b 2b 3b 5t", draw="6t",
    )
    same_progress, candidate = _progress_map(draw_obs, "discard:6t")
    assert same_progress[FamilyId.BRANCH] == (ProgressKind.SAME, RouteStatus.WITNESSED)
    assert candidate.value_facts.routes  # 见证来自一次摸牌成胡路线
    retreat_progress, _ = _progress_map(draw_obs, "discard:1b")
    assert retreat_progress[FamilyId.BRANCH] == (ProgressKind.RETREAT, RouteStatus.OPEN_UNCERTAIN)

    # UNKNOWN：预算超限（详见下方专项测试）。
    limited = _rules().analyze(
        draw_obs, value_limits=ValueAnalysisLimits(max_expansions=1)
    )
    for entry in next(
        c for c in limited.legal_candidates if c.action_key == "discard:6t"
    ).facts.family_progress:
        if entry.family is FamilyId.BRANCH:
            assert entry.progress is ProgressKind.UNKNOWN


def test_chain_advance_same_retreat_matrix():
    """chain：杠 +1（ADVANCE，可带路线见证）、不动（SAME）、断链清零（RETREAT）。"""

    # ADVANCE + WITNESSED：链 2（飘 1）上暗杠 → 链 3；路线条件链次数>0 见证。
    gang_obs = _observation(
        "9w 9w 9w 9w 1t 2t 3t 4t 5t 6t 7t 8t 9t", draw="西",
        chain=2, piao=1,
    )
    progress, candidate = _progress_map(gang_obs, "gang:concealed:9w")
    assert progress[FamilyId.CHAIN] == (ProgressKind.ADVANCE, RouteStatus.WITNESSED)
    assert any(route.conditions.chain_count == 3 for route in candidate.value_facts.routes)

    # SAME：链 0 普通弃牌 0→0。
    garbage = _observation("1w 4w 7w 2b 5b 8b 3t 6t 9t 东 南 西 北", draw="中")
    progress, _ = _progress_map(garbage, "discard:1w")
    assert progress[FamilyId.CHAIN] == (ProgressKind.SAME, RouteStatus.OPEN_UNCERTAIN)

    # RETREAT：链 1（爆头、飘 1）弃非白 → 断链清零。
    break_obs = _observation(
        "1w 2w 3w 4w 5w 6w 7w 8w 9w 1t 2t 3t 白", draw="白",
        baotou=True, chain=1, piao=1,
    )
    progress, _ = _progress_map(break_obs, "discard:1t")
    assert progress[FamilyId.CHAIN] == (ProgressKind.RETREAT, RouteStatus.OPEN_UNCERTAIN)

    # ADVANCE（无见证口径）：链 0 暗杠 → 链 1；杠后未听牌，无路线见证。
    fresh_gang = _observation(
        "9w 9w 9w 9w 1t 3t 5t 7t 9t 2b 4b 6b 东 南", draw="西",
    )
    progress, candidate = _progress_map(fresh_gang, "gang:concealed:9w")
    assert progress[FamilyId.CHAIN] == (ProgressKind.ADVANCE, RouteStatus.OPEN_UNCERTAIN)
    assert not candidate.value_facts.routes


def test_four_white_same_retreat_unknown_matrix():
    """four_white：飘白净持平（SAME，可由成胡白摸入见证）、断链失飘白
    （RETREAT）、链内飘白归因未知（UNKNOWN）。"""

    piao_obs = _observation(
        "1w 2w 3w 4w 5w 6w 7w 8w 9w 1t 2t 3t 白", draw="白",
        baotou=True, chain=1, piao=1,
    )
    # SAME + WITNESSED：飘白（白−1/飘+1）距离 1→1；路线以白摸入成胡使
    # 手留白+链内飘白恰为 4（four_white_indicator 见证）。
    progress, candidate = _progress_map(piao_obs, "discard:白")
    assert progress[FamilyId.FOUR_WHITE] == (ProgressKind.SAME, RouteStatus.WITNESSED)
    assert candidate.value_facts.routes

    # RETREAT：弃 1t 断链，链内飘白 1→0，距离 1→2。
    progress, _ = _progress_map(piao_obs, "discard:1t")
    assert progress[FamilyId.FOUR_WHITE] == (ProgressKind.RETREAT, RouteStatus.OPEN_UNCERTAIN)

    # UNKNOWN：链 1 且链内飘白未知（chain_piao=None）。
    unknown_obs = _observation(
        "1w 2w 3w 4w 5w 6w 7w 8w 9w 1t 2t 3t 白", draw="白",
        baotou=True, chain=1, piao_none=True,
    )
    progress, _ = _progress_map(unknown_obs, "discard:白")
    assert progress[FamilyId.FOUR_WHITE] == (ProgressKind.UNKNOWN, RouteStatus.OPEN_UNCERTAIN)


def test_four_white_advance_and_close_are_not_producible_matrix_boundary():
    """文档化边界：单动作不可能减少 4−(手留白+链内飘白)。

    吃/碰/杠/过不改手留白与链内飘白；飘白弃牌使 手留白−1/飘白+1 净持平；
    其余弃牌只减不增——four_white 的 ADVANCE 在本载荷版本不可构造，
    CLOSE 亦被来源表明确排除（不因单纯弃白写 CLOSE）。全样本扫描固化
    该边界，不伪造样例冒充覆盖。
    """

    fixtures = (
        _observation("1w 4w 7w 2b 5b 8b 3t 6t 9t 东 南 西 北", draw="中"),
        _observation("1w 2w 3w 4w 5w 6w 7w 8w 9w 1t 2t 3t 白", draw="白", baotou=True, chain=1, piao=1),
        _observation("9w 9w 9w 9w 1t 2t 3t 4t 5t 6t 7t 8t 9t", draw="西", chain=2, piao=1),
    )
    rules = _rules()
    for observation in fixtures:
        analysis = rules.analyze(observation, value_limits=ValueAnalysisLimits())
        for candidate in analysis.legal_candidates:
            for entry in candidate.facts.family_progress or ():
                if entry.family is FamilyId.FOUR_WHITE:
                    assert entry.progress is not ProgressKind.ADVANCE
                    assert entry.progress is not ProgressKind.CLOSE


def test_baotou_advance_same_retreat_unknown_matrix():
    """baotou：弃至任意听（ADVANCE）、保持（SAME）、弃出任意听（RETREAT）、
    胡终局转移未知（UNKNOWN）。"""

    any_win = "白 白 白 1w 2w 3w 4w 5w 6w 7w 8w 9w 1w"
    # ADVANCE + WITNESSED：弃东后 13 张任意听；路线条件爆头为真。
    advance_obs = _observation(any_win, draw="东")
    progress, candidate = _progress_map(advance_obs, "discard:东")
    assert progress[FamilyId.BAOTOU] == (ProgressKind.ADVANCE, RouteStatus.WITNESSED)
    assert any(route.conditions.baotou for route in candidate.value_facts.routes)

    # SAME：非爆头弃牌 False→False。
    garbage = _observation("1w 4w 7w 2b 5b 8b 3t 6t 9t 东 南 西 北", draw="中")
    progress, _ = _progress_map(garbage, "discard:1w")
    assert progress[FamilyId.BAOTOU] == (ProgressKind.SAME, RouteStatus.OPEN_UNCERTAIN)

    # RETREAT：已爆头弃 1w 后不再任意听。
    retreat_obs = _observation(
        "白 白 1w 2w 3w 4w 5w 6w 7w 8w 9w 1w 1w", draw="东", baotou=True,
    )
    progress, _ = _progress_map(retreat_obs, "discard:1w")
    assert progress[FamilyId.BAOTOU] == (ProgressKind.RETREAT, RouteStatus.OPEN_UNCERTAIN)
    # 对照：弃东保留任意听结构 → SAME。
    progress, _ = _progress_map(retreat_obs, "discard:东")
    assert progress[FamilyId.BAOTOU] == (ProgressKind.SAME, RouteStatus.WITNESSED)

    # UNKNOWN：胡是终局，动作后爆头无确定转移。
    hu_obs = _observation("1w 2w 3w 4w 5w 6w 7w 8w 9w 1b 2b 3b 4t", draw="4t")
    progress, candidate = _progress_map(hu_obs, "hu")
    assert progress[FamilyId.BAOTOU] == (ProgressKind.UNKNOWN, RouteStatus.OPEN_UNCERTAIN)
    assert candidate.facts.shanten_after == -1


def test_chain_close_not_defined_matrix_boundary():
    """文档化边界：chain 只有 增加/相同/减少；CLOSE 无规则语义（断链=RETREAT
    清零，不是关闭）。"""

    observation = _observation(
        "1w 2w 3w 4w 5w 6w 7w 8w 9w 1t 2t 3t 白", draw="白",
        baotou=True, chain=1, piao=1,
    )
    rules = _rules()
    analysis = rules.analyze(observation, value_limits=ValueAnalysisLimits())
    for candidate in analysis.legal_candidates:
        for entry in candidate.facts.family_progress or ():
            if entry.family in (FamilyId.CHAIN, FamilyId.BAOTOU):
                assert entry.progress is not ProgressKind.CLOSE


# ---------------------------------------------------------------------------
# 路线证据状态矩阵与见证来源
# ---------------------------------------------------------------------------


def test_route_status_witnessed_requires_value_routes():
    """WITNESSED 只来自 ValueRoute 条件见证；同一窗口无路线的候选为
    OPEN_UNCERTAIN（可达未见证），两者可并存。"""

    observation = _observation(
        "1w 2w 3w 4w 5w 6w 7w 8w 9w 1b 2b 3b 5t", draw="6t",
    )
    rules = _rules()
    analysis = rules.analyze(observation, value_limits=ValueAnalysisLimits())
    by_key = {c.action_key: c for c in analysis.legal_candidates}

    witnessed = by_key["discard:6t"]
    assert witnessed.value_facts.routes
    entry = next(e for e in witnessed.facts.family_progress if e.family is FamilyId.BRANCH)
    assert entry.route_status is RouteStatus.WITNESSED
    assert "向听" in entry.basis

    unwitnessed = by_key["discard:1b"]
    assert not unwitnessed.value_facts.routes
    entry = next(e for e in unwitnessed.facts.family_progress if e.family is FamilyId.BRANCH)
    assert entry.route_status is RouteStatus.OPEN_UNCERTAIN


def test_family_witnesses_follow_route_conditions():
    """四家族见证分别对应路线条件：chain_count>0、四白等值成立（含白摸入）、
    baotou=True；branch 只要任一一次摸牌成胡路线。"""

    piao_obs = _observation(
        "1w 2w 3w 4w 5w 6w 7w 8w 9w 1t 2t 3t 白", draw="白",
        baotou=True, chain=1, piao=1,
    )
    progress, candidate = _progress_map(piao_obs, "discard:白")
    assert progress[FamilyId.BRANCH][1] is RouteStatus.WITNESSED
    assert progress[FamilyId.CHAIN][1] is RouteStatus.WITNESSED
    assert progress[FamilyId.FOUR_WHITE][1] is RouteStatus.WITNESSED
    assert progress[FamilyId.BAOTOU][1] is RouteStatus.WITNESSED
    routes = candidate.value_facts.routes
    assert any(r.conditions.chain_count == 2 for r in routes)
    assert any(r.conditions.baotou for r in routes)


def test_all_analyzed_candidates_carry_four_family_entries():
    """开启分值分析后：HAND_PROGRESS/WIN 候选一律四条 FamilyId 声明序条目。"""

    observation = _observation(
        "1w 2w 3w 4w 5w 6w 7w 8w 9w 1b 2b 3b 4t", draw="4t",
    )
    analysis = _rules().analyze(observation, value_limits=ValueAnalysisLimits())
    assert analysis.legal_candidates
    for candidate in analysis.legal_candidates:
        facts = candidate.facts
        if facts is None or facts.fact_kind.value not in ("hand_progress", "win"):
            assert facts is None or facts.family_progress == ()
            continue
        assert [e.family for e in facts.family_progress] == list(FamilyId)
        for entry in facts.family_progress:
            assert entry.basis


# ---------------------------------------------------------------------------
# 预算与故障注入
# ---------------------------------------------------------------------------


def test_budget_limit_keeps_candidates_and_records_issue_without_degrading_analysis():
    """载荷超限：UNKNOWN+UNANALYZED 条目与 progression_payload.limit Issue；
    分析层 completeness 不降级（截断记录在 value_facts.issues，路线不删）。"""

    observation = _observation(
        "1w 4w 7w 2b 5b 8b 3t 6t 9t 东 南 西 北", draw="中",
    )
    analysis = _rules().analyze(
        observation, value_limits=ValueAnalysisLimits(max_expansions=1)
    )

    assert analysis.legal_candidates
    assert analysis.completeness.value == "complete"
    degraded = [
        c for c in analysis.legal_candidates
        if c.facts and c.facts.family_progress
        and c.facts.family_progress[0].route_status is RouteStatus.UNANALYZED
    ]
    assert degraded
    for candidate in degraded:
        assert any(
            issue.area == "progression_payload.limit"
            for issue in candidate.value_facts.issues
        )


def test_payload_failure_keeps_legal_candidates_emergency_and_degrades():
    """进展计算抛错：合法候选与紧急动作完整保留、followup_branches 不丢、
    family_progress 回落空元组（未分析）、completeness=DEGRADED（模块规范）。"""

    observation = _observation(
        "5w 5w 1t 2t 3t 4t 5t 6t 7t 8t 9t 2b 3b",
        phase="response_peng", response="5w",
    )
    rules = _rules()
    baseline = rules.analyze(observation, value_limits=ValueAnalysisLimits())

    def broken(*args, **kwargs):
        raise RuntimeError("进展计算故障注入")

    with mock.patch.object(progression_payload, "BeforeState", side_effect=broken):
        failed = rules.analyze(observation, value_limits=ValueAnalysisLimits())

    assert failed.completeness.value == "degraded"
    assert any(
        "进展计算故障注入" in issue.reason or "故障注入" in issue.reason
        for issue in failed.issues
    )
    # 合法候选集合与紧急动作保持。
    assert {c.action_key for c in failed.legal_candidates} == {
        c.action_key for c in baseline.legal_candidates
    }
    assert failed.emergency_candidate is not None
    assert failed.emergency_candidate.action_key == baseline.emergency_candidate.action_key
    # 事实回落：载荷未分析，机械分支保留，value_facts 整批失败可审计。
    peng = next(c for c in failed.legal_candidates if c.action_key == "peng:5w")
    assert peng.facts.followup_branches is not None
    assert peng.facts.family_progress == ()
    assert peng.value_facts.coverage is ValueCoverage.UNAVAILABLE
    for candidate in failed.legal_candidates:
        assert candidate.facts is None or candidate.facts.family_progress == ()


def test_payload_failure_does_not_affect_analysis_without_value_limits():
    """value_limits=None 时进展计算根本不运行：故障注入无影响。"""

    observation = _observation(
        "1w 2w 3w 4w 5w 6w 7w 8w 9w 1b 2b 3b 5t", draw="6t",
    )
    rules = _rules()

    def broken(*args, **kwargs):
        raise RuntimeError("不应触达")

    with mock.patch.object(progression_payload, "BeforeState", side_effect=broken):
        analysis = rules.analyze(observation)

    assert analysis.completeness.value == "complete"
    assert analysis.legal_candidates
