"""投影层测试：DTO 转内部类型、信息权限、窗口判定与动作请求体。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hangma_bot.adapters.official import projector
from hangma_bot.adapters.official.dto import parse_snapshot, parse_state_response
from hangma_bot.adapters.official.errors import DtoError
from hangma_bot.kernel.actions import (
    Chi,
    Discard,
    Gang,
    GangKind,
    Hu,
    Pass,
    Peng,
    Tile,
    WindowPhase,
)
from hangma_bot.kernel.config import TimingConfig
from hangma_bot.kernel.observation import PublicDiscard

from _official_testkit import TIMING, load_fixture

_CAPTURES = Path(__file__).parents[2] / "fixtures" / "official" / "captures"


def _snapshot(name: str):
    doc = load_fixture(name)
    return parse_snapshot(doc["snapshot"], doc.get("seq"))


def _load_capture(name: str) -> dict:
    """读取真实测试房间捕获（官方纯牌码 last_discard 样本）。"""

    return json.loads((_CAPTURES / name).read_text(encoding="utf-8"))


def _capture_snapshot(name: str):
    doc = _load_capture(name)
    return parse_snapshot(doc["snapshot"], doc.get("seq"))


def test_draw_snapshot_projects_observation() -> None:
    """全量快照投影：字段顺序、座位向量与财神状态正确。"""

    snap = _snapshot("state_response_snapshot_draw.json")
    obs = projector.observation(snap, (), "g_room1_batch1")
    assert obs.game_id == "g_room1_batch1"
    assert obs.seat == 2 and obs.round_no == 1 and obs.snapshot_seq == 101
    assert obs.my_hand[0] == Tile("1w")  # 保留官方返回顺序
    assert obs.drawn_tile == Tile("5w")
    assert obs.hand_counts == (10, 10, 14, 10)
    assert obs.scores == (10, 4, -2, -12)
    assert obs.last_discard is not None and obs.last_discard.tile == Tile("9t")
    assert obs.rule_state.wealth_god == Tile("白")  # 白板是财神
    assert obs.rule_state.catch_play is False
    # 副露座位回填：座位 1 碰、座位 3 吃
    assert obs.melds[1][0].kind == "peng" and obs.melds[1][0].seat == 1
    assert obs.melds[3][0].kind == "chi" and obs.melds[3][0].from_seat == 0


def test_observation_has_no_hidden_information_surface() -> None:
    """信息权限：PlayerObservation 类型面不出现他家手牌/牌墙/赛后结果字段。"""

    field_names = {f for f in type(_obs_fields()).__dataclass_fields__}
    forbidden = {"other_hands", "wall", "final_result", "opponent_tiles"}
    assert forbidden & field_names == set()


def _obs_fields():
    from hangma_bot.kernel.observation import PlayerObservation

    snap = _snapshot("state_response_snapshot_draw.json")
    return projector.observation(snap, (), "g")


def test_detect_window_draw_phase() -> None:
    snap = _snapshot("state_response_snapshot_draw.json")
    detected = projector.detect_window(snap, TIMING, "g_room1_batch1")
    assert detected is not None
    assert detected.window_key.phase is WindowPhase.DRAW
    assert detected.window_key.trigger_seq == 101
    assert detected.timeout_seconds == 3.0


def test_detect_window_response_peng() -> None:
    snap = _snapshot("state_response_snapshot_peng.json")
    detected = projector.detect_window(snap, TIMING, "g")
    assert detected is not None
    assert detected.window_key.phase is WindowPhase.RESPONSE_PENG
    assert detected.timeout_seconds == 1.0


def test_detect_window_response_trigger_stable_when_only_snapshot_seq_changes() -> None:
    """R2 最小复现回归：仅快照 seq 变化（他家 pass 推进 182->185）时 WindowKey 不变。

    响应窗口的触发事件是弃牌（结构化 last_discard seq=182），不是快照本身；
    同一物理窗口绝不因 seq 推进产生第二个 WindowKey。
    """

    doc = load_fixture("state_response_snapshot_peng.json")
    doc["snapshot"]["last_discard"] = {"seat": 1, "tile": "2w", "seq": 182}
    doc["snapshot"]["responding_seats"] = [1, 2]
    first = projector.detect_window(
        parse_snapshot(doc["snapshot"], 182), TIMING, "g"
    )
    doc["seq"] = 185  # 响应窗口走满期间他家 pass 推进权威 seq
    second = projector.detect_window(
        parse_snapshot(doc["snapshot"], 185), TIMING, "g"
    )
    assert first is not None and second is not None
    assert first.window_key == second.window_key
    assert first.window_key.trigger_seq == 182  # 触发弃牌事件序号，非快照 seq


def test_detect_window_response_event_stream_trigger_wins() -> None:
    """事件流解析出的触发弃牌事实优先于结构化 last_discard（设计主源）。"""

    doc = load_fixture("state_response_snapshot_peng.json")
    doc["snapshot"]["last_discard"] = {"seat": 1, "tile": "2w", "seq": 180}
    snap = parse_snapshot(doc["snapshot"], doc.get("seq"))
    detected = projector.detect_window(
        snap, TIMING, "g", event_stream_discard=(182, "2w", 1)
    )
    assert detected is not None and detected.window_key.trigger_seq == 182
    assert detected.trigger_projection_note is None
    assert detected.trigger_discard == (182, "2w", 1)


def test_detect_window_response_bare_last_discard_falls_back_with_note() -> None:
    """纯牌码 last_discard + 无事件流序号且无记忆：退回快照 seq 并留审计提示。"""

    doc = load_fixture("state_response_snapshot_peng.json")
    doc["snapshot"]["last_discard"] = "2w"
    doc["snapshot"]["turn"] = 1
    snap = parse_snapshot(doc["snapshot"], 185)
    detected = projector.detect_window(snap, TIMING, "g")
    assert detected is not None
    assert detected.window_key.trigger_seq == 185
    assert detected.trigger_projection_note is not None
    assert detected.trigger_discard is None


def test_detect_window_remembered_trigger_used_for_bare_last_discard() -> None:
    """纯牌码 last_discard：跨重建记忆（局号/阶段/牌码验证通过）提供稳定触发序号。"""

    doc = load_fixture("state_response_snapshot_peng.json")
    doc["snapshot"]["last_discard"] = "6w"  # 纯牌码形态（测试房实测）
    doc["snapshot"]["turn"] = 0
    snap = parse_snapshot(doc["snapshot"], 185)
    detected = projector.detect_window(
        snap, TIMING, "g", remembered_trigger=(1, 182, "6w", 0)
    )
    assert detected is not None
    assert detected.window_key.trigger_seq == 182  # 记忆序号，而非快照 seq=185
    assert detected.trigger_projection_note is None
    assert detected.trigger_discard == (182, "6w", 0)


def test_detect_window_remembered_trigger_round_mismatch_rejected() -> None:
    """记忆局号与快照不一致：不得串局，退回快照 seq + 审计提示。"""

    doc = load_fixture("state_response_snapshot_peng.json")
    doc["snapshot"]["last_discard"] = "6w"
    doc["snapshot"]["turn"] = 0
    doc["snapshot"]["round_no"] = 2
    snap = parse_snapshot(doc["snapshot"], 185)
    detected = projector.detect_window(
        snap, TIMING, "g", remembered_trigger=(1, 182, "6w", 0)
    )
    assert detected is not None
    assert detected.window_key.trigger_seq == 185
    assert detected.trigger_projection_note is not None
    assert detected.trigger_discard is None


def test_detect_window_remembered_trigger_tile_mismatch_falls_back() -> None:
    """记忆牌码与快照纯牌码 last_discard 不一致：诚实退化 + 审计提示。"""

    doc = load_fixture("state_response_snapshot_peng.json")
    doc["snapshot"]["last_discard"] = "8w"  # 与记忆 "6w" 不一致
    doc["snapshot"]["turn"] = 0
    snap = parse_snapshot(doc["snapshot"], 185)
    detected = projector.detect_window(
        snap, TIMING, "g", remembered_trigger=(1, 182, "6w", 0)
    )
    assert detected is not None
    assert detected.window_key.trigger_seq == 185
    assert detected.trigger_projection_note is not None
    assert detected.trigger_discard is None


def test_detect_window_none_when_no_right_to_act() -> None:
    """他人回合或本人不在响应座位时不开窗。"""

    doc = load_fixture("state_response_snapshot_draw.json")
    doc["snapshot"]["turn"] = 0  # 他人回合
    snap = parse_snapshot(doc["snapshot"], doc["seq"])
    assert projector.detect_window(snap, TIMING, "g") is None

    doc = load_fixture("state_response_snapshot_peng.json")
    doc["snapshot"]["responding_seats"] = [3]  # 本人无响应权
    snap = parse_snapshot(doc["snapshot"], doc["seq"])
    assert projector.detect_window(snap, TIMING, "g") is None


def test_detect_window_spectator_is_none() -> None:
    doc = load_fixture("state_response_snapshot_draw.json")
    doc["snapshot"]["seat"] = -1
    snap = parse_snapshot(doc["snapshot"], doc["seq"])
    assert projector.detect_window(snap, TIMING, "g") is None


class TestLastDiscardReconstruction:
    """官方实测纯牌码 last_discard 在响应阶段的 (座位,牌码,seq) 重建。

    回归背景：真实对局（captures/state-draw-phase-t_714a42392cba.json）
    last_discard 是纯牌码字符串，旧 dto 丢弃该形态使投影为 None，响应窗口
    只剩过。依据：API 文档 §2.3 字段表 `turn`=当前行动座位 + §5.3 响应
    时序（弃牌后行动权停留在弃牌者，响应走满后下家才摸牌）。
    """

    def test_dto_preserves_bare_tile_code(self) -> None:
        snap = _capture_snapshot("state-draw-phase-t_714a42392cba.json")
        assert snap.last_discard == "6w"

    def test_draw_phase_does_not_fabricate_last_discard(self) -> None:
        # draw 阶段 turn=0 已转入下家（牌河末张 "6w" 属座位 3）：不重建；
        # 样本 drawn_tile="1b" 非空，drawn_tile 投影不受影响。
        snap = _capture_snapshot("state-draw-phase-t_714a42392cba.json")
        obs = projector.observation(snap, (), "g")
        assert obs.last_discard is None
        assert obs.drawn_tile == Tile("1b")

    def test_finished_phase_keeps_none(self) -> None:
        snap = _capture_snapshot("state-finished-phase-t_714a42392cba.json")
        assert snap.last_discard == "3b"
        assert projector.observation(snap, (), "g").last_discard is None

    def test_response_peng_reconstructs_full_discard(self) -> None:
        doc = _load_capture("state-draw-phase-t_714a42392cba.json")
        body = dict(doc["snapshot"])
        body.update(
            phase="response_peng",
            turn=3,  # 座位 3 牌河末张即 "6w"：turn 即弃牌者
            responding_seats=[0, 1, 2],
            drawn_tile="",
        )
        snap = parse_snapshot(body, doc["seq"])
        obs = projector.observation(snap, (), "g")
        assert obs.last_discard == PublicDiscard(seat=3, tile=Tile("6w"), seq=doc["seq"])
        discard, notes = projector.project_last_discard(snap)
        assert discard is not None and notes == ()

    def test_response_chi_reconstructs_full_discard(self) -> None:
        doc = _load_capture("state-draw-phase-t_714a42392cba.json")
        body = dict(doc["snapshot"])
        body.update(
            phase="response_chi",
            turn=1,  # 座位 1 牌河末张即 "5w"
            responding_seats=[0, 2, 3],
            drawn_tile="",
        )
        body["last_discard"] = "5w"
        snap = parse_snapshot(body, doc["seq"])
        obs = projector.observation(snap, (), "g")
        assert obs.last_discard == PublicDiscard(seat=1, tile=Tile("5w"), seq=doc["seq"])
        assert projector.project_last_discard(snap)[1] == ()

    def test_river_mismatch_still_uses_turn_with_note(self) -> None:
        # 交叉验证失败：turn=0 但座位 0 牌河末张 "4w" != "6w"。按响应阶段
        # 语义（官方保证存在待认领弃牌）仍以 turn 为座位，绝不返回 None。
        doc = _load_capture("state-draw-phase-t_714a42392cba.json")
        body = dict(doc["snapshot"])
        body.update(
            phase="response_peng", turn=0, responding_seats=[1, 2, 3], drawn_tile=""
        )
        snap = parse_snapshot(body, doc["seq"])
        obs = projector.observation(snap, (), "g")
        assert obs.last_discard == PublicDiscard(seat=0, tile=Tile("6w"), seq=doc["seq"])
        discard, notes = projector.project_last_discard(snap)
        assert discard is not None and discard.seat == 0
        assert len(notes) == 1 and "turn" in notes[0]

    def test_bare_tile_code_invalid_raises_dto_error(self) -> None:
        doc = _load_capture("state-draw-phase-t_714a42392cba.json")
        body = dict(doc["snapshot"])
        body["last_discard"] = "10w"
        with pytest.raises(DtoError):
            parse_snapshot(body, doc["seq"])

    def test_structured_form_unchanged(self) -> None:
        # 结构化 (seat, tile, seq) 形态保持既有投影行为（各阶段通用）。
        doc = load_fixture("state_response_snapshot_peng.json")
        snap = parse_snapshot(doc["snapshot"], doc.get("seq"))
        obs = projector.observation(snap, (), "g")
        assert obs.last_discard == PublicDiscard(seat=1, tile=Tile("2w"), seq=119)
        assert projector.project_last_discard(snap) == (obs.last_discard, ())


class TestActionRequestBody:
    """动作请求体构造：合法动作可构造，非法组合返回 None。"""

    def test_discard(self) -> None:
        hand = (Tile("1w"), Tile("2w"))
        body = projector.action_request_body(
            Discard(Tile("1w")), last_discard_tile=None, hand=hand
        )
        assert body == {"action": "discard", "tile": "1w"}

    def test_discard_tile_not_in_hand_rejected(self) -> None:
        assert projector.action_request_body(
            Discard(Tile("9t")), last_discard_tile=None, hand=(Tile("1w"),)
        ) is None

    def test_catch_play_only_drawn_tile(self) -> None:
        """抓打圈硬约束：只能打刚摸到的牌（API 文档 §5.4）。"""

        hand = (Tile("1w"), Tile("白"))
        assert projector.action_request_body(
            Discard(Tile("1w")),
            last_discard_tile=None,
            hand=hand,
            drawn_tile=Tile("白"),
            catch_play=True,
        ) is None
        assert projector.action_request_body(
            Discard(Tile("白")),
            last_discard_tile=None,
            hand=hand,
            drawn_tile=Tile("白"),
            catch_play=True,
        ) == {"action": "discard", "tile": "白"}

    def test_peng_must_match_last_discard(self) -> None:
        assert projector.action_request_body(
            Peng(Tile("2w")),
            last_discard_tile=Tile("2w"),
            hand=(),
            phase=WindowPhase.RESPONSE_PENG,
        ) == {"action": "peng", "tile": "2w"}
        assert projector.action_request_body(
            Peng(Tile("3w")),
            last_discard_tile=Tile("2w"),
            hand=(),
            phase=WindowPhase.RESPONSE_PENG,
        ) is None
        # 碰只可能在碰响应窗口提出（防御与吃对齐）
        assert projector.action_request_body(
            Peng(Tile("2w")),
            last_discard_tile=Tile("2w"),
            hand=(),
            phase=WindowPhase.DRAW,
        ) is None

    def test_chi_body_and_mismatch(self) -> None:
        chi = Chi((Tile("1w"), Tile("2w"), Tile("3w")))
        body = projector.action_request_body(
            chi,
            last_discard_tile=Tile("3w"),
            hand=(),
            phase=WindowPhase.RESPONSE_CHI,
        )
        assert body == {"action": "chi", "tile": "3w", "tiles": ["1w", "2w"]}
        # 组合不含被吃牌 → 拒绝构造
        assert projector.action_request_body(
            chi, last_discard_tile=Tile("4w"), hand=(), phase=WindowPhase.RESPONSE_CHI
        ) is None
        # 吃只允许在吃窗口提出
        assert projector.action_request_body(
            chi, last_discard_tile=Tile("3w"), hand=(), phase=WindowPhase.DRAW
        ) is None

    def test_gang_and_simple_actions(self) -> None:
        body = projector.action_request_body(
            Gang(Tile("白"), GangKind.CONCEALED), last_discard_tile=None, hand=()
        )
        assert body == {"action": "gang", "tile": "白"}
        exposed = projector.action_request_body(
            Gang(Tile("6w"), GangKind.EXPOSED),
            last_discard_tile=Tile("6w"),
            hand=(),
            phase=WindowPhase.RESPONSE_PENG,
        )
        assert exposed == {"action": "gang", "tile": "6w"}
        assert projector.action_request_body(
            Gang(Tile("6w"), GangKind.EXPOSED),
            last_discard_tile=Tile("6w"),
            hand=(),
            phase=WindowPhase.DRAW,  # 明杠不可能在 draw 窗口
        ) is None
        assert projector.action_request_body(Hu(), last_discard_tile=None, hand=()) == {"action": "hu"}
        assert projector.action_request_body(
            Pass(), last_discard_tile=None, hand=(), phase=WindowPhase.RESPONSE_CHI
        ) == {"action": "pass", "tile": ""}
        # 官方 draw 窗没有 pass 动作（API 文档 §2.4）
        assert projector.action_request_body(
            Pass(), last_discard_tile=None, hand=(), phase=WindowPhase.DRAW
        ) is None
