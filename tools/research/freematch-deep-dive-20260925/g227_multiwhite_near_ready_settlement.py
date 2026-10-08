#!/usr/bin/env python3
"""G227：多白近听牌同窗双臂的生产合法三摸结算包络。"""

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
from collections import Counter
import concurrent.futures
from hashlib import sha256
import json
from pathlib import Path
import time

import c31_action_layer_gap as c31
import g196_three_draw_competing_route_pilot as g196
import g223_visible_multi_action_route as g223
import g224_g223_vector_replay as g224
import g225_equal_width_topology_teacher as g225
import g52_shared_horizon as g52
import g87_post_claim_score_trace as g87
from hangma_bot.application.audit_codec import candidate_value_facts_to_json
from hangma_bot.hangma.internal_types import TILE_ORDER
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
PLAN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G227-MULTIWHITE-NEAR-READY-SETTLEMENT-PLAN-2026-09-29.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g227-multiwhite-near-ready-settlement-20260929')
SALT = "g227-multiwhite-near-ready-v1"
PAIRS_PER_MIX = 12


def digest(path: Path) -> str:
    """冻结文件原始字节以检验来源及方法是否漂移。"""
    return sha256(path.read_bytes()).hexdigest()


def eligible() -> list[dict]:
    """只看行动前规则事实，从 G224 阶段中锁定多白一向听冲突。"""
    summary = json.loads((g224.OUT / "result.json").read_text(encoding="utf-8"))
    if summary["complete_tables_verified"] != 128 or summary["probe_windows"] != 2191:
        raise ValueError("G224 阶段完成规模漂移")
    rows = []
    stage_hashes = summary["stage_sha256"]
    if len(stage_hashes) != 64:
        raise ValueError("G224 阶段摘要个数漂移")
    for filename, expected in sorted(stage_hashes.items()):
        stage_path = g224.OUT / "stages" / filename
        if digest(stage_path) != expected:
            raise ValueError("G224 阶段原文摘要漂移")
        stage = json.loads(stage_path.read_text(encoding="utf-8"))
        for root in stage["roots"]:
            if (root["white_bucket"] != 2
                    or root["root_shape"]["standard_shanten_after"] != 1
                    or root["root_action"] == "discard:白"):
                continue
            parent = next(item for item in root["same_layer_options"]
                          if item["action"] == root["root_action"])
            if (type(parent["seven_pairs_shanten_after"]) is not int
                    or type(parent["white_after"]) is not int
                    or parent["white_after"] < 2):
                continue
            alternatives = [item for item in root["same_layer_options"]
                            if item["action"] != parent["action"]
                            and item["action"] != "discard:白"
                            and item["white_after"] == parent["white_after"]
                            and type(item["seven_pairs_shanten_after"]) is int
                            and item["seven_pairs_shanten_after"]
                                <= parent["seven_pairs_shanten_after"]
                            and type(item["parent_score_gap"]) in (int, float)
                            and 0 <= item["parent_score_gap"] <= 4
                            and g225.vector(item) != g225.vector(parent)]
            if not alternatives:
                continue
            chosen = min(alternatives, key=lambda item:
                         (item["parent_score_gap"], -item["standard_width"][0],
                          -item["standard_width"][1], item["action"]))
            rows.append({
                "mix": stage["mix"], "root_index": stage["root_index"],
                "start_seat": stage["start_seat"],
                "source_stage": filename, "source_stage_sha256": expected,
                "root_decision_id": root["root_decision_id"],
                "table_id": root["table_id"], "round_no": root["round_no"],
                "white_after": parent["white_after"],
                "parent_action": parent["action"],
                "alternative_action": chosen["action"],
                "parent_score_gap": chosen["parent_score_gap"],
                "parent_standard_width": parent["standard_width"],
                "alternative_standard_width": chosen["standard_width"],
            })
    return rows


def selected() -> dict:
    """每池先覆盖不同牌山根，再补足 12 张不同桌；不读未来结果。"""
    rows = eligible()
    picked = []
    coverage = {}
    for mix in ("H", "M"):
        group = sorted((row for row in rows if row["mix"] == mix),
                       key=lambda row: sha256((SALT + ":" + row["root_decision_id"])
                                              .encode("utf-8")).hexdigest())
        chosen = []
        used_roots = set()
        used_tables = set()
        for row in group:
            if row["root_index"] in used_roots or row["table_id"] in used_tables:
                continue
            chosen.append(row)
            used_roots.add(row["root_index"])
            used_tables.add(row["table_id"])
        for row in group:
            if len(chosen) >= PAIRS_PER_MIX:
                break
            if row["table_id"] in used_tables:
                continue
            chosen.append(row)
            used_tables.add(row["table_id"])
        coverage[mix] = {"eligible_windows": len(group),
                         "eligible_tables": len({row["table_id"] for row in group}),
                         "eligible_roots": len({row["root_index"] for row in group}),
                         "selected": len(chosen),
                         "selected_roots": len({row["root_index"] for row in chosen})}
        if len(chosen) != PAIRS_PER_MIX or len(used_roots) < 4:
            raise ValueError("G227 预定的每池 12 对／4 根覆盖不足")
        picked.extend(chosen)
    if len({row["table_id"] for row in picked}) != 2 * PAIRS_PER_MIX:
        raise ValueError("G227 不同池或同池重复完整桌")
    return {
        "schema": "g227-multiwhite-near-ready-selection/1",
        "outcome_blind": True, "salt": SALT,
        "source_sha256": {"plan": digest(PLAN), "script": digest(Path(__file__)),
                          "g224_result": digest(g224.OUT / "result.json")},
        "coverage": coverage, "pairs": picked,
        "boundary": "同窗多白近听牌结果盲选样；后续真实路径和教师值未用于选择。",
    }


def _first_hu_check(search: g196.RouteSearch, candidate, seat: int) -> dict:
    """条件第一摸立即胡事实与生产 value_facts 逐码逐分对账。"""
    expected = g52._first_hu_routes(
        {"value_facts": candidate_value_facts_to_json(candidate.value_facts)}, seat)
    direct = {}
    for index, capacity in enumerate(search.unseen):
        if capacity <= 0:
            continue
        terminal = search._win(search.root, TILE_ORDER[index],
                               baotou=search.root_baotou,
                               chain=search.root_chain,
                               piao=search.root_piao, depth=1)
        if terminal is not None:
            direct[TILE_ORDER[index]] = (round(terminal.total), capacity)
    if direct != expected:
        raise ValueError("G227 首次摸牌胡分与生产价值事实不一致")
    return {"win_tile_codes": len(direct),
            "conditional_mass": sum(value * capacity
                                    for value, capacity in direct.values())}


def _mode(observation, action: str, restricted: bool) -> dict:
    """每个抓打包络独立计时与计叶，避免共用预算掩盖超限。"""
    started = time.perf_counter()
    search = g196.RouteSearch(observation, c31.RULE_CONFIG, action)
    try:
        value = search.evaluate(restricted=restricted)
    except g196.RouteLimitExceeded as exc:
        return {"status": "limit_exceeded", "reason": str(exc),
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                "legal_leaf_count": search.legal_leaf_count}
    elapsed = (time.perf_counter() - started) * 1000
    if elapsed > g196.MAX_SECONDS_PER_ARM * 1000 or search.legal_leaf_count > g196.MAX_LEAVES:
        return {"status": "limit_exceeded", "reason": "事后成本超过事前上界",
                "elapsed_ms": round(elapsed, 3),
                "legal_leaf_count": search.legal_leaf_count}
    return {"status": "complete", "value": value.json(),
            "elapsed_ms": round(elapsed, 3),
            "legal_leaf_count": search.legal_leaf_count,
            "win_split_count": search.win_split_count,
            "third_ready_count": search.third_ready_count,
            "third_memo_states": len(search.memo_third)}


def run_pair(index: int, row: dict) -> dict:
    """重建同一玩家可见根，请生产规则核动作后比较两根结算包络。"""
    stage_path = g224.OUT / "stages" / row["source_stage"]
    if digest(stage_path) != row["source_stage_sha256"]:
        raise ValueError("G227 目标阶段摘要漂移")
    roots = [item for item in json.loads(stage_path.read_text(encoding="utf-8"))["roots"]
             if item["root_decision_id"] == row["root_decision_id"]]
    if len(roots) != 1:
        raise ValueError("G227 根观察身份不唯一")
    root = roots[0]
    observation = observation_from_json(root["observation"])
    request = g87.request_for(observation)
    legal = {item.action_key: item for item in request.rules.legal_candidates}
    arms = {}
    for label, action in (("parent", row["parent_action"]),
                          ("alternative", row["alternative_action"])):
        candidate = legal.get(action)
        if candidate is None or candidate.facts is None or candidate.value_facts is None:
            raise ValueError("G227 根动作缺生产合法或价值事实")
        stored = next(item for item in root["same_layer_options"]
                      if item["action"] == action)
        if (candidate.facts.standard_shanten_after != 1
                or stored["white_after"] != row["white_after"]
                or tuple(stored["standard_width"]) != tuple(
                    row[label + "_standard_width"])
                or g225.vector(stored) != tuple(sorted(
                    (item.code, item.remaining_estimate)
                    for item in candidate.facts.standard_useful_tiles
                    if item.remaining_estimate > 0))):
            raise ValueError("G227 根动作同层、白数或进张向量漂移")
        first = _first_hu_check(g196.RouteSearch(observation, c31.RULE_CONFIG, action),
                                candidate, observation.seat)
        modes = {name: _mode(observation, action, restricted)
                 for name, restricted in (("restricted", True),
                                          ("unrestricted", False))}
        arms[label] = {"first_hu_production_check": first, "modes": modes}
        if any(mode["status"] != "complete" for mode in modes.values()):
            return {"schema": "g227-multiwhite-near-ready-pair/1", "index": index,
                    **row, "status": "stopped_on_cost", "arms": arms}
    delta = {}
    for mode in ("restricted", "unrestricted"):
        a = arms["alternative"]["modes"][mode]["value"]
        p = arms["parent"]["modes"][mode]["value"]
        delta[mode] = {name: a[name] - p[name] for name in
                       ("plain", "special", "depth1", "depth2", "depth3", "total")}
    return {"schema": "g227-multiwhite-near-ready-pair/1", "index": index,
            **row, "status": "complete", "arms": arms, "delta": delta,
            "boundary": "同玩家可见根的生产规则条件三摸值；未估他胡、先鸣和实墙。"}


def pair_path(index: int) -> Path:
    """每对单独存证，可从未完成的索引安全续跑。"""
    return _project_file(_PROJECT_ROOT, OUT / "pairs" / f"pair-{index:03d}.json")


def _sign(value: float) -> str:
    return "positive" if value > 1e-9 else "negative" if value < -1e-9 else "equal"


def summarize(rows: list[dict]) -> dict:
    """统计高番与普通分量冲突，根数用于覆盖而非显著性推断。"""
    by_mix = {}
    for mix in ("H", "M"):
        group = [row for row in rows if row["mix"] == mix]
        unrestricted = [row["delta"]["unrestricted"] for row in group]
        special = [row for row in group if _sign(row["delta"]["unrestricted"]["special"])
                   != "equal"]
        competing = [row for row in group
                     if (_sign(row["delta"]["unrestricted"]["plain"]) != "equal"
                     and _sign(row["delta"]["unrestricted"]["special"]) != "equal"
                     and _sign(row["delta"]["unrestricted"]["plain"])
                         != _sign(row["delta"]["unrestricted"]["special"]))
                     or (_sign(row["delta"]["unrestricted"]["special"]) != "equal"
                         and _sign(row["delta"]["unrestricted"]["total"])
                             != _sign(row["delta"]["unrestricted"]["plain"]))]
        by_mix[mix] = {
            "pairs": len(group), "independent_roots": len({row["root_index"] for row in group}),
            "special_nonzero_pairs": len(special),
            "special_nonzero_roots": len({row["root_index"] for row in special}),
            "plain_nonzero_pairs": sum(_sign(delta["plain"]) != "equal"
                                       for delta in unrestricted),
            "competing_pairs": len(competing),
            "unrestricted_special_sign": dict(sorted(Counter(
                _sign(delta["special"]) for delta in unrestricted).items())),
            "unrestricted_total_sign": dict(sorted(Counter(
                _sign(delta["total"]) for delta in unrestricted).items())),
            "both_modes_total_same_sign": sum(
                _sign(row["delta"]["restricted"]["total"])
                == _sign(row["delta"]["unrestricted"]["total"])
                for row in group),
            "maximum_arm_mode_elapsed_ms": max(
                row["arms"][arm]["modes"][mode]["elapsed_ms"]
                for row in group for arm in ("parent", "alternative")
                for mode in ("restricted", "unrestricted")),
            "maximum_arm_mode_leaves": max(
                row["arms"][arm]["modes"][mode]["legal_leaf_count"]
                for row in group for arm in ("parent", "alternative")
                for mode in ("restricted", "unrestricted")),
        }
    gate = all(item["special_nonzero_pairs"] >= 5
               and item["special_nonzero_roots"] >= 4
               and item["competing_pairs"] >= 2 for item in by_mix.values())
    return {"by_mix": by_mix, "settlement_probe_continue_gate": gate}


def main() -> None:
    """冻结选样；首对成本门后并行可恢复计算；仅完整时汇总。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-new-pairs", type=int, default=0)
    args = parser.parse_args()
    if not 1 <= args.workers <= 4:
        parser.error("workers 必须在 1..4")
    frozen = selected()
    g223.write_new(_project_file(_PROJECT_ROOT, OUT / "selection.json"), frozen)
    units = list(enumerate(frozen["pairs"], 1))
    pending = [(index, row) for index, row in units if not pair_path(index).exists()]
    if args.max_new_pairs > 0:
        pending = pending[:args.max_new_pairs]
    if pending:
        with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(run_pair, index, row): index
                       for index, row in pending}
            for completed, future in enumerate(concurrent.futures.as_completed(futures), 1):
                index = futures[future]
                result = future.result()
                if result["index"] != index:
                    raise ValueError("G227 结果索引错配")
                g223.write_new(pair_path(index), result)
                if result["status"] != "complete":
                    print(json.dumps({"status": result["status"], "index": index}), flush=True)
                    return
                if completed % 4 == 0 or completed == len(pending):
                    print(json.dumps({"new_pairs": completed,
                                      "planned_new_pairs": len(pending)}), flush=True)
    if any(not pair_path(index).exists() for index, _ in units):
        print(json.dumps({"status": "in_progress", "completed":
                          sum(pair_path(index).exists() for index, _ in units)}), flush=True)
        return
    rows = []
    hashes = {}
    for index, source in units:
        path = pair_path(index)
        row = json.loads(path.read_text(encoding="utf-8"))
        if (row["index"] != index or row["status"] != "complete"
                or any(row[key] != value for key, value in source.items())):
            raise ValueError("G227 已存教师与冻结选样不一致或曾超成本")
        hashes[path.name] = digest(path)
        rows.append(row)
    result = {"schema": "g227-multiwhite-near-ready-result/1",
              "selection_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "selection.json")),
              "pair_sha256": hashes, "pairs": len(rows),
              **summarize(rows),
              "boundary": "多白近听牌条件三摸生产结算，不是真实赛事价值。"}
    g223.write_new(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({"pairs": len(rows), **summarize(rows)},
                     ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
