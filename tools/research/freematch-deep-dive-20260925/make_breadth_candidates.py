#!/usr/bin/env python3
"""机械生成「进张宽度」候选：只插入一段，其余与冻结父代逐行相同。

机制来源（真实赛事证据）：2026-09-17 官方测试赛报告的第 2 条发现说，
我方短板是「有效进张宽度 32.5 分位（按向听档匹配后仍低 0.459 种）」，
而不是速度或番数。

而父代的进张项是 `Σ remaining_estimate`——一个**张数**（深度）度量，
不是**种数**（宽度）度量。两者在同等 Σ 下可以差很远：
  「4 种牌各剩 1 张」（宽度 4、深度 4）与「1 种牌剩 4 张」（宽度 1、深度 4）
在父代眼里完全等价。

本候选在父代打分上叠加一个宽度项：

    total += W × len(useful_tiles)

插入点：主项 `total = base_floor - 1.0 if unknown else base` 之后。
生成后逐行核对：除插入块外必须与冻结源码逐字节相同。

用法：
    .venv/bin/python make_breadth_candidates.py --weights 1,3,8
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
ANCHOR = "        total = base_floor - 1.0 if unknown else base\n"


def frozen_source() -> str:
    spec = importlib.util.spec_from_file_location("frozen_r18_v2", FROZEN)
    module = importlib.util.module_from_spec(spec)
    sys.modules["frozen_r18_v2"] = module
    spec.loader.exec_module(module)
    return module.R18_INTEGRATED_POSITIVE_V2_SOURCE


def block(weight: str) -> str:
    """宽度项：只数有几种有效牌，不数各有几剩；与父代同风格做类型防御。"""
    body = [
        "        breadth_tiles = action.get(\"useful_tiles\")",
        "        breadth_count = 0",
        "        if breadth_tiles is not None:",
        "            for breadth_tile in breadth_tiles:",
        "                breadth_remaining = breadth_tile.get(\"remaining_estimate\")",
        "                if breadth_remaining is None or breadth_remaining is True or breadth_remaining is False:",
        "                    continue",
        "                if float(breadth_remaining) > 0.0:",
        "                    breadth_count += 1",
        "        total += %s * breadth_count" % weight,
    ]
    return "\n".join(body) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", default="1,3,8")
    args = ap.parse_args(argv)

    source = frozen_source()
    assert source.count(ANCHOR) == 1, "锚点在冻结源码中出现 %d 次" % source.count(ANCHOR)
    OUT.mkdir(parents=True, exist_ok=True)

    for token in args.weights.split(","):
        weight = token.strip()
        inserted_block = block(weight)
        candidate = source.replace(ANCHOR, ANCHOR + inserted_block)
        before = source.splitlines()
        after = candidate.splitlines()
        added = len(inserted_block.splitlines())
        assert len(after) - len(before) == added, "插入行数不符"
        index = before.index(ANCHOR.rstrip("\n"))
        assert before[:index + 1] == after[:index + 1], "插入点之前出现差异"
        assert before[index + 1:] == after[index + 1 + added:], "插入点之后出现差异"
        assert all(line.startswith("        ") for line in after[index + 1:index + 1 + added])
        name = "OPTY-R18-C07-BREADTH%s.py" % weight.replace(".", "_")
        path = _project_file(_PROJECT_ROOT, OUT / name)
        path.write_text(candidate, encoding="utf-8")
        compile(candidate, str(path), "exec")
        print("%s 插入 %d 行，其余逐行相同，语法通过" % (name, added))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())