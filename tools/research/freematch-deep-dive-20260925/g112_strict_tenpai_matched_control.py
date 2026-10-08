#!/usr/bin/env python3
"""G112：为 G109 高番分歧窗寻找同池、同白、同向听的听牌对照。"""

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
import g110_fresh_hm_no_high_matched_control as g110


HERE = Path(__file__).resolve().parent
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G112-STRICT-TENPAI-MATCHED-CONTROL-PREREG-2026-09-28.md')
SOURCE = g108.OUT / "rows.jsonl"
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g112-strict-tenpai-matched-control-20260928')


def sha(path: Path) -> str:
    """记录冻结来源的字节摘要。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def shanten(target: dict) -> int:
    """读取当前弃牌后的生产规则普通型向听。"""
    return g110.facts(target, "parent", "standard_shanten_after")


def selected() -> list[tuple[dict, dict, tuple]]:
    """完全同池、同白、同向听的一对一可见匹配。"""
    rows = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines()]
    if len(rows) != 128:
        raise ValueError("G112 G108 输入非 128 张完整父代表")
    high = []
    controls = []
    for row in rows:
        for target in row["target_windows"]:
            if target["status"] != "complete":
                continue
            delta = target["delta"]["high_opportunities"]
            (high if delta["parent_only"] or delta["alternate_only"] else controls).append(
                (row, target))
    if len(high) != 10 or any(shanten(target) != 0 for _, target in high):
        raise ValueError("G112 10 个高番窗全听牌的审计前提不成立")
    chosen = set()
    result = []
    for high_row, high_target in high:
        available = [(row, target) for row, target in controls
                     if g110.identity(row, target) not in chosen
                     and row["mix"] == high_row["mix"]
                     and target["white_before"] == high_target["white_before"]
                     and shanten(target) == shanten(high_target)]
        def distance(pair: tuple[dict, dict]) -> tuple:
            row, target = pair
            codes = sum(abs(g110.facts(target, arm, "ordinary_codes")
                            - g110.facts(high_target, arm, "ordinary_codes"))
                        for arm in ("parent", "alternate"))
            capacity = sum(abs(g110.facts(target, arm, "public_unseen_capacity")
                               - g110.facts(high_target, arm, "public_unseen_capacity"))
                           for arm in ("parent", "alternate"))
            return (abs(target["round_no"] - high_target["round_no"]),
                    codes, capacity, row["root_index"], row["focal_seat"],
                    target["round_no"])
        if not available:
            raise ValueError("G112 严格匹配分层无剩余对照")
        row, target = min(available, key=distance)
        chosen.add(g110.identity(row, target))
        result.append((row, target, g110.identity(high_row, high_target)))
    if len(result) != 10 or len(chosen) != 10:
        raise ValueError("G112 匹配数量不守恒")
    return result


def manifest() -> dict:
    """拒绝续跑时混入不同代码或面板。"""
    paths = {"prereg": PREREG, "script": Path(__file__),
             "g108_rows": SOURCE, "g108_manifest": g108.OUT / "manifest.json",
             "g109_script": Path(g109.__file__),
             "contract": g109.g95.g93.paired.CONTRACT}
    return {"schema": "g112-strict-tenpai-control-manifest/1",
            "selected_windows": 10,
            "world_keys": ["historical", *g109.SAMPLES],
            "input_sha256": {name: sha(path) for name, path in paths.items()},
            "boundary": "已看 G109/G110 后修正匹配，仍为开发性机制诊断。"}


def main() -> None:
    """按冻结窗口次序逐窗完成并落盘。"""
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
            raise ValueError("G112 批次清单变化，拒绝混写")
    else:
        manifest_path.write_text(json.dumps(expected, ensure_ascii=False,
                                            sort_keys=True, indent=2) + "\n", encoding="utf-8")
    rows_path = _project_file(_PROJECT_ROOT, OUT / "rows.jsonl")
    rows = ([json.loads(line) for line in rows_path.read_text(encoding="utf-8").splitlines()]
            if rows_path.exists() else [])
    for old, (source, target, matched_to) in zip(rows, targets):
        if ((old["mix"], old["root_index"], old["focal_seat"], old["round_no"])
                != g110.identity(source, target)
                or old["matched_to"] != list(matched_to)):
            raise ValueError("G112 已有记录非严格匹配前缀")
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
    result = g109.summary(rows)
    result["schema"] = "g112-strict-tenpai-control-summary/1"
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(json.dumps(result, ensure_ascii=False,
                                            sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
