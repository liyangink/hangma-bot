#!/usr/bin/env python3
"""机械生成「并列时按可见张数打破」候选（C16）：只插入一段，其余与冻结父代逐行相同。

动机：真实审计里「前两名总分完全并列」的弃牌对占 2967/11912 = 24.9%，
而父代的打破依据是 **action_key 字符串升序**，会把弃牌系统性地推向字典序小的牌
（ASCII 数字 < CJK，所以是「弃筒/条/万、留字牌」，跨类占 56.9%）——没有任何牌理依据。

本候选给一个**有牌理依据**的并列打破规则：**优先弃掉已经被别人打过的牌**
（河里出现次数更多 ⇒ 剩余张数更少 ⇒ 对手更不容易吃碰它，而本赛制只能自摸、没有点炮）。
只在**总分完全相等**时生效：把河里出现次数更多的那张抬到 best + 1.0。

用法：
    .venv/bin/python make_tie_river_candidate.py
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
    "    tr_best_key = None",
    "    tr_best_score = None",
    "    tr_second_key = None",
    "    tr_second_score = None",
    "    for entry in output_entries:",
    "        tr_trace = entry.get(\"trace\")",
    "        if tr_trace is None:",
    "            continue",
    "        if tr_trace.get(\"unknown\") is True:",
    "            continue",
    "        if tr_trace.get(\"hu_sorting_layer\") is True:",
    "            continue",
    "        if tr_trace.get(\"r18_opportunity_overlay\") is not None:",
    "            continue",
    "        if tr_trace.get(\"r18_gang_dominance_overlay\") is not None:",
    "            continue",
    "        if tr_trace.get(\"r18_seven_pairs_value_overlay\") is not None:",
    "            continue",
    "        if tr_trace.get(\"two_wealth_piao_keeps_baotou_cf\") is not None:",
    "            continue",
    "        cfb_tr_trace = tr_trace.get(\"hu_vs_nonwealth_baotou_cf\")",
    "        if cfb_tr_trace is not None and cfb_tr_trace.get(\"triggered\") is True:",
    "            continue",
    "        tr_key = entry.get(\"action_key\")",
    "        tr_score = entry.get(\"score\")",
    "        if tr_key is None or tr_score is None:",
    "            continue",
    "        if tr_best_score is None or tr_score > tr_best_score or (tr_score == tr_best_score and tr_key < tr_best_key):",
    "            tr_second_key = tr_best_key",
    "            tr_second_score = tr_best_score",
    "            tr_best_key = tr_key",
    "            tr_best_score = tr_score",
    "        elif tr_second_score is None or tr_score > tr_second_score or (tr_score == tr_second_score and tr_key < tr_second_key):",
    "            tr_second_key = tr_key",
    "            tr_second_score = tr_score",
    "    tr_triggered = False",
    "    if tr_best_key is not None and tr_second_key is not None and tr_best_key != tr_second_key:",
    "        if tr_second_score == tr_best_score:",
    "            if tr_best_key[0:8] == \"discard:\" and tr_second_key[0:8] == \"discard:\":",
    "                tr_a = tr_best_key[8:]",
    "                tr_b = tr_second_key[8:]",
    "                tr_cnt_a = 0",
    "                tr_cnt_b = 0",
    "                for river_seat in range(4):",
    "                    tr_cnt_a += discards[river_seat].count(tr_a)",
    "                    tr_cnt_b += discards[river_seat].count(tr_b)",
    "                if tr_cnt_b > tr_cnt_a:",
    "                    tr_triggered = True",
    "    if tr_triggered:",
    "        tr_entries = []",
    "        for entry in output_entries:",
    "            tr_key = entry.get(\"action_key\")",
    "            tr_score = entry.get(\"score\")",
    "            tr_trace = entry.get(\"trace\")",
    "            tr_new_score = tr_score",
    "            if tr_key == tr_second_key:",
    "                tr_new_score = tr_best_score + 1.0",
    "            tr_entries.append({\"action_key\": tr_key, \"score\": tr_new_score, \"trace\": dict(tr_trace, tie_river_probe={\"version\": \"tie_river_probe/v1\", \"triggered\": True, \"demoted_key\": tr_best_key, \"promoted_key\": tr_second_key, \"tied_score\": tr_best_score})})",
    "        output_entries = tr_entries",
    "        reason = reason + \"；C16 并列按河张打破探针触发\"",
    "    else:",
    "        reason = reason + \"；C16 并列按河张打破探针未触发，最终entries与父代逐点相同\"",
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
    path = _project_file(_PROJECT_ROOT, OUT / "OPTY-R18-C16-TIERIVER.py")
    path.write_text(candidate, encoding="utf-8")
    compile(candidate, str(path), "exec")
    print("%s：插入 %d 行，其余逐行相同，语法通过" % (path.name, added))

    from hangma_bot.policy.action_value_executor import static_check

    static_check(candidate)
    print("静态合同检查通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())