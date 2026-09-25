"""钉死自由赛战况脚本在「账本已建立但尚无已结算房」时不得崩。

为什么单独测这一条：2026-09-25 晚新开战役时把账本重建为 rooms=[]，
脚本用 ledger["rooms"][-1] 直接索引，抛 IndexError，战况查询整个不可用。
新战役的第一房结算前必然处于这个状态，因此这是常态而不是边界。

测试只替换账本与日志来源，不读真实审计、不联网络。
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _load():
    spec = importlib.util.spec_from_file_location(
        "auto_match_status", ROOT / "scripts" / "auto_match_status.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["auto_match_status"] = module
    spec.loader.exec_module(module)
    return module


status = _load()


def _run(monkeypatch, ledger):
    monkeypatch.setattr(status, "alive", lambda: False)
    monkeypatch.setattr(status, "latest_log", lambda: None)
    monkeypatch.setattr(status, "read_ledger", lambda: ledger)
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = status.main()
    return code, buf.getvalue()


def test_empty_rooms_ledger_does_not_crash(monkeypatch):
    """新战役账本 rooms 为空时必须正常输出，不得 IndexError。"""
    code, out = _run(monkeypatch, {
        "cumulative_total": 0,
        "rooms": [],
        "stopped": False,
    })
    assert code == 0
    assert "尚无已结算房" in out
    assert "累计 0" in out


def test_missing_rooms_key_does_not_crash(monkeypatch):
    """账本缺 rooms 键（旧版或损坏）同样不得崩。"""
    code, out = _run(monkeypatch, {"cumulative_total": 0})
    assert code == 0
    assert "尚无已结算房" in out


def test_settled_room_is_reported(monkeypatch):
    """有已结算房时报告最近一房与累计，保持原有语义。"""
    code, out = _run(monkeypatch, {
        "cumulative_total": -24,
        "rooms": [{"room_id": "a_test", "room_subtotal": -24}],
    })
    assert code == 0
    assert "a_test" in out
    assert "-24" in out


def test_no_ledger_reports_absence(monkeypatch):
    code, out = _run(monkeypatch, None)
    assert code == 0
    assert "无账本" in out
