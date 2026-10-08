#!/usr/bin/env python3
"""G86：定位强手已吃碰后的正常摸打分歧与规则一摸路线。"""

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
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, HERE.parents[0] / "baotou-anatomy-20260925")))

import anatomy_lib as anatomy
from extract_room_scores import load_rooms


SHAPE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g61-strong-draw-action-atlas-20260927/shape_profile.json')
G61 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g61-strong-draw-action-atlas-20260927')
ROUTES = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g69-same-room-route-chain-20260928/route_windows.jsonl.gz')
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G86-POST-CLAIM-NORMAL-DRAW-CHAIN-PREREG-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g86-post-claim-normal-draw-chain-20260928/result.json')
EXPECTED_SHAPE = "ca24fd404d1fb9364553891a7910445b13177e35c67573321ecbfd2b4bd9ea04"
EXPECTED_ROUTES = "a34cb15484ed5c42028d45af4462ef65fe01fdb2def5a25a1452703ffe4fe054"


def sha(path: Path) -> str:
    """冻结发现集、规则路线、预登记及本脚本的摘要。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def key(row: dict) -> tuple:
    """强手单位、官方场次、本人正常摸牌序号的唯一键。"""
    return (row["peer"], row["room"], row["game_id"], row["round_no"], row["draw_seq"])


def direction(value: int | None) -> str:
    """返回强手实际弃牌减父代弃牌的事实方向，未知保持未知。"""
    return "unknown" if value is None else "more" if value > 0 else "less" if value < 0 else "same"


def locate_chain(events: list[dict], seat: int, draw_seq: int, action: str) -> dict:
    """只读官方实际行动链；不让真实后继参与当前动作价值计算。"""
    positions = [i for i, event in enumerate(events) if event.get("seq") == draw_seq]
    if len(positions) != 1:
        raise ValueError("目标正常摸牌序号不存在或重复")
    index = positions[0]
    draw = events[index]
    if draw.get("type") != "tile_drawn" or draw.get("seat") != seat:
        raise ValueError("目标不是本人正常摸牌事件")
    if index + 1 >= len(events):
        raise ValueError("目标正常摸牌无后继事件")
    discarded = events[index + 1]
    if (discarded.get("type") != "tile_discarded" or discarded.get("seat") != seat or
            "discard:" + discarded.get("tile", "") != action):
        raise ValueError("G61 已接受本人弃牌与官方紧接事件不符")
    claims = [i for i, event in enumerate(events[:index])
              if event.get("seat") == seat and event.get("type") in ("chi", "peng")]
    if not claims:
        return {"status": "no_prior_own_claim"}
    claim_index = claims[-1]
    own_draws = [event for event in events[claim_index + 1:index + 1]
                 if event.get("type") == "tile_drawn" and event.get("seat") == seat]
    intervening_gangs = [event for event in events[claim_index + 1:index]
                         if event.get("type") == "gang" and event.get("seat") == seat]
    if not own_draws:
        raise ValueError("鸣牌后没有当前本人摸牌")
    next_status = "no_following_resolution"
    next_seq = None
    for event in events[index + 2:]:
        kind = event.get("type")
        if kind == "round_ended":
            data = event.get("data") or {}
            if data.get("draw") is True:
                next_status = "round_draw"
            elif event.get("seat") == seat:
                next_status = "own_win_before_next_action"
            else:
                next_status = "other_win_before_next_action"
            next_seq = event["seq"]
            break
        if event.get("seat") == seat and kind in ("tile_drawn", "chi", "peng", "gang", "hu"):
            next_status = "next_self_" + kind
            next_seq = event["seq"]
            break
    return {"status": "matched", "last_claim_seq": events[claim_index]["seq"],
            "last_claim_kind": events[claim_index]["type"],
            "normal_draw_ordinal_since_claim": len(own_draws),
            "intervening_own_gang_count": len(intervening_gangs),
            "next_status": next_status, "next_seq": next_seq,
            "official_actual_discard_seq": discarded["seq"]}


def main() -> None:
    """冻结逐窗连接及房级计数，任何键冲突都拒绝出结论。"""
    if OUT.exists():
        raise SystemExit("G86 证据已存在，拒绝覆盖")
    if sha(SHAPE) != EXPECTED_SHAPE or sha(ROUTES) != EXPECTED_ROUTES:
        raise ValueError("G61/G69 冻结来源摘要漂移")
    shape = json.loads(SHAPE.read_text(encoding="utf-8"))
    selected = {}
    for row in shape["strict_discard_rows"]:
        if row["delta"]["ordinary_delta"] != 0:
            continue
        selected[key(row)] = row
    if len(selected) != sum(row["delta"]["ordinary_delta"] == 0
                            for row in shape["strict_discard_rows"]):
        raise ValueError("G61 严格同普通型向听窗口键重复")
    windows = {}
    batch = json.loads((_project_file(_PROJECT_ROOT, G61 / "result.json")).read_text(encoding="utf-8"))
    for unit, record in sorted(batch["units"].items()):
        path = _project_file(_PROJECT_ROOT, G61 / "rooms" / (unit.replace("/", "--") + "/windows.json"))
        if sha(path) != record["windows_sha256"]:
            raise ValueError("G61 原始窗口摘要漂移")
        peer, room = unit.split("/", 1)
        for row in json.loads(path.read_text(encoding="utf-8"))["windows"]:
            k = (peer, room, row["game_id"], row["round_no"], row["draw_seq"])
            if k in selected:
                if k in windows:
                    raise ValueError("G61 目标原始窗口重复")
                windows[k] = row
    if set(windows) != set(selected):
        raise ValueError("G61 严格窗口未全部找到原始观察")
    targets = {}
    for k, row in selected.items():
        window = windows[k]
        if (window["actual_action"] != row["strong_action"] or
                window["parent_top_action"] != row["parent_action"]):
            raise ValueError("G61 原始观察与规则画像动作不一致")
        own_melds = window["observation"]["melds"][window["seat"]]
        if any(meld["kind"] in ("chi", "peng") for meld in own_melds):
            targets[k] = (row, window)
    by_peer = Counter(k[0] for k in targets)
    if by_peer != {"xuanwu_2346": 434, "tengshe_0638": 649}:
        raise ValueError("G78 曾吃碰同向听严格分歧母体漂移")
    route_index = {}
    with gzip.open(ROUTES, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row["actor"] != "peer":
                continue
            k = key(row)
            if k in targets:
                if k in route_index:
                    raise ValueError("G69 目标路线窗口重复")
                route_index[k] = row
    if set(route_index) != set(targets):
        raise ValueError("G69 一摸路线与 G61 目标窗口未全量连接")
    by_game_round = defaultdict(list)
    for k in targets:
        by_game_round[(k[2], k[3])].append(k)
    found = set()
    rows = []
    for _, room, _, game_id, doc in load_rooms():
        if not any(k[2] == game_id for k in targets):
            continue
        for round_no, events, _ in anatomy.round_blocks(doc):
            for k in by_game_round.get((game_id, round_no), ()):
                shape_row, window = targets[k]
                if room != k[1]:
                    raise ValueError("官方房号与 G61 单位不符")
                route = route_index[k]
                if (route["seat"] != window["seat"] or
                        route["actual_action"] != shape_row["strong_action"] or
                        route["parent_action"] != shape_row["parent_action"]):
                    raise ValueError("G69 一摸路线动作与 G61 来源不一致")
                chain = locate_chain(events, window["seat"], k[4], shape_row["strong_action"])
                if chain["status"] != "matched":
                    raise ValueError("G78 已吃碰却无官方本人吃碰事件")
                rows.append({"peer": k[0], "room": room, "game_id": game_id,
                             "round_no": round_no, "draw_seq": k[4], "seat": window["seat"],
                             "strong_action": shape_row["strong_action"],
                             "parent_action": shape_row["parent_action"],
                             "parent_score_gap": shape_row["parent_score_gap"],
                             "white_before": shape_row["white_before"],
                             "own_meld_count": shape_row["own_meld_count"],
                             "ordinary_codes_delta": shape_row["delta"]["ordinary_support_codes_delta_same_layer"],
                             "ordinary_capacity_delta": shape_row["delta"]["ordinary_support_capacity_delta_same_layer"],
                             "route_actual": route["actual"],
                             "route_parent": route["parent"],
                             "chain": chain})
                found.add(k)
    if found != set(targets):
        raise ValueError("G86 官方时序目标未全部重建")
    summaries = {}
    for peer in ("xuanwu_2346", "tengshe_0638"):
        per_bucket = defaultdict(Counter)
        room_sets = defaultdict(set)
        for row in rows:
            if row["peer"] != peer:
                continue
            chain = row["chain"]
            ordinal = chain["normal_draw_ordinal_since_claim"]
            bucket = ("gang_intervened" if chain["intervening_own_gang_count"] else
                      "first" if ordinal == 1 else "second" if ordinal == 2 else "third_plus")
            c = per_bucket[bucket]
            c["windows"] += 1
            room_sets[bucket].add(row["room"])
            for name in ("ordinary_codes", "ordinary_capacity"):
                c[name + ":" + direction(row[name + "_delta"])] += 1
            c["next:" + chain["next_status"]] += 1
            left, right = row["route_parent"], row["route_actual"]
            if left is None or right is None:
                c["route_unknown"] += 1
                continue
            for name in ("plain_capacity", "high_capacity"):
                c[name + ":" + direction(right[name] - left[name])] += 1
            if (row["ordinary_codes_delta"] == 0 and row["ordinary_capacity_delta"] == 0):
                c["same_current_ordinary_width"] += 1
                c["same_width_high_route_diff"] += right["high_capacity"] != left["high_capacity"]
                c["same_width_plain_route_diff"] += right["plain_capacity"] != left["plain_capacity"]
        summaries[peer] = {bucket: {"counts": dict(sorted(count.items())),
                                    "rooms": len(room_sets[bucket])}
                           for bucket, count in sorted(per_bucket.items())}
    result = {"schema": "g86-post-claim-normal-draw-chain/1", "exploratory": True,
              "terminal_score_labels_opened": False, "future_action_events_opened": True,
              "source_sha256": {"g61_shape": sha(SHAPE), "g69_routes": sha(ROUTES),
                                "prereg": sha(PREREG), "script": sha(Path(__file__))},
              "summaries": summaries,
              "rows": sorted(rows, key=lambda r: (r["peer"], r["room"], r["game_id"],
                                                  r["round_no"], r["draw_seq"])),
              "boundary": "官方后继只作删失描述；强手动作不是收益标签，一摸条件路线不是兑现概率。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps(summaries, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
