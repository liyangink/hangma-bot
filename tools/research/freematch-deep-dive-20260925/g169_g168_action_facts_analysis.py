#!/usr/bin/env python3
"""G169：已看 G168 改弃的规则事实与原评分差，纯描述汇总。"""

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

import g169_g168_action_facts as replay


OUT = replay.OUT / "analysis.json"


def _capacity(values) -> int | None:
    """返回公开未见上界张数；未知不当作零。"""
    if values is None:
        return None
    return sum(count for _, count in values)


def _direction(old: int | None, new: int | None) -> str:
    """新旧结果的增加、减少、持平或未知。"""
    if old is None or new is None:
        return "unknown"
    return "more" if new > old else "less" if new < old else "equal"


def main() -> None:
    """逐动作取生产事实；这些计数不用于重新选 G168 已看根。"""
    if OUT.exists():
        raise FileExistsError("G169 分析已存在，拒绝覆盖")
    source = replay.OUT / "result.json"
    data = json.loads(source.read_text(encoding="utf-8"))
    totals = {}
    for mix in replay.g168.panel.MIXES:
        actions = [row for row in data["rows"]
                   if row["mix"] == mix and row["status"] == "adopted"]
        counter = Counter()
        residual = Counter()
        for row in actions:
            parent = row["parent"]
            alternate = row["alternate"]
            counter["seven_shanten_" + _direction(
                parent["seven_pairs_shanten_after"],
                alternate["seven_pairs_shanten_after"])] += 1
            for field in ("standard_useful_tiles", "useful_tiles",
                          "seven_pairs_useful_tiles"):
                old = parent[field]
                new = alternate[field]
                counter[field + "_capacity_" + _direction(
                    _capacity(old), _capacity(new))] += 1
                if old is not None and new is not None:
                    old_white = next((count for code, count in old
                                      if code == "白"), 0)
                    new_white = next((count for code, count in new
                                      if code == "白"), 0)
                    counter[field + "_white_" + _direction(
                        old_white, new_white)] += 1
            if row["parent_score"] > row["alternate_score"]:
                counter["parent_total_score_higher"] += 1
            support_old = _capacity(parent["useful_tiles"])
            support_new = _capacity(alternate["useful_tiles"])
            if support_old is not None and support_new is not None:
                delta = ((row["alternate_score"] - row["parent_score"])
                         - (support_new - support_old))
                residual[str(delta)] += 1
        totals[mix] = {
            "adopted": len(actions),
            "counts": dict(sorted(counter.items())),
            "score_delta_minus_combined_support_delta": dict(sorted(
                residual.items(), key=lambda item: float(item[0]))),
        }
    payload = {
        "schema": "g169-g168-action-facts-analysis/1",
        "source_sha256": replay.g168.sha(source),
        "analysis_script_sha256": replay.g168.sha(Path(__file__)),
        "by_mix": totals,
        "boundary": "已看 G168 结果的行动前描述；残差不是已辨识的风险因果项。",
    }
    replay.g168.panel._write_new(OUT, payload)
    print(json.dumps(totals, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
