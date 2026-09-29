"""G266 结果盲选择、未知保护、非白自然宽度与互斥分账的针对性回归。"""

from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest


ROOT = Path(__file__).resolve().parents[2]
REVIEW = ROOT / "review/freematch-deep-dive-20260925"
if str(REVIEW) not in sys.path:
    sys.path.insert(0, str(REVIEW))

import g266_plain_baotou_entry_branch as subject  # noqa: E402


def tile(code: str, capacity: int | bool = 0) -> NS:
    """构造玩家可见牌码与公开未见张数，不含牌墙真值。"""
    return NS(code=code, remaining_estimate=capacity)


def fact(*, standard: tuple[NS, ...], combined: tuple[NS, ...],
         seven: tuple[NS, ...], std_shanten: int = 2,
         seven_shanten: int = 1, combined_shanten: int = 1) -> NS:
    """构造完整规则动作后牌效，三种向听均按同一动作口径。"""
    return NS(completeness=NS(value="complete"),
              shanten_after=combined_shanten,
              standard_shanten_after=std_shanten,
              seven_pairs_shanten_after=seven_shanten,
              useful_tiles=combined,
              standard_useful_tiles=standard,
              seven_pairs_useful_tiles=seven,
              baotou_after=False)


def ranked(key: str, score: float) -> NS:
    """冻结 R18 结构化分项；让父代分数明确领先。"""
    return NS(action_key=key, total_score=score,
              score_trace={"trace_schema": "sitin-action-score-trace/1",
                           "detail": {"base_score": score,
                                      "wealth_part": 0.0,
                                      "wealth_discard_part": 0.0,
                                      "river_part": 0.0,
                                      "style_part": 0.0,
                                      "risk_units": 0.0}})


def request(*, alternate_standard: tuple[NS, ...] | None = None,
            alternate_value_complete: bool = True,
            existing_baotou: bool = False) -> tuple[NS, NS]:
    """一白、无杠补的模拟器形态：13 张暗手与单列刚摸牌。"""
    parent = fact(standard=(tile("1w", 2),),
                  combined=(tile("1w", 2), tile("3w", 2)),
                  seven=(tile("5w", 2),))
    alternate = fact(standard=alternate_standard or (
        tile("1w", 2), tile("2w", 1)),
        combined=(tile("1w", 2),), seven=(tile("5w", 1),))

    def candidate(key: str, shape: NS, *, complete: bool) -> NS:
        routes = ()
        if existing_baotou:
            routes = (NS(followup_discard=None,
                         conditions=NS(draw_kind="normal"),
                         conditional_settlement=NS(details=("平胡", "爆头"), fan=2),
                         useful_tiles=(tile("9w", 1),)),)
        return NS(action_key=key, facts=shape,
                  value_facts=NS(coverage=NS(value="complete" if complete else "partial"),
                                 routes=routes))

    legal = (candidate("discard:8w", parent, complete=True),
             candidate("discard:9w", alternate,
                       complete=alternate_value_complete))
    observation = NS(seat=0, my_hand=(tile("白"),) + (tile("1w"),) * 12,
                     drawn_tile=tile("2w"), gang_draw=False,
                     melds=((), (), (), ()),
                     rule_state=NS(wealth_god=NS(code="白")))
    req = NS(window_key=NS(phase=NS(value="draw")), observation=observation,
             rejected_attempts=(),
             rules=NS(completeness=NS(value="complete"),
                      legal_candidates=legal))
    plan = NS(degraded_reasons=(subject.SUCCESS_REASON,),
              candidates=(ranked("discard:8w", 10.0),
                          ranked("discard:9w", 9.0)))
    return req, plan


def test_main_costed_layer_uses_nonwhite_width_and_preserves_cost() -> None:
    """七对 1 向听、普通型 2 向听时保留实际容量代价，不删掉主层。"""
    req, plan = request()
    layers, reason = subject.classify_window(req, plan)
    assert reason == "eligible"
    assert set(layers) == {"B_nonready"}
    chosen = layers["B_nonready"]
    assert chosen["nonwhite_standard_width_gain"] == [1, 1]
    assert chosen["combined_capacity_loss"] == 2
    assert chosen["seven_pairs_capacity_loss"] == 1
    assert chosen["parent_action"] == "discard:8w"
    assert chosen["alternate_action"] == "discard:9w"


def test_white_only_expansion_and_bool_capacity_do_not_masquerade_as_natural() -> None:
    """标准有效牌里新增白板不能冒充非白自然进张，布尔容量也不能过门。"""
    req, plan = request(alternate_standard=(tile("1w", 2), tile("白", 2)))
    assert subject.classify_window(req, plan)[0] == {}


def test_white_count_is_identical_for_official_14_and_simulator_13_forms() -> None:
    """官方手牌已含摸牌时不得重复计白；模拟器单列摸牌时结果相同。"""
    simulator, plan = request()
    official, _ = request()
    official.observation.my_hand += (official.observation.drawn_tile,)
    assert simulator.observation.my_hand != official.observation.my_hand
    assert subject.classify_window(simulator, plan)[0]["B_nonready"]["white_before"] == 1
    assert subject.classify_window(official, plan)[0]["B_nonready"]["white_before"] == 1

    simulator, plan = request()
    simulator.observation.drawn_tile = tile("白")
    official, _ = request()
    official.observation.drawn_tile = tile("白")
    official.observation.my_hand += (tile("白"),)
    assert subject.classify_window(simulator, plan)[0]["B_nonready"]["white_before"] == 2
    assert subject.classify_window(official, plan)[0]["B_nonready"]["white_before"] == 2
    req, plan = request(alternate_standard=(tile("1w", 2), tile("2w", True)))
    assert subject.classify_window(req, plan)[0] == {}


def test_incomplete_value_and_existing_opportunity_are_separate_vetoes() -> None:
    """无事实不得推成无机会；已有普通型爆头机会时完整事实也被保护。"""
    req, plan = request(alternate_value_complete=False)
    assert subject.classify_window(req, plan) == ({}, "value_facts_incomplete")
    req, plan = request(existing_baotou=True)
    assert subject.classify_window(req, plan) == (
        {}, "already_plain_baotou_opportunity")


def test_scoring_success_marker_is_allowed_but_actual_degradation_vetoed() -> None:
    """生产策略在 degraded_reasons 写成功标记，不能误杀全部正常摸打。"""
    req, plan = request()
    assert "B_nonready" in subject.classify_window(req, plan)[0]
    plan.degraded_reasons = ("action_value_failed: scorer exception",)
    assert subject.classify_window(req, plan) == ({}, "score_not_frozen_success")


def test_six_class_income_conserves_table_and_piao_is_only_a_tag() -> None:
    """平胡爆头与七对互斥，财飘只附加标签，六类净分合计回到终分。"""
    entries = [
        (0, 1, ["平胡"], 24),
        (0, 2, ["平胡", "财飘", "爆头"], 48),
        (0, 2, ["七对", "爆头"], 96),
        (0, 4, ["其它高番"], 192),
        (1, 1, ["平胡"], -24),
        (None, None, [], 0),
        (None, None, [], 0),
        (None, None, [], 0),
    ]
    score = 0
    hands = []
    for winner, fan, details, focal_delta in entries:
        hands.append({"is_draw": winner is None,
                      "winner_seat": winner, "fan": fan, "details": details,
                      "scores_before": [score, 0, 0, 0],
                      "score_delta": [focal_delta, 0, 0, -focal_delta]})
        score += focal_delta
    result = subject.classify_income(hands, 0, [score, 0, 0, -score])
    assert result["hand_labels"] == [
        "plain_no_baotou", "plain_baotou", "seven_pairs",
        "other_self_special", "other_win", "draw", "draw", "draw"]
    assert result["piao_tags_by_hand"][1] == ["财飘"]
    assert result["by_class"]["plain_baotou"]["focal_net_score"] == 48
    assert sum(item["focal_net_score"] for item in
               result["by_class"].values()) == score


def test_two_seed_root_identity_and_rotating_seat_tie_break(tmp_path) -> None:
    """同号根换种子是新根；同序号四座按 root%4 轮转择代表。"""
    assert subject._root_identity(2026122966, "H", 3) != (
        subject._root_identity(2026122967, "H", 3))
    seed, mix, root, manifest_sha = 2026122966, "H", 3, "a" * 64
    for seat in subject.SEATS:
        hit = {"seat": seat, "layer": "B_nonready", "round_no": 2,
               "trigger_seq": 17}
        path = subject.stage_path(tmp_path, seed, mix, root, seat)
        subject.write_new(path, {"manifest_sha256": manifest_sha,
                                 "table": {"layers": {"B_nonready": hit}}})
    assert subject._representative(seed, mix, root, "B_nonready",
                                   tmp_path, manifest_sha)["seat"] == 3


def test_segment_budget_resumes_from_remaining_total_and_rejects_unclosed(tmp_path) -> None:
    """运行段独立留痕并累计 9000 秒额度；未闭合段不得静默重启。"""
    first = subject.begin_segment(tmp_path, phase="scan", requested_seconds=2,
                                  manifest_sha256="a" * 64)
    with pytest.raises(ValueError, match="未闭合"):
        subject.begin_segment(tmp_path, phase="scan", requested_seconds=2,
                              manifest_sha256="a" * 64)
    subject.finish_segment(tmp_path, first, status="paused")
    second = subject.begin_segment(tmp_path, phase="branch", requested_seconds=2,
                                   manifest_sha256="a" * 64,
                                   selection_sha256="b" * 64)
    assert second.prior_active_seconds > 0
    assert second.deadline_monotonic - second.started_monotonic <= 2
    subject.finish_segment(tmp_path, second, status="complete")

    capped = tmp_path / "capped"
    subject.write_new(capped / "segments" / "fixed.start.json",
                      {"segment_name": "fixed", "manifest_sha256": "a" * 64})
    subject.write_new(capped / "segments" / "fixed.finish.json",
                      {"segment_name": "fixed", "manifest_sha256": "a" * 64,
                       "status": "paused", "active_seconds": 9000})
    with pytest.raises(ValueError, match="累计主动运行已达"):
        subject.begin_segment(capped, phase="scan", requested_seconds=2,
                              manifest_sha256="a" * 64)


def test_unknown_later_opportunity_is_not_counted_as_no_entry() -> None:
    """后续分值事实有 unknown 时本根机会差为空，继续门不能误当负例。"""
    samples = []
    income = {name: {"focal_net_score": 0} for name in subject.HAND_CLASSES}
    for sample in subject.SAMPLES:
        parent = {"income": {"by_class": income},
                  "target_class": "other_win",
                  "timeline": {"first_entered_before_target_end": False,
                               "unknown_after_root": True,
                               "entered_then_other_win": False}}
        alternate = {"income": {"by_class": income},
                     "target_class": "other_win",
                     "timeline": {"first_entered_before_target_end": True,
                                  "unknown_after_root": False,
                                  "entered_then_other_win": True}}
        samples.append({"sample_key": sample,
                        "focal_complete_table_delta": 0,
                        "focal_target_hand_delta": 0,
                        "parent": parent, "alternate": alternate})
    branch = {"identity": {"half": "even"}, "paired_worlds": samples}
    root = subject._per_root(branch)
    assert root["first_enter_delta"] is None
    assert root["first_enter_unknown_arm_worlds"] == 9
    group = subject._group_summary([root], seed=1)
    assert group["first_enter_complete"] is False
    assert group["mean_first_enter_delta"] is None
    gate = subject._main_gate_for_mix(group, exposed_roots=12)
    assert gate["first_enter_complete"] is False
    assert gate["first_enter_positive"] is False
