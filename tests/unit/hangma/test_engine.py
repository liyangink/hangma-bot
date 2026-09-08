"""engine 组装、紧急路径、故障隔离、validate/score 与金例集成对拍测试。

文件归属：规则主 Agent（见模块 AGENTS.md 分工表）。测试只通过
`HangmaRules` 公开接口与 `emergency` 模块验证行为，不触碰私有状态。
金例输入沿用 v9；期望取相同请求的 v23 官方响应（2026-09-08）。
历史响应原样保留，来源与口径见 fixtures/official/v23/fan-calc/README.md。
"""

from __future__ import annotations

import time
from typing import Optional, Tuple

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
    action_key,
)
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import (
    PlayerObservation,
    PublicDiscard,
    PublicEvent,
    PublicMeld,
    RulePublicState,
)
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import RuleCompleteness

# ---------------------------------------------------------------------------
# 测试脚手架
# ---------------------------------------------------------------------------

WEALTH = Tile("白")


def _rule_state(**kw) -> RulePublicState:
    base = dict(
        wealth_god=WEALTH, baotou=False, chain_count=0, catch_play=False
    )
    base.update(kw)
    return RulePublicState(**base)


def make_observation(**kw) -> PlayerObservation:
    """构造合法 PlayerObservation；默认为座位 1 的普通摸牌出牌窗口。"""

    hand_codes = kw.pop("hand_codes", ("1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "1b", "2b", "3b", "东"))
    base = dict(
        game_id="g-test",
        seat=1,
        round_no=1,
        snapshot_seq=10,
        phase="draw",
        dealer_seat=0,
        turn_seat=1,
        responding_seats=(),
        my_hand=tuple(Tile(c) for c in hand_codes),
        drawn_tile=None,
        discards=((), (), (), ()),
        melds=((), (), (), ()),
        hand_counts=(13, 13, 13, 13),
        last_discard=None,
        remaining_tile_count=60,
        scores=(0, 0, 0, 0),
        rule_state=_rule_state(),
        public_history=(),
    )
    base.update(kw)
    return PlayerObservation(**base)


def _engine_stubbed() -> bool:
    """engine 尚未实现（受控签名仍为 NotImplementedError 桩）时跳过组装类测试。

    `raise NotImplementedError` 是全局名查找（落在 co_names），
    实现后该名字不再被引用。
    """

    return "NotImplementedError" in HangmaRules.analyze.__code__.co_names


requires_engine = pytest.mark.skipif(
    _engine_stubbed(), reason="HangmaRules.analyze 尚未实现（等待子模块集成）"
)

GOLDEN_FILES = (
    "cases.jsonl",
    "cases-baotou.jsonl",
    "cases-baotou2.jsonl",
    "cases-chain4.jsonl",
    "cases-random-crossval.jsonl",
)


def _golden_rows():
    """读取官方 fan-calc 金例（jsonl）。

    两种历史格式兼容：cases.jsonl 为 {tag, request, response}；爆头
    探测文件为顶层 {tag, hand, draw, chain, resp}——统一归一为
    {tag, hand, draw, chain, response}。
    """

    import json
    from pathlib import Path
    from .official_fan_tools import current_response

    root = (
        Path(__file__).resolve().parents[2]
        / "fixtures"
        / "official"
        / "v9"
        / "fan-calc"
    )
    rows = []
    for name in GOLDEN_FILES:
        with open(root / name, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if row.get("http_status") == 400:
                    continue  # 非法输入由官方矩阵的拒绝回归覆盖。
                request = row.get("request") or {
                    "hand": row["hand"],
                    "draw": row["draw"],
                    "chain": row.get("chain", {"count": 0, "piao": 0}),
                    "base": row.get("base", 1),
                }
                rows.append(
                    {
                        "tag": row["tag"],
                        "request": request,
                        "response": current_response(request),
                    }
                )
    return rows


# ---------------------------------------------------------------------------
# 紧急路径（独立实现，立即可测）
# ---------------------------------------------------------------------------


class TestEmergencyPath:
    """emergency.Action 独立于任何复杂分析分支（§9）。"""

    def test_normal_draw_discards_rightmost(self):
        from hangma_bot.hangma.emergency import emergency_action

        obs = make_observation()
        candidate = emergency_action(obs)
        assert candidate is not None
        assert candidate.action == Discard(Tile("东"))
        assert candidate.action_key == "discard:东"

    def test_catch_play_discards_drawn_tile(self):
        from hangma_bot.hangma.emergency import emergency_action

        obs = make_observation(
            drawn_tile=Tile("5t"),
            rule_state=_rule_state(catch_play=True),
        )
        candidate = emergency_action(obs)
        assert candidate.action == Discard(Tile("5t"))
        assert candidate.evidence == ("emergency:catch-play-drawn",)

    def test_response_window_passes_when_responding(self):
        from hangma_bot.hangma.emergency import emergency_action

        for phase in ("response_peng", "response_chi"):
            obs = make_observation(
                phase=phase, responding_seats=(1, 2), drawn_tile=None
            )
            candidate = emergency_action(obs)
            assert candidate is not None
            assert candidate.action == Pass()

    def test_response_window_without_right_returns_none(self):
        from hangma_bot.hangma.emergency import emergency_action

        obs = make_observation(
            phase="response_peng", responding_seats=(0, 2), drawn_tile=None
        )
        assert emergency_action(obs) is None

    def test_draw_window_not_my_turn_returns_none(self):
        from hangma_bot.hangma.emergency import emergency_action

        obs = make_observation(turn_seat=2)
        assert emergency_action(obs) is None

    def test_non_action_phase_returns_none(self):
        from hangma_bot.hangma.emergency import emergency_action

        for phase in ("deal", "settled", "finished"):
            assert emergency_action(make_observation(phase=phase)) is None

    def test_empty_hand_with_drawn_discards_drawn(self):
        from hangma_bot.hangma.emergency import emergency_action

        obs = make_observation(
            hand_codes=(), drawn_tile=Tile("9b")
        )
        candidate = emergency_action(obs)
        assert candidate is not None
        assert candidate.action == Discard(Tile("9b"))

    def test_emergency_is_deterministic_and_fast(self):
        """P99 远低于 1 秒预算；不分配大对象（用耗时代理验证）。"""

        from hangma_bot.hangma.emergency import emergency_action

        obs = make_observation()
        durations = []
        for _ in range(2000):
            start = time.perf_counter()
            emergency_action(obs)
            durations.append(time.perf_counter() - start)
        durations.sort()
        p99 = durations[int(len(durations) * 0.99) - 1]
        assert p99 < 0.01, "紧急路径 P99 应远低于 1 秒（实测 {0}s）".format(p99)


# ---------------------------------------------------------------------------
# engine 组装（等待实现后生效）
# ---------------------------------------------------------------------------


@requires_engine
class TestAnalyzeInvariants:
    """RuleAnalysis 必须满足 interface-contracts §4 的全部不变量。"""

    def _rules(self, youcai: bool = False) -> HangmaRules:
        return HangmaRules(
            RuleConfig(ruleset_version="test-v9", base_score=1, you_cai_bi_kao=youcai)
        )

    def test_draw_window_candidates_unique_and_emergency_member(self):
        pytest.importorskip("hangma_bot.hangma.hand_analysis")
        analysis = self._rules().analyze(make_observation())
        keys = [c.action_key for c in analysis.legal_candidates]
        assert keys, "摸牌出牌窗口必须有出牌候选"
        assert len(keys) == len(set(keys)), "action_key 必须唯一"
        assert analysis.emergency_candidate is not None
        assert analysis.emergency_candidate.action_key in keys
        assert analysis.completeness is RuleCompleteness.COMPLETE
        assert analysis.issues == ()

    def test_response_peng_window_has_no_discard_or_hu(self):
        obs = make_observation(
            phase="response_peng",
            responding_seats=(1,),
            drawn_tile=None,
            hand_codes=("1w", "1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "1b", "1b", "1b"),
            last_discard=PublicDiscard(seat=0, tile=Tile("1w"), seq=9),
        )
        analysis = self._rules().analyze(obs)
        kinds = {c.action_key.split(":")[0] for c in analysis.legal_candidates}
        assert "discard" not in kinds
        assert "hu" not in kinds
        assert "pass" in kinds
        assert analysis.emergency_candidate is not None
        assert analysis.emergency_candidate.action_key == "pass"

    def test_no_action_right_returns_empty(self):
        obs = make_observation(turn_seat=2, phase="draw")
        analysis = self._rules().analyze(obs)
        assert analysis.legal_candidates == ()
        assert analysis.emergency_candidate is None

    def test_catch_play_restricts_discard_to_drawn(self):
        obs = make_observation(
            drawn_tile=Tile("5t"),
            rule_state=_rule_state(catch_play=True),
        )
        analysis = self._rules().analyze(obs)
        discards = [
            c
            for c in analysis.legal_candidates
            if c.action_key.startswith("discard:")
        ]
        assert [c.action_key for c in discards] == ["discard:5t"]

    def test_youcai_blocks_plain_hu_with_wealth(self):
        pytest.importorskip("hangma_bot.hangma.hand_analysis")
        hand = ("白", "1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "东", "东", "2b")
        obs = make_observation(
            hand_codes=hand,
            drawn_tile=Tile("3b"),
        )
        with_hu = self._rules(youcai=False).analyze(obs)
        assert any(c.action_key == "hu" for c in with_hu.legal_candidates)
        blocked = self._rules(youcai=True).analyze(obs)
        assert not any(c.action_key == "hu" for c in blocked.legal_candidates)
        assert blocked.completeness is RuleCompleteness.COMPLETE
        assert blocked.issues == ()
        assert any("拷响" in e for c in blocked.legal_candidates for e in c.evidence)

    def test_analysis_is_deterministic(self):
        rules = self._rules()
        obs = make_observation()
        first = rules.analyze(obs)
        second = rules.analyze(obs)
        assert first == second


@requires_engine
class TestFaultIsolation:
    """任一复杂分支异常不得让 analyze() 崩溃（§9 / 契约 §8）。"""

    def _rules(self) -> HangmaRules:
        return HangmaRules(
            RuleConfig(ruleset_version="test-v9", base_score=1, you_cai_bi_kao=False)
        )

    def test_hand_analysis_failure_keeps_candidates_and_emergency(
        self, monkeypatch
    ):
        pytest.importorskip("hangma_bot.hangma.hand_analysis")
        from hangma_bot.hangma import hand_analysis

        def boom(*args, **kwargs):
            raise RuntimeError("向听搜索崩溃")

        monkeypatch.setattr(hand_analysis, "analyse_hand", boom)
        analysis = self._rules().analyze(make_observation())
        assert analysis.completeness is RuleCompleteness.DEGRADED
        assert any("hand_analysis" in i.area for i in analysis.issues)
        assert analysis.legal_candidates, "出牌候选必须保留"
        assert analysis.emergency_candidate is not None

    def test_family_generation_failure_marks_degraded(self, monkeypatch):
        from hangma_bot.hangma import action_families

        def boom(*args, **kwargs):
            raise RuntimeError("动作族崩溃")

        monkeypatch.setattr(action_families, "generate_candidates", boom)
        analysis = self._rules().analyze(make_observation())
        assert analysis.completeness is RuleCompleteness.DEGRADED
        # 接口不变量：候选为空但紧急动作合法时，紧急候选补入合法候选。
        assert analysis.emergency_candidate is not None, "紧急路径必须独立可用"
        assert analysis.legal_candidates == (analysis.emergency_candidate,)

    def test_emergency_failure_still_returns_candidates(self, monkeypatch):
        from hangma_bot.hangma import engine as engine_module

        monkeypatch.setattr(
            engine_module, "emergency_action", lambda obs: (_ for _ in ()).throw(
                RuntimeError("紧急路径崩溃")
            )
        )
        analysis = self._rules().analyze(make_observation())
        assert analysis.legal_candidates, "候选生成不得依赖紧急路径"
        assert analysis.emergency_candidate is None
        assert analysis.completeness is RuleCompleteness.DEGRADED


@requires_engine
class TestValidate:
    """提交前本地复核；失败原因必须可写入审计。"""

    def _rules(self) -> HangmaRules:
        return HangmaRules(
            RuleConfig(ruleset_version="test-v9", base_score=1, you_cai_bi_kao=False)
        )

    def test_legal_discard_accepted(self):
        rules = self._rules()
        result = rules.validate(make_observation(), Discard(Tile("东")))
        assert result.legal is True
        assert result.reason is None

    def test_discard_not_in_hand_rejected(self):
        result = self._rules().validate(make_observation(), Discard(Tile("南")))
        assert result.legal is False
        assert result.reason

    def test_wealth_peng_rejected(self):
        obs = make_observation(
            phase="response_peng",
            responding_seats=(1,),
            drawn_tile=None,
            last_discard=PublicDiscard(seat=0, tile=Tile("白"), seq=9),
        )
        result = self._rules().validate(obs, Peng(Tile("白")))
        assert result.legal is False

    def test_discard_in_response_window_rejected(self):
        obs = make_observation(
            phase="response_peng", responding_seats=(1,), drawn_tile=None
        )
        result = self._rules().validate(obs, Discard(Tile("1w")))
        assert result.legal is False


@requires_engine
class TestScore:
    """score 按 RuleConfig 结算四家；金例口径（指南 1.4）。"""

    def _rules(self, base: int = 1) -> HangmaRules:
        return HangmaRules(
            RuleConfig(
                ruleset_version="test-v9", base_score=base, you_cai_bi_kao=False
            )
        )

    def _win_obs(self, dealer: int, winner: int, chain: int = 0) -> PlayerObservation:
        from hangma_bot.hangma.interface import WinDescription  # noqa: F401

        hand = ("1w", "1w", "1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "东", "东")
        return make_observation(
            hand_codes=hand,
            drawn_tile=Tile("东"),
            dealer_seat=dealer,
            seat=winner,
            turn_seat=winner,
            rule_state=_rule_state(chain_count=chain),
            chain_piao=0,  # 此结算夹具明确构造纯杠链，非从未知历史补零。
        )

    def test_dealer_win_payments(self):
        pytest.importorskip("hangma_bot.hangma.hand_analysis")
        from hangma_bot.hangma.interface import WinDescription

        obs = self._win_obs(dealer=1, winner=1)
        result = self._rules().score(WinDescription(observation=obs, winner_seat=1))
        assert result.fan == 1
        assert result.score_delta == (-8, 24, -8, -8)  # 三个闲家各付 8（§4）
        assert list(result.details) == ["平胡"]

    def test_nondealer_win_payments(self):
        pytest.importorskip("hangma_bot.hangma.hand_analysis")
        from hangma_bot.hangma.interface import WinDescription

        obs = self._win_obs(dealer=0, winner=1)
        result = self._rules().score(WinDescription(observation=obs, winner_seat=1))
        assert result.score_delta == (-8, 10, -1, -1)

    def test_chain_doubles_fan_and_payments(self):
        pytest.importorskip("hangma_bot.hangma.hand_analysis")
        from hangma_bot.hangma.interface import WinDescription

        obs = self._win_obs(dealer=1, winner=1, chain=1)
        result = self._rules().score(WinDescription(observation=obs, winner_seat=1))
        assert result.fan == 2
        assert list(result.details) == ["平胡", "杠开"]
        assert result.score_delta[1] == 48


@requires_engine
class TestGoldenPipelineParity:
    """集成对拍入口：真实分解（hand_analysis）→ 结算（settlement）全链路
    与官方 fan-calc 金例逐字一致；爆头静态判定与官方 baotou 一致。"""

    def test_full_pipeline_matches_official_fan_calc(self):
        import dataclasses

        pytest.importorskip("hangma_bot.hangma.hand_analysis")
        from hangma_bot.hangma.hand_analysis import any_tile_win, win_split
        from hangma_bot.hangma.settlement import compute_fan
        from hangma_bot.hangma.special_rules import static_baotou

        checked = 0
        for row in _golden_rows():
            response = row.get("response") or row.get("resp")
            if not isinstance(response, dict) or not response.get("hu"):
                continue
            request = row["request"]
            hand13 = tuple(Tile(c) for c in request["hand"])
            draw = Tile(request["draw"])
            split = win_split(hand13 + (draw,), 0)
            assert split is not None, "金例 {0} 应判胡".format(row["tag"])
            # 爆头静态判定：any_tile_win 用摸牌前 13 张（指南 1.2）。
            split = dataclasses.replace(
                split, any_tile_tenpai=any_tile_win(hand13, 0)
            )
            assert static_baotou(split) == bool(
                response["baotou"]
            ), "金例 {0} 爆头判定不一致".format(row["tag"])

            chain = request["chain"]
            fan = compute_fan(
                split,
                chain["count"],
                chain["piao"],
                bool(response["baotou"]),
            )
            assert fan.fan == response["fan"], "金例 {0} 番数不一致".format(row["tag"])
            assert list(fan.details) == list(
                response["detail"]
            ), "金例 {0} 明细不一致：{1} vs {2}".format(
                row["tag"], fan.details, response["detail"]
            )
            checked += 1
        # 38 例定向金例 + 59 例随机偏置对拍（2026-09-03，其中 23 例成胡）。
        assert checked >= 61, "金例对拍覆盖不足：{0}".format(checked)

    def test_not_hu_case_detected(self):
        pytest.importorskip("hangma_bot.hangma.hand_analysis")
        from hangma_bot.hangma.hand_analysis import win_split

        for row in _golden_rows():
            response = row.get("response") or row.get("resp")
            if not isinstance(response, dict) or response.get("hu"):
                continue
            request = row["request"]
            full = tuple(Tile(c) for c in request["hand"]) + (
                Tile(request["draw"]),
            )
            assert win_split(full, 0) is None, "金例 {0} 不应判胡".format(row["tag"])
