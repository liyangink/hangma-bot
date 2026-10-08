#!/usr/bin/env python3
"""G118 选样：仅凭 G114 行动前状态冻结一向听多路线教师窗口。"""

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

import g114_fresh_score_matched_route_exposure as g114


HERE = Path(__file__).resolve().parent
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G118-ONE-SHANTEN-NATURAL-ROUTE-BRANCH-PREREG-2026-09-28.md')
SOURCE = g114.OUT / "rows.jsonl"
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g118-one-shanten-natural-route-20260928/selection.json')


def sha(path: Path) -> str:
    """将结果盲窗口来源与选样代码固定。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity(row: dict, target: dict) -> tuple:
    """唯一定位父代表内的本人决策窗口。"""
    return row["mix"], row["root_index"], row["focal_seat"], target["round_no"]


def stratum(row: dict, target: dict) -> tuple:
    """开发/锁定、对手池与当前白板供给决定选样格。"""
    split = "development" if row["root_index"] <= 16 else "locked_evaluation"
    white = "0" if target["white_before"] == 0 else "1plus"
    return split, row["mix"], white


def main() -> None:
    """每格每根先取最小摘要，再选最多八根。"""
    if OUT.exists():
        raise FileExistsError("G118 选样清单已存在，拒绝覆盖")
    exposure = json.loads((g114.OUT / "result.json").read_text(encoding="utf-8"))
    if exposure["status"] != "complete" or exposure["tables_completed"] != 256:
        raise ValueError("G118 必须先完成全部 256 张 G114 父代表")
    rows = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines()]
    if len(rows) != 256:
        raise ValueError("G118 G114 逐桌行数不守恒")
    first_per_root = {}
    eligible_count = Counter()
    for row in rows:
        for target in row["target_windows"]:
            if target["score_facts"]["standard_shanten_after"] != 1:
                continue
            group = stratum(row, target)
            eligible_count[group] += 1
            root_key = (*group, row["root_index"])
            prior = first_per_root.get(root_key)
            candidate = (row, target)
            rank = (target["observation_sha256"], *identity(row, target))
            if prior is None or rank < prior[0]:
                first_per_root[root_key] = (rank, candidate)
    selected = []
    by_stratum = {}
    for split in ("development", "locked_evaluation"):
        for mix in ("H", "M"):
            for white in ("0", "1plus"):
                group = (split, mix, white)
                pool = [item for key, item in first_per_root.items() if key[:3] == group]
                pool.sort(key=lambda item: item[0])
                chosen = pool[:8]
                by_stratum["/".join(group)] = {
                    "eligible_windows": eligible_count[group],
                    "eligible_roots": len(pool), "selected_windows": len(chosen),
                }
                for _, (row, target) in chosen:
                    selected.append({
                        "split": split, "mix": mix, "white_bin": white,
                        "window": list(identity(row, target)),
                        "observation_sha256": target["observation_sha256"],
                        "parent_action": target["parent_action"],
                        "alternate_action": target["alternate_action"],
                        "target_status": target["status"],
                        "score_facts": target["score_facts"],
                    })
    if len(selected) > 64 or len({tuple(item["window"]) for item in selected}) != len(selected):
        raise ValueError("G118 上限或窗口唯一性不守恒")
    result = {
        "schema": "g118-one-shanten-route-selection/1",
        "input_sha256": {
            "prereg": sha(PREREG), "script": sha(Path(__file__)),
            "g114_manifest": sha(g114.OUT / "manifest.json"),
            "g114_rows": sha(SOURCE),
        },
        "selected_windows": len(selected),
        "by_stratum": by_stratum, "selected": selected,
        "boundary": "只用行动前可见状态选样；尚未读取同局分支收益。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"selected_windows": len(selected),
                      "by_stratum": by_stratum}, ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
