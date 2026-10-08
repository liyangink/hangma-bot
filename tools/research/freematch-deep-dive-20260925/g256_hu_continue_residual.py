#!/usr/bin/env python3
"""G256：只读复算 G252 胡／继续分歧的可见逐动作规则事实。

标准输出为确定性 JSON；脚本不打开官方牌谱、后验牌墙、终局标签或数据库。
用法：.venv/bin/python review/freematch-deep-dive-20260925/g256_hu_continue_residual.py
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/freematch-deep-dive-20260925'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))
sys.path.insert(0, str(HERE))

import c31_action_layer_gap as c31  # noqa: E402  冻结 R18 v2 的生产规则配置。
from hangma_bot.hangma import value_analysis  # noqa: E402
from hangma_bot.kernel.serialization import observation_from_json  # noqa: E402
from hangma_bot.simulation.artifacts import compute_rules_hash  # noqa: E402
from hangma_bot.policy.r18_integrated_positive_v2 import (  # noqa: E402
    R18_INTEGRATED_POSITIVE_V2_SHA256,
    R18_INTEGRATED_POSITIVE_V2_SOURCE,
)
from hangma_bot.policy.r18_integrated_positive_v2_release import (  # noqa: E402
    R18_INTEGRATED_POSITIVE_V2_VALUE_ANALYSIS_SHA256,
)
from hangma_bot.policy.r18_integrated_positive_v2_rules_20260929_release import (  # noqa: E402
    R18_V2_RULES_20260929_SOURCE_HASH,
)

SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g252-strong-hu-continue-atlas-20260929')


def sha(path: Path) -> str:
    """返回文件原始字节的 SHA-256，用于绑定只读输入。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def tile_facts(tiles) -> list[dict]:
    """保留牌码与公开未见物理张数上界；该数不是墙中概率。"""

    return [
        {"code": item.code, "public_unseen_upper_bound": item.remaining_estimate}
        for item in tiles
    ]


def route_facts(route, seat: int) -> dict:
    """记录一摸成胡的条件见证，绝不把条件番数当作已兑现收益。"""

    condition = route.conditions
    return {
        "conditional_fan": route.conditional_settlement.fan,
        "conditional_details": list(route.conditional_settlement.details),
        "conditional_focal_delta": route.conditional_settlement.score_delta[seat],
        "draw_kind": condition.draw_kind,
        "chain_count": condition.chain_count,
        "chain_piao": condition.chain_piao,
        "baotou": condition.baotou,
        "meld_count": condition.meld_count,
        "pre_draw_whites": condition.pre_draw_hand.count("白"),
        "useful_tiles": tile_facts(route.useful_tiles),
        "public_unseen_upper_bound": sum(
            tile.remaining_estimate for tile in route.useful_tiles
        ),
    }


def action_facts(candidate, *, seat: int, immediate_fan: int) -> dict:
    """投影同一观察的一个合法续行动作；未知值保持空值。"""

    facts = candidate.facts
    value = candidate.value_facts
    routes = [] if value is None else [route_facts(route, seat) for route in value.routes]
    # 同一动作内各 ValueRoute 的进张互斥；若此不变量变化，不能相加容量。
    route_codes = [tile["code"] for route in routes for tile in route["useful_tiles"]]
    if len(route_codes) != len(set(route_codes)):
        raise ValueError("同一候选的条件路线重复计算一张进张")
    return {
        "action_key": candidate.action_key,
        "fact_kind": None if facts is None else facts.fact_kind.value,
        "fact_completeness": None if facts is None else facts.completeness.value,
        "combined_shanten_after": None if facts is None else facts.shanten_after,
        "standard_shanten_after": None if facts is None else facts.standard_shanten_after,
        "seven_pairs_shanten_after": None if facts is None else facts.seven_pairs_shanten_after,
        "baotou_after": None if facts is None else facts.baotou_after,
        "replacement_draw_unknown": None if facts is None else facts.replacement_draw_unknown,
        "useful_tiles": [] if facts is None else tile_facts(facts.useful_tiles),
        "standard_useful_tiles": (
            None if facts is None or facts.standard_useful_tiles is None
            else tile_facts(facts.standard_useful_tiles)
        ),
        "seven_pairs_useful_tiles": (
            None if facts is None or facts.seven_pairs_useful_tiles is None
            else tile_facts(facts.seven_pairs_useful_tiles)
        ),
        "family_progress": [] if facts is None else [
            {
                "family": entry.family.value,
                "progress": entry.progress.value,
                "route_status": entry.route_status.value,
            }
            for entry in facts.family_progress
        ],
        "value_coverage": None if value is None else value.coverage.value,
        "value_issues": [] if value is None else [
            {"area": issue.area, "reason": issue.reason} for issue in value.issues
        ],
        "routes": routes,
        "max_conditional_fan": max((route["conditional_fan"] for route in routes), default=None),
        "upgrade_public_unseen_upper_bound": sum(
            route["public_unseen_upper_bound"]
            for route in routes if route["conditional_fan"] > immediate_fan
        ),
        "same_or_higher_public_unseen_upper_bound": sum(
            route["public_unseen_upper_bound"]
            for route in routes if route["conditional_fan"] >= immediate_fan
        ),
    }


def full_hand_whites(observation: dict) -> int:
    """归一化官方双形态 my_hand，避免把已含摸牌再计一次。"""

    melds = len(observation["melds"][observation["seat"]])
    target_length = 14 - 3 * melds
    hand = list(observation["my_hand"])
    if len(hand) == target_length - 1:
        hand.append(observation["drawn_tile"])
    elif len(hand) == target_length:
        if observation["drawn_tile"] not in hand:
            raise ValueError("已含摸牌形态却找不到 drawn_tile")
    else:
        raise ValueError("摸牌观察的暗牌张数与副露数不符")
    if hand.count("白") > 4:
        raise ValueError("同一暗手白板超过四张")
    return hand.count("白")


def classify(row: dict) -> str:
    """分歧方向仅由 G252 当窗标签与冻结父代首选给出。"""

    parent_hu = row["parent_top_action"] == "hu"
    expert_hu = row["actual_action"] == "hu"
    if parent_hu and not expert_hu:
        return "parent_hu_expert_continue"
    if expert_hu and not parent_hu:
        return "parent_continue_expert_hu"
    if parent_hu:
        return "both_hu"
    return "both_continue"


def summarize_window(row: dict, actions: list[dict], *, first_forward: bool) -> dict:
    """产生全部 940 窗的结果盲特征摘要，便于负例筛查。"""

    observation = row["observation"]
    nonwhite_discards = [
        action for action in actions if action["action_key"].startswith("discard:")
        and action["action_key"] != "discard:白"
    ]
    immediate_fan = row["immediate_hu"]["fan"]
    upgraded = [
        action for action in nonwhite_discards
        if action["value_coverage"] == "complete"
        and action["upgrade_public_unseen_upper_bound"] > 0
    ]
    new_baotou = [
        action for action in upgraded
        if not observation["rule_state"]["baotou"] and action["baotou_after"] is True
    ]
    actual = next((action for action in actions if action["action_key"] == row["actual_action"]), None)
    if actual is None and row["actual_action"] != "hu":
        raise ValueError("G252 已接受的续行动作不在合法集合")
    return {
        "peer": row["peer"], "room_id": row["room_id"],
        "game_id": row["game_id"], "round_no": row["round_no"],
        "draw_seq": row["draw_seq"], "seat": row["seat"],
        "class": classify(row), "first_forward_in_peer_round": first_forward,
        "actual_action": row["actual_action"],
        "parent_top_action": row["parent_top_action"],
        "parent_score_hu_minus_actual": row["parent_score_hu_minus_actual"],
        "immediate_fan": immediate_fan,
        "immediate_focal_delta": row["immediate_hu"]["focal_delta"],
        "immediate_details": row["immediate_hu"]["details"],
        "wall_remaining": observation["remaining_tile_count"],
        "white_count": full_hand_whites(observation),
        "meld_count": len(observation["melds"][observation["seat"]]),
        "current_baotou": observation["rule_state"]["baotou"],
        "current_chain_count": observation["rule_state"]["chain_count"],
        "current_chain_piao": observation["chain_piao"],
        "any_nonwhite_upgrade": bool(upgraded),
        "any_nonwhite_new_baotou_upgrade": bool(new_baotou),
        "max_nonwhite_upgrade_upper_bound": max(
            (action["upgrade_public_unseen_upper_bound"] for action in upgraded),
            default=0,
        ),
        "actual_baotou_after": None if actual is None else actual["baotou_after"],
        "actual_combined_shanten_after": None if actual is None else actual["combined_shanten_after"],
        "actual_standard_shanten_after": None if actual is None else actual["standard_shanten_after"],
        "actual_seven_pairs_shanten_after": None if actual is None else actual["seven_pairs_shanten_after"],
        "actual_value_coverage": None if actual is None else actual["value_coverage"],
        "actual_max_conditional_fan": None if actual is None else actual["max_conditional_fan"],
        "actual_upgrade_upper_bound": None if actual is None else actual["upgrade_public_unseen_upper_bound"],
        "actual_same_or_higher_upper_bound": None if actual is None else actual["same_or_higher_public_unseen_upper_bound"],
    }


def main() -> None:
    """校验 G252 冻结血缘，复算逐窗候选并将机读结果写到标准输出。"""

    result_path = _project_file(_PROJECT_ROOT, SOURCE / "result.json")
    manifest_path = _project_file(_PROJECT_ROOT, SOURCE / "manifest.json")
    rows_path = _project_file(_PROJECT_ROOT, SOURCE / "rows.jsonl.gz")
    source_result = json.loads(result_path.read_text(encoding="utf-8"))
    source_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if source_result["manifest_sha256"] != sha(manifest_path):
        raise ValueError("G252 清单摘要漂移")
    if source_result["rows_sha256"] != sha(rows_path):
        raise ValueError("G252 逐窗摘要漂移")
    if source_result["script_sha256"] != sha(_project_file(_PROJECT_ROOT, HERE / "g252_strong_hu_continue_atlas.py")):
        raise ValueError("G252 抽取器源码摘要漂移")
    if source_manifest["source_parent_sha256"] != R18_INTEGRATED_POSITIVE_V2_SHA256:
        raise ValueError("G252 父代身份与当前冻结包不符")
    if hashlib.sha256(R18_INTEGRATED_POSITIVE_V2_SOURCE.encode("utf-8")).hexdigest() != R18_INTEGRATED_POSITIVE_V2_SHA256:
        raise ValueError("冻结 R18 v2 源码摘要漂移")
    rules_source_hash = compute_rules_hash(ROOT)
    value_analysis_hash = sha(Path(value_analysis.__file__))
    if rules_source_hash != R18_V2_RULES_20260929_SOURCE_HASH:
        raise ValueError("当前主线规则与 2026-09-29 R18 发布包绑定不符")
    if value_analysis_hash != R18_INTEGRATED_POSITIVE_V2_VALUE_ANALYSIS_SHA256:
        raise ValueError("一次摸牌分值分析源码与 R18 发布包绑定不符")
    with gzip.open(rows_path, "rt", encoding="utf-8") as source:
        rows = [json.loads(line) for line in source]
    if len(rows) != source_result["rows"] or len(rows) != 940:
        raise ValueError("G252 窗口分母不符")
    rows.sort(key=lambda row: (row["peer"], row["room_id"], row["game_id"], row["round_no"], row["draw_seq"]))
    seen_forward = set()
    summaries = []
    cases = []
    negative_cases = []
    for row in rows:
        observation = observation_from_json(row["observation"])
        analysis = c31.RULES.analyze(observation, value_limits=c31.VALUE_LIMITS)
        legal = {candidate.action_key: candidate for candidate in analysis.legal_candidates}
        if sorted(legal) != row["legal_action_keys"] or "hu" not in legal:
            raise ValueError("当前生产规则与 G252 合法动作集合不符")
        immediate = legal["hu"].value_facts.immediate_settlement
        if immediate is None or immediate.fan != row["immediate_hu"]["fan"] or list(immediate.score_delta) != row["immediate_hu"]["score_delta_by_physical_seat"]:
            raise ValueError("当前生产规则与 G252 立即胡结算不符")
        forward = classify(row) == "parent_hu_expert_continue"
        key = (row["peer"], row["game_id"], row["round_no"])
        first_forward = forward and key not in seen_forward
        if forward:
            seen_forward.add(key)
        actions = [
            action_facts(legal[action_key], seat=row["seat"], immediate_fan=immediate.fan)
            for action_key in sorted(legal) if action_key != "hu"
        ]
        summary = summarize_window(row, actions, first_forward=first_forward)
        summaries.append(summary)
        if first_forward or summary["class"] == "parent_continue_expert_hu":
            cases.append({
                "window": summary,
                "visible_observation": row["observation"],
                "legal_continue_actions": actions,
            })
        if summary["class"] == "both_hu" and summary["any_nonwhite_upgrade"]:
            negative_cases.append({
                "window": summary,
                "visible_observation": row["observation"],
                "legal_continue_actions": actions,
            })
    counts = Counter(item["class"] for item in summaries)
    if counts != Counter({"both_hu": 696, "both_continue": 180,
                          "parent_hu_expert_continue": 61,
                          "parent_continue_expert_hu": 3}):
        raise ValueError(f"G252 分歧分母漂移：{counts}")
    if len(seen_forward) != 39 or len(cases) != 42:
        raise ValueError("强手－单局首分歧或反向窗口数漂移")
    if len(negative_cases) != 20:
        raise ValueError("普通立即胡中的高番条件负例数漂移")
    document = {
        "schema": "g256-hu-continue-visible-residual/1",
        "outcome_blind": True,
        "source": {
            "g252_manifest_sha256": sha(manifest_path),
            "g252_result_sha256": sha(result_path),
            "g252_rows_sha256": sha(rows_path),
            "r18_parent_source_sha256": R18_INTEGRATED_POSITIVE_V2_SHA256,
            "rules_source_hash": rules_source_hash,
            "value_analysis_source_sha256": value_analysis_hash,
            "g256_script_sha256": sha(Path(__file__)),
            "ruleset_version": c31.RULE_CONFIG.ruleset_version,
            "you_cai_bi_kao": c31.RULE_CONFIG.you_cai_bi_kao,
            "max_expansions": c31.VALUE_LIMITS.max_expansions,
            "max_routes_per_candidate": c31.VALUE_LIMITS.max_routes_per_candidate,
        },
        "counts": dict(sorted(counts.items())),
        "first_forward_peer_rounds": len(seen_forward),
        "cases": cases,
        "protected_hu_with_upgrade_negative_cases": negative_cases,
        "all_window_summaries": summaries,
        "limits": (
            "只包含动作前 PlayerObservation、已核强手当窗动作和生产规则的一摸条件见证；"
            "公开未见张数是物理容量上界，不是墙中概率；不包含后验牌墙、他家暗牌、"
            "继续后终局或反事实桌收益。"
        ),
    }
    print(json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
