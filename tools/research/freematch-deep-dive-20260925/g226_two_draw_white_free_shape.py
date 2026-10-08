#!/usr/bin/env python3
"""G226：同宽换源后，两次本人普通摸牌的无白自然缺口分布。"""

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
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
import time

import c31_action_layer_gap as c31
import g196_three_draw_competing_route_pilot as g196
import g223_visible_multi_action_route as g223
import g224_g223_vector_replay as g224
import g225_equal_width_topology_teacher as g225
import g87_post_claim_score_trace as g87
from hangma_bot.hangma import hand_analysis
from hangma_bot.hangma.internal_types import TILE_INDEX, TILE_ORDER, counts_from_tiles
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
PLAN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G226-TWO-DRAW-WHITE-FREE-SHAPE-PLAN-2026-09-29.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g226-two-draw-white-free-shape-20260929')
MAX_SECONDS_PER_ARM = 30.0
MAX_LEAVES_PER_ARM = 3_000_000
EXPECTED_PAIRS = 24


class LimitExceeded(Exception):
    """离线成本达到预先冻结的停止线。"""


def digest(path: Path) -> str:
    """锁定文件原始字节，避免已看教师或阶段来源漂移。"""
    return sha256(path.read_bytes()).hexdigest()


def selected() -> dict:
    """从 G225 冻结选样只取一白二向听，不按已看教师方向筛选。"""
    source = g225.OUT / "selection.json"
    frozen = json.loads(source.read_text(encoding="utf-8"))
    if len(frozen["selected"]) != 48 or not frozen["outcome_blind"]:
        raise ValueError("G225 冻结选样规模或状态漂移")
    pairs = [(index, row) for index, row in enumerate(frozen["selected"], 1)
             if row["white_bucket"] == 1 and row["standard_shanten"] == 2]
    if (len(pairs) != EXPECTED_PAIRS
            or Counter(row["mix"] for _, row in pairs) != {"H": 12, "M": 12}
            or len({row["table_id"] for _, row in pairs}) != EXPECTED_PAIRS):
        raise ValueError("G226 目标层不是 H/M 各 12 个不同完整桌")
    return {
        "schema": "g226-two-draw-white-free-selection/1",
        "exploratory_same_sample": True,
        "source_sha256": {
            "plan": digest(PLAN), "script": digest(Path(__file__)),
            "g225_selection": digest(source),
            "g224_result": digest(g224.OUT / "result.json"),
        },
        "pairs": [{"g225_index": index, **row} for index, row in pairs],
        "boundary": "G225 已看层的结构量具探索；不是独立确认或赛事收益。",
    }


def _natural_need(hand: tuple[Tile, ...], meld_count: int) -> int:
    """复用生产普通型缺口数学，去掉白板的百搭贡献。"""
    counts = counts_from_tiles(hand)
    return hand_analysis._need_std(counts[:33], 0, 4 - meld_count, True)


def evaluate_arm(observation, action: str) -> dict:
    """用生产合法弃牌在两次条件本人摸牌后最小化无白自然缺口。"""
    started = time.perf_counter()
    search = g196.RouteSearch(observation, c31.RULE_CONFIG, action)
    initial_need = _natural_need(search.root, search.meld_count)
    if initial_need != 4 or counts_from_tiles(search.root)[TILE_INDEX["白"]] != 1:
        raise ValueError("G226 一白二向听目标的无白自然缺口不是 4")
    unknown = search.unseen
    total = sum(unknown)
    if total <= 2:
        raise ValueError("公开未知池不足两次条件摸牌")
    leaves = 0
    first_legal_branches = 0
    second_legal_branches = 0

    @lru_cache(maxsize=None)
    def terminal(waiting: tuple[Tile, ...], draw_index: int) -> int:
        """固定第二摸码后，只在生产合法非白次弃中取最小自然缺口。"""
        nonlocal leaves, second_legal_branches
        code = TILE_ORDER[draw_index]
        legal = [discard for discard in search._legal(waiting, code, False)
                 if discard != "白"]
        if not legal:
            raise ValueError("G226 第二摸后没有合法非白弃牌")
        second_legal_branches += len(legal)
        full = waiting + (Tile(code),)
        expected_whites = counts_from_tiles(waiting)[TILE_INDEX["白"]] + int(code == "白")
        best = None
        for discard in legal:
            leaves += 1
            if leaves > MAX_LEAVES_PER_ARM:
                raise LimitExceeded("次弃叶数超过 300 万")
            if leaves % 256 == 0 and time.perf_counter() - started > MAX_SECONDS_PER_ARM:
                raise LimitExceeded("单臂超过 30 秒")
            after = g196._drop(full, discard)
            if counts_from_tiles(after)[TILE_INDEX["白"]] != expected_whites:
                raise ValueError("G226 后继弃牌未保持白板")
            value = (_natural_need(after, search.meld_count), TILE_INDEX[discard])
            if best is None or value < best:
                best = value
        assert best is not None
        return best[0]

    distribution: Counter[int] = Counter()
    first_choices = []
    for first_index, capacity in enumerate(unknown):
        if capacity <= 0:
            continue
        first_code = TILE_ORDER[first_index]
        first_full = search.root + (Tile(first_code),)
        legal = [discard for discard in search._legal(search.root, first_code, False)
                 if discard != "白"]
        if not legal:
            raise ValueError("G226 第一摸后没有合法非白弃牌")
        first_legal_branches += len(legal)
        after_unknown = list(unknown)
        after_unknown[first_index] -= 1
        candidates = []
        for discard in legal:
            waiting = g196._drop(first_full, discard)
            conditional: Counter[int] = Counter()
            for second_index, second_capacity in enumerate(after_unknown):
                if second_capacity <= 0:
                    continue
                conditional[terminal(waiting, second_index)] += second_capacity
            if sum(conditional.values()) != total - 1:
                raise ValueError("G226 第二摸条件容量不守恒")
            need_mass = sum(need * mass for need, mass in conditional.items())
            good_mass = sum(mass for need, mass in conditional.items() if need <= 2)
            candidates.append((need_mass, -good_mass, TILE_INDEX[discard],
                               discard, conditional))
        best = min(candidates, key=lambda item: item[:3])
        conditional = best[4]
        for need, mass in conditional.items():
            distribution[need] += capacity * mass
        first_choices.append({"draw_code": first_code, "capacity": capacity,
                              "discard": best[3], "conditional_need_mass": best[0],
                              "conditional_need_le2_mass": -best[1]})
    denominator = total * (total - 1)
    if sum(distribution.values()) != denominator:
        raise ValueError("G226 两摸总容量不守恒")
    need_numerator = sum(need * mass for need, mass in distribution.items())
    good_numerator = sum(mass for need, mass in distribution.items() if need <= 2)
    return {
        "initial_natural_need": initial_need,
        "unknown_pool": total,
        "denominator": denominator,
        "distribution_numerator": {str(key): value
                                   for key, value in sorted(distribution.items())},
        "expected_need_numerator": need_numerator,
        "expected_need": need_numerator / denominator,
        "need_le2_numerator": good_numerator,
        "need_le2_ratio": good_numerator / denominator,
        "first_legal_branches": first_legal_branches,
        "second_legal_branches": second_legal_branches,
        "second_discard_leaves": leaves,
        "first_choices": first_choices,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "boundary": "无白自然缺口的合法不受限两摸条件包络，未模拟先鸣/他胡/真实牌墙。",
    }


def run_pair(row: dict) -> dict:
    """与 G224/G225 身份对账后计算同一观察的两条根弃牌。"""
    stage = g224.OUT / "stages" / row["source_stage"]
    if digest(stage) != row["source_stage_sha256"]:
        raise ValueError("G226 G224 阶段原文摘要漂移")
    roots = [item for item in json.loads(stage.read_text(encoding="utf-8"))["roots"]
             if item["root_decision_id"] == row["root_decision_id"]]
    if len(roots) != 1:
        raise ValueError("G226 行动前根窗不唯一")
    observation = observation_from_json(roots[0]["observation"])
    request = g87.request_for(observation)
    legal = {item.action_key: item for item in request.rules.legal_candidates}
    for action in (row["parent_action"], row["alternative_action"]):
        if action not in legal or legal[action].facts is None:
            raise ValueError("G226 根弃牌不在生产合法动作")
        stored = next(item for item in roots[0]["same_layer_options"]
                      if item["action"] == action)
        if (legal[action].facts.standard_shanten_after != 2
                or stored["standard_width"] != row["standard_width"]
                or g225.vector(stored) != tuple(sorted(
                    (item.code, item.remaining_estimate)
                    for item in legal[action].facts.standard_useful_tiles
                    if item.remaining_estimate > 0))):
            raise ValueError("G226 生产同层和逐码事实与 G224 不一致")
    prior = json.loads(g225.pair_path(row["g225_index"]).read_text(encoding="utf-8"))
    if any(prior[key] != row[key] for key in row if key != "g225_index"):
        raise ValueError("G226 G225 冻结身份漂移")
    if any(prior["arms"][label]["hold_depth2"] != 0
           for label in ("parent", "alternative")):
        raise ValueError("G226 探索层存在两摸提前胡终点")
    arms = {label: evaluate_arm(observation, action)
            for label, action in (("parent", row["parent_action"]),
                                  ("alternative", row["alternative_action"]))}
    if arms["parent"]["unknown_pool"] != arms["alternative"]["unknown_pool"]:
        raise ValueError("G226 同窗公开未知池不一致")
    difference = arms["alternative"]["expected_need"] - arms["parent"]["expected_need"]
    sign = "negative" if difference < -1e-12 else "positive" if difference > 1e-12 else "equal"
    return {"schema": "g226-two-draw-white-free-pair/1", **row,
            "arms": arms, "delta_expected_need": difference,
            "delta_need_le2_ratio": (arms["alternative"]["need_le2_ratio"]
                                     - arms["parent"]["need_le2_ratio"]),
            "expected_need_sign": sign,
            "g217_projection_natural_score_delta": prior["delta_g217_natural_score"],
            "g225_hold_depth3_ratio_delta": prior["delta_hold_depth3_ratio"]}


def pair_path(index: int) -> Path:
    """一对一份可续跑证据，不覆盖已经计算的量具值。"""
    return _project_file(_PROJECT_ROOT, OUT / "pairs" / f"pair-{index:03d}.json")


def summarize(rows: list[dict]) -> dict:
    """按异质对手池和独立牌山根报告覆盖，不把窗口当统计独立单位。"""
    by_mix = {}
    for mix in ("H", "M"):
        group = [item for item in rows if item["mix"] == mix]
        nonzero = [item for item in group if item["expected_need_sign"] != "equal"]
        by_mix[mix] = {
            "pairs": len(group),
            "independent_roots": len({item["root_index"] for item in group}),
            "sign": dict(sorted(Counter(item["expected_need_sign"] for item in group).items())),
            "nonzero_pairs": len(nonzero),
            "nonzero_roots": len({item["root_index"] for item in nonzero}),
            "g225_equal_but_two_draw_diff": sum(
                item["g225_hold_depth3_ratio_delta"] == 0 for item in nonzero),
            "mean_delta_expected_need": sum(item["delta_expected_need"] for item in group)
                                        / len(group),
            "mean_delta_need_le2_ratio": sum(item["delta_need_le2_ratio"] for item in group)
                                         / len(group),
            "maximum_arm_elapsed_ms": max(item["arms"][label]["elapsed_ms"]
                                          for item in group for label in ("parent", "alternative")),
            "maximum_arm_leaves": max(item["arms"][label]["second_discard_leaves"]
                                      for item in group for label in ("parent", "alternative")),
        }
    gate = all(item["nonzero_pairs"] >= 5 and item["nonzero_roots"] >= 4
               and item["g225_equal_but_two_draw_diff"] >= 1
               for item in by_mix.values())
    return {"by_mix": by_mix, "measurement_continue_gate": gate}


def main() -> None:
    """先冻结 G225 子层身份，再计算并保存可续跑的量具结果。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-new-pairs", type=int, default=0)
    args = parser.parse_args()
    if not 1 <= args.workers <= 4:
        parser.error("workers 必须在 1..4")
    frozen = selected()
    g223.write_new(_project_file(_PROJECT_ROOT, OUT / "selection.json"), frozen)
    pending = [row for row in frozen["pairs"] if not pair_path(row["g225_index"]).exists()]
    if args.max_new_pairs > 0:
        pending = pending[:args.max_new_pairs]
    if pending:
        with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(run_pair, row): row["g225_index"] for row in pending}
            for completed, future in enumerate(concurrent.futures.as_completed(futures), 1):
                index = futures[future]
                value = future.result()
                if value["g225_index"] != index:
                    raise ValueError("G226 完成结果与冻结索引错配")
                g223.write_new(pair_path(index), value)
                if completed % 4 == 0 or completed == len(pending):
                    print(json.dumps({"new_pairs": completed, "planned": len(pending)}), flush=True)
    if any(not pair_path(row["g225_index"]).exists() for row in frozen["pairs"]):
        print(json.dumps({"status": "in_progress", "completed":
                          sum(pair_path(row["g225_index"]).exists()
                              for row in frozen["pairs"])}), flush=True)
        return
    rows = []
    hashes = {}
    for source in frozen["pairs"]:
        path = pair_path(source["g225_index"])
        row = json.loads(path.read_text(encoding="utf-8"))
        if any(row[key] != value for key, value in source.items()):
            raise ValueError("G226 已存结果与冻结身份不一致")
        hashes[path.name] = digest(path)
        rows.append(row)
    result = {"schema": "g226-two-draw-white-free-result/1",
              "selection_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "selection.json")),
              "pair_sha256": hashes, "pairs": len(rows),
              **summarize(rows),
              "boundary": "G225 已看层的无白自然牌形条件量具；非真实墙、对手、结算或赛事收益。"}
    g223.write_new(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({"pairs": len(rows), **summarize(rows)},
                     ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
