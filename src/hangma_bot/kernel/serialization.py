"""kernel 值对象的稳定 JSON 序列化。

本模块为 kernel 值对象提供长期稳定的 JSON 转换，供审计记录、牌谱
回放与测试使用。约定：

- 所有 ``*_to_json`` 的输出只包含标准库 ``json`` 可直接序列化的值
  （`None`/`bool`/`int`/`float`/`str`/列表/字典），不把
  ``dataclasses.asdict()`` 当长期格式；
- 每个顶层负载都带 ``schema_version``，等于 `KERNEL_VALUE_SCHEMA_VERSION`；
  破坏性变更必须递增该常量并同步契约测试与文档，新增可选键不算破坏；
- ``*_from_json`` 对必填键缺失或类型不符抛 `ValueError`，对未知新增键
  前向兼容（忽略）；座位范围、向量长度、牌值域、正数配置等语义校验
  由值对象构造函数完成，本模块不重复实现；
- 牌值序列化为 `Tile.code` 字符串；元组一律输出 JSON 数组；
- 本模块是纯函数：不读写文件、不访问网络和时钟。
"""

from __future__ import annotations

from collections.abc import Mapping as MappingABC
from typing import Dict, List, Mapping, Optional, Tuple, Union

from .actions import (
    Action,
    Chi,
    Discard,
    Gang,
    GangKind,
    Hu,
    Pass,
    Peng,
    Tile,
    WindowKey,
    WindowPhase,
)
from .config import RuleConfig, TimingConfig, TournamentConfig
from .observation import (
    CompetitionContext,
    PlayerObservation,
    PublicDiscard,
    PublicEvent,
    PublicMeld,
    RankingEntry,
    RulePublicState,
)

# kernel 值对象线格式版本；仅在做破坏性格式变更（删键、改含义、改单位）时递增。
KERNEL_VALUE_SCHEMA_VERSION = 1

# JSON 兼容值的类型别名（仅用于注解与文档）；`*_to_json` 的实际输出
# 使用 list/dict 字面量，因此联合必须同时包含 Tuple/List 与 Mapping/Dict。
JSONValue = Union[
    None,
    bool,
    int,
    float,
    str,
    Tuple["JSONValue", ...],
    List["JSONValue"],
    Mapping[str, "JSONValue"],
]


def _require_mapping(payload: object, type_name: str) -> Mapping[str, object]:
    """负载必须是 JSON 对象（字典），否则属于格式错误。"""
    if not isinstance(payload, MappingABC):
        raise ValueError("{0} 负载必须是 JSON 对象，得到 {1!r}".format(type_name, payload))
    return payload


def _get(payload: Mapping[str, object], key: str, type_name: str) -> object:
    """读取必填键；缺失说明负载不是本模块生成的格式。"""
    if key not in payload:
        raise ValueError("{0} 负载缺少必填键 {1!r}".format(type_name, key))
    return payload[key]


def _as_str(value: object, type_name: str, key: str) -> str:
    if not isinstance(value, str):
        raise ValueError("{0}.{1} 必须是字符串，得到 {2!r}".format(type_name, key, value))
    return value


def _as_int(value: object, type_name: str, key: str) -> int:
    # `bool` 是 `int` 子类，JSON 里 true/false 不是合法整数。
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("{0}.{1} 必须是整数，得到 {2!r}".format(type_name, key, value))
    return value


def _as_number(value: object, type_name: str, key: str) -> Union[int, float]:
    """秒数等数值字段；接受整数或浮点数，有限性由构造函数校验。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("{0}.{1} 必须是数值，得到 {2!r}".format(type_name, key, value))
    return value


def _as_bool(value: object, type_name: str, key: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError("{0}.{1} 必须是布尔值，得到 {2!r}".format(type_name, key, value))
    return value


def _as_list(value: object, type_name: str, key: str) -> List[object]:
    if not isinstance(value, list):
        raise ValueError("{0}.{1} 必须是数组，得到 {2!r}".format(type_name, key, value))
    return value


def _check_schema_version(payload: Mapping[str, object], type_name: str) -> None:
    """顶层负载必须声明且匹配当前线格式版本。"""
    version = _as_int(_get(payload, "schema_version", type_name), type_name, "schema_version")
    if version != KERNEL_VALUE_SCHEMA_VERSION:
        raise ValueError(
            "{0} 负载 schema_version={1!r} 与当前版本 {2} 不匹配".format(
                type_name, version, KERNEL_VALUE_SCHEMA_VERSION
            )
        )


def _decode_tile(value: object, type_name: str, key: str) -> Tile:
    """牌值编码为 `Tile.code` 字符串；值域校验由 `Tile` 构造函数完成。"""
    return Tile(_as_str(value, type_name, key))


def _decode_tiles(value: object, type_name: str, key: str) -> Tuple[Tile, ...]:
    return tuple(
        _decode_tile(item, type_name, key) for item in _as_list(value, type_name, key)
    )


def _decode_optional_tile(
    value: object, type_name: str, key: str
) -> Optional[Tile]:
    if value is None:
        return None
    return _decode_tile(value, type_name, key)


def _decode_optional_int(value: object, type_name: str, key: str) -> Optional[int]:
    if value is None:
        return None
    return _as_int(value, type_name, key)


# ---------------------------------------------------------------------------
# 动作与窗口键
# ---------------------------------------------------------------------------


def action_to_json(action: Action) -> Dict[str, JSONValue]:
    """把封闭动作联合中的一个动作转为可审计的 JSON 对象。

    输出以 ``kind`` 判别动作种类，杠用 ``gang_kind`` 区分暗/明/补；
    与 `action_key()` 一样不包含任何 Token 或随机成分。
    """
    if isinstance(action, Discard):
        body: Dict[str, JSONValue] = {"kind": "discard", "tile": action.tile.code}
    elif isinstance(action, Chi):
        body = {"kind": "chi", "tiles": [tile.code for tile in action.tiles]}
    elif isinstance(action, Peng):
        body = {"kind": "peng", "tile": action.tile.code}
    elif isinstance(action, Gang):
        body = {
            "kind": "gang",
            "gang_kind": action.kind.value,
            "tile": action.tile.code,
        }
    elif isinstance(action, Hu):
        body = {"kind": "hu"}
    elif isinstance(action, Pass):
        body = {"kind": "pass"}
    else:
        raise ValueError("未知内部动作类型: {0!r}".format(type(action)))
    body["schema_version"] = KERNEL_VALUE_SCHEMA_VERSION
    return body


def action_from_json(payload: object) -> Action:
    """把 JSON 对象还原为封闭动作联合成员；格式错误抛 `ValueError`。"""
    type_name = "action"
    data = _require_mapping(payload, type_name)
    _check_schema_version(data, type_name)
    kind = _as_str(_get(data, "kind", type_name), type_name, "kind")
    if kind == "discard":
        return Discard(_decode_tile(_get(data, "tile", type_name), type_name, "tile"))
    if kind == "chi":
        tiles = _decode_tiles(_get(data, "tiles", type_name), type_name, "tiles")
        return Chi(tiles)  # 张数校验由 Chi 构造函数完成
    if kind == "peng":
        return Peng(_decode_tile(_get(data, "tile", type_name), type_name, "tile"))
    if kind == "gang":
        gang_kind = _as_str(_get(data, "gang_kind", type_name), type_name, "gang_kind")
        try:
            mapped = GangKind(gang_kind)
        except ValueError as error:
            raise ValueError(
                "action.gang_kind 必须是 {0} 之一，得到 {1!r}".format(
                    [member.value for member in GangKind], gang_kind
                )
            ) from error
        return Gang(_decode_tile(_get(data, "tile", type_name), type_name, "tile"), mapped)
    if kind == "hu":
        return Hu()
    if kind == "pass":
        return Pass()
    raise ValueError("action.kind 未知: {0!r}".format(kind))


def window_key_to_json(window_key: WindowKey) -> Dict[str, JSONValue]:
    """把动作窗口键转为 JSON 对象；``phase`` 使用规范枚举值。"""
    return {
        "schema_version": KERNEL_VALUE_SCHEMA_VERSION,
        "game_id": window_key.game_id,
        "round_no": window_key.round_no,
        "trigger_seq": window_key.trigger_seq,
        "phase": window_key.phase.value,
        "seat": window_key.seat,
    }


def window_key_from_json(payload: object) -> WindowKey:
    """把 JSON 对象还原为动作窗口键；座位范围由构造函数校验。"""
    type_name = "window_key"
    data = _require_mapping(payload, type_name)
    _check_schema_version(data, type_name)
    phase_value = _as_str(_get(data, "phase", type_name), type_name, "phase")
    try:
        phase = WindowPhase(phase_value)
    except ValueError as error:
        raise ValueError(
            "window_key.phase 必须是 {0} 之一，得到 {1!r}".format(
                [member.value for member in WindowPhase], phase_value
            )
        ) from error
    return WindowKey(
        game_id=_as_str(_get(data, "game_id", type_name), type_name, "game_id"),
        round_no=_as_int(_get(data, "round_no", type_name), type_name, "round_no"),
        trigger_seq=_as_int(_get(data, "trigger_seq", type_name), type_name, "trigger_seq"),
        phase=phase,
        seat=_as_int(_get(data, "seat", type_name), type_name, "seat"),
    )


# ---------------------------------------------------------------------------
# 玩家观察与已观察赛事上下文
# ---------------------------------------------------------------------------


def _meld_to_json(meld: PublicMeld) -> Dict[str, JSONValue]:
    """单条公开副露的嵌套负载（不带独立 schema_version）。"""
    return {
        "seat": meld.seat,
        "kind": meld.kind,
        "tiles": [tile.code for tile in meld.tiles],
        "from_seat": meld.from_seat,
    }


def _meld_from_json(payload: object) -> PublicMeld:
    type_name = "meld"
    data = _require_mapping(payload, type_name)
    from_seat_raw = _get(data, "from_seat", type_name)
    return PublicMeld(
        seat=_as_int(_get(data, "seat", type_name), type_name, "seat"),
        kind=_as_str(_get(data, "kind", type_name), type_name, "kind"),
        tiles=_decode_tiles(_get(data, "tiles", type_name), type_name, "tiles"),
        from_seat=(
            None
            if from_seat_raw is None
            else _as_int(from_seat_raw, type_name, "from_seat")
        ),
    )


def public_event_to_json(event: PublicEvent) -> Dict[str, JSONValue]:
    """编码本座位可见事件，供无策略窗口的单局收尾审计使用；不扩大信息权限。"""
    return _event_to_json(event)


def _event_to_json(event: PublicEvent) -> Dict[str, JSONValue]:
    """单条公开事件的嵌套负载；`occurred_at_unix_sec` 为墙上时钟 Unix 秒。"""
    return {
        "seq": event.seq,
        "kind": event.kind,
        "seat": event.seat,
        "tiles": [tile.code for tile in event.tiles],
        "occurred_at_unix_sec": event.occurred_at_unix_sec,
        "detail_kind": event.detail_kind,
        "catch_play": event.catch_play,
        "gang_replenish": event.gang_replenish,
        "response_window": event.response_window,
        "result_draw": event.result_draw,
        "result_fan": event.result_fan,
        "result_details": None if event.result_details is None else list(event.result_details),
        "result_scores": None if event.result_scores is None else list(event.result_scores),
        "final_scores": None if event.final_scores is None else list(event.final_scores),
        "claimed_tile": None if event.claimed_tile is None else event.claimed_tile.code,
    }


def _event_from_json(payload: object) -> PublicEvent:
    type_name = "event"
    data = _require_mapping(payload, type_name)
    seat_raw = _get(data, "seat", type_name)
    occurred_raw = _get(data, "occurred_at_unix_sec", type_name)
    return PublicEvent(
        seq=_as_int(_get(data, "seq", type_name), type_name, "seq"),
        kind=_as_str(_get(data, "kind", type_name), type_name, "kind"),
        seat=None if seat_raw is None else _as_int(seat_raw, type_name, "seat"),
        tiles=_decode_tiles(_get(data, "tiles", type_name), type_name, "tiles"),
        occurred_at_unix_sec=(
            None
            if occurred_raw is None
            else _as_int(occurred_raw, type_name, "occurred_at_unix_sec")
        ),
        detail_kind=(None if data.get("detail_kind") is None else
                     _as_str(data["detail_kind"], type_name, "detail_kind")),
        catch_play=None if data.get("catch_play") is None else _as_bool(data["catch_play"], type_name, "catch_play"),
        gang_replenish=None if data.get("gang_replenish") is None else _as_bool(data["gang_replenish"], type_name, "gang_replenish"),
        response_window=None if data.get("response_window") is None else _as_str(data["response_window"], type_name, "response_window"),
        result_draw=None if data.get("result_draw") is None else _as_bool(data["result_draw"], type_name, "result_draw"),
        result_fan=None if data.get("result_fan") is None else _as_int(data["result_fan"], type_name, "result_fan"),
        result_details=None if data.get("result_details") is None else tuple(_as_str(x, type_name, "result_details") for x in _as_list(data["result_details"], type_name, "result_details")),
        result_scores=None if data.get("result_scores") is None else tuple(_as_int(x, type_name, "result_scores") for x in _as_list(data["result_scores"], type_name, "result_scores")),
        final_scores=None if data.get("final_scores") is None else tuple(_as_int(x, type_name, "final_scores") for x in _as_list(data["final_scores"], type_name, "final_scores")),
        claimed_tile=_decode_optional_tile(data.get("claimed_tile"), type_name, "claimed_tile"),
    )


def _public_discard_to_json(discard: PublicDiscard) -> Dict[str, JSONValue]:
    """最近一张公开弃牌的嵌套负载。"""
    return {"seat": discard.seat, "tile": discard.tile.code, "seq": discard.seq}


def _public_discard_from_json(payload: object) -> PublicDiscard:
    type_name = "public_discard"
    data = _require_mapping(payload, type_name)
    return PublicDiscard(
        seat=_as_int(_get(data, "seat", type_name), type_name, "seat"),
        tile=_decode_tile(_get(data, "tile", type_name), type_name, "tile"),
        seq=_as_int(_get(data, "seq", type_name), type_name, "seq"),
    )


def _rule_state_to_json(state: RulePublicState) -> Dict[str, JSONValue]:
    """本人可见规则状态（官方 `god`）的嵌套负载。"""
    payload = {
        "wealth_god": state.wealth_god.code,
        "baotou": state.baotou,
        "chain_count": state.chain_count,
        "catch_play": state.catch_play,
    }
    if state.catch_play_owner_seat is not None:
        payload["catch_play_owner_seat"] = state.catch_play_owner_seat
    return payload


def _rule_state_from_json(payload: object) -> RulePublicState:
    type_name = "rule_state"
    data = _require_mapping(payload, type_name)
    return RulePublicState(
        wealth_god=_decode_tile(_get(data, "wealth_god", type_name), type_name, "wealth_god"),
        baotou=_as_bool(_get(data, "baotou", type_name), type_name, "baotou"),
        chain_count=_as_int(_get(data, "chain_count", type_name), type_name, "chain_count"),
        catch_play=_as_bool(_get(data, "catch_play", type_name), type_name, "catch_play"),
        catch_play_owner_seat=(None if data.get("catch_play_owner_seat") is None else
                              _as_int(data["catch_play_owner_seat"], type_name, "catch_play_owner_seat")),
    )


def observation_to_json(observation: PlayerObservation) -> Dict[str, JSONValue]:
    """把玩家观察转为 JSON 对象；输出与输入信息权限一致，仅含可见事实。"""
    return {
        "schema_version": KERNEL_VALUE_SCHEMA_VERSION,
        "game_id": observation.game_id,
        "seat": observation.seat,
        "round_no": observation.round_no,
        "snapshot_seq": observation.snapshot_seq,
        "consumed_seq": observation.consumed_seq,
        "history_complete": observation.history_complete,
        "chain_piao": observation.chain_piao,
        "gang_draw": observation.gang_draw,
        "observation_issues": list(observation.observation_issues),
        "phase": observation.phase,
        "dealer_seat": observation.dealer_seat,
        "turn_seat": observation.turn_seat,
        "responding_seats": list(observation.responding_seats),
        # 手牌保持官方顺序输出，不排序不去重；紧急弃牌依赖最右一张。
        "my_hand": [tile.code for tile in observation.my_hand],
        "drawn_tile": (
            None if observation.drawn_tile is None else observation.drawn_tile.code
        ),
        "discards": [
            [tile.code for tile in river] for river in observation.discards
        ],
        "melds": [
            [_meld_to_json(meld) for meld in seat_melds] for seat_melds in observation.melds
        ],
        "hand_counts": list(observation.hand_counts),
        "last_discard": (
            None
            if observation.last_discard is None
            else _public_discard_to_json(observation.last_discard)
        ),
        "remaining_tile_count": observation.remaining_tile_count,
        "scores": list(observation.scores),
        "rule_state": _rule_state_to_json(observation.rule_state),
        "public_history": [
            _event_to_json(event) for event in observation.public_history
        ],
    }


def observation_from_json(payload: object) -> PlayerObservation:
    """把 JSON 对象还原为玩家观察；语义校验由构造函数完成。"""
    type_name = "player_observation"
    data = _require_mapping(payload, type_name)
    _check_schema_version(data, type_name)
    last_discard_raw = _get(data, "last_discard", type_name)
    return PlayerObservation(
        game_id=_as_str(_get(data, "game_id", type_name), type_name, "game_id"),
        seat=_as_int(_get(data, "seat", type_name), type_name, "seat"),
        round_no=_as_int(_get(data, "round_no", type_name), type_name, "round_no"),
        snapshot_seq=_as_int(_get(data, "snapshot_seq", type_name), type_name, "snapshot_seq"),
        consumed_seq=_decode_optional_int(data.get("consumed_seq"), type_name, "consumed_seq"),
        history_complete=_as_bool(data.get("history_complete", False), type_name, "history_complete"),
        chain_piao=_decode_optional_int(data.get("chain_piao"), type_name, "chain_piao"),
        gang_draw=(None if data.get("gang_draw") is None else
                   _as_bool(data["gang_draw"], type_name, "gang_draw")),
        observation_issues=tuple(_as_str(item, type_name, "observation_issues") for item in
                                _as_list(data.get("observation_issues", []), type_name, "observation_issues")),
        phase=_as_str(_get(data, "phase", type_name), type_name, "phase"),
        dealer_seat=_as_int(_get(data, "dealer_seat", type_name), type_name, "dealer_seat"),
        turn_seat=_as_int(_get(data, "turn_seat", type_name), type_name, "turn_seat"),
        responding_seats=tuple(
            _as_int(item, type_name, "responding_seats")
            for item in _as_list(
                _get(data, "responding_seats", type_name), type_name, "responding_seats"
            )
        ),
        my_hand=_decode_tiles(_get(data, "my_hand", type_name), type_name, "my_hand"),
        drawn_tile=_decode_optional_tile(
            _get(data, "drawn_tile", type_name), type_name, "drawn_tile"
        ),
        discards=tuple(
            _decode_tiles(row, type_name, "discards")
            for row in _as_list(_get(data, "discards", type_name), type_name, "discards")
        ),
        melds=tuple(
            tuple(
                _meld_from_json(meld)
                for meld in _as_list(row, type_name, "melds 行")
            )
            for row in _as_list(_get(data, "melds", type_name), type_name, "melds")
        ),
        hand_counts=tuple(
            _as_int(item, type_name, "hand_counts")
            for item in _as_list(
                _get(data, "hand_counts", type_name), type_name, "hand_counts"
            )
        ),
        last_discard=(
            None
            if last_discard_raw is None
            else _public_discard_from_json(last_discard_raw)
        ),
        remaining_tile_count=_decode_optional_int(
            _get(data, "remaining_tile_count", type_name),
            type_name,
            "remaining_tile_count",
        ),
        scores=tuple(
            _as_int(item, type_name, "scores")
            for item in _as_list(_get(data, "scores", type_name), type_name, "scores")
        ),
        rule_state=_rule_state_from_json(_get(data, "rule_state", type_name)),
        public_history=tuple(
            _event_from_json(event)
            for event in _as_list(
                _get(data, "public_history", type_name), type_name, "public_history"
            )
        ),
    )


def _ranking_entry_to_json(entry: RankingEntry) -> Dict[str, JSONValue]:
    """单条权威排名的嵌套负载；三个排序键原样分开保存。"""
    return {
        "participant_id": entry.participant_id,
        "total_score": entry.total_score,
        "place_points": entry.place_points,
        "god_count": entry.god_count,
        "games_played": entry.games_played,
        "rank": entry.rank,
    }


def _ranking_entry_from_json(payload: object) -> RankingEntry:
    type_name = "ranking_entry"
    data = _require_mapping(payload, type_name)
    return RankingEntry(
        participant_id=_as_str(
            _get(data, "participant_id", type_name), type_name, "participant_id"
        ),
        total_score=_as_int(_get(data, "total_score", type_name), type_name, "total_score"),
        place_points=_as_int(
            _get(data, "place_points", type_name), type_name, "place_points"
        ),
        god_count=_as_int(_get(data, "god_count", type_name), type_name, "god_count"),
        games_played=_as_int(
            _get(data, "games_played", type_name), type_name, "games_played"
        ),
        rank=_as_int(_get(data, "rank", type_name), type_name, "rank"),
    )


def competition_to_json(context: CompetitionContext) -> Dict[str, JSONValue]:
    """把已观察赛事上下文转为 JSON 对象；只含平台已确认事实。"""
    return {
        "schema_version": KERNEL_VALUE_SCHEMA_VERSION,
        "tournament_id": context.tournament_id,
        "stage_no": context.stage_no,
        "stage_role": context.stage_role,
        "stage_total": context.stage_total,
        "participant_rank": context.participant_rank,
        "ranking": [_ranking_entry_to_json(entry) for entry in context.ranking],
        "observed_at_unix_ms": context.observed_at_unix_ms,
    }


def competition_from_json(payload: object) -> CompetitionContext:
    """把 JSON 对象还原为已观察赛事上下文。"""
    type_name = "competition_context"
    data = _require_mapping(payload, type_name)
    _check_schema_version(data, type_name)
    return CompetitionContext(
        tournament_id=_as_str(
            _get(data, "tournament_id", type_name), type_name, "tournament_id"
        ),
        stage_no=_decode_optional_int(_get(data, "stage_no", type_name), type_name, "stage_no"),
        stage_role=(
            None
            if _get(data, "stage_role", type_name) is None
            else _as_str(_get(data, "stage_role", type_name), type_name, "stage_role")
        ),
        stage_total=_decode_optional_int(
            _get(data, "stage_total", type_name), type_name, "stage_total"
        ),
        participant_rank=_decode_optional_int(
            _get(data, "participant_rank", type_name), type_name, "participant_rank"
        ),
        ranking=tuple(
            _ranking_entry_from_json(entry)
            for entry in _as_list(_get(data, "ranking", type_name), type_name, "ranking")
        ),
        observed_at_unix_ms=_as_int(
            _get(data, "observed_at_unix_ms", type_name),
            type_name,
            "observed_at_unix_ms",
        ),
    )


# ---------------------------------------------------------------------------
# 运行配置
# ---------------------------------------------------------------------------


def tournament_config_to_json(config: TournamentConfig) -> Dict[str, JSONValue]:
    """把赛事运行配置转为 JSON 对象；秒数字段保持数值类型。"""
    return {
        "schema_version": KERNEL_VALUE_SCHEMA_VERSION,
        "max_games": config.max_games,
        "rounds_per_game": config.rounds_per_game,
        "rules": {
            "ruleset_version": config.rules.ruleset_version,
            "base_score": config.rules.base_score,
            "you_cai_bi_kao": config.rules.you_cai_bi_kao,
        },
        "timing": {
            "peng_timeout_sec": config.timing.peng_timeout_sec,
            "chi_timeout_sec": config.timing.chi_timeout_sec,
            "discard_timeout_sec": config.timing.discard_timeout_sec,
        },
    }


def tournament_config_from_json(payload: object) -> TournamentConfig:
    """把 JSON 对象还原为赛事运行配置；正数与秒数校验由构造函数完成。"""
    type_name = "tournament_config"
    data = _require_mapping(payload, type_name)
    _check_schema_version(data, type_name)
    rules_data = _require_mapping(_get(data, "rules", type_name), type_name + ".rules")
    timing_data = _require_mapping(_get(data, "timing", type_name), type_name + ".timing")
    return TournamentConfig(
        max_games=_as_int(_get(data, "max_games", type_name), type_name, "max_games"),
        rounds_per_game=_as_int(
            _get(data, "rounds_per_game", type_name), type_name, "rounds_per_game"
        ),
        rules=RuleConfig(
            ruleset_version=_as_str(
                _get(rules_data, "ruleset_version", type_name + ".rules"),
                type_name + ".rules",
                "ruleset_version",
            ),
            base_score=_as_int(
                _get(rules_data, "base_score", type_name + ".rules"),
                type_name + ".rules",
                "base_score",
            ),
            you_cai_bi_kao=_as_bool(
                _get(rules_data, "you_cai_bi_kao", type_name + ".rules"),
                type_name + ".rules",
                "you_cai_bi_kao",
            ),
        ),
        timing=TimingConfig(
            peng_timeout_sec=_as_number(
                _get(timing_data, "peng_timeout_sec", type_name + ".timing"),
                type_name + ".timing",
                "peng_timeout_sec",
            ),
            chi_timeout_sec=_as_number(
                _get(timing_data, "chi_timeout_sec", type_name + ".timing"),
                type_name + ".timing",
                "chi_timeout_sec",
            ),
            discard_timeout_sec=_as_number(
                _get(timing_data, "discard_timeout_sec", type_name + ".timing"),
                type_name + ".timing",
                "discard_timeout_sec",
            ),
        ),
    )
