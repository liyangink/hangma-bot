"""G246：仅接受 G237 备选中新弃幺九且严格扩宽的合法动作。"""

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

import g237_numeric_inversion_policy as base


POLICY_ID = "action_value_v1:research:g246-terminal-release-width-v1"


def terminal_numeric(key: str) -> bool:
    """弃 1／9 的数牌动作；牌码类别与 G242 特征定义相同。"""
    if not key.startswith("discard:"):
        return False
    code = key.split(":", 1)[1]
    return len(code) == 2 and code[0] in "19" and code[1] in "wbt"


def select(request, plan) -> tuple[str | None, dict]:
    """G237 负责全部生产规则与风险守卫，本层只识别动作类别。"""
    key, evidence = base.select(request, plan)
    if key is None:
        return None, evidence
    parent = evidence["parent_action"]
    if terminal_numeric(parent) or not terminal_numeric(key):
        return None, {**evidence, "reason": "terminal_release_family_rejected"}
    return key, {**evidence, "reason": "terminal_release_family_adopted"}


class TerminalReleasePolicy(base.NumericInversionPolicy):
    """父代始终提供保底；只重排已通过 G237 守卫的合法动作。"""

    policy_id = POLICY_ID

    async def choose(self, request, budget):
        """任何异常均返回冻结 R18 原计划，不改变提交动作的副作用边界。"""
        plan = await self.baseline.choose(request, budget)
        started = time.perf_counter()
        try:
            key, evidence = select(request, plan)
        except Exception as exc:
            key = None
            evidence = {"reason": "selector_exception", "error_type": type(exc).__name__}
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        if key is None:
            if evidence["reason"] in ("terminal_release_family_rejected", "selector_exception"):
                self.metrics.append({
                    "decision_id": request.decision_id,
                    "status": "filtered" if evidence["reason"]
                              == "terminal_release_family_rejected" else "fallback",
                    **evidence, "elapsed_ms": round(elapsed_ms, 3)})
            return plan
        selected = next((item for item in plan.candidates
                         if item.action_key == key), None)
        if selected is None:
            self.metrics.append({"decision_id": request.decision_id,
                                 "status": "fallback", "reason": "selected_not_in_plan"})
            return plan
        ordered = (selected,) + tuple(item for item in plan.candidates
                                     if item.action_key != key)
        ranked = tuple(replace(item, rank=index + 1,
                               reasons=item.reasons + (("G246 弃幺九保宽面",)
                                                       if index == 0 else ()))
                       for index, item in enumerate(ordered))
        self.metrics.append({"decision_id": request.decision_id,
                             "status": "adopted", **evidence,
                             "elapsed_ms": round(elapsed_ms, 3)})
        return replace(plan, candidates=ranked)


research_parent_factory = base.research_parent_factory


def policy_factory(metrics: list[dict]):
    """每张完整桌单独装配候选与指标接收器。"""
    def build(monotonic):
        return TerminalReleasePolicy(research_parent_factory(monotonic), metrics)
    return build
