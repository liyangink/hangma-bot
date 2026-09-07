"""官方分块转换的事件 JSON Pointer 跨局对齐测试（审查返工回归）。

缺陷背景：merge_round_events 曾用"按 round_no 过滤后重新排序的局部
块下标"生成 /blocks/{i}/events/{j}——多局文档里第二局的下标会错位
指向第一局的块。修复后指针必须指向原文档 blocks 数组下标。
"""

from __future__ import annotations

import json

from hangma_bot.adapters.official.replay import (
    merge_round_events,
    parse_room_document,
    round_data,
)


def _block(round_no: int, seq_start: int, seq_end: int) -> dict:
    events = []
    for offset, seq in enumerate(range(seq_start, seq_end + 1)):
        events.append(
            {
                "seq": seq,
                "type": "tile_discarded" if offset % 2 == 0 else "timeout",
                "seat": 0,
                "tile": "1w" if offset % 2 == 0 else "",
                "data": None,
                "ts": 1,
            }
        )
    return {
        "round_no": round_no,
        "seq_start": seq_start,
        "seq_end": seq_end,
        "truncated": False,
        "dealer": 0,
        "start_hands": [
            ["1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "1b", "2b", "3b", "4b", "5b"],
            ["2b", "3b", "4b", "5b", "6b", "7b", "8b", "9b", "1t", "2t", "3t", "4t", "5t"],
            ["6t", "7t", "8t", "9t", "东", "南", "西", "北", "中", "发", "白", "1w", "2w"],
            ["3w", "4w", "5w", "6w", "7w", "8w", "9w", "1b", "2b", "3b", "4b", "5b", "6b"],
        ],
        "events": events,
    }


def _two_round_document():
    return {
        "room_id": "t_multi",
        "game_id": "t_multi_r2_b0_t0",
        "batch": 0,
        "status": "finished",
        "seats": [],
        "rounds": [
            {"round_no": 1, "dealer": 0, "is_draw": 0, "winner": 0, "scores": [1, 0, 0, 0]},
            {"round_no": 2, "dealer": 0, "is_draw": 0, "winner": 1, "scores": [1, 2, 0, 0]},
        ],
        "blocks": [
            _block(1, 1, 3),   # 文档下标 0（第 1 局块 1）
            _block(1, 4, 5),   # 文档下标 1（第 1 局块 2）
            _block(2, 1, 2),   # 文档下标 2（第 2 局块 1）
            _block(2, 3, 5),   # 文档下标 3（第 2 局块 2）
        ],
    }


def test_round_two_pointers_reference_document_block_indexes():
    parsed = parse_room_document(_two_round_document())
    merged = merge_round_events(parsed, 2)
    assert merged["event_pointers"] == [
        "/blocks/2/events/0",
        "/blocks/2/events/1",
        "/blocks/3/events/0",
        "/blocks/3/events/1",
        "/blocks/3/events/2",
    ]
    # 第 1 局仍指向文档下标 0/1（过滤后排序恰好一致，不得回归）。
    merged1 = merge_round_events(parsed, 1)
    assert merged1["event_pointers"][0].startswith("/blocks/0/")
    assert merged1["event_pointers"][-1].startswith("/blocks/1/")


def test_round_data_carries_document_aligned_pointers():
    parsed = parse_room_document(_two_round_document())
    data = round_data(parsed, 2, file_sha256="ab" * 32, json_pointer="#")
    assert data["event_pointers"][0] == "/blocks/2/events/0"
    assert data["event_pointers"][-1] == "/blocks/3/events/2"
    assert data["coverage"] == "full_history"
    # 只有出牌与超时事件，顶层汇总不能代替缺失的单局结束事实。
    assert data["winner_seat"] is None
    assert not data["result_confirmed"]


def test_single_round_document_pointers_unchanged():
    document = _two_round_document()
    document["blocks"] = document["blocks"][:2]
    parsed = parse_room_document(document)
    merged = merge_round_events(parsed, 1)
    assert merged["event_pointers"][0] == "/blocks/0/events/0"
    assert merged["event_pointers"][-1] == "/blocks/1/events/1"
