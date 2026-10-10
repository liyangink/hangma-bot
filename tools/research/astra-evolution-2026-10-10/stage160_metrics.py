"""复用原160局驱动，附加已产生的规则牌效和条件胡牌形状审计。"""
from __future__ import annotations

from dataclasses import asdict
import stage160 as stage


def selected_metrics(request,plan):
    """只读当前公开请求已存在的规则事实；不增加规则查询或策略输入。"""
    candidate=next(x for x in request.rules.legal_candidates if x.action_key==plan.candidates[0].action_key)
    fact=candidate.facts;value=candidate.value_facts
    return {'drawn_tile':None if request.observation.drawn_tile is None else request.observation.drawn_tile.code,
        'selected_rule_facts':None if fact is None else asdict(fact),
        'selected_value_facts':None if value is None else asdict(value),
        'selected_total_score':plan.candidates[0].total_score,
        'selected_score_parts':[(p.name,p.value) for p in plan.candidates[0].score_parts]}


class MetricsAudit(stage.FocalAudit):
    """choose本身与原审计完全相同；额外序列化时间不混入策略动作耗时。"""
    async def choose(self,request,budget):
        plan=await super().choose(request,budget)
        self.rows[-1].update(selected_metrics(request,plan))
        return plan


_base_worker=stage.worker


def worker(task):
    """每个新spawn进程只替换本工具的审计包装，不修改生产策略或规则。"""
    stage.FocalAudit=MetricsAudit
    return _base_worker(task)


def main():
    stage.worker=worker
    stage.main()


if __name__=='__main__':main()
