#!/usr/bin/env python3
"""G201：不读取赢家与后续事件，冻结八个官方多白近听双弃牌窗。"""

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
from hashlib import sha256
import json
from pathlib import Path

import g189_high_white_natural_support as g189
from hangma_bot.application.audit_codec import observation_from_json
from hangma_bot.hangma.engine import _build_context


HERE = Path(__file__).resolve().parent
PLAN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G201-MULTIWHITE-NEAR-READY-ROUTE-PREREG-2026-09-29.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g201-multiwhite-near-ready-route-20260929/selection.json')


def digest(path: Path) -> str:
    """读取冻结输入及选样程序原始字节。"""

    return sha256(path.read_bytes()).hexdigest()


def public_capacity(facts: dict, field: str) -> tuple[int, int] | None:
    """区分缺失事实与已知空向量，只纳入正公开未见容量。"""

    items = facts.get(field)
    if not isinstance(items, list):
        return None
    seen = set()
    values = []
    for item in items:
        code, amount = item.get("code"), item.get("remaining_estimate")
        if not isinstance(code, str) or code in seen or type(amount) is not int or amount < 0:
            raise ValueError("G201 逐牌容量未知、非法或重复")
        seen.add(code)
        if amount > 0:
            values.append(amount)
    return len(values), sum(values)


def candidate(row: dict, raw: dict, ranked: list[dict], parent: str) -> dict | None:
    """对一个已接受父代正常摸打窗，仅比较依法可见的双弃牌事实。"""

    obs = observation_from_json(raw["observation"])
    if (obs.phase != "draw" or obs.turn_seat != obs.seat
            or type(obs.remaining_tile_count) is not int
            or obs.remaining_tile_count <= 32):
        return None
    white = sum(tile.code == "白" for tile in _build_context(obs).full_hand())
    if white < 2 or len(obs.melds[obs.seat]) != 0:
        return None
    legal_list = (raw.get("rules") or {}).get("legal_candidates") or []
    legal = {item["action_key"]: item for item in legal_list}
    if len(legal) != len(legal_list) or parent not in legal:
        raise ValueError("G201 父代合法动作或动作键身份异常")
    if not parent.startswith("discard:") or parent == "discard:白":
        return None
    facts = legal[parent].get("facts") or {}
    shanten = facts.get("standard_shanten_after")
    if type(shanten) is not int or shanten not in (0, 1):
        return None
    standard = public_capacity(facts, "standard_useful_tiles")
    seven = public_capacity(facts, "seven_pairs_useful_tiles")
    if standard is None or seven is None or type(facts.get("seven_pairs_shanten_after")) is not int:
        return None
    scored = {item["action_key"]: item for item in ranked}
    options = []
    for key, action in legal.items():
        if key == parent or not key.startswith("discard:") or key == "discard:白":
            continue
        other = action.get("facts") or {}
        if (other.get("standard_shanten_after") != shanten
                or other.get("shanten_after") != facts.get("shanten_after")
                or other.get("seven_pairs_shanten_after") != facts.get("seven_pairs_shanten_after")):
            continue
        o_standard = public_capacity(other, "standard_useful_tiles")
        o_seven = public_capacity(other, "seven_pairs_useful_tiles")
        if (o_standard is None or o_seven is None
                or o_standard[0] <= standard[0]
                or o_standard[1] - standard[1] < 3
                or o_seven[1] < seven[1]):
            continue
        options.append((key, other, o_standard, o_seven))
    if not options:
        return None
    alternate, other, o_standard, o_seven = min(
        options, key=lambda item: (-item[2][0], -item[2][1],
                                   -item[3][1], item[0]))
    if alternate not in scored:
        raise ValueError("G201 合法备选在冻结父代评分表缺失")
    parent_score = scored[parent].get("total_score")
    alternate_score = scored[alternate].get("total_score")
    if (type(parent_score) not in (int, float)
            or type(alternate_score) not in (int, float)
            or parent_score < alternate_score):
        raise ValueError("G201 冻结父代评分排序与已接受动作矛盾")
    encoded = json.dumps(raw["observation"], ensure_ascii=False,
                         sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        **row, "seat": obs.seat, "white_before": white,
        "standard_shanten_after": shanten,
        "wall_remaining": obs.remaining_tile_count,
        "parent_action": parent, "alternate_action": alternate,
        "parent_score": parent_score, "alternate_score": alternate_score,
        "old_facts": {
            "parent": {"combined_shanten": facts["shanten_after"],
                       "standard_shanten": shanten,
                       "seven_shanten": facts["seven_pairs_shanten_after"],
                       "standard": standard, "seven": seven},
            "alternate": {"combined_shanten": other["shanten_after"],
                          "standard_shanten": other["standard_shanten_after"],
                          "seven_shanten": other["seven_pairs_shanten_after"],
                          "standard": o_standard, "seven": o_seven},
        },
        "observation_sha256": sha256(encoded).hexdigest(),
        "observation": raw["observation"],
    }


def main() -> None:
    """固定资格及散列次序；不从八窗读任何实际后续牌或结算。"""

    if OUT.exists():
        raise FileExistsError("G201 选样已存在，拒绝覆盖")
    frozen = json.loads(g189.atlas.FROZEN.read_text(encoding="utf-8"))
    complete_ids = g189.atlas._complete_ids()
    if len(frozen["rooms"]) != 91 or len(complete_ids) != 909:
        raise ValueError("G201 官方完整桌母体漂移")
    groups = defaultdict(list)
    counts = Counter()
    room_source = {}
    seen = set()
    for room in frozen["rooms"]:
        audit = g189.atlas.source.ROOT / room["audit_dir"]
        decision_file = audit / "participants" / g189.atlas.source.ACTOR / "decisions.jsonl"
        if decision_file.stat().st_size != room["decision_bytes"]:
            raise ValueError("G201 冻结决策文件长度漂移")
        release = ((json.loads((audit / "manifest.json").read_text(encoding="utf-8"))
                    .get("payload") or {}).get("policy_release") or {})
        if release.get("candidate_source_sha256") != frozen["parent_source_sha256"]:
            raise ValueError("G201 冻结 R18 v2 源码身份漂移")
        accepted = g189.atlas.source._accepted(decision_file)
        room_source[room["room_id"]] = {
            "audit_dir": room["audit_dir"], "decision_bytes": room["decision_bytes"]}
        for context, raw, plan in g189.atlas.source.screen._iter_decisions(audit):
            game_id = context.get("game_id")
            if (game_id not in complete_ids
                    or (raw.get("window_key") or {}).get("phase") != "draw"):
                continue
            ranked = sorted(plan.get("candidates") or [],
                            key=lambda item: item.get("rank", 10**9))
            if not ranked:
                continue
            parent = ranked[0].get("action_key")
            if accepted.get(context.get("decision_id")) != parent:
                continue
            key = (game_id, context.get("round_no"), context.get("trigger_seq"),
                   context.get("seat"))
            if key in seen:
                raise ValueError("G201 已接受正常摸打窗口重复")
            seen.add(key)
            row = candidate({"room_id": room["room_id"], "game_id": game_id,
                             "round_no": context["round_no"],
                             "trigger_seq": context["trigger_seq"]},
                            raw, ranked, parent)
            if row is None:
                continue
            layer = "threeplus" if row["white_before"] >= 3 else "two"
            identity = "/".join(str(row[key]) for key in (
                "room_id", "game_id", "round_no", "trigger_seq", "seat"))
            row["identity_sha256"] = sha256(identity.encode("utf-8")).hexdigest()
            groups[layer].append(row)
            counts[layer] += 1
    selected = []
    used_rooms = set()
    for layer in ("threeplus", "two"):
        by_room = {}
        for row in groups[layer]:
            room_id = row["room_id"]
            if (room_id not in by_room
                    or row["identity_sha256"] < by_room[room_id]["identity_sha256"]):
                by_room[room_id] = row
        ordered = sorted((row for room_id, row in by_room.items()
                          if room_id not in used_rooms),
                         key=lambda row: (row["identity_sha256"], row["room_id"]))
        chosen = ordered[:4]
        if len(chosen) != 4:
            raise ValueError(f"G201 {layer} 独立房覆盖不足四间")
        for row in chosen:
            row["layer"] = layer
            used_rooms.add(row["room_id"])
        selected.extend(chosen)
    if len(selected) != 8 or len(used_rooms) != 8:
        raise ValueError("G201 固定八窗八房身份不成立")
    payload = {
        "schema": "g201-multiwhite-near-ready-selection/1",
        "source_sha256": {"plan": digest(PLAN), "script": digest(Path(__file__)),
                          "frozen_rooms": digest(g189.atlas.FROZEN),
                          "g189_result": digest(g189.OUT)},
        "parent_source_sha256": frozen["parent_source_sha256"],
        "official_complete_tables": len(complete_ids),
        "eligible_windows": dict(sorted(counts.items())),
        "room_sources": {room: room_source[room] for room in sorted(used_rooms)},
        "selected": selected,
        "boundary": "只读已确认动作前玩家可见状态、合法事实和父代评分；未读取赢家、后续牌序或结算。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                              indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"eligible_windows": payload["eligible_windows"],
                      "selected": [{key: row[key] for key in (
                          "layer", "room_id", "game_id", "round_no", "trigger_seq",
                          "parent_action", "alternate_action")}
                                   for row in selected]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
