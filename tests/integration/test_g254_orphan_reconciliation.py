"""G254：异常自由赛房只能凭十桌八局的官方终局追回积分。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'tests/integration'

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


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = _project_file(_PROJECT_ROOT, ROOT / "review/freematch-deep-dive-20260925/g254_reconcile_orphan_rooms.py")


def _module():
    spec = importlib.util.spec_from_file_location("g254_orphans", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _source(source: Path, room: str, me: str) -> None:
    """生成每张八局均有权威终局、十张桌都已结束的最小牌谱。"""

    for batch in range(10):
        directory = source / "official" / f"dl-{batch}"
        directory.mkdir(parents=True)
        gid = f"{room}_r1_b{batch}_t0"
        blocks = []
        for round_no in range(1, 9):
            events = [{"type": "round_ended", "data": {"scores": [1, -1, 0, 0]}}]
            if round_no == 8:
                events.append({"type": "game_ended", "data": {
                    "final_scores": [8, -8, 0, 0]}})
            blocks.append({"round_no": round_no, "events": events})
        (directory / "source.json").write_text(json.dumps({
            "room_id": room, "batch": batch}), encoding="utf-8")
        (directory / "events.json").write_text(json.dumps({
            "room_id": room, "game_id": gid, "status": "finished",
            "seats": [{"user_id": me}, {"user_id": "other-1"},
                      {"user_id": "other-2"}, {"user_id": "other-3"}],
            "blocks": blocks,
        }), encoding="utf-8")


def test_full_official_orphan_recovery_is_idempotent(monkeypatch, tmp_path):
    g254 = _module()
    room = "a_fixture"
    monkeypatch.setattr(g254, "ROOT", tmp_path)
    monkeypatch.setattr(g254, "ORPHANS", frozenset({room}))
    source = tmp_path / "derived"
    _source(source, room, g254.watchdog.ME)
    games, hashes = g254.official_games(source)
    assert len(games[room]) == 10
    assert sum(row["final_score"] for row in games[room]) == 80
    assert len(hashes) == 20
    audit = tmp_path / "audit"
    audit.mkdir()
    log = tmp_path / "session.log"
    log.write_text("fixture", encoding="utf-8")
    logs = {room: (log, {"terminal_reason": "matching_unavailable"}, audit)}
    ledger = {"campaign": "r18-sse-freematch-campaign-20260925b",
              "cumulative_total": 0, "current_lose_streak": 0, "rooms": []}

    ledger, added = g254.reconcile(ledger, games, logs, source)
    assert len(added) == 1
    assert ledger["cumulative_total"] == 80
    assert ledger["rooms"][0]["settlement_status"] == "official_recovered_complete"
    ledger, added_again = g254.reconcile(ledger, games, logs, source)
    assert added_again == []
    assert ledger["cumulative_total"] == 80


def test_incomplete_official_room_cannot_enter_ledger(monkeypatch, tmp_path):
    g254 = _module()
    room = "a_fixture"
    monkeypatch.setattr(g254, "ROOT", tmp_path)
    monkeypatch.setattr(g254, "ORPHANS", frozenset({room}))
    source = tmp_path / "derived"
    _source(source, room, g254.watchdog.ME)
    (source / "official/dl-9/source.json").unlink()
    with pytest.raises(ValueError, match="指定房各十桌"):
        g254.official_games(source)
