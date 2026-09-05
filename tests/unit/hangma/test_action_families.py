"""action_families 单元测试：六动作族候选生成。

只通过模块公开导出（族函数 / generate_candidates / FamilyOutcome）验证
行为，不触碰私有状态、不联网。正反例依据 RULES_EVIDENCE.md §1/§2/§6/§7/§9；
手牌数学以 HandSummary 注入模拟，检验"复用而不复制"的接缝契约。
测试手牌为聚焦场景裁剪的张数（WindowContext 不校验牌数）。
"""

from __future__ import annotations

import pytest

from hangma_bot.hangma import action_families
from hangma_bot.hangma.action_families import (
    FAMILY_ORDER,
    FamilyOutcome,
    chi_candidates,
    discard_candidates,
    gang_candidates,
    generate_candidates,
    hu_candidates,
    pass_candidates,
    peng_candidates,
)
from hangma_bot.hangma.internal_types import HandSummary, WindowContext
from hangma_bot.kernel.actions import Chi, Discard, Gang, Hu, Pass, Peng, Tile
from hangma_bot.kernel.observation import PublicDiscard


def _tiles(*codes: str):
    return tuple(Tile(code) for code in codes)


def _summary(is_win: bool = False, evidence=("手牌数学:测试分解",)) -> HandSummary:
    """构造测试用手牌分析结果；向听字段与本模块判定无关。"""

    return HandSummary(
        is_win=is_win,
        standard_shanten=0,
        chiitoi_shanten=None,
        shanten=0,
        useful_tiles=(),
        whites_held=0,
        evidence=tuple(evidence),
    )


def _context(
    seat: int = 1,
    phase: str = "draw",
    turn_seat: int = 1,
    responding=(),
    hand=(),
    drawn=None,
    chi_count: int = 0,
    peng_codes=(),
    last_discard=None,
    catch_play: bool = False,
    wall=60,
) -> WindowContext:
    return WindowContext(
        seat=seat,
        phase=phase,
        turn_seat=turn_seat,
        responding_seats=tuple(responding),
        hand_tiles=tuple(hand),
        drawn_tile=drawn,
        my_chi_count=chi_count,
        my_peng_codes=tuple(peng_codes),
        last_discard=last_discard,
        catch_play=catch_play,
        remaining_tile_count=wall,
    )


def _discard_from(seat: int, code: str, seq: int = 10) -> PublicDiscard:
    return PublicDiscard(seat=seat, tile=Tile(code), seq=seq)


def _keys(outcome: FamilyOutcome):
    return [candidate.action_key for candidate in outcome.candidates]


# 固定场景集：覆盖三种动作窗口与关键特殊状态，供聚合与性质测试复用。
_WIN_DRAW = _context(
    hand=_tiles(
        "7b", "7b", "7b", "7b", "1w", "1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w"
    ),
    drawn=Tile("9w"),
)
_PENG_WINDOW = _context(
    phase="response_peng",
    turn_seat=0,
    responding=(1,),
    hand=_tiles(
        "6w", "6w", "6w", "1w", "2w", "3w", "4w", "5w", "7w", "8w", "9w", "1b", "2b"
    ),
    last_discard=_discard_from(0, "6w"),
)
_CHI_WINDOW = _context(
    phase="response_chi",
    turn_seat=0,
    responding=(1,),
    hand=_tiles("2w", "3w", "5w", "6w", "1w", "7w", "8w", "9w", "1b", "2b", "3b", "4b", "5b"),
    last_discard=_discard_from(0, "4w"),
)
_CATCH_PLAY_DRAW = _context(
    hand=_tiles("1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "1b", "2b", "3b"),
    drawn=Tile("白"),
    catch_play=True,
)
_SETTLED = _context(phase="settled", turn_seat=2)

SCENARIOS = [
    ("win-draw", _WIN_DRAW, _summary(is_win=True)),
    ("response-peng-gang", _PENG_WINDOW, None),
    ("response-chi", _CHI_WINDOW, None),
    ("catch-play-draw", _CATCH_PLAY_DRAW, _summary()),
    ("settled", _SETTLED, None),
]


class TestDiscardFamily:
    """出牌族：摸牌窗口全暗牌可打；抓打圈仅打刚摸牌（§6）。"""

    def test_all_distinct_codes_in_tile_order(self):
        context = _context(
            hand=_tiles("1w", "1w", "3b", "白"), drawn=Tile("9w")
        )
        outcome = discard_candidates(context)
        assert _keys(outcome) == ["discard:1w", "discard:9w", "discard:3b", "discard:白"]
        assert outcome.issues == ()

    def test_wealth_discard_carries_audit_evidence(self):
        context = _context(hand=_tiles("白", "1w"), drawn=None)
        wealth = discard_candidates(context).candidates[-1]
        assert wealth.action_key == "discard:白"
        assert any("财神" in line for line in wealth.evidence)

    def test_catch_play_restricts_to_drawn_tile(self):
        context = _context(
            hand=_tiles("1w", "2w", "3w"), drawn=Tile("5t"), catch_play=True
        )
        outcome = discard_candidates(context)
        assert _keys(outcome) == ["discard:5t"]
        assert any("抓打圈" in line for line in outcome.candidates[0].evidence)

    def test_catch_play_without_drawn_tile_degrades(self):
        outcome = discard_candidates(_context(hand=_tiles("1w"), catch_play=True))
        assert outcome.candidates == ()
        assert len(outcome.issues) == 1
        assert outcome.issues[0].area == "action_families.discard"

    @pytest.mark.parametrize(
        "phase,turn_seat,responding",
        [
            ("response_chi", 0, (1,)),
            ("draw", 0, ()),
            ("settled", 2, ()),
        ],
    )
    def test_no_candidates_outside_own_draw_window(self, phase, turn_seat, responding):
        assert discard_candidates(
            _context(
                phase=phase,
                turn_seat=turn_seat,
                responding=responding,
                hand=_tiles("1w"),
            )
        ) == FamilyOutcome((), ())

    def test_empty_hand_observation_yields_nothing(self):
        assert discard_candidates(_context()) == FamilyOutcome((), ())


class TestChiFamily:
    """吃族：两摊上限、财神不可吃、不吃字牌、仅吃窗口（§1/§6）。"""

    def test_all_runs_generated_in_order(self):
        # 手含 2w3w、3w5w 相邻与 5w6w：被吃 4w 的三个顺位全部成立。
        context = _CHI_WINDOW
        outcome = chi_candidates(context)
        assert _keys(outcome) == [
            "chi:2w,3w,4w",
            "chi:3w,4w,5w",
            "chi:4w,5w,6w",
        ]
        first = outcome.candidates[0].action
        assert isinstance(first, Chi)
        assert tuple(tile.code for tile in first.tiles) == ("2w", "3w", "4w")

    @pytest.mark.parametrize(
        "discarded,hand,expected",
        [
            ("1w", ("2w", "3w"), ["chi:1w,2w,3w"]),
            ("9w", ("7w", "8w"), ["chi:7w,8w,9w"]),
            ("2w", ("1w", "3w", "3w", "4w"), ["chi:1w,2w,3w", "chi:2w,3w,4w"]),
        ],
    )
    def test_boundary_runs(self, discarded, hand, expected):
        context = _context(
            phase="response_chi",
            turn_seat=0,
            responding=(1,),
            hand=_tiles(*hand),
            last_discard=_discard_from(0, discarded),
        )
        assert _keys(chi_candidates(context)) == expected

    def test_blocked_at_two_melds(self):
        context = _context(
            phase="response_chi",
            responding=(1,),
            hand=_tiles("2w", "3w"),
            last_discard=_discard_from(0, "1w"),
            chi_count=2,
        )
        assert chi_candidates(context) == FamilyOutcome((), ())

    def test_wealth_discard_not_claimable(self):
        context = _context(
            phase="response_chi",
            responding=(1,),
            hand=_tiles("2w", "3w"),
            last_discard=_discard_from(0, "白"),
        )
        assert chi_candidates(context) == FamilyOutcome((), ())

    def test_honor_discard_has_no_run(self):
        context = _context(
            phase="response_chi",
            responding=(1,),
            hand=_tiles("2w", "3w"),
            last_discard=_discard_from(0, "中"),
        )
        assert chi_candidates(context) == FamilyOutcome((), ())

    def test_wealth_never_substitutes_partner(self):
        # 手有 2w 与白：白不能替 4w 组顺，吃候选为空（§6 吃牌不得含白）。
        context = _context(
            phase="response_chi",
            responding=(1,),
            hand=_tiles("2w", "白"),
            last_discard=_discard_from(0, "3w"),
        )
        assert chi_candidates(context) == FamilyOutcome((), ())

    def test_not_generated_in_peng_window(self):
        context = _context(
            phase="response_peng",
            responding=(1,),
            hand=_tiles("2w", "3w"),
            last_discard=_discard_from(0, "1w"),
        )
        assert chi_candidates(context) == FamilyOutcome((), ())

    def test_not_responding_seat(self):
        context = _context(
            phase="response_chi",
            responding=(),
            hand=_tiles("2w", "3w"),
            last_discard=_discard_from(0, "1w"),
        )
        assert chi_candidates(context) == FamilyOutcome((), ())

    def test_blocked_in_catch_play(self):
        context = _context(
            phase="response_chi",
            responding=(1,),
            hand=_tiles("2w", "3w"),
            last_discard=_discard_from(0, "1w"),
            catch_play=True,
        )
        assert chi_candidates(context) == FamilyOutcome((), ())

    def test_missing_discard_degrades_with_issue(self):
        outcome = chi_candidates(_context(phase="response_chi", responding=(1,)))
        assert outcome.candidates == ()
        assert outcome.issues[0].area == "action_families.chi"

    def test_own_discard_contradiction_reported(self):
        context = _context(
            phase="response_chi",
            responding=(1,),
            hand=_tiles("2w", "3w"),
            last_discard=_discard_from(1, "1w"),
        )
        outcome = chi_candidates(context)
        assert outcome.candidates == ()
        assert outcome.issues[0].area == "action_families.chi"

    def test_duplicate_shapes_collapse(self):
        context = _context(
            phase="response_chi",
            responding=(1,),
            hand=_tiles("2w", "2w", "3w", "3w"),
            last_discard=_discard_from(0, "4w"),
        )
        assert _keys(chi_candidates(context)) == ["chi:2w,3w,4w"]


class TestPengFamily:
    """碰族：精确两同牌、财神不可碰、仅碰窗口（§1/§6）。"""

    def test_two_copies_yield_single_candidate(self):
        context = _context(
            phase="response_peng",
            responding=(1,),
            hand=_tiles("5t", "5t"),
            last_discard=_discard_from(0, "5t"),
        )
        outcome = peng_candidates(context)
        assert _keys(outcome) == ["peng:5t"]
        assert any("×2" in line for line in outcome.candidates[0].evidence)

    @pytest.mark.parametrize("held", [0, 1])
    def test_insufficient_copies(self, held):
        context = _context(
            phase="response_peng",
            responding=(1,),
            hand=_tiles("5t", "白")[: held + 1] if held else _tiles("1w"),
            last_discard=_discard_from(0, "5t"),
        )
        assert peng_candidates(context) == FamilyOutcome((), ())

    def test_wealth_discard_not_claimable(self):
        context = _context(
            phase="response_peng",
            responding=(1,),
            hand=_tiles("白", "白"),
            last_discard=_discard_from(0, "白"),
        )
        assert peng_candidates(context) == FamilyOutcome((), ())

    def test_not_generated_in_chi_window(self):
        # 碰窗口先于吃窗口：吃阶段碰时机已过（§6）。
        context = _context(
            phase="response_chi",
            responding=(1,),
            hand=_tiles("5t", "5t"),
            last_discard=_discard_from(0, "5t"),
        )
        assert peng_candidates(context) == FamilyOutcome((), ())

    def test_blocked_in_catch_play(self):
        context = _context(
            phase="response_peng",
            responding=(1,),
            hand=_tiles("5t", "5t"),
            last_discard=_discard_from(0, "5t"),
            catch_play=True,
        )
        assert peng_candidates(context) == FamilyOutcome((), ())

    def test_not_responding_seat(self):
        context = _context(
            phase="response_peng",
            responding=(),
            hand=_tiles("5t", "5t"),
            last_discard=_discard_from(0, "5t"),
        )
        assert peng_candidates(context) == FamilyOutcome((), ())

    def test_missing_discard_degrades_with_issue(self):
        outcome = peng_candidates(_context(phase="response_peng", responding=(1,)))
        assert outcome.issues[0].area == "action_families.peng"

    def test_own_discard_contradiction_reported(self):
        context = _context(
            phase="response_peng",
            responding=(1,),
            hand=_tiles("5t", "5t"),
            last_discard=_discard_from(1, "5t"),
        )
        assert peng_candidates(context).issues[0].area == "action_families.peng"


class TestGangFamily:
    """杠族：暗杠/明杠/补杠三类、抓打圈与最后 10 墩约束（§1/§6）。"""

    @pytest.mark.parametrize("catch_play", [False, True])
    def test_concealed_gang_four_natural_tiles(self, catch_play):
        # 抓打圈内仅暗杠与自摸胡：暗杠不受限（§6）。
        context = _context(
            hand=_tiles("7b", "7b", "7b", "7b"), catch_play=catch_play
        )
        outcome = gang_candidates(context)
        assert _keys(outcome) == ["gang:concealed:7b"]

    def test_concealed_gang_excludes_wealth(self):
        # 白不参与任何杠（含暗杠，§1）。
        context = _context(hand=_tiles("白", "白", "白", "白"))
        assert gang_candidates(context) == FamilyOutcome((), ())

    def test_concealed_gang_needs_four_copies(self):
        context = _context(hand=_tiles("7b", "7b", "7b"))
        assert gang_candidates(context) == FamilyOutcome((), ())

    def test_added_gang_with_peng_meld(self):
        context = _context(
            hand=_tiles("2t", "1w", "2w"), peng_codes=("2t",)
        )
        assert _keys(gang_candidates(context)) == ["gang:added:2t"]

    def test_added_gang_blocked_in_catch_play(self):
        # 补杠不是暗杠，按"仅暗杠"原文在抓打圈内禁止（§6）。
        context = _context(
            hand=_tiles("2t", "1w", "2w"), peng_codes=("2t",), catch_play=True
        )
        assert gang_candidates(context) == FamilyOutcome((), ())

    def test_added_gang_requires_fourth_tile_in_hand(self):
        context = _context(hand=_tiles("1w", "2w"), peng_codes=("2t",))
        assert gang_candidates(context) == FamilyOutcome((), ())

    def test_added_gang_wealth_code_skipped_defensively(self):
        # 财神不可能被碰；脏数据不得致崩，也不得生成白板补杠。
        context = _context(hand=_tiles("白", "1w"), peng_codes=("白",))
        assert gang_candidates(context) == FamilyOutcome((), ())

    def test_exposed_gang_in_peng_window(self):
        context = _PENG_WINDOW
        outcome = gang_candidates(context)
        assert _keys(outcome) == ["gang:exposed:6w"]
        assert any("明杠" in line for line in outcome.candidates[0].evidence)

    def test_exposed_gang_needs_three_copies(self):
        context = _context(
            phase="response_peng",
            responding=(1,),
            hand=_tiles("6w", "6w", "1w"),
            last_discard=_discard_from(0, "6w"),
        )
        assert gang_candidates(context) == FamilyOutcome((), ())

    def test_exposed_gang_blocked_in_catch_play(self):
        context = _context(
            phase="response_peng",
            responding=(1,),
            hand=_tiles("6w", "6w", "6w"),
            last_discard=_discard_from(0, "6w"),
            catch_play=True,
        )
        assert gang_candidates(context) == FamilyOutcome((), ())

    def test_exposed_gang_wealth_discard_not_claimable(self):
        context = _context(
            phase="response_peng",
            responding=(1,),
            hand=_tiles("白", "白", "白"),
            last_discard=_discard_from(0, "白"),
        )
        assert gang_candidates(context) == FamilyOutcome((), ())

    def test_no_gang_in_chi_window(self):
        context = _context(
            phase="response_chi",
            responding=(1,),
            hand=_tiles("6w", "6w", "6w"),
            last_discard=_discard_from(0, "6w"),
        )
        assert gang_candidates(context) == FamilyOutcome((), ())

    @pytest.mark.parametrize("wall,expected", [(20, []), (21, ["gang:concealed:7b"])])
    def test_wall_reserve_boundary(self, wall, expected):
        # 剩余 ≤ 20（最后 10 墩）禁止杠牌；规则性关闭不产生 Issue（§6）。
        context = _context(hand=_tiles("7b", "7b", "7b", "7b"), wall=wall)
        outcome = gang_candidates(context)
        assert _keys(outcome) == expected
        assert outcome.issues == ()

    def test_unknown_wall_with_shape_degrades_conservatively(self):
        # 牌墙未知 + 确有杠形状 → 宁漏候选不 409，记 Issue（§7 保守方向）。
        context = _context(hand=_tiles("7b", "7b", "7b", "7b"), wall=None)
        outcome = gang_candidates(context)
        assert outcome.candidates == ()
        assert outcome.issues[0].area == "action_families.gang"

    def test_unknown_wall_without_shape_stays_silent(self):
        context = _context(hand=_tiles("1w", "2w"), wall=None)
        assert gang_candidates(context) == FamilyOutcome((), ())


class TestHuFamily:
    """胡族：仅摸牌窗口自摸胡，复用手牌数学结果（§2/§6）。"""

    def test_win_summary_yields_hu_candidate(self):
        context = _context(hand=_tiles("1w", "2w", "3w"), drawn=Tile("4w"))
        outcome = hu_candidates(context, _summary(is_win=True, evidence=("手牌数学:四面子一将",)))
        assert _keys(outcome) == ["hu"]
        assert any("手牌数学:四面子一将" in line for line in outcome.candidates[0].evidence)

    def test_win_allowed_in_catch_play(self):
        # 抓打圈内仍可自摸胡（§6）。
        context = _context(hand=_tiles("1w"), drawn=Tile("白"), catch_play=True)
        assert _keys(hu_candidates(context, _summary(is_win=True))) == ["hu"]

    def test_not_win_yields_nothing(self):
        context = _context(hand=_tiles("1w"), drawn=Tile("2w"))
        assert hu_candidates(context, _summary(is_win=False)) == FamilyOutcome((), ())

    def test_missing_summary_degrades_with_issue(self):
        # 需要携带 drawn_tile 越过「刚摸牌」门禁（v1），才能走到手牌分析缺失的降级分支。
        outcome = hu_candidates(_context(hand=_tiles("1w"), drawn=Tile("2w")))
        assert outcome.candidates == ()
        assert outcome.issues[0].area == "action_families.hu"

    def test_gate_early_return_precedes_hand_degraded_bookkeeping(self):
        """F-18 意图锁定：drawn=None ∧ hand=None 时门禁早退先于降级簿记——
        返回空且不记 hu 族 Issue（该窗口本就无胡候选，降级噪声无意义；
        手牌分析异常由 engine.hand_analysis Issue 覆盖）。"""

        outcome = hu_candidates(
            _context(hand=_tiles("1w"), drawn=None), hand=None
        )
        assert outcome == FamilyOutcome((), ())

    def test_never_generated_in_response_window(self):
        # 只能自摸、不允许点炮（§2）：响应窗口无胡候选。
        context = _context(
            phase="response_peng",
            turn_seat=0,
            responding=(1,),
            hand=_tiles("1w"),
        )
        assert hu_candidates(context, _summary(is_win=True)) == FamilyOutcome((), ())


class TestPassFamily:
    """过族：两个响应窗口可过；摸牌窗口必须行动（§6）。"""

    @pytest.mark.parametrize("phase", ["response_peng", "response_chi"])
    def test_pass_in_response_windows(self, phase):
        context = _context(phase=phase, turn_seat=0, responding=(1,))
        assert _keys(pass_candidates(context)) == ["pass"]

    def test_no_pass_in_draw_window(self):
        assert pass_candidates(_context(hand=_tiles("1w"))) == FamilyOutcome((), ())

    def test_no_pass_when_not_responding(self):
        context = _context(phase="response_chi", turn_seat=0, responding=())
        assert pass_candidates(context) == FamilyOutcome((), ())


class TestGenerateCandidates:
    """组合器：固定族顺序、逐族异常隔离、确定性（§9）。"""

    def test_draw_window_full_candidate_order(self):
        # 出牌（TILE_ORDER 序）→ 杠 → 胡；摸牌窗口无过。
        outcome = generate_candidates(_WIN_DRAW, _summary(is_win=True))
        assert _keys(outcome) == [
            "discard:1w",
            "discard:2w",
            "discard:3w",
            "discard:4w",
            "discard:5w",
            "discard:6w",
            "discard:7w",
            "discard:8w",
            "discard:9w",
            "discard:7b",
            "gang:concealed:7b",
            "hu",
        ]
        assert outcome.issues == ()

    def test_response_peng_window_order(self):
        outcome = generate_candidates(_PENG_WINDOW)
        assert _keys(outcome) == ["peng:6w", "gang:exposed:6w", "pass"]

    @pytest.mark.parametrize("phase", ["response_peng", "response_chi"])
    def test_catch_play_response_window_suppresses_claims_silently(self, phase):
        # 抓打圈旗标归一化假设（模块 docstring 验证协议）：圈内响应窗口
        # 的吃/碰/明杠候选被静默屏蔽——不记 Issue（规则性关闭而非降级，
        # 免使 engine 误标 DEGRADED），过仍可用作保底。本测试把该口径
        # 固化为回归锚点：测试房间验证后若需改语义，先改这里。
        context = _context(
            phase=phase,
            turn_seat=0,
            responding=(1,),
            hand=_tiles("6w", "6w", "6w", "2w", "3w"),
            last_discard=_discard_from(0, "6w" if phase == "response_peng" else "1w"),
            catch_play=True,
        )
        outcome = generate_candidates(context)
        assert _keys(outcome) == ["pass"]
        assert outcome.issues == ()

    def test_response_chi_window_order(self):
        outcome = generate_candidates(_CHI_WINDOW)
        assert _keys(outcome) == [
            "chi:2w,3w,4w",
            "chi:3w,4w,5w",
            "chi:4w,5w,6w",
            "pass",
        ]

    def test_family_crash_isolated_into_issue(self, monkeypatch):
        def boom(context, hand=None):
            raise RuntimeError("手牌数学炸了")

        monkeypatch.setattr(action_families, "hu_candidates", boom)
        outcome = generate_candidates(_WIN_DRAW, _summary(is_win=True))
        assert "hu" not in _keys(outcome)
        assert "gang:concealed:7b" in _keys(outcome)  # 其余族照常产出。
        assert outcome.issues[0].area == "action_families.hu"
        assert "RuntimeError" in outcome.issues[0].reason
        assert "手牌数学炸了" in outcome.issues[0].reason

    def test_aggregate_equals_family_concatenation(self):
        context = _WIN_DRAW
        hand = _summary(is_win=True)
        expected_candidates = (
            discard_candidates(context).candidates
            + chi_candidates(context).candidates
            + peng_candidates(context).candidates
            + gang_candidates(context).candidates
            + hu_candidates(context, hand).candidates
            + pass_candidates(context).candidates
        )
        assert generate_candidates(context, hand) == FamilyOutcome(
            expected_candidates, ()
        )

    def test_no_action_window_returns_clean_empty(self):
        assert generate_candidates(_SETTLED) == FamilyOutcome((), ())


class TestReconstructedDiscardFeedsClaims:
    """投影层重建的 (座位,牌码,seq) 触发弃牌到位后，吃/碰/明杠正常生成。

    回归背景：官方实测 last_discard 为纯牌码字符串，旧投影返回 None，
    hangma 各族以「缺少触发弃牌」降级，真实对局只剩过。适配器在响应
    阶段按 turn=弃牌者重建 PublicDiscard 后，各族不得再出现该降级。
    """

    def test_peng_with_reconstructed_discard(self):
        context = _context(
            phase="response_peng",
            turn_seat=3,  # 弃牌者座位（与重建语义一致）
            responding=(1,),
            hand=_tiles("6w", "6w"),
            last_discard=_discard_from(3, "6w", seq=374),
        )
        outcome = generate_candidates(context)
        assert _keys(outcome) == ["peng:6w", "pass"]
        assert outcome.issues == ()

    def test_exposed_gang_with_reconstructed_discard(self):
        context = _context(
            phase="response_peng",
            turn_seat=3,
            responding=(1,),
            hand=_tiles("6w", "6w", "6w"),
            last_discard=_discard_from(3, "6w", seq=374),
        )
        outcome = generate_candidates(context)
        assert _keys(outcome) == ["peng:6w", "gang:exposed:6w", "pass"]
        assert outcome.issues == ()

    def test_chi_with_reconstructed_discard(self):
        context = _context(
            phase="response_chi",
            turn_seat=3,
            responding=(1,),
            hand=_tiles("2w", "3w"),
            last_discard=_discard_from(3, "1w", seq=374),
        )
        outcome = generate_candidates(context)
        assert _keys(outcome) == ["chi:1w,2w,3w", "pass"]
        assert outcome.issues == ()

    @pytest.mark.parametrize(
        "phase,generator",
        [
            ("response_peng", peng_candidates),
            ("response_peng", gang_candidates),
            ("response_chi", chi_candidates),
        ],
    )
    def test_missing_discard_still_degrades_with_issue(self, phase, generator):
        # last_discard=None 时各族仍保守降级并给出可审计 RuleIssue（§7）。
        context = _context(
            phase=phase,
            turn_seat=3,
            responding=(1,),
            hand=_tiles("6w", "6w", "6w", "2w", "3w"),
            last_discard=None,
        )
        outcome = generator(context)
        assert outcome.candidates == ()
        assert len(outcome.issues) == 1
        assert "缺少触发弃牌" in outcome.issues[0].reason
        assert "pass" in _keys(pass_candidates(context))  # 过仍保底


class TestInvariants:
    """跨场景性质：牌守恒、键唯一、证据非空、确定性。"""

    @pytest.mark.parametrize(
        "name,context,hand",
        SCENARIOS,
        ids=[scenario[0] for scenario in SCENARIOS],
    )
    def test_candidate_mechanics_and_determinism(self, name, context, hand):
        outcome = generate_candidates(context, hand)
        keys = _keys(outcome)
        assert len(keys) == len(set(keys))  # 无重复候选。

        available = {tile.code for tile in context.full_hand()}
        if context.last_discard is not None:
            available.add(context.last_discard.tile.code)
        for candidate in outcome.candidates:
            assert candidate.evidence  # 审计证据非空。
            action = candidate.action
            if isinstance(action, (Discard, Peng, Gang)):
                assert action.tile.code in available
            elif isinstance(action, Chi):
                codes = [tile.code for tile in action.tiles]
                assert all(code in available for code in codes)
                assert len({code[1] for code in codes}) == 1  # 同花色。
                numbers = sorted(int(code[0]) for code in codes)
                assert numbers == list(range(numbers[0], numbers[0] + 3))  # 连续顺子。
            elif isinstance(action, (Hu, Pass)):
                continue
        # 纯函数确定性：同输入两次调用结果完全一致（禁随机源）。
        assert generate_candidates(context, hand) == outcome

    def test_family_order_is_six_families(self):
        assert FAMILY_ORDER == ("discard", "chi", "peng", "gang", "hu", "pass")
