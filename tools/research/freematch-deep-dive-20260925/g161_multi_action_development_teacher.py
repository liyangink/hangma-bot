#!/usr/bin/env python3
"""G161：G160 开发窗口同世界单次弃牌续打；机制锁定根不打开。"""

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
import hashlib
import json
import os
from pathlib import Path
from statistics import mean

import g100_g96_visible_trajectory as trajectory
import g126_all_draw_natural_width_exposure as capture
import g160_multi_action_value_source as source


HERE = Path(__file__).resolve().parent
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G161-MULTI-ACTION-DEVELOPMENT-TEACHER-PREREG-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g161-multi-action-development-teacher-20260928')
WORLD_KEYS = ("historical",) + tuple("g161-" + str(i).zfill(3)
                                      for i in range(1, 33))


def sha(path: Path) -> str:
    """用原始字节固定来源和结果。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def selected() -> list[dict]:
    """只载入 G160 已冻结的 49 个开发窗。"""
    path = source.OUT / "selection.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if (data["schema"] != "g160-multi-action-value-source-selection/1"
            or data["rows_sha256"] != sha(source.OUT / "rows.jsonl")
            or data["manifest_sha256"] != sha(source.OUT / "manifest.json")):
        raise ValueError("G160 固定选样或父代表来源摘要漂移")
    items = [item for item in data["selected"] if item["split"] == "development"]
    if len(items) != 49 or any(item["root_index"] > 16 for item in items):
        raise ValueError("G161 只能打开 49 个开发窗口")
    return items


def manifest(items: list[dict]) -> dict:
    """绑定重采样算法、对手、规则合同与所有已冻结输入。"""
    paths = {"prereg": PREREG, "script": Path(__file__),
             "g160_selection": source.OUT / "selection.json",
             "g160_rows": source.OUT / "rows.jsonl",
             "g160_script": Path(source.__file__),
             "capture_script": Path(capture.__file__),
             "trajectory_script": Path(trajectory.__file__),
             "runtime_script": Path(source.source.g95.__file__),
             "contract": source.source.g95.g93.paired.CONTRACT,
             "simulation_engine": _project_file(_PROJECT_ROOT, HERE.parents[1] / "src/hangma_bot/simulation/engine.py")}
    return {"schema": "g161-multi-action-development-teacher-manifest/1",
            "windows_planned": len(items), "world_keys": list(WORLD_KEYS),
            "parent_scorer_sha256": capture.g87.c31.R18_INTEGRATED_POSITIVE_V2_SHA256,
            "input_sha256": {name: sha(path) for name, path in paths.items()},
            "boundary": "只运行 G160 开发根的同世界单局反事实；不作完整桌发布效果。"}


def index() -> dict[tuple, tuple[dict, dict]]:
    """按池、根、座和官方单局定位 G160 行动前记录。"""
    rows = [json.loads(line) for line in
            (source.OUT / "rows.jsonl").read_text(encoding="utf-8").splitlines()]
    if len(rows) != 192:
        raise ValueError("G160 192 张父代表不完整")
    found = {}
    for row in rows:
        for target in row["target_windows"]:
            key = (row["mix"], row["root_index"], row["focal_seat"],
                   target["round_no"])
            if key in found:
                raise ValueError("G160 目标窗身份重复")
            found[key] = (row, target)
    return found


def compact_arm(branch: dict, seat: int) -> dict:
    """保留足以复查到达/胡型/可靠性的轨迹，完整世界可按清单重跑。"""
    draws = []
    for item in branch["focal_trajectory"]:
        if item["window"]["phase"] != "draw":
            continue
        draws.append({"action_key": item["action_key"],
                      "standard_shanten_after": item["standard_shanten_after"],
                      "seven_pairs_shanten_after": item["seven_pairs_shanten_after"],
                      "white_after_discard": item["white_after_discard"],
                      "one_draw_win_routes": item["one_draw_win_routes"],
                      "one_draw_highfan_routes": item["one_draw_highfan_routes"],
                      "wall_remaining": item["wall_remaining"],
                      "trigger_seq": item["window"]["trigger_seq"]})
    if not draws or draws[0]["action_key"] != branch["first_decision_action"]:
        raise ValueError("G161 首个正常摸打动作与分支轨迹不一致")
    first_ready = next((i for i, row in enumerate(draws)
                        if row["standard_shanten_after"] == 0), None)
    first_highfan = next((i for i, row in enumerate(draws)
                          if row["one_draw_highfan_routes"] > 0), None)
    return {"settlement": branch["settlement"],
            "decision_count": branch["decision_count"],
            "first_decision_action": branch["first_decision_action"],
            "forced_once": branch["forced_once"],
            "runtime_counts": branch["runtime_counts"],
            "own_normal_draw_actions": len(draws),
            "first_ready_draw_index": first_ready,
            "first_highfan_draw_index": first_highfan,
            "white_at_first_ready": (draws[first_ready]["white_after_discard"]
                                     if first_ready is not None else None),
            "focal_draw_trajectory": draws,
            "focal_score_delta": branch["settlement"]["score_delta"][seat]}


def one_window(item: dict, table: dict, target: dict, plan,
               contract: dict, versions: dict, scorer) -> dict:
    """重建一次完整父代表，然后每个隐藏世界只变第一合法弃牌。"""
    g95 = source.source.g95
    original = g95.CaptureWiderPolicy
    g95.CaptureWiderPolicy = capture.CaptureEveryHandAllDrawPolicy
    try:
        captured, runtime, rules, situation, hands, _ = g95.run_full(
            plan, contract, versions, table["mix"])
    finally:
        g95.CaptureWiderPolicy = original
    record = captured.records.get(target["round_no"])
    if record is None or capture.scored_target(record, scorer) != target:
        raise ValueError("G161 父代观察、合法动作或评分与 G160 不一致")
    if (item["observation_sha256"] != target["observation_sha256"]
            or item["parent_action"] != record.parent_key
            or item["alternate_action"] != record.alternate_key):
        raise ValueError("G161 固定选样身份漂移")
    reference = runtime["engine"].frame(record.world).decisions[0].observation
    worlds = [("historical", record.world)]
    for sample_key in WORLD_KEYS[1:]:
        sampled = runtime["engine"].resample_public_consistent_hidden_world(
            record.world, focal_seat=item["focal_seat"], sample_key=sample_key)
        if runtime["engine"].frame(sampled).decisions[0].observation != reference:
            raise ValueError("G161 重采样改变依法可见观察")
        worlds.append((sample_key, sampled))
    pairs = []
    for sample_key, world in worlds:
        parent_full = trajectory.run_branch(
            world=world, captured=record, plan=plan, contract=contract,
            versions=versions, runtime=runtime, rules=rules,
            situation=situation, mix=table["mix"], forced_key=None)
        alternate_full = trajectory.run_branch(
            world=world, captured=record, plan=plan, contract=contract,
            versions=versions, runtime=runtime, rules=rules,
            situation=situation, mix=table["mix"], forced_key=record.alternate_key)
        parent = compact_arm(parent_full, item["focal_seat"])
        alternate = compact_arm(alternate_full, item["focal_seat"])
        if (parent["forced_once"] != 0 or alternate["forced_once"] != 1
                or parent["first_decision_action"] != record.parent_key
                or alternate["first_decision_action"] != record.alternate_key
                or parent["settlement"]["scores_before"] !=
                   alternate["settlement"]["scores_before"]):
            raise ValueError("G161 首弃或双臂起点不同")
        if any(parent["runtime_counts"].values()) or any(
                alternate["runtime_counts"].values()):
            raise ValueError("G161 分支出现保底、超时或非法动作")
        if sample_key == "historical":
            historical = hands[target["round_no"] - 1]
            for field in ("round_no", "scores_before", "scores_after",
                          "score_delta", "winner_seat", "is_draw", "fan", "details"):
                if parent["settlement"][field] != historical[field]:
                    raise ValueError("G161 历史父代单局恒等失败：" + field)
        pairs.append({"sample_key": sample_key,
                      "focal_delta_alt_minus_parent":
                          alternate["focal_score_delta"] - parent["focal_score_delta"],
                      "parent_class": g95.classify(parent["settlement"],
                                                    item["focal_seat"]),
                      "alternate_class": g95.classify(alternate["settlement"],
                                                       item["focal_seat"]),
                      "parent": parent, "alternate": alternate})
    return {"mix": item["mix"], "root_index": item["root_index"],
            "focal_seat": item["focal_seat"], "round_no": item["round_no"],
            "white_before": item["white_before"],
            "observation_sha256": item["observation_sha256"],
            "parent_action": item["parent_action"],
            "alternate_action": item["alternate_action"],
            "score_facts": target["score_facts"],
            "world_pairs": pairs}


def summary(rows: list[dict], planned: int) -> dict:
    """相关世界先窗口等权，独立信息按 H/M 牌山根聚类。"""
    groups = {}
    for mix in ("H", "M"):
        for white in (0, 1):
            subset = [row for row in rows if row["mix"] == mix
                      and row["white_before"] == white]
            values = [mean(pair["focal_delta_alt_minus_parent"]
                           for pair in row["world_pairs"]) for row in subset]
            by_root = defaultdict(list)
            for row, value in zip(subset, values):
                by_root[row["root_index"]].append(value)
            groups[f"{mix}/{white}"] = {
                "windows": len(subset),
                "roots": len(by_root),
                "related_world_pairs": sum(len(row["world_pairs"]) for row in subset),
                "window_mean_delta": mean(values) if values else None,
                "positive_windows": sum(value > 0 for value in values),
                "negative_windows": sum(value < 0 for value in values),
                "zero_windows": sum(value == 0 for value in values),
                "root_mean_deltas": {str(root): mean(items)
                                     for root, items in sorted(by_root.items())},
            }
    return {"schema": "g161-multi-action-development-teacher-summary/1",
            "status": "complete" if len(rows) == planned else "in_progress",
            "windows_completed": len(rows), "windows_planned": planned,
            "groups": groups,
            "boundary": "开发层相关单局续打，不是独立完整桌策略净分。"}


def main() -> None:
    """仅对固定开发选样逐窗落盘，可从精确前缀恢复。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-new", type=int, default=0)
    args = parser.parse_args()
    items = selected()
    expected = manifest(items)
    targets = index()
    g95 = source.source.g95
    contract = json.loads(g95.g93.paired.CONTRACT.read_text(encoding="utf-8"))
    versions = g95.g93.natural.stage.contract_versions_block(contract)
    scorer = capture.g87.c31.load_parent()
    plans = {(mix, root, seat): plan
             for mix, root, seat, plan in source.plans(contract)}
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = _project_file(_PROJECT_ROOT, OUT / "manifest.json")
    if manifest_path.exists():
        if json.loads(manifest_path.read_text(encoding="utf-8")) != expected:
            raise ValueError("G161 清单或代码改变，不能混写")
    else:
        manifest_path.write_text(json.dumps(expected, ensure_ascii=False,
                                            sort_keys=True, indent=2) + "\n", encoding="utf-8")
    rows_path = _project_file(_PROJECT_ROOT, OUT / "rows.jsonl")
    rows = ([json.loads(line) for line in rows_path.read_text(encoding="utf-8").splitlines()]
            if rows_path.exists() else [])
    if len(rows) > len(items):
        raise ValueError("G161 已有结果超过预定选样")
    for old, item in zip(rows, items):
        if any(old[name] != item[name] for name in (
                "mix", "root_index", "focal_seat", "round_no",
                "observation_sha256", "parent_action", "alternate_action")):
            raise ValueError("G161 既有行不是固定选样准确前缀")
    with rows_path.open("a", encoding="utf-8") as stream:
        for item in items[len(rows):]:
            key = (item["mix"], item["root_index"], item["focal_seat"],
                   item["round_no"])
            table, target = targets[key]
            row = one_window(item, table, target, plans[key[:3]],
                             contract, versions, scorer)
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
            rows.append(row)
            print(json.dumps({"windows_completed": len(rows),
                              "world_pairs": len(row["world_pairs"]),
                              "mix": item["mix"], "root": item["root_index"]},
                             ensure_ascii=False), flush=True)
            if args.max_new > 0 and len(rows) >= args.max_new:
                break
    result = summary(rows, len(items))
    result["manifest_sha256"] = sha(manifest_path)
    result["rows_sha256"] = sha(rows_path)
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(json.dumps(result, ensure_ascii=False,
                                            sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"],
                      "windows_completed": result["windows_completed"],
                      "groups": result["groups"]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
