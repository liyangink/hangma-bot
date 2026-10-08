#!/usr/bin/env python3
"""G253：只按玩家可见条件审计已吃碰后正常摸打的残差支持域。"""

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
import hashlib
import json
from pathlib import Path

from extract_room_scores import load_rooms


HERE = Path(__file__).resolve().parent
G61 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g61-strong-draw-action-atlas-20260927')
G86 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g86-post-claim-normal-draw-chain-20260928/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g253-postclaim-residual-support-20260929/result.json')
PEERS = ("xuanwu_2346", "tengshe_0638")
HONORS = frozenset("东南西北中发白")


def sha(path: Path) -> str:
    """对冻结输入和本审计源码做字节级摘要。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def target_key(peer: str, room: str, row: dict) -> tuple:
    """同一强手、房、桌、单局、座位和官方摸牌序号定位动作窗。"""

    return (peer, room, row["game_id"], row["round_no"], row["draw_seq"], row["seat"])


def features(row: dict) -> dict:
    """仅从行动前 PlayerObservation 提取线上可复算的粗支持域字段。"""

    obs = row["observation"]
    seat = obs["seat"]
    own = obs["melds"][seat]
    chi_peng = sum(meld["kind"] in ("chi", "peng") for meld in own)
    if chi_peng == 0:
        raise ValueError("目标不是已吃碰后摸打")
    if obs["phase"] != "draw" or obs["snapshot_seq"] != row["draw_seq"]:
        raise ValueError("摸打观察的阶段或序号不符")
    white = obs["my_hand"].count("白")
    remaining = obs["remaining_tile_count"]
    opponent_max_melds = max(len(melds) for index, melds in enumerate(obs["melds"])
                             if index != seat)
    scores = obs["scores"]
    own_score = scores[seat]
    other_scores = [score for index, score in enumerate(scores) if index != seat]
    if own_score > max(other_scores):
        score_position = "sole_leader"
    elif own_score < min(other_scores):
        score_position = "sole_last"
    elif own_score == max(scores):
        score_position = "tied_leader"
    elif own_score == min(scores):
        score_position = "tied_last"
    else:
        score_position = "middle"
    return {
        "white": "2plus" if white >= 2 else str(white),
        "own_chi_peng_melds": "2plus" if chi_peng >= 2 else "1",
        "own_meld_kinds": ("mixed" if any(m["kind"] == "chi" for m in own) and
                            any(m["kind"] == "peng" for m in own) else
                            "chi_present" if any(m["kind"] == "chi" for m in own) else
                            "peng_present"),
        "wall_remaining": "0-29" if remaining < 30 else
                          "30-54" if remaining < 55 else "55plus",
        "opponent_max_melds": "2plus" if opponent_max_melds >= 2 else str(opponent_max_melds),
        "score_position": score_position,
        "baotou": bool(obs["rule_state"]["baotou"]),
        "catch_play": bool(obs["rule_state"]["catch_play"]),
    }


def cell(feature: dict) -> str:
    """粗支持域只含事前可见特征；不是可直接调用的动作评分规则。"""

    fields = ("white", "own_chi_peng_melds", "wall_remaining", "opponent_max_melds")
    return "|".join(feature[name] for name in fields)


def discard_family(key: str) -> str:
    """区分强手与父代弃牌的字面族；不等同于行动价值。"""

    if not key.startswith("discard:"):
        raise ValueError("G86 目标动作应为合法弃牌")
    return "honor" if key.removeprefix("discard:") in HONORS else "suit"


def main() -> None:
    """冻结分母、严格分歧与留一房支持覆盖；不打开任何终局得分。"""

    if OUT.exists():
        raise SystemExit("G253 证据已存在，拒绝覆盖")
    g61 = json.loads((_project_file(_PROJECT_ROOT, G61 / "result.json")).read_text(encoding="utf-8"))
    g86 = json.loads(G86.read_text(encoding="utf-8"))
    if (g61.get("outcome_labels_opened") is not False or
            g86.get("terminal_score_labels_opened") is not False):
        raise ValueError("发现集非结果盲")
    if len(g61["units"]) != 32 or len(g86["rows"]) != 1083:
        raise ValueError("G61/G86 母体数量漂移")
    targets = {}
    for row in g86["rows"]:
        key = target_key(row["peer"], row["room"], row)
        if key in targets:
            raise ValueError("G86 严格分歧目标重复")
        targets[key] = row

    # 分析单位是强手－房；同一房的两名强手不可算独立房。
    by_peer_room: dict[tuple[str, str], Counter] = defaultdict(Counter)
    by_cell_room: dict[tuple[str, str, str], Counter] = defaultdict(Counter)
    marginals: dict[tuple[str, str, str], Counter] = defaultdict(Counter)
    honor_pairs: dict[str, Counter] = defaultdict(Counter)
    target_rows = []
    seen_targets = set()
    total_windows = 0
    source_game_room = {}
    for unit_name, manifest in sorted(g61["units"].items()):
        peer, room = unit_name.split("/", 1)
        if peer not in PEERS:
            raise ValueError("意外强手身份")
        source_path = _project_file(_PROJECT_ROOT, G61 / "rooms" / f"{peer}--{room}" / "result.json")
        if sha(source_path) != manifest["result_sha256"]:
            raise ValueError(f"G61 房结果摘要漂移：{unit_name}")
        selected_games = json.loads(source_path.read_text(encoding="utf-8"))["selected_games"]
        if len(selected_games) != 10:
            raise ValueError("G61 强手房不是十张完整桌")
        for game_id in selected_games:
            if game_id in source_game_room and source_game_room[game_id] != room:
                raise ValueError("G61 相同 game_id 被归入不同房")
            source_game_room[game_id] = room
        path = _project_file(_PROJECT_ROOT, G61 / "rooms" / f"{peer}--{room}" / "windows.json")
        if sha(path) != manifest["windows_sha256"]:
            raise ValueError(f"G61 窗口摘要漂移：{unit_name}")
        windows = json.loads(path.read_text(encoding="utf-8"))["windows"]
        if len(windows) != manifest["counts"]["legal_verified_windows"]:
            raise ValueError("G61 逐房合法窗口数漂移")
        total_windows += len(windows)
        for row in windows:
            if row["room_id"] != room:
                raise ValueError("G61 窗口房号漂移")
            obs = row["observation"]
            own = obs["melds"][obs["seat"]]
            if not any(meld["kind"] in ("chi", "peng") for meld in own):
                continue
            feature = features(row)
            group = cell(feature)
            stats = by_peer_room[(peer, room)]
            scope = by_cell_room[(peer, group, room)]
            stats["postclaim_draw_discards"] += 1
            scope["all"] += 1
            for name, value in feature.items():
                marginals[(peer, name, str(value))]["all"] += 1
            if row["parent_agrees"]:
                stats["parent_agrees"] += 1
                scope["parent_agrees"] += 1
            else:
                stats["parent_disagrees"] += 1
                scope["parent_disagrees"] += 1
            key = target_key(peer, room, row)
            target = targets.get(key)
            if target is None:
                continue
            if key in seen_targets:
                raise ValueError("G86 目标重复落到 G61 窗口")
            seen_targets.add(key)
            if (row["actual_action"] != target["strong_action"] or
                    row["parent_top_action"] != target["parent_action"] or
                    row["parent_agrees"] or
                    row["parent_score_gap_top_minus_actual"] != target["parent_score_gap"] or
                    obs["my_hand"].count("白") != target["white_before"] or
                    len(own) != target["own_meld_count"]):
                raise ValueError("G86 严格目标与 G61 行动前观察不符")
            wide = (target["ordinary_codes_delta"] > 0 and
                    target["ordinary_capacity_delta"] > 0)
            stats["strict_same_ordinary_shanten"] += 1
            scope["strict"] += 1
            scope["wide" if wide else "nonwide"] += 1
            if wide:
                stats["strict_wide_both"] += 1
            for name, value in feature.items():
                marginals[(peer, name, str(value))]["strict"] += 1
                marginals[(peer, name, str(value))]["wide"] += wide
            pair = discard_family(row["actual_action"]) + "_vs_" + discard_family(
                row["parent_top_action"])
            honor_pairs[peer][pair] += 1
            target_rows.append({
                "peer": peer, "room": room, "game_id": row["game_id"],
                "round_no": row["round_no"], "draw_seq": row["draw_seq"],
                "seat": row["seat"], "strong_action": row["actual_action"],
                "parent_action": row["parent_top_action"],
                "parent_score_gap": target["parent_score_gap"],
                "ordinary_codes_delta": target["ordinary_codes_delta"],
                "ordinary_capacity_delta": target["ordinary_capacity_delta"],
                "wide_both": wide, "feature": feature, "cell": group,
            })
    if total_windows != g61["totals"]["legal_verified_windows"] or total_windows != 17938:
        raise ValueError("G61 全量窗口数未对账")
    if seen_targets != set(targets):
        raise ValueError("G86 严格目标不全在 G61 已吃碰窗口")
    if Counter(row["peer"] for row in target_rows) != {
            "xuanwu_2346": 434, "tengshe_0638": 649}:
        raise ValueError("G86 分强手目标数漂移")

    # `rounds` 是 API 摘要；`blocks` 内每局的 round_ended 才可核八局完整性。
    # 这里单独审计当前去重官方来源，不把 7 项摘要误判成丢失第八局。
    if len(source_game_room) != 310:
        raise ValueError("G61 强手房不是 310 张不同官方桌")
    official_sources = []
    for _mtime, room, _tag, game_id, doc in load_rooms():
        if game_id not in source_game_room:
            continue
        if room != source_game_room[game_id]:
            raise ValueError("当前官方来源房号与 G61 不符")
        blocks = defaultdict(list)
        for block in doc.get("blocks") or []:
            blocks[block["round_no"]].append(block)
        if set(blocks) != set(range(1, 9)):
            raise ValueError("当前官方来源 blocks 非八局")
        for round_no, parts in blocks.items():
            endings = [event for part in parts for event in part.get("events") or []
                       if event.get("type") == "round_ended"]
            if len(endings) != 1:
                raise ValueError("当前官方来源单局终局非唯一")
            scores = (endings[0].get("data") or {}).get("scores")
            if not isinstance(scores, list) or len(scores) != 4 or sum(scores) != 0:
                raise ValueError("当前官方来源终局四座积分不守恒")
        summaries = doc.get("rounds") or []
        summary_rounds = [entry.get("round_no") for entry in summaries]
        if len(summaries) not in (7, 8) or len(summary_rounds) != len(set(summary_rounds)):
            raise ValueError("当前官方来源 rounds 摘要结构异常")
        official_sources.append({
            "game_id": game_id, "room": room,
            "payload_sha256": hashlib.sha256(json.dumps(
                doc, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
            "summary_round_count": len(summaries),
            "summary_missing_rounds": sorted(set(range(1, 9)) - set(summary_rounds)),
            "block_round_count": len(blocks),
            "rounds_with_unique_round_ended": len(blocks),
        })
    if {row["game_id"] for row in official_sources} != set(source_game_room):
        raise ValueError("当前官方来源缺 G61 冻结桌")
    official_sources.sort(key=lambda row: row["game_id"])
    summary_short = [row for row in official_sources if row["summary_round_count"] == 7]
    if len(summary_short) != 8:
        raise ValueError("当前官方来源摘要缺项桌数漂移")

    # 留一房只量其他房是否见过相近条件，不使用同房窗口自我支持。
    support_counts: dict[str, Counter] = defaultdict(Counter)
    for row in target_rows:
        peer, room, group = row["peer"], row["room"], row["cell"]
        others = [value for (name, domain, other_room), value in by_cell_room.items()
                  if name == peer and domain == group and other_room != room]
        other_all = sum(value["all"] for value in others)
        other_strict = sum(value["strict"] for value in others)
        other_wide = sum(value["wide"] for value in others)
        other_nonwide = sum(value["nonwide"] for value in others)
        other_strict_rooms = sum(value["strict"] > 0 for value in others)
        # 纯描述性覆盖口径，不参与拟合、选候选或发布门。
        supported = other_all >= 20 and other_strict >= 5 and other_strict_rooms >= 3
        row["leave_room_support"] = {
            "other_room_windows": other_all,
            "other_room_strict": other_strict,
            "other_rooms_with_strict": other_strict_rooms,
            "supported_20_5_3": supported,
            "other_room_has_both_wide_and_nonwide": other_wide > 0 and other_nonwide > 0,
        }
        tally = support_counts[peer]
        tally["strict"] += 1
        tally["supported_20_5_3"] += supported
        tally["wide"] += row["wide_both"]
        tally["wide_supported"] += row["wide_both"] and supported
        tally["other_room_both_directions"] += other_wide > 0 and other_nonwide > 0

    peer_summaries = {}
    for peer in PEERS:
        rooms = sorted(room for name, room in by_peer_room if name == peer)
        leader_by_room: dict[str, dict[str, Counter]] = defaultdict(
            lambda: defaultdict(Counter))
        for row in target_rows:
            if row["peer"] != peer:
                continue
            group = ("sole_leader" if row["feature"]["score_position"] == "sole_leader"
                     else "other")
            leader_by_room[row["room"]][group]["strict"] += 1
            leader_by_room[row["room"]][group]["wide"] += row["wide_both"]
        direction = Counter()
        for room in rooms:
            left = leader_by_room[room]["sole_leader"]
            right = leader_by_room[room]["other"]
            if not left["strict"] or not right["strict"]:
                direction["insufficient_both"] += 1
                continue
            leader_rate = left["wide"] / left["strict"]
            other_rate = right["wide"] / right["strict"]
            direction["more" if leader_rate > other_rate else
                      "less" if leader_rate < other_rate else "equal"] += 1
        peer_summaries[peer] = {
            "rooms": len(rooms),
            "counts": dict(sorted(sum((by_peer_room[(peer, room)] for room in rooms), Counter()).items())),
            "leave_room_support": dict(sorted(support_counts[peer].items())),
            "strict_discard_family_pairs": dict(sorted(honor_pairs[peer].items())),
            "sole_leader_vs_other_strict": {
                "sole_leader": dict(sum((leader_by_room[room]["sole_leader"]
                                          for room in rooms), Counter())),
                "other": dict(sum((leader_by_room[room]["other"]
                                    for room in rooms), Counter())),
                "room_wide_rate_direction": dict(sorted(direction.items())),
            },
        }
    result = {
        "schema": "g253-postclaim-residual-support/1",
        "exploratory": True,
        "outcome_labels_opened": False,
        "source_sha256": {
            "g61_result": sha(_project_file(_PROJECT_ROOT, G61 / "result.json")),
            "g86_result": sha(G86),
            "script": sha(Path(__file__)),
        },
        "denominator": {
            "g61_legal_normal_draw_windows": total_windows,
            "postclaim_normal_draw_windows": sum(
                value["postclaim_draw_discards"] for value in by_peer_room.values()),
            "strict_same_ordinary_shanten_targets": len(target_rows),
        },
        "official_source_audit": {
            "canonical_selector": "extract_room_scores.load_rooms，按 game_id 留当前 mtime 最新下载",
            "game_count": len(official_sources),
            "summary_7_count": len(summary_short),
            "summary_8_count": len(official_sources) - len(summary_short),
            "block_complete_8_count": len(official_sources),
            "summary_short_games": summary_short,
            "source_payload_sha256": {row["game_id"]: row["payload_sha256"]
                                      for row in official_sources},
        },
        "feature_contract": {
            "source": "G61 冻结 PlayerObservation，当前本人手牌/公开副露/墙余/桌分/规则公开状态",
            "core_cell_fields": ["white", "own_chi_peng_melds", "wall_remaining",
                                 "opponent_max_melds"],
            "excluded": ["G86 上次鸣牌至今摸牌次数", "G86 下一摸/他家先胡结果",
                         "官方终局积分", "他家暗手", "未来牌墙"],
            "support_definition": "留一房同强手同 cell 的其他房合计>=20正常窗口、>=5严格目标且严格目标覆盖>=3房；仅诊断覆盖。",
        },
        "peers": peer_summaries,
        "by_peer_room": [dict(peer=peer, room=room, counts=dict(sorted(counts.items())))
                         for (peer, room), counts in sorted(by_peer_room.items())],
        "feature_marginals": [dict(peer=peer, feature=name, value=value,
                                   counts=dict(sorted(counts.items())))
                              for (peer, name, value), counts in sorted(marginals.items())],
        "target_rows": sorted(target_rows, key=lambda row: (
            row["peer"], row["room"], row["game_id"], row["round_no"],
            row["draw_seq"], row["seat"])),
        "boundary": "同房强手的合法动作是行为标签而非最优收益标签；留一房有支持不表示动作价值可泛化。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"denominator": result["denominator"], "peers": peer_summaries},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
