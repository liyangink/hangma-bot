#!/usr/bin/env python3
"""G25：在 G23 已冻结动作对上禁止后继弃白的三摸理想容量。"""

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

from collections import Counter, defaultdict
from functools import lru_cache
import gzip
import hashlib
import json
from pathlib import Path
import time

import g7_three_self_draw_probe as natural
from hangma_bot.hangma.internal_types import TILE_INDEX


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g23-three-draw-teacher-20260927')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g25-white-retained-three-draw-20260927')
ROWS = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g25-white-retained-three-draw-20260927/rows.jsonl.gz')
RESULT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g25-white-retained-three-draw-20260927/result.json')
WHITE_INDEX = TILE_INDEX["白"]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@lru_cache(maxsize=500_000)
def favorable_hold_white(counts: tuple[int, ...], unseen: tuple[int, ...],
                         melds: int, depth: int) -> int:
    """G7 同源生产胡数学，唯一变化是未来本人弃牌跳过白板。"""

    current = natural.summary(counts, melds)
    if current.shanten >= depth:
        return 0
    if depth == 1:
        if current.shanten != 0:
            return 0
        return sum(unseen[TILE_INDEX[code]] for code in current.useful_codes)
    n = sum(unseen)
    total = 0
    for drawn_index, available in enumerate(unseen):
        if available <= 0:
            continue
        drawn = natural.changed(counts, drawn_index, 1)
        next_unseen = natural.changed(unseen, drawn_index, -1)
        if natural.summary(drawn, melds).is_win:
            best = natural.falling(n - 1, depth - 1)
        else:
            best = 0
            for discarded_index, held in enumerate(drawn):
                if held <= 0 or discarded_index == WHITE_INDEX:
                    continue
                after = natural.changed(drawn, discarded_index, -1)
                if natural.summary(after, melds).shanten >= depth - 1:
                    continue
                value = favorable_hold_white(after, next_unseen, melds, depth - 1)
                if value > best:
                    best = value
        total += available * best
    return total


def _sign(value: int) -> str:
    return "positive" if value > 0 else "negative" if value < 0 else "equal"


def main() -> None:
    """结果盲固定 144 持白对，和 G23 自由包络逐对同源对账。"""

    if ROWS.exists() or RESULT.exists():
        raise SystemExit("G25 留白教师已存在，拒绝覆盖")
    source = json.loads((_project_file(_PROJECT_ROOT, SOURCE / "result.json")).read_text(encoding="utf-8"))
    source_rows = _project_file(_PROJECT_ROOT, SOURCE / "rows.jsonl.gz")
    if (source.get("outcome_blind") is not True or
            source.get("rows_sha256") != sha(source_rows) or
            source.get("sampled_pairs") != 184):
        raise ValueError("G23 冻结来源漂移")
    rows = []
    counts = Counter()
    tables: dict[str, set[str]] = defaultdict(set)
    elapsed = []
    with gzip.open(source_rows, "rt", encoding="utf-8") as stream:
        for line in stream:
            prior = json.loads(line)
            white = prior["white_after"]
            if white == 0:
                continue
            unknown = tuple(prior["unknown_counts34"])
            melds = prior["meld_count"]
            started = time.perf_counter()
            arms = {}
            for name in ("parent", "alternative"):
                hand = tuple(prior[name]["counts34"])
                if hand[WHITE_INDEX] != white:
                    raise ValueError("G25 初始持白数与 G23 不一致")
                arms[name] = {str(depth): favorable_hold_white(hand, unknown, melds, depth)
                              for depth in (2, 3)}
            duration = (time.perf_counter() - started) * 1000
            favorable_hold_white.cache_clear()
            natural.summary.cache_clear()
            elapsed.append(duration)
            d2 = arms["alternative"]["2"] - arms["parent"]["2"]
            d3 = arms["alternative"]["3"] - arms["parent"]["3"]
            if (arms["parent"]["2"] > prior["parent"]["depth2"] or
                    arms["alternative"]["2"] > prior["alternative"]["depth2"] or
                    arms["parent"]["3"] > prior["parent"]["depth3"] or
                    arms["alternative"]["3"] > prior["alternative"]["depth3"]):
                raise ValueError("限制未来弃白后的成功容量反而超过自由包络")
            row = {"room_id": prior["room_id"], "game_id": prior["game_id"],
                   "round_no": prior["round_no"], "trigger_seq": prior["trigger_seq"],
                   "white_after": white, "parent_action": prior["parent_action"],
                   "alternative_action": prior["alternative_action"],
                   "free_delta_2": prior["delta_2"], "free_delta_3": prior["delta_3"],
                   "hold_parent": arms["parent"], "hold_alternative": arms["alternative"],
                   "hold_delta_2": d2, "hold_delta_3": d3,
                   "elapsed_ms": round(duration, 3)}
            rows.append(row)
            counts["pairs"] += 1
            group = "one_white" if white == 1 else "multi_white"
            counts[group] += 1
            for depth, delta in ((2, d2), (3, d3)):
                label = f"hold_depth{depth}_{_sign(delta)}"
                counts[label] += 1
                tables[label].add(prior["game_id"])
                counts[group + "_" + label] += 1
            if prior["delta_2"] == 0 and prior["delta_3"] != 0:
                counts["free_new_three_only"] += 1
                if d2 == 0 and d3 != 0:
                    counts["hold_new_three_only"] += 1
                if _sign(d3) == _sign(prior["delta_3"]):
                    counts["free_three_direction_retained"] += 1
                elif d3 == 0:
                    counts["free_three_became_equal"] += 1
                else:
                    counts["free_three_direction_reversed"] += 1
            if len(rows) % 20 == 0:
                print("G25 evaluated", len(rows), "of 144", flush=True)
    if len(rows) != 144 or counts["one_white"] != 120 or counts["multi_white"] != 24:
        raise ValueError("G25 冻结持白样本层数漂移")
    OUT.mkdir(parents=True, exist_ok=True)
    with ROWS.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as stream:
            for row in rows:
                stream.write((json.dumps(row, ensure_ascii=False, sort_keys=True,
                                         separators=(",", ":")) + "\n").encode())
    elapsed.sort()
    result = {"schema": "g25-white-retained-three-draw/1", "outcome_blind": True,
              "source_g23_result_sha256": sha(_project_file(_PROJECT_ROOT, SOURCE / "result.json")),
              "source_g23_rows_sha256": sha(source_rows),
              "g7_math_script_sha256": sha(_project_file(_PROJECT_ROOT, HERE / "g7_three_self_draw_probe.py")),
              "probe_script_sha256": sha(Path(__file__)), "rows_sha256": sha(ROWS),
              "counts": dict(sorted(counts.items())),
              "table_coverage": {name: len(ids) for name, ids in sorted(tables.items())},
              "elapsed_ms_p50": elapsed[len(elapsed) // 2],
              "elapsed_ms_p95": elapsed[int(len(elapsed) * .95)],
              "boundary": "保留初始白板但允许其在生产胡数学中作百搭；无真实对手/抓打/留墩/结算，不是爆头或财飘收益。"}
    RESULT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps(result["counts"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
