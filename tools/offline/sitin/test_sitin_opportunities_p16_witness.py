# -*- coding: utf-8 -*-
"""P16-C3 定向测试：实际玩家观察的**完整、版本化规范摘要** + 见证分列读数。

缺陷（R9 冻结复审 C3）：根见证复用了 offline.evaluate 的稀疏帧摘要（定位 / 手牌摘要 /
摸牌 / 墙余量与分数），牌河、副露、最近弃牌、规则状态、公开事件都不在摘要里——
只改牌河 1w→9w 或包头状态，观察摘要与内容摘要都不变、判定仍 MATCHED；同一接口另有
防错缺口：描述符与实际根/种子不一致只记布尔值；对拍对象 expected 未捕获也可能 MATCHED；
requirement 不一致可与内容匹配并存。

本测试用纯函数（真实 root_witness/root_witness_verdict 机制 + 手造 PlayerObservation）
驱动，因此同一份测试在修复前会因缺陷本身变红。
0 真实桌赛 / 0 模型调用 / 0 网络。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/tools'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import sitin_opportunities as so  # noqa: E402
import sitin_search as search  # noqa: E402
from hangma_bot.kernel.actions import Tile, WindowKey, WindowPhase  # noqa: E402
from hangma_bot.kernel.observation import (  # noqa: E402
    PlayerObservation, PublicDiscard, PublicEvent, PublicMeld, RulePublicState,
)

#: 真实同源的根描述符（生成器/子场景/情景/面板种子/序号五维 → 身份与执行种子）。
DESCRIPTOR = search.av_family_root_descriptor(
    prefix_source="v2_behavior", sub_scenario="branch_open", opponent_mix="H",
    panel_seed=20260916, root_index=1)
ROOT_ID = str(DESCRIPTOR["root_id"])
ROOT_SEED = int(DESCRIPTOR["root_seed"])


def _t(code: str) -> Tile:
    return Tile(code)


def _window(*, seat: int = 0, trigger_seq: int = 10, game_id: str = "g-p16"):
    return WindowKey(game_id=game_id, round_no=1, trigger_seq=trigger_seq,
                     phase=WindowPhase.DRAW, seat=seat)


def _event(seq: int, kind: str, **kwargs) -> PublicEvent:
    return PublicEvent(seq=seq, kind=kind, **kwargs)


def _observation(*, seat: int = 0, discards=None, melds=None, last_discard=None,
                 baotou: bool = False, public_history=None, hand=("1w", "2w", "3w"),
                 drawn: str = "4w", remaining: int = 55,
                 game_id: str = "g-p16") -> PlayerObservation:
    """一份真实形状的玩家观察（座位 0 的合法可见事实；他家暗牌在类型上不存在）。"""

    rivers = discards or [("3w",), (), (), ()]
    meld_rows = melds or [(), (), (), ()]
    return PlayerObservation(
        game_id=game_id, seat=seat, round_no=1, snapshot_seq=7, phase="draw",
        dealer_seat=0, turn_seat=seat, responding_seats=(seat,),
        my_hand=tuple(_t(code) for code in hand),
        drawn_tile=None if drawn is None else _t(drawn),
        discards=tuple(tuple(_t(code) for code in river) for river in rivers),
        melds=tuple(tuple(row) for row in meld_rows),
        hand_counts=(13, 13, 13, 13),
        last_discard=last_discard,
        remaining_tile_count=remaining,
        scores=(10, 20, 30, 40),
        rule_state=RulePublicState(wealth_god=_t("白"), baotou=baotou,
                                   chain_count=0, catch_play=False,
                                   catch_play_owner_seat=None),
        public_history=tuple(public_history or (
            _event(1, "draw", seat=0, tiles=(_t("4w"),)),
            _event(2, "discard", seat=1, tiles=(_t("3w"),)),
        )),
        consumed_seq=9, history_complete=True, chain_piao=0, gang_draw=False,
        observation_issues=(),
    )


def _summary(observation):
    """观察本体 → 规范摘要（产物里落的就是这一份；判定按它重算）。"""

    return so.player_observation_summary(observation, window_key=_window(
        seat=int(getattr(observation, "seat", 0))))


def _witness(observation, *, descriptor=None, prefix_source="v2_behavior",
             seed=ROOT_SEED, seat=0, window=None, entry="conditional_first_hit_root"):
    """用**真实捕获机制**造一份见证（AttemptOutcome + root_witness），只喂手造观察。"""

    key = window or _window(seat=seat)
    attempt = so.AttemptOutcome(
        status="hit", attempt_index=1, source_root_id=ROOT_ID, spec_seed=seed,
        prefix=({"window_key": {"phase": "draw", "seat": 2, "trigger_seq": 8},
                 "action_key": "discard:9b"},),
        cut_frame=SimpleNamespace(), cut_decision=SimpleNamespace(
            window_key=key, observation=observation),
        predicate_values={"branch_open": "TRUE"})
    return so.root_witness(
        attempt=attempt, prefix_source=prefix_source, predicate_id="branch_open",
        focal_seat=seat, opponent_scenario="H", match_id="g-p16",
        descriptor=descriptor or DESCRIPTOR,
        requirement_digest="req-digest", entry=entry,
        runtime_kind="real_simulation_engine", execution_kind="real_runtime")


def test_p16_summary_covers_key_visible_facts_and_no_foreign_hands():
    """规范摘要必须覆盖牌河/副露/最近弃牌/规则状态/公开事件，且不含他家暗牌。"""

    melds = [(), (PublicMeld(seat=1, kind="peng",
                             tiles=(_t("5w"), _t("5w"), _t("5w")),
                             from_seat=0),), (), ()]
    last = PublicDiscard(seat=1, tile=_t("3w"), seq=2)
    summary = so.player_observation_summary(
        _observation(melds=melds, last_discard=last), window_key=_window())
    assert summary["schema"] == so.PLAYER_OBSERVATION_SUMMARY_SCHEMA
    for field in so.PLAYER_OBSERVATION_SUMMARY_FIELDS:
        assert field in summary, field
    # 五类关键可见事实进摘要（缺陷复述：旧摘要一个都没有）。
    assert summary["discards"][0] == ["3w"]
    assert summary["melds"][1][0]["tiles"] == ["5w", "5w", "5w"]
    assert summary["last_discard"] == {"seat": 1, "tile": "3w", "seq": 2}
    assert summary["rule_state"]["baotou"] is False
    assert [row["kind"] for row in summary["public_history"]] == ["draw", "discard"]
    # 只有**本人**手牌进摘要（一张摘要 + 张数）：旧帧摘要给每个决策座位都落手牌摘要。
    assert set(summary["my_hand"]) == {"digest", "count"}
    assert "decisions" not in summary
    # 隐藏信息红线：键名不与 WorldState 私有字段名相交。
    assert not (set(summary) & set(so.FORBIDDEN_SNAPSHOT_KEYS))


def test_p16_each_key_field_change_breaks_the_witness_match():
    """关键字段分别变化 ⇒ 必须不匹配（旧摘要对五类字段全都不敏感）。"""

    base = _observation()
    baseline = _witness(base)
    melds = [(), (PublicMeld(seat=1, kind="peng",
                             tiles=(_t("5w"), _t("5w"), _t("5w")), from_seat=0),), (), ()]
    variants = {
        "discards": _observation(discards=[("9w",), (), (), ()]),          # 牌河 1w→9w
        "melds": _observation(melds=melds),                                # 副露出现
        "last_discard": _observation(
            last_discard=PublicDiscard(seat=1, tile=_t("9w"), seq=2)),     # 最近弃牌改牌
        "rule_state": _observation(baotou=True),                           # 包头状态翻转
        "public_history": _observation(public_history=(
            _event(1, "draw", seat=0, tiles=(_t("4w"),)),
            _event(2, "peng", seat=1, tiles=(_t("5w"), _t("5w"), _t("5w")),
                   detail_kind="peng"))),                                  # 公开事件增加
    }
    for field, observation in variants.items():
        variant = _witness(observation)
        # ① 总摘要与逐字段摘要都变（字段可指名）。
        assert variant["observation_summary_sha256"] != \
            baseline["observation_summary_sha256"], field
        assert variant["content_digest"] != baseline["content_digest"], field
        assert (variant["observation_field_digests"][field]
                != baseline["observation_field_digests"][field]), field
        # ② 对拍判定必须 MISMATCH（旧实现这里全是 MATCHED）。
        verdict = so.root_witness_verdict(baseline, expected=variant,
                                          observation_summary=_summary(base))
        assert verdict["content_matched"] is False, (field, verdict)
        assert verdict["status"] == "MISMATCH", (field, verdict["status"])
        assert verdict["overall_status"] == so.ROOT_WITNESS_OVERALL_REJECTED, field
        assert "observation_field_digests.{0}".format(field) in \
            verdict["mismatched_fields"], (field, verdict["mismatched_fields"])


def test_p16_identical_observation_still_verifies():
    """对照：同根同观察的两份真实捕获仍判 VERIFIED（不把修复变成一律拒绝）。"""

    observation = _observation()
    first = _witness(observation)
    second = _witness(observation, entry="conditional_specified_root")
    verdict = so.root_witness_verdict(
        first, requirement="req-digest", expected=second,
        observation_summary=_summary(observation))
    assert verdict["status"] == "MATCHED", verdict
    assert verdict["content_matched"] is True
    assert verdict["requirement_recomputable"] is True
    assert verdict["requirement_passed"] is True
    assert verdict["binding_ok"] is True
    assert verdict["overall_status"] == so.ROOT_WITNESS_OVERALL_VERIFIED, verdict


def test_p16_wrong_root_and_seed_binding_are_rejected():
    """错误根绑定 / 实际种子与描述符不符（真实路由）必须拒绝。"""

    observation = _observation()
    descriptor = dict(DESCRIPTOR)
    # ① 来源根标识与描述符不一致（跑的是别的根）。
    other = dict(descriptor, root_id="av-eval-branch_open:branch_open:"
                                    "v2-behavior-prefix-v1:H:s20260917:root001")
    verdict = so.root_witness_verdict(_witness(observation, descriptor=other),
                                      observation_summary=_summary(observation))
    assert verdict["binding_ok"] is False, verdict
    assert verdict["binding"]["root_id_matches_source"] is False
    assert verdict["overall_status"] == so.ROOT_WITNESS_OVERALL_REJECTED
    assert verdict["status"] == "BINDING_MISMATCH"
    # ② 真实路由的实际执行种子与描述符种子不符（只记布尔值 ⇒ 现在必须拒绝）。
    mismatched_seed = so.root_witness_verdict(
        _witness(observation, seed=ROOT_SEED + 1),
        observation_summary=_summary(observation))
    assert mismatched_seed["binding"]["seed_matches_descriptor"] is False
    assert mismatched_seed["binding_ok"] is False
    assert mismatched_seed["overall_status"] == so.ROOT_WITNESS_OVERALL_REJECTED
    # ③ 夹具路径的种子口径不同是**具名软条件**（能对拍，但不得当真实根等价证据）。
    fixture = so.root_witness_verdict(
        _witness(observation, prefix_source="scripted_fixture",
                 seed=1),
        observation_summary=_summary(observation))
    assert fixture["binding"]["seed_matches_descriptor"] is False
    assert fixture["binding"]["seed_binding_basis"] == "scripted_fixture_attempt_index"
    assert fixture["binding_ok"] is True
    assert fixture["overall_status"] == so.ROOT_WITNESS_OVERALL_CONTENT_ONLY, fixture
    # ④ 窗口座位与焦点座位不符：硬缺口。
    wrong_seat = so.root_witness_verdict(
        _witness(observation, seat=0, window=_window(seat=2, game_id="g-p16")),
        observation_summary=_summary(observation))
    assert wrong_seat["binding"]["window_seat_matches_focal"] is False
    assert wrong_seat["overall_status"] == so.ROOT_WITNESS_OVERALL_REJECTED


def test_p16_uncaptured_counterpart_never_matches():
    """对拍对象 expected 未捕获 ⇒ 不得给出 MATCHED（必须拒绝）。"""

    observation = _observation()
    witness = _witness(observation)
    fabricated = {
        "schema": so.ROOT_WITNESS_SCHEMA,
        "serialization_version": so.ROOT_WITNESS_SCHEMA,
        "root_descriptor": dict(witness["root_descriptor"]),
        "actual_seed": witness["actual_seed"],
        "prefix_sha256": witness["prefix_sha256"], "prefix_len": witness["prefix_len"],
        "cut_window_key": dict(witness["cut_window_key"]),
        "observation_summary_sha256": witness["observation_summary_sha256"],
        "content_digest": witness["content_digest"],
    }
    verdict = so.root_witness_verdict(witness, expected=fabricated,
                                      observation_summary=_summary(observation))
    assert verdict["counterpart_captured"] is False
    assert verdict["content_matched"] is False
    assert verdict["status"] == "EXPECTED_NOT_CAPTURED", verdict
    assert verdict["overall_status"] == so.ROOT_WITNESS_OVERALL_REJECTED
    assert any("对拍对象" in item for item in verdict["problems"])
    # 对照：内容对拍通过、但要求摘要不符 ⇒ 分列读数（内容 True / 要求 False）。
    requirement_mismatch = so.root_witness_verdict(
        witness, requirement="another-requirement", expected=witness,
        observation_summary=_summary(observation))
    assert requirement_mismatch["content_matched"] is True
    assert requirement_mismatch["requirement_recomputable"] is False
    assert requirement_mismatch["requirement_passed"] is None
    assert requirement_mismatch["overall_status"] == so.ROOT_WITNESS_OVERALL_REJECTED


def test_p16_legacy_summary_schema_witness_is_not_captured():
    """旧口径见证（无完整观察摘要）不得当"已捕获"：口径不混用。"""

    observation = _observation()
    witness = dict(_witness(observation))
    witness.pop("observation_summary_schema")
    witness.pop("observation_field_digests")
    verdict = so.root_witness_verdict(witness,
                                      observation_summary=_summary(observation))
    assert verdict["content_captured"] is False
    assert verdict["overall_status"] == so.ROOT_WITNESS_OVERALL_REJECTED
    assert any("观察摘要口径" in item for item in verdict["problems"])


def test_p16_field_readings_name_the_differing_field():
    """逐字段对拍读数：哪个核心字段不同逐条具名（两入口对拍用）。"""

    first = _witness(_observation())
    second = _witness(_observation(discards=[("9w",), (), (), ()]))
    readings = so.root_witness_field_readings(first, expected=second)
    assert readings["matched"] is False
    assert "observation_field_digests" in readings["mismatched_fields"]
    assert readings["fields"]["observation_field_digests"]["match"] is False
    assert readings["fields"]["source_root_id"]["match"] is True


# ===========================================================================
# 落盘核验与真实产物路径（build_snapshot → av_root_witness_records）
# ===========================================================================


def _panel_envelope(snapshot):
    return {"scenarios": [{"snapshot": snapshot}]}


def _frame(observation, window_key=None):
    """最小决策帧（build_snapshot 只用 decisions/revision/completed_hands）。"""

    decision = SimpleNamespace(observation=observation,
                               window_key=window_key or _window())
    return SimpleNamespace(decisions=[decision], revision=1, completed_hands=0)


def _snapshot_for(observation, *, entry="conditional_first_hit_root"):
    attempt = so.AttemptOutcome(
        status="hit", attempt_index=1, source_root_id=ROOT_ID, spec_seed=ROOT_SEED,
        prefix=({"window_key": {"phase": "draw", "seat": 2, "trigger_seq": 8},
                 "action_key": "discard:9b"},),
        cut_frame=_frame(observation),
        cut_decision=SimpleNamespace(window_key=_window(), observation=observation),
        predicate_values={"branch_open": "TRUE"})
    return so.build_snapshot(
        prefix_source="v2_behavior", attempt=attempt, predicate_id="branch_open",
        focal_seat=0, opponent_scenario="H", match_id="g-p16",
        stage_ledger={"completed_table_scores": []},
        remaining_schedule={"declared_endpoint": "stage_complete",
                            "remaining_tables_after_current": 0,
                            "rounds_per_game": 8, "tables_in_stage": 1},
        panel_seed=20260916, descriptor=DESCRIPTOR, requirement_digest="req-digest",
        witness_entry=entry,
        runtime_evidence={"runtime_kind": "real_simulation_engine",
                          "engine_kind": "simulation_engine_public",
                          "execution_kind": "real_runtime"})


def test_p16_persistence_gate_refuses_tampered_binding(tmp_path):
    """落盘前核验：错绑定的见证不得进审计附属文件（不再只认来源字符串）。"""

    observation = _observation()
    snapshot = _snapshot_for(observation)
    # 真实唯一构造点：快照带**完整规范玩家观察摘要**（C3 的产物侧落点）。
    assert snapshot["player_observation_summary"]["schema"] == \
        so.PLAYER_OBSERVATION_SUMMARY_SCHEMA
    assert snapshot["observation_summary"], "既有帧摘要仍在（重建核对口径不变）"
    records = search.av_root_witness_records(
        tmp_path / "kept", panel=_panel_envelope(snapshot), candidate_id="cand-p16",
        predicate="branch_open", opponent="H", panel_seed=20260916,
        prefix_source="v2_behavior", execution_kind="real_runtime",
        runtime_kind="real_simulation_engine")
    assert len(records) == 1
    verdict = so.root_witness_verdict(
        records[0]["witness"], requirement="req-digest",
        observation_summary=snapshot["player_observation_summary"])
    assert verdict["overall_status"] == so.ROOT_WITNESS_OVERALL_VERIFIED, verdict
    assert verdict["binding"]["observation_summary_checked_against_body"] is True
    assert verdict["binding"]["window_bound_to_observation"] is True
    # 错绑定（描述符换成别的根）⇒ 落盘前具名拒绝，且不产生任何附属文件。
    tampered = dict(snapshot)
    tampered["root_witness"] = dict(
        snapshot["root_witness"],
        root_descriptor=dict(DESCRIPTOR, root_id=str(DESCRIPTOR["root_id"]).replace(
            "s20260916", "s20260917")))
    with pytest.raises(search.AvRootWitnessRefused) as failure:
        search.av_root_witness_records(
            tmp_path / "refused", panel=_panel_envelope(tampered), candidate_id="cand-p16",
            predicate="branch_open", opponent="H", panel_seed=20260916,
            prefix_source="v2_behavior", execution_kind="real_runtime",
            runtime_kind="real_simulation_engine")
    assert "拒绝落盘" in str(failure.value)
    assert not (tmp_path / "refused" / search.AV_ROOT_WITNESS_SIDECAR).exists()


def test_p16_snapshot_summary_changes_when_discards_change(tmp_path):
    """产物侧：牌河变化必然改变规范摘要与见证内容摘要（旧摘要对此不敏感）。"""

    first = _snapshot_for(_observation())
    second = _snapshot_for(_observation(discards=[("9w",), (), (), ()]))
    assert (first["player_observation_summary"]["discards"]
            != second["player_observation_summary"]["discards"])
    assert (first["root_witness"]["observation_summary_sha256"]
            != second["root_witness"]["observation_summary_sha256"])
    assert (first["root_witness"]["content_digest"]
            != second["root_witness"]["content_digest"])

