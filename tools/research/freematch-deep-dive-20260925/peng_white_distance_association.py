#!/usr/bin/env python3
"""只读审计：已见白板与供牌座距在 G273 响应窗中的行为关联。"""

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
from collections import Counter
import hashlib
import json
from pathlib import Path

from extract_room_scores import load_rooms
from g273_exposed_response_support import (
    SOURCE,
    digest,
    read_rows,
    stable_key_digest,
)


HERE = Path(__file__).resolve().parent
KEY_FIELDS = ("peer", "room", "game_id", "round_no", "discard_seq", "seat", "phase")
EXPECTED_GROUPS = {
    ("xuanwu_2346", "claim"): 27,
    ("tengshe_0638", "claim"): 25,
    ("xuanwu_2346", "pass"): 366,
}


def window_key(row: dict) -> tuple:
    """保留座位和响应阶段，避免同一物理弃牌的碰／吃窗相互覆盖。"""
    return tuple(row[field] for field in KEY_FIELDS)


def trigger_key(row: dict) -> tuple:
    """连接官方触发弃牌的单局、局号和事件序号。"""
    return row["game_id"], row["round_no"], row["discard_seq"]


def selected_rows() -> tuple[list[dict], list[dict]]:
    """继承 G273 冻结的正例及玄武严格主动过牌口径。"""
    rows = read_rows(SOURCE)
    positive = [row for row in rows if row["actor"] == "peer" and
                row["actual"] == "claim" and row["parent_key"] == "pass" and
                row["r6_key"] == "pass" and row["own_meld_count"] > 0]
    strict_pass = [row for row in rows if row["actor"] == "peer" and
                   row["peer"] == "xuanwu_2346" and row["actual"] == "pass" and
                   row["parent_key"] == "pass" and row["r6_key"] == "pass" and
                   row["own_meld_count"] > 0]
    actual = Counter((row["peer"], row["actual"]) for row in positive + strict_pass)
    if actual != EXPECTED_GROUPS:
        raise ValueError(f"G273 锁定的 52／366 支持域漂移：{actual}")
    target = positive + strict_pass
    if len({window_key(row) for row in target}) != len(target):
        raise ValueError("响应窗身份重复；不能只按物理弃牌去重")
    for row in target:
        if (type(row["white_count"]) is not int or
                not 0 <= row["white_count"] <= 4):
            raise ValueError(f"行动前手留白板数无效：{window_key(row)}")
        if row["actual"] == "claim" and not row["accepted_key"].startswith(
                "chi:" if row["phase"] == "response_chi" else "peng:"):
            raise ValueError(f"已接受吃碰动作与阶段不符：{window_key(row)}")
    return positive, strict_pass


def discarders(target: list[dict]) -> dict[tuple, int]:
    """只投影每窗已发生的触发弃牌事件；忽略牌谱后继与结算。"""
    wanted = {trigger_key(row) for row in target}
    wanted_games = {key[0] for key in wanted}
    found: dict[tuple, int] = {}
    rooms_by_game = {row["game_id"]: row["room"] for row in target}
    for _, room, _, game_id, document in load_rooms():
        if game_id not in wanted_games:
            continue
        if room != rooms_by_game[game_id]:
            raise ValueError(f"官方房与 G76 行不符：{game_id}")
        for block in document.get("blocks") or ():
            round_no = block.get("round_no")
            for event in block.get("events") or ():
                key = game_id, round_no, event.get("seq")
                if key not in wanted:
                    continue
                seat = event.get("seat")
                if event.get("type") != "tile_discarded" or type(seat) is not int or not 0 <= seat < 4:
                    raise ValueError(f"触发序号不是有效的官方弃牌：{key}")
                if key in found and found[key] != seat:
                    raise ValueError(f"同一官方弃牌的供牌座位冲突：{key}")
                found[key] = seat
    if set(found) != wanted:
        raise ValueError(f"有 {len(wanted - set(found))} 个 G76 触发弃牌无法连接")
    return found


def summarize(rows: list[dict], found: dict[tuple, int]) -> dict:
    """按窗口及不同房同时计数；座距只用本座与供牌座位。"""
    distance_counts: Counter[int] = Counter()
    phase_counts: Counter[str] = Counter()
    matched = []
    for row in rows:
        distance = (row["seat"] - found[trigger_key(row)]) % 4
        if distance not in (1, 2, 3) or (row["phase"] == "response_chi" and distance != 1):
            raise ValueError(f"座位与合法响应阶段冲突：{window_key(row)}，距离 {distance}")
        distance_counts[distance] += 1
        phase_counts[row["phase"]] += 1
        if row["phase"] == "response_peng" and row["white_count"] >= 1 and distance >= 2:
            matched.append(row)
    return {
        "windows": len(rows),
        "rooms": len({row["room"] for row in rows}),
        "games": len({row["game_id"] for row in rows}),
        "by_phase": dict(sorted(phase_counts.items())),
        "by_clockwise_discarder_to_actor_distance": {
            str(i): distance_counts[i] for i in (1, 2, 3)
        },
        "matched_windows": len(matched),
        "matched_rooms": len({row["room"] for row in matched}),
        "matched_games": len({row["game_id"] for row in matched}),
        "all_window_keys_sha256": stable_key_digest(rows),
        "matched_window_keys_sha256": stable_key_digest(matched),
    }


def main() -> None:
    """生成可审计 JSON；不修改生产规则、策略或原始牌谱。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path,
                        help="新 JSON 文件路径；拒绝覆盖现有文件")
    args = parser.parse_args()

    positive, strict_pass = selected_rows()
    target = positive + strict_pass
    found = discarders(target)
    by_peer = {
        "xuanwu_accepted_claim": summarize(
            [row for row in positive if row["peer"] == "xuanwu_2346"], found),
        "tengshe_accepted_claim": summarize(
            [row for row in positive if row["peer"] == "tengshe_0638"], found),
        "xuanwu_strict_pass": summarize(strict_pass, found),
        "xuanwu_strict_pass_same_peng_phase": summarize(
            [row for row in strict_pass if row["phase"] == "response_peng"], found),
    }
    expected = (13, 9, 4, 4)
    actual = tuple(group["matched_windows"] for group in by_peer.values())
    if actual != expected or by_peer["xuanwu_strict_pass_same_peng_phase"]["windows"] != 53:
        raise ValueError(f"行为关联复算漂移：{actual}；先检查来源与口径")

    trigger_projection = sorted((game_id, round_no, seq, seat)
                                for (game_id, round_no, seq), seat in found.items())
    trigger_sha = hashlib.sha256(json.dumps(
        trigger_projection, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    result = {
        "schema": "peng-white-distance-association/1",
        "date": "2026-09-29",
        "status": "post_hoc_exploratory_behavior_association",
        "source": {
            "g76_rows": str(SOURCE.relative_to(HERE)),
            "g76_rows_sha256": digest(SOURCE),
            "g273_selection_helper_sha256": digest(_project_file(_PROJECT_ROOT, HERE / "g273_exposed_response_support.py")),
            "official_events_loader_sha256": digest(_project_file(_PROJECT_ROOT, HERE / "extract_room_scores.py")),
            "script_sha256": digest(Path(__file__)),
            "official_trigger_event_projection_sha256": trigger_sha,
            "target_response_windows": len(target),
            "distinct_trigger_discards": len(found),
        },
        "selection": {
            "positive": "actor=peer, actual=claim, parent_key=pass, r6_key=pass, own_meld_count>0",
            "strict_negative_control": "peer=xuanwu_2346, actor=peer, actual=pass, parent_key=pass, r6_key=pass, own_meld_count>0",
            "same_phase_control": "strict_negative_control 且 phase=response_peng",
            "association_predicate": "phase=response_peng 且 white_count>=1 且 (actor_seat-discarder_seat)%4>=2",
            "clockwise_distance": "1=供牌者下家；2=隔一席；3=供牌者上家，按官方四座 0..3 计算",
        },
        "groups": by_peer,
        "interpretation": (
            "这是在已看 G76 强手房中事后筛出的行动前行为关联，不是预登记判据、第二次本人机会路线、"
            "完整桌收益或 G273 任何门禁通过。13/27 与 9/25 含吃窗分母；玄武严格负控为 4/366，"
            "同碰窗负控为 4/53，须报告阶段混杂。腾蛇超时未当主动过牌。G76 已确认响应开启与规则合法性在此继承，"
            "未重新证明；本脚本只从官方牌谱提取触发弃牌座位，不用其后摸牌、他家暗手、结算或终局成绩。"
            "牌谱按 extract_room_scores.load_rooms 的每 game_id 最新本地下载去重；来源更新时应核触发事件摘要。"
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"output": str(args.output), "matched_windows": actual,
                      "same_peng_control_windows": 53}, ensure_ascii=False))


if __name__ == "__main__":
    main()
