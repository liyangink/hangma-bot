#!/usr/bin/env python3
"""G201：对冻结官方多白近听双弃牌计算生产合法三摸终点。"""

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

from hashlib import sha256
import json
from pathlib import Path
import time

import c31_action_layer_gap as c31
import g196_three_draw_competing_route_pilot as g196
import g201_multiwhite_near_ready_select as source
from hangma_bot.application.audit_codec import (
    candidate_facts_to_json, candidate_value_facts_to_json,
    observation_from_json,
)
from hangma_bot.hangma import value_analysis
from hangma_bot.hangma.internal_types import TILE_ORDER
from hangma_bot.policy.r18_integrated_positive_v2_rules_20260929_release import (
    R18IntegratedPositiveV2Rules20260929ReleasePolicy,
    R18_V2_RULES_20260929_SOURCE_HASH,
)


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g201-multiwhite-near-ready-route-20260929/result.json')
MODES = ("restricted", "unrestricted")


def digest(path: Path) -> str:
    """保留选样、生产量具和结果使用的原始源码摘要。"""

    return sha256(path.read_bytes()).hexdigest()


def observe(row: dict):
    """重建仅含行动前可见事实的观察并核冻结摘要。"""

    encoded = json.dumps(row["observation"], ensure_ascii=False,
                         sort_keys=True, separators=(",", ":")).encode("utf-8")
    if sha256(encoded).hexdigest() != row["observation_sha256"]:
        raise ValueError("G201 冻结玩家观察摘要漂移")
    observation = observation_from_json(row["observation"])
    if (observation.game_id != row["game_id"]
            or observation.round_no != row["round_no"]
            or observation.seat != row["seat"]):
        raise ValueError("G201 冻结观察的局与座位身份漂移")
    return observation


def check_rules(row: dict, observation) -> dict:
    """与当前生产规则逐臂对账原向听和公开有效容量。"""

    rule = c31.RULES.analyze(observation, value_limits=c31.VALUE_LIMITS)
    legal = {action.action_key: action for action in rule.legal_candidates}
    if len(legal) != len(rule.legal_candidates):
        raise ValueError("G201 当前合法动作键重复")
    for name in ("parent", "alternate"):
        key = row[name + "_action"]
        action = legal.get(key)
        if action is None or action.facts is None or action.value_facts is None:
            raise ValueError("G201 当前规则缺已冻结合法动作或价值事实")
        facts = candidate_facts_to_json(action.facts)
        current = {
            "combined_shanten": facts.get("shanten_after"),
            "standard_shanten": facts.get("standard_shanten_after"),
            "seven_shanten": facts.get("seven_pairs_shanten_after"),
            "standard": source.public_capacity(facts, "standard_useful_tiles"),
            "seven": source.public_capacity(facts, "seven_pairs_useful_tiles"),
        }
        old = row["old_facts"][name]
        for field in ("standard", "seven"):
            if current[field] is not None:
                current[field] = list(current[field])
        if current != old:
            raise ValueError(f"G201 {name} 当前规则事实与冻结旧动作不同")
    return legal


def first_hu_check(search: g196.RouteSearch, action) -> int:
    """直接枚举第一摸胡并与生产动作路线事实对账。"""

    expected = g196.g52._first_hu_routes(
        {"value_facts": candidate_value_facts_to_json(action.value_facts)},
        search.observation.seat,
    )
    direct = {}
    for index, capacity in enumerate(search.unseen):
        if capacity <= 0:
            continue
        value = search._win(search.root, TILE_ORDER[index],
                            baotou=search.root_baotou,
                            chain=search.root_chain, piao=search.root_piao,
                            depth=1)
        if value is not None:
            direct[TILE_ORDER[index]] = (round(value.total), capacity)
    if direct != expected:
        raise ValueError("G201 第一摸胡分与生产 value_facts 不一致")
    return sum(capacity for _gain, capacity in direct.values())


def main() -> None:
    """冻结八窗完整运行；一臂成本超线停止该层且不使用截断值。"""

    if OUT.exists():
        raise FileExistsError("G201 路线结果已存在，拒绝覆盖")
    selection = json.loads(source.OUT.read_text(encoding="utf-8"))
    if (selection["schema"] != "g201-multiwhite-near-ready-selection/1"
            or selection["source_sha256"]["plan"] != digest(source.PLAN)
            or selection["source_sha256"]["script"] != digest(Path(source.__file__))
            or len(selection["selected"]) != 8
            or len({row["room_id"] for row in selection["selected"]}) != 8):
        raise ValueError("G201 选样或预登记身份漂移")
    # 与 G194/G196 相同的新规则绑定构造，先核发布身份，再运行规则事实。
    R18IntegratedPositiveV2Rules20260929ReleasePolicy(
        rules_source_hash=R18_V2_RULES_20260929_SOURCE_HASH,
        value_analysis_sha256=digest(Path(value_analysis.__file__)),
    )
    results = []
    stopped_layers = set()
    for row in selection["selected"]:
        layer = row["layer"]
        if layer in stopped_layers:
            continue
        result = {key: row[key] for key in (
            "layer", "room_id", "game_id", "round_no", "trigger_seq", "seat",
            "white_before", "wall_remaining", "parent_action", "alternate_action",
            "observation_sha256")}
        result["arms"] = {}
        try:
            observation = observe(row)
            legal = check_rules(row, observation)
            for name in ("parent", "alternate"):
                key = row[name + "_action"]
                started = time.perf_counter()
                search = g196.RouteSearch(observation, c31.RULE_CONFIG, key)
                immediate = first_hu_check(search, legal[key])
                values = {}
                for mode in MODES:
                    values[mode] = search.evaluate(restricted=mode == "restricted").json()
                result["arms"][name] = {
                    "status": "complete", "first_hu_public_capacity": immediate,
                    "values": values,
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                    "counters": {"legal_leaf_count": search.legal_leaf_count,
                                 "win_split_count": search.win_split_count,
                                 "third_ready_count": search.third_ready_count,
                                 "third_memo_states": len(search.memo_third)},
                }
            result["status"] = "complete"
        except (g196.RouteLimitExceeded, ValueError) as exc:
            result["status"] = "abstained"
            result["reason"] = type(exc).__name__ + ": " + str(exc)
            stopped_layers.add(layer)
        results.append(result)
        print(json.dumps({"windows_attempted": len(results),
                          "layer": layer, "status": result["status"],
                          "reason": result.get("reason")},
                         ensure_ascii=False), flush=True)
    payload = {
        "schema": "g201-multiwhite-near-ready-route/1",
        "source_sha256": {"prereg": digest(source.PLAN),
                          "selection": digest(source.OUT),
                          "script": digest(Path(__file__)),
                          "g196_script": digest(Path(g196.__file__)),
                          "value_analysis": digest(Path(value_analysis.__file__))},
        "selected_count": 8, "attempted_count": len(results),
        "stopped_layers": sorted(stopped_layers), "rows": results,
        "boundary": "公开未知物理容量、三次条件本人摸牌、未来受限/不受限两包络；不含对手先胡、真实墙后验和弃胡续行；非真实收益。",
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                              indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"complete": sum(row["status"] == "complete" for row in results),
                      "attempted": len(results), "stopped_layers": payload["stopped_layers"]},
                     ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
