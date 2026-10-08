#!/usr/bin/env python3
"""G155：官方同房首次一白普通型一向听后的真实自然行动链。"""

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

import g145_opportunity_exposure_and_entry_audit as g145


HERE = Path(__file__).resolve().parent
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G155-PRE-READY-NATURAL-CHAIN-PREREG-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g155-pre-ready-natural-chain-20260928')
ROWS = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g155-pre-ready-natural-chain-20260928/rows.jsonl.gz')
RESULT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g155-pre-ready-natural-chain-20260928/result.json')


def sha(path: Path) -> str:
    """返回冻结证据或量具的原始字节 SHA-256。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def white_after(row: dict) -> int:
    """只对已核正常摸打，按真实弃白动作求弃后暗手白板数。"""
    amount = row["white_before"] - (row["actual_action"] == "discard:白")
    if amount < 0 or not row["actual_action"].startswith("discard:"):
        raise ValueError("真实弃牌或白板数不合法")
    return amount


def make_row(hand: tuple, source: list[dict], round_record: dict) -> dict | None:
    """首次一向听按当时事实选入；后续仅作赛后路径描述。"""
    windows = sorted(source, key=lambda item: item["draw_seq"])
    if len(windows) != round_record["clean_windows"]:
        raise ValueError("单局窗口数与 G69 不符")
    if len({row["draw_seq"] for row in windows}) != len(windows):
        raise ValueError("本人正常摸打序号重复")
    if any(row["actual"] is None or row["actual"]["standard_shanten"] is None
           for row in windows):
        raise ValueError("G69 已核本人窗口缺少普通型规则事实")
    first_one = next((index for index, row in enumerate(windows)
                      if row["actual"]["standard_shanten"] == 1), None)
    if first_one is None:
        return None
    first = windows[first_one]
    if (first["white_before"] != 1
            or first["actual"]["plain_capacity"] != 0
            or any(row["actual"]["standard_shanten"] < 2
                   for row in windows[:first_one])):
        return None
    following = windows[first_one + 1:]
    ready_index = next((index for index, row in enumerate(following, 1)
                        if row["actual"]["plain_capacity"] > 0), None)
    ready = following[ready_index - 1] if ready_index is not None else None
    if (round_record["first_plain_ready"] !=
            (None if ready is None else ready["action_ordinal"])):
        raise ValueError("首次普通一番入口与 G69 单局汇总不符")
    if ready is not None and ready["actual"]["standard_shanten"] != 0:
        raise ValueError("普通一番入口不是普通型零向听")
    parent = first["parent"] if hand[4] == "peer" else None
    parent_comparable = (parent is not None
                         and first["parent_action"] is not None
                         and first["parent_action"].startswith("discard:")
                         and parent["standard_shanten"] == 1
                         and parent["standard_support"] is not None)
    if first["actual"]["standard_support"] is None:
        raise ValueError("入口缺少本人普通型即时有效张容量")
    return {
        "peer": hand[0], "room": hand[1], "game_id": hand[2],
        "round_no": hand[3], "actor": hand[4],
        "start_white": round_record["start_white"],
        "entry_draw_seq": first["draw_seq"],
        "entry_action_ordinal": first["action_ordinal"],
        "entry_wall_remaining": first["wall_remaining"],
        "entry_action": first["actual_action"],
        "entry_white_after": white_after(first),
        "entry_standard_support": first["actual"]["standard_support"],
        "parent_action": first["parent_action"],
        "parent_same_shanten_discard": parent_comparable,
        "parent_standard_support": (parent["standard_support"]
                                    if parent_comparable else None),
        "subsequent_clean_windows": len(following),
        "next_clean_draw": bool(following),
        "first_plain_ready_step": ready_index,
        "first_plain_ready_action_ordinal": (
            None if ready is None else ready["action_ordinal"]),
        "first_plain_ready_white_after": None if ready is None else white_after(ready),
        "discarded_white_before_ready": any(
            row["actual_action"] == "discard:白"
            for row in following[:ready_index - 1 if ready_index is not None
                                 else len(following)]),
        "round_status": round_record["status"],
        "round_fan": round_record["fan"],
        "unknown_windows": round_record["unknown_windows"],
    }


def aggregate(rows: list[dict]) -> dict:
    """同房强手与我方分别按座位单局计，来源房数单列。"""
    groups: dict[str, Counter] = defaultdict(Counter)
    rooms: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        start_white = ("2plus" if row["start_white"] >= 2
                       else str(row["start_white"]))
        for suffix in ("all", "start_white_" + start_white):
            name = f"{row['peer']}/{row['actor']}/{suffix}"
            count = groups[name]
            rooms[name].add(row["room"])
            count["entry_hands"] += 1
            count["entry_white_kept"] += row["entry_white_after"] == 1
            count["entry_standard_support_sum"] += row["entry_standard_support"]
            count["entry_action_ordinal_sum"] += row["entry_action_ordinal"]
            count["next_clean_yes"] += row["next_clean_draw"]
            count["next_clean_no"] += not row["next_clean_draw"]
            count["later_plain_ready"] += row["first_plain_ready_step"] is not None
            if row["first_plain_ready_step"] is not None:
                step = row["first_plain_ready_step"]
                count["ready_next_clean"] += step == 1
                count["ready_second_clean"] += step == 2
                count["ready_third_or_later_clean"] += step >= 3
                count["ready_still_has_white"] += (
                    row["first_plain_ready_white_after"] >= 1)
            elif row["next_clean_draw"]:
                count["next_clean_but_not_ready"] += 1
            else:
                count["no_next_status_" + row["round_status"]] += 1
            count["discarded_white_before_ready"] += row[
                "discarded_white_before_ready"]
            if row["parent_same_shanten_discard"]:
                count["peer_parent_comparable"] += 1
                count["peer_parent_action_changed"] += (
                    row["entry_action"] != row["parent_action"])
                difference = (row["entry_standard_support"]
                              - row["parent_standard_support"])
                count["peer_support_more"] += difference > 0
                count["peer_support_equal"] += difference == 0
                count["peer_support_less"] += difference < 0
    result = {name: {**dict(sorted(counter.items())),
                     "rooms": len(rooms[name])}
              for name, counter in sorted(groups.items())}
    for name, count in result.items():
        if (count["entry_hands"] != count.get("next_clean_yes", 0)
                + count.get("next_clean_no", 0)
                or count["entry_hands"] != count.get("later_plain_ready", 0)
                + count.get("next_clean_but_not_ready", 0)
                + count.get("next_clean_no", 0)
                or count.get("later_plain_ready", 0) !=
                count.get("ready_next_clean", 0)
                + count.get("ready_second_clean", 0)
                + count.get("ready_third_or_later_clean", 0)):
            raise ValueError("G155 入口、暴露及首次听牌未守恒: " + name)
    return result


def main() -> None:
    """绑定 G69 已核来源；不存在结果时一次性生成逐局与汇总。"""
    if RESULT.exists() or ROWS.exists():
        raise FileExistsError("G155 已有冻结证据，拒绝覆盖")
    source = json.loads(g145.G69_RESULT.read_text(encoding="utf-8"))
    if source["schema"] != "g69-same-room-route-chain/1" or (
            source["window_count"], source["round_count"]) != (36080, 5120):
        raise ValueError("G69 来源范围或版本漂移")
    rounds = {g145.hand_key(row): row for row in g145.lines(g145.G69_ROUNDS)}
    if len(rounds) != 5120:
        raise ValueError("G69 座位单局身份重复或缺失")
    windows: dict[tuple, list[dict]] = defaultdict(list)
    for row in g145.lines(g145.G69_WINDOWS):
        key = g145.hand_key(row)
        if key not in rounds:
            raise ValueError("本人窗口没有 G69 单局")
        windows[key].append(row)
    if sum(map(len, windows.values())) != 36080:
        raise ValueError("G69 逐窗数量漂移")
    selected = [row for hand, round_record in sorted(rounds.items())
                if (row := make_row(hand, windows.get(hand, []), round_record))
                is not None]
    groups = aggregate(selected)
    body = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
                   for row in selected).encode("utf-8")
    OUT.mkdir(parents=True, exist_ok=False)
    ROWS.write_bytes(gzip.compress(body, compresslevel=9, mtime=0))
    result = {
        "schema": "g155-pre-ready-natural-chain/1",
        "exploratory": True,
        "source_sha256": {
            "prereg": sha(PREREG), "script": sha(Path(__file__)),
            "g69_windows": sha(g145.G69_WINDOWS),
            "g69_rounds": sha(g145.G69_ROUNDS),
            "g69_result": sha(g145.G69_RESULT),
        },
        "rows_sha256": sha(ROWS), "selected_hands": len(selected),
        "groups": groups,
        "boundary": "强手/我方不同手牌与对手下的观察性前段行动链；无下一已核正常摸打既可能终局也可能经其他动作族，不能把入口后未到达当首次弃牌效果。公开有效张容量不是墙内概率。",
    }
    RESULT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True,
                                 indent=2) + "\n", encoding="utf-8")
    print(json.dumps({name: item for name, item in groups.items()
                      if name.endswith("/all")}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
