"""禁胡门禁（v1「刚摸牌」）与摸牌双计归一化的单元回归。

官方依据：
- 门禁：指南变更日志 v1（2026-09-02）「碰后禁止胡牌」——碰/吃/杠动作后、
  摸牌前提交 hu 返回 409 INVALID_ACTION；API 记录 §2.4 同句。
  杠后补牌（杠上摸）属于已摸牌，drawn_tile 非空、门禁放行。
- 双计：2026-09-04 官方快照实测形态（tests/fixtures/official/captures/
  state-draw-phase-t_714a42392cba.json）my_hand 含刚摸的牌且 drawn_tile
  再单列；引擎在 _build_context/_full_hand 归一化，两种形态判定必须一致。

对拍事实基础（2026-09-04 测试赛 t_dee58824c308 审计）：120 次自摸胡提交、
官方仅接受 23 次；9 次为碰/吃后未摸牌即提交（门禁），其余为摸牌双计放宽
的假阳性（差分复现见 test_hu_differential_replay.py 与金例夹具）。
"""

from __future__ import annotations

from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import (
    PlayerObservation,
    PublicMeld,
    RulePublicState,
)
from hangma_bot.hangma.engine import HangmaRules


WEALTH = Tile("白")


def _rules() -> HangmaRules:
    return HangmaRules(
        RuleConfig(ruleset_version="test", base_score=1, you_cai_bi_kao=False)
    )


def _meld(kind: str, codes) -> PublicMeld:
    return PublicMeld(
        seat=0, kind=kind, tiles=tuple(Tile(c) for c in codes), from_seat=None
    )


def _observation(
    hand_codes,
    drawn: str,
    melds=(),
    phase: str = "draw",
    turn_seat: int = 1,
) -> PlayerObservation:
    return PlayerObservation(
        game_id="g-test",
        seat=1,
        round_no=1,
        snapshot_seq=10,
        phase=phase,
        dealer_seat=0,
        turn_seat=turn_seat,
        responding_seats=(),
        my_hand=tuple(Tile(c) for c in hand_codes),
        drawn_tile=Tile(drawn) if drawn else None,
        discards=((), (), (), ()),
        melds=((), (melds), (), ()),  # 座位 1 = 本观察座位
        hand_counts=(14, 13, 13, 13),
        last_discard=None,
        remaining_tile_count=60,
        scores=(0, 0, 0, 0),
        rule_state=RulePublicState(
            wealth_god=WEALTH, baotou=False, chain_count=0, catch_play=False
        ),
        public_history=(),
    )


def _hu_keys(observation) -> list:
    return [
        c.action_key for c in _rules().analyze(observation).legal_candidates
        if c.action_key == "hu"
    ]


class TestHuFreshDrawGate:
    """v1「刚摸牌」门禁：drawn_tile 为空时任何手牌形状都不产生胡候选。"""

    def test_post_peng_discard_window_blocks_hu(self):
        # 碰后、未摸牌前的出牌窗口：11 张暗牌 + 1 副露恰好构成
        # 3 面子 + 1 将（123w 456w 789w 东东）。修复前引擎按「多余牌
        # 视为可弃」会误判成胡并提交 409；修复后门禁关闭该窗口的胡候选。
        obs = _observation(
            ["1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "东", "东"],
            drawn="",
            melds=(_meld("peng", ("2b", "2b", "2b")),),
        )
        analysis = _rules().analyze(obs)
        assert "hu" not in [c.action_key for c in analysis.legal_candidates]
        # 出牌候选仍在（该窗口必须行动），只是不能胡。
        assert any(c.action_key.startswith("discard:") for c in analysis.legal_candidates)

    def test_post_chi_discard_window_blocks_hu(self):
        obs = _observation(
            ["1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "东", "东"],
            drawn="",
            melds=(_meld("chi", ("2b", "3b", "4b")),),
        )
        analysis = _rules().analyze(obs)
        assert "hu" not in [c.action_key for c in analysis.legal_candidates]

    def test_gang_replacement_draw_allows_hu(self):
        # 杠后补牌（杠上摸）属于「已摸牌」：drawn_tile 非空，门禁放行。
        obs = _observation(
            ["1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "东"],
            drawn="东",
            melds=(_meld("gang", ("2b", "2b", "2b", "2b")),),
        )
        assert _hu_keys(obs) == ["hu"]

    def test_dealer_first_direct_draw_allows_hu(self):
        # 庄家首局「发牌直抽」的第 14 张官方以 drawn_tile 单列
        # （2026-09-04 实测，指南 v10 只说明事件流无 tile_drawn），
        # 门禁不得误伤该窗口的自摸胡。
        obs = _observation(
            ["1w", "1w", "1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "东", "东"],
            drawn="东",
        )
        assert _hu_keys(obs) == ["hu"]

    def test_normal_draw_unchanged(self):
        obs = _observation(
            ["1w", "1w", "1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "东", "东"],
            drawn="东",
        )
        assert _hu_keys(obs) == ["hu"]


class TestNormalizationAnomaly:
    """P2-N1 回归：官方「含摸牌」形态长度命中但 my_hand 缺 drawn 同码实例时，
    必须产出 RuleIssue（DEGRADED 可审计），不得静默回到幻影双计口径。"""

    def test_missing_drawn_instance_marks_issue(self):
        obs = _observation(
            ["1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "东", "南", "西", "北", "中"],
            drawn="发",  # 14 张长度命中官方形态，但手牌中没有「发」
        )
        analysis = _rules().analyze(obs)
        assert analysis.completeness.value == "degraded"
        assert any(
            issue.area == "engine.context" and "形态异常" in issue.reason
            for issue in analysis.issues
        )
        # 其余动作族照常可用（降级不丢行动能力）
        assert any(c.action_key.startswith("discard:") for c in analysis.legal_candidates)
        assert analysis.emergency_candidate is not None

    def test_normal_official_form_has_no_anomaly_issue(self):
        # 官方形态但 drawn 同码实例存在（正常）→ 无异常 Issue、不降级
        obs = _observation(
            ["1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "东", "东", "南", "白", "白"],
            drawn="白",
        )
        analysis = _rules().analyze(obs)
        assert not any(
            issue.area == "engine.context" and "形态异常" in issue.reason
            for issue in analysis.issues
        )

    def test_contract_form_has_no_anomaly_issue(self):
        obs = _observation(
            ["1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "东", "东", "南", "白"],
            drawn="白",  # 契约形态：13 张不含摸牌
        )
        analysis = _rules().analyze(obs)
        assert not any(
            issue.area == "engine.context" and "形态异常" in issue.reason
            for issue in analysis.issues
        )

    def test_no_drawn_has_no_anomaly_issue(self):
        obs = _observation(
            ["1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "东", "东", "南", "白"],
            drawn="",
        )
        analysis = _rules().analyze(obs)
        assert analysis.completeness.value == "complete"



class TestDrawnTileDoubleCountNormalization:
    """官方 my_hand 含摸牌形态与契约形态（不含摸牌）判定必须一致。"""

    def test_dup_only_plain_false_win_blocked(self):
        # 金例 dup-white-run-fp-t_6c121bfda7e8-r4-seq112：真实 11 张暗牌
        # （1 副露）不构成 3 面子+将；双计的幻影白会造成平胡假阳性。
        hand_incl_drawn = ["2t", "2b", "6w", "南", "1t", "5w", "3b", "发", "白", "3t", "白"]
        melds = (_meld("peng", ("2w", "2w", "2w")),)
        # 契约形态：my_hand = 10 张（不含摸牌）+ drawn。
        hand_excl_drawn = ["2t", "2b", "6w", "南", "1t", "5w", "3b", "发", "白", "3t"]
        obs_a = _observation(hand_excl_drawn, drawn="白", melds=melds)
        # 官方实测形态：my_hand = 11 张（含摸牌）+ drawn 再单列。
        obs_b = _observation(hand_incl_drawn, drawn="白", melds=melds)
        assert _hu_keys(obs_a) == []
        assert _hu_keys(obs_b) == []

    def test_dup_only_chiitoi_false_win_blocked(self):
        # 金例 dup-white-chiitoi-fp-t_cee1db65a074-r7-seq240：真实 14 张
        # 为 6 对（非七对）；幻影白补第 7 对造成七对假阳性。
        hand_incl_drawn = ["东", "南", "8b", "9w", "7t", "东", "8b", "7t", "8w", "5b", "5b", "白", "3b", "白"]
        hand_excl_drawn = ["东", "南", "8b", "9w", "7t", "东", "8b", "7t", "8w", "5b", "5b", "白", "3b"]
        assert _hu_keys(_observation(hand_excl_drawn, drawn="白")) == []
        assert _hu_keys(_observation(hand_incl_drawn, drawn="白")) == []

    def test_true_win_still_detected_in_both_shapes(self):
        # 金例 white-run-middle-win-t_714a42392cba-r4-seq344：官方真实
        # 自摸胡（白替 6t 组顺）。双计归一化不得把真胡判漏。
        hand_incl_drawn = ["6w", "9w", "4t", "3t", "7t", "2t", "9w", "5w", "5b", "3b", "5t", "4b", "4w", "白"]
        hand_excl_drawn = ["6w", "9w", "4t", "3t", "7t", "2t", "9w", "5w", "5b", "3b", "5t", "4b", "4w"]
        assert _hu_keys(_observation(hand_excl_drawn, drawn="白")) == ["hu"]
        assert _hu_keys(_observation(hand_incl_drawn, drawn="白")) == ["hu"]

    def test_contract_shape_untouched_when_no_dup(self):
        # 契约形态（my_hand 不含摸牌）且手牌末张恰与摸牌同码时，
        # 归一化不得误删真实手牌（长度判定保证只处理含摸牌形态）。
        hand_excl_drawn = ["1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "东", "东", "南", "东"]
        obs = _observation(hand_excl_drawn, drawn="东")
        # 14 张：123w 456w 789w + 东东东 南——不是胡（南 单张无将）。
        assert _hu_keys(obs) == []
