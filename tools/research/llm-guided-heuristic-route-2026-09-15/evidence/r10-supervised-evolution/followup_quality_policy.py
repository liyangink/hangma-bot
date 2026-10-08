"""受监督离线原型：只用唯一规则入口细分V2前列同牌效弃牌；不得直接发布。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution'

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
from time import perf_counter

from followup_rule_probe import hypothetical_observation
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import CandidateFactKind, RuleCompleteness
from hangma_bot.hangma.public_tile_counts import count_public_tiles
from hangma_bot.kernel.actions import CANONICAL_TILE_ORDER, Discard
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2

PROFILE = {"id": "offline-followup-quality-v1", "max_rule_calls": 476,
           "max_elapsed_seconds": 2.0, "max_requests_per_table": 20000,
           "release_eligible": False, "restricted_candidate": False}


class AnalysisUnavailable(ValueError):
    """本次条件事实不完整；整个增强回退V2，不保留部分有利分支。"""


def comparable_fact(candidate):
    """返回可信的当前直接牌效；未知保留为空，计数单位是公开未见枚数。"""
    facts = candidate.facts
    if (not isinstance(candidate.action, Discard) or facts is None
            or facts.fact_kind is not CandidateFactKind.HAND_PROGRESS
            or facts.completeness is not RuleCompleteness.COMPLETE
            or type(facts.shanten_after) is not int or facts.shanten_after < 1):
        return None
    return facts.shanten_after, sum(t.remaining_estimate for t in facts.useful_tiles)


class FollowupQualityPolicy:
    """离线组合V2与受信后继分析器；模型不参与动作闭环，不读模拟完整世界。"""

    policy_id = PROFILE["id"]

    def __init__(self, rule_config, monotonic, *, enabled=True):
        """绑定冻结规则、V2时钟与研究开关；仅保存有界内存审计，无文件副作用。"""
        self.baseline = ComparableHeuristicPolicyV2(monotonic=monotonic)
        self.rules = HangmaRules(rule_config)
        self.enabled = enabled
        self.audit = []

    async def choose(self, request, budget):
        """先取得完整V2退路，再按冻结的条件支持改良量细分可比弃牌前缀。"""
        base = await self.baseline.choose(request, budget)
        if len(self.audit) >= PROFILE["max_requests_per_table"]:
            raise ValueError("离线原型审计请求超过冻结上限")
        row = {"decision_id": request.decision_id, "trigger_seq": request.trigger_seq,
               "status": "NOT_APPLICABLE", "rule_calls": 0, "elapsed_seconds": 0.0,
               "base_first": base.candidates[0].action_key if base.candidates else None,
               "selected_first": base.candidates[0].action_key if base.candidates else None,
               "changed": False, "qualities": []}
        self.audit.append(row)
        obs = request.observation
        full = obs.my_hand + (obs.drawn_tile,) if obs.drawn_tile is not None else obs.my_hand
        if (not self.enabled or not base.candidates or obs.phase != "draw"
                or obs.turn_seat != obs.seat or obs.drawn_tile is None
                or obs.rule_state.catch_play or obs.rule_state.chain_count != 0 or obs.rule_state.baotou
                or any(t == obs.rule_state.wealth_god for t in full)
                or obs.remaining_tile_count is None or obs.remaining_tile_count <= 21
                or len(full) != 14 - 3 * len(obs.melds[obs.seat])
                or obs.hand_counts[obs.seat] != len(full)
                or request.rules.completeness is not RuleCompleteness.COMPLETE):
            return base
        by_key = {c.action_key: c for c in request.rules.legal_candidates}
        first = by_key.get(base.candidates[0].action_key)
        target = comparable_fact(first) if first is not None else None
        if target is None or target[1] <= 0:
            return base
        prefix = []
        for candidate in base.candidates:
            original = by_key.get(candidate.action_key)
            if original is None or comparable_fact(original) != target:
                break
            prefix.append(candidate)
        if len(prefix) < 2:
            return base
        started = perf_counter()
        try:
            public = count_public_tiles(obs)
            if any(value is None for value in public):
                raise AnalysisUnavailable("公开计数未知")
            known = Counter(t.code for t in full)
            unseen = {code: max(0, 4 - known[code] - public[i]) for i, code in enumerate(CANONICAL_TILE_ORDER)}
            q, support = target
            for candidate in prefix:
                original = by_key[candidate.action_key]
                useful = {t.code for t in original.facts.useful_tiles}
                if any(unseen[t.code] != t.remaining_estimate for t in original.facts.useful_tiles):
                    raise AnalysisUnavailable("当前事实与公开计数口径不一致")
                numerator = 0
                nonprogress_weight = 0
                for code, weight in unseen.items():
                    if weight <= 0 or code in useful:
                        continue
                    if row["rule_calls"] >= PROFILE["max_rule_calls"] or perf_counter() - started > PROFILE["max_elapsed_seconds"]:
                        raise TimeoutError("研究分析额度耗尽")
                    conditional = hypothetical_observation(request, full, candidate.action.tile.code, code)
                    row["rule_calls"] += 1
                    analysis = self.rules.analyze(conditional)
                    if analysis.completeness is not RuleCompleteness.COMPLETE or analysis.issues:
                        raise AnalysisUnavailable("条件规则分析降级")
                    choices = []
                    for c in analysis.legal_candidates:
                        if not isinstance(c.action, Discard):
                            continue
                        f = c.facts
                        if (f is None or f.fact_kind is not CandidateFactKind.HAND_PROGRESS
                                or f.completeness is not RuleCompleteness.COMPLETE or type(f.shanten_after) is not int):
                            raise AnalysisUnavailable("条件合法弃牌事实未知")
                        choices.append((f.shanten_after, -sum(t.remaining_estimate for t in f.useful_tiles)))
                    if not choices or min(choices)[0] != q:
                        raise AnalysisUnavailable("非当前有效牌的条件弃牌向听不符合假设")
                    best_support = -min(choices)[1]
                    # 只表示不降向听条件下的支持增量代理；不把未见枚数当作牌墙概率。
                    numerator += weight * max(0, best_support - support)
                    nonprogress_weight += weight
                row["qualities"].append({"action_key": candidate.action_key,
                    "improvement_weighted_sum": numerator, "nonprogress_weight": nonprogress_weight})
            if len({x["nonprogress_weight"] for x in row["qualities"]}) != 1:
                raise AnalysisUnavailable("同牌效集合的非推进权重不一致")
            if perf_counter() - started > PROFILE["max_elapsed_seconds"]:
                raise TimeoutError("研究分析额度耗尽")
            values = {x["action_key"]: x["improvement_weighted_sum"] for x in row["qualities"]}
            # Python稳定排序让新增优先层相同时严格保留原V2顺序；不跨越其余动作。
            ordered = sorted(prefix, key=lambda c: -values[c.action_key])
            row["status"] = "EVALUATED"
            row["selected_first"] = ordered[0].action_key
            row["changed"] = row["selected_first"] != row["base_first"]
            candidates = []
            for index, candidate in enumerate(ordered + list(base.candidates[len(prefix):])):
                reasons = candidate.reasons
                if candidate.action_key in values:
                    reasons += ("离线后继改良优先层={0}枚²；原V2分数仅用于层内平分".format(values[candidate.action_key]),)
                candidates.append(replace(candidate, rank=index + 1, reasons=reasons))
            return replace(base, candidates=tuple(candidates))
        except (AnalysisUnavailable, TimeoutError) as error:
            row["status"] = "COST_FALLBACK" if isinstance(error, TimeoutError) else "FACT_FALLBACK"
            row["reason"] = str(error)
            return base
        except Exception as error:
            # 研究期间保留退路和可见错误；评审据此拒绝干净执行结论，不吞错宣称成功。
            row["status"] = "ERROR_FALLBACK"
            row["reason"] = type(error).__name__ + ": " + str(error)
            return base
        finally:
            row["elapsed_seconds"] = perf_counter() - started
