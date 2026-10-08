"""官方跨局首弃牌超时检查器的事件顺序回归。"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "tools/research/r18-four-arm-evaluation-2026-09-23/verify_sse_settled_first_discard.py"
SPEC = importlib.util.spec_from_file_location("verify_sse_settled_first_discard", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _write_game(
    root: Path, events: list[dict], *, duplicate: bool = False, split_at: int | None = None,
) -> None:
    """构造摘要一致的两局官方原文；duplicate 模拟同一批次下载重试。"""

    new_round_blocks = [{"round_no": 2, "dealer": 0, "truncated": False,
                         "events": events}]
    if split_at is not None:
        new_round_blocks = [
            {"round_no": 2, "dealer": 0, "truncated": False,
             "events": events[:split_at]},
            {"round_no": 2, "dealer": 0, "truncated": False,
             "events": events[split_at:]},
        ]
    document = {
        "status": "finished",
        "game_id": "t_example_r1_b0_t0",
        "seats": [{"user_id": "mine"}, {"user_id": "other"}],
        "blocks": [
            {"round_no": 1, "dealer": 1, "truncated": False,
             "events": [{"seq": 10, "type": "round_ended", "seat": 1,
                         "data": {"round_no": 1}}]},
        ] + new_round_blocks,
    }
    data = json.dumps(document, ensure_ascii=False).encode()
    for name in ("dl-a", "dl-b") if duplicate else ("dl-a",):
        target = root / name
        target.mkdir()
        (target / "events.json").write_bytes(data)
        (target / "source.json").write_text(json.dumps({
            "original_sha256": hashlib.sha256(data).hexdigest(),
        }))


def test_timeout_can_follow_opponent_draw_and_duplicate_download(tmp_path: Path) -> None:
    """官方可先推进下一人摸牌再记自动弃牌超时，重下载不应双计。"""

    _write_game(tmp_path, [
        {"seq": 11, "type": "tile_discarded", "seat": 0},
        {"seq": 12, "type": "tile_drawn", "seat": 1},
        {"seq": 13, "type": "timeout", "seat": 0, "data": {"kind": "discard"}},
    ], duplicate=True)
    result = MODULE.verify(tmp_path, "mine")
    assert result["complete_games"] == 1
    assert result["focal_first_discard_windows"] == 1
    assert result["focal_first_discard_timeouts"] == 1
    assert result["affected"][0]["timeout_seq"] == 13


def test_later_discard_timeout_does_not_attach_to_first(tmp_path: Path) -> None:
    """同局稍后的本人弃牌超时不得误归到跨局首弃牌。"""

    _write_game(tmp_path, [
        {"seq": 11, "type": "tile_discarded", "seat": 0},
        {"seq": 12, "type": "tile_drawn", "seat": 1},
        {"seq": 13, "type": "tile_discarded", "seat": 1},
        {"seq": 14, "type": "tile_drawn", "seat": 0},
        {"seq": 15, "type": "tile_discarded", "seat": 0},
        {"seq": 16, "type": "timeout", "seat": 0, "data": {"kind": "discard"}},
    ])
    result = MODULE.verify(tmp_path, "mine")
    assert result["focal_first_discard_windows"] == 1
    assert result["focal_first_discard_timeouts"] == 0


def test_same_round_split_across_blocks_preserves_timeout_link(tmp_path: Path) -> None:
    """官方可把同一单局拆为多个块；超时仍归属首弃牌。"""

    _write_game(tmp_path, [
        {"seq": 11, "type": "tile_discarded", "seat": 0},
        {"seq": 12, "type": "tile_drawn", "seat": 1},
        {"seq": 13, "type": "timeout", "seat": 0, "data": {"kind": "discard"}},
    ], split_at=2)
    result = MODULE.verify(tmp_path, "mine")
    assert result["focal_first_discard_windows"] == 1
    assert result["focal_first_discard_timeouts"] == 1
