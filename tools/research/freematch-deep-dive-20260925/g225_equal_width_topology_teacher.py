#!/usr/bin/env python3
"""G225：固定同宽换源动作对，比较保白三摸结构教师与两步合法投影。"""

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

import g196_three_draw_competing_route_pilot as g196
import g217_two_step_natural_route_policy as projection
import g223_visible_multi_action_route as g223
import g224_g223_vector_replay as g224
import g25_white_retained_three_draw as hold
import g7_three_self_draw_probe as free
import g87_post_claim_score_trace as g87
from hangma_bot.hangma.internal_types import counts_from_tiles
from hangma_bot.hangma.public_tile_counts import count_unseen_tiles
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G225-EQUAL-WIDTH-TOPOLOGY-TEACHER-PREREG-2026-09-29.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g225-equal-width-topology-teacher-20260929')
SALT = "g225-equal-width-topology-v1"
QUOTA = {(1, 1): 6, (1, 2): 12, (2, 1): 3, (2, 2): 3}
ORDER = ((2, 2), (2, 1), (1, 1), (1, 2))


def digest(path: Path) -> str:
    """锁定来源、程序及冻结选样的原始字节。"""
    return sha256(path.read_bytes()).hexdigest()


def vector(option: dict) -> tuple[tuple[str, int], ...]:
    """只比较公开正容量逐码事实，不把零容量牌计作可进来源。"""
    return tuple(sorted((entry["code"], entry["public_capacity"])
                        for entry in option["standard_useful_tiles"]
                        if entry["public_capacity"] > 0))


def _load_roots() -> list[tuple[Path, dict, dict]]:
    """逐阶段核 G224 补证摘要；不读 G223 后续路线或终局做选样。"""
    result_path = g224.OUT / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if result["complete_tables_verified"] != 128 or result["probe_windows"] != 2191:
        raise ValueError("G224 冻结补证规模漂移")
    roots = []
    for name, expected_sha in sorted(result["stage_sha256"].items()):
        path = g224.OUT / "stages" / name
        if digest(path) != expected_sha:
            raise ValueError("G224 补证阶段摘要漂移")
        stage = json.loads(path.read_text(encoding="utf-8"))
        for root in stage["roots"]:
            roots.append((path, stage, root))
    if len(roots) != 2191:
        raise ValueError("G224 根窗数与各阶段不守恒")
    return roots


def selected() -> dict:
    """仅用行动前事实固定动作对及每桌最多一窗；不看教师值。"""
    options = []
    for path, stage, root in _load_roots():
        white = root["white_bucket"]
        shanten = root["root_shape"]["standard_shanten_after"]
        if (white, shanten) not in QUOTA or root["root_action"] == "discard:白":
            continue
        parent = next(item for item in root["same_layer_options"]
                      if item["action"] == root["root_action"])
        candidates = [item for item in root["same_layer_options"]
                      if item["action"] != parent["action"]
                      and item["action"] != "discard:白"
                      and item["standard_width"] == parent["standard_width"]
                      and item["seven_pairs_shanten_after"]
                          == parent["seven_pairs_shanten_after"]
                      and vector(item) != vector(parent)
                      and type(item["parent_score_gap"]) in (int, float)
                      and 0 <= item["parent_score_gap"] <= 4]
        if not candidates:
            continue
        chosen = min(candidates, key=lambda item:
                     (item["parent_score_gap"], item["action"]))
        options.append({
            "mix": stage["mix"], "root_index": stage["root_index"],
            "start_seat": stage["start_seat"],
            "source_stage": path.name, "source_stage_sha256": digest(path),
            "root_decision_id": root["root_decision_id"],
            "table_id": root["table_id"], "round_no": root["round_no"],
            "white_bucket": white, "standard_shanten": shanten,
            "parent_action": parent["action"],
            "alternative_action": chosen["action"],
            "parent_score_gap": chosen["parent_score_gap"],
            "standard_width": parent["standard_width"],
        })
    picked = []
    used_tables = set()
    coverage = {}
    for mix in g223.MIXES:
        for stratum in ORDER:
            candidates = sorted(
                (row for row in options if row["mix"] == mix
                 and (row["white_bucket"], row["standard_shanten"]) == stratum),
                key=lambda row: sha256((SALT + ":" + row["root_decision_id"])
                                       .encode("utf-8")).hexdigest())
            chosen = []
            for row in candidates:
                if row["table_id"] in used_tables:
                    continue
                chosen.append(row)
                used_tables.add(row["table_id"])
                if len(chosen) == QUOTA[stratum]:
                    break
            coverage[f"{mix}_white{stratum[0]}_standard{stratum[1]}"] = {
                "available_windows": len(candidates), "selected": len(chosen),
                "independent_roots": len({row["root_index"] for row in chosen})}
            picked.extend(chosen)
    if len(picked) != 48 or len({row["table_id"] for row in picked}) != 48:
        raise ValueError("G225 事前 48 对动作配额不足或每桌选样重复")
    return {
        "schema": "g225-equal-width-selection/1",
        "outcome_blind": True, "salt": SALT,
        "quota": {f"white{w}_standard{s}": count for (w, s), count in QUOTA.items()},
        "source_sha256": {str(path.relative_to(g223.ROOT)): digest(path)
                          for path in (PREREG, Path(__file__),
                                       g224.OUT / "manifest.json",
                                       g224.OUT / "result.json")},
        "coverage": coverage, "selected": picked,
        "boundary": "同宽换源的行动前选样；教师值和父代后继未参与选择。",
    }


def _sign(value: float, *, epsilon: float = 1e-12) -> str:
    return "positive" if value > epsilon else "negative" if value < -epsilon else "equal"


def run_pair(index: int, row: dict) -> dict:
    """生产规则对账后，条件未知池算保白三摸与现有两步投影。"""
    started = time.perf_counter()
    stage_path = g224.OUT / "stages" / row["source_stage"]
    if digest(stage_path) != row["source_stage_sha256"]:
        raise ValueError("G225 所选根窗来源摘要漂移")
    roots = [item for item in json.loads(stage_path.read_text(encoding="utf-8"))["roots"]
             if item["root_decision_id"] == row["root_decision_id"]]
    if len(roots) != 1:
        raise ValueError("G225 所选根窗不唯一")
    root = roots[0]
    observation = observation_from_json(root["observation"])
    request = g87.request_for(observation)
    legal = {item.action_key: item for item in request.rules.legal_candidates}
    unseen = count_unseen_tiles(observation)
    if any(type(value) is not int or value < 0 for value in unseen):
        raise ValueError("G225 公开未知牌容量不完整")
    unseen = tuple(unseen)
    n = sum(unseen)
    melds = len(observation.melds[observation.seat])
    full = g196._build_context(observation).full_hand()
    arms = {}
    for label, action in (("parent", row["parent_action"]),
                          ("alternative", row["alternative_action"])):
        if action not in legal or legal[action].facts is None:
            raise ValueError("G225 根动作不是当前生产规则合法弃牌")
        fact = legal[action].facts
        stored = next(item for item in root["same_layer_options"]
                      if item["action"] == action)
        if (fact.standard_shanten_after != row["standard_shanten"]
                or stored["standard_width"] != row["standard_width"]
                or tuple(sorted((item.code, item.remaining_estimate)
                                for item in fact.standard_useful_tiles
                                if item.remaining_estimate > 0)) != vector(stored)):
            raise ValueError("G225 原始生产逐码事实与 G224 补证不一致")
        hand = g196._drop(full, action.split(":", 1)[1])
        counts = counts_from_tiles(hand)
        if counts[hold.WHITE_INDEX] != stored["white_after"]:
            raise ValueError("G225 弃后白板实持数漂移")
        held = {depth: hold.favorable_hold_white(counts, unseen, melds, depth)
                for depth in (2, 3)}
        free_three = free.favorable(counts, unseen, melds, 3)
        if held[3] > free_three:
            raise ValueError("G225 禁弃白三摸容量超过自由弃白容量")
        projected = projection.project(request, action)
        arms[label] = {
            "hold_depth2": held[2], "hold_depth3": held[3],
            "free_depth3": free_three,
            "hold_depth2_ratio": held[2] / free.falling(n, 2),
            "hold_depth3_ratio": held[3] / free.falling(n, 3),
            "free_depth3_ratio": free_three / free.falling(n, 3),
            "g217_unrestricted_natural_score": projected.unrestricted.natural_score,
            "g217_unrestricted_natural_need": projected.unrestricted.natural_need,
            "g217_unrestricted_natural_progress_capacity":
                projected.unrestricted.natural_progress_capacity,
        }
    hold.favorable_hold_white.cache_clear()
    free.favorable.cache_clear()
    free.summary.cache_clear()
    delta_hold = (arms["alternative"]["hold_depth3_ratio"]
                  - arms["parent"]["hold_depth3_ratio"])
    delta_projection = (arms["alternative"]["g217_unrestricted_natural_score"]
                        - arms["parent"]["g217_unrestricted_natural_score"])
    delta_free = (arms["alternative"]["free_depth3_ratio"]
                  - arms["parent"]["free_depth3_ratio"])
    return {"schema": "g225-equal-width-pair/1", "index": index,
            **row, "unknown_pool": n, "arms": arms,
            "delta_hold_depth3_ratio": delta_hold,
            "delta_free_depth3_ratio": delta_free,
            "delta_g217_natural_score": delta_projection,
            "hold_sign": _sign(delta_hold), "free_sign": _sign(delta_free),
            "projection_sign": _sign(delta_projection, epsilon=1e-8),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
            "boundary": "条件公开未知池的理想化三摸能力，不是实墙概率或本座净积分。"}


def summarize(rows: list[dict]) -> dict:
    """按池和牌形格分层；48 对相关窗口不充当独立根。"""
    result = {}
    for mix in g223.MIXES:
        group = [row for row in rows if row["mix"] == mix]
        nonzero = [row for row in group if row["hold_sign"] != "equal"]
        result[mix] = {
            "pairs": len(group),
            "independent_roots": len({row["root_index"] for row in group}),
            "hold_depth3_sign": dict(sorted(Counter(row["hold_sign"] for row in group).items())),
            "free_depth3_sign": dict(sorted(Counter(row["free_sign"] for row in group).items())),
            "g217_projection_sign": dict(sorted(Counter(
                row["projection_sign"] for row in group).items())),
            "nonzero_hold_pairs": len(nonzero),
            "projection_matches_nonzero_hold": sum(
                row["projection_sign"] == row["hold_sign"] for row in nonzero),
            "nonzero_hold_independent_roots": len({row["root_index"] for row in nonzero}),
            "by_white_shanten": {
                f"white{white}_standard{shanten}": dict(sorted(Counter(
                    row["hold_sign"] for row in group
                    if row["white_bucket"] == white
                    and row["standard_shanten"] == shanten).items()))
                for white, shanten in ORDER},
        }
    continue_gate = all(
        value["nonzero_hold_pairs"] >= 8
        and value["nonzero_hold_independent_roots"] >= 5
        and value["projection_matches_nonzero_hold"] / value["nonzero_hold_pairs"] >= .6
        for value in result.values())
    return {"by_mix": result, "g217_tie_break_continue_gate": continue_gate}


def pair_path(index: int) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "pairs" / f"pair-{index:03d}.json")


def main() -> None:
    """先冻结 48 对选择，再逐对保存可续跑教师，最后汇总。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-new-pairs", type=int, default=0)
    args = parser.parse_args()
    if not 1 <= args.workers <= 4:
        parser.error("workers 必须在 1..4")
    frozen = selected()
    g223.write_new(_project_file(_PROJECT_ROOT, OUT / "selection.json"), frozen)
    units = list(enumerate(frozen["selected"], 1))
    pending = [(index, row) for index, row in units if not pair_path(index).exists()]
    if args.max_new_pairs > 0:
        pending = pending[:args.max_new_pairs]
    if pending:
        with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(run_pair, index, row): index
                       for index, row in pending}
            for completed, future in enumerate(concurrent.futures.as_completed(futures), 1):
                index = futures[future]
                value = future.result()
                if value["index"] != index:
                    raise ValueError("G225 相关动作对索引错配")
                g223.write_new(pair_path(index), value)
                if completed % 8 == 0 or completed == len(pending):
                    print(json.dumps({"new_pairs": completed,
                                      "planned_new_pairs": len(pending)}), flush=True)
    if any(not pair_path(index).exists() for index, _ in units):
        print(json.dumps({"status": "in_progress",
                          "pairs_completed": sum(pair_path(index).exists()
                                                 for index, _ in units)}), flush=True)
        return
    rows = []
    hashes = {}
    for index, source in units:
        path = pair_path(index)
        row = json.loads(path.read_text(encoding="utf-8"))
        if row["index"] != index or any(row[key] != source[key] for key in source):
            raise ValueError("G225 已存教师与冻结选样身份不符")
        hashes[path.name] = digest(path)
        rows.append(row)
    elapsed = sorted(row["elapsed_ms"] for row in rows)
    result = {
        "schema": "g225-equal-width-topology-result/1",
        "selection_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "selection.json")),
        "pair_sha256": hashes, "pairs": len(rows),
        **summarize(rows),
        "elapsed_ms": {"p50": elapsed[int((len(elapsed) - 1) * .5)],
                       "p95": elapsed[int((len(elapsed) - 1) * .95)],
                       "max": elapsed[-1]},
        "boundary": "同宽换源的条件三摸结构教师；G223/G224 已见根仅作开发，不是赛事收益。",
    }
    g223.write_new(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({"pairs": result["pairs"], "by_mix": result["by_mix"],
                      "g217_tie_break_continue_gate":
                          result["g217_tie_break_continue_gate"],
                      "elapsed_ms": result["elapsed_ms"]},
                     ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
