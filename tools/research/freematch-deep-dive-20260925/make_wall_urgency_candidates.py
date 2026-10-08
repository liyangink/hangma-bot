#!/usr/bin/env python3
"""机械生成「墙深紧迫度」候选（C24）：墙越短，向听差越贵。

动机（2026-09-26 第 52 轮）：父代核心打分

    base = -100.0 * float(shanten) + round(support, 1)

**完全不含墙深**，而可见状态里的 remaining_tile_count（官方 wall_remaining，含 20 张保留区）
在 32,374 个真实窗口里 100% 可用（缺失 0）。实测分布：中位 68、p10 51、<50 占 8.65%、<30 占 0.32%。

机制：一局可摸次数有限，越到后面「还差两步」的手越接近死手；
父代用固定权重 100 处理向听，等于假设时间无限。

候选形式（T=阈值墙深，L=紧迫系数）：

    urgency = L * (T - w)        （w < T 时）
    base = base - urgency * float(shanten)

用法：
    .venv/bin/python make_wall_urgency_candidates.py --thresholds 60 --weights 1,3,10
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
ANCHOR = "                base = -100.0 * float(shanten) + round(support, 1)\n"

BLOCK_LINES = [
    '                wall_left = visible.get("remaining_tile_count")',
    "                if wall_left is not None and wall_left is not True and wall_left is not False:",
    "                    wall_value = float(wall_left)",
    "                    if wall_value < __THRESHOLD__:",
    "                        urgency = __WEIGHT__ * (__THRESHOLD__ - wall_value)",
    "                        base = base - urgency * float(shanten)",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--thresholds", default="60")
    ap.add_argument("--weights", default="1,3,10")
    args = ap.parse_args()
    source = R18_INTEGRATED_POSITIVE_V2_SOURCE
    assert source.count(ANCHOR) == 1, "锚点在冻结源码中出现 %d 次" % source.count(ANCHOR)
    OUT.mkdir(parents=True, exist_ok=True)
    names = []
    for threshold in args.thresholds.split(","):
        threshold = threshold.strip()
        for token in args.weights.split(","):
            weight = token.strip()
            if not weight:
                continue
            block = "\n".join(
                line.replace("__THRESHOLD__", threshold).replace("__WEIGHT__", weight)
                for line in BLOCK_LINES
            ) + "\n"
            candidate = source.replace(ANCHOR, ANCHOR + block)
            assert len(candidate.splitlines()) - len(source.splitlines()) == len(block.splitlines())
            assert candidate.count(ANCHOR) == 1
            name = "OPTY-R18-C24-WALLURG-T%s-W%s.py" % (threshold, weight.replace(".", "_"))
            path = _project_file(_PROJECT_ROOT, OUT / name)
            path.write_text(candidate, encoding="utf-8")
            compile(candidate, str(path), "exec")
            names.append(name)
    print("生成 %d 个候选：" % len(names))
    for name in names:
        print("  candidates/" + name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
