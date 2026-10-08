"""G217 离线研究候选：合法第二步自然成面及高番选项与 R18 v2 联合排序。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/freematch-deep-dive-20260925'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

from dataclasses import dataclass, replace
from pathlib import Path
import hashlib
import math
import time

import c31_action_layer_gap as c31
import g52_shared_horizon as g52
import g210_post_claim_guarded_familiar_policy as g210
from hangma_bot.application.audit_codec import candidate_value_facts_to_json


HERE = Path(__file__).resolve().parent
G216_RESULT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g216-visible-reach-calibration-20260929/result.json')
G216_SHA256 = "51fd6cab303c1f7a27ff3d34707d46c20a1706fe80ce54c747ca47cba104d93c"
POLICY_ID = "action_value_v1:research:g217-two-step-natural-route-v1"
MAX_ALTERNATES = 6
EPSILON = 1e-8

# G216 父代路径的总体再摸频率；同窗两臂共用，仅作为未来项的工程权重。
REACH_BY_WALL = (
    (32, 28 / 49),
    (48, 214 / 306),
    (64, 914 / 1228),
    (80, 1819 / 2223),
    (96, 383 / 431),
)


def reach_weight(wall: int | None) -> float | None:
    """可见墙余量对应的父代经验再摸权重；未知墙余不推断。"""
    if type(wall) is not int or wall <= 20:
        return None
    for upper, weight in REACH_BY_WALL:
        if wall <= upper:
            return weight
    return REACH_BY_WALL[-1][1]


def _assert_source() -> None:
    """不得在研究运行中悄悄换 G216 校准结果。"""
    if hashlib.sha256(G216_RESULT.read_bytes()).hexdigest() != G216_SHA256:
        raise ValueError("G216 可达权重证据摘要漂移")


@dataclass(frozen=True)
class ModeProjection:
    """第一摸公开容量加权下，同一合法自然续打的后续牌形。"""

    natural_need: float
    natural_progress_capacity: float
    whites_held: float
    baotou: float
    second_hu_option: float
    seven_need: float | None
    seven_progress_capacity: float | None

    @property
    def natural_score(self) -> float:
        """沿用 R18 的 -100×距离+有效容量评分尺度；非真实积分。"""
        return -100.0 * self.natural_need + self.natural_progress_capacity


@dataclass(frozen=True)
class RouteProjection:
    """一个合法根弃牌的一摸终点与两种未来抓打包络。"""

    first_hu_expected_score: float
    restricted: ModeProjection
    unrestricted: ModeProjection


def _mode(tree: dict, mode: str) -> ModeProjection:
    """逐个第一摸码，选该码的单一自然续打；结算选项另作守卫。"""
    total = tree["first_draw_public_capacity"]
    if type(total) is not int or total <= 0:
        raise ValueError("第一次摸牌公开容量非法")
    accum = dict.fromkeys(("natural_need", "natural_progress_capacity",
                           "whites_held", "baotou", "second_hu_option",
                           "seven_need", "seven_progress_capacity"), 0.0)
    seven_available: bool | None = None
    counted = 0
    for edge in tree["edges"]:
        capacity = edge["capacity"]
        if type(capacity) is not int or capacity <= 0:
            raise ValueError("条件第一摸容量非法")
        counted += capacity
        children = edge["best_second"][mode]
        natural = children["best_natural_progress"]
        best_hu = children["best_second_hu"]
        seven = children["best_seven_natural_progress"]
        present = seven is not None
        if seven_available is None:
            seven_available = present
        elif seven_available != present:
            raise ValueError("同根七对适用性随未来牌码改变")
        if natural["capacity"] <= 0 or best_hu["capacity"] <= 0:
            raise ValueError("条件第二摸公开容量非法")
        accum["natural_need"] += capacity * natural["ordinary_natural_need"]
        accum["natural_progress_capacity"] += capacity * natural["ordinary_natural_progress_capacity"]
        accum["whites_held"] += capacity * natural["whites_held"]
        accum["baotou"] += capacity * int(natural["baotou_after"])
        accum["second_hu_option"] += capacity * best_hu["mass"] / best_hu["capacity"]
        if seven is not None:
            accum["seven_need"] += capacity * seven["seven_natural_need"]
            accum["seven_progress_capacity"] += capacity * seven["seven_natural_progress_capacity"]
    if counted != total:
        raise ValueError("第一摸各码公开容量不守恒")
    values = {name: amount / total for name, amount in accum.items()}
    if not seven_available:
        values["seven_need"] = None
        values["seven_progress_capacity"] = None
    if any(not math.isfinite(value) for value in values.values() if value is not None):
        raise ValueError("未来路线投影不是有限数值")
    return ModeProjection(**values)


def project(request, action_key: str) -> RouteProjection:
    """只用可见请求和生产规则事实构造合法两摸路线；不读赛后世界。"""
    candidate = next((item for item in request.rules.legal_candidates
                      if item.action_key == action_key), None)
    if (candidate is None or candidate.value_facts is None
            or not action_key.startswith("discard:")):
        raise ValueError("待评动作无生产规则价值事实")
    tree = g52.evaluate_root(
        request.observation,
        {"action_key": action_key,
         "value_facts": candidate_value_facts_to_json(candidate.value_facts)},
        c31.RULE_CONFIG,
    )
    first = tree["first_hu_mass"] / tree["first_draw_public_capacity"]
    return RouteProjection(
        first_hu_expected_score=first,
        restricted=_mode(tree, "restricted"),
        unrestricted=_mode(tree, "unrestricted"),
    )


def _non_regress(parent: RouteProjection, alt: RouteProjection) -> bool:
    """普通成面与立即胡/二摸胡、留白、爆头及七对选项分别守卫。"""
    if alt.first_hu_expected_score + EPSILON < parent.first_hu_expected_score:
        return False
    for mode in ("restricted", "unrestricted"):
        p, a = getattr(parent, mode), getattr(alt, mode)
        if (a.natural_need > p.natural_need + EPSILON
                or a.natural_progress_capacity + EPSILON < p.natural_progress_capacity
                or a.whites_held + EPSILON < p.whites_held
                or a.baotou + EPSILON < p.baotou
                or a.second_hu_option + EPSILON < p.second_hu_option):
            return False
        if (p.seven_need is None) != (a.seven_need is None):
            return False
        if p.seven_need is not None and (
                a.seven_need > p.seven_need + EPSILON
                or a.seven_progress_capacity + EPSILON < p.seven_progress_capacity):
            return False
    a, p = alt.unrestricted, parent.unrestricted
    return (a.natural_need + EPSILON < p.natural_need
            or a.natural_progress_capacity > p.natural_progress_capacity + EPSILON)


def _width(candidate) -> tuple[int, int] | None:
    facts = candidate.facts
    if facts is None or facts.standard_useful_tiles is None:
        return None
    return g210._width(facts.standard_useful_tiles)


def select(request, parent_plan) -> tuple[str | None, dict]:
    """受限根集内以同窗可见事实比较未来合法路线，异常由包装器退回父代。"""
    if request.window_key.phase.value != "draw" or request.rejected_attempts:
        return None, {"reason": "not_normal_draw"}
    if not parent_plan.candidates:
        return None, {"reason": "empty_plan"}
    parent = parent_plan.candidates[0]
    wealth = request.observation.rule_state.wealth_god.code
    if (not parent.action_key.startswith("discard:")
            or parent.action_key == "discard:" + wealth):
        return None, {"reason": "parent_not_nonwhite_discard"}
    reach = reach_weight(request.observation.remaining_tile_count)
    if reach is None:
        return None, {"reason": "no_reach_weight"}
    legal = {item.action_key: item for item in request.rules.legal_candidates}
    root = legal.get(parent.action_key)
    if (root is None or root.facts is None
            or type(root.facts.standard_shanten_after) is not int
            or _width(root) is None):
        return None, {"reason": "unknown_parent_rule_facts"}
    parent_risk = g210._risk(parent)
    if parent_risk is None:
        return None, {"reason": "unknown_parent_risk"}
    same_layer = []
    for ranked in parent_plan.candidates[1:]:
        key = ranked.action_key
        fact = legal.get(key)
        if (not key.startswith("discard:") or key == "discard:" + wealth
                or fact is None or fact.facts is None
                or fact.facts.standard_shanten_after != root.facts.standard_shanten_after
                or _width(fact) is None):
            continue
        same_layer.append(ranked)
    if not same_layer:
        return None, {"reason": "no_same_layer_alternate"}
    shortlisted = same_layer[:MAX_ALTERNATES]
    widest = max(same_layer, key=lambda row: (_width(legal[row.action_key])[1],
                                               _width(legal[row.action_key])[0],
                                               -row.rank))
    if widest.action_key not in {row.action_key for row in shortlisted}:
        shortlisted.append(widest)
    parent_route = project(request, parent.action_key)
    best = None
    considered = 0
    guard_pass = 0
    for alternate in shortlisted:
        risk = g210._risk(alternate)
        if risk is None or risk > parent_risk + EPSILON:
            continue
        considered += 1
        route = project(request, alternate.action_key)
        if not _non_regress(parent_route, route):
            continue
        guard_pass += 1
        future_gain = (route.unrestricted.natural_score
                       - parent_route.unrestricted.natural_score)
        adjusted_gain = reach * future_gain
        base_gap = parent.total_score - alternate.total_score
        margin = adjusted_gain - base_gap
        if margin <= EPSILON:
            continue
        current_width = _width(legal[alternate.action_key])
        parent_width = _width(root)
        record = {
            "alternate_action": alternate.action_key,
            "parent_action": parent.action_key,
            "first_width_type_gain": current_width[0] - parent_width[0],
            "first_width_capacity_gain": current_width[1] - parent_width[1],
            "future_natural_gain": round(future_gain, 6),
            "reach_weight": round(reach, 9),
            "parent_score_gap": round(base_gap, 6),
            "adjusted_margin": round(margin, 6),
            "rank": alternate.rank,
        }
        if best is None or (margin, -alternate.rank) > (best[0], -best[1].rank):
            best = (margin, alternate, record)
    if best is None:
        return None, {"reason": "no_dominant_route_above_parent",
                      "evaluated_alternates": considered,
                      "guard_pass_alternates": guard_pass}
    return best[1].action_key, {"reason": "two_step_natural_route_dominance",
                                "evaluated_alternates": considered,
                                "guard_pass_alternates": guard_pass,
                                **best[2]}


class TwoStepNaturalRoutePolicy:
    """仅重排父代已提供的合法候选；任何模型或量具失败保留父代动作。"""

    policy_id = POLICY_ID

    def __init__(self, parent, metrics: list[dict]) -> None:
        self.parent = parent
        self.metrics = metrics

    async def choose(self, request, budget):
        """决策窗先取得父代合法保底，再运行有界研究前瞻。"""
        plan = await self.parent.choose(request, budget)
        started = time.perf_counter()
        try:
            selected, evidence = select(request, plan)
        except Exception as error:
            selected = None
            evidence = {"reason": "projection_exception",
                        "error_type": type(error).__name__,
                        "error": str(error)[:160]}
        elapsed = (time.perf_counter() - started) * 1000.0
        if selected is None:
            self.metrics.append({"decision_id": request.decision_id,
                                 "status": "kept_parent", **evidence,
                                 "elapsed_ms": round(elapsed, 3)})
            return plan
        chosen = next((item for item in plan.candidates
                       if item.action_key == selected), None)
        if chosen is None:
            self.metrics.append({"decision_id": request.decision_id,
                                 "status": "fallback", "reason": "selected_not_in_parent",
                                 "elapsed_ms": round(elapsed, 3)})
            return plan
        ordered = (chosen,) + tuple(item for item in plan.candidates
                                   if item.action_key != selected)
        ranked = tuple(replace(item, rank=index + 1,
                               reasons=item.reasons + (("G217 合法第二步自然成面",)
                                                       if index == 0 else ()))
                       for index, item in enumerate(ordered))
        self.metrics.append({"decision_id": request.decision_id,
                             "status": "adopted", **evidence,
                             "elapsed_ms": round(elapsed, 3)})
        return replace(plan, candidates=ranked)


def policy_factory(metrics: list[dict]):
    """研究桌隔离装配父代和本候选；校准源先核内容摘要。"""
    _assert_source()

    def build(monotonic):
        return TwoStepNaturalRoutePolicy(g210.parent_factory(monotonic), metrics)

    return build
