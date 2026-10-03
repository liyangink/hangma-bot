"""路线事实的有界 JSON 编解码；只还原白名单值对象，不重算规则。

线格式 ``route-fact-codec/1`` 冻结每类字段名单。所有字段都保存，包括
不参与数据类相等比较的字段；顺序、None、空元组和枚举类型不互换。
标签只选择本文件已导入的公共事实类型，不允许按输入导入或加载对象。
"""
from __future__ import annotations

from dataclasses import fields
from enum import Enum
import math
from types import UnionType
from typing import Tuple, Union, get_args, get_origin, get_type_hints

from hangma_bot.hangma.interface import (
    PublicSuccessorDrawEdge, PublicSuccessorEnvelope, PublicSuccessorEnvelopeKind,
    PublicSuccessorLeaf, RuleIssue, Settlement, UsefulTileFact, ValueConditions,
)
from hangma_bot.hangma.progression import CatchPlayState, HandResult
from hangma_bot.hangma.public_tile_counts import (
    ConditionalTileCounts, PublicClaimEvidence, PublicTileCounts, PublicTileView,
)
from hangma_bot.hangma.route_frontier import (
    ConditionalWin, RouteDrawEdge, RouteFrontierDraft, RouteFrontierRoot, RouteGapKind,
)
from hangma_bot.hangma.route_transition import (
    ConditionalBranch, ConditionalIdentity, ConditionalPhase, ConditionalRoot,
    ConditionalRouteState,
)
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.observation import PublicDiscard, PublicEvent, PublicMeld


ROUTE_FACT_CODEC_VERSION = "route-fact-codec/1"
MAX_ROUTE_FACT_DEPTH = 32
MAX_ROUTE_FACT_SEQUENCE_ITEMS = 16_384
MAX_ROUTE_FACT_VALUES = 2_000_000
MAX_ROUTE_FACT_STRING_BYTES = 32_768
MAX_ROUTE_FACT_TOTAL_STRING_BYTES = 16 * 1024 * 1024
MAX_ROUTE_FACT_INTEGER_BITS = 128  # 公开前沿的34×3位容量打包整数也完整保留

# 字段显式冻结，不能因生产数据类增加字段而悄悄扩大本版外部读取能力。
_DECLARED_FIELDS = {
    RouteFrontierDraft: "roots ruleset_version top_level_gap issues",
    RouteFrontierRoot: "action_key immediate_settlement draw_edges structure_complete qualification_complete gap_kind issues",
    RouteDrawEdge: "successor immediate_win",
    ConditionalWin: "conditions settlement",
    ConditionalRoot: "action_key branches settlement claim_state proposal_state pending_condition gap_kind gap_kinds issues",
    ConditionalBranch: "state followup_key followup_discard",
    ConditionalIdentity: "game_id round_no root_action_key path ruleset_version",
    ConditionalRouteState: (
        "concealed meld_count phase baotou chain_count chain_piao wall_remaining drawn_tile "
        "my_chi_count my_peng_codes catch_restricted last_draw_replacement unseen_capacities "
        "unseen_evidence root_public_view public_view catch_circle identity seat dealer_seat "
        "response_window response_trigger response_public_discard expected_draw_seat "
        "expected_discard_seat expected_replacement_draw other_draw_replacement terminal_result "
        "structural_only local_witness_only claim_awarded"
    ),
    PublicSuccessorDrawEdge: "draw_tile is_currently_useful restricted unrestricted",
    PublicSuccessorEnvelope: "kind hu_available legal_discard_count gang_leaves discard_frontier",
    PublicSuccessorLeaf: (
        "action_key action_type shanten_after standard_shanten_after seven_pairs_shanten_after "
        "useful_mask useful_remaining_packed useful_tile_count support_remaining "
        "replacement_draw_unknown requires_future_wall_gt20"
    ),
    UsefulTileFact: "code remaining_estimate",
    ValueConditions: "draw_kind pre_draw_hand meld_count chain_count chain_piao baotou",
    Settlement: "score_delta fan details",
    RuleIssue: "area reason",
    PublicTileView: "discards melds hand_counts remaining_tile_count public_history snapshot_seq consumed_seq claim_evidence",
    PublicClaimEvidence: "seat meld_index feeder_seat claimed_tile provenance retained_in_river",
    PublicTileCounts: "counts evidence",
    ConditionalTileCounts: "public unseen evidence",
    CatchPlayState: "active owner",
    HandResult: "winner_seat is_draw fan details score_delta",
    PublicMeld: "seat kind tiles from_seat",
    PublicEvent: (
        "seq kind seat tiles occurred_at_unix_sec detail_kind catch_play gang_replenish "
        "response_window result_draw result_fan result_details result_scores final_scores claimed_tile"
    ),
    PublicDiscard: "seat tile seq",
    Tile: "code",
}
_ENUM_TYPES = (ConditionalPhase, RouteGapKind, PublicSuccessorEnvelopeKind)
_REGISTERED_TYPES = {kind.__name__: kind for kind in (*_DECLARED_FIELDS, *_ENUM_TYPES)}
_ROOT_TYPES = dict(_REGISTERED_TYPES, ConditionalRoots=Tuple[ConditionalRoot, ...])
_SCHEMAS = {}
for _kind, _declared in _DECLARED_FIELDS.items():
    _names = tuple(_declared.split())
    if tuple(item.name for item in fields(_kind)) != _names:
        raise RuntimeError("路线事实字段变更必须显式升级 codec: " + _kind.__name__)
    _hints = get_type_hints(_kind)
    _SCHEMAS[_kind] = tuple((name, _hints[name]) for name in _names)

_FIXED_LENGTHS = {
    (ConditionalRouteState, "unseen_capacities"): 34,
    (ConditionalRouteState, "unseen_evidence"): 34,
    (PublicTileView, "discards"): 4,
    (PublicTileView, "melds"): 4,
    (PublicTileCounts, "counts"): 34,
    (PublicTileCounts, "evidence"): 34,
    (ConditionalTileCounts, "public"): 34,
    (ConditionalTileCounts, "unseen"): 34,
    (ConditionalTileCounts, "evidence"): 34,
}


def _fail(reason: str) -> None:
    raise ValueError("路线事实 JSON: " + reason)


def _wire_guard(value) -> None:
    """迭代预检原始 JSON，先挡住过深/过大/循环载荷再递归还原类型。"""
    pending = [(value, 0)]
    values = string_bytes = 0
    while pending:
        current, depth = pending.pop()
        values += 1
        if depth > MAX_ROUTE_FACT_DEPTH or values > MAX_ROUTE_FACT_VALUES:
            _fail("深度或总值数量超出上限")
        kind = type(current)
        if kind is str:
            try:
                length = len(current.encode("utf-8"))
            except UnicodeError:
                _fail("字符串不是有效 UTF-8")
            string_bytes += length
            if length > MAX_ROUTE_FACT_STRING_BYTES or string_bytes > MAX_ROUTE_FACT_TOTAL_STRING_BYTES:
                _fail("字符串长度超出上限")
        elif kind is int:
            if current.bit_length() > MAX_ROUTE_FACT_INTEGER_BITS:
                _fail("整数位数超出上限")
        elif kind is float:
            if not math.isfinite(current):
                _fail("禁止非有限数")
        elif current is None or kind is bool:
            continue
        elif kind is list:
            if len(current) > MAX_ROUTE_FACT_SEQUENCE_ITEMS:
                _fail("数组长度超出上限")
            pending.extend((item, depth + 1) for item in current)
        elif kind is dict:
            if len(current) > MAX_ROUTE_FACT_SEQUENCE_ITEMS or any(type(key) is not str for key in current):
                _fail("对象键类型或数量不合法")
            pending.extend((item, depth + 1) for pair in current.items() for item in pair)
        else:
            _fail("只允许 JSON 原始值")


def _mapping(value, required):
    if type(value) is not dict or set(value) != set(required):
        _fail("对象字段集合不匹配")
    return value


def _optional_kind(expected):
    origin = get_origin(expected)
    if origin in (Union, UnionType):
        kinds = get_args(expected)
        if len(kinds) == 2 and type(None) in kinds:
            return next(kind for kind in kinds if kind is not type(None))
        _fail("本版不支持该联合类型")
    return None


def _fixed_length(kind, name, value):
    expected = _FIXED_LENGTHS.get((kind, name))
    if value is not None and expected is not None and len(value) != expected:
        _fail(kind.__name__ + "." + name + " 固定长度不匹配")
    if value is not None and expected == 34:
        if name in ("evidence", "unseen_evidence"):
            if any(item not in ("exact", "conservative", "unknown") for item in value):
                _fail("公开计数证据取值不合法")
        elif any(item is not None and not 0 <= item <= 4 for item in value):
            _fail("公开计数容量须为0—4或None")


def _convert(value, expected, *, decoding: bool, depth: int = 0, budget=None):
    if budget is None:
        budget = [0, 0]
    budget[0] += 1
    if budget[0] > MAX_ROUTE_FACT_VALUES:
        _fail("总值数量超出上限")
    if depth > MAX_ROUTE_FACT_DEPTH:
        _fail("深度超出上限")
    optional = _optional_kind(expected)
    if optional is not None:
        return None if value is None else _convert(value, optional, decoding=decoding, depth=depth, budget=budget)
    if expected in (str, int, bool, float):
        if type(value) is not expected:
            _fail("标量类型不匹配: " + expected.__name__)
        if expected is float and not math.isfinite(value):
            _fail("禁止非有限数")
        if expected is int and value.bit_length() > MAX_ROUTE_FACT_INTEGER_BITS:
            _fail("整数位数超出上限")
        if expected is str:
            try:
                length = len(value.encode("utf-8"))
            except UnicodeError:
                _fail("字符串不是有效 UTF-8")
            budget[1] += length
            if length > MAX_ROUTE_FACT_STRING_BYTES or budget[1] > MAX_ROUTE_FACT_TOTAL_STRING_BYTES:
                _fail("字符串长度超出上限")
        return value
    if get_origin(expected) is tuple:
        if type(value) is not (list if decoding else tuple):
            _fail("冻结元组/JSON 数组类型不匹配")
        if len(value) > MAX_ROUTE_FACT_SEQUENCE_ITEMS:
            _fail("数组长度超出上限")
        parts = get_args(expected)
        repeated = len(parts) == 2 and parts[1] is Ellipsis
        if not repeated and len(parts) != len(value):
            _fail("固定元组长度不匹配")
        result = [_convert(item, parts[0] if repeated else parts[index],
                           decoding=decoding, depth=depth + 1, budget=budget) for index, item in enumerate(value)]
        return tuple(result) if decoding else result
    if expected in _ENUM_TYPES:
        if decoding:
            data = _mapping(value, ("type", "value"))
            if data["type"] != expected.__name__ or type(data["value"]) is not str:
                _fail("枚举标签或值类型不匹配")
            try:
                return expected(data["value"])
            except ValueError:
                _fail("未知枚举值")
        if type(value) is not expected:
            _fail("枚举类型不匹配")
        return {"type": expected.__name__, "value": value.value}
    if expected not in _SCHEMAS:
        _fail("类型不在静态白名单内")
    schema = _SCHEMAS[expected]
    if decoding:
        data = _mapping(value, ("type", "fields"))
        if data["type"] != expected.__name__:
            _fail("数据类标签不匹配")
        source = _mapping(data["fields"], (name for name, _ in schema))
    else:
        if type(value) is not expected:
            _fail("数据类类型不匹配: " + expected.__name__)
        source = {name: getattr(value, name) for name, _ in schema}
    converted = {}
    for name, hint in schema:
        converted[name] = _convert(source[name], hint, decoding=decoding, depth=depth + 1, budget=budget)
        _fixed_length(expected, name, converted[name])
    if decoding:
        try:
            return expected(**converted)
        except (ValueError, TypeError, KeyError, IndexError, AttributeError) as error:
            raise ValueError("路线事实 JSON: 值对象校验失败: " + expected.__name__) from error
    return {"type": expected.__name__, "fields": converted}


def route_fact_to_json(value) -> dict[str, object]:
    """编码一个白名单事实或 ConditionalRoot 元组；不支持任意对象。

    返回独立 JSON 容器并保留全部字段。类型不合法或超过本版固定容量时
    抛 ValueError；不读取文件、网络、时间或重新执行规则计算。
    """
    tag = "ConditionalRoots" if type(value) is tuple else type(value).__name__
    expected = _ROOT_TYPES.get(tag)
    if expected is None:
        _fail("根类型不在静态白名单内")
    result = {"codec_version": ROUTE_FACT_CODEC_VERSION, "root_type": tag,
              "value": _convert(value, expected, decoding=False)}
    _wire_guard(result)
    return result


def route_fact_from_json(payload):
    """只由固定标签还原公共事实；字段、类型或容量错误抛 ValueError。"""
    _wire_guard(payload)
    data = _mapping(payload, ("codec_version", "root_type", "value"))
    if type(data["codec_version"]) is not str or data["codec_version"] != ROUTE_FACT_CODEC_VERSION:
        _fail("版本不兼容")
    if type(data["root_type"]) is not str or data["root_type"] not in _ROOT_TYPES:
        _fail("未知根类型标签")
    return _convert(data["value"], _ROOT_TYPES[data["root_type"]], decoding=True)


def route_frontier_to_json(value: RouteFrontierDraft) -> dict[str, object]:
    """保存完整前沿，拒绝把其他白名单事实塞进前沿字段。"""
    if type(value) is not RouteFrontierDraft:
        _fail("前沿类型不匹配")
    return route_fact_to_json(value)


def route_frontier_from_json(payload) -> RouteFrontierDraft:
    """读取前沿字段，保留缺口与条件支付，不补分析结果。"""
    value = route_fact_from_json(payload)
    if type(value) is not RouteFrontierDraft:
        _fail("前沿根标签不匹配")
    return value


def conditional_roots_to_json(value: Tuple[ConditionalRoot, ...]) -> dict[str, object]:
    """保存完整条件根元组；已请求空元组与未请求 None 有不同含义。"""
    if type(value) is not tuple:
        _fail("条件根须为冻结元组")
    return route_fact_to_json(value)


def conditional_roots_from_json(payload) -> Tuple[ConditionalRoot, ...]:
    """读取全部条件根，不丢弃嵌套公开事实和终局状态。"""
    value = route_fact_from_json(payload)
    if type(value) is not tuple or any(type(item) is not ConditionalRoot for item in value):
        _fail("条件根标签不匹配")
    return value
