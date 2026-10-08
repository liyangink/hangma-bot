#!/usr/bin/env python3
"""C34：跟打那张牌是不是被漏掉的价值（只读分析）。

口径、判据与判定三态**冻结**在 C34-PREREG-FOLLOWUP-DISCARD.md（本脚本编写前落盘，运行中不改）。

纪律（根 AGENTS.md §5）：
* 不实现任何规则——吃碰杠扣减只做机械状态搬运，向听/听牌/爆头/成胡全部经 hangma；
* 生产侧事实走生产同一条接缝（hangma.engine.HangmaRules.analyze + 生产观察构造），不另写第二套；
* 信息权限：只读官方牌谱 events.json、公开周榜快照、既有 rounds.jsonl 与 p6 生产视图缓存；
* 不写主树 src/、不合并 worktree、不发网络请求、不做 git commit。

用法：
    PYTHONPATH=$PWD/src UV_CACHE_DIR=/tmp/uv-cache .venv/bin/python \
        review/freematch-deep-dive-20260925/c34_followup_audit.py
    C34_LIMIT=20 …   # 只跑前 20 场（冒烟，不得用于结论）
"""

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

import collections
import glob
import gzip
import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = _PROJECT_ROOT
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "review" / "baotou-anatomy-20260925")))
sys.path.insert(0, str(HERE))

import anatomy_lib as AL  # noqa: E402
import c23_claim_opportunity as C23  # noqa: E402
import c31_action_layer_gap as C31  # noqa: E402
import stats_lib as SL  # noqa: E402

from hangma_bot.hangma import hand_analysis, progression  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.hangma.internal_types import TILE_ORDER  # noqa: E402
from hangma_bot.kernel.actions import Chi, Peng, Tile  # noqa: E402
from hangma_bot.kernel.config import RuleConfig  # noqa: E402

OUT = _project_file(_PROJECT_ROOT, ROOT / ".team-work" / "c34-followup")
ROUNDS_JSONL = _project_file(_PROJECT_ROOT, 'review/baotou-anatomy-20260925/rounds.jsonl')
P6_CACHE_GLOB = str(_project_file(_PROJECT_ROOT, ROOT / ".team-work" / "p6-baotou-route" / "cache" / "*.jsonl.gz"))

ME = AL.ME
WEALTH = AL.WEALTH
WALL_TOTAL = 136
TILE_INDEX = {code: index for index, code in enumerate(TILE_ORDER)}
GROUPS = ("me", "elite", "other")
PENG_CHI = ("peng", "chi")
GANG_KINDS = ("gang_ming", "gang_an", "gang_bu")
BOOTSTRAP_DRAWS = 10000
BOOTSTRAP_SEED = 20260926

RULES = HangmaRules(RuleConfig(
    ruleset_version="hangma-mvp-v10-public-counts", base_score=1, you_cai_bi_kao=False))
"""与 R18 v2 发布包声明逐项一致（r18_integrated_positive_v2_release.py:64-67）。"""

READ_PATHS = []
"""本脚本实际读取的文件路径（泄漏检查用）。"""


# ---------------------------------------------------------------------------
# 事件流：鸣牌 → 跟打窗配对（机械搬运，不涉及规则）
# ---------------------------------------------------------------------------


def find_followups(events):
    """每个鸣牌事件之后的「第一张本人打出的牌」窗口。

    返回 (pairs, anomalies)。pair 字段：
      claim_index/claim_seq/claim_type/claim_seat/claim_tile/claim_tiles（吃）
      follow_index/follow_seq/follow_tile/draws_between/chained_claims
    规则依据：吃/碰后该座**必须立刻打牌**；杠后先补一张再打。
    这里只把「中间插了什么」如实记下来，是否算「跟打」由口径决定（预登记 §3）。
    """

    pairs = []
    anomalies = collections.Counter()
    for index, event in enumerate(events):
        kind = event["type"]
        if kind not in ("peng", "chi", "gang"):
            continue
        seat = event.get("seat")
        if not isinstance(seat, int):
            anomalies["claim_without_seat"] += 1
            continue
        if kind == "gang":
            gang_kind = (event.get("data") or {}).get("kind")
            claim_type = {"ming": "gang_ming", "an": "gang_an",
                          "bu": "gang_bu"}.get(gang_kind)
            if claim_type is None:
                anomalies["unknown_gang_kind"] += 1
                continue
        else:
            claim_type = kind
        # 触发这张鸣牌的弃牌 seq（生产观察按该弃牌的快照构造）
        trigger_seq = None
        back = index - 1
        while back >= 0:
            item = events[back]
            if item["type"] in ("pass", "timeout"):
                back -= 1
                continue
            if item["type"] == "tile_discarded":
                trigger_seq = item.get("seq")
            break
        cursor = index + 1
        draws = 0
        chained = 0
        outcome = None
        while cursor < len(events):
            nxt = events[cursor]
            ntype = nxt["type"]
            if ntype in ("pass", "timeout"):
                cursor += 1
                continue
            if ntype == "tile_drawn" and nxt.get("seat") == seat and draws < 2:
                draws += 1
                cursor += 1
                continue
            if ntype == "tile_discarded" and nxt.get("seat") == seat:
                outcome = ("discard", cursor)
                break
            if ntype in ("peng", "chi", "gang") and nxt.get("seat") == seat:
                # 同一座连续鸣牌（杠后补牌成新杠/碰→杠链）：继续找最后那一次的跟打。
                chained += 1
                cursor += 1
                continue
            if ntype in ("round_ended", "game_ended"):
                outcome = ("round_ended", cursor)
                break
            outcome = ("other:" + str(ntype), cursor)
            break
        if outcome is None:
            anomalies["stream_exhausted:" + claim_type] += 1
            continue
        if outcome[0] != "discard":
            anomalies["no_followup:" + claim_type + ":" + outcome[0]] += 1
            continue
        follow = events[outcome[1]]
        pairs.append({
            "claim_index": index,
            "claim_seq": event.get("seq"),
            "trigger_seq": trigger_seq,
            "claim_type": claim_type,
            "claim_seat": seat,
            "claim_tile": event.get("tile"),
            "claim_tiles": tuple(sorted((event.get("data") or {}).get("tiles") or [])),
            "follow_index": outcome[1],
            "follow_seq": follow.get("seq"),
            "follow_tile": follow.get("tile"),
            "draws_between": draws,
            "chained_claims": chained,
        })
    return pairs, anomalies


def _tiles(counter):
    result = []
    for code in TILE_ORDER:
        result.extend([Tile(code)] * counter[code])
    return tuple(result)


def drop_code(hand, code):
    """从牌元组里去掉首个同码实例；没有该码返回 None（不猜）。"""

    held = list(hand)
    for index, tile in enumerate(held):
        if tile.code == code:
            del held[index]
            return tuple(held)
    return None


def judge_window(hand_before, melds, actual_code):
    """跟打窗的爆头事实（全部经 hangma；不设 is_win 门槛，暴力枚举全部合法跟打）。

    hand_before = 该座此刻的暗牌（14 − 3×副露 张），melds = 鸣牌后的副露数。
    """

    distinct = sorted({tile.code for tile in hand_before}, key=TILE_INDEX.get)
    is_win = hand_analysis.win_split(hand_before, melds) is not None
    targets = []
    for code in distinct:
        after = drop_code(hand_before, code)
        if after is None:
            continue
        if progression.baotou_after_discard(after, melds):
            targets.append(code)
    return {
        "distinct": distinct,
        "is_win": bool(is_win),
        "targets": targets,
        "achievable": bool(targets),
        "achieved": actual_code in targets,
        "n_targets": len(targets),
    }


# ---------------------------------------------------------------------------
# 生产侧事实（走生产同一条接缝）
# ---------------------------------------------------------------------------


def _claim_phase(claim_type):
    if claim_type in ("peng", "gang_ming"):
        return "response_peng"
    if claim_type == "chi":
        return "response_chi"
    return None


def production_followup(snap, claim, game_id, round_no, hand_before, melds):
    """生产侧 best_followup_discard 与全部分支事实；返回 (record, reason)。

    走 HangmaRules.analyze（线上唯一事实生产者），不复制 _followup_branches 的择优。
    """

    phase = _claim_phase(claim["claim_type"])
    if phase is None:
        return None, "phase_not_applicable"
    try:
        observation = C31.build_observation(snap, claim["claim_seat"], phase,
                                             game_id, round_no)
    except Exception as exc:  # noqa: BLE001
        return None, "observation_failed:" + type(exc).__name__
    try:
        analysis = RULES.analyze(observation)
    except Exception as exc:  # noqa: BLE001
        return None, "analyze_failed:" + type(exc).__name__

    wanted = None
    for candidate in analysis.legal_candidates:
        action = candidate.action
        if claim["claim_type"] == "peng" and isinstance(action, Peng) \
                and action.tile.code == claim["claim_tile"]:
            wanted = candidate
            break
        if claim["claim_type"] == "chi" and isinstance(action, Chi) \
                and tuple(sorted(tile.code for tile in action.tiles)) == claim["claim_tiles"]:
            wanted = candidate
            break
    if wanted is None or wanted.facts is None:
        return None, "claim_candidate_missing"
    facts = wanted.facts
    branches = facts.followup_branches
    if branches is None or facts.best_followup_discard is None:
        return None, "no_followup_facts"

    branch_codes = tuple(branch.followup_discard for branch in branches)
    match = sorted(branch_codes) == sorted({tile.code for tile in hand_before})

    rows = []
    for branch in branches:
        after = drop_code(hand_before, branch.followup_discard)
        baotou = None if after is None else bool(
            progression.baotou_after_discard(after, melds))
        support = branch.support_remaining
        rows.append({
            "code": branch.followup_discard,
            "shanten": branch.combined_shanten,
            "support": support,
            "baotou": baotou,
        })
    prod_pick = facts.best_followup_discard
    prod_pick_baotou = next((row["baotou"] for row in rows if row["code"] == prod_pick), None)

    def weight_of(row):
        support = row["support"]
        return support if isinstance(support, int) and not isinstance(support, bool) else -1

    def first_key(row):
        return (0 if row["baotou"] is True else 1, row["shanten"], -weight_of(row),
                TILE_INDEX.get(row["code"], 99))

    ordered = sorted(rows, key=first_key)
    first_pick = ordered[0]["code"] if ordered else None
    prod_row = next((row for row in rows if row["code"] == prod_pick), None)
    prod_key = None if prod_row is None else (
        prod_row["shanten"], -weight_of(prod_row), TILE_INDEX.get(prod_row["code"], 99))
    return {
        "action_key": wanted.action_key,
        "branch_codes_match": bool(match),
        "n_branches": len(rows),
        "branches": rows,
        "prod_pick": prod_pick,
        "prod_pick_baotou": prod_pick_baotou,
        "prod_key": prod_key,
        "baotou_first_pick": first_pick,
        "change": first_pick != prod_pick,
        "n_baotou_branches": sum(1 for row in rows if row["baotou"] is True),
    }, None


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def scan(limit=0):
    rows_jsonl = [json.loads(line) for line in ROUNDS_JSONL.open(encoding="utf-8")
                  if line.strip()]
    READ_PATHS.append(str(ROUNDS_JSONL))
    primary = {(row["game_id"], row["round_no"]) for row in rows_jsonl}
    board, board_path = C23.load_board()
    READ_PATHS.append(board_path)

    games = AL.load_games()
    READ_PATHS.extend(game["path"] for game in games)
    if limit:
        games = games[:limit]
    corpus = {
        "games": len(games),
        "game_ids_sha256": hashlib.sha256(
            "\n".join(sorted(game["game_id"] for game in games)).encode("utf-8")
        ).hexdigest(),
        "truncated_blocks": sum(
            1 for game in games for block in (game["doc"].get("blocks") or [])
            if block.get("truncated")),
        "sessions": dict(collections.Counter(game["session"] for game in games)),
        "primary_rounds": len(primary),
        "rounds_with_start_hands": 0,
    }
    print("语料：%d 场（主语料局 %d / 榜标签 %d 人）"
          % (len(games), len(primary), len(board)))

    windows = []
    counters = collections.Counter()
    fidelity = collections.Counter()
    denominators = collections.Counter()
    started = time.time()

    for position, game in enumerate(games):
        doc = game["doc"]
        room = doc.get("room_id") or game["session"]
        users = [item.get("user_id") for item in (doc.get("seats") or [])]
        dealers = {}
        for block in doc.get("blocks") or []:
            if block.get("dealer") is not None:
                dealers.setdefault(block["round_no"], block["dealer"])
        for round_no, events, start_hands in AL.round_blocks(doc):
            if not start_hands or not all(isinstance(hand, list) for hand in start_hands):
                counters["round_without_start_hands"] += 1
                continue
            corpus["rounds_with_start_hands"] += 1
            dealer = dealers.get(round_no)
            in_primary = (game["game_id"], round_no) in primary
            # C31 的「主语料」= rounds.jsonl **且该局含强手**（A.0 自检锚点用）
            has_elite = any(users[seat] in board for seat in range(min(4, len(users))))
            pairs, anomalies = find_followups(events)
            for key, value in anomalies.items():
                counters["anomaly:" + key] += value
            if not pairs:
                continue
            # —— 分母（C23 机会窗口径，与已发布读数逐位可比）——
            round_summary, _audit, _verbose = C23.scan_round(events, start_hands)
            for seat in range(4):
                user = users[seat] if seat < len(users) else None
                group = "me" if user == ME else ("elite" if user in board else "other")
                denominators["opp:" + group] += round_summary["opp_a"][seat]
                denominators["base:" + group] += round_summary["base_a"][seat]
                denominators["claims:" + group] += round_summary["claims"][seat]
                if in_primary:
                    denominators["opp_primary:" + group] += round_summary["opp_a"][seat]
                if in_primary and has_elite:
                    denominators["opp_c31_primary:" + group] += round_summary["opp_a"][seat]
                    denominators["claims_c31_primary:" + group] += round_summary["claims"][seat]
            # —— 两条独立重建：anatomy_lib（跟打窗锚点）与 C31（生产观察）——
            recon = AL.reconstruct_round(events, start_hands)
            if recon["errors"]:
                counters["recon_errors"] += len(recon["errors"])
                fidelity["rounds_with_recon_errors"] += 1
            al_windows = {item["seq"]: item for item in recon["discard_windows"]}
            snaps = C31.reconstruct(events, start_hands, [0, 0, 0, 0],
                                    dealer if dealer is not None else 0)
            for pair in pairs:
                seat = pair["claim_seat"]
                user = users[seat] if seat < len(users) else None
                group = "me" if user == ME else ("elite" if user in board else "other")
                al_window = al_windows.get(pair["follow_seq"])
                if al_window is None:
                    counters["al_window_missing:" + pair["claim_type"]] += 1
                    continue
                snap = snaps.get(pair["follow_seq"])
                if snap is None:
                    counters["snap_missing:" + pair["claim_type"]] += 1
                    continue
                hand_before = al_window["hand_before"]
                melds = al_window["meld_count"]
                # 保真度：C31 的暗牌 + 打出的那张，与 anatomy_lib 的 hand_before 逐位对拍
                from_snap = _tiles(snap["hands"][seat]) + (Tile(pair["follow_tile"]),)
                fidelity["windows_compared"] += 1
                if sorted(tile.code for tile in from_snap) != sorted(
                        tile.code for tile in hand_before):
                    fidelity["hand_mismatch"] += 1
                    continue
                if len(hand_before) != 14 - 3 * melds:
                    counters["bad_hand_size:" + pair["claim_type"]] += 1
                    continue
                facts = judge_window(hand_before, melds, pair["follow_tile"])
                if facts["achievable"] and not facts["is_win"]:
                    fidelity["necessity_violation"] += 1
                # anatomy_lib 自己的同一判定（独立实现对拍）
                reach = al_window["reach"]
                fidelity["judge_compared"] += 1
                if (bool(reach["is_win"]) != facts["is_win"]
                        or (reach["n_targets"] > 0) != facts["achievable"]
                        or reach["n_targets"] != facts["n_targets"]
                        or bool(reach["chosen_target"]) != facts["achieved"]):
                    fidelity["judge_mismatch"] += 1

                if pair["claim_type"] in PENG_CHI:
                    # 「净跟打」= 吃/碰之后到本人打牌之间没有补牌、没有同座再鸣牌
                    followup_kind = ("plain" if pair["draws_between"] == 0
                                     and pair["chained_claims"] == 0 else "chained")
                else:
                    followup_kind = "gang"
                record = {
                    "followup_kind": followup_kind,
                    "game_id": game["game_id"], "room": room, "session": game["session"],
                    "round_no": round_no, "primary": in_primary, "dealer": dealer,
                    "seat": seat, "user_id": user, "group": group,
                    "claim_type": pair["claim_type"], "claim_seq": pair["claim_seq"],
                    "claim_tile": pair["claim_tile"], "claim_tiles": pair["claim_tiles"],
                    "trigger_seq": pair["trigger_seq"],
                    "follow_seq": pair["follow_seq"], "discard": pair["follow_tile"],
                    "melds": melds, "hand_codes": sorted(tile.code for tile in hand_before),
                    "n_concealed": len(hand_before),
                    "is_win": facts["is_win"], "achievable": facts["achievable"],
                    "achieved": facts["achieved"], "n_targets": facts["n_targets"],
                    "targets": facts["targets"],
                    "draws_between": pair["draws_between"],
                    "chained_claims": pair["chained_claims"],
                    "turn": al_window["turn"],
                    "al_origin": al_window["origin"],
                    "whites_held": al_window["whites_held"],
                    "discard_is_white": pair["follow_tile"] == WEALTH,
                    "is_dealer": (dealer == seat) if dealer is not None else None,
                    "wall_remaining": WALL_TOTAL - sum(
                        sum(snap["hands"][index].values()) for index in range(4))
                    - sum(len(river) for river in snap["rivers"])
                    - sum(len(group["tiles"]) for row in snap["melds"] for group in row),
                }
                if followup_kind == "plain":
                    claim_snap = snaps.get(pair["trigger_seq"])
                    if claim_snap is None:
                        counters["claim_snap_missing"] += 1
                        prod, reason = None, "claim_snap_missing"
                    else:
                        prod, reason = production_followup(
                            claim_snap, pair, game["game_id"], round_no,
                            hand_before, melds)
                    if prod is None:
                        record["prod_error"] = reason
                        counters["prod_error:" + reason] += 1
                    else:
                        record.update({
                            "prod_action_key": prod["action_key"],
                            "branch_codes_match": prod["branch_codes_match"],
                            "n_branches": prod["n_branches"],
                            "prod_pick": prod["prod_pick"],
                            "prod_pick_baotou": prod["prod_pick_baotou"],
                            "prod_key": prod["prod_key"],
                            "baotou_first_pick": prod["baotou_first_pick"],
                            "change": prod["change"],
                            "n_baotou_branches": prod["n_baotou_branches"],
                            "branch_baotou": {row["code"]: row["baotou"]
                                              for row in prod["branches"]},
                            "branch_shanten": {row["code"]: row["shanten"]
                                               for row in prod["branches"]},
                            "branch_support": {row["code"]: row["support"]
                                               for row in prod["branches"]},
                            "actual_eq_prod_pick": (prod["prod_pick"] == pair["follow_tile"]),
                        })
                        counters["prod_ok"] += 1
                        if not prod["branch_codes_match"]:
                            counters["branch_codes_mismatch"] += 1
                windows.append(record)
        if (position + 1) % 50 == 0:
            print("  … %d/%d 场，窗 %d，用时 %.0fs"
                  % (position + 1, len(games), len(windows), time.time() - started))
    return windows, counters, fidelity, denominators, len(games), corpus


def attach_p6_cache(windows):
    """用 p6 生产视图缓存（冻结 R18 v2 真实窗）核对生产事实与父代 rank1。"""

    wanted = {}
    for index, row in enumerate(windows):
        if row["followup_kind"] == "plain":
            # 缓存里的窗口键是 window_key.trigger_seq = **触发弃牌的 seq**（不是我方再鸣牌的 seq）
            wanted[(row["game_id"], row["round_no"], row["trigger_seq"])] = index
    stats = collections.Counter()
    if not wanted:
        return stats
    for path in sorted(glob.glob(P6_CACHE_GLOB)):
        READ_PATHS.append(path)
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                key = (row.get("game_id"), row.get("round_no"), row.get("trigger_seq"))
                index = wanted.get(key)
                if index is None:
                    continue
                target = windows[index]
                # 同一 trigger_seq 上既可能是我方出牌窗、也可能是响应窗；
                # 只接受「本座 + 响应 phase」的那一条。
                visible = (row.get("view") or {}).get("visible_state") or {}
                if visible.get("seat") != target["seat"]:
                    continue
                if row.get("phase") != "response_" + target["claim_type"]:
                    continue
                stats["cache_hits"] += 1
                rank1 = row.get("plan_rank1")
                target["cache_plan_rank1"] = rank1
                target["parent_claims"] = (rank1 == target.get("prod_action_key"))
                stats["parent_claims"] += 1 if target["parent_claims"] else 0
                for action in (row.get("view") or {}).get("actions") or ():
                    if action.get("action_key") != target.get("prod_action_key"):
                        continue
                    target["cache_best_followup"] = action.get("best_followup_discard")
                    stats["cache_action_hit"] += 1
                    if action.get("best_followup_discard") == target.get("prod_pick"):
                        stats["cache_best_followup_agree"] += 1
                    break
    return stats


# ---------------------------------------------------------------------------
# 汇总
# ---------------------------------------------------------------------------


def rate(numerator, denominator):
    return None if not denominator else numerator / denominator


def group_table(windows, kinds=("plain",)):
    table = {}
    for group in GROUPS:
        rows = [row for row in windows
                if row["group"] == group and row["followup_kind"] in kinds]
        achievable = [row for row in rows if row["achievable"]]
        achieved = [row for row in achievable if row["achieved"]]
        table[group] = {
            "windows": len(rows),
            "peng": sum(1 for row in rows if row["claim_type"] == "peng"),
            "chi": sum(1 for row in rows if row["claim_type"] == "chi"),
            "is_win": sum(1 for row in rows if row["is_win"]),
            "achievable": len(achievable),
            "achieved": len(achieved),
            "missed": len(achievable) - len(achieved),
            "rate": rate(len(achieved), len(achievable)),
        }
    return table


def paired_stats(windows, kinds=("plain",)):
    """房级配对：同房内 me 与 elite 都有 >=1 个 achievable 窗时取比例差。"""

    achievable = [row for row in windows
                  if row["achievable"] and row["followup_kind"] in kinds]
    by_room = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0]))
    for row in achievable:
        if row["group"] not in ("me", "elite"):
            continue
        cell = by_room[row["room"]][row["group"]]
        cell[1] += 1
        cell[0] += 1 if row["achieved"] else 0
    diffs = []
    details = []
    for room, groups in sorted(by_room.items()):
        if groups["me"][1] and groups["elite"][1]:
            diff = groups["me"][0] / groups["me"][1] - groups["elite"][0] / groups["elite"][1]
            diffs.append(diff)
            details.append({"room": room, "me": groups["me"], "elite": groups["elite"],
                            "diff": diff})
    result = {
        "paired_rooms": len(diffs),
        "rooms_with_me_achievable": sum(1 for groups in by_room.values() if groups["me"][1]),
        "rooms_with_elite_achievable": sum(1 for groups in by_room.values()
                                           if groups["elite"][1]),
        "diff_mean": (sum(diffs) / len(diffs)) if diffs else None,
        "details": details,
    }
    if len(diffs) >= 2:
        clusters = [item["room"] for item in details]
        result["cr0"] = SL.cluster_ci(diffs, clusters)
        result["bootstrap"] = SL.cluster_bootstrap(
            diffs, clusters, draws=BOOTSTRAP_DRAWS, seed=BOOTSTRAP_SEED)
    else:
        result["cr0"] = None
        result["bootstrap"] = None
    group_a = [(1 if row["achieved"] else 0, row["room"]) for row in achievable
               if row["group"] == "me"]
    group_b = [(1 if row["achieved"] else 0, row["room"]) for row in achievable
               if row["group"] == "elite"]
    result["unpaired_ratio_diff"] = SL.group_ratio_diff_ci(
        group_a, group_b, draws=BOOTSTRAP_DRAWS, seed=BOOTSTRAP_SEED)
    return result


def strata(windows):
    """错过窗与 achievable 窗的分层（预登记 §5 的格边界）。"""

    def labels(row):
        turn = row["turn"]
        melds = row["melds"]
        wall = row["wall_remaining"]
        return {
            "family": "peng" if row["claim_type"] == "peng" else "chi",
            "turn": "t0_2" if turn <= 2 else ("t3_6" if turn <= 6 else "t7p"),
            "melds": "m0" if melds == 0 else ("m1" if melds == 1 else "m2p"),
            "wall": "wlt40" if wall < 40 else ("w40_59" if wall < 60 else "w60p"),
            "dealer": "dealer" if row["is_dealer"] else "non_dealer",
            "targets": str(min(row["n_targets"], 4)),
        }

    out = {}
    for name, selected in (
            ("achievable_all", [row for row in windows if row["achievable"]]),
            ("achievable_me", [row for row in windows if row["achievable"]
                               and row["group"] == "me"]),
            ("missed_me", [row for row in windows if row["group"] == "me"
                           and row["achievable"] and not row["achieved"]]),
            ("missed_all", [row for row in windows if row["achievable"]
                            and not row["achieved"]])):
        table = collections.defaultdict(collections.Counter)
        for row in selected:
            for key, value in labels(row).items():
                table[key][value] += 1
        out[name] = {key: dict(sorted(value.items())) for key, value in table.items()}
    return out


def q2_summary(windows, denominators):
    """Q2：分母、错过窗占比、改选与冲突。"""

    followed = [row for row in windows if row["followup_kind"] == "plain"]
    me_rows = [row for row in followed if row["group"] == "me"]
    missed_me = [row for row in me_rows if row["achievable"] and not row["achieved"]]
    achievable_me = [row for row in me_rows if row["achievable"]]
    d1 = denominators["opp:me"]
    d2 = sum(denominators["opp:" + group] for group in GROUPS)
    d3 = denominators["base:me"]
    d4 = sum(denominators["base:" + group] for group in GROUPS)
    result = {
        "N_miss_me": len(missed_me),
        "N_achievable_me": len(achievable_me),
        "N_followup_me": len(me_rows),
        "denominators": {"D1_opp_me": d1, "D2_opp_all": d2,
                         "D3_base_me": d3, "D4_base_all": d4},
        "missed_over": {
            "D1_opp_me": rate(len(missed_me), d1),
            "D2_opp_all": rate(len(missed_me), d2),
            "D3_base_me": rate(len(missed_me), d3),
            "D4_base_all": rate(len(missed_me), d4),
            "N_followup_me": rate(len(missed_me), len(me_rows)),
        },
    }
    conflict = {}
    for group in GROUPS:
        rows = [row for row in followed if row["group"] == group and row["achievable"]
                and row.get("prod_pick_baotou") is not None]
        bad = [row for row in rows if row["prod_pick_baotou"] is False]
        changed = [row for row in rows if row.get("change")]
        same = [row for row in rows if row.get("actual_eq_prod_pick")]
        conflict[group] = {
            "achievable_with_facts": len(rows),
            "conflict": len(bad),
            "rate": rate(len(bad), len(rows)),
            "change": len(changed),
            "change_rate": rate(len(changed), len(rows)),
            "actual_eq_prod_pick": len(same),
            "actual_eq_prod_pick_rate": rate(len(same), len(rows)),
        }
    result["conflict_by_group"] = conflict
    changed_missed = [row for row in missed_me if row.get("change")]
    parent_claims = [row for row in changed_missed if row.get("parent_claims")]
    result["missed_me_change"] = {
        "n_change": len(changed_missed),
        "n_change_and_parent_rank1": len(parent_claims),
        "over_D1": rate(len(parent_claims), d1),
        "over_missed": rate(len(parent_claims), len(missed_me)),
        "over_D1_all_change": rate(len(changed_missed), d1),
    }
    cached = [row for row in followed if row.get("cache_plan_rank1") is not None]
    result["cache_crosscheck"] = {
        "windows": len(cached),
        "best_followup_agree": sum(
            1 for row in cached if row.get("cache_best_followup") == row.get("prod_pick")),
        "parent_claims": sum(1 for row in cached if row.get("parent_claims")),
        "parent_claims_rate": rate(
            sum(1 for row in cached if row.get("parent_claims")), len(cached)),
    }
    with_facts = [row for row in followed if row.get("actual_eq_prod_pick") is not None]
    result["behavioral_consistency"] = {
        "windows": len(with_facts),
        "match": sum(1 for row in with_facts if row["actual_eq_prod_pick"]),
        "rate": rate(sum(1 for row in with_facts if row["actual_eq_prod_pick"]),
                     len(with_facts)),
    }
    keep = ("game_id", "room", "session", "round_no", "primary", "claim_seq", "follow_seq",
            "claim_tile", "claim_type", "discard", "targets", "n_targets", "melds", "turn",
            "wall_remaining", "is_dealer", "hand_codes", "prod_pick", "prod_pick_baotou",
            "baotou_first_pick", "change", "parent_claims", "cache_plan_rank1", "seat",
            "group", "achieved", "is_win")
    result["missed_me_list"] = [
        {key: row[key] for key in keep if key in row} for row in missed_me]
    result["missed_all_list"] = [
        {key: row[key] for key in keep if key in row}
        for row in followed if row["achievable"] and not row["achieved"]]
    result["conflict_list"] = [
        {key: row[key] for key in keep if key in row}
        for row in followed if row["achievable"] and row.get("prod_pick_baotou") is False]
    return result


def main():
    started = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    limit = int(os.environ.get("C34_LIMIT", "0") or 0)
    if limit:
        print("C34_LIMIT=%d：只跑前 %d 场（仅冒烟用，不用于结论）" % (limit, limit))
    windows, counters, fidelity, denominators, game_count, corpus = scan(limit)
    print("扫描完成：%d 窗，用时 %.0fs" % (len(windows), time.time() - started))

    cache_stats = collections.Counter() if limit else attach_p6_cache(windows)
    for row in windows:
        row.pop("branch_baotou", None)  # 逐分支明细只用于本轮核对，不进产物
        row.pop("branch_shanten", None)
        row.pop("branch_support", None)

    summary = {
        "experiment": "C34-FOLLOWUP-DISCARD",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "limit": limit,
        "games": game_count,
        "corpus": corpus,
        "windows_total": len(windows),
        "followup_kinds": dict(collections.Counter(
            row["followup_kind"] for row in windows)),
        "counters": dict(sorted(counters.items())),
        "fidelity": dict(sorted(fidelity.items())),
        "denominators": dict(sorted(denominators.items())),
        "cache": dict(sorted(cache_stats.items())),
        "Q1_group_table_peng_chi": group_table(windows),
        "Q1_group_table_all_claim_types": group_table(
            windows, ("plain", "chained", "gang")),
        "Q1_group_table_gang": group_table(windows, ("gang",)),
        "Q1_group_table_chained": group_table(windows, ("chained",)),
        "Q1_paired": paired_stats(windows),
        "Q1_paired_primary_only": paired_stats(
            [row for row in windows if row["primary"]]),
        "Q1_strata": strata([row for row in windows if row["followup_kind"] == "plain"]),
        "Q2": q2_summary(windows, denominators),
        "sessions": {},
    }
    by_session = collections.defaultdict(collections.Counter)
    for row in windows:
        if row["followup_kind"] != "plain":
            continue
        cell = by_session[row["session"]]
        cell["windows"] += 1
        if row["achievable"]:
            cell["achievable"] += 1
        if row["achievable"] and not row["achieved"]:
            cell["missed"] += 1
        if row["group"] == "me" and row["achievable"]:
            cell["achievable_me"] += 1
        if row["group"] == "me" and row["achievable"] and not row["achieved"]:
            cell["missed_me"] += 1
    summary["sessions"] = {key: dict(value) for key, value in sorted(by_session.items())}

    with gzip.open(_project_file(_PROJECT_ROOT, OUT / "windows.jsonl.gz"), "wt", encoding="utf-8") as handle:
        for row in windows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    (_project_file(_PROJECT_ROOT, OUT / "summary.json")).write_text(
        json.dumps(summary, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    (_project_file(_PROJECT_ROOT, OUT / "read-paths.json")).write_text(
        json.dumps(sorted(set(READ_PATHS)), ensure_ascii=False, indent=1), encoding="utf-8")
    print("产物：%s" % OUT)
    print(json.dumps(summary["Q1_group_table_peng_chi"], ensure_ascii=False, indent=1))
    print(json.dumps(summary["Q2"]["missed_over"], ensure_ascii=False, indent=1))
    print("总用时 %.0fs" % (time.time() - started))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
