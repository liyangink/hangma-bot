"""指南v19（2026-09-07抓取）新增终局局号/庄家键的兼容性回归。

输入按官方说明构造，不冒充真实牌局抓包；新增键不影响旧字段解析。
完整原文由HTTP审计保留，规范事件只消费当前支持的字段。
"""
import pytest

from hangma_bot.adapters.official.dto import parse_state_response


@pytest.mark.parametrize("draw,winner", [(True, -1), (False, 2)])
def test_round_ended_extra_metadata_does_not_change_known_fields(draw, winner):
    payload = {"draw": draw, "scores": [0, 0, 0, 0] if draw else [-1, -1, 3, -1],
               "round_no": 8, "dealer": 1}
    response = parse_state_response({"events": [
        {"seq": 501, "type": "round_ended", "seat": winner,
         "tile": "", "data": payload, "ts": 1788750000}]})
    event = response.events[0]
    assert event.type == "round_ended"
    assert event.seat == (None if draw else winner)
    assert event.result_draw is draw
    assert event.result_scores == tuple(payload["scores"])
    legacy = {key: value for key, value in payload.items() if key not in ("round_no", "dealer")}
    legacy_response = parse_state_response({"events": [
        {"seq": 501, "type": "round_ended", "seat": winner,
         "tile": "", "data": legacy, "ts": 1788750000}]})
    assert response == legacy_response
