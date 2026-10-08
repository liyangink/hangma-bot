#!/usr/bin/env python3
"""G101：对新增官方房的合法摸打窗，结果盲枚举同向听更宽的非白弃牌。"""

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

import c31_action_layer_gap as c31
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g101-new-free-wider-route-20260928')
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G101-NEW-FREE-WIDER-ROUTE-PREREG-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g101-new-free-wider-route-20260928/selection')


def sha(path: Path) -> str:
    """输入与脚本以原始字节绑定。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def width(facts: object) -> tuple[int, int]:
    """返回普通型有效牌码数及公开未见容量；不能解释为实墙概率。"""
    useful = facts.standard_useful_tiles or ()
    return len(useful), sum(tile.remaining_estimate for tile in useful)


def classify(row: dict, counts: Counter) -> dict | None:
    """完全复现 G95 已冻结的可见选窗与备选弃牌次序。"""
    counts["legal_verified_windows"] += 1
    if not row["parent_agrees"]:
        counts["parent_disagrees"] += 1
        return None
    counts["parent_agrees"] += 1
    own_melds = row["observation"]["melds"][row["seat"]]
    if not any(meld["kind"] in ("chi", "peng") for meld in own_melds):
        return None
    counts["post_chi_peng"] += 1
    parent = row["parent_top_action"]
    if not parent.startswith("discard:") or parent == "discard:白":
        return None
    counts["post_claim_parent_nonwhite"] += 1
    obs = observation_from_json(row["observation"])
    analysis = c31.RULES.analyze(obs, value_limits=c31.VALUE_LIMITS)
    legal = {item.action_key: item for item in analysis.legal_candidates}
    if parent not in legal or parent not in row["legal_action_keys"]:
        raise ValueError("G101 父代弃牌不在重算规则合法集合")
    pf = legal[parent].facts
    if pf is None or type(pf.standard_shanten_after) is not int:
        counts["parent_missing_ordinary_facts"] += 1
        return None
    pw = width(pf)
    eligible = []
    for key, candidate in legal.items():
        if not key.startswith("discard:") or key == parent or key == "discard:白":
            continue
        facts = candidate.facts
        if facts is None or facts.standard_shanten_after != pf.standard_shanten_after:
            continue
        cw = width(facts)
        if cw[0] > pw[0] and cw[1] > pw[1]:
            eligible.append((key, cw))
    if not eligible:
        return None
    alternate, aw = min(eligible, key=lambda pair: (-pair[1][0], -pair[1][1], pair[0]))
    counts["target_windows"] += 1
    counts["target_white_" + str(min(2, sum(tile.code == "白" for tile in obs.my_hand)))] += 1
    shanten = pf.standard_shanten_after
    counts["target_shanten_" + str(min(2, shanten))] += 1
    return {
        "key": [row["room_id"], row["game_id"], row["round_no"], row["draw_seq"]],
        "seat": row["seat"], "remaining_tile_count": row["remaining_tile_count"],
        "white_before": sum(tile.code == "白" for tile in obs.my_hand),
        "own_melds": [meld["kind"] for meld in own_melds],
        "shanten": shanten, "parent_action": parent,
        "alternate_action": alternate,
        "parent_width": {"codes": pw[0], "public_unseen_capacity": pw[1]},
        "alternate_width": {"codes": aw[0], "public_unseen_capacity": aw[1]},
        "eligible_alternate_count": len(eligible),
        "observation": row["observation"],
    }


def main() -> None:
    """房间与牌谱身份逐项核验；完整输出含所有目标窗，不按赛果挑选。"""
    if OUT.exists():
        raise FileExistsError("G101 选择结果目录已有，拒绝覆盖")
    batch_path = _project_file(_PROJECT_ROOT, SOURCE / "result.json")
    batch = json.loads(batch_path.read_text(encoding="utf-8"))
    if batch["outcome_labels_opened"] is not False or len(batch["rooms"]) != 16:
        raise ValueError("G101 来源不属于冻结十六房")
    counts = Counter()
    rooms = Counter()
    tables: dict[str, set[str]] = defaultdict(set)
    rows = []
    for room, record in sorted(batch["rooms"].items()):
        packed_path = _project_file(_PROJECT_ROOT, SOURCE / "rooms" / room / "windows.json.gz")
        if sha(packed_path) != record["windows_gzip_sha256"]:
            raise ValueError("G101 房间窗口压缩证据摘要漂移")
        raw = gzip.decompress(packed_path.read_bytes())
        if hashlib.sha256(raw).hexdigest() != record["windows_uncompressed_sha256"]:
            raise ValueError("G101 房间窗口原文摘要漂移")
        windows = json.loads(raw)["windows"]
        if len(windows) != record["counts"]["legal_verified_windows"]:
            raise ValueError("G101 房间逐窗数量漂移")
        for window in windows:
            if window["room_id"] != room:
                raise ValueError("G101 混入外房窗口")
            target = classify(window, counts)
            if target is None:
                continue
            rows.append(target)
            rooms[room] += 1
            tables[room].add(window["game_id"])
    if counts["legal_verified_windows"] != batch["totals"]["legal_verified_windows"]:
        raise ValueError("G101 十六房逐窗覆盖量不一致")
    rows.sort(key=lambda row: row["key"])
    result = {
        "schema": "g101-new-free-wider-route-selection/1",
        "outcome_labels_opened": False,
        "input_sha256": {"batch": sha(batch_path), "prereg": sha(PREREG),
                         "selector": sha(Path(__file__))},
        "counts": dict(sorted(counts.items())),
        "target_rooms": len(rooms), "target_tables": sum(map(len, tables.values())),
        "per_room_targets": dict(sorted(rooms.items())),
        "per_room_tables": {room: len(value) for room, value in sorted(tables.items())},
        "boundary": "目标窗只按当时可见规则事实选择；官方后续行为与积分未作标签。",
    }
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    with (_project_file(_PROJECT_ROOT, OUT / "rows.jsonl.gz")).open("wb") as output:
        body = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows).encode("utf-8")
        output.write(gzip.compress(body, compresslevel=9, mtime=0))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
