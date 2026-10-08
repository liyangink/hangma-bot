#!/usr/bin/env python3
"""G110：结果盲匹配无局部高番分歧窗，并按 G109 同局续打。"""

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

import g108_fresh_hm_route_exposure as g108
import g109_fresh_hm_high_route_paired_branch as g109


HERE = Path(__file__).resolve().parent
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G110-FRESH-HM-NO-HIGH-MATCHED-CONTROL-PREREG-2026-09-28.md')
SOURCE = g108.OUT / "rows.jsonl"
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g110-fresh-hm-no-high-matched-control-20260928')


def sha(path: Path) -> str:
    """保存冻结输入的字节摘要。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity(row: dict, target: dict) -> tuple:
    """完整父代表、座位及单局决定目标窗口身份。"""
    return row["mix"], row["root_index"], row["focal_seat"], target["round_no"]


def facts(target: dict, arm: str, field: str) -> int:
    """读取已冻结的行动前合法候选牌效事实。"""
    key = target["parent_action"] if arm == "parent" else target["alternate_action"]
    return target["visible_action_facts"][key][field]


def selected() -> list[tuple[dict, dict, tuple]]:
    """按预登记同池同白、可见牌效距离匹配两个不重复对照。"""
    rows = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines()]
    if len(rows) != 128:
        raise ValueError("G110 G108 输入非 128 张完整父代表")
    high = []
    controls = []
    for row in rows:
        for target in row["target_windows"]:
            if target["status"] != "complete":
                continue
            delta = target["delta"]["high_opportunities"]
            (high if delta["parent_only"] or delta["alternate_only"] else controls).append(
                (row, target))
    if len(high) != 10:
        raise ValueError("G110 高番分歧窗数量与预登记不一致")
    chosen = set()
    result = []
    for high_row, high_target in high:
        available = [(row, target) for row, target in controls
                     if identity(row, target) not in chosen
                     and row["mix"] == high_row["mix"]
                     and target["white_before"] == high_target["white_before"]]
        def distance(pair: tuple[dict, dict]) -> tuple:
            row, target = pair
            code_distance = sum(abs(facts(target, arm, "ordinary_codes")
                                    - facts(high_target, arm, "ordinary_codes"))
                                for arm in ("parent", "alternate"))
            capacity_distance = sum(abs(facts(target, arm, "public_unseen_capacity")
                                        - facts(high_target, arm, "public_unseen_capacity"))
                                    for arm in ("parent", "alternate"))
            return (abs(target["round_no"] - high_target["round_no"]),
                    code_distance, capacity_distance,
                    row["root_index"], row["focal_seat"], target["round_no"])
        if len(available) < 2:
            raise ValueError("G110 同池同白不重复对照不足两个")
        for row, target in sorted(available, key=distance)[:2]:
            key = identity(row, target)
            chosen.add(key)
            result.append((row, target, identity(high_row, high_target)))
    if len(result) != 20 or len(chosen) != 20:
        raise ValueError("G110 对照窗数量不守恒")
    return result


def manifest() -> dict:
    """续跑拒绝代码、清单或原始窗口变化。"""
    paths = {
        "prereg": PREREG, "script": Path(__file__),
        "g108_rows": SOURCE, "g108_manifest": g108.OUT / "manifest.json",
        "g109_script": Path(g109.__file__),
        "contract": g109.g95.g93.paired.CONTRACT,
    }
    return {
        "schema": "g110-fresh-hm-no-high-control-manifest/1",
        "selected_windows": 20,
        "world_keys": ["historical", *g109.SAMPLES],
        "input_sha256": {name: sha(path) for name, path in paths.items()},
        "boundary": "匹配对照只校准 G106 信号；不是独立完整桌确认。",
    }


def summary(rows: list[dict]) -> dict:
    """按窗与池保留描述结果，不对 9 个世界作独立推断。"""
    result = {"schema": "g110-fresh-hm-no-high-control-summary/1",
              "status": "complete" if len(rows) == 20 else "in_progress",
              "windows": len(rows), "planned": 20, "by_mix": {}}
    for mix in ("H", "M"):
        group = [row for row in rows if row["mix"] == mix]
        pairs = [pair for row in group for pair in row["world_pairs"]]
        deltas = [pair["focal_delta_alt_minus_parent"] for pair in pairs]
        result["by_mix"][mix] = {
            "windows": len(group), "roots": len({row["root_index"] for row in group}),
            "world_pairs": len(pairs),
            "alt_better_pairs": sum(value > 0 for value in deltas),
            "parent_better_pairs": sum(value < 0 for value in deltas),
            "tied_pairs": sum(value == 0 for value in deltas),
            "alt_minus_parent_sum": sum(deltas),
            "parent_special_win_pairs": sum(pair["parent_class"] == "special_self_win"
                                            for pair in pairs),
            "alt_special_win_pairs": sum(pair["alternate_class"] == "special_self_win"
                                         for pair in pairs),
        }
    return result


def main() -> None:
    """选择记录先于结算，逐窗存盘并允许精确前缀续跑。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-new", type=int, default=0)
    args = parser.parse_args()
    targets = selected()
    expected = manifest()
    contract = json.loads(g109.g95.g93.paired.CONTRACT.read_text(encoding="utf-8"))
    versions = g109.g95.g93.natural.stage.contract_versions_block(contract)
    plans = {(mix, root, seat): plan for mix, root, seat, plan in g108.plans(contract)}
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = _project_file(_PROJECT_ROOT, OUT / "manifest.json")
    if manifest_path.exists():
        if json.loads(manifest_path.read_text(encoding="utf-8")) != expected:
            raise ValueError("G110 批次清单变化，拒绝混写")
    else:
        manifest_path.write_text(json.dumps(expected, ensure_ascii=False,
                                            sort_keys=True, indent=2) + "\n", encoding="utf-8")
    rows_path = _project_file(_PROJECT_ROOT, OUT / "rows.jsonl")
    rows = ([json.loads(line) for line in rows_path.read_text(encoding="utf-8").splitlines()]
            if rows_path.exists() else [])
    for old, (source, target, matched_to) in zip(rows, targets):
        if ((old["mix"], old["root_index"], old["focal_seat"], old["round_no"])
                != identity(source, target)
                or old["matched_to"] != list(matched_to)):
            raise ValueError("G110 已有记录非结果盲匹配前缀")
    added = 0
    with rows_path.open("a", encoding="utf-8") as stream:
        for source, target, matched_to in targets[len(rows):]:
            key = (source["mix"], source["root_index"], source["focal_seat"])
            row = g109.one_window(source, target, plans[key], contract, versions)
            row["matched_to"] = list(matched_to)
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
