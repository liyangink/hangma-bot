#!/usr/bin/env python3
"""G160：新 H/M 根上结果盲采集自然进张冲突，冻结教师开发／锁定来源。"""

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
import os
from pathlib import Path

import g126_all_draw_natural_width_exposure as source


HERE = Path(__file__).resolve().parent
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G160-MULTI-ACTION-VALUE-SOURCE-PREREG-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g160-multi-action-value-source-20260928')
PANEL_SEED = 2026111901
ROOTS = tuple(range(1, 25))


def sha(path: Path) -> str:
    """保存输入字节摘要，已写入的父代表不受后续源码变更污染。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def plans(contract: dict) -> list[tuple[str, int, int, object]]:
    """每根两池四座均衡；各桌仅运行冻结父代。"""
    result = []
    for root_index in ROOTS:
        for mix in ("H", "M"):
            for seat in range(4):
                plan = source.g95.g93.natural.build_seat_stage_plans(
                    contract=contract, opponent=mix, root_index=root_index,
                    focal_seat=seat, panel_seed=PANEL_SEED)[0]
                result.append((mix, root_index, seat, plan))
    return result


def manifest(contract_path: Path) -> dict:
    """绑定预登记、复用的生产采集逻辑与冻结赛事契约。"""
    paths = {"prereg": PREREG, "script": Path(__file__),
             "g126_capture": Path(source.__file__),
             "g95_runtime": Path(source.g95.__file__),
             "contract": contract_path,
             "parent_source": _project_file(_PROJECT_ROOT, HERE.parents[1] /
                 "src/hangma_bot/policy/r18_integrated_positive_v2.py")}
    return {"schema": "g160-multi-action-value-source-manifest/1",
            "panel_seed": PANEL_SEED, "roots": list(ROOTS),
            "tables_planned": len(ROOTS) * 2 * 4,
            "parent_scorer_sha256": source.g87.c31.R18_INTEGRATED_POSITIVE_V2_SHA256,
            "input_sha256": {name: sha(path) for name, path in paths.items()},
            "boundary": "结果盲父代可见观察来源；备选同世界续打与完整桌增益尚未运行。"}


def _selected(rows: list[dict]) -> list[dict]:
    """每池、根、白板格取一个动作前哈希最小的未吃碰二向听窗。"""
    buckets: dict[tuple[str, int, int], list[dict]] = {}
    for row in rows:
        for target in row["target_windows"]:
            facts = target["score_facts"]
            white = facts["white_before"]
            if (facts["own_chi_peng_count"] != 0
                    or facts["standard_shanten_after"] != 2
                    or white not in (0, 1)):
                continue
            key = (row["mix"], row["root_index"], white)
            buckets.setdefault(key, []).append({
                "split": "development" if row["root_index"] <= 16 else "mechanism_locked",
                "mix": row["mix"], "root_index": row["root_index"],
                "focal_seat": row["focal_seat"], "round_no": target["round_no"],
                "observation_sha256": target["observation_sha256"],
                "parent_action": target["parent_action"],
                "alternate_action": target["alternate_action"],
                "white_before": white,
                "score_facts": facts,
            })
    return [min(group, key=lambda item: (
        item["observation_sha256"], item["focal_seat"], item["round_no"]))
            for _key, group in sorted(buckets.items())]


def summary(rows: list[dict], selected: list[dict], planned: int) -> dict:
    """分别给桌、目标窗和独立根计数，不混作效果样本。"""
    by_mix = {}
    for mix in ("H", "M"):
        group = [row for row in rows if row["mix"] == mix]
        targets = [target for row in group for target in row["target_windows"]]
        by_mix[mix] = {
            "tables": len(group), "roots": len({row["root_index"] for row in group}),
            "all_strict_wider_windows": len(targets),
            "two_shanten_no_chi_peng_white_0_or_1": sum(
                target["score_facts"]["own_chi_peng_count"] == 0
                and target["score_facts"]["standard_shanten_after"] == 2
                and target["score_facts"]["white_before"] in (0, 1)
                for target in targets),
            "selected_development": sum(item["mix"] == mix
                                        and item["split"] == "development"
                                        for item in selected),
            "selected_mechanism_locked": sum(item["mix"] == mix
                                             and item["split"] == "mechanism_locked"
                                             for item in selected),
        }
    strata = Counter((item["split"], item["mix"], item["white_before"])
                     for item in selected)
    return {"schema": "g160-multi-action-value-source-summary/1",
            "status": "complete" if len(rows) == planned else "in_progress",
            "tables_completed": len(rows), "tables_planned": planned,
            "by_mix": by_mix,
            "selected_by_split_mix_white": {
                "/".join(map(str, key)): value for key, value in sorted(strata.items())},
            "boundary": "父代可见冲突来源，不是备选行为价值或候选净分。"}


def main() -> None:
    """准确前缀逐桌持久化；完毕后才写固定选样。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run-first", action="store_true")
    parser.add_argument("--max-new", type=int, default=0)
    args = parser.parse_args()
    contract_path = source.g95.g93.paired.CONTRACT
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    versions = source.g95.g93.natural.stage.contract_versions_block(contract)
    all_plans = plans(contract)
    expected = manifest(contract_path)
    scorer = source.g87.c31.load_parent()
    if args.dry_run_first:
        mix, root_index, seat, plan = all_plans[0]
        row = source.run_table(mix, root_index, seat, plan,
                               contract, versions, scorer)
        print(json.dumps({"mix": mix, "root_index": root_index, "seat": seat,
                          "target_windows": len(row["target_windows"])},
                         ensure_ascii=False))
        return
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = _project_file(_PROJECT_ROOT, OUT / "manifest.json")
    if manifest_path.exists():
        if json.loads(manifest_path.read_text(encoding="utf-8")) != expected:
            raise ValueError("G160 既有清单与当前脚本或输入不一致")
    else:
        manifest_path.write_text(json.dumps(expected, ensure_ascii=False,
                                            sort_keys=True, indent=2) + "\n", encoding="utf-8")
    rows_path = _project_file(_PROJECT_ROOT, OUT / "rows.jsonl")
    rows = ([json.loads(line) for line in rows_path.read_text(encoding="utf-8").splitlines()]
            if rows_path.exists() else [])
    if len(rows) > len(all_plans):
        raise ValueError("G160 已有父代表超过预登记范围")
    for old, (mix, root_index, seat, plan) in zip(rows, all_plans):
        if (old["mix"], old["root_index"], old["focal_seat"], old["table_id"]) != (
                mix, root_index, seat, plan.table_id):
            raise ValueError("G160 已有桌不是固定计划的准确前缀")
    added = 0
    with rows_path.open("a", encoding="utf-8") as stream:
        for mix, root_index, seat, plan in all_plans[len(rows):]:
            row = source.run_table(mix, root_index, seat, plan,
                                   contract, versions, scorer)
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
            rows.append(row)
            added += 1
            if added % 16 == 0:
                print(json.dumps({"tables": len(rows),
                                  "selected_so_far": len(_selected(rows))},
                                 ensure_ascii=False), flush=True)
            if args.max_new > 0 and added >= args.max_new:
                break
    selected = _selected(rows)
    result = summary(rows, selected, len(all_plans))
    result["rows_sha256"] = sha(rows_path)
    result["manifest_sha256"] = sha(manifest_path)
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(json.dumps(result, ensure_ascii=False,
                                            sort_keys=True, indent=2) + "\n", encoding="utf-8")
    if result["status"] == "complete":
        (_project_file(_PROJECT_ROOT, OUT / "selection.json")).write_text(json.dumps({
            "schema": "g160-multi-action-value-source-selection/1",
            "manifest_sha256": sha(manifest_path),
            "rows_sha256": sha(rows_path),
            "result_blind": True,
            "selected": selected,
        }, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
