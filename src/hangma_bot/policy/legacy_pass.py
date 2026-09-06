"""冻结策略的过牌事实适配；不改变规则输出、历史记录或原评分源码。

新规则的可信响应过牌携带等待牌效，旧 V0 会误消费这些新增数值。
仅在旧策略 choose 的输入副本中恢复 NOT_APPLICABLE；失败事实原样保留。
装配入口必须使用这里的兼容类，直接导入冻结原类仅用于历史输入复现。
"""

from dataclasses import replace

from hangma_bot.hangma.interface import CandidateFactKind, CandidateFacts, RuleCompleteness
from hangma_bot.kernel.actions import Pass

from .claim_if_legal import ClaimIfLegalPolicy
from .interface import DecisionBudget, DecisionPlan, DecisionRequest
from .weighted_heuristic import WeightedHeuristicPolicy

LEGACY_PASS_VIEW = "legacy-pass-neutral-v1"


def _legacy_request(request: DecisionRequest) -> DecisionRequest:
    """只投影可信新增过牌事实；输入、合法动作、规则问题和信息权限均保持。"""
    changed = False
    candidates = []
    for candidate in request.rules.legal_candidates:
        facts = candidate.facts
        if (
            isinstance(candidate.action, Pass)
            and facts is not None
            and facts.fact_kind is CandidateFactKind.HAND_PROGRESS
            and facts.completeness is RuleCompleteness.COMPLETE
            and type(facts.shanten_after) is int and facts.shanten_after >= 0
            and facts.best_followup_discard is None
            and not facts.replacement_draw_unknown
        ):
            candidate = replace(candidate, facts=CandidateFacts(CandidateFactKind.NOT_APPLICABLE, None))
            changed = True
        candidates.append(candidate)
    if not changed:
        return request
    return replace(request, rules=replace(request.rules, legal_candidates=tuple(candidates)))


def _annotate(plan: DecisionPlan, changed: bool) -> DecisionPlan:
    """计划注明评分事实视图；审计请求仍保存真实的新规则事实。"""
    if not changed:
        return plan
    return replace(plan, degraded_reasons=plan.degraded_reasons + (
        f"评分兼容视图[{LEGACY_PASS_VIEW}]：可信过牌恢复旧中性基线；原始规则事实不改写",
    ))


class LegacyWeightedHeuristicPolicy(WeightedHeuristicPolicy):
    """V0 的显式输入适配；继承原构造器、权重与截止检查，不增加评分规则。"""

    async def choose(self, request: DecisionRequest, budget: DecisionBudget) -> DecisionPlan:
        """以旧过牌视图执行冻结算法，返回原排序并注明适配原因。"""
        view = _legacy_request(request)
        return _annotate(await super().choose(view, budget), view is not request)


class LegacyClaimIfLegalPolicy(ClaimIfLegalPolicy):
    """保持依赖 V0 的测试房鸣牌策略口径；不修改冻结 claim_if_legal 源码。"""

    async def choose(self, request: DecisionRequest, budget: DecisionBudget) -> DecisionPlan:
        """在原鸣牌排序前使用相同旧事实视图，原始请求保持不变。"""
        view = _legacy_request(request)
        return _annotate(await super().choose(view, budget), view is not request)
