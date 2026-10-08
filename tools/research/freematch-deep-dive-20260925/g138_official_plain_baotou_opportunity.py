#!/usr/bin/env python3
"""G138：从已核同房行动前观察计算普通型爆头机会与实际保留。"""

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
import g61_strong_draw_batch as g61
import g69_route_chain_analysis as g69
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G138-OFFICIAL-PLAIN-BAOTOU-OPPORTUNITY-PREREG-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g138-official-plain-baotou-opportunity-20260928/result.json')
KINDS = ("plain", "plain_baotou", "seven_pairs_baotou")


def sha(path: Path) -> str:
    """冻结输入文件的原始字节摘要。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def win_kind(details: tuple[str, ...], fan: int) -> str | None:
    """按生产条件结算明细互斥分类；其他特殊胡不混入目标族。"""
    if details == ("平胡",) and fan == 1:
        return "plain"
    if details and details[0] == "平胡" and "爆头" in details:
        return "plain_baotou"
    if (details and (details[0] == "七对" or details[0].startswith("豪华七对×"))
            and "爆头" in details):
        return "seven_pairs_baotou"
    return None


def action_opportunity(candidate) -> tuple[dict[str, int], bool]:
    """只读当前合法弃牌的一摸条件路线；返回公开容量与完整性。"""
    value = candidate.value_facts
    if value is None:
        return {kind: 0 for kind in KINDS}, False
    capacities = {kind: 0 for kind in KINDS}
    seen: set[str] = set()
    for route in value.routes:
        if route.followup_discard is not None or route.conditions.draw_kind != "normal":
            raise ValueError("G138 正常弃牌含非一次普通摸牌条件路线")
        kind = win_kind(route.conditional_settlement.details,
                        route.conditional_settlement.fan)
        for tile in route.useful_tiles:
            if (tile.code in seen or type(tile.remaining_estimate) is not int
                    or not 0 <= tile.remaining_estimate <= 4):
                raise ValueError("G138 条件路线牌码重复或公开容量非法")
            seen.add(tile.code)
            if kind is not None:
                capacities[kind] += tile.remaining_estimate
    return capacities, value.coverage.value == "complete"


def window(row: dict, *, peer: str, actor: str, room: str) -> dict:
    """重算本座当前观察；未来墙及对手暗牌均不进入规则输入。"""
    observation = observation_from_json(row["observation"])
    if (observation.game_id != row["game_id"] or observation.round_no != row["round_no"]
            or observation.seat != row["seat"] or observation.snapshot_seq != row["draw_seq"]
            or row["room_id"] != room or observation.phase != "draw"):
        raise ValueError("G138 重建动作窗身份漂移")
    rules = c31.RULES.analyze(observation, value_limits=c31.VALUE_LIMITS)
    legal = {candidate.action_key: candidate for candidate in rules.legal_candidates}
    discards = {key: candidate for key, candidate in legal.items()
                if key.startswith("discard:")}
    actual = row["actual_action"]
    if actual not in discards or len(legal) != len(rules.legal_candidates):
        raise ValueError("G138 官方已接受弃牌不是当前规则合法动作")
    facts = {key: action_opportunity(candidate)
             for key, candidate in discards.items()}
    if not facts[actual][1]:
        raise ValueError("G138 实际弃牌条件见证不完整，需单列来源覆盖")
    opportunity = {}
    actual_kept = {}
    for kind in KINDS:
        if any(capacity[kind] > 0 for capacity, _complete in facts.values()):
            opportunity[kind] = "yes"
        elif all(complete for _capacity, complete in facts.values()):
            opportunity[kind] = "no"
        else:
            opportunity[kind] = "unknown"
        actual_kept[kind] = facts[actual][0][kind] > 0
        if actual_kept[kind] and opportunity[kind] != "yes":
            raise ValueError("G138 实际保留机会不属于合法机会")
    seat = observation.seat
    chosen_shape = discards[actual].facts
    return {"peer": peer, "actor": actor, "room": room,
            "game_id": row["game_id"], "round_no": row["round_no"],
            "draw_seq": row["draw_seq"],
            "action_ordinal": len(observation.discards[seat]) + 1,
            "white_before": sum(tile.code == "白" for tile in observation.my_hand),
            "own_meld_count": len(observation.melds[seat]),
            "chosen_standard_shanten": (
                None if chosen_shape is None else chosen_shape.standard_shanten_after),
            "chosen_seven_pairs_shanten": (
                None if chosen_shape is None else chosen_shape.seven_pairs_shanten_after),
            "legal_discard_count": len(discards),
            "partial_legal_discard_count": sum(not complete for _, complete in facts.values()),
            "opportunity": opportunity, "actual_kept": actual_kept}


def add_window(counter: Counter, row: dict) -> None:
    """行动窗数量仅作为暴露，不作为独立效果样本。"""
    counter["windows"] += 1
    counter["partial_legal_discard_windows"] += row["partial_legal_discard_count"] > 0
    for kind in KINDS:
        state = row["opportunity"][kind]
        counter[kind + "/opportunity_" + state] += 1
        counter[kind + "/actual_kept"] += row["actual_kept"][kind]
        counter[kind + "/offered_but_not_kept"] += (
            state == "yes" and not row["actual_kept"][kind])


def add_hand(counter: Counter, rows: list[dict], expected_windows: int) -> None:
    """按官方单局汇总首次机会；未覆盖窗口不当作无机会。"""
    counter["hands"] += 1
    if len(rows) != expected_windows:
        raise ValueError("G138 本座正常摸打数量与 G69 已核单局不符")
    if not rows:
        counter["hands_without_observed_normal_draw"] += 1
        return
    counter["hands_with_observed_normal_draw"] += 1
    for kind in KINDS:
        offered = [r for r in rows if r["opportunity"][kind] == "yes"]
        unknown = any(r["opportunity"][kind] == "unknown" for r in rows)
        kept = [r for r in rows if r["actual_kept"][kind]]
        counter[kind + "/hands_offered"] += bool(offered)
        counter[kind + "/hands_kept"] += bool(kept)
        counter[kind + "/hands_offered_never_kept"] += bool(offered) and not kept
        counter[kind + "/hands_unknown_without_offer"] += not offered and unknown
        if offered:
            first = min(r["action_ordinal"] for r in offered)
            counter[kind + ("/first_offered_le6" if first <= 6 else
                            "/first_offered_ge7")] += 1


def main() -> None:
    """全量 32 强手×房单元、双方行动窗复算并与 G69 单局对账。"""
    if OUT.exists():
        raise FileExistsError("G138 已有证据，拒绝覆盖")
    source_g61 = json.loads((g61.OUT / "result.json").read_text(encoding="utf-8"))
    source_g69 = json.loads((g69.G69 / "batch_result.json").read_text(encoding="utf-8"))
    old_route = json.loads(g69.RESULT.read_text(encoding="utf-8"))
    if (source_g61["outcome_labels_opened"] is not False
            or len(source_g61["units"]) != 32
            or source_g69["completed_rooms"] != 31 or source_g69["errors"]
            or old_route["window_count"] != 36080
            or old_route["round_count"] != 5120):
        raise ValueError("G138 旧行动前源母体不符")
    units = [tuple(key.split("/", 1)) for key in sorted(source_g61["units"])]
    known_hands = {}
    with gzip.open(g69.ROUNDS, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            key = (row["peer"], row["room"], row["game_id"],
                   row["round_no"], row["actor"])
            if key in known_hands:
                raise ValueError("G138 G69 单局身份重复")
            known_hands[key] = row
    if len(known_hands) != 5120:
        raise ValueError("G138 G69 单局数不足")
    grouped: dict[tuple[str, str, str, int, str], list[dict]] = defaultdict(list)
    window_groups: dict[str, Counter] = defaultdict(Counter)
    room_window_groups: dict[str, Counter] = defaultdict(Counter)
    seen = set()
    for peer, room in units:
        strong_path = g61.room_dir((peer, room)) / "windows.json"
        us_path = g69.G69 / "rooms" / room / "windows.json.gz"
        sources = (("peer", strong_path,
                    source_g61["units"][peer + "/" + room]["windows_sha256"]),
                   ("us", us_path, source_g69["rooms"][room]["windows_sha256"]))
        for actor, path, expected_sha in sources:
            raw, observed_sha = g69.load_windows(path)
            if observed_sha != expected_sha:
                raise ValueError("G138 行动前逐窗来源摘要漂移")
            for source in raw:
                result = window(source, peer=peer, actor=actor, room=room)
                key = (peer, room, result["game_id"], result["round_no"], actor)
                marker = key + (result["draw_seq"],)
                if marker in seen or key not in known_hands:
                    raise ValueError("G138 行动窗重复或单局不在冻结母体")
                seen.add(marker)
                grouped[key].append(result)
                axes = (peer + "/" + actor + "/all",
                        peer + "/" + actor + "/white_" +
                        ("2plus" if result["white_before"] >= 2 else
                         str(result["white_before"])),
                        peer + "/" + actor + "/meld_" +
                        ("yes" if result["own_meld_count"] else "no"),
                        peer + "/" + actor + "/turn_" +
                        ("le6" if result["action_ordinal"] <= 6 else "ge7"))
                for name in axes:
                    add_window(window_groups[name], result)
                add_window(room_window_groups[peer + "/" + room + "/" + actor], result)
    if len(seen) != 36080:
        raise ValueError("G138 行动窗总数与 G69 不符")
    hand_groups: dict[str, Counter] = defaultdict(Counter)
    room_hand_groups: dict[str, Counter] = defaultdict(Counter)
    first_plain_baotou_rows = []
    for key, prior in known_hands.items():
        peer, room, _game, _round, actor = key
        rows = sorted(grouped.get(key, []), key=lambda row: row["draw_seq"])
        name = peer + "/" + actor
        add_hand(hand_groups[name], rows, prior["clean_windows"])
        add_hand(room_hand_groups[peer + "/" + room + "/" + actor],
                 rows, prior["clean_windows"])
        first_index = next((index for index, row in enumerate(rows)
                            if row["opportunity"]["plain_baotou"] == "yes"), None)
        if first_index is not None:
            current = rows[first_index]
            previous = rows[first_index - 1] if first_index else None
            first_plain_baotou_rows.append({
                "peer": peer, "room": room, "game_id": key[2],
                "round_no": key[3], "actor": actor,
                "first_draw_seq": current["draw_seq"],
                "first_action_ordinal": current["action_ordinal"],
                "first_white_before": current["white_before"],
                "first_meld_count": current["own_meld_count"],
                "first_chosen_standard_shanten": current["chosen_standard_shanten"],
                "previous_normal_draw": None if previous is None else {
                    "draw_seq": previous["draw_seq"],
                    "action_ordinal": previous["action_ordinal"],
                    "white_before": previous["white_before"],
                    "meld_count": previous["own_meld_count"],
                    "chosen_standard_shanten": previous["chosen_standard_shanten"],
                    "chosen_seven_pairs_shanten": previous["chosen_seven_pairs_shanten"],
                },
            })
    for peer, room in units:
        for actor in ("peer", "us"):
            if room_hand_groups[peer + "/" + room + "/" + actor]["hands"] != 80:
                raise ValueError("G138 单位房不足八十个单局")
    if sum(value["hands"] for value in hand_groups.values()) != 5120:
        raise ValueError("G138 同房双方单局数不守恒")
    result = {"schema": "g138-official-plain-baotou-opportunity/1",
              "inputs_sha256": {"g61_result": sha(g61.OUT / "result.json"),
                                "g69_batch": sha(g69.G69 / "batch_result.json"),
                                "g69_route": sha(g69.RESULT),
                                "g69_rounds": sha(g69.ROUNDS),
                                "prereg": sha(PREREG),
                                "script": sha(Path(__file__)),
                                "hangma_rules": sha(_project_file(_PROJECT_ROOT, HERE.parents[1] /
                                                    "src/hangma_bot/hangma/value_analysis.py"))},
              "strong_room_units": len(units), "distinct_rooms": len({r for _, r in units}),
              "normal_draw_discard_windows": len(seen), "actor_hands": len(known_hands),
              "first_plain_baotou_rows": sorted(first_plain_baotou_rows,
                  key=lambda row: (row["peer"], row["room"], row["game_id"],
                                   row["round_no"], row["actor"])),
              "window_groups": {k: dict(sorted(v.items())) for k, v in sorted(window_groups.items())},
              "room_window_groups": {k: dict(sorted(v.items()))
                                     for k, v in sorted(room_window_groups.items())},
              "hand_groups": {k: dict(sorted(v.items())) for k, v in sorted(hand_groups.items())},
              "room_hand_groups": {k: dict(sorted(v.items()))
                                   for k, v in sorted(room_hand_groups.items())},
              "boundary": "只在正常摸打可重建子集比较下一次本人普通自摸的公开容量；"
                          "公开容量不是牌墙概率，实际行为不是候选因果收益。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True,
                              indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"windows": len(seen), "actor_hands": len(known_hands),
                      "hand_groups": result["hand_groups"]},
                     ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
