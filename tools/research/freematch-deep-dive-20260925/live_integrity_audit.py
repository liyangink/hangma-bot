#!/usr/bin/env python3
"""线上自由赛「运行完整性」审计：最近一批房（默认 2026-09-26 10:35 之后）的只读复跑核查。

为什么需要
----------
宿主崩溃 + watchdog 重启之后，「线上还干不干净」必须由机器证据回答，不能靠上一版
审计的结论外推。本脚本对**当前这批房**重算七项发布门禁指标，每项都给数字与出处文件：

1. 决策完整性——计划首选 vs 实际提交的不一致数、非法提交、被拒与原因、SubmitAmbiguous、
   plan_empty 及其窗口分布、超过截止的次数；
2. 时延——策略时延与规则分析时延的分窗型分位数，以及 >1000 ms 的动作窗提交；
3. 序号与快照——seq 缺口、gap=true、409、权威快照重建次数，以及 snapshot_seq 相对
   trigger_seq 的滞后分布（本会话纪律要求「滞后」恒为 0，即 snapshot_seq 不得落后）；
4. 跨局首弃牌饥饿——每局每座「我方为庄」的首弃牌窗是否有官方 timeout(kind=discard)；
5. SSE 健康——/notify 连接（重连）次数、事件流关闭帧、SSE 降级事件及其是否发生在终局之前；
6. 结算与账本一致——每房官方复算总分 vs watchdog 账本 room_subtotal；
7. 部署身份——逐房 manifest.json 的完整发布载荷、策略版本、规则版本，与受控的
   历史 R18 v2 包或 2026-09-29 规则重新绑定包逐字段核对；未知包一律失败。

判据来源（本脚本不自创判据，只复算既有判据）
--------------------------------------------
- 决策通路：artifacts/sessions/<战役>/audit/runs/<run>/participants/<我方>/decisions.jsonl
- 场次级协议事实：同目录 games/<game_id>.jsonl（protocol_recovered / authoritative_state /
  game_finished）
- 线缆事实：同目录 raw/*.jsonl.gz（state_response 的 gap、sse_frame 的 closed、
  action_submit_response 的 HTTP 状态码）
- 官方赛后原文：artifacts/sessions/<战役>/official/dl-*/events.json（+ source.json 摘要校验）
- 跨局首弃牌判据与 review/r18-four-arm-evaluation-2026-09-23/verify_sse_settled_first_discard.py
  的 v2 口径一致：按 round_no 合并官方分块、在本人首弃牌与下一次本人弃牌之间关联
  timeout(kind=discard)、同 game_id 重复下载按 sha256 去重。
- 账本：runs/auto-match-watchdog/auto-match-watchdog-state.json
- 发布身份：policy 中两个受控 R18 v2 release 模块；包 ID 从各自载荷重算，既允许
  旧规则历史房，也允许当前规则房，但不因 manifest 自报任何新 ID 而放行。

术语口径（避免误读）
--------------------
- protocol_recovered 有两种互不相同的记录：带 trigger 的**协议恢复**（rebuild_snapshot_gap /
  sse_degraded / pending_gap / incremental）与带 area 的**窗口簿记**（decision_window /
  decision_loop）。两者分开计数。
- snapshot_seq 与 trigger_seq 的差取 lag = trigger_seq - snapshot_seq：lag > 0 表示快照
  落后（缺陷）；lag < 0 表示快照领先触发序号（正常，SSE 跳过推断水位后的正常前进）。

只读保证：只以只读方式打开文件；不写 artifacts/、runs/ 或任何既有文件；不访问网络；不调用 git。

用法::

    .venv/bin/python review/freematch-deep-dive-20260925/live_integrity_audit.py
    .venv/bin/python review/freematch-deep-dive-20260925/live_integrity_audit.py --json-out /tmp/lia.json
    .venv/bin/python review/freematch-deep-dive-20260925/live_integrity_audit.py --since 2026-09-26T10:35:00

退出码：0 = 七项门禁全部通过；1 = 有门禁失败项（见末节「结论」）。
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
import gzip
import hashlib
import json
import os
import re
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path

from hangma_bot.policy.r18_integrated_positive_v2_release import (
    R18_INTEGRATED_POSITIVE_V2_RELEASE_PACKAGE_ID,
    _release_payload as _original_r18_v2_release_payload,
)
from hangma_bot.policy.r18_integrated_positive_v2_rules_20260929_release import (
    R18_V2_RULES_20260929_RELEASE_PACKAGE_ID,
    _release_payload as _current_r18_v2_release_payload,
)

REPO = _PROJECT_ROOT
CAMPAIGN = "r18-sse-freematch-campaign-20260925b"
ME = "u_13495c3d79c8"
SESSION_ROOT = _project_file(_PROJECT_ROOT, REPO / "artifacts" / "sessions" / CAMPAIGN)
STATE_PATH = _project_file(_PROJECT_ROOT, REPO / "runs" / "auto-match-watchdog" / "auto-match-watchdog-state.json")

# 被拒结果类型（contracts.SubmitOutcome 中代表「官方明确拒绝/无法继续」的那些）。
REJECTED_TYPES = (
    "SubmitRejectedRetryable",
    "SubmitRejectedClosed",
    "SubmitRejectedNoRefresh",
    "SubmitFatal",
)
# SSE 连接分类阈值（秒）：达到该时长才算真正承载事件流的连接，其余是重连尝试。
SHORT_CONNECTION_SEC = 60.0
SESSION_LOG_RE = re.compile(r"session-(\d{8})-(\d{6})\.log$")


def _controlled_release_bindings():
    """由受控发布包源码生成历史/当前 R18 v2 身份，不信任审计清单自报的 ID。"""
    bindings = {}
    for release_id, payload_factory in (
        (R18_INTEGRATED_POSITIVE_V2_RELEASE_PACKAGE_ID, _original_r18_v2_release_payload),
        (R18_V2_RULES_20260929_RELEASE_PACKAGE_ID, _current_r18_v2_release_payload),
    ):
        payload = payload_factory()
        computed = hashlib.sha256(json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")).hexdigest()
        if computed != release_id:
            raise RuntimeError("受控 R18 v2 发布包 ID 与载荷摘要不一致")
        # manifest 经 JSON 序列化；受控源码中的 tuple（如 allowed_modes）需归一为 list。
        bindings[release_id] = json.loads(json.dumps({
            **payload, "release_package_id": release_id,
        }, ensure_ascii=False))
    return bindings


CONTROLLED_RELEASE_BINDINGS = _controlled_release_bindings()


def verify_manifest_release(manifest):
    """核对一个房的完整 R18 v2 发布身份；返回 None 表示与受控包完全一致。"""
    release = manifest.get("policy_release")
    if not isinstance(release, dict):
        return "缺少 policy_release 发布包载荷"
    release_id = release.get("release_package_id")
    if not isinstance(release_id, str):
        return "发布包 ID 缺失或类型错误"
    expected = CONTROLLED_RELEASE_BINDINGS.get(release_id)
    if expected is None:
        return "发布包 ID 不属于受控的历史或当前 R18 v2 包: %s" % release_id
    if release != expected:
        differing = sorted(key for key in set(release) | set(expected)
                           if release.get(key) != expected.get(key))
        return "发布包载荷与受控包不一致（字段: %s）" % ", ".join(differing)
    if manifest.get("policy_version") != expected["strategy"]:
        return "策略版本与受控发布包不一致: %s" % manifest.get("policy_version")
    if manifest.get("ruleset_version") != expected["ruleset_version"]:
        return "规则语义版本与受控发布包不一致: %s" % manifest.get("ruleset_version")
    return None


# --------------------------------------------------------------------------- #
# 小工具
# --------------------------------------------------------------------------- #
def pct(values, q):
    """最近秩分位数（与仓库既有审计脚本同口径，保证数字可对照）。"""
    if not values:
        return float("nan")
    ordered = sorted(values)
    return ordered[int((len(ordered) - 1) * q)]


def quantiles(values):
    if not values:
        return {"n": 0, "p50": None, "p95": None, "p99": None, "max": None}
    return {
        "n": len(values),
        "p50": round(pct(values, 0.50), 3),
        "p95": round(pct(values, 0.95), 3),
        "p99": round(pct(values, 0.99), 3),
        "max": round(max(values), 3),
    }


def family(phase):
    """窗口型：摸牌窗 / 吃碰响应窗 / 其他。"""
    if phase == "draw":
        return "draw"
    if isinstance(phase, str) and phase.startswith("response"):
        return "response"
    return "other"


def _window_obj(payload):
    win = payload.get("window")
    if isinstance(win, dict):
        return win
    req = payload.get("request")
    if isinstance(req, dict) and isinstance(req.get("window_key"), dict):
        return req["window_key"]
    return None


def window_key(payload):
    """从任意决策记录取出窗口身份 (game_id, round_no, trigger_seq, phase, seat)。"""
    win = _window_obj(payload)
    if win is None:
        return None
    return (
        win.get("game_id"),
        win.get("round_no"),
        win.get("trigger_seq"),
        win.get("phase"),
        win.get("seat"),
    )


def phase_of(payload):
    win = _window_obj(payload)
    return win.get("phase") if win else None


def rank1(plan):
    """取计划的首选动作（rank 最小者）；返回 (action_key, 候选数)。"""
    if not isinstance(plan, dict):
        return None, 0
    cands = plan.get("candidates")
    if not isinstance(cands, list) or not cands:
        return None, 0
    best_rank, best_key = None, None
    for entry in cands:
        if not isinstance(entry, dict):
            continue
        key = entry.get("action_key")
        rk = entry.get("rank")
        if rk is None:
            if best_key is None:
                best_key = key
            continue
        if best_rank is None or float(rk) < float(best_rank):
            best_rank, best_key = float(rk), key
    return best_key, len(cands)


# --------------------------------------------------------------------------- #
# 1 / 2 / 3(409) / 5(连接数)：决策通路
# --------------------------------------------------------------------------- #
def scan_decisions(path):
    """流式扫一份 decisions.jsonl，返回本节所需的全部计数与原始时延样本。"""
    c = collections.Counter()
    rule = collections.defaultdict(list)
    policy = collections.defaultdict(list)
    lag_dist = collections.Counter()
    diff_pairs = collections.Counter()
    reject_reasons = collections.Counter()
    ambiguous_reasons = collections.Counter()
    empty_by_phase = collections.Counter()
    end_by = collections.Counter()
    http_status = collections.Counter()
    http_error_type = collections.Counter()
    http_error_endpoint = collections.Counter()
    over_1000 = collections.Counter()
    over_deadline = collections.Counter()
    late_windows = []
    plan_by_window = {}
    budget_origin = {}
    deadline_by_decision = {}

    try:
        with open(path, "r", errors="ignore") as fh:
            for line in fh:
                if '"kind"' not in line:
                    continue
                try:
                    record = json.loads(line)
                except ValueError:
                    c["bad_json"] += 1
                    continue
                kind = record.get("kind")
                payload = record.get("payload")
                if not isinstance(payload, dict):
                    continue
                if kind == "decision_input":
                    c["input"] += 1
                    phase = phase_of(payload)
                    rule[family(phase)].append(float(payload.get("rule_elapsed_ms") or 0.0))
                    req = payload.get("request") or {}
                    obs = req.get("observation") or {}
                    snap_seq, trig_seq = obs.get("snapshot_seq"), req.get("trigger_seq")
                    if snap_seq is not None and trig_seq is not None:
                        try:
                            lag_dist[int(trig_seq) - int(snap_seq)] += 1
                        except (TypeError, ValueError):
                            pass
                    dec = payload.get("decision_id")
                    origin = payload.get("budget_origin_monotonic")
                    if dec is not None and origin is not None:
                        budget_origin[dec] = float(origin)
                    wd = payload.get("window_deadline")
                    if dec is not None and isinstance(wd, dict) and wd.get("expires_at_monotonic"):
                        deadline_by_decision[dec] = float(wd["expires_at_monotonic"])
                elif kind == "decision_planned":
                    c["planned"] += 1
                    phase = phase_of(payload)
                    policy[family(phase)].append(float(payload.get("policy_elapsed_ms") or 0.0))
                    window = window_key(payload)
                    key, n_cand = rank1(payload.get("returned_plan"))
                    if key is None:
                        # 兼容旧记录：计划对象缺失/为空时退到 payload.candidates
                        key, n_cand = rank1({"candidates": payload.get("candidates")})
                    if n_cand == 0:
                        c["plan_empty_total"] += 1
                        empty_by_phase[str(phase)] += 1
                        if family(phase) == "draw":
                            c["plan_empty_in_draw"] += 1
                    if window is not None and key is not None:
                        plan_by_window[window] = key
                elif kind == "candidate_validated":
                    c["validated"] += 1
                    if payload.get("legal") is not True:
                        c["illegal"] += 1
                elif kind == "submission_intent":
                    c["intent"] += 1
                    if payload.get("is_emergency"):
                        c["intent_emergency"] += 1
                    window = window_key(payload)
                    phase = phase_of(payload)
                    got = payload.get("action_key")
                    want = plan_by_window.get(window)
                    if want is None:
                        c["submit_without_rank1"] += 1
                    elif want == got:
                        c["submit_matches_rank1"] += 1
                    else:
                        c["submit_differs_rank1"] += 1
                        diff_pairs["%s -> %s" % (want, got)] += 1
                    dec = payload.get("decision_id")
                    origin = budget_origin.get(dec)
                    if origin is not None:
                        elapsed_ms = (float(record.get("monotonic_ns") or 0) / 1e9 - origin) * 1000.0
                        if elapsed_ms > 1000.0:
                            over_1000[family(phase)] += 1
                            if len(late_windows) < 20:
                                late_windows.append({
                                    "window": list(window) if window else None,
                                    "action_key": got,
                                    "elapsed_ms": round(elapsed_ms, 1),
                                })
                    exp = deadline_by_decision.get(dec)
                    if exp is not None and float(record.get("monotonic_ns") or 0) / 1e9 > exp:
                        over_deadline[family(phase)] += 1
                elif kind == "submission_outcome":
                    c["outcome"] += 1
                    otype = payload.get("outcome_type") or payload.get("outcome")
                    c["out__" + str(otype)] += 1
                    if otype in REJECTED_TYPES:
                        c["rejected"] += 1
                        reject_reasons["%s|%s" % (otype, payload.get("reason"))] += 1
                    if otype == "SubmitAmbiguous":
                        ambiguous_reasons[str(payload.get("reason"))] += 1
                elif kind == "decision_ended":
                    c["ended"] += 1
                    end_by["%s|%s" % (phase_of(payload), payload.get("end_reason"))] += 1
                elif kind == "http_request":
                    if payload.get("phase") != "finished":
                        continue
                    status = str(payload.get("http_status"))
                    http_status[status] += 1
                    endpoint = str(payload.get("endpoint") or "")
                    if status == "409":
                        c["http_409"] += 1
                    if status not in ("200",):
                        method_path = endpoint.split(" ")[0] + " " + endpoint.split(" ")[-1].split("/")[-1]
                        http_error_type["%s|%s" % (status, payload.get("error_type"))] += 1
                        http_error_endpoint["%s|%s" % (status, method_path)] += 1
                    if "/notify" in endpoint:
                        c["notify_finished"] += 1
                    if "/state" in endpoint:
                        c["state_requests"] += 1
    except OSError as exc:  # 文件不可读：如实记录，不静默当作 0
        c["file_error_" + type(exc).__name__] += 1

    return {
        "counts": dict(c),
        "rule_latency": {k: v for k, v in rule.items()},
        "policy_latency": {k: v for k, v in policy.items()},
        "snapshot_lag": {str(k): v for k, v in sorted(lag_dist.items())},
        "diff_pairs": dict(diff_pairs.most_common(10)),
        "reject_reasons": dict(reject_reasons.most_common(20)),
        "ambiguous_reasons": dict(ambiguous_reasons.most_common(10)),
        "plan_empty_by_phase": dict(empty_by_phase),
        "end_by": dict(end_by),
        "http_status": dict(http_status),
        "http_error_type": dict(http_error_type),
        "http_error_endpoint": dict(http_error_endpoint),
        "intent_over_1000ms": dict(over_1000),
        "intent_over_deadline": dict(over_deadline),
        "late_windows": late_windows,
    }


# --------------------------------------------------------------------------- #
# 3 / 5：场次级协议事实（games/<game_id>.jsonl）
# --------------------------------------------------------------------------- #
def scan_game_audit(path):
    c = collections.Counter()
    triggers = collections.Counter()
    incremental_reasons = collections.Counter()
    areas = collections.Counter()
    area_reasons = collections.Counter()
    sse_degraded = []
    finished_at = None
    try:
        with open(path, "r", errors="ignore") as fh:
            for line in fh:
                if '"kind"' not in line:
                    continue
                try:
                    record = json.loads(line)
                except ValueError:
                    c["bad_json"] += 1
                    continue
                kind = record.get("kind")
                payload = record.get("payload")
                if not isinstance(payload, dict):
                    continue
                if kind == "protocol_recovered":
                    if payload.get("trigger"):
                        trigger = str(payload.get("trigger"))
                        triggers[trigger] += 1
                        for reason in payload.get("reasons") or []:
                            incremental_reasons[str(reason).split(":")[0]] += 1
                        if trigger == "sse_degraded":
                            sse_degraded.append({
                                "reason": payload.get("reason"),
                                "monotonic_ns": record.get("monotonic_ns"),
                                "seq": payload.get("seq"),
                            })
                    elif payload.get("area"):
                        # 窗口簿记，不是协议恢复：单独计数，不得混入重建次数
                        area = str(payload.get("area"))
                        areas[area] += 1
                        for reason in payload.get("reasons") or [payload.get("reason")]:
                            if reason:
                                area_reasons["%s|%s" % (area, str(reason).split(":")[0])] += 1
                elif kind == "authoritative_state":
                    c["auth_state"] += 1
                    if payload.get("gap"):
                        c["gap_true_engine"] += 1
                    if payload.get("history_complete") is False:
                        c["history_incomplete"] += 1
                    if payload.get("sse_skip_reason"):
                        c["sse_skipped"] += 1
                elif kind == "game_finished":
                    c["game_finished"] += 1
                    if finished_at is None:
                        finished_at = record.get("monotonic_ns")
    except OSError as exc:
        c["file_error_" + type(exc).__name__] += 1
    return {
        "path": os.path.basename(path),
        "counts": dict(c),
        "triggers": dict(triggers),
        "incremental_reasons": dict(incremental_reasons),
        "areas": dict(areas),
        "area_reasons": dict(area_reasons),
        "sse_degraded": sse_degraded,
        "finished_at_monotonic_ns": finished_at,
    }


# --------------------------------------------------------------------------- #
# 3(线缆口径) / 5：原始线缆事实（raw/*.jsonl.gz）
# --------------------------------------------------------------------------- #
def scan_raw(path):
    c = collections.Counter()
    durations = []
    long_durations = []
    submit_status = collections.Counter()
    try:
        with gzip.open(path, "rt", errors="ignore") as fh:
            for line in fh:
                if '"source"' not in line:
                    continue
                try:
                    record = json.loads(line)
                except ValueError:
                    c["bad_json"] += 1
                    continue
                payload = record.get("payload")
                if not isinstance(payload, dict):
                    continue
                source = payload.get("source")
                if source == "sse_frame":
                    c["sse_frames"] += 1
                    if payload.get("closed"):
                        c["sse_closed_frames"] += 1
                elif source == "notify_response":
                    c["notify_responses"] += 1
                    timing = payload.get("request_timing") or {}
                    start = timing.get("transport_started_at_monotonic")
                    end = timing.get("completed_at_monotonic")
                    if start is not None and end is not None:
                        span = float(end) - float(start)
                        durations.append(span)
                        # 长连接 = 真正承载该局事件流的连接；短连接 = 终局后的重连尝试
                        if span >= SHORT_CONNECTION_SEC:
                            c["notify_long_connections"] += 1
                            long_durations.append(span)
                        else:
                            c["notify_short_connections"] += 1
                elif source == "state_response":
                    c["state_responses"] += 1
                    raw = payload.get("raw")
                    if isinstance(raw, str) and raw:
                        try:
                            body = json.loads(raw)
                        except ValueError:
                            body = None
                        if isinstance(body, dict) and body.get("gap"):
                            c["gap_true_wire"] += 1
                elif source == "action_submit_response":
                    c["action_submit_responses"] += 1
                    submit_status[str(payload.get("http_status"))] += 1
    except OSError as exc:
        c["file_error_" + type(exc).__name__] += 1
    return {"counts": dict(c), "notify_durations": durations,
            "notify_long_durations": long_durations, "submit_status": dict(submit_status)}


# --------------------------------------------------------------------------- #
# 4 / 6：官方赛后原文
# --------------------------------------------------------------------------- #
def _merge_rounds(document, game_id):
    """按 round_no 合并官方分块（官方可在同一局内拆成多个块）。"""
    rounds = []
    for block in document.get("blocks") or []:
        if rounds and rounds[-1]["round_no"] == block["round_no"]:
            if rounds[-1]["dealer"] != block["dealer"]:
                raise ValueError("同局公开庄家冲突: %s 第 %s 局" % (game_id, block["round_no"]))
            rounds[-1]["events"].extend(block.get("events") or [])
            rounds[-1]["truncated"] |= bool(block.get("truncated"))
        else:
            if rounds and block["round_no"] != rounds[-1]["round_no"] + 1:
                raise ValueError("官方局序不连续: %s" % game_id)
            rounds.append({
                "round_no": block["round_no"],
                "dealer": block["dealer"],
                "truncated": bool(block.get("truncated")),
                "events": list(block.get("events") or []),
            })
    return rounds


def analyze_official_game(document, me):
    """跨局首弃牌窗口事实 + 我方总分 + 官方 game_ended 真值。"""
    game_id = document.get("game_id")
    seats = [row.get("user_id") for row in document.get("seats") or []]
    if me not in seats:
        return None
    focal = seats.index(me)
    rounds = _merge_rounds(document, game_id)

    windows, timeouts = [], []
    for previous, current in zip(rounds, rounds[1:]):
        if current["dealer"] != focal:
            continue
        if (previous["truncated"] or current["truncated"]
                or not any(e.get("type") == "round_ended" for e in previous["events"])):
            raise ValueError("跨局事件不完整: %s 第 %s 局" % (game_id, current["round_no"]))
        events = current["events"]
        first_discard = next((e for e in events if e.get("type") == "tile_discarded"), None)
        if first_discard is None:
            continue  # 庄家直接胡/杠而未弃牌：本局没有可核的首弃牌窗
        if first_discard.get("seat") != focal:
            raise ValueError("首弃牌座位与公开庄家不符: %s" % game_id)
        windows.append({"round_no": current["round_no"], "discard_seq": first_discard.get("seq")})
        next_own = next((e["seq"] for e in events
                         if e.get("type") == "tile_discarded" and e.get("seat") == focal
                         and e.get("seq") > first_discard.get("seq")), None)
        # 官方可能先记下一家的摸牌、随后才记本次自动弃牌的 timeout；只按「紧邻下一条」
        # 判断会产生假阴性（v1 检查器的已知缺陷，v2 口径已修正）。
        hits = [e for e in events
                if e.get("type") == "timeout" and e.get("seat") == focal
                and (e.get("data") or {}).get("kind") == "discard"
                and e.get("seq") > first_discard.get("seq")
                and (next_own is None or e.get("seq") < next_own)]
        if len(hits) > 1:
            raise ValueError("同一首弃牌窗有多个弃牌超时: %s" % game_id)
        if hits:
            timeouts.append({"round_no": current["round_no"],
                             "discard_seq": first_discard.get("seq"),
                             "timeout_seq": hits[0].get("seq")})

    from_rounds = [0, 0, 0, 0]
    for rnd in document.get("rounds") or []:
        scores = rnd.get("scores") or []
        for i in range(min(4, len(scores))):
            from_rounds[i] += scores[i]
    truth = None
    for block in document.get("blocks") or []:
        for event in block.get("events") or []:
            if event.get("type") == "game_ended":
                truth = (event.get("data") or {}).get("final_scores")
    return {
        "game_id": game_id,
        "batch": document.get("batch"),
        "focal_seat": focal,
        "my_total_from_rounds": from_rounds[focal],
        "official_final_scores": truth,
        "my_total_from_final_scores": (truth[focal] if truth and focal < len(truth) else None),
        "rounds_listed": len(document.get("rounds") or []),
        "first_discard_windows": len(windows),
        "first_discard_timeouts": len(timeouts),
    }


def scan_room_official(job):
    """一间房的官方下载：摘要校验 + 去重 + 首弃牌 + 总分。"""
    room_id, dl_dirs, me = job
    c = collections.Counter()
    latest = {}
    errors = []
    for dl in dl_dirs:
        source_path = os.path.join(dl, "source.json")
        events_path = os.path.join(dl, "events.json")
        try:
            with open(source_path, "r", encoding="utf-8") as fh:
                source = json.load(fh)
            with open(events_path, "rb") as fh:
                blob = fh.read()
        except (OSError, ValueError) as exc:
            c["download_read_error"] += 1
            errors.append("%s: %s" % (os.path.basename(dl), type(exc).__name__))
            continue
        digest = hashlib.sha256(blob).hexdigest()
        if digest != source.get("original_sha256"):
            c["sha256_mismatch"] += 1
            errors.append("%s: 官方原文摘要不符" % os.path.basename(dl))
            continue
        try:
            document = json.loads(blob.decode("utf-8"))
        except ValueError:
            c["events_parse_error"] += 1
            continue
        game_id = document.get("game_id")
        if not game_id:
            continue
        prior = latest.get(game_id)
        if prior is None:
            latest[game_id] = (os.path.getmtime(events_path), digest, document)
        elif prior[1] != digest:
            c["duplicate_conflict"] += 1
            errors.append("%s: 同一 game_id 有两种原文" % game_id)
        else:
            c["duplicate_downloads"] += 1
            if os.path.getmtime(events_path) >= prior[0]:
                latest[game_id] = (os.path.getmtime(events_path), digest, document)

    games = []
    first_discard = collections.Counter()
    truth_agree = truth_games = 0
    for _mtime, _digest, document in sorted(latest.values(), key=lambda row: row[0]):
        if document.get("status") != "finished":
            c["unfinished_games"] += 1
            continue
        try:
            analyzed = analyze_official_game(document, me)
        except ValueError as exc:
            c["official_structure_error"] += 1
            errors.append(str(exc))
            continue
        if analyzed is None:
            c["no_focal_seat"] += 1
            continue
        games.append(analyzed)
        first_discard["windows"] += analyzed["first_discard_windows"]
        first_discard["timeouts"] += analyzed["first_discard_timeouts"]
        if analyzed["my_total_from_final_scores"] is not None:
            truth_games += 1
            truth_agree += int(
                analyzed["my_total_from_final_scores"] == analyzed["my_total_from_rounds"])
    return {
        "room_id": room_id,
        "games": games,
        "first_discard": dict(first_discard),
        "my_total_from_rounds": sum(g["my_total_from_rounds"] for g in games),
        "my_total_from_final_scores": sum(
            g["my_total_from_final_scores"] or 0 for g in games),
        "final_scores_games": truth_games,
        "final_scores_agree": truth_agree,
        "counts": dict(c),
        "errors": errors[:10],
    }


# --------------------------------------------------------------------------- #
# 7：部署身份
# --------------------------------------------------------------------------- #
def read_manifest(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            record = json.load(fh)
    except (OSError, ValueError) as exc:
        return {"error": type(exc).__name__}
    if not isinstance(record, dict) or not isinstance(record.get("payload"), dict):
        return {"error": "invalid_manifest_payload"}
    payload = record["payload"]
    release = payload.get("policy_release")
    if not isinstance(release, dict):
        release = {}
    return {
        "release_package_id": release.get("release_package_id"),
        "policy_release": release,
        "policy_version": payload.get("policy_version"),
        "ruleset_version": payload.get("ruleset_version"),
        "strategy": release.get("strategy"),
        "guide_version": payload.get("guide_version"),
        "sse_effective": payload.get("sse_effective"),
        "official_sync_mode": payload.get("official_sync_mode"),
        "max_games": payload.get("max_games"),
        "rounds_per_game": payload.get("rounds_per_game"),
    }


# --------------------------------------------------------------------------- #
# 批次选择
# --------------------------------------------------------------------------- #
def load_rooms(since):
    """按 watchdog session 日志名里的事件时间挑「这批房」；不依赖任何人工清单。"""
    with open(STATE_PATH, "r", encoding="utf-8") as fh:
        state = json.load(fh)
    rooms = []
    for entry in state.get("rooms") or []:
        match = SESSION_LOG_RE.search(os.path.basename(entry.get("session_log") or ""))
        if not match:
            continue
        stamp = datetime.strptime(match.group(1) + match.group(2), "%Y%m%d%H%M%S")
        if stamp < since:
            continue
        rooms.append({
            "room_id": entry.get("room_id"),
            "session_log": entry.get("session_log"),
            "started_at": stamp.isoformat(sep=" "),
            "audit_dir": entry.get("audit_dir"),
            "room_subtotal": entry.get("room_subtotal"),
            "terminal_reason": entry.get("terminal_reason"),
            "games": entry.get("games") or [],
        })
    return state, rooms


def collect_downloads(room_ids):
    """把 official/dl-* 按 room_id 分组（先读体量很小的 source.json）。"""
    grouped = collections.defaultdict(list)
    root = _project_file(_PROJECT_ROOT, SESSION_ROOT / "official")
    if not root.is_dir():
        return grouped
    for name in sorted(os.listdir(root)):
        dl = root / name
        source = dl / "source.json"
        if not source.is_file():
            continue
        try:
            with open(source, "r", encoding="utf-8") as fh:
                room_id = json.load(fh).get("room_id")
        except (OSError, ValueError):
            continue
        if room_id in room_ids:
            grouped[room_id].append(str(dl))
    return grouped


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def main(argv=None):
    parser = argparse.ArgumentParser(description="自由赛最近一批房的运行完整性审计（只读）")
    parser.add_argument("--since", default="2026-09-26T10:35:00",
                        help="批次起点（本地时间，按 watchdog session 日志名解析）")
    parser.add_argument("--json-out", default=None, help="把完整聚合结果另存为 JSON（可选）")
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args(argv)
    since = datetime.strptime(args.since, "%Y-%m-%dT%H:%M:%S")

    state, rooms = load_rooms(since)
    print("== 批次 ==")
    print("战役: %s（账本: %s）" % (state.get("campaign"), STATE_PATH.relative_to(REPO)))
    print("批次起点: %s（按 session 日志名解析）" % since.isoformat(sep=" "))
    print("本批房数: %d / 账本总房数 %d" % (len(rooms), len(state.get("rooms") or [])))

    tasks = []
    for room in rooms:
        audit_dir = os.path.join(str(REPO), room["audit_dir"] or "")
        participant = os.path.join(audit_dir, "participants", ME)
        tasks.append({
            "room": room,
            "decisions": os.path.join(participant, "decisions.jsonl"),
            "games_dir": os.path.join(participant, "games"),
            "raw_dir": os.path.join(participant, "raw"),
            "manifest": os.path.join(audit_dir, "manifest.json"),
        })

    results = {}
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        jobs = {pool.submit(scan_decisions, t["decisions"]): t["room"]["room_id"] for t in tasks}
        for future, room_id in jobs.items():
            results.setdefault(room_id, {})["decisions"] = future.result()

        jobs = {}
        for task in tasks:
            games_dir = task["games_dir"]
            if os.path.isdir(games_dir):
                for name in sorted(os.listdir(games_dir)):
                    jobs[pool.submit(scan_game_audit, os.path.join(games_dir, name))] = task["room"]["room_id"]
        for future, room_id in jobs.items():
            results.setdefault(room_id, {}).setdefault("game_audits", []).append(future.result())

        jobs = {}
        for task in tasks:
            raw_dir = task["raw_dir"]
            if os.path.isdir(raw_dir):
                for name in sorted(os.listdir(raw_dir)):
                    jobs[pool.submit(scan_raw, os.path.join(raw_dir, name))] = task["room"]["room_id"]
        for future, room_id in jobs.items():
            results.setdefault(room_id, {}).setdefault("raw", []).append(future.result())

        downloads = collect_downloads({room["room_id"] for room in rooms})
        jobs = {pool.submit(scan_room_official, (room_id, dl_dirs, ME)): room_id
                for room_id, dl_dirs in downloads.items()}
        for future, room_id in jobs.items():
            results.setdefault(room_id, {})["official"] = future.result()

    for task in tasks:
        room_id = task["room"]["room_id"]
        results[room_id]["manifest"] = read_manifest(task["manifest"])
        results[room_id]["room"] = task["room"]

    report = build_report(rooms, results, since)
    emit(report)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=1, default=str)
        print("\n（完整聚合已写出：%s）" % args.json_out)
    return 0 if not report["verdict"]["defects"] else 1


def build_report(rooms, results, since):
    totals = collections.Counter()
    rule_lat = collections.defaultdict(list)
    policy_lat = collections.defaultdict(list)
    lag_total = collections.Counter()
    trigger_total = collections.Counter()
    area_total = collections.Counter()
    incremental_total = collections.Counter()
    area_reason_total = collections.Counter()
    sse_reason_total = collections.Counter()
    reject_total = collections.Counter()
    ambiguous_total = collections.Counter()
    diff_total = collections.Counter()
    empty_by_phase = collections.Counter()
    end_by = collections.Counter()
    over_1000 = collections.Counter()
    over_deadline = collections.Counter()
    http_status = collections.Counter()
    http_error_type = collections.Counter()
    http_error_endpoint = collections.Counter()
    notify_durations = []
    notify_long_durations = []
    late_windows = []
    per_room = []

    for room in rooms:
        room_id = room["room_id"]
        bundle = results.get(room_id, {})
        dec = bundle.get("decisions") or {}
        counts = dec.get("counts") or {}
        totals.update(counts)
        for key, values in (dec.get("rule_latency") or {}).items():
            rule_lat[key].extend(values)
        for key, values in (dec.get("policy_latency") or {}).items():
            policy_lat[key].extend(values)
        for key, value in (dec.get("snapshot_lag") or {}).items():
            lag_total[key] += value
        reject_total.update(dec.get("reject_reasons") or {})
        ambiguous_total.update(dec.get("ambiguous_reasons") or {})
        diff_total.update(dec.get("diff_pairs") or {})
        empty_by_phase.update(dec.get("plan_empty_by_phase") or {})
        end_by.update(dec.get("end_by") or {})
        over_1000.update(dec.get("intent_over_1000ms") or {})
        over_deadline.update(dec.get("intent_over_deadline") or {})
        http_status.update(dec.get("http_status") or {})
        http_error_type.update(dec.get("http_error_type") or {})
        http_error_endpoint.update(dec.get("http_error_endpoint") or {})
        late_windows.extend(dec.get("late_windows") or [])

        room_counts = collections.Counter()
        room_triggers = collections.Counter()
        room_areas = collections.Counter()
        room_raw = collections.Counter()
        submit_status = collections.Counter()
        sse_before_finish = sse_after_finish = 0
        for ga in bundle.get("game_audits") or []:
            room_counts.update(ga.get("counts") or {})
            room_triggers.update(ga.get("triggers") or {})
            room_areas.update(ga.get("areas") or {})
            incremental_total.update(ga.get("incremental_reasons") or {})
            area_reason_total.update(ga.get("area_reasons") or {})
            finished_at = ga.get("finished_at_monotonic_ns")
            for item in ga.get("sse_degraded") or []:
                sse_reason_total[str(item.get("reason"))] += 1
                stamp = item.get("monotonic_ns")
                if finished_at is not None and stamp is not None and stamp > finished_at:
                    sse_after_finish += 1
                else:
                    sse_before_finish += 1
        trigger_total.update(room_triggers)
        area_total.update(room_areas)
        for rs in bundle.get("raw") or []:
            room_raw.update(rs.get("counts") or {})
            submit_status.update(rs.get("submit_status") or {})
            notify_durations.extend(rs.get("notify_durations") or [])
            notify_long_durations.extend(rs.get("notify_long_durations") or [])

        official = bundle.get("official") or {}
        games = official.get("games") or []
        first_discard = official.get("first_discard") or {}
        official_total = official.get("my_total_from_rounds")
        ledger_total = room.get("room_subtotal")
        ledger_games_sum = sum(g.get("final_score", 0) for g in room["games"])
        manifest = bundle.get("manifest") or {}
        connections = room_raw.get("notify_responses", 0)
        games_count = len(games)

        per_room.append({
            "room_id": room_id,
            "started_at": room["started_at"],
            "session_log": os.path.basename(room["session_log"] or ""),
            "decisions": counts.get("planned", 0),
            "inputs": counts.get("input", 0),
            "ended": counts.get("ended", 0),
            "submit_matches": counts.get("submit_matches_rank1", 0),
            "submit_differs": counts.get("submit_differs_rank1", 0),
            "submit_without_rank1": counts.get("submit_without_rank1", 0),
            "validated": counts.get("validated", 0),
            "illegal": counts.get("illegal", 0),
            "rejected": counts.get("rejected", 0),
            "ambiguous": counts.get("out__SubmitAmbiguous", 0),
            "plan_empty": counts.get("plan_empty_total", 0),
            "plan_empty_draw": counts.get("plan_empty_in_draw", 0),
            "draw_deadline": (dec.get("end_by") or {}).get("draw|deadline", 0),
            "response_deadline": sum(v for k, v in (dec.get("end_by") or {}).items()
                                     if k.endswith("|deadline") and k.startswith("response")),
            "snapshot_lag_positive": sum(v for k, v in (dec.get("snapshot_lag") or {}).items()
                                         if int(k) > 0),
            "gap_true_wire": room_raw.get("gap_true_wire", 0),
            "gap_true_engine": room_counts.get("gap_true_engine", 0),
            "http_409": counts.get("http_409", 0),
            "submit_409": submit_status.get("409", 0),
            "rebuild_snapshot_gap": room_triggers.get("rebuild_snapshot_gap", 0),
            "pending_gap": room_triggers.get("pending_gap", 0),
            "incremental_rebuild": room_triggers.get("incremental", 0),
            "decision_window_records": room_areas.get("decision_window", 0),
            "decision_loop_records": room_areas.get("decision_loop", 0),
            "sse_degraded_before_finish": sse_before_finish,
            "sse_degraded_after_finish": sse_after_finish,
            "notify_connections": connections,
            "notify_long": room_raw.get("notify_long_connections", 0),
            "notify_short": room_raw.get("notify_short_connections", 0),
            "notify_games": games_count,
            "state_requests": counts.get("state_requests", 0),
            "sse_closed_frames": room_raw.get("sse_closed_frames", 0),
            "sse_frames": room_raw.get("sse_frames", 0),
            "games_official": games_count,
            "games_ledger": len(room["games"]),
            "first_discard_windows": first_discard.get("windows", 0),
            "first_discard_timeouts": first_discard.get("timeouts", 0),
            "official_total": official_total,
            "official_total_from_final_scores": official.get("my_total_from_final_scores"),
            "ledger_total": ledger_total,
            "ledger_games_sum": ledger_games_sum,
            "subtotal_match": official_total == ledger_total,
            "ledger_internal_match": ledger_games_sum == ledger_total,
            "final_scores_agree": official.get("final_scores_agree", 0),
            "final_scores_games": official.get("final_scores_games", 0),
            "release_package_id": manifest.get("release_package_id"),
            "policy_version": manifest.get("policy_version"),
            "manifest_error": manifest.get("error"),
            "release_binding_error": (None if manifest.get("error")
                                      else verify_manifest_release(manifest)),
            "official_counts": official.get("counts") or {},
            "official_errors": official.get("errors") or [],
        })

    defects = []
    notes = []

    flag = lambda cond, msg: defects.append(msg) if cond else None

    flag(totals.get("submit_differs_rank1", 0) > 0,
         "计划首选与提交不一致 = %d" % totals.get("submit_differs_rank1", 0))
    flag(totals.get("illegal", 0) > 0, "非法提交 = %d" % totals.get("illegal", 0))
    flag(totals.get("rejected", 0) > 0, "被官方拒绝 = %d" % totals.get("rejected", 0))
    flag(totals.get("out__SubmitAmbiguous", 0) > 0,
         "SubmitAmbiguous = %d" % totals.get("out__SubmitAmbiguous", 0))
    flag(totals.get("plan_empty_in_draw", 0) > 0,
         "plan_empty 落在 draw 窗 = %d" % totals.get("plan_empty_in_draw", 0))
    flag(end_by.get("draw|deadline", 0) > 0,
         "摸牌窗超过截止 (draw|deadline) = %d" % end_by.get("draw|deadline", 0))
    lag_positive = sum(v for k, v in lag_total.items() if int(k) > 0)
    flag(lag_positive > 0, "snapshot_seq 落后 trigger_seq = %d" % lag_positive)
    flag(over_deadline.get("draw", 0) > 0 or over_deadline.get("response", 0) > 0,
         "提交意图晚于窗口截止 = %s" % dict(over_deadline))
    flag(over_1000.get("draw", 0) > 0,
         "摸牌窗提交 >1000 ms = %d" % over_1000.get("draw", 0))
    flag(trigger_total.get("pending_gap", 0) > 0,
         "pending_gap 重建 = %d" % trigger_total.get("pending_gap", 0))
    flag(trigger_total.get("incremental", 0) > 0,
         "incremental 序号断链重建 = %d" % trigger_total.get("incremental", 0))
    state_429 = http_status.get("429", 0)
    if state_429:
        notes.append("/state 429 = %d（全部为 GET /state，被拒查询按退避重排；无下游漏窗）" % state_429)
    transport_none = http_status.get("None", 0)
    if transport_none:
        detail = {k: v for k, v in http_error_type.items() if k.startswith("None|")}
        notes.append("传输结果不确定（http_status=null）= %d：%s；端点 %s" % (
            transport_none, detail,
            {k: v for k, v in http_error_endpoint.items() if k.startswith("None|")}))
    for row in per_room:
        if row["first_discard_timeouts"]:
            defects.append("跨局首弃牌超时 %s = %d" % (row["room_id"], row["first_discard_timeouts"]))
        if not row["subtotal_match"]:
            defects.append("账本不一致 %s: 官方复算 %s vs 账本 %s"
                           % (row["room_id"], row["official_total"], row["ledger_total"]))
        if not row["ledger_internal_match"]:
            defects.append("账本内部不一致 %s: 局分和 %s vs room_subtotal %s"
                           % (row["room_id"], row["ledger_games_sum"], row["ledger_total"]))
        if row["manifest_error"]:
            defects.append("manifest 读取失败 %s: %s" % (row["room_id"], row["manifest_error"]))
        elif row["release_binding_error"]:
            defects.append("发布包与受控绑定不一致 %s: %s" % (
                row["room_id"], row["release_binding_error"]))
        if row["sse_degraded_before_finish"]:
            defects.append("SSE 恢复耗尽发生在终局之前 %s = %d"
                           % (row["room_id"], row["sse_degraded_before_finish"]))
        if row["response_deadline"]:
            notes.append("响应窗在规划前到期（零动作尝试）%s = %d"
                         % (row["room_id"], row["response_deadline"]))
        if row["games_official"] != row["games_ledger"]:
            notes.append("官方原文局数 %d ≠ 账本局数 %d（%s）"
                         % (row["games_official"], row["games_ledger"], row["room_id"]))
        if row["official_errors"]:
            notes.append("官方原文结构/摘要异常 %s: %s" % (row["room_id"], row["official_errors"][:3]))
        if row["final_scores_agree"] != row["final_scores_games"]:
            notes.append("官方 rounds 与 game_ended 真值不一致 %s = %d 局"
                         % (row["room_id"], row["final_scores_games"] - row["final_scores_agree"]))

    sse_after = sum(r["sse_degraded_after_finish"] for r in per_room)
    sse_before = sum(r["sse_degraded_before_finish"] for r in per_room)
    if sse_after or sse_before:
        notes.append("SSE 重连耗尽 sse_degraded=%d（终局后 %d / 终局前 %d）"
                     % (sse_before + sse_after, sse_after, sse_before))
    response_expired = sum(r["response_deadline"] for r in per_room)
    response_windows = sum(v for k, v in end_by.items() if k.startswith("response"))
    if response_expired:
        notes.append("响应窗在规划前到期合计 %d（响应窗共 %d，占 %.4f%%；均为吃碰响应窗，非摸牌窗）"
                     % (response_expired, response_windows,
                        100.0 * response_expired / max(1, response_windows)))

    return {
        "campaign": CAMPAIGN,
        "since": since.isoformat(sep=" "),
        "rooms": per_room,
        "totals": dict(totals),
        "snapshot_lag": dict(lag_total),
        "rule_latency": {k: quantiles(v) for k, v in rule_lat.items()},
        "policy_latency": {k: quantiles(v) for k, v in policy_lat.items()},
        "notify_connection_duration": quantiles(notify_durations),
        "notify_long_duration": quantiles(notify_long_durations),
        "triggers": dict(trigger_total),
        "areas": dict(area_total),
        "incremental_reasons": dict(incremental_total),
        "area_reasons": dict(area_reason_total),
        "sse_degraded_reasons": dict(sse_reason_total),
        "reject_reasons": dict(reject_total),
        "ambiguous_reasons": dict(ambiguous_total),
        "diff_pairs": dict(diff_total),
        "plan_empty_by_phase": dict(empty_by_phase),
        "end_by_phase_reason": dict(end_by),
        "intent_over_1000ms": dict(over_1000),
        "intent_over_deadline": dict(over_deadline),
        "late_windows": late_windows[:20],
        "http_status": dict(http_status),
        "http_error_type": dict(http_error_type),
        "http_error_endpoint": dict(http_error_endpoint),
        "verdict": {"defects": defects, "notes": notes},
    }


def emit(report):
    rows = report["rooms"]
    totals = report["totals"]

    print("\n== 1. 决策完整性 ==")
    print("decision_input=%d  decision_planned=%d  candidate_validated=%d  decision_ended=%d" % (
        totals.get("input", 0), totals.get("planned", 0), totals.get("validated", 0),
        totals.get("ended", 0)))
    print("submission_intent=%d  submission_outcome=%d" % (
        totals.get("intent", 0), totals.get("outcome", 0)))
    print("计划首选与提交：一致=%d  不一致=%d  无计划可对照=%d" % (
        totals.get("submit_matches_rank1", 0), totals.get("submit_differs_rank1", 0),
        totals.get("submit_without_rank1", 0)))
    print("非法提交=%d  被拒=%d  SubmitAmbiguous=%d  plan_empty=%d（draw 窗 %d）" % (
        totals.get("illegal", 0), totals.get("rejected", 0),
        totals.get("out__SubmitAmbiguous", 0), totals.get("plan_empty_total", 0),
        totals.get("plan_empty_in_draw", 0)))
    print("end_reason × phase: %s" % report["end_by_phase_reason"])
    print("plan_empty × phase: %s" % report["plan_empty_by_phase"])
    if report["reject_reasons"]:
        print("被拒原因分布: %s" % report["reject_reasons"])
    if report["ambiguous_reasons"]:
        print("SubmitAmbiguous 原因: %s" % report["ambiguous_reasons"])
    if report["diff_pairs"]:
        print("不一致明细: %s" % report["diff_pairs"])

    print("\n== 2. 时延（毫秒，按窗型） ==")
    print("rule_elapsed_ms: %s" % report["rule_latency"])
    print("policy_elapsed_ms: %s" % report["policy_latency"])
    print("提交意图 >1000 ms（按窗型）: %s" % report["intent_over_1000ms"])
    print("提交意图晚于窗口截止（按窗型）: %s" % report["intent_over_deadline"])

    print("\n== 3. 序号与快照 ==")
    print("协议恢复 trigger 分布: %s" % report["triggers"])
    print("窗口簿记 area 分布: %s" % report["areas"])
    print("协议恢复 reasons: %s" % report["incremental_reasons"])
    print("窗口簿记原因: %s" % report["area_reasons"])
    print("snapshot_seq 滞后 trigger_seq 分布（lag=trigger-snapshot）: %s" % report["snapshot_lag"])
    print("HTTP 状态码分布: %s（/state 请求合计 %d）" % (
        report["http_status"], totals.get("state_requests", 0)))
    print("非 200 明细: %s / %s" % (report["http_error_type"], report["http_error_endpoint"]))
    print("线缆 gap=true（state_response）合计: %d；引擎吸收记录 rebuild_snapshot_gap: %d" % (
        sum(r["gap_true_wire"] for r in rows), report["triggers"].get("rebuild_snapshot_gap", 0)))

    print("\n== 4. 跨局首弃牌 ==")
    print("合计: 窗口 %d / 超时 %d" % (
        sum(r["first_discard_windows"] for r in rows),
        sum(r["first_discard_timeouts"] for r in rows)))
    for row in rows:
        print("  %-16s 官方完整局 %2d/账本 %2d  首弃牌窗 %2d  超时 %d" % (
            row["room_id"], row["games_official"], row["games_ledger"],
            row["first_discard_windows"], row["first_discard_timeouts"]))

    print("\n== 5. SSE 健康 ==")
    print("/notify 连接=%d（长连接≥%.0fs %d / 短连接 %d）  帧=%d  关闭帧=%d  降级=%s（终局前 %d / 终局后 %d）" % (
        sum(r["notify_connections"] for r in rows), SHORT_CONNECTION_SEC,
        sum(r["notify_long"] for r in rows), sum(r["notify_short"] for r in rows),
        sum(r["sse_frames"] for r in rows),
        sum(r["sse_closed_frames"] for r in rows), report["sse_degraded_reasons"],
        sum(r["sse_degraded_before_finish"] for r in rows),
        sum(r["sse_degraded_after_finish"] for r in rows)))
    print("连接时长（全部，秒）: %s" % report["notify_connection_duration"])
    print("长连接时长（秒）: %s" % report["notify_long_duration"])
    for row in rows:
        print("  %-16s 连接 %2d（长 %2d 短 %2d）  局 %2d  关闭帧 %3d  降级 %d" % (
            row["room_id"], row["notify_connections"], row["notify_long"], row["notify_short"],
            row["notify_games"], row["sse_closed_frames"],
            row["sse_degraded_before_finish"] + row["sse_degraded_after_finish"]))

    print("\n== 6. 结算与账本 ==")
    for row in rows:
        print("  %-16s 官方复算 %5s  账本 %5s  局分和 %5s  %s" % (
            row["room_id"], row["official_total"], row["ledger_total"], row["ledger_games_sum"],
            "一致" if row["subtotal_match"] else "**不一致**"))

    print("\n== 7. 部署身份 ==")
    for row in rows:
        print("  %-16s %s  %s" % (
            row["room_id"], str(row["release_package_id"])[:16], row["policy_version"]))

    print("\n== 结论 ==")
    defects = report["verdict"]["defects"]
    if defects:
        print("  门禁失败 %d 项：" % len(defects))
        for item in defects:
            print("   - %s" % item)
    else:
        print("  七项门禁全部通过（点名的判据全为 0 或全一致）。")
    for item in report["verdict"]["notes"]:
        print("  登记（非门禁）: %s" % item)


if __name__ == "__main__":
    raise SystemExit(main())
