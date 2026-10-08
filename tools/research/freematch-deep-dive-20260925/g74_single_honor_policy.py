"""G74 离线研究候选：严格牌效帕累托改善时，打单张非财神字牌。"""

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

from hangma_bot.hangma.engine import _build_context
from hangma_bot.hangma.interface import CandidateFactKind, RuleCompleteness


HONORS = frozenset(("东", "南", "西", "北", "中", "发"))


def _support(entries) -> tuple[int, int] | None:
    """普通型一步进张的正容量张数、牌码数；未知不写零。"""

    if entries is None:
        return None
    if any(type(item.remaining_estimate) is not int or not 0 <= item.remaining_estimate <= 4
           for item in entries):
        return None
    return sum(item.remaining_estimate for item in entries), sum(
        item.remaining_estimate > 0 for item in entries)


def _usable(item) -> bool:
    """缺事实、降级或番型向听未知的候选均不参与重排。"""

    facts = item.facts
    return (facts is not None and facts.fact_kind is CandidateFactKind.HAND_PROGRESS
            and facts.completeness is RuleCompleteness.COMPLETE
            and type(facts.shanten_after) is int
            and type(facts.standard_shanten_after) is int
            and _support(facts.standard_useful_tiles) is not None)


def select(request, plan) -> tuple[str | None, dict]:
    """只读玩家可见观察、生产规则事实与已评分合法候选。"""

    if request.window_key.phase.value != "draw" or not plan.candidates:
        return None, {"reason": "not_draw_or_empty"}
    parent = plan.candidates[0]
    parent_code = parent.action_key.removeprefix("discard:")
    if not parent.action_key.startswith("discard:") or parent_code in HONORS or parent_code == "白":
        return None, {"reason": "parent_not_suited_discard"}
    if any(item.action_key.startswith("hu") for item in request.rules.legal_candidates):
        return None, {"reason": "hu_available"}
    detail = ((parent.score_trace or {}).get("detail") or {})
    if any(isinstance(value, dict) and value.get("triggered") is True
           for value in detail.values()):
        return None, {"reason": "special_overlay"}
    observation = request.observation
    if observation.remaining_tile_count is None or observation.remaining_tile_count < 40:
        return None, {"reason": "late_or_unknown_wall"}
    full = Counter(tile.code for tile in _build_context(observation).full_hand())
    if full["白"] != 0:
        return None, {"reason": "white_in_hand"}
    legal = {item.action_key: item for item in request.rules.legal_candidates}
    scored = {item.action_key: item for item in plan.candidates}
    if (len(legal) != len(request.rules.legal_candidates)
            or len(scored) != len(plan.candidates) or parent.action_key not in legal):
        return None, {"reason": "candidate_identity_mismatch"}
    parent_rules = legal[parent.action_key]
    if not _usable(parent_rules):
        return None, {"reason": "parent_facts_unavailable"}
    p = parent_rules.facts
    p_support = _support(p.standard_useful_tiles)
    options = []
    for key, item in legal.items():
        if not key.startswith("discard:") or key not in scored:
            continue
        code = key.removeprefix("discard:")
        if code not in HONORS or full[code] != 1 or not _usable(item):
            continue
        facts = item.facts
        if (facts.shanten_after != p.shanten_after
                or facts.standard_shanten_after != p.standard_shanten_after
                or (facts.seven_pairs_shanten_after is None) !=
                   (p.seven_pairs_shanten_after is None)):
            continue
        if (facts.seven_pairs_shanten_after is not None
                and facts.seven_pairs_shanten_after > p.seven_pairs_shanten_after):
            continue
        if (p.baotou_after is not None and facts.baotou_after != p.baotou_after):
            continue
        support = _support(facts.standard_useful_tiles)
        if support[0] <= p_support[0] or support[1] <= p_support[1]:
            continue
        gap = parent.total_score - scored[key].total_score
        if not 0 < gap <= 7:
            continue
        options.append((support[0], support[1], scored[key].total_score, key, gap))
    if not options:
        return None, {"reason": "no_strict_honor_pareto"}
    chosen = sorted(options, key=lambda row: (-row[0], -row[1], -row[2], row[3]))[0]
    return chosen[3], {"reason": "strict_honor_pareto", "parent_score_gap": chosen[4],
                       "ordinary_capacity_gain": chosen[0] - p_support[0],
                       "ordinary_code_gain": chosen[1] - p_support[1]}


class SingleHonorPolicy:
    """离线整桌政策：先有冻结父代保底，再只重排本次合法动作。"""

    policy_id = "action_value_v1:research:g74-single-honor-pareto-v1"

    def __init__(self, baseline, metrics: list[dict]):
        self.baseline = baseline
        self.metrics = metrics

    async def choose(self, request, budget):
        """候选异常或身份不合时沿用父代规划，留下可审计计数。"""

        baseline = await self.baseline.choose(request, budget)
        started = time.perf_counter()
        try:
            key, evidence = select(request, baseline)
        except Exception as exc:
            key, evidence = None, {"reason": "selector_exception", "kind": type(exc).__name__}
        elapsed_ms = (time.perf_counter() - started) * 1000
        if key is None:
            if evidence["reason"] in ("selector_exception", "candidate_identity_mismatch"):
                self.metrics.append({"decision_id": request.decision_id,
                                     "status": "fallback", **evidence,
                                     "elapsed_ms": round(elapsed_ms, 3)})
            return baseline
        chosen = next((item for item in baseline.candidates if item.action_key == key), None)
        if chosen is None:
            self.metrics.append({"decision_id": request.decision_id, "status": "fallback",
                                 "reason": "selected_not_in_plan"})
            return baseline
        ordered = (chosen,) + tuple(item for item in baseline.candidates if item.action_key != key)
        ranked = tuple(replace(item, rank=index + 1,
                               reasons=item.reasons + (("G74 单张字牌严格牌效改选",)
                                                       if index == 0 else ()))
                       for index, item in enumerate(ordered))
        self.metrics.append({"decision_id": request.decision_id, "status": "adopted",
                             "action": key, **evidence, "elapsed_ms": round(elapsed_ms, 3)})
        return replace(baseline, candidates=ranked)


def policy_factory(metrics: list[dict]):
    """离线装配冻结 R18 v2；本研究源码没有线上发布身份。"""

    import paired_study

    baseline_factory = paired_study.policy_factory("r18_v2")

    def build(monotonic):
        return SingleHonorPolicy(baseline_factory(monotonic), metrics)

    return build
