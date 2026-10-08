#!/usr/bin/env python3
"""G156：官方同观察强手/父代不同弃牌的保白自然路线对账。"""

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

import g11_longitudinal_route_audit as g11
import g13_two_draw_baotou_support as g13
import g14_white_reserve_frontier as g14
import g61_strong_draw_batch as g61
import g69_route_chain_analysis as g69
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G156-SAME-OBSERVATION-NATURAL-ROUTE-PREREG-2026-09-28.md')
G155_RESULT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g155-pre-ready-natural-chain-20260928/result.json')
G155_ROWS = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g155-pre-ready-natural-chain-20260928/rows.jsonl.gz')
G61_RESULT = g69.G61 / "result.json"
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g156-same-observation-natural-route-20260928')
ROWS = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g156-same-observation-natural-route-20260928/rows.jsonl.gz')
RESULT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g156-same-observation-natural-route-20260928/result.json')


def sha(path: Path) -> str:
    """原始文件字节摘要，绑定量具和官方证据。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def selected() -> dict[tuple, dict]:
    """只用 G155 首次入口的行动前性质选样，不读后续听牌列。"""
    g155 = json.loads(G155_RESULT.read_text(encoding="utf-8"))
    if g155["schema"] != "g155-pre-ready-natural-chain/1":
        raise ValueError("G155 schema 漂移")
    if sha(G155_ROWS) != g155["rows_sha256"] or g155["selected_hands"] != 1479:
        raise ValueError("G155 入口母体摘要或数量漂移")
    result = {}
    with gzip.open(G155_ROWS, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if (row["actor"] != "peer"
                    or not row["parent_same_shanten_discard"]
                    or row["entry_action"] == row["parent_action"]):
                continue
            key = (row["peer"], row["room"], row["game_id"],
                   row["round_no"], row["entry_draw_seq"])
            if key in result:
                raise ValueError("G155 强手入口窗口重复")
            result[key] = {
                "actual_action": row["entry_action"],
                "parent_action": row["parent_action"],
                "actual_standard_support": row["entry_standard_support"],
                "parent_standard_support": row["parent_standard_support"],
            }
    if len(result) != 279:
        raise ValueError("G155 强手同观察不同弃牌窗口数漂移")
    return result


def vector(items) -> tuple[tuple[str, int], ...]:
    """生产规则的逐牌正容量向量；牌码不能重复或未知。"""
    if items is None:
        raise ValueError("普通型有效牌逐牌事实缺失")
    pairs = tuple(sorted((item.code, item.remaining_estimate) for item in items))
    if (len({code for code, _ in pairs}) != len(pairs)
            or any(type(capacity) is not int or not 0 <= capacity <= 4
                   for _, capacity in pairs)):
        raise ValueError("普通型逐牌有效张重复或容量越界")
    return pairs


def analyze(raw: dict, wanted: dict, peer: str, room: str) -> dict:
    """同一动作前观察重算两合法动作的即时与全保白自然事实。"""
    if (raw["actual_action"] != wanted["actual_action"]
            or raw["parent_top_action"] != wanted["parent_action"]):
        raise ValueError("G155 入口动作与强手原始官方观察不一致")
    observation = observation_from_json(raw["observation"])
    rules = g69.c31.RULES.analyze(observation, value_limits=g69.c31.VALUE_LIMITS)
    legal = {candidate.action_key: candidate for candidate in rules.legal_candidates}
    if len(legal) != len(rules.legal_candidates):
        raise ValueError("生产合法候选动作重复")
    parsed = g11._hand(raw["observation"])
    if parsed is None:
        raise ValueError("G155 官方入口非正常摸打手牌")
    full, _, meld_count = parsed
    discards, exposed = g13._public_counts(raw["observation"])
    arms = {}
    for label, action in (("peer", wanted["actual_action"]),
                          ("parent", wanted["parent_action"])):
        candidate = legal.get(action)
        if candidate is None or candidate.facts is None:
            raise ValueError("G155 强手或父代弃牌无生产合法规则事实")
        basic = g69.route_facts(candidate, observation.seat)
        if (basic is None or basic["standard_shanten"] != 1
                or basic["standard_support"] != wanted[
                    "actual_standard_support" if label == "peer"
                    else "parent_standard_support"]):
            raise ValueError("G155 普通型向听或即时有效张漂移")
        after = g11._after_discard(full, action)
        if after is None:
            raise ValueError("合法弃牌不在本人当前手牌")
        facts = candidate.facts
        arm = {
            "action": action,
            "white_after": after["白"],
            "standard_support": basic["standard_support"],
            "standard_vector": vector(facts.standard_useful_tiles),
            "seven_shanten": facts.seven_pairs_shanten_after,
            "combined_shanten": facts.shanten_after,
        }
        if after["白"] == 1:
            natural = g14._frontier(after, meld_count, discards, exposed,
                                    action.split(":", 1)[1])
            arm["natural_need"] = natural[
                "standard_natural_draws_needed_by_reserved_whites"][-1]
            arm["natural_types"] = natural[
                "all_whites_reserved_natural_tile_types"]
            arm["natural_capacity_upper"] = natural[
                "all_whites_reserved_public_capacity_upper"]
            arm["natural_vector"] = natural[
                "all_whites_reserved_useful_by_tile"]
            if (natural["standard_natural_draws_needed_by_reserved_whites"][0]
                    != 2):
                raise ValueError("一白一向听未留白自然缺口不是两张")
        arms[label] = arm
    return {
        "peer": peer, "room": room, "game_id": raw["game_id"],
        "round_no": raw["round_no"], "draw_seq": raw["draw_seq"],
        "wall_remaining": raw["remaining_tile_count"],
        "meld_count": meld_count,
        "peer_arm": arms["peer"], "parent_arm": arms["parent"],
        "both_retain_one_white": (arms["peer"]["white_after"] == 1
                                  and arms["parent"]["white_after"] == 1),
        "same_standard_support": (arms["peer"]["standard_support"]
                                  == arms["parent"]["standard_support"]),
        "same_standard_vector": (arms["peer"]["standard_vector"]
                                 == arms["parent"]["standard_vector"]),
        "same_seven_shanten": (arms["peer"]["seven_shanten"]
                              == arms["parent"]["seven_shanten"]),
    }


def aggregate(rows: list[dict]) -> dict:
    """分强手和可比层完整报告自然方向，不能按好结局筛选。"""
    groups: dict[str, Counter] = defaultdict(Counter)
    rooms: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        peer = row["peer"]
        tiers = ["all_changed"]
        if row["both_retain_one_white"]:
            tiers.append("both_keep_white")
            if row["same_standard_support"]:
                tiers.append("same_standard_support")
            if row["same_standard_vector"]:
                tiers.append("same_standard_vector")
                if row["same_seven_shanten"]:
                    tiers.append("same_standard_vector_and_seven")
        for tier in tiers:
            name = peer + "/" + tier
            count = groups[name]
            rooms[name].add(row["room"])
            count["windows"] += 1
            count["parent_discards_white"] += not row["both_retain_one_white"]
            if not row["both_retain_one_white"]:
                continue
            a, p = row["peer_arm"], row["parent_arm"]
            for metric in ("natural_need", "natural_types", "natural_capacity_upper"):
                delta = a[metric] - p[metric]
                count[metric + "/more"] += delta > 0
                count[metric + "/equal"] += delta == 0
                count[metric + "/less"] += delta < 0
            count["natural_vector_equal"] += a["natural_vector"] == p["natural_vector"]
            count["seven_shanten_peer_worse"] += (
                a["seven_shanten"] is not None
                and p["seven_shanten"] is not None
                and a["seven_shanten"] > p["seven_shanten"])
    return {name: {**dict(sorted(count.items())), "rooms": len(rooms[name])}
            for name, count in sorted(groups.items())}


def main() -> None:
    """G155 入口逐条绑定原始官方观察；已有输出不得覆盖。"""
    if RESULT.exists() or ROWS.exists():
        raise FileExistsError("G156 已有冻结证据，拒绝覆盖")
    wanted = selected()
    g61 = json.loads(G61_RESULT.read_text(encoding="utf-8"))
    rows = []
    source_hashes = {}
    seen = set()
    for peer, room in sorted({key[:2] for key in wanted}):
        path = g61_room_path(peer, room)
        original, original_sha = g69.load_windows(path)
        unit = g61["units"][peer + "/" + room]
        if original_sha != unit["windows_sha256"]:
            raise ValueError("G61 官方行动前窗口摘要漂移")
        source_hashes[peer + "/" + room] = {"raw_sha256": original_sha,
                                             "file_sha256": sha(path)}
        for raw in original:
            marker = (peer, room, raw["game_id"], raw["round_no"],
                      raw["draw_seq"])
            if marker not in wanted:
                continue
            if marker in seen:
                raise ValueError("G156 入口官方观察重复")
            seen.add(marker)
            rows.append(analyze(raw, wanted[marker], peer, room))
    if seen != wanted.keys() or len(rows) != 279:
        raise ValueError("G156 入口官方观察未覆盖或重复")
    summary = aggregate(rows)
    OUT.mkdir(parents=True, exist_ok=False)
    body = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
                   for row in rows).encode("utf-8")
    ROWS.write_bytes(gzip.compress(body, compresslevel=9, mtime=0))
    result = {
        "schema": "g156-same-observation-natural-route/1",
        "exploratory": True,
        "source_sha256": {"prereg": sha(PREREG), "script": sha(Path(__file__)),
                          "g155_result": sha(G155_RESULT),
                          "g155_rows": sha(G155_ROWS),
                          "g61_result": sha(G61_RESULT),
                          "g14_frontier": sha(_project_file(_PROJECT_ROOT, HERE / "g14_white_reserve_frontier.py"))},
        "raw_window_hashes": source_hashes,
        "rows_sha256": sha(ROWS), "windows": len(rows), "groups": summary,
        "boundary": "只比较同一官方玩家可见观察上的合法弃牌即时自然形；强手动作非最优标签，公开未见容量非墙概率。未预测真实后续动作、他家先胡或整桌净分。",
    }
    RESULT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True,
                                 indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


def g61_room_path(peer: str, room: str) -> Path:
    """沿 G61 固定强手－房单位读取行动前观察。"""
    return g61.room_dir((peer, room)) / "windows.json"


if __name__ == "__main__":
    main()
