#!/usr/bin/env python3
"""G261：当前规则研究父代与候选源码的同墙四座八局结算面板。

旧发布包的规则摘要守卫保持原样；本入口只用于离线研究，不生成发布身份。
包装型候选可复用 research_parent_factory 和 G14 的逐局结算执行器。
"""

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
from concurrent.futures import ProcessPoolExecutor, as_completed
from hashlib import sha256
import json
from pathlib import Path

import g14_accounted_paired_panel as panel
from g193_early_shape_policy import research_parent_factory
from hangma_bot.policy.r18_integrated_positive_v2 import (
    R18_INTEGRATED_POSITIVE_V2_SHA256,
    R18_INTEGRATED_POSITIVE_V2_SOURCE,
)


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
RESEARCH_PARENT_ARM = "r18_v2_current_rules_research"


def digest(path: Path) -> str:
    """以源码字节固定研究装配身份。"""

    return sha256(path.read_bytes()).hexdigest()


def arms_for(candidate_arm: str) -> tuple[str, str]:
    """只接受一个可校验的离线候选源码臂，固定当前规则研究父代。"""

    if not candidate_arm.startswith(panel.paired.CANDIDATE_ARM_PREFIX):
        raise ValueError("G261 候选必须是 candidate@<仓库相对源码路径>")
    validated = panel.paired.parse_arms("r18_v2," + candidate_arm)
    if len(validated) != 2 or validated[1] != candidate_arm:
        raise ValueError("G261 只允许一个候选源码臂")
    return RESEARCH_PARENT_ARM, validated[1]


def policy_factory(arm: str):
    """研究父代复用 G193 工厂；候选仍由既有受限源码装配器创建。"""

    if arm == RESEARCH_PARENT_ARM:
        return research_parent_factory
    if arm.startswith(panel.paired.CANDIDATE_ARM_PREFIX):
        return panel.paired.policy_factory(arm)
    raise ValueError("G261 不接受旧发布包或未知臂：" + arm)


def run_unit(unit: tuple[str, int, int, str, int]) -> dict:
    """双臂共用同一规则配置与牌山计划，各自独立创建策略实例。"""

    mix, root, seat, arm, panel_seed = unit
    contract = json.loads(panel.paired.CONTRACT.read_text(encoding="utf-8"))
    plans = panel.natural.build_seat_stage_plans(
        contract=contract, opponent=mix, root_index=root,
        focal_seat=seat, panel_seed=panel_seed)
    stage = panel.accounted.run_accounted_stage(
        plans=plans, candidate_policy_factory=policy_factory(arm),
        opponent_policies=contract["panel"]["opponent_scenarios"][mix]["opponent_policies"],
        versions_block=panel.natural.stage.contract_versions_block(contract),
        step_limit=int(contract["stop"]["step_limit"]),
        value_limits=panel.paired.LIMITS)
    return {"mix": mix, "root_index": root, "focal_seat": seat,
            "arm": arm, "stage": stage}


def manifest(args: argparse.Namespace, arms: tuple[str, str]) -> dict:
    """保留 G14 面板身份，并显式声明研究父代不拥有旧发布资格。"""

    contract = json.loads(panel.paired.CONTRACT.read_text(encoding="utf-8"))
    tables_per_stage = int(contract["group"]["tables_per_group"])
    if sha256(R18_INTEGRATED_POSITIVE_V2_SOURCE.encode("utf-8")).hexdigest() != (
        R18_INTEGRATED_POSITIVE_V2_SHA256
    ):
        raise ValueError("G261 冻结 R18 v2 评分源码摘要漂移")
    result = panel._manifest(args=args, arms=arms,
                             tables_per_stage=tables_per_stage)
    result.update({
        "schema": "g261-current-rules-paired-manifest/1",
        "r18_v2_release_id": None,
        "parent_binding": "research_current_rules_not_release_package",
        "parent_algorithm_sha256": R18_INTEGRATED_POSITIVE_V2_SHA256,
        "research_rules_source_hash": panel.natural.compute_rules_hash(ROOT),
        "boundary": "当前规则离线研究；不改变或冒充旧 R18 v2 发布包准入。",
    })
    result["input_identity"].update({
        'tools/research/freematch-deep-dive-20260925/g193_early_shape_policy.py':
            digest(_project_file(_PROJECT_ROOT, HERE / "g193_early_shape_policy.py")),
        'tools/research/freematch-deep-dive-20260925/g261_current_rules_panel.py':
            digest(Path(__file__)),
    })
    return result


def main() -> None:
    """冻结一条当前规则双臂面板；断点恢复时拒绝清单或阶段漂移。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--panel-seed", type=int, required=True)
    parser.add_argument("--root-start", type=int, default=1)
    parser.add_argument("--roots-per-mix", type=int, default=1)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--candidate-arm", required=True,
                        help="candidate@ 后接仓库相对评分源码路径")
    args = parser.parse_args()
    if (args.root_start < 1 or args.roots_per_mix < 1
            or args.root_start + args.roots_per_mix - 1 > panel.natural.MAX_ROOT_INDEX
            or not 1 <= args.workers <= 6):
        parser.error("根起点／根数需在 1..99，工作进程需在 1..6")
    arms = arms_for(args.candidate_arm)
    frozen = manifest(args, arms)
    panel._write_new(args.out / "manifest.json", frozen)
    units = [(mix, root, seat, arm, args.panel_seed)
             for mix in panel.MIXES
             for root in range(args.root_start, args.root_start + args.roots_per_mix)
             for seat in panel.SEATS for arm in arms]
    pending = []
    for unit in units:
        path = panel.paired.unit_path(args.out, unit)
        if path.exists():
            panel.verify_unit(json.loads(path.read_text(encoding="utf-8")),
                              unit=unit, tables_per_stage=frozen["tables_per_stage"])
        else:
            pending.append(unit)
    if pending:
        with ProcessPoolExecutor(max_workers=args.workers) as workers:
            futures = {workers.submit(run_unit, unit): unit for unit in pending}
            for future in as_completed(futures):
                unit = futures[future]
                row = future.result()
                panel.verify_unit(row, unit=unit,
                                  tables_per_stage=frozen["tables_per_stage"])
                panel._write_new(panel.paired.unit_path(args.out, unit), row)
    result = panel._result(args=args, arms=arms, units=units,
                           out=args.out, tables_per_stage=frozen["tables_per_stage"])
    result["manifest_sha256"] = digest(args.out / "manifest.json")
    result["parent_binding"] = frozen["parent_binding"]
    panel._write_new(args.out / "result.json", result)
    print(json.dumps({"complete_tables": result["complete_tables"],
                      "independent_root_clusters": result["independent_root_clusters"],
                      "mean_delta": result["descriptive_mean_delta_vs_baseline_per_table"]},
                     ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
