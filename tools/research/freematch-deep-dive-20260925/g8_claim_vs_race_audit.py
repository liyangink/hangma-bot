#!/usr/bin/env python3
"""训练房赛后诊断：实际被鸣与本人下次摸牌前他家先胡的关系。"""

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
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np

import g8_public_response_validate as validation


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g8-public-response-training-20260927')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g8-claim-vs-race-20260927/result.json')


def main() -> None:
    """只用已开过的 91 间训练房；按房对账，不从观察关联推因果。"""

    metadata = json.loads((_project_file(_PROJECT_ROOT, SOURCE / "result.json")).read_text(encoding="utf-8"))
    packed = _project_file(_PROJECT_ROOT, SOURCE / "rows.jsonl.gz")
    if hashlib.sha256(packed.read_bytes()).hexdigest() != metadata["rows_gzip_sha256"]:
        raise ValueError("训练弃牌行摘要漂移")
    outcomes = validation.next_self_draw_outcomes(set(metadata["source_rooms"]))
    total = Counter()
    by_room = defaultdict(Counter)
    seen = set()
    with gzip.open(packed, "rt", encoding="utf-8") as stream:
        for line in stream:
            record = json.loads(line)
            key = (record["game_id"], record["round_no"], record["discard_seq"])
            if key in seen:
                raise ValueError("训练弃牌重复")
            seen.add(key)
            outcome = outcomes.get(key)
            if outcome is None:
                raise ValueError("训练弃牌缺赛后下一摸/终局")
            label = "claimed" if record["label_claim"] else "not_claimed"
            kind = outcome["kind"]
            total[f"{label}|{kind}"] += 1
            by_room[record["room_id"]][f"{label}|{kind}"] += 1
    if len(seen) != 62975 or set(by_room) != set(metadata["source_rooms"]):
        raise ValueError("冻结训练房覆盖不符")
    room_differences = []
    for room in sorted(by_room):
        counts = by_room[room]
        claimed = sum(value for key, value in counts.items() if key.startswith("claimed|"))
        not_claimed = sum(value for key, value in counts.items() if key.startswith("not_claimed|"))
        if claimed == 0 or not_claimed == 0:
            raise ValueError("房内一组缺席")
        difference = (counts["claimed|other_hu_before_self_draw"] / claimed -
                      counts["not_claimed|other_hu_before_self_draw"] / not_claimed)
        room_differences.append(difference)
    rng = np.random.default_rng(20260927)
    values = np.array(room_differences)
    samples = rng.integers(0, len(values), size=(20000, len(values)))
    sampled_means = values[samples].mean(axis=1)
    result = {"schema": "g8-claim-vs-race-training-audit/1",
              "source_rows_gzip_sha256": metadata["rows_gzip_sha256"],
              "rooms": len(by_room), "executed_discards": len(seen),
              "total": dict(sorted(total.items())),
              "by_room": {room: dict(sorted(counts.items())) for room, counts in sorted(by_room.items())},
              "room_equal_difference_claimed_minus_not_claimed": {
                  "mean": float(values.mean()),
                  "room_bootstrap_95": [float(np.quantile(sampled_means, 0.025)),
                                        float(np.quantile(sampled_means, 0.975))],
                  "negative_rooms": int(np.sum(values < 0)),
                  "positive_rooms": int(np.sum(values > 0))},
              "boundary": "本人真实弃牌的赛后观察关联；被鸣会改写座位巡序，牌形、墙深和他家暗手未配对；不能解释为避鸣的因果收益"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "by_room"},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
