"""官方 DTO 与内部规范类型之间的纯转换。

本模块不做 IO、不读时钟、不持有状态：所有函数给定相同输入返回相同输出。
牌码直接采用官方 v8 牌码表字符串（kernel Tile.code 示例即 "1w"），
财神固定为白板（依据 API 文档 §2.4："白板是财神"）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from hangma_bot.application.contracts import (
    CompetitionContext,
    GuideVersion,
    StageIdentity,
    TournamentSnapshot,
    TournamentStatus,
)
from hangma_bot.kernel.actions import (
    Action,
    Chi,
    Discard,
    Gang,
    Hu,
    Pass,
    Peng,
    Tile,
    WindowKey,
    WindowPhase,
    action_key as canonical_action_key,
)
from hangma_bot.kernel.config import RuleConfig, TimingConfig, TournamentConfig
from hangma_bot.kernel.observation import (
    PlayerObservation,
    PublicDiscard,
    PublicEvent,
    PublicMeld,
    RankingEntry,
    RulePublicState,
)

from .dto import (
    ParsedEvent,
    ParsedGuideVersion,
    ParsedRankingEntry,
    ParsedRulesConfig,
    ParsedSnapshot,
    ParsedTournament,
)
from .errors import DtoError

WEALTH_GOD_TILE = Tile("白")  # 官方规则：白板是财神（API 文档 §2.4 牌码表）


def guide_version(parsed: ParsedGuideVersion) -> GuideVersion:
    """官方指南版本转内部规范值；breaking 判定已在 dto 层完成。"""

    return GuideVersion(
        version=parsed.version,
        updated_at=parsed.updated_at,
        has_unknown_breaking_change=parsed.has_unknown_breaking_change,
    )


def rules_config(parsed: ParsedRulesConfig, ruleset_version: str) -> TournamentConfig:
    """官方 rules.config 转 TournamentConfig；规则语义版本由本地维护。"""

    return TournamentConfig(
        max_games=parsed.max_games,
        rounds_per_game=parsed.rounds_per_game,
        rules=RuleConfig(
            ruleset_version=ruleset_version,
            base_score=parsed.base_score,
            you_cai_bi_kao=parsed.you_cai_bi_kao,
        ),
        timing=TimingConfig(
            peng_timeout_sec=parsed.peng_timeout_sec,
            chi_timeout_sec=parsed.chi_timeout_sec,
            discard_timeout_sec=parsed.discard_timeout_sec,
        ),
    )


_STATUS_MAP = {
    "registering": TournamentStatus.REGISTERING,
    "running": TournamentStatus.RUNNING,
    "stage_done": TournamentStatus.STAGE_DONE,
    "stage_open": TournamentStatus.STAGE_OPEN,
    "finished": TournamentStatus.FINISHED,
    "closed": TournamentStatus.CLOSED,
    "void": TournamentStatus.VOID,
}


def _status(raw: str) -> TournamentStatus:
    try:
        return _STATUS_MAP[raw]
    except KeyError:
        raise DtoError("未知赛事状态: {}".format(raw), recoverable=False) from None


def ranking_entry(entry: ParsedRankingEntry) -> RankingEntry:
    """官方 ranking 项转内部值；user_id 即脱敏参赛身份。"""

    return RankingEntry(
        participant_id=entry.user_id,
        total_score=entry.total_score,
        place_points=entry.place_points,
        god_count=entry.god_count,
        games_played=entry.games_played,
        rank=entry.rank,
    )


@dataclass(frozen=True)
class TournamentProjection:
    """一次赛事详情投影：快照与观察修订号成对产出。"""

    snapshot: TournamentSnapshot
    observed_revision: int  # 本会话内单调递增，用于拒绝陈旧 ready


def tournament_snapshot(
    parsed: ParsedTournament,
    *,
    tournament_id: str,
    participant_id: str,
    active_games: Tuple[str, ...],
    observed_revision: int,
    observed_at_unix_ms: int,  # 墙上时钟毫秒，由调用方注入
) -> TournamentProjection:
    """官方赛事详情 + /api/me 活跃场合成 TournamentSnapshot。

    active_games 与 my_games 来源不同（前者实时、后者累计），
    由调用方负责把两个端点的结果合并传入。
    """

    ranking = tuple(ranking_entry(e) for e in parsed.ranking)
    my_rank = next((e.rank for e in parsed.ranking if e.user_id == participant_id), None)
    competition = CompetitionContext(
        tournament_id=tournament_id,
        stage_no=parsed.stage_no,
        stage_role=parsed.stage_role,
        stage_total=parsed.stage_total,
        participant_rank=my_rank,
        ranking=ranking,
        observed_at_unix_ms=observed_at_unix_ms,
    )
    snapshot = TournamentSnapshot(
        tournament_id=tournament_id,
        participant_id=participant_id,
        status=_status(parsed.status),
        stage=StageIdentity(stage_no=parsed.stage_no, observed_revision=observed_revision),
        stage_role=parsed.stage_role,
        stage_total=parsed.stage_total,
        stage_crashed=parsed.stage_crashed,
        qualified=parsed.qualified,
        qualify_role=parsed.qualify_role,
        active_games=active_games,
        my_games=parsed.my_games,
        competition=competition,
        observed_at_unix_ms=observed_at_unix_ms,
    )
    return TournamentProjection(snapshot=snapshot, observed_revision=observed_revision)


def public_event(event: ParsedEvent) -> PublicEvent:
    """官方增量事件转公开历史事件；type 保持官方原样。"""

    return PublicEvent(
        seq=event.seq,
        kind=event.type,
        seat=event.seat,
        tiles=tuple(Tile(code) for code in event.tiles),
        occurred_at_unix_sec=event.occurred_at_unix_sec,
    )


def _meld(raw: object, seat_no: int) -> PublicMeld:
    """官方副露对象转 PublicMeld；kind 官方取值未文档化，原样透传。"""

    from typing import Mapping, Sequence

    if not isinstance(raw, Mapping):
        raise DtoError("meld 应为对象")
    kind = raw.get("kind")
    tiles_raw = raw.get("tiles")
    if not isinstance(kind, str) or not isinstance(tiles_raw, Sequence):
        raise DtoError("meld.kind/tiles 缺失或类型不符")
    from_seat = raw.get("from_seat")
    return PublicMeld(
        seat=seat_no,
        kind=kind,
        tiles=tuple(Tile(code) for code in tiles_raw if isinstance(code, str)),
        from_seat=from_seat if isinstance(from_seat, int) else None,
    )


def observation(snapshot: ParsedSnapshot, history: Tuple[PublicEvent, ...], game_id: str) -> PlayerObservation:
    """官方全量快照 + 已累积公开事件转 PlayerObservation。

    只使用本人依法可见字段：my_hand/drawn_tile 是官方私有信息，
    他家手牌与未来牌墙从不出现（信息权限由 kernel 类型保证）。
    """

    melds = tuple(
        tuple(_meld(m, seat_no) for m in row)
        for seat_no, row in enumerate(snapshot.melds_raw)
    )
    last_discard = None
    if snapshot.last_discard is not None:
        seat_no, tile_code, seq = snapshot.last_discard
        last_discard = PublicDiscard(seat=seat_no, tile=Tile(tile_code), seq=seq)
    return PlayerObservation(
        game_id=game_id,
        seat=snapshot.seat,
        round_no=snapshot.round_no,
        snapshot_seq=snapshot.seq,
        phase=snapshot.phase,  # 官方阶段原样保存；窗口阶段由 WindowKey 强类型表达
        dealer_seat=snapshot.dealer,
        turn_seat=snapshot.turn,
        responding_seats=snapshot.responding_seats,
        my_hand=tuple(Tile(code) for code in snapshot.my_hand),
        drawn_tile=Tile(snapshot.drawn_tile) if snapshot.drawn_tile else None,
        discards=tuple(
            tuple(Tile(code) for code in row) for row in snapshot.discards
        ),
        melds=melds,
        hand_counts=snapshot.hand_counts,
        last_discard=last_discard,
        remaining_tile_count=snapshot.wall_remaining,
        scores=snapshot.scores,
        rule_state=RulePublicState(
            wealth_god=WEALTH_GOD_TILE,
            baotou=snapshot.god_baotou,
            chain_count=snapshot.god_chain_count,
            catch_play=snapshot.god_catch_play,
        ),
        public_history=history,
    )


@dataclass(frozen=True)
class DetectedWindow:
    """从权威快照判定出的我方动作窗口。"""

    window_key: WindowKey
    timeout_seconds: float  # 官方配置的窗口持续秒数


def detect_window(snapshot: ParsedSnapshot, timing: TimingConfig, game_id: str) -> Optional[DetectedWindow]:
    """按官方动作判定下限（API 文档 §2.4）识别是否轮到本座行动。

    只判定"是否有动作权"，不判定具体合法动作——合法性属于 hangma 规则模块。
    trigger_seq 使用快照权威 seq：窗口由该权威状态触发。
    """

    seat = snapshot.seat
    if seat < 0:
        return None  # 观赛视角无动作权
    if snapshot.phase == "draw" and snapshot.turn == seat:
        phase, timeout = WindowPhase.DRAW, timing.discard_timeout_sec
    elif snapshot.phase == "response_peng" and seat in snapshot.responding_seats:
        phase, timeout = WindowPhase.RESPONSE_PENG, timing.peng_timeout_sec
    elif snapshot.phase == "response_chi" and seat in snapshot.responding_seats:
        phase, timeout = WindowPhase.RESPONSE_CHI, timing.chi_timeout_sec
    else:
        return None
    return DetectedWindow(
        window_key=WindowKey(
            game_id=game_id,
            round_no=snapshot.round_no,
            trigger_seq=snapshot.seq,
            phase=phase,
            seat=seat,
        ),
        timeout_seconds=timeout,
    )


def action_request_body(
    action: Action,
    *,
    last_discard_tile: Optional[Tile],
    hand: Tuple[Tile, ...],
    drawn_tile: Optional[Tile] = None,
    catch_play: bool = False,
    phase: WindowPhase = WindowPhase.DRAW,
    responding: bool = True,
) -> Optional[dict]:
    """内部动作转官方 POST /api/games/{id}/action 请求体。

    返回 None 表示该动作在当前观察下无法安全构造官方请求体
    （例如吃牌组合与最近弃牌不一致），调用方应按 SubmitNotSent 处理。

    杠不发送类型字段：官方 body 基本结构仅 action+tile（API 文档 §2.4），
    杠种类由服务端按阶段判定——这是待官方样本确认的假设。
    pass 携带空 tile，与官方 demo 一致。
    """

    if isinstance(action, Discard):
        # 官方快照把刚摸的牌单列在 drawn_tile（my_hand 是否并入未文档化）：
        # 出牌合法性按 hand ∪ {drawn_tile} 判定，避免拒绝打刚摸的牌
        available = set(hand) | ({drawn_tile} if drawn_tile is not None else set())
        if catch_play:
            # 抓打圈硬约束：只能打刚摸到的牌（API 文档 §5.4）。
            # drawn_tile 缺失属协议畸形态：客户端不猜测（demo 回退打第一张
            # 与 kernel 最右口径矛盾）——fail-closed 拒绝构造，由服务端
            # 超时自动打"最右一张"兜底（API 文档 §5.2），行为与官方一致
            if drawn_tile is None or action.tile != drawn_tile:
                return None
        if action.tile not in available:
            return None
        return {"action": "discard", "tile": action.tile.code}
    if isinstance(action, Peng):
        if phase != WindowPhase.RESPONSE_PENG or not responding:
            return None  # 碰只可能在碰响应窗口提出（与吃防御对齐）
        if last_discard_tile is None or action.tile != last_discard_tile:
            return None
        return {"action": "peng", "tile": action.tile.code}
    if isinstance(action, Chi):
        if last_discard_tile is None or phase != WindowPhase.RESPONSE_CHI or not responding:
            return None
        claimed = last_discard_tile
        if claimed not in action.tiles:
            return None  # 吃牌组合必须包含被吃牌（kernel Chi 语义）
        remaining = list(action.tiles)
        remaining.remove(claimed)
        return {
            "action": "chi",
            "tile": claimed.code,
            "tiles": [tile.code for tile in remaining],
        }
    if isinstance(action, Gang):
        if action.kind.value == "exposed":
            if phase != WindowPhase.RESPONSE_PENG or not responding:
                return None  # 明杠只可能在碰响应窗口提出
            if last_discard_tile is None or action.tile != last_discard_tile:
                return None
        return {"action": "gang", "tile": action.tile.code}
    if isinstance(action, Hu):
        return {"action": "hu"}
    if isinstance(action, Pass):
        if phase == WindowPhase.DRAW:
            return None  # 官方 draw 窗没有 pass 动作（API 文档 §2.4 动作判定下限）
        return {"action": "pass", "tile": ""}
    return None

