#!/usr/bin/env python3
"""G193：根级完整桌净分、分量与规则／运行门。"""

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

from collections import Counter
import json
from pathlib import Path
import random
from statistics import mean

import g193_early_shape_development as run


OUT = run.OUT / "analysis.json"
REPLICATES = 20_000
BOOTSTRAP_SEED = 20261229194
COMPONENTS = run.panel.COMPONENTS


def interval(values: list[float], rng: random.Random) -> list[float]:
    """只以牌山根重抽样，座位和两桌保留在同一根内。"""
    estimates = sorted(mean(rng.choice(values) for _ in values)
                       for _ in range(REPLICATES))
    return [estimates[int(0.025 * REPLICATES)],
            estimates[int(0.975 * REPLICATES) - 1]]


def main() -> None:
    """先核完整牌山配对及候选源码，再按事前门判开发去留。"""
    if OUT.exists():
        raise FileExistsError("G193 分析已存在，拒绝覆盖")
    manifest = json.loads((run.OUT / "manifest.json").read_text(encoding="utf-8"))
    result = json.loads((run.OUT / "result.json").read_text(encoding="utf-8"))
    if (manifest["panel_seed"] != run.SEED
            or manifest["roots_per_mix"] != 32
            or manifest["arms"] != list(run.ARMS)
            or manifest["planned_complete_tables"] != 1024
            or manifest["input_sha256"]["g193_early_shape_policy.py"]
            != run.digest(run.HERE / "g193_early_shape_policy.py")
            or result["complete_tables"] != 1024
            or len(result["root_clusters"]) != 64):
        raise ValueError("G193 清单、源码或完整桌数漂移")
    stages = {}
    runtime = {arm: Counter() for arm in run.ARMS}
    last = {arm: Counter() for arm in run.ARMS}
    selector = Counter()
    for path in sorted((run.OUT / "stages").glob("*.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        key = (row["mix"], row["root_index"], row["focal_seat"], row["arm"])
        if key in stages:
            raise ValueError("G193 阶段身份重复")
        run.panel.verify_unit(row, unit=key + (run.SEED,),
                              tables_per_stage=manifest["tables_per_stage"])
        stages[key] = row
        arm = row["arm"]
        if arm == run.ARMS[1]:
            for metric in row["stage"]["g193_metrics"]:
                selector[(metric["status"], metric.get("reason"))] += 1
        for table in row["stage"]["tables"]:
            detail = table["result"]
            if (table["match_status"] != "complete"
                    or detail["status"] != "complete"
                    or detail["completed_hands"] != detail["expected_hands"]):
                raise ValueError("G193 完整桌未完成")
            runtime[arm].update(detail["runtime_counts"])
            execution = table["policy_execution"]
            runtime[arm]["action_value_failed"] += execution["action_value_failed"]
            for name, value in execution["failure_kinds"].items():
                runtime[arm]["action_value_" + name] += value
            scores = table["scores_by_seat"]
            focal = scores[row["focal_seat"]]
            last[arm]["tables"] += 1
            last[arm]["last_including_tie"] += focal == min(scores)
            last[arm]["strict_last"] += focal == min(scores) and scores.count(focal) == 1
    if len(stages) != 512:
        raise ValueError("G193 阶段数不是 512")
    for mix in run.panel.MIXES:
        for root in run.ROOTS:
            for seat in run.panel.SEATS:
                a = stages[(mix, root, seat, run.ARMS[0])]["stage"]
                b = stages[(mix, root, seat, run.ARMS[1])]["stage"]
                if [table["seed"] for table in a["tables"]] != [
                        table["seed"] for table in b["tables"]]:
                    raise ValueError("G193 两臂对应牌山种子不同")
    roots = result["root_clusters"]
    arm = run.ARMS[1]
    delta = {mix: [float(row["delta_vs_baseline_per_table"][arm])
                   for row in roots if row["mix"] == mix]
             for mix in run.panel.MIXES}
    if any(len(values) != 32 for values in delta.values()):
        raise ValueError("G193 两池独立根覆盖不完整")
    component = {mix: {
        name: mean(float(row["component_delta_vs_baseline_per_table"][arm][name])
                   for row in roots if row["mix"] == mix)
        for name in COMPONENTS} for mix in run.panel.MIXES}
    means = {mix: mean(values) for mix, values in delta.items()}
    means["combined"] = mean(means[mix] for mix in run.panel.MIXES)
    for mix in run.panel.MIXES:
        if abs(sum(component[mix].values()) - means[mix]) > 1e-9:
            raise ValueError("G193 收益分量与桌均净分不守恒")
    rng = random.Random(BOOTSTRAP_SEED)
    intervals = {mix: interval(values, rng) for mix, values in delta.items()}
    combined = sorted(mean((mean(rng.choice(delta["H"]) for _ in delta["H"]),
                            mean(rng.choice(delta["M"]) for _ in delta["M"])))
                      for _ in range(REPLICATES))
    intervals["combined_stratified"] = [combined[int(0.025 * REPLICATES)],
                                       combined[int(0.975 * REPLICATES) - 1]]
    best_removed = {mix: mean(sorted(values)[:-1]) for mix, values in delta.items()}
    paired_root = {root: mean(next(row["delta_vs_baseline_per_table"][arm]
                                  for row in roots if row["mix"] == mix
                                  and row["root_index"] == root)
                              for mix in run.panel.MIXES)
                   for root in run.ROOTS}
    best_root = max(paired_root, key=paired_root.get)
    combined_after_best_root = mean(value for root, value in paired_root.items()
                                    if root != best_root)
    failures = ("fallbacks", "illegal_choices", "timeouts", "action_value_failed",
                "action_value_abstain", "action_value_scoring_error",
                "action_value_operation_limit", "action_value_resource_or_numeric_limit")
    execution_ok = all(runtime[a][name] == 0 for a in run.ARMS
                       for name in failures)
    selector_ok = not any(status == "fallback" or reason in (
        "selector_exception", "candidate_identity_mismatch")
        for status, reason in selector)
    changed_roots = result["g193_metrics"]["changed_roots"]
    enough_behavior = all(changed_roots[mix] > 0 for mix in run.panel.MIXES)
    gate = (
        execution_ok and selector_ok and enough_behavior
        and all(means[mix] > 0 for mix in run.panel.MIXES)
        and means["combined"] >= 2.0
        and intervals["combined_stratified"][0] > 0
        and all(component[mix]["plain_self_win_delta"] >= 0
                for mix in run.panel.MIXES)
        and combined_after_best_root > 0
        and all(best_removed[mix] > 0 for mix in run.panel.MIXES)
    )
    payload = {
        "schema": "g193-early-shape-development-analysis/1",
        "manifest_sha256": run.digest(run.OUT / "manifest.json"),
        "result_sha256": run.digest(run.OUT / "result.json"),
        "analysis_script_sha256": run.digest(Path(__file__)),
        "complete_tables": 1024,
        "independent_pool_root_clusters": 64,
        "means_delta_per_complete_table": means,
        "root_bootstrap_95_percentile": intervals,
        "component_delta_per_complete_table": component,
        "best_root": best_root,
        "combined_after_best_root": combined_after_best_root,
        "per_pool_after_own_best_root": best_removed,
        "root_signs": {mix: dict(Counter(
            "positive" if value > 0 else "negative" if value < 0 else "zero"
            for value in values)) for mix, values in delta.items()},
        "runtime_counts": {arm: dict(sorted(value.items()))
                           for arm, value in runtime.items()},
        "last_place_counts": {arm: dict(sorted(value.items()))
                              for arm, value in last.items()},
        "selector_status_reason": {
            str(status) + "/" + str(reason): value
            for (status, reason), value in sorted(selector.items(),
                                                   key=lambda x: str(x[0]))},
        "execution_ok": execution_ok,
        "selector_ok": selector_ok,
        "enough_behavior": enough_behavior,
        "development_gate_pass": gate,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "bootstrap_replicates": REPLICATES,
        "boundary": "开发根完整桌描述；过门仍需新根独立确认及官方门。",
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False,
                              sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: payload[key] for key in (
        "means_delta_per_complete_table", "root_bootstrap_95_percentile",
        "component_delta_per_complete_table", "combined_after_best_root",
        "execution_ok", "selector_ok", "development_gate_pass")},
        ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
