#!/usr/bin/env python3
"""G166：独立根的结果盲父代表与每池每白板层各十六窗固定选样。"""

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
import json
import os
from pathlib import Path

import g160_multi_action_value_source as g160


HERE = Path(__file__).resolve().parent
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G166-FRESH-ROOT-LEARNABILITY-PREREG-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g166-fresh-root-learnability-source-20260928')
PANEL_SEED = 2026112001
ROOTS = tuple(range(1, 65))
PER_STRATUM = 16


def plans(contract: dict) -> list[tuple[str, int, int, object]]:
    """所有计划仅由冻结种子、根、对手池、座位及赛事合同导出。"""
    result = []
    for root_index in ROOTS:
        for mix in ("H", "M"):
            for seat in range(4):
                plan = g160.source.g95.g93.natural.build_seat_stage_plans(
                    contract=contract, opponent=mix, root_index=root_index,
                    focal_seat=seat, panel_seed=PANEL_SEED)[0]
                result.append((mix, root_index, seat, plan))
    return result


def manifest(contract_path: Path) -> dict:
    """绑定预登记、采集器、生产父代和真实赛事合同的字节摘要。"""
    paths = {
        "prereg": PREREG,
        "script": Path(__file__),
        "g160_source": Path(g160.__file__),
        "g126_capture": Path(g160.source.__file__),
        "g95_runtime": Path(g160.source.g95.__file__),
        "contract": contract_path,
        "parent_source": _project_file(_PROJECT_ROOT, HERE.parents[1] / "src/hangma_bot/policy/r18_integrated_positive_v2.py"),
    }
    return {
        "schema": "g166-fresh-root-learnability-source-manifest/1",
        "panel_seed": PANEL_SEED,
        "roots": list(ROOTS),
        "tables_planned": len(ROOTS) * 2 * 4,
        "per_stratum": PER_STRATUM,
        "parent_scorer_sha256": g160.source.g87.c31.R18_INTEGRATED_POSITIVE_V2_SHA256,
        "input_sha256": {name: g160.sha(path) for name, path in paths.items()},
        "boundary": "仅采集冻结父代来源并结果盲选样，不运行备选续打。",
    }


def selected(rows: list[dict]) -> list[dict]:
    """每池×根只选预分配白板层的最小观察哈希窗；每层取最前十六根。"""
    buckets: dict[tuple[str, int], list[dict]] = {}
    for row in rows:
        assigned_white = 0 if row["root_index"] <= 32 else 1
        for target in row["target_windows"]:
            facts = target["score_facts"]
            if (facts["own_chi_peng_count"] != 0
                    or facts["standard_shanten_after"] != 2
                    or facts["white_before"] != assigned_white):
                continue
            key = (row["mix"], row["root_index"])
            buckets.setdefault(key, []).append({
                "mix": row["mix"],
                "root_index": row["root_index"],
                "focal_seat": row["focal_seat"],
                "round_no": target["round_no"],
                "observation_sha256": target["observation_sha256"],
                "parent_action": target["parent_action"],
                "alternate_action": target["alternate_action"],
                "white_before": assigned_white,
                "score_facts": facts,
            })
    by_stratum: dict[tuple[str, int], list[dict]] = {}
    for (mix, root_index), group in sorted(buckets.items()):
        choice = min(group, key=lambda item: (
            item["observation_sha256"], item["focal_seat"], item["round_no"]))
        white = 0 if root_index <= 32 else 1
        by_stratum.setdefault((mix, white), []).append(choice)
    return [item for stratum in (("H", 0), ("H", 1), ("M", 0), ("M", 1))
            for item in by_stratum.get(stratum, [])[:PER_STRATUM]]


def summary(rows: list[dict], chosen: list[dict], planned: int) -> dict:
    """区分完整桌覆盖、可选池×根和固定选样，不读任何备选收益。"""
    counts = Counter((item["mix"], item["white_before"]) for item in chosen)
    full = len(rows) == planned
    return {
        "schema": "g166-fresh-root-learnability-source-summary/1",
        "status": "complete" if full else "in_progress",
        "tables_completed": len(rows),
        "tables_planned": planned,
        "selected_by_pool_white": {
            f"{mix}/{white}": counts[(mix, white)]
            for mix in ("H", "M") for white in (0, 1)
        },
        "coverage_sufficient": full and all(
            counts[(mix, white)] == PER_STRATUM
            for mix in ("H", "M") for white in (0, 1)),
        "boundary": "结果盲父代来源；没有备选单局收益或候选准入。",
    }


def main() -> None:
    """逐桌持久化并核精确前缀；只在全 512 桌完成后落盘选样。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run-first", action="store_true")
    parser.add_argument("--max-new", type=int, default=0)
    args = parser.parse_args()
    contract_path = g160.source.g95.g93.paired.CONTRACT
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    versions = g160.source.g95.g93.natural.stage.contract_versions_block(contract)
    all_plans = plans(contract)
    expected = manifest(contract_path)
    scorer = g160.source.g87.c31.load_parent()
    if args.dry_run_first:
        mix, root_index, seat, plan = all_plans[0]
        row = g160.source.run_table(mix, root_index, seat, plan,
                                    contract, versions, scorer)
        print(json.dumps({"mix": mix, "root_index": root_index, "seat": seat,
                          "target_windows": len(row["target_windows"])},
                         ensure_ascii=False))
        return
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = _project_file(_PROJECT_ROOT, OUT / "manifest.json")
    if manifest_path.exists():
        if json.loads(manifest_path.read_text(encoding="utf-8")) != expected:
            raise ValueError("G166 已有清单与当前脚本或输入不一致")
    else:
        manifest_path.write_text(json.dumps(expected, ensure_ascii=False,
                                            sort_keys=True, indent=2) + "\n", encoding="utf-8")
    rows_path = _project_file(_PROJECT_ROOT, OUT / "rows.jsonl")
    rows = ([json.loads(line) for line in rows_path.read_text(encoding="utf-8").splitlines()]
            if rows_path.exists() else [])
    if len(rows) > len(all_plans):
        raise ValueError("G166 已有父代表超过预登记范围")
    for old, (mix, root_index, seat, plan) in zip(rows, all_plans):
        if (old["mix"], old["root_index"], old["focal_seat"], old["table_id"]) != (
                mix, root_index, seat, plan.table_id):
            raise ValueError("G166 已有桌不是固定计划的准确前缀")
    added = 0
    with rows_path.open("a", encoding="utf-8") as stream:
        for mix, root_index, seat, plan in all_plans[len(rows):]:
            row = g160.source.run_table(mix, root_index, seat, plan,
                                        contract, versions, scorer)
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
            rows.append(row)
            added += 1
            if added % 16 == 0:
                print(json.dumps({"tables": len(rows),
                                  "selected_so_far": len(selected(rows))},
                                 ensure_ascii=False), flush=True)
            if args.max_new > 0 and added >= args.max_new:
                break
    chosen = selected(rows)
    result = summary(rows, chosen, len(all_plans))
    result["rows_sha256"] = g160.sha(rows_path)
    result["manifest_sha256"] = g160.sha(manifest_path)
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(json.dumps(result, ensure_ascii=False,
                                            sort_keys=True, indent=2) + "\n", encoding="utf-8")
    if result["status"] == "complete":
        (_project_file(_PROJECT_ROOT, OUT / "selection.json")).write_text(json.dumps({
            "schema": "g166-fresh-root-learnability-source-selection/1",
            "manifest_sha256": g160.sha(manifest_path),
            "rows_sha256": g160.sha(rows_path),
            "result_blind": True,
            "selected": chosen,
        }, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
