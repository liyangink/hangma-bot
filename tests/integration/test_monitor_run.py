"""monitor_run.py 纯函数与 --once 快照契约：raw/ 目录纳入活跃度统计。

背景（d6 返工登记项）：原始事件（RAW_PROTOCOL_STATE）按场落在
participants/<pid>/raw/<game>.jsonl（可选 .NNNNN.jsonl.gz 分段轮转）。
打牌间歇动作流静止时只有 /state 轮询原文在写；监控若不扫 raw/ 会把
运行误判为"审计停摆"。本文件锁定：
- _collect 的"最近写入时间"统计（记录墙钟 last_record_at 与文件
  mtime）覆盖 raw/*.jsonl 与 raw/*.jsonl.gz（gzip 透明解压读取）；
- 损坏/截断 gzip 段不使监控崩溃（最终完整性由离线验证器把关）；
- 输出格式与脱敏纪律不变：快照行不含 Token/Authorization 形态内容。

与 tests/integration 既有脚本测试同布局：importlib 加载脚本模块，
只测纯函数路径与一次性快照，不启动真实进程。
"""

import gzip
import importlib.util
import json
import sys
import time
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location("hangma_scripts_" + name, SCRIPTS_DIR / name)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


monitor = _load_script("monitor_run.py")


# ---- 造目录小工具 -------------------------------------------------------

def _envelope(kind: str, wall_ms: int, payload: dict | None = None) -> dict:
    """最小编信封：monitor 只消费 kind/payload/context/wall_time_unix_ms。"""

    return {
        "schema_version": 1,
        "kind": kind,
        "context": {
            "run_id": "run-1",
            "tournament_id": "t-1",
            "participant_id": "P1",
            "stage_attempt_id": "st-1",
            "game_id": "G1",
        },
        "wall_time_unix_ms": wall_ms,
        "monotonic_ns": 1,
        "payload": payload if payload is not None else {},
    }


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_gzip(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    path.write_bytes(gzip.compress(payload.encode("utf-8")))


def _running_run(base: Path) -> Path:
    """最小 running 运行目录：lifecycle 置 running，无任何 raw 写入。"""

    run = base / "run-1"
    _write_jsonl(
        run / "lifecycle.jsonl",
        [_envelope("lifecycle_changed", 1_000, {"event": "status_changed", "to": "running"})],
    )
    return run


# ---- 用例 ---------------------------------------------------------------

def test_collect_tracks_recency_of_plain_raw_jsonl(tmp_path):
    """raw/<game>.jsonl 的记录墙钟与文件 mtime 计入活跃度统计。"""

    run = _running_run(tmp_path)
    raw_path = run / "participants" / "P1" / "raw" / "G1.jsonl"
    # 打牌间歇形态：只有 /state 轮询原文新落盘（墙钟远新于 lifecycle）
    _write_jsonl(raw_path, [_envelope("raw_protocol_state", 9_000)])

    info = monitor._collect(run)
    assert info["last_record_at"] == 9.0  # raw 记录墙钟被采纳（旧实现只到 1.0）
    assert info["last_file_mtime"] == raw_path.stat().st_mtime
    # raw 记录不参与动作统计、也不因 context.game_id 误入场次集合
    assert info["games"] == set()
    assert info["intent_count"] == 0
    assert info["participant"] == "P1"


def test_collect_tracks_recency_of_gzip_raw_segments(tmp_path):
    """raw/*.NNNNN.jsonl.gz 分段透明解压：记录墙钟与 mtime 一并统计。"""

    run = _running_run(tmp_path)
    seg = run / "participants" / "P1" / "raw" / "G1.00001.jsonl.gz"
    _write_gzip(seg, [_envelope("raw_protocol_state", 1_700_000)])

    info = monitor._collect(run)
    assert info["last_record_at"] == 1700.0
    assert info["last_file_mtime"] == seg.stat().st_mtime


def test_collect_tolerates_truncated_or_corrupt_gzip_segment(tmp_path):
    """截断/非 gzip 的 raw 段不得让监控崩溃：容错跳过，其余文件照常统计。"""

    run = _running_run(tmp_path)
    raw_dir = run / "participants" / "P1" / "raw"
    # 截断段：进程被杀、无 gzip 尾部（读取尾部抛 EOFError 的实证形态）
    raw_dir.mkdir(parents=True, exist_ok=True)
    full = gzip.compress(
        (json.dumps(_envelope("raw_protocol_state", 2_000), ensure_ascii=False) + "\n").encode("utf-8")
    )
    (raw_dir / "G1.00002.jsonl.gz").write_bytes(full[: len(full) // 2])
    # 非 gzip 内容：头部即坏，读取时抛 BadGzipFile（OSError 子类）
    (raw_dir / "G2.00001.jsonl.gz").write_bytes(b"not a gzip stream")
    # 健康 raw 文件仍必须被读到
    _write_jsonl(raw_dir / "G3.jsonl", [_envelope("raw_protocol_state", 3_000)])

    info = monitor._collect(run)
    assert info["last_record_at"] == 3.0
    assert info["status"] == "running"


def test_collect_corrupt_raw_gz_alone_returns_partial_info(tmp_path):
    """只有损坏 gz 的 raw 目录也不抛异常，返回部分信息（容错承诺）。"""

    run = _running_run(tmp_path)
    seg = run / "participants" / "P1" / "raw" / "G1.00001.jsonl.gz"
    seg.parent.mkdir(parents=True, exist_ok=True)
    seg.write_bytes(gzip.compress(b"\x00\x01" * 64))

    info = monitor._collect(run)
    assert info["last_record_at"] == 1.0  # 只来自 lifecycle 记录
    assert info["status"] == "running"


def test_main_once_reports_raw_only_recent_run_without_stall(capsys, tmp_path):
    """端到端快照：raw 原文在写即"审计流有新记录"，running 不误报停摆。"""

    run = _running_run(tmp_path)
    now_ms = int(time.time() * 1000)
    # 打牌间歇：本 tick 内只有 raw/ 收到新的 /state 轮询原文
    _write_jsonl(
        run / "participants" / "P1" / "raw" / "G1.jsonl",
        [_envelope("raw_protocol_state", now_ms)],
    )

    rc = monitor.main(["--run-dir", str(run), "--once"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "状态=running" in out
    assert "审计停滞=" in out
    assert "[ALARM]" not in out  # raw 活跃即非停摆；输出格式与升级前一致
