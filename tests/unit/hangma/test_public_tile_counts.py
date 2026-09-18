"""公开牌计数：逐副露实证去重 + 牌张守恒守卫（2026-09-18 口径修订）。

两代平台行为并存：2026-09-10 之前被鸣弃牌仍在牌河数组里（须去重一次），
2026-09-14 之后已被移除（去重会少算 1 张）。因此本文件同时固化两类回归：

* **保留口径等价**：供牌被证明仍在河中时，与旧实现逐牌种一致（v18/v20 金例）；
* **无证据保守**：历史缺失、冲突、乱序、跨局、超出实例数时**不再降级为 None**，
  改为「不扣重叠」——公开张数可能多算 1、剩余张数少估 1，方向落在保守侧；
* **真矛盾仍为 None**：同码副露超物理上限、实证重叠超过河中实存张数、同快照内证据互相矛盾。
"""

from dataclasses import replace

import pytest

from hangma_bot.hangma.interface import CandidateFactKind, RuleCompleteness
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.observation import PublicEvent, PublicMeld
from tests.unit.hangma.test_candidate_facts import make_observation, _rules
from tests.unit.hangma.test_official_action_chain_trace import trace

from tests.simulation.test_catch_owner_v26 import _after_piao_and_claim


@pytest.mark.parametrize("claim,code,remaining", [("peng", "东", 1), ("chi", "9t", 3)])
def test_called_tile_in_river_and_meld_is_counted_once(claim, code, remaining):
    """136张守恒的公开模拟前缀，鸣牌后的任意听不应少算供牌那一张。"""
    rules, engine, world = _after_piao_and_claim(claim)
    observation = engine.frame(world).decisions[0].observation
    analysis = rules.analyze(observation)
    candidate = next(c for c in analysis.legal_candidates if c.action_key == "discard:白")
    useful = {item.code: item.remaining_estimate for item in candidate.facts.useful_tiles}
    assert useful[code] == remaining


def test_peng_supply_pairing_uses_the_adjacent_discard():
    """第二类强证据（紧邻弃牌 → 碰）必须生效。

    回归要点：查询 pending 与新事件之间不能夹入清空动作，否则碰/明杠的配对恒为空，
    会被误判成「无证据」而放弃一次本该扣掉的重叠（公开多算 1、剩余少估 1）。
    """

    rules, engine, world = _after_piao_and_claim("peng")
    obs = engine.frame(world).decisions[0].observation
    peng = next(e for e in obs.public_history if e.kind == "peng")
    discard = next(e for e in obs.public_history
                   if e.kind == "tile_discarded" and e.seq == peng.seq - 1)
    trimmed = replace(obs, public_history=(discard, peng))
    facts = _facts(rules.analyze(trimmed))
    assert next(u.remaining_estimate for u in facts.useful_tiles if u.code == "东") == 1


def _facts(analysis, key="discard:白"):
    return next(c.facts for c in analysis.legal_candidates if c.action_key == key)


def test_saved_official_chi_and_concealed_gang_keep_nine_bamboo_available():
    """v18 原始连续快照：被吃9条仍在河中，吃/暗杠后均真实未见3张。"""
    views, _ = trace()
    for seq in (2267, 2269):
        facts = _facts(_rules().analyze(views[seq]))
        assert facts.fact_kind is CandidateFactKind.HAND_PROGRESS
        assert next(u.remaining_estimate for u in facts.useful_tiles if u.code == "9t") == 3


@pytest.mark.parametrize("claim,code,remaining", [("peng", "东", 1), ("chi", "9t", 2)])
def test_snapshot_without_history_uses_only_unambiguous_evidence(claim, code, remaining):
    """缺史时：碰可由供牌者座位直接定案；吃无法确定领取的是哪一张，按无证据不扣。"""
    rules, engine, world = _after_piao_and_claim(claim)
    observation = replace(engine.frame(world).decisions[0].observation, public_history=(), history_complete=False)
    facts = _facts(rules.analyze(observation))
    assert next(u.remaining_estimate for u in facts.useful_tiles if u.code == code) == remaining


def test_conflicting_history_is_dropped_instead_of_recovering_a_unique_intersection():
    """合成矛盾历史被丢弃后，不再改用「牌河唯一交集」补供牌，按无证据不扣。"""
    rules, engine, world = _after_piao_and_claim("chi")
    obs = engine.frame(world).decisions[0].observation
    history = tuple(replace(e, claimed_tile=None) if e.kind == "chi"
                    else replace(e, tiles=(Tile("7t"),))
                    if e.kind == "tile_discarded" and e.seat == 3 and e.tiles == (Tile("9t"),)
                    else e for e in obs.public_history)
    facts = _facts(rules.analyze(replace(obs, public_history=history)))
    assert facts.fact_kind is CandidateFactKind.HAND_PROGRESS
    # 上家牌河里只有 9t、供牌被指认为 7t：无重叠可证 ⇒ 9t 公开 2 张、剩余 2。
    assert next(u.remaining_estimate for u in facts.useful_tiles if u.code == "9t") == 2


def test_identical_chi_without_history_does_not_invent_deductions():
    """缺史同形两次吃不猜供牌：不扣重叠，避免从只有一张的牌河里凭空扣出两张。"""
    rules, engine, world = _after_piao_and_claim("peng")
    obs = engine.frame(world).decisions[0].observation
    shape = tuple(Tile(c) for c in ("7t", "8t", "9t"))
    meld = PublicMeld(3, "chi", shape, 2)
    obs = replace(obs, melds=(obs.melds[0], (), (), (meld, meld)),
                  discards=(obs.discards[0], obs.discards[1], (Tile("7t"),), ()), public_history=())
    analysis = rules.analyze(obs)
    facts = _facts(analysis)
    assert facts.fact_kind is CandidateFactKind.HAND_PROGRESS
    counts = {u.code: u.remaining_estimate for u in facts.useful_tiles}
    # 牌河 7t×1 + 两组同形副露各 1 张 ⇒ 公开 3 张；不扣重叠 ⇒ 剩余 1。
    assert counts["7t"] == 1
    assert analysis.emergency_candidate is not None


def _ambiguous_chi():
    rules, engine, world = _after_piao_and_claim("chi")
    obs = engine.frame(world).decisions[0].observation
    rivers = list(obs.discards)
    rivers[3] += (Tile("7t"),)  # 上家还曾丢过7条；缺史时不能区分本次吃7条还是9条。
    return rules, replace(obs, discards=tuple(rivers))


def _with_history(obs, history, watermark=10):
    """为供牌回归隔离圈主与动作链；水位内事件只属于当前单局。"""
    return replace(obs, public_history=history, history_complete=False,
                   snapshot_seq=watermark, consumed_seq=watermark,
                   rule_state=replace(obs.rule_state, catch_play=False, catch_play_owner_seat=None,
                                      chain_count=0), chain_piao=0)


@pytest.mark.parametrize("evidence", ["chi_only", "gap", "continuous", "pass_between", "duplicate"])
def test_explicit_claimed_tile_proves_ambiguous_chi_without_complete_history(evidence):
    """chi 顶层供牌已经公开时，缺史和多张牌河交集不应再丢失牌效。"""
    rules, obs = _ambiguous_chi()
    chi = PublicEvent(7, "chi", 0, tuple(Tile(c) for c in ("7t", "8t", "9t")),
                      claimed_tile=Tile("9t"))
    histories = {
        "chi_only": (chi,),
        "gap": (PublicEvent(5, "tile_discarded", 3, (Tile("7t"),)), chi),
        "continuous": (PublicEvent(6, "tile_discarded", 3, (Tile("9t"),)), chi),
        "pass_between": (PublicEvent(5, "tile_discarded", 3, (Tile("9t"),)),
                         PublicEvent(6, "pass", 1), chi),
        "duplicate": (chi, chi),
    }
    analysis = rules.analyze(_with_history(obs, histories[evidence]))
    facts = _facts(analysis)
    assert facts.fact_kind is CandidateFactKind.HAND_PROGRESS
    counts = {u.code: u.remaining_estimate for u in facts.useful_tiles}
    assert (counts["7t"], counts["9t"]) == (2, 3)


@pytest.mark.parametrize("history_problem", ["discard_conflict", "source_conflict", "duplicate_conflict",
                                           "future", "old_round", "excess_instances", "out_of_order"])
def test_unreliable_history_falls_back_to_no_deduction(history_problem):
    """历史冲突、过期、乱序或与实例数不符时不再采信供牌：给保守数值，不降级、不伪造。

    保守方向：不扣重叠 ⇒ 公开张数可能多算 1 ⇒ 剩余张数少估 1；
    合法动作、立即胡与紧急候选都不读这份计数。
    """
    rules, obs = _ambiguous_chi()
    chi = PublicEvent(7, "chi", 0, tuple(Tile(c) for c in ("7t", "8t", "9t")),
                      claimed_tile=Tile("9t"))
    histories = {
        "discard_conflict": (PublicEvent(6, "tile_discarded", 3, (Tile("7t"),)), chi),
        "source_conflict": (PublicEvent(6, "tile_discarded", 2, (Tile("9t"),)), chi),
        "duplicate_conflict": (chi, replace(chi, claimed_tile=Tile("7t"))),
        "future": (replace(chi, seq=11),),
        "old_round": (chi, PublicEvent(8, "round_ended", None), PublicEvent(9, "round_started", None)),
        "excess_instances": (chi, replace(chi, seq=8, claimed_tile=Tile("7t"))),
        "out_of_order": (chi, PublicEvent(6, "pass", 1)),
    }
    analysis = rules.analyze(_with_history(obs, histories[history_problem]))
    facts = _facts(analysis)
    assert facts.fact_kind is CandidateFactKind.HAND_PROGRESS
    counts = {u.code: u.remaining_estimate for u in facts.useful_tiles}
    # 牌河 7t×1、9t×1 加副露各 1 张 ⇒ 公开 7t=2 / 9t=2；不扣重叠 ⇒ 剩余 2 / 2。
    assert (counts["7t"], counts["9t"]) == (2, 2)
    assert analysis.completeness is RuleCompleteness.COMPLETE
    assert analysis.emergency_candidate is not None


def test_current_river_does_not_override_explicit_claim_with_a_unique_intersection():
    """只给出一张明确领取牌而河中看不到它时不再猜唯一交集：按无证据不扣。"""
    rules, engine, world = _after_piao_and_claim("chi")
    obs = engine.frame(world).decisions[0].observation
    chi = PublicEvent(7, "chi", 0, tuple(Tile(c) for c in ("7t", "8t", "9t")),
                      claimed_tile=Tile("7t"))
    facts = _facts(rules.analyze(_with_history(obs, (chi,))))
    assert facts.fact_kind is CandidateFactKind.HAND_PROGRESS
    # 供牌 7t 不在上家牌河中 ⇒ 无重叠可扣 ⇒ 9t 公开 2 张、剩余 2。
    assert next(u.remaining_estimate for u in facts.useful_tiles if u.code == "9t") == 2


def test_explicit_claim_must_match_current_meld_source():
    rules, obs = _ambiguous_chi()
    melds = list(obs.melds)
    melds[0] = tuple(replace(m, from_seat=1) if m.kind == "chi" else m for m in melds[0])
    rivers = list(obs.discards)
    rivers[1] = (Tile("7t"), Tile("9t"))
    chi = PublicEvent(7, "chi", 0, tuple(Tile(c) for c in ("7t", "8t", "9t")),
                      claimed_tile=Tile("9t"))
    obs = replace(obs, melds=tuple(melds), discards=tuple(rivers))
    analysis = rules.analyze(_with_history(obs, (chi,)))
    assert _facts(analysis).fact_kind is CandidateFactKind.ANALYSIS_FAILED
    assert analysis.emergency_candidate is not None


@pytest.mark.parametrize("passive", [PublicEvent(6, "pass", 1),
                                    PublicEvent(6, "timeout", 1, detail_kind="response")])
def test_legacy_chi_with_continuous_passive_events_keeps_discard_evidence(passive):
    """旧事件没有明确供牌字段时，连续且无动作副作用的事件仍可跨越。"""
    rules, obs = _ambiguous_chi()
    history = (PublicEvent(5, "tile_discarded", 3, (Tile("9t"),)), passive,
               PublicEvent(7, "chi", 0, tuple(Tile(c) for c in ("7t", "8t", "9t"))))
    facts = _facts(rules.analyze(_with_history(obs, history)))
    assert facts.fact_kind is CandidateFactKind.HAND_PROGRESS
    assert next(u.remaining_estimate for u in facts.useful_tiles if u.code == "9t") == 3


@pytest.mark.parametrize("history_problem", ["missing", "gap", "draw_between", "conflict", "future", "old_round"])
def test_unproven_chi_keeps_a_conservative_count(history_problem):
    """缺史/断序/跨局时不再降级为未知，改为「不扣重叠」的保守数值。"""
    rules, obs = _ambiguous_chi()
    discard = PublicEvent(5, "tile_discarded", 3, (Tile("9t"),))
    chi = PublicEvent(6, "chi", 0, tuple(Tile(c) for c in ("7t", "8t", "9t")))
    histories = {
        "missing": (),
        "gap": (discard, replace(chi, seq=7)),
        "draw_between": (discard, PublicEvent(6, "tile_drawn", 1), replace(chi, seq=7)),
        "conflict": (discard, replace(discard, tiles=(Tile("7t"),)), chi),
        "future": (replace(discard, seq=20), replace(chi, seq=21)),
        "old_round": (discard, chi, PublicEvent(7, "round_ended", None), PublicEvent(8, "round_started", None)),
    }
    changed = replace(obs, public_history=histories[history_problem], snapshot_seq=10, consumed_seq=10,
                      rule_state=replace(obs.rule_state, catch_play=False, catch_play_owner_seat=None,
                                         chain_count=0), chain_piao=0)
    analysis = rules.analyze(changed)
    facts = _facts(analysis)
    assert facts.fact_kind is CandidateFactKind.HAND_PROGRESS
    counts = {u.code: u.remaining_estimate for u in facts.useful_tiles}
    # 牌河 7t×1、9t×1 加副露各 1 张 ⇒ 公开 2 / 2；不扣重叠 ⇒ 剩余 2 / 2。
    assert (counts["7t"], counts["9t"]) == (2, 2)
    assert {c.action_key for c in analysis.legal_candidates} == {c.action_key for c in rules.analyze(obs).legal_candidates}
    assert analysis.emergency_candidate is not None


def test_chi_without_claim_evidence_keeps_candidates_and_hu_available():
    chi = PublicMeld(2, "chi", tuple(Tile(c) for c in ("1w", "2w", "3w")), 1)
    obs = make_observation(drawn_tile=Tile("4t"), melds=((), (), (chi,), ()),
                           discards=((), (Tile("1w"), Tile("2w")), (), ()))
    analysis = _rules().analyze(obs)
    # 缺史吃副露不再牵连候选：给保守数值，不影响合法集、立即胡与紧急候选。
    assert _facts(analysis, "discard:1w").fact_kind is CandidateFactKind.HAND_PROGRESS
    assert _facts(analysis, "discard:4t").fact_kind is CandidateFactKind.HAND_PROGRESS
    assert _facts(analysis, "hu").fact_kind is CandidateFactKind.WIN


@pytest.mark.parametrize("repeat", [False, True])
@pytest.mark.parametrize("explicit", [False, True])
def test_identical_chi_shapes_keep_both_distinct_called_tiles(repeat, explicit):
    rules, engine, world = _after_piao_and_claim("peng")
    obs = engine.frame(world).decisions[0].observation
    shape = tuple(Tile(c) for c in ("7t", "8t", "9t"))
    meld = PublicMeld(3, "chi", shape, 2)
    history = (PublicEvent(1, "tile_discarded", 2, (Tile("7t"),)), PublicEvent(2, "chi", 3, shape),
               PublicEvent(10, "tile_discarded", 2, (Tile("9t"),)), PublicEvent(11, "chi", 3, shape))
    if explicit:
        history = (replace(history[1], claimed_tile=Tile("7t")),
                   replace(history[3], claimed_tile=Tile("9t")))
    if repeat:
        index = 0 if explicit else 1
        history = history[:index + 1] + (history[index],) + history[index + 1:]  # 同一事件重复通知不重复扣牌。
    obs = replace(obs, melds=(obs.melds[0], (), (), (meld, meld)),
                  discards=(obs.discards[0], obs.discards[1], (Tile("7t"), Tile("9t")), ()),
                  public_history=history, snapshot_seq=11, consumed_seq=11)
    facts = _facts(rules.analyze(obs))
    counts = {u.code: u.remaining_estimate for u in facts.useful_tiles}
    assert (counts["7t"], counts["8t"], counts["9t"]) == (2, 2, 2)


def test_explicit_identical_claims_cannot_exceed_current_river_capacity():
    """两次吃的明确供牌相同，也不能从仅有一张的牌河中扣两次。"""
    rules, engine, world = _after_piao_and_claim("peng")
    obs = engine.frame(world).decisions[0].observation
    shape = tuple(Tile(c) for c in ("7t", "8t", "9t"))
    meld = PublicMeld(3, "chi", shape, 2)
    history = (PublicEvent(2, "chi", 3, shape, claimed_tile=Tile("7t")),
               PublicEvent(7, "chi", 3, shape, claimed_tile=Tile("7t")))
    obs = replace(obs, melds=(obs.melds[0], (), (), (meld, meld)),
                  discards=(obs.discards[0], obs.discards[1], (Tile("7t"), Tile("9t")), ()))
    analysis = rules.analyze(_with_history(obs, history))
    assert _facts(analysis).fact_kind is CandidateFactKind.ANALYSIS_FAILED
    assert analysis.emergency_candidate is not None


@pytest.mark.parametrize("kind", ["gang", "gang_an", "gang_ming", "gang_bu"])
def test_four_exposed_copies_leave_zero_regardless_of_gang_history(kind):
    rules, engine, world = _after_piao_and_claim("peng")
    obs = engine.frame(world).decisions[0].observation
    quad = PublicMeld(0, kind, (Tile("东"),) * 4, None if kind in ("gang", "gang_an") else 1)
    rivers = obs.discards if kind != "gang_an" else (obs.discards[0], (), (), ())
    obs = replace(obs, melds=((quad,), (), (), ()), discards=rivers, public_history=())
    facts = _facts(rules.analyze(obs))
    assert next(u.remaining_estimate for u in facts.useful_tiles if u.code == "东") == 0
