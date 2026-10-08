#!/usr/bin/env python3
"""G89：全量核对 G88 新 H/M 根配对完整桌并给出根级分布。"""

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
import hashlib
import json
from pathlib import Path
import random


HERE = Path(__file__).resolve().parent
RUN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g89-g88-hm-development-20260928')
CANDIDATE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/candidates/G88-POST-CLAIM-FAMILIAR-BIAS-V1.py')
ARM = "candidate@review/freematch-deep-dive-20260925/candidates/G88-POST-CLAIM-FAMILIAR-BIAS-V1.py"
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g89-g88-hm-development-20260928/analysis.json')
BOOTSTRAPS = 20_000
SEED = 2026110802


def sha(path: Path) -> str:
    """核对开发输入和结果文件的内容身份。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ci(values: list[float], rng: random.Random) -> list[float]:
    """以独立牌山根为单位给出描述性百分位区间。"""
    n = len(values)
    draws = sorted(sum(values[rng.randrange(n)] for _ in range(n)) / n
                   for _ in range(BOOTSTRAPS))
    return [draws[int(0.025 * BOOTSTRAPS)], draws[int(0.975 * BOOTSTRAPS) - 1]]


def main() -> None:
    """只在 768 桌全部结束且配对种子逐点相同时写汇总。"""
    if OUT.exists():
        raise FileExistsError("G89 汇总已存在，拒绝覆盖")
    manifest = json.loads((_project_file(_PROJECT_ROOT, RUN / "manifest.json")).read_text(encoding="utf-8"))
    result = json.loads((_project_file(_PROJECT_ROOT, RUN / "result.json")).read_text(encoding="utf-8"))
    if (manifest["panel_seed"] != 2026110801 or manifest["root_start"] != 1
            or manifest["roots_per_mix"] != 24 or manifest["arms"] != ["r18_v2", ARM]
            or manifest["planned_complete_tables"] != 768
            or manifest.get("candidate_sources", {}).get(ARM) != sha(CANDIDATE)):
        raise ValueError("G89 开发清单与预登记不符")
    roots = result["root_clusters"]
    if result["complete_tables"] != 768 or len(roots) != 48:
        raise ValueError("G89 完整桌或根数不足")
    by_mix = {mix: [float(row["delta_vs_baseline_per_table"][ARM])
                    for row in roots if row["mix"] == mix] for mix in ("H", "M")}
    if any(len(values) != 24 for values in by_mix.values()):
        raise ValueError("G89 H/M 根分层缺失")
    stage_files = sorted((_project_file(_PROJECT_ROOT, RUN / "stages")).glob("*.json"))
    if len(stage_files) != 384:
        raise ValueError("G89 阶段数不为 384")
    stage_rows = {}
    runtime = {arm: Counter() for arm in manifest["arms"]}
    last = {arm: Counter() for arm in manifest["arms"]}
    elapsed = {arm: [] for arm in manifest["arms"]}
    for path in stage_files:
        row = json.loads(path.read_text(encoding="utf-8"))
        key = (row["mix"], row["root_index"], row["focal_seat"], row["arm"])
        stage = row["stage"]
        if key in stage_rows or stage["status"] != "complete" or len(stage["tables"]) != 2:
            raise ValueError("G89 阶段重复或未完整")
        stage_rows[key] = row
        arm = row["arm"]
        elapsed[arm].append(stage["elapsed_ms"])
        for table in stage["tables"]:
            result_json = table["result"]
            if (table["match_status"] != "complete" or result_json["status"] != "complete"
                    or result_json["completed_hands"] != result_json["expected_hands"]):
                raise ValueError("G89 完整桌或单局不完整")
            for name, value in result_json["runtime_counts"].items():
                runtime[arm][name] += value
            execution = table["policy_execution"]
            for name, value in execution["failure_kinds"].items():
                runtime[arm]["action_value_" + name] += value
            runtime[arm]["action_value_scored"] += execution["action_value_scored"]
            runtime[arm]["action_value_failed"] += execution["action_value_failed"]
            scores = table["scores_by_seat"]
            seat = row["focal_seat"]
            last[arm]["tables"] += 1
            last[arm]["last_including_tie"] += scores[seat] == min(scores)
            last[arm]["strict_last"] += scores[seat] == min(scores) and scores.count(scores[seat]) == 1
    if len(stage_rows) != 384:
        raise ValueError("G89 阶段身份不全")
    for mix in ("H", "M"):
        for root_index in range(1, 25):
            for seat in range(4):
                a = stage_rows[(mix, root_index, seat, "r18_v2")]["stage"]
                b = stage_rows[(mix, root_index, seat, ARM)]["stage"]
                if [t["seed"] for t in a["tables"]] != [t["seed"] for t in b["tables"]]:
                    raise ValueError("G89 配对牌山种子不一致")
    rng = random.Random(SEED)
    intervals = {mix: ci(values, rng) for mix, values in by_mix.items()}
    combined_draws = []
    for _ in range(BOOTSTRAPS):
        h = sum(by_mix["H"][rng.randrange(24)] for _ in range(24)) / 24
        m = sum(by_mix["M"][rng.randrange(24)] for _ in range(24)) / 24
        combined_draws.append((h + m) / 2)
    combined_draws.sort()
    intervals["combined_stratified"] = [combined_draws[int(0.025 * BOOTSTRAPS)],
                                        combined_draws[int(0.975 * BOOTSTRAPS) - 1]]
    means = {mix: sum(values) / len(values) for mix, values in by_mix.items()}
    means["combined"] = (means["H"] + means["M"]) / 2
    failure_names = ("fallbacks", "illegal_choices", "timeouts", "action_value_failed",
                     "action_value_abstain", "action_value_scoring_error",
                     "action_value_operation_limit", "action_value_resource_or_numeric_limit")
    execution_ok = all(runtime[arm][name] == 0 for arm in manifest["arms"]
                       for name in failure_names)
    summary = {
        "schema": "g89-g88-hm-development-summary/1",
        "manifest_sha256": sha(_project_file(_PROJECT_ROOT, RUN / "manifest.json")), "result_sha256": sha(_project_file(_PROJECT_ROOT, RUN / "result.json")),
        "candidate_sha256": sha(CANDIDATE), "summary_script_sha256": sha(Path(__file__)),
        "complete_tables": 768, "independent_roots": 48,
        "means_delta_per_complete_table": means, "root_bootstrap_95_percentile": intervals,
        "root_signs": {mix: dict(Counter("positive" if value > 0 else
                                          "negative" if value < 0 else "zero"
                                          for value in values))
                       for mix, values in by_mix.items()},
        "runtime_counts": {arm: dict(sorted(value.items())) for arm, value in runtime.items()},
        "last_place_counts": {arm: dict(sorted(value.items())) for arm, value in last.items()},
        "stage_elapsed_mean_ms": {arm: sum(values) / len(values) for arm, values in elapsed.items()},
        "execution_ok": execution_ok,
        "numeric_development_gate": execution_ok and means["H"] > 0 and means["M"] > 0
            and means["combined"] >= 2.0,
        "bootstrap_seed": SEED, "bootstrap_replicates": BOOTSTRAPS,
        "limits": "开发描述区间不是独立确认；阶段文件无逐局收入账，不能推断普通胡/高番拆账或线上动作尾时限。",
    }
    OUT.write_text(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
