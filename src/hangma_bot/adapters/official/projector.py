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
        detail_kind=event.detail_kind,
        catch_play=event.catch_play,
        gang_replenish=event.gang_replenish,
        response_window=event.response_window,
        result_draw=event.result_draw,
        result_fan=event.result_fan,
        result_details=event.result_details,
        result_scores=event.result_scores,
        final_scores=event.final_scores,
        claimed_tile=Tile(event.claimed_tile) if event.claimed_tile is not None else None,
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


_RESPONSE_PHASES = ("response_peng", "response_chi")


def project_last_discard(
    snapshot: ParsedSnapshot,
) -> Tuple[Optional[PublicDiscard], Tuple[str, ...]]:
    """官方 last_discard 投影为 PublicDiscard(座位, 牌码, seq)，并返回审计提示。

    官方两种形态（dto 已校验牌码）：

    - 结构化 (座位, 牌码, seq)：直接采用，各阶段通用（既有行为）。
    - 纯牌码字符串（2026-09 测试房间实测，captures/state-draw-phase-*.json）：
      仅 response_peng / response_chi 阶段重建。响应阶段快照 turn 即
      弃牌者——API 文档 §2.3 字段表 `turn` 为"当前行动座位"，§5.3 时序
      中弃牌后行动权停留在弃牌者直到响应窗口走满、下家才摸牌；而 draw
      阶段 turn 已转入下家（实测样本：turn=0 但牌河末张 "6w" 属座位 3），
      语义不成立，故 draw 等其他阶段不强行造 last_discard，维持 None。
    - 重建以 turn 为座位，并以"该座位牌河末张 == 牌码"交叉验证；不一致
      仍以 turn 为准（响应阶段官方语义保证存在待认领弃牌），只记审计
      提示，绝不因此返回 None。seq 取快照权威 seq：弃牌即最近事件，
      误差可接受且只用于审计关联。
    - turn 越界（如 -1）属协议畸形态：不伪造座位，返回 None + 提示，
      交由 hangma 以"缺少触发弃牌"RuleIssue 保守降级（过仍保底）。
    """

    raw = snapshot.last_discard
    if raw is None:
        return None, ()
    if isinstance(raw, str):
        if snapshot.phase not in _RESPONSE_PHASES:
            return None, ()  # 非响应阶段 turn 已不是弃牌者，不重建
        seat_no = snapshot.turn
        if not 0 <= seat_no <= 3:
            return None, (
                "response 阶段 turn={0} 越界，无法重建 last_discard({1})".format(
                    snapshot.turn, raw
                ),
            )
        river = snapshot.discards[seat_no]
        river_tail = river[-1] if river else None
        notes = ()
        if river_tail != raw:
            notes = (
                "重建 last_discard：以 turn={0} 为弃牌者，该座位牌河末张 {1} != {2}，"
                "按响应阶段语义保留 turn 为弃牌者座位".format(
                    seat_no,
                    river_tail if river_tail is not None else "空",
                    raw,
                ),
            )
        return PublicDiscard(seat=seat_no, tile=Tile(raw), seq=snapshot.seq), notes
    seat_no, tile_code, seq = raw
    return PublicDiscard(seat=seat_no, tile=Tile(tile_code), seq=seq), ()


def observation(snapshot: ParsedSnapshot, history: Tuple[PublicEvent, ...], game_id: str) -> PlayerObservation:
    """官方全量快照 + 已累积公开事件转 PlayerObservation。

    只使用本人依法可见字段：my_hand/drawn_tile 是官方私有信息，
    他家手牌与未来牌墙从不出现（信息权限由 kernel 类型保证）。
    last_discard 的投影规则见 :func:`project_last_discard`。
    """

    melds = tuple(
        tuple(_meld(m, seat_no) for m in row)
        for seat_no, row in enumerate(snapshot.melds_raw)
    )
    last_discard, _ = project_last_discard(snapshot)
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
            catch_play_owner_seat=(snapshot.god_discarder_seat
                if snapshot.god_catch_play and snapshot.god_discarder_seat in (0, 1, 2, 3) else None),
        ),
        public_history=history,
    )


@dataclass(frozen=True)
class DetectedWindow:
    """从权威快照判定出的我方动作窗口。"""

    window_key: WindowKey
    timeout_seconds: float  # 官方配置的窗口持续秒数
    trigger_projection_note: Optional[str] = None  # 触发序号退化兜底时的审计提示
    # 解析命中的触发弃牌事实 (seq, 牌码, 座位)；调用方据此更新跨重建记忆
    trigger_discard: Optional[Tuple[int, str, int]] = None


def _structured_last_discard(snapshot: ParsedSnapshot) -> Optional[Tuple[int, str, int]]:
    """结构化 last_discard (seat, tile, seq) 转触发弃牌事实 (seq, 牌码, 座位)。"""

    raw = snapshot.last_discard
    if isinstance(raw, tuple) and len(raw) == 3 and isinstance(raw[2], int):
        seat_no, tile_code, seq = raw
        if isinstance(seat_no, int) and isinstance(tile_code, str):
            return (seq, tile_code, seat_no)
    return None


def _remembered_matches(
    snapshot: ParsedSnapshot, remembered: Tuple[int, int, str, int]
) -> bool:
    """跨重建触发弃牌记忆与当前快照是否一致（第三级验证口径）。

    验证条件（全部满足才采用记忆）：
    - 记忆局号与快照 round_no 一致（防串局）；
    - 快照处于 response_* 阶段（调用方已保证，双保险）；
    - 快照 last_discard 为纯牌码形态且牌码与记忆一致（无牌码证据
      （last_discard=None）时不得采用记忆——诚实退化）；
    - 弃牌者座位一致：快照 turn 即弃牌者座位（响应阶段语义，
      v8 fixture state_response_snapshot_peng.json 实证：response_peng
      下 turn=1 且 last_discard.seat=1），记忆第 4 元素（写回时取自
      事件流/结构化弃牌的座位）必须与之一致——跨座同码再弃（Expert
      wv6 复现的 key 碰撞：同局他座再弃同码且期间清史）在此被挡下，
      降级 tier-4（快照 seq + 审计提示），两物理窗口不碰撞。

    刻意不做牌河交叉验证：测试房实测牌河末张与 last_discard 存在
    不一致样本（last_discard_projection_note 证据），牌河交叉会误伤
    记忆，反而破坏身份稳定；牌码+座位一致性已足以区分"同一弃牌"与
    "他家新弃牌"。已知残余：同座同码再弃（同一弃牌者两轮弃同码且
    期间发生清史重建）在纯牌码形态下与"pass 推进的同一弃牌"信息
    不可分（官方未提供结构化序号），记忆仍会命中旧 seq——方向保守
    （窗口抑制=欠交付、官方超时兜底，绝不双投/重复行动）；彻底消除
    需官方 last_discard 携带序号或 SSE 接入后的水位对齐（R2 附注）。
    """

    if remembered[0] != snapshot.round_no:
        return False
    if snapshot.phase not in _RESPONSE_PHASES:
        return False
    raw = snapshot.last_discard
    if not isinstance(raw, str) or raw != remembered[2]:
        return False
    return remembered[3] == snapshot.turn


def _response_trigger(
    snapshot: ParsedSnapshot,
    event_stream_discard: Optional[Tuple[int, str, int]],
    remembered_trigger: Optional[Tuple[int, int, str, int]],
) -> Tuple[int, Optional[str], Optional[Tuple[int, str, int]]]:
    """响应窗口触发弃牌的四级解析；返回 (trigger_seq, 审计提示, 弃牌事实)。

    - 第一级：比较事件流最近弃牌与结构化 last_discard，采用较新的官方 seq；
      纯牌码快照只采用座位、牌码匹配的历史弃牌或快照后的新事件；
    - 第二级：快照结构化 last_discard 携带的官方弃牌 seq（全量重建后
      唯一存活于快照内的权威来源）；
    - 第三级：跨重建存活的触发弃牌记忆（纯牌码 last_discard 场景的
      身份稳定来源，见 _remembered_matches 验证口径）；
    - 第四级：退回快照 seq + 审计提示——响应窗口走满期间他家 pass 会
      推进快照 seq，此级只能保证构造成功，不代表身份稳定（R2 残留风险，
      提示必须进审计）。
    """

    structured = _structured_last_discard(snapshot)
    if event_stream_discard is not None:
        # 同单局刷新保留历史后，末条弃牌可能比快照中的新弃牌旧。结构化
        # 官方 seq 不得被保留历史覆盖；真正更新的增量仍优先于旧快照。
        if structured is not None:
            if structured[0] >= event_stream_discard[0]:
                return structured[0], None, structured
            return event_stream_discard[0], None, event_stream_discard
        raw = snapshot.last_discard
        if event_stream_discard[0] > snapshot.seq or (
            isinstance(raw, str)
            and raw == event_stream_discard[1]
            and snapshot.turn == event_stream_discard[2]
        ):
            return event_stream_discard[0], None, event_stream_discard
    if structured is not None:
        return structured[0], None, structured
    if remembered_trigger is not None and _remembered_matches(snapshot, remembered_trigger):
        return (
            remembered_trigger[1],
            None,
            (remembered_trigger[1], remembered_trigger[2], remembered_trigger[3]),
        )
    # F1（2026-09-05 取证修复）：tier-4 也回写弃牌事实——窗口出生时的
    # 快照 seq 即触发弃牌 seq（实测出生快照 seq=2=弃牌事件 seq），把它连同
    # 牌码与弃牌者座位写入跨重建记忆后，后续快照 seq 随 pass 推进时 tier-3
    # 命中恒定键，不再漂移成"新窗口"（重复提交根治的主路径）。
    birth_fact = (
        (snapshot.seq, raw_ld, snapshot.turn)
        if isinstance(raw_ld := snapshot.last_discard, str)
        else None
    )
    return snapshot.seq, (
        "response 阶段缺少可解析的触发弃牌序号（事件历史为空、last_discard 无结构化序号、"
        "跨重建记忆缺失或验证不通过），WindowKey.trigger_seq 退化为快照 seq={0}；"
        "出生快照事实已回写跨重建记忆（F1），后续派生按 tier-3 恒定".format(snapshot.seq)
    ), birth_fact


def detect_window(
    snapshot: ParsedSnapshot,
    timing: TimingConfig,
    game_id: str,
    *,
    event_stream_discard: Optional[Tuple[int, str, int]] = None,
    remembered_trigger: Optional[Tuple[int, int, str, int]] = None,
) -> Optional[DetectedWindow]:
    """按官方动作判定下限（API 文档 §2.4）识别是否轮到本座行动。

    只判定"是否有动作权"，不判定具体合法动作——合法性属于 hangma 规则模块。
    窗口身份（WindowKey.trigger_seq 即"触发本窗口的官方事件序号"）：

    - draw 窗口：触发事件是本人摸牌，使用快照权威 seq（现状已稳定）。
    - response_peng/response_chi 窗口：触发事件是他人弃牌，按四级解析
      （比较事件流与结构化 last_discard -> 跨重建记忆 -> 快照 seq），
      详见 _response_trigger；解析命中时 trigger_discard 返回弃牌事实，
      供 sync_state 更新跨重建记忆。
    """

    seat = snapshot.seat
    if seat < 0:
        return None  # 观赛视角无动作权
    note: Optional[str] = None
    trigger_discard: Optional[Tuple[int, str, int]] = None
    if snapshot.phase == "draw" and snapshot.turn == seat:
        phase, timeout = WindowPhase.DRAW, timing.discard_timeout_sec
        trigger_seq = snapshot.seq
    elif snapshot.phase == "response_peng" and seat in snapshot.responding_seats:
        phase, timeout = WindowPhase.RESPONSE_PENG, timing.peng_timeout_sec
        trigger_seq, note, trigger_discard = _response_trigger(
            snapshot, event_stream_discard, remembered_trigger
        )
    elif snapshot.phase == "response_chi" and seat in snapshot.responding_seats:
        phase, timeout = WindowPhase.RESPONSE_CHI, timing.chi_timeout_sec
        trigger_seq, note, trigger_discard = _response_trigger(
            snapshot, event_stream_discard, remembered_trigger
        )
    else:
        return None
    return DetectedWindow(
        window_key=WindowKey(
            game_id=game_id,
            round_no=snapshot.round_no,
            trigger_seq=trigger_seq,
            phase=phase,
            seat=seat,
        ),
        timeout_seconds=timeout,
        trigger_projection_note=note,
        trigger_discard=trigger_discard,
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
    catch_play 参数是规则源根据圈主身份得到的本座摸切限制，
    不能直接传官方 god.catch_play 全局标记；圈主可手切。
    """

    if isinstance(action, Discard):
        # 官方快照把刚摸的牌单列在 drawn_tile，且实测 my_hand 已并入该牌
        # （tests/fixtures/official/captures/state-draw-phase-t_714a42392cba.json，
        # 2026-09-04 实测抓取）：kernel 契约要求 my_hand 保留官方原样（顺序与
        # 内容），双计口径由 hangma 引擎按张数归一化（见
        # doc/implementation/notes/rules-hu-gate-and-win-detection.md）；
        # 此处出牌合法性按 hand ∪ {drawn_tile} 并集判定，两种官方形态都
        # 不会拒绝打刚摸的牌
        available = set(hand) | ({drawn_tile} if drawn_tile is not None else set())
        if catch_play:
            # 已由规则源确认本座受摸切限制；圈主不进入此分支。
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
