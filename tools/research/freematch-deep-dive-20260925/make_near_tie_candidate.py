#!/usr/bin/env python3
"""机械生成「近并列次选」候选（C11）：只插入一段，其余与冻结父代逐行相同。

与 C10（SECONDCHOICE）的区别：C10 无条件把非胡层首选降到次选，实测 **−64.37 分/桌**
（145 个配对 unit，候选更好 13 / 父代更好 132）——**层内效应不能相加**。
C11 是它的**受限版本**，只在与 regret 面板里「疑似反号」的区域同构的窗口上动手：

- 非胡层（不碰 hu_sorting_layer）；
- 不碰五个 overlay 已指定的目标动作；
- 排除 trace.unknown 为真的动作（父代保证它们沉底，不能破这个不变量）；
- **Δ向听 = 0**；
- **|Δ总分| <= EPS**。

用法：
    .venv/bin/python make_near_tie_candidate.py --eps 10
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

import argparse
import sys
from pathlib import Path

ROOT = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))

from hangma_bot.policy.r18_integrated_positive_v2 import (  # noqa: E402
    R18_INTEGRATED_POSITIVE_V2_SOURCE,
)

OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/candidates')
ANCHOR = '    return {"status": "SCORED", "entries": output_entries, "reason": reason}\n'

BLOCK_TEMPLATE = '''    nt_best_key = None
    nt_best_score = None
    nt_best_shanten = None
    nt_second_key = None
    nt_second_score = None
    nt_second_shanten = None
    for entry in output_entries:
        nt_trace = entry.get("trace")
        if nt_trace is None:
            continue
        if nt_trace.get("unknown") is True:
            continue
        if nt_trace.get("hu_sorting_layer") is True:
            continue
        if nt_trace.get("r18_opportunity_overlay") is not None:
            continue
        if nt_trace.get("r18_gang_dominance_overlay") is not None:
            continue
        if nt_trace.get("r18_seven_pairs_value_overlay") is not None:
            continue
        if nt_trace.get("two_wealth_piao_keeps_baotou_cf") is not None:
            continue
        cfb_nt_trace = nt_trace.get("hu_vs_nonwealth_baotou_cf")
        if cfb_nt_trace is not None and cfb_nt_trace.get("triggered") is True:
            continue
        nt_key = entry.get("action_key")
        nt_score = entry.get("score")
        nt_shanten = nt_trace.get("shanten_after")
        if nt_key is None or nt_score is None or nt_shanten is None:
            continue
        if nt_best_score is None or nt_score > nt_best_score or (nt_score == nt_best_score and nt_key < nt_best_key):
            nt_second_key = nt_best_key
            nt_second_score = nt_best_score
            nt_second_shanten = nt_best_shanten
            nt_best_key = nt_key
            nt_best_score = nt_score
            nt_best_shanten = nt_shanten
        elif nt_second_score is None or nt_score > nt_second_score or (nt_score == nt_second_score and nt_key < nt_second_key):
            nt_second_key = nt_key
            nt_second_score = nt_score
            nt_second_shanten = nt_shanten
    nt_gap = 0.0
    if nt_best_score is not None and nt_second_score is not None:
        nt_gap = nt_best_score - nt_second_score
    nt_triggered = False
    if nt_best_key is not None and nt_second_key is not None and nt_best_key != nt_second_key:
        if nt_second_shanten == nt_best_shanten and nt_gap <= __EPS__ and nt_gap > 0.0:
            nt_triggered = True
    if nt_triggered:
        nt_entries = []
        for entry in output_entries:
            nt_key = entry.get("action_key")
            nt_score = entry.get("score")
            nt_trace = entry.get("trace")
            nt_new_score = nt_score
            if nt_key == nt_best_key:
                nt_new_score = nt_second_score
            if nt_key == nt_second_key:
                nt_new_score = nt_best_score
            nt_entries.append({"action_key": nt_key, "score": nt_new_score, "trace": dict(nt_trace, near_tie_second_choice_probe={"version": "near_tie_second_choice_probe/v1", "triggered": True, "epsilon": __EPS__, "demoted_key": nt_best_key, "promoted_key": nt_second_key, "gap": nt_gap})})
        output_entries = nt_entries
        reason = reason + "；C11 近并列次选探针触发"
    else:
        reason = reason + "；C11 近并列次选探针未触发，最终entries与父代逐点相同"
'''


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eps", default="10")
    args = ap.parse_args()
    eps = float(args.eps)
    block = BLOCK_TEMPLATE.replace("__EPS__", repr(eps))
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
    name = "OPTY-R18-C11-NEARTIE%s.py" % args.eps.replace(".", "_")
    path = _project_file(_PROJECT_ROOT, OUT / name)
    path.write_text(candidate, encoding="utf-8")
    compile(candidate, str(path), "exec")
    print("%s 插入 %d 行，其余逐行相同，语法通过" % (name, added))

    from hangma_bot.policy.action_value_executor import static_check

    static_check(candidate)
    print("静态合同检查通过（eps=%s）" % args.eps)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())