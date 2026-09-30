"""已开结果根的宽进张面对照；只作开发诊断，不作新算法确认。"""

from __future__ import annotations

import argparse
import gzip
import json
from collections import Counter
from pathlib import Path

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.serialization import observation_from_json

from scripts.vip_p3_afterstate_contract import AfterstateStatus, project_afterstate


def _read(path: Path) -> dict:
    """只读已冻结的压缩 JSON，不改写教师结局。"""

    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def _net(row: dict, key: str, seat: int) -> float:
    """同一观察根内、相关隐藏世界等权的本人单局净积分。"""

    samples = row["outcomes_by_action"][key]
    if [sample["sample"] for sample in samples] != list(range(row["sample_count"])):
        raise ValueError("教师相关世界编号不守恒")
    return sum(sample["terminal"]["score_delta"][seat] for sample in samples) / len(samples)


def diagnose(scan: dict, shape: dict, r18: dict) -> dict:
    """每根只留一对同资格弃牌；选对不看教师结局。"""

    if (scan.get("scope") != "pre_outcome_all_action_root_scan_not_strategy_value"
            or shape.get("continuation_reference") != "shape"
            or r18.get("continuation_reference") != "r18_frozen"
            or scan.get("root_count") != len(scan.get("rows", ()))
            or any(report.get("rule_config") != scan.get("rule_config")
                   or report.get("start_seed") != scan.get("start_seed")
                   or report.get("requested_seeds") != scan.get("requested_seeds")
                   for report in (shape, r18))):
        raise ValueError("宽面诊断来源不符")
    teachers = {name: {row["root_id"]: row for row in report["rows"]}
                for name, report in (("shape", shape), ("r18_frozen", r18))}
    roots = {row["root_id"] for row in scan["rows"]}
    if any(set(rows) != roots for rows in teachers.values()):
        raise ValueError("宽面诊断的观察根不守恒")
    rules = HangmaRules(RuleConfig("hangma-mvp-v10-public-counts", 1, False))
    rows = []
    for source in scan["rows"]:
        observation = observation_from_json(source["observation"])
        if observation.phase != "draw":
            continue
        analysis = rules.analyze(
            observation, route_limits=ValueAnalysisLimits(max_expansions=8192))
        if [candidate.action_key for candidate in analysis.legal_candidates] != source["legal_action_keys"]:
            raise ValueError("行动前合法动作与冻结扫描不同")
        discards = []
        for candidate, root in zip(analysis.legal_candidates, analysis.conditional_roots):
            if not candidate.action_key.startswith("discard:") or candidate.action_key == "discard:白":
                continue
            facts = project_afterstate(candidate, root, observation.seat)
            if facts.status is not AfterstateStatus.EFFECTIVE_PENDING_EVENT:
                raise ValueError("弃牌没有已生效条件后态")
            hand = facts.own_shape
            if hand.useful_unseen_capacity is not None:
                discards.append((candidate.action_key, hand))
        pairs = []
        for high_key, high in discards:
            for low_key, low in discards:
                if high_key == low_key:
                    continue
                # 当前白板实持、两型向听与爆头/链资格一致；只隔离进张
                # 牌码宽度和最多两张公开未见容量损失。不是随机实验。
                identity_high = (high.standard_shanten, high.seven_pairs_shanten,
                                 high.whites_held, high.baotou, high.chain_count,
                                 high.chain_piao)
                identity_low = (low.standard_shanten, low.seven_pairs_shanten,
                                low.whites_held, low.baotou, low.chain_count,
                                low.chain_piao)
                width = high.useful_positive_code_count - low.useful_positive_code_count
                capacity = high.useful_unseen_capacity - low.useful_unseen_capacity
                if identity_high == identity_low and width > 0 and -2 <= capacity <= 0:
                    pairs.append((-width, -capacity, high_key, low_key, width, capacity))
        if not pairs:
            continue
        _, _, high_key, low_key, width, capacity = min(pairs)
        outcome = {}
        for name, teacher in teachers.items():
            row = teacher[source["root_id"]]
            if (row["observation"] != source["observation"]
                    or row["legal_action_keys"] != source["legal_action_keys"]):
                raise ValueError("教师根与行动前扫描不同")
            outcome[name] = _net(row, high_key, observation.seat) - _net(
                row, low_key, observation.seat)
        rows.append({"seed": source["seed"], "root_id": source["root_id"],
                     "wider_action": high_key, "narrower_action": low_key,
                     "positive_code_difference": width,
                     "unseen_capacity_difference": capacity,
                     "paired_net_wider_minus_narrower": outcome})
    totals = {}
    for name in teachers:
        values = [row["paired_net_wider_minus_narrower"][name] for row in rows]
        signs = Counter("positive" if value > 0 else "negative" if value < 0 else "zero"
                        for value in values)
        totals[name] = {"mean_net_per_root": sum(values) / len(values) if values else None,
                        "root_signs": {sign: signs[sign] for sign in
                                       ("positive", "negative", "zero")}}
    return {"scope": "opened_outcome_width_diagnostic_not_policy_or_confirmatory_test",
            "root_count": len(rows), "summary": totals, "rows": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan", type=Path, required=True)
    parser.add_argument("--shape", type=Path, required=True)
    parser.add_argument("--r18", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(diagnose(_read(args.scan), _read(args.shape), _read(args.r18)),
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
