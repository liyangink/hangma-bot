#!/usr/bin/env python3
"""G167：逐分支恒等重放 G166，跳过响应窗并采集下一本人正常摸打。"""

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
import gzip
import hashlib
import json
import os
from pathlib import Path
from statistics import mean

import g100_g96_visible_trajectory as trajectory
import g166_fresh_root_two_arm_teacher as prior
from hangma_bot.application.audit_codec import candidate_facts_to_json


HERE = Path(__file__).resolve().parent
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G167-NEXT-OWN-DRAW-ROUTE-PREREG-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g167-next-own-draw-route-20260928')
PRIOR_GZ = prior.OUT / "rows.jsonl.gz"


class NextDrawTracePolicy(trajectory.TracePolicy):
    """响应窗仍逐次核实，但只给下一正常摸打附完整合法弃牌规则事实。"""

    def __init__(self, inner) -> None:
        super().__init__(inner)
        self.draw_count = 0

    async def choose(self, request, budget):
        """透明记录本次动作；第二个本人摸打另保存生产合法弃牌事实。"""
        plan = await super().choose(request, budget)
        if request.window_key.phase.value == "draw":
            self.draw_count += 1
            if self.draw_count == 2:
                self.records[-1]["all_legal_discards"] = [
                    {"action_key": candidate.action_key,
                     "facts": (candidate_facts_to_json(candidate.facts)
                               if candidate.facts is not None else None)}
                    for candidate in request.rules.legal_candidates
                    if candidate.action_key.startswith("discard:")
                ]
        return plan


def branch(**kwargs) -> dict:
    """复用 G100 驱动，不改变冻结四方策略或单局截止条件。"""
    original = trajectory.TracePolicy
    trajectory.TracePolicy = NextDrawTracePolicy
    try:
        return trajectory.run_branch(**kwargs)
    finally:
        trajectory.TracePolicy = original


def sha(path: Path) -> str:
    """计算磁盘证据的原始字节摘要。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_prior() -> list[dict]:
    """解压前批逐窗行并核原始字节 SHA；每行顺序就是固定选样顺序。"""
    prior_result = json.loads((prior.OUT / "result.json").read_text(encoding="utf-8"))
    with gzip.open(PRIOR_GZ, "rb") as stream:
        data = stream.read()
    if (prior_result["status"] != "complete"
            or hashlib.sha256(data).hexdigest() != prior_result["rows_sha256"]):
        raise ValueError("G167 G166 压缩证据与原始摘要不符")
    rows = [json.loads(line) for line in data.decode("utf-8").splitlines()]
    if len(rows) != 64:
        raise ValueError("G167 G166 固定窗口数不守恒")
    return rows


def manifest(items: list[dict]) -> dict:
    """绑定已看 G166 结果、同世界重放器和新增下一摸量具。"""
    paths = {
        "prereg": PREREG,
        "script": Path(__file__),
        "prior_rows_gzip": PRIOR_GZ,
        "prior_result": prior.OUT / "result.json",
        "prior_script": Path(prior.__file__),
        "selection": prior.source.OUT / "selection.json",
        "trajectory_script": Path(trajectory.__file__),
        "contract": prior.source.g160.source.g95.g93.paired.CONTRACT,
    }
    return {
        "schema": "g167-next-own-draw-route-manifest/1",
        "windows_planned": len(items),
        "world_keys": list(prior.WORLD_KEYS),
        "input_sha256": {name: sha(path) for name, path in paths.items()},
        "boundary": "G166 终局已看后的同世界下一本人摸打诊断，不是独立候选确认。",
    }


def next_draw(full: dict, old: dict, item: dict) -> dict:
    """跳过所有响应窗；若终局先到则显式截尾，绝不把未到达算零进张。"""
    for name in ("settlement", "decision_count", "first_decision_action",
                 "forced_once", "runtime_counts"):
        if full[name] != old[name]:
            raise ValueError("G167 重放与 G166 原分支不一致：" + name)
    draws = [record for record in full["focal_trajectory"]
             if record["window"]["phase"] == "draw"]
    if not draws or draws[0]["action_key"] != full["first_decision_action"]:
        raise ValueError("G167 首弃不是第一次本人正常摸打")
    if len(draws) < 2:
        return {"reached": False, "next_draw": None}
    record = draws[1]
    entries = record.get("all_legal_discards")
    if entries is None:
        raise ValueError("G167 下一摸未采集生产合法弃牌事实")
    by_key = {entry["action_key"]: entry["facts"] for entry in entries}
    if len(by_key) != len(entries):
        raise ValueError("G167 下一摸生产合法弃牌键重复")
    legal = []
    for key, facts in by_key.items():
        if facts is None:
            continue
        shanten = facts.get("standard_shanten_after")
        useful = facts.get("standard_useful_tiles")
        if type(shanten) is not int or useful is None:
            continue
        legal.append((key, shanten, len(useful),
                      sum(tile["remaining_estimate"] for tile in useful)))
    if (record["action_key"].startswith("discard:")
            and record["action_key"] not in {entry[0] for entry in legal}):
        raise ValueError("G167 下一摸普通型生产事实不完整")
    best_shanten = min((entry[1] for entry in legal), default=None)
    frontier = [entry for entry in legal if entry[1] == best_shanten]
    chosen = next((entry for entry in legal if entry[0] == record["action_key"]), None)
    return {
        "reached": True,
        "next_draw": {
            "window": record["window"],
            "hand_codes": record["hand_codes"],
            "action_key": record["action_key"],
            "white_before": record["white_before"],
            "white_after_discard": record["white_after_discard"],
            "wall_remaining": record["wall_remaining"],
            "chosen_standard_shanten_after": chosen[1] if chosen else None,
            "chosen_standard_useful_types": chosen[2] if chosen else None,
            "chosen_public_unseen_capacity": chosen[3] if chosen else None,
            "best_standard_shanten_after": best_shanten,
            "frontier_max_standard_useful_types": (
                max(entry[2] for entry in frontier) if frontier else None),
            "frontier_max_public_unseen_capacity": (
                max(entry[3] for entry in frontier) if frontier else None),
            "all_legal_discards": entries,
        },
    }


def one_window(item: dict, old: dict, table: dict, target: dict, plan,
               contract: dict, versions: dict, scorer) -> dict:
    """新轨迹逐分支复算并与 G166 同世界结算严格对账。"""
    capture = prior.source.g160.source
    g95 = capture.g95
    original = g95.CaptureWiderPolicy
    g95.CaptureWiderPolicy = capture.CaptureEveryHandAllDrawPolicy
    try:
        captured, runtime, rules, situation, _hands, _ = g95.run_full(
            plan, contract, versions, table["mix"])
    finally:
        g95.CaptureWiderPolicy = original
    record = captured.records.get(target["round_no"])
    if record is None or capture.scored_target(record, scorer) != target:
        raise ValueError("G167 父代目标观察、规则或评分漂移")
    for name in ("mix", "root_index", "focal_seat", "round_no",
                 "white_before", "observation_sha256",
                 "parent_action", "alternate_action"):
        if item[name] != old[name]:
            raise ValueError("G167 G166 逐窗身份或选样漂移：" + name)
    reference = runtime["engine"].frame(record.world).decisions[0].observation
    worlds = [("historical", record.world)]
    for sample_key in prior.WORLD_KEYS[1:]:
        sampled = runtime["engine"].resample_public_consistent_hidden_world(
            record.world, focal_seat=item["focal_seat"], sample_key=sample_key)
        if runtime["engine"].frame(sampled).decisions[0].observation != reference:
            raise ValueError("G167 重采样改变依法可见观察")
        worlds.append((sample_key, sampled))
    if len(old["world_pairs"]) != len(worlds):
        raise ValueError("G167 G166 原证据世界数不守恒")
    pairs = []
    for (sample_key, world), previous in zip(worlds, old["world_pairs"]):
        if sample_key != previous["sample_key"]:
            raise ValueError("G167 世界键与 G166 原证据不一致")
        arms = {}
        for arm in ("parent", "alternate"):
            full = branch(
                world=world, captured=record, plan=plan, contract=contract,
                versions=versions, runtime=runtime, rules=rules,
                situation=situation, mix=table["mix"],
                forced_key=(None if arm == "parent" else record.alternate_key))
            arms[arm] = next_draw(full, previous[arm], item)
        pairs.append({"sample_key": sample_key,
                      "focal_delta_alt_minus_parent":
                          previous["focal_delta_alt_minus_parent"],
                      **arms})
    if len(pairs) != 17:
        raise ValueError("G167 同世界双臂数量不守恒")
    return {"mix": item["mix"], "root_index": item["root_index"],
            "focal_seat": item["focal_seat"], "round_no": item["round_no"],
            "white_before": item["white_before"],
            "observation_sha256": item["observation_sha256"],
            "parent_action": item["parent_action"],
            "alternate_action": item["alternate_action"],
            "world_pairs": pairs}


def summary(rows: list[dict], planned: int) -> dict:
    """截尾和双臂到达分别记，不对未到达的路径虚构宽度。"""
    groups = {}
    for mix in ("H", "M"):
        for white in (0, 1):
            subset = [row for row in rows if row["mix"] == mix
                      and row["white_before"] == white]
            count = Counter()
            shanten_diffs, chosen_type_diffs, frontier_type_diffs = [], [], []
            for row in subset:
                for pair in row["world_pairs"]:
                    parent, alternate = pair["parent"], pair["alternate"]
                    reach = (parent["reached"], alternate["reached"])
                    count[str(reach)] += 1
                    if reach != (True, True):
                        continue
                    p, a = parent["next_draw"], alternate["next_draw"]
                    if (p["chosen_standard_shanten_after"] is not None
                            and a["chosen_standard_shanten_after"] is not None):
                        shanten_diffs.append(a["chosen_standard_shanten_after"]
                                             - p["chosen_standard_shanten_after"])
                        chosen_type_diffs.append(a["chosen_standard_useful_types"]
                                                 - p["chosen_standard_useful_types"])
                    if (p["frontier_max_standard_useful_types"] is not None
                            and a["frontier_max_standard_useful_types"] is not None):
                        frontier_type_diffs.append(a["frontier_max_standard_useful_types"]
                                                   - p["frontier_max_standard_useful_types"])
            groups[f"{mix}/{white}"] = {
                "windows": len(subset), "related_world_pairs": len(subset) * 17,
                "reach_pairs": dict(count),
                "both_reached_chosen_discard_pairs": len(shanten_diffs),
                "both_reached_legal_discard_frontier_pairs": len(frontier_type_diffs),
                "both_reached_chosen_shanten_difference_mean":
                    mean(shanten_diffs) if shanten_diffs else None,
                "both_reached_chosen_useful_type_difference_mean":
                    mean(chosen_type_diffs) if chosen_type_diffs else None,
                "both_reached_frontier_useful_type_difference_mean":
                    mean(frontier_type_diffs) if frontier_type_diffs else None,
            }
    return {"schema": "g167-next-own-draw-route-summary/1",
            "status": "complete" if len(rows) == planned else "in_progress",
            "windows_completed": len(rows), "windows_planned": planned,
            "groups": groups,
            "boundary": "已看 G166 终局的后续摸打机制诊断；截尾世界不参与形状均值。"}


def main() -> None:
    """固定顺序逐窗落盘；准确前缀重启不混入不同脚本或证据。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-new", type=int, default=0)
    args = parser.parse_args()
    items = prior.selected()
    previous = load_prior()
    expected = manifest(items)
    targets = prior.index()
    g95 = prior.source.g160.source.g95
    contract = json.loads(g95.g93.paired.CONTRACT.read_text(encoding="utf-8"))
    versions = g95.g93.natural.stage.contract_versions_block(contract)
    scorer = prior.source.g160.source.g87.c31.load_parent()
    plans = {(mix, root, seat): plan
             for mix, root, seat, plan in prior.source.plans(contract)}
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = _project_file(_PROJECT_ROOT, OUT / "manifest.json")
    if manifest_path.exists():
        if json.loads(manifest_path.read_text(encoding="utf-8")) != expected:
            raise ValueError("G167 清单或代码改变，拒绝混写")
    else:
        manifest_path.write_text(json.dumps(expected, ensure_ascii=False,
                                            sort_keys=True, indent=2) + "\n", encoding="utf-8")
    rows_path = _project_file(_PROJECT_ROOT, OUT / "rows.jsonl")
    rows = ([json.loads(line) for line in rows_path.read_text(encoding="utf-8").splitlines()]
            if rows_path.exists() else [])
    if len(rows) > len(items):
        raise ValueError("G167 已有轨迹超过固定窗口数")
    for old, item in zip(rows, items):
        if any(old[name] != item[name] for name in (
                "mix", "root_index", "focal_seat", "round_no",
                "observation_sha256", "parent_action", "alternate_action")):
            raise ValueError("G167 既有行不是准确前缀")
    with rows_path.open("a", encoding="utf-8") as stream:
        for item, old in zip(items[len(rows):], previous[len(rows):]):
            key = (item["mix"], item["root_index"], item["focal_seat"],
                   item["round_no"])
            table, target = targets[key]
            row = one_window(item, old, table, target, plans[key[:3]],
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
