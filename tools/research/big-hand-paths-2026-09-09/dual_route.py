"""七对距离相同时，先保留普通型距离再比较七对活进张；离线研究候选。"""

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
from hangma_bot.kernel.actions import Discard,Pass,action_key
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2
from progress_guard import ProgressGuardCombinedPolicy


class DualRouteCombinedPolicy:
    """在上一版速度约束之上，仅改变七对同距离候选的第二排序项。

    原第二项为七对活进张数；本版先选择普通型更近的候选，再沿用原项。
    仍不声称进张集合或长期净分支配；相同距离的进张代价交给续打与桌赛
    检验。内部选择范围副本不修改原始规则事实、合法动作或公开审计请求。
    """
    def __init__(self):
        self.base=ComparableHeuristicPolicyV2(monotonic=lambda:0)
        self.guarded=ProgressGuardCombinedPolicy()

    async def choose(self,request,budget):
        """保持当前胡/爆头等待；仅对已有七对增强可参与的候选限定普通型距离。"""
        obs=request.observation
        if (obs.rule_state.baotou or any(c.action_key=='hu' for c in request.rules.legal_candidates)
                or obs.melds[obs.seat] or obs.rule_state.catch_play or obs.rule_state.chain_count
                or obs.gang_draw or obs.remaining_tile_count is None):
            return await self.guarded.choose(request,budget)
        base=await self.base.choose(request,budget);available={}
        for c in request.rules.legal_candidates:
            try:
                if c.action_key==action_key(c.action):available.setdefault(c.action_key,c)
            except TypeError:continue
        waiting={}
        for ranked in base.candidates:
            c=available.get(ranked.action_key);f=None if c is None else c.facts
            if (f is not None and f.fact_kind is CandidateFactKind.HAND_PROGRESS
                    and f.completeness is RuleCompleteness.COMPLETE and not f.replacement_draw_unknown
                    and f.shanten_after is not None and f.shanten_after>=0):waiting[ranked.action_key]=c
        if not waiting:return base
        floor=min(c.facts.shanten_after for c in waiting.values());eligible={}
        for key,c in waiting.items():
            f=c.facts;q=f.seven_pairs_shanten_after
            if (not isinstance(c.action,(Discard,Pass)) or f.shanten_after!=floor
                    or q is None or not 0<=q<=min(3,floor+1)
                    or f.seven_pairs_useful_tiles is None
                    or not any(t.remaining_estimate>0 for t in f.seven_pairs_useful_tiles)
                    or obs.remaining_tile_count-20<8*(q+1)):
                continue
            if isinstance(c.action,Discard) and c.action.tile==obs.rule_state.wealth_god:continue
            if f.standard_shanten_after is None:return await self.guarded.choose(request,budget)
            eligible[key]=f
        nearest={}
        for f in eligible.values():
            q=f.seven_pairs_shanten_after
            nearest[q]=min(nearest.get(q,f.standard_shanten_after),f.standard_shanten_after)
        excluded={key for key,f in eligible.items() if f.standard_shanten_after>nearest[f.seven_pairs_shanten_after]}
        scoped=replace(request,rules=replace(request.rules,legal_candidates=tuple(
            replace(c,facts=replace(c.facts,seven_pairs_useful_tiles=None))
            if c.action_key in excluded and c.facts is not None else c
            for c in request.rules.legal_candidates)))
        plan=await self.guarded.choose(scoped,budget)
        if plan.candidates and any(p.name=='七对持续续打消融' for p in plan.candidates[0].score_parts):
            chosen=plan.candidates[0]
            f=available[chosen.action_key].facts
            assert f.standard_shanten_after==nearest[f.seven_pairs_shanten_after]
            chosen=replace(chosen,reasons=chosen.reasons+('研究单项排序：七对同距离时先保留较近普通型，再比较七对活进张。',))
            return replace(plan,candidates=(chosen,)+plan.candidates[1:])
        return plan
