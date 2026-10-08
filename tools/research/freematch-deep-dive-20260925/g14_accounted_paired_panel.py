#!/usr/bin/env python3
"""G14 新根四座成对桌赛：在原评价口径外记录逐小局结算，供收益归因。"""

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
import concurrent.futures
import json
from pathlib import Path
from typing import Any

import g13_accounted_panel as accounted


ROOT = accounted.ROOT
paired = accounted.paired_study
natural = accounted.natural
MIXES = paired.MIXES
SEATS = paired.SEATS
COMPONENTS = ("plain_self_win_delta", "special_self_win_delta",
              "other_win_delta", "draw_delta")
HERE = Path(__file__).resolve().parent


def run_unit(unit: tuple[str, int, int, str, int]) -> dict[str, Any]:
    """每进程只运行一个阶段；逐局旁路不会跨进程污染其他策略臂。"""
    mix, root_index, seat, arm, panel_seed = unit
    contract = json.loads(paired.CONTRACT.read_text(encoding="utf-8"))
    plans = natural.build_seat_stage_plans(
        contract=contract, opponent=mix, root_index=root_index,
        focal_seat=seat, panel_seed=panel_seed)
    stage = accounted.run_accounted_stage(
        plans=plans, candidate_policy_factory=paired.policy_factory(arm),
        opponent_policies=contract["panel"]["opponent_scenarios"][mix]["opponent_policies"],
        versions_block=natural.stage.contract_versions_block(contract),
        step_limit=int(contract["stop"]["step_limit"]),
        value_limits=paired.LIMITS)
    return {"mix": mix, "root_index": root_index, "focal_seat": seat,
            "arm": arm, "stage": stage}


def verify_unit(row: dict[str, Any], *, unit: tuple[str, int, int, str, int],
                tables_per_stage: int) -> None:
    """已完成阶段必须含逐局证据，且拆账与本人完整阶段积分一致。"""
    mix, root_index, seat, arm, _seed = unit
    if any(row.get(key) != value for key, value in
           (("mix", mix), ("root_index", root_index),
            ("focal_seat", seat), ("arm", arm))):
        raise ValueError("阶段身份与运行单元不符")
    stage = row["stage"]
    tables = stage["tables"]
    if stage["status"] != "complete" or len(tables) != tables_per_stage:
        raise ValueError("阶段不完整或桌数不符")
    total = 0
    for table in tables:
        account = table.get("hand_account")
        records = table.get("hand_records")
        if not isinstance(account, dict) or not isinstance(records, list):
            raise ValueError("完整桌缺逐局结算旁路")
        if len(records) != account["complete_hands"]:
            raise ValueError("逐局记录数与收益拆账不符")
        scores = table["scores_by_seat"]
        if (account["focal_table_delta"] != scores[account["focal_seat"]]
                or sum(account[name] for name in COMPONENTS)
                != account["focal_table_delta"]):
            raise ValueError("逐局拆账与完整桌本人积分不符")
        total += account["focal_table_delta"]
    if total != stage["focal_stage_score"]:
        raise ValueError("逐局拆账与完整阶段本人积分不符")


def _write_new(path: Path, data: Any) -> None:
    """原子写入冻结证据，已有产物仅允许逐字相同。"""
    encoded = json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != encoded:
            raise FileExistsError("已有产物不同，拒绝覆盖：" + str(path))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(encoded, encoding="utf-8")
    tmp.replace(path)


def _manifest(*, args: argparse.Namespace, arms: tuple[str, ...],
              tables_per_stage: int) -> dict[str, Any]:
    """绑定候选、父代、规则与两个旁路源码的执行身份。"""
    sources = paired.candidate_sources(arms)
    return {
        "schema": "g14-accounted-paired-panel/1",
        "panel_seed": args.panel_seed,
        "root_start": args.root_start,
        "roots_per_mix": args.roots_per_mix,
        "mixes": list(MIXES),
        "seats": list(SEATS),
        "arms": list(arms),
        "tables_per_stage": tables_per_stage,
        "planned_complete_tables": len(MIXES) * args.roots_per_mix * len(SEATS)
                                   * len(arms) * tables_per_stage,
        "statistical_unit": "opponent_mix×root_index；四座位和各阶段桌先在根内平均",
        "candidate_sources": sources,
        "rules_source_hash": natural.compute_rules_hash(ROOT),
        "r18_v2_release_id": paired.R18_INTEGRATED_POSITIVE_V2_RELEASE_PACKAGE_ID,
        "input_identity": {
            **paired.input_identity(),
            'tools/research/freematch-deep-dive-20260925/g13_hand_accounting.py':
                paired.digest(_project_file(_PROJECT_ROOT, HERE / "g13_hand_accounting.py")),
            'tools/research/freematch-deep-dive-20260925/g13_accounted_panel.py':
                paired.digest(_project_file(_PROJECT_ROOT, HERE / "g13_accounted_panel.py")),
            'tools/research/freematch-deep-dive-20260925/g14_accounted_paired_panel.py':
                paired.digest(Path(__file__)),
        },
    }


def _result(*, args: argparse.Namespace, arms: tuple[str, ...],
            units: list[tuple[str, int, int, str, int]], out: Path,
            tables_per_stage: int) -> dict[str, Any]:
    """先按根聚合四座完整桌，再给出描述性净分和收益分量。"""
    stage_score: dict[tuple[str, int, str], list[int]] = {}
    component: dict[tuple[str, int, str, str], list[int]] = {}
    for unit in units:
        row = json.loads(paired.unit_path(out, unit).read_text(encoding="utf-8"))
        verify_unit(row, unit=unit, tables_per_stage=tables_per_stage)
        mix, root, _seat, arm, _seed = unit
        stage_score.setdefault((mix, root, arm), []).append(row["stage"]["focal_stage_score"])
        for table in row["stage"]["tables"]:
            account = table["hand_account"]
            for name in COMPONENTS:
                component.setdefault((mix, root, arm, name), []).append(account[name])
    roots = []
    for mix in MIXES:
        for root in range(args.root_start, args.root_start + args.roots_per_mix):
            table_means = {arm: sum(stage_score[(mix, root, arm)]) /
                           (len(SEATS) * tables_per_stage) for arm in arms}
            component_means = {arm: {
                name: sum(component[(mix, root, arm, name)]) /
                      (len(SEATS) * tables_per_stage) for name in COMPONENTS
            } for arm in arms}
            for arm in arms:
                if abs(sum(component_means[arm].values()) - table_means[arm]) > 1e-9:
                    raise ValueError("根级收益分量与净分不守恒")
            roots.append({
                "mix": mix, "root_index": root,
                "table_score_mean_by_arm": table_means,
                "component_mean_by_arm": component_means,
                "delta_vs_baseline_per_table": {
                    arm: table_means[arm] - table_means[arms[0]] for arm in arms[1:]},
                "component_delta_vs_baseline_per_table": {
                    arm: {name: component_means[arm][name] - component_means[arms[0]][name]
                          for name in COMPONENTS} for arm in arms[1:]},
            })
    return {
        "schema": "g14-accounted-paired-result/1",
        "baseline_arm": arms[0],
        "independent_root_clusters": len(roots),
        "complete_tables": len(units) * tables_per_stage,
        "root_clusters": roots,
        "descriptive_mean_delta_vs_baseline_per_table": {
            arm: sum(row["delta_vs_baseline_per_table"][arm] for row in roots) / len(roots)
            for arm in arms[1:]},
        "boundary": "开发根描述值；单局是收入分量而非独立统计单位，发布仍需全新根确认。",
    }


def main() -> None:
    """冻结新根面板身份，支持阶段级恢复，任何缺局或分数不守恒即失败。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--panel-seed", type=int, required=True)
    parser.add_argument("--root-start", type=int, default=1)
    parser.add_argument("--roots-per-mix", type=int, default=1)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--arms", required=True,
                        help="逗号分隔，第一臂为基准；candidate@ 后接仓库相对源码路径")
    args = parser.parse_args()
    if (args.root_start < 1 or args.roots_per_mix < 1
            or args.root_start + args.roots_per_mix - 1 > natural.MAX_ROOT_INDEX
            or not 1 <= args.workers <= 6):
        parser.error("根起点/根数必须在 1..99，工作进程必须在 1..6")
    arms = paired.parse_arms(args.arms)
    if arms[0] != "r18_v2":
        parser.error("G14 必须以冻结 R18 v2 为首臂基线")
    contract = json.loads(paired.CONTRACT.read_text(encoding="utf-8"))
    tables_per_stage = int(contract["group"]["tables_per_group"])
    manifest = _manifest(args=args, arms=arms, tables_per_stage=tables_per_stage)
    _write_new(args.out / "manifest.json", manifest)
    units = [(mix, root, seat, arm, args.panel_seed)
             for mix in MIXES
             for root in range(args.root_start, args.root_start + args.roots_per_mix)
             for seat in SEATS for arm in arms]
    pending = []
    for unit in units:
        path = paired.unit_path(args.out, unit)
        if path.exists():
            verify_unit(json.loads(path.read_text(encoding="utf-8")), unit=unit,
                        tables_per_stage=tables_per_stage)
        else:
            pending.append(unit)
    if pending:
        with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(run_unit, unit): unit for unit in pending}
            for future in concurrent.futures.as_completed(futures):
                unit = futures[future]
                row = future.result()
                path = paired.unit_path(args.out, unit)
                _write_new(path, row)
                verify_unit(row, unit=unit, tables_per_stage=tables_per_stage)
    result = _result(args=args, arms=arms, units=units,
                     out=args.out, tables_per_stage=tables_per_stage)
    _write_new(args.out / "result.json", result)
    print(json.dumps({"out": str(args.out),
                      "complete_tables": result["complete_tables"],
                      "independent_root_clusters": result["independent_root_clusters"],
                      "descriptive_mean_delta_vs_baseline_per_table":
                          result["descriptive_mean_delta_vs_baseline_per_table"]},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
