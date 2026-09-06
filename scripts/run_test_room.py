"""官方测试房间四 Token 启动入口：四个隔离子进程，复用正式单身份入口。

拓扑（doc/implementation/modules/test-room-runner.md）：

```text
run_test_room.py
  ├─ 子进程 run_participant.py --slot A   （最多 config.M 场）
  ├─ 子进程 run_participant.py --slot B
  ├─ 子进程 run_participant.py --slot C
  └─ 子进程 run_participant.py --slot D
```

``config.M`` 是每个身份的同时场数，不是 Token 数。四个身份完全隔离：
各自子进程独享连接池、限速器、动作门状态与审计目录（audit_root/slot-X/）。

Token 安全：Token 只经环境变量 ``HM_IDENTITY_TOKEN`` 传给子进程，
不写入任何派生配置文件、命令行参数或本进程输出；身份重启会重新执行
``initialize()`` 的版本/身份/目标核对并从权威状态恢复，不复用内存命令。

房间配置 JSON 结构（示例）：

```jsonc
{
  "mode": "test_room",           // 固定；本入口只接受测试房间模式
  "base_url": "<官方平台基址>",
  "expected_tournament_id": "<目标赛事 id>",
  "known_guide_version": 15,
  "audit_root": "./room-runs",   // 每身份生成 audit_root/slot-{X}/runs/{run_id}/...
  "strategy": "weighted_heuristic",   // 可选
  "insecure_hosts": ["<官方内网主机>"], // 可选
  "identities": [                // 必须恰好四个；token 与 token_env 二选一
    {"slot": "A", "token": "...", "strategy": "weighted_heuristic_v1"},
    {"slot": "B", "token_env": "HM_ROOM_TOKEN_B"},
    {"slot": "C", "token_env": "HM_ROOM_TOKEN_C"},
    {"slot": "D", "token_env": "HM_ROOM_TOKEN_D"}
  ],
  "restart": {                   // 可选；重启预算
    "max_restarts": 2,           // 致命错误的有界重启次数（指数退避）
    "base_delay_seconds": 1.0,
    "factor": 2.0,
    "max_delay_seconds": 8.0,
    "finished_restart_delay_seconds": 2.0  // 跨轮续跑节奏（见守护语义）
  }
}
```

守护语义：

- 退出码 0 + 终态 tournament_finished：测试房间完赛一轮的正常出口，不消耗
  失败预算，按 finished_restart_delay_seconds 节奏重启新进程承接下一轮。
  新进程冷启动后 register+ready 一次即可等待下一轮（房间仍 finished 时
  存活轮询，不退出）；配合 application 跨轮复用分支与适配器的测试房间
  finished 快照透传，四身份可持续跨轮运行；
- 退出码 0 的其他终态（eliminated / tournament_closed / tournament_void）
  与 10（身份永久失败）都是该身份最终结果；
- 退出码 11（致命协议错误/异常）在 max_restarts 内按指数退避重启，
  耗尽后标记 restart_exhausted。一个身份失败不终止其余三个身份。
- 信号：本进程收到 SIGINT/SIGTERM 时立即向全部在途子进程转发同一信号
  （不等待其自然完赛一轮），并打断跨轮续跑/退避睡眠——shutdown 后
  绝不拉起新的子进程；子进程各自取消运行、冲刷审计后返回收尾。

退出码：0 = 四身份全部正常终态；1 = 至少一个身份失败或重启耗尽；
2 = 配置错误；130/143 = 收到信号（已向子进程转发并等待收尾）。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import signal
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional, Sequence


def _ensure_import_path() -> None:
    src = Path(__file__).resolve().parents[1] / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))


_ensure_import_path()

from hangma_bot.application.deadline import BoundedBackoff  # noqa: E402  编排级有界退避

TOKEN_ENV_VAR = "HM_IDENTITY_TOKEN"
RESULT_PREFIX = "RESULT "

EXIT_ROOM_OK = 0
EXIT_ROOM_FAILED = 1
EXIT_ROOM_USAGE = 2
EXIT_SIGINT = 130
EXIT_SIGTERM = 143

# 子进程退出码约定（与 run_participant.py 对齐）。
# 除 0（正常终态）与 10（身份永久失败）外，其余退出码（含 11 致命错误、
# 信号负值）都进入有界重启预算。
EXIT_CHILD_COMPLETED = 0
EXIT_CHILD_PERMANENT = 10

_ROOM_FIELDS = frozenset({
    "mode",
    "base_url",
    "expected_tournament_id",
    "known_guide_version",
    "audit_root",
    "strategy",
    "insecure_hosts",
    "identities",
    "restart",
    "sse_enabled",
})
_RESTART_FIELDS = frozenset({
    "max_restarts",
    "base_delay_seconds",
    "factor",
    "max_delay_seconds",
    "finished_restart_delay_seconds",
})


def _require_non_empty_str(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} 必须是非空字符串，得到 {value!r}")
    return value


def _require_positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} 必须是正整数，得到 {value!r}")
    return value


def _require_strategy(value: object) -> str:
    """校验启动器可装配的固定策略名；配置错误在启动子进程前报告。"""

    choices = ("weighted_heuristic", "weighted_heuristic_v1", "weighted_heuristic_v2", "safe_fallback", "claim_if_legal")
    if not isinstance(value, str) or value not in choices:
        raise ValueError("未知策略名；可用：" + " / ".join(choices))
    return value


@dataclass(frozen=True)
class IdentitySlot:
    """一个测试身份的槽位与已解析 Token；Token 绝不进入 repr/日志。"""

    slot: str
    token: str
    token_source: str  # "inline" 或 "env:<变量名>"；用于审计启动来源，不含 Token
    strategy: Optional[str] = None  # 未指定时继承房间策略；在本次进程生命周期内固定

    def __repr__(self) -> str:
        return f"IdentitySlot(slot={self.slot!r}, token=<redacted>, token_source={self.token_source!r})"


@dataclass(frozen=True)
class RoomRestart:
    """重启预算；标量参数，实例按需独立创建。

    两类重启语义分开：
    - 失败重启（max_restarts / base_delay_seconds / factor / max_delay_seconds）：
      致命错误/异常退出的有界指数退避，耗尽标记 restart_exhausted；
    - 跨轮续跑（finished_restart_delay_seconds）：测试房间完赛一轮的正常
      出口（exit 0 + tournament_finished）不消耗失败预算，按固定节奏重启
      新进程承接下一轮（supervisor 启动复用路径）。适配器在测试房间模式
      对 finished 透传快照而非终态，冷启动子进程会在 finished 窗口内
      存活轮询（register+ready），因此续跑重启每轮至多一次，不构成热循环。
    """

    max_restarts: int = 2
    base_delay_seconds: float = 1.0
    factor: float = 2.0
    max_delay_seconds: float = 8.0
    finished_restart_delay_seconds: float = 2.0

    def new_backoff(self) -> "BoundedBackoff | None":
        """max_restarts=0 表示禁用重启，返回 None。"""

        if self.max_restarts == 0:
            return None
        return BoundedBackoff(
            base_delay_seconds=self.base_delay_seconds,
            factor=self.factor,
            max_delay_seconds=self.max_delay_seconds,
            max_attempts=self.max_restarts,
        )


@dataclass(frozen=True)
class RoomConfig:
    """四身份测试房间的完整配置；派生到子进程时不含 Token。"""

    base_url: str
    expected_tournament_id: str
    known_guide_version: int
    audit_root: Path
    strategy: str
    insecure_hosts: frozenset
    identities: tuple
    restart: RoomRestart
    sse_enabled: bool = False  # SSE 帧驱动开关（透传给每身份子进程）


@dataclass
class IdentityReport:
    """一个身份的守护结果汇总；只含可打印的安全状态。"""

    slot: str = ""
    outcome: str = "pending"  # completed / failed / interrupted / restart_exhausted
    attempts: int = 0
    rounds_completed: int = 0  # 测试房间跨轮续跑：已完赛并重启承接的轮次数
    exit_code: Optional[int] = None
    terminal_reason: Optional[str] = None
    detail: Optional[str] = None
    run_id: Optional[str] = None
    audit_dir: Optional[str] = None
    participant_id_prefix: Optional[str] = None
    audit_degraded: Optional[bool] = None
    audit_summary: Optional[dict] = None
    audit_complete: Optional[bool] = None
    audit_violations: Optional[int] = None
    games_finished: Optional[int] = None
    final_scores_by_game: dict = field(default_factory=dict)
    outcome_histogram: dict = field(default_factory=dict)


def load_room_config(path: Path, environ: Optional[Mapping[str, str]] = None) -> RoomConfig:
    """读取并严格校验房间配置；Token 在此解析为原文并保持掩码。"""

    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, Mapping):
        raise ValueError("房间配置根必须是 JSON 对象")
    unknown = sorted(set(data) - _ROOM_FIELDS)
    if unknown:
        raise ValueError("房间配置包含未知字段: " + ", ".join(unknown))
    if data.get("mode") != "test_room":
        raise ValueError("run_test_room.py 只接受 mode=test_room，得到 " + repr(data.get("mode")))
    env = os.environ if environ is None else environ
    identities_value = data.get("identities")
    if not isinstance(identities_value, list) or len(identities_value) != 4:
        raise ValueError(f"identities 必须恰好是四个身份槽位，得到 {identities_value!r}")
    identities = []
    slots = []
    for item in identities_value:
        if not isinstance(item, Mapping):
            raise ValueError("每个身份槽位必须是 JSON 对象")
        unknown_keys = sorted(set(item) - {"slot", "token", "token_env", "token_file", "strategy"})
        if unknown_keys:
            raise ValueError("身份槽位包含未知字段: " + ", ".join(unknown_keys))
        slot = _require_non_empty_str(item.get("slot"), "identity.slot")
        if not all(ch.isalnum() or ch in "-_" for ch in slot):
            raise ValueError(f"身份槽位标签只能包含字母数字与 - _，得到 {slot!r}")
        slots.append(slot)
        inline = item.get("token")
        token_env = item.get("token_env")
        token_file = item.get("token_file")
        provided = sum(value is not None for value in (inline, token_env, token_file))
        if provided != 1:
            raise ValueError(f"身份 {slot}: token / token_env / token_file 必须且只能提供一个")
        if inline is not None:
            token = _require_non_empty_str(inline, "identity.token")
            source = "inline"
        elif token_env is not None:
            name = _require_non_empty_str(token_env, "identity.token_env")
            token = env.get(name)
            if not token or not token.strip():
                raise ValueError(f"身份 {slot}: 环境变量 {name} 未提供非空 Token")
            source = "env:" + name
        else:
            file_path = _require_non_empty_str(token_file, "identity.token_file")
            content = Path(file_path).read_text(encoding="utf-8").strip()
            lines = [line.strip() for line in content.splitlines() if line.strip()]
            if not lines:
                raise ValueError(f"身份 {slot}: Token 文件内容为空")
            if len(lines) > 1:
                raise ValueError(
                    f"身份 {slot}: Token 文件包含多行内容；请提供只含单个 Token 的文件"
                )
            token = lines[0]
            source = "file:" + file_path
        identity_strategy = _require_strategy(item["strategy"]) if "strategy" in item else None
        identities.append(IdentitySlot(
            slot=slot, token=token, token_source=source, strategy=identity_strategy,
        ))
    if len(set(slots)) != 4:
        raise ValueError("四个身份槽位标签必须互不相同，得到 " + ", ".join(slots))

    restart_value = data.get("restart", {})
    if not isinstance(restart_value, Mapping):
        raise ValueError("restart 必须是 JSON 对象")
    unknown_keys = sorted(set(restart_value) - _RESTART_FIELDS)
    if unknown_keys:
        raise ValueError("restart 包含未知字段: " + ", ".join(unknown_keys))
    max_restarts = restart_value.get("max_restarts", 2)
    if isinstance(max_restarts, bool) or not isinstance(max_restarts, int) or max_restarts < 0:
        raise ValueError(f"restart.max_restarts 必须是非负整数，得到 {max_restarts!r}")

    def _positive_seconds(value: object, field: str) -> float:
        """正的有限秒数；bool、NaN 与 inf 均拒绝。"""
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not value > 0
            or not math.isfinite(value)
        ):
            raise ValueError(f"restart.{field} 必须是正的有限秒数，得到 {value!r}")
        return float(value)

    factor_value = restart_value.get("factor", 2.0)
    if (
        isinstance(factor_value, bool)
        or not isinstance(factor_value, (int, float))
        or not factor_value >= 1
        or not math.isfinite(factor_value)
    ):
        raise ValueError(f"restart.factor 必须是 >= 1 的有限数值，得到 {factor_value!r}")
    restart = RoomRestart(
        max_restarts=max_restarts,
        base_delay_seconds=_positive_seconds(restart_value.get("base_delay_seconds", 1.0), "base_delay_seconds"),
        factor=float(factor_value),
        max_delay_seconds=_positive_seconds(restart_value.get("max_delay_seconds", 8.0), "max_delay_seconds"),
        finished_restart_delay_seconds=_positive_seconds(
            restart_value.get("finished_restart_delay_seconds", 2.0), "finished_restart_delay_seconds"
        ),
    )

    strategy = _require_strategy(data.get("strategy", "weighted_heuristic"))
    hosts = data.get("insecure_hosts", [])
    if not isinstance(hosts, (list, tuple)):
        raise ValueError("insecure_hosts 必须是数组")

    sse_value = data.get("sse_enabled", False)
    if not isinstance(sse_value, bool):
        raise ValueError("sse_enabled 必须是布尔值，得到 {0!r}".format(sse_value))
    return RoomConfig(
        base_url=_require_non_empty_str(data.get("base_url"), "base_url"),
        expected_tournament_id=_require_non_empty_str(data.get("expected_tournament_id"), "expected_tournament_id"),
        known_guide_version=_require_positive_int(data.get("known_guide_version"), "known_guide_version"),
        audit_root=Path(_require_non_empty_str(data.get("audit_root"), "audit_root")),
        strategy=strategy,
        insecure_hosts=frozenset(hosts),
        identities=tuple(identities),
        restart=restart,
        sse_enabled=sse_value,
    )


def child_config_mapping(room: RoomConfig, identity: IdentitySlot) -> dict:
    """派生单身份子进程配置；Token 不落盘，由环境变量 TOKEN_ENV_VAR 提供。"""

    config = {
        "mode": "test_room",
        "base_url": room.base_url,
        "expected_tournament_id": room.expected_tournament_id,
        "known_guide_version": room.known_guide_version,
        "token_env": TOKEN_ENV_VAR,
        "token_kind": "test",
        "audit_root": str(room.audit_root / ("slot-" + identity.slot)),
        "strategy": identity.strategy if identity.strategy is not None else room.strategy,
        "sse_enabled": room.sse_enabled,
    }
    if room.insecure_hosts:
        config["insecure_hosts"] = sorted(room.insecure_hosts)
    return config


def _parse_result(stdout_text: str) -> dict:
    """从子进程 stdout 提取最后一条 RESULT 行；失败返回空字典。"""

    for line in reversed(stdout_text.splitlines()):
        if line.startswith(RESULT_PREFIX):
            try:
                value = json.loads(line[len(RESULT_PREFIX):])
                return value if isinstance(value, Mapping) else {}
            except json.JSONDecodeError:
                return {}
    return {}


def _signal_children(active_processes: set, signum: int) -> None:
    """向全部在途子进程转发信号；进程已退出或句柄差异一律吞掉。

    信号处理器与身份守护协程共享 active_processes：处理器只负责转发，
    收尾等待仍由各守护协程的 communicate() 完成（子进程收到信号后
    自行取消运行并冲刷审计，返回后再由 shutdown 判定分支标记 interrupted）。
    """

    for process in list(active_processes):
        try:
            send = getattr(process, "send_signal", None)
            if send is not None:
                send(signum)
            else:
                process.terminate()
        except (ProcessLookupError, OSError):
            pass
        except Exception:  # noqa: BLE001 - 转发失败不阻断其他身份收尾
            pass


async def _interruptible_sleep(
    delay: float,
    shutdown: asyncio.Event,
    sleep_fn,
) -> bool:
    """等待 delay 或被 shutdown 打断；返回 True 表示被 shutdown 打断。

    用途：重启退避与跨轮续跑节奏期间收到停止信号时，不得再拉起下一个
    子进程开新轮——睡眠必须可中断。sleep_fn 保持测试注入（真实睡眠
    替身），被打断时其任务被取消并回收，不留悬挂任务。
    """

    if shutdown.is_set():
        return True
    sleep_task = asyncio.ensure_future(sleep_fn(delay))
    stop_task = asyncio.ensure_future(shutdown.wait())
    try:
        await asyncio.wait(
            {sleep_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
        )
        return shutdown.is_set()
    finally:
        for task in (sleep_task, stop_task):
            if not task.done():
                task.cancel()
        # 取消任务仍须回收，否则事件循环关闭时报悬挂任务警告。
        await asyncio.gather(sleep_task, stop_task, return_exceptions=True)


async def _run_identity(
    room: RoomConfig,
    identity: IdentitySlot,
    environ: Mapping[str, str],
    tempdir: str,
    shutdown: asyncio.Event,
    sleep_fn=asyncio.sleep,
    spawn=asyncio.create_subprocess_exec,
    active_processes: Optional[set] = None,
) -> IdentityReport:
    """守护一个身份的整个生命周期：启动 → 有界重启 → 终局分类。

    sleep_fn / spawn 仅测试注入（退避睡眠替身与假子进程工厂）。
    active_processes 是编排层的在途子进程登记表（信号转发目标），
    缺省使用本协程私有集合（单测场景）。子进程本身不做任何状态持久化，
    每次重启都由新进程重新 initialize 从权威状态恢复，不复用内存中的
    提交判断。
    """

    report = IdentityReport(slot=identity.slot)
    participant_script = Path(__file__).resolve().parent / "run_participant.py"
    child_config_path = Path(tempdir) / ("slot-" + identity.slot + ".json")
    child_config_path.write_text(
        json.dumps(child_config_mapping(room, identity), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    backoff = room.restart.new_backoff()
    registry = active_processes if active_processes is not None else set()
    while True:
        # 停止信号可在任意等待点到达（含上一轮的跨轮续跑睡眠）：
        # 循环顶部兜底保证 shutdown 后绝不拉起新子进程。
        if shutdown.is_set():
            report.outcome = "interrupted"
            return report
        report.attempts += 1
        env = dict(environ)
        env[TOKEN_ENV_VAR] = identity.token
        print(
            f"[{identity.slot}] 启动第 {report.attempts} 次（Token 来源: {identity.token_source}）",
            flush=True,
        )
        try:
            process = await spawn(
                sys.executable,
                str(participant_script),
                "--config", str(child_config_path),
                "--slot", identity.slot,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            # 登记在途句柄：信号处理器据此向子进程转发 INT/TERM，
            # 使收到停止信号后无需等子进程跑满一整轮。
            registry.add(process)
            try:
                stdout_bytes, stderr_bytes = await process.communicate()
            finally:
                registry.discard(process)
        except OSError as exc:
            print(f"[{identity.slot}] 子进程启动失败: {exc}", file=sys.stderr, flush=True)
            report.exit_code = None
            stdout_bytes, stderr_bytes = b"", b""
            if shutdown.is_set():
                report.outcome = "interrupted"
                return report
        else:
            report.exit_code = process.returncode
        stderr_text = stderr_bytes.decode("utf-8", errors="replace")
        if stderr_text.strip():
            for line in stderr_text.splitlines():
                print(f"[{identity.slot}] {line}", file=sys.stderr, flush=True)
        result = _parse_result(stdout_bytes.decode("utf-8", errors="replace"))
        report.terminal_reason = result.get("terminal_reason")
        report.detail = result.get("detail")
        report.run_id = result.get("run_id")
        report.audit_dir = result.get("audit_dir")
        report.participant_id_prefix = result.get("participant_id_prefix")
        report.audit_degraded = result.get("audit_degraded")
        report.audit_summary = result.get("audit_summary")

        if shutdown.is_set():
            report.outcome = "interrupted"
            return report
        if report.exit_code == EXIT_CHILD_COMPLETED:
            if report.terminal_reason == "tournament_finished":
                # 测试房间跨轮续跑：完赛一轮的正常出口不消耗失败重启预算，
                # 按固定节奏重启新进程承接下一轮（新进程冷启动后 register+ready，
                # 若房间仍 finished 则存活轮询等待下一轮）。其余 exit 0 终态
                # （eliminated / tournament_closed / tournament_void）为最终结果。
                report.rounds_completed += 1
                print(
                    f"[{identity.slot}] 完赛第 {report.rounds_completed} 轮，"
                    f"{room.restart.finished_restart_delay_seconds:.1f} 秒后重启承接下一轮",
                    flush=True,
                )
                if await _interruptible_sleep(
                    room.restart.finished_restart_delay_seconds, shutdown, sleep_fn
                ):
                    report.outcome = "interrupted"
                    return report
                if shutdown.is_set():
                    # 双重防护（评审修复设计第 2 点）：睡眠自然结束与 shutdown
                    # 置位的竞态窗口内也绝不拉起新子进程开新轮。
                    report.outcome = "interrupted"
                    return report
                continue
            report.outcome = "completed"
            return report
        if report.exit_code == EXIT_CHILD_PERMANENT:
            report.outcome = "failed"
            return report
        # 致命错误 / 异常退出：重启预算内有界重启；预算耗尽标记失败。
        delay = backoff.next_delay_or_none() if backoff is not None else None
        if delay is None:
            report.outcome = "restart_exhausted"
            return report
        print(
            f"[{identity.slot}] 退出码 {report.exit_code}，{delay:.1f} 秒后重启（有界退避）",
            flush=True,
        )
        if await _interruptible_sleep(delay, shutdown, sleep_fn):
            report.outcome = "interrupted"
            return report


def enrich_with_audit(report: IdentityReport) -> None:
    """用离线验证器补充审计完整性、终局分数与提交结果统计。"""

    if not report.audit_dir or not Path(report.audit_dir).is_dir():
        return
    try:
        from hangma_bot.adapters.recording import validate_run

        validated = validate_run(report.audit_dir)
        report.audit_complete = bool(validated["audit_complete"])
        report.audit_violations = int(validated["violation_count"])
        coverage = validated.get("coverage") or {}
        report.games_finished = coverage.get("games_finished")
        report.final_scores_by_game = dict(coverage.get("final_scores_by_game") or {})
        submissions = validated.get("submissions") or {}
        report.outcome_histogram = dict(submissions.get("outcome_histogram") or {})
    except Exception:  # noqa: BLE001 - 审计目录损坏只影响汇总，不改变身份结果
        report.audit_complete = None


def report_lines(reports: Sequence[IdentityReport]) -> Sequence[str]:
    """渲染最终汇总：每身份终态、场次数、最终分、提交结果与审计完整性。"""

    lines = ["", "==== 四身份汇总 ===="]
    for report in reports:
        head = (
            f"[{report.slot}] {report.outcome} | 终态: {report.terminal_reason or '未知'}"
            f" | 尝试: {report.attempts} 次 | 完赛轮次: {report.rounds_completed} | exit={report.exit_code}"
        )
        lines.append(head)
        if report.run_id:
            lines.append(f"        run_id: {report.run_id}")
        if report.participant_id_prefix:
            lines.append(f"        身份（脱敏前缀）: {report.participant_id_prefix}*")
        if report.audit_dir:
            lines.append(f"        审计目录: {report.audit_dir}")
        if report.audit_complete is not None:
            verdict = "complete" if report.audit_complete else "incomplete"
            lines.append(f"        审计完整性: {verdict}（violations={report.audit_violations}）")
        if report.audit_degraded:
            lines.append("        审计降级: true（本运行不能宣称完整可审计）")
        if report.games_finished is not None:
            lines.append(f"        完赛场次: {report.games_finished}")
        for game_key, scores in sorted(report.final_scores_by_game.items()):
            lines.append(f"        终局分数 {game_key}: {scores}")
        if report.outcome_histogram:
            lines.append(f"        提交结果分布: {report.outcome_histogram}")
        if report.detail:
            lines.append(f"        详情: {report.detail}")
    return lines


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_test_room.py",
        description="用四个隔离子进程运行官方测试房间四 Token 身份",
    )
    parser.add_argument("--config", required=True, help="JSON 房间配置路径")
    return parser


async def _amain(room: RoomConfig, environ: Mapping[str, str]) -> int:
    """四个身份并发守护；收到信号后向子进程转发终止并等待收尾。"""

    loop = asyncio.get_running_loop()
    shutdown = asyncio.Event()
    received: list[int] = []
    # 在途子进程登记表：信号处理器只向表内句柄转发信号（不代管收尾），
    # 身份守护协程在 communicate() 返回后按 shutdown 判定 interrupted。
    active_processes: set = set()

    def _on_signal(signum: int) -> None:
        received.append(signum)
        shutdown.set()
        _signal_children(active_processes, signum)

    registered: list[int] = []
    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signum, _on_signal, signum)
            registered.append(signum)
        except NotImplementedError:
            pass

    print(
        f"测试房间启动：目标赛事 {room.expected_tournament_id}，"
        f"指南版本下限 {room.known_guide_version}，审计根 {room.audit_root}",
        flush=True,
    )
    for identity in room.identities:
        strategy = identity.strategy if identity.strategy is not None else room.strategy
        print(f"身份 {identity.slot}：策略 {strategy}，Token 来源 {identity.token_source}", flush=True)

    try:
        with tempfile.TemporaryDirectory(prefix="hangma-room-") as tempdir:
            tasks = [
                asyncio.create_task(
                    _run_identity(
                        room,
                        identity,
                        environ,
                        tempdir,
                        shutdown,
                        active_processes=active_processes,
                    )
                )
                for identity in room.identities
            ]
            reports = list(await asyncio.gather(*tasks))
    finally:
        for signum in registered:
            try:
                loop.remove_signal_handler(signum)
            except Exception:  # noqa: BLE001
                pass

    for report in reports:
        enrich_with_audit(report)
    for line in report_lines(reports):
        print(line, flush=True)
    if received:
        return EXIT_SIGINT if received[0] == signal.SIGINT else EXIT_SIGTERM
    return EXIT_ROOM_OK if all(r.outcome == "completed" for r in reports) else EXIT_ROOM_FAILED


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        room = load_room_config(Path(args.config))
    except Exception as exc:  # noqa: BLE001 - 配置错误统一转为退出码 2
        print(f"配置错误: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_ROOM_USAGE
    environ = dict(os.environ)
    try:
        return asyncio.run(_amain(room, environ))
    except Exception as exc:  # noqa: BLE001 - 入口级兜底
        print(f"编排异常: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_ROOM_FAILED


if __name__ == "__main__":
    sys.exit(main())
