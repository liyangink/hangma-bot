"""明确拒绝后的合法备用选择；不修改规则候选、规则紧急身份或动作合法性。"""

from hangma_bot.hangma.interface import RuleCandidate
from hangma_bot.policy.interface import DecisionRequest


def rejected_emergency_backup(request: DecisionRequest) -> RuleCandidate | None:
    """只在规则紧急候选已明确拒绝时，准备同次规则合法集中未拒的备用动作。

    输入仅含玩家可见请求；无副作用、无额外分析。按 action_key 固定选取，
    排名包装必须标记 is_emergency=False，不能冒称规则模块另给了紧急动作。
    规则原本没有紧急候选、原紧急候选未拒或全部合法动作已拒时返回 None。
    """
    emergency = request.rules.emergency_candidate
    rejected = frozenset(item.action_key for item in request.rejected_attempts)
    if emergency is None or emergency.action_key not in rejected:
        return None
    return next((candidate for candidate in sorted(request.rules.legal_candidates,
        key=lambda item: item.action_key) if candidate.action_key not in rejected), None)
