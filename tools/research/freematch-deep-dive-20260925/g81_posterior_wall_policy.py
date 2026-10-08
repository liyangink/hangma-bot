"""G81 离线候选：用固定公开占用后验校正 R18 v2 的有效牌项。"""

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
import math
import time

from hangma_bot.hangma.engine import _build_context
from hangma_bot.hangma.interface import CandidateFactKind, RuleCompleteness
from hangma_bot.hangma.internal_types import TILE_ORDER
from hangma_bot.hangma.public_tile_counts import count_unseen_tiles


# G79B 冻结系数，顺序与 G79B-CORRECTED-OCCUPANCY-RESULT 的八维特征完全相同。
COEFFICIENTS = (
    -0.39314279657013323, -0.11559617088927696,
    -0.014252653505989277, 0.1146038257135079,
    -0.5931214339095022, -0.26845990045669443,
    -0.11862114699473385, 0.07150313370488913,
)
ORDER = tuple(TILE_ORDER)
INDEX = {code: index for index, code in enumerate(ORDER)}


def _sigmoid(value: float) -> float:
    """稳定计算某公开未知实体牌位于他家暗手的条件概率。"""

    value = max(-35.0, min(35.0, value))
    return 1.0 / (1.0 + math.exp(-value))


def predict_wall_counts(observation) -> tuple[tuple[int, ...], tuple[float, ...], int, int] | None:
    """只读玩家可见事实；任何牌码/总数不守恒均弃权。"""

    seat = observation.seat
    if len(observation.discards) != 4 or len(observation.melds) != 4 or len(observation.hand_counts) != 4:
        return None
    wall = observation.remaining_tile_count
    if type(wall) is not int or wall <= 0:
        return None
    H = sum(count for other, count in enumerate(observation.hand_counts) if other != seat)
    if H <= 0:
        return None
    try:
        hand = _build_context(observation).full_hand()
    except (ValueError, TypeError):
        return None
    if len(hand) != observation.hand_counts[seat]:
        return None
    raw = count_unseen_tiles(observation)
    if len(raw) != 34 or any(type(amount) is not int or not 0 <= amount <= 4 for amount in raw):
        return None
    unknown = tuple(raw)
    if sum(unknown) != H + wall:
        return None
    rivers = [[tile.code for tile in river] for river in observation.discards]
    own_river = Counter(rivers[seat])
    other_river = Counter(code for other, river in enumerate(rivers)
                          if other != seat for code in river)
    meld_suit = Counter()
    for other, seat_melds in enumerate(observation.melds):
        if other == seat:
            continue
        for meld in seat_melds:
            codes = [tile.code for tile in meld.tiles]
            if codes and len(codes[0]) == 2 and codes[0][1] in "wbt":
                meld_suit[codes[0][1]] += 1
    logits = []
    offset = math.log(H / wall)
    for index, code in enumerate(ORDER):
        honor = code == "白" or not (len(code) == 2 and code[1] in "wbt")
        row = [float(honor), float(not honor and code[0] in "19"),
               float(not honor and code[0] in "28"), float(unknown[index] - 2),
               float(min(2, other_river[code])), float(min(2, own_river[code])),
               0.0, 0.0]
        if not honor:
            number, suit = int(code[0]), code[1]
            row[6] = float(min(4, sum(other_river[f"{neighbor}{suit}"]
                                    for neighbor in (number - 1, number + 1)
                                    if 1 <= neighbor <= 9)))
            row[7] = float(min(2, meld_suit[suit]))
        logits.append(offset + sum(weight * feature for weight, feature in zip(COEFFICIENTS, row)))
    lower, upper = -35.0, 35.0
    for _ in range(48):
        middle = (lower + upper) / 2.0
        if sum(n * _sigmoid(z + middle) for n, z in zip(unknown, logits)) < H:
            lower = middle
        else:
            upper = middle
    shift = (lower + upper) / 2.0
    predicted = tuple(n * (1.0 - _sigmoid(z + shift)) for n, z in zip(unknown, logits))
    if not math.isclose(sum(predicted), wall, abs_tol=1e-6):
        return None
    return unknown, predicted, H, wall


def _useful(facts, unknown: tuple[int, ...]) -> tuple[str, ...] | None:
    """从生产规则事实读取有效牌码，逐码对拍生产未知实体容量。"""

    entries = facts.useful_tiles
    if entries is None:
        return None
    found = []
    for item in entries:
        code, amount = item.code, item.remaining_estimate
        if code not in INDEX or type(amount) is not int or amount != unknown[INDEX[code]]:
            return None
        if amount > 0:
            found.append(code)
    if len(set(found)) != len(found):
        return None
    return tuple(found)


def _usable(item) -> bool:
    """仅认可生产规则已完成、父代按原始 V2 基础式评分的弃牌。"""

    facts = item.facts
    return (facts is not None and facts.fact_kind is CandidateFactKind.HAND_PROGRESS
            and facts.completeness is RuleCompleteness.COMPLETE
            and type(facts.shanten_after) is int
            and type(facts.standard_shanten_after) is int)


def select(request, plan) -> tuple[str | None, dict]:
    """返回比冻结父代校正分更高的合法弃牌键；所有未知逐窗回退。"""

    if request.window_key.phase.value != "draw" or not plan.candidates:
        return None, {"reason": "not_draw_or_empty"}
    parent = plan.candidates[0]
    if not parent.action_key.startswith("discard:"):
        return None, {"reason": "parent_not_discard"}
    if request.rules.completeness is not RuleCompleteness.COMPLETE:
        return None, {"reason": "rules_incomplete"}
    if any(item.action_key.startswith("hu") for item in request.rules.legal_candidates):
        return None, {"reason": "hu_available"}
    detail = ((parent.score_trace or {}).get("detail") or {})
    if detail.get("basis") != "direct_v2" or any(
        isinstance(value, dict) and value.get("triggered") is True
        for scored_item in plan.candidates
        for value in (((scored_item.score_trace or {}).get("detail") or {}).values())
    ):
        return None, {"reason": "special_overlay_or_score_basis"}
    observation = request.observation
    seat = observation.seat
    if len(observation.discards[seat]) < 3:
        return None, {"reason": "before_fourth_discard"}
    forecast = predict_wall_counts(observation)
    if forecast is None:
        return None, {"reason": "posterior_unavailable"}
    unknown, predicted, H, wall = forecast
    legal = {item.action_key: item for item in request.rules.legal_candidates}
    scored = {item.action_key: item for item in plan.candidates}
    if (len(legal) != len(request.rules.legal_candidates)
            or len(scored) != len(plan.candidates) or parent.action_key not in legal):
        return None, {"reason": "candidate_identity_mismatch"}
    parent_rule = legal[parent.action_key]
    if not _usable(parent_rule):
        return None, {"reason": "parent_facts_unavailable"}
    parent_facts = parent_rule.facts
    own_white = sum(tile.code == "白" for tile in _build_context(observation).full_hand())
    parent_white = own_white - (parent.action_key == "discard:白")
    parent_codes = _useful(parent_facts, unknown)
    if parent_codes is None:
        return None, {"reason": "rule_unknown_capacity_mismatch"}
    if (type(detail.get("base_score")) not in (int, float)
            or not math.isclose(detail["base_score"],
                                -100 * parent_facts.shanten_after +
                                sum(unknown[INDEX[code]] for code in parent_codes),
                                abs_tol=1e-6)):
        return None, {"reason": "parent_score_basis_mismatch"}
    order = {item.action_key: index for index, item in enumerate(plan.candidates)}
    options = []
    for key, rule in legal.items():
        if not key.startswith("discard:") or key not in scored or not _usable(rule):
            continue
        facts = rule.facts
        if (facts.shanten_after != parent_facts.shanten_after
                or facts.standard_shanten_after != parent_facts.standard_shanten_after
                or (parent_facts.seven_pairs_shanten_after is None) !=
                   (facts.seven_pairs_shanten_after is None)
                or (parent_facts.seven_pairs_shanten_after is not None
                    and facts.seven_pairs_shanten_after > parent_facts.seven_pairs_shanten_after)
                or (parent_facts.baotou_after is True and facts.baotou_after is not True)
                or own_white - (key == "discard:白") < parent_white):
            continue
        trace = ((scored[key].score_trace or {}).get("detail") or {})
        if trace.get("basis") != "direct_v2" or any(
            isinstance(value, dict) and value.get("triggered") is True for value in trace.values()
        ):
            continue
        codes = _useful(facts, unknown)
        if codes is None:
            return None, {"reason": "rule_unknown_capacity_mismatch"}
        if (type(trace.get("base_score")) not in (int, float)
                or not math.isclose(trace["base_score"],
                                    -100 * facts.shanten_after +
                                    sum(unknown[INDEX[code]] for code in codes),
                                    abs_tol=1e-6)):
            return None, {"reason": "candidate_score_basis_mismatch"}
        expected_wall = sum(predicted[INDEX[code]] for code in codes)
        baseline_wall = sum(unknown[INDEX[code]] for code in codes) * wall / (H + wall)
        correction = (expected_wall - baseline_wall) * (H + wall) / wall
        if not (math.isfinite(correction) and math.isfinite(scored[key].total_score)):
            return None, {"reason": "nonfinite_score"}
        adjusted = round(scored[key].total_score + correction, 9)
        options.append((adjusted, order[key], key, correction, expected_wall,
                        baseline_wall, scored[key].total_score))
    if not options or not any(row[2] == parent.action_key for row in options):
        return None, {"reason": "no_comparable_options"}
    options.sort(key=lambda row: (-row[0], row[1]))
    best = options[0]
    if best[2] == parent.action_key:
        return None, {"reason": "parent_still_best"}
    return best[2], {"reason": "posterior_recalibration", "parent_action": parent.action_key,
                     "parent_score_gap": parent.total_score - best[6],
                     "correction": best[3], "expected_wall_support": best[4],
                     "exchangeable_wall_support": best[5], "candidate_score": best[0],
                     "parent_corrected_score": next(row[0] for row in options
                                                    if row[2] == parent.action_key)}


class PosteriorWallPolicy:
    """研究装配：R18 v2 先生成保底计划，后验校正失败时原样返回。"""

    policy_id = "action_value_v1:research:g81-posterior-wall-v1"

    def __init__(self, baseline, metrics: list[dict]):
        self.baseline = baseline
        self.metrics = metrics

    async def choose(self, request, budget):
        """不更改合法集和动作提交；只重排父代计划里已有的一个弃牌。"""

        baseline = await self.baseline.choose(request, budget)
        start = time.perf_counter()
        try:
            key, evidence = select(request, baseline)
        except Exception as error:
            key, evidence = None, {"reason": "selector_exception", "error_type": type(error).__name__}
        elapsed_ms = (time.perf_counter() - start) * 1000
        if key is None:
            if evidence["reason"] in ("selector_exception", "posterior_unavailable",
                                      "rule_unknown_capacity_mismatch", "candidate_identity_mismatch",
                                      "nonfinite_score"):
                self.metrics.append({"decision_id": request.decision_id, "status": "fallback",
                                     **evidence, "elapsed_ms": round(elapsed_ms, 3)})
            return baseline
        chosen = next((item for item in baseline.candidates if item.action_key == key), None)
        if chosen is None:
            self.metrics.append({"decision_id": request.decision_id, "status": "fallback",
                                 "reason": "selected_not_in_plan"})
            return baseline
        ordered = (chosen,) + tuple(item for item in baseline.candidates if item.action_key != key)
        ranked = tuple(replace(item, rank=index + 1,
                               reasons=item.reasons + (("G81 公开占用后验墙内进张校正",)
                                                       if index == 0 else ()))
                       for index, item in enumerate(ordered))
        self.metrics.append({"decision_id": request.decision_id, "status": "adopted",
                             "action": key, **evidence, "elapsed_ms": round(elapsed_ms, 3)})
        return replace(baseline, candidates=ranked)


def policy_factory(metrics: list[dict]):
    """离线装配冻结 R18 v2；本研究版本没有线上发布身份。"""

    import paired_study

    baseline_factory = paired_study.policy_factory("r18_v2")

    def build(monotonic):
        return PosteriorWallPolicy(baseline_factory(monotonic), metrics)

    return build
