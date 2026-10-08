#!/usr/bin/env python3
"""机械生成「完全并列交换」候选（C15）：只插入一段，其余与冻结父代逐行相同。

动机：P22 发现在「父代首选与次选在总分上**完全并列**」的窗口里，
均匀随机臂是**负**的（−1.217），而模拟估值是正的（+1.828）——
这是全批唯一「靶面还没被污染」的层（345 窗 / 1600 窗 ≈ 21.6%）。
而父代在完全并列时的排序是 **action_key 字符串升序**，本身没有任何依据。

本候选只在这**一种**情形下动手：非胡层、不动 overlay、排除 unknown，
若前两名总分**完全相等**，把第二名抬到 `best + 1.0`，让驱动改选它。
其余窗口与父代逐点相同。

用法：
    .venv/bin/python make_tie_swap_candidate.py
"""
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

import sys
from pathlib import Path

ROOT = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))

from hangma_bot.policy.r18_integrated_positive_v2 import (  # noqa: E402
    R18_INTEGRATED_POSITIVE_V2_SOURCE,
)

OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/candidates')
ANCHOR = '    return {"status": "SCORED", "entries": output_entries, "reason": reason}\n'

BLOCK_LINES = [
    "    ts_best_key = None",
    "    ts_best_score = None",
    "    ts_second_key = None",
    "    ts_second_score = None",
    "    for entry in output_entries:",
    "        ts_trace = entry.get(\"trace\")",
    "        if ts_trace is None:",
    "            continue",
    "        if ts_trace.get(\"unknown\") is True:",
    "            continue",
    "        if ts_trace.get(\"hu_sorting_layer\") is True:",
    "            continue",
    "        if ts_trace.get(\"r18_opportunity_overlay\") is not None:",
    "            continue",
    "        if ts_trace.get(\"r18_gang_dominance_overlay\") is not None:",
    "            continue",
    "        if ts_trace.get(\"r18_seven_pairs_value_overlay\") is not None:",
    "            continue",
    "        if ts_trace.get(\"two_wealth_piao_keeps_baotou_cf\") is not None:",
    "            continue",
    "        cfb_ts_trace = ts_trace.get(\"hu_vs_nonwealth_baotou_cf\")",
    "        if cfb_ts_trace is not None and cfb_ts_trace.get(\"triggered\") is True:",
    "            continue",
    "        ts_key = entry.get(\"action_key\")",
    "        ts_score = entry.get(\"score\")",
    "        if ts_key is None or ts_score is None:",
    "            continue",
    "        if ts_best_score is None or ts_score > ts_best_score or (ts_score == ts_best_score and ts_key < ts_best_key):",
    "            ts_second_key = ts_best_key",
    "            ts_second_score = ts_best_score",
    "            ts_best_key = ts_key",
    "            ts_best_score = ts_score",
    "        elif ts_second_score is None or ts_score > ts_second_score or (ts_score == ts_second_score and ts_key < ts_second_key):",
    "            ts_second_key = ts_key",
    "            ts_second_score = ts_score",
    "    ts_triggered = False",
    "    if ts_best_key is not None and ts_second_key is not None and ts_best_key != ts_second_key:",
    "        if ts_second_score == ts_best_score:",
    "            ts_triggered = True",
    "    if ts_triggered:",
    "        ts_entries = []",
    "        for entry in output_entries:",
    "            ts_key = entry.get(\"action_key\")",
    "            ts_score = entry.get(\"score\")",
    "            ts_trace = entry.get(\"trace\")",
    "            ts_new_score = ts_score",
    "            if ts_key == ts_second_key:",
    "                ts_new_score = ts_best_score + 1.0",
    "            ts_entries.append({\"action_key\": ts_key, \"score\": ts_new_score, \"trace\": dict(ts_trace, tie_swap_probe={\"version\": \"tie_swap_probe/v1\", \"triggered\": True, \"demoted_key\": ts_best_key, \"promoted_key\": ts_second_key, \"tied_score\": ts_best_score})})",
    "        output_entries = ts_entries",
    "        reason = reason + \"；C15 完全并列交换探针触发\"",
    "    else:",
    "        reason = reason + \"；C15 完全并列交换探针未触发，最终entries与父代逐点相同\"",
]


def main() -> int:
    block = "\n".join(BLOCK_LINES) + "\n"
    source = R18_INTEGRATED_POSITIVE_V2_SOURCE
    assert source.count(ANCHOR) == 1, "锚点在冻结源码中出现 %d 次" % source.count(ANCHOR)
    OUT.mkdir(parents=True, exist_ok=True)
    candidate = source.replace(ANCHOR, block + ANCHOR)
    before = source.splitlines()
    after = candidate.splitlines()
    added = len(block.splitlines())
    assert len(after) - len(before) == added, "插入行数不符"
    index = before.index(ANCHOR.rstrip("\n"))
    assert before[:index] == after[:index], "插入点之前出现差异"
    assert before[index:] == after[index + added:], "插入点之后出现差异"
    path = _project_file(_PROJECT_ROOT, OUT / "OPTY-R18-C15-TIESWAP.py")
    path.write_text(candidate, encoding="utf-8")
    compile(candidate, str(path), "exec")
    print("%s：插入 %d 行，其余逐行相同，语法通过" % (path.name, added))

    from hangma_bot.policy.action_value_executor import static_check

    static_check(candidate)
    print("静态合同检查通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())