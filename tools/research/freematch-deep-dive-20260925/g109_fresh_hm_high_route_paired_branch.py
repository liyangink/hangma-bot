#!/usr/bin/env python3
"""G109：在 G108 全部高番机会差异窗复现世界并进行同局配对续打。"""

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
import os
from pathlib import Path

import g95_wider_discard_same_hand_preflight as g95
import g108_fresh_hm_route_exposure as g108


HERE = Path(__file__).resolve().parent
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G109-FRESH-HM-HIGH-ROUTE-PAIRED-BRANCH-PREREG-2026-09-28.md')
SOURCE = g108.OUT / "rows.jsonl"
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g109-fresh-hm-high-route-paired-branch-20260928')
SAMPLES = g95.SAMPLES


def sha(path: Path) -> str:
    """冻结程序、选样及合同的字节摘要。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: object) -> str:
    """规范化 JSON，避免 tuple/list 内存表示差异。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def selected() -> list[tuple[dict, dict]]:
    """只依 G108 行动前局部高番差异选择全部目标窗。"""
    rows = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines()]
    result = []
    for row in rows:
        for target in row["target_windows"]:
            if target["status"] != "complete":
                continue
            difference = target["delta"]["high_opportunities"]
            if difference["parent_only"] or difference["alternate_only"]:
                result.append((row, target))
    if len(rows) != 128 or len(result) != 10:
        raise ValueError("G108 冻结选样数量与 G109 事前登记不一致")
    return result


def manifest() -> dict:
    """续跑时拒绝新旧输入混写。"""
    paths = {
        "prereg": PREREG, "script": Path(__file__),
        "g108_rows": SOURCE, "g108_manifest": g108.OUT / "manifest.json",
        "g108_script": Path(g108.__file__), "g95_script": Path(g95.__file__),
        "g93_script": Path(g95.g93.__file__),
        "contract": g95.g93.paired.CONTRACT,
    }
    return {
        "schema": "g109-fresh-hm-high-route-paired-manifest/1",
        "selected_windows": 10,
        "world_keys": ["historical", *SAMPLES],
        "input_sha256": {name: sha(path) for name, path in paths.items()},
        "boundary": "同局机制开发样本，不是未见根完整桌收益确认。",
    }


def one_window(source: dict, target: dict, plan, contract: dict,
               versions: dict) -> dict:
    """重跑完整父代表核对身份，再对同一世界逐臂续打至单局结算。"""
    original = g95.CaptureWiderPolicy
    g95.CaptureWiderPolicy = g108.CaptureEveryHandPolicy
    try:
        captured, runtime, rules, situation, hands, _ = g95.run_full(
            plan, contract, versions, source["mix"])
    finally:
        g95.CaptureWiderPolicy = original
    record = captured.records.get(target["round_no"])
    if record is None:
        raise ValueError("G109 重跑未复现目标单局窗口")
    replayed = g108.target_row(record)
    if canonical(replayed) != canonical(target):
        raise ValueError("G109 重跑的可见观察、动作或机会量具不一致")
    window = record.request.window_key
    focal_observation = runtime["engine"].frame(record.world).decisions[0].observation
    worlds = [("historical", record.world)]
    for sample_key in SAMPLES:
        sampled = runtime["engine"].resample_public_consistent_hidden_world(
            record.world, focal_seat=window.seat, sample_key=sample_key)
        if runtime["engine"].frame(sampled).decisions[0].observation != focal_observation:
            raise ValueError("G109 隐藏重采样改变玩家可见观察")
        worlds.append((sample_key, sampled))
    pairs = []
    for sample_key, world in worlds:
        parent = g95.run_branch(
            world=world, captured=record, plan=plan, contract=contract,
            versions=versions, runtime=runtime, rules=rules,
            situation=situation, mix=source["mix"], forced_key=None)
        alternate = g95.run_branch(
            world=world, captured=record, plan=plan, contract=contract,
            versions=versions, runtime=runtime, rules=rules,
            situation=situation, mix=source["mix"], forced_key=record.alternate_key)
        p = parent["settlement"]
        a = alternate["settlement"]
        if p["scores_before"] != a["scores_before"]:
            raise ValueError("G109 两臂起点积分不相同")
        if sample_key == "historical":
            old = hands[window.round_no - 1]
            for field in ("round_no", "scores_before", "scores_after", "score_delta",
                          "winner_seat", "is_draw", "fan", "details"):
                if p[field] != old[field]:
                    raise ValueError("G109 历史世界父代结算不守恒：" + field)
        pairs.append({
            "sample_key": sample_key,
            "parent": parent, "alternate": alternate,
            "focal_delta_alt_minus_parent":
                a["score_delta"][window.seat] - p["score_delta"][window.seat],
            "parent_class": g95.classify(p, window.seat),
            "alternate_class": g95.classify(a, window.seat),
        })
    return {
        "mix": source["mix"], "root_index": source["root_index"],
        "focal_seat": source["focal_seat"], "round_no": target["round_no"],
        "table_id": source["table_id"], "status": "paired",
        "observation_sha256": target["observation_sha256"],
        "parent_action": target["parent_action"],
        "alternate_action": target["alternate_action"],
        "high_difference": target["delta"]["high_opportunities"],
        "world_pairs": pairs,
    }


def summary(rows: list[dict]) -> dict:
    """只做描述性计数；不把世界重采样当独立桌赛统计。"""
    result = {"schema": "g109-fresh-hm-high-route-paired-summary/1",
              "status": "complete" if len(rows) == 10 else "in_progress",
              "windows": len(rows), "planned": 10, "by_mix": {}}
    for mix in ("H", "M"):
        group = [row for row in rows if row["mix"] == mix]
        pairs = [pair for row in group for pair in row["world_pairs"]]
        deltas = [pair["focal_delta_alt_minus_parent"] for pair in pairs]
        result["by_mix"][mix] = {
            "windows": len(group),
            "roots": len({row["root_index"] for row in group}),
            "world_pairs": len(pairs),
            "alt_better_pairs": sum(delta > 0 for delta in deltas),
            "parent_better_pairs": sum(delta < 0 for delta in deltas),
            "tied_pairs": sum(delta == 0 for delta in deltas),
            "alt_minus_parent_sum": sum(deltas),
            "parent_special_win_pairs": sum(pair["parent_class"] == "special_self_win"
                                            for pair in pairs),
            "alt_special_win_pairs": sum(pair["alternate_class"] == "special_self_win"
                                         for pair in pairs),
            "parent_other_win_pairs": sum(pair["parent_class"] == "other_win"
                                          for pair in pairs),
            "alt_other_win_pairs": sum(pair["alternate_class"] == "other_win"
                                       for pair in pairs),
        }
    return result


def main() -> None:
    """按冻结行顺序增量执行，完成每窗立即落盘。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-new", type=int, default=0)
    args = parser.parse_args()
    targets = selected()
    expected = manifest()
    contract = json.loads(g95.g93.paired.CONTRACT.read_text(encoding="utf-8"))
    versions = g95.g93.natural.stage.contract_versions_block(contract)
    plans = {
        (mix, root, seat): plan
        for mix, root, seat, plan in g108.plans(contract)
    }
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = _project_file(_PROJECT_ROOT, OUT / "manifest.json")
    if manifest_path.exists():
        if json.loads(manifest_path.read_text(encoding="utf-8")) != expected:
            raise ValueError("G109 已有批次清单不一致，拒绝混写")
    else:
        manifest_path.write_text(json.dumps(expected, ensure_ascii=False,
                                            sort_keys=True, indent=2) + "\n", encoding="utf-8")
    rows_path = _project_file(_PROJECT_ROOT, OUT / "rows.jsonl")
    rows = ([json.loads(line) for line in rows_path.read_text(encoding="utf-8").splitlines()]
            if rows_path.exists() else [])
    for old, (source, target) in zip(rows, targets):
        if (old["mix"], old["root_index"], old["focal_seat"], old["round_no"],
                old["observation_sha256"]) != (
                source["mix"], source["root_index"], source["focal_seat"],
                target["round_no"], target["observation_sha256"]):
            raise ValueError("G109 续跑记录不是冻结选样的前缀")
    added = 0
    with rows_path.open("a", encoding="utf-8") as stream:
        for source, target in targets[len(rows):]:
            key = (source["mix"], source["root_index"], source["focal_seat"])
            row = one_window(source, target, plans[key], contract, versions)
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
            rows.append(row)
            added += 1
            print(json.dumps({"mix": row["mix"], "root": row["root_index"],
                              "seat": row["focal_seat"], "round": row["round_no"],
                              "paired": len(row["world_pairs"])}, ensure_ascii=False), flush=True)
            if args.max_new > 0 and added >= args.max_new:
                break
    result = summary(rows)
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(json.dumps(result, ensure_ascii=False,
                                            sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
