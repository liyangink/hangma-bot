#!/usr/bin/env python3
"""机械生成「保留对子」候选：只插入一段，其余与冻结父代逐行相同。

动机：本会话唯一稳定的大行为差异是爆头进入率 2.1 倍，而爆头需要「4 面子 + 浮财神」；
面子的来源之一是碰，而碰需要手里留对子。我方弃牌在向听意义上比所有人都规范
（最优率 0.9989 > 榜上 0.9881 > 其他 0.9814），但鸣牌比对手少 0.119 次/局。

本候选在父代打分上叠加「手牌里的对子数」项：total += W * (出现 >= 2 次的牌种数)。
若可达性够大，说明同在最小向听档内的弃牌选择确实有系统性差别；若 < 10%，与 P13 同型一并关闭。

用法：
    .venv/bin/python make_pair_keep_candidates.py --weights 3,10,30
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
ANCHOR = "            total = round(total, 6)\n            total += style_part\n"

BLOCK_LINES = [
    "            pairs_kept = 0",
    "            seen_pairs = []",
    "            for tile in hand:",
    "                if tile == wealth:",
    "                    continue",
    "                if tile in seen_pairs:",
    "                    continue",
    "                seen_pairs.append(tile)",
    "                copies = hand.count(tile)",
    "                if tile == tile_code:",
    "                    copies -= 1",
    "                if copies >= 2:",
    "                    pairs_kept += 1",
    "            total += __WEIGHT__ * pairs_kept",
]


def block_for(weight: str) -> str:
    return "\n".join(line.replace("__WEIGHT__", weight) for line in BLOCK_LINES) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", default="3,10,30")
    args = ap.parse_args()
    source = R18_INTEGRATED_POSITIVE_V2_SOURCE
    assert source.count(ANCHOR) == 1, "锚点在冻结源码中出现 %d 次" % source.count(ANCHOR)
    OUT.mkdir(parents=True, exist_ok=True)
    for token in args.weights.split(","):
        weight = token.strip()
        block = block_for(weight)
        candidate = source.replace(ANCHOR, block + ANCHOR)
        before = source.splitlines()
        after = candidate.splitlines()
        added = len(block.splitlines())
        assert len(after) - len(before) == added, "插入行数不符"
        anchor_lines = ANCHOR.split("\n")[:2]
        index = -1
        for i in range(len(before) - 1):
            if before[i:i + 2] == anchor_lines:
                index = i
                break
        assert index >= 0, "锚点行在源码中找不到"
        assert before[:index] == after[:index], "插入点之前出现差异"
        assert before[index:] == after[index + added:], "插入点之后出现差异"
        name = "OPTY-R18-C14-PAIRKEEP%s.py" % weight.replace(".", "_")
        path = _project_file(_PROJECT_ROOT, OUT / name)
        path.write_text(candidate, encoding="utf-8")
        compile(candidate, str(path), "exec")
        print("%s：插入 %d 行，其余逐行相同，语法通过" % (name, added))

        from hangma_bot.policy.action_value_executor import static_check

        static_check(candidate)
    print("静态合同检查全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())