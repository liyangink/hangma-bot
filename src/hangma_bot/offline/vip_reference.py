"""VIP 离线配对实验的冻结基础续打者；不参与线上策略闭环。"""

from __future__ import annotations

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.kernel.actions import Discard, Hu, Pass


def choose_reference_action(rules: HangmaRules, decision, *, mode: str):
    """只消费依法可见观察与同源合法牌效，不读取完整模拟世界。"""

    candidates = rules.analyze(decision.observation).legal_candidates
    if decision.observation.phase.startswith("response_"):
        return Pass()
    win = next((item.action for item in candidates if isinstance(item.action, Hu)), None)
    if win is not None:
        return win
    discards = [item for item in candidates if isinstance(item.action, Discard)]
    if mode == "first_discard":
        return discards[0].action
    if mode != "shape":
        raise ValueError("未知参考续打者")

    def shape_key(item):
        facts = item.facts
        if facts is None or facts.shanten_after is None:
            raise ValueError("基础牌效参考者缺规则模块动作后牌效")
        return (facts.shanten_after,
                -sum(tile.remaining_estimate for tile in facts.useful_tiles),
                item.action_key)

    return min(discards, key=shape_key).action
