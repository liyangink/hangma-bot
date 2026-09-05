"""原始事件全量保留接线回归（E1/E2/E3，主会话集成）。

验证 game session 的公开接口（next_item/submit）在以下路径都会发射
RAW_PROTOCOL_STATE 原始事件记录，且对账键与 SUBMISSION_INTENT/OUTCOME
一致（验证器据此检查"每个实际发出的请求都有响应原文"）：

- /state 成功响应：request_no 单调、seq_observed 取快照权威水位；
- /state 坏报文（解析失败）：seq_observed=None、原文照样落盘；
- 动作 POST 成功：http_status=200、raw 为响应原文；
- 409 拒绝：拒绝体原文完整保留（经 errors.raw_text 携带，E2）；
- POST 结果不确定（超时）：http_status=None、raw=""，记录"原文不存在"。

全部用例走模块公开接口，不触内部私有状态（tests/AGENTS.md）。
"""

from __future__ import annotations

import asyncio
import json

from hangma_bot.adapters.official.errors import ConflictError, UncertainTransportError
from hangma_bot.application.contracts import (
    ActionAttempt,
    AuditKind,
    GameFailed,
    ObservedActionWindow,
    SubmitAccepted,
    SubmitAmbiguous,
    SubmitRejectedRetryable,
)
from hangma_bot.kernel.actions import Discard, Peng, Tile, WindowKey, WindowPhase

from _official_testkit import load_fixture, make_game_session


def _draw_key() -> WindowKey:
    return WindowKey(game_id="g_room1_batch1", round_no=1, trigger_seq=101, phase=WindowPhase.DRAW, seat=2)


def _attempt(window: WindowKey, action, action_key: str) -> ActionAttempt:
    return ActionAttempt(
        decision_id="d-raw-1",
        attempt_no=1,
        plan_revision=1,
        window_key=window,
        based_on_authoritative_seq=window.trigger_seq,
        action=action,
        action_key=action_key,
        latest_send_at_monotonic=1005.0,
    )


def _state_handler(queue: list):
    """按调用顺序弹出 (status, text) 或异常实例；GET/POST 共用队列。"""

    def handler(*, method: str, path: str, json_body=None, params=None, long_poll=False):
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    return handler


def _raw_payloads(audit, endpoint_prefix: str) -> list:
    """按 endpoint 前缀过滤原始事件 payload（扁平结构，raw 字段是文本）。"""

    return [
        record.payload
        for record in audit.records
        if record.kind is AuditKind.RAW_PROTOCOL_STATE
        and str(record.payload.get("endpoint", "")).startswith(endpoint_prefix)
    ]


class TestStateRawRetention:
    async def test_success_state_response_recorded(self, transport, clock, audit) -> None:
        """成功 /state：request_no 从 1 起、seq_observed=快照权威水位、原文落盘。"""

        transport.handler = _state_handler([
            (200, json.dumps(load_fixture("state_response_snapshot_draw.json"))),
        ])
        session = make_game_session(transport=transport, clock=clock, audit=audit)
        item = await asyncio.wait_for(session.next_item(), timeout=2)
        assert isinstance(item, ObservedActionWindow)

        payloads = _raw_payloads(audit, "GET /api/games/")
        assert len(payloads) == 1
        raw = payloads[0]
        assert raw["http_status"] == 200
        assert raw["request_no"] == 1
        assert raw["seq_observed"] == 101  # 与窗口 authoritative_seq 同源
        assert raw["seq_requested"] == 0  # 首拉为 seq=0 全量
        assert "snapshot" in raw["raw"]  # 响应原文（非二次加工）

    async def test_unparseable_state_body_still_recorded(self, transport, clock, audit) -> None:
        """坏报文（200 + 非 state 契约 JSON）：解析失败也必须留原文供诊断。"""

        garbage = (200, json.dumps({"unexpected": True}))
        transport.handler = _state_handler([garbage] * 6)
        session = make_game_session(transport=transport, clock=clock, audit=audit)
        item = await asyncio.wait_for(session.next_item(), timeout=2)
        assert isinstance(item, GameFailed)  # 解析失败上交为可恢复失败

        payloads = _raw_payloads(audit, "GET /api/games/")
        assert payloads, "坏报文也必须有原始事件记录"
        first = payloads[0]
        assert first["http_status"] == 200
        assert first.get("seq_observed") is None  # 无法解析出权威水位（构造器省略 None 键）
        assert "unexpected" in first["raw"]  # 原文保留


class TestActionRawRetention:
    async def test_accepted_submit_records_response(self, transport, clock, audit) -> None:
        """成功 POST：原文记录与 intent/outcome 同键（decision_id/attempt_no）。"""

        transport.handler = _state_handler([
            (200, json.dumps(load_fixture("state_response_snapshot_draw.json"))),
        ])
        session = make_game_session(transport=transport, clock=clock, audit=audit)
        window = await asyncio.wait_for(session.next_item(), timeout=2)
        transport.handler = lambda **kw: (200, '{"accepted": true}')

        outcome = await asyncio.wait_for(
            session.submit(_attempt(window.window_key, Discard(Tile("5w")), "discard:5w")),
            timeout=2,
        )
        assert isinstance(outcome, SubmitAccepted)

        payloads = _raw_payloads(audit, "POST /api/games/")
        assert len(payloads) == 1
        raw = payloads[0]
        assert raw["http_status"] == 200
        assert raw["raw"] == '{"accepted": true}'
        assert raw["decision_id"] == "d-raw-1"
        assert raw["attempt_no"] == 1

    async def test_conflict_body_preserved_via_raw_text(self, transport, clock, audit) -> None:
        """409 拒绝体经 errors.raw_text（E2）完整保留；对账键一致。"""

        body = '{"code":"INVALID_ACTION","message":"peng not allowed"}'
        transport.handler = _state_handler([
            (200, json.dumps(load_fixture("state_response_snapshot_peng.json"))),
        ])
        session = make_game_session(transport=transport, clock=clock, audit=audit)
        window = await asyncio.wait_for(session.next_item(), timeout=2)
        assert window.window_key.phase is WindowPhase.RESPONSE_PENG
        transport.handler = _state_handler([
            ConflictError(409, "INVALID_ACTION", "no", raw_text=body),
            (200, json.dumps(load_fixture("state_response_snapshot_peng.json"))),  # 刷新：同窗仍开
        ])

        outcome = await asyncio.wait_for(
            session.submit(_attempt(window.window_key, Peng(Tile("2w")), "peng:2w")),
            timeout=2,
        )
        assert isinstance(outcome, SubmitRejectedRetryable)

        post_raw = _raw_payloads(audit, "POST /api/games/")
        assert len(post_raw) == 1
        assert post_raw[0]["http_status"] == 409
        assert post_raw[0]["raw"] == body  # 拒绝体原文完整、未被截断脱敏破坏
        assert post_raw[0]["decision_id"] == "d-raw-1"
        # 刷新 GET 也有原始记录（对账闭环：开桌 1 次 + 409 刷新 1 次）
        assert len(_raw_payloads(audit, "GET /api/games/")) == 2

    async def test_uncertain_post_records_absent_body(self, transport, clock, audit) -> None:
        """POST 结果不确定：http_status=None + raw=""，记录"原文不存在"。"""

        transport.handler = _state_handler([
            (200, json.dumps(load_fixture("state_response_snapshot_draw.json"))),
        ])
        session = make_game_session(transport=transport, clock=clock, audit=audit)
        window = await asyncio.wait_for(session.next_item(), timeout=2)
        transport.handler = _state_handler([UncertainTransportError("timeout:ReadTimeout")])

        outcome = await asyncio.wait_for(
            session.submit(_attempt(window.window_key, Discard(Tile("5w")), "discard:5w")),
            timeout=2,
        )
        assert isinstance(outcome, SubmitAmbiguous)

        post_raw = _raw_payloads(audit, "POST /api/games/")
        assert len(post_raw) == 1
        assert post_raw[0].get("http_status") is None  # 构造器对 None 省略键
        assert post_raw[0]["raw"] == ""
