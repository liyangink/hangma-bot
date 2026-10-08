#!/usr/bin/env python3
"""G11 预登记全程桌赛的根级积分、同墙和执行可靠性对账。"""

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
ROOT = _PROJECT_ROOT
RUN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g11-shape-risk-development-20260927')
CANDIDATE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/candidates/G11-SHAPE-RISK-PARETO-V1.py')
ARM = "candidate@review/freematch-deep-dive-20260925/candidates/G11-SHAPE-RISK-PARETO-V1.py"
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g11-shape-risk-development-20260927/analysis.json')
SEED = 2026110602
BOOTSTRAPS = 20_000


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ci(values: list[float], rng: random.Random) -> list[float]:
    n = len(values)
    draws = sorted(sum(values[rng.randrange(n)] for _ in range(n)) / n
                   for _ in range(BOOTSTRAPS))
    return [draws[int(0.025 * BOOTSTRAPS)], draws[int(0.975 * BOOTSTRAPS) - 1]]


def main() -> None:
    """先全量机械核验，再按“对手池×牌山根”计算效果；不读过程中的部分积分。"""

    if OUT.exists():
        raise SystemExit("G11 开发汇总已存在，拒绝覆盖")
    manifest = json.loads((_project_file(_PROJECT_ROOT, RUN / "manifest.json")).read_text(encoding="utf-8"))
    result = json.loads((_project_file(_PROJECT_ROOT, RUN / "result.json")).read_text(encoding="utf-8"))
    if (manifest["panel_seed"] != 2026110601 or manifest["root_start"] != 1
            or manifest["roots_per_mix"] != 24 or manifest["arms"] != ["r18_v2", ARM]
            or manifest["planned_complete_tables"] != 768
            or manifest.get("candidate_sources", {}).get(ARM) != _sha(CANDIDATE)):
        raise ValueError("预登记牌山、源码或两臂清单漂移")
    roots = result["root_clusters"]
    if result["complete_tables"] != 768 or len(roots) != 48:
        raise ValueError("完整桌或独立根数量不足")
    by_mix = {mix: [float(row["delta_vs_baseline_per_table"][ARM])
                    for row in roots if row["mix"] == mix] for mix in ("H", "M")}
    if any(len(values) != 24 for values in by_mix.values()):
        raise ValueError("H/M 根分层缺失")
    stage_files = sorted((_project_file(_PROJECT_ROOT, RUN / "stages")).glob("*.json"))
    if len(stage_files) != 384:
        raise ValueError("阶段文件未齐 384")
    stage_rows = {}
    runtime = {arm: Counter() for arm in manifest["arms"]}
    bottom = {arm: Counter() for arm in manifest["arms"]}
    stage_elapsed = {arm: [] for arm in manifest["arms"]}
    for path in stage_files:
        row = json.loads(path.read_text(encoding="utf-8"))
        key = (row["mix"], row["root_index"], row["focal_seat"], row["arm"])
        if key in stage_rows or row["stage"]["status"] != "complete":
            raise ValueError("阶段重复或未完成：" + str(path))
        stage_rows[key] = row
        arm = row["arm"]
        stage = row["stage"]
        if len(stage["tables"]) != 2:
            raise ValueError("阶段不足 2 张完整桌")
        stage_elapsed[arm].append(stage["elapsed_ms"])
        for table in stage["tables"]:
            result_json = table["result"]
            if (table["match_status"] != "complete" or result_json["status"] != "complete"
                    or result_json["completed_hands"] != result_json["expected_hands"]):
                raise ValueError("场次或局数未完整")
            for name, value in result_json["runtime_counts"].items():
                runtime[arm][name] += value
            execution = table["policy_execution"]
            for name, value in execution["failure_kinds"].items():
                runtime[arm]["action_value_" + name] += value
            runtime[arm]["action_value_scored"] += execution["action_value_scored"]
            runtime[arm]["action_value_failed"] += execution["action_value_failed"]
            scores = table["scores_by_seat"]
            seat = row["focal_seat"]
            if scores[seat] == min(scores):
                bottom[arm]["bottom_including_tie"] += 1
                if scores.count(scores[seat]) == 1:
                    bottom[arm]["strict_last"] += 1
            bottom[arm]["tables"] += 1
    if len(stage_rows) != 384:
        raise ValueError("阶段身份未齐")
    for mix in ("H", "M"):
        for root_index in range(1, 25):
            for seat in range(4):
                a = stage_rows[(mix, root_index, seat, "r18_v2")]["stage"]
                b = stage_rows[(mix, root_index, seat, ARM)]["stage"]
                if [t["seed"] for t in a["tables"]] != [t["seed"] for t in b["tables"]]:
                    raise ValueError("配对臂的牌山种子不一致")
    rng = random.Random(SEED)
    ci = {mix: _ci(values, rng) for mix, values in by_mix.items()}
    combined = by_mix["H"] + by_mix["M"]
    paired_draws = []
    for _ in range(BOOTSTRAPS):
        mean_h = sum(by_mix["H"][rng.randrange(24)] for _ in range(24)) / 24
        mean_m = sum(by_mix["M"][rng.randrange(24)] for _ in range(24)) / 24
        paired_draws.append((mean_h + mean_m) / 2)
    paired_draws.sort()
    ci["combined_stratified"] = [paired_draws[int(0.025 * BOOTSTRAPS)],
                                 paired_draws[int(0.975 * BOOTSTRAPS) - 1]]
    means = {mix: sum(values) / len(values) for mix, values in by_mix.items()}
    means["combined"] = sum(combined) / len(combined)
    signs = {mix: dict(Counter("positive" if value > 0 else "negative" if value < 0 else "zero"
                               for value in values)) for mix, values in by_mix.items()}
    execution_ok = all(runtime[arm][name] == 0 for arm in manifest["arms"]
                       for name in ("fallbacks", "illegal_choices", "timeouts",
                                    "action_value_failed", "action_value_abstain",
                                    "action_value_scoring_error", "action_value_operation_limit",
                                    "action_value_resource_or_numeric_limit"))
    analysis = {"schema": "g11-shape-risk-development-summary/1",
                "manifest_sha256": _sha(_project_file(_PROJECT_ROOT, RUN / "manifest.json")),
                "result_sha256": _sha(_project_file(_PROJECT_ROOT, RUN / "result.json")),
                "candidate_sha256": _sha(CANDIDATE),
                "complete_tables": 768, "independent_roots": 48,
                "means_delta_per_complete_table": means,
                "root_bootstrap_95_percentile": ci,
                "root_signs": signs,
                "runtime_counts": {arm: dict(sorted(value.items())) for arm, value in runtime.items()},
                "last_place_counts": {arm: dict(sorted(value.items())) for arm, value in bottom.items()},
                "stage_elapsed_mean_ms": {
                    arm: sum(values) / len(values) for arm, values in stage_elapsed.items()},
                "execution_ok": execution_ok,
                "numeric_development_gate": execution_ok and means["combined"] >= 2
                    and means["H"] > 0 and means["M"] > 0,
                "bootstrap_seed": SEED, "bootstrap_replicates": BOOTSTRAPS,
                "limits": "阶段 JSON 未保存逐局胡牌番种和在线动作 p99；不能把阶段耗时或本汇总当正式时限/特殊胡审核。"}
    OUT.write_text(json.dumps(analysis, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps(analysis, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
