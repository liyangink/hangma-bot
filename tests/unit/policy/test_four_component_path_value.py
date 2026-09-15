"""价值族③（四分量完整结构基线）的契约测试与势差结构测试。

三组断言，对应 PLAN-REVISION §1.2 / §3.0 的验收项：

  C 组（契约）：静态注册、参数往返进身份、bound 由声明域推导、未知键拒绝、
      适配器只做唯一一次钳制（候选内部不裁剪）、纯函数与确定性；
  S 组（势差结构）：term = Φ(s′) − Φ(s)、可加性、环判据、动作标签无关性、
      **路径存活内部的变化不被吞掉**（R8-2 的教训）、终局例外；
  U 组（不猜）：未知事实不填 0 / 不填 False、越出声明域只收窄不惩罚、
      四白等值条件与"飘不改变四白之和"。

**本文件不构成准入或效果证据**：它只证明结构与接线，代表语料准入与效果评估
是另外两步（README §17.1 第 3 条：工具完成 / 发现候选 / 通过发布门禁分开报）。
"""

import math
from dataclasses import replace

import pytest

from hangma_bot.hangma.interface import RuleCandidate
from hangma_bot.kernel.actions import (
    Chi,
    Discard,
    Gang,
    GangKind,
    Hu,
    Pass,
    Peng,
    Tile,
    action_key,
)
from hangma_bot.policy.evaluation_v1 import ScoredCandidate, build_context
from hangma_bot.policy.heuristics import four_component_path_value as fc
from hangma_bot.policy import heuristics

from .support import WEALTH_CODE, make_observation

SCALE = 40.0
PARAMS = fc.FourComponentPathParams()

#: 13 张暗牌：三组"恰好 4 张"（豪华候选）+ 1 张散牌。
LUXURY_HAND = ("1w", "1w", "1w", "1w", "2b", "2b", "2b", "2b",
               "3t", "3t", "3t", "3t", "9w")
#: 14 张（13 张 + 摸到第 14 张）：用于含刚摸牌的形态。
FULL_HAND = LUXURY_HAND + ("5b",)
#: 13 张含全部 4 张财神（四白已锁定）+ 三个自然面子，摸任意一张即 14 张。
WEALTH_HAND = ("白",) * 4 + ("1w",) * 3 + ("2b",) * 3 + ("3t",) * 3

WEALTH = Tile(WEALTH_CODE)
OTHER = Tile("9w")
GANG = Gang(Tile("2b"), GangKind.EXPOSED)


def _cand(action) -> RuleCandidate:
    return RuleCandidate(action=action, action_key=action_key(action),
                         evidence=(), facts=None)


def _ctx(**overrides):
    """从最小观察构造上下文；只覆盖需要的字段，其余保持真实构建结果。"""

    return replace(build_context(make_observation()), **overrides)


def _hand_ctx(codes, *, drawn=None, **overrides):
    """按牌码构造上下文；`drawn` 非空时模拟"刚摸到这张"的形态。"""

    observation = make_observation(
        my_hand=tuple(Tile(code) for code in codes),
        drawn_tile=None if drawn is None else Tile(drawn))
    return replace(build_context(observation), **overrides)


def _state(**overrides) -> fc.PathState:
    base = dict(branch_log2=1.0, chain_count=0, four_white=False, baotou=False)
    base.update(overrides)
    return fc.PathState(**base)


def _apply(action, ctx, adjustment):
    """走**适配器**算一次调整：返回 (生效分项值, 钳制次数, 触发次数)。"""

    item = ScoredCandidate(priority=1, candidate=_cand(action),
                           action_key=action_key(action), parts=(), reasons=(),
                           total=0.0, shanten=None, is_safe_discard=False)
    applied = adjustment.apply(item, ctx, (_cand(action),))
    value = applied.parts[-1].value if applied.parts else 0.0
    if applied.parts:
        assert applied.parts[-1].name == adjustment.spec.name
    return value, adjustment.clamped_count, adjustment.fired_count


# --- C 组：契约（注册 / 身份 / bound / 唯一强制点） ---------------------------


def test_candidate_is_registered_in_the_static_registry() -> None:
    """静态注册表是**唯一**装载入口（不是插件系统、不是自动扫描）。"""

    assert heuristics.is_candidate("four_component_path_value")
    assert "four_component_path_value" in heuristics.candidate_names()
    assert heuristics.candidate_module("four_component_path_value") is fc


def test_declared_spec_is_complete() -> None:
    """G-3 要求的 name / thought / trigger / scope / bound 必须齐全且非空。"""

    spec = fc.build_adjustment().spec
    assert spec.version == fc.FOUR_COMPONENT_VERSION
    assert spec.name.strip() and spec.thought.strip() and spec.trigger.strip()
    assert set(spec.scope) == {"chi", "peng", "gang", "discard", "pass", "hu"}
    assert spec.bound == pytest.approx(480.0)          # 40 × (4 + 6 + 1 + 1)


def test_bound_is_derived_from_the_declared_caps() -> None:
    """`bound` 是推导量：改尺度或关分量时上界跟着变，不会与声明域漂移。"""

    assert fc.FourComponentPathParams().bound == pytest.approx(480.0)
    assert fc.FourComponentPathParams(scale=10.0).bound == pytest.approx(120.0)
    ablated = fc.FourComponentPathParams(use_chain=0.0, use_baotou=0.0)
    assert ablated.bound == pytest.approx(SCALE * (4 + 0 + 1 + 0))


def test_declaration_parameters_round_trip_through_the_identity() -> None:
    """参数与推导出的 bound 都进候选身份；同参数必须给出同身份。"""

    adjustment = fc.build_adjustment_from_params({"scale": 12.5})
    identity = adjustment.identity()
    assert "four-component-path-value-v1" in identity
    assert "scale=12.5" in identity
    assert "bound=150.0" in identity                   # 12.5 × 12
    assert fc.build_adjustment_from_params({"scale": 12.5}).identity() == identity


def test_ablation_switches_change_the_identity() -> None:
    """消融变体是**独立候选身份**，不能拿完整版本的结论代用。"""

    full = fc.build_adjustment().identity()
    for key in ("use_branch", "use_chain", "use_four_white", "use_baotou"):
        assert fc.build_adjustment_from_params({key: 0.0}).identity() != full


def test_unknown_parameter_key_is_rejected() -> None:
    with pytest.raises(ValueError):
        fc.build_adjustment_from_params({"scal": 1.0})


def test_scope_covers_every_action_kind() -> None:
    """作用面必须是全部动作类别，否则状态势会退化成动作标签加分。"""

    adjustment = fc.build_adjustment()
    for action in (Discard(OTHER), Peng(Tile("1w")), GANG, Pass(), Hu()):
        assert adjustment.applies_to(action_key(action))


def test_adapter_is_the_only_clamp_and_it_does_not_fire() -> None:
    """**候选内部不裁剪**：适配器拿到的就是原始差值，clamped_count 保持 0。

    构造声明域内的极端状态（分支 4 + 链 6 + 四白 1 + 爆头 1 ⇒ Φ_max = 480），
    再让一次弃牌同时打掉豪华组、链、四白与爆头：生效分项必须等于原始差值，
    且没有任何钳制。若候选内部先裁剪，这条断言会失败。
    """

    ctx = _hand_ctx(LUXURY_HAND, drawn=FULL_HAND[-1], chain_count=6,
                    baotou=True, chain_piao=4)
    action = Discard(Tile("2b"))
    adjustment = fc.build_adjustment()
    raw = fc.path_term(_cand(action), ctx, PARAMS)
    effective, clamped, fired = _apply(action, ctx, adjustment)
    assert effective == pytest.approx(raw)
    assert clamped == 0
    assert fired == 1
    assert abs(raw) <= PARAMS.bound


def test_delta_is_deterministic_and_does_not_mutate_inputs() -> None:
    """同输入同输出；候选不得改动上下文或候选对象。"""

    ctx = _hand_ctx(FULL_HAND, chain_count=2, baotou=True, chain_piao=1)
    candidates = tuple(_cand(action) for action in
                       (Discard(Tile("9w")), Peng(Tile("1w")), GANG, Pass()))
    before_snapshot = (ctx, candidates)
    values = [fc.path_term(c, ctx, PARAMS)
              for c in candidates for _ in range(2)]
    assert values[0::2] == values[1::2]
    assert (ctx, candidates) == before_snapshot


def test_zero_scale_disables_the_family_without_unloading_it() -> None:
    zero = fc.FourComponentPathParams(scale=0.0)
    ctx = _hand_ctx(LUXURY_HAND, drawn=FULL_HAND[-1], chain_count=6,
                    baotou=True, chain_piao=4)
    assert fc.path_term(_cand(Discard(Tile("2b"))), ctx, zero) == 0.0
    assert zero.bound == 0.0


# --- S 组：势差结构（Φ 的定义、完整差值、可加性、环、标签无关） --------------


def test_term_is_the_difference_of_the_declared_potential() -> None:
    """term 必须等于 `Φ(s′) − Φ(s)`，并且用 `potential()` 直接复算得到。"""

    pairs = [
        (_state(branch_log2=1.0), _state(branch_log2=0.0)),
        (_state(chain_count=3), _state(chain_count=4)),
        (_state(four_white=True), _state(four_white=False)),
        (_state(baotou=False), _state(baotou=True)),
        (_state(branch_log2=4.0, chain_count=6, four_white=True, baotou=True),
         _state(branch_log2=0.0, chain_count=0, four_white=False, baotou=False)),
    ]
    for before, after in pairs:
        assert fc.state_term(before, after, PARAMS) == pytest.approx(
            fc.potential(after, PARAMS) - fc.potential(before, PARAMS), abs=1e-6)


def test_potential_envelope_matches_the_declared_bound() -> None:
    """Φ_min = 0、Φ_max = 480，且 `bound = Φ_max − Φ_min`。"""

    low = _state(branch_log2=0.0, chain_count=0, four_white=False, baotou=False)
    high = _state(branch_log2=4.0, chain_count=6, four_white=True, baotou=True)
    assert fc.potential(low, PARAMS) == 0.0
    assert fc.potential(high, PARAMS) == pytest.approx(PARAMS.bound)
    assert fc.state_term(low, high, PARAMS) == pytest.approx(PARAMS.bound)


def test_every_determinable_state_pair_stays_within_the_bound() -> None:
    """声明域内任意一对状态的差值都不得超过 bound（否则会被适配器钳制）。"""

    states = [fc.PathState(branch_log2=b, chain_count=c, four_white=f, baotou=t)
              for b in (0.0, 0.5, 1.0, 4.0)
              for c in (0, 3, 6)
              for f in (False, True)
              for t in (False, True)]
    for before in states:
        for after in states:
            assert abs(fc.state_term(before, after, PARAMS)) <= PARAMS.bound + 1e-9


def test_additivity_over_a_three_state_chain() -> None:
    """`F(A,B) + F(B,C) = F(A,C)`：这是"同一个状态势的差"的可执行判据。"""

    a = _state(branch_log2=4.0, chain_count=6, four_white=True, baotou=True)
    b = _state(branch_log2=2.0, chain_count=2, four_white=False, baotou=True)
    c = _state(branch_log2=0.0, chain_count=0, four_white=False, baotou=False)
    f_ab = fc.state_term(a, b, PARAMS)
    f_bc = fc.state_term(b, c, PARAMS)
    f_ac = fc.state_term(a, c, PARAMS)
    assert f_ab == pytest.approx(-7 * SCALE)     # 480 → 200
    assert f_bc == pytest.approx(-5 * SCALE)     # 200 → 0
    assert f_ab + f_bc == pytest.approx(f_ac, abs=1e-9)


def test_cycle_criterion_sums_to_zero() -> None:
    """沿任意闭环求和必须为 0（Ng §3 的环判据）。"""

    states = [
        _state(branch_log2=4.0, chain_count=6, four_white=True, baotou=True),
        _state(branch_log2=1.0, chain_count=0, four_white=False, baotou=True),
        _state(branch_log2=0.0, chain_count=3, four_white=False, baotou=False),
    ]
    loop = math.fsum(fc.state_term(states[i], states[(i + 1) % 3], PARAMS)
                     for i in range(3))
    assert loop == pytest.approx(0.0, abs=1e-9)


def test_path_internal_change_is_not_swallowed() -> None:
    """R8-2 的教训：路径仍存活时，**路径内部的变化也要计入**。

    弃掉"恰好 4 张"里的一张 ⇒ 少一组豪华 ⇒ −scale（初版那种"前后都存活就返回 0"
    会把这一项整个吞掉）；弃散牌则组数不变 ⇒ 0。
    """

    ctx = _hand_ctx(LUXURY_HAND, drawn="5b")
    assert fc.path_term(_cand(Discard(Tile("2b"))), ctx, PARAMS) == pytest.approx(-SCALE)
    assert fc.path_term(_cand(Discard(Tile("9w"))), ctx, PARAMS) == 0.0


def test_claim_actions_are_label_independent() -> None:
    """吃与碰引发的状态变化相同 ⇒ 必须给出同一个数（不是按动作标签分档）。"""

    ctx = _hand_ctx(LUXURY_HAND, drawn="5b")
    chi = fc.path_term(_cand(Chi((Tile("1w"), Tile("2w"), Tile("3w")))), ctx, PARAMS)
    peng = fc.path_term(_cand(Peng(Tile("1w"))), ctx, PARAMS)
    assert chi == peng == pytest.approx(-4 * SCALE)      # 关闭分支 4，其余分量不变


def test_gang_differs_only_by_the_chain_step_it_really_makes() -> None:
    """杠与碰的差别只来自"杠真的让链前进一步"（官方：杠每个动作 ×2）。"""

    ctx = _hand_ctx(LUXURY_HAND, drawn="5b", chain_count=2)
    peng = fc.path_term(_cand(Peng(Tile("1w"))), ctx, PARAMS)
    gang = fc.path_term(_cand(GANG), ctx, PARAMS)
    assert gang == pytest.approx(peng + SCALE)


def test_pass_is_the_reference_state_and_changes_nothing() -> None:
    ctx = _hand_ctx(LUXURY_HAND, drawn="5b", chain_count=3, baotou=True, chain_piao=1)
    assert fc.path_term(_cand(Pass()), ctx, PARAMS) == 0.0


def test_component_deltas_report_every_component_separately() -> None:
    """逐分量报告是 §3.0 的要求：某一分量的全局 PASS 不能代替其它分量。"""

    before = _state(branch_log2=4.0, chain_count=6, four_white=True, baotou=True)
    after = _state(branch_log2=3.0, chain_count=0, four_white=False, baotou=True)
    parts = dict(fc.component_deltas(before, after, PARAMS))
    assert set(parts) == set(fc.COMPONENT_NAMES)
    assert parts["branch"] == pytest.approx(-SCALE)
    assert parts["chain"] == pytest.approx(-6 * SCALE)
    assert parts["four_white"] == pytest.approx(-SCALE)
    assert parts["baotou"] == 0.0


def test_win_action_is_zero_by_documented_convention() -> None:
    """终局例外：胡返回 0，**不是** `−Φ(s)`；理由是评分不参与胡的排序。"""

    ctx = _hand_ctx(LUXURY_HAND, drawn="5b", chain_count=4, baotou=True)
    assert fc.path_term(_cand(Hu()), ctx, PARAMS) == 0.0
    assert fc.potential(fc.context_state(ctx), PARAMS) > 0.0


# --- U 组：不猜（未知不填 0/False、越域只收窄、机械计数的事实来源） -----------


def test_meld_count_derivation_covers_every_legal_hand_shape() -> None:
    """暗牌张数 → 副露数：13/14 − 3×副露，两种形态对 3 取余分别为 1 与 2。"""

    shapes = {0: (13, 14), 1: (10, 11), 2: (7, 8), 3: (4, 5), 4: (1, 2)}
    for melds, lengths in shapes.items():
        for length in lengths:
            assert fc.meld_count_of(tuple(["9w"] * length)) == melds
    assert fc.meld_count_of(tuple(["9w"] * 12)) is None      # 对 3 取余为 0：非法形态


def test_locked_luxury_groups_counts_only_natural_fours() -> None:
    """恰好 4 张的**自然牌**各计一组；白板不计（那是成胡时才判定的事实）。"""

    assert fc.locked_luxury_groups(("1w",) * 4 + ("白",) * 4, "白") == 1
    assert fc.locked_luxury_groups(("1w",) * 3 + ("白",) * 4, "白") == 0
    assert fc.locked_luxury_groups(("1w",) * 4 + ("2b",) * 4, "白") == 2
    assert fc.locked_luxury_groups(("1w",) * 2 + ("2b",) * 2, "白") == 0


def test_branch_component_is_plain_after_a_meld() -> None:
    """官方「七对子：禁止吃碰明杠暗杠」⇒ 有副露时分支取平胡的 0，且不会回来。"""

    melded = _ctx(combined_codes=("1w",) * 4 + ("2b",) * 4 + ("3t",) * 3)
    assert fc.meld_count_of(melded.combined_codes) == 1
    assert fc.context_state(melded).branch_log2 == fc.BRANCH_LOG2_PLAIN


def test_undeterminable_component_is_absent_not_zero() -> None:
    """不可判定的分量**不出现在分项里**（不是 0.0）——空与 0 必须区分。"""

    before = _state(four_white=None)
    after = _state(four_white=None)
    names = [name for name, _ in fc.component_deltas(before, after, PARAMS)]
    assert names == ["branch", "chain", "baotou"]
    assert "four_white" not in names


def test_unknown_chain_piao_does_not_fake_the_four_white_component() -> None:
    """链内飘出**真的**未知时（链非零且没落盘）四白不可判定；等值条件本身必须精确。

    要与下面那条"可推导"的测试分开读：链次数为 0（官方 piao ≤ count）或手留 4 张时，
    飘出是**可以推导**的，那时四白可判定——把可判定的情形也当成"未知"是另一种错误。
    """

    ctx = _hand_ctx(FULL_HAND, chain_count=2, chain_piao=None)
    assert ctx.wealth_count == 0
    assert fc.context_state(ctx).four_white is None
    assert fc.four_white_state(3, None) is None
    assert fc.four_white_state(3, 0) is False
    assert fc.four_white_state(3, 1) is True          # 3 + 1 == 4（正好 4 张才算）
    assert fc.four_white_state(2, 1) is False


def test_unknown_four_white_does_not_stop_the_other_components() -> None:
    """一个分量不可判定不得让整项失效：其余分量照常计分。"""

    ctx = _hand_ctx(LUXURY_HAND, drawn="5b", chain_count=2, chain_piao=None)
    before = fc.context_state(ctx)
    after = fc.action_state(_cand(GANG), ctx, before)
    assert after is not None
    names = [name for name, _ in fc.component_deltas(before, after, PARAMS)]
    assert "four_white" not in names
    assert "chain" in names
    assert fc.state_term(before, after, PARAMS) == pytest.approx(SCALE - 4 * SCALE)


def test_chain_piao_is_derived_from_the_two_rule_facts_that_make_it_certain() -> None:
    """两条**可推导**：链次数为 0（官方 `piao ≤ count`）、手留 4 张（白板共 4 张）。

    其余情形必须保持 None——未知与 0 不能混。这两条推导同时决定了 §D2 的适用面：
    没有它们，`s` 的四白不可判定而 `s′`（断链后飘出确定为 0）却可判定，
    绝大多数弃牌窗口会因为"可判定性模式不同"整段落入域外。
    """

    assert fc.known_piao(0, None, 0) == 0            # piao ≤ count ⇒ 链 0 ⇒ 飘出 0
    assert fc.known_piao(4, None, 3) == 0            # 4 张白板全在手上 ⇒ 飘出 0
    assert fc.known_piao(3, None, 3) is None         # 链非零且没落盘 ⇒ 真的未知
    assert fc.known_piao(0, None, 1) is None         # 同上：链 1、手留 0
    assert fc.known_piao(2, 3, 5) == 3               # 已知时原样返回
    ctx = _hand_ctx(WEALTH_HAND, drawn="9w", chain_piao=None)
    assert ctx.wealth_count == 4
    assert fc.context_state(ctx).four_white is True


def test_piao_does_not_change_the_four_white_sum() -> None:
    """爆头态打出财神 = 飘：手留 −1、链内飘出 +1 ⇒ 和不变（四白仍在）。"""

    ctx = _hand_ctx(WEALTH_HAND, drawn="9w", baotou=True,
                    chain_count=0, chain_piao=None)
    before = fc.context_state(ctx)
    assert before.four_white is True
    after = fc.action_state(_cand(Discard(WEALTH)), ctx, before)
    assert after.four_white is True
    parts = dict(fc.component_deltas(before, after, PARAMS))
    assert parts["four_white"] == 0.0


def test_non_baotou_wealth_discard_loses_the_four_white_multiplier() -> None:
    """非爆头态打白板不是飘：断链 ⇒ 链内飘出归零，手留从 4 掉到 3 ⇒ 四白丢失。"""

    ctx = _hand_ctx(WEALTH_HAND, drawn="9w", baotou=False,
                    chain_count=0, chain_piao=None)
    before = fc.context_state(ctx)
    after = fc.action_state(_cand(Discard(WEALTH)), ctx, before)
    assert after.four_white is False
    parts = dict(fc.component_deltas(before, after, PARAMS))
    assert parts["four_white"] == pytest.approx(-SCALE)


def test_out_of_domain_chain_is_excluded_instead_of_penalised() -> None:
    """链 6 → 7 越出官方 0—6 域：该分量两侧都不计入，不产生"扣 6 步链"的假惩罚。"""

    before = _state(chain_count=6)
    after = _state(chain_count=7)
    assert fc.state_term(before, after, PARAMS) == 0.0
    assert fc.potential(after, PARAMS) == fc.potential(_state(chain_count=0), PARAMS)


def test_out_of_range_four_white_inputs_do_not_raise_inside_the_scoring_path() -> None:
    """上游越界只让该分量不适用：**不夹取、不抛错**（评分路径整体失效代价更大）。"""

    assert fc.four_white_state(9, 0) is None
    assert fc.four_white_state(0, 9) is None


def test_baotou_component_inherits_on_melds_and_is_recomputed_on_discards() -> None:
    """吃/碰/杠继承爆头（无变化 ⇒ 不产生分项差），弃牌用**弃后暗牌**重新判定。"""

    ctx = _hand_ctx(LUXURY_HAND, drawn="5b", baotou=True)
    before = fc.context_state(ctx)
    for action in (Peng(Tile("1w")), GANG):
        after = fc.action_state(_cand(action), ctx, before)
        assert after.baotou is True
        assert dict(fc.component_deltas(before, after, PARAMS))["baotou"] == 0.0


def test_unknown_action_type_is_not_guessed() -> None:
    """非六类动作（不可能来自规则模块，属装配错误）⇒ 不加不减。"""

    ctx = _hand_ctx(LUXURY_HAND, drawn="5b")
    before = fc.context_state(ctx)

    class _Alien:
        pass

    alien = RuleCandidate(action=_Alien(), action_key="alien:1w",
                          evidence=(), facts=None)
    assert fc.action_state(alien, ctx, before) is None
    assert fc.path_term(alien, ctx, PARAMS) == 0.0

# --- S1 接缝：门控只依赖单个状态、域外转移与可加性的作用域 -------------------


def _all_grid_states():
    return [fc.PathState(branch_log2=b, chain_count=c, four_white=fw, baotou=t)
            for b in (0.0, 1.0, 4.0)
            for c in (0, 6)
            for fw in (False, True, None)
            for t in (False, True)]


def test_potential_and_state_term_share_one_source() -> None:
    """点 4：域内转移的 term 必须**就是** `Φ(s′) − Φ(s)`，不能两套口径。

    同时验证逐分量分解之和等于 term（同一份口径的两种视图）。
    """

    checked = 0
    for before in _all_grid_states():
        for after in _all_grid_states():
            in_domain, reasons = fc.domain_status(before, after, PARAMS)
            if not in_domain:
                continue
            checked += 1
            expected = fc.potential(after, PARAMS) - fc.potential(before, PARAMS)
            assert fc.state_term(before, after, PARAMS) == pytest.approx(expected, abs=1e-9)
            parts = fc.component_deltas(before, after, PARAMS)
            assert math.fsum(value for _, value in parts) == pytest.approx(
                fc.state_term(before, after, PARAMS), abs=1e-9)
    assert checked > 0


def test_domain_status_is_empty_for_an_in_domain_transition() -> None:
    before = _state(branch_log2=1.0, chain_count=0, four_white=False, baotou=False)
    after = _state(branch_log2=0.0, chain_count=1, four_white=True, baotou=True)
    assert fc.domain_status(before, after, PARAMS) == (True, ())


def test_out_of_domain_chain_reports_d1_with_the_component_and_value() -> None:
    """D1：端点越出**声明域**（链次数 ∉ [0,6]）⇒ 域外，并给出可读原因。

    这条转移同时改变门控值（¬g: 1 → 0¬），所以 D1 与 D2 两条原因都会被列出——
    两条都是事实，这里只要求 D1 的原因在场且可读。
    """

    before = _state(chain_count=6)
    after = _state(chain_count=7)
    in_domain, reasons = fc.domain_status(before, after, PARAMS)
    assert in_domain is False
    assert "chain:动作后越出声明域(7)" in reasons
    assert "chain:可判定性模式不同" in reasons
    assert fc.state_term(before, after, PARAMS) == 0.0


def test_mode_change_reports_d2_and_voids_the_whole_transition() -> None:
    """D2：某分量在一端可判定、另一端不可判定 ⇒ **整段**转移域外（返回 0）。

    返回 0 不等于"没有价值变化"：原因必须能被读出来（domain_status）。
    """

    before = _state(chain_count=0, four_white=None)
    after = _state(chain_count=0, four_white=False)
    in_domain, reasons = fc.domain_status(before, after, PARAMS)
    assert in_domain is False
    assert reasons == ("four_white:可判定性模式不同",)
    assert fc.state_term(before, after, PARAMS) == 0.0
    assert fc.component_deltas(before, after, PARAMS) == ()


def test_gated_counterexample_pins_the_scope_of_additivity() -> None:
    """★ 挑战者实测的"违规 40"：可加性**只在声明域内**成立，域外必须被报告。

    A: 四白 False（φ=0）      B: 四白 True（φ=1）      C: 四白 不可判定（g=0）

        F(A,B) = +40（域内）   F(B,C) = 0（D2 域外）   F(A,C) = 0（D2 域外）
        ⇒ F(A,B) + F(B,C) = 40 ≠ 0 = F(A,C)

    这不是把势差算错了，而是 A→C 与 B→C 根本不在声明域内、按声明返回降级值 0。
    本条回归把"全域可加"这种读法钉死：域内子集可加（下面第二段），全域不可加。
    """

    a = _state(branch_log2=1.0, chain_count=0, four_white=False, baotou=False)
    b = _state(branch_log2=1.0, chain_count=0, four_white=True, baotou=False)
    c = _state(branch_log2=1.0, chain_count=0, four_white=None, baotou=False)
    f_ab = fc.state_term(a, b, PARAMS)
    f_bc = fc.state_term(b, c, PARAMS)
    f_ac = fc.state_term(a, c, PARAMS)
    assert f_ab == pytest.approx(SCALE)
    assert (f_bc, f_ac) == (0.0, 0.0)
    assert abs(f_ab + f_bc - f_ac) == pytest.approx(SCALE)      # 全域差值 40
    for left, right in ((b, c), (a, c)):
        in_domain, reasons = fc.domain_status(left, right, PARAMS)
        assert in_domain is False
        assert any("four_white" in reason for reason in reasons)
    # 域内子集：三状态链全部可判定 ⇒ 可加性成立
    d = _state(branch_log2=1.0, chain_count=1, four_white=True, baotou=False)
    assert (fc.state_term(a, b, PARAMS) + fc.state_term(b, d, PARAMS)
            == pytest.approx(fc.state_term(a, d, PARAMS), abs=1e-9))


def test_branch_does_not_charge_for_discarding_the_fourth_wealth_tile() -> None:
    """★ 修正：手里 4 张财神时打出其中一张，**分支分量必须为 0**。

    豪华组数只数**自然牌**的四张（"4 张真白板算 1 组"要成胡时才判定），
    所以打折一张财神并没有打掉任何已锁定的豪华组。初版按"恰好 4 张"一刀切，
    对第 4 张财神多扣了 1 个 log2 番（−40）——那时单测只断四白，所以是绿的。
    """

    ctx = _hand_ctx(WEALTH_HAND, drawn="9w", baotou=True,
                    chain_count=0, chain_piao=None)
    before = fc.context_state(ctx)
    assert before.branch_log2 == fc.BRANCH_LOG2_CHIITOI      # 无副露、无豪华组
    after = fc.action_state(_cand(Discard(WEALTH)), ctx, before)
    parts = dict(fc.component_deltas(before, after, PARAMS))
    assert parts["branch"] == 0.0
    # 对照：打掉**自然牌**的第四张必须扣满 1 个 log2 番
    natural = _hand_ctx(LUXURY_HAND, drawn="5b")
    natural_before = fc.context_state(natural)
    assert natural_before.branch_log2 == pytest.approx(4.0)
    natural_after = fc.action_state(_cand(Discard(Tile("2b"))), natural, natural_before)
    assert dict(fc.component_deltas(natural_before, natural_after, PARAMS))["branch"] == (
        pytest.approx(-SCALE))

