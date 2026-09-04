"""投影层测试：DTO 转内部类型、信息权限、窗口判定与动作请求体。"""
from __future__ import annotations

import pytest

from hangma_bot.adapters.official import projector
from hangma_bot.adapters.official.dto import parse_snapshot, parse_state_response
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

from _official_testkit import TIMING, load_fixture


def _snapshot(name: str):
    doc = load_fixture(name)
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
