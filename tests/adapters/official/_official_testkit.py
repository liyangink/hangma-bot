"""official 适配器测试工具箱（唯一模块名，避免跨目录 conftest 撞名）。

时间测试全部注入假时钟，不使用真实等待（tests/AGENTS.md）；
假传输按脚本返回响应或抛分类错误，用于覆盖 409/429/401/超时/断连。
pytest fixtures 见同目录 conftest.py。
"""
from __future__ import annotations

import asyncio
import inspect
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from hangma_bot.adapters.official.game import OfficialGameSession
from hangma_bot.adapters.official.participant import OfficialTournamentSession
from hangma_bot.adapters.official.scheduler import RequestScheduler
from hangma_bot.application.contracts import (
    AuditContext,
    AuditReceipt,
    AuditRecord,
    AuditSink,
)
from hangma_bot.kernel.config import TimingConfig

FIXTURE_DIR = Path(__file__).parents[2] / "fixtures" / "official" / "v8"


def load_fixture(name: str) -> Dict[str, Any]:
    """读取 fixture 并剥离本地 _meta 证据标注（非官方字段）。"""

    doc = json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))
    doc.pop("_meta", None)
    return doc


class FakeClock:
    """可控单调时钟；advance 推进秒数，wall_ms 同步推进。"""

    def __init__(self, start: float = 1000.0) -> None:
        self._now = start
        self._wall_ms = 1_750_000_000_000

    def monotonic(self) -> float:
        return self._now

    def wall_ms(self) -> int:
        return self._wall_ms

    def advance(self, seconds: float) -> None:
        self._now += seconds
        self._wall_ms += int(seconds * 1000)


@dataclass
class RecordedCall:
    """一次传输调用的完整参数记录（不含认证头）。"""

    method: str
    path: str
    json_body: Optional[Mapping[str, Any]]
    params: Optional[Mapping[str, Any]]
    long_poll: bool


class FakeTransport:
    """脚本化传输；handler 收到调用参数，返回 (status, text) 或抛 OfficialError。"""

    def __init__(self) -> None:
        self.calls: List[RecordedCall] = []
        self.handler: Callable[..., Any] = lambda **kw: (200, "{}")

    async def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Optional[Mapping[str, Any]] = None,
        params: Optional[Mapping[str, Any]] = None,
        with_auth: bool = True,
        long_poll: bool = False,
        request_budget_sec: Optional[float] = None,
    ):
        from hangma_bot.adapters.official.transport import TransportResult

        self.calls.append(
            RecordedCall(method, path, json_body, dict(params) if params else None, long_poll)
        )
        outcome = self.handler(method=method, path=path, json_body=json_body, params=params, long_poll=long_poll)
        if inspect.isawaitable(outcome):
            outcome = await outcome
        if isinstance(outcome, Exception):
            raise outcome
        status, text = outcome
        return TransportResult(status=status, text=text)

    async def aclose(self) -> None:
        return None


class FakeAuditSink:
    """内存审计；记录顺序即入队顺序。"""

    def __init__(self) -> None:
        self.records: List[AuditRecord] = []

    def emit(self, record: AuditRecord) -> AuditReceipt:
        self.records.append(record)
        return AuditReceipt(queued=True, audit_degraded=False)

    async def aclose(self, timeout_seconds: float):
        from hangma_bot.application.contracts import AuditSummary

        return AuditSummary(
            written=len(self.records),
            dropped_low_priority=0,
            missing_high_priority=0,
            serialization_failures=0,
            audit_degraded=False,
        )


def instant_sleep(clock: FakeClock):
    """假 sleep：推进假时钟并用真实零等待让出事件循环（避免测试自旋饥饿）。"""

    async def _sleep(seconds: float) -> None:
        clock.advance(max(0.0, seconds))
        await asyncio.sleep(0)

    return _sleep


TIMING = TimingConfig(peng_timeout_sec=1.0, chi_timeout_sec=1.0, discard_timeout_sec=3.0)


def make_audit_context(**overrides: Any) -> AuditContext:
    fields = {
        "run_id": "run-test",
        "tournament_id": "t_test_room_1",
        "participant_id": "u_player_a",
    }
    fields.update(overrides)
    return AuditContext(**fields)


def make_game_session(
    *,
    transport: FakeTransport,
    clock: FakeClock,
    audit: Optional[FakeAuditSink] = None,
    game_id: str = "g_room1_batch1",
    scheduler: Optional[RequestScheduler] = None,
) -> OfficialGameSession:
    scheduler = scheduler or RequestScheduler(
        clock=clock.monotonic,
        sleep=instant_sleep(clock),
        poll_interval=0.0,
    )
    return OfficialGameSession(
        game_id=game_id,
        transport=transport,  # type: ignore[arg-type]
        scheduler=scheduler,
        timing=TIMING,
        monotonic_clock=clock.monotonic,
        wall_clock_unix_ms=clock.wall_ms,
        audit=audit,
        audit_context=lambda: make_audit_context(),
        retry_sleep=instant_sleep(clock),
    )


def make_tournament_session(
    *,
    clock: FakeClock,
    transport: FakeTransport,
    audit: Optional[FakeAuditSink] = None,
    scheduler: Optional[RequestScheduler] = None,
) -> OfficialTournamentSession:
    from hangma_bot.adapters.official.transport import TransportConfig

    if scheduler is None:
        scheduler = RequestScheduler(
            clock=clock.monotonic,
            sleep=instant_sleep(clock),
            poll_interval=0.0,
        )
    session = OfficialTournamentSession(
        token="fake-token-do-not-log",
        transport_config=TransportConfig(
            base_url="https://10.240.169.190:18080",
            insecure_hosts=frozenset({"10.240.169.190"}),
        ),
        monotonic_clock=clock.monotonic,
        wall_clock_unix_ms=clock.wall_ms,
        audit=audit,
        audit_context=lambda: make_audit_context(),
        scheduler=scheduler,
        retry_sleep=instant_sleep(clock),
    )
    session._transport = transport  # 测试注入假传输
    return session
