"""自由赛 watchdog 结算回归：部分下载不能吞掉完整审计场次。"""

from __future__ import annotations

import importlib.util
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import sys
import subprocess

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


def _terminal_session(
    root: Path, name: str, room: str, *, reason: str = "matching_unavailable"
) -> tuple[Path, Path]:
    audit = root / "artifacts" / name / "audit" / "runs" / "run-fixture"
    audit.mkdir(parents=True)
    log = root / "runs" / "auto-match-watchdog" / f"session-{name}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(
        "RESULT "
        + json.dumps({"terminal_reason": reason, "audit_dir": str(audit.relative_to(root))})
        + "\n",
        encoding="utf-8",
    )
    _audit_game(audit, f"{room}_r1_b1_t0", seat=2, scores=[-20, -10, 40, -10])
    return log, audit


def test_one_room_accounted_session_does_not_start_another_player(monkeypatch, tmp_path, capsys):
    """通过巡检入口确认单房验收结算后不会再次匹配。"""
    log, audit = _terminal_session(tmp_path, "single", "a_fixture", reason="tournament_finished")
    state = log.parent
    ledger = state / "auto-match-watchdog-state.json"
    ledger.write_text(json.dumps({"cumulative_total": 40, "current_lose_streak": 0,
        "rooms": [{"room_id": "a_fixture", "session_log": str(log.relative_to(tmp_path)),
            "audit_dir": str(audit.relative_to(tmp_path)), "room_subtotal": 40,
            "games": [{"game_id": "a_fixture_r1_b1_t0", "seat": 2, "final_score": 40}],
            "terminal_reason": "tournament_finished"}]}))
    monkeypatch.setattr(watchdog, "ROOT", str(tmp_path))
    monkeypatch.setattr(watchdog, "STATE", str(state))
    monkeypatch.setattr(watchdog, "LEDGER", str(ledger))
    monkeypatch.setenv("WATCHDOG_ONE_ROOM", "1")
    monkeypatch.setattr(watchdog, "sh", lambda *_args, **_kwargs: SimpleNamespace(returncode=1))

    def forbidden_player(*_args, **_kwargs):
        raise AssertionError("单房验收不允许再启动玩家")

    monkeypatch.setattr(watchdog.subprocess, "Popen", forbidden_player)
    assert watchdog.main() == 0
    assert "不再开房" in capsys.readouterr().out


def test_watch_shell_uses_isolated_state_and_requested_interpreter(tmp_path):
    """停止态通过真实壳入口读取独立账本，不触碰默认战役或启动网络玩家。"""
    state = tmp_path / "state"
    state.mkdir()
    ledger = state / "auto-match-watchdog-state.json"
    ledger.write_text(json.dumps({"cumulative_total": 17, "current_lose_streak": 0,
                                "rooms": [], "stopped": True}))
    before = ledger.read_bytes()
    env = dict(os.environ, WATCHDOG_STATE_DIR=str(state), WATCHDOG_PYTHON=sys.executable,
               WATCHDOG_ONE_ROOM="1")
    result = subprocess.run(["bash", str(SCRIPT.with_name("auto_match_watch.sh"))],
                            env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0 and "累计 17" in result.stdout
    assert ledger.read_bytes() == before


def _official_game(session: Path, room: str, batch: int, *, status="finished",
                   final_override=None, user_override=None, omit_round=None) -> None:
    folder = session / "official" / f"dl-{batch}"
    folder.mkdir(parents=True)
    scores = [-20, -10, 40, -10]
    rounds = []
    blocks = []
    for round_no in range(1, 9):
        delta = scores if round_no == 1 else [0, 0, 0, 0]
        rounds.append({"round_no": round_no, "scores": delta})
        events = ([] if round_no == omit_round else [{"type": "round_ended",
                   "seq": round_no, "data": {"round_no": round_no, "scores": delta}}])
        if round_no == 8:
            events.append({"type": "game_ended", "seq": 9,
                           "data": {"final_scores": final_override or scores}})
        blocks.append({"round_no": round_no, "events": events})
    gid = f"{room}_r1_b{batch}_t0"
    doc = {"room_id": room, "batch": batch, "game_id": gid, "status": status,
           "seats": [{"user_id": user_override or "u_other0"},
                     {"user_id": "u_other1"}, {"user_id": watchdog.ME},
                     {"user_id": "u_other3"}],
           "rounds": rounds, "blocks": blocks}
    raw = json.dumps(doc).encode("utf-8")
    (folder / "events.json").write_bytes(raw)
    (folder / "source.json").write_text(json.dumps({"room_id": room, "batch": batch,
         "game_id": gid, "original_sha256": hashlib.sha256(raw).hexdigest()}), encoding="utf-8")


def test_matching_unavailable_recovers_only_complete_official_room_and_resumes(
    monkeypatch, tmp_path
) -> None:
    log, _audit = _terminal_session(tmp_path, "complete", "a_complete")
    session = tmp_path / "artifacts" / "complete"
    for batch in range(10):
        _official_game(session, "a_complete", batch)
    ledger = {"cumulative_total": 0, "current_lose_streak": 0, "rooms": []}
    restarted = []
    monkeypatch.setattr(watchdog, "ROOT", str(tmp_path))
    monkeypatch.setattr(watchdog, "load_ledger", lambda: ledger)
    monkeypatch.setattr(watchdog, "save_ledger", lambda _ledger: None)
    monkeypatch.setattr(watchdog, "session_alive", lambda: False)
    monkeypatch.setattr(watchdog, "latest_session_log", lambda: str(log))
    monkeypatch.setattr(watchdog, "_declared_batches", lambda: 10)
    monkeypatch.setattr(watchdog, "download", lambda *_args, **_kw: str(session))
    monkeypatch.setattr(watchdog, "maybe_restart", lambda: restarted.append(True))

    assert watchdog.run_cycle() == 0
    assert ledger["cumulative_total"] == 400
    assert len(ledger["rooms"][0]["games"]) == 10
    assert ledger["rooms"][0]["settlement_status"] == "official_recovered_complete"
    assert ledger.get("stopped") is not True
    assert restarted == [True]
    assert watchdog.run_cycle() == 0
    assert ledger["cumulative_total"] == 400
    assert restarted == [True, True]


@pytest.mark.parametrize("damage", [
    "missing_batch", "running_status", "missing_round_end", "wrong_game_total",
    "duplicate_me", "source_digest_mismatch",
])
def test_matching_unavailable_incomplete_or_untrusted_archive_stays_provisional(
    monkeypatch, tmp_path, damage
) -> None:
    log, _audit = _terminal_session(tmp_path, "damaged", "a_damaged")
    session = tmp_path / "artifacts" / "damaged"
    for batch in range(10):
        if damage == "missing_batch" and batch == 5:
            continue
        kw = {}
        if batch == 5:
            if damage == "running_status":
                kw["status"] = "running"
            if damage == "missing_round_end":
                kw["omit_round"] = 3
            if damage == "wrong_game_total":
                kw["final_override"] = [-21, -10, 41, -10]
            if damage == "duplicate_me":
                kw["user_override"] = watchdog.ME
        _official_game(session, "a_damaged", batch, **kw)
    if damage == "source_digest_mismatch":
        with (session / "official" / "dl-5" / "events.json").open("ab") as f:
            f.write(b" ")
    ledger = {"cumulative_total": 0, "current_lose_streak": 0, "rooms": []}
    restarted = []
    monkeypatch.setattr(watchdog, "ROOT", str(tmp_path))
    monkeypatch.setattr(watchdog, "load_ledger", lambda: ledger)
    monkeypatch.setattr(watchdog, "save_ledger", lambda _ledger: None)
    monkeypatch.setattr(watchdog, "session_alive", lambda: False)
    monkeypatch.setattr(watchdog, "latest_session_log", lambda: str(log))
    monkeypatch.setattr(watchdog, "_declared_batches", lambda: 10)
    monkeypatch.setattr(watchdog, "download", lambda *_args, **_kw: str(session))
    monkeypatch.setattr(watchdog, "maybe_restart", lambda: restarted.append(True))

    assert watchdog.run_cycle() == 3
    assert restarted == []
    assert ledger["stopped"] is True
    assert ledger["cumulative_total"] == 40
    assert ledger["rooms"][0]["settlement_status"] == "provisional"
    assert ledger["rooms"][0]["verification_issue"]


def test_matching_unavailable_download_429_does_not_retry_or_resume(
    monkeypatch, tmp_path
) -> None:
    room = "a_rate_limited"
    for batch in range(1, 10):
        _source(tmp_path, f"dl-{batch}", room=room, batch=batch)
    requests = []

    def rate_limited(command, **_kw):
        requests.append(command)
        return SimpleNamespace(returncode=1, stderr="HTTP 429", stdout="")

    monkeypatch.setattr(watchdog, "_declared_batches", lambda: 10)
    monkeypatch.setattr(watchdog, "sh", rate_limited)
    monkeypatch.setattr(watchdog.time, "sleep", lambda _sec: pytest.fail("不得退避重试"))
    assert watchdog.download(room, str(tmp_path), max_attempts=1) is None
    assert len(requests) == 1


def test_matching_unavailable_with_completed_game_keeps_score_and_stops(
    monkeypatch, tmp_path
) -> None:
    log, _audit = _terminal_session(tmp_path, "partial", "a_partial")
    ledger = {"cumulative_total": 0, "current_lose_streak": 0, "rooms": []}
    restarted = []
    monkeypatch.setattr(watchdog, "ROOT", str(tmp_path))
    monkeypatch.setattr(watchdog, "STATE", str(log.parent))
    monkeypatch.setattr(watchdog, "load_ledger", lambda: ledger)
    monkeypatch.setattr(watchdog, "save_ledger", lambda _ledger: None)
    monkeypatch.setattr(watchdog, "session_alive", lambda: False)
    monkeypatch.setattr(watchdog, "latest_session_log", lambda: str(log))
    monkeypatch.setattr(watchdog, "_declared_batches", lambda: 10)
    monkeypatch.setattr(watchdog, "download", lambda *_args, **_kw: None)
    monkeypatch.setattr(watchdog, "maybe_restart", lambda: restarted.append(True))

    assert watchdog.run_cycle() == 3
    assert restarted == []
    assert ledger["cumulative_total"] == 40
    assert ledger["stopped"] is True
    assert ledger["rooms"] == [{
        "room_id": "a_partial",
        "session_log": str(log.relative_to(tmp_path)),
        "audit_dir": str(_audit.relative_to(tmp_path)),
        "download_dir": None,
        "terminal_reason": "matching_unavailable",
        "settlement_status": "provisional",
        "verification_issue": "ValueError:official_download_incomplete",
        "room_subtotal": 40,
        "games": [{"game_id": "a_partial_r1_b1_t0", "seat": 2,
                   "final_score": 40, "source": "audit"}],
    }]
    assert watchdog.run_cycle() == 3
    assert len(ledger["rooms"]) == 1
    assert restarted == []


def test_matching_unavailable_without_completed_game_still_stops(
    monkeypatch, tmp_path
) -> None:
    log, audit = _terminal_session(tmp_path, "unknown", "a_unknown")
    for game in (audit / "participants" / watchdog.ME / "games").glob("*.jsonl"):
        game.unlink()
    ledger = {"cumulative_total": 0, "current_lose_streak": 0, "rooms": []}
    restarted = []
    monkeypatch.setattr(watchdog, "ROOT", str(tmp_path))
    monkeypatch.setattr(watchdog, "load_ledger", lambda: ledger)
    monkeypatch.setattr(watchdog, "save_ledger", lambda _ledger: None)
    monkeypatch.setattr(watchdog, "session_alive", lambda: False)
    monkeypatch.setattr(watchdog, "latest_session_log", lambda: str(log))
    monkeypatch.setattr(watchdog, "maybe_restart", lambda: restarted.append(True))

    assert watchdog.run_cycle() == 3
    assert ledger["rooms"] == []
    assert ledger["stopped"] is True
    assert ledger["unresolved_sessions"][0]["session_log"] == str(log.relative_to(tmp_path))
    assert restarted == []
    assert watchdog.run_cycle() == 3
    assert len(ledger["unresolved_sessions"]) == 1


def test_matching_unavailable_resume_of_accounted_room_never_double_counts(
    monkeypatch, tmp_path
) -> None:
    log, _audit = _terminal_session(tmp_path, "resumed", "a_accounted")
    prior = {"room_id": "a_accounted", "session_log": "old-session.log",
             "room_subtotal": 40, "games": []}
    ledger = {"cumulative_total": 40, "current_lose_streak": 0, "rooms": [prior]}
    restarted = []
    monkeypatch.setattr(watchdog, "ROOT", str(tmp_path))
    monkeypatch.setattr(watchdog, "load_ledger", lambda: ledger)
    monkeypatch.setattr(watchdog, "save_ledger", lambda _ledger: None)
    monkeypatch.setattr(watchdog, "session_alive", lambda: False)
    monkeypatch.setattr(watchdog, "latest_session_log", lambda: str(log))
    monkeypatch.setattr(watchdog, "maybe_restart", lambda: restarted.append(True))

    assert watchdog.run_cycle() == 3
    assert ledger["rooms"] == [prior]
    assert ledger["cumulative_total"] == 40
    assert ledger["unresolved_sessions"][0]["reason"] == "room_already_accounted"
    assert restarted == []
