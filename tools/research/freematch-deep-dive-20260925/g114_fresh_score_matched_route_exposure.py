#!/usr/bin/env python3
"""G114：在全新 H/M 根结果盲采集宽面冲突、局部机会与父代评分差。"""

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
import json
import math
import os
from pathlib import Path

import g87_post_claim_score_trace as g87
import g95_wider_discard_same_hand_preflight as g95
import g108_fresh_hm_route_exposure as g108


HERE = Path(__file__).resolve().parent
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G114-FRESH-SCORE-MATCHED-ROUTE-EXPOSURE-PREREG-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g114-fresh-score-matched-route-exposure-20260928')
PANEL_SEED = 2026111301
ROOTS = tuple(range(1, 33))


def plans(contract: dict) -> list[tuple[str, int, int, object]]:
    """交错对手池的固定 256 张父代表计划。"""
    result = []
    for root_index in ROOTS:
        for mix in ("H", "M"):
            for seat in range(4):
                plan = g95.g93.natural.build_seat_stage_plans(
                    contract=contract, opponent=mix, root_index=root_index,
                    focal_seat=seat, panel_seed=PANEL_SEED)[0]
                result.append((mix, root_index, seat, plan))
    return result


def scored_target(record, scorer) -> dict:
    """同一可见决策前状态重算冻结父代评分，绝不读取后续结算。"""
    target = g108.target_row(record)
    request = record.request
    view = g87.g05.build_scoring_view(
        request, value_limits=g87.c31.VALUE_LIMITS).candidate_view()
    scored = scorer(view)
    if scored["status"] != "SCORED":
        raise ValueError("G114 冻结父代评分失败")
    entries = {entry["action_key"]: entry for entry in scored["entries"]}
    scores = {key: float(entry["score"]) for key, entry in entries.items()}
    parent, alternate = record.parent_key, record.alternate_key
    if (g87.argmax(scores) != parent or parent not in entries
            or alternate not in entries):
        raise ValueError("G114 父代评分动作与完整父代表不一致")
    gap = scores[parent] - scores[alternate]
    if not math.isfinite(gap) or gap < -1e-8:
        raise ValueError("G114 父代分差非法")
    components = {name: g87.component(entries[parent]["trace"], name)
                  - g87.component(entries[alternate]["trace"], name)
                  for name in g87.COMPONENTS}
    if abs(sum(components.values()) - gap) > 1e-8:
        raise ValueError("G114 评分分量不守恒")
    observation = request.observation
    target["score_facts"] = {
        "parent_score_gap": gap,
        "component_parent_minus_alternate": components,
        "ordinary_codes_delta": record.facts[alternate]["ordinary_codes"]
        - record.facts[parent]["ordinary_codes"],
        "public_unseen_capacity_delta":
        record.facts[alternate]["public_unseen_capacity"]
        - record.facts[parent]["public_unseen_capacity"],
        "standard_shanten_after": record.facts[parent]["standard_shanten_after"],
        "own_chi_peng_count": sum(meld.kind in ("chi", "peng")
                                 for meld in observation.melds[observation.seat]),
        "remaining_tile_count": observation.remaining_tile_count,
    }
    return target


def run_table(mix: str, root_index: int, seat: int, plan,
              contract: dict, versions: dict, scorer) -> dict:
    """全桌照冻结父代运行，保存各完整单局首冲突的可见事实。"""
    original = g95.CaptureWiderPolicy
    g95.CaptureWiderPolicy = g108.CaptureEveryHandPolicy
    try:
        captured, _, _, _, hands, _ = g95.run_full(plan, contract, versions, mix)
    finally:
        g95.CaptureWiderPolicy = original
    if len(hands) != int(versions["rounds_per_game"]):
        raise ValueError("G114 父代表不是完整八单局")
    targets = [scored_target(captured.records[number], scorer)
               for number in sorted(captured.records)]
    return {"mix": mix, "root_index": root_index, "focal_seat": seat,
            "table_id": plan.table_id, "seed": plan.seed,
            "status": "complete", "hands": len(hands),
            "target_windows": targets}


def manifest(contract_path: Path) -> dict:
    """记录不可混写的结果盲面板及评分代码身份。"""
    paths = {"prereg": PREREG, "script": Path(__file__),
             "contract": contract_path, "g95": Path(g95.__file__),
             "g108": Path(g108.__file__), "g106": Path(g108.g106.__file__),
             "g87": Path(g87.__file__),
             "g93": Path(g95.g93.__file__)}
    return {"schema": "g114-fresh-score-matched-route-manifest/1",
            "panel_seed": PANEL_SEED, "roots": list(ROOTS),
            "tables_planned": len(ROOTS) * 2 * 4,
            "parent_scorer_sha256": g87.c31.R18_INTEGRATED_POSITIVE_V2_SHA256,
            "input_sha256": {name: g108.sha(path) for name, path in paths.items()},
            "boundary": "整桌只用于可见目标窗采集；未来结算不参与机会与评分。"}


def read_existing(expected: dict) -> list[dict]:
    """仅在清单一致时读取已完成整桌前缀。"""
    if not OUT.exists():
        return []
    recorded = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    if recorded != expected:
        raise ValueError("G114 已有清单不一致，拒绝混写")
    rows_path = _project_file(_PROJECT_ROOT, OUT / "rows.jsonl")
    return ([json.loads(line) for line in rows_path.read_text(encoding="utf-8").splitlines()]
            if rows_path.exists() else [])


def summary(rows: list[dict], planned: int) -> dict:
    """按对手池与独立根报告机会覆盖，暂不读取任何反事实收益。"""
    by_mix = {}
    for mix in ("H", "M"):
        group = [row for row in rows if row["mix"] == mix]
        targets = [target for row in group for target in row["target_windows"]]
        high = [target for target in targets
                if target["status"] == "complete"
                and (target["delta"]["high_opportunities"]["parent_only"]
                     or target["delta"]["high_opportunities"]["alternate_only"])]
        by_mix[mix] = {
            "tables": len(group), "roots": len({row["root_index"] for row in group}),
            "target_windows": len(targets),
            "opportunity_complete": sum(target["status"] == "complete"
                                        for target in targets),
            "opportunity_unavailable": sum(target["status"] == "unavailable"
                                           for target in targets),
            "high_difference_windows": len(high),
            "high_difference_roots": len({row["root_index"] for row in group
                                          if any(target in high for target in row["target_windows"])}),
            "high_shanten": sorted({target["score_facts"]["standard_shanten_after"]
                                     for target in high}),
        }
    return {"schema": "g114-fresh-score-matched-route-summary/1",
            "status": "complete" if len(rows) == planned else "in_progress",
            "tables_completed": len(rows), "tables_planned": planned,
            "by_mix": by_mix,
            "boundary": "行动前可见暴露，不是高番到达概率或完整桌候选效果。"}


def main() -> None:
    """按预登记顺序逐桌保存并允许从精确前缀续跑。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run-first", action="store_true")
    parser.add_argument("--max-new", type=int, default=0)
    args = parser.parse_args()
    contract_path = g95.g93.paired.CONTRACT
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    versions = g95.g93.natural.stage.contract_versions_block(contract)
    all_plans = plans(contract)
    expected = manifest(contract_path)
    if len(all_plans) != expected["tables_planned"]:
        raise ValueError("G114 计划数量不守恒")
    scorer = g87.c31.load_parent()
    if args.dry_run_first:
        mix, root_index, seat, plan = all_plans[0]
        row = run_table(mix, root_index, seat, plan, contract, versions, scorer)
        print(json.dumps({"mix": mix, "root": root_index, "seat": seat,
                          "targets": len(row["target_windows"]),
                          "statuses": [target["status"] for target in row["target_windows"]]},
                         ensure_ascii=False))
        return
    rows = read_existing(expected)
    for old, (mix, root_index, seat, plan) in zip(rows, all_plans):
        if (old["mix"], old["root_index"], old["focal_seat"], old["table_id"]) != (
            mix, root_index, seat, plan.table_id,
        ):
            raise ValueError("G114 已有行不是冻结计划前缀")
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = _project_file(_PROJECT_ROOT, OUT / "manifest.json")
    if not manifest_path.exists():
        manifest_path.write_text(json.dumps(expected, ensure_ascii=False,
                                            sort_keys=True, indent=2) + "\n", encoding="utf-8")
    added = 0
    with (_project_file(_PROJECT_ROOT, OUT / "rows.jsonl")).open("a", encoding="utf-8") as stream:
        for mix, root_index, seat, plan in all_plans[len(rows):]:
            row = run_table(mix, root_index, seat, plan, contract, versions, scorer)
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
            rows.append(row)
            added += 1
            if added % 8 == 0:
                print(json.dumps({"tables": len(rows),
                                  "by_mix": summary(rows, len(all_plans))["by_mix"]},
                                 ensure_ascii=False, sort_keys=True), flush=True)
            if args.max_new > 0 and added >= args.max_new:
                break
    result = summary(rows, len(all_plans))
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(json.dumps(result, ensure_ascii=False,
                                            sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
