#!/usr/bin/env python3
"""G151：沿已核官方正常摸打链审计首次一白普通听牌后的暴露与截尾。"""

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
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G151-ONE-WHITE-READY-LIFECYCLE-PREREG-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g151-one-white-ready-lifecycle-20260928')
ROWS = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g151-one-white-ready-lifecycle-20260928/rows.jsonl.gz')
RESULT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g151-one-white-ready-lifecycle-20260928/result.json')


def sha(path: Path) -> str:
    """以原始字节绑定上游证据和本量具。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wall_bin(remaining: int) -> str:
    """仅用于查阶段混杂的事前固定墙余分层。"""
    if remaining <= 40:
        return "le40"
    if remaining <= 60:
        return "41to60"
    return "gt60"


def make_row(hand: tuple, windows: list[dict], round_record: dict,
             first_baotou: dict | None) -> dict | None:
    """先按行动前已见牌形选单局，未来窗口和终局只作赛后诊断。"""
    ordered = sorted(windows, key=lambda row: row["draw_seq"])
    if len({row["draw_seq"] for row in ordered}) != len(ordered):
        raise ValueError("同一座位单局本人正常摸打序号重复")
    first = next((row for row in ordered if row["actual"]["plain_capacity"] > 0), None)
    if first is None or first["white_before"] != 1:
        return None
    if first["actual"]["standard_shanten"] != 0:
        raise ValueError("首次普通胡入口但普通型并非零向听")
    following = [row for row in ordered if row["draw_seq"] > first["draw_seq"]]
    next_row = following[0] if following else None
    baotou_seq = None if first_baotou is None else first_baotou["first_draw_seq"]
    if baotou_seq == first["draw_seq"]:
        raise ValueError("首次一白普通胡入口与首次爆头机会同窗，不能算后续形成")
    baotou_later = baotou_seq is not None and baotou_seq > first["draw_seq"]
    later_index = None
    if baotou_later:
        matches = [i for i, row in enumerate(following, 1)
                   if row["draw_seq"] == baotou_seq]
        if len(matches) != 1:
            raise ValueError("首次后续爆头机会不在本人已核正常摸打链")
        later_index = matches[0]
    if (round_record["clean_windows"] != len(ordered)
            or round_record["first_plain_ready"] != first["action_ordinal"]):
        raise ValueError("G69 单局与首次普通胡入口不能对账")
    return {
        "peer": hand[0], "room": hand[1], "game_id": hand[2],
        "round_no": hand[3], "actor": hand[4],
        "first_draw_seq": first["draw_seq"],
        "first_action_ordinal": first["action_ordinal"],
        "first_wall_remaining": first["wall_remaining"],
        "first_wall_bin": wall_bin(first["wall_remaining"]),
        "first_plain_capacity": first["actual"]["plain_capacity"],
        "first_high_capacity": first["actual"]["high_capacity"],
        "next_clean_draw": next_row is not None,
        "next_draw_seq": None if next_row is None else next_row["draw_seq"],
        "next_action_ordinal": None if next_row is None else next_row["action_ordinal"],
        "next_white": None if next_row is None else next_row["white_before"],
        "next_standard_shanten": None if next_row is None else next_row[
            "actual"]["standard_shanten"],
        "next_plain_capacity": None if next_row is None else next_row[
            "actual"]["plain_capacity"],
        "next_high_capacity": None if next_row is None else next_row[
            "actual"]["high_capacity"],
        "first_baotou_after_ready": baotou_later,
        "first_baotou_clean_step": later_index,
        "round_status": round_record["status"],
        "round_fan": round_record["fan"],
        "unknown_windows": round_record["unknown_windows"],
    }


def aggregate(rows: list[dict]) -> tuple[dict, dict]:
    """分强手/我方和入口阶段统计；只报告观察量，不估策略效应。"""
    groups: dict[str, Counter] = defaultdict(Counter)
    rooms: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        for suffix in ("all", "wall_" + row["first_wall_bin"]):
            name = f"{row['peer']}/{row['actor']}/{suffix}"
            c = groups[name]
            rooms[name].add(row["room"])
            c["first_ready_one_white_hands"] += 1
            c["first_plain_capacity_sum"] += row["first_plain_capacity"]
            c["first_action_ordinal_sum"] += row["first_action_ordinal"]
            c["next_clean_draw_yes"] += row["next_clean_draw"]
            c["next_clean_draw_no"] += not row["next_clean_draw"]
            c["first_baotou_after_ready"] += row["first_baotou_after_ready"]
            if row["first_baotou_after_ready"]:
                step = row["first_baotou_clean_step"]
                c["first_baotou_next_clean_draw"] += step == 1
                c["first_baotou_second_clean_draw"] += step == 2
                c["first_baotou_third_or_later_clean_draw"] += step >= 3
            c["status_" + row["round_status"]] += 1
            if row["next_clean_draw"]:
                c["next_white_still_one"] += row["next_white"] == 1
                c["next_standard_ready"] += row["next_standard_shanten"] == 0
                c["next_plain_ready"] += row["next_plain_capacity"] > 0
                c["next_white_one_and_standard_ready"] += (
                    row["next_white"] == 1 and row["next_standard_shanten"] == 0)
                c["next_white_one_and_plain_ready"] += (
                    row["next_white"] == 1 and row["next_plain_capacity"] > 0)
            else:
                c["no_next_status_" + row["round_status"]] += 1
                c["no_next_unknown_window_positive"] += row["unknown_windows"] > 0
    return ({name: {**dict(sorted(counter.items())), "rooms": len(rooms[name])}
             for name, counter in sorted(groups.items())},
            {name: len(value) for name, value in sorted(rooms.items())})


def main() -> None:
    """绑定 G69/G138/G145，生成不可覆盖的逐局与聚合证据。"""
    if RESULT.exists() or ROWS.exists():
        raise FileExistsError("G151 已有冻结证据，拒绝覆盖")
    g69 = json.loads(g145.G69_RESULT.read_text(encoding="utf-8"))
    g138 = json.loads(g145.G138.read_text(encoding="utf-8"))
    g145_doc = json.loads(g145.OUT.read_text(encoding="utf-8"))
    if (g69["round_count"] != 5120 or g69["window_count"] != 36080
            or g138["actor_hands"] != 5120
            or g138["normal_draw_discard_windows"] != 36080):
        raise ValueError("G69/G138 冻结母体数量漂移")
    by_hand: dict[tuple, list[dict]] = defaultdict(list)
    for row in g145.lines(g145.G69_WINDOWS):
        by_hand[g145.hand_key(row)].append(row)
    rounds = {g145.hand_key(row): row for row in g145.lines(g145.G69_ROUNDS)}
    first_baotou = {g145.hand_key(row): row for row in
                     g138["first_plain_baotou_rows"]}
    if (len(rounds) != 5120 or len(first_baotou) != 239
            or sum(map(len, by_hand.values())) != 36080):
        raise ValueError("G69/G138 逐局键或行动窗数量漂移")
    rows = []
    for hand, round_record in sorted(rounds.items()):
        row = make_row(hand, by_hand.get(hand, []), round_record,
                       first_baotou.get(hand))
        if row is not None:
            rows.append(row)
    groups, room_count = aggregate(rows)
    if len(rows) != 1372:
        raise ValueError("首次一白普通胡入口与 G147 数量不同")
    for peer in g145.PEERS:
        for actor in ("peer", "us"):
            name = f"{peer}/{actor}/all"
            old = g145_doc["peers"][peer]["actors"][actor]
            if (groups[name]["first_ready_one_white_hands"] != old[
                    "first_plain_ready_by_white"]["1"]
                    or groups[name]["first_baotou_after_ready"] != old[
                        "baotou_after_first_ready_by_white"]["1"]):
                raise ValueError("G151 一白入口或后续首次机会与 G145 不一致")
            if groups[name]["next_clean_draw_yes"] + groups[name][
                    "next_clean_draw_no"] != groups[name]["first_ready_one_white_hands"]:
                raise ValueError("下一已核摸打暴露分母不守恒")
    body = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
                   for row in rows).encode("utf-8")
    OUT.mkdir(parents=True, exist_ok=False)
    ROWS.write_bytes(gzip.compress(body, compresslevel=9, mtime=0))
    result = {
        "schema": "g151-one-white-ready-lifecycle/1",
        "exploratory": True,
        "source_sha256": {
            "prereg": sha(PREREG), "script": sha(Path(__file__)),
            "g69_windows": sha(g145.G69_WINDOWS),
            "g69_rounds": sha(g145.G69_ROUNDS),
            "g69_result": sha(g145.G69_RESULT),
            "g138": sha(g145.G138), "g145": sha(g145.OUT),
        },
        "rows_sha256": sha(ROWS), "selected_hands": len(rows),
        "groups": groups, "room_count": room_count,
        "boundary": "父代/强手历史行动链的赛后观察；下一窗缺失或爆头未出现不能归咎首次弃牌。公开容量是物理上界，不是摸墙概率；既有房不可作候选收益确认。",
    }
    RESULT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True,
                                 indent=2) + "\n", encoding="utf-8")
    print(json.dumps({name: item for name, item in groups.items()
                      if name.endswith("/all")}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
