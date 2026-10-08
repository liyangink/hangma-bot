#!/usr/bin/env python3
"""C31：动作层的「可见事实缺口 vs 同事实权重缺口」标定。

口径、窗口、观察重建白名单、margin 定义、分箱边界、Δ 算法与判定三态见同目录
C31-PREREG-ACTION-LAYER-GAP.md（该文件在本脚本任何结论性运行之前落盘，落盘后不改）。

纪律：
* 复用 C23 的窗口模型与 C27 的格定义（import c23_claim_opportunity / c27_claim_cells，
  只读不改）；本脚本不实现任何吃碰杠合法性、向听、听牌或爆头规则，全部经 hangma；
* 视图构造走生产同一条接缝：hangma.engine.HangmaRules.analyze →
  policy.interface.DecisionRequest → policy.action_value_policy.build_scoring_view →
  ScoringView.candidate_view()；
* 冻结父代 r18_integrated_positive_v2 只读：装配前断言源码摘要；
* 信息权限：只读官方牌谱 events.json、公开周榜快照、既有重建索引 rounds.jsonl，
  以及 p6 生产视图缓存（只用于第三类核对）。脚本末尾对读取路径做断言。

用法：
    UV_CACHE_DIR=/tmp/uv-cache .venv/bin/python \
        review/freematch-deep-dive-20260925/c31_action_layer_gap.py
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
import c23_claim_opportunity as C23  # noqa: E402
import c27_claim_cells as C27  # noqa: E402
import stats_lib as SL  # noqa: E402

from hangma_bot.hangma import progression  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402
from hangma_bot.hangma.internal_types import TILE_ORDER  # noqa: E402
from dataclasses import replace
from hangma_bot.kernel.actions import (  # noqa: E402
    Chi,
    Discard,
    Gang,
    Peng,
    Tile,
    WindowKey,
    WindowPhase,
)
from hangma_bot.kernel.config import RuleConfig  # noqa: E402
from hangma_bot.kernel.observation import (  # noqa: E402
    CompetitionContext,
    PlayerObservation,
    PublicDiscard,
    PublicMeld,
    RulePublicState,
)
from hangma_bot.policy.action_value_policy import build_scoring_view  # noqa: E402
from hangma_bot.policy.interface import DecisionRequest  # noqa: E402
from hangma_bot.policy.r18_integrated_positive_v2 import (  # noqa: E402
    R18_INTEGRATED_POSITIVE_V2_SHA256,
    R18_INTEGRATED_POSITIVE_V2_SOURCE,
)

OUT = _project_file(_PROJECT_ROOT, ROOT / ".team-work" / "c31-action-layer")
ROUNDS_JSONL = _project_file(_PROJECT_ROOT, 'review/baotou-anatomy-20260925/rounds.jsonl')
P6_CACHE_GLOB = str(_project_file(_PROJECT_ROOT, ROOT / ".team-work" / "p6-baotou-route" / "cache" / "*.jsonl.gz"))

ME = AL.ME
WEALTH = AL.WEALTH
WALL_TOTAL = 136

RULE_CONFIG = RuleConfig(
    ruleset_version="hangma-mvp-v10-public-counts", base_score=1, you_cai_bi_kao=False,
)
"""与 R18 v2 发布包声明逐项一致（r18_integrated_positive_v2_release.py:64-67）。"""

VALUE_LIMITS = ValueAnalysisLimits()
"""与发布包声明一致（max_expansions=2048 / max_routes_per_candidate=128）。"""

RULES = HangmaRules(RULE_CONFIG)

BINS = ((-10 ** 9, -20.0), (-20.0, -10.0), (-10.0, -5.0),
        (-5.0, 0.0), (0.0, 5.0), (5.0, 10 ** 9))
BIN_LABELS = ("<=-20", "(-20,-10]", "(-10,-5]", "(-5,0]", "(0,+5]", ">+5")

C_STAR = ("F3:same", "F1:sh0")
"""任务书背景第 3 条冻结的定位格（C27 非退化定位格 + 听牌格）。"""

GROUPS = ("me", "elite")
CLAIM_TYPES = ("peng", "chi", "gang")

RHO_WEIGHT_DOMINANT = 0.70
RHO_FACT_DOMINANT = 0.40

XUANWU_ID = "u_380da525337c"
"""同桌复核锁定的强手（玄武-2346）；只用于评审第 2 条的逐格对照。"""

READ_PATHS = []
"""本脚本实际读取的文件路径（泄漏检查用）。"""


# ---------------------------------------------------------------------------
# 冻结父代
# ---------------------------------------------------------------------------


def load_parent():
    """装配冻结父代 score_actions；源码摘要必须等于发布包声明。"""

    digest = hashlib.sha256(R18_INTEGRATED_POSITIVE_V2_SOURCE.encode("utf-8")).hexdigest()
    if digest != R18_INTEGRATED_POSITIVE_V2_SHA256:
        raise SystemExit("冻结父代源码摘要漂移：%s" % digest)
    namespace = {"__name__": "c31_frozen_parent"}
    exec(compile(R18_INTEGRATED_POSITIVE_V2_SOURCE, "<r18_integrated_positive_v2>", "exec"),
         namespace)
    return namespace["score_actions"]


# ---------------------------------------------------------------------------
# 重建：逐事件推进，给每一张弃牌留一份响应窗口快照（纯公开事实）
# ---------------------------------------------------------------------------


def _tiles(counter):
    result = []
    for code in TILE_ORDER:
        result.extend([Tile(code)] * counter[code])
    return tuple(result)


def reconstruct(events, start_hands, table_scores, dealer):
    """重建一局，返回 {弃牌事件 seq: 快照}。

    快照 = 该弃牌**被响应之前**的四家公开状态。被鸣走的弃牌在该快照里仍在
    牌河（它就是刚打出的那张）；鸣牌发生后从牌河移入鸣牌者副露——这与官方
    wall_remaining 恒等式一致（见 c31_rebuild_validate.py 的对拍）。
    其余三家暗牌只保存在快照里供赛后核对；构造某座观察时只取该座自己的暗牌。
    """

    hands = [collections.Counter(hand) for hand in start_hands]
    rivers = [[] for _ in range(4)]
    melds = [[] for _ in range(4)]
    melds_count = [0, 0, 0, 0]
    catch = [False, False, False, False]
    baotou = []
    for hand in start_hands:
        if len(hand) == 14:
            baotou.append(None)
        else:
            try:
                baotou.append(progression.baotou_after_discard(
                    _tiles(collections.Counter(hand)), 0))
            except Exception:  # noqa: BLE001
                baotou.append(None)
    chain = [0, 0, 0, 0]
    piao = [0, 0, 0, 0]
    discards_n = [0, 0, 0, 0]

    snaps = {}
    index = 0
    total = len(events)
    while index < total:
        event = events[index]
        kind = event["type"]
        seat = event.get("seat")
        tile = event.get("tile")
        data = event.get("data") or {}
        if kind in ("round_ended", "game_ended"):
            break
        if kind in ("pass", "timeout"):
            index += 1
            continue
        if kind == "tile_drawn":
            before = _tiles(hands[seat])
            hands[seat][tile] += 1
            try:
                baotou[seat] = progression.baotou_after_draw(
                    bool(baotou[seat]), before, melds_count[seat], Tile(tile))
            except (ValueError, TypeError):
                baotou[seat] = None
            index += 1
            continue
        if kind == "peng":
            melds_count[seat] += 1
            melds[seat].append({"kind": "peng", "tiles": [tile] * 3, "from": None})
            hands[seat][tile] -= 2
            index += 1
            continue
        if kind == "chi":
            consumed = list(data["tiles"])
            consumed.remove(tile)
            for code in consumed:
                hands[seat][code] -= 1
            melds_count[seat] += 1
            melds[seat].append({"kind": "chi", "tiles": sorted(list(data["tiles"])),
                                "from": None})
            index += 1
            continue
        if kind == "gang":
            gang_kind = data.get("kind")
            consumed = {"ming": 3, "an": 4, "bu": 1}.get(gang_kind)
            if consumed is None:
                index += 1
                continue
            if gang_kind == "bu":
                for group in melds[seat]:
                    if group["kind"] == "peng" and group["tiles"] and group["tiles"][0] == tile:
                        group["kind"] = "gang_bu"
                        group["tiles"] = [tile] * 4
                        break
            else:
                melds_count[seat] += 1
                melds[seat].append({
                    "kind": "gang_ming" if gang_kind == "ming" else "gang_an",
                    "tiles": [tile] * (3 if gang_kind == "ming" else 4),
                    "from": None})
            hands[seat][tile] -= consumed
            chain[seat], piao[seat] = progression.chain_after_gang(chain[seat], piao[seat])
            baotou[seat] = None
            index += 1
            continue
        if kind != "tile_discarded":
            index += 1
            continue

        # ---- 弃牌：先应用，再留响应窗口快照 ----
        hands[seat][tile] -= 1
        rivers[seat].append(tile)
        discards_n[seat] += 1
        # 链状态依赖弃牌前的持续爆头态；普通弃牌断链，爆头弃白才计飘。
        # 与线上唯一规则来源共用同一转移，避免赛后重建把番数错带到后续响应窗。
        chain[seat], piao[seat] = progression.chain_after_discard(
            chain[seat], piao[seat], bool(baotou[seat]), Tile(tile))
        if tile == WEALTH:
            catch = [False, False, False, False]
            catch[seat] = True
        else:
            catch[seat] = False
        owners = [item for item in range(4) if catch[item]]
        owner = owners[0] if owners else None
        try:
            baotou[seat] = progression.baotou_after_discard(
                _tiles(hands[seat]), melds_count[seat])
        except Exception:  # noqa: BLE001
            baotou[seat] = None

        # 响应段：该弃牌之后、下一张弃牌之前的响应型鸣牌
        cursor = index + 1
        claim = None
        responses = []
        while cursor < total:
            nxt = events[cursor]
            ntype = nxt["type"]
            if ntype in ("pass", "timeout"):
                if nxt.get("seat") is not None:
                    responses.append([nxt["seat"], ntype,
                                      (nxt.get("data") or {}).get("window")])
                cursor += 1
                continue
            if ntype in ("peng", "chi") or (
                    ntype == "gang" and (nxt.get("data") or {}).get("kind") == "ming"):
                claim = nxt
            break

        snaps[event["seq"]] = {
            "seq": event["seq"],
            "discarder": seat,
            "tile": tile,
            "owner": owner,
            "hands": [collections.Counter(hand) for hand in hands],
            "rivers": [list(river) for river in rivers],
            "melds": [[dict(group) for group in row] for row in melds],
            "melds_count": list(melds_count),
            "baotou": list(baotou),
            "chain": list(chain),
            "piao": list(piao),
            "discards_n": list(discards_n),
            "table_scores": list(table_scores),
            "dealer": dealer,
            "claim_seat": None if claim is None else claim["seat"],
            "claim_kind": None if claim is None else claim["type"],
            "responses": responses,
        }

        # ---- 应用鸣牌后果，继续推进事件流 ----
        if claim is not None and claim["seat"] is not None:
            claim_seat = claim["seat"]
            if rivers[seat] and rivers[seat][-1] == tile:
                rivers[seat].pop()
            if claim["type"] == "peng":
                hands[claim_seat][tile] -= 2
                melds_count[claim_seat] += 1
                melds[claim_seat].append({"kind": "peng", "tiles": [tile] * 3, "from": seat})
            elif claim["type"] == "chi":
                raw = list((claim.get("data") or {}).get("tiles") or [])
                consumed = list(raw)
                if tile in consumed:
                    consumed.remove(tile)
                for code in consumed:
                    hands[claim_seat][code] -= 1
                melds_count[claim_seat] += 1
                melds[claim_seat].append({"kind": "chi", "tiles": sorted(raw), "from": seat})
            else:
                hands[claim_seat][tile] -= 3
                melds_count[claim_seat] += 1
                melds[claim_seat].append({"kind": "gang_ming", "tiles": [tile] * 4,
                                          "from": seat})
            baotou[claim_seat] = None
            index = cursor + 1
            continue
        index += 1

    return snaps


def _peng_members(discarder, tile, owner):
    return C23.window_members(discarder, tile, owner)[0]


def _chi_members(discarder, tile, owner):
    return C23.window_members(discarder, tile, owner)[1]


# ---------------------------------------------------------------------------
# 观察构造（白名单字段；只取该座自己的暗牌）
# ---------------------------------------------------------------------------


def build_observation(snap, seat, phase, game_id, round_no):
    """把公开快照投影成生产同形的 PlayerObservation。

    只用：该座自己的暗牌、四家牌河与副露、四家暗牌张数、桌内累计分、庄位、
    圈态与链态、触发弃牌。其余三家的暗牌不参与（泄漏检查见
    c31_rebuild_validate.py 的扰动不变量）。
    """

    discarder = snap["discarder"]
    tile = snap["tile"]
    seq = snap["seq"]
    rivers = snap["rivers"]
    melds = snap["melds"]
    hand_counts = tuple(sum(snap["hands"][index].values()) for index in range(4))
    meld_tiles = sum(len(group["tiles"]) for row in melds for group in row)
    remaining = WALL_TOTAL - sum(hand_counts) - sum(len(river) for river in rivers) - meld_tiles
    members = (_peng_members(discarder, tile, snap["owner"]) if phase == "response_peng"
               else _chi_members(discarder, tile, snap["owner"]))
    chain_count = snap["chain"][seat]
    chain_piao = min(snap["piao"][seat], chain_count)
    return PlayerObservation(
        game_id=game_id,
        seat=seat,
        round_no=round_no,
        snapshot_seq=seq,
        phase=phase,
        dealer_seat=snap["dealer"],
        turn_seat=discarder,
        responding_seats=tuple(members),
        my_hand=_tiles(snap["hands"][seat]),
        drawn_tile=None,
        discards=tuple(tuple(Tile(code) for code in river) for river in rivers),
        melds=tuple(tuple(
            PublicMeld(seat=index, kind=group["kind"],
                       tiles=tuple(Tile(code) for code in group["tiles"]),
                       from_seat=group.get("from"))
            for group in melds[index]) for index in range(4)),
        hand_counts=hand_counts,
        last_discard=PublicDiscard(seat=discarder, tile=Tile(tile), seq=seq),
        remaining_tile_count=remaining,
        scores=tuple(snap["table_scores"]),
        rule_state=RulePublicState(
            wealth_god=Tile(WEALTH),
            baotou=bool(snap["baotou"][seat]),
            chain_count=chain_count,
            catch_play=snap["owner"] is not None,
            catch_play_owner_seat=snap["owner"],
        ),
        public_history=(),
        chain_piao=chain_piao,
        gang_draw=False,
    )


def score_window(observation, parent):
    """跑规则分析 + 生产视图 + 冻结父代；返回 (view, scores, status, reason)。"""

    analysis = RULES.analyze(observation, value_limits=VALUE_LIMITS)
    request = DecisionRequest(
        observation=observation,
        competition=CompetitionContext(
            tournament_id="c31-offline",
            stage_no=None, stage_role=None, stage_total=None,
            participant_rank=None, ranking=(), observed_at_unix_ms=0),
        rules=analysis,
        decision_id="c31",
        trigger_seq=observation.snapshot_seq,
        window_key=WindowKey(
            game_id=observation.game_id, round_no=observation.round_no,
            trigger_seq=observation.snapshot_seq,
            phase=(WindowPhase.RESPONSE_PENG if observation.phase == "response_peng"
                   else WindowPhase.RESPONSE_CHI),
            seat=observation.seat),
        rejected_attempts=(),
    )
    view = build_scoring_view(request, value_limits=VALUE_LIMITS).candidate_view()
    result = parent(view)
    status = result.get("status")
    if status != "SCORED":
        return view, None, status, result.get("reason"), analysis
    scores = {entry["action_key"]: entry["score"] for entry in result.get("entries") or []}
    bases = {entry["action_key"]: (entry.get("trace") or {}).get("base_score")
             for entry in result.get("entries") or []}
    return view, scores, status, None, analysis, bases


def evaluate_window(snap, seat, phases, game_id, round_no, parent):
    """跑该座在该弃牌上的全部 phase，返回 (窗口记录或 None, 每 phase, 审计)。

    margin 定义见 PREREG 第 5 节：每个 phase 各自
    max(鸣牌候选分) − pass 分，窗口取两者最大；机会定义与 C27 的 hit 一致
    （合法碰 或 合法吃，明杠不进入机会定义）。
    """

    per_phase = []
    audit = collections.Counter()
    for phase in phases:
        observation = build_observation(snap, seat, phase, game_id, round_no)
        view, scores, status, reason, analysis, bases = score_window(observation, parent)
        entry = {"phase": phase, "view": view, "scores": scores, "status": status,
                 "observation": observation, "analysis": analysis, "bases": bases,
                 "degraded": analysis.completeness.value != "complete",
                 "issues": tuple(issue.area for issue in analysis.issues)}
        if status != "SCORED":
            entry["reason"] = reason
            per_phase.append(entry)
            audit["abstain_" + phase] += 1
            audit["abstain_reason:" + str(reason)[:40]] += 1
            continue
        actions = view["actions"]
        claims = [item for item in actions
                  if item["action_type"] in CLAIM_TYPES and item["action_key"] in scores]
        passes = [item for item in actions
                  if item["action_type"] == "pass" and item["action_key"] in scores]
        if not passes or not claims:
            audit["degenerate_no_pass" if not passes else "degenerate_no_claim"] += 1
            per_phase.append(entry)
            continue
        pass_action = passes[0]
        best = max(claims, key=lambda item: (scores[item["action_key"]], item["action_key"]))
        entry.update({
            "pass": pass_action,
            "pass_score": scores[pass_action["action_key"]],
            "claim": best,
            "claim_score": scores[best["action_key"]],
            "margin": scores[best["action_key"]] - scores[pass_action["action_key"]],
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


def width_of(action):
    """动作表里的有效牌未见张数之和；缺任何一张计数即 None（不猜零）。"""

    tiles = action.get("useful_tiles")
    if tiles is None:
        return None
    total = 0.0
    for item in tiles:
        remaining = item.get("remaining_estimate")
        if remaining is None or remaining is True or remaining is False:
            return None
        total += float(remaining)
    return total


CLAIM_PENALTY = {"peng": -6.0, "chi": -10.0, "gang": 40.0}
"""冻结父代对非弃牌候选的固定项（r18_integrated_positive_v2 源码 line 172-178）。"""


def post_claim_observation(observation, action, *, remove_claimed_from_river=False):
    """鸣牌**之后**、跟打之前的观察（走牌阶段的合法弃牌全集来源）。

    只做规则模块要求的机械状态搬运：暗牌扣减、副露 +1、座位转为该座出牌。
    2026-09-14 后官方快照会从供牌者牌河移走被鸣牌；对已核准该口径的
    官方样本显式传 ``remove_claimed_from_river=True``。默认保留旧行为，
    避免悄悄改变旧口径研究；不明口径的调用方须自行做双包络或弃权。
    """

    seat = observation.seat
    claimed = observation.last_discard
    if isinstance(action, Peng):
        removal = {action.tile.code: 2}
        meld = PublicMeld(seat=seat, kind="peng", tiles=(action.tile,) * 3, from_seat=None)
    elif isinstance(action, Chi):
        target = claimed.tile.code if claimed is not None else None
        removal = {}
        skipped = False
        for tile in action.tiles:
            if tile.code == target and not skipped:
                skipped = True
                continue
            removal[tile.code] = removal.get(tile.code, 0) + 1
        meld = PublicMeld(seat=seat, kind="chi", tiles=tuple(action.tiles), from_seat=None)
    elif isinstance(action, Gang):
        removal = {action.tile.code: 3}
        meld = PublicMeld(seat=seat, kind="gang_ming", tiles=(action.tile,) * 4,
                          from_seat=None)
    else:
        return None
    hand = list(observation.my_hand)
    for code, amount in removal.items():
        for _ in range(amount):
            for index, tile in enumerate(hand):
                if tile.code == code:
                    del hand[index]
                    break
            else:
                return None
    counts = list(observation.hand_counts)
    counts[seat] = len(hand)
    melds = [tuple(row) for row in observation.melds]
    if remove_claimed_from_river:
        if claimed is None or claimed.seat == seat:
            return None
        rivers = [tuple(row) for row in observation.discards]
        river = rivers[claimed.seat]
        if not river or river[-1] != claimed.tile:
            return None
        rivers[claimed.seat] = river[:-1]
        meld = replace(meld, from_seat=claimed.seat)
    else:
        rivers = observation.discards
    melds[seat] = melds[seat] + (meld,)
    return replace(observation, phase="draw", turn_seat=seat, responding_seats=(),
                   my_hand=tuple(hand), melds=tuple(melds), hand_counts=tuple(counts),
                   drawn_tile=None, discards=tuple(rivers),
                   last_discard=None if remove_claimed_from_river else claimed)


def followup_value(observation, action):
    """「鸣牌 + 最佳合法跟打」的完整价值：返回 (base, discard_key, baotou_after)。

    base 与父代对弃牌候选的 base 同式：-100×向听 + Σ有效牌公开未见张数。
    跟打全集由规则模块在**鸣牌后的观察**上生成，不另写合法性。
    """

    post = post_claim_observation(observation, action)
    if post is None:
        return None
    analysis = RULES.analyze(post)
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
            if isinstance(remaining, bool):
                ok = False
                break
            support += remaining
        if not ok:
            continue
        value = -100.0 * float(shanten) + round(float(support), 1)
        key = (-value, candidate.action_key)
        if best is None or key < best[0]:
            best = (key, value, candidate.action_key, facts.baotou_after)
    if best is None:
        return None
    return {"base": best[1], "discard": best[2], "baotou_after": best[3]}


def followup_column(window, claim_key):
    """可选列：把鸣牌候选的价值换成「鸣牌 + 最佳合法跟打」后的重算 margin。"""

    observation = window["observation"]
    bases = window["bases"] or {}
    types = {item["action_key"]: item["action_type"] for item in window["view"]["actions"]}
    values = {}
    for candidate in window["analysis"].legal_candidates:
        if types.get(candidate.action_key) not in CLAIM_TYPES:
            continue
        result = followup_value(observation, candidate.action)
        if result is not None:
            values[candidate.action_key] = result
    if claim_key not in values:
        return {"available": False}
    parent_base = bases.get(claim_key)
    picked = values[claim_key]
    margin_followup = None
    if parent_base is not None:
        margin_followup = window["margin"] + (picked["base"] - float(parent_base))
    best_key = None
    best_total = None
    for key, result in values.items():
        total = result["base"] + CLAIM_PENALTY.get(types.get(key), 0.0)
        if best_total is None or total > best_total or (
                total == best_total and (best_key is None or key < best_key)):
            best_total = total
            best_key = key
    parent_followup = window["claim"].get("best_followup_discard")
    return {
        "available": True,
        "parent_base": parent_base,
        "followup_base": picked["base"],
        "followup_discard": picked["discard"],
        "followup_baotou": picked["baotou_after"],
        "parent_followup": parent_followup,
        "pick_matches_parent": (
            None if parent_followup is None
            else "discard:" + parent_followup == picked["discard"]),
        "bt_action": window["claim"].get("baotou_after"),
        "margin_followup": margin_followup,
        "delta_margin": (None if margin_followup is None
                         else margin_followup - window["margin"]),
        "claim_changed": best_key != claim_key,
        "best_followup_claim": best_key,
        "n_claim_candidates": len(values),
    }


def parent_space_feature(window):
    """按父代动作表算 C27 同一份格特征（键与 feature_of_record 相同）。

    F3 的 dsh 与 F4 的 dw 直接取父代动作表的口径（CELL-R6 常数作用的同一空间）；
    F1 的 sh 取 pass 候选的 shanten_after（= 过牌后的等待向听）。
    """

    claim = window["claim"]
    pas = window["pass"]
    visible = window["visible"]
    claim_shanten = claim.get("shanten_after")
    pass_shanten = pas.get("shanten_after")
    if (claim_shanten is None or pass_shanten is None
            or isinstance(claim_shanten, bool) or isinstance(pass_shanten, bool)):
        dsh = "unknown"
    else:
        delta = claim_shanten - pass_shanten
        dsh = "down" if delta < 0 else ("same" if delta == 0 else "up")
    left = width_of(pas)
    right = width_of(claim)
    if left is None or right is None:
        dw = "unknown"
    elif right - left > 0:
        dw = "wider"
    elif right - left == 0:
        dw = "equal"
    else:
        dw = "narrower"
    bucket = 3 if (pass_shanten is None or isinstance(pass_shanten, bool)) else min(3, pass_shanten)
    discards_n = len(visible["discards"][visible["seat"]])
    wall = visible.get("remaining_tile_count")
    tile = (visible.get("last_discard") or {}).get("tile")
    return {
        "sh": bucket,
        "fam": "peng" if window["has_peng"] else "chi",
        "dsh": dsh,
        "dw": dw,
        "ml": "m0" if len(visible["melds"][visible["seat"]]) == 0 else (
            "m1" if len(visible["melds"][visible["seat"]]) == 1 else "m2p"),
        "tn": "t0_2" if discards_n <= 2 else ("t3_6" if discards_n <= 6 else "t7p"),
        "wl": "w60p" if (wall or 0) >= 60 else ("w40_59" if (wall or 0) >= 40 else "wlt40"),
        "tc": "number" if (tile and len(tile) >= 2 and tile[0] in "123456789") else "honor",
        "bt": "yes" if claim.get("baotou_after") is True else "no",
    }


def bin_label(margin):
    for index, (low, high) in enumerate(BINS):
        if low < margin <= high:
            return BIN_LABELS[index]
    return BIN_LABELS[0]


def quantile(values, probability):
    """线性插值分位点（PREREG 第 6.3 节冻结的算法）。"""

    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    fraction = position - low
    return ordered[low] * (1.0 - fraction) + ordered[high] * fraction


def bootstrap_delta(rooms, draws=1200, seed=20260926):
    """按房 cluster bootstrap 的 Δ 区间（PREREG 第 6.3 节）。"""

    keys = sorted(rooms)
    if not keys:
        return {"lo": None, "hi": None, "mean": None, "rooms": 0, "draws": 0}
    rng = random.Random(seed)
    values = []
    for _ in range(draws):
        margins = []
        chances = 0
        taken = 0
        for _ in keys:
            room = rng.choice(keys)
            entry = rooms[room]
            margins.extend(entry["margins"])
            chances += entry["elite_chances"]
            taken += entry["elite_taken"]
        if not margins or not chances:
            continue
        level = 1.0 - taken / chances
        if level <= 0.0:
            values.append(-min(margins))
        elif level >= 1.0:
            values.append(-max(margins))
        else:
            values.append(-quantile(margins, level))
    if not values:
        return {"lo": None, "hi": None, "mean": None, "rooms": len(keys), "draws": 0}
    values.sort()
    return {"lo": values[int(0.025 * len(values))],
            "hi": values[min(len(values) - 1, int(0.975 * len(values)))],
            "mean": statistics.fmean(values), "rooms": len(keys), "draws": len(values)}


def load_p6_cache():
    """生产候选表缓存（只含冻结 R18 v2 战役）；用于第三类核对。"""

    index = collections.defaultdict(list)
    paths = sorted(glob.glob(P6_CACHE_GLOB))
    for path in paths:
        READ_PATHS.append(path)
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                key = (row.get("game_id"), row.get("round_no"), row.get("trigger_seq"))
                index[key].append({
                    "phase": row.get("phase"),
                    "plan_keys": row.get("plan_keys") or [],
                    "plan_rank1": row.get("plan_rank1"),
                    "run": row.get("run_id"),
                    "room": row.get("room"),
                })
    return index, paths


def run_identities(rooms=None):
    """按审计 run manifest 取策略身份（不靠命名推断）。

    返回 {(room, run_id): {"strategy","policy_version","candidate_source_sha256"}}；
    只读 manifest.json，不读任何决策内容。
    """

    wanted_rooms = set(rooms) if rooms else None
    identities = {}
    pattern = str(_project_file(_PROJECT_ROOT, ROOT / "artifacts" / "sessions" / "*" / "audit" / "runs" / "*"
                  / "manifest.json"))
    for path in sorted(glob.glob(pattern)):
        parts = Path(path).parts
        room = parts[parts.index("sessions") + 1]
        if wanted_rooms is not None and room not in wanted_rooms:
            continue
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8")).get("payload") or {}
        except (OSError, ValueError):
            continue
        READ_PATHS.append(path)
        release = payload.get("policy_release") or {}
        identities[(room, Path(path).parent.name)] = {
            "strategy": release.get("strategy") or payload.get("policy_version"),
            "policy_version": payload.get("policy_version"),
            "candidate_source_sha256": release.get("candidate_source_sha256"),
            "release_schema": release.get("schema"),
        }
    return identities


def round_metadata(document):
    """按 official 块与 round_ended 事件取每局的庄位与当局分数增量。

    官方 rounds[] 会省略零分流局（实测存在：块里有 round_no 而 rounds[] 无），
    因此庄位以块字段 dealer 为第一来源、round_ended.data.dealer 为第二来源；
    分数增量取 round_ended.data.scores，逐局累加得桌内累计分。
    """

    meta = {}
    for block in document.get("blocks") or []:
        index = block.get("round_no")
        if not isinstance(index, int):
            continue
        entry = meta.setdefault(index, {})
        dealer = block.get("dealer")
        if isinstance(dealer, int) and 0 <= dealer <= 3:
            entry.setdefault("dealer", dealer)
    return meta


def round_end_facts(events):
    """从事件流取该局的 round_ended：返回 (dealer, scores)。"""

    for event in events:
        if event["type"] == "round_ended":
            data = event.get("data") or {}
            dealer = data.get("dealer")
            scores = data.get("scores")
            if not isinstance(dealer, int) or not 0 <= dealer <= 3:
                dealer = None
            if not (isinstance(scores, list) and len(scores) == 4
                    and all(isinstance(item, int) for item in scores)):
                scores = None
            return dealer, scores
    return None, None


# ---------------------------------------------------------------------------
# 三张表
# ---------------------------------------------------------------------------


def table_a(rows, title):
    """表 A：标定曲线——按 margin 分箱的实际鸣牌率。"""

    out = {"title": title, "bins": []}
    for label in BIN_LABELS:
        entry = {"bin": label}
        for group in GROUPS:
            subset = [row for row in rows if row["group"] == group and row["bin"] == label]
            taken = sum(row["claimed"] for row in subset)
            entry[group] = {
                "windows": len(subset), "claimed": taken,
                "rate": (taken / len(subset)) if subset else None,
            }
        out["bins"].append(entry)
    return out


def cell_index(rows, group, key):
    return [row for row in rows if row["group"] == group and row["labels"].get(key[:2]) == key]


def attribution(rows, cells, name):
    """表 B：缺口归属（我方未鸣窗按 margin 符号拆分）。"""

    selected = []
    for row in rows:
        if row["group"] != "me" or row["claimed"]:
            continue
        if any(row["labels"].get(key[:2]) == key for key in cells):
            selected.append(row)
    weight = [row for row in selected if row["margin"] <= 0.0]
    fact = [row for row in selected if row["margin"] > 0.0]
    total = len(selected)
    rho = (len(weight) / total) if total else None
    if rho is None:
        verdict = "n/a"
    elif rho >= RHO_WEIGHT_DOMINANT:
        verdict = "权重缺口为主"
    elif rho <= RHO_FACT_DOMINANT:
        verdict = "事实缺口为主"
    else:
        verdict = "灰区"
    return {
        "name": name, "cells": list(cells), "windows": total,
        "weight_gap": len(weight), "fact_gap": len(fact), "rho": rho, "verdict": verdict,
        # 事实缺口窗的构成（判读用）：按 phase 与「另一家先鸣走」拆
        "fact_gap_by_phase": dict(collections.Counter(row["phase"] for row in fact)),
        "fact_gap_other_claimed": sum(1 for row in fact if row["other_claimed"]),
        "fact_gap_frozen": sum(1 for row in fact if row["frozen_run"]),
    }


def table_c(rows, cell, title):
    """表 C：格内隐含剂量 Δ。"""

    mine = cell_index(rows, "me", cell)
    theirs = cell_index(rows, "elite", cell)
    elite_taken = sum(row["claimed"] for row in theirs)
    elite_usage = (elite_taken / len(theirs)) if theirs else None
    margins = sorted(row["margin"] for row in mine)
    delta = None if (elite_usage is None or not margins) else -quantile(margins, 1.0 - elite_usage)
    rooms = collections.defaultdict(lambda: {"margins": [], "elite_chances": 0, "elite_taken": 0})
    for row in mine:
        rooms[row["room"]]["margins"].append(row["margin"])
    for row in theirs:
        rooms[row["room"]]["elite_chances"] += 1
        rooms[row["room"]]["elite_taken"] += row["claimed"]
    rooms = {room: entry for room, entry in rooms.items() if entry["margins"]}
    interval = bootstrap_delta(rooms)
    my_usage = (sum(row["claimed"] for row in mine) / len(mine)) if mine else None
    their_margins = sorted(row["margin"] for row in theirs)
    delta_prime = (None if (my_usage is None or not their_margins)
                   else -quantile(their_margins, 1.0 - my_usage))
    return {
        "cell": cell, "title": title,
        "me_windows": len(mine), "me_claimed": sum(row["claimed"] for row in mine),
        "me_usage": my_usage,
        "elite_windows": len(theirs), "elite_claimed": elite_taken,
        "elite_usage": elite_usage,
        "delta": delta, "delta_interval": interval, "delta_prime": delta_prime,
        "me_margin_quantiles": ({str(level): quantile(margins, level)
                                 for level in (0.1, 0.25, 0.5, 0.75, 0.9)} if margins else {}),
        "elite_margin_quantiles": ({str(level): quantile(their_margins, level)
                                    for level in (0.1, 0.25, 0.5, 0.75, 0.9)}
                                   if their_margins else {}),
    }


FROZEN_SHA12 = R18_INTEGRATED_POSITIVE_V2_SHA256[:12]


def third_category(rows):
    """第三类：margin > 0 且我方实际没过——逐项排查后分桶（评审新增，不覆盖原读数）。

    条件表为**非互斥**计数；buckets 为按优先级的互斥归因。只有
    「同 phase 有线上决策记录、且动作键不在生产候选表」才归入事实缺口候选，
    其余一律归入「重建/身份/候选/执行未对齐」。
    """

    selected = [row for row in rows
                if row["group"] == "me" and not row["claimed"] and row["margin"] > 0.0]
    conditions = collections.Counter()
    buckets = collections.Counter()
    examples = []
    for row in selected:
        conditions["windows"] += 1
        identity = row.get("policy_identity")
        frozen_v2 = bool(identity and identity[2] == FROZEN_SHA12)
        phase_online = (row.get("prod_phases") is not None
                        and row["phase"] in (row.get("prod_phases") or []))
        if identity is not None:
            conditions["audited_identity"] += 1
        if frozen_v2:
            conditions["identity_frozen_v2"] += 1
        if phase_online:
            conditions["phase_seen_online"] += 1
        if row.get("prod_phase_has_claim") is True:
            conditions["claim_key_in_prod_table"] += 1
        if row.get("prod_phase_has_claim") is False:
            conditions["claim_key_missing_in_prod_table"] += 1
        if row.get("hu_keys"):
            conditions["hu_available"] += 1
        if row.get("gang_beats_claim"):
            conditions["gang_beats_claim"] += 1
        if row.get("degraded"):
            conditions["analysis_degraded"] += 1
        kinds = row.get("response_kinds") or []
        if "timeout" in kinds:
            conditions["response_timeout_any"] += 1
            if "pass" not in kinds:
                conditions["response_timeout_only"] += 1
        if row.get("other_claimed"):
            conditions["other_seat_claimed_discard"] += 1

        if row.get("degraded") or row.get("hu_keys") or row.get("gang_beats_claim"):
            bucket = "4/5 规则降级或存在更高优先级动作（胡/杠打分更高）"
        elif not frozen_v2:
            bucket = "1 身份未对齐：该局无冻结 R18 v2 审计记录"
        elif not phase_online:
            bucket = ("2 反事实窗：该 phase 窗口线上从未开（另一家先鸣走该弃牌）"
                      if row.get("other_claimed")
                      else "2/5 线上同 phase 无决策记录（未记录或窗口未开）")
        elif row.get("prod_phase_has_claim") is False:
            bucket = "3 事实缺口候选：动作键不在生产候选表"
            if len(examples) < 10:
                examples.append([row["game_id"], row["round_no"], row["seq"],
                                 row["claim_key"], row["margin"], row["phase"]])
        elif row.get("prod_phase_rank1") == row["claim_key"]:
            bucket = "5 生产 rank1 就是该动作（执行或重建未对齐）"
        else:
            bucket = "3b 在候选表但非 rank1（打分未对齐）"
        buckets[bucket] += 1
    return {"windows": len(selected), "conditions": dict(conditions),
            "buckets": dict(buckets), "examples": examples}


STATE_FAMILIES = ("F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "G4", "G5")


def _wall_bucket(value):
    if value is None:
        return "unknown"
    return "w>=60" if value >= 60 else ("w40_59" if value >= 40 else "w<40")


def xuanwu_comparison(rows, target, label):
    """评审第 2 条：玄武本人合法观察上「父代也认为该过、玄武实际鸣了」的窗与我方逐格对照。

    单位：窗。格的家族与 C27 同一份定义；同时报各格样本数、两边状态分布与无法匹配比例。
    """

    x_set = [row for row in rows
             if row.get("user_id") == target and row["margin"] <= 0.0 and row["claimed"]]
    m_set = [row for row in rows if row["group"] == "me"]
    m_noclaim = [row for row in m_set if not row["claimed"] and row["margin"] <= 0.0]
    result = {
        "target": target, "label": label,
        "x_windows": len(x_set), "x_rooms": len({row["room"] for row in x_set}),
        "x_rounds": len({(row["game_id"], row["round_no"]) for row in x_set}),
        "m_windows": len(m_set), "m_noclaim_windows": len(m_noclaim),
        "cells": {}, "state": {}, "match": {},
    }
    for family in STATE_FAMILIES:
        result["cells"][family] = {
            "x": dict(sorted(collections.Counter(
                row["labels"][family] for row in x_set).items())),
            "m": dict(sorted(collections.Counter(
                row["labels"][family] for row in m_set).items())),
        }
    for name, fn in (
        ("pass_shanten", lambda row: str(row.get("pass_shanten"))),
        ("width_delta", lambda row: row["labels"]["F4"].split(":", 1)[1]),
        ("whites", lambda row: str(row.get("whites"))),
        ("melds", lambda row: str(row.get("melds"))),
        ("dealer", lambda row: "dealer" if row.get("is_dealer") else "non_dealer"),
        ("wall", lambda row: _wall_bucket(row.get("wall"))),
        ("tile_class", lambda row: row["labels"]["F8"].split(":", 1)[1]),
        ("claim_type", lambda row: str(row.get("claim_type"))),
    ):
        result["state"][name] = {
            "x": dict(sorted(collections.Counter(fn(row) for row in x_set).items())),
            "m": dict(sorted(collections.Counter(fn(row) for row in m_set).items())),
        }
    for family in ("F3", "G4", "G5"):
        mine = {row["labels"][family] for row in m_set}
        unmatched = [row for row in x_set if row["labels"][family] not in mine]
        result["match"][family] = {
            "unmatched": len(unmatched), "windows": len(x_set),
            "share": (len(unmatched) / len(x_set)) if x_set else None,
        }
    return result


def followup_summary(rows):
    """可选列汇总：跟打口径 margin 与动作层 margin 的分歧率与分歧窗特征。"""

    usable = [row for row in rows if row.get("followup")
              and row["followup"].get("available")]
    diverged = []
    for row in usable:
        column = row["followup"]
        delta = column.get("delta_margin")
        if column.get("claim_changed") or (delta is not None and abs(delta) > 1e-9):
            diverged.append(row)
    matched = [row for row in usable
               if row["followup"].get("pick_matches_parent") is not None]
    return {
        "windows": len(rows),
        "available": len(usable),
        "available_share": (len(usable) / len(rows)) if rows else None,
        "diverged": len(diverged),
        "diverged_share": (len(diverged) / len(usable)) if usable else None,
        "claim_changed": sum(1 for row in usable if row["followup"]["claim_changed"]),
        "delta_over_0_5": sum(1 for row in usable
                              if abs(row["followup"].get("delta_margin") or 0.0) > 0.5),
        "delta_over_5": sum(1 for row in usable
                            if abs(row["followup"].get("delta_margin") or 0.0) > 5.0),
        "parent_pick_agrees": (
            (sum(1 for row in matched if row["followup"]["pick_matches_parent"])
             / len(matched)) if matched else None),
        "parent_pick_known": len(matched),
        "diverged_cells": dict(sorted(collections.Counter(
            row["labels"]["F3"] for row in diverged).items())),
        "bt_action_true": sum(1 for row in usable
                              if row["followup"].get("bt_action") is True),
        "bt_followup_true": sum(1 for row in usable
                                if row["followup"].get("followup_baotou") is True),
    }


def fmt(value, digits=3, signed=False):
    if value is None:
        return "n/a"
    return ("%+.*f" if signed else "%.*f") % (digits, value)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def build_rows(games, board, primary_index, p6_index, parent, audit, identities,
               do_followup=True):
    rows = []
    rounds_done = 0
    for game in games:
        document = game["doc"]
        seats_meta = document.get("seats") or []
        room = document.get("room_id") or game["session"]
        users = [item.get("user_id") for item in seats_meta]
        groups = []
        for index in range(4):
            user = users[index] if index < len(users) else None
            groups.append("me" if user == ME else ("elite" if user in board else "other"))
        if "me" not in groups and "elite" not in groups:
            continue
        block_meta = round_metadata(document)
        table = [0, 0, 0, 0]
        game_id = document.get("game_id") or game["game_id"]
        for round_no, events, start_hands in AL.round_blocks(document):
            if not start_hands or not all(isinstance(hand, list) for hand in start_hands):
                continue
            ended_dealer, ended_scores = round_end_facts(events)
            dealer = (block_meta.get(round_no) or {}).get("dealer")
            if dealer is None:
                dealer = ended_dealer
            if dealer is None:
                dealer = next((index for index, hand in enumerate(start_hands)
                               if len(hand) == 14), None)
            if dealer is None:
                audit["round_without_dealer"] += 1
                continue
            snaps = reconstruct(events, start_hands, table, dealer)
            rounds_done += 1
            # 主语料口径与 C27 逐字一致：rounds.jsonl 登记过**且该局含强手座**
            primary = (game_id, round_no) in primary_index and "elite" in groups
            for seq in sorted(snaps):
                snap = snaps[seq]
                if snap["tile"] == WEALTH:
                    audit["white_discard_no_window"] += 1
                    continue
                discarder = snap["discarder"]
                peng = _peng_members(discarder, snap["tile"], snap["owner"])
                chi = _chi_members(discarder, snap["tile"], snap["owner"])
                for seat in range(4):
                    if seat == discarder or groups[seat] not in GROUPS:
                        continue
                    phases = []
                    if seat in peng:
                        phases.append("response_peng")
                    if seat in chi:
                        phases.append("response_chi")
                    if not phases:
                        continue
                    audit["seat_discard_windows"] += 1
                    window, _per_phase, window_audit = evaluate_window(
                        snap, seat, phases, game_id, round_no, parent)
                    audit.update(window_audit)
                    if window is None:
                        audit["not_opportunity"] += 1
                        continue
                    feature = parent_space_feature(window)
                    labels = C27.cells(feature)
                    claim_key = window["claim"]["action_key"]
                    actual = snap["claim_kind"] if snap["claim_seat"] == seat else None
                    claimed = 1 if actual in ("peng", "chi", "gang") else 0
                    cached = p6_index.get((game_id, round_no, seq))
                    same_phase = [item for item in (cached or [])
                                  if item["phase"] == window["phase"]]
                    run_entry = (cached or [None])[0]
                    identity = (identities.get((run_entry["room"], run_entry["run"]))
                                if run_entry else None)
                    responses = [item for item in snap["responses"] if item[0] == seat]
                    response_kinds = sorted({item[1] for item in responses})
                    response_windows = sorted({str(item[2]) for item in responses})
                    gorilla = do_followup and window["claim"]["action_type"] != "gang"
                    followup = None
                    if gorilla:
                        followup = followup_column(window, claim_key)
                    visible = window["visible"]
                    hu_keys = [item["action_key"] for item in window["view"]["actions"]
                               if item["action_type"] == "hu"]
                    gang_better = None
                    for item in window["view"]["actions"]:
                        if item["action_type"] != "gang":
                            continue
                        value = (window["scores"] or {}).get(item["action_key"])
                        if value is None:
                            continue
                        if gang_better is None or value > gang_better:
                            gang_better = value
                    gang_beats_claim = (None if gang_better is None
                                        else bool(gang_better > window["claim_score"]))
                    rows.append({
                        "game_id": game_id, "round_no": round_no, "room": room,
                        "primary": primary, "seat": seat, "group": groups[seat],
                        "seq": seq, "discarder": discarder, "tile": snap["tile"],
                        "phase": window["phase"], "phases": phases,
                        "margin": window["margin"],
                        "pass_score": window["pass_score"],
                        "claim_score": window["claim_score"],
                        "claim_key": claim_key,
                        "claim_type": window["claim"]["action_type"],
                        "has_peng": window["has_peng"], "has_chi": window["has_chi"],
                        "has_gang": window["has_gang"],
                        "actual": actual, "claimed": claimed,
                        "labels": labels, "feature": feature,
                        "melds": len(window["visible"]["melds"][seat]),
                        "bin": bin_label(window["margin"]),
                        "user_id": users[seat] if seat < len(users) else None,
                        "whites": visible["my_hand"].count(WEALTH),
                        "is_dealer": visible["dealer_seat"] == seat,
                        "wall": visible.get("remaining_tile_count"),
                        "pass_shanten": window["pass"].get("shanten_after"),
                        "turn": len(visible["discards"][seat]),
                        "degraded": bool(window.get("degraded")),
                        "issue_areas": list(window.get("issues") or ()),
                        "hu_keys": hu_keys,
                        "gang_beats_claim": gang_beats_claim,
                        "response_kinds": response_kinds,
                        "response_windows": response_windows,
                        "policy_identity": (
                            None if identity is None else
                            [identity["strategy"], identity["policy_version"],
                             (identity["candidate_source_sha256"] or "")[:12]]),
                        "followup": followup,
                        "frozen_run": cached is not None,
                        "other_claimed": (snap["claim_seat"] is not None
                                          and snap["claim_seat"] != seat),
                        "claim_in_prod": (
                            None if cached is None else
                            any(claim_key in item["plan_keys"] for item in cached)),
                        "prod_rank1": (
                            None if cached is None else
                            sorted({item["plan_rank1"] for item in cached})),
                        "prod_phases": (
                            None if cached is None else
                            sorted({item["phase"] for item in cached})),
                        "prod_phase_rank1": (
                            None if not same_phase else same_phase[0]["plan_rank1"]),
                        "prod_phase_has_claim": (
                            None if not same_phase else
                            any(claim_key in item["plan_keys"] for item in same_phase)),
                    })
            if ended_scores is not None:
                table = [a + b for a, b in zip(table, ended_scores)]
    return rows, rounds_done


def main():
    started = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    parent = load_parent()
    print("冻结父代装配完成：%s" % R18_INTEGRATED_POSITIVE_V2_SHA256[:16])

    board, board_path = C23.load_board()
    READ_PATHS.append(board_path)
    print("榜单快照 %s：top+prev %d 人" % (Path(board_path).name, len(board)))

    primary_rows = [json.loads(line) for line in ROUNDS_JSONL.open(encoding="utf-8")
                    if line.strip()]
    READ_PATHS.append(str(ROUNDS_JSONL))
    primary_index = {(row["game_id"], row["round_no"]) for row in primary_rows}
    print("主语料 rounds.jsonl：%d 局" % len(primary_rows))

    p6_index, p6_paths = load_p6_cache()
    print("生产候选表缓存：%d 个文件 / %d 个 (game,round,seq) 键"
          % (len(p6_paths), len(p6_index)))

    games = AL.load_games()
    READ_PATHS.extend(game["path"] for game in games)
    print("官方牌谱去重后 %d 场" % len(games))
    limit = int(os.environ.get("C31_GAME_LIMIT", "0") or 0)
    if limit:
        games = games[:limit]
        print("C31_GAME_LIMIT=%d：只跑前 %d 场（冒烟用，不用于结论）" % (limit, limit))

    audit = collections.Counter()
    do_followup = os.environ.get("C31_FOLLOWUP", "1") != "0"
    identities = run_identities()
    print("审计 run manifest 策略身份：%d 条" % len(identities))
    rows, rounds_done = build_rows(games, board, primary_index, p6_index, parent, audit,
                                   identities, do_followup=do_followup)
    print("重建 %d 局，机会窗 %d 个，用时 %.1f 秒"
          % (rounds_done, len(rows), time.time() - started))
    print("审计：%s" % json.dumps(dict(sorted(audit.items())), ensure_ascii=False))

    primary = [row for row in rows if row["primary"]]
    payload = {
        "audit": dict(audit), "rounds": rounds_done,
        "windows_all": len(rows), "windows_primary": len(primary),
        "selfcheck": {}, "table_a": {}, "table_b": {}, "table_c": {}, "third": {},
    }

    def usage(subset, group):
        picked = [row for row in subset if row["group"] == group]
        taken = sum(row["claimed"] for row in picked)
        return len(picked), taken, (taken / len(picked) if picked else None)

    checks = []
    me_chances, me_taken, me_usage = usage(primary, "me")
    el_chances, el_taken, el_usage = usage(primary, "elite")
    checks.append(("主语料机会数 me=5965", me_chances, 5965))
    checks.append(("主语料机会数 elite=10394", el_chances, 10394))
    checks.append(("主语料使用率 me=0.4801", me_usage, 0.4801))
    checks.append(("主语料使用率 elite=0.5790", el_usage, 0.5790))
    got = tuple(len(cell_index(primary, group, "F1:sh0")) for group in GROUPS)
    checks.append(("F1:sh0 机会数 me/elite=(1607,2906)", got, (1607, 2906)))
    pool = [row for row in primary if row["group"] in GROUPS]
    share_cells = {}
    for cell in ("F3:same", "F1:sh0"):
        share_cells[cell] = (len(cell_index(primary, "me", cell))
                             + len(cell_index(primary, "elite", cell))) / len(pool)
    checks.append(("F3:same 机会占比 0.528", share_cells["F3:same"], 0.528))
    checks.append(("F1:sh0 机会占比 0.276", share_cells["F1:sh0"], 0.276))
    print()
    print("== 自检（与 C23/C27 已发布读数对拍，主语料含强手的局）")
    selfcheck_ok = True
    for label, got, want in checks:
        if isinstance(want, tuple):
            passed = all(abs(a - b) <= max(20, 0.005 * b) for a, b in zip(got, want))
        elif want > 10:
            passed = abs(got - want) <= max(20, 0.005 * want)
        else:
            passed = abs(got - want) <= 0.005
        selfcheck_ok = selfcheck_ok and passed
        print("  %s %s：得到 %s，期望 %s" % ("通过" if passed else "**不符**", label, got, want))
    print("自检总体：%s" % ("通过" if selfcheck_ok else "**失败**"))
    payload["selfcheck"] = {
        "ok": selfcheck_ok,
        "rows": [{"label": label, "got": got, "want": want} for label, got, want in checks],
    }
    if not selfcheck_ok and not os.environ.get("C31_SKIP_SELFCHECK"):
        print("自检未通过：按 PREREG 第 2 节停止分析。")
        return 1

    print()
    print("== 表 A：标定曲线（按 margin 分箱的实际鸣牌率）")
    for title, subset in (("primary", primary), ("full", rows)):
        entry = table_a(subset, title)
        payload["table_a"][title] = entry
        print("  [%s]" % title)
        print("  | 箱 | 我方窗数 | 我方鸣牌率 | 强手窗数 | 强手鸣牌率 |")
        for item in entry["bins"]:
            print("  | %s | %d | %s | %d | %s |"
                  % (item["bin"], item["me"]["windows"], fmt(item["me"]["rate"]),
                     item["elite"]["windows"], fmt(item["elite"]["rate"])))

    print()
    print("== 表 B：缺口归属（我方未鸣窗按 margin 符号）")
    result = attribution(primary, C_STAR, "B1 primary F3:same ∪ F1:sh0")
    payload["table_b"]["B1"] = result
    print("  B1 primary 对照格 F3:same ∪ F1:sh0：未鸣窗 %d；margin<=0 %d（rho=%s）；"
          "margin>0 %d；判定 %s"
          % (result["windows"], result["weight_gap"], fmt(result["rho"]),
             result["fact_gap"], result["verdict"]))
    print("     事实缺口窗构成：phase %s；其中另一家先鸣走 %d；冻结 v2 战役 %d"
          % (result["fact_gap_by_phase"], result["fact_gap_other_claimed"],
             result["fact_gap_frozen"]))
    for tag, subset, name in (
            ("B2", primary, "B2 primary 全部机会窗"),
            ("B3", rows, "B3 全量语料全部机会窗"),
            ("B4", [row for row in rows if row["frozen_run"]], "B4 冻结 R18 v2 战役窗")):
        selected = [row for row in subset if row["group"] == "me" and not row["claimed"]]
        weight = [row for row in selected if row["margin"] <= 0.0]
        rho = (len(weight) / len(selected)) if selected else None
        verdict = ("n/a" if rho is None else
                   "权重缺口为主" if rho >= RHO_WEIGHT_DOMINANT else
                   "事实缺口为主" if rho <= RHO_FACT_DOMINANT else "灰区")
        payload["table_b"][tag] = {
            "name": name, "cells": None, "windows": len(selected),
            "weight_gap": len(weight), "fact_gap": len(selected) - len(weight),
            "rho": rho, "verdict": verdict}
        print("  %s：未鸣窗 %d；margin<=0 %d（rho=%s）；判定 %s"
              % (name, len(selected), len(weight), fmt(rho), verdict))

    print()
    print("== 表 C：格内隐含剂量 Δ（与 CELL-R6 的 +6 直接可比；描述性等效阈值，"
          "不是最优加分）")
    for cell in C_STAR:
        entry = table_c(primary, cell, "primary")
        payload["table_c"][cell] = entry
        print("  %s：我方 %d 窗（使用率 %s）｜强手 %d 窗（使用率 %s）｜Δ = %s [%s, %s]"
              "（%d 房）｜对照 Δ' = %s"
              % (cell, entry["me_windows"], fmt(entry["me_usage"]),
                 entry["elite_windows"], fmt(entry["elite_usage"]),
                 fmt(entry["delta"], 2, True), fmt(entry["delta_interval"]["lo"], 2, True),
                 fmt(entry["delta_interval"]["hi"], 2, True),
                 entry["delta_interval"]["rooms"], fmt(entry["delta_prime"], 2, True)))
        full = table_c(rows, cell, "full")
        payload["table_c"][cell + "@full"] = full
        print("     全量语料：Δ = %s [%s, %s]"
              % (fmt(full["delta"], 2, True), fmt(full["delta_interval"]["lo"], 2, True),
                 fmt(full["delta_interval"]["hi"], 2, True)))

    print()
    print("== 可选列：「鸣牌 + 最佳合法跟打」对「过牌」重算 margin")
    follow = followup_summary(rows)
    payload["followup"] = follow
    print("  可用窗 %d（占机会窗 %.3f）；与动作层 margin 分歧 %d（%.4f）"
          % (follow["available"], follow["available_share"], follow["diverged"],
             follow["diverged_share"]))
    print("  分歧构成：跟打口径改变首选鸣牌 %d；数值差 >0.5 %d；差 >5 %d"
          % (follow["claim_changed"], follow["delta_over_0_5"], follow["delta_over_5"]))
    print("  父代 best_followup_discard 与本次枚举最优跟打一致率 %s"
          % fmt(follow["parent_pick_agrees"]))
    print("  分歧窗的格分布（F3）%s" % follow["diverged_cells"])
    print("  爆头口径差：动作层 baotou_after=true 而跟打后 true 的窗 %s / 跟打后为 true 的窗 %s"
          % (follow["bt_action_true"], follow["bt_followup_true"]))

    print()
    print("== 第三类：margin > 0 且我方实际没过（评审口径分桶）")
    third = third_category(rows)
    payload["third"] = third
    print("  窗数 %d" % third["windows"])
    for name, value in sorted(third["conditions"].items()):
        print("    条件 %-34s %d" % (name, value))
    for name, value in sorted(third["buckets"].items(), key=lambda item: -item[1]):
        print("    归因 %-52s %d" % (name, value))
    for item in third["examples"]:
        print("    事实缺口候选样例：%s r%s seq%s %s margin=%s phase=%s"
              % (item[0], item[1], item[2], item[3], fmt(item[4], 2, True), item[5]))

    print()
    print("== 玄武对照：玄武实际鸣了、冻结父代在其本人观察上也会过（margin<=0）")
    xuanwu = xuanwu_comparison(rows, XUANWU_ID, "u_380da525337c（玄武-2346）")
    payload["xuanwu"] = xuanwu
    print("  玄武此类窗 %d（%d 房 / %d 局）；我方机会窗 %d（其中未鸣且 margin<=0 %d）"
          % (xuanwu["x_windows"], xuanwu["x_rooms"], xuanwu["x_rounds"],
             xuanwu["m_windows"], xuanwu["m_noclaim_windows"]))
    for family in STATE_FAMILIES:
        cells = xuanwu["cells"][family]
        keys = sorted(set(cells["x"]) | set(cells["m"]),
                      key=lambda key: -cells["x"].get(key, 0))
        print("  [%s] 格 | 玄武窗 | 我方窗" % family)
        for key in keys[:8]:
            print("    | %-16s | %d | %d" % (key, cells["x"].get(key, 0),
                                             cells["m"].get(key, 0)))
    for name, entry in xuanwu["state"].items():
        print("  状态 %-12s 玄武 %s" % (name, entry["x"]))
        print("  状态 %-12s 我方 %s" % (name, entry["m"]))
    for family, entry in xuanwu["match"].items():
        print("  无法匹配（我方在同格无窗）按 %s：%d/%d = %s"
              % (family, entry["unmatched"], entry["windows"], fmt(entry["share"])))

    payload["elapsed_sec"] = time.time() - started
    (_project_file(_PROJECT_ROOT, OUT / "summary.json")).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    with gzip.open(_project_file(_PROJECT_ROOT, OUT / "windows.jsonl.gz"), "wt", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + chr(10))
    print()
    print("结果写入 %s 与 %s" % (_project_file(_PROJECT_ROOT, OUT / "summary.json"), _project_file(_PROJECT_ROOT, OUT / "windows.jsonl.gz")))
    print("总用时 %.1f 秒" % (time.time() - started))

    bad = [path for path in READ_PATHS
           if "events.json" not in path and "leaderboard-week.json" not in path
           and "rounds.jsonl" not in path and ".jsonl.gz" not in path
           and "manifest.json" not in path]
    print("泄漏检查：读取路径 %d 条，非官方牌谱/公开榜单/既有重建产物/生产缓存/运行清单者"
          " %d 条 -> %s" % (len(READ_PATHS), len(bad), "通过" if not bad else "**失败**"))
    assert not bad, bad
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
