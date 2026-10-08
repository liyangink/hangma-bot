#!/usr/bin/env python3
"""机械生成「非胡层次选」探针候选（C10）：只插入一段，其余与冻结父代逐行相同。

机制来源：生产 regret 批次（.team-work/rollout-regret-v1/prod/rows.json，1600 窗 / 3490 桌）
报告父代**次选**好过**首选** +2.49 分/桌 [+0.47, +4.51]、**第三选** +2.73 [+0.46, +4.99]，
而**自评最差**只有 −0.95 [−3.46, +1.56]。主审独立复算确认：首选与次选的分差中位只有 8 分，
73% 的窗口 Δ向听 = 0，20.3% 完全并列。

**本候选是该结论最直接的翻译**：在父代打分不变的前提下，把「非胡层」的首选与次选
**互换分数**，即让驱动去执行父代自评的次选。

边界（防止把已关闭的轴重新打开）：
- **不碰胡层**（hu_sorting_layer 为真的条目不参与），因此不会变成弃胡；
- **不碰五个 overlay 已明确指定的目标动作**（机会边界、补杠支配、七对路线价值、
  双财神保包头、立即胡vs非财神建爆头）——它们是被刻意抬到胡层上方的；
- 只改 score，不改 action_key，不改条目数量；未触发时与父代逐点相同。

用法：
    .venv/bin/python make_second_choice_candidate.py
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

BLOCK = '''    sc_best_key = None
    sc_best_score = None
    sc_second_key = None
    sc_second_score = None
    for entry in output_entries:
        entry_trace = entry.get("trace")
        if entry_trace is None:
            continue
        if entry_trace.get("hu_sorting_layer") is True:
            continue
        if entry_trace.get("r18_opportunity_overlay") is not None:
            continue
        if entry_trace.get("r18_gang_dominance_overlay") is not None:
            continue
        if entry_trace.get("r18_seven_pairs_value_overlay") is not None:
            continue
        if entry_trace.get("two_wealth_piao_keeps_baotou_cf") is not None:
            continue
        cfb_entry_trace = entry_trace.get("hu_vs_nonwealth_baotou_cf")
        if cfb_entry_trace is not None and cfb_entry_trace.get("triggered") is True:
            continue
        entry_key = entry.get("action_key")
        entry_score = entry.get("score")
        if entry_key is None or entry_score is None:
            continue
        if sc_best_score is None or entry_score > sc_best_score or (entry_score == sc_best_score and entry_key < sc_best_key):
            sc_second_key = sc_best_key
            sc_second_score = sc_best_score
            sc_best_key = entry_key
            sc_best_score = entry_score
        elif sc_second_score is None or entry_score > sc_second_score or (entry_score == sc_second_score and entry_key < sc_second_key):
            sc_second_key = entry_key
            sc_second_score = entry_score
    sc_triggered = False
    if sc_best_key is not None and sc_second_key is not None and sc_best_key != sc_second_key and sc_second_score < sc_best_score:
        sc_triggered = True
    if sc_triggered:
        sc_entries = []
        for entry in output_entries:
            entry_key = entry.get("action_key")
            entry_score = entry.get("score")
            entry_trace = entry.get("trace")
            sc_new_score = entry_score
            if entry_key == sc_best_key:
                sc_new_score = sc_second_score
            if entry_key == sc_second_key:
                sc_new_score = sc_best_score
            sc_entries.append({"action_key": entry_key, "score": sc_new_score, "trace": dict(entry_trace, nonhu_second_choice_probe={"version": "nonhu_second_choice_probe/v1", "triggered": True, "demoted_key": sc_best_key, "demoted_score": sc_best_score, "promoted_key": sc_second_key, "promoted_score": sc_second_score})})
        output_entries = sc_entries
        reason = reason + "；C10 次选探针触发：非胡层首选与次选互换分数"
    else:
        reason = reason + "；C10 次选探针未触发（非胡层可行动作不足两个或已并列），最终entries与父代逐点相同"
'''


def main() -> int:
    source = R18_INTEGRATED_POSITIVE_V2_SOURCE
    assert source.count(ANCHOR) == 1, "锚点在冻结源码中出现 %d 次" % source.count(ANCHOR)
    OUT.mkdir(parents=True, exist_ok=True)
    candidate = source.replace(ANCHOR, BLOCK + ANCHOR)
    before = source.splitlines()
    after = candidate.splitlines()
    added = len(BLOCK.splitlines())
    assert len(after) - len(before) == added, "插入行数不符"
    index = before.index(ANCHOR.rstrip("\n"))
    assert before[:index] == after[:index], "插入点之前出现差异"
    assert before[index:] == after[index + added:], "插入点之后出现差异"
    assert all(line.startswith("    ") for line in after[index:index + added])
    path = _project_file(_PROJECT_ROOT, OUT / "OPTY-R18-C10-SECONDCHOICE.py")
    path.write_text(candidate, encoding="utf-8")
    compile(candidate, str(path), "exec")
    print("%s 插入 %d 行，其余逐行相同，语法通过" % (path.name, added))

    from hangma_bot.policy.action_value_executor import static_check

    static_check(candidate)
    print("静态合同检查通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())