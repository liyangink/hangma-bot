#!/usr/bin/env python3
"""C32：响应窗口卡（可审计的复打单位）+ 四类分歧计数 + 分层抽样。

口径、字段清单、四类定义、抽样配额与候选形状**冻结**在同目录
C32-PREREG-CARDS-BOUNDED-CANDIDATE.md（本脚本任何结论性运行之前落盘，落盘后不改）。

纪律：
* 窗口模型、观察重建白名单、规则接缝、margin 定义**逐字复用**
  c31_action_layer_gap.py（只读 import，不改其文件），本脚本不实现任何吃碰杠合法性、
  向听、听牌或爆头规则；爆头一律经 hangma.progression；
* 「跟打后爆头」只在**分析侧**可得（progression.baotou_after_discard）；候选源码面不可得
  （受限执行器静态拒绝 import 与白名单外属性），候选不得依赖该列；
* 信息权限：只用官方牌谱公开字段与该座自己的暗牌；他人暗牌只用于赛后核对（泄漏扰动测试）。

用法：
    UV_CACHE_DIR=/tmp/uv-cache .venv/bin/python \
        review/freematch-deep-dive-20260925/c32_cards.py
环境变量：
    C32_GAME_LIMIT=N   只跑前 N 场（冒烟，不用于结论）
    C32_SAMPLE_SEED    抽样种子（默认 20260926，与预登记一致）
    C32_NO_LEAK=1      跳过泄漏扰动测试（只用于冒烟）
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
import gzip
import json
import os
import random
import sys
import time
from pathlib import Path

ROOT = _PROJECT_ROOT
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "review" / "baotou-anatomy-20260925")))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / ".team-work" / "p6-baotou-route")))

import anatomy_lib as AL  # noqa: E402
import c31_action_layer_gap as C31  # noqa: E402
import c27_claim_cells as C27  # noqa: E402

from hangma_bot.hangma import progression  # noqa: E402

OUT = _project_file(_PROJECT_ROOT, ROOT / ".team-work" / "c32-cards")
CAND_DIR = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/candidates')
ARM_FILES = collections.OrderedDict((
    ("V1-DOSE-C6K6", "OPTY-R18-C32-DOSE-C6K6.py"),
    ("V1-DOSE-C6K3", "OPTY-R18-C32-DOSE-C6K3.py"),
    ("V1-DOSE-C6K9", "OPTY-R18-C32-DOSE-C6K9.py"),
    ("V2-RERANK-R6", "OPTY-R18-C32-RERANK-R6.py"),
    ("V3-DOSE-TENPAI", "OPTY-R18-C32-DOSE-C6-TENPAI.py"),
    ("AUDIT-TENPAI9", "OPTY-R18-C32-AUDIT-TENPAI9.py"),
))
"""AUDIT-TENPAI9 是预登记外的审计臂（只用于回答「R6 未触发的新窗」是否可达），
不参与有边界候选的判定；登记在结果文档的「偏离与补充」。"""
R6_FILE = "OPTY-R18-C27-CELL-R6.py"
"""已确认对照臂（C27/C29/C30）；只读调用其源码做同台对照。"""

XUANWU_ID = C31.XUANWU_ID
CLAIM_TYPES = C31.CLAIM_TYPES
WEALTH = C31.WEALTH
SAMPLE_SEED = int(os.environ.get("C32_SAMPLE_SEED", "20260926"))


# ---------------------------------------------------------------------------
# 候选臂装配（只读）
# ---------------------------------------------------------------------------


def load_scorer(name):
    """装配一个候选：源码必须存在且可 compile / exec；缺文件返回 (None, None)。"""

    path = _project_file(_PROJECT_ROOT, CAND_DIR / name)
    if not path.exists():
        return None, None
    # P6 是已不随仓库维护的旧战役辅助；只在实际复跑该旧候选时装入。
    try:
        import p6_lib
    except ModuleNotFoundError as exc:
        raise RuntimeError("旧 C32 候选复跑缺少本机 P6 工具；当前进化请使用共享 VIP 入口") from exc
    return p6_lib.compile_candidate(path), path.name


# ---------------------------------------------------------------------------
# 跟打（鸣牌后最佳合法弃牌）事实
# ---------------------------------------------------------------------------


def followup_detail(observation, action):
    """沿规则模块枚举鸣牌后**全部合法跟打**，取牌效最优者。

    价值式与冻结父代弃牌候选一致：base = -100 x 向听 + round(Σ 有效牌未见枚数, 1)；
    并列取 action_key 升序。返回 dict；无可用跟打返回 None。
    """

    post = C31.post_claim_observation(observation, action)
    if post is None:
        return None
    analysis = C31.RULES.analyze(post)
    best = None
    for candidate in analysis.legal_candidates:
        facts = candidate.facts
        if facts is None or not candidate.action_key.startswith("discard:"):
            continue
        shanten = facts.shanten_after
        if shanten is None or isinstance(shanten, bool):
            continue
        support = 0
        ok = True
        for tile in facts.useful_tiles:
            remaining = tile.remaining_estimate
            if remaining is None or isinstance(remaining, bool):
                ok = False
                break
            support += remaining
        if not ok:
            continue
        value = -100.0 * float(shanten) + round(float(support), 1)
        key = (-value, candidate.action_key)
        if best is None or key < best[0]:
            best = (key, value, candidate.action_key, facts.baotou_after,
                    int(shanten), float(support))
    if best is None:
        return None
    return {
        "value": best[1], "discard_key": best[2], "discard": best[2][8:],
        "facts_baotou": best[3], "shanten": best[4], "width": best[5], "post": post,
    }


def baotou_after_followup(post, discard_code):
    """**规则层**跟打后爆头：弃后暗牌 + 鸣后副露数（hangma.progression 单一口径）。

    与候选事实层的 facts.baotou_after 不同：后者在本重建里恒为 None（C31 B.4）。
    """

    hand = list(post.my_hand)
    for index, tile in enumerate(hand):
        if tile.code == discard_code:
            del hand[index]
            break
    else:
        return None
    try:
        return bool(progression.baotou_after_discard(tuple(hand), len(post.melds[post.seat])))
    except Exception:  # noqa: BLE001 —— 规则层拒绝时如实记 None，不猜
        return None


def visible_code_count(snap, code):
    """该牌码在四家公开牌河与副露中的公开张数（触发弃牌在快照里仍在牌河，需扣除）。"""

    total = 0
    for river in snap["rivers"]:
        total += river.count(code)
    for row in snap["melds"]:
        for group in row:
            total += group["tiles"].count(code)
    if snap["claim_kind"] in ("peng", "chi", "gang") and code == snap["tile"]:
        total -= 1
    return max(0, total)


# ---------------------------------------------------------------------------
# 打分面 → 计划（与 l1_reach.py 同序：分数降序、action_key 升序兜底）
# ---------------------------------------------------------------------------


def action_entry(view, key):
    for item in view["actions"]:
        if item["action_key"] == key:
            return item
    return None


def scored_plan(view, scores):
    actions = [item for item in view["actions"] if item["action_key"] in scores]
    if not actions:
        return None, None
    best = min(actions, key=lambda item: (-float(scores[item["action_key"]]),
                                          item["action_key"]))
    return best["action_key"], float(scores[best["action_key"]])


def phase_margin(view, scores):
    """该 phase 的 margin = max(鸣牌候选分) - pass 分（C31 第 5 节冻结定义）。"""

    claims = [item for item in view["actions"]
              if item["action_type"] in CLAIM_TYPES and item["action_key"] in scores]
    passes = [item for item in view["actions"]
              if item["action_type"] == "pass" and item["action_key"] in scores]
    if not claims or not passes:
        return None
    claim = min(claims, key=lambda item: (-float(scores[item["action_key"]]),
                                          item["action_key"]))
    pas = passes[0]
    return {
        "margin": float(scores[claim["action_key"]]) - float(scores[pas["action_key"]]),
        "claim_key": claim["action_key"],
        "claim_score": float(scores[claim["action_key"]]),
        "pass_key": pas["action_key"],
        "pass_score": float(scores[pas["action_key"]]),
    }


def arm_plan(scorer):
    """把一个打分器包成 per_phase -> 该窗最优 phase 的计划（margin 取两 phase 最大）。"""

    def plan(per_phase):
        best = None
        for entry in per_phase:
            if scorer is None:
                return None
            result = scorer(entry["view"])
            if result.get("status") != "SCORED":
                continue
            scores = {item["action_key"]: float(item["score"])
                      for item in result.get("entries") or []}
            info = phase_margin(entry["view"], scores)
            if info is None:
                continue
            info["phase"] = entry["phase"]
            info["plan_first"] = scored_plan(entry["view"], scores)[0]
            if best is None or (info["margin"], entry["phase"]) > (best["margin"],
                                                                   best["phase"]):
                best = info
        return best

    return plan


# ---------------------------------------------------------------------------
# 结果注记（赛后事实，不作特征）
# ---------------------------------------------------------------------------


def round_outcome(events):
    for event in events:
        if event.get("type") != "round_ended":
            continue
        data = event.get("data") or {}
        return {
            "fan": data.get("fan"), "detail": list(data.get("detail") or ()),
            "draw": data.get("draw"), "scores": list(data.get("scores") or ()),
            "dealer": data.get("dealer"),
        }
    return {}


def phases_for(snap, seat):
    phases = []
    peng = C31._peng_members(snap["discarder"], snap["tile"], snap["owner"])
    chi = C31._chi_members(snap["discarder"], snap["tile"], snap["owner"])
    if seat in peng:
        phases.append("response_peng")
    if seat in chi:
        phases.append("response_chi")
    return phases


# ---------------------------------------------------------------------------
# 主构建：逐窗出卡
# ---------------------------------------------------------------------------


def build_one_card(snap, seat, phases, per_phase, window, game_id, round_no, room, group,
                   user_id, primary, outcome, r6_plan, arms_plans):
    """把一个响应窗口落成一张固定字段的卡（字段清单见预登记第 3 节）。"""

    observation = window["observation"]
    visible = window["visible"]
    view = window["view"]
    scores = {key: float(value) for key, value in (window["scores"] or {}).items()}
    feature = C31.parent_space_feature(window)
    labels = C27.cells(feature)
    claim_key = window["claim"]["action_key"]
    pass_action = window["pass"]
    pass_W = C31.width_of(pass_action)
    claim_W = C31.width_of(window["claim"])
    types = {item["action_key"]: item["action_type"] for item in view["actions"]}
    claims = []
    for candidate in window["analysis"].legal_candidates:
        key = candidate.action_key
        if types.get(key) not in CLAIM_TYPES or key not in scores:
            continue
        item = action_entry(view, key)
        entry = {
            "action_key": key, "action_type": types[key],
            "shanten_after": (item.get("shanten_after") if item else None),
            "W_after": (C31.width_of(item) if item else None),
            "baotou_after": (item.get("baotou_after") if item else None),
            "best_followup_discard": (item.get("best_followup_discard") if item else None),
            "parent_score": scores.get(key),
            "is_parent_pick": key == claim_key,
        }
        entry["dw_vs_pass"] = (None if (entry["W_after"] is None or pass_W is None)
                               else entry["W_after"] - pass_W)
        detail = followup_detail(observation, candidate.action)
        if detail is not None:
            post = detail["post"]
            exposed = visible_code_count(snap, detail["discard"])
            entry.update({
                "fu_discard": detail["discard"], "fu_shanten": detail["shanten"],
                "fu_W": detail["width"], "fu_value": detail["value"],
                "fu_facts_baotou": detail["facts_baotou"],
                "fu_baotou": baotou_after_followup(post, detail["discard"]),
                "fu_exposed": exposed, "fu_exposed_new": exposed == 0,
            })
            if entry["is_parent_pick"] and item is not None:
                base = (window["bases"] or {}).get(key)
                entry["margin_followup"] = (
                    None if base is None else window["margin"] + (detail["value"] - float(base)))
        claims.append(entry)
    r6 = r6_plan(per_phase)
    arms = {}
    for name, planner in arms_plans.items():
        info = planner(per_phase)
        if info is None:
            continue
        arms[name] = {"margin": info["margin"], "plan_first": info["plan_first"],
                      "claim_key": info["claim_key"], "phase": info["phase"]}
    actual = snap["claim_kind"] if snap["claim_seat"] == seat else None
    claimed = 1 if actual in ("peng", "chi", "gang") else 0
    scores_arr = list(outcome.get("scores") or ())
    seat_delta = scores_arr[seat] if seat < len(scores_arr) else None
    others = [index for index in range(4) if index != seat]
    card = {
        "game_id": game_id, "round_no": round_no, "seq": snap["seq"], "seat": seat,
        "room": room, "primary": primary, "group": group, "user_id": user_id,
        "is_xuanwu": user_id == XUANWU_ID,
        "phase": window["phase"], "phases": phases,
        "dealer_seat": visible["dealer_seat"], "is_dealer": visible["dealer_seat"] == seat,
        "wall": visible.get("remaining_tile_count"),
        "turn": len(visible["discards"][seat]),
        "melds": len(visible["melds"][seat]), "whites": visible["my_hand"].count(WEALTH),
        "opp_melds": sum(len(visible["melds"][index]) for index in others),
        "opp_meld_seats": sum(1 for index in others if len(visible["melds"][index]) > 0),
        "discarder": snap["discarder"], "tile": snap["tile"],
        "tile_class": ("number" if (snap["tile"] and snap["tile"][0] in "123456789")
                       else "honor"),
        "other_claimed": bool(snap["claim_seat"] is not None and snap["claim_seat"] != seat),
        "my_hand_codes": [tile.code for tile in observation.my_hand],
        "my_river": list(snap["rivers"][seat]),
        "my_meld_groups": [group_item["kind"] + ":" + ",".join(group_item["tiles"])
                           for group_item in snap["melds"][seat]],
        "labels": labels, "feature": feature,
        "pass_shanten": window["pass"].get("shanten_after"),
        "pass_W": pass_W, "claim_W": claim_W,
        "pass_score": window["pass_score"], "claim_score": window["claim_score"],
        "margin": window["margin"], "claim_key": claim_key,
        "claim_type": window["claim"]["action_type"],
        "parent_plan_first": scored_plan(view, scores)[0],
        "claims": claims,
        "margin_r6": (None if r6 is None else r6["margin"]),
        "r6_plan_first": (None if r6 is None else r6["plan_first"]),
        "r6_claim_key": (None if r6 is None else r6["claim_key"]),
        "r6_phase": (None if r6 is None else r6["phase"]),
        "arms": arms,
        "actual": actual, "claimed": claimed,
        "hu_keys": [item["action_key"] for item in view["actions"]
                    if item["action_type"] == "hu"],
        "gang_beats_claim": None,
        "outcome": {"fan": outcome.get("fan"), "detail": outcome.get("detail"),
                    "draw": outcome.get("draw"), "scores": scores_arr,
                    "seat_delta": seat_delta},
    }
    card["parent_claims"] = 1 if window["margin"] > 0 else 0
    card["r6_claims"] = (None if r6 is None else (1 if r6["margin"] > 0 else 0))
    card["r6_changed"] = (None if r6 is None else int(
        card["r6_claims"] != card["parent_claims"]
        or card["r6_plan_first"] != card["parent_plan_first"]))
    for name, info in arms.items():
        info["claims"] = 1 if info["margin"] > 0 else 0
        info["changed_vs_r6"] = (None if r6 is None else int(
            info["claims"] != card["r6_claims"]
            or info["plan_first"] != card["r6_plan_first"]))
        info["changed_vs_parent"] = int(info["claims"] != card["parent_claims"]
                                        or info["plan_first"] != card["parent_plan_first"])
    return card


def compact_row(card):
    """内存里的紧凑行：四类计数、分层抽样、判据聚合都用它。"""

    pick = next((item for item in card["claims"] if item["is_parent_pick"]), None)
    dw = None if pick is None else pick["dw_vs_pass"]
    W = None if pick is None else pick["W_after"]
    pred = {
        "dw_ge_1": (dw is not None and dw >= 1.0),
        "dw_ge_3": (dw is not None and dw >= 3.0),
        "dw_ge_6": (dw is not None and dw >= 6.0),
        "dw_ge_9": (dw is not None and dw >= 9.0),
        "W_after_ge_8": (W is not None and W >= 8.0),
        "W_after_ge_12": (W is not None and W >= 12.0),
        "W_after_ge_16": (W is not None and W >= 16.0),
        "listening": card["pass_shanten"] == 0,
        "melds_le_1": card["melds"] <= 1,
        "wall_ge_40": (card["wall"] or 0) >= 40,
        "is_dealer": bool(card["is_dealer"]),
        "turn_le_6": card["turn"] <= 6,
        "opp_attack": card["opp_meld_seats"] >= 1,
        "fu_new_tile": (pick is not None and pick.get("fu_exposed_new") is True),
        "fu_baotou": (pick is not None and pick.get("fu_baotou") is True),
        "bt_action": (pick is not None and pick.get("baotou_after") is True),
        "fu_W_ge_8": (pick is not None and pick.get("fu_W") is not None
                      and pick["fu_W"] >= 8.0),
    }
    return {
        "key": [card["game_id"], card["round_no"], card["seq"], card["seat"]],
        "room": card["room"], "primary": card["primary"], "group": card["group"],
        "user_id": card["user_id"], "is_xuanwu": card["is_xuanwu"],
        "labels": card["labels"], "feature": card["feature"],
        "margin": card["margin"], "margin_r6": card["margin_r6"],
        "claimed": card["claimed"], "parent_claims": card["parent_claims"],
        "r6_claims": card["r6_claims"], "r6_changed": card["r6_changed"],
        "actual": card["actual"], "dw": dw, "W_after": W,
        "pass_shanten": card["pass_shanten"],
        "melds": card["melds"], "wall": card["wall"], "whites": card["whites"],
        "is_dealer": card["is_dealer"], "turn": card["turn"],
        "opp_meld_seats": card["opp_meld_seats"],
        "seat_delta": card["outcome"]["seat_delta"],
        "fan": card["outcome"]["fan"], "draw": card["outcome"]["draw"],
        "r6_plan_first": card["r6_plan_first"],
        "parent_plan_first": card["parent_plan_first"],
        "arms": {name: {"margin": info["margin"], "plan_first": info["plan_first"],
                        "claims": info["claims"], "changed_vs_r6": info["changed_vs_r6"],
                        "changed_vs_parent": info["changed_vs_parent"]}
                 for name, info in card["arms"].items()},
        "pred": pred,
        "followup_ok": any("fu_value" in item for item in card["claims"]),
        "fu_facts_baotou_none": all(item.get("fu_facts_baotou") is None
                                    for item in card["claims"] if "fu_value" in item),
        "stratum": [card["room"], "dealer" if card["is_dealer"] else "nondealer",
                    "w%d" % min(2, card["whites"]),
                    card["labels"].get("F1", "?"), card["labels"].get("F6", "?")],
    }


def build_cards(games, board, primary_index, parent, r6, arms, audit, card_sink):
    rows = []
    r6_plan = arm_plan(r6)
    arms_plans = collections.OrderedDict((name, arm_plan(scorer))
                                         for name, scorer in arms.items())
    rounds_done = 0
    for game in games:
        document = game["doc"]
        seats_meta = document.get("seats") or []
        room = document.get("room_id") or game["session"]
        users = [item.get("user_id") for item in seats_meta]
        groups = []
        for index in range(4):
            user = users[index] if index < len(users) else None
            groups.append("me" if user == AL.ME else ("elite" if user in board else "other"))
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
            outcome = round_outcome(events)
            snaps = C31.reconstruct(events, start_hands, table, dealer)
            rounds_done += 1
            primary = (game_id, round_no) in primary_index and "elite" in groups
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
                    window, per_phase, window_audit = C31.evaluate_window(
                        snap, seat, phases, game_id, round_no, parent)
                    audit.update(window_audit)
                    if window is None:
                        audit["not_opportunity"] += 1
                        continue
                    card = build_one_card(
                        snap, seat, phases, per_phase, window, game_id, round_no, room,
                        groups[seat], (users[seat] if seat < len(users) else None),
                        primary, outcome, r6_plan, arms_plans)
                    card_sink(card)
                    rows.append(compact_row(card))
            if ended_scores is not None:
                table = [a + b for a, b in zip(table, ended_scores)]
    return rows, rounds_done


# ---------------------------------------------------------------------------
# 四类分歧、判据表、分层抽样
# ---------------------------------------------------------------------------


def four_classes(rows, group=None, only_xuanwu=False):
    picked = [row for row in rows
              if (group is None or row["group"] == group)
              and (not only_xuanwu or row["is_xuanwu"])]
    box = collections.Counter()
    for row in picked:
        actual = 1 if row["claimed"] else 0
        plan = row["parent_claims"]
        if actual and plan:
            box["agree_claim"] += 1
        elif actual and not plan:
            box["x_claim_parent_pass"] += 1
        elif plan and not actual:
            box["x_pass_parent_claim"] += 1
        else:
            box["agree_pass"] += 1
    return {"windows": len(picked), "classes": dict(box)}


def bucket_ids(rows):
    boxes = collections.defaultdict(list)
    for index, row in enumerate(rows):
        labels = row["labels"]
        same = labels.get("F3") == "F3:same"
        wider = labels.get("F4") == "F4:wider"
        margin = row["margin"] or 0.0
        if row["is_xuanwu"] and row["claimed"] and margin <= 0 and same and wider:
            boxes["A_focus"].append(index)
        if (row["group"] == "me" and same and wider and row["claimed"]
                and row["seat_delta"] is not None and row["seat_delta"] <= 0):
            boxes["B_me_fail"].append(index)
        if (row["group"] == "me" and same and wider and row["claimed"]
                and row["seat_delta"] is not None and row["seat_delta"] > 0):
            boxes["C_me_ok"].append(index)
        if (row["group"] == "me" and same and not row["claimed"]
                and row["r6_claims"] and margin <= 0):
            boxes["D_r6_would"].append(index)
        dw = row["dw"]
        if (row["pass_shanten"] == 0 and dw is not None and dw >= 6.0 and margin <= -6.0):
            boxes["E_new_window"].append(index)
    return boxes


QUOTA = (("A_focus", 12), ("B_me_fail", 10), ("C_me_ok", 6),
         ("D_r6_would", 6), ("E_new_window", 6))


def sample_cards(rows, total=44):
    """按预登记配额抽卡；桶内固定种子抽样，剩余按层补齐（≥40 张）。"""

    boxes = bucket_ids(rows)
    rng = random.Random(SAMPLE_SEED)
    chosen = []
    seen = set()

    def take(indices, quota):
        pool = sorted({index for index in indices if index not in seen},
                      key=lambda index: tuple(rows[index]["key"]))
        if not pool:
            return 0
        picked = rng.sample(pool, min(quota, len(pool)))
        for index in picked:
            seen.add(index)
            chosen.append(index)
        return len(picked)

    report = {}
    for name, quota in QUOTA:
        report[name] = {"available": len(boxes.get(name, ())),
                        "taken": take(boxes.get(name, ()), quota)}
    if len(chosen) < total:
        strata = collections.defaultdict(list)
        for index, row in enumerate(rows):
            if index not in seen:
                strata[tuple(row["stratum"])].append(index)
        keys = sorted(strata)
        cursor = 0
        while len(chosen) < total and keys and cursor <= 40 * len(keys):
            key = keys[cursor % len(keys)]
            pool = sorted([index for index in strata[key] if index not in seen],
                          key=lambda index: tuple(rows[index]["key"]))
            if pool:
                index = rng.choice(pool)
                seen.add(index)
                chosen.append(index)
            cursor += 1
    chosen.sort(key=lambda index: tuple(rows[index]["key"]))
    report["total"] = len(chosen)
    report["strata_covered"] = len({tuple(rows[index]["stratum"]) for index in chosen})
    report["quota_n"] = {name: quota for name, quota in QUOTA}
    return chosen, report


# ---------------------------------------------------------------------------
# 人可读渲染
# ---------------------------------------------------------------------------

BT = chr(96)


def code(text):
    return BT + str(text) + BT


def render_card(card, tags):
    lines = []
    lines.append("### %s r%s seq%s 座%s（%s%s）" % (
        card["game_id"], card["round_no"], card["seq"], card["seat"],
        card["group"], "·玄武" if card["is_xuanwu"] else ""))
    lines.append("")
    lines.append("* 桶：%s；层：房 %s / %s / 白%s / %s / %s"
                 % (", ".join(tags) or "-", card["room"],
                    "庄" if card["is_dealer"] else "闲", min(2, card["whites"]),
                    card["labels"].get("F1"), card["labels"].get("F6")))
    lines.append("* 触发：座 %s 打出 %s（%s）；phase %s；墙余 %s；巡目 %s；自有副露 %s；"
                 "他家副露 %s 家；持白 %s"
                 % (card["discarder"], code(card["tile"]), card["tile_class"],
                    card["phase"], card["wall"], card["turn"], card["melds"],
                    card["opp_meld_seats"], card["whites"]))
    lines.append("* 本座暗牌：%s；过牌向听 %s；本座牌河 %s；本座副露 %s"
                 % (code("".join(card["my_hand_codes"])), card["pass_shanten"],
                    code("".join(card["my_river"]) or "空"),
                    "、".join(card["my_meld_groups"]) or "无"))
    lines.append("* 格标签：%s" % " ".join("%s=%s" % (key, value)
                                          for key, value in sorted(card["labels"].items())))
    lines.append("* 过牌分 %s；父代首选 %s；margin = %s；CELL-R6 首选 %s，margin_r6 = %s（%s）"
                 % (card["pass_score"], code(card["parent_plan_first"]), card["margin"],
                    code(card["r6_plan_first"]), card["margin_r6"],
                    "改选" if card["r6_changed"] else "不变"))
    lines.append("* 真实动作：%s；另有他家先鸣走：%s"
                 % (card["actual"] or "过", card["other_claimed"]))
    lines.append("")
    lines.append("| 鸣牌候选 | 类型 | 鸣后向听 | 鸣后真实张数 | Δ张数 | 动作层爆头 | 最佳跟打 | 跟打后向听 | 跟打后张数 | 跟打后爆头 | 跟打公开张数 | 父代分 |")
    lines.append("| --- | --- | ---: | ---: | ---: | --- | --- | ---: | ---: | --- | ---: | ---: |")
    for item in card["claims"]:
        lines.append("| %s%s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |"
                     % (code(item["action_key"]),
                        " ★" if item["is_parent_pick"] else "",
                        item["action_type"], item["shanten_after"], item["W_after"],
                        item["dw_vs_pass"], item["baotou_after"],
                        code(item.get("fu_discard", "-")) if item.get("fu_discard") else "-",
                        item.get("fu_shanten", "-"), item.get("fu_W", "-"),
                        item.get("fu_baotou", "-"), item.get("fu_exposed", "-"),
                        item["parent_score"]))
    lines.append("")
    if card["arms"]:
        lines.append("* C32 臂：%s" % "；".join(
            "%s margin %s%s" % (name, info["margin"],
                                "（改选）" if info["changed_vs_r6"] else "")
            for name, info in sorted(card["arms"].items())))
    lines.append("* 赛后注记（不作特征）：番数 %s；番型 %s；流局 %s；本座当局得分 %s"
                 % (card["outcome"]["fan"],
                    "、".join(card["outcome"]["detail"] or []) or "-",
                    card["outcome"]["draw"], card["outcome"]["seat_delta"]))
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def parent_scores(observation, parent):
    """冻结父代在该观察上的 (scores, status)；ABSTAIN 路径返回 (None, status)。

    C31.score_window 在非 SCORED 路径少返回一项，这里统一成二元组。
    """

    out = C31.score_window(observation, parent)
    return out[1], out[2]


def mutate_snap(snap, swaps):
    """按 (座位, 去掉一张, 加一张) 清单复制一份快照（暗牌用 Counter，保持总数守恒）。"""

    hands = [collections.Counter(snap["hands"][index]) for index in range(4)]
    for seat, remove_code, add_code in swaps:
        hands[seat][remove_code] -= 1
        hands[seat][add_code] += 1
    clone = dict(snap)
    clone["hands"] = hands
    return clone


def leak_probe(games_by_id, sample_keys, parent, audit):
    """互换**非主体**座位的两张暗牌 ⇒ 该座观察与父代分数必须逐字节不变；
    改主体自己的暗牌 ⇒ 必须改变（C31 同款不变量）。"""

    for key in sample_keys:
        game = games_by_id.get(key[0])
        if game is None:
            continue
        document = game["doc"]
        block_meta = C31.round_metadata(document)
        for round_no, events, start_hands in AL.round_blocks(document):
            if round_no != key[1] or not start_hands:
                continue
            dealer = (block_meta.get(round_no) or {}).get("dealer")
            if dealer is None:
                dealer = next((index for index, hand in enumerate(start_hands)
                               if len(hand) == 14), None)
            if dealer is None:
                continue
            snaps = C31.reconstruct(events, start_hands, [0, 0, 0, 0], dealer)
            snap = snaps.get(key[2])
            if snap is None:
                continue
            seat = key[3]
            phases = phases_for(snap, seat)
            if not phases:
                continue
            phase = phases[0]
            others = [index for index in range(4) if index != seat]
            first, second = others[0], others[1]
            codes_a = sorted(snap["hands"][first])
            codes_b = sorted(snap["hands"][second])
            if not codes_a or not codes_b or codes_a[0] == codes_b[0]:
                continue
            mutated = mutate_snap(snap, [(first, codes_a[0], codes_b[0]),
                                         (second, codes_b[0], codes_a[0])])
            base_obs = C31.build_observation(snap, seat, phase, key[0], key[1])
            mut_obs = C31.build_observation(mutated, seat, phase, key[0], key[1])
            score_a, status_a = parent_scores(base_obs, parent)
            score_b, status_b = parent_scores(mut_obs, parent)
            if status_a != "SCORED":
                audit["leak_skipped_abstain"] += 1
                break
            audit["leak_other_seats_checked"] += 1
            if status_a == status_b and score_a == score_b:
                audit["leak_other_seats_unchanged"] += 1
            else:
                audit["leak_other_seats_CHANGED"] += 1
            own_codes = sorted(snap["hands"][seat])
            swap_in = next((code for code in codes_a if code != own_codes[0]), None) \
                if own_codes else None
            if own_codes and swap_in is not None:
                own = mutate_snap(snap, [(seat, own_codes[0], swap_in)])
                own_obs = C31.build_observation(own, seat, phase, key[0], key[1])
                score_c, status_c = parent_scores(own_obs, parent)
                audit["leak_own_hand_checked"] += 1
                if status_a != status_c or score_a != score_c:
                    audit["leak_own_hand_CHANGED"] += 1
            break


def arm_delta_table(rows):
    """各臂相对冻结父代与 CELL-R6 的改选集合对比（重建语料，逐窗可比）。"""

    def is_claim(key):
        return bool(key) and key.split(":")[0] in CLAIM_TYPES

    table = {}
    base = {index for index, row in enumerate(rows) if row["r6_changed"]}
    for name in sorted({name for row in rows for name in row["arms"]}):
        changed = set()
        flips = set()
        swaps = set()
        for index, row in enumerate(rows):
            info = row["arms"].get(name)
            if info is None:
                continue
            differs = (info["claims"] != row["parent_claims"]
                       or info["plan_first"] != row["parent_plan_first"])
            if not differs:
                continue
            changed.add(index)
            if is_claim(info["plan_first"]) != is_claim(row["parent_plan_first"]):
                flips.add(index)
            else:
                swaps.add(index)
        extra = changed - base
        removed = base - changed
        table[name] = {"changed_vs_parent": len(changed), "claim_flip": len(flips),
                       "pick_swap": len(swaps), "r6_changed": len(base),
                       "extra_vs_r6": len(extra), "removed_vs_r6": len(removed),
                       "extra_flip": len([i for i in extra if i in flips]),
                       "extra_swap": len([i for i in extra if i in swaps]),
                       "extra_keys": [rows[index]["key"] for index in sorted(extra)[:12]]}
    return table


def main():
    started = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    parent = C31.load_parent()
    parent_sha = C31.R18_INTEGRATED_POSITIVE_V2_SHA256
    print("冻结父代装配完成：%s" % parent_sha[:16])
    r6, _ = load_scorer(R6_FILE)
    print("对照臂 %s：%s" % (R6_FILE, "已装配" if r6 else "**缺失**"))
    arms = collections.OrderedDict()
    for name, file_name in ARM_FILES.items():
        scorer, _used = load_scorer(file_name)
        if scorer is not None:
            arms[name] = scorer
    print("C32 臂：%s" % (", ".join(arms) or "（尚未生成，先出卡再补）"))

    board, _board_path = C31.C23.load_board()
    primary_rows = [json.loads(line) for line in C31.ROUNDS_JSONL.open(encoding="utf-8")
                    if line.strip()]
    primary_index = {(row["game_id"], row["round_no"]) for row in primary_rows}
    games = AL.load_games()
    limit = int(os.environ.get("C32_GAME_LIMIT", "0") or 0)
    if limit:
        games = games[:limit]
        print("C32_GAME_LIMIT=%d：只跑前 %d 场（冒烟用，不用于结论）" % (limit, limit))
    print("官方牌谱 %d 场；主语料 %d 局" % (len(games), len(primary_rows)))

    audit = collections.Counter()
    cards_path = _project_file(_PROJECT_ROOT, OUT / "cards.jsonl.gz")
    rows = []
    handle = gzip.open(cards_path, "wt", encoding="utf-8")
    try:
        rows, rounds_done = build_cards(games, board, primary_index, parent, r6, arms,
                                        audit, lambda card: handle.write(
                                            json.dumps(card, ensure_ascii=False,
                                                       default=str) + "\n"))
    finally:
        handle.close()
    print("重建 %d 局，机会窗 %d 个，用时 %.1f 秒"
          % (rounds_done, len(rows), time.time() - started))
    print("审计：%s" % json.dumps(dict(sorted(audit.items())), ensure_ascii=False))

    primary = [row for row in rows if row["primary"]]
    payload = {"audit": dict(sorted(audit.items())), "rounds": rounds_done,
               "windows_all": len(rows), "windows_primary": len(primary),
               "parent_sha256": parent_sha}

    def usage(subset, group):
        picked = [row for row in subset if row["group"] == group]
        taken = sum(row["claimed"] for row in picked)
        return len(picked), taken, (taken / len(picked) if picked else None)

    checks = []
    me_chances, _me_taken, me_usage = usage(primary, "me")
    el_chances, _el_taken, el_usage = usage(primary, "elite")
    checks.append(("主语料机会数 me=5965", me_chances, 5965))
    checks.append(("主语料机会数 elite=10394", el_chances, 10394))
    checks.append(("主语料使用率 me=0.4801", me_usage, 0.4801))
    checks.append(("主语料使用率 elite=0.5790", el_usage, 0.5790))
    got = tuple(sum(1 for row in primary if row["group"] == group
                    and row["labels"].get("F1") == "F1:sh0") for group in C31.GROUPS)
    checks.append(("F1:sh0 机会数 me/elite=(1607,2906)", got, (1607, 2906)))
    pool = [row for row in primary if row["group"] in C31.GROUPS]
    share = {}
    for cell, family in (("F3:same", "F3"), ("F1:sh0", "F1")):
        share[cell] = (sum(1 for row in pool if row["labels"].get(family) == cell)
                       / len(pool)) if pool else 0.0
    checks.append(("F3:same 机会占比 0.528", share["F3:same"], 0.528))
    checks.append(("F1:sh0 机会占比 0.276", share["F1:sh0"], 0.276))
    print()
    print("== 自检（与 C23/C27/C31 已发布读数对拍）")
    ok = True
    for label, got_value, want in checks:
        if isinstance(want, tuple):
            passed = all(abs(a - b) <= max(20, 0.005 * b) for a, b in zip(got_value, want))
        elif want > 10:
            passed = abs(got_value - want) <= max(20, 0.005 * want)
        else:
            passed = abs(got_value - want) <= 0.005
        ok = ok and passed
        print("  %s %s：得到 %s，期望 %s"
              % ("通过" if passed else "**不符**", label, got_value, want))
    payload["selfcheck"] = {"ok": ok,
                            "rows": [{"label": label, "got": got_value, "want": want}
                                     for label, got_value, want in checks]}
    print("自检总体：%s" % ("通过" if ok else "**失败**"))

    print()
    print("== 四类分歧（同一张观察：实际动作 vs 冻结父代计划；margin > 0 = 计划鸣）")
    payload["four_classes"] = {}
    for tag, subset, kwargs in (("玄武座窗", rows, {"only_xuanwu": True}),
                                ("我方座窗", rows, {"group": "me"}),
                                ("全部 elite 座窗", rows, {"group": "elite"}),
                                ("主语料全部座窗", primary, {})):
        entry = four_classes(subset, **kwargs)
        payload["four_classes"][tag] = entry
        classes = entry["classes"]
        print("  %s：窗 %d｜同意鸣 %d｜同意过 %d｜实际鸣而父代过 %d｜实际过而父代鸣 %d"
              % (tag, entry["windows"], classes.get("agree_claim", 0),
                 classes.get("agree_pass", 0), classes.get("x_claim_parent_pass", 0),
                 classes.get("x_pass_parent_claim", 0)))

    print()
    print("== CELL-R6 把哪一类搬到哪一类（同窗对照）")
    moved = collections.Counter()
    for row in rows:
        if row["r6_claims"] is None:
            continue
        moved[(row["parent_claims"], row["r6_claims"], row["claimed"])] += 1
    payload["r6_transitions"] = {"%d|%d|%d" % key: value for key, value in moved.items()}
    for key, value in sorted(moved.items()):
        print("  父代计划 %d → R6 计划 %d，实际鸣 %d：%d" % (key[0], key[1], key[2], value))

    print()
    print("== 跟打口径与爆头列")
    follow = {"available": 0, "fu_facts_baotou_none": 0, "fu_baotou_true": 0,
              "fu_baotou_none": 0, "bt_action_true": 0, "fu_true_without_action": 0,
              "diverged_from_action_margin": 0}
    for row in rows:
        if not row["followup_ok"]:
            continue
        follow["available"] += 1
        if row["fu_facts_baotou_none"]:
            follow["fu_facts_baotou_none"] += 1
        if row["pred"]["fu_baotou"]:
            follow["fu_baotou_true"] += 1
            if not row["pred"]["bt_action"]:
                follow["fu_true_without_action"] += 1
        if row["pred"]["bt_action"]:
            follow["bt_action_true"] += 1
        arm0 = row["arms"].get("V1-DOSE-C6K6")
        if arm0 is not None and row["r6_claims"] is not None:
            pass
    payload["followup"] = follow
    print("  可用窗 %d / %d；跟打观察上候选事实层爆头恒 None：%d"
          % (follow["available"], len(rows), follow["fu_facts_baotou_none"]))
    print("  规则层跟打后爆头 = True：%d（其中动作层非 True：%d）；动作层爆头 True：%d"
          % (follow["fu_baotou_true"], follow["fu_true_without_action"],
             follow["bt_action_true"]))

    print()
    print("== 判据清单（行动前可计算）")
    focus = [row for row in rows if row["is_xuanwu"] and row["claimed"]
             and (row["margin"] or 0) <= 0
             and row["labels"].get("F3") == "F3:same"
             and row["labels"].get("F4") == "F4:wider"]
    me_same = [row for row in rows if row["group"] == "me"
               and row["labels"].get("F3") == "F3:same"]
    me_cell = [row for row in rows if row["group"] == "me"
               and row["labels"].get("F3") == "F3:same"
               and row["labels"].get("F4") == "F4:wider"]
    table = {}
    for name in sorted(rows[0]["pred"]):
        table[name] = {
            "all_hits": sum(1 for row in rows if row["pred"][name]),
            "all_n": len(rows),
            "focus_A_hits": sum(1 for row in focus if row["pred"][name]),
            "focus_A_n": len(focus),
            "me_F3same_hits": sum(1 for row in me_same if row["pred"][name]),
            "me_F3same_n": len(me_same),
            "me_cell_hits": sum(1 for row in me_cell if row["pred"][name]),
            "me_cell_n": len(me_cell),
        }
        print("  %-14s 全语料 %6d/%6d｜玄武重点格 %3d/%3d｜我方 F3:same %5d/%5d"
              % (name, table[name]["all_hits"], table[name]["all_n"],
                 table[name]["focus_A_hits"], table[name]["focus_A_n"],
                 table[name]["me_F3same_hits"], table[name]["me_F3same_n"]))
    payload["predicates"] = table

    print()
    print("== 各臂改选集合（重建语料；相对 CELL-R6）")
    delta = arm_delta_table(rows)
    payload["arm_delta"] = delta
    for name, entry in delta.items():
        print("  %-16s 改选(vs 父代) %5d（鸣/过翻转 %4d＋首选换位 %4d）｜R6 改选 %5d｜"
              "额外 %4d（翻转 %d＋换位 %d）｜移除 %4d"
              % (name, entry["changed_vs_parent"], entry["claim_flip"], entry["pick_swap"],
                 entry["r6_changed"], entry["extra_vs_r6"], entry["extra_flip"],
                 entry["extra_swap"], entry["removed_vs_r6"]))

    print()
    print("== 分层抽样")
    boxes = bucket_ids(rows)
    payload["buckets"] = {name: len(value) for name, value in boxes.items()}
    for name, value in sorted(boxes.items()):
        print("  桶 %-14s 可用 %d" % (name, len(value)))
    chosen, quota_report = sample_cards(rows)
    payload["sample"] = quota_report
    print("  抽中 %d 张；覆盖层 %d；配额执行 %s"
          % (quota_report["total"], quota_report["strata_covered"],
             json.dumps({name: quota_report[name] for name, _ in QUOTA},
                        ensure_ascii=False)))

    wanted = {tuple(rows[index]["key"]) for index in chosen}
    tag_by_key = collections.defaultdict(list)
    for name, indices in boxes.items():
        for index in indices:
            tag_by_key[tuple(rows[index]["key"])].append(name)
    cards_md = ["# C32 响应窗口卡（分层抽样 %d 张）" % len(chosen), "",
                "生成脚本：c32_cards.py；口径冻结在 C32-PREREG-CARDS-BOUNDED-CANDIDATE.md。",
                "★ = 冻结父代在本窗的首选鸣牌候选；「跟打后爆头」由 "
                "hangma.progression.baotou_after_discard 在**分析侧**判定，"
                "候选源码面不可得（见结果文档负控）。", ""]
    rendered = 0
    with gzip.open(cards_path, "rt", encoding="utf-8") as handle:
        for line in handle:
            card = json.loads(line)
            key = (card["game_id"], card["round_no"], card["seq"], card["seat"])
            if key not in wanted:
                continue
            cards_md.append(render_card(card, tag_by_key.get(key, [])))
            rendered += 1
    (_project_file(_PROJECT_ROOT, OUT / "cards.md")).write_text("\n".join(cards_md), encoding="utf-8")
    print("  渲染人可读卡 %d 张 → %s" % (rendered, _project_file(_PROJECT_ROOT, OUT / "cards.md")))
    payload["sample"]["rendered"] = rendered

    audit2 = collections.Counter()
    if os.environ.get("C32_NO_LEAK") != "1":
        print()
        print("== 泄漏扰动测试（暗牌不变量）")
        games_by_id = {}
        for game in games:
            document = game["doc"]
            games_by_id[document.get("game_id") or game["game_id"]] = game
        sample_keys = [tuple(rows[index]["key"]) for index in chosen[:60]]
        leak_probe(games_by_id, sample_keys, parent, audit2)
        print("  非主体暗牌互换受检 %d 次；分数变化 %d 次（必须 0）"
              % (audit2["leak_other_seats_checked"], audit2["leak_other_seats_CHANGED"]))
        print("  主体自己暗牌改动受检 %d 次；分数变化 %d 次（必须全部变化）"
              % (audit2["leak_own_hand_checked"], audit2["leak_own_hand_CHANGED"]))
    payload["leak"] = dict(sorted(audit2.items()))
    payload["audit"].update(dict(sorted(audit2.items())))

    payload["elapsed_sec"] = time.time() - started
    (_project_file(_PROJECT_ROOT, OUT / "summary.json")).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    with gzip.open(_project_file(_PROJECT_ROOT, OUT / "windows.jsonl.gz"), "wt", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    print()
    print("产物：%s（cards.jsonl.gz / cards.md / windows.jsonl.gz / summary.json）" % OUT)
    print("总用时 %.1f 秒" % (time.time() - started))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
