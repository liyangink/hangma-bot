#!/usr/bin/env python3
"""机械生成「向听系数」候选：只改一个字符序列，其余与冻结父代逐字节相同。

机制：冻结父代的主项是 `base = -100.0 * float(shanten) + round(support, 1)`，
即把 1 个向听步长定价为 100 张有效牌。实测（shanten_coefficient_reach.py）
接受「多一个向听」中位能换回 21 张有效牌，所以 100 相当于 5 倍惩罚向听。
本脚本把 100.0 替换为给定系数，产生一批只差该常数的候选。

为什么机械生成：这样「行为差异」只可能来自这一个标量，
不会混入重写引入的无关改动。生成后脚本会逐行核对差异行数。

用法：
    .venv/bin/python make_shanten_candidates.py --coefficients 70,60,50,40,30
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
import importlib.util
import sys
from pathlib import Path

ROOT = _PROJECT_ROOT
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/candidates')
FROZEN = _project_file(_PROJECT_ROOT, ROOT / "src" / "hangma_bot" / "policy" / "r18_integrated_positive_v2.py")
ORIGINAL = "base = -100.0 * float(shanten) + round(support, 1)"


def frozen_source() -> str:
    """直接取冻结发布模块里的内嵌源码，避免手工反转义出错。"""
    spec = importlib.util.spec_from_file_location("frozen_r18_v2", FROZEN)
    module = importlib.util.module_from_spec(spec)
    sys.modules["frozen_r18_v2"] = module
    spec.loader.exec_module(module)
    return module.R18_INTEGRATED_POSITIVE_V2_SOURCE


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--coefficients", default="70,60,50,40,30")
    args = ap.parse_args(argv)

    source = frozen_source()
    assert source.count(ORIGINAL) == 1, "主项模板在冻结源码中出现 %d 次" % source.count(ORIGINAL)
    OUT.mkdir(parents=True, exist_ok=True)

    for token in args.coefficients.split(","):
        coefficient = float(token)
        replaced = "base = -%s * float(shanten) + round(support, 1)" % coefficient
        candidate = source.replace(ORIGINAL, replaced)
        differing = [i for i, (a, b) in enumerate(zip(source.splitlines(), candidate.splitlines()))
                     if a != b]
        assert len(differing) == 1, "差异行数应为 1，实际 %d" % len(differing)
        path = _project_file(_PROJECT_ROOT, OUT / ("OPTY-R18-C04-SHANTEN%s.py" % token.strip().replace(".", "_")))
        path.write_text(candidate, encoding="utf-8")
        print("%s 差异行 %d（第 %d 行）：%s"
              % (path.name, len(differing), differing[0] + 1, candidate.splitlines()[differing[0]].strip()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())