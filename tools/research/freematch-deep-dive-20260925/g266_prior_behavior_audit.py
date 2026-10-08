#!/usr/bin/env python3
"""G266 先验行为审计：在冻结 G259 官方行动前观察上重判分层选择器。

只读旧官方窗口与生产规则、R18 评分器；不读取结算、不运行模拟器，
不选择 G266 新牌山根。输出只描述强手分歧窗命中与一致窗误触。
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

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import c31_action_layer_gap as c31
import g05_strong_draw_reconstruction as g05
import g87_post_claim_score_trace as g87
import g138_official_plain_baotou_opportunity as g138
import g259_preclaim_route_pairs as g259
from hangma_bot.hangma.interface import RuleCompleteness, ValueCoverage
from hangma_bot.kernel.serialization import observation_from_json
from hangma_bot.offline.evaluation_results import compute_rules_hash


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
G259 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g259-preclaim-route-pairs-20260929')
G61 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g61-strong-draw-action-atlas-20260927')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g266-prior-behavior-audit-20260929/result.json')


def sha(path: Path) -> str:
    """返回文件原始字节摘要，供旧源与本次执行身份对账。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    """只读本地 JSON，不访问官方接口或赛后结算。"""

    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """读取已冻结的行动前动作对与一致负控。"""

    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def identity(row: dict[str, Any]) -> tuple[str, str, str, int, int, int]:
    """官方行动窗身份：强手、房、桌、单局、序号、物理座位。"""

    return (row["peer"], row["room"], row["game_id"], row["round_no"],
            row["draw_seq"], row["seat"])


def capacity(items: Any, *, nonwhite: bool = False) -> tuple[int, int]:
    """玩家视角公开未见物理容量；首项是正容量牌码数，次项是张数。"""

    if items is None:
        raise ValueError("G266 牌型有效牌事实缺失")
    values = []
    for item in items:
        value = item.remaining_estimate
        if type(value) is not int or not 0 <= value <= 4:
            raise ValueError("G266 有效牌公开容量必须是 0..4 整数")
        if value > 0 and (not nonwhite or item.code != "白"):
            values.append(value)
    return len(values), sum(values)


def finite_number(value: Any, name: str) -> float:
    """拒绝布尔伪数和非有限分数，保留评分器真实数值口径。"""

    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(name + " 缺失或不是有限数值")
    return float(value)


def b_alternatives(candidates: dict[str, Any], entries: dict[str, dict],
                   parent: str) -> list[tuple[tuple[Any, ...], str]]:
    """按 G266 B_nonready 硬门与事前排序取合法非白改弃。

    返回每个候选的排序键；核对旧母体入选备选的白板贡献恒等，避免
    把白板容量变化误称自然牌进张增加。
    """

    parent_fact = candidates[parent].facts
    base_shape = (parent_fact.standard_shanten_after,
                  parent_fact.seven_pairs_shanten_after,
                  parent_fact.shanten_after)
    if base_shape[:2] not in ((2, 1), (3, 2)):
        raise ValueError("旧母体 B_nonready 分牌型向听漂移")
    parent_ordinary = capacity(parent_fact.standard_useful_tiles, nonwhite=True)
    parent_all_ordinary = capacity(parent_fact.standard_useful_tiles)
    parent_combined = capacity(parent_fact.useful_tiles)
    parent_seven = capacity(parent_fact.seven_pairs_useful_tiles)
    parent_score = finite_number(entries[parent]["score"], "父代总分")
    parent_risk = finite_number(entries[parent]["trace"].get("risk_units"), "父代风险")
    if type(parent_fact.baotou_after) is not bool:
        raise ValueError("父代 baotou_after 不是显式布尔")
    ranked = []
    for action, candidate in candidates.items():
        if action == parent or not action.startswith("discard:") or action == "discard:白":
            continue
        facts = candidate.facts
        if (facts.standard_shanten_after, facts.seven_pairs_shanten_after,
                facts.shanten_after) != base_shape:
            continue
        ordinary = capacity(facts.standard_useful_tiles, nonwhite=True)
        all_ordinary = capacity(facts.standard_useful_tiles)
        if (all_ordinary[0] - parent_all_ordinary[0],
                all_ordinary[1] - parent_all_ordinary[1]) != (
                    ordinary[0] - parent_ordinary[0],
                    ordinary[1] - parent_ordinary[1]):
            raise ValueError("旧同向听候选的普通型宽度变化混入白板；非白选择不可直接等同全部普通宽度")
        if ordinary[0] <= parent_ordinary[0] or ordinary[1] <= parent_ordinary[1]:
            continue
        if facts.baotou_after is not parent_fact.baotou_after:
            continue
        risk = finite_number(entries[action]["trace"].get("risk_units"), "备选风险")
        if risk > parent_risk:
            continue
        score_gap = parent_score - finite_number(entries[action]["score"], "备选总分")
        if score_gap <= 0:
            continue
        combined = capacity(facts.useful_tiles)
        seven = capacity(facts.seven_pairs_useful_tiles)
        combined_loss = max(0, parent_combined[1] - combined[1])
        seven_loss = max(0, parent_seven[1] - seven[1])
        if not (combined_loss or seven_loss):
            continue
        rank = (-(ordinary[0] - parent_ordinary[0]),
                -(ordinary[1] - parent_ordinary[1]),
                combined_loss, seven_loss, score_gap, action)
        ranked.append((rank, action))
    ranked.sort()
    return ranked


def audit_window(kind: str, row: dict[str, Any], window: dict[str, Any],
                 scorer: Any) -> dict[str, Any]:
    """只用该动作窗可见观察重算规则、评分、机会及唯一排序备选。"""

    observed = window["observation"]
    observation = observation_from_json(observed)
    request = g87.request_for(observation)
    rules = request.rules
    candidates = {item.action_key: item for item in rules.legal_candidates}
    if len(candidates) != len(rules.legal_candidates):
        raise ValueError("合法动作键重复")
    view = g05.build_scoring_view(request, value_limits=c31.VALUE_LIMITS).candidate_view()
    entries = g259.score_entries(scorer(view))
    parent = row["parent_action"] if kind == "target" else row["agreed_action"]
    actual = row["strong_action"] if kind == "target" else row["agreed_action"]
    if (set(entries) != set(candidates) or set(entries) != set(window["legal_action_keys"])
            or g259.top(entries) != parent or window["parent_top_action"] != parent
            or window["actual_action"] != actual or actual not in candidates):
        raise ValueError("旧窗口、当前合法候选与父代/强手动作不一致")
    if (observation.phase != "draw" or observation.gang_draw is not None
            or window["own_meld_count"] != 0 or observed["observation_issues"]
            or rules.completeness is not RuleCompleteness.COMPLETE
            or len(observed["my_hand"]) != 14
            or observed["my_hand"].count("白") not in (1, 2)
            or not parent.startswith("discard:") or parent == "discard:白"):
        raise ValueError("旧窗口不满足 G266 B 类可见硬门")
    # 本次冻结目标与同格负控全部只有正常弃牌；其他动作族不外推。
    if not candidates or any(not key.startswith("discard:") for key in candidates):
        raise ValueError("旧窗口含即时胡或非弃牌动作族，不能用本先验口径重判")
    for candidate in candidates.values():
        facts, value = candidate.facts, candidate.value_facts
        if (facts is None or facts.completeness is not RuleCompleteness.COMPLETE
                or value is None or value.coverage is not ValueCoverage.COMPLETE):
            raise ValueError("合法弃牌事实或条件结算不完整")
        capacities, complete = g138.action_opportunity(candidate)
        if not complete or capacities["plain_baotou"] > 0:
            raise ValueError("旧窗口已有普通爆头机会或机会未知")
    for entry in entries.values():
        if entry["trace"].get("unknown") is not False:
            raise ValueError("R18 评分出现未知事实")
        finite_number(entry["score"], "R18 总分")
        finite_number(entry["trace"].get("risk_units"), "R18 风险")
    ranked = b_alternatives(candidates, entries, parent)
    chosen = ranked[0][1] if ranked else None
    ranks = {action: rank for rank, action in ranked}
    return {
        "identity": list(identity(row)), "kind": kind,
        "parent_action": parent, "observed_action": actual,
        "selected_alternative": chosen,
        "eligible_alternative_count": len(ranked),
        "matches_observed_action": chosen == actual,
        "observed_action_is_eligible_alternative": actual in ranks,
        "same_rank_before_action_key": (chosen != actual and actual in ranks
                                        and ranks[chosen][:-1] == ranks[actual][:-1]),
    }


def main() -> None:
    """冻结旧资料 SHA 与逐窗对账，写出不含结算的行为指纹证据。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT,
                        help="独立输出 JSON；已有文件拒绝覆盖")
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError("G266 先验行为审计证据已存在，拒绝覆盖")
    old = read_json(_project_file(_PROJECT_ROOT, G259 / "result.json"))
    old_g61 = read_json(_project_file(_PROJECT_ROOT, G61 / "result.json"))
    if old.get("result_blind") is not True or old_g61.get("outcome_labels_opened") is not False:
        raise ValueError("G259/G61 旧官方行动前母体盲态不符")
    if old["source_sha256"]["g61_result"] != sha(_project_file(_PROJECT_ROOT, G61 / "result.json")):
        raise ValueError("G259 绑定的 G61 汇总摘要漂移")
    for filename in ("target_pairs.jsonl", "matched_controls.jsonl"):
        if old["evidence_sha256"][filename] != sha(_project_file(_PROJECT_ROOT, G259 / filename)):
            raise ValueError("G259 冻结动作对摘要漂移：" + filename)
    target_rows = read_jsonl(_project_file(_PROJECT_ROOT, G259 / "target_pairs.jsonl"))
    control_rows = read_jsonl(_project_file(_PROJECT_ROOT, G259 / "matched_controls.jsonl"))
    selected_targets = [row for row in target_rows if (
        row["route_trade"] is True
        and row["pair"]["white_retained_parent"] in (1, 2)
        and (row["pair"]["parent_shanten"]["ordinary"],
             row["pair"]["parent_shanten"]["seven"]) in ((2, 1), (3, 2)))]
    contexts = {(row["peer"], row["context"]) for row in selected_targets}
    selected_controls = [row for row in control_rows
                         if (row["peer"], row["context"]) in contexts]
    if len(selected_targets) != 17 or len(selected_controls) != 61:
        raise ValueError("G259 B-like 目标/同格一致负控分母漂移")
    selection = [("target", row) for row in selected_targets]
    selection += [("control", row) for row in selected_controls]
    if len({identity(row) for _, row in selection}) != len(selection):
        raise ValueError("目标与负控动作窗身份重叠或重复")
    units = {(row["peer"], row["room"]) for _, row in selection}
    window_index: dict[tuple[str, str, str, int, int, int], dict] = {}
    unit_sha: dict[str, str] = {}
    for peer, room in sorted(units):
        path = _project_file(_PROJECT_ROOT, G61 / "rooms" / f"{peer}--{room}" / "windows.json")
        observed = sha(path)
        unit = peer + "/" + room
        if (observed != old_g61["units"][unit]["windows_sha256"]
                or observed != old["source_sha256"]["g61_windows_by_unit"][unit]):
            raise ValueError("G61/G259 逐房行动前窗口 SHA 漂移：" + unit)
        unit_sha[unit] = observed
        for window in read_json(path)["windows"]:
            key = (peer, room, window["game_id"], window["round_no"],
                   window["draw_seq"], window["seat"])
            if key in window_index:
                raise ValueError("G61 行动窗身份重复")
            window_index[key] = window
    scorer = c31.load_parent()
    rows = [audit_window(kind, row, window_index[identity(row)], scorer)
            for kind, row in selection]
    targets = rows[:len(selected_targets)]
    controls = rows[len(selected_targets):]
    hit = sum(row["matches_observed_action"] for row in targets)
    false_trigger = sum(row["selected_alternative"] is not None for row in controls)
    cross_room = [row for row, original in zip(controls, selected_controls)
                  if any(original["peer"] == target["peer"]
                         and original["context"] == target["context"]
                         and original["room"] != target["room"]
                         for target in selected_targets)]
    cross_false = sum(row["selected_alternative"] is not None for row in cross_room)
    if (hit, false_trigger, len(cross_room), cross_false) != (13, 10, 60, 9):
        raise ValueError("G266 先验行为复算与冻结期望 13/17、10/61、9/60 不同")
    source_paths = {
        "g259_result": _project_file(_PROJECT_ROOT, G259 / "result.json"),
        "g259_targets": _project_file(_PROJECT_ROOT, G259 / "target_pairs.jsonl"),
        "g259_controls": _project_file(_PROJECT_ROOT, G259 / "matched_controls.jsonl"),
        "g61_result": _project_file(_PROJECT_ROOT, G61 / "result.json"),
        "g259_reconstructor": Path(g259.__file__),
        "g87_request": Path(g87.__file__),
        "g05_view": Path(g05.__file__),
        "c31_parent_loader": Path(c31.__file__),
        "g138_opportunity": Path(g138.__file__),
        "r18_scoring_source": _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/r18_integrated_positive_v2.py"),
        "audit_script": Path(__file__),
    }
    output = {
        "schema": "g266-prior-behavior-audit/1",
        "date": "2026-09-29",
        "source_sha256": {name: sha(path) for name, path in source_paths.items()},
        "g61_windows_sha256_by_unit": unit_sha,
        "current_rules_source_hash": compute_rules_hash(ROOT),
        "target": {
            "windows": len(targets), "distinct_rooms": len({r["identity"][1] for r in targets}),
            "hit_strong_action": hit,
            "mismatch_same_rank_before_action_key": sum(
                row["same_rank_before_action_key"] for row in targets),
            "by_peer": {peer: {"windows": sum(r["identity"][0] == peer for r in targets),
                               "hits": sum(r["identity"][0] == peer and r["matches_observed_action"]
                                           for r in targets)}
                        for peer in ("xuanwu_2346", "tengshe_0638")},
        },
        "matched_agreement_control": {
            "windows": len(controls),
            "distinct_rooms": len({r["identity"][1] for r in controls}),
            "false_triggers": false_trigger,
            "cross_room_windows": len(cross_room),
            "cross_room_false_triggers": cross_false,
            "by_peer": {peer: {"windows": sum(r["identity"][0] == peer for r in controls),
                               "false_triggers": sum(r["identity"][0] == peer
                                                     and r["selected_alternative"] is not None
                                                     for r in controls)}
                        for peer in ("xuanwu_2346", "tengshe_0638")},
        },
        "selected_rows": rows,
        "limitations": [
            "G259 目标按强手与父代严格分歧及普通宽/七对损失预选；负控按两者一致预选，窗口率不是总体敏感度/特异度。",
            "G61 未存该官方动作窗完整 rejected_attempts 或历史降级记录；g87.request_for 为离线重判填空元组，不能核 G266 该硬门。",
            "同一房、完整桌、单局中可有多个窗口；17/61/60 均非独立房数，不报告因果效果或收益。",
            "只在旧官方正常弃牌行动前观察重判；未运行新牌山、隐藏世界、完整桌或后续结算。",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, ensure_ascii=False, sort_keys=True,
                                  indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"target_hits": [hit, len(targets)],
                      "control_false_triggers": [false_trigger, len(controls)],
                      "cross_room_false_triggers": [cross_false, len(cross_room)]},
                     ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
