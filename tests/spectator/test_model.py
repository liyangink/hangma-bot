"""P0 观战器：只读目录发现与显示投影测试。"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from spectator.model import (
    SpectatorRepository,
    discover_live_audit_roots,
    discover_run_directories,
)


def _record(kind: str, payload: dict, *, game_id: str | None = None, wall_time: int = 1000) -> dict:
    """构造一条脱敏审计信封；墙钟单位为 Unix 毫秒。"""

    return {
        "schema_version": 1,
        "kind": kind,
        "context": {
            "run_id": "run-a",
            "tournament_id": "t-a",
            "participant_id": "player-a",
            "game_id": game_id,
        },
        "wall_time_unix_ms": wall_time,
        "monotonic_ns": wall_time * 1_000_000,
        "payload": payload,
    }


def _observation(game_id: str, seq: int = 11) -> dict:
    """一个只含本家私有信息与桌面公开信息的玩家观察。"""

    return {
        "schema_version": 1,
        "game_id": game_id,
        "seat": 2,
        "round_no": 3,
        "snapshot_seq": seq,
        "consumed_seq": seq,
        "history_complete": True,
        "chain_piao": 0,
        "gang_draw": False,
        "observation_issues": [],
        "phase": "draw",
        "dealer_seat": 0,
        "turn_seat": 2,
        "responding_seats": [],
        "my_hand": ["1w", "2w", "白"],
        "drawn_tile": "3w",
        "discards": [["1t"], ["2t"], [], ["东"]],
        "melds": [[], [], [], []],
        "hand_counts": [13, 13, 14, 13],
        "last_discard": {"seat": 1, "tile": "2t", "seq": 10},
        "remaining_tile_count": 48,
        "scores": [5, -1, 8, -12],
        "rule_state": {
            "wealth_god": "白",
            "baotou": True,
            "chain_count": 2,
            "catch_play": False,
        },
        "public_history": [],
    }


def _write_line(path, document: dict, *, newline: bool = True) -> None:
    """向 JSONL 写一条信封；newline=False 模拟写线程尚未完成的一行。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(document, ensure_ascii=False))
        if newline:
            handle.write("\n")


def _make_run(tmp_path, *, slot: str = "slot-A"):
    """创建测试房间形态的单 Token 运行目录。"""

    run_dir = tmp_path / slot / "runs" / "run-a"
    manifest = _record(
        "run_manifest",
        {"mode": "test_room", "participant_id": "player-a", "run_id": "run-a"},
        wall_time=900,
    )
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return run_dir


def test_auto_discovers_test_room_slot_and_projects_multiple_games(tmp_path):
    """父目录输入自动发现 slot，且一个身份可切换两个官方场次。"""

    run_dir = _make_run(tmp_path)
    facts = {
        "fact_kind": "hand_progress",
        "shanten_after": 0,
        "useful_tiles": [{"code": "3w", "remaining_estimate": 3}],
        "best_followup_discard": None,
        "replacement_draw_unknown": False,
        "completeness": "complete",
        "note": None,
    }
    request = {
        "observation": _observation("g-one"),
        "rules": {
            "legal_candidates": [
                {"action_key": "discard:1w", "facts": facts},
            ]
        },
    }
    _write_line(
        run_dir / "participants" / "player-a" / "decisions.jsonl",
        _record("decision_input", {"request": request}, game_id="g-one", wall_time=1000),
    )
    _write_line(
        run_dir / "participants" / "player-a" / "decisions.jsonl",
        _record(
            "decision_planned",
            {
                "effective_candidates": [
                    {
                        "action_key": "discard:1w",
                        "rank": 1,
                        "action": {"kind": "discard", "tile": "1w"},
                        "reasons": ["测试候选"],
                        "total_score": 12.5,
                        "is_emergency": False,
                    }
                ]
            },
            game_id="g-one",
            wall_time=1001,
        ),
    )
    _write_line(
        run_dir / "participants" / "player-a" / "decisions.jsonl",
        _record("decision_input", {"request": {"observation": _observation("g-two", 7), "rules": {}}}, game_id="g-two", wall_time=1002),
    )
    raw = {
        "seq": 12,
        "snapshot": {
            "seat": 2,
            "round_no": 3,
            "phase": "draw",
            "turn": 2,
            "responding_seats": [],
            "dealer": 0,
            "my_hand": ["1w", "2w", "白"],
            "drawn_tile": "3w",
            "wall_remaining": 47,
            "scores": [5, -1, 8, -12],
            "last_discard": {"seat": 1, "tile": "2t", "seq": 10},
            "discards": [["1t"], ["2t"], [], ["东"]],
            "melds": [[], [], [], []],
            "hand_counts": [13, 13, 14, 13],
            "god": {"baotou": True, "chain_count": 2, "catch_play": False},
        },
    }
    _write_line(
        run_dir / "participants" / "player-a" / "raw" / "g-one.jsonl",
        _record("raw_protocol_state", {"source": "state_response", "raw": json.dumps(raw)}, game_id="g-one", wall_time=1003),
    )
    _write_line(
        run_dir / "participants" / "player-a" / "raw" / "g-one.jsonl",
        _record(
            "raw_protocol_state",
            {"source": "state_response", "raw": json.dumps({"seq": 13, "events": [{"seq": 13, "type": "tile_discarded", "seat": 2, "tile": "3w", "data": {}}]})},
            game_id="g-one",
            wall_time=1004,
        ),
    )

    # macOS 把 /var 映射到 /private/var；目录发现会规范化用户传入路径。
    assert discover_run_directories((tmp_path,)) == (run_dir.resolve(),)
    snapshot = SpectatorRepository((tmp_path,)).snapshot()

    assert snapshot["visibility"] == "single_player_observation"
    assert len(snapshot["sources"]) == 1
    source = snapshot["sources"][0]
    assert source["role"] == "slot-A"
    assert source["participant_id"] == "player-a"
    assert [game["game_id"] for game in source["games"]] == ["g-one", "g-two"]
    one = source["games"][0]
    assert one["observation_source"] == "权威快照"
    assert one["observation"]["my_hand"] == ["1w", "2w", "白"]
    assert one["candidates"][0]["facts"]["shanten_after"] == 0
    assert one["candidates"][0]["facts"]["useful_tiles"] == [{"code": "3w", "remaining_estimate": 3}]
    assert one["freshness"]["event_ahead_of_table_snapshot"] is True
    assert one["events"][0]["type"] == "tile_discarded"


def test_trailing_jsonl_line_is_not_visible_until_writer_completes_it(tmp_path):
    """活动文件尾部半行不产生半张手牌；补齐换行后才投影。"""

    run_dir = _make_run(tmp_path, slot="slot-B")
    path = run_dir / "participants" / "player-a" / "decisions.jsonl"
    record = _record(
        "decision_input",
        {"request": {"observation": _observation("g-live"), "rules": {}}},
        game_id="g-live",
    )
    _write_line(path, record, newline=False)
    repository = SpectatorRepository((tmp_path,))

    first = repository.snapshot()
    assert first["sources"] == []

    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n")
    second = repository.snapshot()
    game = second["sources"][0]["games"][0]
    assert game["game_id"] == "g-live"
    assert game["observation"]["my_hand"] == ["1w", "2w", "白"]


def test_snapshot_only_exposes_active_games_and_their_sources(tmp_path):
    """P0 不混入历史场次；同一活跃场次可由多个角色同时提供视角。"""

    first = _make_run(tmp_path, slot="slot-baihu")
    second = _make_run(tmp_path, slot="slot-qinglong")
    finished = _make_run(tmp_path, slot="slot-xuanwu")

    for run_dir in (first, second):
        _write_line(
            run_dir / "participants" / "player-a" / "decisions.jsonl",
            _record(
                "decision_input",
                {"request": {"observation": _observation("g-live"), "rules": {}}},
                game_id="g-live",
            ),
        )
    _write_line(
        first / "participants" / "player-a" / "decisions.jsonl",
        _record(
            "decision_input",
            {"request": {"observation": _observation("g-old"), "rules": {}}},
            game_id="g-old",
        ),
    )
    _write_line(
        first / "participants" / "player-a" / "decisions.jsonl",
        _record("game_finished", {"final_scores": [1, 2, 3, 4]}, game_id="g-old"),
    )
    _write_line(
        finished / "participants" / "player-a" / "decisions.jsonl",
        _record(
            "decision_input",
            {
                "request": {
                    "observation": {**_observation("g-finished"), "phase": "finished"},
                    "rules": {},
                }
            },
            game_id="g-finished",
        ),
    )

    snapshot = SpectatorRepository((tmp_path,)).snapshot()

    assert [source["role"] for source in snapshot["sources"]] == [
        "slot-baihu",
        "slot-qinglong",
    ]
    assert all([game["game_id"] for game in source["games"]] == ["g-live"] for source in snapshot["sources"])


def test_discovers_checked_in_legacy_test_room_audit_layout():
    """精选的真实历史审计布局仍能被发现；结束的牌局不进入实时观战快照。"""

    repository_root = Path(__file__).resolve().parents[2]
    audit_root = (
        repository_root
        / "tests/fixtures/legacy-audit"
    )
    target_run = audit_root / "xuanwu/run-8c975e27eaa14429973671b841c88923"

    assert target_run.resolve() in discover_run_directories((audit_root,))
    snapshot = SpectatorRepository((audit_root,)).snapshot()

    assert all(item["run_id"] != target_run.name for item in snapshot["sources"])


def _make_batch(sessions_root: Path, name: str, *, run_id: str, game_id: str, wall_time: int = 1000):
    """在赛事父目录下造一个批次审计根：<会话>/audit/runs/<run_id>。"""

    run_dir = sessions_root / name / "audit" / "runs" / run_id
    manifest = _record(
        "run_manifest",
        {"mode": "auto_match", "participant_id": "player-a", "run_id": run_id},
        wall_time=wall_time,
    )
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    request = {"observation": _observation(game_id), "rules": {"legal_candidates": []}}
    _write_line(
        run_dir / "participants" / "player-a" / "decisions.jsonl",
        _record("decision_input", {"request": request}, game_id=game_id, wall_time=wall_time),
    )
    return run_dir


def _age_tree(directory: Path, *, seconds: float) -> None:
    """把一个目录树内所有文件的时间戳往前挪，模拟已经停止写入的批次。"""

    stamp = time.time() - seconds
    for path in directory.rglob("*"):
        if path.is_file():
            os.utime(path, (stamp, stamp))


def test_follow_mode_ignores_stale_batch_and_postgame_writes(tmp_path):
    """跟随父目录时，只有 runs/ 子树仍在写入的批次算活跃；赛后 postgame 不算。"""

    sessions = tmp_path / "sessions"
    stale_run = _make_batch(sessions, "batch-old", run_id="run-old", game_id="g-old")
    _age_tree(stale_run, seconds=7200)
    # 刚结束的批次仍在写 postgame，但它不是活跃对局，不能被当成进行中的批次。
    postgame = sessions / "batch-old" / "postgame" / "archive"
    postgame.mkdir(parents=True)
    (postgame / "report.json").write_text("{}", encoding="utf-8")
    _make_batch(sessions, "batch-new", run_id="run-new", game_id="g-new", wall_time=2000)

    roots = discover_live_audit_roots(sessions, window_seconds=600)
    assert [root.parent.name for root in roots] == ["batch-new"]


def test_follow_mode_picks_up_next_batch_without_restart(tmp_path):
    """新批次出现后，同一个观战器实例无需重启即可发现并显示其活跃对局。"""

    sessions = tmp_path / "sessions"
    _make_batch(sessions, "batch-001", run_id="run-a", game_id="g-one")
    repository = SpectatorRepository(follow_sessions_root=sessions, rescan_seconds=0)
    assert [root.parent.name for root in repository.followed_roots] == ["batch-001"]
    assert [game["game_id"] for source in repository.snapshot()["sources"] for game in source["games"]] == ["g-one"]

    # 换批：新批次是兄弟目录，之前只固定单一批次目录的实现会永远看不到它。
    _make_batch(sessions, "batch-002", run_id="run-b", game_id="g-two", wall_time=2000)
    game_ids = sorted(
        game["game_id"]
        for source in repository.snapshot()["sources"]
        for game in source["games"]
    )
    assert game_ids == ["g-one", "g-two"]


def test_follow_mode_drops_batch_after_it_leaves_the_live_window(tmp_path):
    """批次停止写入并超出活跃窗口后，观战器不再跟随它。"""

    sessions = tmp_path / "sessions"
    run_dir = _make_batch(sessions, "batch-001", run_id="run-a", game_id="g-one")
    repository = SpectatorRepository(
        follow_sessions_root=sessions, live_window_seconds=600, rescan_seconds=0
    )
    assert repository.followed_roots

    _age_tree(run_dir, seconds=7200)
    repository.refresh()
    assert repository.followed_roots == ()
    assert repository.snapshot()["sources"] == []

