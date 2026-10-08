#!/usr/bin/env python3
"""G140：枚举一次自然摸打后可进入普通型爆头的公开支持集。"""

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
import hashlib
import json
from pathlib import Path

import c31_action_layer_gap as c31
import g52_shared_horizon as g52
import g61_strong_draw_batch as g61
import g138_official_plain_baotou_opportunity as g138
import g140_plain_baotou_precursor_select as selected
from hangma_bot.hangma import action_families, hand_analysis, progression, settlement, special_rules
from hangma_bot.hangma.candidate_facts import _remaining
from hangma_bot.hangma.engine import _build_context
from hangma_bot.hangma.internal_types import TILE_ORDER, counts_from_tiles
from hangma_bot.hangma.public_tile_counts import count_public_tiles
from hangma_bot.kernel.actions import Discard, Tile
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g140-plain-baotou-precursor-20260928')
NATURAL_CODES = TILE_ORDER[:33]


def sha(path: Path) -> str:
    """冻结已选窗、程序和逐窗输入字节。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _plain_baotou_next_capacity(waiting: tuple[Tile, ...], meld_count: int,
                                public, new_public: Counter, missing_own_piao: int,
                                chain: int, piao: int, observation) -> int:
    """同一合法后继弃牌后，再下一次普通摸牌的真实规则条件胡容量。"""
    baotou = progression.baotou_after_discard(waiting, meld_count)
    if not baotou:
        return 0
    waiting_counts = counts_from_tiles(waiting)
    capacity = 0
    for code in TILE_ORDER:
        left = _remaining(code, waiting_counts, public, dict(new_public))
        if code == "白":
            left -= missing_own_piao
        if left < 0:
            raise ValueError("G140 链内飘白与公开容量矛盾")
        if left == 0:
            continue
        drawn = Tile(code)
        split = hand_analysis.win_split(waiting + (drawn,), meld_count)
        if split is None or split.branch != "平胡":
            continue
        second_baotou = progression.baotou_after_draw(
            baotou, waiting, meld_count, drawn, replacement=False)
        if not second_baotou or special_rules.you_cai_bi_kao_block(
                c31.RULE_CONFIG.you_cai_bi_kao, split, second_baotou):
            continue
        result = settlement.settle_win(
            split, chain, piao, second_baotou, c31.RULE_CONFIG.base_score,
            observation.seat, observation.dealer_seat)
        if not result.details or result.details[0] != "平胡" or "爆头" not in result.details:
            raise ValueError("G140 普通型爆头结算与规则形态不符")
        capacity += left
    return capacity


def precursor(observation, action_key: str) -> dict:
    """同一弃牌根按受限／不受限两包络枚举自然第一摸与合法后继。"""
    if observation.phase != "draw" or not action_key.startswith("discard:"):
        raise ValueError("G140 只支持合法普通摸打弃牌")
    if c31.RULE_CONFIG.you_cai_bi_kao:
        raise ValueError("G140 有财必拷响开启时停算")
    context = _build_context(observation)
    meld_count = len(observation.melds[observation.seat])
    code = action_key.split(":", 1)[1]
    root = g52._drop(context.full_hand(), code)
    if len(root) != 13 - 3 * meld_count:
        raise ValueError("G140 根弃后暗牌张数不符")
    root_counts = counts_from_tiles(root)
    public = count_public_tiles(observation)
    root_public = Counter({code: 1})
    root_baotou = progression.baotou_after_discard(root, meld_count)
    root_chain, root_piao = progression.chain_after_action(
        observation.rule_state.chain_count, observation.chain_piao,
        observation.rule_state.baotou, Discard(Tile(code)))
    if root_piao is None:
        raise ValueError("G140 根弃牌后链内飘数未知")
    own_visible_whites = sum(tile.code == "白" for tile in observation.discards[observation.seat])
    missing_own_piao = max(0, (observation.chain_piao or 0) - own_visible_whites)
    results = {"restricted": Counter(), "unrestricted": Counter()}
    first_success = {"restricted": [], "unrestricted": []}
    for first_code in NATURAL_CODES:
        first_cap = _remaining(first_code, root_counts, public, dict(root_public))
        if first_cap < 0:
            raise ValueError("G140 第一摸公开容量为负")
        if first_cap == 0:
            continue
        first_tile = Tile(first_code)
        first_full = root + (first_tile,)
        first_baotou = progression.baotou_after_draw(
            root_baotou, root, meld_count, first_tile, replacement=False)
        for restricted in (True, False):
            mode = "restricted" if restricted else "unrestricted"
            future = g52._first_context(context, root, first_code, restricted)
            legal, issues = action_families.discard_tile_codes(future)
            if issues or not legal:
                raise ValueError("G140 第一摸后合法弃牌资格未知")
            best = 0
            qualifying = 0
            white_retained_best = 0
            for discard in legal:
                waiting = g52._drop(first_full, discard)
                chain, piao = progression.chain_after_discard(
                    root_chain, root_piao, first_baotou, Tile(discard))
                if piao is None:
                    raise ValueError("G140 后继弃牌链内飘数未知")
                public_after = root_public.copy()
                public_after[discard] += 1
                next_cap = _plain_baotou_next_capacity(
                    waiting, meld_count, public, public_after, missing_own_piao,
                    chain, piao, observation)
                if next_cap > 0:
                    qualifying += 1
                    best = max(best, next_cap)
                    if counts_from_tiles(waiting)[33] == root_counts[33]:
                        white_retained_best = max(white_retained_best, next_cap)
            results[mode]["legal_successors"] += len(legal)
            results[mode]["qualifying_successors"] += qualifying
            if best > 0:
                first_success[mode].append(first_code)
                results[mode]["first_draw_codes"] += 1
                results[mode]["first_draw_public_capacity"] += first_cap
                results[mode]["second_support_mass_upper"] += first_cap * best
            if white_retained_best > 0:
                results[mode]["white_retained_first_draw_codes"] += 1
                results[mode]["white_retained_first_draw_public_capacity"] += first_cap
    return {mode: {**dict(counter), "first_draw_code_list": first_success[mode]}
            for mode, counter in results.items()}


def run_one(record: dict, source: dict) -> dict:
    """对冻结实际／父代两根同观察计算；逐项核对根规则事实。"""
    observation = observation_from_json(source["observation"])
    rules = c31.RULES.analyze(observation, value_limits=c31.VALUE_LIMITS)
    legal = {item.action_key: item for item in rules.legal_candidates}
    arms = {}
    for label, action in (("strong", record["actual_action"]),
                          ("parent", record["parent_action"])):
        candidate = legal.get(action)
        if candidate is None or candidate.facts is None:
            raise ValueError("G140 根弃牌已不合法")
        value, complete = g138.action_opportunity(candidate)
        if not complete or value["plain_baotou"] != 0:
            raise ValueError("G140 根动作已有即时普通型爆头或事实不全")
        facts = candidate.facts
        std = facts.standard_useful_tiles or ()
        arms[label] = {
            "action": action, "standard_shanten": facts.standard_shanten_after,
            "seven_pairs_shanten": facts.seven_pairs_shanten_after,
            "whites_held": sum(tile.code == "白" for tile in observation.my_hand)
                           - int(action == "discard:白"),
            "standard_useful_codes": len(std),
            "standard_useful_public_capacity": sum(tile.remaining_estimate for tile in std),
            "immediate_plain_capacity": value["plain"],
            "precursor": precursor(observation, action),
        }
    if (arms["strong"]["standard_shanten"] != arms["parent"]["standard_shanten"]
            or arms["strong"]["whites_held"] != arms["parent"]["whites_held"]):
        raise ValueError("G140 根动作不在冻结可比层")
    return {"identity": {key: record[key] for key in (
                "peer", "room", "game_id", "round_no", "draw_seq",
                "white_before", "standard_shanten_after", "selection_sha256")},
            "arms": arms}


def main() -> None:
    """逐窗原子落盘便于耗时计算后精确续跑，完成后才汇总。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-new", type=int, default=0)
    args = parser.parse_args()
    selection = json.loads(selected.OUT.read_text(encoding="utf-8"))
    if selection["selected_count"] != 63:
        raise ValueError("G140 冻结选样数漂移")
    stage_dir = _project_file(_PROJECT_ROOT, OUT / "stages")
    stage_dir.mkdir(parents=True, exist_ok=True)
    input_by_unit = {}
    added = 0
    for index, record in enumerate(selection["selected"]):
        target = stage_dir / f"window-{index:03d}.json"
        if target.exists():
            prior = json.loads(target.read_text(encoding="utf-8"))
            if prior["identity"]["selection_sha256"] != record["selection_sha256"]:
                raise ValueError("G140 已完成窗口身份漂移")
            continue
        if args.max_new and added >= args.max_new:
            break
        unit = record["peer"] + "/" + record["room"]
        if unit not in input_by_unit:
            source_path = g61.room_dir((record["peer"], record["room"])) / "windows.json"
            if sha(source_path) != selection["input_sha256"]["g61_windows_by_unit"][unit]:
                raise ValueError("G140 逐窗来源摘要漂移")
            input_by_unit[unit] = {
                (row["game_id"], row["round_no"], row["draw_seq"]): row
                for row in json.loads(source_path.read_text(encoding="utf-8"))["windows"]}
        source = input_by_unit[unit].get(
            (record["game_id"], record["round_no"], record["draw_seq"]))
        if source is None or (source["actual_action"], source["parent_top_action"]) != (
                record["actual_action"], record["parent_action"]):
            raise ValueError("G140 冻结目标窗不在来源或动作漂移")
        result = run_one(record, source)
        target.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True,
                                     indent=2) + "\n", encoding="utf-8")
        added += 1
        print(json.dumps({"completed": index, "peer": record["peer"],
                          "white": record["white_stratum"]}, ensure_ascii=False), flush=True)
    completed = sum((stage_dir / f"window-{index:03d}.json").exists()
                    for index in range(len(selection["selected"])))
    print(json.dumps({"completed": completed, "selected": len(selection["selected"]),
                      "added": added}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
