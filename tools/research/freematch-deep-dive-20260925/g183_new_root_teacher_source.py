#!/usr/bin/env python3
"""G183：全新 H/M 根的冻结 R18 v2 父代表与结果盲教师入口。"""

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

import g160_multi_action_value_source as g160


HERE = Path(__file__).resolve().parent
PLAN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G183-NEW-ROOT-TEACHER-SOURCE-PREREG-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g183-new-root-teacher-source-20260928')
PANEL_SEED = 20261228183
ROOTS = tuple(range(1, 49))
DEVELOPMENT_MAX_ROOT = 32


def sha(path: Path) -> str:
    """绑定计划、父代、面板契约及采集器原始字节。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def plans(contract: dict) -> list[tuple[str, int, int, object]]:
    """新面板每个牌山根按 H/M 与四座完整换位。"""

    result = []
    for root in ROOTS:
        for mix in ("H", "M"):
            for seat in range(4):
                plan = g160.source.g95.g93.natural.build_seat_stage_plans(
                    contract=contract, opponent=mix, root_index=root,
                    focal_seat=seat, panel_seed=PANEL_SEED)[0]
                result.append((mix, root, seat, plan))
    return result


def manifest(contract_path: Path) -> dict:
    """按清单防止续跑时源代码或面板静默漂移。"""

    paths = {
        "prereg": PLAN, "script": Path(__file__),
        "g160_selection": Path(g160.__file__),
        "g126_capture": Path(g160.source.__file__),
        "runtime": Path(g160.source.g95.__file__),
        "contract": contract_path,
        "parent_source": _project_file(_PROJECT_ROOT, HERE.parents[1] / "src/hangma_bot/policy/r18_integrated_positive_v2.py"),
    }
    return {
        "schema": "g183-new-root-teacher-source-manifest/1",
        "panel_seed": PANEL_SEED, "roots": list(ROOTS),
        "development_roots": [root for root in ROOTS if root <= DEVELOPMENT_MAX_ROOT],
        "mechanism_locked_roots": [root for root in ROOTS if root > DEVELOPMENT_MAX_ROOT],
        "tables_planned": len(ROOTS) * 2 * 4,
        "parent_scorer_sha256": g160.source.g87.c31.R18_INTEGRATED_POSITIVE_V2_SHA256,
        "input_sha256": {name: sha(path) for name, path in paths.items()},
        "boundary": "全新结果盲父代表；不运行备选或打开锁定来源的结果标签。",
    }


def selected(rows: list[dict]) -> list[dict]:
    """原封复用 G160 行动前最小摘要选样，仅更换事前根级拆分。"""

    chosen = g160._selected(rows)
    return [{**item, "split": ("development" if item["root_index"] <= DEVELOPMENT_MAX_ROOT
                               else "mechanism_locked")}
            for item in chosen]


def coverage(rows: list[dict], chosen: list[dict], planned: int) -> dict:
    """桌、窗、根分开记账，不将同根四座当作独立来源。"""

    source_summary = g160.summary(rows, chosen, planned)
    strata = Counter((item["split"], item["mix"], item["white_before"]) for item in chosen)
    roots_by_stratum = {"/".join(map(str, key)): len({item["root_index"] for item in chosen
                                               if (item["split"], item["mix"],
                                                   item["white_before"]) == key})
                        for key in sorted(strata)}
    def roots(split: str, mix: str, white: int | None = None) -> int:
        return len({item["root_index"] for item in chosen
                    if item["split"] == split and item["mix"] == mix
                    and (white is None or item["white_before"] == white)})
    ready = (len(rows) == planned and
             all(roots("development", mix) >= 20
                 and all(roots("development", mix, white) >= 8 for white in (0, 1))
                 and roots("mechanism_locked", mix) >= 8
                 and all(roots("mechanism_locked", mix, white) >= 4
                         for white in (0, 1))
                 for mix in ("H", "M")))
    return {"schema": "g183-new-root-teacher-source-summary/1",
            "status": "complete" if len(rows) == planned else "in_progress",
            "tables_completed": len(rows), "tables_planned": planned,
            "by_mix": source_summary["by_mix"],
            "selected_by_split_mix_white": source_summary["selected_by_split_mix_white"],
            "roots_by_split_mix_white": roots_by_stratum,
            "source_coverage_gate_pass": ready,
            "boundary": "仅结果盲父代观察覆盖；无备选收益、模型或发布证据。"}


def main() -> None:
    """准确前缀断点续跑；完成后才冻结选样及来源门。"""

    parser = argparse.ArgumentParser()
    parser.add_argument("--max-new", type=int, default=0)
    parser.add_argument("--dry-run-first", action="store_true")
    args = parser.parse_args()
    contract_path = g160.source.g95.g93.paired.CONTRACT
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    versions = g160.source.g95.g93.natural.stage.contract_versions_block(contract)
    schedule = plans(contract)
    expected = manifest(contract_path)
    scorer = g160.source.g87.c31.load_parent()
    if args.dry_run_first:
        mix, root, seat, plan = schedule[0]
        row = g160.source.run_table(mix, root, seat, plan, contract, versions, scorer)
        print(json.dumps({"mix": mix, "root": root, "seat": seat,
                          "target_windows": len(row["target_windows"])},
                         ensure_ascii=False), flush=True)
        return
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = _project_file(_PROJECT_ROOT, OUT / "manifest.json")
    if manifest_path.exists():
        if json.loads(manifest_path.read_text(encoding="utf-8")) != expected:
            raise ValueError("G183 既有清单与当前冻结输入不同，拒绝混写")
    else:
        manifest_path.write_text(json.dumps(expected, ensure_ascii=False,
                                            sort_keys=True, indent=2) + "\n", encoding="utf-8")
    rows_path = _project_file(_PROJECT_ROOT, OUT / "rows.jsonl")
    rows = ([json.loads(line) for line in rows_path.read_text(encoding="utf-8").splitlines()]
            if rows_path.exists() else [])
    if len(rows) > len(schedule):
        raise ValueError("G183 已有父代表超出事前赛程")
    for previous, (mix, root, seat, plan) in zip(rows, schedule):
        if (previous["mix"], previous["root_index"], previous["focal_seat"],
                previous["table_id"]) != (mix, root, seat, plan.table_id):
            raise ValueError("G183 已有结果并非事前赛程准确前缀")
    added = 0
    with rows_path.open("a", encoding="utf-8") as stream:
        for mix, root, seat, plan in schedule[len(rows):]:
            row = g160.source.run_table(mix, root, seat, plan,
                                        contract, versions, scorer)
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
            rows.append(row)
            added += 1
            if len(rows) % 16 == 0:
                print(json.dumps({"tables": len(rows),
                                  "selected_so_far": len(selected(rows))},
                                 ensure_ascii=False), flush=True)
            if args.max_new > 0 and added >= args.max_new:
                break
    chosen = selected(rows)
    summary = coverage(rows, chosen, len(schedule))
    summary["rows_sha256"] = sha(rows_path)
    summary["manifest_sha256"] = sha(manifest_path)
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(json.dumps(summary, ensure_ascii=False,
                                            sort_keys=True, indent=2) + "\n", encoding="utf-8")
    if summary["status"] == "complete":
        (_project_file(_PROJECT_ROOT, OUT / "selection.json")).write_text(json.dumps({
            "schema": "g183-new-root-teacher-source-selection/1",
            "manifest_sha256": sha(manifest_path),
            "rows_sha256": sha(rows_path),
            "result_blind": True,
            "selected": chosen,
        }, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": summary["status"],
                      "tables_completed": summary["tables_completed"],
                      "source_coverage_gate_pass": summary["source_coverage_gate_pass"],
                      "strata": summary["roots_by_split_mix_white"]},
                     ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
