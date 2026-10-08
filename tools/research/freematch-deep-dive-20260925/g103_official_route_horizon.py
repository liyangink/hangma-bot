#!/usr/bin/env python3
"""G103：只读官方真实父代行动链，核对高番入口距根动作几次本人摸牌。"""

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
import g05_strong_draw_reconstruction as g05
import g69_route_chain_analysis as g69
import g59_freematch_white_value_audit as g59
from extract_room_scores import load_rooms
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g101-new-free-wider-route-20260928')
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G103-OFFICIAL-ROUTE-HORIZON-PREREG-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g103-official-route-horizon-20260928')


def sha(path: Path) -> str:
    """输入和脚本按原始字节绑定。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha(doc: dict) -> str:
    """官方牌谱去重后整场 JSON 的稳定摘要，不修改原始归档。"""
    raw = json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def selected_roots() -> list[dict]:
    """只按 G101 动作前键取每个单局首个冲突，绝不按终局筛选。"""
    doc = json.loads((_project_file(_PROJECT_ROOT, SOURCE / "selection/result.json")).read_text(encoding="utf-8"))
    if doc["outcome_labels_opened"] is not False or doc["counts"]["target_windows"] != 203:
        raise ValueError("G103 G101 冻结选择集漂移")
    roots = [json.loads(line) for line in gzip.open(
        _project_file(_PROJECT_ROOT, SOURCE / "selection/rows.jsonl.gz"), "rt", encoding="utf-8")]
    roots.sort(key=lambda row: row["key"])
    first = {}
    for root in roots:
        key = tuple(root["key"][:3])
        first.setdefault(key, root)
    if len(first) != 170 or len({root["key"][1] for root in first.values()}) != 105:
        raise ValueError("G103 预登记的独立单局/桌数漂移")
    return list(first.values())


def official_games(roots: list[dict]) -> tuple[dict[str, dict], dict[str, str]]:
    """使用既有去重口径找完整十六房中的官方原始事件。"""
    batch = json.loads((_project_file(_PROJECT_ROOT, SOURCE / "result.json")).read_text(encoding="utf-8"))
    expected = {game_id for record in batch["rooms"].values() for game_id in record["selected_games"]}
    if len(expected) != 160:
        raise ValueError("G103 十六房并非 160 张官方桌")
    games = {}
    digests = {}
    for _, room, _, game_id, doc in load_rooms():
        if game_id not in expected:
            continue
        if game_id in games or room not in batch["rooms"]:
            raise ValueError("G103 官方牌谱重复或外房")
        seats = [seat.get("user_id") for seat in doc.get("seats") or []]
        if len(seats) != 4 or seats.count(g59.US) != 1:
            raise ValueError("G103 官方本人座位身份不唯一")
        games[game_id] = doc
        digests[game_id] = canonical_sha(doc)
    if set(games) != expected:
        raise ValueError("G103 缺少 G101 冻结完整桌官方牌谱")
    return games, digests


def all_clean_windows(batch: dict) -> dict[tuple[str, int], list[dict]]:
    """读取 G101 已核干净摸打，不用未来事件重建另一个在线状态。"""
    grouped: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for room, record in sorted(batch["rooms"].items()):
        path = _project_file(_PROJECT_ROOT, SOURCE / "rooms" / room / "windows.json.gz")
        if sha(path) != record["windows_gzip_sha256"]:
            raise ValueError("G103 官方窗口压缩摘要漂移")
        for row in json.loads(gzip.decompress(path.read_bytes()))["windows"]:
            if row["room_id"] != room:
                raise ValueError("G103 混入外房干净窗口")
            grouped[(row["game_id"], row["round_no"])].append(row)
    for rows in grouped.values():
        rows.sort(key=lambda row: row["draw_seq"])
        if len({row["draw_seq"] for row in rows}) != len(rows):
            raise ValueError("G103 同局干净摸打序号重复")
    return grouped


def entry(row: dict) -> dict:
    """入口只由动作当时的 PlayerObservation 与生产规则合法弃牌计算。"""
    obs = observation_from_json(row["observation"])
    rules = c31.RULES.analyze(obs, value_limits=c31.VALUE_LIMITS)
    candidate = next((item for item in rules.legal_candidates
                      if item.action_key == row["actual_action"]), None)
    if candidate is None or not row["actual_action"].startswith("discard:"):
        raise ValueError("G103 官方实际弃牌不在生产合法动作中")
    facts = g69.route_facts(candidate, obs.seat)
    if facts is None:
        raise ValueError("G103 官方实际弃牌缺完整条件胡事实")
    return facts


def analyze_root(root: dict, doc: dict, all_windows: list[dict]) -> dict:
    """先核对根后官方事件；未来仅作描述标签，绝不反馈到根动作评分。"""
    room, game_id, round_no, draw_seq = root["key"]
    seats = [seat.get("user_id") for seat in doc.get("seats") or []]
    if seats[root["seat"]] != g59.US:
        raise ValueError("G103 本人座位身份不符")
    blocks = [(events, start_hands) for number, events, start_hands in g05.anatomy.round_blocks(doc)
              if number == round_no]
    if len(blocks) != 1 or blocks[0][1] is None:
        raise ValueError("G103 官方单局事件块不唯一或缺起手")
    events = blocks[0][0]
    if len({event["seq"] for event in events}) != len(events):
        raise ValueError("G103 官方单局事件序号重复")
    draw = next((event for event in events if event["seq"] == draw_seq), None)
    if draw is None or draw["type"] != "tile_drawn" or draw["seat"] != root["seat"]:
        raise ValueError("G103 冻结根不是本人正常摸牌")
    material = next((event for event in events if event["seq"] > draw_seq
                     and event["type"] not in g05.SKIP_EVENT_TYPES), None)
    if (material is None or material["type"] != "tile_discarded" or
            material["seat"] != root["seat"] or
            "discard:" + material["tile"] != root["parent_action"]):
        raise ValueError("G103 根摸后实战弃牌与 G101 冻结父代不符")
    root_discard_seq = material["seq"]
    ended = [event for event in events if event["type"] == "round_ended"]
    if len(ended) != 1 or ended[0]["seq"] <= root_discard_seq:
        raise ValueError("G103 根后无唯一终局事件")
    terminal = ended[0]
    summary = next((item for item in doc["rounds"] if item["round_no"] == round_no), None)
    data = terminal.get("data") or {}
    # 官方 rounds[] 会省略零分流局；完整 round_ended 事件仍在。该口径
    # 已由 G60 的全房结算审计确认，不能把省略误报成官方终局矛盾。
    omitted_zero_draw = summary is None
    if omitted_zero_draw:
        if (data.get("draw") is not True or data.get("scores") != [0, 0, 0, 0]
                or terminal["seat"] != -1):
            raise ValueError("G103 仅允许摘要省略零分流局")
    elif (summary["scores"] != data.get("scores") or
          bool(summary["is_draw"]) != bool(data.get("draw")) or
          (not data.get("draw") and summary["winner"] != terminal["seat"])):
        raise ValueError("G103 官方逐事件终局与整场摘要不一致")
    if data.get("draw"):
        outcome = "draw"
    else:
        outcome = "self_win" if terminal["seat"] == root["seat"] else "other_win"
    post = [event for event in events if root_discard_seq < event["seq"] < terminal["seq"]]
    future_draws = [event for event in post if event["type"] == "tile_drawn"
                    and event["seat"] == root["seat"]]
    future_claims = [event for event in post if event["type"] in ("chi", "peng", "gang")
                     and event["seat"] == root["seat"]]
    clean = [row for row in all_windows if row["draw_seq"] >= draw_seq]
    if len([row for row in clean if row["draw_seq"] == draw_seq]) != 1:
        raise ValueError("G103 根窗口不在 G101 干净重建结果中")
    clean = [row for row in clean if row["draw_seq"] == draw_seq or
             root_discard_seq < row["draw_seq"] < terminal["seq"]]
    future_indices = {event["seq"]: index for index, event in enumerate(future_draws, 1)}
    analyzed = []
    for row in clean:
        ordinal = 0 if row["draw_seq"] == draw_seq else future_indices.get(row["draw_seq"])
        if ordinal is None:
            raise ValueError("G103 干净未来窗口不在官方本人摸牌事件中")
        facts = entry(row)
        analyzed.append({"draw_seq": row["draw_seq"], "ordinal": ordinal,
                         "actual_action": row["actual_action"], "facts": facts})
    first = {}
    for label, field in (("any", "any_capacity"), ("plain", "plain_capacity"),
                         ("high", "high_capacity")):
        matching = [item for item in analyzed if item["facts"][field] > 0]
        first[label] = min((item["ordinal"] for item in matching), default=None)
    covered = {item["draw_seq"] for item in analyzed if item["ordinal"] > 0}
    gaps = [event["seq"] for event in future_draws if event["seq"] not in covered]
    return {
        "key": root["key"], "seat": root["seat"],
        "white_before": root["white_before"], "shanten": root["shanten"],
        "root_action": root["parent_action"], "alternate_action": root["alternate_action"],
        "root_discard_seq": root_discard_seq, "round_end_seq": terminal["seq"],
        "outcome": outcome, "terminal_fan": data.get("fan"),
        "summary_omitted_zero_draw": omitted_zero_draw,
        "future_own_draw_count": len(future_draws),
        "future_own_draw_seq": [event["seq"] for event in future_draws],
        "future_own_claim_count": len(future_claims),
        "future_own_claim_types": [event["type"] for event in future_claims],
        "future_clean_normal_discard_count": len(clean) - 1,
        "future_uncovered_draw_seq": gaps,
        "first_entry_ordinal": first,
        "entry_windows": analyzed,
    }


def main() -> None:
    """全量 170 个首冲突单局，保留缺证据和官方终局类别。"""
    if OUT.exists():
        raise FileExistsError("G103 已有结果，拒绝覆盖")
    roots = selected_roots()
    games, game_sha = official_games(roots)
    batch = json.loads((_project_file(_PROJECT_ROOT, SOURCE / "result.json")).read_text(encoding="utf-8"))
    windows = all_clean_windows(batch)
    rows = []
    counts = Counter()
    rooms: dict[str, set[str]] = defaultdict(set)
    for root in roots:
        room, game_id, round_no, _ = root["key"]
        try:
            row = analyze_root(root, games[game_id], windows[(game_id, round_no)])
            counts["complete"] += 1
            counts["outcome/" + row["outcome"]] += 1
            counts["summary_omitted_zero_draw"] += row["summary_omitted_zero_draw"]
            counts["future_draw/" + str(min(3, row["future_own_draw_count"]))] += 1
            if row["outcome"] == "other_win":
                counts["other_win_after_draw/" + str(min(3, row["future_own_draw_count"]))] += 1
            counts["future_claims"] += row["future_own_claim_count"]
            counts["uncovered_future_draws"] += len(row["future_uncovered_draw_seq"])
            counts["hands_with_uncovered_future_draw"] += bool(row["future_uncovered_draw_seq"])
            for label, ordinal in row["first_entry_ordinal"].items():
                if ordinal is not None:
                    band = str(min(3, ordinal))
                    key = "first_" + label + "/" + band
                    counts[key] += 1
                    rooms[key].add(room)
                    if ordinal >= 3:
                        earlier_draws = row["future_own_draw_seq"][:ordinal - 1]
                        counts["first_" + label + "_3plus_with_prior_gap"] += any(
                            seq in row["future_uncovered_draw_seq"] for seq in earlier_draws)
                else:
                    counts["no_observed_" + label + "_entry"] += 1
        except (ValueError, TypeError, KeyError) as exc:
            reason = type(exc).__name__ + ": " + str(exc)[:180]
            row = {"key": root["key"], "status": "unavailable", "reason": reason}
            counts["unavailable"] += 1
            counts["unavailable/" + reason] += 1
        rows.append(row)
    result = {
        "schema": "g103-official-route-horizon/1", "outcome_labels_opened": True,
        "root_count": len(roots), "rooms": len({root["key"][0] for root in roots}),
        "tables": len({root["key"][1] for root in roots}),
        "counts": dict(sorted(counts.items())),
        "entry_room_coverage": {key: len(value) for key, value in sorted(rooms.items())},
        "input_sha256": {"g101_batch": sha(_project_file(_PROJECT_ROOT, SOURCE / "result.json")),
                         "g101_selection": sha(_project_file(_PROJECT_ROOT, SOURCE / "selection/result.json")),
                         "g101_rows": sha(_project_file(_PROJECT_ROOT, SOURCE / "selection/rows.jsonl.gz")),
                         "prereg": sha(PREREG), "script": sha(Path(__file__)),
                         "g69_route_helper": sha(_project_file(_PROJECT_ROOT, HERE / "g69_route_chain_analysis.py"))},
        "official_game_canonical_sha256": dict(sorted(game_sha.items())),
        "boundary": "仅父代官方已发生行动链；干净摸打限定覆盖，不能由父代结局推断另一弃牌的效果。",
    }
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    body = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    (_project_file(_PROJECT_ROOT, OUT / "rows.jsonl.gz")).write_bytes(gzip.compress(body.encode("utf-8"), compresslevel=9, mtime=0))
    print(json.dumps({"root_count": len(roots), "counts": result["counts"]}, ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
