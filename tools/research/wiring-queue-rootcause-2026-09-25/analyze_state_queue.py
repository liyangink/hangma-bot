#!/usr/bin/env python3
"""state 查询排队/限速根因的只读分析脚本。

用途
    消费运行审计目录里的 decisions.jsonl，回答"官方 state 查询为什么被限速（429）"这一类问题：
    排队延迟分布在哪个 (query_purpose, scheduler_priority) 分组、获准发送速率是否触到本地
    记账上限（1.05 秒窗口 16 笔 / 14.5 次每秒平滑）、429 发生时前 1.05 秒内已获准多少笔。

输入
    命令行第一个位置参数：decisions.jsonl 路径。
    形如 artifacts/sessions/<session>/audit/runs/<run>/participants/<pid>/decisions.jsonl，
    每行一个 JSON 记录，本脚本只读取不写入：
      - kind=http_request、payload.phase=started 的记录带 request_timing.queued_at_monotonic /
        granted_at_monotonic / transport_started_at_monotonic（单位：秒，单调时钟）；
      - 同 request_id 的 phase=finished 记录带 http_status / error_type；
      - 非 state 端点（GET /api/me、GET /api/games/X/notify、POST /api/games/X/action 等）
        的 request_timing 没有 queued_at/granted_at，只有 transport_started_at_monotonic，
        因此不参与排队延迟统计，只用于 wall clock 锚点与 http_status>=400 清单。

输出
    stdout：中文文本报告（分组延迟、滚动窗口、每秒直方图、Top 排队、每 game 计数、
    long poll 间隔、全部 http_status>=400 明细、决策密度比值）。
    --json-out <路径>：同一份结果的机器可读 JSON 汇总。

口径
    1. 只统计 endpoint 以 "/state" 结尾且 method == "GET" 的请求。
    2. 同一 request_id 的 started/finished 记录合并为一条请求，按 request_id 去重计数。
    3. 排队延迟 = (granted_at_monotonic - queued_at_monotonic) * 1000（毫秒）；
       传输耗时 = (transport_started_at_monotonic - granted_at_monotonic) * 1000（毫秒）；
       两者只有在两个端点都存在时才计入，缺失时单独计数（missing_queue_timing）。
    4. 百分位采用最近秩（nearest-rank）：idx = ceil(pct * n / 100) - 1。
    5. 滚动窗口按 transport_started_at_monotonic 升序排列，窗口两端都算在内（<=）。
    6. wall clock 用"第一条带 transport_started_at_monotonic 的记录"作为
       monotonic -> wall 的线性锚点换算；优先用该记录的 request_timing.started_wall_unix_ms
       （与单调时刻精确配对），缺失时退化为记录自带的 wall_time_unix_ms。
    7. 429 归因用的"前 1.05 秒已获准笔数"窗口是半开区间 [t - 1.05, t)，不含本请求自身。

只读约束：不导入 hangma_bot 任何模块、不访问网络、不修改任何输入文件，只使用标准库。
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/wiring-queue-rootcause-2026-09-25'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import bisect
import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone

# 官方额度口径：每身份 16 次/1.05 秒窗口，另有 14.5 次/秒的平滑间隔。
# 1.00 s 与 1.05 s 两个窗口同时观察，便于区分"记账窗口触顶"与"平滑间隔触顶"。
WINDOW_SECONDS = (1.00, 1.05)
ACCOUNT_WINDOW_SECONDS = 1.05
DEFAULT_TOP = 25

UNKNOWN = "(unknown)"


# --------------------------------------------------------------------------------------
# 基础工具
# --------------------------------------------------------------------------------------


def percentile_ms(sorted_values: list[float], pct: int) -> float | None:
    """最近秩百分位；入参必须已升序，空列表返回 None。"""
    if not sorted_values:
        return None
    n = len(sorted_values)
    idx = -(-pct * n // 100) - 1  # ceil(pct * n / 100) - 1，整数运算避免浮点误差
    idx = min(max(idx, 0), n - 1)
    return sorted_values[idx]


def latency_bundle(values_ms: list[float]) -> dict:
    """把一组毫秒样本整理成 p50/p90/p99/max/mean 摘要。"""
    ordered = sorted(values_ms)
    return {
        "count": len(ordered),
        "p50": percentile_ms(ordered, 50),
        "p90": percentile_ms(ordered, 90),
        "p99": percentile_ms(ordered, 99),
        "max": ordered[-1] if ordered else None,
        "mean": statistics.mean(ordered) if ordered else None,
    }


def rolling_window_counts(times_s: list[float], window_s: float) -> list[int]:
    """对升序时间序列求"每个起点窗口内包含的样本数"；窗口两端都算（t <= start + window）。"""
    return [bisect.bisect_right(times_s, t + window_s) - i for i, t in enumerate(times_s)]


def histogram_of_counts(counts: list[int]) -> dict:
    """把窗口样本数序列变成直方图：{窗口内笔数: 出现该笔数的窗口个数}。"""
    return {str(k): v for k, v in sorted(Counter(counts).items())}


def format_wall_clock(wall_ms: float | None) -> str | None:
    """Unix 毫秒 -> UTC 的 HH:MM:SS.mmm。"""
    if wall_ms is None:
        return None
    dt = datetime.fromtimestamp(wall_ms / 1000.0, tz=timezone.utc)
    return dt.strftime("%H:%M:%S.") + f"{dt.microsecond // 1000:03d}"


def format_utc_iso(wall_ms: float | None) -> str | None:
    """Unix 毫秒 -> UTC ISO 8601（带毫秒），用于报告表头。"""
    if wall_ms is None:
        return None
    dt = datetime.fromtimestamp(wall_ms / 1000.0, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _fmt(value, digits: int = 3, unit: str = "") -> str:
    """报告用数值格式化，None 显示为 "-"。"""
    if value is None:
        return "-"
    return f"{value:.{digits}f}{unit}"


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _delta_ms(later, earlier) -> float | None:
    """两个单调秒差值 -> 毫秒；任一端缺失则返回 None。"""
    if not (_is_number(later) and _is_number(earlier)):
        return None
    return (later - earlier) * 1000.0


# --------------------------------------------------------------------------------------
# 记录采集
# --------------------------------------------------------------------------------------


def iter_records(path: str, stats: dict):
    """逐行读取 decisions.jsonl，产出 (行号, 记录)；损坏行只计数不中断。"""
    with open(path, "r", encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            stats["lines_total"] += 1
            try:
                record = json.loads(line)
            except (ValueError, UnicodeDecodeError) as exc:  # 审计文件可能被截断
                stats["lines_malformed"] += 1
                stats["malformed_examples"].append({"line": lineno, "error": str(exc)[:120]})
                continue
            if not isinstance(record, dict):
                stats["lines_malformed"] += 1
                continue
            stats["lines_parsed"] += 1
            yield lineno, record


def collect(path: str) -> dict:
    """单遍扫描审计文件，收集 http_request 合并视图、锚点与 kind 计数。"""
    stats = {
        "lines_total": 0,
        "lines_parsed": 0,
        "lines_malformed": 0,
        "malformed_examples": [],
    }
    kind_counter: Counter = Counter()
    decisions = {"count": 0, "game_rounds": set()}
    requests: dict = {}  # request_id -> 合并后的请求视图
    anonymous = 0
    anchor = {"monotonic_s": None, "wall_unix_ms": None, "source": None, "line": None}

    for lineno, record in iter_records(path, stats):
        kind = record.get("kind")
        kind_counter[str(kind)] += 1

        if kind == "decision_input":
            decisions["count"] += 1
            context = record.get("context") or {}
            game_id = context.get("game_id")
            round_no = context.get("round_no")
            if game_id is not None and round_no is not None:
                decisions["game_rounds"].add((game_id, round_no))
            continue

        if kind != "http_request":
            continue

        payload = record.get("payload")
        if not isinstance(payload, dict):
            continue
        timing = payload.get("request_timing")
        timing = timing if isinstance(timing, dict) else {}
        context = record.get("context") if isinstance(record.get("context"), dict) else {}

        # wall clock 锚点：文件中第一条带 transport_started_at_monotonic 的记录。
        transport = timing.get("transport_started_at_monotonic")
        if _is_number(transport) and anchor["monotonic_s"] is None:
            started_wall = timing.get("started_wall_unix_ms")
            if _is_number(started_wall):
                anchor.update(
                    monotonic_s=transport,
                    wall_unix_ms=started_wall,
                    source="request_timing.started_wall_unix_ms",
                    line=lineno,
                )
            else:
                anchor.update(
                    monotonic_s=transport,
                    wall_unix_ms=record.get("wall_time_unix_ms"),
                    source="record.wall_time_unix_ms",
                    line=lineno,
                )

        endpoint = payload.get("endpoint") or ""
        method = str(payload.get("method") or "").upper()
        request_id = payload.get("request_id") or timing.get("request_id")
        if not request_id:
            anonymous += 1
            request_id = f"__anonymous_{anonymous}"
        params = payload.get("params") if isinstance(payload.get("params"), dict) else {}

        entry = requests.get(request_id)
        if entry is None:
            entry = {
                "request_id": request_id,
                "endpoint": endpoint,
                "method": method,
                "game_id": context.get("game_id"),
                "round_no": context.get("round_no"),
                "seq": params.get("seq"),
                "purpose": None,
                "priority": None,
                "queued_s": None,
                "granted_s": None,
                "transport_s": None,
                "started_wall_ms": None,
                "record_wall_ms": None,
                "http_status": None,
                "error_type": None,
                "phases": [],
                "outcome": None,
            }
            requests[request_id] = entry

        # 端点/方法以 started 记录为准，finished-only 记录也能补齐。
        if endpoint and not entry["endpoint"]:
            entry["endpoint"] = endpoint
        if method and not entry["method"]:
            entry["method"] = method
        if entry["game_id"] is None and context.get("game_id") is not None:
            entry["game_id"] = context.get("game_id")
        if entry["round_no"] is None and context.get("round_no") is not None:
            entry["round_no"] = context.get("round_no")
        if entry["seq"] is None and params.get("seq") is not None:
            entry["seq"] = params.get("seq")

        # 首个非空值优先，避免后写的 null 覆盖已有元信息。
        # 字符串元信息（purpose/priority）与数值时刻分开判断，避免数值守卫吞掉字符串。
        for key, value in (
            ("purpose", timing.get("query_purpose")),
            ("priority", timing.get("scheduler_priority")),
        ):
            if entry[key] is None and isinstance(value, str) and value:
                entry[key] = value
        for key, value in (
            ("queued_s", timing.get("queued_at_monotonic")),
            ("granted_s", timing.get("granted_at_monotonic")),
            ("transport_s", transport),
        ):
            if entry[key] is None and _is_number(value):
                entry[key] = value

        if entry["started_wall_ms"] is None and _is_number(timing.get("started_wall_unix_ms")):
            entry["started_wall_ms"] = timing["started_wall_unix_ms"]
        if entry["record_wall_ms"] is None and _is_number(record.get("wall_time_unix_ms")):
            entry["record_wall_ms"] = record["wall_time_unix_ms"]

        phase = payload.get("phase")
        if isinstance(phase, str) and phase not in entry["phases"]:
            entry["phases"].append(phase)
        if payload.get("http_status") is not None:
            entry["http_status"] = payload.get("http_status")
        if payload.get("error_type") is not None:
            entry["error_type"] = payload.get("error_type")
        if payload.get("outcome") is not None:
            entry["outcome"] = payload.get("outcome")

    return {
        "stats": stats,
        "kind_counter": kind_counter,
        "decisions": decisions,
        "requests": requests,
        "anchor": anchor,
    }


# --------------------------------------------------------------------------------------
# 分析
# --------------------------------------------------------------------------------------


def _is_state_request(entry: dict) -> bool:
    """口径 1：endpoint 以 /state 结尾且 method=GET。"""
    return entry["endpoint"].endswith("/state") and entry["method"] == "GET"


def _wall_ms(entry: dict, anchor: dict) -> float | None:
    """按锚点把单调时刻线性换算成 Unix 毫秒。"""
    if anchor["monotonic_s"] is None or anchor["wall_unix_ms"] is None:
        return None
    if entry["transport_s"] is None:
        return None
    return anchor["wall_unix_ms"] + (entry["transport_s"] - anchor["monotonic_s"]) * 1000.0


def analyze(path: str, top_n: int = DEFAULT_TOP) -> dict:
    """跑完整套统计，返回可直接 json.dump 的汇总字典。"""
    collected = collect(path)
    requests = collected["requests"]
    anchor = collected["anchor"]
    decisions = collected["decisions"]

    state_entries = [e for e in requests.values() if _is_state_request(e)]
    state_entries.sort(key=lambda e: (e["transport_s"] is None, e["transport_s"]))

    started = [e for e in state_entries if "started" in e["phases"]]
    finished = [e for e in state_entries if "finished" in e["phases"]]
    transport_times = [e["transport_s"] for e in state_entries if e["transport_s"] is not None]

    # --- 2. 按 (query_purpose, scheduler_priority) 交叉分组 -------------------------------
    grouped: dict = defaultdict(
        lambda: {"queue_ms": [], "transport_ms": [], "status": Counter(), "missing_queue_timing": 0}
    )
    for entry in state_entries:
        bucket = grouped[(entry["purpose"] or UNKNOWN, entry["priority"] or UNKNOWN)]
        queue_ms = _delta_ms(entry["granted_s"], entry["queued_s"])
        transport_ms = _delta_ms(entry["transport_s"], entry["granted_s"])
        if queue_ms is not None:
            bucket["queue_ms"].append(queue_ms)
        else:
            bucket["missing_queue_timing"] += 1
        if transport_ms is not None:
            bucket["transport_ms"].append(transport_ms)
        bucket["status"][str(entry["http_status"]) if entry["http_status"] is not None else "none"] += 1

    groups = []
    for (purpose, priority), bucket in sorted(
        grouped.items(), key=lambda item: (-len(item[1]["queue_ms"]) - item[1]["missing_queue_timing"], item[0])
    ):
        queue_stats = latency_bundle(bucket["queue_ms"])
        transport_stats = latency_bundle(bucket["transport_ms"])
        requests_in_group = sum(bucket["status"].values())
        groups.append(
            {
                "purpose": purpose,
                "priority": priority,
                "requests": requests_in_group,
                "queue_delay_ms": queue_stats,
                "transport_ms": {
                    "count": transport_stats["count"],
                    "p50": transport_stats["p50"],
                    "p99": transport_stats["p99"],
                    "max": transport_stats["max"],
                },
                "http_status": dict(sorted(bucket["status"].items())),
                "http_429_count": bucket["status"].get("429", 0),
                "http_error_count": sum(
                    v for k, v in bucket["status"].items() if k not in ("none",) and int(k) >= 400
                ),
                "missing_queue_timing": bucket["missing_queue_timing"],
            }
        )

    # --- 3. 滚动窗口（获准发送速率） ----------------------------------------------------
    rolling = {}
    for window in WINDOW_SECONDS:
        counts = rolling_window_counts(transport_times, window)
        rolling[f"{window:.2f}"] = {
            "window_seconds": window,
            "max": max(counts) if counts else 0,
            "windows": len(counts),
            "histogram": histogram_of_counts(counts),
        }

    # --- 4. 每秒 state 请求数直方图 ------------------------------------------------------
    second_counter: Counter = Counter()
    for value in transport_times:
        second_counter[int(value)] += 1  # 单调秒向下取整（正值截断等价于 floor）
    base_second = min(second_counter) if second_counter else None
    per_second_buckets = [
        {"offset_s": sec - base_second, "monotonic_floor_s": sec, "count": count}
        for sec, count in sorted(second_counter.items())
    ]
    per_second_counts = list(second_counter.values())
    per_second = {
        "buckets": per_second_buckets,
        "bucket_count": len(per_second_buckets),
        "max": max(per_second_counts) if per_second_counts else 0,
        "mean": statistics.mean(per_second_counts) if per_second_counts else None,
        "span_seconds": (max(second_counter) - base_second + 1) if second_counter else 0,
        "total": sum(per_second_counts),
    }

    # --- 5. 排队延迟 Top N ---------------------------------------------------------------
    delayed = [
        (queue_ms, entry)
        for entry in state_entries
        if (queue_ms := _delta_ms(entry["granted_s"], entry["queued_s"])) is not None
    ]
    delayed.sort(key=lambda item: -item[0])
    top_queue_delay = [
        {
            "request_id": entry["request_id"],
            "purpose": entry["purpose"],
            "priority": entry["priority"],
            "seq": entry["seq"],
            "game_id": entry["game_id"],
            "queue_delay_ms": queue_ms,
            "transport_ms": _delta_ms(entry["transport_s"], entry["granted_s"]),
            "http_status": entry["http_status"],
            "wall_clock_utc": format_wall_clock(_wall_ms(entry, anchor)),
        }
        for queue_ms, entry in delayed[:top_n]
    ]

    # --- 6. 每个 game_id 的 state 请求数与 long poll 间隔 --------------------------------
    games: dict = defaultdict(lambda: {"state_requests": 0, "transport_times": []})
    for entry in state_entries:
        game_id = entry["game_id"] if entry["game_id"] is not None else UNKNOWN
        games[game_id]["state_requests"] += 1
        if entry["transport_s"] is not None:
            games[game_id]["transport_times"].append(entry["transport_s"])

    games_summary = {}
    for game_id, info in sorted(games.items(), key=lambda item: -item[1]["state_requests"]):
        times = sorted(info["transport_times"])
        games_summary[game_id] = {
            "state_requests": info["state_requests"],
            "first_wall_utc": format_wall_clock(
                anchor["wall_unix_ms"] + (times[0] - anchor["monotonic_s"]) * 1000.0
                if times and anchor["monotonic_s"] is not None
                else None
            ),
            "last_wall_utc": format_wall_clock(
                anchor["wall_unix_ms"] + (times[-1] - anchor["monotonic_s"]) * 1000.0
                if times and anchor["monotonic_s"] is not None
                else None
            ),
            "span_seconds": (times[-1] - times[0]) if len(times) >= 2 else None,
        }

    long_poll_times_by_game: dict = defaultdict(list)
    for entry in state_entries:
        if entry["purpose"] == "sse_settled_long_poll" and entry["transport_s"] is not None:
            long_poll_times_by_game[entry["game_id"] if entry["game_id"] is not None else UNKNOWN].append(
                entry["transport_s"]
            )
    all_long_poll_times = sorted(t for times in long_poll_times_by_game.values() for t in times)

    def _gaps(times: list[float]) -> list[float]:
        ordered = sorted(times)
        return [b - a for a, b in zip(ordered, ordered[1:])]

    def _gap_bundle(gaps: list[float]) -> dict:
        ordered = sorted(gaps)
        return {
            "count": len(ordered),
            "p50": percentile_ms(ordered, 50),
            "p90": percentile_ms(ordered, 90),
            "max": ordered[-1] if ordered else None,
            "mean": statistics.mean(ordered) if ordered else None,
        }

    long_poll = {
        "requests": len(all_long_poll_times),
        "overall_gap_seconds": _gap_bundle(_gaps(all_long_poll_times)),
        "by_game": {
            game_id: {"requests": len(times), "gap_seconds": _gap_bundle(_gaps(times))}
            for game_id, times in sorted(long_poll_times_by_game.items())
        },
    }

    # --- 7. 全部 http_status >= 400 明细 -------------------------------------------------
    errors = []
    for entry in requests.values():
        status = entry["http_status"]
        if not isinstance(status, int) or status < 400:
            continue
        left = bisect.bisect_left(transport_times, entry["transport_s"] - ACCOUNT_WINDOW_SECONDS) if entry[
            "transport_s"
        ] is not None else None
        right = bisect.bisect_left(transport_times, entry["transport_s"]) if entry["transport_s"] is not None else None
        errors.append(
            {
                "request_id": entry["request_id"],
                "wall_clock_utc": format_wall_clock(_wall_ms(entry, anchor)),
                "http_status": status,
                "error_type": entry["error_type"],
                "endpoint": entry["endpoint"],
                "method": entry["method"],
                "game_id": entry["game_id"],
                "purpose": entry["purpose"],
                "priority": entry["priority"],
                "seq": entry["seq"],
                "is_state_request": _is_state_request(entry),
                "queue_delay_ms": _delta_ms(entry["granted_s"], entry["queued_s"]),
                "transport_ms": _delta_ms(entry["transport_s"], entry["granted_s"]),
                "granted_state_requests_in_prior_1_05s": (right - left) if left is not None else None,
            }
        )
    errors.sort(key=lambda item: (item["wall_clock_utc"] or "", item["request_id"]))

    # --- 8. 决策密度比值 ----------------------------------------------------------------
    state_count = len(state_entries)
    decision_count = decisions["count"]
    game_round_count = len(decisions["game_rounds"])
    ratios = {
        "state_requests": state_count,
        "decision_inputs": decision_count,
        "distinct_game_rounds": game_round_count,
        "state_per_decision": (state_count / decision_count) if decision_count else None,
        "state_per_game_round": (state_count / game_round_count) if game_round_count else None,
    }

    status_counter: Counter = Counter()
    for entry in state_entries:
        status_counter[str(entry["http_status"]) if entry["http_status"] is not None else "none"] += 1

    return {
        "input_path": path,
        "generated_at_utc": format_utc_iso(datetime.now(tz=timezone.utc).timestamp() * 1000.0),
        "lines": {
            "total": collected["stats"]["lines_total"],
            "parsed": collected["stats"]["lines_parsed"],
            "malformed": collected["stats"]["lines_malformed"],
            "malformed_examples": collected["stats"]["malformed_examples"][:5],
        },
        "kind_counts": dict(sorted(collected["kind_counter"].items())),
        "state_requests": {
            "total": state_count,
            "started_records": len(started),
            "finished_records": len(finished),
            "http_status": dict(sorted(status_counter.items())),
            "http_429_count": status_counter.get("429", 0),
            "missing_queue_timing": sum(g["missing_queue_timing"] for g in groups),
        },
        "wall_anchor": {
            "monotonic_s": anchor["monotonic_s"],
            "wall_unix_ms": anchor["wall_unix_ms"],
            "wall_iso_utc": format_utc_iso(anchor["wall_unix_ms"]),
            "source": anchor["source"],
            "line": anchor["line"],
        },
        "groups": groups,
        "rolling_window": rolling,
        "per_second": per_second,
        "top_queue_delay": top_queue_delay,
        "games": games_summary,
        "long_poll": long_poll,
        "http_errors": errors,
        "decision_density": ratios,
    }


# --------------------------------------------------------------------------------------
# 文本报告
# --------------------------------------------------------------------------------------


def render_report(result: dict) -> str:
    """把汇总字典渲染成中文文本报告。"""
    out: list[str] = []
    add = out.append

    add("=" * 100)
    add("state 查询排队/限速根因分析（只读）")
    add("=" * 100)
    add(f"输入文件      : {result['input_path']}")
    add(f"生成时间 (UTC): {result['generated_at_utc']}")
    lines = result["lines"]
    add(f"记录行        : {lines['total']}（解析成功 {lines['parsed']}，损坏 {lines['malformed']}）")
    anchor = result["wall_anchor"]
    add(
        "wall 锚点     : monotonic={} s <-> {}（来源 {}，行 {}）".format(
            _fmt(anchor["monotonic_s"]), anchor["wall_iso_utc"] or "-", anchor["source"] or "-", anchor["line"]
        )
    )

    state = result["state_requests"]
    add("")
    add("--- 总览 ---")
    add(
        "state 请求（GET + endpoint 以 /state 结尾）: {}（started 记录 {}，finished 记录 {}）".format(
            state["total"], state["started_records"], state["finished_records"]
        )
    )
    add(f"HTTP 状态码分布: {state['http_status']}    429 计数: {state['http_429_count']}")
    add(f"缺少 queued_at/granted_at 的 state 请求: {state['missing_queue_timing']}")

    add("")
    add("--- 按 (query_purpose, scheduler_priority) 分组 ---")
    header = "{:<26} {:<10} {:>6} {:>9} {:>9} {:>9} {:>9} {:>9} {:>9}  {}".format(
        "purpose", "priority", "n", "p50排队", "p90排队", "p99排队", "max排队", "p50传输", "p99传输", "状态码分布"
    )
    add(header)
    add("-" * len(header))
    for group in result["groups"]:
        queue = group["queue_delay_ms"]
        transport = group["transport_ms"]
        add(
            "{:<26} {:<10} {:>6} {:>9} {:>9} {:>9} {:>9} {:>9} {:>9}  {}".format(
                group["purpose"][:26],
                group["priority"][:10],
                group["requests"],
                _fmt(queue["p50"]),
                _fmt(queue["p90"]),
                _fmt(queue["p99"]),
                _fmt(queue["max"]),
                _fmt(transport["p50"]),
                _fmt(transport["p99"]),
                group["http_status"],
            )
        )

    add("")
    add("--- 滚动窗口：任意窗口内“获准发送”（transport_started）的 state 请求数 ---")
    for key, item in result["rolling_window"].items():
        add(
            "窗口 {:.2f}s：最大 {} 笔（共 {} 个起点窗口）；直方图 {}".format(
                item["window_seconds"], item["max"], item["windows"], item["histogram"]
            )
        )

    add("")
    add("--- 每秒 state 请求数直方图（按 transport_started 取整秒） ---")
    per_second = result["per_second"]
    add(
        "覆盖 {} 秒（{} 个非空秒），最大 {} 次/秒，非空秒均值 {} 次/秒".format(
            per_second["span_seconds"], per_second["bucket_count"], per_second["max"], _fmt(per_second["mean"], 2)
        )
    )
    for bucket in per_second["buckets"]:
        add(f"  +{bucket['offset_s']:>5}s (monotonic {bucket['monotonic_floor_s']}): {bucket['count']:>4} 次")

    add("")
    add("--- 排队延迟 Top {}（granted - queued） ---".format(len(result["top_queue_delay"])))
    header = "{:>4} {:<24} {:<10} {:>5} {:<26} {:>10} {:>10}  {}".format(
        "#", "purpose", "priority", "seq", "game_id", "排队ms", "传输ms", "wall(UTC)"
    )
    add(header)
    add("-" * len(header))
    for index, item in enumerate(result["top_queue_delay"], start=1):
        add(
            "{:>4} {:<24} {:<10} {:>5} {:<26} {:>10} {:>10}  {}".format(
                index,
                str(item["purpose"])[:24],
                str(item["priority"])[:10],
                "-" if item["seq"] is None else item["seq"],
                str(item["game_id"])[:26],
                _fmt(item["queue_delay_ms"]),
                _fmt(item["transport_ms"]),
                item["wall_clock_utc"] or "-",
            )
        )

    add("")
    add("--- 每个 game_id 的 state 请求数 ---")
    for game_id, info in result["games"].items():
        add(
            "  {:<28} {:>6} 笔   首 {}  末 {}  跨度 {}".format(
                game_id,
                info["state_requests"],
                info["first_wall_utc"] or "-",
                info["last_wall_utc"] or "-",
                _fmt(info["span_seconds"], 1, "s"),
            )
        )

    add("")
    add("--- purpose=sse_settled_long_poll 相邻间隔 ---")
    long_poll = result["long_poll"]
    overall = long_poll["overall_gap_seconds"]
    add(
        "总计 {} 笔；全局间隔 p50={} p90={} max={}（秒，{} 个间隔）".format(
            long_poll["requests"],
            _fmt(overall["p50"]),
            _fmt(overall["p90"]),
            _fmt(overall["max"]),
            overall["count"],
        )
    )
    for game_id, info in long_poll["by_game"].items():
        gaps = info["gap_seconds"]
        add(
            "  {:<28} {:>4} 笔  间隔 p50={} p90={} max={}（{} 个间隔）".format(
                game_id,
                info["requests"],
                _fmt(gaps["p50"]),
                _fmt(gaps["p90"]),
                _fmt(gaps["max"]),
                gaps["count"],
            )
        )

    add("")
    add("--- 全部 http_status >= 400 明细（含“前 1.05s 已获准 state 笔数”归因） ---")
    header = "{:<12} {:>5} {:<22} {:<44} {:>10} {:>12}  {}".format(
        "wall(UTC)", "状态", "error_type", "endpoint", "排队ms", "前1.05s获准", "purpose/game"
    )
    add(header)
    add("-" * len(header))
    for item in result["http_errors"]:
        add(
            "{:<12} {:>5} {:<22} {:<44} {:>10} {:>12}  {}".format(
                item["wall_clock_utc"] or "-",
                item["http_status"],
                str(item["error_type"])[:22],
                item["endpoint"][:44],
                _fmt(item["queue_delay_ms"]),
                "-" if item["granted_state_requests_in_prior_1_05s"] is None else item[
                    "granted_state_requests_in_prior_1_05s"
                ],
                f"{item['purpose']}/{item['game_id']}",
            )
        )
    if not result["http_errors"]:
        add("  （无）")

    add("")
    add("--- 决策密度比值 ---")
    density = result["decision_density"]
    add(
        "state 请求 {} / decision_input {} = {} ；/ distinct(game_id, round_no) {} = {}".format(
            density["state_requests"],
            density["decision_inputs"],
            _fmt(density["state_per_decision"], 3),
            density["distinct_game_rounds"],
            _fmt(density["state_per_game_round"], 3),
        )
    )

    add("")
    add("--- kind 计数 ---")
    for kind, count in result["kind_counts"].items():
        add(f"  {kind:<24} {count}")
    add("")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    """命令行入口：分析一个 decisions.jsonl 并打印/落盘汇总。"""
    parser = argparse.ArgumentParser(
        description="只读分析 decisions.jsonl 中的 state 查询排队与限速（429）根因",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("decisions_jsonl", help="participants/<pid>/decisions.jsonl 路径")
    parser.add_argument("--json-out", dest="json_out", default=None, help="机器可读 JSON 汇总输出路径")
    parser.add_argument("--top", dest="top_n", type=int, default=DEFAULT_TOP, help="排队延迟 Top N（默认 25）")
    args = parser.parse_args(argv)

    result = analyze(args.decisions_jsonl, top_n=args.top_n)
    print(render_report(result))

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2, sort_keys=False)
            handle.write("\n")
        print(f"[json] 汇总已写入 {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
