#!/usr/bin/env python3
"""G76：只在官方确认开启的响应阶段重判强手与 R18 v2 的同观察动作。"""

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
import c31_action_layer_gap as c31
import c32_cards as c32
import g59_freematch_white_value_audit as g59
from extract_room_scores import load_rooms


G61 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g61-strong-draw-action-atlas-20260927/manifest.json')
G69 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g69-same-room-route-chain-20260928/manifest.json')
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G76-CONFIRMED-RESPONSE-ATLAS-PREREG-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g76-confirmed-response-atlas-20260928')
ORDER = {code: index for index, code in enumerate(c31.TILE_ORDER)}
CLAIMS = {"peng": "response_peng", "chi": "response_chi", "gang": "response_peng"}


def sha(path: Path) -> str:
    """将母体、源码和结果绑定，防止后来无意替换输入。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def official_claim(events: list[dict], discard_seq: int) -> dict | None:
    """只读本次弃牌后紧随的官方响应段，不把后继摸牌当成本次动作。"""
    indices = [i for i, event in enumerate(events) if event.get("seq") == discard_seq]
    if len(indices) != 1 or events[indices[0]].get("type") != "tile_discarded":
        raise ValueError("弃牌官方序号非唯一")
    for event in events[indices[0] + 1:]:
        kind = event.get("type")
        if kind in ("pass", "timeout"):
            continue
        if kind in ("peng", "chi") or (kind == "gang" and
                (event.get("data") or {}).get("kind") == "ming"):
            return event
        return None
    return None


def action_key(event: dict) -> str:
    """把官方已接受吃碰动作映射到生产动作键，仅供合法性对账。"""
    kind = event["type"]
    if kind == "chi":
        codes = (event.get("data") or {}).get("tiles") or ()
        if len(codes) != 3 or event.get("tile") not in codes:
            raise ValueError("官方吃牌组合不完整")
        return "chi:" + ",".join(sorted(codes, key=ORDER.__getitem__))
    if kind == "peng":
        return "peng:" + event["tile"]
    if kind == "gang" and (event.get("data") or {}).get("kind") == "ming":
        return "gang:exposed:" + event["tile"]
    raise ValueError("官方响应动作种类不符")


def confirmed_phases(snap: dict, seat: int, claim: dict | None) -> tuple[dict[str, str], int]:
    """阶段以官方本人响应和窗口字段确认；无字段单条过牌双阶段歧义排除。"""
    discarder, tile, owner = snap["discarder"], snap["tile"], snap["owner"]
    eligible = []
    if seat in c31._peng_members(discarder, tile, owner):
        eligible.append("response_peng")
    if seat in c31._chi_members(discarder, tile, owner):
        eligible.append("response_chi")
    responses = [(kind, window) for responder, kind, window in snap["responses"]
                 if responder == seat]
    actual = claim if claim is not None and claim.get("seat") == seat else None
    mapped: dict[str, str] = {}
    ambiguous = 0
    for index, (kind, window) in enumerate(responses):
        if kind not in ("pass", "timeout"):
            raise ValueError("官方响应事件不是过牌或超时")
        if kind == "timeout" and window in ("peng", "chi"):
            phase = "response_" + window
        elif len(eligible) == 1:
            phase = eligible[0]
        elif len(responses) == 2 and eligible == ["response_peng", "response_chi"]:
            phase = eligible[index]
        elif (len(responses) == 1 and index == 0 and actual is not None and
              actual["type"] == "chi" and "response_peng" in eligible):
            phase = "response_peng"
        else:
            ambiguous += 1
            continue
        if phase not in eligible or phase in mapped:
            raise ValueError("官方响应阶段与规则成员或时序不一致")
        mapped[phase] = kind
    if actual is not None:
        phase = CLAIMS[actual["type"]]
        if phase not in eligible or phase in mapped:
            raise ValueError("官方鸣牌阶段与规则成员或已有本人响应冲突")
        mapped[phase] = "claim"
    return mapped, ambiguous


def main() -> None:
    if OUT.exists():
        raise SystemExit("G76 证据目录已存在，拒绝覆盖")
    parent = c31.load_parent()
    r6, _ = c32.load_scorer(c32.R6_FILE)
    if r6 is None:
        raise ValueError("C39 旧固定鸣牌奖金源码不可装配")
    g61, g69 = json.loads(G61.read_text()), json.loads(G69.read_text())
    room_units = defaultdict(list)
    for unit in g61["units"]:
        room_units[unit["room"]].append((unit["peer"], unit["target_user_id"]))
    if set(room_units) != set(g69["rooms"]) or len(room_units) != 31 or len(g61["units"]) != 32:
        raise ValueError("G61/G69 强手同房母体漂移")
    expected_games = {(room, game) for room, games in g69["games"].items() for game in games}
    if len(expected_games) != 310:
        raise ValueError("G69 官方完整桌数漂移")
    found_games = set()
    official_digests = []
    rows = []
    by_unit: dict[tuple[str, str, str], Counter] = defaultdict(Counter)
    for _, room, _, game_id, doc in load_rooms():
        if (room, game_id) not in expected_games:
            continue
        if (room, game_id) in found_games:
            raise ValueError("官方桌重复")
        found_games.add((room, game_id))
        official_digests.append((game_id, hashlib.sha256(json.dumps(
            doc, ensure_ascii=False, sort_keys=True).encode()).hexdigest()))
        users = [seat.get("user_id") for seat in doc.get("seats") or []]
        if len(users) != 4 or users.count(g59.US) != 1:
            raise ValueError("冻结桌缺我方唯一座位")
        metadata = c31.round_metadata(doc)
        scores = [0, 0, 0, 0]
        units = room_units[room]
        for peer, peer_id in units:
            if users.count(peer_id) != 1:
                raise ValueError("同房强手身份不唯一")
        for round_no, events, start_hands in anatomy.round_blocks(doc):
            if start_hands is None or len(start_hands) != 4:
                raise ValueError("冻结单局缺完整起手")
            dealer = metadata.get(round_no, {}).get("dealer")
            if dealer is None:
                raise ValueError("冻结单局庄位未知")
            snaps = c31.reconstruct(events, start_hands, scores, dealer)
            for seq, snap in sorted(snaps.items()):
                claim = official_claim(events, seq)
                if ((claim is None) != (snap["claim_seat"] is None) or
                        (claim is not None and (claim["seat"] != snap["claim_seat"] or
                                                claim["type"] != snap["claim_kind"]))):
                    raise ValueError("官方响应动作与 C31 快照冲突")
                for peer, peer_id in units:
                    for actor, target in (("peer", users.index(peer_id)),
                                          ("us", users.index(g59.US))):
                        if target == snap["discarder"] or snap["tile"] == c31.WEALTH:
                            continue
                        counts = by_unit[(peer, room, actor)]
                        confirmed, ambiguous = confirmed_phases(snap, target, claim)
                        counts["ambiguous_phase_responses"] += ambiguous
                        counts["confirmed_stages"] += len(confirmed)
                        for phase, actual in confirmed.items():
                            counts["confirmed_" + actual] += 1
                            window, per_phase, audit = c31.evaluate_window(
                                snap, target, [phase], game_id, round_no, parent)
                            counts.update(audit)
                            if window is None:
                                counts["excluded_no_legal_chi_peng_or_parent_score"] += 1
                                continue
                            if window["degraded"]:
                                counts["excluded_degraded_rules"] += 1
                                continue
                            view = window["view"]
                            scores_by_key = window["scores"]
                            parent_key, _ = c32.scored_plan(view, scores_by_key)
                            if parent_key is None:
                                counts["excluded_parent_no_plan"] += 1
                                continue
                            choices = {item["action_key"]: item for item in view["actions"]}
                            if actual == "claim":
                                accepted_key = action_key(claim)
                                if accepted_key not in choices or accepted_key not in scores_by_key:
                                    raise ValueError("官方已接受吃碰不在生产合法动作与评分表")
                            else:
                                accepted_key = None
                            r6_result = r6(view)
                            if r6_result.get("status") != "SCORED":
                                counts["r6_abstain"] += 1
                                r6_key = None
                            else:
                                r6_scores = {entry["action_key"]: entry["score"]
                                             for entry in r6_result.get("entries") or []}
                                r6_key, _ = c32.scored_plan(view, r6_scores)
                            parent_kind = choices[parent_key]["action_type"]
                            parent_claim = parent_kind in c31.CLAIM_TYPES
                            r6_claim = (r6_key is not None and
                                        choices[r6_key]["action_type"] in c31.CLAIM_TYPES)
                            counts["legal_confirmed_opportunities"] += 1
                            counts["actual_" + actual] += 1
                            counts["parent_claim"] += parent_claim
                            counts["r6_claim"] += r6_claim
                            if actual == "claim" and not parent_claim:
                                counts["actual_claim_parent_pass"] += 1
                            if actual == "pass" and parent_claim:
                                counts["actual_pass_parent_claim"] += 1
                            if actual == "claim" and parent_key == accepted_key:
                                counts["actual_claim_parent_exact"] += 1
                            if actual == "pass" and not parent_claim:
                                counts["actual_pass_parent_pass"] += 1
                            if actual == "timeout":
                                counts["actual_timeout_parent_claim"] += parent_claim
                            row = {"peer": peer, "actor": actor, "room": room,
                                   "game_id": game_id, "round_no": round_no,
                                   "discard_seq": seq, "seat": target, "phase": phase,
                                   "actual": actual, "accepted_key": accepted_key,
                                   "parent_key": parent_key, "r6_key": r6_key,
                                   "parent_margin": window["margin"],
                                   "pass_shanten": window["pass"].get("shanten_after"),
                                   "claim_shanten": window["claim"].get("shanten_after"),
                                   "pass_width": c31.width_of(window["pass"]),
                                   "claim_width": c31.width_of(window["claim"]),
                                   "white_count": sum(tile.code == c31.WEALTH
                                                      for tile in window["observation"].my_hand),
                                   "own_meld_count": len(window["observation"].melds[target]),
                                   "wall_remaining": window["observation"].remaining_tile_count,
                                   "dealer": dealer == target}
                            rows.append(row)
            ended = next((event for event in events if event.get("type") == "round_ended"), None)
            if ended is None:
                raise ValueError("冻结单局缺官方终局")
            delta = (ended.get("data") or {}).get("scores")
            if not isinstance(delta, list) or len(delta) != 4 or sum(delta) != 0:
                raise ValueError("官方单局四座积分不守恒")
            scores = [a + b for a, b in zip(scores, delta)]
        room_games_done = sum(r == room for r, _ in found_games)
        if room_games_done == 10:
            print(json.dumps({"room": room, "games_done": room_games_done,
                              "rows": len(rows)}, ensure_ascii=False), flush=True)
    if found_games != expected_games:
        raise ValueError("G69 冻结完整桌未全部覆盖")
    unique = {(row["peer"], row["actor"], row["game_id"], row["round_no"],
               row["discard_seq"], row["seat"], row["phase"]) for row in rows}
    if len(unique) != len(rows):
        raise ValueError("响应阶段窗口重复")
    OUT.mkdir(parents=True)
    rows_path = _project_file(_PROJECT_ROOT, OUT / "rows.jsonl.gz")
    with rows_path.open("wb") as stream:
        with gzip.GzipFile(filename="", mode="wb", fileobj=stream, mtime=0) as zipped:
            for row in rows:
                zipped.write((json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode())
    result = {"schema": "g76-confirmed-response-atlas/1", "exploratory": True,
              "parent_source_sha256": c31.R18_INTEGRATED_POSITIVE_V2_SHA256,
              "source_sha256": {"g61": sha(G61), "g69": sha(G69), "prereg": sha(PREREG),
                                "c31_reconstruction": sha(Path(c31.__file__)),
                                "g76_script": sha(Path(__file__)), "rows_gzip": sha(rows_path)},
              "official_game_digests": sorted(official_digests),
              "games": len(found_games), "rows": len(rows),
              "physical_seat_discard_units": len({
                  (row["peer"], row["actor"], row["game_id"], row["round_no"],
                   row["discard_seq"], row["seat"]) for row in rows}),
              "physical_discard_events": len({
                  (row["game_id"], row["round_no"], row["discard_seq"]) for row in rows}),
              "by_unit": [{"peer": peer, "room": room, "actor": actor,
                           "counts": dict(sorted(counter.items()))}
                          for (peer, room, actor), counter in sorted(by_unit.items())],
              "boundary": "只用官方确认阶段，主动过牌与超时分列；已看强手房为发现集，非候选价值标签。"}
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(json.dumps(result, ensure_ascii=False, sort_keys=True,
                                                  indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"games": len(found_games), "rows": len(rows),
                      "units": len(by_unit)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
