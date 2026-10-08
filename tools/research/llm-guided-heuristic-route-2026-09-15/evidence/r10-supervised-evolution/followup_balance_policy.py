"""后继改良组合提案的离线包装：受信规则分析不变，只接收已审查的有界纯排序器。"""

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
import json
from dataclasses import replace
from time import perf_counter

from followup_quality_policy import FollowupQualityPolicy


class BalancedFollowupPolicy:
    """先执行已冻结规则分析，再以只读数值行调用独立排序函数；原V2始终作为退路。"""

    def __init__(self, rule_config, monotonic, ranker, ranking_identity, *, enabled=True):
        """注入经监督者审查的纯函数与摘要；不在策略内读取模型源码或文件。"""
        self.inner = FollowupQualityPolicy(rule_config, monotonic, enabled=enabled)
        self.ranker = ranker
        self.policy_id = "offline-followup-balance-v1:" + ranking_identity
        self.audit = []

    async def choose(self, request, budget):
        """只重排原分析器实际覆盖的同牌效前缀，坏输出整次回退V2并显式记错。"""
        proposal = await self.inner.choose(request, budget)
        row = dict(self.inner.audit[-1])
        row["parent_selected_first"] = row["selected_first"]
        row["parent_changed"] = row["changed"]
        row["ranking_elapsed_seconds"] = 0.0
        self.audit.append(row)
        if row["status"] != "EVALUATED":
            return proposal
        baseline = await self.inner.baseline.choose(request, budget)
        row["selected_first"] = row["base_first"]
        row["changed"] = False
        started = perf_counter()
        try:
            by_key = {c.action_key: c for c in baseline.candidates}
            qualities = row["qualities"]
            keys = [q["action_key"] for q in qualities]
            assert 2 <= len(keys) <= 14 and len(set(keys)) == len(keys)
            assert keys == [c.action_key for c in baseline.candidates[:len(keys)]]
            assert len({q["nonprogress_weight"] for q in qualities}) == 1
            first = next(c for c in request.rules.legal_candidates if c.action_key == keys[0])
            context = {"direct_shanten": first.facts.shanten_after,
                "direct_support": sum(t.remaining_estimate for t in first.facts.useful_tiles),
                "nonprogress_weight": qualities[0]["nonprogress_weight"]}
            rows = [{"action_key": q["action_key"], "v2_total": by_key[q["action_key"]].total_score,
                "score_parts": {p.name: p.value for p in by_key[q["action_key"]].score_parts},
                "improvement_weighted_sum": q["improvement_weighted_sum"]} for q in qualities]
            before = json.dumps([rows, context], sort_keys=True, ensure_ascii=False, allow_nan=False)
            order = self.ranker(rows, context)
            if (not isinstance(order, list) or len(order) != len(keys)
                    or any(type(k) is not str for k in order) or sorted(order) != sorted(keys)):
                raise ValueError("排序输出必须恰好包含每个已分析动作一次")
            if json.dumps([rows, context], sort_keys=True, ensure_ascii=False, allow_nan=False) != before:
                raise ValueError("排序器修改了只读输入")
            row["ranking_context"] = context
            row["ranking_rows"] = rows
            row["ranking_order"] = order
            row["selected_first"] = order[0]
            row["changed"] = order[0] != row["base_first"]
            candidates = []
            for index, item in enumerate([by_key[k] for k in order] + list(baseline.candidates[len(keys):])):
                reasons = item.reasons
                if item.action_key in keys:
                    reasons += ("离线后继组合排序；原V2总分保留为解释，最终顺序见rank及独立排序审计",)
                candidates.append(replace(item, rank=index + 1, reasons=reasons))
            return replace(baseline, candidates=tuple(candidates))
        except Exception as error:
            row["status"] = "ERROR_FALLBACK"
            row["reason"] = "ranker:" + type(error).__name__ + ": " + str(error)
            row["selected_first"] = row["base_first"]
            row["changed"] = False
            return baseline
        finally:
            row["ranking_elapsed_seconds"] = perf_counter() - started
