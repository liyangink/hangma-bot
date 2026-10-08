#!/usr/bin/env python3
"""G38：生产数学下固定随机物理手牌的同向听全留白自然缺口空间。"""

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

from collections import Counter
import hashlib
import json
from pathlib import Path
import random

from hangma_bot.hangma._standard import backend_info, need
from hangma_bot.hangma.hand_analysis import _chiitoi_pairs
from hangma_bot.kernel.actions import CANONICAL_TILE_INDEX, CANONICAL_TILE_ORDER


HERE = Path(__file__).resolve().parent
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G38-NATURAL-GAP-SEARCH-PREREG-2026-09-27.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g38-natural-gap-search-20260927/result.json')
SEED = 2026092738
HANDS_PER_WHITE = 100_000
NATURAL = tuple(code for code in CANONICAL_TILE_ORDER if code != "白")
DECK = tuple(code for code in NATURAL for _ in range(4))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def values(natural_counts: tuple[int, ...], whites: int) -> dict[str, int]:
    """生产数学：无副露弃后暗牌的普通/七对向听及全留白自然缺口。"""

    natural_need = need(natural_counts, 0, 4, True)
    standard = need(natural_counts, whites, 4, True) - 1
    seven = 6 - _chiitoi_pairs(natural_counts, whites)
    return {"standard_shanten": standard, "seven_pairs_shanten": seven,
            "combined_shanten": min(standard, seven), "all_white_reserved_natural_need": natural_need}


def _scan_hand(codes: list[str], whites: int) -> tuple[int, int, list[dict], Counter]:
    """同一 14 张手牌比较所有不同非白弃牌，返回同向听自然缺口差异。"""

    before = [codes.count(code) for code in NATURAL]
    arms = []
    for code in sorted(set(codes)):
        index = CANONICAL_TILE_INDEX[code]
        if index >= 33:
            raise ValueError("G38 自然牌抽样出现白板")
        before[index] -= 1
        facts = values(tuple(before), whites)
        before[index] += 1
        arms.append({"discard": code, **facts})
    differing = 0
    same = 0
    first_pairs = []
    strata = Counter()
    for left_index, left in enumerate(arms):
        for right in arms[left_index + 1:]:
            if (left["standard_shanten"] != right["standard_shanten"] or
                    left["seven_pairs_shanten"] != right["seven_pairs_shanten"]):
                continue
            if left["combined_shanten"] != right["combined_shanten"]:
                raise ValueError("同普通/七对向听而综合向听不同")
            same += 1
            if (left["all_white_reserved_natural_need"] !=
                    right["all_white_reserved_natural_need"]):
                differing += 1
                strata[(left["standard_shanten"], left["seven_pairs_shanten"])] += 1
                if not first_pairs:
                    first_pairs = [left, right]
    return same, differing, first_pairs, strata


def main() -> None:
    """固定样本数和种子，输出可复算分层；既有结果不可覆盖。"""

    if OUT.exists():
        raise SystemExit("G38 已有结果，拒绝覆盖")
    if not PREREG.exists():
        raise ValueError("G38 预登记缺失")
    rng = random.Random(SEED)
    counts = Counter()
    examples = {}
    for whites in (1, 2):
        for _ in range(HANDS_PER_WHITE):
            codes = rng.sample(DECK, 14 - whites)
            same, differing, pair, strata = _scan_hand(codes, whites)
            prefix = f"white_{whites}_"
            counts[prefix + "hands"] += 1
            counts[prefix + "same_shanten_pairs"] += same
            counts[prefix + "different_natural_gap_pairs"] += differing
            counts[prefix + "hands_with_same_shanten_pair"] += int(same > 0)
            counts[prefix + "hands_with_gap_difference"] += int(differing > 0)
            for (standard, seven), amount in strata.items():
                counts[prefix + f"gap_difference_pairs_std_{standard}_seven_{seven}"] += amount
            if pair:
                if str(whites) not in examples:
                    examples[str(whites)] = {"natural_hand": tuple(sorted(codes)),
                                              "whites_held": whites, "arms": pair}
    result = {"schema": "g38-natural-gap-search/1", "seed": SEED,
              "hands_per_white": HANDS_PER_WHITE, "native_math": backend_info(),
              "prereg_sha256": sha(PREREG), "script_sha256": sha(Path(__file__)),
              "counts": dict(sorted(counts.items())), "first_examples": examples,
              "boundary": "条件随机物理 14 张手牌的生产数学搜索空间；不含父代实际动作、公开可摸性、对手或净分。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"counts": result["counts"], "first_examples": examples},
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
