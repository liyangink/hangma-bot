"""对持续七对偏好增加实际向听不退步约束；仍是离线消融候选。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/big-hand-paths-2026-09-09'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from dataclasses import replace

from hangma_bot.hangma.interface import CandidateFactKind,RuleCompleteness
from hangma_bot.kernel.actions import action_key
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2
from persistent_seven import PersistentSevenPolicy
from upgrade_persistent import upgrade_policy


class ProgressGuardCombinedPolicy:
    """只屏蔽会增加最优向听的七对偏好，保留原等胡、墙余、距离与进张排序。

    通过内部输入副本使不合格候选不参加既有七对增强；不删除合法动作，
    不修改原请求/审计事实、V2综合事实或任何条件结算。这个副本是策略
    选择范围，并非将已知进张宣称为规则未知。现阶段不承诺期望净分提高。
    """
    def __init__(self):
        self.base=ComparableHeuristicPolicyV2(monotonic=lambda:0)
        self.persistent=PersistentSevenPolicy(monotonic=lambda:0)
        self.upgrade=upgrade_policy()

    async def choose(self,request,budget):
        """从已过滤V2候选确定可比最优向听，再限制七对增强的参与范围。"""
        if request.observation.rule_state.baotou or any(c.action_key=='hu' for c in request.rules.legal_candidates):
            return await self.upgrade.choose(request,budget)
        base=await self.base.choose(request,budget)
        available={}
        for c in request.rules.legal_candidates:
            try:
                if c.action_key==action_key(c.action):available.setdefault(c.action_key,c.facts)
            except TypeError:continue
        waiting={}
        for ranked in base.candidates:
            f=available.get(ranked.action_key)
            if (f is not None and f.fact_kind is CandidateFactKind.HAND_PROGRESS
                    and f.completeness is RuleCompleteness.COMPLETE and not f.replacement_draw_unknown
                    and f.shanten_after is not None and f.shanten_after>=0):
                waiting[ranked.action_key]=f
        if not waiting:return base
        floor=min(f.shanten_after for f in waiting.values())
        excluded={key for key,f in waiting.items() if f.shanten_after>floor}
        scoped=replace(request,rules=replace(request.rules,legal_candidates=tuple(
            replace(c,facts=replace(c.facts,seven_pairs_useful_tiles=None))
            if c.action_key in excluded and c.facts is not None else c
            for c in request.rules.legal_candidates)))
        plan=await self.persistent.choose(scoped,budget)
        if plan.candidates and any(p.name=='七对持续续打消融' for p in plan.candidates[0].score_parts):
            chosen=plan.candidates[0]
            assert available[chosen.action_key].shanten_after==floor
            chosen=replace(chosen,reasons=chosen.reasons+(f'研究单项约束：保七对后综合向听不超过当前可比最优值{floor}。',))
            return replace(plan,candidates=(chosen,)+plan.candidates[1:])
        return plan
