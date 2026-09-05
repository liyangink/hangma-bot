"""last_discard 官方占位符回归（"0w" = 本局尚无弃牌）。

背景（2026-09-05 测试房实测）：游戏开局快照的 last_discard 携带 "0w"
占位符而非空串，旧实现按非法牌码抛 DtoError，导致每场开局一次
dto_invalid 重建循环（自愈但有 0.5-1s 代价）。验收报告 §4.1。
"""

import pytest

from hangma_bot.adapters.official.dto import DtoError, _parse_last_discard as parse_last_discard


class TestLastDiscardPlaceholder:
    def test_placeholder_0w_maps_to_none(self) -> None:
        """占位符 "0w" 语义等同无弃牌。"""

        assert parse_last_discard("0w") is None

    def test_empty_and_none_still_none(self) -> None:
        assert parse_last_discard("") is None
        assert parse_last_discard(None) is None

    def test_real_tile_still_valid(self) -> None:
        assert parse_last_discard("5w") == "5w"

    def test_other_bad_codes_still_rejected(self) -> None:
        """除官方占位符外，非法牌码仍按协议错误拒绝（不静默丢弃）。"""

        with pytest.raises(DtoError):
            parse_last_discard("9z")
