"""离线多父代交叉：按动作窗口组合后继质量与条件路线专长。"""
from __future__ import annotations

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

from time import perf_counter

from followup_quality_policy import FollowupQualityPolicy
from hangma_bot.policy.action_value_policy import ActionValuePolicy
from hangma_bot.policy.action_value_seeds import ActionValueScorer
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2


MODES = {
    "v2",
    "followup_discard",
    "route_all",
    "route_draw_only",
    "route_claim_only",
    "cross_followup_claim",
}
CLAIM_PHASES = {"response_chi", "response_peng"}


class CrossSpecialistPolicy:
    """按可见动作窗口选择冻结父代；每个父代仍保留自身完整失败退路。"""

    def __init__(self, rule_config, monotonic, *, mode: str,
                 route_source: str, identity: str, value_limits=None) -> None:
        """绑定冻结父代源码和模式；不在动作闭环读取文件、网络或模型。"""
        if mode not in MODES:
            raise ValueError("未知多父代交叉模式：" + mode)
        self.mode = mode
        self.baseline = ComparableHeuristicPolicyV2(monotonic=monotonic)
        self.followup = FollowupQualityPolicy(rule_config, monotonic)
        self.route = ActionValuePolicy(
            ActionValueScorer("cross-route-parent:" + identity, route_source),
            value_limits=value_limits,
        )
        self.policy_id = "offline-cross-specialist-v1:" + mode + ":" + identity
        self.audit: list[dict] = []

    @staticmethod
    def first_key(plan):
        """读取计划第一候选；空计划显式返回 None。"""
        return plan.candidates[0].action_key if plan.candidates else None

    def component_for(self, phase: str) -> str:
        """只用当前公开动作阶段决定父代，不读取对手池、种子或终局标签。"""
        if self.mode == "followup_discard":
            return "followup" if phase == "draw" else "v2"
        if self.mode == "route_all":
            return "route"
        if self.mode == "route_draw_only":
            return "route" if phase == "draw" else "v2"
        if self.mode == "route_claim_only":
            return "route" if phase in CLAIM_PHASES else "v2"
        if self.mode == "cross_followup_claim":
            if phase == "draw":
                return "followup"
            return "route" if phase in CLAIM_PHASES else "v2"
        return "v2"

    async def choose(self, request, budget):
        """先生成 V2 保底，再执行冻结窗口对应父代并记录逐决策身份。"""
        started = perf_counter()
        base = await self.baseline.choose(request, budget)
        component = self.component_for(request.observation.phase)
        if component == "followup":
            selected = await self.followup.choose(request, budget)
            row = dict(self.followup.audit[-1])
            row["component"] = "followup_discard"
            row["mode"] = self.mode
            row["wrapper_elapsed_seconds"] = perf_counter() - started
            self.audit.append(row)
            return selected
        if component == "route":
            selected = await self.route.choose(request, budget)
            base_first = self.first_key(base)
            selected_first = self.first_key(selected)
            degraded = any(
                str(reason).startswith("action_value_failed:")
                for reason in selected.degraded_reasons
            )
            row = {
                "decision_id": request.decision_id,
                "trigger_seq": request.trigger_seq,
                "status": "ERROR_FALLBACK" if degraded else "EVALUATED",
                "rule_calls": 0,
                "elapsed_seconds": perf_counter() - started,
                "base_first": base_first,
                "selected_first": base_first if degraded else selected_first,
                "changed": False if degraded else selected_first != base_first,
                "component": "route_claim" if request.observation.phase in CLAIM_PHASES else "route_draw",
                "mode": self.mode,
            }
            if degraded:
                row["reason"] = ";".join(selected.degraded_reasons)
            self.audit.append(row)
            return base if degraded else selected
        self.audit.append({
            "decision_id": request.decision_id,
            "trigger_seq": request.trigger_seq,
            "status": "NOT_APPLICABLE",
            "rule_calls": 0,
            "elapsed_seconds": perf_counter() - started,
            "base_first": self.first_key(base),
            "selected_first": self.first_key(base),
            "changed": False,
            "component": "v2",
            "mode": self.mode,
        })
        return base
