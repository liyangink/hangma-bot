"""新根结局打开前锁定互斥终局探针的全部合法动作分数与首选。"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import RuleCompleteness, ValueAnalysisLimits
from hangma_bot.kernel.actions import Hu
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.serialization import observation_from_json

from scripts.vip_p3_competing_value_probe import expected_net
from scripts.vip_p3_value_fit_probe import _FEATURE_NAMES, _features


def predict(scan: dict, model: dict) -> dict:
    """只消费事前行动前观察和冻结系数，逐根输出可复算的合法首选。"""

    if (scan.get("scope") != "pre_outcome_all_action_root_scan_not_strategy_value"
            or scan.get("selection_method") != "first_per_tag_under_shape_per_seed"
            or scan.get("rule_config") != model.get("rule_config")
            or model.get("schema") != "vip-p3-competing-terminal-probe/1"
            or tuple(model.get("feature_names", ())) != _FEATURE_NAMES):
        raise ValueError("全动作扫描与冻结竞争终局模型口径不匹配")
    source_hash = hashlib.sha256((Path(__file__).resolve().parent /
        "vip_p3_value_fit_probe.py").read_bytes()).hexdigest()
    if source_hash != model.get("feature_source_sha256"):
        raise ValueError("竞争终局模型使用的行动前特征源码摘要漂移")
    for source in model["training_sources"]:
        path = Path(source["path"])
        if hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
            raise ValueError("竞争终局模型的训练教师来源摘要漂移")
    rules = HangmaRules(RuleConfig("hangma-mvp-v10-public-counts", 1, False))
    limits = ValueAnalysisLimits(max_expansions=8192)
    rows = []
    for row in scan["rows"]:
        observation = observation_from_json(row["observation"])
        root_id = hashlib.sha256(repr(observation).encode()).hexdigest()
        if root_id != row["root_id"]:
            raise ValueError("全动作扫描的玩家观察摘要不一致")
        analysis = rules.analyze(observation, value_limits=limits)
        keys = [candidate.action_key for candidate in analysis.legal_candidates]
        if (analysis.completeness is not RuleCompleteness.COMPLETE
                or keys != row["legal_action_keys"]
                or row["shape_first_action_key"] not in keys):
            raise ValueError("行动前规则合法动作或冻结参考首选不一致")
        scores = []
        for candidate in analysis.legal_candidates:
            features, exact = _features(candidate, observation)
            if isinstance(candidate.action, Hu):
                score, probability = exact, None
            else:
                score, probability = expected_net(features, model)
            scores.append({
                "action_key": candidate.action_key,
                "expected_net_probe": score,
                "terminal_category_probability": (
                    list(probability) if probability is not None else None),
                "exact_current_hu_net": exact if probability is None else None,
            })
        chosen = min(scores, key=lambda item: (
            -round(item["expected_net_probe"], 8),
            item["action_key"] != "hu", item["action_key"],
        ))
        rows.append({
            "seed": row["seed"], "root_id": root_id,
            "tags": row["tags"], "phase": row["phase"],
            "shape_first_action_key": row["shape_first_action_key"],
            "chosen_action_key": chosen["action_key"],
            "scores": sorted(scores, key=lambda item: item["action_key"]),
        })
    if len(rows) != scan["root_count"] or len({row["root_id"] for row in rows}) != len(rows):
        raise ValueError("全动作扫描的根数量或身份不守恒")
    return {
        "scope": "pre_outcome_competing_terminal_predictions_not_C_alg",
        "start_seed": scan["start_seed"],
        "requested_seeds": scan["requested_seeds"],
        "root_count": len(rows),
        "changed_vs_shape_roots": sum(row["chosen_action_key"] !=
                                      row["shape_first_action_key"] for row in rows),
        "deferred_current_hu_roots": sum(
            row["shape_first_action_key"] == "hu" and
            row["chosen_action_key"] != "hu" for row in rows),
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    args = parser.parse_args()
    if args.scan.suffix == ".gz":
        with gzip.open(args.scan, "rt", encoding="utf-8") as stream:
            scan = json.load(stream)
    else:
        scan = json.loads(args.scan.read_text(encoding="utf-8"))
    model = json.loads(args.model.read_text(encoding="utf-8"))
    print(json.dumps(predict(scan, model), ensure_ascii=False,
                     sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
