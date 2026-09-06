"""四身份编排测试：注入假子进程，验证并发守护、独立失败、有界重启、目录隔离与信号收尾。

不启动真实子进程、不连接网络：spawn 与 sleep 均注入替身。
场景：A 失败一次后重启成功；B 一次成功；C 身份永久失败（不重启）；
D 连续失败耗尽重启预算。另有信号收尾回归：shutdown 转发信号到在途
子进程（不等待其自然完赛一轮）、打断跨轮续跑睡眠且不拉起新进程。
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import signal
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"

SPEC = importlib.util.spec_from_file_location("hangma_room_orchestration_runner", SCRIPTS_DIR / "run_test_room.py")
assert SPEC is not None and SPEC.loader is not None
room = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = room
SPEC.loader.exec_module(room)

SECRET_A = "orch-secret-token-A-0123456789abcdef"
SECRET_B = "orch-secret-token-B-0123456789abcdef"
SECRET_C = "orch-secret-token-C-0123456789abcdef"
SECRET_D = "orch-secret-token-D-0123456789abcdef"


def test_example_room_config_accepts_batch_limit_and_rejects_invalid_values(tmp_path):
    data = json.loads((SCRIPTS_DIR.parent / "configs/test-room.example.json").read_text())
    for item in data["identities"]:
        item.pop("token_file")
        item["token_env"] = "TEST_ROOM_TOKEN"
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data))
    config = room.load_room_config(path, environ={"TEST_ROOM_TOKEN": SECRET_A})
    assert config.max_completed_batches == 1
    for invalid in (0, -1, True, 1.5):
        data["max_completed_batches"] = invalid
        path.write_text(json.dumps(data))
        with pytest.raises(ValueError, match="正整数"):
            room.load_room_config(path, environ={"TEST_ROOM_TOKEN": SECRET_A})


async def test_bounded_batch_finishes_without_spawning_a_new_registration(tmp_path):
    from dataclasses import replace
    config = replace(_room_config(tmp_path), max_completed_batches=1)
    calls = []
    async def spawn(*args, **kwargs):
        calls.append(args)
        return _FakeProcess(0, _result("tournament_finished"))
    result = await room._run_identity(config, config.identities[0], {}, str(tmp_path), asyncio.Event(), spawn=spawn)
    assert result.outcome == "completed"
    assert result.rounds_completed == 1
    assert len(calls) == 1


def _result(terminal_reason: str, prefix=None) -> str:
    payload = {
        "slot": "X",
        "run_id": "run-fake",
        "audit_dir": "/tmp/fake-audit/slot-X/runs/run-fake",
        "participant_id_prefix": prefix,
        "terminal_reason": terminal_reason,
        "detail": "脚本化终态",
    }
    return room.RESULT_PREFIX + json.dumps(payload, ensure_ascii=False)


class _FakeProcess:
    """最小子进程替身：communicate 返回脚本化输出，returncode 固定。"""

    def __init__(self, exit_code: int, stdout_text: str = "", stderr_text: str = ""):
        self.returncode = exit_code
        self._stdout = stdout_text.encode("utf-8")
        self._stderr = stderr_text.encode("utf-8")
        self.terminated = False

    async def communicate(self):
        return self._stdout, self._stderr

    def terminate(self) -> None:
        self.terminated = True


def _room_config(tmp_path: Path, restart=None) -> room.RoomConfig:
    return room.RoomConfig(
        base_url="https://platform.invalid",
        expected_tournament_id="t1",
        known_guide_version=8,
        audit_root=tmp_path / "room-audit",
        strategy="weighted_heuristic",
        insecure_hosts=frozenset(),
        identities=(
            room.IdentitySlot(slot="A", token=SECRET_A, token_source="inline"),
            room.IdentitySlot(slot="B", token=SECRET_B, token_source="inline"),
            room.IdentitySlot(slot="C", token=SECRET_C, token_source="inline"),
            room.IdentitySlot(slot="D", token=SECRET_D, token_source="inline"),
        ),
        restart=(
            restart
            if restart is not None
            else room.RoomRestart(
                max_restarts=2,
                base_delay_seconds=0.01,
                factor=2.0,
                max_delay_seconds=0.04,
                finished_restart_delay_seconds=0.05,
            )
        ),
    )


async def test_room_orchestration_isolation_and_restart(tmp_path):
    """A 失败一次重启成功；B 一次成功；C 永久失败；D 重启耗尽；目录隔离。"""

    # 按身份槽位脚本化（(exit_code, stdout, stderr) 队列）；spawn 并发顺序
    # 由调度决定，因此必须按 argv 中的 --slot 派发，不能假设全局顺序。
    per_slot = {
        "A": [
            (11, _result("fatal_protocol_error"), ""),   # 第 1 次：致命失败 → 重启
            (0, _result("eliminated", prefix="p1ab"), ""),  # 第 2 次：正常终态
        ],
        "B": [(0, _result("tournament_closed", prefix="p2cd"), "")],  # 一次成功（房间关闭）
        "C": [(10, _result("authentication_failed"), "")],   # 身份永久失败：不重启
        "D": [
            (11, _result("fatal_protocol_error"), ""),
            (11, _result("fatal_protocol_error"), ""),
            (11, _result("fatal_protocol_error"), ""),  # 第 3 次 → 预算耗尽
        ],
    }
    spawned = []
    delays = []

    async def fake_spawn(*args, **kwargs):
        argv = list(args)
        slot = argv[argv.index("--slot") + 1]
        spawned.append({"argv": argv, "env": dict(kwargs.get("env") or {})})
        exit_code, stdout_text, stderr_text = per_slot[slot].pop(0)
        return _FakeProcess(exit_code, stdout_text, stderr_text)

    async def fake_sleep(seconds: float) -> None:
        delays.append(seconds)
        await asyncio.sleep(0)

    config = _room_config(tmp_path)
    shutdown = asyncio.Event()
    reports = await asyncio.gather(*(
        room._run_identity(
            config, identity, {}, str(tmp_path), shutdown,
            sleep_fn=fake_sleep, spawn=fake_spawn,
        )
        for identity in config.identities
    ))

    outcomes = {report.slot: report for report in reports}
    assert outcomes["A"].outcome == "completed"
    assert outcomes["A"].attempts == 2
    assert outcomes["A"].participant_id_prefix == "p1ab"
    assert outcomes["B"].outcome == "completed"
    assert outcomes["B"].attempts == 1
    assert outcomes["C"].outcome == "failed"
    assert outcomes["C"].attempts == 1
    assert outcomes["D"].outcome == "restart_exhausted"
    assert outcomes["D"].attempts == 3
    # 一个身份失败不终止其余身份：B/C/D 的进程照常被拉起。
    assert len(spawned) == 7
    # 退避按指数递增：共三次重启等待（A 一次 + D 两次）= 0.01、0.01、0.02。
    assert sorted(delays) == [0.01, 0.01, 0.02]

    # Token 只经环境变量传递，绝不进入 argv。
    for record in spawned:
        assert room.TOKEN_ENV_VAR in record["env"]
        for argv_item in record["argv"]:
            assert SECRET_A not in argv_item
            assert SECRET_B not in argv_item
            assert SECRET_C not in argv_item
            assert SECRET_D not in argv_item

    # 每身份的派生配置独立且不含 Token：审计目录按 slot 隔离。
    config_paths = set()
    audit_roots = set()
    for record in spawned:
        config_arg = record["argv"][record["argv"].index("--config") + 1]
        config_paths.add(config_arg)
        child = json.loads(Path(config_arg).read_text(encoding="utf-8"))
        assert "token" not in child
        assert child["token_env"] == room.TOKEN_ENV_VAR
        audit_roots.add(child["audit_root"])
    assert len(config_paths) == 4  # 四个身份各自独立配置文件
    assert len(audit_roots) == 4  # 四个身份审计根目录互不相同
    for audit_root in audit_roots:
        assert "/slot-" in audit_root

    # 汇总渲染覆盖全部身份与终态，且不含 Token。
    rendered = "\n".join(room.report_lines(reports))
    assert "restart_exhausted" in rendered
    assert "p1ab" in rendered
    for secret in (SECRET_A, SECRET_B, SECRET_C, SECRET_D):
        assert secret not in rendered


async def test_finished_identity_restarts_for_next_round_without_budget(tmp_path):
    """跨轮续跑：exit 0 + tournament_finished 不消耗失败重启预算，持续承接下一轮。"""

    per_slot = {
        "A": [
            (0, _result("tournament_finished", prefix="p1ab"), ""),
            (0, _result("tournament_finished", prefix="p1ab"), ""),
            (0, _result("eliminated", prefix="p1ab"), ""),
        ],
        "B": [(0, _result("tournament_closed"), "")],
        "C": [(0, _result("tournament_void"), "")],
        "D": [
            (0, _result("tournament_finished"), ""),
            (0, _result("tournament_closed"), ""),
        ],
    }
    spawned = []
    delays = []

    async def fake_spawn(*args, **kwargs):
        argv = list(args)
        slot = argv[argv.index("--slot") + 1]
        spawned.append(slot)
        exit_code, stdout_text, stderr_text = per_slot[slot].pop(0)
        return _FakeProcess(exit_code, stdout_text, stderr_text)

    async def fake_sleep(seconds: float) -> None:
        delays.append(seconds)
        await asyncio.sleep(0)

    config = _room_config(
        tmp_path,
        restart=room.RoomRestart(
            max_restarts=0,  # 失败重启预算为 0：跨轮续跑仍必须工作
            base_delay_seconds=0.01,
            factor=2.0,
            max_delay_seconds=0.04,
            finished_restart_delay_seconds=0.05,
        ),
    )
    shutdown = asyncio.Event()
    reports = await asyncio.gather(*(
        room._run_identity(
            config, identity, {}, str(tmp_path), shutdown,
            sleep_fn=fake_sleep, spawn=fake_spawn,
        )
        for identity in config.identities
    ))

    outcomes = {report.slot: report for report in reports}
    assert outcomes["A"].outcome == "completed"
    assert outcomes["A"].attempts == 3
    assert outcomes["A"].rounds_completed == 2
    assert outcomes["B"].outcome == "completed"
    assert outcomes["B"].rounds_completed == 0
    assert outcomes["C"].outcome == "completed"
    assert outcomes["D"].outcome == "completed"
    assert outcomes["D"].rounds_completed == 1
    # 续跑等待只在 finished 重启路径产生：A 两次 + D 一次 = 0.05 × 3。
    assert sorted(delays) == [0.05, 0.05, 0.05]
    rendered = "\n".join(room.report_lines(reports))
    assert "完赛轮次: 2" in rendered


def test_signal_children_falls_back_to_terminate():
    """转发路径兜底：无 send_signal 的句柄（_FakeProcess）走 terminate，
    评审指出 _FakeProcess.terminate 从未被测试调用——此处显式覆盖。"""

    fake = _FakeProcess(0)
    room._signal_children({fake}, signal.SIGTERM)
    assert fake.terminated is True


class _BlockingProcess:
    """挂起子进程替身：communicate 阻塞到收到信号才返回（模拟在途运行）。"""

    def __init__(self):
        self.returncode = None
        self.signals = []
        self._released = asyncio.Event()

    async def communicate(self):
        await self._released.wait()
        self.returncode = -signal.SIGTERM
        return _result("cancelled").encode("utf-8"), b""

    def send_signal(self, signum: int) -> None:
        self.signals.append(signum)
        self._released.set()

    def terminate(self) -> None:
        self.send_signal(signal.SIGTERM)


async def test_shutdown_forwards_signal_and_blocks_new_spawn(tmp_path):
    """Challenger 回归 1：信号处理器必须向在途子进程转发信号，
    子进程不必跑满一整轮才停；shutdown 后不再拉起新进程。"""

    blocking = _BlockingProcess()
    spawned = []

    async def fake_spawn(*args, **kwargs):
        spawned.append(list(args))
        return blocking

    config = _room_config(
        tmp_path,
        restart=room.RoomRestart(
            max_restarts=1,
            base_delay_seconds=0.01,
            factor=2.0,
            max_delay_seconds=0.04,
            finished_restart_delay_seconds=0.05,
        ),
    )
    shutdown = asyncio.Event()
    registry: set = set()
    task = asyncio.ensure_future(
        room._run_identity(
            config,
            config.identities[0],
            {},
            str(tmp_path),
            shutdown,
            sleep_fn=lambda _s: asyncio.sleep(0),
            spawn=fake_spawn,
            active_processes=registry,
        )
    )
    for _ in range(2000):
        if registry:
            break
        await asyncio.sleep(0.001)
    assert len(registry) == 1

    # 模拟 _amain 信号处理器：置 shutdown 并转发 SIGTERM。
    shutdown.set()
    room._signal_children(registry, signal.SIGTERM)

    report = await task
    assert report.outcome == "interrupted"
    assert blocking.signals == [signal.SIGTERM]
    assert len(spawned) == 1  # 停止后绝不拉起新进程


async def test_shutdown_interrupts_finished_restart_sleep(tmp_path):
    """Challenger 回归 2：跨轮续跑睡眠期间收到 shutdown，
    必须立即 interrupted，不得在睡眠结束后再拉起子进程开新轮。"""

    first = _FakeProcess(0, _result("tournament_finished"))
    spawned = []

    async def fake_spawn(*args, **kwargs):
        spawned.append(list(args))
        return first

    config = _room_config(
        tmp_path,
        restart=room.RoomRestart(
            max_restarts=0,
            base_delay_seconds=0.01,
            factor=2.0,
            max_delay_seconds=0.04,
            finished_restart_delay_seconds=0.05,
        ),
    )
    shutdown = asyncio.Event()
    sleeping = asyncio.Event()

    async def fake_sleep(_seconds: float) -> None:
        sleeping.set()
        await asyncio.Event().wait()  # 长眠：由可中断睡眠包装取消回收

    task = asyncio.ensure_future(
        room._run_identity(
            config,
            config.identities[0],
            {},
            str(tmp_path),
            shutdown,
            sleep_fn=fake_sleep,
            spawn=fake_spawn,
        )
    )
    for _ in range(2000):
        if sleeping.is_set():
            break
        await asyncio.sleep(0.001)
    assert sleeping.is_set()

    shutdown.set()
    report = await task
    assert report.outcome == "interrupted"
    assert report.rounds_completed == 1
    assert len(spawned) == 1  # 续跑睡眠被中断：没有拉起新子进程


if __name__ == "__main__":
    pytest.main([__file__])
