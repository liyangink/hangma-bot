#!/usr/bin/env python3
"""P24 前置普查：自然样本上「弃胡机会窗」的逐层计数（全部规则判定经 hangma / RuleAnalysis）。

口径来源
--------
- 覆盖口径（P85/P86、预登记 §一）：父代 R18 v2 的 hu_vs_nonwealth_baotou_cf 覆盖的
  degrade_reason，以及 hu 是否仍是当前首选。
- 有靶口径（P19 review/baotou-anatomy-20260925）：是否存在一张合法弃牌 c 使 hangma 的
  baotou_after_discard(hand - c, melds) 为真（= 弃后即爆头）。
- 主审收紧 v2（池 A）：draw ∧ hu 合法 ∧ 父代选 hu ∧ 立刻胡番 == 1 ∧
  rule_state.baotou is False ∧ ∃ 非财神弃牌 c 使 baotou_after(c) 且 shanten_after == 0。
- 主审收紧 v3（最终池）：draw ∧ hu 合法 ∧ 父代选 hu ∧ 立刻胡番 == 1
  ∧ 不存在任何合法非财神弃牌 c 使 baotou_after(c)。

Part 1 在 8 房真实审计（1,120 局 / 32,374 窗口）上算；读数是**我自己的**重建：
复用 .team-work/p6-baotou-route/p6_lib.py 的冻结父代源码与 DecisionRequest 视图。
Part 2 在**全量自然样本 3,920 局**（官方牌谱）上算，用我自己的单座位暗牌重放；
所有向听/成胡/爆头/番值判定一律来自 hangma，并与 P19 冻结的 rounds.jsonl 逐窗对拍
（n_targets 与 targets 集合必须逐窗相等），以此自证重放口径与 P19 一致。
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p24-deferral-complement-01-20260925'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import collections
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT

for extra in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROOT / ".team-work" / "p6-baotou-route")):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from hangma_bot.hangma import hand_analysis  # noqa: E402
from hangma_bot.hangma.internal_types import TILE_ORDER  # noqa: E402
from hangma_bot.hangma.progression import (  # noqa: E402
    baotou_after_discard,
    baotou_after_draw,
    chain_after_discard,
    chain_after_gang,
)
from hangma_bot.hangma.settlement import compute_fan  # noqa: E402
from hangma_bot.kernel.actions import Tile  # noqa: E402

WEALTH = "白"


def kind_of(key):
    return key.split(":", 1)[0] if ":" in key else key


def tile_of(key):
    return key.split(":", 1)[1] if ":" in key else None


def chosen_entry(entries):
    return min(entries, key=lambda e: (-float(e["score"]), e["action_key"]))


def wealth_code(rule_state):
    raw = (rule_state or {}).get("wealth_god")
    if isinstance(raw, dict):
        return raw.get("code")
    return raw


# ---------------------------------------------------------------------------
# Part 1：8 房真实审计（DecisionRequest 口径）
# ---------------------------------------------------------------------------


def part_audit() -> dict:
    import p6_lib

    namespace = {"__name__": "frozen"}
    exec(compile(p6_lib.frozen_source(), "frozen", "exec"), namespace)
    parent = namespace["score_actions"]

    layers = collections.Counter()
    reasons = collections.Counter()
    hu_fans = collections.Counter()
    baotou_flags = collections.Counter()
    v2_pool_rows = []
    v3_pool_rows = []
    p19_pool_rows = []
    all_hu_rows = []

    for row in p6_lib.iter_rooms(p6_lib.ROOMS_PRIMARY + p6_lib.ROOMS_EXTRA):
        view = row["view"]
        layers["windows"] += 1
        try:
            scored = parent(view)
        except Exception:
            layers["score_error"] += 1
            continue
        entries = scored["entries"]
        if not entries:
            continue
        actions = {a["action_key"]: a for a in view["actions"]}
        if "hu" not in actions:
            continue
        layers["legal_hu"] += 1

        vis = view["visible_state"]
        rule_state = vis.get("rule_state") or {}
        wealth = wealth_code(rule_state)
        baotou_now = rule_state.get("baotou")
        hu_action = actions["hu"]
        settlement = hu_action.get("immediate_settlement") or {}
        hu_fan = settlement.get("fan")
        hu_fans[hu_fan] += 1
        baotou_flags[repr(baotou_now)] += 1

        chosen = chosen_entry(entries)
        took_hu = kind_of(chosen["action_key"]) == "hu"
        trace = (chosen.get("trace") or {}).get("hu_vs_nonwealth_baotou_cf") or {}
        reasons[str(trace.get("degrade_reason"))] += 1
        if took_hu:
            layers["chose_hu"] += 1
        elif kind_of(chosen["action_key"]) == "discard":
            layers["chose_discard"] += 1
        else:
            layers["chose_other"] += 1

        nonwealth_discards = []
        for key, action in actions.items():
            if action.get("action_type") != "discard":
                continue
            if wealth is not None and tile_of(key) == wealth:
                continue
            nonwealth_discards.append((key, action))
        layers["has_nonwealth_discard"] += bool(nonwealth_discards)

        broad = [k for k, a in nonwealth_discards if a.get("baotou_after") is True]
        tight = [k for k, a in nonwealth_discards
                 if a.get("baotou_after") is True and a.get("shanten_after") == 0]
        p19 = [k for k, a in actions.items()
               if a.get("action_type") == "discard" and a.get("baotou_after") is True]

        ctx = {
            "key": [row["game_id"], row["round_no"], row["trigger_seq"]],
            "room": row["room"], "run_id": row["run_id"],
            "hu_fan": hu_fan, "baotou_now": baotou_now, "wealth": wealth,
            "chose": chosen["action_key"], "seat": vis.get("seat"),
            "hand": list(vis.get("my_hand") or ()),
        }

        all_hu_rows.append({
            "game_id": row["game_id"], "round_no": row["round_no"],
            "seq": row["trigger_seq"], "seat": vis.get("seat"),
            "fan": hu_fan, "baotou": baotou_now,
            "hand": list(vis.get("my_hand") or ()),
            "drawn_tile": vis.get("drawn_tile"),
            "melds": vis.get("melds"),
            "phase": vis.get("phase"),
            "broad": sorted(tile_of(k) for k in broad),
            "tight": sorted(tile_of(k) for k in tight),
            "p19": sorted(tile_of(k) for k in p19),
            "chose": chosen["action_key"],
        })

        if p19:
            layers["p19_with_target"] += 1
            if took_hu:
                layers["p19_with_target_chose_hu"] += 1
                p19_pool_rows.append(dict(ctx, targets=p19))
        if broad:
            layers["has_nonwealth_broad_target"] += 1
            if took_hu:
                layers["broad_target_chose_hu"] += 1
        else:
            layers["no_nonwealth_broad_target"] += 1
            if took_hu:
                layers["v3_top_hu_no_target"] += 1
                if hu_fan == 1:
                    layers["V3_POOL_fan1"] += 1
                    v3_pool_rows.append(ctx)
        if tight:
            layers["has_tight_target"] += 1
            if took_hu:
                layers["tight_target_chose_hu"] += 1
                if hu_fan == 1 and baotou_now is False:
                    layers["V2_POOL_final"] += 1
                    v2_pool_rows.append(dict(ctx, targets=tight))

    return {
        "part": "audit-8-room",
        "layers": dict(sorted(layers.items())),
        "degrade_reason": dict(reasons.most_common()),
        "hu_fan_distribution": {str(k): v for k, v in sorted(
            hu_fans.items(), key=lambda kv: (kv[0] is None, kv[0]))},
        "rule_state_baotou_distribution": dict(baotou_flags),
        "all_hu_rows": all_hu_rows,
        "V3_POOL_rows": v3_pool_rows,
        "V2_POOL_rows": v2_pool_rows,
        "p19_pool_rows": p19_pool_rows,
    }


# ---------------------------------------------------------------------------
# Part 2：全量自然样本（官方牌谱重建）
# ---------------------------------------------------------------------------


def _tiles(counter):
    result = []
    for code in TILE_ORDER:
        result.extend([Tile(code)] * counter[code])
    return tuple(result)


def drop_tile(hand, code):
    held = list(hand)
    for index, tile in enumerate(held):
        if tile.code == code:
            del held[index]
            return tuple(held)
    return None


def replay_round(events, start_hands):
    """单局逐事件重放四家暗牌/副露/链/爆头，并记录「摸牌窗口已成胡」事实。

    扣减口径与 P19 anatomy_lib.reconstruct_round 逐字一致（摸 +1、弃 -1、
    碰 -2、吃扣被吃牌外两张、杠 明 3 / 暗 4 / 补 1）；全部规则量经 hangma。
    """

    hands = [collections.Counter(hand) for hand in start_hands]
    melds = [0, 0, 0, 0]
    baotou = [
        None if len(hand) == 14 else baotou_after_discard(_tiles(collections.Counter(hand)), 0)
        for hand in start_hands
    ]
    chain = [0, 0, 0, 0]
    piao = [0, 0, 0, 0]
    draws_n = [0, 0, 0, 0]
    hu_windows = []
    pending = None
    previous_event = None
    for event in events:
        kind = event["type"]
        seat = event.get("seat")
        tile = event.get("tile")
        data = event.get("data") or {}
        if kind == "round_ended":
            if pending is not None and pending["chosen"] is None:
                pending["chosen"] = "hu" if event.get("seat") == pending["seat"] else "none"
                pending = None
            break
        if kind in ("pass", "timeout"):
            previous_event = event
            continue
        if kind == "tile_drawn":
            replacement = (
                previous_event is not None
                and previous_event["type"] == "gang"
                and previous_event.get("seat") == seat
                and previous_event["seq"] == event["seq"] - 1
            )
            pre = _tiles(hands[seat])
            hands[seat][tile] += 1
            draws_n[seat] += 1
            baotou[seat] = baotou_after_draw(
                baotou[seat], pre, melds[seat], Tile(tile), replacement=bool(replacement))
            full = _tiles(hands[seat])
            if len(full) == 14 - 3 * melds[seat] and \
                    hand_analysis.win_split(full, melds[seat]) is not None:
                targets = []
                for code in sorted({t.code for t in full}):
                    after = drop_tile(full, code)
                    if after is not None and baotou_after_discard(after, melds[seat]):
                        targets.append(code)
                pending = {
                    "seat": seat, "seq": event["seq"], "turn": draws_n[seat] - 1,
                    "melds": melds[seat], "whites": hands[seat][WEALTH],
                    "baotou_after_draw": bool(baotou[seat]),
                    "targets": targets, "chosen": None, "hand": [t.code for t in full],
                    "chain": chain[seat], "piao": piao[seat],
                }
                hu_windows.append(pending)
        elif kind == "tile_discarded":
            if pending is not None and pending["seat"] == seat and pending["chosen"] is None:
                pending["chosen"] = "discard:" + str(tile)
                pending = None
            chain[seat], piao[seat] = chain_after_discard(
                chain[seat], piao[seat], bool(baotou[seat]), Tile(tile))
            hands[seat][tile] -= 1
            baotou[seat] = baotou_after_discard(_tiles(hands[seat]), melds[seat])
        elif kind == "peng":
            melds[seat] += 1
            hands[seat][tile] -= 2
        elif kind == "chi":
            consumed = list(data["tiles"])
            consumed.remove(tile)
            melds[seat] += 1
            for own in consumed:
                hands[seat][own] -= 1
        elif kind == "gang":
            gang_kind = data.get("kind")
            consumed = {"ming": 3, "an": 4, "bu": 1}.get(gang_kind)
            if consumed is None:
                raise ValueError("未知杠类别 %r" % (gang_kind,))
            if gang_kind != "bu":
                melds[seat] += 1
            hands[seat][tile] -= consumed
            chain[seat], piao[seat] = chain_after_gang(chain[seat], piao[seat])
        elif kind == "game_ended":
            pass
        else:
            raise ValueError("未知事件类型 %r" % (kind,))
        previous_event = event
    return hu_windows


def part_full(limit: int | None) -> dict:
    sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "review" / "baotou-anatomy-20260925")))
    import anatomy_lib as lib

    frozen = {}
    frozen_path = _project_file(_PROJECT_ROOT, ROOT / "review" / "baotou-anatomy-20260925" / "rounds.jsonl")
    with frozen_path.open(encoding="utf-8") as handle:
        for line in handle:
            rec = json.loads(line)
            frozen[(rec["game_id"], rec["round_no"])] = rec

    games = lib.load_games()
    games = [g for g in games
             if lib.ME in [s.get("user_id") for s in g["doc"].get("seats") or []]]
    if limit:
        games = games[:limit]

    me = lib.ME
    layers = collections.Counter()
    mismatch = collections.Counter()
    examples = []
    v2_rows = []
    me_hu_rows = []
    v2_by_room = collections.Counter()
    v3_by_room = collections.Counter()
    target_hu_fan = collections.Counter()
    for game in games:
        doc = game["doc"]
        seats = [s.get("user_id") for s in doc.get("seats") or []]
        my_seat = seats.index(me) if me in seats else None
        for round_no, events, start_hands in lib.round_blocks(doc):
            if not start_hands:
                layers["rounds_without_start_hands"] += 1
                continue
            try:
                windows = replay_round(events, start_hands)
            except ValueError:
                layers["replay_errors"] += 1
                continue
            record = frozen.get((game["game_id"], round_no))
            if record is None:
                mismatch["round_missing_in_frozen"] += 1
                continue
            recorded = []
            for seat_facts in record["seats"]:
                for item in seat_facts["hu_windows"]:
                    recorded.append((seat_facts["seat"], item))
            if len(recorded) != len(windows):
                mismatch["window_count"] += 1
                continue
            mine_sorted = sorted(windows, key=lambda w: (w["seq"], w["seat"]))
            theirs_sorted = sorted(recorded, key=lambda x: (x[1][0], x[0]))
            for (seat, item), mine in zip(theirs_sorted, mine_sorted):
                ok = (
                    seat == mine["seat"]
                    and item[0] == mine["seq"] and item[1] == mine["turn"]
                    and item[2] == mine["melds"] and item[3] == mine["whites"]
                    and bool(item[4]) == bool(mine["baotou_after_draw"])
                    and item[5] == len(mine["targets"])
                    and item[6] == mine["chosen"]
                    and item[7] == ",".join(mine["targets"])
                )
                if not ok:
                    mismatch["window_field"] += 1

            for window in windows:
                if window["seat"] != my_seat:
                    continue
                full = tuple(Tile(code) for code in window["hand"])
                split = hand_analysis.win_split(full, window["melds"])
                if split is None:
                    layers["replay_win_split_none"] += 1
                    continue
                fan = compute_fan(split, int(window["chain"]), int(window["piao"]),
                                  bool(window["baotou_after_draw"])).fan
                layers["me_hu_windows"] += 1
                layers["fan_" + str(fan)] += 1
                if window["chosen"] == "hu":
                    layers["me_chose_hu"] += 1
                elif str(window["chosen"]).startswith("discard"):
                    layers["me_chose_discard"] += 1
                else:
                    layers["me_chose_none"] += 1
                if bool(window["baotou_after_draw"]):
                    layers["me_already_baotou"] += 1
                nonwealth = sorted({code for code in window["hand"] if code != WEALTH})
                broad = [c for c in nonwealth
                         if baotou_after_discard(drop_tile(full, c), window["melds"])]
                tight = [c for c in broad
                         if hand_analysis.analyse_hand(
                             drop_tile(full, c), window["melds"]).shanten == 0]
                if broad:
                    layers["me_has_nonwealth_target"] += 1
                if tight:
                    layers["me_has_tight_target"] += 1
                me_hu_rows.append({
                    "game_id": game["game_id"], "round_no": round_no,
                    "seq": window["seq"], "seat": window["seat"], "fan": fan,
                    "baotou": bool(window["baotou_after_draw"]),
                    "hand": window["hand"], "broad": broad, "tight": tight,
                    "chose": window["chosen"],
                })
                if window["chosen"] != "hu":
                    continue
                if broad:
                    layers["me_target_chose_hu"] += 1
                    target_hu_fan["fan_" + str(fan)] += 1
                    v2_by_room[str(game.get("session"))] += 1
                if tight:
                    layers["me_tight_target_chose_hu"] += 1
                    if fan == 1 and not bool(window["baotou_after_draw"]):
                        layers["V2_POOL"] += 1
                        v2_rows.append({
                            "game_id": game["game_id"], "round_no": round_no,
                            "seq": window["seq"], "seat": window["seat"],
                            "fan": fan, "melds": window["melds"],
                            "whites": window["whites"], "baotou": False,
                            "hand": window["hand"], "targets": broad,
                            "room_id": str(game.get("session")),
                            "chosen": window["chosen"],
                        })
                if not broad:
                    layers["v3_top_hu_no_target"] += 1
                    if fan == 1:
                        layers["V3_POOL_fan1"] += 1
                        v3_by_room[str(game.get("session"))] += 1
                        if not bool(window["baotou_after_draw"]):
                            layers["V3_POOL_fan1_not_baotou"] += 1
                        if len(examples) < 6:
                            examples.append({
                                "game_id": game["game_id"], "round_no": round_no,
                                "seat": window["seat"], "seq": window["seq"],
                                "fan": fan, "melds": window["melds"],
                                "whites": window["whites"],
                                "baotou": bool(window["baotou_after_draw"]),
                                "hand": window["hand"],
                            })
    return {
        "part": "full-natural-audit",
        "games": len(games),
        "rounds": sum(layers[key] for key in ()) or None,
        "layers": dict(sorted(layers.items())),
        "frozen_mismatch": dict(sorted(mismatch.items())),
        "target_hu_fan_distribution": dict(sorted(target_hu_fan.items())),
        "V2_POOL_rows": v2_rows,
        "me_hu_rows": me_hu_rows,
        "V2_POOL_distinct_games": len({r["game_id"] for r in v2_rows}),
        "V2_POOL_distinct_rounds": len({(r["game_id"], r["round_no"]) for r in v2_rows}),
        "V2_POOL_by_room": dict(sorted(v2_by_room.items())),
        "V3_by_room": dict(sorted(v3_by_room.items())),
        "v3_fan1_examples": examples,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--part", choices=("audit", "full", "both"), default="both")
    parser.add_argument("--limit-games", type=int, default=0)
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    payload = {}
    if args.part in ("audit", "both"):
        payload["audit"] = part_audit()
    if args.part in ("full", "both"):
        payload["full"] = part_full(args.limit_games or None)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    target = Path(args.out) if args.out else _project_file(_PROJECT_ROOT, HERE / "census.json")
    target.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
