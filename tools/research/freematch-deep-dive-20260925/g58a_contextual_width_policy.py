"""G58A 离线研究包装：受限作者纯函数重排 R18 v2 已评分的合法弃牌。"""

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

import g58a_author_program as author
from hangma_bot.hangma.engine import _build_context


def _support(facts) -> list[dict] | None:
    """生产公开未见容量投影；不是牌墙概率。"""

    if facts is None:
        return None
    return [{"tile": item.code, "remaining": item.remaining_estimate} for item in facts]


def select(request, plan) -> tuple[str | None, dict]:
    """只在父代弃牌且无合法立即胡时调用派生纯函数；未知或专项覆盖回退。"""

    if request.window_key.phase.value != "draw" or not plan.candidates:
        return None, {"reason": "not_draw_or_empty"}
    parent = plan.candidates[0]
    if not parent.action_key.startswith("discard:"):
        return None, {"reason": "parent_not_discard"}
    if any(item.action_key.startswith("hu") for item in request.rules.legal_candidates):
        return None, {"reason": "hu_available"}
    detail = ((parent.score_trace or {}).get("detail") or {})
    if any(isinstance(value, dict) and value.get("triggered") is True
           for value in detail.values()):
        return None, {"reason": "parent_special_overlay"}
    observation = request.observation
    seat = observation.seat
    full = Counter(tile.code for tile in _build_context(observation).full_hand())
    scores = observation.scores
    ctx = {
        "white_count": full["白"], "own_melds": len(observation.melds[seat]),
        "wall_remaining": observation.remaining_tile_count,
        "dealer": observation.dealer_seat == seat,
        "table_rank": 1 + sum(value > scores[seat] for value in scores),
        "opponent_melds": [len(observation.melds[(seat + offset) % 4])
                           for offset in (1, 2, 3)],
        "drawn_tile": None if observation.drawn_tile is None else observation.drawn_tile.code,
    }
    scored = {item.action_key: item for item in plan.candidates}
    if len(scored) != len(plan.candidates):
        return None, {"reason": "duplicate_plan_action"}
    legal = {item.action_key: item for item in request.rules.legal_candidates}
    if len(legal) != len(request.rules.legal_candidates) or parent.action_key not in legal:
        return None, {"reason": "legal_action_mismatch"}
    options = []
    for key, item in legal.items():
        if not key.startswith("discard:"):
            continue
        scored_item = scored.get(key)
        if scored_item is None:
            return None, {"reason": "unscored_legal_discard"}
        facts = item.facts
        options.append({
            "key": key, "score": scored_item.total_score, "is_parent": key == parent.action_key,
            "combined": None if facts is None else facts.shanten_after,
            "ordinary": None if facts is None else facts.standard_shanten_after,
            "seven": None if facts is None else facts.seven_pairs_shanten_after,
            "support": None if facts is None else _support(facts.useful_tiles),
            "ordinary_support": None if facts is None else _support(facts.standard_useful_tiles),
            "seven_support": None if facts is None else _support(facts.seven_pairs_useful_tiles),
            "baotou_after": None if facts is None else facts.baotou_after,
            "white_after": full["白"] - (key == "discard:白"),
        })
    options.sort(key=lambda item: item["key"])
    key = author.choose(ctx, options)
    if key is None:
        return None, {"reason": "author_abstained"}
    if key == parent.action_key or key not in legal or key not in scored or not key.startswith("discard:"):
        return None, {"reason": "author_invalid_action", "action": key}
    chosen = next(item for item in options if item["key"] == key)
    return key, {"reason": "g58a_contextual_width", "parent_score_gap":
                 parent.total_score - scored[key].total_score,
                 "parent_combined": next(item for item in options
                                         if item["is_parent"])["combined"],
                 "chosen_combined": chosen["combined"],
                 "white_count": ctx["white_count"]}


class ContextualWidthPolicy:
    """仅供离线完整桌赛：父代始终先提供合法保底，作者异常逐点回退。"""

    policy_id = "action_value_v1:research:g58a-contextual-width-v1"

    def __init__(self, baseline, metrics: list[dict]):
        self.baseline = baseline
        self.metrics = metrics

    async def choose(self, request, budget):
        """先让冻结父代完整规划；只改变本次合法动作的排序。"""

        baseline = await self.baseline.choose(request, budget)
        start = time.perf_counter()
        try:
            key, evidence = select(request, baseline)
        except Exception as error:
            key, evidence = None, {"reason": "selector_exception", "error_type": type(error).__name__}
        elapsed_ms = (time.perf_counter() - start) * 1000
        if key is None:
            if evidence["reason"] in ("selector_exception", "author_invalid_action",
                                      "duplicate_plan_action", "legal_action_mismatch",
                                      "unscored_legal_discard"):
                self.metrics.append({"decision_id": request.decision_id, "status": "fallback",
                                     **evidence, "elapsed_ms": round(elapsed_ms, 3)})
            return baseline
        selected = next((item for item in baseline.candidates if item.action_key == key), None)
        if selected is None:
            self.metrics.append({"decision_id": request.decision_id, "status": "fallback",
                                 "reason": "selected_not_in_plan"})
            return baseline
        ordered = (selected,) + tuple(item for item in baseline.candidates if item.action_key != key)
        ranked = tuple(replace(item, rank=index + 1,
                               reasons=item.reasons + (("G58A 同层情境有效张仲裁",)
                                                       if index == 0 else ()))
                       for index, item in enumerate(ordered))
        self.metrics.append({"decision_id": request.decision_id, "status": "adopted",
                             "action": key, **evidence, "elapsed_ms": round(elapsed_ms, 3)})
        return replace(baseline, candidates=ranked)


def policy_factory(metrics: list[dict]):
    """离线装配冻结 R18 v2；新策略没有线上发布或时限资格。"""

    import paired_study

    baseline_factory = paired_study.policy_factory("r18_v2")

    def build(monotonic):
        return ContextualWidthPolicy(baseline_factory(monotonic), metrics)

    return build
