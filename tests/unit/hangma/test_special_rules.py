"""special_rules 单元测试：财神限制、抓打圈、爆头、有财必拷响与链判定。

只通过模块公开函数验证行为；金例口径见 RULES_EVIDENCE.md §5/§6/§7/§8。
"""

from __future__ import annotations

import pytest

from hangma_bot.kernel.actions import (
    Chi,
    Discard,
    Gang,
    GangKind,
    Hu,
    Pass,
    Peng,
    Tile,
)
from hangma_bot.kernel.observation import PublicEvent
from hangma_bot.hangma.internal_types import WinSplit
from hangma_bot.hangma.special_rules import (
    catch_play_restriction,
    chain_breaks_on_discard,
    is_gang_draw,
    is_piao_discard,
    static_baotou,
    wealth_action_restriction,
    you_cai_bi_kao_block,
)


def _tile(code: str) -> Tile:
    return Tile(code)


def _split(
    branch: str = "平胡",
    whites: int = 0,
    tenpai: bool = False,
    luxury: int = 0,
) -> WinSplit:
    """构造测试用胡牌分解元数据；evidence 与本模块判定无关。"""

    return WinSplit(
        branch=branch,
        luxury_pairs=luxury,
        whites_held=whites,
        any_tile_tenpai=tenpai,
        evidence=(),
    )


def _event(seq: int, kind: str, seat: int, tiles=()) -> PublicEvent:
    return PublicEvent(
        seq=seq, kind=kind, seat=seat, tiles=tuple(Tile(code) for code in tiles)
    )


class TestWealthActionRestriction:
    """财神不能被吃/碰/杠；可主动打出（指南 1.1、§6）。"""

    def test_chi_with_wealth_claimed_tile_blocked(self):
        # 被吃牌本身是白：财神不能被吃（组合按规范牌序升序构造）。
        action = Chi((_tile("1w"), _tile("2w"), _tile("白")))
        assert wealth_action_restriction(action) is not None

    def test_chi_with_wealth_hand_tile_blocked(self):
        # 两张手牌之一为白同样非法（吃牌组合不得含白）。
        action = Chi((_tile("2w"), _tile("3w"), _tile("白")))
        assert wealth_action_restriction(action) is not None

    def test_normal_chi_allowed(self):
        action = Chi((_tile("1w"), _tile("2w"), _tile("3w")))
        assert wealth_action_restriction(action) is None

    def test_peng_wealth_blocked(self):
        assert wealth_action_restriction(Peng(_tile("白"))) is not None

    def test_peng_normal_allowed(self):
        assert wealth_action_restriction(Peng(_tile("5t"))) is None

    @pytest.mark.parametrize("kind", list(GangKind))
    def test_gang_wealth_blocked_for_all_kinds(self, kind):
        # 白不参与任何杠：暗杠/明杠/补杠一视同仁。
        assert wealth_action_restriction(Gang(_tile("白"), kind)) is not None

    def test_gang_normal_allowed(self):
        assert wealth_action_restriction(Gang(_tile("9b"), GangKind.CONCEALED)) is None

    def test_discard_wealth_allowed(self):
        # 财神可主动打出（飘的前提）。
        assert wealth_action_restriction(Discard(_tile("白"))) is None

    def test_hu_and_pass_unrestricted(self):
        assert wealth_action_restriction(Hu()) is None
        assert wealth_action_restriction(Pass()) is None


class TestCatchPlayRestriction:
    """抓打圈：只能打刚摸的牌；不能吃碰明杠补杠；暗杠与自摸胡仍可（API §5.4）。"""

    def test_discard_drawn_tile_allowed(self):
        drawn = _tile("白")
        assert catch_play_restriction(Discard(_tile("白")), drawn) is None

    def test_discard_other_tile_blocked(self):
        drawn = _tile("5w")
        assert catch_play_restriction(Discard(_tile("白")), drawn) is not None

    def test_discard_without_drawn_tile_blocked(self):
        # 缺少摸牌信息时保守拒绝，不得放行无法核对的出牌。
        assert catch_play_restriction(Discard(_tile("5w")), None) is not None

    def test_chi_and_peng_blocked(self):
        drawn = _tile("5w")
        chi = Chi((_tile("3w"), _tile("4w"), _tile("5w")))
        assert catch_play_restriction(chi, drawn) is not None
        assert catch_play_restriction(Peng(_tile("5w")), drawn) is not None

    def test_exposed_and_added_gang_blocked(self):
        drawn = _tile("5w")
        exposed = Gang(_tile("5w"), GangKind.EXPOSED)
        added = Gang(_tile("5w"), GangKind.ADDED)
        assert catch_play_restriction(exposed, drawn) is not None
        assert catch_play_restriction(added, drawn) is not None

    def test_concealed_gang_allowed(self):
        drawn = _tile("5w")
        concealed = Gang(_tile("9b"), GangKind.CONCEALED)
        assert catch_play_restriction(concealed, drawn) is None

    def test_hu_and_pass_allowed(self):
        assert catch_play_restriction(Hu(), None) is None
        assert catch_play_restriction(Pass(), None) is None


class TestPiaoAndChain:
    """飘 = 爆头状态下打财神；非飘弃牌断链（指南 1.3、§8）。"""

    def test_wealth_discard_while_baotou_is_piao(self):
        assert is_piao_discard(_tile("白"), True) is True

    def test_wealth_discard_without_baotou_not_piao(self):
        assert is_piao_discard(_tile("白"), False) is False

    def test_normal_discard_never_piao(self):
        assert is_piao_discard(_tile("5w"), True) is False

    def test_chain_breaks_on_normal_discard(self):
        assert chain_breaks_on_discard(_tile("5w"), True) is True

    def test_chain_breaks_on_non_baotou_white_discard(self):
        # 非爆头态打白板 = 普通弃牌，链断清零。
        assert chain_breaks_on_discard(_tile("白"), False) is True

    def test_chain_continues_on_piao(self):
        assert chain_breaks_on_discard(_tile("白"), True) is False


class TestStaticBaotou:
    """静态爆头 = 任意听 ∧ 手留白板数 ≠ 4（§5）。"""

    def test_tenpai_with_three_whites_is_baotou(self):
        assert static_baotou(_split(whites=3, tenpai=True)) is True

    def test_four_whites_held_never_baotou(self):
        # 正好 4 张手留白板不视为爆头（金例 four-white-kept / chiitoi-held4）。
        assert static_baotou(_split(whites=4, tenpai=True)) is False

    def test_not_tenpai_is_not_baotou(self):
        assert static_baotou(_split(whites=0, tenpai=False)) is False

    def test_chiitoi_branch_follows_same_rule(self):
        assert static_baotou(_split("七对", whites=1, tenpai=True)) is True


class TestYouCaiBiKao:
    """有财必拷响：手留财神时须爆头/杠开才能胡（§7，含保守假设）。"""

    def test_switch_off_never_blocks(self):
        win = _split(whites=1)
        assert you_cai_bi_kao_block(False, win, False, False) is None

    def test_no_wealth_in_hand_never_blocks(self):
        win = _split(whites=0)
        assert you_cai_bi_kao_block(True, win, False, False) is None

    def test_plain_hu_with_wealth_blocked(self):
        win = _split("平胡", whites=1)
        assert you_cai_bi_kao_block(True, win, False, False) is not None

    def test_baotou_releases_block(self):
        win = _split("平胡", whites=1)
        assert you_cai_bi_kao_block(True, win, True, False) is None

    def test_gang_draw_releases_block(self):
        win = _split("平胡", whites=1)
        assert you_cai_bi_kao_block(True, win, False, True) is None

    def test_chiitoi_conservatively_blocked(self):
        # 【假设】七对分支是否豁免未确认——保守同样要求爆头/杠开。
        win = _split("七对", whites=2)
        reason = you_cai_bi_kao_block(True, win, False, False)
        assert reason is not None and "七对" in reason

    def test_blocked_reason_mentions_rule_name(self):
        win = _split("平胡", whites=3)
        reason = you_cai_bi_kao_block(True, win, False, False)
        assert reason is not None and "有财必拷响" in reason and "3" in reason


class TestIsGangDraw:
    """杠上摸牌推断：本人杠事件紧跟本人摸牌事件（§7 假设）。"""

    def test_gang_then_draw_is_gang_draw(self):
        history = (
            _event(10, "gang", 2, ("9b",)),
            _event(11, "tile_drawn", 2),
        )
        assert is_gang_draw(history, 2) is True

    def test_normal_draw_after_discard_is_not_gang_draw(self):
        history = (
            _event(9, "gang", 2, ("9b",)),
            _event(10, "tile_discarded", 2, ("9b",)),
            _event(11, "tile_drawn", 2),
        )
        assert is_gang_draw(history, 2) is False

    def test_other_seat_gang_does_not_count(self):
        history = (
            _event(10, "gang", 1, ("9b",)),
            _event(11, "tile_drawn", 2),
        )
        assert is_gang_draw(history, 2) is False

    def test_latest_draw_matters(self):
        # 杠后补牌已打出，最近一次摸牌是普通摸牌 → False。
        history = (
            _event(10, "gang", 2, ("9b",)),
            _event(11, "tile_drawn", 2),
            _event(12, "tile_discarded", 2, ("9b",)),
            _event(13, "tile_drawn", 2),
        )
        assert is_gang_draw(history, 2) is False

    def test_unknown_event_between_gang_and_draw_is_conservatively_false(self):
        history = (
            _event(10, "gang", 2, ("9b",)),
            _event(11, "timeout", None),
            _event(12, "tile_drawn", 2),
        )
        assert is_gang_draw(history, 2) is False

    def test_seq_gap_between_gang_and_draw_is_false(self):
        """评审 d4-4f5bf9 回归：seq 缺口（历史不完整）不得误授杠开豁免。

        杠开豁免会绕过有财必拷响门禁，缺口历史必须保守判 False。
        """

        gap = (
            _event(10, "gang", 2, ("9b",)),
            # 缺 11-13：事件流存在缺口（长轮询恢复场景）。
            _event(14, "tile_drawn", 2),
        )
        assert is_gang_draw(gap, 2) is False

    def test_empty_history_or_drawless_history_is_false(self):
        assert is_gang_draw((), 0) is False
        history = (_event(10, "tile_discarded", 0, ("5w",)),)
        assert is_gang_draw(history, 0) is False

    def test_first_event_draw_has_no_predecessor(self):
        history = (_event(1, "tile_drawn", 3),)
        assert is_gang_draw(history, 3) is False


class TestPurity:
    """同输入恒同输出（确定性；模块不接触网络/文件/时钟/随机源）。"""

    def test_functions_are_deterministic(self):
        win = _split(whites=1, tenpai=True)
        for _ in range(3):
            assert static_baotou(win) is True
            assert you_cai_bi_kao_block(True, win, False, False) is not None
        history = (_event(1, "gang", 0, ("9b",)), _event(2, "tile_drawn", 0))
        for _ in range(3):
            assert is_gang_draw(history, 0) is True
