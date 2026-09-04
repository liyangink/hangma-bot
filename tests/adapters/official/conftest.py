"""official 适配器测试 fixtures；共享工具在 _official_testkit（唯一模块名）。"""

from __future__ import annotations

import pytest

from _official_testkit import FakeAuditSink, FakeClock, FakeTransport


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def transport() -> FakeTransport:
    return FakeTransport()


@pytest.fixture
def audit() -> FakeAuditSink:
    return FakeAuditSink()
