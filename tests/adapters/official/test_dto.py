"""官方 v8 报文解析测试：fixtures 全部可解析，breaking 版本被识别。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hangma_bot.adapters.official.dto import (
    KNOWN_GUIDE_VERSION,
    extract_error_code,
    parse_guide_version,
    parse_me,
    parse_rules_config,
    parse_state_response,
    parse_tournament_detail,
)
from hangma_bot.adapters.official.errors import DtoError

from _official_testkit import FIXTURE_DIR, load_fixture

REFERENCE_GUIDE_V8 = Path(__file__).parents[3] / "doc" / "references" / "official-guide-version-v8.json"
REFERENCE_GUIDE_V11 = Path(__file__).parents[3] / "doc" / "references" / "official-guide-version-v11.json"
REFERENCE_GUIDE_V14 = Path(__file__).parents[3] / "doc" / "references" / "official-guide-version-v14.json"
REFERENCE_GUIDE_V15 = Path(__file__).parents[3] / "doc" / "references" / "official-guide-version-v15.json"


def test_reference_guide_v8_snapshot_parses() -> None:
    """官方指南 v8 历史快照必须完整解析且无未知 breaking。"""

    doc = json.loads(REFERENCE_GUIDE_V8.read_text(encoding="utf-8"))
    parsed = parse_guide_version(doc)
    assert parsed.version == 8
    assert parsed.updated_at
    assert parsed.has_unknown_breaking_change is False


def test_reference_guide_v11_snapshot_parses() -> None:
    """已审查基线 v11 真实快照（2026-09-04 抓取）完整解析且无未知 breaking。"""

    doc = json.loads(REFERENCE_GUIDE_V11.read_text(encoding="utf-8"))
    parsed = parse_guide_version(doc)
    assert parsed.version == 11
    assert parsed.updated_at
    assert parsed.has_unknown_breaking_change is False


def test_reference_guide_v14_snapshot_parses() -> None:
    """已审查基线 v14 真实快照（2026-09-05 抓取）完整解析且无未知 breaking。"""

    doc = json.loads(REFERENCE_GUIDE_V14.read_text(encoding="utf-8"))
    parsed = parse_guide_version(doc)
    assert parsed.version == 14
    assert parsed.updated_at
    assert parsed.has_unknown_breaking_change is False
    assert len(parsed.changes) >= 27  # v1—v14 全量变更


def test_reference_guide_v15_snapshot_parses() -> None:
    """已审查基线 v15 真实快照（2026-09-05 抓取）完整解析且无未知 breaking：

    v15 自动匹配默认房配置上调（M=1/Rounds=2 → M=10/Rounds=8）为 breaking 条目，
    但版本 ≤ KNOWN_GUIDE_VERSION 且 breaking 面仅限 POST /api/match 显式低上限
    调用方——本 bot 不调用 /api/match、不支持全局 Token，正式赛事与测试房间
    路径不受影响，因此不得触发未知 breaking 判定。
    """

    doc = json.loads(REFERENCE_GUIDE_V15.read_text(encoding="utf-8"))
    parsed = parse_guide_version(doc)
    assert parsed.version == KNOWN_GUIDE_VERSION == 15
    assert parsed.updated_at
    assert parsed.has_unknown_breaking_change is False
    assert len(parsed.changes) >= 38  # v1—v15 全量变更（含回溯扩充的自动匹配条目）


def test_guide_v10_v11_non_breaking_changes_accepted() -> None:
    """指南 v10/v11 兼容变更（快照 gap=true、16/s 限速）不触发未知 breaking 判定。"""

    doc = json.loads(REFERENCE_GUIDE_V8.read_text(encoding="utf-8"))
    doc["version"] = 11
    doc["changes"] = [
        {"version": 11, "type": "changed", "summary": "state 轮询限速放宽 8/s → 16/s（每用户聚合）"},
        {"version": 10, "type": "changed", "summary": "跨局断链时快照可携带 gap=true"},
    ]
    parsed = parse_guide_version(doc)
    assert parsed.version == 11
    assert parsed.has_unknown_breaking_change is False


def test_future_breaking_guide_is_flagged() -> None:
    """高于已知版本的 breaking 变更必须被标记，供初始化拒绝。"""

    parsed = parse_guide_version(load_fixture("guide_breaking_future.json"))
    assert parsed.version == 16
    assert parsed.has_unknown_breaking_change is True


def test_me_fixture_parses() -> None:
    me = parse_me(load_fixture("me.json"))
    assert me.user_id == "u_player_a"
    assert me.tournament_id == "t_test_room_1"
    assert me.active_games == ("g_room1_batch1",)


def test_rules_fixture_parses() -> None:
    rules = parse_rules_config(load_fixture("rules.json"))
    assert rules.max_games == 10
    assert rules.rounds_per_game == 1
    assert rules.base_score == 1
    assert rules.you_cai_bi_kao is False
    assert rules.discard_timeout_sec == 3.0
    assert rules.description and rules.description.startswith("本场赛程说明")
    assert rules.online_confirm is False  # 缺键 = 存量赛（v13 判别）


def test_rules_online_confirm_parses() -> None:
    """指南 v13：config.OnlineConfirm=true 表示新建赛事「确认 ∧ 在线」分桌；
    缺键/False 为存量赛旧分桌；非布尔按协议错误拒绝。"""

    doc = load_fixture("rules.json")
    doc["config"]["OnlineConfirm"] = True
    assert parse_rules_config(doc).online_confirm is True
    doc["config"]["OnlineConfirm"] = False
    assert parse_rules_config(doc).online_confirm is False
    doc["config"]["OnlineConfirm"] = "yes"
    with pytest.raises(DtoError):
        parse_rules_config(doc)


def test_tournament_detail_fixtures_parse() -> None:
    running = parse_tournament_detail(load_fixture("tournament_detail.json"))
    assert running.status == "running"
    assert running.stage_no == 1
    assert running.qualified is True
    assert running.my_games == ("g_room1_batch1",)
    assert running.ranking[0].rank == 1
    assert running.stage_crashed is False

    stage_open = parse_tournament_detail(load_fixture("tournament_stage_open.json"))
    assert stage_open.status == "stage_open"
    assert stage_open.qualified is False

    finished = parse_tournament_detail(load_fixture("tournament_finished.json"))
    assert finished.status == "finished"


def test_state_response_classification() -> None:
    pending = parse_state_response(load_fixture("state_response_pending.json"))
    assert pending.kind == "pending"

    snapshot = parse_state_response(load_fixture("state_response_snapshot_draw.json"))
    assert snapshot.kind == "snapshot"
    assert snapshot.snapshot is not None and snapshot.snapshot.seq == 101
    assert snapshot.snapshot.my_hand[0] == "1w"

    events = parse_state_response(load_fixture("state_response_events.json"))
    assert events.kind == "events"
    assert [e.seq for e in events.events] == [102, 103]
    assert events.events[0].type == "tile_discarded"
    assert events.events[0].tiles == ("发",)

    gap = parse_state_response(load_fixture("state_response_gap.json"))
    assert gap.kind == "events" and gap.gap is True

    finished = parse_state_response(load_fixture("state_response_finished.json"))
    assert finished.kind == "finished"
    assert finished.snapshot.scores == (34, 12, -6, -40)


def test_snapshot_with_gap_parses() -> None:
    """指南 v10：快照响应可携带 gap=true（跨局断链）；解析保留该事实。"""

    doc = load_fixture("state_response_snapshot_draw.json")
    doc["gap"] = True
    parsed = parse_state_response(doc)
    assert parsed.kind == "snapshot"
    assert parsed.gap is True
    assert parsed.snapshot is not None and parsed.snapshot.seq == 101


def test_snapshot_empty_drawn_tile_normalized_to_none() -> None:
    """官方实测（2026-09-04，房间 t_714a42392cba）：非摸牌阶段 drawn_tile
    为空字符串 "" 而非 null；空串必须归一化为 None，不得判为非法牌码。"""

    doc = load_fixture("state_response_snapshot_draw.json")
    doc["snapshot"]["drawn_tile"] = ""
    parsed = parse_state_response(doc)
    assert parsed.kind == "snapshot"
    assert parsed.snapshot is not None and parsed.snapshot.drawn_tile is None


def test_snapshot_without_seq_is_dto_error() -> None:
    doc = load_fixture("state_response_snapshot_draw.json")
    doc.pop("seq")
    doc["snapshot"].pop("seq", None)
    with pytest.raises(DtoError):
        parse_state_response(doc)


def test_unknown_fields_are_tolerated() -> None:
    """兼容新增字段：官方未来加字段不能让解析崩溃。"""

    doc = load_fixture("state_response_snapshot_draw.json")
    doc["future_field"] = {"anything": True}
    doc["snapshot"]["future_tile_field"] = "x"
    parsed = parse_state_response(doc)
    assert parsed.kind == "snapshot"


def test_error_code_extraction() -> None:
    body = json.dumps(load_fixture("error_invalid_action.json"))
    assert extract_error_code(409, body) == "INVALID_ACTION"
    assert extract_error_code(429, "plain text") is None
    assert extract_error_code(500, "") is None
