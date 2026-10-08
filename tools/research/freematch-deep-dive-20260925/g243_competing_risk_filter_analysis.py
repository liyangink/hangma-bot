#!/usr/bin/env python3
"""G243：按冻结判据核新根过滤候选的完整桌净分、分账和可靠性。"""

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

import g243_competing_risk_filter_development as run


OUT = run.OUT / "analysis.json"
REPLICATES = 20_000
BOOTSTRAP_SEED = 20261229424
COMPONENTS = run.panel.COMPONENTS


def interval(values: list[float], rng: random.Random) -> list[float]:
    """只重抽独立牌山根；同根四座两桌保持相关。"""
    samples = sorted(mean(rng.choice(values) for _ in values)
                     for _ in range(REPLICATES))
    return [samples[int(0.025 * REPLICATES)],
            samples[int(0.975 * REPLICATES) - 1]]


def main() -> None:
    """先逐阶段核身份、完整性与同墙，再报告根级收益门。"""
    if OUT.exists():
        raise FileExistsError(OUT)
    manifest = json.loads((run.OUT / "manifest.json").read_text(encoding="utf-8"))
    result = json.loads((run.OUT / "result.json").read_text(encoding="utf-8"))
    if (manifest.get("schema") != "g243-competing-risk-filter-development-manifest/1"
            or manifest["panel_seed"] != run.SEED
            or manifest["roots"] != list(run.ROOTS)
            or manifest["arms"] != list(run.ARMS)
            or manifest["planned_complete_tables"] != 512
            or result["complete_tables"] != 512
            or len(result["root_clusters"]) != 32):
        raise ValueError("G243 清单或根级结果漂移")
    for path in (run.PLAN, Path(run.candidate.__file__), run.candidate.MODEL_PATH,
                 run.HERE / "g237_numeric_inversion_policy.py"):
        name = str(path.relative_to(run.ROOT))
        if manifest["input_sha256"].get(name) != run.digest(path):
            raise ValueError("G243 冻结候选输入摘要漂移：" + name)
    stages = {}
    runtime = {arm: Counter() for arm in run.ARMS}
    selector = Counter()
    for path in sorted((run.OUT / "stages").glob("*.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        key = (row["mix"], row["root_index"], row["focal_seat"], row["arm"])
        if key in stages:
            raise ValueError("G243 阶段身份重复")
        run.panel.verify_unit(row, unit=key + (run.SEED,),
                              tables_per_stage=manifest["tables_per_stage"])
        stages[key] = row
        arm = row["arm"]
        if arm == run.ARMS[1]:
            for metric in row["stage"]["g243_metrics"]:
                selector[(metric["status"], metric.get("reason"))] += 1
        for table in row["stage"]["tables"]:
            detail = table["result"]
            if (table["match_status"] != "complete"
                    or detail["status"] != "complete"
                    or detail["completed_hands"] != detail["expected_hands"]):
                raise ValueError("G243 不完整桌或局数不符")
            runtime[arm].update(detail["runtime_counts"])
            execution = table["policy_execution"]
            runtime[arm]["action_value_failed"] += execution["action_value_failed"]
            for name, value in execution["failure_kinds"].items():
                runtime[arm]["action_value_" + name] += value
    if len(stages) != 256:
        raise ValueError("G243 阶段数不是 256")
    for mix in run.panel.MIXES:
        for root in run.ROOTS:
            for seat in run.panel.SEATS:
                old = stages[(mix, root, seat, run.ARMS[0])]["stage"]
                new = stages[(mix, root, seat, run.ARMS[1])]["stage"]
                if [table["seed"] for table in old["tables"]] != [
                        table["seed"] for table in new["tables"]]:
                    raise ValueError("G243 父代与候选不同牌山")
    arm = run.ARMS[1]
    roots = result["root_clusters"]
    delta = {mix: [float(row["delta_vs_baseline_per_table"][arm])
                   for row in roots if row["mix"] == mix]
             for mix in run.panel.MIXES}
    if any(len(values) != 16 for values in delta.values()):
        raise ValueError("G243 两池独立根不足 16")
    components = {mix: {
        name: mean(float(row["component_delta_vs_baseline_per_table"][arm][name])
                   for row in roots if row["mix"] == mix)
        for name in COMPONENTS} for mix in run.panel.MIXES}
    means = {mix: mean(values) for mix, values in delta.items()}
    means["combined"] = mean(means[mix] for mix in run.panel.MIXES)
    for mix in run.panel.MIXES:
        if abs(sum(components[mix].values()) - means[mix]) > 1e-9:
            raise ValueError("G243 收益分量与净分不守恒")
    rng = random.Random(BOOTSTRAP_SEED)
    intervals = {mix: interval(values, rng) for mix, values in delta.items()}
    combined = sorted(mean((mean(rng.choice(delta["H"]) for _ in delta["H"]),
                            mean(rng.choice(delta["M"]) for _ in delta["M"])))
                      for _ in range(REPLICATES))
    intervals["combined_stratified"] = [combined[int(0.025 * REPLICATES)],
                                        combined[int(0.975 * REPLICATES) - 1]]
    best_removed = {mix: mean(sorted(values)[:-1]) for mix, values in delta.items()}
    fail_names = ("fallbacks", "illegal_choices", "timeouts", "action_value_failed",
                  "action_value_abstain", "action_value_scoring_error",
                  "action_value_operation_limit", "action_value_resource_or_numeric_limit")
    execution_ok = all(runtime[arm_name][name] == 0
                       for arm_name in run.ARMS for name in fail_names)
    selector_ok = not any(status == "fallback" or reason == "selector_exception"
                          for status, reason in selector)
    metrics = result["g243_metrics"]
    latency = metrics["selector_elapsed_ms"]
    latency_ok = bool(latency) and latency["p95"] < 100 and latency["max"] < 350
    behavior_ok = all(metrics["per_mix"][mix].get("adopted", 0) >= 20
                      and metrics["changed_roots"][mix] >= 8
                      for mix in run.panel.MIXES)
    gate = (execution_ok and selector_ok and latency_ok and behavior_ok
            and all(means[mix] > 0 for mix in run.panel.MIXES)
            and means["combined"] >= 1.0)
    payload = {
        "schema": "g243-competing-risk-filter-development-analysis/1",
        "manifest_sha256": run.digest(run.OUT / "manifest.json"),
        "result_sha256": run.digest(run.OUT / "result.json"),
        "analysis_script_sha256": run.digest(Path(__file__)),
        "complete_tables": 512,
        "independent_pool_root_clusters": 32,
        "mean_delta_per_complete_table": means,
        "root_bootstrap_95_percentile": intervals,
        "component_delta_per_complete_table": components,
        "per_pool_after_own_best_root": best_removed,
        "root_signs": {mix: dict(Counter(
            "positive" if value > 0 else "negative" if value < 0 else "zero"
            for value in values)) for mix, values in delta.items()},
        "runtime_counts": {arm_name: dict(sorted(value.items()))
                           for arm_name, value in runtime.items()},
        "selector_status_reason": {str(status) + "/" + str(reason): value
                                   for (status, reason), value in sorted(
                                       selector.items(), key=lambda item: str(item[0]))},
        "execution_ok": execution_ok,
        "selector_ok": selector_ok,
        "latency_ok": latency_ok,
        "behavior_ok": behavior_ok,
        "development_continue_gate_pass": gate,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "bootstrap_replicates": REPLICATES,
        "boundary": "全新根开发收益；通过才开独立确认，不是发布或接线资格。",
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False,
                              sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({name: payload[name] for name in (
        "mean_delta_per_complete_table", "root_bootstrap_95_percentile",
        "component_delta_per_complete_table", "per_pool_after_own_best_root",
        "execution_ok", "selector_ok", "latency_ok", "behavior_ok",
        "development_continue_gate_pass")}, ensure_ascii=False, sort_keys=True),
          flush=True)


if __name__ == "__main__":
    main()
