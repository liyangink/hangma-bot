#!/usr/bin/env python3
"""机械生成「杠常数」候选：只改一行，其余与冻结父代逐行相同。

动机：父代对杠给 fixed = +40.0（r18_integrated_positive_v2.py:176-177）。
P14 只测过碰/吃常数，**杠常数从未被测**。而杠在赛制里有额外价值：
明杠/补杠买一次摸牌，杠开 ×2，且杠是 2^动作链 的一个入口。

用法：
    .venv/bin/python make_gang_candidates.py --values 0,100,200
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
ANCHOR = "            elif kind == \"gang\":\n                fixed = 40.0\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--values", default="0,100,200")
    args = ap.parse_args()
    source = R18_INTEGRATED_POSITIVE_V2_SOURCE
    assert source.count(ANCHOR) == 1, "锚点在冻结源码中出现 %d 次" % source.count(ANCHOR)
    OUT.mkdir(parents=True, exist_ok=True)
    for token in args.values.split(","):
        value = token.strip()
        tail = 11 + len(value) + 1 + 40 - 4  # 占位，下面用真实替换
        replacement = "            elif kind == \"gang\":\n                fixed = " + value + ".0\n"
        candidate = source.replace(ANCHOR, replacement)
        before = source.splitlines()
        after = candidate.splitlines()
        assert len(before) == len(after), "行数必须相同（只改一行）"
        diff = [i for i in range(len(before)) if before[i] != after[i]]
        assert len(diff) == 1, "只允许改一行，实际改了 %d 行" % len(diff)
        name = "OPTY-R18-C13-GANG%s.py" % value.replace(".", "_")
        path = _project_file(_PROJECT_ROOT, OUT / name)
        path.write_text(candidate, encoding="utf-8")
        compile(candidate, str(path), "exec")
        print("%s：只改第 %d 行，语法通过" % (name, diff[0] + 1))

        from hangma_bot.policy.action_value_executor import static_check

        static_check(candidate)
    print("静态合同检查全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())