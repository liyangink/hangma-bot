"""受监管的进程执行：墙钟上限 + **进程组**终止 + 有界输出收集。

## 为什么必须是**共用**入口（REVIEW-8 S8-2）

门禁与桌赛执行都要跑"离线生成的任意候选代码"。两处各写一份终止逻辑，
就会出现两份不同的缺陷——初版正是如此：

1. **门禁根本没有隔离**：G-1/G-2 在**当前进程**直接执行候选。一个纯计算的
   `while True` 候选把门禁本身挂住，连"真实时钟检查"都没有执行机会；
   审查探针是靠**额外**加的外部两秒监管才把它清掉的。
2. **调度器只等待直接子进程**：组长收到 TERM 后退出、而后代忽略 TERM 时，
   `if process.poll() is None` 为假 ⇒ **不会进入发 KILL 的分支**，
   随后无超时的 `communicate()` 继续等后代持有的输出管道。
   实测：配置超时 0.5 秒、宽限 5 秒，**8.041 秒**后才返回，
   并且输出里写着后代是 `CHILD_NATURAL_EXIT`（自然退出，不是被杀的）。

## 本模块的三条纪律

1. **立即记录组身份**：`start_new_session=True` 让子进程自成进程组，
   紧接着取 `os.getpgid(pid)` 存下来。**不能等到期后再取**——
   那时组长可能已经被回收，取不到组号，就会退化成"只杀直接子进程"。
2. **不以组长已退出作为全组结束的依据**：到期后对**整组**发 TERM，
   宽限期内轮询**组是否为空**（`killpg(pgid, 0)`），仍非空则**无条件**发 KILL。
3. **收输出有界**：用**读者线程**按上限收集，超出部分丢弃但继续排空
   （否则子进程会被管道写满阻塞），最后 join 也带超时；不依赖
   `communicate()` 的"读到 EOF 为止"语义。
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

import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

#: SIGTERM 之后给多久再无条件 SIGKILL。
DEFAULT_TERM_GRACE_SEC = 5.0
#: 每个流最多收集多少字符（超出丢弃；收集本身不会无界增长）。
DEFAULT_MAX_OUTPUT_CHARS = 200_000
#: 宽限轮询间隔。
_POLL_INTERVAL_SEC = 0.05
#: 收尾阶段（组已清空后）等待读者线程的上限。
_DRAIN_JOIN_SEC = 5.0


@dataclass(frozen=True)
class SupervisedResult:
    """一次受监管执行的完整结局；**必须能区分"被杀"与"自然退出"**。"""

    returncode: Optional[int]
    stdout: str
    stderr: str
    timed_out: bool
    elapsed_sec: float
    signals_sent: Tuple[str, ...]
    group_still_alive: bool
    output_truncated: bool

    def to_json(self) -> dict:
        return {
            "returncode": self.returncode,
            "timed_out": self.timed_out,
            "elapsed_sec": round(self.elapsed_sec, 3),
            "signals_sent": list(self.signals_sent),
            "group_still_alive": self.group_still_alive,
            "output_truncated": self.output_truncated,
            "stdout_tail": self.stdout[-2000:],
            "stderr_tail": self.stderr[-2000:],
        }


def _group_alive(pgid: int) -> bool:
    """进程组里是否还有成员；**用于判断"整组是否结束"，不看组长状态**。"""

    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True          # 存在但不可信号：仍算"还在"
    return True


def _signal_group(pgid: int, signum: int) -> bool:
    try:
        os.killpg(pgid, signum)
    except ProcessLookupError:
        return False
    return True


def _drain(stream, cap: int, sink: List[str], counter: List[int]) -> None:
    """按上限收集一个流；超出后继续排空但不再保留。"""

    kept = 0
    total = 0
    try:
        while True:
            chunk = stream.read(65536)
            if not chunk:
                break
            total += len(chunk)
            if kept < cap:
                piece = chunk[: cap - kept]
                sink.append(piece)
                kept += len(piece)
    except (OSError, ValueError):
        pass
    finally:
        counter[0] = total
        try:
            stream.close()
        except (OSError, ValueError):
            pass


def run_supervised(
    command: Sequence[str],
    *,
    cwd: Optional[Path] = None,
    timeout_sec: float,
    grace_sec: float = DEFAULT_TERM_GRACE_SEC,
    max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS,
    env: Optional[dict] = None,
) -> SupervisedResult:
    """在**受监管的进程组**里执行命令，返回结局；**到期必终止整组**。"""

    started = time.monotonic()
    process = subprocess.Popen(
        [str(item) for item in command],
        cwd=str(cwd) if cwd is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        start_new_session=True,
    )
    pgid = os.getpgid(process.pid)          # 立刻记录，组长被回收后就取不到了

    out_chunks: List[str] = []
    err_chunks: List[str] = []
    out_total = [0]
    err_total = [0]
    readers = [
        threading.Thread(target=_drain,
                         args=(process.stdout, max_output_chars, out_chunks, out_total),
                         daemon=True),
        threading.Thread(target=_drain,
                         args=(process.stderr, max_output_chars, err_chunks, err_total),
                         daemon=True),
    ]
    for reader in readers:
        reader.start()

    signals_sent: List[str] = []
    timed_out = False
    try:
        process.wait(timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        timed_out = True
        signals_sent.append("TERM")
        _signal_group(pgid, signal.SIGTERM)
        grace_deadline = time.monotonic() + grace_sec
        while time.monotonic() < grace_deadline:
            process.poll()
            if not _group_alive(pgid):
                break
            time.sleep(_POLL_INTERVAL_SEC)
        # **无条件**补 KILL：组长已退出不代表后代已退出。
        if _group_alive(pgid):
            signals_sent.append("KILL")
            _signal_group(pgid, signal.SIGKILL)
        try:
            process.wait(timeout=grace_sec)
        except subprocess.TimeoutExpired:
            pass

    for reader in readers:
        reader.join(timeout=_DRAIN_JOIN_SEC)

    return SupervisedResult(
        returncode=process.returncode,
        stdout="".join(out_chunks),
        stderr="".join(err_chunks),
        timed_out=timed_out,
        elapsed_sec=time.monotonic() - started,
        signals_sent=tuple(signals_sent),
        group_still_alive=_group_alive(pgid),
        output_truncated=(out_total[0] > max_output_chars
                          or err_total[0] > max_output_chars),
    )


def kill_group_of(pid: int, signum: int = signal.SIGKILL) -> bool:
    """测试与调用方清场用：按 pid 反查组并终止；组已不存在返回 False。"""

    try:
        pgid = os.getpgid(pid)
    except ProcessLookupError:
        return False
    return _signal_group(pgid, signum)


__all__ = [
    "DEFAULT_MAX_OUTPUT_CHARS",
    "DEFAULT_TERM_GRACE_SEC",
    "SupervisedResult",
    "kill_group_of",
    "run_supervised",
]
