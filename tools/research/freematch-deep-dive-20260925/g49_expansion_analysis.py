#!/usr/bin/env python3
"""G49 扩样：从冻结阶段证据复算根分、逐桌分叉和描述性重抽样。"""

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
import statistics

import g49_expansion as expansion


OUT = expansion.OUT / "analysis.json"
COMPONENTS = expansion.panel.COMPONENTS


def main() -> None:
    """只作赛后诊断；任何分数或隐藏状态均不反馈给已冻结候选。"""

    if OUT.exists():
        raise SystemExit("G49 扩样分析已存在，拒绝覆盖")
    result_path = expansion.OUT / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if result["complete_tables"] != 384 or len(result["root_clusters"]) != 24:
        raise ValueError("G49 扩样尚未完整")
    arm = expansion.ARMS[1]
    groups = {mix: [row["delta_vs_baseline_per_table"][arm]
                    for row in result["root_clusters"] if row["mix"] == mix]
              for mix in expansion.panel.MIXES}
    if any(len(values) != 12 for values in groups.values()):
        raise ValueError("G49 扩样根数不符")
    changed = []
    counts = Counter()
    for mix in expansion.panel.MIXES:
        for root in expansion.ROOTS:
            for seat_group in expansion.panel.SEATS:
                stages = {}
                for arm_name in expansion.ARMS:
                    unit = mix, root, seat_group, arm_name, expansion.SEED
                    row = json.loads(expansion.panel.paired.unit_path(expansion.OUT, unit).read_text(encoding="utf-8"))
                    expansion.panel.verify_unit(row, unit=unit, tables_per_stage=2)
                    stages[arm_name] = row["stage"]
                baseline = stages[expansion.ARMS[0]]["tables"]
                candidate = stages[expansion.ARMS[1]]["tables"]
                for index, (before, after) in enumerate(zip(baseline, candidate), 1):
                    counts["paired_tables"] += 1
                    old = before["hand_account"]
                    new = after["hand_account"]
                    delta = new["focal_table_delta"] - old["focal_table_delta"]
                    if delta == 0:
                        counts["same_score_pairs"] += 1
                        continue
                    component = {name: new[name] - old[name] for name in COMPONENTS}
                    if sum(component.values()) != delta:
                        raise ValueError("G49 逐桌分量不守恒")
                    counts["positive_pairs" if delta > 0 else "negative_pairs"] += 1
                    changed.append({"mix": mix, "root_index": root,
                                    "seat_group": seat_group, "table_index": index,
                                    "baseline_score": old["focal_table_delta"],
                                    "candidate_score": new["focal_table_delta"],
                                    "delta": delta, "component_delta": component})
    if counts["paired_tables"] != 192:
        raise ValueError("G49 配对桌数不符")
    rng = random.Random(20260927)
    bootstrap = {}
    for mix in (*expansion.panel.MIXES, "combined"):
        samples = []
        for _ in range(20_000):
            h = sum(rng.choices(groups["H"], k=12)) / 12
            m = sum(rng.choices(groups["M"], k=12)) / 12
            samples.append(h if mix == "H" else m if mix == "M" else (h + m) / 2)
        samples.sort()
        bootstrap[mix] = {"mean": statistics.mean(groups[mix]) if mix != "combined"
                          else (statistics.mean(groups["H"]) + statistics.mean(groups["M"])) / 2,
                          "percentile_95": [samples[499], samples[19499]]}
    output = {"schema": "g49-expansion-analysis/1",
              "expansion_result_sha256": expansion.pilot.sha(result_path),
              "script_sha256": expansion.pilot.sha(Path(__file__)),
              "counts": dict(sorted(counts.items())),
              "bootstrap": {"seed": 20260927, "draws": 20_000,
                            "stratification": "H/M 各 12 根分别有放回重抽；描述性开发区间，非独立确认",
                            "by_mix": bootstrap},
              "changed_pairs": changed}
    expansion.panel._write_new(OUT, output)
    print(json.dumps({"counts": output["counts"], "bootstrap": output["bootstrap"]},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
