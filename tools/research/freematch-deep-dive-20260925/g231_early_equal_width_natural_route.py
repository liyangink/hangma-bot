#!/usr/bin/env python3
"""G231：一白三向听同宽换源后的合法两摸自然缺口分布。"""

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
from collections import Counter, defaultdict
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
import time

import c31_action_layer_gap as c31
import g196_three_draw_competing_route_pilot as g196
import g224_g223_vector_replay as g224
import g225_equal_width_topology_teacher as g225
import g87_post_claim_score_trace as g87
from hangma_bot.hangma import hand_analysis
from hangma_bot.hangma.internal_types import TILE_INDEX, TILE_ORDER, counts_from_tiles
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
PLAN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G231-EARLY-EQUAL-WIDTH-NATURAL-ROUTE-PREREG-2026-09-29.md')
SOURCE = g224.OUT
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g231-early-equal-width-natural-route-20260929')
MAX_SECONDS_PER_ARM = 10.0
MAX_LEAVES_PER_ARM = 3_000_000


class LimitExceeded(Exception):
    """离线量具超过事前成本门，不把截断树当完整值。"""


def digest(path: Path) -> str:
    """返回原字节 SHA-256 以绑定冻结输入与程序。"""
    return sha256(path.read_bytes()).hexdigest()


def write_new(path: Path, data: dict) -> None:
    """冻结证据只创建一次；重复请求不得覆盖已有计算。"""
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8")


def vector(option: dict) -> tuple[tuple[str, int], ...]:
    """生产普通型逐牌正公开容量，用于同宽不同源身份核验。"""
    return g225.vector(option)


def eligible_alternative(root: dict) -> dict | None:
    """只用行动前事实，在同层同宽动作中确定唯一备选。"""
    parent_key = root["root_action"]
    if (root["white_bucket"] != 1 or parent_key == "discard:白"
            or root["root_shape"]["standard_shanten_after"] != 3
            or root["root_shape"]["natural_need_after"] != 5):
        return None
    options = {option["action"]: option for option in root["same_layer_options"]}
    parent = options.get(parent_key)
    if parent is None:
        raise ValueError("G224 父代动作未在同层合法弃牌表")
    alternatives = []
    for option in options.values():
        if (option["action"] in (parent_key, "discard:白")
                or option["white_after"] != 1
                or option["standard_shanten_after"] != 3
                or option["standard_width"] != parent["standard_width"]
                or vector(option) == vector(parent)
                or not 0 <= option["parent_score_gap"] <= 4):
            continue
        seven = parent["seven_pairs_shanten_after"]
        other = option["seven_pairs_shanten_after"]
        if seven is not None and (other is None or other > seven):
            continue
        alternatives.append(option)
    if not alternatives:
        return None
    return min(alternatives, key=lambda item: (item["parent_score_gap"], item["action"]))


def select() -> dict:
    """全量扫描 G224 行动前窗口，每桌首窗且不读取后续路径/结算。"""
    result_path = SOURCE / "result.json"
    source = json.loads(result_path.read_text(encoding="utf-8"))
    if (source.get("schema") != "g224-g223-vector-replay-result/1"
            or source.get("complete_stages") != 64
            or len(source.get("stage_sha256") or {}) != 64):
        raise ValueError("G224 父代来源未完整冻结")
    by_table = {}
    for stage_name, expected in sorted(source["stage_sha256"].items()):
        path = SOURCE / "stages" / stage_name
        if digest(path) != expected:
            raise ValueError("G224 阶段原文摘要漂移")
        stage = json.loads(path.read_text(encoding="utf-8"))
        for root in stage["roots"]:
            alternate = eligible_alternative(root)
            if alternate is None:
                continue
            observation = root["observation"]
            key = (stage["mix"], stage["root_index"], root["table_id"])
            row = {
                "mix": stage["mix"], "root_index": stage["root_index"],
                "table_id": root["table_id"], "round_no": root["round_no"],
                "snapshot_seq": observation["snapshot_seq"],
                "root_decision_id": root["root_decision_id"],
                "source_stage": stage_name, "source_stage_sha256": expected,
                "parent_action": root["root_action"],
                "alternate_action": alternate["action"],
                "parent_score_gap": alternate["parent_score_gap"],
                "standard_width": root["root_shape"]["standard_width"],
                "parent_vector": vector(root["root_shape"]),
                "alternate_vector": vector(alternate),
                "natural_need_after": root["root_shape"]["natural_need_after"],
            }
            prior = by_table.get(key)
            if prior is None or ((row["round_no"], row["snapshot_seq"], row["root_decision_id"])
                                 < (prior["round_no"], prior["snapshot_seq"], prior["root_decision_id"])):
                by_table[key] = row
    rows = sorted(by_table.values(), key=lambda row:
                  (row["mix"], row["root_index"], row["table_id"],
                   row["round_no"], row["snapshot_seq"]))
    by_mix = {mix: {"pairs": sum(row["mix"] == mix for row in rows),
                    "roots": len({row["root_index"] for row in rows if row["mix"] == mix})}
              for mix in ("H", "M")}
    if min(item["pairs"] for item in by_mix.values()) < 20 or min(item["roots"] for item in by_mix.values()) < 6:
        raise ValueError("G231 行动前同宽选样覆盖不足")
    return {
        "schema": "g231-early-equal-width-selection/1",
        "outcome_blind": True,
        "source_sha256": {"plan": digest(PLAN), "script": digest(Path(__file__)),
                          "g224_result": digest(result_path)},
        "by_mix": by_mix, "selected": rows,
        "boundary": "仅已执行父代的行动前可见事实；每完整桌首个合格窗，不按后来胡牌、路线或本项量具筛选。",
    }


def natural_need(hand: tuple[Tile, ...], meld_count: int) -> int:
    """白板不作百搭，只复用生产普通型数学求解器。"""
    return hand_analysis._need_std(counts_from_tiles(hand)[:33], 0,
                                   4 - meld_count, True)


def evaluate_arm(observation, action: str) -> dict:
    """枚举两次条件本人摸牌及其合法保白弃牌，最小化自然缺口。"""
    started = time.perf_counter()
    search = g196.RouteSearch(observation, c31.RULE_CONFIG, action)
    initial = natural_need(search.root, search.meld_count)
    if initial != 5 or counts_from_tiles(search.root)[TILE_INDEX["白"]] != 1:
        raise ValueError("G231 根弃后不是一白、无白自然缺口五")
    unknown = search.unseen
    total = sum(unknown)
    if total <= 2:
        raise ValueError("公开未知池不足两次条件摸牌")
    leaves = 0
    first_branches = 0
    second_branches = 0

    @lru_cache(maxsize=None)
    def terminal(waiting: tuple[Tile, ...], draw_index: int) -> int:
        """第二摸后从规则允许的非白弃牌中取最小自然缺口。"""
        nonlocal leaves, second_branches
        code = TILE_ORDER[draw_index]
        legal = [discard for discard in search._legal(waiting, code, False)
                 if discard != "白"]
        if not legal:
            raise ValueError("第二次本人摸牌后没有合法保白弃牌")
        second_branches += len(legal)
        full = waiting + (Tile(code),)
        expected_whites = counts_from_tiles(waiting)[TILE_INDEX["白"]] + int(code == "白")
        best = None
        for discard in legal:
            leaves += 1
            if leaves > MAX_LEAVES_PER_ARM:
                raise LimitExceeded("单臂次弃叶数超限")
            if leaves % 256 == 0 and time.perf_counter() - started > MAX_SECONDS_PER_ARM:
                raise LimitExceeded("单臂时间超限")
            after = g196._drop(full, discard)
            if counts_from_tiles(after)[TILE_INDEX["白"]] != expected_whites:
                raise ValueError("后继弃牌未保持白板")
            value = (natural_need(after, search.meld_count), TILE_INDEX[discard])
            if best is None or value < best:
                best = value
        assert best is not None
        return best[0]

    distribution: Counter[int] = Counter()
    for first_index, capacity in enumerate(unknown):
        if capacity <= 0:
            continue
        code = TILE_ORDER[first_index]
        full = search.root + (Tile(code),)
        legal = [discard for discard in search._legal(search.root, code, False)
                 if discard != "白"]
        if not legal:
            raise ValueError("第一次本人摸牌后没有合法保白弃牌")
        first_branches += len(legal)
        after_unknown = list(unknown)
        after_unknown[first_index] -= 1
        candidates = []
        for discard in legal:
            waiting = g196._drop(full, discard)
            conditional: Counter[int] = Counter()
            for second_index, count in enumerate(after_unknown):
                if count > 0:
                    conditional[terminal(waiting, second_index)] += count
            if sum(conditional.values()) != total - 1:
                raise ValueError("第二次摸牌公开容量不守恒")
            need_mass = sum(need * mass for need, mass in conditional.items())
            good_mass = sum(mass for need, mass in conditional.items() if need <= 3)
            candidates.append((need_mass, -good_mass, TILE_INDEX[discard], conditional))
        chosen = min(candidates, key=lambda item: item[:3])
        for need, mass in chosen[3].items():
            distribution[need] += capacity * mass
    denominator = total * (total - 1)
    if sum(distribution.values()) != denominator:
        raise ValueError("两次摸牌总容量不守恒")
    numerator = sum(need * mass for need, mass in distribution.items())
    near = sum(mass for need, mass in distribution.items() if need <= 3)
    return {
        "initial_natural_need": initial, "unknown_pool": total,
        "denominator": denominator,
        "distribution_numerator": {str(need): mass for need, mass in sorted(distribution.items())},
        "expected_need_numerator": numerator,
        "expected_need": numerator / denominator,
        "need_le3_numerator": near, "need_le3_ratio": near / denominator,
        "first_legal_branches": first_branches,
        "second_legal_branches": second_branches,
        "second_discard_leaves": leaves,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "boundary": "合法保白、未来抓打不受限的两次本人摸牌条件包络；不含实际对手和赛后墙。",
    }


def evaluate_pair(row: dict) -> dict:
    """同窗两臂先核 G224 行动前事实，再打开两摸条件树。"""
    stage = SOURCE / "stages" / row["source_stage"]
    if digest(stage) != row["source_stage_sha256"]:
        raise ValueError("G224 目标阶段摘要漂移")
    roots = [item for item in json.loads(stage.read_text(encoding="utf-8"))["roots"]
             if item["root_decision_id"] == row["root_decision_id"]]
    if len(roots) != 1:
        raise ValueError("G231 目标根窗不唯一")
    root = roots[0]
    if root["table_id"] != row["table_id"] or root["round_no"] != row["round_no"]:
        raise ValueError("G231 目标完整桌身份漂移")
    observation = observation_from_json(root["observation"])
    request = g87.request_for(observation)
    legal = {item.action_key: item for item in request.rules.legal_candidates}
    for key, expected in ((row["parent_action"], row["parent_vector"]),
                          (row["alternate_action"], row["alternate_vector"])):
        item = legal.get(key)
        if item is None or item.facts is None or item.facts.standard_shanten_after != 3:
            raise ValueError("G231 根弃牌当前生产规则身份/向听不符")
        actual = tuple(sorted((tile.code, tile.remaining_estimate)
                              for tile in item.facts.standard_useful_tiles
                              if tile.remaining_estimate > 0))
        if actual != tuple(tuple(entry) for entry in expected):
            raise ValueError("G231 生产逐码有效牌与 G224 冻结向量不同")
    arms = {label: evaluate_arm(observation, action)
            for label, action in (("parent", row["parent_action"]),
                                  ("alternate", row["alternate_action"]))}
    if arms["parent"]["unknown_pool"] != arms["alternate"]["unknown_pool"]:
        raise ValueError("同窗两臂公开未知池不同")
    delta = arms["alternate"]["expected_need"] - arms["parent"]["expected_need"]
    return {
        "schema": "g231-early-equal-width-pair/1", **row,
        "arms": arms, "delta_expected_need": delta,
        "delta_need_le3_ratio": (arms["alternate"]["need_le3_ratio"]
                                 - arms["parent"]["need_le3_ratio"]),
        "expected_need_sign": ("improve" if delta < -1e-12 else
                               "worse" if delta > 1e-12 else "equal"),
    }


def measure() -> None:
    """选样已落盘后才枚举合法未来；完整失败不吞成零值。"""
    path = _project_file(_PROJECT_ROOT, OUT / "selection.json")
    selected = json.loads(path.read_text(encoding="utf-8"))
    if (selected.get("schema") != "g231-early-equal-width-selection/1"
            or selected["source_sha256"]["plan"] != digest(PLAN)
            or selected["source_sha256"]["script"] != digest(Path(__file__))
            or selected["source_sha256"]["g224_result"] != digest(SOURCE / "result.json")):
        raise ValueError("G231 冻结选样或计算源码漂移")
    if (_project_file(_PROJECT_ROOT, OUT / "result.json")).exists():
        raise FileExistsError("G231 总结果已存在")
    rows = []
    for index, row in enumerate(selected["selected"], 1):
        pair_path = _project_file(_PROJECT_ROOT, OUT / "pairs" / f"pair-{index:03d}.json")
        if pair_path.exists():
            item = json.loads(pair_path.read_text(encoding="utf-8"))
            if any(item.get(key) != value for key, value in row.items()):
                raise ValueError("G231 已有单对结果与冻结选样不符")
        else:
            item = evaluate_pair(row)
            write_new(pair_path, item)
        rows.append(item)
        if index % 10 == 0:
            print(json.dumps({"pairs_completed": index, "total": len(selected["selected"])}), flush=True)
    by_mix = {}
    for mix in ("H", "M"):
        group = [row for row in rows if row["mix"] == mix]
        changed = [row for row in group if row["expected_need_sign"] != "equal"]
        improved = [row for row in group if row["delta_expected_need"] <= -0.005]
        by_mix[mix] = {
            "pairs": len(group), "roots": len({row["root_index"] for row in group}),
            "direction": dict(sorted(Counter(row["expected_need_sign"] for row in group).items())),
            "nonzero_pairs": len(changed),
            "nonzero_roots": len({row["root_index"] for row in changed}),
            "material_improved_pairs": len(improved),
            "need_le3_improved_pairs": sum(row["delta_need_le3_ratio"] > 1e-12 for row in group),
            "mean_delta_expected_need": sum(row["delta_expected_need"] for row in group) / len(group),
            "min_delta_expected_need": min(row["delta_expected_need"] for row in group),
            "max_delta_expected_need": max(row["delta_expected_need"] for row in group),
            "max_elapsed_ms": max(arm["elapsed_ms"] for row in group for arm in row["arms"].values()),
        }
    gate = all(by_mix[mix]["nonzero_pairs"] >= 8
               and by_mix[mix]["nonzero_roots"] >= 5
               and by_mix[mix]["material_improved_pairs"] >= 4
               and by_mix[mix]["need_le3_improved_pairs"] > 0
               for mix in ("H", "M"))
    result = {
        "schema": "g231-early-equal-width-natural-route-result/1",
        "selection_sha256": digest(path), "script_sha256": digest(Path(__file__)),
        "by_mix": by_mix, "continue_gate_pass": gate,
        "pairs": [{"index": index, "sha256": digest(_project_file(_PROJECT_ROOT, OUT / "pairs" / f"pair-{index:03d}.json"))}
                  for index in range(1, len(rows) + 1)],
        "boundary": "同一行动前可见状态的条件两摸自然缺口，不是实际墙、对手先胡或赛事收益。",
    }
    write_new(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({"by_mix": by_mix, "continue_gate_pass": gate},
                     ensure_ascii=False, sort_keys=True), flush=True)


def main() -> None:
    """先 select 冻结行动前来源，再独立调用 measure 打开条件树。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("select", "measure"))
    mode = parser.parse_args().mode
    if mode == "select":
        selected = select()
        write_new(_project_file(_PROJECT_ROOT, OUT / "selection.json"), selected)
        print(json.dumps(selected["by_mix"], ensure_ascii=False, sort_keys=True), flush=True)
    else:
        measure()


if __name__ == "__main__":
    main()
