#!/usr/bin/env python3
"""G116：按 G115 结果盲匹配清单逐窗同世界双臂续打。"""

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
from statistics import mean

import g109_fresh_hm_high_route_paired_branch as g109
import g114_fresh_score_matched_route_exposure as g114
import g115_score_matched_route_support as g115


HERE = Path(__file__).resolve().parent
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G116-SCORE-MATCHED-ROUTE-BRANCH-PREREG-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g116-score-matched-route-branch-20260928')


def sha(path: Path) -> str:
    """冻结窗口清单和双分支程序的字节摘要。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def planned() -> list[tuple[int, str, dict, dict, dict]]:
    """只依 G115 可见匹配结果生成固定窗口次序。"""
    matched = json.loads(g115.OUT.read_text(encoding="utf-8"))
    if matched["schema"] != "g115-score-matched-route-support/1":
        raise ValueError("G116 G115 清单 schema 错误")
    if not matched["next_gate_support"]:
        raise ValueError("G116 G115 支持集门未通过")
    rows = [json.loads(line) for line in (g114.OUT / "rows.jsonl").read_text(
        encoding="utf-8").splitlines()]
    targets = {(row["mix"], row["root_index"], row["focal_seat"], target["round_no"]):
               (row, target)
               for row in rows for target in row["target_windows"]}
    result = []
    for index, match in enumerate(matched["matches"]):
        for group, field in (("high_difference", "high_window"),
                             ("matched_control", "control_window")):
            key = tuple(match[field])
            row, target = targets[key]
            expected_sha = match[("high" if group == "high_difference"
                                  else "control") + "_observation_sha256"]
            if target["observation_sha256"] != expected_sha:
                raise ValueError("G116 冻结可见观察摘要不一致")
            if target["status"] != "complete" or g115.is_high(target) != (
                group == "high_difference"):
                raise ValueError("G116 高番分组与 G115 冻结结果不一致")
            result.append((index, group, row, target, match))
    if len(result) != 2 * matched["matched_pairs"]:
        raise ValueError("G116 固定匹配窗口数不守恒")
    return result


def manifest(expected_windows: int) -> dict:
    """运行前固定全部研究输入与程序身份。"""
    paths = {"prereg": PREREG, "script": Path(__file__),
             "g114_rows": g114.OUT / "rows.jsonl",
             "g114_manifest": g114.OUT / "manifest.json",
             "g115_result": g115.OUT,
             "g109_script": Path(g109.__file__),
             "contract": g109.g95.g93.paired.CONTRACT}
    return {"schema": "g116-score-matched-route-branch-manifest/1",
            "windows_planned": expected_windows,
            "world_keys": ["historical", *g109.SAMPLES],
            "input_sha256": {name: sha(path) for name, path in paths.items()},
            "boundary": "匹配跨窗口是观察性比较；每窗内同世界双臂才是干预对照。"}


def one_window(index: int, group: str, source: dict, target: dict,
               match: dict, plan, contract: dict, versions: dict) -> dict:
    """G114 新种子的目标窗复现后，严格复用 G109 同局双臂量具。"""
    frozen_target = {key: value for key, value in target.items()
                     if key != "score_facts"}
    row = g109.one_window(source, frozen_target, plan, contract, versions)
    row.update({"match_index": index, "group": group,
                "score_facts": target["score_facts"],
                "matched_to": (match["control_window"] if group == "high_difference"
                               else match["high_window"]),
                "match_distance": match["distance"]})
    return row


def window_mean(row: dict) -> float:
    """同一可见窗口九世界等权配对差的描述均值。"""
    pairs = row["world_pairs"]
    if len(pairs) != 9:
        raise ValueError("G116 窗口隐藏样本数不为九")
    return mean(pair["focal_delta_alt_minus_parent"] for pair in pairs)


def summary(rows: list[dict], expected: int) -> dict:
    """匹配差按窗与根描述，避免把 9 世界冒充独立桌赛。"""
    by_mix = {}
    for mix in ("H", "M"):
        group = [row for row in rows if row["mix"] == mix]
        by_arm = {}
        for arm in ("high_difference", "matched_control"):
            subset = [row for row in group if row["group"] == arm]
            by_arm[arm] = {
                "windows": len(subset),
                "roots": len({row["root_index"] for row in subset}),
                "world_pairs": sum(len(row["world_pairs"]) for row in subset),
                "window_mean_sum": sum(window_mean(row) for row in subset),
                "positive_windows": sum(window_mean(row) > 0 for row in subset),
                "negative_windows": sum(window_mean(row) < 0 for row in subset),
                "zero_windows": sum(window_mean(row) == 0 for row in subset),
            }
        high_by_index = {row["match_index"]: row for row in group
                         if row["group"] == "high_difference"}
        controls_by_index = {row["match_index"]: row for row in group
                             if row["group"] == "matched_control"}
        completed = sorted(set(high_by_index) & set(controls_by_index))
        contrasts = [window_mean(high_by_index[index])
                     - window_mean(controls_by_index[index]) for index in completed]
        by_mix[mix] = {"groups": by_arm, "complete_matches": len(completed),
                       "contrast_mean": mean(contrasts) if contrasts else None,
                       "contrast_positive": sum(value > 0 for value in contrasts),
                       "contrast_negative": sum(value < 0 for value in contrasts),
                       "contrast_zero": sum(value == 0 for value in contrasts)}
    return {"schema": "g116-score-matched-route-branch-summary/1",
            "status": "complete" if len(rows) == expected else "in_progress",
            "windows_completed": len(rows), "windows_planned": expected,
            "by_mix": by_mix,
            "boundary": "同局配对是机制诊断；跨窗口匹配和九世界均非独立完整桌收益确认。"}


def main() -> None:
    """固定顺序逐窗执行，支持严格清单前缀续跑。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-new", type=int, default=0)
    args = parser.parse_args()
    targets = planned()
    expected = manifest(len(targets))
    contract = json.loads(g109.g95.g93.paired.CONTRACT.read_text(encoding="utf-8"))
    versions = g109.g95.g93.natural.stage.contract_versions_block(contract)
    plans = {(mix, root, seat): plan for mix, root, seat, plan in g114.plans(contract)}
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = _project_file(_PROJECT_ROOT, OUT / "manifest.json")
    if manifest_path.exists():
        if json.loads(manifest_path.read_text(encoding="utf-8")) != expected:
            raise ValueError("G116 批次清单变化，拒绝混写")
    else:
        manifest_path.write_text(json.dumps(expected, ensure_ascii=False,
                                            sort_keys=True, indent=2) + "\n", encoding="utf-8")
    rows_path = _project_file(_PROJECT_ROOT, OUT / "rows.jsonl")
    rows = ([json.loads(line) for line in rows_path.read_text(encoding="utf-8").splitlines()]
            if rows_path.exists() else [])
    for old, (index, group, source, target, _) in zip(rows, targets):
        if (old["match_index"], old["group"], old["mix"], old["root_index"],
                old["focal_seat"], old["round_no"], old["observation_sha256"]) != (
                index, group, source["mix"], source["root_index"],
                source["focal_seat"], target["round_no"], target["observation_sha256"]):
            raise ValueError("G116 已有证据非冻结目标窗前缀")
    added = 0
    with rows_path.open("a", encoding="utf-8") as stream:
        for index, group, source, target, match in targets[len(rows):]:
            plan = plans[(source["mix"], source["root_index"], source["focal_seat"])]
            row = one_window(index, group, source, target, match, plan, contract, versions)
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
            rows.append(row)
            added += 1
            print(json.dumps({"match": index, "group": group,
                              "mix": row["mix"], "root": row["root_index"],
                              "window_mean": window_mean(row)}, ensure_ascii=False), flush=True)
            if args.max_new > 0 and added >= args.max_new:
                break
    result = summary(rows, len(targets))
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(json.dumps(result, ensure_ascii=False,
                                            sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
