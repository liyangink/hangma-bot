"""同步状态机测试：重复 seq、缺口、gap、未知事件与全量替换。"""
from __future__ import annotations

from hangma_bot.adapters.official.dto import ParsedEvent
from hangma_bot.adapters.official.sync_state import (
    ProtocolSyncState,
    SyncDecision,
)

from _official_testkit import TIMING, load_fixture


def _snapshot(name: str = "state_response_snapshot_draw.json") -> None:
    from hangma_bot.adapters.official.dto import parse_snapshot

    doc = load_fixture(name)
    return parse_snapshot(doc["snapshot"], doc.get("seq"))


def _event(seq: int, type_: str = "tile_discarded") -> ParsedEvent:
    return ParsedEvent(seq=seq, type=type_, seat=0, tiles=("1w",), occurred_at_unix_sec=1756771200)


def test_full_snapshot_replaces_state() -> None:
    state = ProtocolSyncState("g", TIMING)
    state.apply_full_snapshot(_snapshot())
    assert state.has_snapshot and state.last_seq == 101
    assert state.current_observation() is not None

    # 第二次全量替换：序号回退也整体替换（快照是规范真相）
    doc = load_fixture("state_response_snapshot_draw.json")
    doc["seq"] = 90
    from hangma_bot.adapters.official.dto import parse_snapshot

    state.apply_full_snapshot(parse_snapshot(doc["snapshot"], doc["seq"]))
    assert state.last_seq == 90


def test_consecutive_events_accepted() -> None:
    state = ProtocolSyncState("g", TIMING)
    state.apply_full_snapshot(_snapshot())
    result = state.apply_events((_event(102), _event(103)))
    assert result.decision is SyncDecision.ACCEPTED
    assert state.last_seq == 103
    assert len(state.current_observation().public_history) == 2


def test_duplicate_seq_ignored_idempotently() -> None:
    state = ProtocolSyncState("g", TIMING)
    state.apply_full_snapshot(_snapshot())
    result = state.apply_events((_event(101), _event(102), _event(102)))
    assert result.decision is SyncDecision.ACCEPTED
    assert result.ignored_duplicate_seqs == (101, 102)
    assert state.last_seq == 102


def test_seq_gap_triggers_rebuild() -> None:
    state = ProtocolSyncState("g", TIMING)
    state.apply_full_snapshot(_snapshot())
    result = state.apply_events((_event(104),))  # 102/103 缺失
    assert result.decision is SyncDecision.NEEDS_REBUILD
    assert result.reasons[0].startswith("seq_gap:")


def test_explicit_gap_flag_triggers_rebuild() -> None:
    state = ProtocolSyncState("g", TIMING)
    state.apply_full_snapshot(_snapshot())
    result = state.apply_events((_event(102),), gap=True)
    assert result.decision is SyncDecision.NEEDS_REBUILD
    assert result.reasons == ("gap=true",)


def test_events_without_snapshot_rebuild() -> None:
    state = ProtocolSyncState("g", TIMING)
    assert state.apply_events((_event(1),)).decision is SyncDecision.NEEDS_REBUILD


def test_unknown_event_rebuilds_once_then_learned() -> None:
    """未知关键事件重建一次；学习后同类型不再触发重建风暴。"""

    state = ProtocolSyncState("g", TIMING)
    state.apply_full_snapshot(_snapshot())
    first = state.apply_events((_event(102, "future_event"),))
    assert first.decision is SyncDecision.NEEDS_REBUILD
    assert first.reasons[0] == "unknown_event:future_event"

    state.note_rebuild_absorbed("future_event")
    second = state.apply_events((_event(102, "future_event"),))
    assert second.decision is SyncDecision.ACCEPTED
    assert state.last_seq == 102


def test_learned_unknown_event_type_requires_authoritative_refresh():
    """P2-N3 回归：已学习忽略的未知事件类型行为不可知，每次出现都必须
    触发权威刷新（防止手牌/窗口状态静默漂移），但不触发重建风暴。"""

    state = ProtocolSyncState("g", TIMING)
    state.apply_full_snapshot(_snapshot())
    assert not state.events_need_authoritative_refresh(
        (_event(102, "tile_drawn"),)
    )  # 已知可忽略行（他家摸牌）不受影响
    state.note_rebuild_absorbed("future_event")
    assert state.events_need_authoritative_refresh((_event(102, "future_event"),))
    # 学习前（首见）该类型在 apply 层走 NEEDS_REBUILD，不进入本谓词
    other = ProtocolSyncState("g", TIMING)
    other.apply_full_snapshot(_snapshot())
    assert not other.events_need_authoritative_refresh((_event(102, "future_event"),))
    assert other.apply_events(
        (_event(102, "future_event"),)
    ).decision is SyncDecision.NEEDS_REBUILD


def test_game_ended_marks_finished() -> None:
    state = ProtocolSyncState("g", TIMING)
    state.apply_full_snapshot(_snapshot())
    state.apply_events((_event(102, "game_ended"),))
    assert state.finished is True

def _snapshot_with(name="state_response_snapshot_peng.json", **overrides):
    from hangma_bot.adapters.official.dto import parse_snapshot

    doc = load_fixture(name)
    body = dict(doc["snapshot"])
    body.update(overrides)
    seq = doc.get("seq")
    return parse_snapshot(body, seq)


def _snapshot_with(name="state_response_snapshot_peng.json", seq=None, **overrides):
    from hangma_bot.adapters.official.dto import parse_snapshot

    doc = load_fixture(name)
    body = dict(doc["snapshot"])
    body.update(overrides)
    top_seq = doc.get("seq") if seq is None else seq
    return parse_snapshot(body, top_seq)


def test_pass_event_is_known_and_does_not_rebuild():
    """R3 回归：pass 是官方常规事件，应用后不得触发未知事件重建。

    实测牌谱中响应窗口走满期间他家 pass 连续推进权威 seq（182->183/184/185）；
    缺该类型会被当作未知关键事件反复全量重建（抖动风暴）。
    """

    state = ProtocolSyncState("g", TIMING)
    state.apply_full_snapshot(_snapshot_with(seq=182))
    result = state.apply_events((_event(183, "pass"), _event(184, "pass"), _event(185, "pass")))
    assert result.decision is SyncDecision.ACCEPTED
    assert state.last_seq == 185
    assert len(state.current_observation().public_history) == 3


def test_response_window_trigger_from_event_stream():
    """R2 回归：响应窗口 trigger_seq 优先取事件流最近一次 tile_discarded 的 seq。

    快照权威 seq=185 且结构化 last_discard 序号（119）与事件流弃牌（186）不同：
    事件流最近弃牌优先（设计主源）；触发序号绝不再直接用快照 seq，
    同一物理窗口不因 pass 推进 seq 产生新 WindowKey。
    """

    from hangma_bot.kernel.actions import WindowPhase

    state = ProtocolSyncState("g", TIMING)
    state.apply_full_snapshot(_snapshot_with(seq=185))
    state.apply_events((_event(186, "tile_discarded"), _event(187, "pass")))
    window = state.current_window()
    assert window is not None and window.window_key.phase is WindowPhase.RESPONSE_PENG
    assert window.window_key.trigger_seq == 186
    assert window.trigger_projection_note is None


def test_response_window_trigger_from_structured_last_discard_after_rebuild():
    """全量重建清空事件历史后，结构化 last_discard 的官方弃牌 seq 保持身份稳定。"""

    from hangma_bot.kernel.actions import WindowPhase

    state = ProtocolSyncState("g", TIMING)
    # 快照权威 seq=185（他家 pass 已推进），结构化 last_discard 携带弃牌 seq=119
    state.apply_full_snapshot(_snapshot_with(seq=185))
    window = state.current_window()
    assert window is not None and window.window_key.phase is WindowPhase.RESPONSE_PENG
    assert window.window_key.trigger_seq == 119
    assert window.trigger_projection_note is None


def test_response_window_trigger_fallback_to_snapshot_seq_with_note():
    """事件历史空 + 纯牌码 last_discard：退回快照 seq 并带审计提示（同款降级）。"""

    from hangma_bot.kernel.actions import WindowPhase

    state = ProtocolSyncState("g", TIMING)
    state.apply_full_snapshot(_snapshot_with(seq=185, last_discard="2w", turn=1))
    window = state.current_window()
    assert window is not None and window.window_key.phase is WindowPhase.RESPONSE_PENG
    assert window.window_key.trigger_seq == 185  # 退化兜底：仅审计关联
    assert window.trigger_projection_note is not None
    assert "185" in window.trigger_projection_note

def _discard_event(seq: int, tile: str, seat: int) -> ParsedEvent:
    """构造带牌码与座位的官方弃牌增量事件。"""

    return ParsedEvent(
        seq=seq, type="tile_discarded", seat=seat, tiles=(tile,),
        occurred_at_unix_sec=1756771200,
    )


def test_memory_seeded_from_events_survives_rebuild():
    """R2 加固 (a)：事件流弃牌写入跨重建记忆，纯牌码快照身份稳定。

    测试房实测响应阶段 last_discard 为纯牌码字符串：每次交付前全量重建
    清空事件历史，旧实现退回快照 seq 会把同一物理窗口拆成多个 WindowKey
    （seq 182->185）。记忆由 tile_discarded 事件写入、apply_full_snapshot
    不清空，seq 推进后仍解析出同一触发序号。
    """

    from hangma_bot.kernel.actions import WindowPhase

    state = ProtocolSyncState("g", TIMING)
    state.apply_full_snapshot(
        _snapshot_with(seq=180, phase="draw", turn=0, last_discard=None)
    )
    state.apply_events((_discard_event(181, "6w", 1),))
    # 第一次全量重建：事件历史清空，纯牌码 last_discard，记忆命中
    state.apply_full_snapshot(_snapshot_with(seq=182, last_discard="6w", turn=1))
    first = state.current_window()
    assert first is not None and first.window_key.phase is WindowPhase.RESPONSE_PENG
    assert first.window_key.trigger_seq == 181
    # 他家 pass 推进权威 seq 到 185：同一物理窗口，WindowKey 不变
    state.apply_full_snapshot(_snapshot_with(seq=185, last_discard="6w", turn=1))
    second = state.current_window()
    assert second is not None and second.window_key == first.window_key
    assert second.trigger_projection_note is None


def test_new_discard_overwrites_memory_new_window():
    """R2 加固 (b)：新弃牌事件覆盖记忆，产出新 WindowKey（新物理窗口）。"""

    from hangma_bot.kernel.actions import WindowPhase

    state = ProtocolSyncState("g", TIMING)
    # 他家 pass 已把权威 seq 推进到 185；结构化弃牌序号仍为 181
    state.apply_full_snapshot(
        _snapshot_with(seq=185, last_discard={"seat": 1, "tile": "6w", "seq": 181})
    )
    first = state.current_window()
    assert first is not None and first.window_key.trigger_seq == 181
    # 新弃牌（座位 2 弃 3b，seq 连续）→ 记忆覆盖
    state.apply_events((_discard_event(186, "3b", 2),))
    state.apply_full_snapshot(_snapshot_with(seq=188, last_discard="3b", turn=2))
    second = state.current_window()
    assert second is not None and second.window_key.phase is WindowPhase.RESPONSE_PENG
    assert second.window_key.trigger_seq == 186  # 新触发弃牌序号
    assert second.window_key != first.window_key
    assert second.trigger_projection_note is None


def test_structured_last_discard_seeds_memory_for_bare_snapshots():
    """R2 加固 (b)：三级解析命中（结构化）写回记忆，供后续纯牌码快照使用。"""

    from hangma_bot.kernel.actions import WindowPhase

    state = ProtocolSyncState("g", TIMING)
    state.apply_full_snapshot(
        _snapshot_with(seq=182, last_discard={"seat": 1, "tile": "6w", "seq": 181})
    )
    first = state.current_window()
    assert first is not None and first.window_key.trigger_seq == 181
    # 重建后官方改为纯牌码形态：记忆延续身份
    state.apply_full_snapshot(_snapshot_with(seq=185, last_discard="6w", turn=1))
    second = state.current_window()
    assert second is not None and second.window_key == first.window_key


def test_round_change_invalidates_memory_no_cross_round():
    """R2 加固 (c)：局号变化后记忆失效，不串局；退化到快照 seq + 提示。"""

    from hangma_bot.kernel.actions import WindowPhase

    state = ProtocolSyncState("g", TIMING)
    state.apply_full_snapshot(
        _snapshot_with(seq=182, last_discard={"seat": 1, "tile": "6w", "seq": 181})
    )
    first = state.current_window()
    assert first is not None and first.window_key.trigger_seq == 181
    state.apply_full_snapshot(
        _snapshot_with(seq=190, round_no=2, last_discard="6w", turn=1)
    )
    window = state.current_window()
    assert window is not None and window.window_key.round_no == 2
    assert window.window_key.trigger_seq == 190  # 记忆已失效：诚实退化
    assert window.trigger_projection_note is not None


def test_memory_tile_mismatch_falls_back_with_note():
    """R2 加固 (d)：记忆牌码与快照 last_discard 不一致：诚实退化 + 审计提示。"""

    from hangma_bot.kernel.actions import WindowPhase

    state = ProtocolSyncState("g", TIMING)
    state.apply_full_snapshot(
        _snapshot_with(seq=180, phase="draw", turn=0, last_discard=None)
    )
    state.apply_events((_discard_event(181, "6w", 1),))
    state.apply_full_snapshot(_snapshot_with(seq=185, last_discard="8w", turn=1))
    window = state.current_window()
    assert window is not None and window.window_key.phase is WindowPhase.RESPONSE_PENG
    assert window.window_key.trigger_seq == 185  # 记忆 "6w" != 快照 "8w"
    assert window.trigger_projection_note is not None
    assert "185" in window.trigger_projection_note





def test_memory_rejected_when_other_seat_discards_same_tile():
    """Expert major 回归：跨重建触发记忆必须校验弃牌者座位。

    序列：座位 1 弃 5w（seq 101，结构化 last_discard）→ 记忆写入
    (round, 101, "5w", seat=1) → 全量重建清空事件历史（409/gap）→
    座位 0 再弃 5w（seq 130，官方纯牌码形态、快照 turn=0）：
    修复前记忆只按"局号+牌码"命中 → 新窗 trigger_seq 误用 101，与
    已投递旧窗 WindowKey 完全碰撞（_delivered_windows/ActionGate 抑制
    → 整窗零投递，R2 exactly-once 欠交付方向）；修复后座位交叉校验
    不通过 → 降级 tier-4（快照 seq=130 + 审计提示），两窗不碰撞且
    新窗正常投递。
    """

    from hangma_bot.kernel.actions import WindowPhase

    state = ProtocolSyncState("g", TIMING)
    # 阶段 1：座位 1 结构化弃牌 5w@101 开启我方响应窗口 → 记忆写回
    state.apply_full_snapshot(
        _snapshot_with(
            seq=101, last_discard={"seat": 1, "tile": "5w", "seq": 101}, turn=1
        )
    )
    first = state.current_window()
    assert first is not None
    assert first.window_key.phase is WindowPhase.RESPONSE_PENG
    assert first.window_key.trigger_seq == 101
    # 阶段 2：重建清史后，他座（座位 0）再弃同码 5w（纯牌码形态）
    state.apply_full_snapshot(_snapshot_with(seq=130, last_discard="5w", turn=0))
    second = state.current_window()
    assert second is not None
    assert second.window_key.phase is WindowPhase.RESPONSE_PENG
    assert second.window_key.trigger_seq == 130  # 不再误用旧弃牌 seq=101
    assert second.window_key != first.window_key  # 两物理窗口不碰撞
    assert second.trigger_projection_note is not None  # tier-4 降级提示进审计
    assert "130" in second.trigger_projection_note


def test_memory_still_hits_when_same_seat_discards_same_tile_after_rebuild():
    """座位校验不误伤 R2 主场景：同座（同一次弃牌）清史重建后记忆继续命中。"""

    from hangma_bot.kernel.actions import WindowPhase

    state = ProtocolSyncState("g", TIMING)
    state.apply_full_snapshot(
        _snapshot_with(
            seq=101, last_discard={"seat": 1, "tile": "5w", "seq": 101}, turn=1
        )
    )
    first = state.current_window()
    assert first is not None and first.window_key.trigger_seq == 101
    # 同一弃牌、pass 推进水位后清史重建（纯牌码、turn 仍=弃牌者 1）
    state.apply_full_snapshot(_snapshot_with(seq=105, last_discard="5w", turn=1))
    second = state.current_window()
    assert second is not None
    assert second.window_key == first.window_key  # 身份稳定：同窗同 key
    assert second.trigger_projection_note is None


def test_incremental_draw_observation_keeps_counts_consistent() -> None:
    """N-2 回归：增量摸牌窗口的观察自洽性——快照 hand_counts[本人] 不含刚摸牌
    时，增量送达必须本人手数 +1、墙余 -1（否则 my_hand+drawn 与 hand_counts
    口径互相矛盾，污染牌效估算/审计快照）。"""

    from hangma_bot.adapters.official.dto import parse_snapshot

    doc = load_fixture("state_response_snapshot_draw.json")
    body = dict(doc["snapshot"])
    body["turn"] = 0  # 无窗基础快照（正常增量流程形态：本人弃牌后、下次摸牌前）
    body["drawn_tile"] = ""
    body["hand_counts"] = [10, 10, 13, 10]  # 本人(seat 2) 13 张：不含刚摸
    body["wall_remaining"] = 40
    state = ProtocolSyncState("g", TIMING)
    state.apply_full_snapshot(parse_snapshot(body, doc.get("seq")))
    state.apply_events(
        (
            _event(102),  # 他家弃牌（_event 默认 seat=0）
            ParsedEvent(
                seq=103, type="tile_drawn", seat=2, tiles=("7w",),
                occurred_at_unix_sec=1756771200,
            ),
        )
    )
    observation = state.incremental_draw_observation()
    assert observation is not None
    assert observation.hand_counts[2] == 14  # 含刚摸的 7w
    assert observation.remaining_tile_count == 39  # 墙余减 1
    assert observation.hand_counts[0] == 10  # 他家不变


def test_incremental_observation_counts_unchanged_when_base_already_drawn() -> None:
    """N-2 防御分支：基础快照已是本人摸牌形态（含 drawn）时不做 +1/-1。"""

    from hangma_bot.adapters.official.dto import parse_snapshot

    doc = load_fixture("state_response_snapshot_draw.json")
    state = ProtocolSyncState("g", TIMING)
    state.apply_full_snapshot(parse_snapshot(doc["snapshot"], doc.get("seq")))
    state.apply_events(
        (
            ParsedEvent(
                seq=102, type="tile_drawn", seat=2, tiles=("7w",),
                occurred_at_unix_sec=1756771200,
            ),
        )
    )
    observation = state.incremental_draw_observation()
    assert observation is not None
    # 基础快照 hand_counts[2]=14（官方含摸牌形态口径）：换牌等量，不再 +1
    assert observation.hand_counts[2] == 14
    assert observation.drawn_tile is not None and observation.drawn_tile.code == "7w"

