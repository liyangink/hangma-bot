"""G221 离线候选：用可见公开容量的合法两摸互斥结算比较弃牌。"""

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

from dataclasses import replace
import math
import time

import c31_action_layer_gap as c31
import g196_three_draw_competing_route_pilot as g196
import g210_post_claim_guarded_familiar_policy as g210
import g219_two_draw_settlement_route as g219


POLICY_ID = "action_value_v1:research:g221-settlement-route-v1"
MAX_SELECT_MS = 350.0
# 为异常回退、审计记录和函数返回预留 10 ms，实测上限仍以 350 ms 计。
INTERNAL_STOP_MS = 340.0
EPS = 1e-8


class BoundedSearch(g219.ModeSearch):
    """单臂本地操作墙钟有界；总选择器另有 350 ms 整窗边界。"""

    def __init__(self, observation, config, root_action: str, *, restricted: bool,
                 deadline: float) -> None:
        super().__init__(observation, config, root_action, restricted=restricted)
        self.deadline = deadline

    def _check_budget(self) -> None:
        super()._check_budget()
        if time.perf_counter() >= self.deadline:
            raise g196.RouteLimitExceeded("G221 达到内部预算截止")

    def _win(self, waiting, code, *, baotou, chain, piao, depth):
        """每次条件胡分解前后检查整窗预算，避免单臂长算后才发现超时。"""
        self._check_budget()
        value = super()._win(waiting, code, baotou=baotou,
                             chain=chain, piao=piao, depth=depth)
        self._check_budget()
        return value

    def _legal(self, waiting, draw_code, restricted):
        """未来合法弃牌规则分析也必须处在同一绝对截止内。"""
        self._check_budget()
        legal = super()._legal(waiting, draw_code, restricted)
        self._check_budget()
        return legal


def _eligible(request, plan) -> tuple[dict, object, list[str]] | tuple[None, None, None]:
    """只取生产合法、同向听、非白根；不读对手暗手或赛果。"""
    if (request.window_key.phase.value != "draw" or request.rejected_attempts
            or not plan.candidates or any(item.action_key == "hu"
                                         for item in request.rules.legal_candidates)):
        return None, None, None
    parent_key = plan.candidates[0].action_key
    wealth = request.observation.rule_state.wealth_god.code
    if not parent_key.startswith("discard:") or parent_key == "discard:" + wealth:
        return None, None, None
    legal = {item.action_key: item for item in request.rules.legal_candidates}
    parent = legal.get(parent_key)
    if (parent is None or parent.facts is None
            or parent.facts.standard_shanten_after not in (0, 1)
            or type(parent.facts.standard_shanten_after) is not int
            or g210._width(parent.facts.standard_useful_tiles) is None):
        return None, None, None
    alternatives = g219.shortlist(plan, legal, parent_key, wealth)
    if not alternatives:
        return None, None, None
    return legal, parent, alternatives


def _arm(request, legal: dict, action_key: str, deadline: float) -> dict:
    """生产规则逐码对账后计算一条根弃牌的两个条件续打权重。"""
    search = BoundedSearch(request.observation, c31.RULE_CONFIG, action_key,
                           restricted=False, deadline=deadline)
    g219.first_hu_parity(search, legal[action_key], request.observation.seat)
    branches = search.branches()
    half, half_deferred = search.value(branches, 0.5)
    full, full_deferred = search.value(branches, 1.0)
    if (not math.isfinite(half.total) or not math.isfinite(full.total)
            or half.total < 0 or full.total + EPS < half.total):
        raise ValueError("G221 两摸互斥结算或权重单调性失败")
    return {"half": half, "full": full,
            "half_deferred_codes": half_deferred,
            "full_deferred_codes": full_deferred,
            "legal_leaf_count": search.legal_leaf_count}


def select(request, plan) -> tuple[str | None, dict]:
    """按较保守条件结算值改弃；任何异常由包装器整体回退父代。"""
    legal, parent_fact, alternatives = _eligible(request, plan)
    if legal is None:
        return None, {"reason": "ineligible"}
    started = time.perf_counter()
    deadline = started + INTERNAL_STOP_MS / 1000.0
    parent_ranked = plan.candidates[0]
    parent_key = parent_ranked.action_key
    parent_risk = g210._risk(parent_ranked)
    if parent_risk is None:
        return None, {"reason": "unknown_parent_risk"}
    ranked = {item.action_key: item for item in plan.candidates}
    root = _arm(request, legal, parent_key, deadline)
    best_key, best_arm = parent_key, root
    evaluated = 0
    skipped_risk = 0
    for key in alternatives:
        if time.perf_counter() >= deadline:
            raise g196.RouteLimitExceeded("G221 达到内部预算截止")
        ranked_item = ranked.get(key)
        fact = legal[key].facts
        if ranked_item is None or fact is None:
            raise ValueError("父代排名或生产规则事实缺失")
        risk = g210._risk(ranked_item)
        if (risk is None or risk > parent_risk + EPS
                or (parent_fact.facts.baotou_after is True
                    and fact.baotou_after is not True)):
            skipped_risk += 1
            continue
        arm = _arm(request, legal, key, deadline)
        evaluated += 1
        if arm["half"].total > best_arm["half"].total + EPS:
            best_key = key
            best_arm = arm
    if time.perf_counter() >= deadline:
        raise g196.RouteLimitExceeded("G221 达到内部预算截止")
    if best_key == parent_key:
        return None, {"reason": "parent_value_not_beaten", "evaluated": evaluated,
                      "skipped_risk": skipped_risk}
    best_width = g210._width(legal[best_key].facts.standard_useful_tiles)
    parent_width = g210._width(parent_fact.facts.standard_useful_tiles)
    return best_key, {
        "reason": "higher_two_draw_settlement",
        "parent_action": parent_key, "alternate_action": best_key,
        "half_total_gain": round(best_arm["half"].total - root["half"].total, 9),
        "half_plain_gain": round(best_arm["half"].plain - root["half"].plain, 9),
        "half_special_gain": round(best_arm["half"].special - root["half"].special, 9),
        "full_total_gain": round(best_arm["full"].total - root["full"].total, 9),
        "type_gain": best_width[0] - parent_width[0],
        "capacity_gain": best_width[1] - parent_width[1],
        "evaluated": evaluated, "skipped_risk": skipped_risk,
    }


class SettlementRoutePolicy:
    """只重排父代已给出的合法候选；失败仍使用原父代计划。"""

    policy_id = POLICY_ID

    def __init__(self, parent, metrics: list[dict]) -> None:
        self.parent = parent
        self.metrics = metrics

    async def choose(self, request, budget):
        """先取得父代合法保底，离线研究值仅影响正常摸打的首选顺序。"""
        plan = await self.parent.choose(request, budget)
        started = time.perf_counter()
        try:
            selected, evidence = select(request, plan)
        except Exception as error:
            selected = None
            evidence = {"reason": "selector_exception",
                        "error_type": type(error).__name__,
                        "error": str(error)[:160]}
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        if selected is None:
            if evidence["reason"] != "ineligible":
                self.metrics.append({"decision_id": request.decision_id,
                                     "status": "fallback" if evidence["reason"] == "selector_exception"
                                               else "kept_parent",
                                     **evidence, "elapsed_ms": round(elapsed_ms, 3)})
            return plan
        chosen = next((item for item in plan.candidates
                       if item.action_key == selected), None)
        if chosen is None:
            self.metrics.append({"decision_id": request.decision_id,
                                 "status": "fallback", "reason": "selected_not_in_parent",
                                 "elapsed_ms": round(elapsed_ms, 3)})
            return plan
        ordered = (chosen,) + tuple(item for item in plan.candidates
                                   if item.action_key != selected)
        ranked = tuple(replace(item, rank=index + 1,
                               reasons=item.reasons + (("G221 同值合法两摸结算",)
                                                       if index == 0 else ()))
                       for index, item in enumerate(ordered))
        self.metrics.append({"decision_id": request.decision_id,
                             "status": "adopted", **evidence,
                             "elapsed_ms": round(elapsed_ms, 3)})
        return replace(plan, candidates=ranked)


def policy_factory(metrics: list[dict]):
    """每个离线桌赛单元新建父代与指标容器；不改线上组合根。"""
    def build(monotonic):
        return SettlementRoutePolicy(g210.parent_factory(monotonic), metrics)
    return build
