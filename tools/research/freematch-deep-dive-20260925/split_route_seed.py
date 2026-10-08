#!/usr/bin/env python3
"""主审：把 route_value_seed 拆成「弱向听权重」与「路线项」两部分，先测它们各自的影响力。

背景：route_value_seed 归一后等价于「向听系数 = 6」（父代 100，P5 判负的最激进档 30）。
所以它若为负，无法区分是「向听权重过弱」还是「路线项有害」。

本脚本从 route_value_seed 源码派生出两个对照：
  (A) 去掉路线项，只留 -3·shanten + 0.5·support  → 纯牌效、极弱向听权重
  (B) 原版（弱向听 + 路线项）
然后测 B 相对 A 的改选率：
  改选率高 → 路线项在起作用，P17 的结果可以归因到它；
  改选率极低 → 路线项几乎不改变行为，P17 测的其实是向听权重。
"""

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
import importlib.util
import sys
from pathlib import Path

ROOT = _PROJECT_ROOT
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/candidates')
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))


def seed_source() -> str:
    # 必须按包导入：模块内部有相对导入，独立 exec 会 ImportError。
    from hangma_bot.policy import action_value_seeds
    return action_value_seeds.ROUTE_VALUE_SEED_SOURCE


OLD = "        score = base + bonus + settle[0] + fan_scale(route_fan) * ROUTE_FAN_WEIGHT\n"
NEW = "        score = base\n"


def main() -> int:
    source = seed_source()
    assert source.count(OLD) == 1, "计分行在 route_value_seed 中出现 %d 次" % source.count(OLD)
    stripped = source.replace(OLD, NEW)
    before = source.splitlines()
    after = stripped.splitlines()
    assert len(before) == len(after), "行数应一致"
    diff = [i for i in range(len(before)) if before[i] != after[i]]
    assert len(diff) == 1, "差异行应为 1，实际 %d" % len(diff)
    OUT.mkdir(parents=True, exist_ok=True)
    path = _project_file(_PROJECT_ROOT, OUT / "OPTY-R18-C11-ROUTESEED-NOROUTE.py")
    path.write_text(stripped, encoding="utf-8")
    print("写出 %s（去掉路线项，差异 1 行：第 %d 行）" % (path.name, diff[0] + 1))
    original = _project_file(_PROJECT_ROOT, OUT / "OPTY-R18-C11-ROUTESEED-ORIGINAL.py")
    original.write_text(source, encoding="utf-8")
    print("写出 %s（原版，用于同口径对照）" % original.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())