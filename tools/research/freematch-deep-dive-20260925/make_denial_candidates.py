#!/usr/bin/env python3
"""机械生成「不喂牌给对手」候选（C17）：在父代打分上叠加「弃牌的对手可鸣张数」惩罚。

动机：本赛制**只能自摸、没有点炮**，所以父代的 risk_units（按下家/庄家副露判「危险」）
防的是一个不存在的威胁。**唯一的防守形态是「不借牌给对手吃碰提速」**——
而对手的爆头路线正好需要副露（P19：前提窗口 75% 来自鸣牌之后）。

本候选惩罚「弃一张对手还有较多未见张可用来吃碰的牌」：

    claim_pool = 4 - 我手张数 - 牌河与副露里的张数
    total -= W * claim_pool

用法：
    .venv/bin/python make_denial_candidates.py --weights 1,3,8
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
    "            vis_elsewhere = 0",
    "            for river_seat in range(4):",
    "                vis_elsewhere += discards[river_seat].count(tile_code)",
    "            for meld_seat in range(4):",
    "                for meld in melds[meld_seat]:",
    "                    for other in meld.get(\"tiles\"):",
    "                        if other == tile_code:",
    "                            vis_elsewhere += 1",
    "            hand_copies = hand.count(tile_code)",
    "            claim_pool = 4 - vis_elsewhere - hand_copies",
    "            if claim_pool < 0:",
    "                claim_pool = 0",
    "            total -= __WEIGHT__ * claim_pool",
]


def block_for(weight: str) -> str:
    return "\n".join(line.replace("__WEIGHT__", weight) for line in BLOCK_LINES) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", default="1,3,8")
    args = ap.parse_args()
    source = R18_INTEGRATED_POSITIVE_V2_SOURCE
    assert source.count(ANCHOR) == 1, "锚点在冻结源码中出现 %d 次" % source.count(ANCHOR)
    OUT.mkdir(parents=True, exist_ok=True)
    anchor_lines = ANCHOR.split("\n")[:2]
    for token in args.weights.split(","):
        weight = token.strip()
        block = block_for(weight)
        candidate = source.replace(ANCHOR, block + ANCHOR)
        before = source.splitlines()
        after = candidate.splitlines()
        added = len(block.splitlines())
        assert len(after) - len(before) == added, "插入行数不符"
        index = -1
        for i in range(len(before) - 1):
            if before[i:i + 2] == anchor_lines:
                index = i
                break
        assert index >= 0, "锚点行在源码中找不到"
        assert before[:index] == after[:index], "插入点之前出现差异"
        assert before[index:] == after[index + added:], "插入点之后出现差异"
        name = "OPTY-R18-C17-DENIAL%s.py" % weight.replace(".", "_")
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