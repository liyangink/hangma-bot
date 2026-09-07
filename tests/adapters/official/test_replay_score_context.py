"""导出积分变化不能冒充累计积分；通过公开牌谱解析入口检查非零起点。"""
from copy import deepcopy

from hangma_bot.adapters.official.replay import parse_room_document, round_data


def score_document():
    """构造两单局的协议样本，最终累计积分显式包含非零起点。"""
    first, second = [24, -8, -8, -8], [-16, 20, -2, -2]
    return {
        "room_id": "score-room", "game_id": "score-game", "batch": 0, "status": "finished",
        "rounds": [
            {"round_no": 1, "dealer": 0, "is_draw": False, "winner": 0, "multiplier": 1, "scores": first},
            {"round_no": 2, "dealer": 0, "is_draw": False, "winner": 1, "multiplier": 2, "scores": second},
        ],
        "blocks": [
            {"round_no": 1, "dealer": 0, "seq_start": 1, "seq_end": 1, "truncated": False,
             "events": [{"seq": 1, "type": "round_ended", "seat": 0,
                         "data": {"draw": False, "fan": 1, "scores": first}}]},
            {"round_no": 2, "dealer": 0, "seq_start": 2, "seq_end": 3, "truncated": False,
             "events": [{"seq": 2, "type": "round_ended", "seat": 1,
                         "data": {"draw": False, "fan": 2, "scores": second}},
                        {"seq": 3, "type": "game_ended", "seat": -1,
                         "data": {"final_scores": [108, 212, 290, 390]}}]},
        ],
    }


def read_hand(document, number):
    return round_data(parse_room_document(document), number, file_sha256="ab" * 32, json_pointer="#")


def test_hand_score_context_uses_terminal_total_without_assuming_zero_start():
    document = score_document()
    original = deepcopy(document)
    first, second = read_hand(document, 1), read_hand(document, 2)
    assert first["scores_before"] == [100, 200, 300, 400]
    assert first["scores_after"] == second["scores_before"] == [124, 192, 292, 392]
    assert second["scores_after"] == [108, 212, 290, 390]
    assert first["score_delta"] == [24, -8, -8, -8]
    assert second["score_delta"] == [-16, 20, -2, -2]
    assert document == original


def test_missing_terminal_total_does_not_promote_a_change_to_a_total():
    document = score_document()
    document["blocks"][-1]["events"].pop()
    document["blocks"][-1]["seq_end"] = 2
    row = read_hand(document, 2)
    assert row["scores_before"] is None
    assert row["scores_after"] is None
    assert row["score_delta"] is None  # 既有统一契约要求两端均已确认才填此字段。


def test_missing_later_settlement_prevents_inventing_earlier_cumulative_score():
    document = score_document()
    document["blocks"][-1]["events"].pop(0)
    document["blocks"][-1]["seq_start"] = 3
    row = read_hand(document, 1)
    assert row["scores_after"] is None
    assert row["scores_before"] is None


def test_block_order_does_not_change_score_context():
    document = score_document()
    expected = read_hand(document, 1)
    document["blocks"].reverse()
    actual = read_hand(document, 1)
    for field in ("scores_before", "scores_after", "score_delta"):
        assert actual[field] == expected[field]
