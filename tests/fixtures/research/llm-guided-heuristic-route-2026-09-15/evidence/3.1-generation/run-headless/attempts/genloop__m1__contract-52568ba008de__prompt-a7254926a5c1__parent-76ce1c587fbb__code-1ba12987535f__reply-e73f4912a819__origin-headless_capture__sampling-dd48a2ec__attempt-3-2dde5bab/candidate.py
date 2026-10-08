from __future__ import annotations

import math
from typing import Mapping, Optional, Tuple

from hangma_bot.hangma.interface import CandidateFactKind, RuleCandidate
from hangma_bot.policy.evaluation_v1 import EvaluationContext
from hangma_bot.policy.heuristic_adapter import AdjustmentSpec, HeuristicAdjustment


def _param(
    params: Mapping[str, float], key: str, default: float, cap: float
) -> float:
    """读取一个非负、有限、带上限的参数；坏值退回 default。"""
    try:
        raw = params.get(key, default)
    except AttributeError:
        raw = default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(value):
        return default
    if value < 0.0:
        value = 0.0
    if value > cap:
        value = cap
    return value


def _as_int(value, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _tile_code(tile) -> Optional[str]:
    for attr in ("code", "tile_code", "tile", "name"):
        value = getattr(tile, attr, None)
        if isinstance(value, str):
            return value
    return None


def _quality(shanten) -> Optional[float]:
    """向听 -> [0,1] 的单调准备度；WIN(-1) 视为 1.0；未知返回 None。"""
    if shanten is None or isinstance(shanten, bool):
        return None
    try:
        value = int(shanten)
    except (TypeError, ValueError):
        return None
    if value <= -1:
        return 1.0
    return 1.0 / (1.0 + float(value))


def _breadth(useful) -> Optional[float]:
    """有效牌张数 -> [0,1) 的有界宽度；未知返回 None，() 表示已知空集。"""
    if useful is None:
        return None
    try:
        count = len(useful)
    except TypeError:
        return None
    if count <= 0:
        return 0.0
    return float(count) / (4.0 + float(count))


def _mix(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a
    return 0.5 * (a + b)


def _whites_ratio(useful, wealth_code) -> Optional[float]:
    """有效牌中白板占比；无可用牌码证据时返回 None。"""
    if useful is None or not isinstance(wealth_code, str):
        return None
    try:
        count = len(useful)
    except TypeError:
        return None
    if count == 0:
        return 0.0
    known = 0
    hits = 0
    for tile in useful:
        code = _tile_code(tile)
        if code is None:
            continue
        known += 1
        if code == wealth_code:
            hits += 1
    if known == 0:
        return None
    return float(hits) / float(known)


def _is_win(kind) -> bool:
    if kind is None:
        return False
    win = getattr(CandidateFactKind, "WIN", None)
    if win is not None and kind == win:
        return True
    name = getattr(kind, "name", None)
    if isinstance(name, str) and name.strip().upper() == "WIN":
        return True
    if isinstance(kind, str) and kind.strip().upper() == "WIN":
        return True
    return False


def _is_complete(value) -> bool:
    """不依赖具体导入位置的完整性判定。

    先取 `type(value).COMPLETE` 做等值比较，再退回 `.name`/字符串判定，
    只承认明确为 COMPLETE 的值，None 或未知一律视为不完整。
    """
    if value is None:
        return False
    complete = getattr(type(value), "COMPLETE", None)
    if complete is not None and value == complete:
        return True
    name = getattr(value, "name", None)
    if isinstance(name, str) and name.strip().upper() == "COMPLETE":
        return True
    if isinstance(value, str):
        return value.strip().upper().endswith("COMPLETE")
    return False


def _action_kind(candidate) -> str:
    key = getattr(candidate, "action_key", "")
    if not isinstance(key, str):
        return ""
    return key.split(":", 1)[0].strip().lower()


def _find_reference(candidates: Tuple[RuleCandidate, ...]):
    """确定性地选一个过牌候选作为动作前参考状态；没有则返回 None。"""
    best = None
    best_key = None
    infinity = 1 << 30
    for cand in candidates:
        if _action_kind(cand) != "pass":
            continue
        facts = getattr(cand, "facts", None)
        shanten = getattr(facts, "shanten_after", None) if facts is not None else None
        if shanten is None:
            key = (1, infinity)
        else:
            key = (0, _as_int(shanten, infinity))
        if best_key is None or key < best_key:
            best = cand
            best_key = key
    return best


def _weighted_phi(candidate, ctx: EvaluationContext, weights: Mapping[str, float]) -> float:
    """Φ(s)=Σ g_i(s)·φ_i(s)，门控与分项都在同一状态上求值。"""
    facts = getattr(candidate, "facts", None)
    if facts is None:
        return 0.0

    q_best = _quality(getattr(facts, "shanten_after", None))
    b_best = _breadth(getattr(facts, "useful_tiles", None))
    q_std = _quality(getattr(facts, "standard_shanten_after", None))
    b_std = _breadth(getattr(facts, "standard_useful_tiles", None))
    q_sev = _quality(getattr(facts, "seven_pairs_shanten_after", None))
    b_sev = _breadth(getattr(facts, "seven_pairs_useful_tiles", None))
    ratio = _whites_ratio(
        getattr(facts, "useful_tiles", None), getattr(ctx, "wealth_code", None)
    )

    is_step = 1.0 if _action_kind(candidate) in ("chi", "peng", "gang") else 0.0

    g_chain = 1.0 if _as_int(getattr(ctx, "chain_count", 0), 0) >= 1 else 0.0
    g_baotou = 1.0 if bool(getattr(ctx, "baotou", False)) else 0.0

    chain_piao = getattr(ctx, "chain_piao", None)
    wealth_count = getattr(ctx, "wealth_count", None)
    g_four = 0.0
    if chain_piao is not None and wealth_count is not None:
        if _as_int(wealth_count, -1) + _as_int(chain_piao, -1) == 4:
            g_four = 1.0

    branch_live = (
        getattr(facts, "standard_shanten_after", None) is not None
        and getattr(facts, "seven_pairs_shanten_after", None) is not None
    )
    branch = _mix(_mix(q_std, b_std), _mix(q_sev, b_sev))
    progress = _mix(q_best, b_best)

    total = g_chain * weights["step"] * is_step
    if progress is not None:
        total += g_chain * weights["progress"] * progress
    if q_best is not None:
        total += g_baotou * weights["baotou"] * q_best
    if branch_live and branch is not None:
        total += weights["branch"] * branch
    if g_four > 0.0 and ratio is not None:
        total += weights["four_white"] * ratio
    return total


def build_adjustment_from_params(
    params: Mapping[str, float], source_fingerprint_value: str = ""
) -> HeuristicAdjustment:
    """按声明参数构造本候选。"""

    scale = _param(params, "scale_points_per_log2_fan", 12.0, 1000.0)
    w_step = _param(params, "w_chain_step_log2fan", 1.0, 8.0)
    w_progress = _param(params, "w_chain_progress_log2fan", 0.5, 8.0)
    w_baotou = _param(params, "w_baotou_progress_log2fan", 0.5, 8.0)
    w_branch = _param(params, "w_branch_quality_log2fan", 0.5, 8.0)
    w_four = _param(params, "w_four_white_ratio_log2fan", 0.5, 8.0)

    weights = {
        "step": w_step,
        "progress": w_progress,
        "baotou": w_baotou,
        "branch": w_branch,
        "four_white": w_four,
    }
    total_weight = w_step + w_progress + w_baotou + w_branch + w_four
    if total_weight <= 0.0:
        weights = {
            "step": 1.0,
            "progress": 0.5,
            "baotou": 0.5,
            "branch": 0.5,
            "four_white": 0.5,
        }
        total_weight = sum(weights.values())

    bound = scale * total_weight + 1e-6
    if not math.isfinite(bound) or bound <= 0.0:
        bound = 1.0

    def delta(
        candidate: RuleCandidate,
        ctx: EvaluationContext,
        candidates: Tuple[RuleCandidate, ...],
    ) -> float:
        facts = getattr(candidate, "facts", None)
        if facts is None:
            return 0.0
        if not _is_complete(getattr(facts, "completeness", None)):
            return 0.0
        if _is_win(getattr(facts, "fact_kind", None)):
            return 0.0
        if bool(getattr(facts, "replacement_draw_unknown", False)):
            return 0.0
        if _action_kind(candidate) not in ("chi", "peng", "gang"):
            return 0.0

        reference = _find_reference(candidates)
        if reference is None or reference is candidate:
            return 0.0
        ref_facts = getattr(reference, "facts", None)
        if ref_facts is None:
            return 0.0
        if not _is_complete(getattr(ref_facts, "completeness", None)):
            return 0.0
        if _is_win(getattr(ref_facts, "fact_kind", None)):
            return 0.0
        if bool(getattr(ref_facts, "replacement_draw_unknown", False)):
            return 0.0

        phi_action = _weighted_phi(candidate, ctx, weights)
        phi_reference = _weighted_phi(reference, ctx, weights)
        return scale * (phi_action - phi_reference)

    fingerprint = str(source_fingerprint_value).strip()
    version = "multiplier_path_potential/1.2.0"
    if fingerprint:
        version = version + "+fp:" + fingerprint

    # 修订点：父代 scope 使用 frozenset({...})，隔离装载时报
    # TypeError: 'frozenset' object is not subscriptable（下游按下标读取 scope）。
    # 本版改为可下标的元组，取值仍严格来自 chi/peng/gang/discard/pass/hu。
    scope_value = ("chi", "peng", "gang")

    thought = (
        "按官方番型倍率路径组织：定义同一个势函数 Φ(s)=Σ_i g_i(s)·φ_i(s)，"
        "各分项在候选自身状态上取门控与事实："
        "动作链项 g_chain=1[ctx.chain_count>=1]，含 step(动作种类为吃/碰/杠) 与 progress(向听准备度与有效牌宽度的混合)；"
        "爆头项 g_baotou=1[ctx.baotou]，作用在向听准备度上；"
        "四白项 g_four=1[ctx.chain_piao 已知 且 ctx.wealth_count+ctx.chain_piao 恰为 4]，是等值门控，作用在有效牌中白板占比上；"
        "分支项要求该状态同时有普通型与七对向听分析，取两路质量的混合。"
        "delta=scale·(Φ(动作候选)-Φ(过牌参考))，scale 为显式参数，单位是评分点/log2番；"
        "×2 对应 1 log2番，换算为 scale 个评分点，不把 ×2 直接当 +2 分，也不据此断言分数或番数。"
        "适用域：吃/碰/杠窗口且存在完整事实的过牌参考。"
        "本分项只调整评分，不改候选集合、不改排序，也不声称势差可保持最优策略。"
        "修订说明：反馈「隔离装载 ok=False，原因 TypeError: 'frozenset' object is not subscriptable」"
        "对应改动——父代 AdjustmentSpec.scope=frozenset({\"chi\",\"peng\",\"gang\"}) 改为元组 "
        "(\"chi\",\"peng\",\"gang\")，避免下游按 scope[i] 取值时失败；函数合同、门控、权重、"
        "尺度、回退与其余实现均未改动。"
    )
    trigger = (
        "scope=chi/peng/gang 元组；仅当候选事实完整、动作种类为吃/碰/杠、窗口内存在完整事实的过牌参考时触发，"
        "否则返回 0.0（不加不减）。以下情况必须返回 0.0："
        "(1) 候选 facts 为 None 或 completeness 非 COMPLETE（用 type(value).COMPLETE/.name/字符串判定，None 视为不完整）；"
        "(2) facts.fact_kind 为 WIN（路径已兑现，不得当作被打掉扣分）；"
        "(3) 纯弃牌窗口没有过牌参考可代表动作前状态，势差不适用；"
        "(4) replacement_draw_unknown=True 的杠后补牌未知状态，或参考状态本身补牌未知，不得假设具体未来摸牌；"
        "(5) 当前动作为 pass/discard/hu 等非吃碰杠动作；"
        "(6) 四白门控中 ctx.chain_piao 为 None 时不得当 0，视为门控不成立。"
    )

    spec = AdjustmentSpec(
        name="multiplier_path_potential_v1",
        version=version,
        thought=thought,
        trigger=trigger,
        scope=scope_value,
        bound=bound,
    )
    return HeuristicAdjustment(spec=spec, delta=delta)
