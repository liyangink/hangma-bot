"""启发式适配器与候选注册表的契约测试（README §17 2.2；见 SEAM-DESIGN.md §8）。

守住的设计判据：
  A2 消融等价（`adjustments=()` 逐字节等于基线，构造保证 + 本测试）
  A3 候选隔离（不同参数实例互不污染）
  A4 合法动作来源（产物候选 ⊆ 规则给的候选）
  A5 拒绝过滤（守住"漏 continue 会把已拒动作重新提交"那次缺陷）
  A6 保底保留、A7 截止时间、A8 有界、A9 纯度、A11 合法胡仍在第一
另守住装载纪律：注册表是静态显式、未知名不静默回退、参数前缀拆分、G-3 触发条件必填。
"""

import asyncio
import hashlib
import importlib.util
from dataclasses import replace
from pathlib import Path

import pytest

from hangma_bot.hangma.interface import (
    CandidateFactKind,
    CandidateFacts,
    RuleCandidate,
    RuleCompleteness,
    UsefulTileFact,
)
from hangma_bot.kernel.actions import Discard, Hu, Pass, Peng, Tile, action_key
from hangma_bot.policy import heuristics
from hangma_bot.policy.errors import PolicyTimeoutError
from hangma_bot.policy.heuristic_adapter import (
    AdjustmentSpec,
    HeuristicAdjustment,
    HeuristicAdjustmentPolicy,
    action_kind,
)
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2
from hangma_bot.policy.heuristics import meld_opportunity_cost as meld

from .support import make_budget, make_observation, make_request, make_rules, rejected
from .test_hu_upgrade import historical

HISTORICAL = list("ABCDEFGH")


def _facts(shanten=3, useful=(("1w", 3), ("2w", 4))):
    return CandidateFacts(
        CandidateFactKind.HAND_PROGRESS, shanten,
        useful_tiles=tuple(UsefulTileFact(code, n) for code, n in useful))


def _cand(action, facts=None):
    return RuleCandidate(action=action, action_key=action_key(action), evidence=(),
                         facts=facts)


def _response_request(candidates, emergency=None, rejected_attempts=()):
    """构造一个带等待事实的响应窗口请求（吃碰 + 过）。"""

    rules = make_rules(candidates, emergency=emergency)
    return make_request(make_observation(), rules, rejected=rejected_attempts)


def _policy(adjustment, enabled=True):
    return HeuristicAdjustmentPolicy(adjustment, monotonic=lambda: 0.0, enabled=enabled)


def _m4(**params):
    return meld.build_adjustment(meld.MeldCostParams(**params))


# --- A2 消融等价：构造保证 + 逐字节验证 -------------------------------------

@pytest.mark.parametrize("name", HISTORICAL)
def test_ablation_is_bit_identical_to_baseline_on_historical_cases(name):
    """关闭候选必须**逐字节**等于基线；这是"关闭即等价"的构造保证的外部验证。"""

    request = historical(name)
    baseline = asyncio.run(
        ComparableHeuristicPolicyV2(monotonic=lambda: 0.0).choose(request, make_budget()))
    empty = asyncio.run(
        ComparableHeuristicPolicyV2(monotonic=lambda: 0.0, adjustments=()).choose(
            request, make_budget()))
    disabled = asyncio.run(_policy(_m4(), enabled=False).choose(request, make_budget()))
    assert empty == baseline
    assert disabled == baseline


def test_turning_the_candidate_on_preserves_the_plan_when_it_does_not_apply():
    """无等待事实的窗口上，启用候选也必须与基线一致（不改别的动作）。"""

    request = historical("A")
    baseline = asyncio.run(
        ComparableHeuristicPolicyV2(monotonic=lambda: 0.0).choose(request, make_budget()))
    enabled = asyncio.run(_policy(_m4()).choose(request, make_budget()))
    if meld.natural_draw_value(request.rules.legal_candidates) is None:
        assert enabled == baseline


# --- A3 候选隔离 ------------------------------------------------------------

def test_two_parameterisations_do_not_interfere():
    """参数属于实例；交替调用不得互相污染（REVIEW-6 S6-2 的教训）。"""

    low = _policy(_m4(beta=1.0))
    high = _policy(_m4(beta=20.0))
    assert low.identity() != high.identity()
    assert "beta=1.0" in low.identity() and "beta=20.0" in high.identity()
    for _ in range(3):
        assert "beta=1.0" in low.identity()
        assert "beta=20.0" in high.identity()


# --- A4/A5/A6/A7/A11：V2 管线的不变量必须原样保留 ---------------------------

def _response_plan(policy, candidates, **kwargs):
    return asyncio.run(policy.choose(_response_request(candidates, **kwargs), make_budget()))


def test_legal_action_source_is_the_rule_analysis():
    given = {"peng:1w", "pass"}
    plan = _response_plan(_policy(_m4(beta=20.0)),
                          [_cand(Peng(Tile("1w")), _facts()), _cand(Pass(), _facts())])
    produced = {c.action_key for c in plan.candidates}
    assert produced <= given, produced - given


def test_rejected_candidate_is_excluded_and_audited():
    """守住那次缺陷：过滤分支漏 continue 会把官方已拒绝的动作重新提交。"""

    plan = _response_plan(
        _policy(_m4(beta=20.0)),
        [_cand(Peng(Tile("1w")), _facts()), _cand(Pass(), _facts())],
        rejected_attempts=(rejected("peng:1w"),))
    assert "peng:1w" not in {c.action_key for c in plan.candidates}
    assert any("过滤已拒绝候选" in r for r in plan.degraded_reasons)


def test_emergency_candidate_is_preserved():
    emergency = _cand(Discard(Tile("9w")))
    plan = _response_plan(
        _policy(_m4(beta=20.0)),
        [_cand(Peng(Tile("1w")), _facts()), emergency, _cand(Pass(), _facts())],
        emergency=emergency)
    keys = {c.action_key for c in plan.candidates}
    assert "discard:9w" in keys, keys
    assert [c.action_key for c in plan.candidates if c.is_emergency] == ["discard:9w"]


def test_past_deadline_raises_instead_of_computing():
    """截止时间：过期必须抛错交由应用层保底，而不是硬算下去。

    注入时钟停在 500，增强截止设为 100 ⇒ 首次检查即过期。
    """

    policy = HeuristicAdjustmentPolicy(_m4(beta=20.0), monotonic=lambda: 500.0)
    request = _response_request(
        [_cand(Peng(Tile("1w")), _facts()), _cand(Pass(), _facts())])
    with pytest.raises(PolicyTimeoutError):
        asyncio.run(policy.choose(request, make_budget(enhancement=100.0)))


def test_legal_hu_stays_first():
    """层级纪律：合法胡永远在第一（README §5 与 REVIEW-6 的核心约束）。"""

    request = historical("A")
    plan = asyncio.run(_policy(_m4(beta=20.0)).choose(request, make_budget()))
    if plan.candidates and any(isinstance(c.action, Hu) for c in plan.candidates):
        assert isinstance(plan.candidates[0].action, Hu)


# --- 候选数学与 scope ------------------------------------------------------

def test_candidate_only_affects_chi_and_peng():
    params = meld.MeldCostParams(beta=20.0)
    assert params.scope == ("chi", "peng")
    for action in (Discard(Tile("1w")), Pass(), Hu()):
        assert meld.opportunity_cost(action, 40, params) == 0.0


def test_candidate_is_monotone_and_never_positive():
    params = meld.MeldCostParams(beta=20.0)
    values = [meld.opportunity_cost(Peng(Tile("1w")), n, params) for n in (5, 10, 21, 40, 85)]
    assert values == sorted(values, reverse=True)
    assert all(v <= 0.0 for v in values)


def test_natural_draw_value_is_none_when_facts_missing():
    """缺事实时按未知处理，**不填 0**（填 0 会假装摸牌无价值并放大鸣牌）。"""

    assert meld.natural_draw_value((_cand(Peng(Tile("1w"))),)) is None
    degraded = CandidateFacts(CandidateFactKind.HAND_PROGRESS, 3,
                              completeness=RuleCompleteness.DEGRADED)
    assert meld.natural_draw_value((_cand(Pass(), degraded),)) is None


def test_beta_reads_the_existing_weight_it_rescales():
    """§E / R6-1：本项与 V2 既有项共线——β=20 即把有效牌系数抬到约 1.95 倍。"""

    assert meld.MeldCostParams(beta=20.0).effective_tile_multiplier(1.0) == pytest.approx(
        1.9524, abs=1e-4)
    assert meld.MeldCostParams(beta=0.0).effective_tile_multiplier(1.0) == pytest.approx(1.0)


# --- A8 有界 + 越界不静默 ---------------------------------------------------

def test_out_of_bound_delta_is_clamped_and_audited():
    """越界必须钳制**并留审计**——静默钳制会掩盖候选缺陷。"""

    spec = AdjustmentSpec(name="测试越界项", version="t-v1", thought="测试用",
                          trigger="总是触发", scope=("peng",), bound=1.0)
    adjustment = HeuristicAdjustment(
        spec, lambda candidate, ctx, candidates: -50.0,
        source_fingerprint_value="deadbeef")
    request = _response_request(
        [_cand(Peng(Tile("1w")), _facts()), _cand(Pass(), _facts())])
    plan = asyncio.run(_policy(adjustment).choose(request, make_budget()))
    peng = next(c for c in plan.candidates if c.action_key == "peng:1w")
    parts = {p.name: p.value for p in peng.score_parts}
    assert parts["测试越界项"] == -1.0
    assert adjustment.clamped_count >= 1
    assert any("候选越界已钳制" in r for r in peng.reasons)


def test_registered_candidate_respects_its_own_bound_on_real_windows():
    """A8：注册候选的**实际** delta 必须落在它自己声明的 bound 内。"""

    adjustment = _m4(beta=1000.0)
    request = _response_request(
        [_cand(Peng(Tile("1w")), _facts()), _cand(Pass(), _facts())])
    plan = asyncio.run(_policy(adjustment).choose(request, make_budget()))
    for candidate in plan.candidates:
        for part in candidate.score_parts:
            if part.name == adjustment.spec.name:
                assert abs(part.value) <= adjustment.spec.bound


# --- A9 纯度（G-1） ---------------------------------------------------------

def test_candidate_is_deterministic():
    request = _response_request(
        [_cand(Peng(Tile("1w")), _facts()), _cand(Pass(), _facts())])
    policy = _policy(_m4(beta=20.0))
    first = asyncio.run(policy.choose(request, make_budget()))
    second = asyncio.run(policy.choose(request, make_budget()))
    assert first == second


def test_candidate_module_has_no_io_or_nondeterministic_imports():
    """G-1 静态门禁：候选模块不得引入 IO、时间、随机或子进程能力。"""

    banned = {"os", "io", "sys", "time", "random", "socket", "subprocess",
              "pathlib", "requests", "urllib", "shutil", "threading",
              "multiprocessing", "asyncio"}
    spec = importlib.util.find_spec("hangma_bot.policy.heuristics.meld_opportunity_cost")
    source = Path(spec.origin).read_text(encoding="utf-8")
    imported = set()
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            head = stripped.split()[1]
            imported.add(head.split(".")[0])
    assert not (imported & banned), imported & banned


def test_spec_requires_a_trigger_description():
    """G-3：缺少触发条件说明的候选不得进入队列。"""

    with pytest.raises(ValueError):
        AdjustmentSpec(name="x", version="v", thought="t", trigger="   ",
                       scope=("peng",), bound=1.0)
    with pytest.raises(ValueError):
        AdjustmentSpec(name="x", version="v", thought="t", trigger="t",
                       scope=(), bound=1.0)
    with pytest.raises(ValueError):
        AdjustmentSpec(name="x", version="v", thought="t", trigger="t",
                       scope=("peng",), bound=0.0)


# --- 装载：静态注册表、参数前缀、未知名不静默回退 ---------------------------

def test_registry_is_static_and_exposes_the_first_candidate():
    assert "meld_opportunity_cost" in heuristics.candidate_names()
    assert heuristics.is_candidate("meld_opportunity_cost")
    assert not heuristics.is_candidate("weighted_heuristic_v2")


def test_unknown_candidate_name_raises_instead_of_falling_back():
    with pytest.raises(KeyError) as info:
        heuristics.build_candidate("no_such_candidate")
    assert "meld_opportunity_cost" in str(info.value)


def test_declaration_params_split_on_the_adj_prefix():
    params, base = heuristics.split_declaration_params(
        {"adj.beta": 20.0, "shanten_step": 100.0, "effective_tile": 1.0})
    assert params == {"beta": 20.0}
    assert base == {"shanten_step": 100.0, "effective_tile": 1.0}


def test_unknown_candidate_param_key_raises():
    """参数写错必须报错，不能静默用默认值——那会让实验标签与实际行为不符。"""

    with pytest.raises(ValueError):
        meld.build_adjustment_from_params({"betta": 20.0})


def test_build_candidate_carries_identity_and_base_weights():
    policy = heuristics.build_candidate(
        "meld_opportunity_cost",
        weights={"adj.beta": 20.0, "shanten_step": 100.0})
    assert "beta=20.0" in policy.identity()
    assert "meld-opportunity-cost-v1" in policy.identity()
    assert isinstance(policy.base_policy, ComparableHeuristicPolicyV2)


def test_source_fingerprint_is_supplied_by_the_loader_and_matches_the_module():
    """指纹由装载方计算；缺省时**省略该段**而不是填占位符。

    这样"未计算"与"已计算"在身份串上可区分，且不会读到一个假指纹。
    本测试同时防漂移：装载方算出来的值必须等于候选模块源码的真实摘要。
    """

    without = heuristics.build_candidate("meld_opportunity_cost")
    assert "+src" not in without.identity()

    module = heuristics.candidate_module("meld_opportunity_cost")
    real = hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()[:16]
    with_fp = heuristics.build_candidate(
        "meld_opportunity_cost", source_fingerprint_value=real)
    assert with_fp.identity().endswith("+src" + real)


def test_candidate_module_accessor_rejects_unknown_names():
    with pytest.raises(KeyError):
        heuristics.candidate_module("no_such_candidate")


def test_action_kind_matches_product_convention():
    assert action_kind("peng:1w") == "peng"
    assert action_kind("discard:白") == "discard"
    assert action_kind(None) == ""

# --- 2.5 合法动作与保底不变量 + 故障注入 ------------------------------------

def _adjustment_with(delta, *, bound=300.0, scope=("chi", "peng")):
    spec = AdjustmentSpec(name="故障注入项", version="fault-v1", thought="故障注入",
                          trigger="总是触发", scope=scope, bound=bound)
    return HeuristicAdjustment(spec, delta, source_fingerprint_value="deadbeef")


def test_candidate_exception_propagates_so_the_app_can_fall_back():
    """候选异常**不得被适配器吞掉**：应用层必须能看到它并改用紧急保底。

    适配器只做"追加分项"，不接管错误处理——吞掉异常会让线上处于
    "计划看起来正常但其实没算完"的危险状态。
    """

    def boom(candidate, ctx, candidates):
        raise RuntimeError("注入的候选故障")

    request = _response_request(
        [_cand(Peng(Tile("1w")), _facts()), _cand(Pass(), _facts())])
    with pytest.raises(RuntimeError):
        asyncio.run(_policy(_adjustment_with(boom)).choose(request, make_budget()))


def test_candidate_returning_non_numeric_is_rejected():
    request = _response_request(
        [_cand(Peng(Tile("1w")), _facts()), _cand(Pass(), _facts())])
    with pytest.raises(TypeError):
        asyncio.run(_policy(_adjustment_with(lambda c, x, y: "很便宜")).choose(
            request, make_budget()))


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_candidate_returning_non_finite_is_rejected(value):
    """非有限值必须立刻失败，交由应用层保底——不能带着 NaN 去排序。"""

    request = _response_request(
        [_cand(Peng(Tile("1w")), _facts()), _cand(Pass(), _facts())])
    with pytest.raises(ValueError):
        asyncio.run(_policy(_adjustment_with(lambda c, x, y: value)).choose(
            request, make_budget()))


def test_degraded_rules_still_produce_a_plan():
    """规则降级时候选仍须产出保守计划，并把降级原因写进审计。"""

    from hangma_bot.hangma.interface import RuleIssue

    rules = make_rules(
        [_cand(Peng(Tile("1w")), _facts()), _cand(Pass(), _facts())],
        completeness=RuleCompleteness.DEGRADED,
        issues=(RuleIssue(area="hu", reason="注入的规则分支失败"),))
    request = make_request(make_observation(), rules)
    plan = asyncio.run(_policy(_m4(beta=20.0)).choose(request, make_budget()))
    assert plan.candidates, "降级也必须给出计划"
    assert any("DEGRADED" in r for r in plan.degraded_reasons)
    assert any("规则降级" in r for r in plan.degraded_reasons)


def test_empty_candidates_produce_an_audited_empty_plan():
    request = make_request(make_observation(), make_rules([]))
    plan = asyncio.run(_policy(_m4(beta=20.0)).choose(request, make_budget()))
    assert plan.candidates == ()
    assert any("计划为空" in r for r in plan.degraded_reasons)


def test_unknown_facts_put_the_emergency_candidate_first():
    """事实全未知、且**没有过牌候选**时，紧急候选必须排在最前（保底不变量）。

    注意分支优先级：只要存在过牌候选且缺可比等待基线，V2 的既有规则是
    "合法胡优先，其次使用未拒绝的过牌退路"——此时过牌**故意**排在紧急候选之前。
    因此要触发"全部未知 ⇒ 紧急优先"分支，候选里必须没有 Pass。
    """

    emergency = _cand(Discard(Tile("9w")))
    request = _response_request(
        [_cand(Peng(Tile("1w"))), emergency], emergency=emergency)
    plan = asyncio.run(_policy(_m4(beta=20.0)).choose(request, make_budget()))
    assert plan.candidates[0].action_key == "discard:9w"
    assert plan.candidates[0].is_emergency
    assert any("全部候选事实未知" in r for r in plan.degraded_reasons)


def test_factless_pass_retreat_outranks_the_emergency_candidate():
    """反向记录 V2 的既有语义：缺等待基线时过牌退路优先于紧急候选。

    这是**既有行为**，适配器不得改变它；把它写成测试是为了防止将来
    有人"顺手"调换这两个分支的优先级。
    """

    emergency = _cand(Discard(Tile("9w")))
    request = _response_request(
        [_cand(Peng(Tile("1w"))), emergency, _cand(Pass())], emergency=emergency)
    plan = asyncio.run(_policy(_m4(beta=20.0)).choose(request, make_budget()))
    assert plan.candidates[0].action_key == "pass"
    assert any("缺可比等待基线" in r for r in plan.degraded_reasons)


def test_disabled_candidate_is_identical_even_under_fault_injection():
    """关闭候选时，即使候选本身会抛异常也**不得**被调用（构造保证）。"""

    called = {"n": 0}

    def counting_boom(candidate, ctx, candidates):
        called["n"] += 1
        raise RuntimeError("不应被调用")

    request = _response_request(
        [_cand(Peng(Tile("1w")), _facts()), _cand(Pass(), _facts())])
    plan = asyncio.run(_policy(_adjustment_with(counting_boom), enabled=False).choose(
        request, make_budget()))
    assert called["n"] == 0
    assert plan.candidates
