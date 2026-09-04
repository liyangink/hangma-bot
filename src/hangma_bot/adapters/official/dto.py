"""官方 v8 JSON 报文解析。

解析原则（依据 doc/official-platform-api-v2.md，指南 v8，抓取 2026-09-03）：

- 已确认必需字段缺失时抛 DtoError（默认可用 seq=0 快照重建修复）；
- 未知新增字段一律忽略并保留（v8 的 Description 属于此类兼容新增）；
- 牌码使用官方 v8 牌码表（1w-9w、1b-9b、1t-9t、东南西北中发白），不自行翻译；
- 错误体形状官方未文档化，extract_error_code 对 JSON 与纯文本都宽容。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence, Tuple

from hangma_bot.kernel.actions import CANONICAL_TILE_CODES

from .errors import DtoError

KNOWN_GUIDE_VERSION = 8  # 已审查指南版本；更高版本需检查未知 breaking 变更


def _require_mapping(doc: Any, what: str) -> Mapping[str, Any]:
    if not isinstance(doc, Mapping):
        raise DtoError('{} 应为 JSON 对象'.format(what))
    return doc


def _require_str(value: Any, what: str) -> str:
    if not isinstance(value, str):
        raise DtoError('{} 应为字符串'.format(what))
    return value


def _require_int(value: Any, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise DtoError('{} 应为整数'.format(what))
    return value


def _require_bool(value: Any, what: str) -> bool:
    if not isinstance(value, bool):
        raise DtoError('{} 应为布尔'.format(what))
    return value


def _tile_list(value: Any, what: str) -> Tuple[str, ...]:
    """把官方牌码数组转成元组；空与缺失都合法（不同座位牌河可为空）。

    牌码按官方 v8 牌码表校验（与 kernel CANONICAL_TILE_CODES 同源）；
    非法牌码抛可恢复 DtoError，交由 seq=0 全量重建或分类故障兜底，
    避免投影层 ValueError 裸逃逸。
    """

    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise DtoError('{} 应为牌码数组'.format(what))
    for item in value:
        if not isinstance(item, str):
            raise DtoError('{} 内应为字符串牌码'.format(what))
        if item not in CANONICAL_TILE_CODES:
            raise DtoError('{} 含非法牌码 {!r}'.format(what, item))
    return tuple(value)


def _require_seat(value: Any, what: str, *, allow_negative: bool = False) -> int:
    """座位下标校验：0-3；观赛/终局哨兵允许 -1。布尔一律拒绝。"""

    if isinstance(value, bool) or not isinstance(value, int):
        raise DtoError('{} 应为座位整数'.format(what))
    if value == -1 and allow_negative:
        return value
    if not 0 <= value <= 3:
        raise DtoError('{} 越界: {}'.format(what, value))
    return value


@dataclass(frozen=True)
class ParsedGuideVersion:
    """GET /portal/api/guide/version 的解析结果。"""

    version: int
    updated_at: str
    has_unknown_breaking_change: bool  # 存在 version>KNOWN 且 type=breaking 的变更
    changes: Tuple[Mapping[str, Any], ...]  # 原样保留，供审计与回放解释行为差异


def parse_guide_version(doc: Any) -> ParsedGuideVersion:
    """解析指南版本；未知 breaking 判定依据官方建议的启动策略（API 文档 §3.1）。"""

    body = _require_mapping(doc, "guide/version")
    version = _require_int(body.get("version"), "guide.version")
    updated_at = _require_str(body.get("updated_at"), "guide.updated_at")
    raw_changes = body.get("changes") or []
    if not isinstance(raw_changes, Sequence):
        raise DtoError("guide.changes 应为数组")
    changes: Tuple[Mapping[str, Any], ...] = tuple(
        item for item in raw_changes if isinstance(item, Mapping)
    )
    has_breaking = any(
        isinstance(item.get("type"), str)
        and item.get("type") == "breaking"
        and (
            # version 畸形（非整数）的 breaking 条目按保守未知处理，不因数据
            # 质量问题放行未审查变更
            not isinstance(item.get("version"), int)
            or isinstance(item.get("version"), bool)
            or item["version"] > KNOWN_GUIDE_VERSION
        )
        for item in changes
    )
    return ParsedGuideVersion(
        version=version,
        updated_at=updated_at,
        has_unknown_breaking_change=has_breaking,
        changes=changes,
    )


@dataclass(frozen=True)
class ParsedMe:
    """GET /api/me 的解析结果。"""

    user_id: str  # 官方身份标识；作为脱敏 participant_id 使用，不是 Token
    tournament_id: str  # 报名 Token 绑定的锦标赛；全局 Token 为空字符串
    active_games: Tuple[str, ...]  # 当前进行中的官方场次，顺序保持官方返回


def parse_me(doc: Any) -> ParsedMe:
    body = _require_mapping(doc, "/api/me")
    raw_games = body.get("active_games") or []
    if not isinstance(raw_games, Sequence):
        raise DtoError("active_games 应为数组")
    game_ids = []
    for item in raw_games:
        entry = _require_mapping(item, "active_games 项")
        game_ids.append(_require_str(entry.get("game_id"), "active_games.game_id"))
    return ParsedMe(
        user_id=_require_str(body.get("user_id"), "user_id"),
        tournament_id=str(body.get("tournament_id") or ""),
        active_games=tuple(game_ids),
    )


@dataclass(frozen=True)
class ParsedRulesConfig:
    """GET /api/tournaments/*/rules 的 config 解析结果；字段名为官方原样。"""

    tournament_id: str
    status: str
    max_games: int  # 官方 M
    rounds_per_game: int  # 官方 Rounds，每场包含的单局数
    base_score: int  # 官方 BaseScore
    you_cai_bi_kao: bool  # 官方 YouCaiBiKao
    peng_timeout_sec: float
    chi_timeout_sec: float
    discard_timeout_sec: float
    description: Optional[str]  # v8 兼容新增；仅展示记录，不进入策略输入


def parse_rules_config(doc: Any) -> ParsedRulesConfig:
    body = _require_mapping(doc, "rules")
    config = _require_mapping(body.get("config"), "rules.config")
    description = config.get("Description")
    if description is not None and not isinstance(description, str):
        raise DtoError("Description 应为字符串")
    return ParsedRulesConfig(
        tournament_id=_require_str(body.get("tournament_id"), "rules.tournament_id"),
        status=_require_str(body.get("status"), "rules.status"),
        max_games=_require_int(config.get("M"), "config.M"),
        rounds_per_game=_require_int(config.get("Rounds"), "config.Rounds"),
        base_score=_require_int(config.get("BaseScore"), "config.BaseScore"),
        you_cai_bi_kao=_require_bool(config.get("YouCaiBiKao"), "config.YouCaiBiKao"),
        peng_timeout_sec=float(_require_int(config.get("PengTimeoutSec"), "config.PengTimeoutSec")),
        chi_timeout_sec=float(_require_int(config.get("ChiTimeoutSec"), "config.ChiTimeoutSec")),
        discard_timeout_sec=float(_require_int(config.get("DiscardTimeoutSec"), "config.DiscardTimeoutSec")),
        description=description,
    )


@dataclass(frozen=True)
class ParsedRankingEntry:
    """ranking 数组项；字段为官方 v7 排名字段。"""

    user_id: str
    total_score: int
    place_points: int
    god_count: int
    games_played: int
    rank: int


@dataclass(frozen=True)
class ParsedTournament:
    """GET /api/tournaments/{id} 的解析结果。"""

    status: str
    stage_no: Optional[int]
    stage_role: Optional[str]  # qualify 晋级轮 / final 决赛
    stage_total: Optional[int]
    stage_crashed: bool
    qualified: Optional[bool]
    qualify_role: Optional[str]  # finalist / backup；阶段 1 通常为空
    my_games: Tuple[str, ...]  # 跨阶段累计历史，决赛加赛会追加
    ranking: Tuple[ParsedRankingEntry, ...]
    voided: bool


def parse_tournament_detail(doc: Any) -> ParsedTournament:
    body = _require_mapping(doc, "tournament detail")
    stage_raw = body.get("stage")
    stage_no: Optional[int] = None
    stage_role: Optional[str] = None
    stage_total: Optional[int] = None
    if isinstance(stage_raw, Mapping):
        # 字段缺失/None 是协议允许（阶段 1 前）；存在但类型错是协议错误：
        # 静默置 None 会让 stage_open 携带坏 stage.no 时应用层永不 ready
        raw_no = stage_raw.get("no")
        if raw_no is not None:
            stage_no = _require_int(raw_no, "stage.no")
        raw_role = stage_raw.get("role")
        if raw_role is not None:
            stage_role = _require_str(raw_role, "stage.role")
        raw_total = stage_raw.get("total")
        if raw_total is not None:
            stage_total = _require_int(raw_total, "stage.total")
    elif stage_raw is not None:
        raise DtoError("stage 应为对象")
    qualified = body.get("qualified")
    if qualified is not None and not isinstance(qualified, bool):
        raise DtoError("qualified 应为布尔")
    qualify_role = body.get("qualify_role")
    if qualify_role is not None and not isinstance(qualify_role, str):
        raise DtoError("qualify_role 应为字符串")
    my_games_raw = body.get("my_games") or []
    if not isinstance(my_games_raw, Sequence):
        raise DtoError("my_games 应为数组")
    for item in my_games_raw:
        if not isinstance(item, str):
            raise DtoError("my_games 含非字符串项")
    ranking_raw = body.get("ranking") or []
    if not isinstance(ranking_raw, Sequence):
        raise DtoError("ranking 应为数组")
    for item in ranking_raw:
        if not isinstance(item, Mapping):
            raise DtoError("ranking 含非对象项")
    ranking = tuple(
        ParsedRankingEntry(
            user_id=_require_str(item.get("user_id"), "ranking.user_id"),
            total_score=_require_int(item.get("total_score"), "ranking.total_score"),
            place_points=_require_int(item.get("place_points"), "ranking.place_points"),
            god_count=_require_int(item.get("god_count"), "ranking.god_count"),
            games_played=_require_int(item.get("games_played"), "ranking.games_played"),
            rank=_require_int(item.get("rank"), "ranking.rank"),
        )
        for item in ranking_raw
    )
    return ParsedTournament(
        status=_require_str(body.get("status"), "tournament.status"),
        stage_no=stage_no,
        stage_role=stage_role,
        stage_total=stage_total,
        stage_crashed=_require_bool(body.get("stage_crashed") or False, "stage_crashed"),
        qualified=qualified,
        qualify_role=qualify_role,
        my_games=tuple(g for g in my_games_raw if isinstance(g, str)),
        ranking=ranking,
        voided=_require_bool(body.get("voided") or False, "voided"),
    )


@dataclass(frozen=True)
class ParsedEvent:
    """一条官方增量事件；未知 type 原样保留由同步层分类。"""

    seq: int
    type: str  # 官方事件名保持原样，不翻译
    seat: Optional[int]
    tiles: Tuple[str, ...]
    occurred_at_unix_sec: Optional[int]  # 官方 ts；墙上时钟 Unix 秒


@dataclass(frozen=True)
class ParsedSnapshot:
    """官方全量快照的形状校验结果；字段为官方原样命名。"""

    seq: int  # 快照权威序号
    seat: int
    phase: str  # deal/draw/response_peng/response_chi/settled/finished
    turn: int
    responding_seats: Tuple[int, ...]
    dealer: int
    round_no: int
    drawn_tile: Optional[str]
    my_hand: Tuple[str, ...]  # 保留官方返回顺序；紧急"最右一张"依赖该顺序
    wall_remaining: Optional[int]
    scores: Tuple[int, int, int, int]  # 官方 scores 顺序，固定按座位 0-3
    discards: Tuple[Tuple[str, ...], ...]  # 外层固定按座位 0-3
    melds_raw: Tuple[Tuple[Mapping[str, Any], ...], ...]  # 副露原始对象，projector 再映射
    hand_counts: Tuple[int, int, int, int]  # 四家剩余手牌张数，固定按座位 0-3
    last_discard: Optional[Tuple[int, str, int]]  # (座位, 牌码, seq)，形状不全时为空
    god_baotou: bool
    god_chain_count: int
    god_catch_play: bool


def _seat_vector(value: Any, what: str, *, length: int = 4) -> Tuple[int, ...]:
    if not isinstance(value, Sequence) or len(value) != length:
        raise DtoError('{} 应为长度 {} 的数组'.format(what, length))
    return tuple(_require_int(item, what + " 项") for item in value)


def _parse_last_discard(value: Any) -> Optional[Tuple[int, str, int]]:
    """last_discard 官方形状未完整文档化：仅当 (seat, tile, seq) 齐备才采用。"""

    if not isinstance(value, Mapping):
        return None
    seat, tile, seq = value.get("seat"), value.get("tile"), value.get("seq")
    if seat is None and tile is None and seq is None:
        return None  # 字段缺失属协议允许：无最近弃牌
    # 对象存在但字段坏：协议错误而非"无弃牌"，不得静默丢弃
    if isinstance(seat, int) and not isinstance(seat, bool) and isinstance(tile, str) and isinstance(seq, int) and not isinstance(seq, bool):
        if tile not in CANONICAL_TILE_CODES:
            raise DtoError("last_discard.tile 非法牌码")
        return (_require_seat(seat, "last_discard.seat"), tile, seq)
    raise DtoError("last_discard 字段类型不符", recoverable=True)


def parse_snapshot(doc: Any, top_level_seq: Optional[int] = None) -> ParsedSnapshot:
    """校验全量快照必需字段；缺关键私有/公开字段视为可重建解析失败。

    权威 seq 优先取顶层响应的 seq（官方 demo 行为：res["seq"]），
    快照对象内部若也携带 seq 则以顶层为准。
    """

    body = _require_mapping(doc, "snapshot")
    phase = _require_str(body.get("phase"), "snapshot.phase")
    god_raw = body.get("god") or {}
    if not isinstance(god_raw, Mapping):
        raise DtoError("snapshot.god 应为对象")
    responding_raw = body.get("responding_seats") or []
    if not isinstance(responding_raw, Sequence):
        raise DtoError("responding_seats 应为数组")
    # 关键数组逐项严格校验：坏值静默丢弃会让动作权从观察中消失而不触发
    # 重建（fail-open）；宽容只保留给未知新增键
    for item in responding_raw:
        if isinstance(item, bool) or not isinstance(item, int) or not 0 <= item <= 3:
            raise DtoError("responding_seats 含非法座位 {!r}".format(type(item).__name__))
    discards_raw = body.get("discards") or []
    if not isinstance(discards_raw, Sequence) or len(discards_raw) != 4:
        raise DtoError("discards 应为按座位 0-3 的四元素数组")
    discards = tuple(_tile_list(row, "discards 行") for row in discards_raw)
    melds_raw = body.get("melds") or []
    if not isinstance(melds_raw, Sequence) or len(melds_raw) != 4:
        raise DtoError("melds 应为按座位 0-3 的四元素数组")
    meld_rows = []
    for row in melds_raw:
        if not isinstance(row, Sequence):
            raise DtoError("melds 行应为副露数组")
        checked = []
        for meld in row:
            if not isinstance(meld, Mapping):
                # 副露数组内非对象属协议错误：静默跳过会让公开副露消失
                raise DtoError("melds 内含非对象项")
            # 牌码在 DTO 边界统一校验，避免投影层 Tile 构造裸抛
            _tile_list(meld.get("tiles"), "meld.tiles")
            checked.append(meld)
        meld_rows.append(tuple(checked))
    drawn = body.get("drawn_tile")
    if drawn is not None:
        if not isinstance(drawn, str):
            raise DtoError("drawn_tile 应为字符串牌码或 null")
        if drawn not in CANONICAL_TILE_CODES:
            raise DtoError("drawn_tile 非法牌码 {!r}".format(drawn))
    wall = body.get("wall_remaining")
    if wall is not None and (isinstance(wall, bool) or not isinstance(wall, int)):
        raise DtoError("wall_remaining 应为整数或 null")
    inner_seq = body.get("seq")
    if inner_seq is not None and (isinstance(inner_seq, bool) or not isinstance(inner_seq, int)):
        raise DtoError("snapshot.seq 应为整数")
    if top_level_seq is None and inner_seq is None:
        raise DtoError("快照响应缺少权威 seq")
    authoritative_seq = top_level_seq if top_level_seq is not None else inner_seq
    return ParsedSnapshot(
        seq=authoritative_seq,
        seat=_require_seat(body.get("seat"), "snapshot.seat", allow_negative=True),
        phase=phase,
        turn=_require_seat(body.get("turn"), "snapshot.turn", allow_negative=True),
        responding_seats=tuple(
            s
            for s in responding_raw
            if isinstance(s, int) and not isinstance(s, bool) and 0 <= s <= 3
        ),
        dealer=_require_seat(body.get("dealer"), "snapshot.dealer"),
        round_no=_require_int(body.get("round_no"), "snapshot.round_no"),
        drawn_tile=drawn,
        my_hand=_tile_list(body.get("my_hand"), "my_hand"),
        wall_remaining=wall,
        scores=_seat_vector(body.get("scores"), "scores"),
        discards=discards,
        melds_raw=tuple(meld_rows),
        hand_counts=_seat_vector(body.get("hand_counts"), "hand_counts"),
        last_discard=_parse_last_discard(body.get("last_discard")),
        god_baotou=_require_bool(god_raw.get("baotou") or False, "god.baotou"),
        god_chain_count=_require_int(god_raw.get("chain_count") or 0, "god.chain_count"),
        god_catch_play=_require_bool(god_raw.get("catch_play") or False, "god.catch_play"),
    )


@dataclass(frozen=True)
class StateResponse:
    """GET /api/games/{id}/state 的四种互斥响应分类。"""

    kind: str  # pending / snapshot / events / finished
    snapshot: Optional[ParsedSnapshot] = None  # kind=snapshot 或 finished 时存在
    events: Tuple[ParsedEvent, ...] = ()  # kind=events 时存在，按官方顺序
    gap: bool = False  # 官方显式 gap=true：必须 seq=0 重建
    finished: bool = False


def parse_state_response(doc: Any) -> StateResponse:
    """按官方 demo 与 API 文档分类长轮询响应。

    pending 响应只含 pending=true；含 snapshot 的响应按全量快照处理；
    否则视为增量事件响应。未知顶层字段忽略（兼容新增）。
    """

    body = _require_mapping(doc, "state 响应")
    # gap 判定优先于 pending 早退：官方若在 pending 响应中附带 gap=true，
    # 仍必须触发 seq=0 权威重建（API 文档 §2.3 硬约束，wv9 探针）
    gap = body.get("gap") is True
    if body.get("pending") is True:
        return StateResponse(kind="pending", gap=gap)
    if isinstance(body.get("snapshot"), Mapping):
        top_seq = body.get("seq")
        if top_seq is not None and (isinstance(top_seq, bool) or not isinstance(top_seq, int)):
            raise DtoError("state 响应顶层 seq 应为整数")
        snapshot = parse_snapshot(body["snapshot"], top_seq)
        finished = body.get("finished") is True
        return StateResponse(
            kind="finished" if finished else "snapshot",
            snapshot=snapshot,
            finished=finished,
            gap=gap,
        )
    events_raw = body.get("events")
    if events_raw is None:
        events_raw = []
    if not isinstance(events_raw, Sequence):
        raise DtoError("events 应为数组")
    events = []
    for item in events_raw:
        entry = _require_mapping(item, "events 项")
        seat = entry.get("seat")
        ts = entry.get("ts")
        tiles = _tile_list(entry.get("tiles"), "event.tiles")
        single = entry.get("tile")
        if single is not None:
            # 单数字段同样走牌码校验：非法值在 DTO 边界拦截，
            # 不得在投影层以 ValueError 裸抛
            tiles = tiles + _tile_list((single,), "event.tile")
        if seat is not None:
            seat = _require_seat(seat, "event.seat", allow_negative=True)
        # bool 是 int 子类：ts=true 不得当作合法 Unix 秒
        valid_ts = ts if isinstance(ts, int) and not isinstance(ts, bool) else None
        events.append(
            ParsedEvent(
                seq=_require_int(entry.get("seq"), "event.seq"),
                type=_require_str(entry.get("type"), "event.type"),
                seat=seat,
                tiles=tiles,
                occurred_at_unix_sec=valid_ts,
            )
        )
    return StateResponse(kind="events", events=tuple(events), gap=gap)


def extract_error_code(status: int, text: str) -> Optional[str]:
    """从官方错误响应体提取非敏感错误码；形状未文档化，JSON 与文本都容忍。"""

    stripped = (text or "").strip()
    if not stripped:
        return None
    try:
        import json

        doc = json.loads(stripped)
    except ValueError:
        return None
    if not isinstance(doc, Mapping):
        return None
    for key in ("code", "error", "error_code"):
        value = doc.get(key)
        if isinstance(value, str) and value:
            return value
    return None

