#!/usr/bin/env python3
"""完整桌研究的分辨率与效用边界（只读计算）。

背景：本仓的完整桌面板用 48 个独立牌山根、6 worker、约 10-15 分钟一轮。
本轮多份报告都写「某臂更差」，但**没有任何一份算过这些差异是否在分辨率内**。
本脚本把这件事算清楚，给出：

1. 在给定根数下，95% 置信区间能分辨的最小效应（「看不出来」的门槛）；
2. 要在 80% 功效下检出某效应所需根数；
3. 把本轮已跑的实验按这个标尺逐一判定「结论成立 / 不可分辨」。

用法：
    .venv/bin/python review/freematch-deep-dive-20260925/detection_resolution.py
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

import math

# 根级标准差：由 2026-09-25 P3-A 确认批（48 根，报告 95% 半宽 ±3.1）反推，
# 与更早的独立校准（SD ≈ 11.02 分/桌）一致。
ROOT_SD = 11.0
PLANNED_ROOTS = 48
Z_95 = 1.959964
Z_80 = 0.8416212


def half_width(roots: int, sd: float = ROOT_SD) -> float:
    """该根数下 95% 区间的半宽：小于它的效应看不出来。"""
    return Z_95 * sd / math.sqrt(roots)


def roots_for(effect: float, power_z: float = Z_80, sd: float = ROOT_SD) -> int:
    """在给定功效下检出该效应所需根数。"""
    return math.ceil(((Z_95 + power_z) * sd / effect) ** 2)


EXPERIMENTS = [
    ("P5 向听系数 50", -2.2005208333333335),
    ("P5 向听系数 40", -11.072916666666666),
    ("P5 向听系数 30", -17.783854166666668),
    ("P7 七对份额 10", -4.255),
    ("P7 七对份额 20", -14.536),
    ("P7 七对份额 40", -16.029),
    ("P9 序列 4096-projected", -2.359),
    ("P9 序列 4096-direct", -2.401),
    ("P9 序列 2048-projected", -2.862),
    ("P9 v2_hu_upgrade（对照）", -0.927),
]


def main() -> int:
    print("根级标准差 σ = %.1f 分/桌" % ROOT_SD)
    print("95%% 区间半宽 @ %d 根 = %.2f 分/桌（小于它 = 与零不可分辨）"
          % (PLANNED_ROOTS, half_width(PLANNED_ROOTS)))
    print()
    print("| 目标效应 δ | 要 95% 显著所需根数 | 要 80%% 功效所需根数 |")
    print("| --- | --- | --- |")
    for delta in (0.5, 1, 2, 3, 4, 5, 10, 20):
        print("| %.1f | %d | %d |"
              % (delta, roots_for(delta, power_z=0.0), roots_for(delta)))
    print()
    print("| 本轮实验 | 实测 Δ | 在 48 根下的判定 |")
    print("| --- | --- | --- |")
    limit = half_width(PLANNED_ROOTS)
    for name, value in EXPERIMENTS:
        verdict = "**在分辨率内，结论成立**" if abs(value) > limit else "**不可分辨**（|Δ| < %.2f）" % limit
        print("| %s | %+.2f | %s |" % (name, value, verdict))
    print()
    print("## 读法")
    print()
    print("- 48 根面板只能分辨 **≥ %.1f 分/桌** 的效应。低于它的一律不能下结论，无论方向多一致。" % limit)
    print("- 要检出 **+2 分/桌** 的改进需要 **%d 根**（约 5 倍预算）；" % roots_for(2.0))
    print("  要检出 **+1 分/桌** 需要 **%d 根**。" % roots_for(1.0))
    print("- 因此：**要么候选效应量大于 4 分/桌，要么把根数抬到 200 以上**，"
          "中间没有第三条路。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())