#!/usr/bin/env python3
"""G244：同 G243 牌山原样运行 G239，三臂根级拆账。"""

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
from concurrent.futures import ProcessPoolExecutor, as_completed
from hashlib import sha256
import json
from pathlib import Path
import random
from statistics import mean

import g14_accounted_paired_panel as panel
import g239_numeric_route_policy as g239
import g243_competing_risk_filter_development as g243


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
PLAN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G244-SAME-WALL-FILTER-ATTRIBUTION-PREREG-2026-09-29.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g244-same-wall-filter-attribution-20260929')
ARM = "g239_numeric_route"
REPLICATES = 20_000
BOOTSTRAP_SEED = 20261229444
COMPONENTS = panel.COMPONENTS


def digest(path: Path) -> str:
    """绑定原文文件，不把目录状态冒充可复算证据。"""
    return sha256(path.read_bytes()).hexdigest()


def unit_path(mix: str, root: int, seat: int) -> Path:
    """G239 第三臂阶段身份沿用同一 G243 牌山根。"""
    return panel.paired.unit_path(OUT, (mix, root, seat, ARM, g243.SEED))


def run_unit(unit: tuple[str, int, int]) -> dict:
    """只换冻结 G239 策略，计划、对手、种子同 G243。"""
    mix, root, seat = unit
    contract = json.loads(panel.paired.CONTRACT.read_text(encoding="utf-8"))
    plans = panel.natural.build_seat_stage_plans(
        contract=contract, opponent=mix, root_index=root,
        focal_seat=seat, panel_seed=g243.SEED)
    metrics: list[dict] = []
    stage = panel.accounted.run_accounted_stage(
        plans=plans, candidate_policy_factory=g239.policy_factory(metrics),
        opponent_policies=contract["panel"]["opponent_scenarios"][mix][
            "opponent_policies"],
        versions_block=panel.natural.stage.contract_versions_block(contract),
        step_limit=int(contract["stop"]["step_limit"]),
        value_limits=panel.paired.LIMITS)
    stage["g244_metrics"] = metrics
    return {"mix": mix, "root_index": root, "focal_seat": seat,
            "arm": ARM, "stage": stage}


def manifest() -> dict:
    """冻结 G243 全部阶段原文摘要及第三臂源码后再运行。"""
    contract = json.loads(panel.paired.CONTRACT.read_text(encoding="utf-8"))
    stages = sorted((g243.OUT / "stages").glob("*.json"))
    if len(stages) != 256:
        raise ValueError("G244 来源 G243 阶段未齐")
    return {
        "schema": "g244-same-wall-filter-attribution-manifest/1",
        "panel_seed": g243.SEED,
        "mixes": list(panel.MIXES), "roots": list(g243.ROOTS),
        "seats": list(panel.SEATS), "third_arm": ARM,
        "planned_third_arm_tables": 256,
        "tables_per_stage": int(contract["group"]["tables_per_group"]),
        "rules_source_hash": panel.natural.compute_rules_hash(ROOT),
        "input_sha256": {str(path.relative_to(ROOT)): digest(path) for path in (
            PLAN, Path(__file__), Path(g239.__file__),
            _project_file(_PROJECT_ROOT, HERE / "g237_numeric_inversion_policy.py"),
            g243.OUT / "manifest.json", g243.OUT / "result.json",
            g243.OUT / "analysis.json", panel.paired.CONTRACT)},
        "g243_stage_sha256": {path.name: digest(path) for path in stages},
        "boundary": "同牌山第三臂失败归因；不得改变 G243 已失败的继续门。",
    }


def interval(values: list[float], rng: random.Random) -> list[float]:
    """只重采样独立牌山根，四座两桌相关性留在根内。"""
    samples = sorted(mean(rng.choice(values) for _ in values)
                     for _ in range(REPLICATES))
    return [samples[int(0.025 * REPLICATES)],
            samples[int(0.975 * REPLICATES) - 1]]


def analyze(frozen: dict) -> dict:
    """三臂八桌根内均值与已提交 G243 收益逐根恒等。"""
    original = json.loads((g243.OUT / "result.json").read_text(encoding="utf-8"))
    clusters = {(row["mix"], row["root_index"]): row
                for row in original["root_clusters"]}
    root_rows = []
    runtime = Counter()
    metrics = Counter()
    for mix in panel.MIXES:
        for root in g243.ROOTS:
            accumulator = {arm: Counter() for arm in (
                g243.ARMS[0], ARM, g243.ARMS[1])}
            for seat in panel.SEATS:
                rows = {}
                for arm in (g243.ARMS[0], g243.ARMS[1]):
                    path = panel.paired.unit_path(
                        g243.OUT, (mix, root, seat, arm, g243.SEED))
                    if digest(path) != frozen["g243_stage_sha256"][path.name]:
                        raise ValueError("G244 G243 来源阶段摘要漂移")
                    rows[arm] = json.loads(path.read_text(encoding="utf-8"))
                path = unit_path(mix, root, seat)
                rows[ARM] = json.loads(path.read_text(encoding="utf-8"))
                panel.verify_unit(rows[ARM], unit=(mix, root, seat, ARM, g243.SEED),
                                  tables_per_stage=frozen["tables_per_stage"])
                seeds = [[table["seed"] for table in rows[arm]["stage"]["tables"]]
                         for arm in rows]
                if any(value != seeds[0] for value in seeds[1:]):
                    raise ValueError("G244 三臂牌山不一致")
                for metric in rows[ARM]["stage"]["g244_metrics"]:
                    metrics[metric["status"]] += 1
                for arm, row in rows.items():
                    for table in row["stage"]["tables"]:
                        account = table["hand_account"]
                        if account["complete_hands"] != 8:
                            raise ValueError("G244 第三臂八局不完整")
                        if abs(sum(account[name] for name in COMPONENTS)
                               - account["focal_table_delta"]) > 1e-9:
                            raise ValueError("G244 单桌分量不守恒")
                        accumulator[arm].update({name: account[name]
                                                 for name in COMPONENTS})
                        accumulator[arm]["net"] += account["focal_table_delta"]
                        if arm == ARM:
                            runtime.update(table["result"]["runtime_counts"])
                            execution = table["policy_execution"]
                            runtime["action_value_failed"] += execution[
                                "action_value_failed"]
            per_table = {arm: {key: accumulator[arm][key] / 8.0
                               for key in (*COMPONENTS, "net")}
                         for arm in accumulator}
            old = clusters[(mix, root)]
            g243_delta = (per_table[g243.ARMS[1]]["net"]
                          - per_table[g243.ARMS[0]]["net"])
            if abs(g243_delta - old["delta_vs_baseline_per_table"][g243.ARMS[1]]) > 1e-9:
                raise ValueError("G244 已提交 G243 根级净分未恒等")
            for name in COMPONENTS:
                actual = (per_table[g243.ARMS[1]][name]
                          - per_table[g243.ARMS[0]][name])
                expected = old["component_delta_vs_baseline_per_table"][
                    g243.ARMS[1]][name]
                if abs(actual - expected) > 1e-9:
                    raise ValueError("G244 已提交 G243 根级分量未恒等")
            root_rows.append({"mix": mix, "root_index": root,
                              "per_table_by_arm": per_table})
    fail_names = ("fallbacks", "illegal_choices", "timeouts", "action_value_failed",
                  "action_value_abstain", "action_value_scoring_error",
                  "action_value_operation_limit", "action_value_resource_or_numeric_limit")
    runtime_ok = all(runtime[name] == 0 for name in fail_names)
    if not runtime_ok:
        raise ValueError("G244 第三臂运行可靠性失败")
    comparisons = ((ARM, g243.ARMS[0], "g239_minus_r18"),
                   (g243.ARMS[1], ARM, "g243_minus_g239"),
                   (g243.ARMS[1], g243.ARMS[0], "g243_minus_r18"))
    means = {}
    components = {}
    intervals = {}
    root_deltas = {}
    rng = random.Random(BOOTSTRAP_SEED)
    for left, right, name in comparisons:
        root_deltas[name] = {mix: [
            row["per_table_by_arm"][left]["net"]
            - row["per_table_by_arm"][right]["net"]
            for row in root_rows if row["mix"] == mix]
            for mix in panel.MIXES}
        means[name] = {mix: mean(root_deltas[name][mix]) for mix in panel.MIXES}
        means[name]["combined"] = mean(means[name][mix] for mix in panel.MIXES)
        components[name] = {mix: {component: mean(
            row["per_table_by_arm"][left][component]
            - row["per_table_by_arm"][right][component]
            for row in root_rows if row["mix"] == mix)
            for component in COMPONENTS} for mix in panel.MIXES}
        for mix in panel.MIXES:
            if abs(sum(components[name][mix].values()) - means[name][mix]) > 1e-9:
                raise ValueError("G244 比较分量不守恒")
        intervals[name] = {mix: interval(root_deltas[name][mix], rng)
                           for mix in panel.MIXES}
        combined = sorted(mean((mean(rng.choice(root_deltas[name]["H"])
                                     for _ in root_deltas[name]["H"]),
                                mean(rng.choice(root_deltas[name]["M"])
                                     for _ in root_deltas[name]["M"])))
                          for _ in range(REPLICATES))
        intervals[name]["combined_stratified"] = [
            combined[int(0.025 * REPLICATES)],
            combined[int(0.975 * REPLICATES) - 1]]
    if (abs(means["g243_minus_r18"]["combined"] - original[
            "descriptive_mean_delta_vs_baseline_per_table"][g243.ARMS[1]]) > 1e-9):
        raise ValueError("G244 已提交 G243 总净分未恒等")
    return {"schema": "g244-same-wall-filter-attribution-result/1",
            "manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
            "analysis_script_sha256": digest(Path(__file__)),
            "third_arm_complete_tables": 256,
            "same_wall_tri_arm_root_clusters": len(root_rows),
            "root_rows": root_rows,
            "mean_delta_per_complete_table": means,
            "component_delta_per_complete_table": components,
            "root_bootstrap_95_percentile": intervals,
            "third_arm_runtime_counts": dict(runtime),
            "third_arm_selector_counts": dict(metrics),
            "bootstrap_seed": BOOTSTRAP_SEED,
            "bootstrap_replicates": REPLICATES,
            "boundary": frozen["boundary"]}


def main() -> None:
    """第三臂断点续跑；所有新旧桌齐备时才开同墙拆账。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-new-units", type=int, default=0)
    args = parser.parse_args()
    if not 1 <= args.workers <= 4:
        parser.error("workers 必须在 1..4")
    frozen = manifest()
    panel._write_new(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), frozen)
    units = [(mix, root, seat) for mix in panel.MIXES
             for root in g243.ROOTS for seat in panel.SEATS]
    pending = [unit for unit in units if not unit_path(*unit).exists()]
    if args.max_new_units > 0:
        pending = pending[:args.max_new_units]
    if pending:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(run_unit, unit): unit for unit in pending}
            for count, future in enumerate(as_completed(futures), 1):
                unit = futures[future]
                try:
                    value = future.result()
                except Exception as exc:
                    raise RuntimeError(f"G244 stage failed: {unit}") from exc
                panel.verify_unit(value, unit=unit + (ARM, g243.SEED),
                                  tables_per_stage=frozen["tables_per_stage"])
                panel._write_new(unit_path(*unit), value)
                if count % 16 == 0 or count == len(pending):
                    print(json.dumps({"new_units": count,
                                      "planned_new_units": len(pending)}), flush=True)
    if any(not unit_path(*unit).exists() for unit in units):
        print(json.dumps({"status": "in_progress", "units_complete": sum(
            unit_path(*unit).exists() for unit in units)}), flush=True)
        return
    if (_project_file(_PROJECT_ROOT, OUT / "result.json")).exists():
        raise FileExistsError("G244 结果已存在")
    result = analyze(frozen)
    panel._write_new(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({"means": result["mean_delta_per_complete_table"],
                      "components": result["component_delta_per_complete_table"],
                      "intervals": result["root_bootstrap_95_percentile"],
                      "third_arm_runtime_counts": result["third_arm_runtime_counts"]},
                     ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
