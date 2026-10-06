"""一次摸牌分值的独立官方证据与物理约束，指南 v23 / 2026-09-08。

闭手使用完全相同的 13+1 输入。计算器不接受副露，标记为
score_only_reference 的补组请求只证明普通型计分，不能证明原副露动作
或继承爆头的可达性。所有规则断言通过 HangmaRules.analyze 公开入口。
"""

from collections import Counter
from dataclasses import replace
from functools import lru_cache
import hashlib
import json
from pathlib import Path

import pytest

from hangma_bot.application.audit_codec import decision_request_from_json
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits, ValueCoverage
from hangma_bot.kernel.actions import Chi, Discard, Gang, GangKind, Hu, Peng, Tile
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import PublicDiscard
from tests.unit.hangma.official_fan_tools import request_key, current_override
from tests.unit.hangma.test_official_action_chain_trace import trace
from tests.unit.hangma.test_youcai_integration import make_observation, meld


FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
ORACLE = FIXTURES / "official/v23/one-draw-value"
SCENARIO_IDS = tuple("ABCDEFGH") + (
    "four-white-standard", "four-white-pairs", "piao-four-white", "chi",
    "gang-concealed", "gang-exposed", "gang-added", "gang-mixed",
)
BINDINGS = json.loads((ORACLE / "bindings.json").read_text())


@lru_cache(maxsize=None)
def scenario(name):
    """返回原始本人观察，或显式合成的动作族控制；不注入未来牌或他家暗牌。"""
    if name in tuple("ABCDEFGH"):
        doc = json.loads((FIXTURES / "policy/one-draw-value" / (name + ".json")).read_text())
        return decision_request_from_json(doc["request_event"]["payload"]["request"]).observation
    if name == "four-white-standard":
        return make_observation("1w 2w 3w 4w 5w 6w 7b 8b 9b 白 白 白 白".split(), "东", baotou=True)
    if name == "four-white-pairs":
        return make_observation("1w 1w 3w 3w 5b 5b 7b 7b 2t 白 白 白 白".split(), "3t", baotou=True)
    if name == "piao-four-white":
        return make_observation("白 白 白 1w 2w 3w 4w 4w 5w 5w 6w 6w 7w".split(), "白", baotou=True)
    if name == "chi":
        obs = make_observation("1w 2w 4w 5w 6w 7b 8b 9b 南 南 西 西 东".split(), "3w")
        return replace(obs, phase="response_chi", turn_seat=3, responding_seats=(0,),
                       drawn_tile=None, last_discard=PublicDiscard(3, Tile("3w"), 9),
                       discards=((), (), (), (Tile("3w"),)), hand_counts=(13, 13, 13, 13))
    waiting = "1w 2w 3w 4w 5w 6w 7b 8b 9b 西".split()
    if name == "gang-concealed":
        return make_observation(waiting + ["东"] * 3, "东")
    if name == "gang-exposed":
        obs = make_observation(waiting + ["东"] * 3, "东")
        return replace(obs, phase="response_peng", turn_seat=2, responding_seats=(0,),
                       drawn_tile=None, last_discard=PublicDiscard(2, Tile("东"), 9),
                       discards=((), (), (Tile("东"),), ()), hand_counts=(13, 13, 13, 13))
    if name == "gang-added":
        return make_observation(waiting, "东", melds=(meld("peng", ["东"] * 3),))
    if name == "gang-mixed":
        obs = make_observation(waiting[:-1] + ["白"], "东", melds=(meld("peng", ["东"] * 3),),
                               baotou=True, chain=1, piao=1)
        return replace(obs, discards=((Tile("白"),), (), (), ()))
    raise KeyError(name)


@lru_cache(maxsize=None)
def analyzed(name, enabled=False):
    """给证据检验足够的固定工作量，不将策略默认截断当成无路线。"""
    return HangmaRules(RuleConfig("one-draw-official-oracle", 1, enabled)).analyze(
        scenario(name), value_limits=ValueAnalysisLimits(max_expansions=16384),
    )


def candidate_for(name, action_key, enabled=False):
    return next(c for c in analyzed(name, enabled).legal_candidates if c.action_key == action_key)


def route_for(binding, enabled=False):
    facts = candidate_for(binding["scenario"], binding["action_key"], enabled).value_facts
    assert facts.coverage is ValueCoverage.COMPLETE
    return next((r for r in facts.routes
                 if r.followup_discard == binding["followup_discard"]
                 and binding["draw"] in {u.code for u in r.useful_tiles}), None)


@lru_cache(maxsize=1)
def references():
    return {r["reference_id"]: r for r in map(json.loads, (ORACLE / "cases.jsonl").read_text().splitlines())}


def _assert_scores(settled, official, obs):
    """官方的庄/闲总得分与付分列表映射到原观察座位，向量顺序 0—3。"""
    expected = official["scores"]["dealer_hu" if obs.seat == obs.dealer_seat else "nondealer_hu"]
    assert settled.fan == official["fan"]
    assert settled.details == tuple(official["detail"])
    assert settled.score_delta[obs.seat] == expected["win"]
    losses = [-v for s, v in enumerate(settled.score_delta) if s != obs.seat]
    assert sorted(losses) == sorted(expected["lose"])
    assert sum(settled.score_delta) == 0
    if obs.seat != obs.dealer_seat:
        assert -settled.score_delta[obs.dealer_seat] == max(expected["lose"])


def test_oracle_integrity_and_evidence_boundaries():
    manifest = json.loads((ORACLE / "manifest.json").read_text())
    assert manifest["guide_version"] == 23
    assert manifest["unique_requests"] == len(references())
    assert manifest["bindings"] == len(BINDINGS)
    assert manifest["fresh_requests"] <= 100
    for name, digest in manifest["sha256"].items():
        assert hashlib.sha256((ORACLE / name).read_bytes()).hexdigest() == digest
    assert {b["evidence_kind"] for b in BINDINGS} == {"exact_input", "score_only_reference"}
    assert set("BCDEG") <= {b["scenario"] for b in BINDINGS}
    for ref in references().values():
        assert ref["http_status"] == 200 and ref["guide_version"] == 23
        assert json.loads(ref["response_raw"]) == ref["response"]
        assert len(ref["request"]["hand"]) == 13
        assert max(Counter(ref["request"]["hand"] + [ref["request"]["draw"]]).values()) <= 4


@pytest.mark.parametrize("binding", BINDINGS, ids=lambda b: ":".join(str(b[k]) for k in ("scenario", "action_key", "followup_discard", "draw")))
def test_conditional_value_matches_independent_official_response(binding):
    """完全相同输入或明确限制的普通型计分参考，两者绝不混称原副露对拍。"""
    route = route_for(binding)
    assert route is not None
    cond = route.conditions
    ref = references()[binding["reference_id"]]
    q = {"hand": list(cond.pre_draw_hand) + binding["padding"], "draw": binding["draw"],
         "chain": {"count": cond.chain_count, "piao": cond.chain_piao}, "base": 1}
    assert request_key(q) == request_key(ref["request"])
    official = current_override(q, ref["response"])
    assert official["hu"] and official["baotou"] == cond.baotou
    if binding["evidence_kind"] == "exact_input":
        assert cond.meld_count == 0 and binding["padding"] == []
    else:
        assert cond.meld_count > 0 and len(binding["padding"]) == cond.meld_count * 3
        # 补组后至少三个自然单张、百搭不足以配尽落单，独立排除七对。
        counts = Counter(q["hand"] + [q["draw"]])
        assert sum(n % 2 for code, n in counts.items() if code != "白") > counts["白"]
        assert official["detail"][0] == "平胡"
    _assert_scores(route.conditional_settlement, official, scenario(binding["scenario"]))
    enabled = route_for(binding, True)
    allowed = not ("白" in cond.pre_draw_hand or binding["draw"] == "白") or official["baotou"]
    assert (enabled is not None) is allowed
    if allowed:
        assert enabled.conditional_settlement == route.conditional_settlement
        assert enabled.conditions == route.conditions
        assert enabled.followup_discard == route.followup_discard
        # 开关可从同一分组移除“摸到白但不爆头”的另一进张；当前进张数不变。
        assert next(t for t in enabled.useful_tiles if t.code == binding["draw"]) == next(
            t for t in route.useful_tiles if t.code == binding["draw"]
        )


def _full_hand(obs):
    """按公开牌数兼容含摸牌和分离摸牌表示，独立于规则模块的归一化函数。"""
    hand = [t.code for t in obs.my_hand]
    if obs.drawn_tile is not None and len(hand) == 13 - 3 * len(obs.melds[obs.seat]):
        hand.append(obs.drawn_tile.code)
    return hand


@pytest.mark.parametrize("name", SCENARIO_IDS)
@pytest.mark.parametrize("enabled", [False, True])
def test_visible_tile_conservation_followup_legality_and_chain_conditions(name, enabled):
    """动作只是移动已见牌；其余未见张数不随同一动作的后续弃牌选择而改变。"""
    obs = scenario(name)
    full = _full_hand(obs)
    visible = Counter(full)
    visible.update(t.code for river in obs.discards for t in river)
    visible.update(t.code for seat in obs.melds for m in seat for t in m.tiles)
    # 2026-09-18 口径修订：这两个现场快照都来自「保留口径」（守恒等式显示 A 有 1 处、
    # F 有 4 处重叠仍留在牌河），因此碰按守恒等式各扣一次：F 的 4b/东/6b。
    # 吃的供牌是「三张里的一张」，缺 claimed_tile 与紧邻弃牌配对时无法判定是哪一张，
    # 新口径**不再用「上家牌河唯一交集」猜**（该旧规则会伪造供牌），故 A 的 1 处、
    # F 的 1 处吃重叠不再扣；方向落在保守侧（公开可能多算 1，剩余少估 1）。
    overlaps = {"A": (), "F": ("4b", "东", "6b")}.get(name, ())
    for code in overlaps:
        assert any(t.code == code for river in obs.discards for t in river)
        assert any(t.code == code for seat in obs.melds for m in seat for t in m.tiles)
        visible[code] -= 1
    for candidate in analyzed(name, enabled).legal_candidates:
        facts = candidate.value_facts
        assert facts.coverage is ValueCoverage.COMPLETE, (name, candidate.action_key, facts.issues)
        action = candidate.action
        seen = set()
        for route in facts.routes:
            hand = list(full)
            meld_count = len(obs.melds[obs.seat])
            count, piao = obs.rule_state.chain_count, obs.chain_piao or 0
            discarded = None
            if isinstance(action, Discard):
                discarded = action.tile.code
                hand.remove(discarded)
            elif isinstance(action, (Peng, Chi)):
                removed = ([action.tile.code] * 2 if isinstance(action, Peng)
                           else [t.code for t in action.tiles if t != obs.last_discard.tile])
                for code in removed:
                    hand.remove(code)
                meld_count += 1
                discarded = route.followup_discard
                assert discarded in hand
                hand.remove(discarded)
            elif isinstance(action, Gang):
                n = {GangKind.CONCEALED: 4, GangKind.EXPOSED: 3, GangKind.ADDED: 1}[action.kind]
                for _ in range(n):
                    hand.remove(action.tile.code)
                meld_count += action.kind is not GangKind.ADDED
                count += 1
            if discarded is not None:
                count, piao = ((count + 1, piao + 1) if obs.rule_state.baotou and discarded == "白" else (0, 0))
            assert Counter(route.conditions.pre_draw_hand) == Counter(hand)
            assert route.conditions.meld_count == meld_count
            assert len(hand) == 13 - 3 * meld_count
            assert (route.conditions.chain_count, route.conditions.chain_piao) == (count, piao)
            assert route.conditions.draw_kind == ("replacement" if isinstance(action, Gang) else "normal")
            assert route.followup_discard is None or isinstance(action, (Chi, Peng))
            for tile in route.useful_tiles:
                key = (route.followup_discard, tile.code)
                assert key not in seen  # 不把同一后续选择中的一张进张重复累计。
                seen.add(key)
                assert tile.remaining_estimate == max(0, 4 - visible[tile.code])
                assert tile.remaining_estimate > 0
                assert hand.count(tile.code) + 1 <= 4
                if tile.code == "白":
                    assert hand.count("白") + 1 + piao <= 4


@pytest.mark.parametrize("name,key,followup,expected", [
    ("B", "discard:1b", None, {1: 14}),
    ("B", "discard:3b", None, {1: 8, 2: 8, 4: 1}),
    ("C", "discard:6w", None, {1: 8}),
    ("C", "discard:5w", None, {2: 7}),
    ("D", "peng:发", "3t", {1: 22}),
    ("D", "pass", None, {1: 6, 2: 9}),
    ("E", "gang:concealed:东", None, {2: 17, 4: 1}),
    ("E", "discard:中", None, {1: 11, 4: 11, 8: 1}),
    ("G", "peng:南", "8t", {1: 25}),
    ("G", "pass", None, {2: 8, 4: 1}),
])
def test_retrospective_cases_keep_separate_fan_and_unseen_tile_profiles(name, key, followup, expected):
    """可见张数加官方番型得到条件画像；不能解读为真实摸牌概率或必然漏胡。"""
    profile = Counter()
    for route in candidate_for(name, key).value_facts.routes:
        if route.followup_discard == followup:
            profile[route.conditional_settlement.fan] += sum(t.remaining_estimate for t in route.useful_tiles)
    assert profile == expected


@pytest.mark.parametrize("action_key", ["gang:added:东", "discard:东"])
@pytest.mark.parametrize("own_piao_in_river", [False, True])
@pytest.mark.parametrize("enabled", [False, True])
def test_own_piao_evidence_cannot_overlap_other_players_discarded_whites(action_key, own_piao_in_river, enabled):
    """手留一白、本人已飘一白、他家弃两白：四白均已见，断链也不能使旧白重现。

    本人牌河缺失时 chain_piao 能证明那张本人的白，与他家两张白必定不同。
    本人牌河完整时不能再扣一次。这里没有假定任何他家暗牌或未来牌墙。
    """
    own_river = (Tile("白"),) if own_piao_in_river else ()
    obs = replace(scenario("gang-mixed"), discards=(own_river, (Tile("白"), Tile("白")), (), ()))
    rules = HangmaRules(RuleConfig("value-white-evidence", 1, enabled))
    result = rules.analyze(obs, value_limits=ValueAnalysisLimits(max_expansions=8192))
    candidate = next(c for c in result.legal_candidates if c.action_key == action_key)
    assert candidate.value_facts.coverage is ValueCoverage.COMPLETE
    assert candidate.value_facts.routes
    assert not any(t.code == "白" for r in candidate.value_facts.routes for t in r.useful_tiles)


def test_observed_chi_gang_trace_keeps_inherited_baotou_boundary():
    """真实 seq 2267→2269 证明杠补继承；静态计算器不支持此运行态输入。

    原实际补牌为 4w，没有本路线见证；不能把“爆头继承”为真误解释成
    移牌后的任意补牌都完成普通型分解。分值仅在列出的成胡进张条件下成立。
    """
    views, _ = trace()
    before, after = views[2267], views[2269]
    rules = HangmaRules(RuleConfig("value-official-chain", 1, True))
    analysis = rules.analyze(before, value_limits=ValueAnalysisLimits(max_expansions=8192))
    candidate = next(c for c in analysis.legal_candidates if c.action_key == "gang:concealed:2w")
    route, = candidate.value_facts.routes
    assert before.rule_state.baotou and after.rule_state.baotou
    assert route.conditions.baotou and route.conditions.draw_kind == "replacement"
    assert route.conditions.pre_draw_hand == ("6w", "6w", "7t", "西", "西", "白", "白")
    assert (route.conditions.chain_count, route.conditions.chain_piao) == (1, 0)
    assert after.drawn_tile.code == "4w"
    assert "4w" not in {u.code for u in route.useful_tiles}
    assert {u.code for u in route.useful_tiles} == {"6w", "5t", "6t", "7t", "8t", "9t", "西", "白"}
    assert route.conditional_settlement.fan == 4
    assert route.conditional_settlement.details == ("平胡", "杠开", "爆头")
    assert not any(isinstance(c.action, Hu) for c in rules.analyze(after).legal_candidates)
