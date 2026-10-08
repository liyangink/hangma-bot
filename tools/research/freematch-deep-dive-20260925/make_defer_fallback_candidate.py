#!/usr/bin/env python3
"""机械生成「弃胡覆盖回退」候选：只插入一段，其余与冻结父代逐行相同。

动机（第 36–37 轮）：P19 实测在 3,920 局里，**摸牌窗口已能胡、且存在一张「弃后即爆头」的
非财神弃牌**的情形有 337 次，但父代的 hu_vs_nonwealth_baotou_cf 覆盖只触发 78 次
（对手是 647/1,470 = 44%，我们是 23%）。未触发的绝大多数是因为覆盖要求了
value_coverage=complete、routes、self_delta、useful_tiles 等**事实完备性**条件。

机制上：`baotou_after is True` 且 `shanten_after == 0` 表示弃这张牌之后**摸任意一张即胡**
（爆头 ×2），而当前只能是普通胡。也就是说弃胡换爆头的番值几乎必然更高。
本候选在原有覆盖**没有触发**时补一个回退：只要找到这样一张合法非财神弃牌就执行它。

用法：
    .venv/bin/python make_defer_fallback_candidate.py --mode banfan
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
ANCHOR = '    final_output_entries = []\n'

BLOCK_TEMPLATE = '''    if cfb_triggered is not True and cfb_top_entry is not None and cfb_top_type == "hu":
        cfb_fallback_score = cfb_top_entry.get("score")
        cfb_fallback_ok = True
        if __LOWFAN_GUARD__ and (cfb_hu_fan is None or cfb_hu_fan > 1.0):
            cfb_fallback_ok = False
        cfb_fallback_key = None
        if cfb_fallback_ok:
            for action in actions:
                fb_key = action.get("action_key")
                if action.get("is_legal") is not True or action.get("action_type") != "discard" or fb_key is None:
                    continue
                if fb_key[8:] == wealth:
                    continue
                if action.get("baotou_after") is not True:
                    continue
                if action.get("shanten_after") != 0:
                    continue
                if cfb_fallback_key is None or fb_key < cfb_fallback_key:
                    cfb_fallback_key = fb_key
        if cfb_fallback_key is not None and cfb_fallback_score is not None:
            cfb_target_key = cfb_fallback_key
            cfb_hu_final_score = cfb_fallback_score
            cfb_triggered = True
            cfb_degrade_reason = "回退触发：仅凭 baotou_after 事实"
'''


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="all", choices=("all", "lowfan"))
    args = ap.parse_args()
    guard = "True" if args.mode == "lowfan" else "False"
    block = BLOCK_TEMPLATE.replace("__LOWFAN_GUARD__", guard)
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
    name = "OPTY-R18-C12-DEFERFALLBACK-%s.py" % args.mode.upper()
    path = _project_file(_PROJECT_ROOT, OUT / name)
    path.write_text(candidate, encoding="utf-8")
    compile(candidate, str(path), "exec")
    print("%s 插入 %d 行，其余逐行相同，语法通过" % (name, added))

    from hangma_bot.policy.action_value_executor import static_check

    static_check(candidate)
    print("静态合同检查通过（mode=%s）" % args.mode)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())