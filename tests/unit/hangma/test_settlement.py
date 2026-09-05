"""settlement 单元测试：番数公式、明细命名、四家结算与 61 例官方金例重放。

金例来源：tests/fixtures/official/v9/fan-calc/*.jsonl（官方 fan-calc 实测，
指南 v9，2026-09-03 抓取；离线只读，不联网）。重放口径：分支与豪华组数
取自官方期望 detail[0]，手留白板数由手牌机械计数，链参数取自请求——
因此本测试只验证番数公式/命名/结算层，不复制通用牌型分解（hand_analysis
的职责）。分解层金例由规则主 Agent 的集成对拍覆盖。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.observation import PublicEvent
from hangma_bot.hangma.interface import Settlement
from hangma_bot.hangma.internal_types import WinSplit
from hangma_bot.hangma.settlement import (
    FanResult,
    compute_fan,
    infer_piao_count,
    settle_scores,
    settle_win,
)

_FAN_CALC_DIR = (
    Path(__file__).resolve().parents[2] / "fixtures" / "official" / "v9" / "fan-calc"
)
_GOLDEN_FILES = (
    "cases.jsonl",
    "cases-baotou.jsonl",
    "cases-baotou2.jsonl",
    "cases-chain4.jsonl",
    "cases-random-crossval.jsonl",
)


def _iter_golden_records():
    """逐行读取三份金例；统一为 (tag, request, response) 三元组。"""

    for name in _GOLDEN_FILES:
        for line in (_FAN_CALC_DIR / name).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record.get("http_status") is not None:
                # 400 输入校验反例无常规响应体，单独覆盖。
                continue
            if "request" in record:
                request, response = record["request"], record["response"]
            else:
                request = {
                    "hand": record["hand"],
                    "draw": record["draw"],
                    "chain": record.get("chain", {"count": 0, "piao": 0}),
                    "base": record.get("base", 1),
                }
                response = record["resp"]
            yield record.get("tag", name), request, response


def _golden_params():
    return [
        (tag, request, response)
        for tag, request, response in _iter_golden_records()
        if response.get("hu")
    ]


def _split_from_golden(request: dict, response: dict) -> WinSplit:
    """从官方期望 detail[0] 与手牌机械信息构造分解元数据（不复刻分解算法）。"""

    head = response["detail"][0]
    if head == "平胡":
        branch, luxury = "平胡", 0
    elif head == "七对":
        branch, luxury = "七对", 0
    else:
        branch, luxury = "七对", int(head.rsplit("×", 1)[1])
    whites = list(request["hand"]) + [request["draw"]]
    return WinSplit(
        branch=branch,
        luxury_pairs=luxury,
        whites_held=whites.count("白"),
        any_tile_tenpai=response["baotou"],
        evidence=(),
    )


_GOLDEN_PARAMS = _golden_params()


@pytest.mark.parametrize("tag,req,response", _GOLDEN_PARAMS, ids=[p[0] for p in _GOLDEN_PARAMS])
def test_golden_fan_details_and_scores(tag, req, response):
    """官方金例重放：总番、明细命名与庄/闲两种结算场景逐字一致。"""

    chain = req.get("chain") or {"count": 0, "piao": 0}
    base = req.get("base", 1)
    win = _split_from_golden(req, response)

    result = compute_fan(win, chain["count"], chain["piao"], response["baotou"])
    assert isinstance(result, FanResult)
    assert result.fan == response["fan"]
    assert list(result.details) == response["detail"]

    # 金例同时给出庄家胡与闲家胡两种支付；按座位 0-3 校核每个角色金额。
    fan, unit = response["fan"], response["fan"] * base
    dealer_case = response["scores"]["dealer_hu"]
    delta = settle_scores(fan, base, winner_seat=2, dealer_seat=2)
    assert delta[2] == dealer_case["win"]
    assert all(delta[seat] == -dealer_case["lose"][0] for seat in (0, 1, 3))
    assert sum(delta) == 0

    nondealer_case = response["scores"]["nondealer_hu"]
    delta = settle_scores(fan, base, winner_seat=1, dealer_seat=0)
    assert delta[1] == nondealer_case["win"]
    assert delta[0] == -nondealer_case["lose"][0]
    assert delta[2] == -nondealer_case["lose"][1]
    assert delta[3] == -nondealer_case["lose"][2]
    assert sum(delta) == 0


def test_golden_hu_false_case_has_no_settlement():
    """hu=false 反例（not-hu）不经结算路径；engine 以流局番 0 处理。"""

    records = {tag: response for tag, _, response in _iter_golden_records()}
    assert "not-hu" in records and records["not-hu"]["hu"] is False


def test_golden_rejects_white_total_over_four():
    """400 输入校验反例（four-white-plus-lux）：手留 4 白 + 链内飘 3 本地同口径拒绝。"""

    win = WinSplit(
        branch="七对", luxury_pairs=3, whites_held=4, any_tile_tenpai=False, evidence=()
    )
    with pytest.raises(ValueError, match="白板总数"):
        compute_fan(win, 3, 3, False)


def test_golden_replay_covers_all_cases():
    """防夹具漂移：61 例胡牌全部进入重放（定向 38 + 随机对拍 23）。"""

    replayed = {tag for tag, _, _ in _golden_params()}
    assert len(replayed) == 61  # 与 RULES_EVIDENCE.md 头部声明对齐
    assert "chain-4-4" in replayed  # 连飘×4 命名金例（2026-09-03 实测补录）
    assert sum(1 for t in replayed if t.startswith("random-cv-")) == 23
    assert "chiitoi-held4" in replayed
    assert "held3-piao1-no-white-pair" in replayed


class TestChainDetailNaming:
    """链型明细命名表（§3；金例已覆盖大部分组合，这里补齐边界）。"""

    def _fan(self, count, piao, whites=0, baotou=False):
        win = WinSplit(
            branch="平胡", luxury_pairs=0, whites_held=whites,
            any_tile_tenpai=False, evidence=(),
        )
        return compute_fan(win, count, piao, baotou)

    def test_no_chain_has_no_chain_detail(self):
        assert list(self._fan(0, 0).details) == ["平胡"]

    def test_single_gang_is_gangkai(self):
        assert list(self._fan(1, 0).details) == ["平胡", "杠开"]

    def test_double_piao_with_more_gangs_is_chain_n(self):
        result = self._fan(5, 2)
        assert list(result.details) == ["平胡", "杠飘链×5"]
        assert result.fan == 32  # 1 × 2^5

    def test_piao_equals_count_four_is_lianpiao(self):
        # 官方金例 chain-4-4（2026-09-03 实测）：count=piao=4 → 连飘×4；
        # 手留 0 + 飘出 4 = 白板总数 4，同时 ×2 并记 4个白板。
        result = self._fan(4, 4)
        assert list(result.details) == ["平胡", "连飘×4", "4个白板"]
        assert result.fan == 32  # 1 × 2^4 × 2

    def test_piao_above_count_is_rejected(self):
        with pytest.raises(ValueError, match="不能超过"):
            self._fan(1, 2)


class TestComputeFanValidation:
    """输入校验：非法组合立即失败，不产出臆造番数。"""

    def test_unknown_branch_rejected(self):
        win = WinSplit("清一色", 0, 0, False, ())
        with pytest.raises(ValueError, match="分支"):
            compute_fan(win, 0, 0, False)

    def test_plain_branch_with_luxury_rejected(self):
        win = WinSplit("平胡", 2, 0, False, ())
        with pytest.raises(ValueError, match="平胡分支"):
            compute_fan(win, 0, 0, False)

    def test_luxury_out_of_range_rejected(self):
        win = WinSplit("七对", 4, 0, False, ())
        with pytest.raises(ValueError, match="0-3"):
            compute_fan(win, 0, 0, False)

    def test_whites_out_of_range_rejected(self):
        win = WinSplit("平胡", 0, 5, False, ())
        with pytest.raises(ValueError, match="0-4"):
            compute_fan(win, 0, 0, False)

    def test_negative_chain_rejected(self):
        win = WinSplit("平胡", 0, 0, False, ())
        with pytest.raises(ValueError, match="非负整数"):
            compute_fan(win, -1, 0, False)


class TestBaotouGuard:
    """爆头守卫：手留白板数 = 4 时平台爆头标志被压平（§5）。"""

    def test_four_whites_held_suppresses_baotou(self):
        win = WinSplit("平胡", 0, 4, False, ())
        result = compute_fan(win, 0, 0, True)
        assert "爆头" not in result.details
        assert result.fan == 2  # 仅 4个白板 ×2

    def test_three_held_one_piao_keeps_baotou(self):
        # 手留 3 + 飘出 1 = 4 白板，但爆头只看手留数（金例 three-white-kept-one-piao）。
        win = WinSplit("平胡", 0, 3, True, ())
        result = compute_fan(win, 1, 1, True)
        assert list(result.details) == ["平胡", "财飘", "4个白板", "爆头"]
        assert result.fan == 8


class TestGlobalMaxFan:
    """全局最大番型 ×512：三豪华七对 + 三财飘 + 4 白板 + 爆头。

    指南 v3 修订（2026-09-02）：七对允许财飘，与飘/杠链叠加；2026-09-05 经
    官方 fan-calc 实测确认（hand=3 组四张+1 白，draw=东，chain 3/3，baotou）：
    fan=512、detail=["豪华七对×3", "三财飘", "4个白板", "爆头"]。
    """

    def test_max_fan_512(self):
        win = WinSplit("七对", 3, 1, True, ())
        result = compute_fan(win, 3, 3, True)
        assert list(result.details) == ["豪华七对×3", "三财飘", "4个白板", "爆头"]
        assert result.fan == 512
        assert settle_scores(512, 1, 0, 0) == (12288, -4096, -4096, -4096)

    def test_max_fan_non_dealer(self):
        win = WinSplit("七对", 3, 1, True, ())
        result = compute_fan(win, 3, 3, True)
        assert result.fan == 512
        # 闲家胡：庄家付 4096，另外两个闲家各付 512，胜者共得 5120（官方 fan-calc 实测）
        assert settle_scores(512, 1, 2, 0) == (-4096, -512, 5120, -512)


class TestSettleScores:
    """四家结算：庄家倍率恒 ×8、闲家 ×1、总分守恒、流局零支付（§4）。"""

    def test_property_conservation_and_roles(self):
        for fan in (0, 1, 2, 8, 64):
            for base in (1, 2, 10):
                for winner in range(4):
                    for dealer in range(4):
                        delta = settle_scores(fan, base, winner, dealer)
                        assert sum(delta) == 0
                        if fan == 0:
                            assert delta == (0, 0, 0, 0)
                            continue
                        unit = base * fan
                        if winner == dealer:
                            assert delta[winner] == 24 * unit
                            for seat in range(4):
                                if seat != winner:
                                    assert delta[seat] == -8 * unit
                        else:
                            assert delta[winner] == 10 * unit
                            assert delta[dealer] == -8 * unit
                            for seat in range(4):
                                if seat not in (winner, dealer):
                                    assert delta[seat] == -unit

    def test_dealer_multiplier_never_escalates(self):
        # 直上三连庄：庄家倍率恒 ×8，不存在 ×2/×4 递增。
        assert settle_scores(1, 1, 0, 0) == (24, -8, -8, -8)
        assert settle_scores(4, 1, 0, 0) == (96, -32, -32, -32)

    def test_draw_round_pays_nothing(self):
        assert settle_scores(0, 100, 2, 2) == (0, 0, 0, 0)

    def test_invalid_inputs_rejected(self):
        with pytest.raises(ValueError):
            settle_scores(-1, 1, 0, 0)
        with pytest.raises(ValueError):
            settle_scores(True, 1, 0, 0)  # bool 不是合法番数
        with pytest.raises(ValueError):
            settle_scores(1, 0, 0, 0)
        with pytest.raises(ValueError):
            settle_scores(1, 1, 4, 0)
        with pytest.raises(ValueError):
            settle_scores(1, 1, 0, -1)

    def test_deterministic(self):
        for _ in range(3):
            assert settle_scores(3, 2, 1, 3) == (-6, 60, -6, -48)


class TestInferPiaoCount:
    """链内飘出白板数 best-effort 推断（§8 假设：弃白次数，上限链计数）。"""

    @staticmethod
    def _event(seq, kind, seat, tiles=()):
        return PublicEvent(
            seq=seq, kind=kind, seat=seat,
            tiles=tuple(Tile(code) for code in tiles),
        )

    def test_counts_own_white_discards(self):
        history = (
            self._event(1, "tile_discarded", 0, ("白",)),
            self._event(2, "tile_discarded", 1, ("白",)),  # 他家弃白不计
            self._event(3, "tile_discarded", 0, ("白",)),
        )
        assert infer_piao_count(history, 0, 2) == 2

    def test_capped_by_chain_count(self):
        # 链开始前的普通弃白会高估 piao；按链计数封顶（best-effort 口径）。
        history = (
            self._event(1, "tile_discarded", 0, ("白",)),
            self._event(2, "tile_discarded", 0, ("白",)),
        )
        assert infer_piao_count(history, 0, 1) == 1

    def test_zero_chain_means_zero_piao(self):
        history = (self._event(1, "tile_discarded", 0, ("白",)),)
        assert infer_piao_count(history, 0, 0) == 0

    def test_normal_discards_ignored(self):
        history = (
            self._event(1, "tile_discarded", 0, ("5w",)),
            self._event(2, "gang", 0, ("9b",)),
            self._event(3, "tile_drawn", 0),
        )
        assert infer_piao_count(history, 0, 2) == 0

    def test_empty_history(self):
        assert infer_piao_count((), 2, 3) == 0


class TestSettleWin:
    """便捷入口组装 Settlement：只组装、不改变两个核心函数的语义。"""

    def test_wires_fan_details_and_delta(self):
        win = WinSplit("七对", 0, 1, True, ())
        result = settle_win(win, 0, 0, True, base_score=2, winner_seat=3, dealer_seat=1)
        assert isinstance(result, Settlement)
        assert result.fan == 4
        assert result.details == ("七对", "爆头")
        unit = 4 * 2
        assert result.score_delta == (-unit, -8 * unit, -unit, 10 * unit)
        assert sum(result.score_delta) == 0

    def test_matches_core_functions(self):
        win = WinSplit("平胡", 0, 0, False, ())
        settled = settle_win(win, 2, 0, False, 1, 0, 2)
        fan = compute_fan(win, 2, 0, False)
        assert settled.fan == fan.fan
        assert settled.details == fan.details
        assert settled.score_delta == settle_scores(fan.fan, 1, 0, 2)

    def test_deterministic(self):
        win = WinSplit("平胡", 0, 2, True, ())
        first = settle_win(win, 1, 1, True, 1, 0, 0)
        second = settle_win(win, 1, 1, True, 1, 0, 0)
        assert first == second
