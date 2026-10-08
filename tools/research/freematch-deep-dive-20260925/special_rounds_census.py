#!/usr/bin/env python3
"""特殊局普查：杠 / 杠后补牌 / 抢杠 / 爆头 / 财神 / 抓打圈 / 流局 / 连庄。

只读脚本：不发网络请求、不运行模拟、不改动任何既有文件。
规则口径全部来自仓库 src/hangma_bot/hangma 模块（本脚本只 import 其公开纯函数，
不复制第二套杭麻规则）：

| 用途 | 唯一来源 |
| --- | --- |
| 四家结算公式 | hangma_bot.hangma.settlement.settle_scores |
| 番数明细命名表 | hangma_bot.hangma.settlement.compute_fan |
| 财神（白板）牌值编码 | hangma_bot.hangma.internal_types.WEALTH_CODE |
| 爆头静态判定 | hangma_bot.hangma.special_rules.static_baotou |
| 四白等值条件 | hangma_bot.hangma.special_rules.four_white_indicator |

数据来源（全部为已落盘历史产物，官方权威优先）：

1. artifacts/sessions/<会话标签>/official/dl-*/events.json
   官方下载牌谱。关键字段：seats（座位 0..3 顺序的 user_id）、blocks
   （每局按 seq 连续分段的事件流，含 start_hands 开局手牌）、rounds
   （每局官方结算：dealer / is_draw / multiplier / round_no / scores / winner）。
2. artifacts/sessions/<会话标签>/audit/runs/<run_id>/participants/<user_id>/decisions.jsonl
   我方逐动作审计。本脚本只消费 decision_input（观察 + 合法候选）、
   decision_planned（候选与选中）、submission_intent / submission_outcome。

用法:

    # 仅官方牌谱普查（快，约 10 秒）
    .venv/bin/python review/freematch-deep-dive-20260925/special_rounds_census.py

    # 追加我方行为分布（扫描约 4.8 GB 审计，约 1-3 分钟）
    .venv/bin/python review/freematch-deep-dive-20260925/special_rounds_census.py --audit \
        --out review/freematch-deep-dive-20260925/special-rounds-census.json
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

import argparse
import collections
import glob
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "..", "src"))

from hangma_bot.hangma.internal_types import WEALTH_CODE  # noqa: E402
from hangma_bot.hangma.settlement import settle_scores  # noqa: E402

ME_DEFAULT = "u_13495c3d79c8"

# 承载本次 358 场的会话标签（由 review/freematch-deep-dive-20260925/room-scores.json 反查）。
TARGET_TAGS = (
    "r18-auto-match-campaign-20260923",
    "r18-integrated-positive-v1-auto-match",
    "r18-v2-sse-freematch-20260925-pm",
    "r18-v2-sse-freematch-20260925-pm2",
    "r18-v2-sse-freematch-20260925-pm3",
)

# 官方事件 type 原样值（doc/official-platform-api-v2.md §2.3）。
EV_DRAWN = "tile_drawn"
EV_DISCARDED = "tile_discarded"
EV_GANG = "gang"
EV_CHI = "chi"
EV_PENG = "peng"
EV_ROUND_ENDED = "round_ended"
EV_GAME_ENDED = "game_ended"

# 官方 gang.data.kind 原样值 → 中文杠种（kernel GangKind 的官方映射）。
GANG_KIND_CN = {"an": "暗杠", "ming": "明杠", "bu": "补杠"}

# 官方 round_ended.data.detail 的特殊明细标签（settlement._chain_detail 命名表）。
TAG_BAOTOU = "爆头"
TAG_FOUR_WHITE = "4个白板"
TAG_GANG_OPEN = ("杠开", "连杠")
TAG_PIAO = ("财飘", "双财飘", "三财飘", "连飘")

# 官方牌墙开局剩余张数（136 张 - 四家 13 张 - 庄家第 14 张）。
WALL_FULL = 83


# ---------------------------------------------------------------------------
# 官方牌谱
# ---------------------------------------------------------------------------

def load_official(root):
    """读取全部官方 events.json；按文件 mtime 升序返回 [(path, payload)]。"""
    out = []
    for path in glob.glob(os.path.join(root, "*", "official", "dl-*", "events.json")):
        try:
            with open(path) as fh:
                payload = json.load(fh)
        except (OSError, ValueError):
            continue
        out.append((os.path.getmtime(path), path, payload))
    out.sort(key=lambda row: row[0])
    return [(path, payload) for _m, path, payload in out]


def merge_events(blocks):
    """把同一局多个 seq 分段合并为按 seq 升序且不重复的事件列表。

    分段来自 SSE 断线重连；官方 seq 区间互不重叠，仍按 seq 去重，
    重复序号保留首次出现的事件（不改写官方原始记录）。
    """
    seen = {}
    for block in blocks:
        for event in block.get("events") or []:
            seq = event.get("seq")
            if seq not in seen:
                seen[seq] = event
    return [seen[key] for key in sorted(seen)]


def taglist(detail):
    """把官方 round_ended.data.detail 规范成字符串列表。"""
    if isinstance(detail, (list, tuple)):
        return [str(item) for item in detail]
    if detail is None:
        return []
    return [str(detail)]


def has_tag(tags, prefixes):
    """明细标签前缀匹配（官方命名含 连杠×2、豪华七对×1 等带后缀形式）。"""
    return any(tag.startswith(prefix) for tag in tags for prefix in prefixes)


def analyze_round(round_no, dealer, events, start_hands, ended, meta, my_seat, n_seats):
    """把单局的官方事件流折算成一条特殊局普查记录（纯函数，无副作用）。

    抓打圈口径（与 hangma.special_rules.catch_play_restriction / hangma.catch_play
    同一语义）：任何弃白都开圈并按「最新弃白者」换主；圈主下一次弃非白关圈；
    摸牌、吃、碰、杠都不自行关圈。官方 tile_discarded.data.catch_play 是该次弃牌
    之后的圈活跃标记，本函数用它作为独立核对，与本地推演不一致时计数上报。
    """
    gang_by_seat = collections.Counter()
    gang_kind_by_seat = collections.defaultdict(collections.Counter)
    replenish_by_seat = collections.Counter()
    chi_by_seat = collections.Counter()
    peng_by_seat = collections.Counter()
    white_discard_by_seat = collections.Counter()

    active = False
    owner = None
    circles_opened = 0
    circles_opened_by_seat = collections.Counter()
    cp_flag_true = 0
    cp_flag_mismatch = 0
    restricted_chi = 0
    restricted_peng = 0
    restricted_ming_gang = 0
    restricted_bu_gang = 0
    restricted_concealed_gang = 0
    restricted_discards = 0
    restricted_mocki_ok = 0
    restricted_mocki_bad = 0
    owner_discards_in_circle = 0
    owner_discards_white = 0

    last_drawn_by_seat = {}
    draws_total = 0
    gang_after_low_wall = 0
    my_gang_seqs = []
    opp_gang_seqs = []

    for event in events:
        etype = event.get("type")
        seat = event.get("seat")
        data = event.get("data") or {}
        if etype == EV_DRAWN:
            draws_total += 1
            last_drawn_by_seat[seat] = event.get("tile")
            if data.get("gang_replenish"):
                replenish_by_seat[seat] += 1
        elif etype == EV_DISCARDED:
            tile = event.get("tile")
            flag = data.get("catch_play")
            if flag is True:
                cp_flag_true += 1
            if tile == WEALTH_CODE:
                # 任何弃白都开圈或换主（最新弃白者成为圈主），并重新起算一整圈。
                if not active or owner != seat:
                    circles_opened += 1
                    circles_opened_by_seat[seat] += 1
                if active and owner == seat:
                    owner_discards_white += 1
                active, owner = True, seat
            elif active and owner is not None:
                if seat == owner:
                    # 圈主下一次弃非白即关圈断链。
                    owner_discards_in_circle += 1
                    active, owner = False, None
                else:
                    restricted_discards += 1
                    drawn = last_drawn_by_seat.get(seat)
                    if drawn is not None:
                        if drawn == tile:
                            restricted_mocki_ok += 1
                        else:
                            restricted_mocki_bad += 1
            if tile == WEALTH_CODE:
                white_discard_by_seat[seat] += 1
            if flag is not None and bool(flag) != active:
                cp_flag_mismatch += 1
        elif etype == EV_GANG:
            kind = data.get("kind")
            gang_by_seat[seat] += 1
            gang_kind_by_seat[seat][kind] += 1
            remaining = WALL_FULL - draws_total
            if remaining <= 20:
                gang_after_low_wall += 1
            if seat == my_seat:
                my_gang_seqs.append({"seq": event.get("seq"), "kind": kind})
            else:
                opp_gang_seqs.append({"seq": event.get("seq"), "seat": seat, "kind": kind})
            if active and owner is not None and seat != owner:
                if kind == "an":
                    restricted_concealed_gang += 1
                elif kind == "ming":
                    restricted_ming_gang += 1
                elif kind == "bu":
                    restricted_bu_gang += 1
        elif etype == EV_CHI:
            chi_by_seat[seat] += 1
            if active and owner is not None and seat != owner:
                restricted_chi += 1
        elif etype == EV_PENG:
            peng_by_seat[seat] += 1
            if active and owner is not None and seat != owner:
                restricted_peng += 1

    total_gang_kind = collections.Counter()
    for seat in gang_kind_by_seat:
        total_gang_kind.update(gang_kind_by_seat[seat])

    detail = taglist((ended or {}).get("detail"))
    fan = (ended or {}).get("fan")
    scores = (ended or {}).get("scores") or (meta or {}).get("scores") or []
    is_draw = (ended or {}).get("draw") if ended else (meta or {}).get("is_draw")
    is_draw = bool(is_draw)

    winner_raw = None
    if meta is not None and meta.get("winner") is not None:
        winner_raw = meta.get("winner")
    elif ended and not is_draw:
        positive = [i for i, value in enumerate(scores) if value > 0]
        if len(positive) == 1:
            winner_raw = positive[0]
    # 官方对流局给 winner = -1；必须在所有统计里归一到「无赢家」，
    # 否则 start_whites[-1] 会被误当成座位 3 的赢家。
    winner = None if (is_draw or winner_raw is None or winner_raw < 0) else winner_raw

    my_whites = None
    start_whites = None
    if start_hands:
        try:
            start_whites = [sum(1 for t in hand if t == WEALTH_CODE) for hand in start_hands]
            my_whites = start_whites[my_seat]
        except (TypeError, IndexError):
            start_whites = None
            my_whites = None

    settlement_ok = None
    if (not is_draw) and winner is not None and fan is not None and dealer is not None \
            and len(scores) == 4:
        try:
            settlement_ok = (list(settle_scores(int(fan), 1, int(winner), int(dealer)))
                             == list(scores))
        except (ValueError, TypeError):
            settlement_ok = None

    multiplier = (meta or {}).get("multiplier")

    return {
        "round_no": round_no,
        "dealer": dealer,
        "n_events": len(events),
        "is_draw": is_draw,
        "winner": winner,
        "winner_raw": winner_raw,
        "fan": fan,
        "multiplier": multiplier,
        "multiplier_equals_fan": (None if (multiplier is None or fan is None)
                                  else int(multiplier) == int(fan)),
        "detail": detail,
        "scores": list(scores),
        "my_score": scores[my_seat] if my_seat < len(scores) else None,
        "i_won": winner == my_seat,
        "dealer_is_me": dealer == my_seat,
        "i_win_as_dealer": winner == my_seat and dealer == my_seat,
        "settlement_matches_hangma": settlement_ok,
        "gang_total": sum(gang_by_seat.values()),
        "gang_an": total_gang_kind.get("an", 0),
        "gang_ming": total_gang_kind.get("ming", 0),
        "gang_bu": total_gang_kind.get("bu", 0),
        "my_gang": gang_by_seat.get(my_seat, 0),
        "my_gang_an": gang_kind_by_seat[my_seat].get("an", 0),
        "my_gang_ming": gang_kind_by_seat[my_seat].get("ming", 0),
        "my_gang_bu": gang_kind_by_seat[my_seat].get("bu", 0),
        "opp_gang": sum(gang_by_seat.values()) - gang_by_seat.get(my_seat, 0),
        "replenish_total": sum(replenish_by_seat.values()),
        "my_replenish": replenish_by_seat.get(my_seat, 0),
        "gang_after_low_wall": gang_after_low_wall,
        "my_peng": peng_by_seat.get(my_seat, 0),
        "opp_peng": sum(peng_by_seat.values()) - peng_by_seat.get(my_seat, 0),
        "my_chi": chi_by_seat.get(my_seat, 0),
        "opp_chi": sum(chi_by_seat.values()) - chi_by_seat.get(my_seat, 0),
        "my_white_discards": white_discard_by_seat.get(my_seat, 0),
        "opp_white_discards": (sum(white_discard_by_seat.values())
                               - white_discard_by_seat.get(my_seat, 0)),
        "start_whites": start_whites,
        "my_start_whites": my_whites,
        "circles_opened": circles_opened,
        "circles_started_by_me": circles_opened_by_seat.get(my_seat, 0),
        "has_catchplay": circles_opened > 0,
        "cp_flag_true": cp_flag_true,
        "cp_flag_mismatch": cp_flag_mismatch,
        "restricted_chi": restricted_chi,
        "restricted_peng": restricted_peng,
        "restricted_ming_gang": restricted_ming_gang,
        "restricted_bu_gang": restricted_bu_gang,
        "restricted_concealed_gang": restricted_concealed_gang,
        "restricted_discards": restricted_discards,
        "restricted_mocki_ok": restricted_mocki_ok,
        "restricted_mocki_bad": restricted_mocki_bad,
        "owner_discards_in_circle": owner_discards_in_circle,
        "owner_discards_white": owner_discards_white,
        "tag_baotou": has_tag(detail, (TAG_BAOTOU,)),
        "tag_four_white": has_tag(detail, (TAG_FOUR_WHITE,)),
        "tag_piao": has_tag(detail, TAG_PIAO),
        "tag_gang_open": has_tag(detail, TAG_GANG_OPEN),
        "winner_start_whites": (None if start_whites is None or winner is None
                                else start_whites[winner]),
        "my_gang_seqs": my_gang_seqs,
        "my_gang_bu_seqs": [g["seq"] for g in my_gang_seqs if g["kind"] == "bu"],
        "opp_gang_seqs": opp_gang_seqs,
        "positive_seats": [i for i, v in enumerate(scores) if v > 0],
        "_seat_gang": {str(s): gang_by_seat.get(s, 0) for s in range(n_seats)},
        "_seat_rounds": {str(s): 1 for s in range(n_seats)},
        "fan_from_detail": fan_from_detail(detail),
    }


def fan_from_detail(detail):
    """按 settlement.compute_fan 的公开命名表还原官方明细的番数（对拍用）。

    只使用 compute_fan 的命名约定反推乘子，不重复实现规则：
    分支因子（平胡 1 / 七对 2 / 豪华七对×N 得 2^(N+1)）× 2^链次数 × 四白 ×2 × 爆头 ×2。
    """
    if not detail:
        return None
    branch = None
    chain = 0
    for tag in detail:
        if tag == "平胡":
            branch = 1
        elif tag == "七对":
            branch = 2
        elif tag.startswith("豪华七对×"):
            try:
                branch = 2 * (1 << int(tag.split("×")[1]))
            except (IndexError, ValueError):
                return None
        elif tag == "杠开":
            chain = 1
        elif tag.startswith("连杠×"):
            try:
                chain = int(tag.split("×")[1])
            except (IndexError, ValueError):
                return None
        elif tag == "财飘":
            chain = 1
        elif tag == "双财飘":
            chain = 2
        elif tag == "三财飘":
            chain = 3
        elif tag.startswith("连飘×"):
            try:
                chain = int(tag.split("×")[1])
            except (IndexError, ValueError):
                return None
        elif tag.startswith("杠飘链×"):
            try:
                chain = int(tag.split("×")[1])
            except (IndexError, ValueError):
                return None
    if branch is None:
        return None
    fan = branch << chain
    if "4个白板" in detail:
        fan <<= 1
    if "爆头" in detail:
        fan <<= 1
    return fan


def parse_game(payload, my_seat, me):
    """把一份官方牌谱拆成逐局记录。"""
    seats = [s.get("user_id") for s in (payload.get("seats") or [])]
    if me not in seats:
        return None
    room_id = payload.get("room_id")
    game_id = payload.get("game_id")
    by_round = collections.defaultdict(list)
    for block in payload.get("blocks") or []:
        by_round[block.get("round_no")].append(block)

    ended = {}
    game_ended = None
    for round_no, blocks in by_round.items():
        for event in merge_events(blocks):
            if event.get("type") == EV_ROUND_ENDED:
                ended[round_no] = event.get("data") or {}
            elif event.get("type") == EV_GAME_ENDED:
                game_ended = event.get("data") or {}
    rounds_meta = {r.get("round_no"): r for r in (payload.get("rounds") or [])}

    records = []
    order = sorted(by_round, key=lambda rn: min(b.get("seq_start", 0) for b in by_round[rn]))
    for round_no in order:
        blocks = by_round[round_no]
        events = merge_events(blocks)
        first = min(blocks, key=lambda b: b.get("seq_start", 0))
        start_hands = None
        for block in blocks:
            if block.get("start_hands"):
                start_hands = block["start_hands"]
                break
        rec = analyze_round(round_no, first.get("dealer"), events, start_hands,
                            ended.get(round_no), rounds_meta.get(round_no),
                            my_seat, len(seats))
        rec["room_id"] = room_id
        rec["game_id"] = game_id
        rec["my_seat"] = my_seat
        records.append(rec)
    return {
        "room_id": room_id,
        "game_id": game_id,
        "my_seat": my_seat,
        "seats": seats,
        "final_scores": (game_ended or {}).get("final_scores"),
        "rounds": records,
    }


# ---------------------------------------------------------------------------
# 我方行为分布（审计，可选）
# ---------------------------------------------------------------------------

def iter_audit_files(root, tags, me):
    """列出目标会话标签下我方的 decisions.jsonl 路径。"""
    paths = []
    for tag in tags:
        pattern = os.path.join(root, tag, "audit", "runs", "*", "participants", me,
                               "decisions.jsonl")
        paths.extend(sorted(glob.glob(pattern)))
    return sorted(set(paths))


def scan_audit(paths, me):
    """快速扫描审计：逐行先做廉价子串判定再 json 解析，避免为大多数行付代价。"""
    counts = collections.Counter()
    action_kind_plan = collections.Counter()
    action_kind_effective = collections.Counter()
    gang_offered = 0
    gang_chosen = 0
    gang_rank1_by_kind = collections.Counter()
    gang_offered_windows = set()
    hu_offered = 0
    hu_offered_windows = set()
    hu_declined = []
    gang_declined = collections.Counter()
    gang_declined_windows = 0
    gang_offered_not_effective = 0
    rule_state = collections.Counter()
    outcomes = collections.Counter()
    outcome_reasons = collections.Counter()
    intent_by_kind = collections.Counter()
    phases = collections.Counter()
    whites_hist = collections.Counter()
    whites_hist_baotou = collections.Counter()
    catchplay_windows = 0
    games = set()

    for path in paths:
        with open(path, errors="replace") as fh:
            for line in fh:
                head = line[:120]
                if '"kind": "decision_planned"' in head:
                    counts["decision_planned"] += 1
                    plan = json.loads(line)["payload"]
                    window = plan.get("window") or {}
                    phases[str(window.get("phase"))] += 1
                    if window.get("game_id"):
                        games.add(window["game_id"])
                    key_window = (window.get("game_id"), window.get("round_no"),
                                  window.get("trigger_seq"), window.get("phase"))
                    effective = plan.get("effective_candidates") or []
                    for cand in effective:
                        key = str(cand.get("action_key"))
                        action_kind_effective[key.split(":")[0]] += 1
                    if effective:
                        top = min(effective, key=lambda c: c.get("rank", 999))
                        key = str(top.get("action_key"))
                        action_kind_plan[key.split(":")[0]] += 1
                        if key.startswith("gang:"):
                            gang_rank1_by_kind[key.split(":")[1]] += 1
                    chosen_key = None
                    if effective:
                        chosen_key = str(min(effective, key=lambda c: c.get("rank", 999))
                                         .get("action_key"))
                    effective_keys = {str(c.get("action_key")) for c in effective}
                    for cand in (plan.get("candidates") or []):
                        key = str(cand.get("action_key"))
                        if key.startswith("gang:"):
                            gang_offered += 1
                            gang_offered_windows.add(key_window)
                            if key not in effective_keys:
                                gang_offered_not_effective += 1
                            elif chosen_key != key:
                                gang_declined[str(chosen_key)] += 1
                                gang_declined_windows += 1
                        elif key == "hu":
                            hu_offered += 1
                            hu_offered_windows.add(key_window)
                            hu_score = None
                            chosen_score = None
                            for c in effective:
                                if str(c.get("action_key")) == "hu":
                                    hu_score = c.get("total_score")
                                if str(c.get("action_key")) == chosen_key:
                                    chosen_score = c.get("total_score")
                            if chosen_key != "hu":
                                snapshot = plan.get("observation_snapshot") or {}
                                state = snapshot.get("rule_state") or {}
                                hand = snapshot.get("my_hand") or []
                                hu_declined.append({
                                    "game_id": window.get("game_id"),
                                    "round_no": window.get("round_no"),
                                    "trigger_seq": window.get("trigger_seq"),
                                    "phase": window.get("phase"),
                                    "chosen": chosen_key,
                                    "chosen_score": chosen_score,
                                    "hu_score": hu_score,
                                    "score_gap": (None if (chosen_score is None or hu_score is None)
                                                  else round(chosen_score - hu_score, 2)),
                                    "hu_in_effective": "hu" in effective_keys,
                                    "baotou": bool(state.get("baotou")),
                                    "chain_count": state.get("chain_count"),
                                    "catch_play": bool(state.get("catch_play")),
                                    "whites": sum(1 for t in hand if t == WEALTH_CODE),
                                    "hand_size": len(hand),
                                })
                elif '"kind": "decision_input"' in head:
                    counts["decision_input"] += 1
                    payload = json.loads(line)["payload"]
                    obs = (payload.get("request") or {}).get("observation") or {}
                    state = obs.get("rule_state") or {}
                    rule_state[(bool(state.get("catch_play")), bool(state.get("baotou")),
                                int(state.get("chain_count") or 0))] += 1
                    if state.get("catch_play"):
                        catchplay_windows += 1
                    hand = obs.get("my_hand") or []
                    whites = sum(1 for t in hand if t == WEALTH_CODE)
                    whites_hist[whites] += 1
                    if state.get("baotou"):
                        whites_hist_baotou[whites] += 1
                elif '"kind": "submission_intent"' in head:
                    counts["submission_intent"] += 1
                    payload = json.loads(line)["payload"]
                    key = str(payload.get("action_key"))
                    intent_by_kind[key.split(":")[0]] += 1
                    if key.startswith("gang:"):
                        gang_chosen += 1
                elif '"kind": "submission_outcome"' in head:
                    counts["submission_outcome"] += 1
                    payload = json.loads(line)["payload"]
                    outcomes[str(payload.get("outcome_type"))] += 1
                    if payload.get("reason"):
                        outcome_reasons[str(payload.get("reason"))] += 1
                elif '"kind": "decision_ended"' in head:
                    counts["decision_ended"] += 1

    return {
        "files": len(paths),
        "counts": dict(counts),
        "games_touched": len(games),
        "phases": dict(phases),
        "action_kind_plan_rank1": dict(action_kind_plan),
        "action_kind_effective": dict(action_kind_effective),
        "gang_candidates_offered": gang_offered,
        "gang_candidate_windows": len(gang_offered_windows),
        "gang_intents_submitted": gang_chosen,
        "gang_rank1_by_kind": dict(gang_rank1_by_kind),
        "hu_candidates_offered": hu_offered,
        "hu_candidate_windows": len(hu_offered_windows),
        "hu_rank1": action_kind_plan.get("hu", 0),
        "hu_declined_count": len(hu_declined),
        "hu_declined_examples": hu_declined,
        "hu_declined_with_baotou": sum(1 for d in hu_declined if d["baotou"]),
        "hu_declined_with_whites": sum(1 for d in hu_declined if d["whites"] > 0),
        "hu_declined_whites_hist": dict(sorted(collections.Counter(
            d["whites"] for d in hu_declined).items())),
        "hu_declined_gap_hist": dict(sorted(collections.Counter(
            d["score_gap"] for d in hu_declined).items(), key=lambda x: (x[0] is None, x[0]))),
        "hu_declined_positive_gap": sum(1 for d in hu_declined
                                        if d["score_gap"] is not None and d["score_gap"] > 0),
        "hu_declined_by_chosen": dict(collections.Counter(d["chosen"] for d in hu_declined)),
        "hu_declined_hu_filtered_out": sum(1 for d in hu_declined if not d["hu_in_effective"]),
        "gang_declined_windows": gang_declined_windows,
        "gang_declined_by_chosen": dict(gang_declined.most_common(15)),
        "gang_offered_not_effective": gang_offered_not_effective,
        "intent_by_kind": dict(intent_by_kind),
        "submission_outcomes": dict(outcomes),
        "submission_outcome_reasons_top": dict(outcome_reasons.most_common(20)),
        "rule_state_top": {"|".join(map(str, k)): v for k, v in rule_state.most_common(20)},
        "catchplay_windows": catchplay_windows,
        "baotou_windows": sum(v for k, v in rule_state.items() if k[1]),
        "chain_windows": sum(v for k, v in rule_state.items() if k[2] > 0),
        "my_hand_whites_hist": dict(sorted(whites_hist.items())),
        "my_hand_whites_hist_when_baotou": dict(sorted(whites_hist_baotou.items())),
    }


# ---------------------------------------------------------------------------
# 聚合与打印
# ---------------------------------------------------------------------------

def summarize(rounds):
    """把逐局记录聚合成报告所需的全部表格。"""
    total = len(rounds)

    def agg(selector, label):
        picked = [r for r in rounds if selector(r)]
        n = len(picked)
        my = sum(r["my_score"] or 0 for r in picked)
        wins = sum(1 for r in picked if r["i_won"])
        winner_scores = [r["scores"][r["winner"]] for r in picked
                         if r["winner"] is not None and 0 <= r["winner"] < len(r["scores"])]
        return {
            "label": label,
            "rounds": n,
            "share": round(n / total, 4) if total else None,
            "my_total": my,
            "my_mean": round(my / n, 3) if n else None,
            "my_wins": wins,
            "my_win_rate": round(wins / n, 4) if n else None,
            "my_deals": sum(1 for r in picked if r["dealer_is_me"]),
            "draws": sum(1 for r in picked if r["is_draw"]),
            "mean_winner_score": (round(sum(winner_scores) / len(winner_scores), 3)
                                  if winner_scores else None),
        }

    groups = [
        agg(lambda r: True, "全部"),
        agg(lambda r: r["is_draw"], "流局"),
        agg(lambda r: not r["is_draw"], "非流局"),
        agg(lambda r: r["gang_total"] > 0, "有杠（任意家）"),
        agg(lambda r: r["gang_total"] == 0, "无杠"),
        agg(lambda r: r["my_gang"] > 0, "我方开杠"),
        agg(lambda r: r["my_gang"] == 0, "我方未开杠"),
        agg(lambda r: r["opp_gang"] > 0, "对手开杠"),
        agg(lambda r: r["gang_total"] > 0 and r["my_gang"] == 0, "仅对手开杠"),
        agg(lambda r: r["tag_baotou"], "爆头胡"),
        agg(lambda r: r["tag_gang_open"], "杠上开花（官方明细）"),
        agg(lambda r: r["tag_piao"], "财飘系（官方明细）"),
        agg(lambda r: r["tag_four_white"], "四白板（官方明细）"),
        agg(lambda r: r["has_catchplay"], "抓打圈出现"),
        agg(lambda r: r["circles_started_by_me"] > 0, "我方开抓打圈"),
        agg(lambda r: r["circles_opened"] > 0 and r["circles_started_by_me"] == 0,
            "仅对手开抓打圈"),
        agg(lambda r: r["my_gang"] > 0 and r["i_won"], "我方开杠且我方胡"),
        agg(lambda r: r["my_gang"] > 0 and not r["i_won"] and not r["is_draw"],
            "我方开杠但他人胡"),
        agg(lambda r: r["my_gang"] > 0 and r["is_draw"], "我方开杠且流局"),
    ]

    gang_kind = collections.Counter()
    gang_kind_me = collections.Counter()
    for rec in rounds:
        gang_kind["an"] += rec["gang_an"]
        gang_kind["ming"] += rec["gang_ming"]
        gang_kind["bu"] += rec["gang_bu"]
        gang_kind_me["an"] += rec["my_gang_an"]
        gang_kind_me["ming"] += rec["my_gang_ming"]
        gang_kind_me["bu"] += rec["my_gang_bu"]

    white_table = {}
    for k in range(5):
        picked = [r for r in rounds if r["my_start_whites"] == k]
        if not picked:
            continue
        white_table[str(k)] = {
            "rounds": len(picked),
            "my_total": sum(r["my_score"] or 0 for r in picked),
            "my_mean": round(sum(r["my_score"] or 0 for r in picked) / len(picked), 3),
            "my_wins": sum(1 for r in picked if r["i_won"]),
            "my_win_rate": round(sum(1 for r in picked if r["i_won"]) / len(picked), 4),
            "my_gangs": sum(r["my_gang"] for r in picked),
        }

    winner_white = {}
    for k in range(5):
        picked = [r for r in rounds if r["winner_start_whites"] == k]
        if picked:
            winner_white[str(k)] = len(picked)

    streak_hist = collections.Counter()
    dealer_runs = []
    by_game = collections.defaultdict(list)
    for rec in rounds:
        by_game[rec["game_id"]].append(rec)
    for _game_id, recs in by_game.items():
        recs = sorted(recs, key=lambda r: r["round_no"])
        run = 0
        prev = None
        for rec in recs:
            if rec["dealer"] == prev:
                run += 1
            else:
                if prev is not None:
                    dealer_runs.append(run)
                run = 0
                prev = rec["dealer"]
        if prev is not None:
            dealer_runs.append(run)
    for run in dealer_runs:
        streak_hist[run] += 1

    special_defs = {
        "有杠（任意家）": lambda r: r["gang_total"] > 0,
        "我方开杠": lambda r: r["my_gang"] > 0,
        "对手开杠": lambda r: r["opp_gang"] > 0,
        "爆头胡": lambda r: r["tag_baotou"],
        "抓打圈": lambda r: r["has_catchplay"],
        "流局": lambda r: r["is_draw"],
        "存在特殊（任意一项）": lambda r: (r["gang_total"] > 0 or r["tag_baotou"]
                                            or r["has_catchplay"] or r["is_draw"]),
    }
    attribution = {}
    for name, sel in special_defs.items():
        picked = [r for r in rounds if sel(r)]
        attribution[name] = {
            "rounds": len(picked),
            "my_total": sum((r["my_score"] or 0) for r in picked),
            "my_mean": (round(sum((r["my_score"] or 0) for r in picked) / len(picked), 3)
                        if picked else None),
        }
    attribution["全部"] = {
        "rounds": total,
        "my_total": sum((r["my_score"] or 0) for r in rounds),
        "my_mean": round(sum((r["my_score"] or 0) for r in rounds) / total, 3) if total else None,
    }

    conformance = {
        "rounds": total,
        "cp_flag_mismatch_rounds": sum(1 for r in rounds if r["cp_flag_mismatch"] > 0),
        "cp_flag_mismatch_events": sum(r["cp_flag_mismatch"] for r in rounds),
        "circles_opened_total": sum(r["circles_opened"] for r in rounds),
        "circles_rounds": sum(1 for r in rounds if r["has_catchplay"]),
        "restricted_chi": sum(r["restricted_chi"] for r in rounds),
        "restricted_peng": sum(r["restricted_peng"] for r in rounds),
        "restricted_ming_gang": sum(r["restricted_ming_gang"] for r in rounds),
        "restricted_bu_gang": sum(r["restricted_bu_gang"] for r in rounds),
        "restricted_concealed_gang": sum(r["restricted_concealed_gang"] for r in rounds),
        "restricted_discards": sum(r["restricted_discards"] for r in rounds),
        "restricted_mocki_ok": sum(r["restricted_mocki_ok"] for r in rounds),
        "restricted_mocki_bad": sum(r["restricted_mocki_bad"] for r in rounds),
        "gang_in_last_20_wall": sum(r["gang_after_low_wall"] for r in rounds),
        "settlement_checked": sum(1 for r in rounds if r["settlement_matches_hangma"] is not None),
        "settlement_mismatch": sum(1 for r in rounds
                                   if r["settlement_matches_hangma"] is False),
        "multiplier_checked": sum(1 for r in rounds if r["multiplier_equals_fan"] is not None),
        "multiplier_differs_from_fan": sum(1 for r in rounds
                                           if r["multiplier_equals_fan"] is False),
        "detail_missing_on_non_draw": sum(1 for r in rounds
                                          if not r["detail"] and not r["is_draw"]),
        "fan_vs_detail_mismatch": sum(1 for r in rounds if r["fan_from_detail"] is not None
                                      and r["fan"] is not None
                                      and r["fan_from_detail"] != r["fan"]),
    }

    # ---- 特殊族按「谁赢的」拆分 -------------------------------------------
    tag_winner = {}
    for tag_name, sel in (("爆头胡", lambda r: r["tag_baotou"]),
                          ("杠上开花", lambda r: r["tag_gang_open"]),
                          ("财飘系", lambda r: r["tag_piao"]),
                          ("四白板", lambda r: r["tag_four_white"])):
        picked = [r for r in rounds if sel(r)]
        mine = sum(1 for r in picked if r["i_won"])
        tag_winner[tag_name] = {
            "rounds": len(picked),
            "won_by_me": mine,
            "won_by_opp": sum(1 for r in picked if r["winner"] is not None and not r["i_won"]),
            "draw": sum(1 for r in picked if r["is_draw"]),
            "my_expected_share": round(len(picked) / 4, 1),
            "my_share_ratio": round(mine / (len(picked) / 4), 3) if picked else None,
            "my_total": sum((r["my_score"] or 0) for r in picked),
            "my_mean": round(sum((r["my_score"] or 0) for r in picked) / len(picked), 3)
            if picked else None,
        }

    # ---- 我方胡牌明细分布（找「从未胡过的类型」） ---------------------------
    my_win_detail = collections.Counter()
    all_win_detail = collections.Counter()
    for rec in rounds:
        if not rec["detail"]:
            continue
        key = "+".join(rec["detail"])
        all_win_detail[key] += 1
        if rec["i_won"]:
            my_win_detail[key] += 1

    # ---- 财神弃牌 ---------------------------------------------------------
    white_total = sum(r["my_white_discards"] + r["opp_white_discards"] for r in rounds)
    white_mine = sum(r["my_white_discards"] for r in rounds)
    white_rounds_mine = sum(1 for r in rounds if r["my_white_discards"] > 0)

    # ---- 四座位杠频次（排除座位偏差） -------------------------------------
    seat_gang = collections.Counter()
    seat_rounds = collections.Counter()
    for rec in rounds:
        for key, value in (rec.get("_seat_gang") or {}).items():
            seat_gang[int(key)] += value
        for key, value in (rec.get("_seat_rounds") or {}).items():
            seat_rounds[int(key)] += value

    # ---- 一炮多响 / 无赢家异常 --------------------------------------------
    multi_winner = sum(1 for r in rounds if len(r["positive_seats"]) > 1)
    no_winner_non_draw = sum(1 for r in rounds
                             if not r["is_draw"] and not r["positive_seats"])

    # ---- 我方开杠的收益与风险 --------------------------------------------
    my_gang_rounds = [r for r in rounds if r["my_gang"] > 0]
    my_gang_outcome = {
        "rounds": len(my_gang_rounds),
        "i_won": sum(1 for r in my_gang_rounds if r["i_won"]),
        "opp_won": sum(1 for r in my_gang_rounds if r["winner"] is not None and not r["i_won"]),
        "draw": sum(1 for r in my_gang_rounds if r["is_draw"]),
        "my_total": sum((r["my_score"] or 0) for r in my_gang_rounds),
        "my_mean": round(sum((r["my_score"] or 0) for r in my_gang_rounds)
                         / len(my_gang_rounds), 3) if my_gang_rounds else None,
        "i_won_with_gang_open_tag": sum(1 for r in my_gang_rounds
                                        if r["i_won"] and r["tag_gang_open"]),
        "gang_rounds_by_kind": {
            "an": sum(1 for r in my_gang_rounds if r["my_gang_an"] > 0),
            "ming": sum(1 for r in my_gang_rounds if r["my_gang_ming"] > 0),
            "bu": sum(1 for r in my_gang_rounds if r["my_gang_bu"] > 0),
        },
        "my_gang_count": sum(r["my_gang"] for r in my_gang_rounds),
    }
    opp_gang_rounds = [r for r in rounds if r["opp_gang"] > 0 and r["my_gang"] == 0]
    opp_gang_outcome = {
        "rounds": len(opp_gang_rounds),
        "i_won": sum(1 for r in opp_gang_rounds if r["i_won"]),
        "my_win_rate": round(sum(1 for r in opp_gang_rounds if r["i_won"])
                             / len(opp_gang_rounds), 4) if opp_gang_rounds else None,
        "my_total": sum((r["my_score"] or 0) for r in opp_gang_rounds),
        "my_mean": round(sum((r["my_score"] or 0) for r in opp_gang_rounds)
                         / len(opp_gang_rounds), 3) if opp_gang_rounds else None,
    }

    # ---- 抓打圈内部结构 ---------------------------------------------------
    circle_rows = [r for r in rounds if r["has_catchplay"]]
    catchplay = {
        "rounds_with_circle": len(circle_rows),
        "circles_opened": sum(r["circles_opened"] for r in circle_rows),
        "circles_by_me": sum(r["circles_started_by_me"] for r in circle_rows),
        "circles_by_opp": sum(r["circles_opened"] - r["circles_started_by_me"]
                              for r in circle_rows),
        "white_discards_total": white_total,
        "white_discards_mine": white_mine,
        "white_discard_rounds_mine": white_rounds_mine,
        "my_score_rounds_with_circle": sum((r["my_score"] or 0) for r in circle_rows),
        "my_mean_rounds_with_circle": round(sum((r["my_score"] or 0) for r in circle_rows)
                                            / len(circle_rows), 3) if circle_rows else None,
    }

    # ---- 失分/得分归因：按「本局赢家胡牌明细」拆分 ------------------------
    loss_attr = collections.Counter()
    loss_rounds = collections.Counter()
    gain_attr = collections.Counter()
    gain_rounds = collections.Counter()
    for rec in rounds:
        if rec["is_draw"] or rec["winner"] is None:
            continue
        key = "+".join(rec["detail"]) if rec["detail"] else "(明细缺失)"
        if rec["i_won"]:
            gain_attr[key] += (rec["my_score"] or 0)
            gain_rounds[key] += 1
        else:
            loss_attr[key] += (rec["my_score"] or 0)
            loss_rounds[key] += 1
    total_loss = sum(loss_attr.values())
    total_gain = sum(gain_attr.values())
    loss_table = []
    for key, value in loss_attr.most_common():
        loss_table.append({
            "detail": key,
            "rounds": loss_rounds[key],
            "my_total": value,
            "share_of_loss": round(value / total_loss, 4) if total_loss else None,
            "mean": round(value / loss_rounds[key], 3) if loss_rounds[key] else None,
        })
    gain_table = []
    for key, value in gain_attr.most_common():
        gain_table.append({
            "detail": key,
            "rounds": gain_rounds[key],
            "my_total": value,
            "mean": round(value / gain_rounds[key], 3) if gain_rounds[key] else None,
        })

    # ---- 单局赢分规模与番数分布（胜率 vs 单次收益） -----------------------
    def win_stats(rows):
        values = [r["scores"][r["winner"]] for r in rows
                  if r["winner"] is not None and 0 <= r["winner"] < len(r["scores"])]
        if not values:
            return {"n": 0}
        values_sorted = sorted(values)
        return {
            "n": len(values),
            "mean": round(sum(values) / len(values), 3),
            "median": values_sorted[len(values_sorted) // 2],
            "max": max(values),
            "sum": sum(values),
        }
    win_size = {
        "all_winners": win_stats(rounds),
        "my_wins": win_stats([r for r in rounds if r["i_won"]]),
        "opp_wins": win_stats([r for r in rounds if r["winner"] is not None and not r["i_won"]]),
    }
    fan_hist_mine = collections.Counter()
    fan_hist_opp = collections.Counter()
    for rec in rounds:
        if rec["winner"] is None or rec["is_draw"]:
            continue
        (fan_hist_mine if rec["i_won"] else fan_hist_opp)[rec["fan"]] += 1

    # ---- 爆头达成率：按房拆分（聚类单位） ---------------------------------
    per_room_baotou = []
    by_room = collections.defaultdict(list)
    for rec in rounds:
        by_room[rec["room_id"]].append(rec)
    for room_id, rows in sorted(by_room.items()):
        baotou_rows = [r for r in rows if r["tag_baotou"]]
        mine = sum(1 for r in baotou_rows if r["i_won"])
        per_room_baotou.append({
            "room_id": room_id,
            "rounds": len(rows),
            "baotou_rounds": len(baotou_rows),
            "my_baotou_wins": mine,
            "expected": round(len(baotou_rows) / 4, 2),
            "ratio": round(mine / (len(baotou_rows) / 4), 3) if baotou_rows else None,
            "my_wins": sum(1 for r in rows if r["i_won"]),
            "expected_wins": round(len(rows) / 4, 2),
            "my_total": sum((r["my_score"] or 0) for r in rows),
        })
    rooms_below = sum(1 for row in per_room_baotou if row["ratio"] is not None and row["ratio"] < 1)
    rooms_above = sum(1 for row in per_room_baotou if row["ratio"] is not None and row["ratio"] > 1)
    rooms_total_above = sum(1 for row in per_room_baotou
                            if row["my_wins"] > row["expected_wins"])

    # ---- 我方杠的仓位校正期望 --------------------------------------------
    my_rounds_by_seat = collections.Counter()
    for rec in rounds:
        my_rounds_by_seat[rec["my_seat"]] += 1
    position_expected_gang = sum(
        my_rounds_by_seat[s] * (seat_gang.get(s, 0) / seat_rounds.get(s, 1))
        for s in my_rounds_by_seat)
    my_gang_total = sum(r["my_gang"] for r in rounds)
    multi_gang_rounds = collections.Counter(r["my_gang"] for r in [x for x in rounds])

    # ---- 爆头与开局财神数的关系 ------------------------------------------
    baotou_white = {}
    for rows_name, rows in (("all_rounds", rounds),
                            ("baotou_rounds", [r for r in rounds if r["tag_baotou"]]),
                            ("non_baotou_rounds", [r for r in rounds if not r["tag_baotou"]])):
        dist = collections.Counter(r["winner_start_whites"] for r in rows
                                   if r["winner"] is not None)
        baotou_white[rows_name] = {str(k): v for k, v in sorted(dist.items(),
                                                                key=lambda x: (x[0] is None, x[0]))}

    # ---- 同番收益对拍与番数结构反事实 ------------------------------------
    fan_side = collections.defaultdict(list)
    for rec in rounds:
        if rec["winner"] is None or rec["is_draw"]:
            continue
        fan_side[(rec["fan"], bool(rec["i_won"]))].append(rec["scores"][rec["winner"]])
    win_size_by_fan = {}
    for (fan, is_mine), values in sorted(fan_side.items(), key=lambda x: (x[0][0] is None,
                                                                         x[0][0], x[0][1])):
        win_size_by_fan["%s|%s" % (fan, "me" if is_mine else "opp")] = {
            "n": len(values), "mean": round(sum(values) / len(values), 3)}
    opp_fan = collections.Counter()
    my_fan = collections.Counter()
    for (fan, is_mine), values in fan_side.items():
        (my_fan if is_mine else opp_fan)[fan] += len(values)
    n_opp = sum(opp_fan.values())
    n_me = sum(my_fan.values())
    my_gain = sum(sum(values) for (fan, is_mine), values in fan_side.items() if is_mine)
    opp_mean_by_fan = {fan: sum(values) / len(values)
                       for (fan, is_mine), values in fan_side.items() if not is_mine}
    counterfactual_gain = sum(n_me * (opp_fan[fan] / n_opp) * opp_mean_by_fan[fan]
                              for fan in opp_mean_by_fan)
    high_fan = {}
    for threshold in (2, 4):
        high_fan["ge%d" % threshold] = {
            "mine": round(sum(v for f, v in my_fan.items() if f is not None and f >= threshold) / n_me, 4),
            "opp": round(sum(v for f, v in opp_fan.items() if f is not None and f >= threshold) / n_opp, 4),
        }
    fan_structure = {
        "my_wins": n_me, "opp_wins": n_opp,
        "my_gain_actual": my_gain,
        "my_gain_counterfactual_opp_fan_mix": round(counterfactual_gain, 1),
        "gap": round(counterfactual_gain - my_gain, 1),
        "net_actual": sum((r["my_score"] or 0) for r in rounds),
        "net_if_fan_mix_equal": round(sum((r["my_score"] or 0) for r in rounds)
                                      + (counterfactual_gain - my_gain), 1),
        "high_fan_share": high_fan,
        "my_mean_win": round(my_gain / n_me, 3) if n_me else None,
        "opp_mean_win": round(sum(sum(v) for (f, m), v in fan_side.items() if not m) / n_opp, 3)
        if n_opp else None,
    }

    # 逐房反事实：验证番数结构差距是否跨房一致（房是聚类单位）
    per_room_fan_gap = []
    for room_id, rows in sorted(by_room.items()):
        rs_opp = [r for r in rows if r["winner"] is not None and not r["is_draw"] and not r["i_won"]]
        rs_me = [r for r in rows if r["i_won"]]
        if not rs_opp or not rs_me:
            per_room_fan_gap.append({"room_id": room_id, "rounds": len(rows),
                                     "my_wins": len(rs_me), "my_total": sum((r["my_score"] or 0) for r in rows),
                                     "gap": None})
            continue
        local_buckets = collections.defaultdict(list)
        for r in rs_opp:
            local_buckets[r["fan"]].append(r["scores"][r["winner"]])
        local_mean = {f: sum(v) / len(v) for f, v in local_buckets.items()}
        opponent_wins = sum(len(v) for v in local_buckets.values())
        # 正确反事实：本房我方每一胜都按本房对手的番数分布重抽样。
        per_win_expected = sum((len(v) / opponent_wins) * local_mean[f]
                               for f, v in local_buckets.items())
        cf = len(rs_me) * per_win_expected
        actual = sum(r["scores"][r["winner"]] for r in rs_me)
        per_room_fan_gap.append({
            "room_id": room_id,
            "rounds": len(rows),
            "my_wins": len(rs_me),
            "my_total": sum((r["my_score"] or 0) for r in rows),
            "gap": round(cf - actual, 1),
        })
    rooms_gap_positive = sum(1 for row in per_room_fan_gap if row["gap"] is not None and row["gap"] > 0)

    # ---- 分杠种的我方结果 ------------------------------------------------
    by_kind_outcome = {}
    for kind_key, label in (("my_gang_an", "暗杠"), ("my_gang_ming", "明杠"), ("my_gang_bu", "补杠")):
        rows_kind = [r for r in rounds if r[kind_key] > 0]
        by_kind_outcome[label] = {
            "rounds": len(rows_kind),
            "gangs": sum(r[kind_key] for r in rows_kind),
            "i_won": sum(1 for r in rows_kind if r["i_won"]),
            "my_total": sum((r["my_score"] or 0) for r in rows_kind),
            "my_mean": round(sum((r["my_score"] or 0) for r in rows_kind) / len(rows_kind), 3)
            if rows_kind else None,
        }

    # ---- 抓打圈标记不一致样本 --------------------------------------------
    cp_mismatch_rows = [{
        "room_id": r.get("room_id"), "game_id": r.get("game_id"),
        "round_no": r["round_no"], "events": r["cp_flag_mismatch"],
    } for r in rounds if r["cp_flag_mismatch"] > 0]

    # ---- 流局明细 ---------------------------------------------------------
    draw_rows = [{"room_id": r.get("room_id"), "game_id": r.get("game_id"),
                  "round_no": r["round_no"], "dealer": r["dealer"],
                  "my_score": r["my_score"], "n_events": r["n_events"]}
                 for r in rounds if r["is_draw"]]

    return {
        "rounds_total": total,
        "groups": groups,
        "tag_winner": tag_winner,
        "my_win_detail_top": dict(my_win_detail.most_common(30)),
        "all_win_detail_top": dict(all_win_detail.most_common(30)),
        "my_wins_total": sum(my_win_detail.values()),
        "white_discards_total": white_total,
        "white_discards_mine": white_mine,
        "seat_gang": {str(k): v for k, v in sorted(seat_gang.items())},
        "seat_rounds": {str(k): v for k, v in sorted(seat_rounds.items())},
        "multi_winner_rounds": multi_winner,
        "no_winner_non_draw_rounds": no_winner_non_draw,
        "my_gang_outcome": my_gang_outcome,
        "opp_gang_outcome": opp_gang_outcome,
        "catchplay": catchplay,
        "loss_attribution": loss_table,
        "gain_attribution": gain_table,
        "loss_attribution_total": total_loss,
        "gain_attribution_total": total_gain,
        "win_size": win_size,
        "fan_hist_mine": {str(k): v for k, v in sorted(fan_hist_mine.items(), key=lambda x: (x[0] is None, x[0]))},
        "fan_hist_opp": {str(k): v for k, v in sorted(fan_hist_opp.items(), key=lambda x: (x[0] is None, x[0]))},
        "per_room_baotou": per_room_baotou,
        "rooms_baotou_ratio_below_1": rooms_below,
        "rooms_baotou_ratio_above_1": rooms_above,
        "rooms_mywins_above_expected": rooms_total_above,
        "my_gang_total": my_gang_total,
        "position_expected_gang": round(position_expected_gang, 2),
        "my_gang_vs_position_ratio": (round(my_gang_total / position_expected_gang, 4)
                                      if position_expected_gang else None),
        "my_gangs_per_round_hist": {str(k): v for k, v in sorted(multi_gang_rounds.items())},
        "winner_start_whites_by_tag": baotou_white,
        "win_size_by_fan": win_size_by_fan,
        "fan_structure": fan_structure,
        "per_room_fan_gap": per_room_fan_gap,
        "rooms_fan_gap_positive": rooms_gap_positive,
        "my_gang_by_kind_outcome": by_kind_outcome,
        "cp_mismatch_rows": cp_mismatch_rows,
        "draw_rows": draw_rows,
        "gang_kind_total": dict(gang_kind),
        "gang_kind_mine": dict(gang_kind_me),
        "white_by_my_start_hand": white_table,
        "winner_start_whites": winner_white,
        "dealer_streak_hist": dict(sorted(streak_hist.items())),
        "dealer_streak_max": (max(streak_hist) if streak_hist else None),
        "attribution": attribution,
        "conformance": conformance,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="杭麻特殊局普查（只读）")
    parser.add_argument("--me", default=ME_DEFAULT)
    parser.add_argument("--root", default="artifacts/sessions")
    parser.add_argument("--audit", action="store_true", help="追加扫描我方审计（慢）")
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    raw = load_official(args.root)
    all_games = []
    for path, payload in raw:
        seats = [s.get("user_id") for s in (payload.get("seats") or [])]
        if args.me not in seats:
            continue
        parsed = parse_game(payload, seats.index(args.me), args.me)
        if parsed is None:
            continue
        parsed["path"] = path
        parsed["session_tag"] = path.split(os.sep)[2]
        all_games.append(parsed)

    # 同一 game_id 在 09-23 战投里被重复下载（payload 逐字节相同），
    # 按 game_id 去重取 mtime 最早的一份，避免把同一局算两次。
    dup_counter = collections.Counter(game["game_id"] for game in all_games)
    duplicates = {gid: n for gid, n in dup_counter.items() if n > 1}
    seen_ids = set()
    games = []
    for game in all_games:
        if game["game_id"] in seen_ids:
            continue
        seen_ids.add(game["game_id"])
        games.append(game)
    files_total_my = sum((rec["my_score"] or 0) for game in all_games
                         for rec in game["rounds"])

    rounds = [rec for game in games for rec in game["rounds"]]
    rooms = collections.defaultdict(list)
    for game in games:
        rooms[game["room_id"]].append(game)

    summary = summarize(rounds)
    summary["official_files_total"] = len(raw)
    summary["files_with_me"] = len(all_games)
    summary["duplicate_game_ids"] = duplicates
    summary["duplicate_file_count"] = len(all_games) - len(games)
    summary["my_total_files_dedup_missing"] = files_total_my
    summary["rounds_total_files"] = sum(len(g["rounds"]) for g in all_games)
    summary["games_with_me"] = len(games)
    summary["rooms_with_me"] = len(rooms)
    summary["unique_game_ids"] = len({g["game_id"] for g in games})
    summary["my_seat_hist"] = dict(collections.Counter(g["my_seat"] for g in games))
    summary["rounds_per_game_hist"] = dict(collections.Counter(len(g["rounds"]) for g in games))
    summary["my_total_all_rooms"] = sum((rec["my_score"] or 0) for rec in rounds)

    room_rows = []
    for room_id, gs in sorted(rooms.items()):
        rs = [rec for g in gs for rec in g["rounds"]]
        room_rows.append({
            "room_id": room_id,
            "session_tag": gs[0]["session_tag"],
            "games": len(gs),
            "rounds": len(rs),
            "my_total": sum((r["my_score"] or 0) for r in rs),
            "my_gang": sum(r["my_gang"] for r in rs),
            "opp_gang": sum(r["opp_gang"] for r in rs),
            "gang_an": sum(r["gang_an"] for r in rs),
            "gang_ming": sum(r["gang_ming"] for r in rs),
            "gang_bu": sum(r["gang_bu"] for r in rs),
            "baotou_rounds": sum(1 for r in rs if r["tag_baotou"]),
            "piao_rounds": sum(1 for r in rs if r["tag_piao"]),
            "gang_open_rounds": sum(1 for r in rs if r["tag_gang_open"]),
            "catchplay_rounds": sum(1 for r in rs if r["has_catchplay"]),
            "draws": sum(1 for r in rs if r["is_draw"]),
            "my_wins": sum(1 for r in rs if r["i_won"]),
        })

    result = {
        "meta": {
            "me": args.me,
            "root": args.root,
            "audit_scanned": bool(args.audit),
            "target_tags": list(TARGET_TAGS),
        },
        "summary": summary,
        "rooms": room_rows,
        "rounds": rounds,
    }
    if args.audit:
        paths = iter_audit_files(args.root, TARGET_TAGS, args.me)
        audit = scan_audit(paths, args.me)
        # 把 42 个「弃胡」窗口接回官方结算：我们最终有没有赢下这一局
        round_index = {(r["game_id"], r["round_no"]): r for r in rounds}
        outcome_hist = collections.Counter()
        for entry in audit.get("hu_declined_examples") or []:
            rec = round_index.get((entry["game_id"], entry["round_no"]))
            if rec is None:
                entry["round_outcome"] = "unknown"
                outcome_hist["unknown"] += 1
                continue
            entry["round_outcome"] = ("i_won" if rec["i_won"]
                                      else ("draw" if rec["is_draw"] else "opp_won"))
            entry["round_detail"] = "+".join(rec["detail"]) if rec["detail"] else None
            entry["round_my_score"] = rec["my_score"]
            outcome_hist[entry["round_outcome"]] += 1
        audit["hu_declined_round_outcome"] = dict(outcome_hist)
        audit["hu_declined_my_score_sum"] = sum(
            (entry.get("round_my_score") or 0) for entry in
            (audit.get("hu_declined_examples") or []))
        gaps = [entry["score_gap"] for entry in (audit.get("hu_declined_examples") or [])
                if entry.get("score_gap") is not None]
        audit["hu_declined_gap_stats"] = {
            "n": len(gaps),
            "min": min(gaps) if gaps else None,
            "max": max(gaps) if gaps else None,
            "mean": round(sum(gaps) / len(gaps), 3) if gaps else None,
            "le_1": sum(1 for g in gaps if g <= 1),
            "gt_10": sum(1 for g in gaps if g > 10),
        }
        result["my_audit"] = audit

    if args.out:
        with open(args.out, "w") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=1)
        print("写出 " + args.out, file=sys.stderr)

    print_tables(result)
    return 0


def print_tables(result):
    s = result["summary"]
    print("=" * 100)
    print("官方牌谱：文件 %d，含我方文件 %d 份，其中 %d 份是 %d 个 game_id 的重复下载；"
          "去重后 %d 场，房 %d 个，局 %d 局"
          % (s["official_files_total"], s["files_with_me"], s["duplicate_file_count"],
             len(s["duplicate_game_ids"]), s["games_with_me"], s["rooms_with_me"],
             s["rounds_total"]))
    print("我方合计：文件口径（含重复）%+d 分 / %d 局；去重口径 %+d 分 / %d 局"
          % (s["my_total_files_dedup_missing"], s["rounds_total_files"],
             s["my_total_all_rooms"], s["rounds_total"]))
    print("重复 game_id：", s["duplicate_game_ids"])
    print("我方座位分布：", s["my_seat_hist"])
    print("每场局数分布：", s["rounds_per_game_hist"])
    print("-" * 100)
    print("%-28s%7s%8s%10s%9s%9s%8s%8s" %
          ("分组", "局数", "占比", "我方总分", "我方均分", "我方胡率", "庄家局", "流局"))
    for group in s["groups"]:
        print("%-28s%7d%8s%10d%9s%9s%8d%8d" % (
            group["label"], group["rounds"], group["share"], group["my_total"],
            group["my_mean"], group["my_win_rate"], group["my_deals"], group["draws"]))
    print("-" * 100)
    print("杠种总数：", s["gang_kind_total"], " 我方：", s["gang_kind_mine"])
    print("得分归因：")
    for name, row in s["attribution"].items():
        print("  %-22s 局 %5d  我方合计 %+7d  均分 %s" %
              (name, row["rounds"], row["my_total"], row["my_mean"]))
    print("-" * 100)
    print("规则一致性核对：")
    for key, value in s["conformance"].items():
        print("  %-32s %s" % (key, value))
    print("-" * 100)
    print("我方开局手牌财神数 → 结果：")
    for key, row in sorted(s["white_by_my_start_hand"].items()):
        print("  %s 张：局 %5d  我方合计 %+6d  均分 %8.3f  胡率 %s  我方杠 %d" %
              (key, row["rounds"], row["my_total"], row["my_mean"],
               row["my_win_rate"], row["my_gangs"]))
    print("赢家开局手牌财神数分布：", s["winner_start_whites"])
    print("连庄长度分布（同庄连续局数-1）：", s["dealer_streak_hist"],
          " 最长", s["dealer_streak_max"])
    print("-" * 100)
    print("特殊族按赢家拆分（我方期望份额 = 局数/4）：")
    for name, row in s["tag_winner"].items():
        print("  %-10s 局 %4d  我方赢 %3d  对手赢 %3d  流局 %2d  期望 %5.1f  比值 %s  我方合计 %+6d 均分 %s"
              % (name, row["rounds"], row["won_by_me"], row["won_by_opp"], row["draw"],
                 row["my_expected_share"], row["my_share_ratio"], row["my_total"], row["my_mean"]))
    print("-" * 100)
    print("我方胡牌明细（共 %d 次）：" % s["my_wins_total"])
    for key, value in s["my_win_detail_top"].items():
        print("  我方 %-28s %4d     全局同型 %d" % (key, value, s["all_win_detail_top"].get(key, 0)))
    print("全局胡牌明细：")
    for key, value in s["all_win_detail_top"].items():
        print("  %-30s %5d   我方 %d" % (key, value, s["my_win_detail_top"].get(key, 0)))
    print("-" * 100)
    print("四座位杠频次（分母 = 该座位出现的局数）：")
    for seat, count in s["seat_gang"].items():
        rounds_seat = s["seat_rounds"].get(seat, 0)
        print("  seat %s：杠 %4d / 局 %5d = %.4f" % (seat, count, rounds_seat,
                                                     count / rounds_seat if rounds_seat else 0))
    print("一炮多响局数（>1 个正分座位）：", s["multi_winner_rounds"],
          " 非流局但无正分座位：", s["no_winner_non_draw_rounds"])
    print("财神弃牌：全局 %d 张，我方 %d 张（出现在 %d 局）"
          % (s["white_discards_total"], s["white_discards_mine"],
             s["catchplay"]["white_discard_rounds_mine"]))
    print("-" * 100)
    print("我方开杠结果：", s["my_gang_outcome"])
    print("对手开杠结果：", s["opp_gang_outcome"])
    print("抓打圈结构：", s["catchplay"])
    print("-" * 100)
    print("失分归因（按赢家胡牌明细；我方总失分 %+d，总得分 %+d）："
          % (s["loss_attribution_total"], s["gain_attribution_total"]))
    for row in s["loss_attribution"]:
        print("  %-30s 局 %4d  我方 %+7d  占失分 %s  均分 %s"
              % (row["detail"], row["rounds"], row["my_total"], row["share_of_loss"], row["mean"]))
    print("-" * 100)
    print("得分归因（我方胡牌明细）：")
    for row in s["gain_attribution"]:
        print("  %-30s 局 %4d  我方 %+7d  均分 %s"
              % (row["detail"], row["rounds"], row["my_total"], row["mean"]))
    print("-" * 100)
    print("单局赢分规模：", s["win_size"])
    print("番数分布  我方赢：", s["fan_hist_mine"])
    print("番数分布  对手赢：", s["fan_hist_opp"])
    print("-" * 100)
    print("我方杠总数 %d；按我方实际占位校正的期望 %s；比值 %s"
          % (s["my_gang_total"], s["position_expected_gang"], s["my_gang_vs_position_ratio"]))
    print("我方单局杠数分布：", s["my_gangs_per_round_hist"])
    print("爆头达成率按房：低于 1 的房 %d 个，高于 1 的房 %d 个；我方总胜场高于期望的房 %d 个 / %d"
          % (s["rooms_baotou_ratio_below_1"], s["rooms_baotou_ratio_above_1"],
             s["rooms_mywins_above_expected"], len(s["per_room_baotou"])))
    for row in s["per_room_baotou"]:
        print("  %-20s 局 %4d 爆头局 %3d 我赢爆头 %2d 期望 %5.2f 比值 %-6s 我总胜 %2d 期望 %5.2f 我方分 %+5d"
              % (row["room_id"], row["rounds"], row["baotou_rounds"], row["my_baotou_wins"],
                 row["expected"], row["ratio"], row["my_wins"], row["expected_wins"], row["my_total"]))
    print("赢家开局财神数（全部局 / 爆头局 / 非爆头局）：")
    for key, value in s["winner_start_whites_by_tag"].items():
        print("  %-20s %s" % (key, value))
    print("-" * 100)
    print("同番收益对拍（番|阵营）：", s["win_size_by_fan"])
    print("番数结构反事实：", s["fan_structure"])
    print("逐房番数结构差距（>0 表示我方赢面偏小）：正差距房 %d / %d"
          % (s["rooms_fan_gap_positive"], len(s["per_room_fan_gap"])))
    for row in s["per_room_fan_gap"]:
        print("  %-20s 局 %4d 我胜 %3d 我方分 %+5d 番数差距 %s"
              % (row["room_id"], row["rounds"], row["my_wins"], row["my_total"], row["gap"]))
    print("我方分杠种结果：", s["my_gang_by_kind_outcome"])
    print("抓打圈标记不一致（%d 局）：" % len(s["cp_mismatch_rows"]))
    for row in s["cp_mismatch_rows"]:
        print("  %s %s 局 %s 事件 %s" % (row["room_id"], row["game_id"], row["round_no"], row["events"]))
    print("-" * 100)
    print("流局明细（%d 局）：" % len(s["draw_rows"]))
    for row in s["draw_rows"]:
        print("  %s %s 局 %s 庄 %s 我方 %s 事件 %s" %
              (row["room_id"], row["game_id"], row["round_no"], row["dealer"],
               row["my_score"], row["n_events"]))
    print("-" * 100)
    print("%-20s%-40s%5s%6s%8s%8s%8s%6s%6s%7s%7s%6s" %
          ("room", "tag", "场", "局", "我方分", "我方杠", "对手杠", "明杠", "暗杠", "补杠",
           "爆头局", "流局"))
    for row in result["rooms"]:
        print("%-20s%-40s%5d%6d%8d%8d%8d%6d%6d%7d%7d%6d" % (
            row["room_id"], row["session_tag"], row["games"], row["rounds"], row["my_total"],
            row["my_gang"], row["opp_gang"], row["gang_ming"], row["gang_an"], row["gang_bu"],
            row["baotou_rounds"], row["draws"]))
    if "my_audit" in result:
        print("=" * 100)
        print("我方审计：")
        audit = result["my_audit"]
        for key in ("files", "games_touched", "counts", "phases", "action_kind_plan_rank1",
                    "action_kind_effective", "gang_candidates_offered", "gang_candidate_windows",
                    "gang_intents_submitted", "gang_rank1_by_kind", "hu_candidates_offered",
                    "hu_candidate_windows", "hu_rank1", "hu_declined_count",
                    "hu_declined_by_chosen", "hu_declined_hu_filtered_out",
                    "gang_declined_windows", "gang_declined_by_chosen",
                    "gang_offered_not_effective", "intent_by_kind",
                    "submission_outcomes", "catchplay_windows", "baotou_windows",
                    "chain_windows", "my_hand_whites_hist", "my_hand_whites_hist_when_baotou",
                    "submission_outcome_reasons_top", "rule_state_top"):
            print("  %-32s %s" % (key, audit.get(key)))


if __name__ == "__main__":
    raise SystemExit(main())
