"""官方 JSON 报文解析（v8 历史快照，当前已审查指南 v27）。

解析原则（依据 doc/official-platform-api-v2.md，指南 v8 快照，抓取 2026-09-03；
v9–v11 变更依据 doc/references/official-guide-version-v11.json，2026-09-04 抓取；
v12–v15 变更依据 doc/references/official-guide-version-v15.json，2026-09-05 抓取；
最新变更依据 doc/references/official-guide-version-v27.json，2026-09-09 抓取）：

- 已确认必需字段缺失时抛 DtoError（默认可用 seq=0 快照重建修复）；
- 未知新增字段一律忽略并保留（v8 的 Description 属于此类兼容新增）；
- 牌码使用官方 v8 牌码表（1w-9w、1b-9b、1t-9t、东南西北中发白），不自行翻译；
- 错误体形状官方未文档化，extract_error_code 对 JSON 与纯文本都宽容。
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping, Optional, Sequence, Tuple, Union

from hangma_bot.kernel.actions import CANONICAL_TILE_CODES

from .errors import DtoError

KNOWN_GUIDE_VERSION = 30  # 当前已审查指南；v16之后仍逐条验摘要，不能仅按顶层版本放行。
_LEGACY_GUIDE_BASELINE = 15  # 原已接受基线，之后的breaking需按调用路径和完整条目审查。
# v9—v11：非破坏性 changed 条目，已逐条审查并同步实现（v9 测试房间数据 API
# 限速粒度、v10 跨局 gap=true 全量快照、v11 state 轮询 16/s 每用户聚合）。
# v12（added）：GET /api/games/{id}/notify SSE 通知流，可选能力——当前实现继续
# 用 /state 长轮询，不采纳 SSE；帧协议不影响既有轮询路径。
# v13（breaking，已审查）：新建赛事分桌 = 「已确认 ∧ 开赛时刻在线」；报名=意向；
# 在线证据 = 任意已认证 Bearer 请求 90s 内触达；config 新增 OnlineConfirm 键
# （缺失或 false = 2026-09-05 前创建的存量赛，沿用旧分桌）。本 bot 用玩家 API
# register→ready 且空转期以 2s 间隔轮询本赛端点，天然满足在线要求，无协议破坏。
# v14（added）：GET /portal/api/guide 免认证全文端点（?format=text 给 LLM/终端），
# 仅文档同步用途，运行时继续用 /portal/api/guide/version 做版本自检。
# v12—v14 追加审查（2026-09-05 同步发现官方变更日志回溯扩充自动匹配条目）：
#   v12 玩家 API 新增 POST /api/match（自动匹配房池入席，仅全局 token）；测试房间
#   创建支持 match_seats（门户侧）；门户「我的 AI 身份」昵称+全局令牌轮换——
#   本 bot 用报名 Token、不调用 /api/match、不支持全局 Token（initialize 直接
#   TARGET_MISMATCH 拒绝），零协议影响，仅文档记录。
#   v13 POST /api/match 改全自动语义；新增 404 NO_ROOM_AVAILABLE 与 409
#   AUTO_MATCH_ONLY / MATCH_BUSY / MATCH_LIMIT_REACHED——仅在自动匹配路径出现，
#   本 bot 不触发。
#   v14 门户新增 GET /portal/api/leaderboard 排行榜与身份昵称修改——门户 API，
#   玩家 API 契约零影响。
# v15（breaking，已审查）：自动匹配房服务默认配置上调 M=1/Rounds=2 → M=10/Rounds=8。
# breaking 面仅限 POST /api/match 显式声明上限低于新默认（M∈1..9 或 Rounds∈1..7）
# 的调用方（→ 404 NO_ROOM_AVAILABLE）；无 body 协议不变。本 bot 不调用 /api/match，
# 正式锦标赛/测试房间路径不受影响；16 场记账仅自动房入席时占用 cfg.M=10 格，
# 与既有正式赛 M 上限互不叠加（同桶 16 上限仍由服务端统一校验）。
# 依据：doc/references/official-guide-version-v15.json（2026-09-05 抓取）。

# v24（2026-09-09 补充审查）：scoped 令牌不受匿名入口限制；自动匹配入口
# 不做匿名注册，显式处理未绑定门户身份时的 PORTAL_BINDING_REQUIRED。
# 两种已审查调用路径按条目完整内容匹配；无调用上下文的解析仍不豁免。
_SCOPED_V24_BREAKING_SHA256 = "a07463ab753085c0198156065ad3ca2baeb2fa1fe53f59b6d0d5da338f773171"
# v25吃最多2摊：hangma已从本人chi副露数限制；v26恢复圈主响应及公开身份，
# v27仅门户排行榜变更。原文快照：official-guide-version-v27.json，2026-09-09。
_V25_CHI_LIMIT_SHA256 = "cb5be8f872ea83d02c88fe7fa79e45bb10314c057a0110011c16f9df968b8026"
# v28（changed，已审查，2026-09-10 复审）：胡大牌榜排序链去掉第 3 键「该牌型全史次数」，
#   同番同分改为只按胡手时刻排名。纯门户展示，不进入任何决策输入，零协议影响。
# v29（breaking，已审查，2026-09-10 复审）：新增全服功能开关，管理页可关闭自由匹配与
#   自建测试房；关闭后 POST /api/match 新匹配、建测试房、test 房「重开下一轮」一律
#   403 FEATURE_DISABLED（**永久条件，不要重试**；该路径此前返回 409 房态类错误）。
#   在途照常：已在房中的用户重调 /api/match 仍 200 返回原房，进行中的对局与房间打完；
#   已有房间的列表/详情/关闭/删除/重发令牌不受影响。本 bot 的 match 入口已按
#   auto_match.FEATURE_DISABLED 分支给出明确终态诊断，不会把它误报成门户绑定问题。
#   依据：doc/references/official-guide-version-v30.json（2026-09-10 抓取）。
# v30（changed，已审查，2026-09-10 复审）：他人 name 全面收口——仅管理面建的正式锦标赛
#   仍下发 users.name；测试房/自由房/排行榜一律只出 AI 昵称，昵称为空返回**空串**
#   （消费方按空串回退 user_id），「昵称为空即真名」的回退全部取消；本人 /portal/api/me
#   顶层 name 与 /admin/* 语义不变。本 bot 与离线分析全部按 user_id 作稳定身份，
#   name 只用于展示与本地路径命名，零协议影响。
_V29_FEATURE_DISABLED_SHA256 = "b7da31d4c244cbb33fa4cd15781d478220eeab3ad7e1a4c1535f5f9be0cda0d3"


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
    has_unknown_breaking_change: bool  # 存在超出当前调用路径已审查范围的 breaking 变更
    changes: Tuple[Mapping[str, Any], ...]  # 原样保留，供审计与回放解释行为差异


def parse_guide_version(doc: Any, *, scoped_tournament: bool = False,
                        auto_match: bool = False) -> ParsedGuideVersion:
    """解析指南版本并标记未知破坏性变更，无副作用。

    scoped_tournament只供核验报名令牌绑定的赛事会话使用；auto_match只供
    已处理门户绑定403且不调用匿名注册的自动匹配入口使用。v24按这两条
    已审查路径放行，v25按本地吃摊限制放行，v29按全服功能开关放行
    （关闭自由匹配/测试房时返回永久 403 FEATURE_DISABLED，不重试）；
    同版本回溯新增/改写仍未知。
    """

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
            or item["version"] > _LEGACY_GUIDE_BASELINE
        )
        and not (
            hashlib.sha256(
                json.dumps(item, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            ).hexdigest() in (
                (_V25_CHI_LIMIT_SHA256, _SCOPED_V24_BREAKING_SHA256, _V29_FEATURE_DISABLED_SHA256)
                if scoped_tournament or auto_match
                else (_V25_CHI_LIMIT_SHA256, _V29_FEATURE_DISABLED_SHA256)
            )
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
    online_confirm: bool  # v13：新建赛事「确认 ∧ 在线」分桌开关；缺失或 false = 存量赛旧分桌


def parse_rules_config(doc: Any) -> ParsedRulesConfig:
    body = _require_mapping(doc, "rules")
    config = _require_mapping(body.get("config"), "rules.config")
    description = config.get("Description")
    if description is not None and not isinstance(description, str):
        raise DtoError("Description 应为字符串")
    online_confirm = config.get("OnlineConfirm")
    if online_confirm is not None and not isinstance(online_confirm, bool):
        raise DtoError("OnlineConfirm 应为布尔")
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
        online_confirm=bool(online_confirm or False),  # 缺键/False = 存量赛（v13 判别）
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
    detail_kind: Optional[str] = None  # gang/timeout 的 data.kind；缺失表示未提供，不推测
    catch_play: Optional[bool] = None  # 弃牌事件公开的抓打圈标记；缺失不等于 False
    gang_replenish: Optional[bool] = None  # 摸牌事件明确声明杠补牌；缺失须另行推导
    response_window: Optional[str] = None  # 超时所属 peng/chi 阶段；保留官方扩展值
    result_draw: Optional[bool] = None  # 已公开的本单局终局是否流局
    result_fan: Optional[int] = None  # 已公开的本单局终局番数，非负
    result_details: Optional[Tuple[str, ...]] = None  # 已公开的终局计番明细，顺序不变
    result_scores: Optional[Tuple[int, int, int, int]] = None  # 终局积分增量，座位 0—3
    final_scores: Optional[Tuple[int, int, int, int]] = None  # 终场公开积分，座位 0—3；不从赛后隐藏数据填入
    claimed_tile: Optional[str] = None  # chi 顶层 tile 明确公开的被吃牌；缺失/空值不按组合位置推测


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
    last_discard: Optional[Union[Tuple[int, str, int], str]]
    # 两种官方形态：结构化 (座位, 牌码, seq)，或纯牌码字符串
    # （2026-09 测试房间实测，captures/state-draw-phase-*.json）。
    # 字符串形态的座位与序号由 projector 按响应阶段重建（turn 即弃牌者）。
    god_baotou: bool
    god_chain_count: int
    god_catch_play: bool
    # 官方响应窗绝对截止（墙上时钟毫秒；2026-09-05 实测在场，响应阶段快照
    # 4264/4264 携带）。缺省 None：draw/deal 等无窗阶段或官方未提供时。
    window_deadline_ms: Optional[int] = None
    god_discarder_seat: Optional[int] = None  # v26公开豁免方0—3，-1为无圈；旧响应未给字段时为空


def _seat_vector(value: Any, what: str, *, length: int = 4) -> Tuple[int, ...]:
    if not isinstance(value, Sequence) or len(value) != length:
        raise DtoError('{} 应为长度 {} 的数组'.format(what, length))
    return tuple(_require_int(item, what + " 项") for item in value)


def _parse_last_discard(value: Any) -> Optional[Union[Tuple[int, str, int], str]]:
    """last_discard 两种官方形态：结构化 (seat, tile, seq) 或纯牌码字符串。

    2026-09 测试房间实测（captures/state-draw-phase-t_714a42392cba.json）官方
    返回纯牌码字符串（如 "6w"）；字符串保留给 projector 按响应阶段重建
    （响应阶段 turn 即弃牌者，API 文档 §2.3/§5.3）。两种形态都做牌码校验；
    空串与 drawn_tile 同口径归一化为 None。对象存在但字段坏、或出现第三
    种未知形状，属协议错误而非"无弃牌"，不得静默丢弃。
    """

    if value is None or value == "" or value == "0w":
        # "0w" 是官方"本局尚无弃牌"的占位符（2026-09-05 测试房实测：开局
        # 快照 16/16 场全部携带，见 doc/implementation/reviews/
        # test-room-acceptance-result-2026-09-05.md §4.1）——牌码 0 不存在，
        # 语义等同空串，按无弃牌归一化
        return None
    if isinstance(value, str):
        if value not in CANONICAL_TILE_CODES:
            raise DtoError("last_discard 非法牌码 {!r}".format(value))
        return value
    if not isinstance(value, Mapping):
        raise DtoError("last_discard 字段类型不符", recoverable=True)
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
    # god 是活动玩家决策依据，缺失不能静默变成三个关闭值。终态不再
    # 投递动作窗口，允许旧平台省略整个对象；部分对象仍严格逐项验证。
    god_raw = body.get("god")
    if god_raw is None and phase in ("settled", "finished"):
        god_raw = {"baotou": False, "chain_count": 0, "catch_play": False}
    if not isinstance(god_raw, Mapping):
        raise DtoError("snapshot.god 应为完整对象")
    god_baotou = _require_bool(god_raw.get("baotou"), "god.baotou")
    god_chain_count = _require_int(god_raw.get("chain_count"), "god.chain_count")
    god_catch_play = _require_bool(god_raw.get("catch_play"), "god.catch_play")
    god_discarder_seat = None
    if "god_discarder_seat" in god_raw:
        god_discarder_seat = _require_seat(
            god_raw["god_discarder_seat"], "god.god_discarder_seat", allow_negative=True)
        if god_catch_play and god_discarder_seat == -1 and phase not in ("settled", "finished"):
            raise DtoError("god.catch_play=true 与 god_discarder_seat=-1 冲突")
    if god_chain_count < 0:
        raise DtoError("god.chain_count 不能为负数")
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
    # 官方实测（2026-09-04，房间 t_714a42392cba）：非摸牌阶段 drawn_tile
    # 为空字符串 "" 而非 null。空串在此归一化为 None（无摸牌），其余
    # 非法值仍然拒绝——与 kernel 裁决"摸牌单列、适配器归一化"一致。
    if drawn == "":
        drawn = None
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
        god_baotou=god_baotou,
        god_chain_count=god_chain_count,
        god_catch_play=god_catch_play,
        god_discarder_seat=god_discarder_seat,
        window_deadline_ms=(
            body.get("window_deadline_ms")
            if isinstance(body.get("window_deadline_ms"), int)
            and not isinstance(body.get("window_deadline_ms"), bool)
            and body.get("window_deadline_ms") > 0
            else None
        ),
    )


@dataclass(frozen=True)
class StateResponse:
    """GET /api/games/{id}/state 的主响应分类；快照可同时携带事件。"""

    kind: str  # pending / snapshot / events / finished
    snapshot: Optional[ParsedSnapshot] = None  # kind=snapshot 或 finished 时存在
    events: Tuple[ParsedEvent, ...] = ()  # 各类响应均可附带，按官方顺序，快照不可遮蔽它们
    gap: bool = False  # 官方显式 gap=true：必须 seq=0 重建；指南 v10 起快照响应也可携带（跨局断链），此时快照即权威重建结果
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
    events_raw = body.get("events")
    if events_raw is None:
        events_raw = []
    if not isinstance(events_raw, (list, tuple)):
        raise DtoError("events 应为数组")
    events = tuple(_parse_event(item) for item in events_raw)
    if isinstance(body.get("snapshot"), Mapping):
        top_seq = body.get("seq")
        if top_seq is not None and (isinstance(top_seq, bool) or not isinstance(top_seq, int)):
            raise DtoError("state 响应顶层 seq 应为整数")
        snapshot = parse_snapshot(body["snapshot"], top_seq)
        finished = body.get("finished") is True
        return StateResponse(
            kind="finished" if finished else "snapshot",
            snapshot=snapshot,
            events=events,
            finished=finished,
            gap=gap,
        )
    return StateResponse(kind="events", events=events, gap=gap, finished=body.get("finished") is True)


_TILE_ACTIONS = frozenset({"tile_drawn", "tile_discarded", "chi", "peng", "gang"})
_TERMINAL_EVENTS = frozenset({"round_ended", "game_ended"})


def _parse_event(item: Any) -> ParsedEvent:
    """规范化玩家可见事件的牌与动作细节，不透传未声明的 data 字典。

    官方 v15 本地归档（2026-09-05）：pass/timeout/终局携带空 tile，
    chi 的 data.tiles 携带完整组合，gang/timeout 用 data.kind 描述类别。
    归档仅用于确认字段形状，运行时信息权限仍由玩家会话边界保证。
    """

    entry = _require_mapping(item, "events 项")
    event_type = _require_str(entry.get("type"), "event.type")
    seat = entry.get("seat")
    if event_type in _TERMINAL_EVENTS and seat == -1:
        seat = None
    elif seat is not None:
        seat = _require_seat(seat, "event.seat")
    if event_type in _TILE_ACTIONS | {"pass", "timeout"} and seat is None:
        raise DtoError("event.seat 动作事件不可缺失")
    single = entry.get("tile")
    single_tiles = () if single is None or single == "" else _tile_list((single,), "event.tile")
    tiles = _tile_list(entry.get("tiles"), "event.tiles")
    data_raw = entry.get("data")
    data = {} if data_raw is None else _require_mapping(data_raw, "event.data")
    if event_type == "chi" and "tiles" in data:
        tiles = _tile_list(data["tiles"], "event.data.tiles")
        if len(tiles) != 3 or (single_tiles and single not in tiles):
            raise DtoError("chi data.tiles 应为包含被吃牌的三张完整组合")
    elif not tiles:
        tiles = single_tiles
    elif single_tiles:
        # 顶层完整组合不再拼接被吃牌；旧两张自有牌形状补上顶层 tile。
        if event_type == "chi" and len(tiles) == 2:
            tiles = tiles + single_tiles
        elif single not in tiles:
            raise DtoError("event.tile 与 event.tiles 不一致")
    # 无牌摸牌可能是脱敏事件；DTO 不知道本人座位，由会话判断本人
    # 缺牌需恢复、他家异常摸牌不公开牌值并恢复权威快照。
    if event_type in _TILE_ACTIONS - {"tile_drawn"} and not tiles:
        raise DtoError("{} 事件缺少必要牌码".format(event_type))
    if event_type in {"tile_drawn", "tile_discarded"} and tiles and len(tiles) != 1:
        raise DtoError("{} 事件应恰有一张牌".format(event_type))
    detail_kind = None
    if event_type in ("gang", "timeout") and data.get("kind") is not None:
        detail_kind = _require_str(data["kind"], "event.data.kind")
        if not detail_kind:
            raise DtoError("event.data.kind 不可为空字符串")
    # v17 实测白名单：仅接收对应事件已公开的强类型字段，不透传私有 data。
    facts = {}
    specification = {
        "tile_discarded": (("catch_play", "catch_play", "bool"),),
        "tile_drawn": (("gang_replenish", "gang_replenish", "bool"),),
        "timeout": (("window", "response_window", "str"),),
        "round_ended": (("draw", "result_draw", "bool"), ("fan", "result_fan", "int"),
                        ("detail", "result_details", "strings"), ("scores", "result_scores", "scores")),
        "game_ended": (("final_scores", "final_scores", "scores"),),
    }
    for key, name, kind in specification.get(event_type, ()):
        if key not in data:
            continue
        value = data[key]
        label = "event.data." + key
        if kind == "bool":
            value = _require_bool(value, label)
        elif kind == "str":
            value = _require_str(value, label)
            if not value:
                raise DtoError(label + " 不可为空")
        elif kind == "int":
            value = _require_int(value, label)
            if value < 0:
                raise DtoError(label + " 不可为负")
        else:
            if not isinstance(value, (list, tuple)):
                raise DtoError(label + " 应为数组")
            if kind == "scores" and len(value) != 4:
                raise DtoError(label + " 应按座位 0—3 保存四个整数")
            value = tuple((_require_str if kind == "strings" else _require_int)(x, label) for x in value)
            if kind == "strings" and any(not x for x in value):
                raise DtoError(label + " 不可含空明细")
        facts[name] = value
    ts = entry.get("ts")
    valid_ts = ts if isinstance(ts, int) and not isinstance(ts, bool) else None
    return ParsedEvent(
        seq=_require_int(entry.get("seq"), "event.seq"),
        type=event_type,
        seat=seat,
        tiles=tiles,
        occurred_at_unix_sec=valid_ts,
        detail_kind=detail_kind,
        claimed_tile=single_tiles[0] if event_type == "chi" and single_tiles else None,
        **facts,
    )


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
