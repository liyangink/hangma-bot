"""暗杠机会成本的窄范围消融；只消费当前规则提供的条件分值和七对听牌事实。"""

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
import math

from hangma_bot.hangma.interface import RuleCompleteness,ValueCoverage
from hangma_bot.kernel.actions import Discard,Gang,GangKind
from hangma_bot.policy.hu_upgrade import upgrade_risk_key
from hangma_bot.policy.hu_upgrade_calibration import RISK_CELLS,SAFETY_MARGIN
from hangma_bot.policy.interface import ScorePart
from upgrade_persistent import upgrade_policy


def direct_mass(candidate,seat,kind):
    """合计同一等待手形的互斥下一摸成胡质量；未知或非指定摸牌来源返回空。

质量单位为未见张数×本人条件胡牌净分，未成胡后的继续价值不在这里
计算；不能把本比较写成完整单局期望或暗杠一定有害。
"""
    facts=candidate.value_facts
    if facts is None or facts.coverage is not ValueCoverage.COMPLETE or facts.immediate_settlement is not None or not facts.routes:
        return None
    condition=facts.routes[0].conditions
    if condition.draw_kind!=kind:
        return None
    seen=set()
    mass=0.0
    count=0
    for route in facts.routes:
        if route.conditions!=condition or route.followup_discard is not None:
            return None
        value=route.conditional_settlement.score_delta[seat]
        if type(value) not in (int,float) or not math.isfinite(value) or value<=0:
            return None
        for tile in route.useful_tiles:
            if tile.code in seen or tile.remaining_estimate<=0:
                return None
            seen.add(tile.code)
            count+=tile.remaining_estimate
            mass+=tile.remaining_estimate*value
    return mass,count


class GangValueDelayPolicy:
    """仅在原计划选门清暗杠时考虑保留已听七对；其他动作完整沿用原等胡。"""
    def __init__(self):
        self.base=upgrade_policy()

    async def choose(self,request,budget):
        baseline=await self.base.choose(request,budget)
        obs=request.observation
        if (not baseline.candidates or request.rules.completeness is not RuleCompleteness.COMPLETE
            or obs.phase!='draw' or obs.melds[obs.seat] or obs.rule_state.catch_play
            or obs.rule_state.chain_count or obs.gang_draw
            or any(c.action_key=='hu' for c in request.rules.legal_candidates)):
            return baseline
        first=baseline.candidates[0]
        if not isinstance(first.action,Gang) or first.action.kind is not GangKind.CONCEALED:
            return baseline
        cell=next((c for c in RISK_CELLS if (c.wall_band,c.threat)==upgrade_risk_key(obs)),None)
        if cell is None:
            return baseline
        available={c.action_key:c for c in request.rules.legal_candidates}
        original=direct_mass(available[first.action_key],obs.seat,'replacement')
        if original is None:
            return baseline
        offers=[]
        for ranked in baseline.candidates:
            if not isinstance(ranked.action,Discard) or ranked.action.tile==first.action.tile:
                continue
            candidate=available[ranked.action_key]
            facts=candidate.facts
            if (facts is None or facts.completeness is not RuleCompleteness.COMPLETE
                or facts.seven_pairs_shanten_after!=0 or facts.shanten_after!=0):
                continue
            value=direct_mass(candidate,obs.seat,'normal')
            if value is None or value[1]<original[1]:
                continue
            quality=cell.survival_floor*value[0]
            if quality>original[0]*(1+SAFETY_MARGIN):
                offers.append((quality,value[1],ranked))
        if not offers:
            return baseline
        quality,outs,selected=min(offers,key=lambda item:(-item[0],-item[1],item[2].rank))
        parts=selected.score_parts+(ScorePart('缓杠-抵消基线总分',-sum(p.value for p in selected.score_parts)),
                                    ScorePart('缓杠-折扣后一次摸牌质量',quality))
        reason=(f'缓杠消融：保持七对听牌与自然四张；普通摸牌质量乘 {cell.survival_floor} 得 {quality:g}，'
                f'高于立即杠补 {original[0]:g} 的 1.1 倍，听牌未见数 {outs}≥{original[1]}；'
                '不同摸牌时序的模型近似，未估计两边未成胡后的剩余价值')
        chosen=replace(selected,score_parts=parts,total_score=sum(p.value for p in parts),reasons=selected.reasons+(reason,))
        items=[chosen]+[c for c in baseline.candidates if c.action_key!=selected.action_key]
        return replace(baseline,candidates=tuple(replace(c,rank=i+1) for i,c in enumerate(items)))
