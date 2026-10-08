"""analyze_state_queue.py 的合成数据回归测试。

被测脚本是只读分析器（review/wiring-queue-rootcause-2026-09-25/analyze_state_queue.py），
这里用 tmp_path 构造小的合成 decisions.jsonl，覆盖：
200 正常、429、多 purpose、多优先级、多 game、started+finished 成对记录、
缺 queued_at 的非 state 端点（GET /api/me、POST .../action）、finished-only 的 state 记录、
以及损坏行。

合成数据的单调时钟单位是秒，锚点固定为 monotonic=1000.060 s <-> Unix 1700000000000 ms
（2023-11-14T22:13:20.000Z），因此 wall clock 断言可以直接手算：
  wall_ms = 1700000000000 + (transport - 1000.060) * 1000。
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'tests/review'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = _project_file(_PROJECT_ROOT, REPO_ROOT / "review" / "wiring-queue-rootcause-2026-09-25" / "analyze_state_queue.py")

ANCHOR_TRANSPORT_S = 1000.060
ANCHOR_WALL_MS = 1_700_000_000_000
WINDOW_1_00 = "1.00"
WINDOW_1_05 = "1.05"


def _wall_ms(transport_s: float) -> int:
    """按锚点把手算的单调秒换算成 Unix 毫秒（与脚本的线性换算口径一致）。"""
    return ANCHOR_WALL_MS + round((transport_s - ANCHOR_TRANSPORT_S) * 1000)


@pytest.fixture(scope="module")
def analyzer():
    """从 review 目录加载被测脚本（该目录不是包，只能用 spec_from_file_location）。"""
    spec = importlib.util.spec_from_file_location("analyze_state_queue_under_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------------------
# 合成数据构造
# --------------------------------------------------------------------------------------

# (request_id, game_id, purpose, priority, seq, queued, granted, transport, http_status)
STATE_REQUESTS = [
    ("A", "g1", "sse_frame", "RECOVERY", 0, 1000.000, 1000.050, 1000.060, 200),  # 排队 50ms
    ("B", "g1", "sse_frame", "RECOVERY", 1, 1000.100, 1000.150, 1000.160, 200),  # 排队 50ms
    ("G", "g1", "sse_frame", "RECOVERY", 2, 1000.600, 1000.620, 1000.630, 200),  # 排队 20ms
    ("H", "g1", "sse_frame", "RECOVERY", 3, 1000.800, 1000.830, 1000.840, 200),  # 排队 30ms
    ("I", "g1", "sse_frame", "RECOVERY", 4, 1001.000, 1001.060, 1001.070, 200),  # 排队 60ms
    ("C", "g2", "current_state_sync", "POLL", 5, 1001.500, 1001.700, 1001.760, 429),  # 排队 200ms
    ("D", "g2", "current_state_sync", "POLL", 6, 1001.600, 1001.900, 1001.960, 200),  # 排队 300ms
    ("E", "g1", "sse_settled_long_poll", "RECOVERY", 7, 1003.000, 1003.010, 1003.020, 200),  # 排队 10ms
    ("F", "g2", "sse_settled_long_poll", "RECOVERY", 8, 1004.000, 1004.400, 1004.500, 200),  # 排队 400ms
    ("J", "g1", "sse_settled_long_poll", "RECOVERY", 9, 1005.000, 1005.020, 1005.030, 200),  # 排队 20ms
    ("K", "g2", "sse_frame", "DRAW_WATCH", 10, 1006.000, 1006.100, 1006.120, 200),  # 排队 100ms
]

# 非 state 端点：没有 queued_at/granted_at，只有 transport_started_at_monotonic
# (request_id, endpoint, method, transport, http_status, error_type)
PLAIN_REQUESTS = [
    ("N1", "GET /api/me", "GET", 1000.500, 200, None),
    ("N2", "GET /api/me", "GET", 1002.500, 404, "NotFoundError"),
    ("N3", "POST /api/games/g1/action", "POST", 1000.700, 200, None),
]


def _base_record(kind: str, request_id: str, endpoint: str, method: str, transport: float, game_id=None) -> dict:
    """造一条 http_request 记录骨架，字段名与真实审计保持一致。"""
    return {
        "schema_version": 1,
        "kind": kind,
        "context": {
            "run_id": "run-synth",
            "tournament_id": "t_synth",
            "participant_id": "u_synth",
            "game_id": game_id,
            "round_no": 1 if game_id else None,
            "trigger_seq": None,
            "decision_id": None,
            "attempt_no": None,
        },
        "wall_time_unix_ms": _wall_ms(transport),
        "monotonic_ns": int(transport * 1_000_000_000),
        "payload": {
            "request_id": request_id,
            "endpoint": endpoint,
            "method": method,
            "params": {},
            "body": {},
            "phase": "started",
            "request_timing": {"request_id": request_id, "transport_started_at_monotonic": transport},
        },
    }


def _state_records(request_id, game_id, purpose, priority, seq, queued, granted, transport, status) -> list:
    """造一对 started/finished state 请求记录（finished 带 http_status/error_type）。"""
    endpoint = f"GET /api/games/{game_id}/state"
    started = _base_record("http_request", request_id, endpoint, "GET", transport, game_id=game_id)
    timing = started["payload"]["request_timing"]
    timing.update(
        {
            "queued_at_monotonic": queued,
            "granted_at_monotonic": granted,
            "query_purpose": purpose,
            "query_origin": purpose,
            "scheduler_priority": priority,
            "started_wall_unix_ms": _wall_ms(transport),
        }
    )
    started["payload"]["params"] = {"seq": seq}

    finished = _base_record(
        "http_request", request_id, endpoint, "GET", transport + 0.010, game_id=game_id
    )
    finished["payload"]["phase"] = "finished"
    finished["payload"]["params"] = {"seq": seq}
    finished["payload"]["http_status"] = status
    finished["payload"]["outcome"] = "error" if status >= 400 else "response"
    finished["payload"]["error_type"] = "RateLimitedError" if status == 429 else None
    finished["payload"]["request_timing"] = dict(timing)
    finished["payload"]["request_timing"]["completed_at_monotonic"] = transport + 0.010
    finished["payload"]["request_timing"]["outcome"] = finished["payload"]["outcome"]
    finished["payload"]["request_timing"]["error_type"] = finished["payload"]["error_type"]
    return [started, finished]


def _plain_records(request_id, endpoint, method, transport, status, error_type) -> list:
    """造一对非 state 请求记录：request_timing 里只有 transport_started_at_monotonic。"""
    started = _base_record("http_request", request_id, endpoint, method, transport)
    finished = _base_record("http_request", request_id, endpoint, method, transport + 0.005)
    finished["payload"]["phase"] = "finished"
    finished["payload"]["http_status"] = status
    finished["payload"]["outcome"] = "error" if status >= 400 else "response"
    finished["payload"]["error_type"] = error_type
    finished["payload"]["request_timing"] = dict(started["payload"]["request_timing"])
    finished["payload"]["request_timing"]["completed_at_monotonic"] = transport + 0.005
    return [started, finished]


def _decision_input(game_id, round_no, decision_id) -> dict:
    """造一条 decision_input 记录（只取 context 里的 game_id/round_no）。"""
    return {
        "schema_version": 1,
        "kind": "decision_input",
        "context": {
            "run_id": "run-synth",
            "tournament_id": "t_synth",
            "participant_id": "u_synth",
            "game_id": game_id,
            "round_no": round_no,
            "trigger_seq": 0,
            "decision_id": decision_id,
        },
        "wall_time_unix_ms": _wall_ms(1001.0),
        "monotonic_ns": 1_001_000_000_000,
        "payload": {"plan_revision": 1},
    }


@pytest.fixture()
def synthetic_jsonl(tmp_path: Path) -> Path:
    """写一份覆盖全部断言点的合成 decisions.jsonl，返回路径。"""
    records: list = [
        {
            "schema_version": 1,
            "kind": "authoritative_state",
            "context": {"run_id": "run-synth"},
            "wall_time_unix_ms": _wall_ms(ANCHOR_TRANSPORT_S),
            "monotonic_ns": int(ANCHOR_TRANSPORT_S * 1_000_000_000),
            "payload": {"status": "registering"},
        }
    ]
    for spec in STATE_REQUESTS:
        records.extend(_state_records(*spec))
    for spec in PLAIN_REQUESTS:
        records.extend(_plain_records(*spec))
    records.append(_decision_input("g1", 1, "dec-1"))
    records.append(_decision_input("g1", 1, "dec-2"))  # 同一 (game_id, round_no)
    records.append(_decision_input("g2", 2, "dec-3"))
    records.append({"schema_version": 1, "kind": "participant_finished", "context": {}, "payload": {}})

    path = tmp_path / "decisions.jsonl"
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    return path


def _group(result: dict, purpose: str, priority: str) -> dict:
    """按 (purpose, priority) 取分组结果。"""
    for group in result["groups"]:
        if group["purpose"] == purpose and group["priority"] == priority:
            return group
    raise AssertionError(f"未找到分组 {purpose}/{priority}：{[g['purpose'] + '/' + g['priority'] for g in result['groups']]}")


# --------------------------------------------------------------------------------------
# 断言
# --------------------------------------------------------------------------------------


def test_state_请求计数与状态码分布(analyzer, synthetic_jsonl):
    """只统计 GET + /state 结尾的请求；非 state 端点与其它 kind 不得混入。"""
    result = analyzer.analyze(str(synthetic_jsonl))

    state = result["state_requests"]
    assert state["total"] == len(STATE_REQUESTS) == 11
    assert state["started_records"] == 11
    assert state["finished_records"] == 11
    assert state["http_status"] == {"200": 10, "429": 1}
    assert state["http_429_count"] == 1
    assert state["missing_queue_timing"] == 0
    assert result["lines"]["malformed"] == 0
    assert result["kind_counts"]["decision_input"] == 3
    # 非 state 端点（/api/me、POST action）不应出现在任何分组里
    endpoints = {group["purpose"] for group in result["groups"]}
    assert endpoints == {
        "sse_frame",
        "current_state_sync",
        "sse_settled_long_poll",
    }


def test_分组的排队与传输延迟百分位(analyzer, synthetic_jsonl):
    """按 (query_purpose, scheduler_priority) 交叉分组的延迟百分位（最近秩）。"""
    result = analyzer.analyze(str(synthetic_jsonl))

    frame_recovery = _group(result, "sse_frame", "RECOVERY")
    assert frame_recovery["requests"] == 5
    assert frame_recovery["queue_delay_ms"]["p50"] == pytest.approx(50.0)
    assert frame_recovery["queue_delay_ms"]["p90"] == pytest.approx(60.0)
    assert frame_recovery["queue_delay_ms"]["p99"] == pytest.approx(60.0)
    assert frame_recovery["queue_delay_ms"]["max"] == pytest.approx(60.0)
    assert frame_recovery["transport_ms"]["p50"] == pytest.approx(10.0)
    assert frame_recovery["transport_ms"]["p99"] == pytest.approx(10.0)
    assert frame_recovery["http_status"] == {"200": 5}
    assert frame_recovery["http_429_count"] == 0

    sync_poll = _group(result, "current_state_sync", "POLL")
    assert sync_poll["requests"] == 2
    assert sync_poll["queue_delay_ms"]["p50"] == pytest.approx(200.0)
    assert sync_poll["queue_delay_ms"]["p90"] == pytest.approx(300.0)
    assert sync_poll["queue_delay_ms"]["max"] == pytest.approx(300.0)
    assert sync_poll["transport_ms"]["p50"] == pytest.approx(60.0)
    assert sync_poll["transport_ms"]["p99"] == pytest.approx(60.0)
    assert sync_poll["http_status"] == {"200": 1, "429": 1}
    assert sync_poll["http_429_count"] == 1

    long_poll = _group(result, "sse_settled_long_poll", "RECOVERY")
    assert long_poll["requests"] == 3
    assert long_poll["queue_delay_ms"]["p50"] == pytest.approx(20.0)
    assert long_poll["queue_delay_ms"]["p90"] == pytest.approx(400.0)
    assert long_poll["queue_delay_ms"]["max"] == pytest.approx(400.0)
    assert long_poll["transport_ms"]["p50"] == pytest.approx(10.0)
    assert long_poll["transport_ms"]["p99"] == pytest.approx(100.0)

    # 同一 purpose 的不同 priority 必须分成两组
    frame_watch = _group(result, "sse_frame", "DRAW_WATCH")
    assert frame_watch["requests"] == 1
    assert frame_watch["queue_delay_ms"]["p50"] == pytest.approx(100.0)


def test_滚动窗口与直方图(analyzer, synthetic_jsonl):
    """1.00s / 1.05s 窗口内的最大获准笔数与完整直方图；窗口两端都算。"""
    result = analyzer.analyze(str(synthetic_jsonl))
    rolling = result["rolling_window"]

    # 1.00s：A 起点 [1000.060, 1001.060] 命中 A/B/G/H；1.05s：多命中 I（1001.070）
    assert rolling[WINDOW_1_00]["max"] == 4
    assert rolling[WINDOW_1_05]["max"] == 5

    hist_100 = rolling[WINDOW_1_00]["histogram"]
    hist_105 = rolling[WINDOW_1_05]["histogram"]
    assert hist_100 == {"1": 4, "2": 2, "3": 3, "4": 2}
    assert hist_105 == {"1": 4, "2": 2, "3": 3, "4": 1, "5": 1}
    # 每个获准时刻都是一个窗口起点
    assert sum(int(v) for v in hist_100.values()) == 11
    assert sum(int(v) for v in hist_105.values()) == 11
    assert rolling[WINDOW_1_05]["windows"] == 11

    # 边界：D(1001.960) 与 E(1003.020) 相差恰好 1.060s，
    # 在 1.05s 窗口里 D 只能覆盖自己（起点 1001.960 的上界是 1003.010 < 1003.020）。
    assert hist_105["2"] == 2  # 只有 C->D 与 F->J 这两对贴得够近


def test_每秒直方图(analyzer, synthetic_jsonl):
    """按 transport_started 取整秒的每秒请求数。"""
    result = analyzer.analyze(str(synthetic_jsonl))
    per_second = result["per_second"]

    counts = {bucket["monotonic_floor_s"]: bucket["count"] for bucket in per_second["buckets"]}
    assert counts == {1000: 4, 1001: 3, 1003: 1, 1004: 1, 1005: 1, 1006: 1}
    assert per_second["max"] == 4
    assert per_second["span_seconds"] == 7
    assert per_second["bucket_count"] == 6
    assert per_second["total"] == 11
    assert [b["offset_s"] for b in per_second["buckets"]] == [0, 1, 3, 4, 5, 6]


def test_排队延迟Top与wall_clock换算(analyzer, synthetic_jsonl):
    """Top 25 排序、字段完整性与锚点线性的 wall clock 换算。"""
    result = analyzer.analyze(str(synthetic_jsonl))
    top = result["top_queue_delay"]

    assert [item["request_id"] for item in top] == ["F", "D", "C", "K", "I", "A", "B", "H", "G", "J", "E"]
    first = top[0]
    assert first["purpose"] == "sse_settled_long_poll"
    assert first["priority"] == "RECOVERY"
    assert first["seq"] == 8
    assert first["game_id"] == "g2"
    assert first["queue_delay_ms"] == pytest.approx(400.0)
    assert first["http_status"] == 200
    # F 的 transport=1004.500 -> 1700000000000 + 4440 ms = 2023-11-14T22:13:24.440Z
    assert first["wall_clock_utc"] == "22:13:24.440"

    # C：transport 1001.760 -> +1700 ms -> 22:13:21.700
    assert top[2]["wall_clock_utc"] == "22:13:21.700"
    assert result["wall_anchor"]["source"] == "request_timing.started_wall_unix_ms"
    assert result["wall_anchor"]["monotonic_s"] == pytest.approx(ANCHOR_TRANSPORT_S)
    assert result["wall_anchor"]["wall_iso_utc"] == "2023-11-14T22:13:20.000Z"


def test_每game计数与long_poll间隔(analyzer, synthetic_jsonl):
    """每 game_id 的 state 请求数与 sse_settled_long_poll 相邻间隔分布。"""
    result = analyzer.analyze(str(synthetic_jsonl))

    games = result["games"]
    assert games["g1"]["state_requests"] == 7
    assert games["g2"]["state_requests"] == 4

    long_poll = result["long_poll"]
    assert long_poll["requests"] == 3
    # 全局间隔：1004.500-1003.020 = 1.480s；1005.030-1004.500 = 0.530s -> 排序 [0.530, 1.480]
    overall = long_poll["overall_gap_seconds"]
    assert overall["count"] == 2
    assert overall["p50"] == pytest.approx(0.530, abs=1e-6)
    assert overall["p90"] == pytest.approx(1.480, abs=1e-6)
    assert overall["max"] == pytest.approx(1.480, abs=1e-6)
    # g1 内部间隔：1005.030-1003.020 = 2.010s；g2 只有 1 笔没有间隔
    assert long_poll["by_game"]["g1"]["requests"] == 2
    assert long_poll["by_game"]["g1"]["gap_seconds"]["max"] == pytest.approx(2.010, abs=1e-6)
    assert long_poll["by_game"]["g2"]["gap_seconds"]["count"] == 0
    assert long_poll["by_game"]["g2"]["gap_seconds"]["p50"] is None


def test_http错误明细与429归因(analyzer, synthetic_jsonl):
    """http_status>=400 逐条列出，并给出 transport_started 前 1.05s 已获准的 state 笔数。"""
    result = analyzer.analyze(str(synthetic_jsonl))

    errors = result["http_errors"]
    assert len(errors) == 2  # state 的 429 + 非 state 的 404
    assert [item["http_status"] for item in errors] == [429, 404]

    limited = errors[0]
    assert limited["request_id"] == "C"
    assert limited["endpoint"] == "GET /api/games/g2/state"
    assert limited["error_type"] == "RateLimitedError"
    assert limited["is_state_request"] is True
    assert limited["queue_delay_ms"] == pytest.approx(200.0)
    assert limited["wall_clock_utc"] == "22:13:21.700"
    # C 的 transport=1001.760，前 1.05s 即 [1000.710, 1001.760)：只有 H(1000.840)、I(1001.070)
    assert limited["granted_state_requests_in_prior_1_05s"] == 2

    not_found = errors[1]
    assert not_found["request_id"] == "N2"
    assert not_found["is_state_request"] is False
    assert not_found["queue_delay_ms"] is None  # 非 state 端点没有 queued_at/granted_at
    # N2 的 transport=1002.500，前 1.05s 即 [1001.450, 1002.500)：C(1001.760)、D(1001.960)
    assert not_found["granted_state_requests_in_prior_1_05s"] == 2


def test_决策密度比值(analyzer, synthetic_jsonl):
    """state 请求数 / decision_input 数与 / distinct(game_id, round_no) 数。"""
    result = analyzer.analyze(str(synthetic_jsonl))
    density = result["decision_density"]

    assert density["state_requests"] == 11
    assert density["decision_inputs"] == 3
    assert density["distinct_game_rounds"] == 2  # (g1,1) 重复两次
    assert density["state_per_decision"] == pytest.approx(11 / 3)
    assert density["state_per_game_round"] == pytest.approx(5.5)


def test_命令行json输出与文本报告(analyzer, synthetic_jsonl, tmp_path, capsys):
    """main() 打印文本报告，--json-out 落盘机器可读汇总且内容与 API 一致。"""
    out_path = tmp_path / "summary.json"
    exit_code = analyzer.main([str(synthetic_jsonl), "--json-out", str(out_path)])

    assert exit_code == 0
    text = capsys.readouterr().out
    assert "state 请求（GET + endpoint 以 /state 结尾）: 11" in text
    assert "窗口 1.05s：最大 5 笔" in text
    assert "sse_settled_long_poll" in text
    assert "state 请求 11 / decision_input 3" in text

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["state_requests"]["total"] == 11
    assert payload["state_requests"]["http_429_count"] == 1
    assert payload["rolling_window"][WINDOW_1_05]["max"] == 5
    assert payload["top_queue_delay"][0]["request_id"] == "F"
    assert payload["decision_density"]["state_per_game_round"] == pytest.approx(5.5)
    # JSON 必须可序列化且无 NaN/Infinity
    assert "NaN" not in out_path.read_text(encoding="utf-8")


def test_finished_only与损坏行的容错(analyzer, tmp_path):
    """finished-only 的 state 记录仍计入请求数，但缺 queued_at 时不计入延迟统计。"""
    only_finished = _base_record(
        "http_request", "Z1", "GET /api/games/g9/state", "GET", 2000.000, game_id="g9"
    )
    only_finished["payload"]["phase"] = "finished"
    only_finished["payload"]["http_status"] = 200
    only_finished["payload"]["params"] = {"seq": 3}
    only_finished["payload"]["request_timing"] = {
        "request_id": "Z1",
        "transport_started_at_monotonic": 2000.000,
        "query_purpose": "sse_frame",
        "scheduler_priority": "RECOVERY",
        "completed_at_monotonic": 2000.020,
    }

    path = tmp_path / "edge.jsonl"
    path.write_text(
        json.dumps(only_finished, ensure_ascii=False) + "\n" + "{不是合法 JSON\n",
        encoding="utf-8",
    )

    result = analyzer.analyze(str(path))
    assert result["lines"]["total"] == 2
    assert result["lines"]["malformed"] == 1
    assert result["state_requests"]["total"] == 1
    assert result["state_requests"]["started_records"] == 0
    assert result["state_requests"]["finished_records"] == 1
    assert result["state_requests"]["missing_queue_timing"] == 1
    assert result["http_errors"] == []

    group = _group(result, "sse_frame", "RECOVERY")
    assert group["requests"] == 1
    assert group["queue_delay_ms"]["count"] == 0
    assert group["queue_delay_ms"]["p50"] is None
    # 该记录本身提供了锚点（无 started_wall_unix_ms 时退化为记录 wall_time_unix_ms）
    assert result["wall_anchor"]["source"] == "record.wall_time_unix_ms"
    assert result["wall_anchor"]["monotonic_s"] == pytest.approx(2000.000)
