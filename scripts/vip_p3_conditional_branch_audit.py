"""同事件动作差的规则后继分支辨识审计；不读取未来作为模型输入。

教师首次事件牌码只用于赛后分层；每个后继摘要均由动作前
PlayerObservation 和同次 HangmaRules 路线前沿算出。摘要不同
不等于可以预测收益方向，只证明静态动作后态遗漏了可用信息。
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import RuleCompleteness, ValueAnalysisLimits
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.serialization import observation_from_json

from scripts.vip_p3_multi_opportunity_analysis import _load, analyze


_LIMITS = ValueAnalysisLimits(max_expansions=8192)


def _branch_signature(edge) -> tuple:
    """两种抓打条件各取可见的最优向听/进张与前沿大小。"""

    def envelope(item) -> tuple:
        if not item.discard_frontier:
            best = None
        else:
            best = min((leaf.shanten_after, -leaf.support_remaining)
                       for leaf in item.discard_frontier)
        return (item.hu_available, best, len(item.discard_frontier))

    return (envelope(edge.successor.restricted),
            envelope(edge.successor.unrestricted))


def audit(selection: dict, frozen: dict, report: dict,
          freeze_path: Path) -> dict:
    """只比较事前锁定且实际改选的首动作，并保留相关世界配对。"""

    analyze(report, frozen, freeze_path)  # 先重核完整动作世界与四座结算
    if (selection.get("scope") !=
            "pre_outcome_r18_natural_two_white_and_highfan_roots_not_strategy_result"
            or selection.get("scenario_prefix") != frozen.get("scenario_prefix")
            or selection.get("model_sha256") != frozen.get("model_sha256")):
        raise ValueError("同事件审计的结果盲选根身份不符")
    chosen = {item["root_id"]: item for item in selection["selected_roots"]}
    if len(chosen) != len(frozen["roots"]):
        raise ValueError("同事件审计选根数量不守恒")
    outcomes = {}
    for item in report["rows"]:
        key = (item["root_id"], item["sample"], item["first_action_key"],
               item["continuation_reference"])
        if key in outcomes:
            raise ValueError("同事件审计动作世界重复")
        outcomes[key] = item
    rules = HangmaRules(RuleConfig("hangma-mvp-v10-public-counts", 1, False))
    totals = {ref: Counter() for ref in frozen["continuation_references"]}
    per_root = []
    changed_roots = 0
    for root in frozen["roots"]:
        model = root["roles"]["anchored"]
        baseline = root["roles"]["r18"]
        if model is None or model == baseline:
            continue
        changed_roots += 1
        source = chosen[root["root_id"]]
        observation = observation_from_json(source["observation"])
        if hashlib.sha256(repr(observation).encode()).hexdigest() != root["root_id"]:
            raise ValueError("规则后继根玩家观察摘要不符")
        analysis = rules.analyze(observation, value_limits=_LIMITS, route_limits=_LIMITS)
        frontier = analysis.route_frontier
        if (analysis.completeness is not RuleCompleteness.COMPLETE
                or frontier is None or not frontier.complete):
            raise ValueError("改选根的 P1 条件后继前沿不完整")
        edges = {item.action_key: {edge.draw_code: edge for edge in item.draw_edges}
                 for item in frontier.roots}
        root_counts = {}
        for reference in frozen["continuation_references"]:
            counts = Counter()
            for sample in range(root["worlds_per_root"]):
                left = outcomes[(root["root_id"], sample, model, reference)]
                right = outcomes[(root["root_id"], sample, baseline, reference)]
                counts["paired_worlds"] += 1
                same_event = left["first_event_key"] == right["first_event_key"]
                same_offer = (left["first_event_immediate_hu"] ==
                              right["first_event_immediate_hu"])
                same_net = (left["terminal"]["score_delta"][observation.seat] ==
                            right["terminal"]["score_delta"][observation.seat])
                counts["same_first_event_key"] += same_event
                counts["same_direct_hu_offer"] += same_offer
                counts["different_terminal_net"] += not same_net
                if not same_event or same_net:
                    continue
                counts["same_event_different_terminal_net"] += 1
                if same_offer:
                    counts["same_event_same_offer_different_terminal_net"] += 1
                if (left["first_event_kind"] != "self_normal_draw"
                        or right["first_event_kind"] != "self_normal_draw"):
                    counts["same_event_non_normal_draw_terminal_difference"] += 1
                    continue
                kind, draw_code = left["first_event_key"].split(":", 1)
                if kind != "self_normal_draw":
                    raise ValueError("本人普通摸牌事件键与类别冲突")
                left_edge = edges[model].get(draw_code)
                right_edge = edges[baseline].get(draw_code)
                if left_edge is None or right_edge is None:
                    raise ValueError("实际下一摸牌缺行动前条件边")
                counts["same_normal_draw_different_terminal_net"] += 1
                if _branch_signature(left_edge) == _branch_signature(right_edge):
                    counts["same_projected_branch_signature"] += 1
                else:
                    counts["different_projected_branch_signature"] += 1
            totals[reference].update(counts)
            root_counts[reference] = dict(sorted(counts.items()))
        per_root.append({"seed": root["seed"], "root_id": root["root_id"],
                         "model_action": model, "r18_action": baseline,
                         "worlds_per_root": root["worlds_per_root"],
                         "references": root_counts})
    if changed_roots != 13:
        raise ValueError("预冻结改选观察根数不守恒")
    return {
        "scope": "opened_same_first_event_branch_discrimination_not_predictive_value",
        "pre_outcome_freeze_commit": report["pre_outcome_freeze_commit"],
        "changed_root_count": changed_roots,
        "totals": {ref: dict(sorted(counts.items())) for ref, counts in totals.items()},
        "roots": per_root,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--teacher", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(_load(args.selection), _load(args.freeze),
                           _load(args.teacher), args.freeze),
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
