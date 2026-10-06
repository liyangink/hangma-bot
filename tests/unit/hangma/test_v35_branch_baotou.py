"""现行官方计算器原始回执：爆头旗与分支支付资格分别验收。

2026-10-06、指南 v35。期望只读封存 HTTP 200，不由本地算法生成。
合成手牌只证明计算型结果；不承诺链控制例在真实牌局中可达。
"""

import hashlib
import json
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.hand_analysis import any_tile_win
from hangma_bot.hangma.hand_analysis import qualify_seven_pairs_baotou, win_split
from hangma_bot.hangma.interface import ValueAnalysisLimits, WinDescription
from hangma_bot.hangma.route_hu_witness import analyze_waiting_hu_witness
from hangma_bot.hangma.route_transition import (analyze_waiting_draw_witness,
    given_next_normal_draw, analyze_given_self_draw, apply_given_draw,
    analyze_given_replacement_draw)
from hangma_bot.hangma.settlement import compute_fan, settle_win
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.actions import CANONICAL_TILE_ORDER, Hu
from hangma_bot.kernel.config import RuleConfig
from tests.unit.hangma.test_route_hu_witness import CONFIG as WITNESS_CONFIG, _waiting
from tests.unit.hangma.test_youcai_integration import make_observation


FIXTURES = Path(__file__).resolve().parents[2] / "fixtures/official/v35/fan-calc-branch-baotou"
ROWS = [json.loads(line) for line in (FIXTURES / "cases.jsonl").read_text().splitlines()]
CONFIG = RuleConfig("v35-branch-baotou", 1, False)


def _observation(row):
    q = row["request"]
    chain = q["chain"]
    return make_observation(q["hand"], q["draw"], baotou=row["response"]["baotou"],
                            chain=chain["count"], piao=chain["piao"],
                            gang=chain["count"] > chain["piao"])


def _assert_payment(settled, row, dealer=0):
    official = row["response"]
    assert settled.fan == official["fan"]
    assert list(settled.details) == official["detail"]
    expected = official["scores"]["dealer_hu" if dealer == 0 else "nondealer_hu"]
    assert settled.score_delta[0] == expected["win"]
    assert sorted(-value for value in settled.score_delta[1:]) == sorted(expected["lose"])
    assert sum(settled.score_delta) == 0


def _physical_layout(request):
    """由136张四份牌构造独立合成布局；不读取任何真实他家手牌。"""
    held = Counter(request["hand"] + [request["draw"]])
    remaining = [code for code in CANONICAL_TILE_ORDER for _ in range(4 - held[code])]
    hands = [request["hand"]] + [remaining[index:index + 13] for index in range(0, 39, 13)]
    return hands, remaining[39:]


def test_raw_current_oracle_integrity():
    manifest = json.loads((FIXTURES / "manifest.json").read_text())
    assert manifest["case_count"] == len(ROWS) == 13
    assert manifest["guide_version"] == 35
    assert hashlib.sha256((FIXTURES / "cases.jsonl").read_bytes()).hexdigest() == manifest["case_sha256"]
    assert all(row["http_status"] == 200 and row["guide_version"] == 35 for row in ROWS)


@pytest.mark.parametrize("row", ROWS, ids=[row["tag"] for row in ROWS])
@pytest.mark.parametrize("includes_draw", (False, True))
def test_public_score_matches_current_oracle_for_both_hand_representations(row, includes_draw):
    """13+draw 与官方含摸牌14张必须按同一个前驱手牌结算。"""
    obs = _observation(row)
    if includes_draw:
        obs = replace(obs, my_hand=obs.my_hand + (obs.drawn_tile,))
    assert any_tile_win(tuple(Tile(code) for code in row["request"]["hand"]), 0) == row["response"]["baotou"]
    for dealer in (0, 1):
        _assert_payment(HangmaRules(CONFIG).score(WinDescription(replace(obs, dealer_seat=dealer), 0)), row, dealer)


ROOT_ROWS = [row for row in ROWS if row["request"]["chain"]["count"] == 0]


@pytest.mark.parametrize("row", ROOT_ROWS, ids=[row["tag"] for row in ROOT_ROWS])
def test_public_hu_value_root_matches_current_oracle(row):
    """支付修复必须进入候选事实；爆头旗仍控制有财必拷的合法性。"""
    rules = HangmaRules(CONFIG)
    obs = _observation(row)
    analysis = rules.analyze(obs, value_limits=ValueAnalysisLimits(max_expansions=8192))
    hu = next(candidate for candidate in analysis.legal_candidates if candidate.action_key == "hu")
    _assert_payment(hu.value_facts.immediate_settlement, row)


@pytest.mark.parametrize("row", ROOT_ROWS, ids=[row["tag"] for row in ROOT_ROWS])
def test_normal_draw_full_and_minimal_witness_match_current_oracle(row):
    """从公开合法弃牌根产生摸前手牌，下一摸支付不得仍沿用旧公式。"""
    state = _waiting(tuple(row["request"]["hand"]), discarded="发")
    args = dict(wall_remaining_before_draw=60, catch_restricted=False, config=WITNESS_CONFIG)
    tile = Tile(row["request"]["draw"])
    full = analyze_waiting_draw_witness(state, tile, **args)
    only = analyze_waiting_hu_witness(state, tile, **args)
    assert only.legal_hu
    assert only.baotou_after_draw is row["response"]["baotou"]
    assert only.immediate_settlement == full.immediate_settlement
    _assert_payment(only.immediate_settlement, row)


@pytest.mark.parametrize("row", ROOT_ROWS, ids=[row["tag"] for row in ROOT_ROWS])
def test_explicit_given_normal_draw_matches_current_oracle(row):
    """直接给定普通摸牌入口也消费同一前驱资格；仅局部见证，不补造中间事件。"""
    waiting = _waiting(tuple(row["request"]["hand"]), discarded="发")
    landed = given_next_normal_draw(waiting, Tile(row["request"]["draw"]),
        wall_remaining_before_draw=60, catch_restricted=False, allow_local_witness=True)
    result = analyze_given_self_draw(landed, seat=0, dealer_seat=0, config=WITNESS_CONFIG)
    assert result.local_witness_only
    _assert_payment(result.immediate_settlement, row)


def test_legal_concealed_gang_replacement_payment_keeps_standard_branch():
    """真实合法暗杠根→给定杠补；有副露不能七对，仅保留普通型原规则对照。"""
    obs = make_observation(["1w", "2w", "3w", "4w", "5w", "6w", "7b", "8b", "9b", "西", "东", "东", "东"], "东")
    rules = HangmaRules(CONFIG)
    analysis = rules.analyze(obs, route_limits=ValueAnalysisLimits(max_expansions=8192))
    root = next(root for root in analysis.conditional_roots if root.action_key == "gang:concealed:东")
    waiting = root.branches[0].state
    landed = apply_given_draw(waiting, Tile("西"), replacement=True)
    result = analyze_given_replacement_draw(landed, seat=0, dealer_seat=0, config=CONFIG)
    assert result.immediate_settlement.fan == 2
    assert result.immediate_settlement.details == ("平胡", "杠开")
    assert result.immediate_settlement.score_delta == (48, -16, -16, -16)


@pytest.mark.parametrize("row", ROWS, ids=[row["tag"] for row in ROWS])
def test_production_progression_payment_matches_oracle(row):
    """推进生产入口结算同请求；合成链控制只核公式，不声明轨迹可达。"""
    from hangma_bot.hangma.progression import deal_state, attach_draw, resolve
    q = row["request"]
    hands, wall = _physical_layout(q)
    hands = tuple(tuple(Tile(code) for code in hand) for hand in hands)
    state = deal_state(1, 0, hands, (0, 0, 0, 0), 0, q["base"], len(wall) - 20, len(wall))
    state = attach_draw(state, Tile(q["draw"])).state
    seat = replace(state.seats[0], baotou=row["response"]["baotou"],
        chain_count=q["chain"]["count"], chain_piao=q["chain"]["piao"])
    state = replace(state, seats=(seat,) + state.seats[1:])
    result = resolve(state, ((0, Hu()),)).state.hand_result
    _assert_payment(result, row)


@pytest.mark.parametrize("row", ROOT_ROWS, ids=[row["tag"] for row in ROOT_ROWS])
def test_exported_single_hand_replay_and_official_payment_match(row):
    """一副物理合法合成牌墙，仅执行即胡规则路径；没有策略评分或桌分评测。"""
    from hangma_bot.offline.replay_check import check_hand
    from hangma_bot.simulation import SimulationEngine
    from tests.simulation._helpers import build_full_world_row, drive
    q = row["request"]
    hands, wall = _physical_layout(q)
    rules = HangmaRules(CONFIG)
    engine = SimulationEngine(rules, rules_hash="v35-oracle-unit")
    source = build_full_world_row(rules, hands13=hands, dealer_drawn=q["draw"], wall=wall)
    world = drive(engine, engine.from_replay(source), lambda request: Hu(), max_steps=2)
    _assert_payment(world.progression.hand_result, row)
    replay = engine.export_hand(world, 1)
    outcome = check_hand(replay, rules)
    assert outcome["status"] == "passed", outcome


def test_same_final_fourteen_never_shares_predecessor_bonus_via_split_cache():
    """SYN01/SYN02胡牌14张完全相同，但官方分别2番/4番；交替重复查缓存。"""
    first, second, third = ROWS[0], ROWS[1], ROWS[8]
    assert sorted(first["request"]["hand"] + [first["request"]["draw"]]) == sorted(second["request"]["hand"] + [second["request"]["draw"]])
    rules = HangmaRules(CONFIG)
    assert sorted(first["request"]["hand"] + [first["request"]["draw"]]) == sorted(third["request"]["hand"] + [third["request"]["draw"]])
    for row in (first, second, third, first, second, third):
        _assert_payment(rules.score(WinDescription(_observation(row), 0)), row)


def _raw_seven_split():
    row = ROWS[1]
    return win_split(tuple(Tile(code) for code in row["request"]["hand"] + [row["request"]["draw"]]), 0)


def test_missing_predecessor_is_explicit_unknown_not_true_or_false():
    split = _raw_seven_split()
    assert split.seven_pairs_baotou is None
    with pytest.raises(ValueError, match="资格未知"):
        compute_fan(split, 0, 0, True)
    with pytest.raises(ValueError, match="资格未知"):
        settle_win(split, 0, 0, True, 1, 0, 0)
    assert compute_fan(split, 0, 0, False).fan == 2


@pytest.mark.parametrize("invalid", (0, 1, "true", (), []))
def test_non_bool_qualification_is_rejected(invalid):
    with pytest.raises(ValueError, match="bool"):
        compute_fan(replace(_raw_seven_split(), seven_pairs_baotou=invalid), 0, 0, True)


@pytest.mark.parametrize("meld_count,length", ((1, 13), (0, 14), (0, 12)))
def test_qualification_cannot_guess_malformed_predecessor(meld_count, length):
    hand = tuple(Tile(code) for code in ROWS[1]["request"]["hand"])
    hand = hand[:length] if length <= 13 else hand + (Tile("1t"),)
    with pytest.raises(ValueError, match="准确摸前13张"):
        qualify_seven_pairs_baotou(_raw_seven_split(), hand, meld_count)


def test_qualification_rejects_physically_impossible_fifth_tile():
    hand = tuple(Tile(code) for code in (["东"] * 5 + ["南"] * 4 + ["白"] * 4))
    with pytest.raises(ValueError, match="第五张"):
        qualify_seven_pairs_baotou(_raw_seven_split(), hand, 0)


def test_no_drawn_tile_keeps_existing_gate_and_unknown_payment():
    obs = _observation(ROWS[1])
    obs = replace(obs, my_hand=obs.my_hand + (obs.drawn_tile,), drawn_tile=None)
    rules = HangmaRules(CONFIG)
    analysis = rules.analyze(obs)
    assert "hu" not in {candidate.action_key for candidate in analysis.legal_candidates}
    assert analysis.emergency_candidate is not None
    with pytest.raises(ValueError, match="准确摸前13张"):
        rules.score(WinDescription(obs, 0))
