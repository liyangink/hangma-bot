#!/usr/bin/env python3
"""G129：只读 G128 开发根，核自然成面到终局积分的转移。"""

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

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from statistics import mean

import g100_analyze_visible_trajectory as g100
import g119_one_shanten_development_analysis as g119
import g128_no_claim_two_shanten_branch as g128


SOURCE = g128.BASE / "development/rows.jsonl"
OUT = g128.BASE / "development/analysis.json"


def sha(path: Path) -> str:
    """绑定开发分支原文与分析程序。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """每窗先合并九个相关世界，保留 H/M 与白板分层。"""
    if OUT.exists():
        raise FileExistsError("G129 开发分析已存在，拒绝覆盖")
    status = json.loads((g128.BASE / "development/result.json").read_text(
        encoding="utf-8"))
    rows = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines()]
    if (status["status"] != "complete" or len(rows) != 38
            or any(len(row["world_pairs"]) != 9 for row in rows)):
        raise ValueError("G129 G128 开发分支不完整")
    groups = defaultdict(Counter)
    window_rows = []
    root_values = defaultdict(list)
    for row in rows:
        group = row["mix"] + "/" + row["white_bin"]
        counts = Counter()
        deltas = []
        for pair in row["world_pairs"]:
            delta = pair["focal_delta_alt_minus_parent"]
            deltas.append(delta)
            counts["pairs"] += 1
            counts["pair_positive"] += delta > 0
            counts["pair_negative"] += delta < 0
            counts["pair_zero"] += delta == 0
            for arm in ("parent", "alternate"):
                kind = pair[arm + "_class"]
                counts[arm + "/" + kind] += 1
                # 首次 DRAW 已是强制弃牌窗口；至少两次才表示真正再正常摸打。
                counts[arm + "/next_normal_draw_discard"] += (
                    len(g100.draw_discards(pair[arm])) >= 2)
                state = g119.first_tenpai(pair[arm])
                counts[arm + "/first_tenpai_reached"] += state[0] == "reached"
            p = g119.first_tenpai(pair["parent"])
            a = g119.first_tenpai(pair["alternate"])
            counts["first_tenpai/" + g119.compare_entry(p, a)] += 1
            counts["outcome/" + pair["parent_class"] + "->"
                   + pair["alternate_class"]] += 1
        window_mean = mean(deltas)
        root_values[(row["mix"], row["root_index"])].append(window_mean)
        counts["window_positive"] += window_mean > 0
        counts["window_negative"] += window_mean < 0
        counts["window_zero"] += window_mean == 0
        groups[group].update(counts)
        window_rows.append({
            "mix": row["mix"], "white_bin": row["white_bin"],
            "root_index": row["root_index"], "focal_seat": row["focal_seat"],
            "round_no": row["round_no"], "observation_sha256": row["observation_sha256"],
            "score_facts": row["score_facts"],
            "mean_focal_delta_alt_minus_parent": window_mean,
            "counts": dict(sorted(counts.items())),
        })
    result = {
        "schema": "g129-two-shanten-development-analysis/1",
        "input_sha256": {"script": sha(Path(__file__)),
                         "development_rows": sha(SOURCE),
                         "selection": sha(g128.select.OUT)},
        "windows": window_rows,
        "groups": {key: dict(sorted(value.items())) for key, value in sorted(groups.items())},
        "root_means": {mix + "/" + str(root): mean(values)
                       for (mix, root), values in sorted(root_values.items())},
        "boundary": "仅开发根的赛后结果；九世界同窗相关，根内多窗相关，"
                    "首次听牌及后续行动是结果不是在线输入。",
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"windows": len(rows), "groups": result["groups"]},
                     ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
