"""G168 离线候选：每手首次零白二向听严格宽面冲突仅改弃一次。"""

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
import time


def _width(facts) -> tuple[int, int] | None:
    """生产普通型有效码和公开未见容量；未知不猜牌墙概率。"""
    if facts is None or facts.standard_useful_tiles is None:
        return None
    values = [item.remaining_estimate for item in facts.standard_useful_tiles]
    if any(type(value) is not int or value < 0 for value in values):
        return None
    return len(values), sum(values)


def select(request, plan) -> tuple[str | None, dict, bool]:
    """返回已评分合法备选、诊断理由、是否消耗本手唯一改弃机会。"""
    if request.window_key.phase.value != "draw" or not plan.candidates:
        return None, {"reason": "not_draw_or_empty"}, False
    if request.rejected_attempts:
        return None, {"reason": "previous_attempt_rejected"}, False
    parent_key = plan.candidates[0].action_key
    if not parent_key.startswith("discard:") or parent_key == "discard:白":
        return None, {"reason": "parent_not_nonwhite_discard"}, False
    observation = request.observation
    white_before = (sum(tile.code == "白" for tile in observation.my_hand)
                    + int(observation.drawn_tile is not None
                          and observation.drawn_tile.code == "白"))
    if white_before != 0:
        return None, {"reason": "white_present"}, False
    if any(meld.kind in ("chi", "peng")
           for meld in observation.melds[observation.seat]):
        return None, {"reason": "own_chi_peng"}, False
    ranked = {item.action_key: item for item in plan.candidates}
    if len(ranked) != len(plan.candidates):
        return None, {"reason": "duplicate_ranked_action"}, False
    legal = {item.action_key: item for item in request.rules.legal_candidates}
    if parent_key not in legal or len(legal) != len(request.rules.legal_candidates):
        return None, {"reason": "legal_action_mismatch"}, False
    parent = legal[parent_key].facts
    if parent is None or type(parent.standard_shanten_after) is not int:
        return None, {"reason": "parent_standard_unknown"}, False
    if parent.standard_shanten_after != 2:
        return None, {"reason": "not_two_shanten"}, False
    parent_width = _width(parent)
    if parent_width is None:
        return None, {"reason": "parent_width_unknown"}, False
    options = []
    for ranked_action in plan.candidates[1:]:
        key = ranked_action.action_key
        if not key.startswith("discard:") or key == "discard:白" or key not in legal:
            continue
        facts = legal[key].facts
        if facts is None or facts.standard_shanten_after != 2:
            continue
        width = _width(facts)
        if width is None:
            continue
        if width[0] > parent_width[0] and width[1] > parent_width[1]:
            options.append((key, width, facts))
    if not options:
        return None, {"reason": "no_strict_wider_alternate"}, False
    key, width, alternate = min(options, key=lambda item: (
        -item[1][0], -item[1][1], item[0]))
    if (type(parent.shanten_after) is not int
            or type(alternate.shanten_after) is not int):
        return None, {"reason": "combined_shanten_unknown",
                      "alternate_action": key}, True
    if alternate.shanten_after > parent.shanten_after:
        return None, {"reason": "combined_shanten_regression",
                      "alternate_action": key,
                      "parent_combined_shanten": parent.shanten_after,
                      "alternate_combined_shanten": alternate.shanten_after}, True
    return key, {
        "reason": "zero_white_first_strict_width",
        "parent_action": parent_key,
        "alternate_action": key,
        "parent_standard_width": parent_width,
        "alternate_standard_width": width,
        "parent_combined_shanten": parent.shanten_after,
        "alternate_combined_shanten": alternate.shanten_after,
    }, True


class ZeroWhiteFirstWidthPolicy:
    """研究包装器：父代先生成完整合法计划，每手首次目标冲突后不再改弃。"""

    policy_id = "action_value_v1:research:g168-zero-white-first-width-v1"

    def __init__(self, baseline, metrics: list[dict]) -> None:
        self.baseline = baseline
        self.metrics = metrics
        self.hand_seen: set[tuple[str, int]] = set()

    async def choose(self, request, budget):
        """状态丢失或候选事实未知时采用父代；当前仅供离线完整桌验证。"""
        baseline = await self.baseline.choose(request, budget)
        hand_key = (request.window_key.game_id, request.window_key.round_no)
        if hand_key in self.hand_seen:
            return baseline
        started = time.perf_counter()
        try:
            key, evidence, consumed = select(request, baseline)
        except Exception as exc:
            key, consumed = None, False
            evidence = {"reason": "selector_exception", "error_type": type(exc).__name__}
        elapsed_ms = (time.perf_counter() - started) * 1000
        if consumed:
            self.hand_seen.add(hand_key)
        if key is None:
            if consumed or evidence["reason"] in (
                    "selector_exception", "legal_action_mismatch",
                    "duplicate_ranked_action"):
                self.metrics.append({"decision_id": request.decision_id,
                                     "status": "guarded_or_fallback", **evidence,
                                     "elapsed_ms": round(elapsed_ms, 3)})
            return baseline
        selected = next((item for item in baseline.candidates
                         if item.action_key == key), None)
        if selected is None:
            self.metrics.append({"decision_id": request.decision_id,
                                 "status": "fallback", "reason": "selected_not_in_plan"})
            return baseline
        ordered = (selected,) + tuple(item for item in baseline.candidates
                                      if item.action_key != key)
        ranked = tuple(replace(item, rank=index + 1,
                               reasons=item.reasons + (("G168 零白首次普通宽面",)
                                                       if index == 0 else ()))
                       for index, item in enumerate(ordered))
        self.metrics.append({"decision_id": request.decision_id,
                             "status": "adopted", "action": key,
                             **evidence, "elapsed_ms": round(elapsed_ms, 3)})
        return replace(baseline, candidates=ranked)


def policy_factory(metrics: list[dict]):
    """只离线装配冻结 R18 v2；没有在线状态恢复与动作时限验收。"""
    import paired_study

    baseline_factory = paired_study.policy_factory("r18_v2")

    def build(monotonic):
        return ZeroWhiteFirstWidthPolicy(baseline_factory(monotonic), metrics)

    return build
