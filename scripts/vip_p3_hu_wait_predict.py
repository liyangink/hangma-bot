"""在读取低番胡留出反事实结局前，锁定冻结模型的行动前预测。

模拟器只负责沿冻结 shape 路径生成当前 PlayerObservation；到达目标
窗口即停止，不查询该动作之后的世界。模型只消费观察与同源规则事实。
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import RuleCompleteness, ValueAnalysisLimits
from hangma_bot.kernel.config import RuleConfig, TimingConfig, TournamentConfig
from hangma_bot.offline.vip_reference import choose_reference_action
from hangma_bot.simulation import MatchSpec, SimulationChoice, SimulationEngine

from scripts.vip_p3_value_fit_probe import _FEATURE_NAMES, _features


def _reach_observation(engine: SimulationEngine, rules: HangmaRules,
                       seed: int, own_draw_index: int):
    """走到目标行动前窗口立即返回，绝不打开当前动作之后的事件。"""

    spec = MatchSpec(
        match_id=f"vip-p3-opportunity-{seed}",
        scenario_id=f"vip-p3-opportunity-{seed}",
        config=TournamentConfig(1, 1, rules.config, TimingConfig(1.0, 1.0, 3.0)),
        seed=seed, initial_dealer=0, initial_scores=(0, 0, 0, 0),
    )
    world = engine.start(spec)
    seen = 0
    for _ in range(500):
        frame = engine.frame(world)
        if frame.blocked_reason is not None or frame.final_scores is not None:
            raise ValueError("冻结目标低番胡窗口前模拟器已阻塞或结束")
        for decision in frame.decisions:
            observation = decision.observation
            if (decision.window_key.seat == 0 and observation.phase == "draw"
                    and observation.drawn_tile is not None):
                seen += 1
                if seen == own_draw_index:
                    return observation
        world = engine.advance(world, frame.revision, tuple(
            SimulationChoice(item.window_key,
                             choose_reference_action(rules, item, mode="shape"))
            for item in frame.decisions
        ))
    raise ValueError("目标低番胡窗口在 500 帧内未到达")


def predict(scan: dict, model: dict) -> dict:
    """只输出结果盲观察根的评分、合法首选及绑定身份。"""

    if (scan.get("scope") !=
            "result_blind_opportunity_root_selection_not_outcome_or_probability"
            or scan.get("selection_method") != "first_low_fan_hu_under_shape_per_seed"
            or model.get("schema") != "vip-p3-hu-wait-direct-route-probe/1"
            or model.get("frozen_before_holdout_labels") is not True
            or scan.get("rule_config") != model.get("rule_config")
            or tuple(model.get("feature_names", ())) != _FEATURE_NAMES
            or model.get("ridge") != 10.0):
        raise ValueError("行动前选根或模型冻结身份不匹配")
    feature_sha = hashlib.sha256((Path(__file__).resolve().parent /
                                  "vip_p3_value_fit_probe.py").read_bytes()).hexdigest()
    if feature_sha != model.get("feature_source_sha256"):
        raise ValueError("冻结特征源码摘要漂移")
    beta = model.get("coefficients")
    if not isinstance(beta, list) or len(beta) != len(_FEATURE_NAMES):
        raise ValueError("冻结系数维度不匹配")
    rules = HangmaRules(RuleConfig("hangma-mvp-v10-public-counts", 1, False))
    engine = SimulationEngine(rules)
    limits = ValueAnalysisLimits(max_expansions=8192)
    rows = []
    selected = [row for row in scan["selected_roots"]
                if "first_low_fan_hu" in row["tags"]]
    if len(selected) != scan["counts"]["selected_first_low_fan_hu"]:
        raise ValueError("冻结低番胡观察根计数不守恒")
    for selected_row in selected:
        observation = _reach_observation(
            engine, rules, selected_row["seed"],
            selected_row["own_draw_index"],
        )
        root_id = hashlib.sha256(repr(observation).encode("utf-8")).hexdigest()
        if root_id != selected_row["observation_sha256"]:
            raise ValueError("目标行动前玩家观察与冻结扫描摘要不一致")
        analysis = rules.analyze(observation, value_limits=limits)
        if analysis.completeness is not RuleCompleteness.COMPLETE:
            raise ValueError("留出根规则分析不完整")
        scored = []
        for candidate in analysis.legal_candidates:
            features, exact = _features(candidate, observation)
            score = exact + sum(weight * value for weight, value
                                in zip(beta, features))
            scored.append({
                "action_key": candidate.action_key,
                "expected_net_probe": score,
                "exact_current_hu_net": exact if candidate.action_key == "hu" else None,
                "feature_values": list(features),
            })
        if (not scored or len({row["action_key"] for row in scored}) != len(scored)
                or not any(row["action_key"] == "hu" for row in scored)):
            raise ValueError("冻结低番胡根缺合法当前胡或动作键重复")
        chosen = min(scored, key=lambda row: (
            -round(row["expected_net_probe"], 8),
            row["action_key"] != "hu", row["action_key"],
        ))
        rows.append({
            "seed": selected_row["seed"], "root_id": root_id,
            "own_draw_index": selected_row["own_draw_index"],
            "current_hu_fan": selected_row["current_hu_fan"],
            "current_hu_net": selected_row["current_hu_net"],
            "white_count": selected_row["white_count"],
            "wall_remaining": selected_row["wall_remaining"],
            "chosen_action_key": chosen["action_key"],
            "scores": sorted(scored, key=lambda row: row["action_key"]),
        })
    return {
        "scope": "pre_outcome_frozen_hu_wait_predictions_not_C_alg",
        "selection_method": scan["selection_method"],
        "start_seed": scan["start_seed"],
        "requested_seeds": scan["requested_seeds"],
        "root_count": len(rows),
        "wait_chosen_roots": sum(row["chosen_action_key"] != "hu" for row in rows),
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    args = parser.parse_args()
    scan = json.loads(args.scan.read_text(encoding="utf-8"))
    model = json.loads(args.model.read_text(encoding="utf-8"))
    print(json.dumps(predict(scan, model), ensure_ascii=False,
                     sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
