#!/usr/bin/env python3
"""G39：强制一/二组四张同码及 1—4 白的生产自然缺口压力样本。"""

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

import g38_natural_gap_search as g38


HERE = Path(__file__).resolve().parent
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G39-QUAD-WHITE-GAP-STRESS-PREREG-2026-09-27.md')
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g38-natural-gap-search-20260927/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g39-quad-white-gap-stress-20260927/result.json')
SEED = 2026092739
HANDS_PER_CELL = 50_000


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """固定极端物理起手样本，输出同向听全留白缺口差异。"""

    if OUT.exists():
        raise SystemExit("G39 已有结果，拒绝覆盖")
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    if (source["schema"] != "g38-natural-gap-search/1" or
            source["script_sha256"] != sha(Path(g38.__file__))):
        raise ValueError("G38 冻结数学扫描来源漂移")
    rng = random.Random(SEED)
    counts = Counter()
    examples = {}
    for whites in (1, 2, 3, 4):
        for quads in (1, 2):
            cohort = f"white_{whites}_quads_{quads}"
            for _ in range(HANDS_PER_CELL):
                kinds = rng.sample(g38.NATURAL, quads)
                deck = [code for code in g38.DECK if code not in kinds]
                others = rng.sample(deck, 14 - whites - 4 * quads)
                hand = [code for code in kinds for _ in range(4)] + others
                same, different, pair, strata = g38._scan_hand(hand, whites)
                counts[cohort + "_hands"] += 1
                counts[cohort + "_same_shanten_pairs"] += same
                counts[cohort + "_different_natural_gap_pairs"] += different
                counts[cohort + "_hands_with_gap_difference"] += int(different > 0)
                for (standard, seven), amount in strata.items():
                    counts[cohort + f"_gap_difference_pairs_std_{standard}_seven_{seven}"] += amount
                if pair and cohort not in examples:
                    examples[cohort] = {"natural_hand": tuple(sorted(hand)),
                                        "whites_held": whites, "arms": pair}
    result = {"schema": "g39-quad-white-gap-stress/1", "seed": SEED,
              "hands_per_cell": HANDS_PER_CELL,
              "prereg_sha256": sha(PREREG), "source_g38_result_sha256": sha(SOURCE),
              "source_g38_script_sha256": sha(Path(g38.__file__)),
              "script_sha256": sha(Path(__file__)),
              "counts": dict(sorted(counts.items())), "first_examples": examples,
              "boundary": "强制四张同码及多白物理起手的生产数学压力样本；没有官方父代触达或整桌收益。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"counts": result["counts"], "first_examples": examples},
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
