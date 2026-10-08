"""已听牌组的有限等待分值消融；研究专用，不新增线上策略枚举。

本模型假定维持等待手形、未见牌交换同分布、每次本人摸牌间隔有固定
存活折扣。折扣借用已有等胡分组系数做敏感性实验，不是为长期等待校准
过的概率；输出是模型内胡牌进分，不是整单局净分或严格风险下界。
"""

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

from hangma_bot.hangma.interface import RuleCompleteness, ValueCoverage
from hangma_bot.kernel.actions import Gang, Hu, action_key
from hangma_bot.policy.hu_upgrade import upgrade_risk_key
from hangma_bot.policy.hu_upgrade_calibration import RISK_CELLS
from hangma_bot.policy.interface import ScorePart
from hangma_bot.policy.value_one_draw import OneDrawValuePolicy, _normal_ready
from upgrade_persistent import upgrade_policy


def hit_weight(unseen, outs, draws, survival):
    """无放回抽样中首次命中于第 k 次的质量乘 survival**k，再有限求和。

unseen 包含牌墙与其他座位暗牌的未知物理张数；draws 为正常四家依次
摸牌下的本人次数近似，未建模吃碰杠改变摸牌节奏，也不输入实际暗牌。
"""
    if not (0 <= outs <= unseen and 0 <= draws <= unseen and 0 <= survival <= 1):
        raise ValueError('有限等待输入越界')
    miss=1.0
    value=0.0
    for index in range(draws):
        hit=outs/(unseen-index)
        # 若之前已必命中，不能继续产生虚假的负未命中质量。
        if miss==0:
            break
        value+=miss*hit*survival**(index+1)
        miss*=1-hit
    return value


class FiniteWaitingPolicy:
    """保留现有等胡；仅重排零链且已经听牌的可比组，不跨越杠动作位置。"""
    def __init__(self):
        self.base=upgrade_policy()
        self.validator=OneDrawValuePolicy(monotonic=lambda:0)

    async def choose(self,request,budget):
        baseline=await self.base.choose(request,budget)
        obs=request.observation
        if (not baseline.candidates or isinstance(baseline.candidates[0].action,Hu)
            or obs.rule_state.baotou or obs.rule_state.catch_play or obs.rule_state.chain_count
            or obs.gang_draw or request.rules.completeness is not RuleCompleteness.COMPLETE):
            return baseline
        cell=next((c for c in RISK_CELLS if (c.wall_band,c.threat)==upgrade_risk_key(obs)),None)
        if cell is None or obs.remaining_tile_count is None or any(type(n) is not int or n<0 for n in obs.hand_counts):
            return baseline
        unseen=obs.remaining_tile_count+sum(n for seat,n in enumerate(obs.hand_counts) if seat!=obs.seat)
        draws=(obs.remaining_tile_count-20)//4
        if unseen<=0 or not 1<=draws<=unseen:
            return baseline
        available={}
        for candidate in request.rules.legal_candidates:
            if action_key(candidate.action)==candidate.action_key:
                available.setdefault(candidate.action_key,candidate)
        first=available.get(baseline.candidates[0].action_key)
        if first is None or not _normal_ready(first):
            return baseline
        values={}
        for item in baseline.candidates:
            candidate=available.get(item.action_key)
            if candidate is None:
                return baseline
            if not _normal_ready(candidate):
                continue
            facts=candidate.value_facts
            if facts is None or facts.coverage is not ValueCoverage.COMPLETE:
                return baseline
            if any(r.conditions.chain_count for r in facts.routes):
                return baseline
            # 先让生产一次摸牌消费者校验完整组的互斥牌、等待手形和事实语义。
            validated=await self.validator._waiting_value(candidate,obs.seat,budget)
            if validated is None:
                return baseline
            groups={r.followup_discard for r in facts.routes}
            group_values=[]
            for followup in groups:
                view=replace(candidate,value_facts=replace(facts,routes=tuple(r for r in facts.routes if r.followup_discard==followup)))
                value=await self.validator._waiting_value(view,obs.seat,budget)
                if value is None or not value.unseen_count:
                    continue
                weight=hit_weight(unseen,value.unseen_count,draws,cell.survival_floor)
                group_values.append((value.score_mass/value.unseen_count*weight,value.unseen_count,followup))
            values[item.action_key]=min(group_values,key=lambda v:(-v[0],-v[1],v[2] or '')) if group_values else (0.0,0,None)
        if len(values)<2:
            return baseline
        result=list(baseline.candidates)
        start=0
        for end in [i for i,item in enumerate(result) if isinstance(item.action,Gang)]+[len(result)]:
            positions=[i for i in range(start,end) if result[i].action_key in values]
            ordered=sorted((result[i] for i in positions),key=lambda item:(-values[item.action_key][0],-values[item.action_key][1],item.action_key))
            for index,item in zip(positions,ordered):
                value,outs,followup=values[item.action_key]
                parts=item.score_parts+(ScorePart('有限等待-抵消基线总分',-sum(p.value for p in item.score_parts)),
                                        ScorePart('有限等待-模型胡牌进分',value))
                reason=(f'有限等待消融：未知牌 {unseen} 张，听牌 {outs} 张，约 {draws} 次本人摸牌，'
                        f'每次折扣 {cell.survival_floor}；模型进分 {value:.4f}，后续弃牌 {followup}；'
                        '固定等待与独立存活近似，非完整净分或校准风险保证')
                result[index]=replace(item,score_parts=parts,total_score=sum(p.value for p in parts),
                                      reasons=item.reasons+(reason,))
            start=end+1
        return replace(baseline,candidates=tuple(replace(item,rank=i+1) for i,item in enumerate(result)))
