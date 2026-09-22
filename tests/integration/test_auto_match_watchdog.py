"""自由赛 watchdog 结算回归：部分下载不能吞掉完整审计场次。"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/auto_match_watchdog.py"
SPEC = importlib.util.spec_from_file_location("hangma_test_auto_match_watchdog", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
watchdog = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = watchdog
SPEC.loader.exec_module(watchdog)


def _source(session: Path, name: str, *, room: str, batch: object) -> None:
    folder = session / "official" / name
    folder.mkdir(parents=True)
    (folder / "source.json").write_text(
        json.dumps({"room_id": room, "batch": batch}), encoding="utf-8"
    )


def _audit_game(audit: Path, game_id: str, *, seat: int, scores: list[int]) -> None:
    folder = audit / "participants" / watchdog.ME / "games"
    folder.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "kind": "authoritative_state",
            "payload": {"window": {"seat": seat}},
        },
        {"kind": "game_finished", "payload": {"final_scores": scores}},
    ]
    (folder / (game_id + ".jsonl")).write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )


def test_download_resumes_missing_batches_instead_of_accepting_any_partial(
    monkeypatch, tmp_path
) -> None:
    room = "a_fixture"
    _source(tmp_path, "dl-existing", room=room, batch=0)
    _source(tmp_path, "dl-bad", room=room, batch=True)
    calls = []

    def fake_sh(command, **_kwargs):
        calls.append(command)
        assert "--batch 1" in command
        _source(tmp_path, "dl-new", room=room, batch=1)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(watchdog, "_declared_batches", lambda: 2)
    monkeypatch.setattr(watchdog, "sh", fake_sh)

    assert watchdog.download(room, str(tmp_path)) == str(tmp_path)
    assert len(calls) == 1
    assert watchdog._downloaded_batches(str(tmp_path), room) == {0, 1}


def test_settle_uses_union_and_audit_seat_when_download_misses_last_game(
    monkeypatch, tmp_path
) -> None:
    audit = tmp_path / "session" / "audit" / "runs" / "run-fixture"
    audit.mkdir(parents=True)
    _audit_game(audit, "g1", seat=2, scores=[-20, -10, 40, -10])
    monkeypatch.setattr(watchdog, "download", lambda *_args: str(tmp_path / "session"))
    monkeypatch.setattr(
        watchdog,
        "official_table",
        lambda *_args: {"g0": (1, 7)},
    )

    subtotal, games, _dest = watchdog.settle(str(audit), "a_fixture")

    assert subtotal == 47
    assert games == [
        {"game_id": "g0", "seat": 1, "final_score": 7, "source": "official_download补全"},
        {"game_id": "g1", "seat": 2, "final_score": 40, "source": "audit"},
    ]


def test_settle_rejects_conflicting_download_and_audit_seats(monkeypatch, tmp_path) -> None:
    audit = tmp_path / "session" / "audit" / "runs" / "run-fixture"
    audit.mkdir(parents=True)
    _audit_game(audit, "g0", seat=2, scores=[-20, -10, 40, -10])
    monkeypatch.setattr(watchdog, "download", lambda *_args: str(tmp_path / "session"))
    monkeypatch.setattr(watchdog, "official_table", lambda *_args: {"g0": (1, 7)})

    with pytest.raises(ValueError, match="座位冲突"):
        watchdog.settle(str(audit), "a_fixture")


def test_reconcile_ledger_adds_audit_only_game_and_recomputes_totals(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(watchdog, "ROOT", str(tmp_path))
    audit = tmp_path / "audit" / "runs" / "run-fixture"
    audit.mkdir(parents=True)
    _audit_game(audit, "g0", seat=1, scores=[-2, 5, -1, -2])
    _audit_game(audit, "g1", seat=2, scores=[-20, -10, 40, -10])
    ledger = {
        "cumulative_total": -95,
        "current_lose_streak": 1,
        "rooms": [
            {
                "room_id": "a_fixture",
                "audit_dir": "audit/runs/run-fixture",
                "room_subtotal": 5,
                "games": [
                    {"game_id": "g0", "seat": 1, "final_score": 5, "source": "audit"}
                ],
            },
            {"room_id": "a_other", "room_subtotal": -100, "games": []},
        ],
    }

    assert watchdog.reconcile_ledger(ledger)
    assert ledger["rooms"][0]["room_subtotal"] == 45
    assert ledger["rooms"][0]["games"][1] == {
        "game_id": "g1",
        "seat": 2,
        "final_score": 40,
        "source": "audit_reconciled",
    }
    assert ledger["cumulative_total"] == -55
    assert ledger["current_lose_streak"] == 1
    assert ledger["reconciliations"][-1]["repairs"][0]["added_games"] == ["g1"]
