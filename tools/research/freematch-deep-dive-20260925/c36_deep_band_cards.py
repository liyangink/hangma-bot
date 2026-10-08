#!/usr/bin/env python3
"""C36：深带窗与腾蛇分歧卡的逐窗价值复盘（只做逐窗诊断，不造候选、不跑完整桌）。

口径、三层窗定义、卡片字段、四问与判定三态逐字见同目录
C36-PREREG-DEEP-BAND-CARDS.md（该文件在本脚本任何结论性运行之前落盘，落盘后不改）。

纪律：
* 复用 C31 的窗口模型/重建/打分接缝与 C32 的跟打枚举（只读 import），
  本脚本不实现第二套规则；全部向听/听牌/爆头判定只经 hangma；
* 特征只用公开事实；赛后（番/得分/流局）只作解释列，不进任何判据；
* 不用腾蛇/Astra 的真实后续当我方反事实收益；
* 只读官方牌谱 events.json 与各房 manifest.json，不写 src/、policy/、hangma/。

用法：
    UV_CACHE_DIR=/tmp/uv-cache .venv/bin/python \
        review/freematch-deep-dive-20260925/c36_deep_band_cards.py
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
import json
import math
import os
import random
import statistics
import sys
import time
from pathlib import Path

ROOT = _PROJECT_ROOT
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "review" / "baotou-anatomy-20260925")))
sys.path.insert(0, str(HERE))

import anatomy_lib as AL  # noqa: E402
import c31_action_layer_gap as C31  # noqa: E402
import c32_cards as C32  # noqa: E402

C27 = C31.C27
"""C27 的格定义（C31 只读 import 的同一模块对象，键与 feature_of_record 相同）。"""

from hangma_bot.hangma import progression  # noqa: E402
from hangma_bot.kernel.actions import Tile  # noqa: E402

OUT = _project_file(_PROJECT_ROOT, ROOT / ".team-work" / "c36-deep-band")
C32_WINDOWS = _project_file(_PROJECT_ROOT, ROOT / ".team-work" / "c32-cards" / "windows.jsonl.gz")

ME = AL.ME
WEALTH = C31.WEALTH
CLAIM_TYPES = C31.CLAIM_TYPES
FIXED = {"peng": -6.0, "chi": -10.0, "gang": 40.0}
"""冻结父代对非弃牌候选的固定项（r18_integrated_positive_v2 源码 166-173 行）。"""

TENG = "u_b2aa6abe7811"
ASTRA = "u_a24596248186"
L2_ROOMS = ("a_53f4861835b9", "a_5e16dfc1305b", "a_d773a8e428a0", "a_d8e15fe8bc96")
L3_ROOMS = ("a_b0d2cf5da218", "a_d7c3190a1422")
V1_SHA = "0d3c094d"
V2_SHA = "a2d9b8af"

BOOTSTRAP_DRAWS = 1200
BOOTSTRAP_SEED = 20260926

L1_DEF = "听牌 ∧ dw >= 6 ∧ margin <= -6"
"""C32 冻结的深带定义；L1 = C32 cards 里符合它的键集合。"""

READ_PATHS = []
"""本脚本实际读取的文件路径（泄漏检查用）。"""


# ---------------------------------------------------------------------------
# 房级策略身份（只读各房 manifest.json，不按战役目录推断）
# ---------------------------------------------------------------------------


def room_identity():
    """返回 {room: {policy_version, sha12, schema, tag, n_runs}}。"""

    found = collections.defaultdict(set)
    pattern = str(_project_file(_PROJECT_ROOT, ROOT / "artifacts" / "sessions" / "*" / "audit" / "runs" / "*"
                  / "manifest.json"))
    for path in sorted(glob.glob(pattern)):
        try:
            doc = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        room = (doc.get("context") or {}).get("tournament_id")
        payload = doc.get("payload") or {}
        if not room:
            continue
        release = payload.get("policy_release") or {}
        found[room].add((payload.get("policy_version"),
                         (release.get("candidate_source_sha256") or "")[:12],
                         release.get("schema")))
    result = {}
    for room, entries in found.items():
        hashes = sorted({sha for _v, sha, _s in entries})
        versions = sorted({v for v, _s, _x in entries})
        if hashes and all(sha.startswith(V2_SHA) for sha in hashes):
            tag = "R18 v2"
        elif hashes and all(sha.startswith(V1_SHA) for sha in hashes):
            tag = "R18 v1"
        else:
            tag = "mixed/other"
        result[room] = {
            "policy_version": versions[0] if len(versions) == 1 else versions,
            "sha12": hashes, "schema": sorted({s for _v, _h, s in entries}),
            "tag": tag, "n_runs": len(entries)}
    return result


# ---------------------------------------------------------------------------
# 打分接缝（C31.score_window 的逐字镜像 + 保留完整 trace）
# ---------------------------------------------------------------------------


def score_window_full(observation, parent):
    """与 C31.score_window 同一条接缝、同一个 decision_id；额外保留每个动作的 trace。

    一致性由 selfcheck_consistency() 抽样逐位断言（scores 必须完全相同）。
    """

    analysis = C31.RULES.analyze(observation, value_limits=C31.VALUE_LIMITS)
    request = C31.DecisionRequest(
        observation=observation,
        competition=C31.CompetitionContext(
            tournament_id="c31-offline",
            stage_no=None, stage_role=None, stage_total=None,
            participant_rank=None, ranking=(), observed_at_unix_ms=0),
        rules=analysis,
        decision_id="c31",
        trigger_seq=observation.snapshot_seq,
        window_key=C31.WindowKey(
            game_id=observation.game_id, round_no=observation.round_no,
            trigger_seq=observation.snapshot_seq,
            phase=(C31.WindowPhase.RESPONSE_PENG if observation.phase == "response_peng"
                   else C31.WindowPhase.RESPONSE_CHI),
            seat=observation.seat),
        rejected_attempts=(),
    )
    view = C31.build_scoring_view(request, value_limits=C31.VALUE_LIMITS).candidate_view()
    result = parent(view)
    status = result.get("status")
    if status != "SCORED":
        return view, None, status, result.get("reason"), analysis
    entries = {}
    for item in result.get("entries") or []:
        entries[item["action_key"]] = {
            "score": item.get("score"), "trace": item.get("trace") or {},
            "action_type": item.get("action_type")}
    return view, entries, status, None, analysis


def evaluate_window_full(snap, seat, phases, game_id, round_no, parent):
    """C31.evaluate_window 的逐字镜像（窗口取两 phase 最大 margin）。"""

    per_phase = []
    audit = collections.Counter()
    for phase in phases:
        observation = C31.build_observation(snap, seat, phase, game_id, round_no)
        view, entries, status, reason, analysis = score_window_full(observation, parent)
        entry = {"phase": phase, "view": view, "entries": entries, "status": status,
                 "observation": observation, "analysis": analysis,
                 "degraded": analysis.completeness.value != "complete",
                 "issues": tuple(issue.area for issue in analysis.issues)}
        if status != "SCORED":
            entry["reason"] = reason
            per_phase.append(entry)
            audit["abstain_" + phase] += 1
            continue
        actions = view["actions"]
        claims = [item for item in actions
                  if item["action_type"] in CLAIM_TYPES and item["action_key"] in entries]
        passes = [item for item in actions
                  if item["action_type"] == "pass" and item["action_key"] in entries]
        if not passes or not claims:
            audit["degenerate_no_pass" if not passes else "degenerate_no_claim"] += 1
            per_phase.append(entry)
            continue
        pass_action = passes[0]
        best = max(claims, key=lambda item: (entries[item["action_key"]]["score"],
                                             item["action_key"]))
        entry.update({
            "pass": pass_action, "pass_score": entries[pass_action["action_key"]]["score"],
            "claim": best, "claim_score": entries[best["action_key"]]["score"],
            "margin": (entries[best["action_key"]]["score"]
                       - entries[pass_action["action_key"]]["score"]),
            "has_peng": any(item["action_type"] == "peng" for item in actions),
            "has_chi": any(item["action_type"] == "chi" for item in actions),
            "has_gang": any(item["action_type"] == "gang" for item in actions),
            "visible": view["visible_state"],
        })
        per_phase.append(entry)
    scored = [item for item in per_phase if "margin" in item]
    if not scored:
        return None, per_phase, audit
    chosen = max(scored, key=lambda item: (item["margin"], item["phase"]))
    opportunity = any(item.get("has_peng") or item.get("has_chi") for item in scored)
    if not opportunity:
        return None, per_phase, audit
    return chosen, per_phase, audit


# ---------------------------------------------------------------------------
# 六项拆解（冻结父代源码 117-176 行的项名与公式）
# ---------------------------------------------------------------------------


def terms_of(trace, action_type):
    """六项：向听项 / 支持项 / 罚项 / 白板项 / 风险项 / 风格项。"""

    base = trace.get("base_score")
    shanten = trace.get("shanten_after")
    unknown = trace.get("unknown") is True
    shanten_term = None
    support_term = None
    if (not unknown and base is not None and shanten is not None
            and not isinstance(shanten, bool)):
        shanten_term = -100.0 * float(shanten)
        support_term = float(base) - shanten_term
    risk_units = trace.get("risk_units") or 0.0
    wealth = trace.get("wealth_part")
    return {
        "unknown": unknown,
        "shanten": shanten_term,
        "support": support_term,
        "fixed": FIXED.get(action_type, 0.0),
        "wealth": None if wealth is None else float(wealth),
        "wealth_discard": float(trace.get("wealth_discard_part") or 0.0),
        "river": float(trace.get("river_part") or 0.0),
        "risk": (-round(6.0 * float(risk_units), 1) if action_type == "discard" else 0.0),
        "style": float(trace.get("style_part") or 0.0),
    }


def delta_terms(claim_terms, pass_terms):
    """鸣牌候选 - 过牌的六项差（未含叠加层残差）。"""

    if claim_terms["shanten"] is None or pass_terms["shanten"] is None:
        return None
    out = {}
    for key in ("shanten", "support", "fixed", "wealth", "wealth_discard", "river",
                "risk", "style"):
        out[key] = (claim_terms[key] or 0.0) - (pass_terms[key] or 0.0)
    return out


def useful_kinds(action):
    tiles = action.get("useful_tiles")
    return None if tiles is None else len(tiles)


def structural_upper_bound(hand_codes, meld_count):
    """预登记 Q1(d) 的机械上界：从当前手牌再去掉一张后是否进爆头。

    当前手牌已是「弃牌后」的合法张数（13 - 3x副露），再去掉一张落到 12 - 3x副露，
    **不是**规则中任何停牌张数；本读数只作机械上界登记，不作机制结论。
    """

    hand = tuple(Tile(code) for code in hand_codes)
    seen = set()
    for index, tile in enumerate(hand):
        if tile.code in seen:
            continue
        seen.add(tile.code)
        after = hand[:index] + hand[index + 1:]
        try:
            if progression.baotou_after_discard(after, meld_count):
                return True
        except Exception:  # noqa: BLE001 —— 规则层拒绝时如实跳过
            continue
    return False


def static_baotou_now(hand_codes, meld_count):
    """当前手牌的静态爆头条件（规则层对 13-3x副露 张暗牌的任意听判定）。"""

    try:
        return bool(progression.recompute_baotou(
            tuple(Tile(code) for code in hand_codes), meld_count, 0))
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# 逐窗记录
# ---------------------------------------------------------------------------


def build_record(snap, seat, phases, window, game_id, round_no, room, session, group,
                 user_id, primary, outcome, identity, audit):
    observation = window["observation"]
    visible = window["visible"]
    view = window["view"]
    entries = window["entries"]
    feature = C31.parent_space_feature(window)
    labels = C27.cells(feature)
    claim_key = window["claim"]["action_key"]
    pass_action = window["pass"]
    pass_key = pass_action["action_key"]
    pass_W = C31.width_of(pass_action)
    claim_W = C31.width_of(window["claim"])
    claim_type = window["claim"]["action_type"]
    pass_terms = terms_of(entries[pass_key]["trace"], "pass")
    claim_terms = terms_of(entries[claim_key]["trace"], claim_type)
    delta = delta_terms(claim_terms, pass_terms)
    residual = None
    if delta is not None:
        residual = round(float(window["margin"]) - sum(delta.values()), 6)
        audit["terms_checked"] += 1
        if abs(residual) > 1e-6:
            audit["terms_residual_nonzero"] += 1
    # 冻结父代的**最终** entries 不带 action_type（源码 445 行只留 action_key/score/trace），
    # 动作类型一律从同一张观察的 action 表取（C32 同序），不从 entries 反查。
    types_by_key = {item["action_key"]: item["action_type"] for item in view["actions"]}
    claims = []
    for candidate in window["analysis"].legal_candidates:
        key = candidate.action_key
        kind = types_by_key.get(key)
        if kind not in CLAIM_TYPES or key not in entries:
            continue
        item = C32.action_entry(view, key)
        if item is None:
            continue
        entry = {
            "action_key": key, "action_type": kind,
            "shanten_after": item.get("shanten_after"),
            "W_after": C31.width_of(item), "kinds": useful_kinds(item),
            "baotou_after": item.get("baotou_after"),
            "best_followup_discard": item.get("best_followup_discard"),
            "score": entries[key]["score"],
            "terms": terms_of(entries[key]["trace"], kind),
            "is_pick": key == claim_key,
        }
        entry["dw_vs_pass"] = (None if (entry["W_after"] is None or pass_W is None)
                               else entry["W_after"] - pass_W)
        detail = C32.followup_detail(observation, candidate.action)
        if detail is not None:
            post = detail["post"]
            entry.update({
                "fu_discard": detail["discard"], "fu_shanten": detail["shanten"],
                "fu_W": detail["width"], "fu_value": detail["value"],
                "fu_baotou": C32.baotou_after_followup(post, detail["discard"]),
                "fu_exposed": C32.visible_code_count(snap, detail["discard"]),
            })
            entry["fu_exposed_new"] = entry["fu_exposed"] == 0
        claims.append(entry)
    actual = snap["claim_kind"] if snap["claim_seat"] == seat else None
    claimed = 1 if actual in ("peng", "chi", "gang") else 0
    scores_arr = list(outcome.get("scores") or ())
    seat_delta = scores_arr[seat] if seat < len(scores_arr) else None
    hand_codes = [tile.code for tile in observation.my_hand]
    meld_count = len(visible["melds"][seat])
    hu_keys = [item["action_key"] for item in view["actions"]
               if item["action_type"] == "hu"]
    gang_better = None
    for item in view["actions"]:
        if item["action_type"] != "gang":
            continue
        value = entries.get(item["action_key"], {}).get("score")
        if value is None:
            continue
        if gang_better is None or value > gang_better:
            gang_better = value
    record = {
        "game_id": game_id, "round_no": round_no, "seq": snap["seq"], "seat": seat,
        "room": room, "session": session, "group": group, "user_id": user_id,
        "primary": primary,
        "policy_version": (identity or {}).get("policy_version"),
        "release_sha": (identity or {}).get("sha12"),
        "release_schema": (identity or {}).get("schema"),
        "room_version": (identity or {}).get("tag"),
        "phase": window["phase"], "phases": phases,
        "dealer_seat": visible["dealer_seat"], "is_dealer": visible["dealer_seat"] == seat,
        "wall": visible.get("remaining_tile_count"),
        "turn": len(visible["discards"][seat]),
        "melds": meld_count,
        "opp_meld_seats": sum(1 for index in range(4)
                              if index != seat and len(visible["melds"][index]) > 0),
        "whites": visible["my_hand"].count(WEALTH),
        "discarder": snap["discarder"], "tile": snap["tile"],
        "my_hand_codes": hand_codes,
        "my_meld_groups": [group_item["kind"] + ":" + ",".join(group_item["tiles"])
                           for group_item in snap["melds"][seat]],
        "my_river": list(snap["rivers"][seat]),
        "labels": labels, "feature": feature,
        "pass_key": pass_key, "pass_score": window["pass_score"],
        "pass_shanten": pass_action.get("shanten_after"), "pass_W": pass_W,
        "pass_kinds": useful_kinds(pass_action),
        "pass_bt": pass_action.get("baotou_after"),
        "claim_key": claim_key, "claim_type": claim_type,
        "claim_score": window["claim_score"],
        "claim_shanten": window["claim"].get("shanten_after"), "claim_W": claim_W,
        "claim_kinds": useful_kinds(window["claim"]),
        "claim_bt": window["claim"].get("baotou_after"),
        "margin": window["margin"],
        "dw": (None if (claim_W is None or pass_W is None) else claim_W - pass_W),
        "dsh": (None if (pass_action.get("shanten_after") is None
                         or window["claim"].get("shanten_after") is None)
                else (window["claim"].get("shanten_after")
                      - pass_action.get("shanten_after"))),
        "terms_pass": pass_terms, "terms_claim": claim_terms,
        "terms_delta": delta, "terms_residual": residual,
        "parent_plan_first": C32.scored_plan(
            view, {key: value["score"] for key, value in entries.items()})[0],
        "claims": claims,
        "degraded": bool(window.get("degraded")),
        "issue_areas": list(window.get("issues") or ()),
        "hu_keys": hu_keys,
        "gang_beats_claim": (None if gang_better is None
                             else bool(gang_better > window["claim_score"])),
        "actual": actual, "claimed": claimed,
        "outcome": {"fan": outcome.get("fan"), "detail": outcome.get("detail"),
                    "draw": outcome.get("draw"), "scores": scores_arr,
                    "seat_delta": seat_delta, "winner_seat": outcome.get("winner_seat")},
    }
    record["parent_claims"] = 1 if window["margin"] > 0 else 0
    audit["claims_total"] += len(claims)
    audit["claims_with_fu"] += sum(1 for item in claims if "fu_baotou" in item)
    audit["claims_fu_true"] += sum(1 for item in claims if item.get("fu_baotou") is True)
    record["any_fu_baotou"] = bool(any(item.get("fu_baotou") is True for item in claims))
    pick = next((item for item in claims if item["is_pick"]), None)
    record["pick_fu_baotou"] = None if pick is None else pick.get("fu_baotou")
    record["pick_fu_shanten"] = None if pick is None else pick.get("fu_shanten")
    record["pick_fu_W"] = None if pick is None else pick.get("fu_W")
    record["pick_fu_W_gain"] = (None if (pick is None or pick.get("fu_W") is None
                                         or pass_W is None)
                                else float(pick["fu_W"]) - float(pass_W))
    record["won"] = (outcome.get("winner_seat") == seat)
    return record


_BOARD = None


def board():
    global _BOARD
    if _BOARD is None:
        import c23_claim_opportunity as C23
        loaded, path = C23.load_board()
        READ_PATHS.append(path)
        _BOARD = loaded
    return _BOARD


_PRIMARY = None


def primary_index():
    global _PRIMARY
    if _PRIMARY is None:
        path = _project_file(_PROJECT_ROOT, ROOT / "review" / "baotou-anatomy-20260925" / "rounds.jsonl")
        READ_PATHS.append(str(path))
        rows = [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]
        _PRIMARY = {(row["game_id"], row["round_no"]) for row in rows}
    return _PRIMARY


def build_windows(games, parent, identities, audit, rooms=None):
    """语料逐窗重建；rooms 为 None 时跑全部。"""

    board_ids = board()
    primary_ids = primary_index()
    records = []
    rounds_done = 0
    for game in games:
        document = game["doc"]
        room = document.get("room_id") or game["session"]
        if rooms is not None and room not in rooms:
            continue
        users = [item.get("user_id") for item in (document.get("seats") or [])]
        groups = []
        for index in range(4):
            user = users[index] if index < len(users) else None
            groups.append("me" if user == ME
                          else ("elite" if user in board_ids else "other"))
        if "me" not in groups and "elite" not in groups:
            continue
        block_meta = C31.round_metadata(document)
        table = [0, 0, 0, 0]
        game_id = document.get("game_id") or game["game_id"]
        for round_no, events, start_hands in AL.round_blocks(document):
            if not start_hands or not all(isinstance(hand, list) for hand in start_hands):
                continue
            ended_dealer, ended_scores = C31.round_end_facts(events)
            dealer = (block_meta.get(round_no) or {}).get("dealer")
            if dealer is None:
                dealer = ended_dealer
            if dealer is None:
                dealer = next((index for index, hand in enumerate(start_hands)
                               if len(hand) == 14), None)
            if dealer is None:
                audit["round_without_dealer"] += 1
                continue
            outcome = C32.round_outcome(events)
            winner = next((event.get("seat") for event in events
                           if event.get("type") == "round_ended"), None)
            if outcome.get("draw") is True:
                winner = None
            outcome["winner_seat"] = winner
            snaps = C31.reconstruct(events, start_hands, table, dealer)
            rounds_done += 1
            primary = (game_id, round_no) in primary_ids and "elite" in groups
            identity = identities.get(room)
            for seq in sorted(snaps):
                snap = snaps[seq]
                if snap["tile"] == WEALTH:
                    audit["white_discard_no_window"] += 1
                    continue
                discarder = snap["discarder"]
                peng = C31._peng_members(discarder, snap["tile"], snap["owner"])
                chi = C31._chi_members(discarder, snap["tile"], snap["owner"])
                for seat in range(4):
                    if seat == discarder or groups[seat] not in C31.GROUPS:
                        continue
                    phases = []
                    if seat in peng:
                        phases.append("response_peng")
                    if seat in chi:
                        phases.append("response_chi")
                    if not phases:
                        continue
                    audit["seat_discard_windows"] += 1
                    window, _per_phase, window_audit = evaluate_window_full(
                        snap, seat, phases, game_id, round_no, parent)
                    audit.update(window_audit)
                    if window is None:
                        audit["not_opportunity"] += 1
                        continue
                    records.append(build_record(
                        snap, seat, phases, window, game_id, round_no, room,
                        game["session"], groups[seat],
                        users[seat] if seat < len(users) else None, primary, outcome,
                        identity, audit))
            if ended_scores is not None:
                table = [a + b for a, b in zip(table, ended_scores)]
    return records, rounds_done


def selfcheck_consistency(games, parent, sample=240):
    """抽样断言：本脚本的打分接缝与 C31.score_window 逐位一致。"""

    checked = 0
    seen = 0
    for game in games:
        document = game["doc"]
        if ME not in [item.get("user_id") for item in (document.get("seats") or [])]:
            continue
        seen += 1
        if seen % 7 != 0:
            continue
        meta = C31.round_metadata(document)
        table = [0, 0, 0, 0]
        for round_no, events, start_hands in AL.round_blocks(document):
            if not start_hands:
                continue
            dealer = (meta.get(round_no) or {}).get("dealer")
            if dealer is None:
                continue
            snaps = C31.reconstruct(events, start_hands, table, dealer)
            for seq in sorted(snaps):
                snap = snaps[seq]
                if snap["tile"] == WEALTH:
                    continue
                for seat in range(4):
                    if seat == snap["discarder"]:
                        continue
                    phases = C32.phases_for(snap, seat)
                    if not phases:
                        continue
                    observation = C31.build_observation(snap, seat, phases[0],
                                                        game["game_id"], round_no)
                    _v1, s1, st1, _r1, _a1, _b1 = C31.score_window(observation, parent)
                    _v2, e2, st2, _r2, _a2 = score_window_full(observation, parent)
                    if st1 != st2:
                        raise AssertionError(("status", st1, st2))
                    if st1 == "SCORED":
                        s2 = {key: value["score"] for key, value in e2.items()}
                        if dict(s1) != dict(s2):
                            raise AssertionError(("scores", game["game_id"], round_no,
                                                  snap["seq"], seat))
                    checked += 1
                    break
                if checked >= sample:
                    return {"checked": checked, "ok": True}
        if checked >= sample:
            break
    return {"checked": checked, "ok": True}



# ---------------------------------------------------------------------------
# 统计小工具
# ---------------------------------------------------------------------------


def fmt(value, digits=3, signed=False):
    if value is None:
        return "-"
    return ("%+.*f" if signed else "%.*f") % (digits, value)


def quantile(values, probability):
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = probability * (len(ordered) - 1)
    low = int(math.floor(position))
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def group_by_room(records):
    out = collections.defaultdict(list)
    for record in records:
        out[record["room"]].append(record)
    return out


def cluster_bootstrap(records, statistic, draws=BOOTSTRAP_DRAWS, seed=BOOTSTRAP_SEED):
    """按房 cluster bootstrap（重抽整房，不把窗当独立复现）。"""

    by_room = group_by_room(records)
    rooms = sorted(by_room)
    if not rooms:
        return {"lo": None, "hi": None, "mean": None, "rooms": 0, "draws": 0}
    rng = random.Random(seed)
    values = []
    for _ in range(draws):
        pool = []
        for _ in rooms:
            pool.extend(by_room[rng.choice(rooms)])
        value = statistic(pool)
        if value is not None:
            values.append(value)
    if not values:
        return {"lo": None, "hi": None, "mean": None, "rooms": len(rooms), "draws": 0}
    values.sort()
    return {"lo": values[int(0.025 * len(values))],
            "hi": values[min(len(values) - 1, int(0.975 * len(values)))],
            "mean": statistics.fmean(values), "rooms": len(rooms), "draws": len(values)}


def rate(records, predicate):
    if not records:
        return None
    return sum(1 for record in records if predicate(record)) / len(records)


def key_of(record):
    return (record["game_id"], record["round_no"], record["seq"], record["seat"])


def is_band(record):
    return (record["pass_shanten"] == 0 and record["dw"] is not None
            and record["dw"] >= 6.0 and record["margin"] is not None
            and record["margin"] <= -6.0)


PREDICATES = collections.OrderedDict((
    ("P1:band", lambda r: (r["pass_shanten"] == 0 and r["dw"] is not None
                           and r["dw"] >= 6.0)),
    ("P2:gated", lambda r: (r["pass_shanten"] == 0 and r["dw"] is not None
                            and r["dw"] >= 6.0 and r["melds"] <= 1
                            and (r["wall"] or 0) >= 40)),
    ("P3:same", lambda r: (r["dsh"] == 0 and r["dw"] is not None
                           and r["dw"] >= 6.0)),
    ("P4:fu_bto", lambda r: bool(r["any_fu_baotou"])),
))


def change_rate(records, predicate, dose):
    """该层内「父代首选为过 ∧ 判据为真 ∧ margin + d > 0」的窗占比。"""

    if not records:
        return None
    hits = sum(1 for record in records
               if predicate(record) and (record["margin"] or 0.0) <= 0.0
               and (record["margin"] or 0.0) + dose > 0.0)
    return hits / len(records)


def load_c32_band_keys():
    """L1 = C32 冻结的「听牌 ∧ dw >= 6 ∧ margin <= -6」键集合。"""

    READ_PATHS.append(str(C32_WINDOWS))
    keys = set()
    with gzip.open(C32_WINDOWS, "rt", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if (row["pass_shanten"] == 0 and row["dw"] is not None
                    and row["dw"] >= 6.0 and (row["margin"] or 0) <= -6.0):
                keys.add(tuple(row["key"]))
    return keys


def annotate_baotou_side(records):
    """给不鸣侧补两个规则层读数：静态爆头条件与预登记 Q1(d) 的机械上界。"""

    for record in records:
        record["bt_static"] = static_baotou_now(record["my_hand_codes"], record["melds"])
        record["struct_ub"] = structural_upper_bound(record["my_hand_codes"],
                                                     record["melds"])
    return records


def feature_table(records, label):
    if not records:
        return {"layer": label, "windows": 0}
    return {
        "layer": label, "windows": len(records),
        "rooms": len({r["room"] for r in records}),
        "pass_shanten": dict(sorted(collections.Counter(
            str(r["pass_shanten"]) for r in records).items())),
        "dsh": dict(sorted(collections.Counter(str(r["dsh"]) for r in records).items())),
        "whites": dict(sorted(collections.Counter(min(2, r["whites"])
                                                  for r in records).items())),
        "dealer_share": sum(1 for r in records if r["is_dealer"]) / len(records),
        "melds": dict(sorted(collections.Counter(min(2, r["melds"])
                                                 for r in records).items())),
        "turn_median": quantile([r["turn"] for r in records], 0.5),
        "wall_median": quantile([r["wall"] for r in records], 0.5),
        "margin_median": quantile([r["margin"] for r in records], 0.5),
        "margin_min": min(r["margin"] for r in records),
        "margin_max": max(r["margin"] for r in records),
        "dw_median": quantile([r["dw"] for r in records if r["dw"] is not None], 0.5),
        "claimed_share": sum(r["claimed"] for r in records) / len(records),
        "listening_share": sum(1 for r in records if r["pass_shanten"] == 0) / len(records),
        "bt_now_share": sum(1 for r in records if r["pass_bt"] is True) / len(records),
        "bt_static_share": sum(1 for r in records if r.get("bt_static") is True) / len(records),
        "fu_baotou_share": sum(1 for r in records if r["any_fu_baotou"]) / len(records),
        "band_share": sum(1 for r in records if is_band(r)) / len(records),
    }


# ---------------------------------------------------------------------------
# Q5（主审增补，预登记后落盘）：鸣后换积分 vs 只换爆头的可分性
# ---------------------------------------------------------------------------

Q5_FEATURES = collections.OrderedDict((
    ("listening（过牌向听 0）", lambda r: r["pass_shanten"] == 0),
    ("dw>=1", lambda r: r["dw"] is not None and r["dw"] >= 1.0),
    ("dw>=3", lambda r: r["dw"] is not None and r["dw"] >= 3.0),
    ("dw>=6", lambda r: r["dw"] is not None and r["dw"] >= 6.0),
    ("W_pass>=16", lambda r: (r["pass_W"] or 0) >= 16.0),
    ("whites>=1（持白）", lambda r: r["whites"] >= 1),
    ("melds<=1（副露<=1）", lambda r: r["melds"] <= 1),
    ("wall>=40", lambda r: (r["wall"] or 0) >= 40),
    ("turn<=6（巡目<=6）", lambda r: r["turn"] <= 6),
    ("is_dealer（庄）", lambda r: bool(r["is_dealer"])),
    ("bt_now（鸣前已爆头）", lambda r: r["pass_bt"] is True),
    ("[中介]鸣后仍听牌", lambda r: r["pick_fu_shanten"] == 0),
    ("[中介]鸣后张数净增>=1", lambda r: (r["pick_fu_W_gain"] is not None
                                          and r["pick_fu_W_gain"] >= 1.0)),
    ("[中介]鸣后张数净增>=6", lambda r: (r["pick_fu_W_gain"] is not None
                                          and r["pick_fu_W_gain"] >= 6.0)),
    ("[中介]鸣后进爆头", lambda r: bool(r["any_fu_baotou"])),
))
# 前 11 项可由候选面的公开事实算出（行动前可算）；后 4 项标注 [中介]，
# 其中「鸣后进爆头」在候选源码面不可得（C32 负控），只作分析侧参照，不进候选。


def q5_block(records):
    """按赛后标签分层：鸣 -> 该座当局得分 > 0（换到积分） vs <= 0（没换到）。

    标签只作解释与分层，不作因果；强手真实后续不当作我方反事实收益。
    """

    def usable(rows):
        return [r for r in rows if r["claimed"] == 1
                and r["outcome"]["seat_delta"] is not None]

    def positive(record):
        return (record["outcome"]["seat_delta"] or 0) > 0

    groups = collections.OrderedDict((
        ("全语料·真实鸣", usable(records)),
        ("腾蛇(L2 四房)", usable([r for r in records
                                  if r["user_id"] == TENG and r["room"] in L2_ROOMS])),
        ("Astra(L3 两房)", usable([r for r in records
                                   if r["user_id"] == ASTRA and r["room"] in L3_ROOMS])),
        ("我方(me)", usable([r for r in records if r["group"] == "me"])),
        ("其它 elite", usable([r for r in records
                               if r["group"] == "elite"
                               and r["user_id"] not in (TENG, ASTRA)])),
    ))
    out = {"groups": {}, "split": {}, "note": ("赛后标签只作分层与解释；"
                                               "不代表鸣牌的因果收益")}
    for label, rows in groups.items():
        if not rows:
            out["groups"][label] = {"windows": 0}
            continue
        bao = [r for r in rows if r["any_fu_baotou"]]
        plain = [r for r in rows if not r["any_fu_baotou"]]
        out["groups"][label] = {
            "windows": len(rows),
            "rooms": len({r["room"] for r in rows}),
            "positive_share": rate(rows, positive),
            "won_share": rate(rows, lambda r: bool(r["won"])),
            "fu_baotou_windows": len(bao),
            "fu_baotou_positive_share": rate(bao, positive),
            "no_fu_baotou_windows": len(plain),
            "no_fu_baotou_positive_share": rate(plain, positive),
        }
        if bao and plain:
            out["groups"][label]["fu_baotou_gain_pp"] = (
                100.0 * (rate(bao, positive) - rate(plain, positive)))
            out["groups"][label]["fu_baotou_gain_ci"] = cluster_bootstrap(
                rows, lambda pool: (
                    None if (not [r for r in pool if r["any_fu_baotou"]]
                             or not [r for r in pool if not r["any_fu_baotou"]])
                    else 100.0 * (rate([r for r in pool if r["any_fu_baotou"]], positive)
                                  - rate([r for r in pool if not r["any_fu_baotou"]],
                                         positive))))
        # 「换成积分」vs「只换成爆头」：只在鸣后进爆头的窗内比较
        pos = [r for r in bao if positive(r)]
        neg = [r for r in bao if not positive(r)]
        features = {}
        for name, predicate in Q5_FEATURES.items():
            features[name] = {
                "positive_hit": rate(pos, predicate), "negative_hit": rate(neg, predicate),
                "delta": (None if (not pos or not neg)
                          else rate(pos, predicate) - rate(neg, predicate)),
            }
        out["split"][label] = {"positive_windows": len(pos), "negative_windows": len(neg),
                               "features": features}
    return out


# ---------------------------------------------------------------------------
# 人可读卡
# ---------------------------------------------------------------------------


def cards_markdown(records, start=1):
    blocks = []
    for index, record in enumerate(records, start=start):
        claims = sorted(record["claims"],
                        key=lambda item: (not item["is_pick"], item["action_key"]))
        delta = record["terms_delta"] or {}
        lines = [
            "**卡 %d｜%s r%s seq%s 座%s（%s%s）**"
            % (index, record["game_id"], record["round_no"], record["seq"], record["seat"],
               record["group"],
               "／腾蛇" if record["user_id"] == TENG else
               ("／Astra" if record["user_id"] == ASTRA else "")),
            "- 身份：房 %s（%s；%s；%s）｜会话 %s｜父代被选 %s｜降级 %s｜更高优先级动作 %s"
            % (record["room"], record["room_version"],
               ",".join(record["release_sha"] or []) or "-",
               record["policy_version"] or "-", record["session"],
               record["parent_plan_first"], record["degraded"],
               ("胡 " + ",".join(record["hu_keys"])) if record["hu_keys"] else
               ("明杠分更高" if record["gang_beats_claim"] else "无")),
            "- 鸣前公开态：向听 %s｜有效牌 %s 张／%s 种｜白板 %s｜副露 %s｜他家副露 %s 家｜"
            "巡目 %s｜墙余 %s｜%s｜座 %s 打「%s」"
            % (record["pass_shanten"], fmt(record["pass_W"], 0), record["pass_kinds"],
               record["whites"], record["melds"], record["opp_meld_seats"], record["turn"],
               record["wall"], "庄" if record["is_dealer"] else "闲",
               record["discarder"], record["tile"]),
            "- 手牌「%s」｜副露 %s｜牌河 %s"
            % ("".join(record["my_hand_codes"]), record["my_meld_groups"] or "无",
               "".join(record["my_river"]) or "空"),
            "- 父代：margin %s｜六项差 向听 %s／支持 %s／罚 %s／白板 %s／风险 %s／风格 %s｜"
            "叠加残差 %s"
            % (fmt(record["margin"], 1, True), fmt(delta.get("shanten"), 1, True),
               fmt(delta.get("support"), 1, True), fmt(delta.get("fixed"), 1, True),
               fmt((delta.get("wealth") or 0.0) + (delta.get("wealth_discard") or 0.0),
                   1, True),
               fmt(delta.get("risk"), 1, True), fmt(delta.get("style"), 1, True),
               fmt(record["terms_residual"], 1, True)),
        ]
        for item in claims:
            lines.append(
                "  - 候选 %s「%s」｜dw %s｜分 %s｜鸣后向听 %s／张 %s／种 %s／动作层爆头 %s｜"
                "跟打「%s」→向听 %s／张 %s／**爆头 %s**／公开 %s"
                % ("★" if item["is_pick"] else "・", item["action_key"],
                   fmt(item.get("dw_vs_pass"), 1, True), fmt(item["score"], 1, True),
                   item["shanten_after"], fmt(item["W_after"], 0), item["kinds"],
                   item["baotou_after"], item.get("fu_discard"), item.get("fu_shanten"),
                   fmt(item.get("fu_W"), 0), item.get("fu_baotou"),
                   item.get("fu_exposed")))
        lines.append("- 不鸣侧：bt_now（继承态）%s｜静态爆头条件 %s｜机械上界 %s｜"
                     "鸣后任一进爆头 %s"
                     % (record["pass_bt"], record.get("bt_static"), record.get("struct_ub"),
                        record["any_fu_baotou"]))
        outcome = record["outcome"]
        lines.append("- 赛后（不作特征）：真实动作 %s｜番 %s／%s｜流局 %s｜该座当局得分 %s｜"
                     "四座 %s"
                     % (record["actual"] or "过", outcome.get("fan"),
                        "／".join(outcome.get("detail") or []) or "-", outcome.get("draw"),
                        outcome.get("seat_delta"), outcome.get("scores")))
        blocks.append(chr(10).join(lines))
    return (chr(10) + chr(10)).join(blocks)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def main():
    started = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    parent = C31.load_parent()
    print("冻结父代装配：%s" % C31.R18_INTEGRATED_POSITIVE_V2_SHA256[:16])
    identities = room_identity()
    versions = collections.Counter(item["tag"] for item in identities.values())
    print("房级策略身份（读各房 manifest.json）：%d 房 %s" % (len(identities), dict(versions)))
    games = AL.load_games()
    READ_PATHS.extend(game["path"] for game in games)
    print("官方牌谱按 game_id 去重：%d 场" % len(games))
    limit = int(os.environ.get("C36_GAME_LIMIT", "0") or 0)
    if limit:
        games = games[:limit]
        print("C36_GAME_LIMIT=%d：只跑前 %d 场（冒烟用，不用于结论）" % (limit, limit))

    audit = collections.Counter()
    consistency = selfcheck_consistency(games, parent)
    print("接缝自检（与 C31.score_window 逐位比对）：%d 窗，%s"
          % (consistency["checked"], "一致" if consistency["ok"] else "**不一致**"))

    records, rounds_done = build_windows(games, parent, identities, audit)
    print("重建 %d 局，机会窗 %d 个，用时 %.1f 秒"
          % (rounds_done, len(records), time.time() - started))
    print("审计：%s" % json.dumps(dict(sorted(audit.items())), ensure_ascii=False))

    l1_keys = load_c32_band_keys()
    found = {key_of(record) for record in records}
    l1 = [record for record in records if key_of(record) in l1_keys]
    l1_missing = sorted(l1_keys - found)
    l1_new = [record for record in records if is_band(record)]
    print("L1（C32 冻结键集合）：%d/%d 命中，缺 %d 个" % (len(l1), len(l1_keys), len(l1_missing)))
    print("同定义在新语料上的窗数：%d" % len(l1_new))

    l2 = [record for record in records
          if record["room"] in L2_ROOMS and record["user_id"] == TENG
          and record["claimed"] == 1 and (record["margin"] or 0.0) <= 0.0]
    l2_all = [record for record in records
              if record["room"] in L2_ROOMS and record["user_id"] == TENG]
    l3_all = [record for record in records
              if record["room"] in L3_ROOMS and record["user_id"] == ASTRA]
    l3_div = [record for record in l3_all
              if record["claimed"] == 1 and (record["margin"] or 0.0) <= 0.0]
    l3_band = [record for record in l3_all if is_band(record)]
    for label, subset in (("L1", l1), ("L2", l2), ("L2_all", l2_all), ("L3", l3_all),
                          ("L3_div", l3_div), ("L3_band", l3_band)):
        annotate_baotou_side(subset)
    print("L2 腾蛇分歧窗 %d（其全部窗 %d）；L3 Astra 窗 %d（div %d／band %d）"
          % (len(l2), len(l2_all), len(l3_all), len(l3_div), len(l3_band)))

    payload = {"audit": dict(sorted(audit.items())), "rounds": rounds_done,
               "windows": len(records), "consistency": consistency,
               "corpus": {"games": len(games), "rooms": len(
                   {game["doc"].get("room_id") or game["session"] for game in games}),
                   "snapshot_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                   "note": ("官方归档在自由赛进行期间仍在增长；本读数是本次运行的语料快照，"
                            "复跑时场数可能更多")},
               "room_versions": {room: item["tag"] for room, item in identities.items()},
               "l1": {"windows": len(l1), "frozen_keys": len(l1_keys),
                      "missing": len(l1_missing), "same_def_new_corpus": len(l1_new)},
               "l2": {"windows": len(l2), "all": len(l2_all)},
               "l3": {"windows": len(l3_all), "div": len(l3_div), "band": len(l3_band)}}

    # ---- Q1：爆头可达性对照 ----
    print()
    print("== Q1 L1 爆头可达性对照（n=%d）" % len(l1))
    pick_true = [r for r in l1 if r["pick_fu_baotou"] is True]
    any_true = [r for r in l1 if r["any_fu_baotou"]]
    now_true = [r for r in l1 if r["pass_bt"] is True]
    static_true = [r for r in l1 if r.get("bt_static") is True]
    upper_true = [r for r in l1 if r.get("struct_ub") is True]
    inherit_same = sum(1 for r in l1 if r["pass_bt"] == r["claim_bt"])
    q1 = {
        "windows": len(l1),
        "pick_fu_baotou_true": len(pick_true),
        "any_fu_baotou_true": len(any_true),
        "bt_now_true": len(now_true),
        "bt_static_true": len(static_true),
        "struct_upper_true": len(upper_true),
        "inherit_state_agree": inherit_same,
        "fu_baotou_none": sum(1 for r in l1
                              for item in r["claims"] if item.get("fu_baotou") is None),
    }
    print("  鸣+最佳跟打后进爆头（父代首选鸣牌候选）：%d/%d" % (len(pick_true), len(l1)))
    print("  鸣+最佳跟打后进爆头（任一鸣牌候选）：%d/%d" % (len(any_true), len(l1)))
    print("  不鸣侧：bt_now 继承态 %d/%d｜静态爆头条件 %d/%d｜机械上界 %d/%d"
          % (len(now_true), len(l1), len(static_true), len(l1),
             len(upper_true), len(l1)))
    print("  继承态一致性（pass_bt == claim_bt）：%d/%d" % (inherit_same, len(l1)))
    diff = cluster_bootstrap(
        l1, lambda pool: (rate(pool, lambda r: r["any_fu_baotou"])
                          - rate(pool, lambda r: r["pass_bt"] is True)))
    print("  配对差 (任一鸣后爆头 − 不鸣态) = %s，95%% 房级区间 [%s, %s]（%d 房）"
          % (fmt(diff["mean"], 4, True), fmt(diff["lo"], 4, True),
             fmt(diff["hi"], 4, True), diff["rooms"]))
    q1["paired_diff"] = diff
    payload["q1"] = q1

    # ---- Q2：margin 构成 ----
    print()
    print("== Q2 L1 margin 构成拆解（六项差 + 叠加残差）")
    keys = ("shanten", "support", "fixed", "wealth", "wealth_discard", "river", "risk",
            "style")
    term_stats = {}
    for key in keys:
        values = [(r["terms_delta"] or {}).get(key) for r in l1]
        values = [v for v in values if v is not None]
        term_stats[key] = {
            "n": len(values),
            "nonzero": sum(1 for v in values if abs(v) > 1e-9),
            "min": min(values) if values else None, "max": max(values) if values else None,
            "p25": quantile(values, 0.25), "median": quantile(values, 0.5),
            "p75": quantile(values, 0.75),
            "share_neg": (sum(1 for v in values if v < 0) / len(values)) if values else None,
        }
        print("  %-14s 非零 %3d/%d｜min %s｜p25 %s｜中位 %s｜p75 %s｜max %s"
              % (key, term_stats[key]["nonzero"], term_stats[key]["n"],
                 fmt(term_stats[key]["min"], 1, True), fmt(term_stats[key]["p25"], 1, True),
                 fmt(term_stats[key]["median"], 1, True),
                 fmt(term_stats[key]["p75"], 1, True), fmt(term_stats[key]["max"], 1, True)))
    residuals = [r["terms_residual"] for r in l1 if r["terms_residual"] is not None]
    print("  恒等式残差非零窗：%d/%d（最大绝对值 %s）"
          % (sum(1 for v in residuals if abs(v) > 1e-6), len(residuals),
             fmt(max((abs(v) for v in residuals), default=0.0), 6)))
    dsh_hist = collections.Counter(str(r["dsh"]) for r in l1)
    ratios = []
    for record in l1:
        delta = record["terms_delta"] or {}
        if delta.get("shanten") is None or not record["margin"]:
            continue
        ratios.append(abs(delta["shanten"]) / abs(record["margin"]))
    small_support = [r for r in l1
                     if (r["terms_delta"] or {}).get("support") is not None
                     and 0.0 <= r["terms_delta"]["support"] < 12.0
                     and r["claim_type"] in ("peng", "chi")]
    small_support6 = [r for r in l1
                      if (r["terms_delta"] or {}).get("support") is not None
                      and 0.0 <= r["terms_delta"]["support"] < 6.0
                      and r["claim_type"] in ("peng", "chi")]
    print("  Δshanten 分布：%s" % dict(sorted(dsh_hist.items())))
    print("  |向听项|/|margin| 中位 %s（最小 %s）"
          % (fmt(quantile(ratios, 0.5), 4), fmt(min(ratios) if ratios else None, 4)))
    print("  「支持项变化很小（[0,12)）且罚项吃满」：%d/%d = %s"
          % (len(small_support), len(l1), fmt(rate(l1, lambda r: r in small_support), 4)))
    print("  同口径收紧到 [0,6)：%d/%d" % (len(small_support6), len(l1)))
    payload["q2"] = {
        "terms": term_stats, "residual_nonzero": sum(1 for v in residuals
                                                     if abs(v) > 1e-6),
        "dsh": dict(sorted(dsh_hist.items())),
        "shanten_share_median": quantile(ratios, 0.5),
        "small_support_fixed_full": len(small_support),
        "small_support_lt6_fixed_full": len(small_support6),
        "claim_type": dict(sorted(collections.Counter(r["claim_type"] for r in l1).items())),
    }

    # ---- Q3：三层同族性 ----
    print()
    print("== Q3 三层特征分布对照")
    layers = collections.OrderedDict((
        ("L1", l1), ("L2", l2), ("L2_all", l2_all), ("L3", l3_all), ("L3_div", l3_div),
        ("L3_band", l3_band)))
    payload["q3"] = {"tables": {}, "overlap": {}}
    for label, subset in layers.items():
        table = feature_table(subset, label)
        payload["q3"]["tables"][label] = table
        if not subset:
            print("  [%s] 无窗" % label)
            continue
        print("  [%s] 窗 %d／房 %d｜向听 %s｜Δshanten %s｜白板 %s｜庄占比 %s｜副露 %s｜"
              "巡目中位 %s｜墙余中位 %s｜margin 中位 %s（min %s）｜dw 中位 %s｜"
              "实际鸣 %s｜听牌 %s｜bt_now %s｜静态爆头 %s｜鸣后爆头 %s｜band %s"
              % (label, table["windows"], table["rooms"], table["pass_shanten"],
                 table["dsh"], table["whites"], fmt(table["dealer_share"], 3),
                 table["melds"], fmt(table["turn_median"], 1), fmt(table["wall_median"], 0),
                 fmt(table["margin_median"], 1, True), fmt(table["margin_min"], 1, True),
                 fmt(table["dw_median"], 1, True), fmt(table["claimed_share"], 3),
                 fmt(table["listening_share"], 3), fmt(table["bt_now_share"], 3),
                 fmt(table["bt_static_share"], 3), fmt(table["fu_baotou_share"], 3),
                 fmt(table["band_share"], 3)))
    l2_keys = {key_of(r) for r in l2}
    payload["q3"]["overlap"]["L2_with_L1"] = len(l2_keys & {key_of(r) for r in l1})
    payload["q3"]["overlap"]["L3_div_with_L1"] = len({key_of(r) for r in l3_div}
                                                     & {key_of(r) for r in l1})
    payload["q3"]["overlap"]["L2_by_room"] = dict(sorted(collections.Counter(
        r["room"] for r in l2).items()))
    print("  重合：L2∩L1 = %d；L3_div∩L1 = %d" % (payload["q3"]["overlap"]["L2_with_L1"],
                                                  payload["q3"]["overlap"]["L3_div_with_L1"]))
    print("  L2 按房：%s" % payload["q3"]["overlap"]["L2_by_room"])

    # ---- 剂量（只来自 L1 的 margin 分布） ----
    print()
    print("== 剂量（只从 L1 的 margin 分布导出，不照抄任何单一选手的窗）")
    abs_margin = sorted(abs(r["margin"]) for r in l1)
    d_min = abs_margin[0]
    d30 = math.ceil(quantile(abs_margin, 0.30))
    d50 = math.ceil(quantile(abs_margin, 0.50))
    d70 = math.ceil(quantile(abs_margin, 0.70))
    print("  |margin|：min %s｜P30 %s｜P50 %s｜P70 %s｜max %s"
          % (fmt(d_min, 1), fmt(quantile(abs_margin, 0.30), 1),
             fmt(quantile(abs_margin, 0.50), 1), fmt(quantile(abs_margin, 0.70), 1),
             fmt(abs_margin[-1], 1)))
    print("  覆盖 >=30%% L1 所需最小剂量 d30 = +%d；d50 = +%d；d70 = +%d" % (d30, d50, d70))
    payload["dose"] = {"min": d_min, "d30": d30, "d50": d50, "d70": d70,
                       "max": abs_margin[-1],
                       "p30_raw": quantile(abs_margin, 0.30),
                       "p50_raw": quantile(abs_margin, 0.50)}

    # ---- Q4：判据的可计算性与选择性 ----
    print()
    print("== Q4 判据命中率与改选率（剂量 d = d30 = +%d）" % d30)
    q4 = {"dose": d30, "layers": {}, "predicates": {}}
    header = "  %-10s" % "判据"
    for label in layers:
        header += "%14s" % label
    print(header)
    for name, predicate in PREDICATES.items():
        row = {}
        line = "  %-10s" % name
        for label, subset in layers.items():
            hit = rate(subset, predicate)
            changed = change_rate(subset, predicate, d30)
            row[label] = {"hit": hit, "change": changed, "windows": len(subset)}
            line += "%14s" % ("%s/%s" % (fmt(hit, 3), fmt(changed, 3)))
        q4["predicates"][name] = row
        print(line)
    for label, subset in layers.items():
        q4["layers"][label] = {"windows": len(subset),
                               "rooms": len({r["room"] for r in subset})}
    sel = {}
    for name in PREDICATES:
        base = q4["predicates"][name]["L1"]["hit"]
        l3 = q4["predicates"][name]["L3"]["hit"]
        sel[name] = (None if (not base or l3 is None) else l3 / base)
    q4["selectivity_ratio_L3_over_L1"] = sel
    print("  选择性比值（L3 全体机会窗命中率 / L1 命中率）：%s"
          % {name: fmt(value, 3) for name, value in sel.items()})
    target = [r for r in l1 if r["any_fu_baotou"]]
    q4["target_subset_windows"] = len(target)
    q4["target_subset_share"] = (len(target) / len(l1)) if l1 else None
    print("  「确实该鸣」子集（鸣后进爆头）窗数 %d；替代靶子 P3:same 在 L1 命中 %s"
          % (len(target), fmt(q4["predicates"]["P3:same"]["L1"]["hit"], 3)))
    payload["q4"] = q4
    payload["predicates"] = {name: {"definition": name} for name in PREDICATES}

    # ---- Q5（主审增补）：鸣后换积分 vs 只换爆头 ----
    print()
    print("== Q5 鸣后换积分 vs 只换爆头（赛后标签只作分层，不作因果）")
    q5 = q5_block(records)
    for label, entry in q5["groups"].items():
        if not entry.get("windows"):
            print("  [%s] 无窗" % label)
            continue
        print("  [%s] 真实鸣窗 %d／房 %d｜该座当局为正 %s｜该座胡 %s｜"
              "鸣后进爆头 %d 窗（正收益 %s）｜未进爆头 %d 窗（正收益 %s）｜差 %s pp [%s, %s]"
              % (label, entry["windows"], entry["rooms"],
                 fmt(entry["positive_share"], 3), fmt(entry["won_share"], 3),
                 entry["fu_baotou_windows"], fmt(entry["fu_baotou_positive_share"], 3),
                 entry["no_fu_baotou_windows"],
                 fmt(entry["no_fu_baotou_positive_share"], 3),
                 fmt(entry.get("fu_baotou_gain_pp"), 2, True),
                 fmt((entry.get("fu_baotou_gain_ci") or {}).get("lo"), 2, True),
                 fmt((entry.get("fu_baotou_gain_ci") or {}).get("hi"), 2, True)))
    print("  -- 「换成积分」vs「只换成爆头」（仅在鸣后进爆头的窗内）")
    for label, entry in q5["split"].items():
        if not entry.get("positive_windows") and not entry.get("negative_windows"):
            continue
        print("  [%s] 正 %d 窗 / 非正 %d 窗" % (label, entry["positive_windows"],
                                              entry["negative_windows"]))
        for name, stats in entry["features"].items():
            print("     %-24s 正 %s｜非正 %s｜差 %s"
                  % (name, fmt(stats["positive_hit"], 3), fmt(stats["negative_hit"], 3),
                     fmt(stats["delta"], 3, True)))
    payload["q5"] = q5

    # 迁移检验：把「全语料」上区分度最大的行动前可算判据拿去三层复核
    transfer = []
    best_name, best_value = None, 0.0
    for name, _predicate in Q5_FEATURES.items():
        if name.startswith("[中介]"):
            continue
        stats = q5["split"]["全语料·真实鸣"]["features"].get(name) or {}
        value = abs(stats.get("delta") or 0.0)
        if value > best_value:
            best_name, best_value = name, value
    for label in ("腾蛇(L2 四房)", "Astra(L3 两房)", "我方(me)"):
        entry = q5["split"].get(label) or {}
        stats = (entry.get("features") or {}).get(best_name) or {}
        transfer.append({"group": label, "feature": best_name,
                         "delta": stats.get("delta"),
                         "positive_hit": stats.get("positive_hit"),
                         "negative_hit": stats.get("negative_hit"),
                         "positive_windows": entry.get("positive_windows"),
                         "negative_windows": entry.get("negative_windows")})
        print("  迁移检验 %-16s %s：差 %s（正 %s｜非正 %s；%s 正窗 / %s 非正窗）"
              % (label, best_name, fmt(stats.get("delta"), 3, True),
                 fmt(stats.get("positive_hit"), 3), fmt(stats.get("negative_hit"), 3),
                 entry.get("positive_windows"), entry.get("negative_windows")))
    q5["transfer_max_separator"] = {"feature": best_name, "abs_delta": best_value,
                                     "rows": transfer}
    print("  全语料上区分度最大的行动前可算判据：%s（|Δ| = %s，只作迁移检验的入口，"
          "不作候选）" % (best_name, fmt(best_value, 3)))

    # ---- 样例卡 ----
    print()
    print("== 样例卡")
    sampled = []
    picked = set()

    def take(subset, count, key=None):
        chosen = []
        ordered = sorted(subset, key=key or (lambda r: (r["room"], r["round_no"], r["seq"])))
        step = max(1, len(ordered) // max(1, count)) if ordered else 1
        for record in ordered[::step]:
            if len(chosen) >= count:
                break
            if key_of(record) in picked:
                continue
            picked.add(key_of(record))
            chosen.append(record)
        return chosen

    sampled.extend(take(l1, 6))
    l2_filled = [r for r in l2 if r["room"] == "a_53f4861835b9"]
    sampled.extend(take(l2_filled, 3))
    sampled.extend(take([r for r in l2 if r["room"] != "a_53f4861835b9"], 4))
    sampled.extend(take(l3_div, 3))
    text = cards_markdown(sampled)
    header = (chr(10).join([
        "# C36 样例卡（%d 张）" % len(sampled),
        "",
        "生成自 c36_deep_band_cards.py；字段口径见 C36-PREREG-DEEP-BAND-CARDS.md 第 2 节。",
        "赛后列（番/流局/当局得分）只作解释，不进任何判据。", ""]))
    (_project_file(_PROJECT_ROOT, OUT / "cards.md")).write_text(header + text + chr(10), encoding="utf-8")
    payload["cards"] = [{"key": list(key_of(r)), "layer_room": r["room"],
                         "claimed": r["claimed"]} for r in sampled]
    print("  样例卡 %d 张 → %s" % (len(sampled), _project_file(_PROJECT_ROOT, OUT / "cards.md")))

    payload["elapsed_sec"] = time.time() - started
    (_project_file(_PROJECT_ROOT, OUT / "summary.json")).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    with gzip.open(_project_file(_PROJECT_ROOT, OUT / "windows.jsonl.gz"), "wt", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + chr(10))
    print()
    print("结果写入 %s 与 %s" % (_project_file(_PROJECT_ROOT, OUT / "summary.json"), _project_file(_PROJECT_ROOT, OUT / "windows.jsonl.gz")))
    print("总用时 %.1f 秒" % (time.time() - started))

    bad = [path for path in READ_PATHS
           if "events.json" not in path and "manifest.json" not in path
           and "rounds.jsonl" not in path and ".jsonl.gz" not in path
           and "leaderboard-week.json" not in path]
    print("泄漏检查：读取路径 %d 条，非官方牌谱/运行清单/既有重建产物者 %d 条 -> %s"
          % (len(READ_PATHS), len(bad), "通过" if not bad else "**失败**"))
    assert not bad, bad
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
