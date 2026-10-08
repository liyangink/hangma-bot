"""T54 公共计数 scope 行为草稿；只核公开输出，不读取缓存或 ContextVar。

合成输入只含本人观察可见字段。可变子类是兼容旁路输入，不绕过 frozen。
缓存规模与命中数由根的独立仪器核验，本文件不把私有状态当成公共合同。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t54-public-count-native-cache-1/edgecase-tests'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from dataclasses import replace
import gc
from threading import Barrier
from types import SimpleNamespace
import weakref

import pytest

from hangma_bot.hangma.public_tile_counts import (
    PublicClaimEvidence, PublicTileView, count_public_tiles,
    count_public_tiles_from_view, count_unseen_tiles_from_view,
    public_count_result_scope,
)
from hangma_bot.kernel.actions import CANONICAL_TILE_ORDER, Tile
from hangma_bot.kernel.observation import (
    PlayerObservation, PublicEvent, PublicMeld, RulePublicState,
)


def _tiles(*codes):
    """构造规范牌码元组；不包含他家暗牌或未来牌墙。"""
    return tuple(Tile(code) for code in codes)


def _empty_view(**changes):
    """合成四座公开输入，座位顺序 0—3；墙余缺失时不猜留河口径。"""
    values = dict(discards=((), (), (), ()), melds=((), (), (), ()),
                  hand_counts=(13, 13, 13, 13), remaining_tile_count=None,
                  snapshot_seq=0, consumed_seq=2)
    return PublicTileView(**(values | changes))


def _chi_view():
    """公开吃3w的保留口径，官方序号1弃牌、2吃；无本地伪序号。"""
    shape = _tiles("1w", "2w", "3w")
    history = (PublicEvent(1, "tile_discarded", 3, _tiles("3w")),
               PublicEvent(2, "chi", 0, shape))
    return _empty_view(
        discards=((), (), (), _tiles("3w")),
        melds=((PublicMeld(0, "chi", shape, 3),), (), (), ()),
        hand_counts=(10, 13, 13, 13), remaining_tile_count=84,
        public_history=history)


def _public_fact(result, code):
    """按规范34牌序取公开张数和证据，不使用私有索引常量。"""
    index = CANONICAL_TILE_ORDER.index(code)
    return result.counts[index], result.evidence[index]


def _conditional_fact(view, code, *, concealed=(), drawn=None, piao=0, seat=0):
    """只经公共条件计数核容量；暗牌和单列摸牌严格分开。"""
    result = count_unseen_tiles_from_view(
        view, seat=seat, concealed=concealed, drawn_tile=drawn, chain_piao=piao)
    index = CANONICAL_TILE_ORDER.index(code)
    return result.public[index], result.unseen[index], result.evidence[index]


def _observation(view):
    """给旧观察入口构造最小公开观察；不执行策略、模型或模拟器。"""
    return PlayerObservation(
        game_id="t54-public-result-scope", seat=0, round_no=1,
        snapshot_seq=view.snapshot_seq, consumed_seq=view.consumed_seq,
        phase="draw", dealer_seat=0, turn_seat=0, responding_seats=(),
        my_hand=_tiles("1w", "2w", "3w", "4w", "5w", "6w", "7w",
                       "8w", "9w", "1b", "2b", "3b", "4b"),
        drawn_tile=None, discards=view.discards, melds=view.melds,
        hand_counts=view.hand_counts, last_discard=None,
        remaining_tile_count=view.remaining_tile_count, scores=(0, 0, 0, 0),
        rule_state=RulePublicState(Tile("白"), False, 0, False),
        public_history=view.public_history, chain_piao=0, gang_draw=False)


@pytest.mark.parametrize("field", (
    "discards", "melds", "hand_counts", "remaining_tile_count",
    "public_history", "snapshot_seq", "consumed_seq", "claim_evidence",
))
def test_each_public_view_field_preserves_its_actual_result(field):
    """八字段各有改变完整输出的输入；前后交错调用不能继承旧事实。"""
    source = _chi_view()
    alternatives = {
        "discards": replace(source, discards=((), (), (), _tiles("2w"))),
        "melds": replace(source, melds=((), (), (), ())),
        "hand_counts": replace(source, hand_counts=(11, 13, 13, 13)),
        "remaining_tile_count": replace(source, remaining_tile_count=None),
        "public_history": replace(source, public_history=()),
        "consumed_seq": replace(source, consumed_seq=1),
    }
    if field == "snapshot_seq":
        source = replace(source, snapshot_seq=2, consumed_seq=None)
        alternative = replace(source, snapshot_seq=1)
    elif field == "claim_evidence":
        source = replace(source, public_history=(), remaining_tile_count=None)
        alternative = replace(source, claim_evidence=(
            PublicClaimEvidence(0, 0, 3, Tile("3w"), "assumed", True),))
    else:
        alternative = alternatives[field]
    expected = [count_public_tiles_from_view(source), count_public_tiles_from_view(alternative)]
    assert expected[0] != expected[1]
    with public_count_result_scope() as value:
        assert value is None
        for _ in range(3):
            assert count_public_tiles_from_view(source) == expected[0]
            assert count_public_tiles_from_view(alternative) == expected[1]


def test_equal_history_with_different_tuple_identity_has_same_full_result():
    """同值不同历史原件可独立解析；身份分离不能改变事实。"""
    source = _chi_view()
    duplicate = replace(source, public_history=tuple(list(source.public_history)))
    assert source.public_history is not duplicate.public_history
    expected = count_public_tiles_from_view(source)
    with public_count_result_scope():
        for value in (source, duplicate, source, duplicate):
            assert count_public_tiles_from_view(value) == expected


def test_legacy_four_meld_and_strict_condition_view_keep_different_meanings():
    """暗杠之外的第五张同码河牌，旧兼容4与严格未知不能混用。"""
    gang = PublicMeld(2, "gang_an", (Tile("2w"),) * 4, None)
    view = _empty_view(discards=(_tiles("2w"), (), (), ()), melds=((), (), (gang,), ()))
    observation = _observation(view)
    index = CANONICAL_TILE_ORDER.index("2w")
    for _ in range(3):
        with public_count_result_scope():
            assert count_public_tiles(observation)[index] == 4
            assert _public_fact(count_public_tiles_from_view(view), "2w") == (None, "unknown")
            assert count_public_tiles(observation)[index] == 4


@pytest.mark.parametrize("problem", ("conflict", "reordered", "reset", "gap", "intervening_draw"))
def test_conflicting_or_incomplete_history_keeps_conservative_result(problem):
    """冲突、回退、跨单局、缺口及插入他家摸牌不能保留旧领取证明。"""
    source = _chi_view()
    discard, claim = source.public_history
    histories = {
        "conflict": (discard, replace(discard, tiles=_tiles("2w")), claim),
        "reordered": (claim, discard),
        "reset": (discard, claim, PublicEvent(3, "round_started", None)),
        "gap": (discard, replace(claim, seq=3)),
        "intervening_draw": (discard, PublicEvent(2, "tile_drawn", 1), replace(claim, seq=3)),
    }
    changed = replace(source, public_history=histories[problem], consumed_seq=3)
    with public_count_result_scope():
        assert _public_fact(count_public_tiles_from_view(source), "3w") == (1, "exact")
        assert _public_fact(count_public_tiles_from_view(changed), "3w") == (2, "conservative")
        assert _public_fact(count_public_tiles_from_view(changed), "3w") == (2, "conservative")
        assert _public_fact(count_public_tiles_from_view(source), "3w") == (1, "exact")


def test_instance_proof_consumption_does_not_change_later_public_call():
    """相同牌形两份证明对应两副露；一次调用消费列表不能污染下一次。"""
    source = _chi_view()
    source = replace(source, public_history=source.public_history + (
        PublicEvent(3, "tile_discarded", 3, _tiles("3w")),
        PublicEvent(4, "chi", 0, source.melds[0][0].tiles)), consumed_seq=4)
    two = replace(source, melds=((source.melds[0][0], source.melds[0][0]), (), (), ()),
                  discards=((), (), (), _tiles("3w", "3w")), hand_counts=(7, 13, 13, 13))
    with public_count_result_scope():
        for _ in range(3):
            assert _public_fact(count_public_tiles_from_view(source), "3w") == (2, "conservative")
            assert _public_fact(count_public_tiles_from_view(two), "3w") == (2, "exact")


@pytest.mark.parametrize("hidden_count", (0, 1, 4))
@pytest.mark.parametrize("piao", (0, None, 2))
def test_same_public_view_recalculates_nine_hidden_and_white_capacity_combinations(hidden_count, piao):
    """同一公开视图下，本人超量与飘白未知分别覆盖最终条件证据。"""
    source = _chi_view()
    hidden = (Tile("3w"),) * hidden_count
    expected = count_unseen_tiles_from_view(source, seat=0, concealed=hidden, drawn_tile=None, chain_piao=piao)
    with public_count_result_scope():
        count_unseen_tiles_from_view(source, seat=0, concealed=(), drawn_tile=None, chain_piao=0)
        actual = count_unseen_tiles_from_view(source, seat=0, concealed=hidden, drawn_tile=None, chain_piao=piao)
        assert actual == expected
        normal_index, white_index = map(CANONICAL_TILE_ORDER.index, ("3w", "白"))
        assert actual.public[normal_index] == 1
        assert actual.unseen[normal_index] == (3 - hidden_count if hidden_count <= 3 else None)
        assert actual.evidence[normal_index] == ("exact" if hidden_count <= 3 else "unknown")
        assert actual.unseen[white_index] == (None if piao is None else 4 - piao)
        assert actual.evidence[white_index] == ("unknown" if piao is None else "exact")


def test_drawn_tile_and_concealed_are_recalculated_independently():
    """单列摸牌只扣一次，不能继承另一个暗牌输入的条件容量。"""
    source = _chi_view()
    with public_count_result_scope():
        assert _conditional_fact(source, "3w", concealed=_tiles("3w")) == (1, 2, "exact")
        assert _conditional_fact(source, "3w", drawn=Tile("3w")) == (1, 2, "exact")
        assert _conditional_fact(source, "3w", concealed=(Tile("3w"),) * 3, drawn=Tile("3w")) == (1, None, "unknown")
        assert _conditional_fact(source, "3w") == (1, 3, "exact")


def test_missing_white_evidence_can_recover_after_nonwhite_discard():
    """给定公开弃牌事实与断链结果后，白板未知不能粘在旧容量上。"""
    source = _empty_view(hand_counts=(14, 13, 13, 13), remaining_tile_count=83)
    after = replace(source, discards=(_tiles("南"), (), (), ()), hand_counts=(13, 13, 13, 13))
    with public_count_result_scope():
        assert _conditional_fact(source, "白", concealed=_tiles("白", "南"), piao=None) == (0, None, "unknown")
        assert _conditional_fact(after, "白", concealed=_tiles("白"), piao=0) == (0, 3, "exact")
        assert _conditional_fact(source, "白", concealed=_tiles("白", "南"), piao=2) == (0, 1, "exact")
        assert _conditional_fact(after, "白", concealed=_tiles("白"), piao=0) == (0, 3, "exact")


def test_forced_white_discard_and_piao_white_discard_use_given_chain_facts():
    """仅给公开计数事实：同一弃白后态，断链与保链的白板容量不同。"""
    source = _empty_view(hand_counts=(14, 13, 13, 13))
    after = replace(source, discards=(_tiles("白"), (), (), ()), hand_counts=(13, 13, 13, 13))
    with public_count_result_scope():
        assert _conditional_fact(source, "白", concealed=_tiles("白"), piao=2) == (0, 1, "exact")
        assert _conditional_fact(after, "白", piao=0) == (1, 3, "exact")
        assert _conditional_fact(after, "白", piao=3) == (1, 1, "exact")
        assert _conditional_fact(after, "白", piao=None) == (1, None, "unknown")


@pytest.mark.parametrize("kind", ("gang_ming", "gang_bu"))
@pytest.mark.parametrize("retained", (False, True))
def test_gang_claim_is_counted_once_for_both_river_regimes(kind, retained):
    """补杠继承一次领取；留河或移河都不能虚增第五张。"""
    meld = PublicMeld(1, kind, (Tile("东"),) * 4, 0)
    source = _empty_view(
        discards=(_tiles("东") if retained else (), (), (), ()),
        melds=((), (meld,), (), ()),
        claim_evidence=(PublicClaimEvidence(1, 0, 0, Tile("东"), "assumed", retained),))
    with public_count_result_scope():
        assert _conditional_fact(source, "东") == (4, 0, "exact")
        impossible = replace(source, discards=(source.discards[0], (), _tiles("东"), ()))
        assert _conditional_fact(impossible, "东") == (None, None, "unknown")
        assert _conditional_fact(source, "东") == (4, 0, "exact")


def test_mixed_river_regime_does_not_claim_an_old_same_code_discard():
    """同码旧弃牌不能代替本次已经移河的领取牌，另一副露仍留河。"""
    source = _empty_view(
        discards=(_tiles("1w", "2w"), (), (), ()),
        melds=((), (PublicMeld(1, "peng", (Tile("1w"),) * 3, 0),),
               (PublicMeld(2, "peng", (Tile("2w"),) * 3, 0),), ()),
        hand_counts=(13, 10, 10, 13), remaining_tile_count=83,
        claim_evidence=(PublicClaimEvidence(1, 0, 0, Tile("1w"), "assumed", False),
                        PublicClaimEvidence(2, 0, 0, Tile("2w"), "assumed", True)))
    with public_count_result_scope():
        assert _conditional_fact(source, "1w") == (4, 0, "exact")
        assert _conditional_fact(source, "2w") == (3, 1, "exact")
        unknown_first_claim = replace(source, claim_evidence=source.claim_evidence[1:])
        assert _conditional_fact(unknown_first_claim, "1w") == (4, 0, "conservative")
        assert _conditional_fact(source, "1w") == (4, 0, "exact")


def test_fifth_discard_and_missing_retained_feeder_are_unknown_not_zero():
    """真实物理矛盾标未知；不能把上一结果的四张或精确证据复用。"""
    four = _empty_view(discards=(_tiles("3w", "3w", "3w", "3w"), (), (), ()))
    five = replace(four, discards=(_tiles("3w", "3w", "3w", "3w", "3w"), (), (), ()))
    source = replace(_chi_view(), public_history=(), remaining_tile_count=None,
                     claim_evidence=(PublicClaimEvidence(0, 0, 3, Tile("3w"), "assumed", True),))
    other_river = replace(source, discards=(_tiles("3w"), (), (), ()))
    with public_count_result_scope():
        assert _conditional_fact(four, "3w") == (4, 0, "exact")
        assert _conditional_fact(five, "3w") == (None, None, "unknown")
        assert _conditional_fact(source, "3w") == (1, 3, "exact")
        assert _conditional_fact(other_river, "3w") == (None, None, "unknown")


class _MutableRow(tuple):
    """tuple 子类的迭代语义可由普通属性写入改变。"""
    def __iter__(self):
        return iter(_tiles("2w")) if getattr(self, "changed", False) else super().__iter__()


class _MutableText(str):
    """字符串子类保持哈希，可切换比较语义。"""
    __hash__ = str.__hash__
    def __eq__(self, other):
        return not getattr(self, "changed", False) and str.__eq__(self, other)


class _MutableInt(int):
    """整数子类保持键值，普通属性可改变守恒求和或转换的结果。"""
    def __int__(self):
        return int.__int__(self) + int(getattr(self, "changed", False))
    def __radd__(self, other):
        return int.__int__(self) + other + int(getattr(self, "changed", False))


class _MutableTile(Tile):
    """牌值子类可以新增普通属性；不是深不可变规范牌值。"""
    def __getattribute__(self, name):
        if name == "code" and getattr(self, "changed", False):
            return "2w"
        return super().__getattribute__(name)
    def __hash__(self):
        return 3


class _MutableMeld(PublicMeld):
    """副露子类可改变种类；全字段键也不能代替类型旁路。"""
    def __getattribute__(self, name):
        if name == "kind" and getattr(self, "changed", False):
            return "unrecognised"
        return super().__getattribute__(name)
    def __hash__(self):
        return 4


class _MutableClaim(PublicClaimEvidence):
    """领取证据子类可改变留河判断，不绕过 frozen 的已有字段。"""
    def __getattribute__(self, name):
        if name == "retained_in_river" and getattr(self, "changed", False):
            return False
        return super().__getattribute__(name)
    def __hash__(self):
        return 5


class _MutableView(PublicTileView):
    """公开视图子类可改变墙余判断；调用方仍应得到原计数结果。"""
    def __getattribute__(self, name):
        if name == "remaining_tile_count" and getattr(self, "changed", False):
            return 85
        return super().__getattribute__(name)


def _mutable_case(kind):
    """返回兼容输入与普通变更操作；不修改任何规范 frozen 对象。"""
    source = _chi_view()
    if kind == "river_tuple":
        mutable = _MutableRow(_tiles("3w"))
        source = replace(source, discards=((), (), (), mutable))
    elif kind == "meld_text":
        mutable = _MutableText("chi")
        source = replace(source, melds=((PublicMeld(0, mutable, source.melds[0][0].tiles, 3),), (), (), ()))
    elif kind == "wall_int":
        mutable = _MutableInt(84)
        source = replace(source, remaining_tile_count=mutable)
    elif kind == "hand_int":
        mutable = _MutableInt(10)
        source = replace(source, hand_counts=(mutable, 13, 13, 13))
    elif kind == "tile_value":
        mutable = _MutableTile("3w")
        source = replace(source, discards=((), (), (), (mutable,)))
    elif kind == "meld_value":
        mutable = _MutableMeld(0, "chi", source.melds[0][0].tiles, 3)
        source = replace(source, melds=((mutable,), (), (), ()))
    elif kind == "claim_value":
        mutable = _MutableClaim(0, 0, 3, Tile("3w"), "assumed", True)
        source = replace(source, public_history=(), remaining_tile_count=None, claim_evidence=(mutable,))
    elif kind == "view_value":
        mutable = _MutableView(**source.__dict__)
        source = mutable
    elif kind == "event_text":
        mutable = _MutableText("same")
        discard, claim = source.public_history
        source = replace(source, public_history=(replace(discard, result_details=(mutable,)),
                                                 replace(discard, result_details=("same",)), claim))
    elif kind == "mutable_event":
        events = tuple(SimpleNamespace(**event.__dict__) for event in source.public_history)
        source = replace(source, public_history=events)
        return source, lambda changed: setattr(events[0], "tiles", _tiles("9w" if changed else "3w"))
    elif kind == "history_list":
        history = list(source.public_history)
        source = replace(source, public_history=history)
        return source, lambda changed: history.__setitem__(0, replace(history[0], tiles=_tiles("9w" if changed else "3w")))
    elif kind == "hand_list":
        hands = list(source.hand_counts)
        source = replace(source, hand_counts=hands)
        return source, lambda changed: hands.__setitem__(0, 11 if changed else 10)
    else:
        raise AssertionError("未登记的兼容输入")
    return source, lambda changed: setattr(mutable, "changed", changed)


@pytest.mark.parametrize("kind", (
    "river_tuple", "meld_text", "wall_int", "hand_int", "tile_value", "meld_value",
    "claim_value", "view_value", "event_text", "mutable_event", "history_list", "hand_list",
))
def test_mutable_inputs_keep_their_uncached_behavior(kind):
    """实际输出随普通可变输入变化；重复调用不得保持旧结果或拒绝原输入。"""
    source, change = _mutable_case(kind)
    change(False)
    before = count_public_tiles_from_view(source)
    change(True)
    after = count_public_tiles_from_view(source)
    assert before != after
    change(False)
    with public_count_result_scope():
        assert count_public_tiles_from_view(source) == before
        change(True)
        assert count_public_tiles_from_view(source) == after
        change(False)
        assert count_public_tiles_from_view(source) == before


@pytest.mark.parametrize("field", ("hand_counts", "remaining_tile_count", "snapshot_seq", "consumed_seq"))
def test_bool_in_int_field_preserves_existing_result_instead_of_new_rejection(field):
    """公开视图历史上接纳的非规范布尔字段仍按原计算；不增加新拒绝。"""
    source = _chi_view()
    changes = {"hand_counts": (True, 13, 13, 13), "remaining_tile_count": True,
               "snapshot_seq": True, "consumed_seq": True}
    source = replace(source, **{field: changes[field]})
    expected = count_public_tiles_from_view(source)
    with public_count_result_scope():
        assert count_public_tiles_from_view(source) == expected
        assert count_public_tiles_from_view(source) == expected


def test_existing_exception_is_preserved_and_mutable_input_can_be_repaired():
    """原函数异常不能变成缓存成功；可变兼容输入修正后仍可重新计算。"""
    river = [1]
    source = _empty_view(discards=(river, (), (), ()))
    with pytest.raises(AttributeError) as reference:
        count_public_tiles_from_view(source)
    with public_count_result_scope():
        with pytest.raises(type(reference.value)) as actual:
            count_public_tiles_from_view(source)
        assert str(actual.value) == str(reference.value)
        river[0] = Tile("3w")
        assert _public_fact(count_public_tiles_from_view(source), "3w") == (1, "exact")


def test_long_history_has_same_result_when_called_repeatedly():
    """超长规范历史保留原解析行为，不要求纳入结果缓存。"""
    source = _chi_view()
    source = replace(source, public_history=source.public_history + tuple(
        PublicEvent(seq, "pass", 1) for seq in range(3, 4100)), consumed_seq=4099)
    expected = count_public_tiles_from_view(source)
    with public_count_result_scope():
        assert count_public_tiles_from_view(source) == expected
        assert count_public_tiles_from_view(source) == expected


def test_many_distinct_views_keep_their_results_after_default_capacity_boundary():
    """跨过默认结果条目数量仍计算完整正确输出；不读取实际缓存规模。"""
    with public_count_result_scope():
        for index in range(2100):
            count = index % 5
            source = _empty_view(discards=((Tile("3w"),) * count, (), (), ()),
                                 snapshot_seq=index, consumed_seq=index)
            actual = count_public_tiles_from_view(source)
            assert _public_fact(actual, "3w") == (count, "exact")
            assert len(actual.counts) == len(actual.evidence) == 34
        assert _public_fact(count_public_tiles_from_view(_empty_view()), "3w") == (0, "exact")


def test_nested_scope_releases_inner_inputs_and_restores_outer_behavior():
    """每次scope独立拥有资源；内层退出不把原件留在外层缓存。"""
    source = _chi_view()
    expected = count_public_tiles_from_view(source)
    with public_count_result_scope():
        assert count_public_tiles_from_view(source) == expected
        with public_count_result_scope():
            inner = _empty_view(discards=(_tiles("4w"), (), (), ()))
            reference = weakref.ref(inner)
            assert _public_fact(count_public_tiles_from_view(inner), "4w") == (1, "exact")
            del inner
        gc.collect()
        assert reference() is None
        assert count_public_tiles_from_view(source) == expected


def test_exception_exit_releases_scope_inputs_and_next_call_is_correct():
    """异常退出必须归还上下文和原件；随后普通公共调用可继续。"""
    with pytest.raises(RuntimeError, match="t54-scope-test"):
        with public_count_result_scope():
            source = _empty_view(discards=(_tiles("4w"), (), (), ()))
            reference = weakref.ref(source)
            assert _public_fact(count_public_tiles_from_view(source), "4w") == (1, "exact")
            del source
            raise RuntimeError("t54-scope-test")
    gc.collect()
    assert reference() is None
    assert _public_fact(count_public_tiles_from_view(_chi_view()), "3w") == (1, "exact")


def test_parallel_threads_use_scopes_without_crossing_public_observations():
    """线程并行各开scope；子scope退出释放自己的原件并保持父调用。"""
    barrier = Barrier(4)
    sources = [_chi_view(), replace(_chi_view(), remaining_tile_count=None),
               _empty_view(discards=(_tiles("白"), (), (), ())), _empty_view()]
    expected = [count_public_tiles_from_view(source) for source in sources]

    def worker(index):
        with public_count_result_scope():
            ephemeral = replace(sources[index])
            reference = weakref.ref(ephemeral)
            barrier.wait(timeout=5)
            values = [count_public_tiles_from_view(ephemeral) for _ in range(3)]
            del ephemeral
        return values, reference

    with public_count_result_scope():
        parent = _chi_view()
        parent_expected = count_public_tiles_from_view(parent)
        with ThreadPoolExecutor(max_workers=4) as executor:
            actual = list(executor.map(worker, range(4)))
        gc.collect()
        for index, (values, reference) in enumerate(actual):
            assert values == [expected[index]] * 3
            assert reference() is None
        assert count_public_tiles_from_view(parent) == parent_expected


def test_parallel_async_tasks_with_nested_scopes_keep_observations_separate():
    """异步任务继承父上下文后各开独立scope；交错await不混用观察。"""
    sources = [_chi_view(), replace(_chi_view(), remaining_tile_count=None), _empty_view()]
    expected = [count_public_tiles_from_view(source) for source in sources]

    async def run():
        async def worker(index):
            with public_count_result_scope():
                ephemeral = replace(sources[index])
                reference = weakref.ref(ephemeral)
                first = count_public_tiles_from_view(ephemeral)
                await asyncio.sleep(0)
                second = count_public_tiles_from_view(ephemeral)
                with public_count_result_scope():
                    alternate = count_public_tiles_from_view(sources[(index + 1) % len(sources)])
                    await asyncio.sleep(0)
                third = count_public_tiles_from_view(ephemeral)
                del ephemeral
            return (first, second, third), alternate, reference

        with public_count_result_scope():
            parent_expected = count_public_tiles_from_view(sources[0])
            actual = await asyncio.gather(*(worker(index) for index in range(len(sources))))
            assert count_public_tiles_from_view(sources[0]) == parent_expected
        return actual

    actual = asyncio.run(run())
    gc.collect()
    for index, (values, alternate, reference) in enumerate(actual):
        assert values == (expected[index],) * 3
        assert alternate == expected[(index + 1) % len(sources)]
        assert reference() is None


def test_threads_with_copied_active_context_keep_full_results_correct():
    """显式复制活动上下文供线程并行读取，公开结果不能被中间状态污染。"""
    sources = [_chi_view(), replace(_chi_view(), remaining_tile_count=None),
               _empty_view(discards=(_tiles("白"), (), (), ())), _empty_view()]
    expected = [count_public_tiles_from_view(source) for source in sources]
    barrier = Barrier(4)

    def worker(index):
        barrier.wait(timeout=5)
        return [count_public_tiles_from_view(sources[index]) for _ in range(3)]

    with public_count_result_scope():
        contexts = [copy_context() for _ in sources]
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(contexts[index].run, worker, index) for index in range(4)]
            actual = [future.result(timeout=5) for future in futures]
        assert actual == [[result] * 3 for result in expected]


def test_async_task_inheriting_closed_scope_uses_original_behavior_without_retention():
    """父scope结束后逃逸任务仍可计算，但不能把新原件存进已关闭资源。"""
    async def run():
        started, release = asyncio.Event(), asyncio.Event()

        async def worker():
            started.set()
            await release.wait()
            source = _empty_view(discards=(_tiles("4w"), (), (), ()))
            reference = weakref.ref(source)
            first = count_public_tiles_from_view(source)
            await asyncio.sleep(0)
            second = count_public_tiles_from_view(source)
            del source
            gc.collect()
            assert reference() is None
            return first, second

        with public_count_result_scope():
            count_public_tiles_from_view(_chi_view())
            task = asyncio.create_task(worker())
            await started.wait()
        release.set()
        return await asyncio.wait_for(task, timeout=5)

    first, second = asyncio.run(run())
    assert first == second
    assert _public_fact(first, "4w") == (1, "exact")
