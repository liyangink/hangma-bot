"""官方本人可见轨迹锁定连续动作的爆头继承，不依赖随机触发。"""
import json
from pathlib import Path
from dataclasses import replace

from hangma_bot.adapters.official.dto import parse_state_response
from hangma_bot.adapters.official.projector import observation, public_event
from hangma_bot.hangma.observation_rules import compare_observation_transition, recompute_draw_rule_state
from hangma_bot.hangma.progression import recompute_baotou

FIXTURE = Path(__file__).parents[2] / 'fixtures/official/v18/action-chain/chi-gang-draw.json'


def trace():
    data = json.loads(FIXTURE.read_text())
    events = tuple(public_event(e) for e in parse_state_response({'events': data['events']}).events)
    views = {}
    for seq, doc in data['snapshots'].items():
        snap = parse_state_response(doc).snapshot
        views[int(seq)] = replace(observation(snap, tuple(e for e in events if e.seq <= int(seq)), 'chain-trace'), consumed_seq=int(seq))
    return views, events


def test_official_chi_gang_replacement_keeps_baotou_until_discard():
    views, events = trace()
    before, after = views[2267], views[2269]
    hand = list(after.my_hand);hand.remove(after.drawn_tile)
    assert not recompute_baotou(tuple(hand), 2, 2)  # 静态已改变，持续状态仍继承
    assert before.rule_state.baotou and after.rule_state.baotou
    checks = compare_observation_transition(before, tuple(e for e in events if 2267 < e.seq <= 2269), after)
    assert not any(x.startswith('god_mismatch:') for x in checks)
    discarded = views[2270]
    assert not discarded.rule_state.baotou and discarded.rule_state.chain_count == 0
    checks = compare_observation_transition(after, (events[-1],), discarded)
    assert not any(x.startswith('god_mismatch:') for x in checks)


def test_incremental_replacement_uses_same_lifecycle_as_authoritative_trace():
    views, _ = trace();after = views[2269]
    hand = list(after.my_hand);hand.remove(after.drawn_tile)
    base = replace(after, my_hand=tuple(hand), drawn_tile=None)
    assert recompute_draw_rule_state(base, after.drawn_tile, replacement=True).baotou
