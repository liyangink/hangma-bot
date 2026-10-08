"""坐隐 2.1/M4 工具自测（REVIEW-6 修正后的口径）。

守住的易错点：
  1. `natural_draw_value` 事实缺失时返回 None（**不填 0**）；
  2. 机会成本只作用于 `scope` 内动作，默认**只吃碰**（R6-3）；
  3. 参数是**实例不可变状态**，并发/异常都不互相污染（S6-2）；
  4. 过滤与候选耗尽的**审计说明与 V2 对齐**，不静默丢候选（S6-3）；
  5. 窗口分类区分响应吃碰与自摸杠（S6-1-a）；
  6. 分差是**同层：最佳受影响 − 最佳退路**，可以为负（S6-1-b）；
  7. 排除记录**逐条留 ID 与原因**，不静默跳过（S6-3）。
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/tools'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import asyncio
import importlib.util
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_REPO = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, _REPO / "src")))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _project_file(_PROJECT_ROOT, _HERE / (name + ".py")))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


m4 = _load("sitin_m4_policy")
recompute = _load("sitin_m4_recompute")

from hangma_bot.application.deadline import ManualClock  # noqa: E402
from hangma_bot.hangma.interface import (  # noqa: E402
    CandidateFactKind,
    CandidateFacts,
    RuleAnalysis,
    RuleCandidate,
    RuleCompleteness,
)
from hangma_bot.kernel.actions import (  # noqa: E402
    Chi,
    Discard,
    Gang,
    GangKind,
    Hu,
    Pass,
    Peng,
    Tile,
    WindowKey,
    WindowPhase,
    action_key,
)
from hangma_bot.kernel.observation import (  # noqa: E402
    CompetitionContext,
    PlayerObservation,
    RulePublicState,
)
# **必须是 V2 的评分**：M4 与诊断的分差都建立在 V2 的过牌等待分项上。
# 若误用 V1（Pass 只有中性 0.0），全部分差会被系统性算错（见下方守卫测试）。
from hangma_bot.policy.evaluation_v2 import build_context, score_candidates  # noqa: E402
from hangma_bot.policy.interface import DecisionBudget, DecisionRequest  # noqa: E402
from hangma_bot.policy.weights_v1 import DEFAULT_WEIGHTS_V1  # noqa: E402


def _facts(shanten=3, useful=(("1w", 3), ("2w", 4))):
    from hangma_bot.hangma.interface import UsefulTileFact

    return CandidateFacts(
        CandidateFactKind.HAND_PROGRESS,
        shanten,
        useful_tiles=tuple(UsefulTileFact(code, n) for code, n in useful),
    )


def _cand(action, facts=None):
    return RuleCandidate(action=action, action_key=action_key(action), evidence=(), facts=facts)


def _observation():
    return PlayerObservation(
        game_id="g1", seat=0, round_no=1, snapshot_seq=10, phase="draw",
        dealer_seat=0, turn_seat=0, responding_seats=(), my_hand=(), drawn_tile=None,
        discards=((), (), (), ()), melds=((), (), (), ()),
        hand_counts=(13, 13, 13, 13), last_discard=None, remaining_tile_count=60,
        scores=(0, 0, 0, 0),
        rule_state=RulePublicState(wealth_god=Tile("白"), baotou=False,
                                   chain_count=0, catch_play=False),
        public_history=(),
    )


def _request(candidates, emergency=None, rejected=()):
    rules = RuleAnalysis(
        legal_candidates=tuple(candidates), emergency_candidate=emergency,
        completeness=RuleCompleteness.COMPLETE, ruleset_version="test-rules", issues=(),
    )
    observation = _observation()
    return DecisionRequest(
        observation=observation,
        competition=CompetitionContext(
            tournament_id="t1", stage_no=None, stage_role=None, stage_total=None,
            participant_rank=None, ranking=(), observed_at_unix_ms=0),
        rules=rules, decision_id="d1", trigger_seq=observation.snapshot_seq,
        window_key=WindowKey(game_id="g1", round_no=1, trigger_seq=10,
                             phase=WindowPhase.DRAW, seat=0),
        rejected_attempts=tuple(rejected),
    )


def _budget(now=0.0, enhancement=100.0):
    return DecisionBudget(enhancement, 200.0, 300.0)


# --- 参数与身份（2.2 基础） -------------------------------------------------

def test_params_are_frozen_and_validated():
    params = m4.M4Params(beta=1.0)
    with pytest.raises(FrozenInstanceError):
        params.beta = 2.0  # type: ignore[misc]
    with pytest.raises(ValueError):
        m4.M4Params(scope=("peng", "mystery"))
    with pytest.raises(ValueError):
        m4.M4Params(natural_ref=0.0)
    with pytest.raises(TypeError):
        m4.M4OpportunityCostPolicy(params={"beta": 1.0})  # type: ignore[arg-type]


def test_candidate_identity_tracks_params_and_source():
    """候选身份必须随 β 与 scope 变化，且含源码指纹（S6-3）。"""

    a = m4.M4OpportunityCostPolicy(params=m4.M4Params(beta=1.0))
    b = m4.M4OpportunityCostPolicy(params=m4.M4Params(beta=20.0))
    c = m4.M4OpportunityCostPolicy(params=m4.M4Params(beta=1.0, scope=("chi", "peng", "gang")))
    assert a.candidate_identity() != b.candidate_identity()
    assert a.candidate_identity() != c.candidate_identity()
    assert m4.source_fingerprint() in a.candidate_identity()


def test_effective_tile_multiplier_states_the_collinearity():
    """R6-1：追加项与 V2 已有项共线——β 只是把有效牌系数抬高。"""

    assert m4.M4Params(beta=20.0).effective_tile_multiplier(1.0) == pytest.approx(1.9524, abs=1e-4)
    assert m4.M4Params(beta=0.0).effective_tile_multiplier(1.0) == pytest.approx(1.0)


# --- natural_draw_value ------------------------------------------------------

def test_natural_draw_value_reads_pass_facts():
    # 契约要求 remaining_estimate 在 0—4（每种牌最多 4 张）
    pass_c = _cand(Pass(), _facts())
    assert m4.natural_draw_value((pass_c, _cand(Peng(Tile("1w"))))) == 7


def test_natural_draw_value_is_none_when_facts_missing():
    """缺事实时返回 None——**不填 0**，否则会假装摸牌无价值并放大鸣牌。"""

    assert m4.natural_draw_value((_cand(Pass()), _cand(Peng(Tile("1w"))))) is None
    not_applicable = CandidateFacts(CandidateFactKind.NOT_APPLICABLE, None)
    assert m4.natural_draw_value(
        (_cand(Pass(), not_applicable), _cand(Peng(Tile("1w"))))) is None
    degraded = CandidateFacts(
        CandidateFactKind.HAND_PROGRESS, 3, completeness=RuleCompleteness.DEGRADED)
    assert m4.natural_draw_value((_cand(Pass(), degraded),)) is None


# --- opportunity_cost -------------------------------------------------------

def test_opportunity_cost_is_scoped_to_chi_and_peng_by_default():
    """R6-3：杠的语义不同（明杠补牌、暗/补杠无响应 Pass），首版不纳入。"""

    assert m4.DEFAULT_PARAMS.scope == ("chi", "peng")
    for action in (Discard(Tile("1w")), Pass(), Hu()):
        assert m4.opportunity_cost(action, 40) == 0.0
    for action in (Peng(Tile("1w")), Chi((Tile("1w"), Tile("2w"), Tile("3w")))):
        assert m4.opportunity_cost(action, 40) < 0.0
    # 杠默认不受影响；显式放开后才受影响
    gang = Gang(Tile("1w"), GangKind.EXPOSED)
    assert m4.opportunity_cost(gang, 40) == 0.0
    assert m4.opportunity_cost(
        gang, 40, m4.M4Params(scope=("chi", "peng", "gang"))) < 0.0


def test_opportunity_cost_is_monotone_and_never_positive():
    """R6-2：本式**单向**——只能降低鸣牌排序，不可能抬高。"""

    peng = Peng(Tile("1w"))
    values = [m4.opportunity_cost(peng, n) for n in (5, 10, 20, 40, 80)]
    assert values == sorted(values, reverse=True), values
    assert values[0] != values[-1], "不得退化成常数——那只是重调固定惩罚"
    assert all(v <= 0.0 for v in values)
    assert all(v == 0.0 for v in (m4.opportunity_cost(peng, 0),
                                  m4.opportunity_cost(peng, None)))


def test_cap_bounds_the_adjustment():
    big = m4.opportunity_cost(Peng(Tile("1w")), 10 ** 6)
    assert abs(big) <= m4.DEFAULT_PARAMS.cap


# --- S6-2：参数隔离 ---------------------------------------------------------

def test_two_policies_with_different_params_do_not_interfere():
    """S6-2：参数属于实例；不同 β 的候选在同一进程内互不覆盖。"""

    clock = ManualClock(start_monotonic=0.0)
    low = m4.M4OpportunityCostPolicy(monotonic=clock.now, params=m4.M4Params(beta=1.0))
    high = m4.M4OpportunityCostPolicy(monotonic=clock.now, params=m4.M4Params(beta=20.0))
    assert low.params.beta == 1.0 and high.params.beta == 20.0
    # 交替取用不得改变任何一方
    for _ in range(3):
        assert low.params.beta == 1.0
        assert high.params.beta == 20.0
    assert m4.adjust((_cand(Peng(Tile("1w"))),), 21, low.params) != \
        m4.adjust((_cand(Peng(Tile("1w"))),), 21, high.params)


def test_policy_params_survive_an_exception_path():
    """S6-2 反例：异常分支不得留下被污染的参数（旧实现用模块全局会残留）。"""

    clock = ManualClock(start_monotonic=500.0)  # 已过截止时间 → choose 立刻超时
    policy = m4.M4OpportunityCostPolicy(
        monotonic=clock.now, params=m4.M4Params(beta=99.0))
    request = _request([_cand(Peng(Tile("1w")), _facts()), _cand(Pass(), _facts())])
    with pytest.raises(Exception):
        asyncio.run(policy.choose(request, _budget(enhancement=100.0)))
    # 异常后参数仍是构造时的值，且模块级没有可变全局可被残留
    assert policy.params.beta == 99.0
    assert not hasattr(m4, "_BETA")


# --- S6-3：审计对齐 ---------------------------------------------------------

def _run_choose(policy, request):
    return asyncio.run(policy.choose(request, _budget()))


def test_duplicate_and_missing_emergency_are_audited():
    """S6-3：重复候选与缺保底必须留下说明，不能静默丢弃。"""

    clock = ManualClock(start_monotonic=0.0)
    policy = m4.M4OpportunityCostPolicy(monotonic=clock.now)
    peng = _cand(Peng(Tile("1w")), _facts())
    plan = _run_choose(policy, _request([peng, peng, _cand(Pass(), _facts())]))
    reasons = tuple(plan.degraded_reasons)
    assert any("过滤重复候选" in r for r in reasons), reasons
    assert any("未提供紧急候选" in r for r in reasons), reasons


def test_empty_candidates_are_audited():
    clock = ManualClock(start_monotonic=0.0)
    policy = m4.M4OpportunityCostPolicy(monotonic=clock.now)
    plan = _run_choose(policy, _request([]))
    assert plan.candidates == ()
    assert any("计划为空" in r for r in plan.degraded_reasons), plan.degraded_reasons


def test_enabled_policy_audits_the_candidate_identity():
    """S6-3：启用时的审计必须带上候选身份，便于与产物关联。"""

    clock = ManualClock(start_monotonic=0.0)
    policy = m4.M4OpportunityCostPolicy(
        monotonic=clock.now, params=m4.M4Params(beta=5.0))
    plan = _run_choose(policy, _request(
        [_cand(Peng(Tile("1w")), _facts()), _cand(Pass(), _facts())]))
    joined = " ".join(plan.degraded_reasons)
    assert policy.candidate_identity() in joined, joined


# --- S6-1-a：窗口分类 -------------------------------------------------------

def test_window_class_separates_self_draw_gang_from_response():
    """自摸暗杠/补杠**没有响应 Pass**，不得算作响应窗口（S6-1-a）。"""

    assert recompute.window_class(["gang:concealed:1w", "discard:1w"]) == "self_draw_gang"
    assert recompute.window_class(["gang:added:1w", "discard:1w"]) == "self_draw_gang"
    assert recompute.window_class(["peng:1w", "pass"]) == "response"
    assert recompute.window_class(["chi:1w2w3w", "pass"]) == "response"
    assert recompute.window_class(["gang:exposed:1w", "pass"]) == "response"
    assert recompute.window_class(["discard:1w", "pass"]) == "other"


# --- S6-1-b：分差口径 -------------------------------------------------------

def _scored(candidates):
    async def _no_deadline():
        return None

    return asyncio.run(score_candidates(
        tuple(candidates), build_context(_observation()), DEFAULT_WEIGHTS_V1, _no_deadline))


def test_tier_gap_measures_best_affected_minus_best_pass():
    scored = _scored([_cand(Peng(Tile("1w")), _facts()), _cand(Pass(), _facts())])
    info = recompute.tier_gap(scored)
    assert info["gap"] is not None
    assert info["best_affected"]["key"] == "peng:1w"
    assert info["best_fallback"]["key"] == "pass"
    assert info["gap"] == pytest.approx(
        info["best_affected"]["score"] - info["best_fallback"]["score"])


def test_tier_gap_can_be_negative_unlike_the_top2_spread():
    """S6-1-b 的反例：v1 用"数值前两名之差"，该值**恒非负**，
    无法表达"鸣牌已经领先退路"。正确口径必须允许负值。
    """

    # 碰与过都带牌效事实 → 同为可信层；过略高于碰 ⇒ 分差为负
    scored = _scored([_cand(Peng(Tile("1w")), _facts()), _cand(Pass(), _facts())])
    gap = recompute.tier_gap(scored)["gap"]
    assert gap is not None and gap < 0, gap
    # 旧口径（全部候选数值前两名之差）在同一输入上恒 >= 0，掩盖了方向
    totals = sorted((c.total for c in scored), reverse=True)
    assert totals[0] - totals[1] >= 0


def test_cross_tier_pair_hides_behind_a_large_positive_top2_spread():
    """S6-1-b 的核心反例：v1 会把**跨层**的两个候选当成可比较分差。

    无事实的碰（未知层，分数高）与有事实的过（可信层，分数低）：
    旧口径报告一个很大的**正**分差，正确口径必须说"跨层不可比"。
    """

    scored = _scored([_cand(Peng(Tile("1w"))), _cand(Pass(), _facts())])
    info = recompute.tier_gap(scored)
    assert info["gap"] is None and info["reason"] == "cross_tier"
    assert {c.priority for c in scored} == {1, 2}
    # 旧口径在此输入上给出一个**正**分差，看起来像"鸣牌领先多少"，
    # 实际是两个不可比层级相减，方向毫无意义。
    totals = sorted((c.total for c in scored), reverse=True)
    assert totals[0] - totals[1] > 0


def test_diagnostics_must_use_v2_scoring_not_v1():
    """守卫：诊断分差必须建立在 V2 的过牌等待分项上。

    V1 的 Pass 只有中性 0.0；若误用 V1，过牌等待越高反而分差越离谱，
    整套分差会被系统性算错，而且**不会报错**。
    """

    import hangma_bot.policy.evaluation_v2 as v2

    assert recompute.score_candidates is v2.score_candidates,         "重算驱动必须用 V2 评分计算基线分差"
    pass_scored = _scored([_cand(Pass(), _facts())])[0]
    expected = -DEFAULT_WEIGHTS_V1.shanten_step * 3 + 7
    assert pass_scored.total == pytest.approx(expected),         "V2 过牌评分 = -shanten_step×向深 + 有效牌剩余；V1 会给 0.0"


def test_tier_gap_refuses_to_compare_across_tiers():
    """跨可信层不得直接给分差，必须显式分层（S6-1-b）。"""

    strong = _cand(Pass(), _facts())
    weak = _cand(Peng(Tile("1w")))
    scored = _scored([strong, weak])
    info = recompute.tier_gap(scored)
    tiers = {c.priority for c in scored}
    if len(tiers) > 1:
        assert info["gap"] is None and info["reason"] == "cross_tier"
    else:
        assert info["gap"] is not None


def test_tier_gap_reports_missing_fallback():
    scored = _scored([_cand(Peng(Tile("1w")), _facts())])
    info = recompute.tier_gap(scored)
    assert info["gap"] is None and info["reason"] == "no_pass_fallback"


# --- S6-3：排除不留白 -------------------------------------------------------

def test_recompute_records_excluded_rows_instead_of_silently_skipping():
    """S6-3 反例：旧工具遇到没有 request 的输入会**全部静默消失**且 degraded=0。"""

    rows = [{"decision_id": "x1"}, {"decision_id": "x2"}, {"nope": 1}]
    result = recompute.measure(rows, "v26", betas=(1.0,))
    assert result["inputs"]["rows"] == 3
    assert result["inputs"]["analysed"] == 0
    assert result["inputs"]["excluded"] == 3
    assert {e["reason"] for e in result["excluded_records"]} == {"no_request_payload"}
    assert [e["decision_id"] for e in result["excluded_records"]] == ["x1", "x2", None]


def test_recompute_output_is_traceable():
    """S6-3：产物必须带规则配置、基线权重与源码指纹。"""

    result = recompute.measure([], "v26", betas=(1.0,))
    assert result["rules"]["ruleset_version"] == "v26"
    assert result["baseline"]["weights"]["effective_tile"] == DEFAULT_WEIGHTS_V1.effective_tile
    assert result["source_fingerprints"]["m4_policy_fingerprint"] == m4.source_fingerprint()
    assert result["cross_check"]["expected"] == 0

# --- REVIEW-6 §4 第一步要求的进入批量运行前的四类测试 -----------------------

def test_legal_action_source_is_rules_not_invented():
    """合法动作来源：M4 只能对 `RuleAnalysis` 给的候选排序，不得自造动作。"""

    clock = ManualClock(start_monotonic=0.0)
    policy = m4.M4OpportunityCostPolicy(monotonic=clock.now)
    peng = _cand(Peng(Tile("1w")), _facts())
    plan = _run_choose(policy, _request([peng, _cand(Pass(), _facts())]))
    given = {"peng:1w", "pass"}
    produced = {c.action_key for c in plan.candidates}
    assert produced <= given, produced - given


def test_rejected_candidates_are_excluded_and_audited():
    """拒绝过滤：已明确拒绝的候选不得进入计划，且必须留审计说明。"""

    from hangma_bot.policy.interface import RejectedAttempt

    clock = ManualClock(start_monotonic=0.0)
    policy = m4.M4OpportunityCostPolicy(monotonic=clock.now)
    rejected = (RejectedAttempt(action_key="peng:1w", official_code="409",
                                attempt_no=1, based_on_authoritative_seq=10),)
    plan = _run_choose(policy, _request(
        [_cand(Peng(Tile("1w")), _facts()), _cand(Pass(), _facts())], rejected=rejected))
    assert "peng:1w" not in {c.action_key for c in plan.candidates}
    assert any("过滤已拒绝候选" in r for r in plan.degraded_reasons), plan.degraded_reasons


def test_emergency_candidate_is_preserved_and_flagged():
    """保底：紧急候选必须在计划中保留，并带 is_emergency 标记。"""

    clock = ManualClock(start_monotonic=0.0)
    policy = m4.M4OpportunityCostPolicy(monotonic=clock.now)
    # 紧急候选必须同时是规则给出的合法候选，才会进入计划（V2 语义）
    emergency = _cand(Discard(Tile("9w")))
    plan = _run_choose(policy, _request(
        [_cand(Peng(Tile("1w")), _facts()), emergency, _cand(Pass(), _facts())],
        emergency=emergency))
    keys = {c.action_key for c in plan.candidates}
    assert "discard:9w" in keys, keys
    flagged = [c for c in plan.candidates if c.is_emergency]
    assert [c.action_key for c in flagged] == ["discard:9w"]


def test_past_enhancement_deadline_raises_before_producing_a_plan():
    """截止时间：增强预算过期必须抛错，交由应用层已有保底，而不是硬算下去。"""

    from hangma_bot.policy.errors import PolicyTimeoutError

    clock = ManualClock(start_monotonic=500.0)
    policy = m4.M4OpportunityCostPolicy(monotonic=clock.now)
    request = _request([_cand(Peng(Tile("1w")), _facts()), _cand(Pass(), _facts())])
    with pytest.raises(PolicyTimeoutError):
        asyncio.run(policy.choose(request, _budget(enhancement=100.0)))


def test_plan_is_deterministic_for_same_input():
    """同输入、同配置输出完全确定（AGENTS.md policy 计划不变量）。"""

    clock = ManualClock(start_monotonic=0.0)
    policy = m4.M4OpportunityCostPolicy(monotonic=clock.now, params=m4.M4Params(beta=10.0))
    request = _request([_cand(Peng(Tile("1w")), _facts()),
                        _cand(Chi((Tile("1w"), Tile("2w"), Tile("3w"))), _facts()),
                        _cand(Pass(), _facts())])
    a = _run_choose(policy, request)
    b = _run_choose(policy, request)
    assert [(c.rank, c.action_key, c.total_score) for c in a.candidates] == \
        [(c.rank, c.action_key, c.total_score) for c in b.candidates]
