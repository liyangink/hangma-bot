#!/usr/bin/env python3
"""G228：多白一向听强手已执行路径的下一摸与生产抓打资格。"""

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

import g196_three_draw_competing_route_pilot as g196
import g220_future_qualification_audit as g220
import g223_visible_multi_action_route as g223
import g87_post_claim_score_trace as g87
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
PLAN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G228-MULTIWHITE-FUTURE-QUALIFICATION-PLAN-2026-09-29.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g228-multiwhite-future-qualification-20260929')
EXPECTED = 351


def digest(path: Path) -> str:
    """按原始字节绑定官方复盘派生来源和本次程序。"""
    return sha256(path.read_bytes()).hexdigest()


def _wall_bucket(wall: int) -> str:
    if wall <= 48:
        return "33-48"
    if wall <= 64:
        return "49-64"
    if wall <= 80:
        return "65-80"
    return "81+"


def selected(visible: dict[tuple, dict]) -> dict:
    """只用行动前观察和已执行合法动作筛目标，不读 G65 后继。"""
    rows = []
    for identity, row in sorted(visible.items()):
        action = row["actual_action"]
        wall = row["remaining_tile_count"]
        if (not action.startswith("discard:") or action == "discard:白"
                or type(wall) is not int or wall <= 32):
            continue
        observation = observation_from_json(row["observation"])
        full_hand = g196._build_context(observation).full_hand()
        whites = sum(tile.code == "白" for tile in full_hand)
        if whites < 2:
            continue
        request = g87.request_for(observation)
        legal = {item.action_key: item for item in request.rules.legal_candidates}
        if len(legal) != len(request.rules.legal_candidates):
            raise ValueError("G228 生产合法动作键重复")
        candidate = legal.get(action)
        if candidate is None or candidate.facts is None:
            raise ValueError("G228 官方已接受动作不在生产合法事实")
        if candidate.facts.standard_shanten_after != 1:
            continue
        rows.append({
            "identity": list(identity), "peer": identity[0], "room": identity[1],
            "game_id": identity[2], "round_no": identity[3],
            "draw_seq": identity[4], "seat": identity[5],
            "actual_action": action, "parent_agrees": row["parent_agrees"],
            "whites_before": whites, "wall": wall,
            "wall_bucket": _wall_bucket(wall),
            "own_melds": len(observation.melds[observation.seat]),
            "baotou_before": bool(observation.rule_state.baotou),
            "chain_count_before": observation.rule_state.chain_count,
        })
    counts = Counter(row["peer"] for row in rows)
    rooms = {peer: len({row["room"] for row in rows if row["peer"] == peer})
             for peer in counts}
    if (len(rows) != EXPECTED or counts != {"tengshe_0638": 199,
                                             "xuanwu_2346": 152}
            or rooms != {"tengshe_0638": 17, "xuanwu_2346": 15}):
        raise ValueError("G228 行动前预检母体规模漂移")
    return {
        "schema": "g228-multiwhite-future-selection/1", "outcome_blind": True,
        "source_sha256": {
            "plan": digest(PLAN), "script": digest(Path(__file__)),
            "g61_result": digest(g220.G61 / "result.json"),
            "g220_script": digest(Path(g220.__file__)),
        },
        "counts_by_peer": dict(sorted(counts.items())), "rooms_by_peer": rooms,
        "rows": rows,
        "boundary": "仅行动前玩家可见状态与当时合法动作；不读后继标签。",
    }


def _summary(rows: list[dict], field: str) -> dict:
    """未重建下一摸资格保留未知，报告保守分母。"""
    events = Counter(row[field] for row in rows if row[field] is not None)
    total = sum(events.values())
    if total == 0:
        return {"windows": 0, "events": {}}
    next_draw = sum(count for name, count in events.items()
                    if name.startswith(("reconstructed/", "unreconstructed/")))
    free = events["reconstructed/free"]
    restricted = events["reconstructed/restricted"]
    return {
        "windows": total,
        "rooms": len({row["room"] for row in rows if row[field] is not None}),
        "events": dict(sorted(events.items())),
        "next_own_normal_draw": next_draw,
        "next_draw_share": next_draw / total,
        "reconstructed_next_discard": free + restricted + events["reconstructed/unknown"],
        "free_among_known_reconstructed": (
            free / (free + restricted) if free + restricted else None),
        "free_lower_bound_among_all_next_draws": (
            free / next_draw if next_draw else None),
        "unknown_next_draw_count": next_draw - free - restricted,
    }


def main() -> None:
    """先冻结目标身份，再连接已归档官方后继和生产抓打资格。"""
    visible = g220.windows()
    frozen = selected(visible)
    g223.write_new(_project_file(_PROJECT_ROOT, OUT / "selection.json"), frozen)
    labels = g220.labels()
    status = g220.hand_status()
    if labels.keys() != visible.keys():
        raise ValueError("G228 G61/G65 全母体不能一一连接")
    rows = []
    for root in frozen["rows"]:
        identity = tuple(root["identity"])
        label = labels[identity]
        first = g220.successor(identity, label, visible, status)
        second = None
        if first.startswith("reconstructed/"):
            next_identity = identity[:4] + (label["next_seq"], identity[5])
            if next_identity not in labels or next_identity not in visible:
                raise ValueError("G228 已重建第一摸缺第二步官方标签")
            second = g220.successor(next_identity, labels[next_identity],
                                    visible, status)
        rows.append({**root, "first": first, "second": second,
                     "first_next_seq": label["next_seq"]})
    if len(rows) != EXPECTED:
        raise ValueError("G228 后继连接未覆盖所有选窗")
    groups = {"all": rows}
    for name in ("tengshe_0638", "xuanwu_2346"):
        groups[name] = [row for row in rows if row["peer"] == name]
    for name in ("33-48", "49-64", "65-80", "81+"):
        groups["wall/" + name] = [row for row in rows if row["wall_bucket"] == name]
    for name in ("closed", "postclaim"):
        groups["meld/" + name] = [row for row in rows
                                   if (row["own_melds"] == 0) == (name == "closed")]
    result = {
        "schema": "g228-multiwhite-future-qualification-result/1",
        "selection_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "selection.json")),
        "source_sha256": {
            "g65_result": digest(g220.G65 / "result.json"),
            "g65_rows": digest(g220.G65 / "rows.jsonl.gz"),
            "g64_result": digest(g220.G64),
            "catch_play_production": digest(
                _project_file(_PROJECT_ROOT, HERE.parents[1] / "src/hangma_bot/hangma/catch_play.py")),
        },
        "groups": {name: {"first": _summary(group, "first"),
                          "second_after_reconstructed_first": _summary(group, "second")}
                   for name, group in sorted(groups.items())},
        "rows": rows,
        "boundary": "强手已执行路径的观察性后继，缺观察保持未知；不是备选根的因果再摸概率。",
    }
    g223.write_new(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({"selected": len(rows),
                      "all": result["groups"]["all"],
                      "by_peer": {name: result["groups"][name]
                                  for name in ("tengshe_0638", "xuanwu_2346")}},
                     ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
