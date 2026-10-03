"""T129批次的公开事实差分、规范编码、实体边界及装配恢复验证。"""

from dataclasses import asdict
import importlib.util
import json
from pathlib import Path
import random
import subprocess
import sys
from types import ModuleType

import pytest

from hangma_bot.hangma import hand_analysis as hand
from hangma_bot.hangma import natural_preparation as natural
from hangma_bot.hangma import route_structure as route
from hangma_bot.kernel.actions import CANONICAL_TILE_ORDER, Tile


ROOT = Path(__file__).resolve().parents[3]
OVERLAY_PATH = ROOT / "review/vip-route-2026-09-30/evidence/t129-s02-grouped-optimization-1/math_batch.py"
spec = importlib.util.spec_from_file_location("t129_math_batch_test", OVERLAY_PATH)
overlay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(overlay)


def counts(codes):
    """按规范牌序构造等待手牌，不读取隐藏信息或运行比赛。"""
    parts = codes.split()
    return tuple(parts.count(code) for code in CANONICAL_TILE_ORDER)


def random_counts(rng, melds, whites, extra=0):
    """固定随机实体域；extra=1补成动作态以验证普通进张核心。"""
    result = [0] * 33
    for _ in range(13 - 3 * melds + extra - whites):
        index = rng.choice([index for index, value in enumerate(result) if value < 4])
        result[index] += 1
    return tuple(result) + (whites,)


def hand_tiles(values):
    return tuple(Tile(code) for code, value in zip(CANONICAL_TILE_ORDER, values) for _ in range(value))


def canonical(facts):
    """全字段规范JSON字节，包括计量、空值、解释及规范牌码顺序。"""
    return json.dumps(asdict(facts), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode()


def panel():
    rng = random.Random(1294600)
    found = []
    for melds in range(5):
        for whites in range(min(4, 13 - 3 * melds) + 1):
            found.extend((random_counts(rng, melds, whites), melds) for _ in range(5))
    found.extend([
        (counts("东 东 东 东"), 3),
        (counts("东 东 东 东 2w 4w 白"), 2),
        (counts("1w 1w 1w 1w 2w 2w 3w 3w 4w 4w 5w 5w 白"), 0),
        (counts("1w 1w 3w 3w 5b 5b 7t 7t 东 南 西 白 白"), 0),
        (counts("1w 2w 3w 1t 2t 3t 1b 2b 3b 7w 8w 白 白"), 0),
        (counts("白 白 白 白"), 3),
        (counts("1w 2w 3w 1b 2b 3b 1t 2t 3t 白 白 白 白"), 0),
        (counts("2w 3w 4w 4b 6b 9b 9b 9b 5t 5t 7t 8t 9t"), 0),
        (counts("2w 3w 4w 4b 9b 9b 9b 5t 5t 5t 7t 8t 9t"), 0),
    ])
    return found


@pytest.mark.parametrize("order", ("hand_first", "natural_first", "route_first"))
def test_complete_public_facts_and_canonical_bytes_match_frozen_formula(order):
    rows = panel()
    references = [(
        canonical(hand.analyse_hand(hand_tiles(values), melds)),
        canonical(hand.analyse_counts_progress(values, melds)),
        canonical(route.analyze_route_structure(values, melds)),
        canonical(natural.analyze_natural_set_preparation(values, melds)),
    ) for values, melds in rows]
    with overlay.installed() as (_, stats):
        for (values, melds), expected in zip(rows, references):
            if order == "natural_first":
                natural.analyze_natural_set_preparation(values, melds)
            elif order == "route_first":
                route.analyze_route_structure(values, melds)
            actual = (
                canonical(hand.analyse_hand(hand_tiles(values), melds)),
                canonical(hand.analyse_counts_progress(values, melds)),
                canonical(route.analyze_route_structure(values, melds)),
                canonical(natural.analyze_natural_set_preparation(values, melds)),
            )
            assert actual == expected
    assert stats["bindings_restored"]
    assert stats["standard_need_calls_avoided"] > 0


def test_action_size_win_and_non_win_inputs_keep_all_pattern_useful_sets():
    rng = random.Random(1291400)
    rows = []
    for melds in range(5):
        for whites in range(min(4, 14 - 3 * melds) + 1):
            rows.extend((random_counts(rng, melds, whites, extra=1), melds) for _ in range(3))
    rows.extend([
        (counts("1w 2w 3w 1b 2b 3b 1t 2t 3t 东 东 东 白 白"), 0),
        (counts("1w 1w 1w 1w 2w 2w 3w 3w 4w 4w 5w 5w 白 白"), 0),
        (counts("东 白"), 4),
        (counts("白 白"), 4),
    ])
    expected = [canonical(hand.analyse_hand(hand_tiles(values), melds)) for values, melds in rows]
    with overlay.installed():
        assert [canonical(hand.analyse_hand(hand_tiles(values), melds)) for values, melds in rows] == expected


def test_distinct_global_standard_natural_and_retained_white_targets_remain_distinct():
    values = counts("1w 2w 3w 1t 2t 3t 1b 2b 3b 7w 8w 白 白")
    with overlay.installed():
        summary = hand.analyse_hand(hand_tiles(values), 0)
        structure = route.analyze_route_structure(values, 0)
        preparation = natural.analyze_natural_set_preparation(values, 0)
    complete, one, all_white = structure.targets[:3]
    assert "白" in tuple(tile.code for tile in summary.useful_tiles)
    assert complete.natural_need == 1 and len(complete.conditional_need_improvement_codes) == 33
    assert one.natural_need == 0 and one.conditional_need_improvement_codes == ()
    assert all_white.natural_need == preparation.natural_draw_lower_bound == 1
    assert preparation.natural_need_improvement_codes == ("6w", "9w")
    assert "白" not in preparation.natural_need_improvement_codes


def test_actual_backend_calls_are_separate_from_preserved_result_request_counts():
    values = counts("东 东 东 东 2w 4w 白")
    with overlay.installed() as (_, stats):
        summary = hand.analyse_counts_progress(values, 2)
        structure = route.analyze_route_structure(values, 2)
        preparation = natural.analyze_natural_set_preparation(values, 2)
        calls = stats["backend_need_calls"]
        assert summary.standard_shanten == structure.standard_shanten
        assert structure.target_distance_evaluation_count == 66
        assert preparation.target_distance_evaluation_count == 33
        assert "东" not in preparation.natural_need_improvement_codes
        # 完成目标和全保白目标各33请求，白进张另1请求；天然目标复用后端。
        assert calls == 67
        assert stats["standard_distance_requests"] == 134
        assert stats["target_distance_requests"] == 99
        assert stats["natural_draw_tuple_constructions"] == 64
        route.analyze_route_structure(values, 2)
        natural.analyze_natural_set_preparation(values, 2)
        assert stats["backend_need_calls"] == calls
    assert stats["standard_need_calls_avoided"] == 67


def test_four_white_waiting_hand_and_complete_hand_keep_original_win_short_circuit():
    """四财等待态不凭库存提前跳过进张；完整数学已胡才返回空/None结果。"""
    waiting = counts("1w 2w 3w 1b 2b 3b 1t 2t 3t 白 白 白 白")
    complete = counts("1w 2w 3w 1b 2b 3b 1t 2t 3t 东 白 白 白 白")
    expected_waiting = canonical(hand.analyse_hand(hand_tiles(waiting), 0))
    expected_complete = canonical(hand.analyse_hand(hand_tiles(complete), 0))
    with overlay.installed() as (_, stats):
        won = hand.analyse_hand(hand_tiles(complete), 0)
        assert canonical(won) == expected_complete
        assert won.is_win and won.useful_tiles == ()
        assert won.standard_useful_tiles is won.seven_pairs_useful_tiles is None
        assert stats["backend_need_calls"] == 1
        assert stats["natural_draw_tuple_constructions"] == 0
        pending = hand.analyse_hand(hand_tiles(waiting), 0)
        assert canonical(pending) == expected_waiting
        assert not pending.is_win
        assert "白" not in tuple(tile.code for tile in pending.useful_tiles)
        assert len(pending.standard_useful_tiles) == 33


@pytest.mark.parametrize("target", ("route", "natural"))
def test_strict_waiting_validation_still_precedes_cache(target):
    original = route.analyze_route_structure if target == "route" else natural.analyze_natural_set_preparation
    valid = counts("东")
    invalids = [(list(valid), 4), (tuple(bool(value) for value in valid), 4),
                (valid, True), (valid, 5), (valid[:-1], 4), (counts("东 东"), 4),
                ((5,) + (0,) * 33, 3), (valid[:27] + (1.0,) + valid[28:], 4)]
    expected = []
    for values, melds in invalids:
        try:
            original(values, melds)
        except (TypeError, ValueError) as exc:
            expected.append((type(exc), str(exc)))
        else:
            pytest.fail("invalid reference input accepted")
    with overlay.installed():
        function = route.analyze_route_structure if target == "route" else natural.analyze_natural_set_preparation
        function(valid, 4)
        for (values, melds), (kind, message) in zip(invalids, expected):
            with pytest.raises(kind) as raised:
                function(values, melds)
            assert str(raised.value) == message


def test_first_party_aliases_and_exception_restore_use_object_identity(monkeypatch):
    aliases = ModuleType("_t88_t129_test_aliases")
    aliases.route = route.analyze_route_structure
    aliases.natural = natural.analyze_natural_set_preparation
    monkeypatch.setitem(sys.modules, aliases.__name__, aliases)
    original_route, original_natural = aliases.route, aliases.natural
    with pytest.raises(RuntimeError, match="test failure"):
        with overlay.installed() as (_, stats):
            assert aliases.route is route.analyze_route_structure
            assert aliases.natural is natural.analyze_natural_set_preparation
            assert aliases.route is not original_route
            aliases.route(counts("东"), 4)
            raise RuntimeError("test failure")
    assert aliases.route is original_route and aliases.natural is original_natural
    assert stats["bindings_restored"]


def test_fixed_random_difference_uses_frozen_c_and_python_backends_without_mutation():
    """隔离解释器读冻结源码；Python退路也和自身未装配事实逐字段差分。"""
    frozen = Path("/Users/liyang/.codex/worktrees/t54-public-count-cache/hangma-bot/src")
    if not frozen.exists():
        pytest.skip("fixed frozen worktree absent")
    script = r'''
import dataclasses, hashlib, importlib.util, json, random, sys
sys.path.insert(0, sys.argv[1])
if sys.argv[3] == "python":
    sys.modules["hangma_bot.hangma._grouped_native"] = None
from hangma_bot.hangma import _standard, hand_analysis as h, route_structure as r, natural_preparation as n
from hangma_bot.kernel.actions import CANONICAL_TILE_ORDER, Tile
spec=importlib.util.spec_from_file_location("t129_frozen_diff",sys.argv[2])
o=importlib.util.module_from_spec(spec);spec.loader.exec_module(o)
rng=random.Random(1293141)
rows=[]
for m in range(5):
    for w in range(min(4,13-3*m)+1):
        for _ in range(3):
            values=[0]*33
            for __ in range(13-3*m-w):
                i=rng.choice([i for i,v in enumerate(values) if v<4]);values[i]+=1
            rows.append((tuple(values)+(w,),m))
def emit(c,m):
    tiles=tuple(Tile(code) for code,v in zip(CANONICAL_TILE_ORDER,c) for _ in range(v))
    return json.dumps([dataclasses.asdict(h.analyse_hand(tiles,m)),
                       dataclasses.asdict(r.analyze_route_structure(c,m)),
                       dataclasses.asdict(n.analyze_natural_set_preparation(c,m))],
                      ensure_ascii=False,sort_keys=True,separators=(",",":"))
before=[emit(c,m) for c,m in rows]
with o.installed() as (_,stats):
    after=[emit(c,m) for c,m in rows]
assert before==after
print(json.dumps({"backend":_standard.IMPLEMENTATION,"rows":len(rows),"stats":stats,
                  "complete_facts_sha256":hashlib.sha256("\n".join(before).encode()).hexdigest()}))
'''
    results = []
    for backend in ("native", "python"):
        completed = subprocess.run([sys.executable, "-I", "-B", "-c", script,
                                    str(frozen), str(OVERLAY_PATH), backend],
                                   capture_output=True, text=True, check=True, timeout=60)
        results.append(json.loads(completed.stdout))
    assert results[0]["backend"] == "c_grouped"
    assert results[1]["backend"] == "python_grouped"
    assert results[0]["rows"] == results[1]["rows"] == 66
    assert results[0]["complete_facts_sha256"] == results[1]["complete_facts_sha256"]
    assert all(item["stats"]["bindings_restored"] for item in results)
