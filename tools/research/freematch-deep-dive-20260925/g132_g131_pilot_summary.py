#!/usr/bin/env python3
"""G132：核 G131 H/M 同牌山完整桌，并按牌山根汇总效应。"""

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
RUN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g131-standard-shadow-pilot-20260928')
ARM_LOW = ("candidate@review/freematch-deep-dive-20260925/candidates/"
           "G131-STANDARD-SHADOW-LOW-V1.py")
ARM_HIGH = ("candidate@review/freematch-deep-dive-20260925/candidates/"
            "G131-STANDARD-SHADOW-HIGH-V1.py")
ARMS = ("r18_v2", ARM_LOW, ARM_HIGH)
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g131-standard-shadow-pilot-20260928/analysis.json')
BOOTSTRAPS = 20_000
SEED = 2026123102


def sha(path: Path) -> str:
    """核输入文件字节身份。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ci(values: list[float], rng: random.Random) -> list[float]:
    """以牌山根为单位做百分位描述区间。"""
    n = len(values)
    draws = sorted(sum(values[rng.randrange(n)] for _ in range(n)) / n
                   for _ in range(BOOTSTRAPS))
    return [draws[int(.025 * BOOTSTRAPS)], draws[int(.975 * BOOTSTRAPS) - 1]]


def main() -> None:
    """要求 192 阶段、384 完整桌、三臂相同牌山及无运行失效。"""
    if OUT.exists():
        raise FileExistsError("G132 汇总已存在，拒绝覆盖")
    manifest = json.loads((_project_file(_PROJECT_ROOT, RUN / "manifest.json")).read_text(encoding="utf-8"))
    result = json.loads((_project_file(_PROJECT_ROOT, RUN / "result.json")).read_text(encoding="utf-8"))
    expected_sources = {
        ARM_LOW: sha(_project_file(_PROJECT_ROOT, HERE / "candidates/G131-STANDARD-SHADOW-LOW-V1.py")),
        ARM_HIGH: sha(_project_file(_PROJECT_ROOT, HERE / "candidates/G131-STANDARD-SHADOW-HIGH-V1.py"))}
    if (manifest["panel_seed"] != 2026123101 or manifest["root_start"] != 1
            or manifest["roots_per_mix"] != 8 or manifest["arms"] != list(ARMS)
            or manifest["planned_complete_tables"] != 384
            or manifest["candidate_sources"] != expected_sources
            or result["complete_tables"] != 384
            or len(result["root_clusters"]) != 16):
        raise ValueError("G132 清单、候选摘要或完整桌数不符")
    stage_files = sorted((_project_file(_PROJECT_ROOT, RUN / "stages")).glob("*.json"))
    if len(stage_files) != 192:
        raise ValueError("G132 完整阶段数不是 192")
    stages = {}
    runtime = {arm: Counter() for arm in ARMS}
    for path in stage_files:
        row = json.loads(path.read_text(encoding="utf-8"))
        key = (row["mix"], row["root_index"], row["focal_seat"], row["arm"])
        stage = row["stage"]
        if key in stages or stage["status"] != "complete" or len(stage["tables"]) != 2:
            raise ValueError("G132 阶段重复或不完整")
        stages[key] = stage
        for table in stage["tables"]:
            t = table["result"]
            if (table["match_status"] != "complete" or t["status"] != "complete"
                    or t["completed_hands"] != t["expected_hands"]):
                raise ValueError("G132 完整桌或单局未完成")
            for name, count in t["runtime_counts"].items():
                runtime[row["arm"]][name] += count
            execution = table["policy_execution"]
            runtime[row["arm"]]["action_value_scored"] += execution["action_value_scored"]
            runtime[row["arm"]]["action_value_failed"] += execution["action_value_failed"]
            for name, count in execution["failure_kinds"].items():
                runtime[row["arm"]]["action_value_" + name] += count
    if len(stages) != 192:
        raise ValueError("G132 H/M×根×座×臂不全")
    for mix in ("H", "M"):
        for root in range(1, 9):
            for seat in range(4):
                seeds = [[t["seed"] for t in stages[(mix, root, seat, arm)]["tables"]]
                         for arm in ARMS]
                if seeds[0] != seeds[1] or seeds[0] != seeds[2]:
                    raise ValueError("G132 三臂同根牌山未对齐")
    by_arm = {arm: {mix: [float(row["delta_vs_baseline_per_table"][arm])
                            for row in result["root_clusters"] if row["mix"] == mix]
                    for mix in ("H", "M")} for arm in (ARM_LOW, ARM_HIGH)}
    if any(len(by_arm[arm][mix]) != 8 for arm in by_arm for mix in ("H", "M")):
        raise ValueError("G132 根级效应不全")
    failure_names = ("fallbacks", "illegal_choices", "timeouts", "action_value_failed",
                     "action_value_abstain", "action_value_scoring_error",
                     "action_value_operation_limit", "action_value_resource_or_numeric_limit")
    execution_ok = all(runtime[arm][name] == 0 for arm in ARMS
                       for name in failure_names)
    rng = random.Random(SEED)
    candidates = {}
    for arm, mixes in by_arm.items():
        h, m = mixes["H"], mixes["M"]
        means = {"H": sum(h) / 8, "M": sum(m) / 8}
        means["combined"] = (means["H"] + means["M"]) / 2
        boot = {mix: ci(mixes[mix], rng) for mix in ("H", "M")}
        draws = sorted(((sum(h[rng.randrange(8)] for _ in range(8)) / 8)
                        + (sum(m[rng.randrange(8)] for _ in range(8)) / 8)) / 2
                       for _ in range(BOOTSTRAPS))
        boot["combined"] = [draws[int(.025 * BOOTSTRAPS)],
                            draws[int(.975 * BOOTSTRAPS) - 1]]
        candidates[arm] = {
            "means_delta_per_complete_table": means,
            "root_bootstrap_95_percentile": boot,
            "root_signs": {mix: dict(Counter("positive" if value > 0 else
                                              "negative" if value < 0 else "zero"
                                              for value in mixes[mix])) for mix in ("H", "M")},
            "numeric_development_gate": execution_ok and means["H"] > 0
            and means["M"] > 0 and means["combined"] >= 2.0,
        }
    summary = {
        "schema": "g132-g131-pilot-summary/1",
        "manifest_sha256": sha(_project_file(_PROJECT_ROOT, RUN / "manifest.json")),
        "result_sha256": sha(_project_file(_PROJECT_ROOT, RUN / "result.json")),
        "script_sha256": sha(Path(__file__)),
        "complete_tables": 384, "independent_roots": 16,
        "runtime_counts": {arm: dict(sorted(value.items())) for arm, value in runtime.items()},
        "execution_ok": execution_ok, "candidates": candidates,
        "bootstrap_seed": SEED, "bootstrap_replicates": BOOTSTRAPS,
        "boundary": "开发桌赛，非独立确认；无逐局普通胡、高番与收入拆账。",
    }
    OUT.write_text(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"complete_tables": 384, "execution_ok": execution_ok,
                      "candidates": candidates}, ensure_ascii=False, sort_keys=True),
          flush=True)


if __name__ == "__main__":
    main()
