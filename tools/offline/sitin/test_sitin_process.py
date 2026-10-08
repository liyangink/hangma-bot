"""受监管进程执行的回归（REVIEW-8 S8-2）。

两条反例都来自阶段二第八轮复核：

1. **后代忽略 TERM**：组长收到 TERM 后退出、后代忽略 TERM 时，
   初版"只看组长是否还活着"就不发 KILL，随后无超时的 `communicate()`
   继续等后代持有的管道——实测配置 0.5 秒、宽限 5 秒，**8.041 秒**后才返回，
   输出里写着后代是 `CHILD_NATURAL_EXIT`。
2. **输出无界**：收集不设上限时，一个疯狂打印的子进程会把父进程内存吃光。
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/tools'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import importlib.util
import sys
import time
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

spec = importlib.util.spec_from_file_location("sitin_process", _project_file(_PROJECT_ROOT, _HERE / "sitin_process.py"))
guard = importlib.util.module_from_spec(spec)
sys.modules["sitin_process"] = guard
assert spec.loader is not None
spec.loader.exec_module(guard)


def test_simple_command_returns_output_and_rc(tmp_path):
    result = guard.run_supervised([sys.executable, "-c", "print('hi')"], cwd=tmp_path,
                                  timeout_sec=30)
    assert result.timed_out is False
    assert result.returncode == 0
    assert result.stdout.strip() == "hi"
    assert result.group_still_alive is False


def test_infinite_loop_is_killed_within_the_deadline(tmp_path):
    """纯计算死循环：必须**由监管方**终止，而不是等它自己结束。"""

    started = time.monotonic()
    result = guard.run_supervised(
        [sys.executable, "-c", "while True: pass"], cwd=tmp_path,
        timeout_sec=0.5, grace_sec=1.0)
    elapsed = time.monotonic() - started
    assert result.timed_out is True
    assert elapsed < 10.0
    assert result.group_still_alive is False


def test_grandchild_ignoring_term_is_killed_anyway(tmp_path):
    """★ 审查反例：组长退出 ≠ 后代退出；**不许**把"组长已回收"当成"全组结束"。

    探针：组长派生一个忽略 TERM、睡 8 秒的后代；组长自己收到 TERM 后立刻退出。
    初版因此跳过 KILL，并一直等到后代自然退出（8.041 秒）。
    """

    probe = tmp_path / "probe.py"
    probe.write_text(
        "import signal, subprocess, sys, time\n"
        "subprocess.Popen([sys.executable, '-c',\n"
        "    \"import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN);\"\n"
        "    \"print('CHILD_READY', flush=True); time.sleep(8);\"\n"
        "    \"print('CHILD_NATURAL_EXIT', flush=True)\"])\n"
        "def on_term(signum, frame):\n"
        "    print('LEADER_GOT_TERM', flush=True)\n"
        "    sys.exit(0)\n"
        "signal.signal(signal.SIGTERM, on_term)\n"
        "print('LEADER_READY', flush=True)\n"
        "while True:\n"
        "    time.sleep(0.1)\n",
        encoding="utf-8")
    started = time.monotonic()
    result = guard.run_supervised([sys.executable, str(probe)], cwd=tmp_path,
                                  timeout_sec=0.5, grace_sec=1.0)
    elapsed = time.monotonic() - started
    assert result.timed_out is True
    assert result.group_still_alive is False
    assert "KILL" in result.signals_sent, "组长退出后仍必须对**整组**补 KILL"
    assert "CHILD_NATURAL_EXIT" not in result.stdout
    # 1 秒宽限 + 收尾：远小于后代的 8 秒自然睡眠
    assert elapsed < 6.0, elapsed


def test_output_is_bounded(tmp_path):
    """收集有上限：超出部分丢弃，但子进程不能被管道写满卡住。"""

    result = guard.run_supervised(
        [sys.executable, "-c",
         "import sys\n"
         "chunk = 'x' * 4096\n"
         "for _ in range(2000):\n"
         "    sys.stdout.write(chunk)\n"],
        cwd=tmp_path, timeout_sec=60, max_output_chars=10_000)
    assert result.timed_out is False
    assert result.returncode == 0
    assert len(result.stdout) <= 10_000
    assert result.output_truncated is True


def test_result_json_is_serialisable(tmp_path):
    result = guard.run_supervised([sys.executable, "-c", "print('ok')"], cwd=tmp_path,
                                  timeout_sec=30)
    payload = result.to_json()
    assert payload["timed_out"] is False
    assert payload["signals_sent"] == []
    assert "stdout_tail" in payload
