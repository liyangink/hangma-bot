#!/usr/bin/env python3
"""G276：只读原始官方 /state，核对 G273 强手吃碰前后供牌者牌河。"""

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
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path


ROOT = _PROJECT_ROOT
HERE = Path(__file__).resolve().parent
G76 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g76-confirmed-response-atlas-20260928/rows.jsonl.gz')
G76_SHA256 = "2a26d239e79ce863311b4be2681a86a9d7d94b50648ab4f4a5355f6d3cd08fc6"
G61 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g61-strong-draw-action-atlas-20260927/manifest.json')
LEDGER = _project_file(_PROJECT_ROOT, ROOT / "runs/auto-match-watchdog/auto-match-watchdog-state.json")
DEFAULT_OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g276-official-river-snapshot-calibration-20260929')
ME = "u_13495c3d79c8"
KEY_FIELDS = ("peer", "room", "game_id", "round_no", "discard_seq", "seat", "phase")


def sha(path: Path) -> str:
    """对原始文件字节计算摘要；摘要是来源身份，不参与动作决策。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict:
    """只读取本地 JSON；本量具无网络和认证配置入口。"""
    return json.loads(path.read_text(encoding="utf-8"))


def target_rows() -> list[dict]:
    """锁定 G76 行动前 52 个真实已接受鸣牌，不读取 G275 后继事实。"""
    if sha(G76) != G76_SHA256:
        raise ValueError("G76 压缩行摘要漂移")
    with gzip.open(G76, "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    selected = [row for row in rows if row["actor"] == "peer" and
                row["actual"] == "claim" and row["parent_key"] == "pass" and
                row["r6_key"] == "pass" and row["own_meld_count"] > 0]
    if (len(selected) != 52 or Counter(row["peer"] for row in selected) !=
            {"xuanwu_2346": 27, "tengshe_0638": 25}):
        raise ValueError("G273 冻结目标集合漂移")
    selected.sort(key=lambda row: tuple(row[field] for field in KEY_FIELDS))
    if len({tuple(row[field] for field in KEY_FIELDS) for row in selected}) != 52:
        raise ValueError("G76 窗口键重复")
    return selected


def source_index(download_dir: Path, game_ids: set[str]) -> dict[str, tuple[Path, str, dict]]:
    """用官方下载 source.json 定位牌谱，并校验原文摘要与重复副本。"""
    candidates: dict[str, list[tuple[Path, str, dict]]] = defaultdict(list)
    for source_path in sorted((download_dir / "official").rglob("source.json")):
        source = read_json(source_path)
        game_id = source.get("game_id")
        if game_id not in game_ids:
            continue
        events_path = source_path.with_name("events.json")
        if not events_path.is_file():
            continue
        digest = sha(events_path)
        if digest != source.get("original_sha256"):
            raise ValueError(f"官方牌谱原文摘要不符：{game_id}")
        candidates[game_id].append((events_path, digest, {
            "source_path": str(source_path.relative_to(ROOT)),
            "source_sha256": sha(source_path),
            "guide_version": source.get("guide_version"),
            "captured_at": source.get("captured_at"),
        }))
    selected = {}
    for game_id, choices in candidates.items():
        if len({digest for _, digest, _ in choices}) != 1:
            raise ValueError(f"同桌官方下载牌谱冲突：{game_id}")
        selected[game_id] = choices[0]
    return selected


def claim_anchor(doc: dict, row: dict, peer_user_id: str) -> dict:
    """只用官方事件确定供牌、鸣牌序号及后验对账边界，不投影暗手。"""
    seats = [seat.get("user_id") for seat in doc.get("seats") or []]
    if (doc.get("game_id") != row["game_id"] or doc.get("room_id") != row["room"] or
            len(seats) != 4 or seats.count(ME) != 1 or
            seats[row["seat"]] != peer_user_id):
        raise ValueError("官方场次、座位或强手身份与 G76 不符")
    events = sorted((event for block in doc.get("blocks") or []
                     if block.get("round_no") == row["round_no"]
                     for event in block.get("events") or []), key=lambda event: event["seq"])
    discard_matches = [index for index, event in enumerate(events)
                       if event["seq"] == row["discard_seq"]]
    if len(discard_matches) != 1:
        raise ValueError("目标弃牌官方序号非唯一")
    index = discard_matches[0]
    discard = events[index]
    if discard["type"] != "tile_discarded" or discard["seat"] == row["seat"]:
        raise ValueError("目标序号不是他座供牌")
    claim = next((event for event in events[index + 1:]
                  if event["type"] not in ("pass", "timeout")), None)
    if (claim is None or claim.get("type") not in ("chi", "peng") or
            claim.get("seat") != row["seat"] or claim.get("tile") != discard["tile"] or
            claim["seq"] <= discard["seq"]):
        raise ValueError("官方紧接鸣牌与 G76 阶段身份不符")
    if claim["type"] == "chi":
        tiles = (claim.get("data") or {}).get("tiles") or []
        accepted = row["accepted_key"].removeprefix("chi:").split(",")
        if (not row["accepted_key"].startswith("chi:") or
                Counter(tiles) != Counter(accepted) or discard["tile"] not in tiles):
            raise ValueError("官方吃牌组合与 G76 已接受动作键不符")
    elif row["accepted_key"] != "peng:" + discard["tile"]:
        raise ValueError("官方碰牌与 G76 已接受动作键不符")
    if row["phase"] != "response_" + claim["type"]:
        raise ValueError("官方鸣牌种类与 G76 响应阶段不符")
    later_discard = next((event["seq"] for event in events if event["seq"] > claim["seq"]
                          and event["type"] == "tile_discarded" and
                          event["seat"] == discard["seat"]), None)
    return {"discard_seq": discard["seq"], "claim_seq": claim["seq"],
            "discarder_seat": discard["seat"], "claimant_seat": claim["seat"],
            "tile": discard["tile"], "kind": claim["type"],
            "chi_tiles": (claim.get("data") or {}).get("tiles") if claim["type"] == "chi" else None,
            "next_discard_by_source_seq": later_discard,
            "my_seat": seats.index(ME), "round_last_seq": events[-1]["seq"]}


def raw_states(paths: list[Path], anchors: list[dict]) -> tuple[dict[int, dict], dict]:
    """顺序流读原始 /state；仅留目标序号附近公开牌河／副露与定位元数据。"""
    found = {index: {"pre": [], "post": [], "bad_identity": Counter(),
                     "raw_after_boundary": 0} for index in range(len(anchors))}
    hashes = {}
    skipped = Counter()
    state_count = 0
    for path in paths:
        hashes[str(path.relative_to(ROOT))] = sha(path)
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for line_no, line in enumerate(stream, start=1):
                record = json.loads(line)
                payload = record.get("payload") or {}
                if payload.get("source") != "state_response":
                    continue
                if payload.get("endpoint") != f"GET /api/games/{anchors[0]['game_id']}/state":
                    skipped["wrong_endpoint"] += 1
                    continue
                if payload.get("http_status") != 200:
                    skipped["non_200_http_status"] += 1
                    continue
                raw = payload.get("raw")
                if isinstance(raw, str):
                    try:
                        raw = json.loads(raw)
                    except ValueError:
                        skipped["invalid_json"] += 1
                        continue
                if not isinstance(raw, dict) or not isinstance(raw.get("snapshot"), dict):
                    skipped["no_snapshot_in_response"] += 1
                    continue
                if raw.get("seq") != payload.get("seq_observed"):
                    skipped["seq_observed_mismatch"] += 1
                    continue
                state_count += 1
                snapshot = raw["snapshot"]
                seq = raw.get("seq")
                for index, anchor in enumerate(anchors):
                    if not isinstance(seq, int) or seq < anchor["discard_seq"]:
                        continue
                    if seq < anchor["claim_seq"]:
                        side = "pre"
                    elif (seq < (anchor["next_discard_by_source_seq"] or
                                 anchor["round_last_seq"] + 1)):
                        side = "post"
                    else:
                        found[index]["raw_after_boundary"] += 1
                        continue
                    if (snapshot.get("game_id") != anchor["game_id"] or
                            snapshot.get("round_no") != anchor["round_no"] or
                            snapshot.get("seat") != anchor["my_seat"]):
                        found[index]["bad_identity"][side] += 1
                        continue
                    discards = snapshot.get("discards")
                    melds = snapshot.get("melds")
                    if (not isinstance(discards, list) or len(discards) != 4 or
                            not isinstance(melds, list) or len(melds) != 4):
                        found[index]["bad_identity"]["invalid_public_shape"] += 1
                        continue
                    found[index][side].append({
                        "path": str(path.relative_to(ROOT)), "line": line_no,
                        "seq": seq, "phase": snapshot.get("phase"),
                        "last_discard": snapshot.get("last_discard"),
                        "turn": snapshot.get("turn"), "waited_seat": snapshot.get("waited_seat"),
                        "seat": snapshot.get("seat"), "round_no": snapshot.get("round_no"),
                        "source_river": discards[anchor["discarder_seat"]],
                        "claimant_melds": melds[anchor["claimant_seat"]],
                    })
    return found, {"raw_file_sha256": hashes, "raw_snapshot_count": state_count,
                   "skipped_state_response_counts": dict(skipped)}


def claim_meld_count(snapshot: dict, anchor: dict) -> int:
    """按种类和物理牌多重集计数，允许此前已有同形吃牌。"""
    count = 0
    for meld in snapshot["claimant_melds"]:
        if meld.get("kind") != anchor["kind"]:
            continue
        expected = ([anchor["tile"]] * 3 if anchor["kind"] == "peng"
                    else anchor["chi_tiles"])
        if Counter(meld.get("tiles") or []) == Counter(expected):
            count += 1
    return count


def calibrate(found: dict, anchor: dict) -> dict:
    """只由同局同座的原始快照比较供牌者末张；后态仅用于事后规则口径核验。"""
    pre = [snapshot for snapshot in found["pre"]
           if snapshot["last_discard"] == anchor["tile"] and
           snapshot["turn"] == anchor["discarder_seat"] and
           snapshot["source_river"] and snapshot["source_river"][-1] == anchor["tile"]]
    prior_meld_count = max((claim_meld_count(snapshot, anchor) for snapshot in pre),
                           default=0)
    post = [snapshot for snapshot in found["post"]
            if claim_meld_count(snapshot, anchor) > prior_meld_count]
    result = {"status": "unknown", "reason": None,
              "raw_pre_candidate_count": len(found["pre"]),
              "raw_post_candidate_count": len(found["post"]),
              "matched_pre_count": len(pre), "matched_post_meld_count": len(post),
              "bad_identity": dict(found["bad_identity"]),
              "raw_after_boundary_count": found["raw_after_boundary"],
              "before": None, "after": None, "snapshot_pair_kind": None}
    if not pre:
        result["reason"] = ("pre_snapshot_no_claimed_tile_or_identity" if found["pre"]
                            else "pre_snapshot_absent")
        return result
    if not post:
        result["reason"] = ("post_snapshot_no_claim_meld" if found["post"]
                            else "post_snapshot_absent_before_source_next_discard")
        return result
    pre_rivers = {tuple(snapshot["source_river"]) for snapshot in pre}
    post_rivers = {tuple(snapshot["source_river"]) for snapshot in post}
    if len(pre_rivers) != 1 or len(post_rivers) != 1:
        result["reason"] = "multiple_public_river_versions_within_pair_window"
        return result
    before = max(pre, key=lambda snapshot: (snapshot["seq"], snapshot["path"], snapshot["line"]))
    after = min(post, key=lambda snapshot: (snapshot["seq"], snapshot["path"], snapshot["line"]))
    result["before"] = {key: value for key, value in before.items() if key != "claimant_melds"}
    result["after"] = {key: value for key, value in after.items() if key != "claimant_melds"}
    result["snapshot_pair_kind"] = ("exact_claim_seq" if after["seq"] == anchor["claim_seq"]
                                    else "bounded_later_state")
    left = before["source_river"]
    right = after["source_river"]
    if right == left[:-1]:
        result["status"] = "removed"
    elif right == left:
        result["status"] = "retained"
    else:
        result["reason"] = "river_difference_not_explained_by_one_claimed_tile"
    return result


def main() -> None:
    """输出逐窗证据和房级覆盖；缺快照保持 unknown，不借 C31 填值。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("G276 输出目录已存在，拒绝覆盖")
    targets = target_rows()
    ledger = read_json(LEDGER)
    rooms = {item["room_id"]: item for item in ledger.get("rooms") or []}
    units = {(item["room"], item["peer"]): item["target_user_id"]
             for item in read_json(G61)["units"]}
    grouped = defaultdict(list)
    for row in targets:
        grouped[row["game_id"]].append(row)
    download_dirs = {_project_file(_PROJECT_ROOT, ROOT / rooms[row["room"]]["download_dir"]) for row in targets
                     if row["room"] in rooms}
    indices = {directory: source_index(directory, set(grouped)) for directory in download_dirs}
    out_rows = []
    official_hashes = {}
    official_source_metadata = {}
    raw_hashes = {}
    raw_snapshot_count = 0
    skipped_state_responses = Counter()
    for game_id, rows in sorted(grouped.items()):
        room = rooms.get(rows[0]["room"])
        if room is None:
            for row in rows:
                out_rows.append({"window_key": {field: row[field] for field in KEY_FIELDS},
                                 "status": "unknown", "reason": "audit_room_absent"})
            continue
        game_entries = [game for game in room.get("games") or []
                        if game.get("game_id") == game_id]
        if len(game_entries) != 1:
            raise ValueError("看护账本官方场次身份缺失或重复：" + game_id)
        source = indices[_project_file(_PROJECT_ROOT, ROOT / room["download_dir"])].get(game_id)
        if source is None:
            for row in rows:
                out_rows.append({"window_key": {field: row[field] for field in KEY_FIELDS},
                                 "status": "unknown", "reason": "official_event_archive_absent"})
            continue
        official_path, official_digest, source_meta = source
        official_hashes[str(official_path.relative_to(ROOT))] = official_digest
        official_source_metadata[str(official_path.relative_to(ROOT))] = source_meta
        doc = read_json(official_path)
        anchors = []
        for row in rows:
            peer_user_id = units.get((row["room"], row["peer"]))
            if peer_user_id is None:
                raise ValueError("G61 房内强手身份缺失")
            anchor = claim_anchor(doc, row, peer_user_id)
            if game_entries[0]["seat"] != anchor["my_seat"]:
                raise ValueError("账本与官方牌谱我方座位不符")
            anchor.update({"game_id": game_id, "round_no": row["round_no"]})
            anchors.append(anchor)
        raw_dir = _project_file(_PROJECT_ROOT, ROOT / room["audit_dir"] / "participants" / ME / "raw")
        paths = sorted(raw_dir.glob(game_id + ".*.jsonl.gz"))
        if not paths:
            for row, anchor in zip(rows, anchors):
                out_rows.append({"window_key": {field: row[field] for field in KEY_FIELDS},
                                 "official_anchor": anchor, "status": "unknown",
                                 "reason": "raw_state_archive_absent"})
            continue
        found, source_stats = raw_states(paths, anchors)
        raw_hashes.update(source_stats["raw_file_sha256"])
        raw_snapshot_count += source_stats["raw_snapshot_count"]
        skipped_state_responses.update(source_stats["skipped_state_response_counts"])
        for index, (row, anchor) in enumerate(zip(rows, anchors)):
            out_rows.append({"window_key": {field: row[field] for field in KEY_FIELDS},
                             "accepted_key": row["accepted_key"],
                             "official_anchor": anchor, **calibrate(found[index], anchor)})
    out_rows.sort(key=lambda item: tuple(item["window_key"][field] for field in KEY_FIELDS))
    if len(out_rows) != 52:
        raise ValueError("G276 输出窗口数漂移")
    summary = {
        "schema": "g276-official-river-snapshot-calibration-v1",
        "source": "original GET /state audit raw payloads plus official postgame event identities",
        "validation_only": "Post-claim snapshots calibrate public river handling retrospectively; never an action-before feature.",
        "target_windows": len(out_rows),
        "distinct_rooms": len({row["window_key"]["room"] for row in out_rows}),
        "distinct_games": len({row["window_key"]["game_id"] for row in out_rows}),
        "status_counts": dict(Counter(row["status"] for row in out_rows)),
        "unknown_reason_counts": dict(Counter(row.get("reason") for row in out_rows
                                              if row["status"] == "unknown")),
        "pair_kind_counts": dict(Counter(row.get("snapshot_pair_kind") for row in out_rows
                                         if row["status"] != "unknown")),
        "by_peer_status": {peer: dict(Counter(row["status"] for row in out_rows
                                      if row["window_key"]["peer"] == peer))
                           for peer in ("xuanwu_2346", "tengshe_0638")},
        "raw_snapshot_count_in_selected_games": raw_snapshot_count,
        "skipped_state_response_counts_in_selected_games": dict(skipped_state_responses),
        "source_sha256": {"g76_rows_gzip": sha(G76), "g61_manifest": sha(G61),
                          "watchdog_ledger": sha(LEDGER),
                          "official_events": official_hashes,
                          "raw_audit_gzip": raw_hashes},
        "official_source_metadata": official_source_metadata,
    }
    args.output.mkdir(parents=True)
    (args.output / "rows.json").write_text(json.dumps(out_rows, ensure_ascii=False,
                                                       indent=2, sort_keys=True) + "\n",
                                           encoding="utf-8")
    (args.output / "result.json").write_text(json.dumps(summary, ensure_ascii=False,
                                                         indent=2, sort_keys=True) + "\n",
                                             encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("target_windows", "distinct_rooms",
                                                "status_counts", "unknown_reason_counts",
                                                "pair_kind_counts", "by_peer_status")},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
