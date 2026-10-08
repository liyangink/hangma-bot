"""`multiplier_path_potential`（生成端产出的第四个乘子势候选）的契约与结构测试。

**这个候选是谁**：它不是人工推导的价值族实例，而是**生成闭环的产物**——
3.1 生成包在 headless（默认通道）上经 I1 → 两次拒绝诊断修复 → M1 得到的候选
（版本 `multiplier_path_potential/1.2.0`），落盘于
`review/llm-guided-heuristic-route-2026-09-15/evidence/3.1-generation/run-headless/attempts/...attempt-3.../candidate.py`。
注册包（sitin-batch-v1 / register）按既有合同做**人工静态注册**：模块**逐字节**复制产物、
在 `CANDIDATE_FACTORIES` 加一行、在 `evidence/2.3-gates/candidate-registrations.json` 写 G-3 登记，
再跑 G-0/G-1/G-2/G-3（记录见 `evidence/3.4-registration/`）。

**本文件证明什么、不证明什么**：

  C 组（契约）：静态注册、spec 齐备、**注册源码与产物逐字节相同**、声明参数与产物字面默认值一致、
      作用面只覆盖声明类别、适配器是唯一钳制点、纯函数与确定性；
  Z 组（零值边界）：WIN、事实不完整、无过牌参考、杠后补牌未知 —— 一律 0.0（不加不减）；
  U 组（不猜）：链内飘出数未知（`chain_piao=None`）时四白门控**不成立**，但**不因此把整项清零**；
  L 组（机制形状）：势差在两侧事实相同时只差"链在动时的吃碰杠步进项"——这是**登记时记录的
      标签相关项**（见 G-3 登记与 `evidence/3.4-registration/README.md` 的复核发现）。

**本文件不构成准入或效果证据**：它只证明结构与接线；代表语料准入在门禁记录里，
效果评估是另外两步（README §17.1 第 3 条：工具完成 / 发现候选 / 通过发布门禁分开报）。
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'tests/unit/policy'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import hashlib
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
from hangma_bot.policy import heuristics
from hangma_bot.policy.evaluation_v1 import ScoredCandidate, build_context
from hangma_bot.policy.heuristics import multiplier_path_potential as mpp

from .support import WEALTH_CODE, make_observation

REPO = Path(__file__).resolve().parents[3]

#: 生成产物的 sha256（= 注册模块的 sha256；注册为**逐字节复制**，不做任何改写）。
ARTIFACT_SHA256 = "1ba12987535fba2edfbab1422ecac545444629328259233652a7e35fbf1622e2"

#: 产物落盘路径（注册来源；用于把"注册 = 这份产物"变成可机器核验的断言）。
ARTIFACT_PATH = (_project_file(_PROJECT_ROOT, REPO / "review" / "llm-guided-heuristic-route-2026-09-15" / "evidence"
                 / "3.1-generation" / "run-headless" / "attempts"
                 / "genloop__m1__contract-52568ba008de__prompt-a7254926a5c1__parent-76ce1c587fbb"
                   "__code-1ba12987535f__reply-e73f4912a819__origin-headless_capture"
                   "__sampling-dd48a2ec__attempt-3-2dde5bab" / "candidate.py"))

#: 注册时声明的参数（`adj.` 去前缀后的键；值**逐字取自产物代码里的字面默认值**）。
DECLARED_PARAMS = {
    "scale_points_per_log2_fan": 12.0,
    "w_chain_step_log2fan": 1.0,
    "w_chain_progress_log2fan": 0.5,
    "w_baotou_progress_log2fan": 0.5,
    "w_branch_quality_log2fan": 0.5,
    "w_four_white_ratio_log2fan": 0.5,
}

WEALTH = Tile(WEALTH_CODE)
OTHER = Tile("9w")


def _ctx(**overrides):
    """从最小观察构造评分上下文；只覆盖需要改的规则状态字段。"""

    return replace(build_context(make_observation()), **overrides)


def _cand(action, facts=None) -> RuleCandidate:
    return RuleCandidate(action=action, action_key=action_key(action), evidence=(),
                         facts=facts)


def _facts(*, kind=CandidateFactKind.HAND_PROGRESS, shanten=1, standard=None, seven=None,
           useful=(), standard_useful=None, seven_useful=None,
           completeness=RuleCompleteness.COMPLETE, replacement_unknown=False):
    """构造动作后牌效事实；默认是"完整、可评估"的等待状态。"""

    return CandidateFacts(
        kind, shanten,
        useful_tiles=tuple(useful),
        replacement_draw_unknown=replacement_unknown,
        completeness=completeness,
        standard_shanten_after=standard,
        seven_pairs_shanten_after=seven,
        standard_useful_tiles=standard_useful,
        seven_pairs_useful_tiles=seven_useful,
    )


def _adjustment(**params):
    return mpp.build_adjustment_from_params(dict(params))


def _delta(action, ctx, candidate_facts, reference_facts, *, adjustment=None,
           extra=()):
    """经**适配器**算一次分项：返回 (生效值, 钳制次数, 触发次数, 是否产生分项)。"""

    adjustment = adjustment or _adjustment(**DECLARED_PARAMS)
    candidate = _cand(action, candidate_facts)
    reference = _cand(Pass(), reference_facts)
    candidates = (candidate, reference) + tuple(extra)
    item = ScoredCandidate(priority=1, candidate=candidate, action_key=action_key(action),
                           parts=(), reasons=(), total=0.0, shanten=None,
                           is_safe_discard=False)
    applied = adjustment.apply(item, ctx, candidates)
    value = applied.parts[-1].value if applied.parts else 0.0
    if applied.parts:
        assert applied.parts[-1].name == adjustment.spec.name
    return value, adjustment.clamped_count, adjustment.fired_count, bool(applied.parts)


# --- C 组：契约（注册 / 身份 / 来源 / bound / 唯一强制点） ---------------------

def test_candidate_is_registered_in_the_static_registry() -> None:
    """静态注册表是**唯一**装载入口（不是插件系统、不是自动扫描）。"""

    assert heuristics.is_candidate("multiplier_path_potential")
    assert "multiplier_path_potential" in heuristics.candidate_names()
    assert heuristics.candidate_module("multiplier_path_potential") is mpp


def test_registered_source_is_byte_identical_to_the_generation_artifact() -> None:
    """注册 = **逐字节**接受那份产物；改写过一个字节，注册来源就不成立。"""

    registered = Path(mpp.__file__).read_bytes()
    assert hashlib.sha256(registered).hexdigest() == ARTIFACT_SHA256
    if not ARTIFACT_PATH.is_file():
        pytest.skip("生成产物不在本检出中，只能校验注册模块自身的指纹")
    assert hashlib.sha256(ARTIFACT_PATH.read_bytes()).hexdigest() == ARTIFACT_SHA256


def test_declared_spec_is_complete() -> None:
    """G-3 要求的 name / thought / trigger / scope / bound 必须齐全且非空。"""

    spec = _adjustment().spec
    assert spec.name == "multiplier_path_potential_v1"
    assert spec.version.startswith("multiplier_path_potential/1.2.0")
    assert spec.thought.strip() and spec.trigger.strip()
    assert tuple(spec.scope) == ("chi", "peng", "gang")
    assert spec.bound == pytest.approx(36.000001)


def test_version_carries_the_source_fingerprint() -> None:
    """装入方传入的源码指纹进**版本段**（该候选的唯一来源溯源点）。"""

    plain = _adjustment().spec.version
    printed = mpp.build_adjustment_from_params({}, source_fingerprint_value="abc123")
    assert printed.spec.version == plain + "+fp:abc123"


def test_declared_parameters_match_the_artifact_defaults() -> None:
    """声明参数逐字等于产物代码里的默认值 ⇒ 显式声明与"不传参数"行为一致。"""

    ctx = _ctx(chain_count=1)
    action_facts = _facts(shanten=1, standard=2, seven=1)
    reference_facts = _facts(shanten=3, standard=3, seven=3)

    implicit = _delta(Peng(OTHER), ctx, action_facts, reference_facts,
                      adjustment=_adjustment())
    declared = _delta(Peng(OTHER), ctx, action_facts, reference_facts,
                      adjustment=_adjustment(**DECLARED_PARAMS))
    assert implicit[0] == pytest.approx(declared[0])
    assert implicit[0] != 0.0                      # 否则这条断言没有判别力


def test_scope_covers_only_the_declared_action_kinds() -> None:
    """吃/碰/杠在作用面内；过牌、弃牌、胡不在——适配器按 scope 过滤，不调 delta。"""

    adjustment = _adjustment(**DECLARED_PARAMS)
    assert adjustment.applies_to("chi") and adjustment.applies_to("peng")
    assert adjustment.applies_to("gang")
    for outside in ("pass", "discard", "hu"):
        assert not adjustment.applies_to(outside)

    ctx = _ctx()
    facts = _facts(shanten=1, standard=2, seven=1)
    value, clamped, fired, produced = _delta(Discard(OTHER), ctx, facts,
                                             _facts(shanten=3, standard=3, seven=3),
                                             adjustment=adjustment)
    assert (value, clamped, fired, produced) == (0.0, 0, 0, False)


def test_zero_scale_disables_the_term_without_unloading_it() -> None:
    """消融：scale=0 时整项恒为 0，但候选仍可装载（不靠卸载做消融）。"""

    ctx = _ctx(chain_count=1)
    value, _, _, produced = _delta(
        Peng(OTHER), ctx, _facts(shanten=1, standard=2, seven=1),
        _facts(shanten=3, standard=3, seven=3),
        adjustment=mpp.build_adjustment_from_params({"scale_points_per_log2_fan": 0.0}))
    assert value == 0.0 and not produced


def test_declared_bound_holds_and_the_adapter_never_clamps() -> None:
    """|delta| 始终在声明上界内；钳制点只有适配器一个（本候选不裁剪 delta）。"""

    adjustment = _adjustment(**DECLARED_PARAMS)
    bound = adjustment.spec.bound
    # 两端都拉到最远：动作后接近听牌、参考态最差，且链与爆头都成立。
    cases = [
        (_ctx(chain_count=1, baotou=True, wealth_count=4, chain_piao=0),
         _facts(shanten=0, standard=0, seven=0,
                useful=(UsefulTileFact(WEALTH_CODE, 4),),
                standard_useful=(UsefulTileFact(WEALTH_CODE, 4),),
                seven_useful=(UsefulTileFact(WEALTH_CODE, 4),)),
         _facts(shanten=6, standard=6, seven=6)),
        (_ctx(chain_count=6, baotou=True, wealth_count=0, chain_piao=0),
         _facts(shanten=6, standard=6, seven=6, replacement_unknown=False),
         _facts(shanten=0, standard=0, seven=0)),
    ]
    for ctx, action_facts, reference_facts in cases:
        value, clamped, _, _ = _delta(Gang(OTHER, GangKind.EXPOSED), ctx, action_facts,
                                      reference_facts, adjustment=adjustment)
        assert abs(value) <= bound + 1e-9
        assert clamped == 0


def test_delta_is_deterministic_and_does_not_mutate_inputs() -> None:
    """同输入同输出，且不改动传入的候选与事实对象。"""

    ctx = _ctx(chain_count=1)
    action_facts = _facts(shanten=1, standard=2, seven=1)
    reference_facts = _facts(shanten=3, standard=3, seven=3)
    first = _delta(Peng(OTHER), ctx, action_facts, reference_facts)
    second = _delta(Peng(OTHER), ctx, action_facts, reference_facts)
    assert first[:3] == second[:3]
    assert action_facts.shanten_after == 1 and reference_facts.shanten_after == 3


def test_unknown_parameter_keys_are_ignored_not_rejected() -> None:
    """**已知偏离**：本候选对未知参数键不报错（人工登记的 5 个候选都报错）。

    登记时如实记录：调用方写错键名不会得到提示，行为退回默认值。危险面有限
    （键只影响尺度与权重），但**这不是**本项目"静默失败要拦"的常态。
    """

    ctx = _ctx(chain_count=1)
    action_facts = _facts(shanten=1, standard=2, seven=1)
    reference_facts = _facts(shanten=3, standard=3, seven=3)
    baseline = _delta(Peng(OTHER), ctx, action_facts, reference_facts,
                      adjustment=_adjustment(**DECLARED_PARAMS))[0]
    typo = _delta(Peng(OTHER), ctx, action_facts, reference_facts,
                  adjustment=_adjustment(**dict(DECLARED_PARAMS, w_branch_qlty=8.0)))[0]
    assert typo == pytest.approx(baseline)


# --- Z 组：零值边界（必须"不加不减"） ----------------------------------------

def test_win_candidate_returns_zero() -> None:
    """已胡的动作不参与：路径已兑现，不得当成被打掉。"""

    ctx = _ctx(chain_count=1)
    win = _facts(kind=CandidateFactKind.WIN, shanten=-1)
    value, _, _, produced = _delta(Peng(OTHER), ctx, win,
                                   _facts(shanten=3, standard=3, seven=3))
    assert value == 0.0 and not produced


def test_incomplete_facts_return_zero() -> None:
    """事实完整性不是 COMPLETE 的一律 0.0（不猜）。"""

    ctx = _ctx(chain_count=1)
    degraded = _facts(completeness=RuleCompleteness.DEGRADED,
                      shanten=1, standard=2, seven=1)
    assert _delta(Peng(OTHER), ctx, degraded,
                  _facts(shanten=3, standard=3, seven=3))[0] == 0.0
    assert _delta(Peng(OTHER), ctx, _facts(shanten=1, standard=2, seven=1),
                  _facts(completeness=RuleCompleteness.DEGRADED, shanten=3))[0] == 0.0


def test_missing_facts_return_zero() -> None:
    """候选没有事实对象时不做任何推断。"""

    assert _delta(Peng(OTHER), _ctx(), None,
                  _facts(shanten=3, standard=3, seven=3))[0] == 0.0


def test_without_a_pass_reference_the_potential_difference_does_not_apply() -> None:
    """没有过牌候选就没有"动作前状态"的代表，势差不适用。"""

    ctx = _ctx(chain_count=1)
    candidate = _cand(Peng(OTHER), _facts(shanten=1, standard=2, seven=1))
    adjustment = _adjustment(**DECLARED_PARAMS)
    item = ScoredCandidate(priority=1, candidate=candidate, action_key="peng:9w",
                           parts=(), reasons=(), total=0.0, shanten=None,
                           is_safe_discard=False)
    applied = adjustment.apply(item, ctx, (candidate,))
    assert applied.parts == ()


def test_unknown_replacement_draw_returns_zero() -> None:
    """杠后补牌未知时不借动作后事实假设具体未来摸牌（两侧都检查）。"""

    ctx = _ctx(chain_count=1)
    good = _facts(shanten=1, standard=2, seven=1)
    unknown = _facts(shanten=1, standard=2, seven=1, replacement_unknown=True)
    reference = _facts(shanten=3, standard=3, seven=3)
    reference_unknown = _facts(shanten=3, standard=3, seven=3, replacement_unknown=True)
    assert _delta(Gang(OTHER, GangKind.EXPOSED), ctx, unknown, reference)[0] == 0.0
    assert _delta(Gang(OTHER, GangKind.EXPOSED), ctx, good, reference_unknown)[0] == 0.0


# --- U 组：不猜（未知不等于零，但也不许把整项清零） ---------------------------

def test_four_white_gate_is_off_when_the_chain_piao_count_is_unknown() -> None:
    """链内飘出数未知 ⇒ 四白门控**不成立**（不得当 0 用），其余分项照常生效。

    这条是登记复核的重点：门禁语料里链状态字段整体缺失（0 行记录 `chain_piao`），
    若实现把"未知"读成"不是四白"就会虚高，若把"未知"读成"整项作废"就会在语料上
    恒为 0（另一份生成候选正是后者）。本候选两者都不是。
    """

    warm = (UsefulTileFact(WEALTH_CODE, 4),)         # 有效牌里全是财神 ⇒ 占比 1.0
    action_facts = _facts(shanten=1, standard=2, seven=1, useful=warm)
    reference_facts = _facts(shanten=3, standard=3, seven=3)

    unknown_ctx = _ctx(chain_count=0, wealth_count=4, chain_piao=None)
    locked_ctx = _ctx(chain_count=0, wealth_count=4, chain_piao=0)   # 4 + 0 = 4 ⇒ 成立
    unknown_value = _delta(Peng(OTHER), unknown_ctx, action_facts, reference_facts)[0]
    locked_value = _delta(Peng(OTHER), locked_ctx, action_facts, reference_facts)[0]

    assert unknown_value != 0.0                       # 未知不把整项清零
    assert locked_value > unknown_value               # 四白成立时才多出那一项
    assert locked_value - unknown_value == pytest.approx(0.5 * 12.0)


def test_four_white_gate_needs_the_sum_to_be_exactly_four() -> None:
    """四白是**等值条件**：手留 3 张且链内飘出 1 张合计 4 才成立（不是单调量）。"""

    warm = (UsefulTileFact(WEALTH_CODE, 4),)
    action_facts = _facts(shanten=1, standard=2, seven=1, useful=warm)
    reference_facts = _facts(shanten=3, standard=3, seven=3)
    sum_is_four = _delta(Peng(OTHER), _ctx(wealth_count=3, chain_piao=1),
                         action_facts, reference_facts)[0]
    sum_is_three = _delta(Peng(OTHER), _ctx(wealth_count=3, chain_piao=0),
                          action_facts, reference_facts)[0]
    assert sum_is_four > sum_is_three


# --- L 组：机制形状（势差 + 一处标签相关项） ----------------------------------

def test_equal_states_differ_only_by_the_chain_step_term() -> None:
    """两侧事实相同时，唯一非零来源是"链在动时的吃碰杠步进项"。

    这是**登记时记录的标签相关项**：动作链项写成 `1[链≥1]·1[动作为吃碰杠]`，
    于是链非零时吃碰杠本身就带一个正的尺度分（对应"圈内吃碰后再打财神续飘"的
    投资解释），链为 0 时不存在。它偏离价值族"只看状态、不看动作标签"的纪律，
    登记为**生成候选的机制差异**，不改写、不美化（见 3.4-registration 复核发现）。
    """

    action_facts = _facts(shanten=2, standard=2, seven=2)
    reference_facts = _facts(shanten=2, standard=2, seven=2)

    live_chain = _delta(Peng(OTHER), _ctx(chain_count=1), action_facts,
                        reference_facts)[0]
    dead_chain = _delta(Peng(OTHER), _ctx(chain_count=0), action_facts,
                        reference_facts)[0]
    assert live_chain == pytest.approx(12.0)          # scale × w_step
    assert dead_chain == 0.0                          # 链不在动 ⇒ 不加不减


def test_better_landing_state_scores_higher_and_worse_scores_lower() -> None:
    """势差方向：动作后推进度更高 ⇒ 加分为正；参考态更好 ⇒ 加分为负。"""

    ctx = _ctx(chain_count=0)
    better = _delta(Peng(OTHER), ctx, _facts(shanten=1, standard=2, seven=1),
                    _facts(shanten=4, standard=4, seven=4))[0]
    worse = _delta(Peng(OTHER), ctx, _facts(shanten=4, standard=4, seven=4),
                   _facts(shanten=1, standard=2, seven=1))[0]
    assert better > 0 > worse


def test_claim_actions_are_not_penalised_unconditionally() -> None:
    """同状态同事实下，吃与碰给**同一个**值——惩罚不来自动作标签。"""

    ctx = _ctx(chain_count=0)
    action_facts = _facts(shanten=1, standard=2, seven=1)
    reference_facts = _facts(shanten=3, standard=3, seven=3)
    peng = _delta(Peng(OTHER), ctx, action_facts, reference_facts)[0]
    chi = _delta(Chi((Tile("1w"), Tile("2w"), Tile("3w"))), ctx, action_facts,
                 reference_facts)[0]
    assert peng == pytest.approx(chi)


def test_reference_selection_is_deterministic_and_fails_closed() -> None:
    """参考态按 (向听已知优先, 向听更小) 确定性选取；**选中的参考不完整就整项归零**。

    已知行为（登记复核记录，不美化）：实现不"跳过不完整的过牌再找下一个"，
    而是选出参考后校验其事实完整性，不完整即返回 0.0。方向是保守的（不加不减），
    但代价是——窗口里若存在一个向听更小、事实降级的过牌候选，这一项就整体失效。
    本用例把它钉住，避免以后被悄悄改成"悄悄换一个参考"。
    """

    ctx = _ctx(chain_count=0)
    action_facts = _facts(shanten=1, standard=2, seven=1)

    # 参考事实完整（向听 3）⇒ 正常产生正分项。
    value, _, _, produced = _delta(Peng(OTHER), ctx, action_facts,
                                   _facts(shanten=3, standard=3, seven=3))
    assert produced and value > 0.0

    # 追加一个向听更小但事实降级的过牌候选 ⇒ 它成为被选中的参考 ⇒ 整项归零。
    degraded_pass = _cand(Pass(), _facts(completeness=RuleCompleteness.DEGRADED,
                                         shanten=0, standard=0, seven=0))
    guarded, _, _, produced_guarded = _delta(Peng(OTHER), ctx, action_facts,
                                             _facts(shanten=3, standard=3, seven=3),
                                             extra=(degraded_pass,))
    assert (guarded, produced_guarded) == (0.0, False)
