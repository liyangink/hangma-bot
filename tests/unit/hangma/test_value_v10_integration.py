"""v10 规则接入：去重缺证据局部降级，圈主吃碰续飘的条件值匹配实际短前缀。

只通过 HangmaRules 与 SimulationEngine 的公开入口检验；不运行整桌策略赛。
圈主语义来自官方 v27 指南的 v26 修订，2026-09-09 已入库主线证据。
"""

from dataclasses import replace

import pytest

from hangma_bot.hangma.interface import ValueAnalysisLimits, ValueCoverage, WinDescription
from hangma_bot.kernel.actions import Chi, Discard, Pass, Peng, Tile
from hangma_bot.kernel.observation import PublicMeld
from hangma_bot.simulation import SimulationChoice
from tests.simulation.test_catch_owner_v26 import _game, _discard, _play
from tests.unit.hangma.test_candidate_facts import make_observation, _rules


def _values(rules, observation):
    """全部候选共享足够的固定节点预算；避免把预算截断误判为接线问题。"""
    return {c.action_key: c.value_facts for c in rules.analyze(
        observation, value_limits=ValueAnalysisLimits(max_expansions=16384),
    ).legal_candidates}


def test_unknown_public_overlap_only_disables_routes_that_need_its_tiles():
    """1/2万供牌不明；打4条仅听4条/白，仍能完整证明；立即胡不依赖该计数。"""
    chi = PublicMeld(2, "chi", tuple(Tile(c) for c in ("1w", "2w", "3w")), 1)
    obs = make_observation(drawn_tile=Tile("4t"), melds=((), (), (chi,), ()),
                           discards=((), (Tile("1w"), Tile("2w")), (), ()))
    rules = _rules()
    values = _values(rules, obs)
    assert values["discard:4t"].coverage is ValueCoverage.COMPLETE
    assert {t.code for r in values["discard:4t"].routes for t in r.useful_tiles} == {"4t", "白"}
    assert values["hu"].immediate_settlement == rules.score(WinDescription(obs, 0))
    assert values["discard:1w"].coverage is ValueCoverage.UNAVAILABLE
    assert not values["discard:1w"].routes
    assert values["discard:1w"].issues[0].area == "value_analysis.missing_evidence"
    plain = rules.analyze(obs)
    enriched = rules.analyze(obs, value_limits=ValueAnalysisLimits(max_expansions=16384))

    def _strip_value(candidate):
        # 编解码升级后载荷参与相等性：载荷随 value 分析开启而不同，比较前剥离。
        facts = candidate.facts
        if facts is not None:
            facts = replace(facts, followup_branches=None, family_progress=())
        return replace(candidate, value_facts=None, facts=facts)

    assert tuple(_strip_value(c) for c in enriched.legal_candidates) == plain.legal_candidates


@pytest.mark.parametrize("claim", ["peng", "chi"])
@pytest.mark.parametrize("followup", ["白", "1w"])
def test_owner_claim_followup_value_matches_next_actual_draw(claim, followup):
    """同一合法鸣牌分别续白/断链，在他家全过且摸切的条件下比对下一摸分值。"""
    if claim == "peng":
        rules, engine, world = _game("1w 2w 3w 4w 5w 6w 7w 8w 9w 东 东 白 白", ["东", "5b"])
        actions = ((1, "东"),)
        action, key, phase = Peng(Tile("东")), "peng:东", "response_peng"
    else:
        rules, engine, world = _game("1w 2w 3w 4w 5w 6w 7w 8w 9w 7t 8t 白 白", ["1b", "2b", "9t", "5b"])
        actions = ((1, "1b"), (2, "2b"), (3, "9t"))
        action = Chi(tuple(Tile(c) for c in ("7t", "8t", "9t")))
        key, phase = "chi:7t,8t,9t", "response_chi"
    world = _discard(engine, world, 0, "白")
    for seat, code in actions:
        world = _discard(engine, world, seat, code)
    if claim == "chi":
        world = _play(engine, world, 0, Pass(), "response_peng")
    observation = engine.frame(world).decisions[0].observation
    assert observation.rule_state.catch_play_owner_seat == 0
    facts = _values(rules, observation)[key]
    assert facts.coverage is ValueCoverage.COMPLETE
    routes = tuple(route for route in facts.routes if route.followup_discard == followup)
    assert routes
    expected_chain = (2, 2) if followup == "白" else (0, 0)
    assert {(r.conditions.chain_count, r.conditions.chain_piao) for r in routes} == {expected_chain}
    world = _play(engine, world, 0, action, phase)
    world = _discard(engine, world, 0, followup)
    for _ in range(16):
        frame = engine.frame(world)
        assert frame.blocked_reason is None and frame.decisions
        current = frame.decisions[0].observation
        if current.phase == "draw" and current.seat == 0:
            break
        choices = tuple(SimulationChoice(d.window_key, Discard(d.observation.drawn_tile)
                        if d.observation.phase == "draw" else Pass()) for d in frame.decisions)
        world = engine.advance(world, frame.revision, choices)
    else:
        pytest.fail("短前缀中圈主下一次摸牌未到达")
    assert (current.rule_state.chain_count, current.chain_piao) == expected_chain
    proof = next(r for r in routes if current.drawn_tile.code in {t.code for t in r.useful_tiles})
    assert proof.conditions.baotou == current.rule_state.baotou
    assert _values(rules, current)["hu"].immediate_settlement == proof.conditional_settlement
    assert rules.score(WinDescription(current, 0)) == proof.conditional_settlement


@pytest.mark.parametrize("kind", ["exposed", "added"])
def test_owner_gang_value_matches_immediate_replacement(kind):
    """圈主明杠/补杠继承财飘链与爆头；条件结算等于真实杠补后的当前胡值。"""
    from hangma_bot.kernel.actions import Gang, GangKind

    rules, engine, world = _game("1w 2w 3w 4w 5w 6w 7w 8w 9w 东 东 东 白", ["东", "3b"], replacement="5b")
    world = _discard(engine, world, 0, "白")
    world = _discard(engine, world, 1, "东")
    phase = "response_peng"
    if kind == "added":
        world = _play(engine, world, 0, Peng(Tile("东")), phase)
        phase = "draw"
    observation = engine.frame(world).decisions[0].observation
    facts = _values(rules, observation)["gang:{0}:东".format(kind)]
    assert facts.coverage is ValueCoverage.COMPLETE
    proof = next(r for r in facts.routes if "5b" in {t.code for t in r.useful_tiles})
    assert (proof.conditions.chain_count, proof.conditions.chain_piao) == (2, 1)
    assert proof.conditions.draw_kind == "replacement"
    world = _play(engine, world, 0, Gang(Tile("东"), GangKind(kind)), phase)
    current = engine.frame(world).decisions[0].observation
    assert current.rule_state.catch_play_owner_seat == 0
    assert current.drawn_tile == Tile("5b")
    assert _values(rules, current)["hu"].immediate_settlement == proof.conditional_settlement
    assert rules.score(WinDescription(current, 0)) == proof.conditional_settlement
