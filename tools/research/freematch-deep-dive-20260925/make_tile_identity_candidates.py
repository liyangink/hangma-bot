#!/usr/bin/env python3
"""机械生成「只依赖牌码」的候选：插入一段按**牌的身份**（不是张数）打分的项。

动机：父代的 support = Σ remaining 只看**张数**。实测 13.4% 的窗口里，
前两名总数相同、种数也相同，只有「是哪几张牌」不同——所有派生摘要取平。
但牌码本身是可读的，所以「对有效牌集合排序」这件事在受限 DSL 里**写得出来**。

本脚本生成三种只依赖牌码的项：
  CENTRAL  偏好中张（2—8）有效牌
  TERMINAL 偏好幺九与字牌有效牌
  SAME_SUIT 偏好与本家副露同花色的有效牌

用法：
    .venv/bin/python make_tile_identity_candidates.py --settings "CENTRAL:1,CENTRAL:4,TERMINAL:4"
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


def block(mode: str, weight: str) -> str:
    body = [
        "        tile_id_count = 0",
        "        tile_id_tiles = action.get(\"useful_tiles\")",
        "        if tile_id_tiles is not None:",
        "            for tile_id_item in tile_id_tiles:",
        "                tile_id_code = tile_id_item.get(\"code\")",
        "                tile_id_remaining = tile_id_item.get(\"remaining_estimate\")",
        "                if tile_id_code is None or len(tile_id_code) < 2:",
        "                    continue",
        "                if tile_id_remaining is None or tile_id_remaining is True or tile_id_remaining is False:",
        "                    continue",
        "                if float(tile_id_remaining) <= 0.0:",
        "                    continue",
    ]
    if mode == "CENTRAL":
        body += [
            "                if tile_id_code[0] in \"2345678\" and tile_id_code[-1] in \"wbt\":",
            "                    tile_id_count += 1",
        ]
    elif mode == "TERMINAL":
        body += [
            "                if tile_id_code[-1] not in \"wbt\" or tile_id_code[0] in \"19\":",
            "                    tile_id_count += 1",
        ]
    elif mode == "SAME_SUIT":
        body += [
            "                for tile_id_meld in melds[seat]:",
            "                    for tile_id_other in tile_id_meld.get(\"tiles\"):",
            "                        if (len(tile_id_other) >= 2 and tile_id_other[-1] == tile_id_code[-1]",
            "                                and tile_id_other[-1] in \"wbt\"):",
            "                            tile_id_count += 1",
            "                            break",
        ]
    else:
        raise SystemExit("未知模式: " + mode)
    body += ["        total += %s * tile_id_count" % weight]
    return "\n".join(body) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--settings", default="CENTRAL:1,CENTRAL:4,TERMINAL:4")
    args = ap.parse_args(argv)

    source = frozen_source()
    assert source.count(ANCHOR) == 1, "锚点出现 %d 次" % source.count(ANCHOR)
    OUT.mkdir(parents=True, exist_ok=True)

    for token in args.settings.split(","):
        mode, weight = (part.strip() for part in token.split(":"))
        inserted = block(mode, weight)
        candidate = source.replace(ANCHOR, ANCHOR + inserted)
        before = source.splitlines()
        after = candidate.splitlines()
        added = len(inserted.splitlines())
        assert len(after) - len(before) == added, "插入行数不符"
        index = before.index(ANCHOR.rstrip("\n"))
        assert before[:index + 1] == after[:index + 1], "插入点之前出现差异"
        assert before[index + 1:] == after[index + 1 + added:], "插入点之后出现差异"
        name = "OPTY-R18-C09-%s%s.py" % (mode, weight.replace(".", "_"))
        path = _project_file(_PROJECT_ROOT, OUT / name)
        path.write_text(candidate, encoding="utf-8")
        compile(candidate, str(path), "exec")
        print("%s 插入 %d 行，逐行核对通过，语法通过" % (name, added))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())