"""G49 离线种子：每窗重估保白普通型路线的有界独有改选。"""

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

from collections import Counter
from dataclasses import replace
import time

import g40_official_natural_gap_reach as natural
from hangma_bot.hangma.engine import _build_context
from hangma_bot.kernel.actions import Tile


SCORE_GAP_CAP = 10.0  # 事前沿用 G10 的父代近分描述带，非由 G49 桌分调出。


def _support(entries) -> int | None:
    """当前分层公开未见张数；缺事实即弃权，不把它解释为墙内概率。"""

    if entries is None:
        return None
    amounts = [item.remaining_estimate for item in entries]
    return sum(amounts) if all(type(value) is int and value >= 0 for value in amounts) else None


def _after(full: Counter, key: str) -> Counter | None:
    if not key.startswith("discard:"):
        return None
    tile = key.split(":", 1)[1]
    if full[tile] <= 0:
        return None
    after = full.copy()
    after[tile] -= 1
    if after[tile] == 0:
        del after[tile]
    return after


def select(request, plan) -> tuple[str | None, dict]:
    """只返回 R18 已评分合法备选；新入口严格排除 G10 无容量代价的窗口。"""

    if request.window_key.phase.value != "draw" or not plan.candidates:
        return None, {"reason": "not_draw_or_empty"}
    parent = plan.candidates[0]
    if not parent.action_key.startswith("discard:"):
        return None, {"reason": "parent_not_discard"}
    if any(item.action_key.startswith("hu:") or item.action_key == "hu"
           for item in request.rules.legal_candidates):
        return None, {"reason": "hu_available"}
    legal = {item.action_key: item for item in request.rules.legal_candidates}
    if parent.action_key not in legal:
        return None, {"reason": "parent_not_legal"}
    facts = legal[parent.action_key].facts
    if facts is None or type(facts.shanten_after) is not int or type(facts.standard_shanten_after) is not int:
        return None, {"reason": "parent_facts_unknown"}
    seven = facts.seven_pairs_shanten_after
    if type(seven) is not int or seven < 1:
        return None, {"reason": "seven_tenpai_or_unknown"}
    parent_support = _support(facts.useful_tiles)
    if parent_support is None:
        return None, {"reason": "parent_support_unknown"}
    observation = request.observation
    full = Counter(tile.code for tile in _build_context(observation).full_hand())
    parent_hand = _after(full, parent.action_key)
    if parent_hand is None or parent_hand["白"] <= 0:
        return None, {"reason": "no_retained_white"}
    melds = len(observation.melds[observation.seat])
    parent_gap = natural.gap(parent_hand, melds)
    if natural.standard(parent_hand, melds) != facts.standard_shanten_after:
        return None, {"reason": "parent_rule_math_mismatch"}
    ranked = {item.action_key: item for item in plan.candidates}
    if len(ranked) != len(plan.candidates):
        return None, {"reason": "duplicate_plan_action"}
    options = []
    g10_available = False
    for key, rule in legal.items():
        if key == parent.action_key or key not in ranked or not key.startswith("discard:") or key == "discard:白":
            continue
        alt = rule.facts
        if (alt is None or type(alt.shanten_after) is not int
                or type(alt.standard_shanten_after) is not int
                or type(alt.seven_pairs_shanten_after) is not int):
            continue
        after = _after(full, key)
        if after is None or after["白"] != parent_hand["白"]:
            continue
        if (alt.shanten_after != facts.shanten_after
                or alt.standard_shanten_after != facts.standard_shanten_after - 1
                or alt.seven_pairs_shanten_after > seven):
            continue
        alt_support = _support(alt.useful_tiles)
        if alt_support is None:
            continue
        if alt_support >= parent_support:
            g10_available = True
            continue
        score_gap = parent.total_score - ranked[key].total_score
        if not 0 <= score_gap <= SCORE_GAP_CAP:
            continue
        if natural.standard(after, melds) != alt.standard_shanten_after:
            return None, {"reason": "alternate_rule_math_mismatch"}
        alt_gap = natural.gap(after, melds)
        if alt_gap != parent_gap - 1:
            continue
        options.append((score_gap, -alt_support, key, alt_gap))
    if g10_available:
        return None, {"reason": "old_g10_route_available"}
    if not options:
        return None, {"reason": "no_bounded_new_route"}
    score_gap, negative_support, key, alt_gap = min(options)
    return key, {"reason": "g49_novel_ordinary_route", "parent_natural_need": parent_gap,
                 "alternate_natural_need": alt_gap, "parent_combined_support": parent_support,
                 "alternate_combined_support": -negative_support,
                 "parent_score_gap": score_gap, "white_count": parent_hand["白"]}


class NaturalRoutePolicy:
    """研究包装器：当前窗全部事实可重算，任意缺证据退回冻结父代。"""

    policy_id = "action_value_v1:research:g49-novel-ordinary-route-v1"

    def __init__(self, baseline, metrics: list[dict]):
        self.baseline = baseline
        self.metrics = metrics

    async def choose(self, request, budget):
        """先取得完整合法保底计划；只在父代已选择弃牌时调整排序。"""

        baseline = await self.baseline.choose(request, budget)
        started = time.perf_counter()
        try:
            key, evidence = select(request, baseline)
        except Exception as exc:
            key, evidence = None, {"reason": "selector_exception", "error_type": type(exc).__name__}
        elapsed_ms = (time.perf_counter() - started) * 1000
        if key is None:
            if evidence["reason"] in ("selector_exception", "parent_rule_math_mismatch",
                                      "alternate_rule_math_mismatch"):
                self.metrics.append({"decision_id": request.decision_id, "status": "fallback",
                                     **evidence, "elapsed_ms": round(elapsed_ms, 3)})
            return baseline
        selected = next((item for item in baseline.candidates if item.action_key == key), None)
        if selected is None:
            self.metrics.append({"decision_id": request.decision_id,
                                 "status": "fallback", "reason": "selected_not_in_plan"})
            return baseline
        ordered = (selected,) + tuple(item for item in baseline.candidates if item.action_key != key)
        ranked = tuple(replace(item, rank=index + 1,
                               reasons=item.reasons + (("G49 保白普通型跨路线进入",)
                                                       if index == 0 else ()))
                       for index, item in enumerate(ordered))
        self.metrics.append({"decision_id": request.decision_id, "status": "adopted",
                             "action": key, **evidence, "elapsed_ms": round(elapsed_ms, 3)})
        return replace(baseline, candidates=ranked)


def policy_factory(metrics: list[dict]):
    """离线装配冻结 R18 v2；本研究种子尚无总工作量/线上时限证明。"""

    import paired_study

    baseline_factory = paired_study.policy_factory("r18_v2")

    def build(monotonic):
        return NaturalRoutePolicy(baseline_factory(monotonic), metrics)

    return build
