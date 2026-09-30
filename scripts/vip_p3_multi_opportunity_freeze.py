"""在打开结局前固定双白机会根、比较首动作与相关隐藏世界键。"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import RuleCompleteness, ValueAnalysisLimits
from hangma_bot.kernel.actions import Discard, Hu
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.serialization import observation_from_json

from scripts.vip_p3_anchored_value_probe import predict_observation
from scripts.vip_p3_multi_opportunity_scan import _KNOWN_MODEL_GAP, _opportunity
from scripts.vip_p3_payoff_frontier import ordinary_discard_one_draw_component


_LIMITS = ValueAnalysisLimits(max_expansions=8192)


def freeze(selection_path: Path) -> dict:
    """逐根重核依法可见事实，不借教师结局决定比较臂或样本量。"""

    source = selection_path.read_bytes()
    selection = json.loads(gzip.decompress(source) if selection_path.suffix == ".gz"
                           else source)
    if (selection.get("scope") !=
            "pre_outcome_r18_natural_two_white_and_highfan_roots_not_strategy_result"
            or selection.get("reference") != "r18_frozen"
            or selection.get("rule_config") != {"BaseScore": 1, "YouCaiBiKao": False}
            or selection.get("start_seed") != 4101
            or selection.get("requested_seeds") != 300):
        raise ValueError("双白机会冻结仅接受预定 R18 自然牌山 4101—4400")
    model_path = Path(selection["model_path"])
    model_bytes = model_path.read_bytes()
    if hashlib.sha256(model_bytes).hexdigest() != selection["model_sha256"]:
        raise ValueError("机会扫描的支付模型摘要漂移")
    model = json.loads(model_bytes)
    rules = HangmaRules(RuleConfig("hangma-mvp-v10-public-counts", 1, False))
    root_ids = set()
    frozen = []
    for row in selection["selected_roots"]:
        observation = observation_from_json(row["observation"])
        root_id = hashlib.sha256(repr(observation).encode()).hexdigest()
        if (root_id != row["root_id"] or root_id in root_ids
                or row["white_count"] < 2):
            raise ValueError("双白机会根身份、去重或白板条件不符")
        root_ids.add(root_id)
        tags = row["tags"]
        if (not tags or len(set(tags)) != len(tags)
                or any(tag not in ("first_two_white", "first_highfan_witness")
                       for tag in tags)):
            raise ValueError("机会根标签不符")
        analysis = rules.analyze(observation, value_limits=_LIMITS, route_limits=_LIMITS)
        candidates = analysis.legal_candidates
        routes = analysis.conditional_roots
        keys = [candidate.action_key for candidate in candidates]
        if (analysis.completeness is not RuleCompleteness.COMPLETE
                or routes is None or len(routes) != len(candidates)
                or any(route.gap_kind is not None for route in routes)
                or keys != row["legal_action_keys"]):
            raise ValueError("冻结机会根合法动作或条件状态缺失")
        witness = _opportunity(analysis, observation.seat)
        if (witness != row["highfan_witness"]
                or ("first_highfan_witness" in tags) != (witness is not None)):
            # 非高番标签的早期根允许有高番见证，但此时它必是该种子
            # 首次命中，扫描应同时给出两个标签，故仍可拒绝。
            raise ValueError("高番标签与同次精确规则支付见证不符")
        try:
            predicted = predict_observation(observation, model)
            model_key = predicted[0]["action_key"]
            model_gap = None
        except ValueError as exc:
            if str(exc) != _KNOWN_MODEL_GAP:
                raise
            model_key = None
            model_gap = str(exc)
        if (model_key != row["anchored_first_action_key"]
                or model_gap != row["anchored_value_gap"]):
            raise ValueError("冻结模型首选或缺证据与扫描不符")
        roles = {
            "r18": row["r18_first_action_key"],
            "anchored": model_key,
            "shape": row["shape_first_action_key"],
            "highfan_witness": witness["action_key"] if witness else None,
            "immediate_hu": "hu" if "hu" in keys else None,
        }
        if any(key not in keys for key in roles.values() if key is not None):
            raise ValueError("冻结比较首动作不属于本根合法动作")
        forced = list(dict.fromkeys(key for key in roles.values() if key is not None))
        if not forced:
            raise ValueError("机会根没有可比较动作")
        rule_payoff = {}
        for candidate, route in zip(candidates, routes):
            if candidate.action_key not in forced:
                continue
            if isinstance(candidate.action, Hu):
                rule_payoff[candidate.action_key] = {
                    "exact_immediate_hu_net": route.settlement.score_delta[observation.seat],
                    "conditional_next_normal_draw_net": None,
                    "condition_gap": None,
                }
            elif isinstance(candidate.action, Discard):
                try:
                    component = ordinary_discard_one_draw_component(
                        candidate, route, observation.seat)
                    value = component.conditional_exchangeable_direct_hu_net
                    gap = None
                except ValueError as exc:
                    if str(exc) != _KNOWN_MODEL_GAP:
                        raise
                    value, gap = None, str(exc)
                rule_payoff[candidate.action_key] = {
                    "exact_immediate_hu_net": None,
                    "conditional_next_normal_draw_net": value,
                    "condition_gap": gap,
                }
            else:
                raise ValueError("本批本人普通摸牌根出现未知比较动作族")
        sample_count = 32 if "first_highfan_witness" in tags else 16
        frozen.append({
            "seed": row["seed"], "root_id": root_id,
            "own_draw_index": row["own_draw_index"], "tags": tags,
            "white_count": row["white_count"],
            "wall_remaining": row["wall_remaining"],
            "roles": roles, "forced_first_actions": forced,
            "rule_payoff_before_outcome": rule_payoff,
            "worlds_per_root": sample_count,
            "resample_key_prefix": (
                f"vip-p3-multi-opportunity-{row['seed']}-{row['own_draw_index']}"),
        })
    if (len(frozen) != len(selection["selected_roots"])
            or len({row["seed"] for row in frozen}) != 31):
        raise ValueError("预定自然牌山选根或聚类数不守恒")
    return {
        "scope": "pre_outcome_multi_root_paired_actions_not_algorithm_confirmation",
        "selection_report": str(selection_path),
        "selection_report_sha256": hashlib.sha256(source).hexdigest(),
        "model_path": str(model_path),
        "model_sha256": selection["model_sha256"],
        "rule_config": selection["rule_config"],
        "selection_reference": "r18_frozen",
        "scenario_prefix": selection["scenario_prefix"],
        "focal_seat": 0,
        "continuation_references": ["shape", "r18_frozen"],
        "natural_seed_frame": [4101, 4400],
        "primary_cluster_unit": "natural_seed_not_hidden_world_or_window",
        "comparison": "anchored_minus_r18_first_action_under_each_frozen_reference",
        "report_all_tags": True,
        "model_gaps_not_dropped": True,
        "interpretation_limit": (
            "Single forced first action then teacher continuation; opened conditional "
            "roots cannot prove full VIP policy or natural full-table gain."
        ),
        "roots": frozen,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(freeze(args.selection), ensure_ascii=False,
                     sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
