#!/usr/bin/env python3
"""机械生成「七对路线偏好」候选：只插入一段，其余与冻结父代逐行相同。

机制：父代只读综合 `shanten_after`，把普通型与七对两个分牌型向听塌缩成一个数。
七对是真实的番值来源（七对 ×2、豪华七对 ×4、七对形爆头 ×4），
而三个独立分析都指出我们的失分在番值侧。本候选在同等综合向听下，
偏好七对向听更低的候选，即在评分里补回被塌缩掉的那一维。

插入点：主项 `total = base_floor - 1.0 if unknown else base` 之后。
生成后逐行核对：除插入块外必须逐字节相同。

用法：
    .venv/bin/python make_seven_pairs_candidates.py --weights 10,20,40
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
    """插入的七对路线项；与父代同风格做类型防御，未知值不参与打分。"""
    return (
        "        seven_pairs_shanten = action.get(\"seven_pairs_shanten_after\")\n"
        "        if seven_pairs_shanten is not None and seven_pairs_shanten is not True and seven_pairs_shanten is not False and 0 <= seven_pairs_shanten <= 8:\n"
        "            total += %s * (8 - seven_pairs_shanten)\n" % weight
    )


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", default="10,20,40")
    args = ap.parse_args(argv)

    source = frozen_source()
    assert source.count(ANCHOR) == 1, "锚点在冻结源码中出现 %d 次" % source.count(ANCHOR)
    OUT.mkdir(parents=True, exist_ok=True)

    for token in args.weights.split(","):
        weight = token.strip()
        candidate = source.replace(ANCHOR, ANCHOR + block(weight))
        before = source.splitlines()
        after = candidate.splitlines()
        added = len(block(weight).splitlines())
        inserted = len(after) - len(before)
        assert inserted == added, "应插入 %d 行，实际 %d" % (added, inserted)
        # 逐行核对：删掉插入块后必须与冻结源码逐行完全相同。
        index = before.index(ANCHOR.rstrip("\n"))
        assert before[:index + 1] == after[:index + 1], "插入点之前出现差异"
        assert before[index + 1:] == after[index + 1 + added:], "插入点之后出现差异"
        assert all(line.startswith("        ") for line in after[index + 1:index + 1 + added]), "插入行缩进异常"
        path = _project_file(_PROJECT_ROOT, OUT / ("OPTY-R18-C05-SEVENPAIRS%s.py" % weight))
        path.write_text(candidate, encoding="utf-8")
        print("%s 插入 %d 行，其余逐行相同" % (path.name, inserted))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())