#!/usr/bin/env python3
"""G26：生产 any_tile_win 对下一本人摸打后爆头态的结果盲条件机会。"""

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
from hangma_bot.hangma.hand_analysis import any_tile_win
from hangma_bot.hangma.internal_types import TILE_INDEX, TILE_ORDER, codes_from_counts
from hangma_bot.kernel.actions import Tile


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g23-three-draw-teacher-20260927')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g26-baotou-reach-20260927')
ROWS = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g26-baotou-reach-20260927/rows.jsonl.gz')
RESULT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g26-baotou-reach-20260927/result.json')
WHITE = TILE_INDEX["白"]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@lru_cache(maxsize=100_000)
def is_baotou_hand(counts: tuple[int, ...], melds: int) -> bool:
    """只复用生产任意听数学，不在研究脚本另写胡牌/爆头判定。"""

    if natural.summary(counts, melds).shanten != 0:
        return False
    tiles = tuple(Tile(code) for code in codes_from_counts(counts))
    return any_tile_win(tiles, melds)


def one_draw_reach(counts: tuple[int, ...], unseen: tuple[int, ...],
                   melds: int) -> dict:
    """每个物理可有摸牌码至多计一次；只允许非白后继弃牌。"""

    possible = []
    immediate = []
    for index, amount in enumerate(unseen):
        if amount <= 0:
            continue
        drawn = natural.changed(counts, index, 1)
        if natural.summary(drawn, melds).is_win:
            immediate.append(TILE_ORDER[index])
        for discard_index, held in enumerate(drawn):
            if held <= 0 or discard_index == WHITE:
                continue
            after = natural.changed(drawn, discard_index, -1)
            if is_baotou_hand(after, melds):
                possible.append(TILE_ORDER[index])
                break
    return {"baotou_draw_codes": possible,
            "baotou_public_capacity": sum(unseen[TILE_INDEX[code]] for code in possible),
            "immediate_hu_draw_codes": immediate,
            "immediate_hu_public_capacity": sum(unseen[TILE_INDEX[code]] for code in immediate)}


def _sign(value: int) -> str:
    return "positive" if value > 0 else "negative" if value < 0 else "equal"


def main() -> None:
    """对 G23 固定 144 对持白动作计算下一摸打爆头机会，不读赛果。"""

    if ROWS.exists() or RESULT.exists():
        raise SystemExit("G26 爆头机会证据已存在，拒绝覆盖")
    source = json.loads((_project_file(_PROJECT_ROOT, SOURCE / "result.json")).read_text(encoding="utf-8"))
    source_rows = _project_file(_PROJECT_ROOT, SOURCE / "rows.jsonl.gz")
    if (source.get("outcome_blind") is not True or
            source.get("rows_sha256") != sha(source_rows) or
            source.get("sampled_pairs") != 184):
        raise ValueError("G23 冻结输入漂移")
    rows = []
    counts = Counter()
    tables: dict[str, set[str]] = defaultdict(set)
    durations = []
    with gzip.open(source_rows, "rt", encoding="utf-8") as stream:
        for line in stream:
            prior = json.loads(line)
            if prior["white_after"] == 0:
                continue
            unknown = tuple(prior["unknown_counts34"])
            melds = prior["meld_count"]
            started = time.perf_counter()
            arms = {name: one_draw_reach(tuple(prior[name]["counts34"]), unknown, melds)
                    for name in ("parent", "alternative")}
            duration = (time.perf_counter() - started) * 1000
            is_baotou_hand.cache_clear()
            natural.summary.cache_clear()
            durations.append(duration)
            delta = (arms["alternative"]["baotou_public_capacity"] -
                     arms["parent"]["baotou_public_capacity"])
            early_delta = (arms["alternative"]["immediate_hu_public_capacity"] -
                           arms["parent"]["immediate_hu_public_capacity"])
            row = {"room_id": prior["room_id"], "game_id": prior["game_id"],
                   "round_no": prior["round_no"], "trigger_seq": prior["trigger_seq"],
                   "white_after": prior["white_after"],
                   "parent_action": prior["parent_action"],
                   "alternative_action": prior["alternative_action"],
                   "free_delta_2": prior["delta_2"], "free_delta_3": prior["delta_3"],
                   "parent": arms["parent"], "alternative": arms["alternative"],
                   "baotou_capacity_delta": delta, "immediate_hu_capacity_delta": early_delta,
                   "elapsed_ms": round(duration, 3)}
            rows.append(row)
            counts["pairs"] += 1
            group = "one_white" if prior["white_after"] == 1 else "multi_white"
            counts[group] += 1
            label = "baotou_" + _sign(delta)
            counts[label] += 1
            counts[group + "_" + label] += 1
            tables[label].add(prior["game_id"])
            counts["immediate_hu_" + _sign(early_delta)] += 1
            if prior["delta_2"] == 0 and prior["delta_3"] > 0:
                counts["free_three_positive_after_two_equal"] += 1
                counts["free_three_positive_baotou_" + _sign(delta)] += 1
            if len(rows) % 20 == 0:
                print("G26 evaluated", len(rows), "of 144", flush=True)
    if len(rows) != 144 or counts["one_white"] != 120 or counts["multi_white"] != 24:
        raise ValueError("G26 持白来源样本层漂移")
    OUT.mkdir(parents=True, exist_ok=True)
    with ROWS.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as stream:
            for row in rows:
                stream.write((json.dumps(row, ensure_ascii=False, sort_keys=True,
                                         separators=(",", ":")) + "\n").encode())
    durations.sort()
    result = {"schema": "g26-baotou-reach/1", "outcome_blind": True,
              "source_g23_result_sha256": sha(_project_file(_PROJECT_ROOT, SOURCE / "result.json")),
              "source_g23_rows_sha256": sha(source_rows),
              "production_hand_analysis_sha256": sha(_project_file(_PROJECT_ROOT, HERE.parents[1] / "src/hangma_bot/hangma/hand_analysis.py")),
              "probe_script_sha256": sha(Path(__file__)), "rows_sha256": sha(ROWS),
              "counts": dict(sorted(counts.items())),
              "table_coverage": {name: len(ids) for name, ids in sorted(tables.items())},
              "elapsed_ms_p50": durations[len(durations) // 2],
              "elapsed_ms_p95": durations[int(len(durations) * .95)],
              "boundary": "仅本人下一摸可见未知牌容量与可选非白弃牌下的静态生产 any_tile_win；非牌墙概率、非实际爆头/财飘/净分。"}
    RESULT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps(result["counts"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
