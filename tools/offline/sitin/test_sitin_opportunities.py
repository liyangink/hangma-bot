# -*- coding: utf-8 -*-
"""sitin_opportunities（C1 legal-prefix-v1）测试：T09/T16 与合同行为。

权威行为 SEARCH-SPACE-REDESIGN-2026-09-16.md §7.2/§7.4/§14 T09/T16：

- T09：夹具构造真实可达机会（branch_open TRUE）；谓词只看行动前观察（投影
  输入不含世界私有字段名）；夹具剧本不含未来牌值；快照重建核对（重放前缀
  →观察摘要一致才通过，篡改摘要 fail-closed）；
- T16：双臂一臂执行失败 → 该样本整体 invalid 并记费用，不保留半成品成功臂；
- 谓词尝试计数与 256 上限（attempts_exhausted 如实上报）；
- 费用账字段完整（§7.4 清单逐项存在性）；
- v2_behavior 无授权直接拒绝并说明原因。

预算红线：全部用夹具（脚本帧+真规则纯分析），零真实桌赛实例。
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

import copy
import json

import pytest

import sitin_opportunities as so
from sitin_predicates_v4 import PREDICATE_IDS, evaluate_predicates

REAL_RULES = None


def real_rules():
    from hangma_bot.hangma.engine import HangmaRules
    from hangma_bot.kernel.config import RuleConfig

    return HangmaRules(RuleConfig(so.DEFAULT_RULESET_VERSION, 1, False))


def cut_observation(template_id: str, seat: int = 0):
    """按模板构造截取窗口观察（与 build_fixture_frames 同参数口径）。"""
    frames = so.build_fixture_frames(template_id, match_id="t", focal_seat=seat)
    window = frames[1].windows[0]
    return so.fixture_observation(
        game_id=window.game_id, seat=window.seat, phase=window.phase,
        hand=window.hand, drawn=window.drawn, trigger_seq=window.trigger_seq,
        wall_left=window.wall_left, scores=window.scores,
        last_discard=window.last_discard,
    )


# ---------------------------------------------------------------------------
# 任务 2：谓词事实投影器
# ---------------------------------------------------------------------------


class TestProjectPredicateFacts:
    def test_projection_shape_matches_predicate_input_contract(self):
        from hangma_bot.hangma.interface import ValueAnalysisLimits

        rules = real_rules()
        observation = cut_observation("peng_branch")
        analysis = rules.analyze(observation, value_limits=ValueAnalysisLimits())
        facts = so.project_predicate_facts(observation, analysis)
        # 顶层合同形状：wall_left + branches（额外键按合同忽略）。
        assert set(facts) >= {"wall_left", "branches"}
        # P9 FAMCOST（投影单位修正）：wall_left = 可摸牌墙余量 =
        # 公开余量 − 保留区。这是**换算**断言而非恒等断言：旧口径把含保留区的
        # 公开余量直接当谓词输入，使 §7.3 的 8/16 阈值两侧同时退化。
        reserve = so.wall_reserve_tiles()
        assert reserve == 20
        assert facts["wall_left"] == so.wall_left_drawable(
            observation.remaining_tile_count)
        assert facts["wall_left"] == max(
            0, int(observation.remaining_tile_count) - reserve)
        allowed = {
            "action_key", "combined_shanten", "shanten_state", "family_progress",
            "route_status", "support_remaining", "family_route_status",
        }
        for branch in facts["branches"]:
            assert set(branch) == allowed
            assert set(branch["family_progress"]) == set(so.FAMILIES)
            assert set(branch["support_remaining"]) == set(so.FAMILIES)
        # 真谓词接受该投影（结构校验通过）。
        results = evaluate_predicates(facts)
        assert set(results) == set(PREDICATE_IDS)

    def test_projection_none_semantics_passthrough(self):
        from hangma_bot.hangma.interface import (
            CandidateFactKind,
            CandidateFacts,
            FamilyId,
            FamilyProgress,
            ProgressKind,
            RouteStatus,
            RuleAnalysis,
            RuleCandidate,
            RuleCompleteness,
        )
        from hangma_bot.kernel.actions import Discard, Pass, Tile

        observation = cut_observation("pair_wait")
        assert observation.remaining_tile_count is not None
        # facts=None 的候选：全部 UNKNOWN/UNANALYZED/None 透传，不冒充已知。
        analysis = RuleAnalysis(
            legal_candidates=(
                RuleCandidate(action=Pass(), action_key="pass", evidence=(), facts=None),
                RuleCandidate(action=Discard(Tile("9b")), action_key="discard:9b",
                              evidence=(), facts=None),
            ),
            emergency_candidate=None,
            completeness=RuleCompleteness.COMPLETE,
            ruleset_version="t",
            issues=(),
        )
        facts = so.project_predicate_facts(observation, analysis)
        for branch in facts["branches"]:
            assert branch["combined_shanten"] is None
            assert branch["route_status"] == "UNANALYZED"
            assert branch["family_progress"] == {f: "UNKNOWN" for f in so.FAMILIES}
            assert branch["support_remaining"] == {f: None for f in so.FAMILIES}
        # 谓词合同的硬门槛：UNANALYZED 路线证据 definitive 排除（不产生
        # UNKNOWN）——无可用推进侧即 FALSE；投影与该冻结语义联动。
        results = evaluate_predicates(facts)
        assert results["branch_open"]["value"] == "FALSE"
        assert results["branch_open"]["missing"] is None

        # 已进入分析（route OPEN_UNCERTAIN）但进展 UNKNOWN 且向听缺失：
        # 补全后可能翻转为 TRUE → 单列 UNKNOWN，不当作 FALSE。
        unknown_progress_facts = CandidateFacts(
            fact_kind=CandidateFactKind.HAND_PROGRESS,
            shanten_after=None,
            family_progress=(
                FamilyProgress(
                    family=FamilyId.BRANCH, progress=ProgressKind.UNKNOWN,
                    route_status=RouteStatus.OPEN_UNCERTAIN, basis="t",
                ),
            ),
        )
        analysis_unknown = RuleAnalysis(
            legal_candidates=(
                RuleCandidate(action=Pass(), action_key="pass", evidence=(),
                              facts=unknown_progress_facts),
                RuleCandidate(action=Discard(Tile("9b")), action_key="discard:9b",
                              evidence=(), facts=unknown_progress_facts),
            ),
            emergency_candidate=None,
            completeness=RuleCompleteness.COMPLETE,
            ruleset_version="t",
            issues=(),
        )
        facts_unknown = so.project_predicate_facts(observation, analysis_unknown)
        results_unknown = evaluate_predicates(facts_unknown)
        assert results_unknown["branch_open"]["value"] == "UNKNOWN"
        assert results_unknown["branch_open"]["missing"]

    def test_projection_wall_left_none_passthrough(self):
        from hangma_bot.hangma.interface import RuleAnalysis, RuleCandidate, RuleCompleteness
        from hangma_bot.kernel.actions import Pass

        observation = cut_observation("pair_wait")
        # 墙余量未知（官方未提供）：wall_left=None 透传，不猜数值。
        from dataclasses import replace

        observation = replace(observation, remaining_tile_count=None)
        analysis = RuleAnalysis(
            legal_candidates=(
                RuleCandidate(action=Pass(), action_key="pass", evidence=(), facts=None),
            ),
            emergency_candidate=None,
            completeness=RuleCompleteness.COMPLETE,
            ruleset_version="t",
            issues=(),
        )
        facts = so.project_predicate_facts(observation, analysis)
        assert facts["wall_left"] is None

    def test_projection_with_real_predicates_true_false_unknown(self):
        from hangma_bot.hangma.interface import ValueAnalysisLimits

        rules = real_rules()
        limits = ValueAnalysisLimits()
        expectations = {
            "peng_branch": "TRUE",
            "pair_wait": "FALSE",
            # P9 FAMCOST（判别字段修复，2026-09-18）：该窗口唯一可能充当推进侧 b
            # 的分支是 hu（branch_progress=SAME），而它的 fact_kind=WIN —— 接口
            # 契约禁止 WIN 携带向听/有效牌数值 ⇒ 按「不可比较」definitive 排除，
            # 不进入缺失分析。修复前它被当作"待补全的缺失值"⇒ 误判 UNKNOWN；
            # 修复后没有任何候选对 ⇒ FALSE（合同三值语义：必要比较已知且均不满足）。
            "draw_unknown": "FALSE",
        }
        for template_id, expected in expectations.items():
            observation = cut_observation(template_id)
            analysis = rules.analyze(observation, value_limits=limits)
            facts = so.project_predicate_facts(observation, analysis)
            results = evaluate_predicates(facts)
            assert results["branch_open"]["value"] == expected, template_id

    def test_hu_branch_is_not_applicable_not_unknown(self):
        """P9：合法 hu 分支不得把谓词拖进 UNKNOWN（"不适用" ≠ "缺失"）。"""

        from hangma_bot.hangma.interface import ValueAnalysisLimits

        rules = real_rules()
        observation = cut_observation("draw_unknown")
        analysis = rules.analyze(observation, value_limits=ValueAnalysisLimits())
        facts = so.project_predicate_facts(observation, analysis)
        hu = [b for b in facts["branches"] if b["action_key"] == "hu"]
        assert hu and hu[0]["combined_shanten"] is None
        assert hu[0]["shanten_state"] == "not_applicable"
        # 其余可比较分支照旧 known（判别字段只标"不适用"，不动可比较分支）。
        assert {b["shanten_state"] for b in facts["branches"] if b["action_key"] != "hu"} == {
            "known"}
        results = evaluate_predicates(facts)
        assert results["branch_open"]["value"] != "UNKNOWN"
        assert results["branch_cost"]["value"] != "UNKNOWN"
        # 反例（同一帧，人为把 hu 标回"未知"）：缺失分析重新触发 ⇒ UNKNOWN。
        # 这正是修复前 4/331 帧读数的来源，用例把它钉死。
        legacy = json.loads(json.dumps(facts))
        for branch in legacy["branches"]:
            if branch["action_key"] == "hu":
                branch["shanten_state"] = "unknown"
        assert evaluate_predicates(legacy)["branch_open"]["value"] == "UNKNOWN"

    def test_facts_none_or_unanalyzed_splits_stay_unknown(self):
        """真缺失（无事实 / 分牌型未分析）仍然判 UNKNOWN——判据未被本次修复放宽。"""

        from hangma_bot.hangma.interface import (
            CandidateFactKind,
            CandidateFacts,
            FamilyProgress,
            FamilyId,
            ProgressKind,
            RouteStatus,
        )
        from hangma_bot.kernel.actions import Discard, Pass, Tile

        from hangma_bot.hangma.interface import RuleAnalysis, RuleCandidate, RuleCompleteness

        observation = cut_observation("peng_branch")

        def facts_with(kind, shanten, progress):
            return CandidateFacts(
                fact_kind=kind, shanten_after=shanten,
                family_progress=(FamilyProgress(
                    family=FamilyId.BRANCH, progress=progress,
                    route_status=RouteStatus.OPEN_UNCERTAIN, basis="t"),))

        # 情形一：**真缺失**（HAND_PROGRESS 但分牌型未分析）⇒ 仍判 UNKNOWN。
        analysis = RuleAnalysis(
            legal_candidates=(
                RuleCandidate(action=Pass(), action_key="pass", evidence=(),
                              facts=facts_with(CandidateFactKind.HAND_PROGRESS, None,
                                               ProgressKind.SAME)),
                RuleCandidate(action=Discard(Tile("9b")), action_key="discard:9b",
                              evidence=(), facts=facts_with(
                                  CandidateFactKind.HAND_PROGRESS, None,
                                  ProgressKind.RETREAT)),
            ),
            emergency_candidate=None,
            completeness=RuleCompleteness.COMPLETE,
            ruleset_version="t",
            issues=(),
        )
        projected = so.project_predicate_facts(observation, analysis)
        assert {b["shanten_state"] for b in projected["branches"]} == {"unknown"}
        assert evaluate_predicates(projected)["branch_open"]["value"] == "UNKNOWN"
        assert evaluate_predicates(projected)["branch_open"]["missing"]

        # 情形二：完全没有事实（facts=None）⇒ 路线证据默认 UNANALYZED，
        # 被合同硬门槛 definitive 排除（这一条是既有语义，本次修复未改动），
        # 因此判 FALSE 而不是 UNKNOWN —— 与"缺失"分开记。
        analysis_none = RuleAnalysis(
            legal_candidates=(
                RuleCandidate(action=Pass(), action_key="pass", evidence=(),
                              facts=None),
                RuleCandidate(action=Discard(Tile("9b")), action_key="discard:9b",
                              evidence=(), facts=None),
            ),
            emergency_candidate=None,
            completeness=RuleCompleteness.COMPLETE,
            ruleset_version="t",
            issues=(),
        )
        projected_none = so.project_predicate_facts(observation, analysis_none)
        assert {b["shanten_state"] for b in projected_none["branches"]} == {"unknown"}
        assert evaluate_predicates(projected_none)["branch_open"]["value"] == "FALSE"

    def test_projection_input_has_no_world_private_field_names(self):
        from hangma_bot.hangma.interface import ValueAnalysisLimits

        rules = real_rules()
        observation = cut_observation("peng_branch")
        analysis = rules.analyze(observation, value_limits=ValueAnalysisLimits())
        facts = so.project_predicate_facts(observation, analysis)
        text = json.dumps(facts, ensure_ascii=False, default=str)
        for forbidden in so.FORBIDDEN_SNAPSHOT_KEYS:
            assert '"{0}"'.format(forbidden) not in text


# ---------------------------------------------------------------------------
# T09：夹具构造真实可达机会；谓词只看行动前观察；重建核对 fail-closed
# ---------------------------------------------------------------------------


def _generate_hit_snapshot():
    from hangma_bot.hangma.interface import ValueAnalysisLimits

    snapshot, counters = so.generate_opportunity(
        prefix_source="scripted_fixture",
        rules=real_rules(),
        predicate_id="branch_open",
        focal_seat=0,
        opponent_scenario="H",
        root_label="t09",
        match_id="t09-match",
        stage_ledger={"completed_table_scores": [(3, 1, -1, -3)]},
        remaining_schedule={"declared_endpoint": "stage_complete",
                            "remaining_tables_after_current": 1,
                            "rounds_per_game": 8, "tables_in_stage": 2},
        value_limits=ValueAnalysisLimits(),
    )
    assert snapshot is not None
    return snapshot, counters


class TestT09FixtureOpportunity:
    def test_fixture_prefix_reaches_real_branch_open_true(self):
        snapshot, counters = _generate_hit_snapshot()
        # 预分配谓词在焦点座位行动前真实命中（真规则分析 + 八谓词判定）。
        assert counters["hit"] == 1
        assert snapshot["labels"]["predicate_values_at_cut"]["branch_open"] == "TRUE"
        assert snapshot["labels"]["main"] == "branch_open"
        # 同根只贡献一个样本一个主子场景：其他谓词命中仅作标签。
        assert set(snapshot["labels"]["predicate_values_at_cut"]) == set(PREDICATE_IDS)

    def test_predicate_judged_on_pre_action_observation_visible_only(self, monkeypatch):
        captured = {}
        original = so.evaluate_predicates

        def spy(facts):
            captured["facts"] = facts
            return original(facts)

        monkeypatch.setattr(so, "evaluate_predicates", spy)
        snapshot, _ = _generate_hit_snapshot()
        # 投影输入 = 玩家可见事实（观察 + 规则分析），无世界私有字段。
        facts = captured["facts"]
        assert set(facts) >= {"wall_left", "branches"}
        text = json.dumps(facts, ensure_ascii=False, default=str)
        for forbidden in so.FORBIDDEN_SNAPSHOT_KEYS:
            assert '"{0}"'.format(forbidden) not in text
        # 判定发生在焦点座位行动前（截取窗口，非事后）。
        assert snapshot["cut_window"]["seat"] == 0
        assert snapshot["cut_window"]["trigger_seq"] == 10

    def test_fixture_script_contains_no_future_tile_values(self):
        for template_id in so.FIXTURE_TEMPLATE_SEQUENCE:
            frames = so.build_fixture_frames(template_id, match_id="t")
            for frame in frames:
                for window in frame.windows:
                    # 窗口规格只含可见事实字段；无牌墙顺序/未来事件键。
                    fields = set(window.__dict__)
                    assert fields == {
                        "game_id", "seat", "phase", "hand", "drawn", "trigger_seq",
                        "wall_left", "scores", "last_discard",
                    }

    def test_panel_artifacts_contain_no_world_private_keys(self):
        snapshot, _ = _generate_hit_snapshot()
        text = json.dumps(snapshot, ensure_ascii=False, default=str)
        for forbidden in so.FORBIDDEN_SNAPSHOT_KEYS:
            assert '"{0}"'.format(forbidden) not in text

    def test_snapshot_rebuild_verifies_observation_summary(self):
        from hangma_bot.offline.evaluate import frame_observation_summary

        snapshot, _ = _generate_hit_snapshot()
        engine, world = so.rebuild_world(rules=real_rules(), snapshot=snapshot)
        frame = engine.frame(world)
        # 重放合法前缀后到达同一决策边界：观察摘要逐键一致。
        assert frame_observation_summary(frame) == snapshot["observation_summary"]

    def test_tampered_summary_fails_closed(self, tmp_path):
        snapshot, _ = _generate_hit_snapshot()
        tampered = copy.deepcopy(snapshot)
        digest = tampered["observation_summary"]["decisions"][0]["hand_digest"]
        tampered["observation_summary"]["decisions"][0]["hand_digest"] = (
            "0" * len(digest) if digest else "0" * 64
        )
        panel = {
            "schema": so.PANEL_SCHEMA,
            "scenarios": [{"sub_scenario": "branch_open", "snapshot": tampered}],
        }
        panel_path = tmp_path / "panel.json"
        panel_path.write_text(json.dumps(panel, ensure_ascii=False), encoding="utf-8")
        verdict = so.inspect_panel(panel_path=panel_path)
        assert verdict["ok"] is False
        assert any("不一致" in problem or "摘要" in problem for problem in verdict["problems"])

    def test_tampered_prefix_fails_closed(self):
        snapshot, _ = _generate_hit_snapshot()
        tampered = copy.deepcopy(snapshot)
        # 该前缀窗口是摸牌窗口：peng:9b 不可能合法（重建必须拒绝非法前缀）。
        tampered["legal_action_prefix"][0]["action_key"] = "peng:9b"
        with pytest.raises(ValueError):
            so.rebuild_world(rules=real_rules(), snapshot=tampered)


# ---------------------------------------------------------------------------
# 双臂续打与 T16：一臂失败 → 整样本 invalid
# ---------------------------------------------------------------------------


class TestDoubleArm:
    def _arm_setup(self, candidate_focal):
        snapshot, _ = _generate_hit_snapshot()
        opponent = so.FixtureBehaviorPolicy("fixture-opponent-standin", prefer=("pass",))
        baseline = so.FixtureBehaviorPolicy("fixture-baseline-focal", prefer=("pass",))
        by_seat_baseline = [opponent] * 4
        by_seat_candidate = [opponent] * 4
        by_seat_baseline[0] = baseline
        by_seat_candidate[0] = candidate_focal
        return snapshot, by_seat_baseline, by_seat_candidate

    def test_double_arm_diverges_and_unadvanced_responder_redecides(self):
        snapshot, by_seat_baseline, by_seat_candidate = self._arm_setup(
            so.FixtureBehaviorPolicy("fixture-candidate-focal", prefer=("peng:5w",))
        )
        result = so.run_double_arm(
            rules=real_rules(), snapshot=snapshot,
            baseline_policies_by_seat=by_seat_baseline,
            candidate_policies_by_seat=by_seat_candidate,
            config=so._driver_config(),
        )
        assert result["valid"] is True
        assert result["declared_endpoint"] == "stage_complete"
        # 完整剩余阶段：当前桌（部分）+ 剩余桌（完整）都被执行。
        for arm in result["arms"].values():
            assert [table["partial"] for table in arm["tables"]] == [True, False]
        baseline_current = result["arms"]["baseline"]["tables"][0]["scores_by_seat"]
        candidate_current = result["arms"]["candidate"]["tables"][0]["scores_by_seat"]
        assert baseline_current == [2, 0, -1, -1]
        assert candidate_current == [6, -2, -2, -2]
        # 两臂焦点阶段总账与 U 识别区间已求值（快照携带已完成桌账 focal=3 +
        # 当前桌 + 剩余桌；同根两臂同剩余桌 seed）。
        assert result["arms"]["baseline"]["stage_totals_by_participant"]["focal"] == 7
        assert result["arms"]["candidate"]["stage_totals_by_participant"]["focal"] == 11
        for arm in result["arms"].values():
            assert arm["u"] == 1.0 and arm["u_low"] == 1.0 and arm["u_high"] == 1.0
        # 截取帧两个窗口（焦点 0 + 未推进响应者 2）都在续打中重新决策。
        for arm in result["arms"].values():
            assert arm["decisions_after_cut"] == 2

    def test_t16_one_arm_policy_failure_invalidates_whole_sample(self):
        from hangma_bot.hangma.interface import (
            RuleAnalysis, RuleCandidate, RuleCompleteness, RuleIssue,
        )
        from hangma_bot.kernel.actions import Discard, Pass, Tile

        snapshot, by_seat_baseline, _ = self._arm_setup(None)
        # 无紧急候选的规则桩：候选臂策略抛错 → 本窗口无可用动作 → 该臂失败。
        candidates = (
            RuleCandidate(action=Pass(), action_key="pass", evidence=()),
            RuleCandidate(action=Discard(Tile("1t")), action_key="discard:1t", evidence=()),
        )
        stub = type("StubNoEmergency", (), {})()

        def analyze(observation, value_limits=None):
            return RuleAnalysis(
                legal_candidates=candidates, emergency_candidate=None,
                completeness=RuleCompleteness.COMPLETE, ruleset_version="t16",
                issues=(RuleIssue("stub", "T16 构造：无紧急候选"),),
            )

        stub.analyze = analyze
        by_seat_candidate = [so.FixtureBehaviorPolicy("fixture-opponent-standin", prefer=("pass",))] * 4
        by_seat_candidate[0] = so.RaisingPolicy("t16-candidate-focal")
        result = so.run_double_arm(
            rules=stub, snapshot=snapshot,
            baseline_policies_by_seat=by_seat_baseline,
            candidate_policies_by_seat=by_seat_candidate,
            config=so._driver_config(),
        )
        # T16：一臂失败 → 整样本 invalid；成功臂数值保留在明细但不可用。
        assert result["valid"] is False
        assert result["arms"]["candidate"]["usable"] is False
        assert result["arms"]["candidate"]["error"] is not None
        assert result["arms"]["candidate"]["status"] != "complete"
        # 基线臂可能成功，但样本整体无效（不保留半成品成功臂）。
        record = so.build_cost_record(
            snapshot=snapshot, double_arm=result,
            counters={"total": 3, "hit": 1, "missed": 1, "unknown": 1,
                      "cap": 256, "attempts_exhausted": False},
            opponent_policies=["weighted_heuristic_v2"] * 3,
            rule_config={"ruleset_version": so.DEFAULT_RULESET_VERSION,
                         "base_score": 1, "you_cai_bi_kao": False},
            focal_seat=0,
        )
        assert record["completeness"] == "invalid"
        assert record["invalid_reasons"]
        # 无效样本不冒充 U 已求值：失败臂的 U 字段全空。
        assert record["u_or_interval_by_arm"]["candidate"]["u"] is None
        assert record["actual_table_instances"] == 0  # 失败也记费用（夹具口径）
        assert record["prefix_attempts"]["total"] == 3


# ---------------------------------------------------------------------------
# 尝试计数与 256 上限；费用账字段；配额结构；v2_behavior 拒绝
# ---------------------------------------------------------------------------


class TestAttemptAccounting:
    def test_fixture_sequence_counters_after_p9_classification(self):
        """夹具尝试序列（miss → 【P9 后】miss → hit）的计数如实上报。

        P9 前中间的 draw_unknown 模板被判 UNKNOWN（hu 分支被当缺失），修复后该
        窗口判 FALSE ⇒ 记 missed。计数口径本身不变，变的是该窗口的真实判定。
        """

        _, counters = _generate_hit_snapshot()
        assert counters["total"] == 3
        assert counters["missed"] == 2
        assert counters["unknown"] == 0
        assert counters["hit"] == 1
        assert counters["attempts_exhausted"] is False

    def test_counters_count_miss_unknown_independently_of_predicate(self, monkeypatch):
        """计数回路单测：三种状态各自落哪个计数器（与谓词实现解耦）。

        修复前这条覆盖依赖 draw_unknown 夹具恰好产出 UNKNOWN；P9 判别字段修复后
        该窗口判 FALSE，因此这里改为按**尝试状态**注入 —— 被测对象是计数回路本身，
        注入后断言更直接（不再依赖某个窗口的偶然判定）。
        """

        statuses = ["miss", "unknown", "miss"]
        calls = {"n": 0}

        def fake_attempt(**kwargs):
            status = statuses[calls["n"]]
            calls["n"] += 1
            assert calls["n"] <= len(statuses)
            return so.AttemptOutcome(
                status=status, template_id=None,
                attempt_index=int(kwargs["attempt_index"]),
                source_root_id=str(kwargs["source_root_id"]), spec_seed=1,
                prefix=(), cut_frame=None, cut_decision=None,
                predicate_values={"branch_open": "FALSE"},
                predicate_witness=None, projected_facts=None)

        monkeypatch.setattr(so, "run_prefix_attempt", fake_attempt)
        snapshot, counters = so.generate_opportunity(
            prefix_source="scripted_fixture", rules=real_rules(),
            predicate_id="branch_open", focal_seat=0, opponent_scenario="H",
            root_label="counters", match_id="counters-match",
            stage_ledger={"completed_table_scores": []},
            remaining_schedule={"declared_endpoint": "stage_complete",
                                "remaining_tables_after_current": 1,
                                "rounds_per_game": 8, "tables_in_stage": 2},
            attempts_cap=3)
        assert snapshot is None
        assert counters["total"] == 3
        assert counters["missed"] == 2
        assert counters["unknown"] == 1
        assert counters["hit"] == 0
        assert counters["errors"] == 0
        assert counters["attempts_exhausted"] is True

    def test_cap_is_256_and_exhaustion_reported(self):
        assert so.PREFIX_ATTEMPT_CAP == 256
        snapshot, counters = so.generate_opportunity(
            prefix_source="scripted_fixture",
            rules=real_rules(),
            predicate_id="branch_open",
            focal_seat=0,
            opponent_scenario="H",
            root_label="cap",
            match_id="cap-match",
            stage_ledger={"completed_table_scores": []},
            remaining_schedule={"declared_endpoint": "current_table_end"},
            attempts_cap=3,
            template_sequence=("pair_wait",),  # 永不命中的模板
        )
        assert snapshot is None
        assert counters["total"] == 3
        assert counters["hit"] == 0
        assert counters["missed"] == 3
        assert counters["attempts_exhausted"] is True


class TestCostLedgerAndQuota:
    def test_cost_record_fields_complete_per_7_4(self):
        snapshot, _ = _generate_hit_snapshot()
        double_arm = so.run_double_arm(
            rules=real_rules(), snapshot=snapshot,
            baseline_policies_by_seat=[so.FixtureBehaviorPolicy("b")] * 4,
            candidate_policies_by_seat=[so.FixtureBehaviorPolicy("c")] * 4,
            config=so._driver_config(),
        )
        record = so.build_cost_record(
            snapshot=snapshot, double_arm=double_arm,
            counters={"total": 3, "hit": 1, "missed": 1, "unknown": 1,
                      "cap": 256, "attempts_exhausted": False},
            opponent_policies=["weighted_heuristic_v2"] * 3,
            rule_config={"ruleset_version": "v", "base_score": 1, "you_cai_bi_kao": False},
            focal_seat=0,
        )
        required = {
            "source_root_id", "scenario_predicate", "generator", "prefix_source",
            "fixture_mode",
            "opponent_scenario", "opponent_policies", "focal_seat", "seats_order",
            "policy_ids", "rule_config", "declared_endpoint", "completeness",
            "invalid_reasons", "u_or_interval_by_arm", "u_hook",
            "net_score_focal_by_arm",
            "stage_net_score_focal_by_arm", "seat_order_scores_final_by_arm",
            "current_table_final_by_arm", "stage_totals_by_participant_by_arm",
            "tables_executed_by_arm",
            "large_settlement_contributions", "payments_by_seat_by_arm",
            "elapsed_ms_by_arm", "degradations", "actual_rounds_executed_by_arm",
            "actual_table_instances", "partial_table_execution", "prefix_attempts",
            "strength_evidence",
        }
        assert required <= set(record)
        assert record["u_hook"]["target"] == "group_advance_v1"
        assert record["declared_endpoint"] == "stage_complete"
        assert record["u_or_interval_by_arm"]["baseline"]["u_low"] is not None
        assert record["partial_table_execution"] is True
        assert record["prefix_attempts"]["missed"] == 1
        assert record["prefix_attempts"]["unknown"] == 1

    def test_quota_declaration_structure(self):
        quota = so.quota_declaration({"branch_open": 1})
        assert len(quota["rows"]) == 8
        for row in quota["rows"]:
            assert row["target_roots"] == 4
            assert row["opponent_split"] == {"H": 2, "M": 2}
        filled = [r for r in quota["rows"] if r["roots_filled"]]
        assert [r["sub_scenario"] for r in filled] == ["branch_open"]
        assert all(
            r["status"] == "structure_declared_not_filled"
            for r in quota["rows"] if not r["roots_filled"]
        )


class TestV2BehaviorRefusal:
    def test_refused_without_authorization_with_clear_reason(self):
        with pytest.raises(ValueError, match="批次 7"):
            so.generate_opportunity(
                prefix_source="v2_behavior",
                rules=real_rules(),
                predicate_id="branch_open",
                focal_seat=0,
                opponent_scenario="H",
                root_label="v2",
                match_id="v2-match",
                stage_ledger={"completed_table_scores": []},
                remaining_schedule={"declared_endpoint": "current_table_end"},
            )

    def test_wrong_batch_token_refused(self):
        with pytest.raises(ValueError, match="批次 7"):
            so.generate_opportunity(
                prefix_source="v2_behavior",
                rules=real_rules(),
                predicate_id="branch_open",
                focal_seat=0,
                opponent_scenario="H",
                root_label="v2",
                match_id="v2-match",
                stage_ledger={"completed_table_scores": []},
                remaining_schedule={"declared_endpoint": "current_table_end"},
                authorization_token={"authorized": True, "batch": 6},
            )

    def test_cli_refuses_v2_without_token(self, tmp_path, capsys):
        exit_code = so.main([
            "build-panel", "--prefix-source", "v2_behavior",
            "--sub-scenario", "branch_open", "--out", str(tmp_path / "v2"),
        ])
        assert exit_code == 2
        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is False
        assert "批次 7" in payload["reason"]

    def test_generators_are_layered_versions(self):
        assert so.GENERATOR_SCRIPTED_FIXTURE != so.GENERATOR_V2_BEHAVIOR
        snapshot, _ = _generate_hit_snapshot()
        assert snapshot["generator"] == so.GENERATOR_SCRIPTED_FIXTURE


class TestBuildPanelEndToEnd:
    def test_build_panel_fixture_demo(self, tmp_path):
        panel = so.build_panel(
            prefix_source="scripted_fixture",
            predicate_id="branch_open",
            focal_seat=0,
            opponent_scenario="H",
            root_label="e2e",
            out_dir=tmp_path,
            ruleset_version=so.DEFAULT_RULESET_VERSION,
            base_score=1,
            you_cai_bi_kao=False,
            attempts_cap=so.PREFIX_ATTEMPT_CAP,
            panel_seed=20260916,
        )
        scenario = panel["scenarios"][0]
        assert scenario["status"] == "sampled"
        assert panel["prefix_attempts"]["total"] == 3
        assert panel["fixture_mode"] is True
        assert panel["engine_kind"] == "scripted_fixture_engine"
        assert panel["budget_red_line"]["real_table_instances_started"] == 0
        assert panel["strength_evidence"] is False
        assert (tmp_path / "panel.json").is_file()
        ledger = panel["cost_ledger"][0]
        assert ledger["declared_endpoint"] == "stage_complete"
        assert ledger["fixture_mode"] is True
        assert ledger["u_or_interval_by_arm"]["baseline"]["u_low"] is not None


# ---------------------------------------------------------------------------
# R3（Q1 修复）真实路径接线、跨进程重建、完整剩余阶段一致性与夹具门禁
# ---------------------------------------------------------------------------

V2_AUTH = {"authorized": True, "batch": 7}


def _real_rules_with_limits():
    from hangma_bot.hangma.interface import ValueAnalysisLimits

    return real_rules(), ValueAnalysisLimits()


def _runtime_double(rules, value_limits=None):
    """显式测试入口装配的验证替身（带 runtime_kind 标签；A1 修复后唯一合法来源）。"""

    return so.build_test_runtime_double(rules=rules, value_limits=value_limits)


def _generate_real_snapshot(root_label="r3-real"):
    rules, limits = _real_rules_with_limits()
    runtime = _runtime_double(rules, limits)
    snapshot, counters = so.generate_opportunity(
        prefix_source="v2_behavior",
        rules=rules,
        predicate_id="branch_open",
        focal_seat=0,
        opponent_scenario="H",
        root_label=root_label,
        match_id="{0}-match".format(root_label),
        stage_ledger={"completed_table_scores": []},
        remaining_schedule={"declared_endpoint": "stage_complete",
                            "remaining_tables_after_current": 1,
                            "rounds_per_game": 8, "tables_in_stage": 2},
        value_limits=limits,
        attempts_cap=4,
        authorization_token=V2_AUTH,
        runtime=runtime,
        tournament_config=so._snapshot_tournament_config(
            {"rounds_per_game": 8}, rules),
        behavior_policies_by_seat=so.frozen_generation_policies(
            opponent_names=["weighted_heuristic_v2"] * 3, focal_seat=0,
            monotonic=lambda: 800.0),
        opponent_names=["weighted_heuristic_v2"] * 3,
        tables_in_stage=2,
        rounds_per_game=8,
    )
    assert snapshot is not None
    return snapshot, counters, rules, limits, runtime


class TestRealPathWiring:
    def test_build_real_runtime_assembles_public_simulation_engine(self):
        """组合根装配：真实 SimulationEngine + spec/choice 工厂；零桌赛执行。"""
        from hangma_bot.simulation.engine import SimulationEngine

        rules, _ = _real_rules_with_limits()
        runtime = so.build_real_runtime(
            rules_config=rules.config, rounds_per_game=8, seed=1)
        assert set(runtime) >= {"engine", "spec_factory", "choice_factory"}
        assert isinstance(runtime["engine"], SimulationEngine)
        assert not getattr(runtime["engine"], "fixture_mode", False)

    def test_v2_generation_never_touches_fixture_machinery(self, monkeypatch):
        """Q1 修复⑤：真实路径绝不调用 build_fixture_frames/ScriptedFixtureEngine。"""
        def boom_frames(*args, **kwargs):
            raise AssertionError("真实路径不得构造夹具帧")

        def boom_engine(*args, **kwargs):
            raise AssertionError("真实路径不得构造 ScriptedFixtureEngine")

        monkeypatch.setattr(so, "build_fixture_frames", boom_frames)
        monkeypatch.setattr(so, "ScriptedFixtureEngine", boom_engine)
        snapshot, counters, *_ = _generate_real_snapshot("r3-wiring")
        assert counters["generator"] == so.GENERATOR_V2_BEHAVIOR
        assert counters["hit"] == 1
        assert snapshot["generator"] == so.GENERATOR_V2_BEHAVIOR
        assert snapshot["fixture_mode"] is False
        assert snapshot["real"]["runtime_source"] == "build_test_runtime_double"
        # A1(c)：注入的替身如实标替身（不再按「传了 runtime」推断）。
        assert snapshot["real"]["engine_kind"] == "simulation_runtime_double"
        assert snapshot["real"]["execution_kind"] == so.EXECUTION_TEST_DOUBLE
        assert snapshot["prefix_source"] == "v2_behavior"

    def test_real_path_rejects_fixture_engine(self):
        rules, limits = _real_rules_with_limits()
        fixture_engine = so.ScriptedFixtureEngine(
            so.build_fixture_frames("peng_branch", match_id="t"), rules)
        with pytest.raises(ValueError, match="不得使用 fixture_mode 引擎"):
            so.run_real_prefix_attempt(
                runtime={"engine": fixture_engine, "spec_factory": None,
                         "choice_factory": None},
                rules=rules, predicate_id="branch_open", focal_seat=0,
                attempt_index=0, source_root_id="r", match_id="m",
                tournament_config=None, seed=0)

    def test_real_snapshot_rebuild_via_public_runtime(self):
        rules, limits = _real_rules_with_limits()
        snapshot, *_ = _generate_real_snapshot("r3-rebuild")
        engine, world = so.rebuild_world(
            rules=rules, snapshot=snapshot, value_limits=limits,
            runtime=_runtime_double(rules, limits))
        frame = engine.frame(world)
        assert so.frame_observation_summary(frame) == snapshot["observation_summary"]

    def test_behavior_policy_failure_counted_as_error_attempt(self, monkeypatch):
        """行为策略执行失败 → 尝试按 errors 作废（不保底冒充前缀），如实计数。

        M2 修复后装配对象必须来自白名单（按合同情景装配）；本测试把白名单工厂
        整体换成"会抛错的策略"，使装配核对通过而**执行**失败，从而覆盖 T16 路径。
        """
        rules, limits = _real_rules_with_limits()

        def broken_builder(name, monotonic):
            return so.RaisingPolicy("broken:{0}".format(name))

        monkeypatch.setattr(so.stage, "build_panel_policy", broken_builder)
        broken = (so.RaisingPolicy("broken"),) * 4
        snapshot, counters = so.generate_opportunity(
            prefix_source="v2_behavior",
            rules=rules, predicate_id="branch_open", focal_seat=0,
            opponent_scenario="H", root_label="r3-err",
            match_id="r3-err-match",
            stage_ledger={"completed_table_scores": []},
            remaining_schedule={"declared_endpoint": "stage_complete"},
            attempts_cap=3, authorization_token=V2_AUTH,
            runtime=_runtime_double(rules, limits),
            tournament_config=so._snapshot_tournament_config(
                {"rounds_per_game": 8}, rules),
            behavior_policies_by_seat=broken,
            opponent_names=["weighted_heuristic_v2"] * 3,
        )
        assert snapshot is None
        assert counters["errors"] == 3
        assert counters["hit"] == 0
        assert counters["attempts_exhausted"] is True

    def test_assembly_mismatch_refused_without_burning_attempts(self, monkeypatch):
        """M2 fail-closed：装配对象与合同情景不符 → 直接拒绝，不烧尝试上限。"""

        rules, limits = _real_rules_with_limits()
        # 合同情景 M，却把三家 V2（H 缺省）塞进前缀装配。
        with pytest.raises(so.RuntimeAssemblyError, match="合同"):
            so.generate_opportunity(
                prefix_source="v2_behavior",
                rules=rules, predicate_id="branch_open", focal_seat=0,
                opponent_scenario="M", root_label="r3-mismatch",
                match_id="r3-mismatch-match",
                stage_ledger={"completed_table_scores": []},
                remaining_schedule={"declared_endpoint": "stage_complete"},
                attempts_cap=3, authorization_token=V2_AUTH,
                runtime=_runtime_double(rules, limits),
                tournament_config=so._snapshot_tournament_config(
                    {"rounds_per_game": 8}, rules),
                behavior_policies_by_seat=so.frozen_generation_policies(
                    opponent_names=["weighted_heuristic_v2"] * 3, focal_seat=0,
                    monotonic=lambda: 800.0),
                opponent_names=["weighted_heuristic_v2",
                                "weighted_heuristic_v2_white_guard",
                                "weighted_heuristic_v1"],
            )


class TestCrossProcessRebuild:
    def test_persisted_snapshot_rebuilds_in_new_process(self, tmp_path):
        """R3 验收：持久化快照 → 新进程 rebuild → 观察摘要一致。"""
        import subprocess
        import sys as _sys

        snapshot, counters, *_ = _generate_real_snapshot("r3-xproc")
        snapshot_path = tmp_path / "snapshot.json"
        snapshot_path.write_text(
            json.dumps(snapshot, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        script = tmp_path / "rebuild_check.py"
        script.write_text(
            "import json, sys\n"
            "sys.path.insert(0, {tools!r})\n"
            "sys.path.insert(0, {src!r})\n"
            "import sitin_opportunities as so\n"
            "from hangma_bot.hangma.engine import HangmaRules\n"
            "from hangma_bot.hangma.interface import ValueAnalysisLimits\n"
            "from hangma_bot.kernel.config import RuleConfig\n"
            "snapshot = json.loads(open({snap!r}, encoding='utf-8').read())\n"
            "rules = HangmaRules(RuleConfig(so.DEFAULT_RULESET_VERSION, 1, False))\n"
            "runtime = so.build_test_runtime_double(rules=rules,\n"
            "    value_limits=ValueAnalysisLimits())\n"
            "engine, world = so.rebuild_world(rules=rules, snapshot=snapshot,\n"
            "    value_limits=ValueAnalysisLimits(), runtime=runtime)\n"
            "summary = so.frame_observation_summary(engine.frame(world))\n"
            "print(json.dumps({{'ok': summary == snapshot['observation_summary']}}))\n".format(
                tools=str(so._HERE), src=str(so.REPO / "src"), snap=str(snapshot_path)),
            encoding="utf-8")
        result = subprocess.run(
            [_sys.executable, str(script)], capture_output=True, text=True,
            cwd=str(so.REPO), timeout=120)
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        assert payload["ok"] is True


class TestFullStageConsistency:
    def test_conditional_stage_matches_uninterrupted_full_stage(self):
        """R3 验收：条件续打（行为策略=臂策略）与整阶段连续运行的终端账一致。"""
        import asyncio

        snapshot, _, rules, limits, runtime = _generate_real_snapshot("r3-cons")
        behavior = so.frozen_generation_policies(
            opponent_names=["weighted_heuristic_v2"] * 3, focal_seat=0,
            monotonic=lambda: 800.0)
        conditional = so.run_conditional_stage_arm(
            arm_name="baseline", rules=rules, snapshot=snapshot,
            policies_by_seat=behavior, config=so._driver_config(),
            value_limits=limits, runtime=runtime)
        assert conditional["usable"], conditional["error"]
        # 参照：同一根从自然开局整阶段连续运行（table1 + table2，同 seed 派生）。
        from hangma_bot.offline.evaluate import drive_match

        fresh_runtime = _runtime_double(rules, limits)
        engine = fresh_runtime["engine"]
        totals = {}
        places = {}
        root_seed = int(snapshot["match_spec"]["seed"])
        match_id = snapshot["match_spec"]["match_id"]
        for table_no in (1, 2):
            table_seed = (root_seed if table_no == 1
                          else so.stage.derive_seed(root_seed, "table", "2", "residual"))
            spec = fresh_runtime["spec_factory"](
                match_id=match_id if table_no == 1 else match_id + ":t2",
                scenario_id=snapshot["match_spec"]["scenario_id"],
                config=so._snapshot_tournament_config(
                    snapshot["match_spec"], rules),
                seed=table_seed, initial_dealer=0, initial_scores=[0, 0, 0, 0])
            situation = so._stage_situation_for(
                snapshot=snapshot, table_no=table_no, totals=totals,
                place_totals=places,
                participants_by_seat=snapshot["stage_plan"]["participant_ids_by_seat"],
                permutation=(0, 1, 2, 3))
            outcome = asyncio.run(drive_match(
                engine=engine, spec=spec, policies_by_seat=behavior, rules=rules,
                choice_factory=fresh_runtime["choice_factory"],
                config=so._driver_config(), now_monotonic=lambda: 800.0,
                wall_clock=None, value_limits=limits, stage_situation=situation))
            assert outcome.status == "complete", outcome.error_reason
            so._accumulate_table(totals, places, outcome.final_scores,
                                 snapshot["stage_plan"]["participant_ids_by_seat"])
        rows = [so.stage.LedgerRow(participant_id=pid, total_score=totals[pid],
                                   place_points=places[pid]) for pid in sorted(totals)]
        reference_u = so.stage.group_advance_utility(rows, focal_id=so.FOCAL_PARTICIPANT)
        # 终端 U 与整阶段对照一致（R3 验收）。
        assert conditional["stage_totals_by_participant"] == dict(sorted(totals.items()))
        assert conditional["u_low"] == float(reference_u["u_low"])
        assert conditional["u_high"] == float(reference_u["u_high"])
        assert conditional["unresolved"] == reference_u["unresolved"]

    def test_unadvanced_responder_not_carried_from_baseline(self):
        """截取帧未行动窗口在续打中按该帧观察重新决策（不沿用基线预选响应）。"""
        snapshot, *_ = _generate_real_snapshot("r3-responder")
        rules, limits = _real_rules_with_limits()
        recorded = {}

        class RecordingArmPolicy:
            def __init__(self, policy_id, prefer):
                self.policy_id = policy_id
                self._inner = so.FixtureBehaviorPolicy(policy_id, prefer=(prefer,))

            async def choose(self, request, budget):
                recorded.setdefault(self.policy_id, []).append(
                    (request.observation.snapshot_seq, request.window_key.seat))
                return await self._inner.choose(request, budget)

        baseline = [RecordingArmPolicy("b{0}".format(i), "pass") for i in range(4)]
        candidate = [RecordingArmPolicy("c{0}".format(i), "peng:5w") for i in range(4)]
        result = so.run_double_arm(
            rules=rules, snapshot=snapshot,
            baseline_policies_by_seat=baseline, candidate_policies_by_seat=candidate,
            config=so._driver_config(), value_limits=limits,
            runtime=_runtime_double(rules, limits))
        assert result["valid"] is True
        # 每臂的焦点策略都在截取帧（trigger_seq=9）按该帧观察重新决策。
        assert ("b0" in recorded and recorded["b0"][0] == (9, 0))
        assert ("c0" in recorded and recorded["c0"][0] == (9, 0))
        # 两臂在截取帧选择了不同动作 → 当前桌结果分叉（不沿用基线响应）。
        baseline_scores = result["arms"]["baseline"]["tables"][0]["scores_by_seat"]
        candidate_scores = result["arms"]["candidate"]["tables"][0]["scores_by_seat"]
        assert baseline_scores != candidate_scores


# ---------------------------------------------------------------------------
# P5（R7 修复）A1 + M2：运行时装配来源、引擎种类、前缀行为策略身份绑定
# ---------------------------------------------------------------------------


GROUP_DEV_CONTRACT = (so.REPO / "review/llm-guided-heuristic-route-2026-09-15"
                      / "contracts" / "group-dev-v1.json")


def _contract_opponent_names(scenario):
    contract = json.loads(GROUP_DEV_CONTRACT.read_text(encoding="utf-8"))
    return list(contract["panel"]["opponent_scenarios"][scenario]["opponent_policies"])


def _m_scenario_panel(tmp_path, scenario):
    """真实路由（注入显式测试替身）建面板：用于核对前缀对手身份绑定。"""

    rules, limits = _real_rules_with_limits()
    return so.build_panel(
        prefix_source="v2_behavior", predicate_id="branch_open", focal_seat=0,
        opponent_scenario=scenario, root_label="p5-" + scenario, out_dir=tmp_path,
        ruleset_version="v26", base_score=1, you_cai_bi_kao=False, attempts_cap=4,
        panel_seed=20260916, authorization_token=V2_AUTH,
        runtime=so.build_test_runtime_double(rules=rules, value_limits=limits),
        contract_file=GROUP_DEV_CONTRACT, tables_in_stage=2, rounds_per_game=8)


class TestRuntimeAssemblyProvenance:
    """A1 修复：运行时种类由装配入口决定，替身只在显式测试入口可达。"""

    def test_real_runtime_tagged_real_and_not_double(self):
        rules, _ = _real_rules_with_limits()
        runtime = so.build_real_runtime(
            rules_config=rules.config, rounds_per_game=8, seed=5)
        assert runtime["runtime_kind"] == so.RUNTIME_KIND_REAL
        assert runtime["runtime_entry"] == "build_real_runtime"
        assert so.engine_kind_for(prefix_source="v2_behavior",
                                  runtime=runtime) == "simulation_engine_public"
        assert so.execution_kind_for(prefix_source="v2_behavior",
                                     runtime=runtime) == so.EXECUTION_REAL
        identity = dict(runtime["engine_identity"])
        assert identity["class"] == "SimulationEngine"
        assert identity["fixture_mode"] is False
        assert identity["engine_version"]  # 实际引擎版本（规则源摘要）来自引擎对象
        assert runtime.get("real_tables") is True

    def test_injected_real_runtime_not_mislabelled_as_double(self):
        """(c)：engine_kind 由运行时**种类**决定，不由「是否传入 runtime」决定。"""

        rules, _ = _real_rules_with_limits()
        injected = so.build_real_runtime(
            rules_config=rules.config, rounds_per_game=8, seed=6)
        # 显式传入的真实运行时必须仍标真实（旧实现按 runtime is not None 误标替身）。
        assert so.engine_kind_for(prefix_source="v2_behavior",
                                  runtime=injected) == "simulation_engine_public"
        double = so.build_test_runtime_double(rules=rules)
        assert so.engine_kind_for(prefix_source="v2_behavior",
                                  runtime=double) == "simulation_runtime_double"
        assert so.execution_kind_for(prefix_source="v2_behavior",
                                     runtime=double) == so.EXECUTION_TEST_DOUBLE
        assert so.engine_kind_for(prefix_source="scripted_fixture",
                                  runtime=None) == "scripted_fixture_engine"

    def test_unlabelled_runtime_refused(self):
        """无装配标签的运行时无法区分真伪：拒绝（fail-closed，不猜）。"""

        import c1_runtime_double as double

        rules, limits = _real_rules_with_limits()
        raw = double.build_runtime_double(rules, limits)  # 刻意不打标签
        assert "runtime_kind" not in raw
        with pytest.raises(so.RuntimeAssemblyError, match="runtime_kind"):
            so.run_real_prefix_attempt(
                runtime=raw, rules=rules, predicate_id="branch_open", focal_seat=0,
                attempt_index=0, source_root_id="r", match_id="m",
                tournament_config=None, seed=0)

    def test_missing_runtime_refused_not_defaulted_to_double(self):
        """(a)：真实路径缺 runtime 即拒绝，绝不自动注入替身。"""

        rules, _ = _real_rules_with_limits()
        with pytest.raises(so.RuntimeAssemblyError, match="显式装配"):
            so.run_real_prefix_attempt(
                runtime=None, rules=rules, predicate_id="branch_open", focal_seat=0,
                attempt_index=0, source_root_id="r", match_id="m",
                tournament_config=None, seed=0)

    def test_prefix_behavior_missing_is_refused(self):
        """M2：前缀行为策略缺失即拒绝，不落回「三家 V2」缺省。"""

        rules, limits = _real_rules_with_limits()
        with pytest.raises(so.RuntimeAssemblyError, match="行为策略"):
            so.run_real_prefix_attempt(
                runtime=so.build_test_runtime_double(rules=rules,
                                                     value_limits=limits),
                rules=rules, predicate_id="branch_open", focal_seat=0,
                attempt_index=0, source_root_id="r", match_id="m",
                tournament_config=None, seed=0)


class TestPrefixBehaviorScenarioBinding:
    """M2 修复：前缀行为策略从冻结合同装配，身份绑定根摘要并核对执行记录。"""

    def test_m_scenario_prefix_assembles_m_opponents(self, tmp_path, monkeypatch):
        expected = _contract_opponent_names("M")
        assert expected != ["weighted_heuristic_v2"] * 3  # H 缺省确实不等价
        # 回归见证：装配确实**按合同 M 名字**向白名单工厂取策略（旧缺省是三家 V2）。
        asked = []
        real_build = so.stage.build_panel_policy

        def recording(name, monotonic):
            asked.append(str(name))
            return real_build(name, monotonic)

        monkeypatch.setattr(so.stage, "build_panel_policy", recording)
        panel = _m_scenario_panel(tmp_path, "M")
        behavior = panel["prefix_behavior"]
        assert behavior["opponent_scenario"] == "M"
        assert behavior["expected_opponent_names"] == expected
        assert set(expected) <= set(asked), (expected, asked)
        rows = {row["seat"]: row for row in behavior["by_seat"]}
        assert [rows[seat]["assigned_name"] for seat in (1, 2, 3)] == expected
        # 装配对象的**类**逐座位对上合同情景（M 的第 2/3 家不是 V2）。
        assert rows[2]["policy_class"] == "WhiteDiscardGuardPolicy"
        assert rows[3]["policy_class"] == "ReliableHeuristicPolicyV1"
        # 执行记录与装配对象逐座位对账（对象 token 相同才认；不只看字符串标签）。
        executed = {row["seat"]: row for row in behavior["execution"]["by_seat"]}
        assert executed, "执行记录为空：无法核对装配对象是否真的被使用"
        for seat, record in executed.items():
            assert record["object_token"] == rows[seat]["object_token"]
            assert record["policy_class"] == rows[seat]["policy_class"]
            assert record["windows"] > 0
        assert behavior["object_identity_checked"] is True
        assert behavior["verified"] is True
        # R9/A3：前缀行为绑定记的根身份 = 面板快照的**完整根身份**（描述符），不再
        # 依赖调用方给的 root_label 前缀（标签只是展示，身份由生成器/子场景/情景/
        # 实际种子/序号决定）。
        snapshot = panel["scenarios"][0]["snapshot"]
        assert behavior["prefix_actions_sha256"]
        assert behavior["source_root_id"] == snapshot["source_root_id"]
        assert behavior["source_root_id"] == snapshot["root_descriptor"]["root_id"]
        assert snapshot["root_descriptor"]["opponent_mix"] == "M"

    def test_h_scenario_prefix_assembles_h_opponents(self, tmp_path):
        """H 情景不因此反推错标：H 的合同对手就是三家 V2，且确实被执行。"""

        expected = _contract_opponent_names("H")
        panel = _m_scenario_panel(tmp_path, "H")
        behavior = panel["prefix_behavior"]
        assert behavior["expected_opponent_names"] == expected
        assert behavior["verified"] is True
        assert [row["assigned_name"] for row in behavior["by_seat"] if row["seat"] != 0]             == ["weighted_heuristic_v2"] * 3

    def test_binding_check_rejects_label_only_match(self):
        """标签全对但执行对象不是装配对象 → 判定不通过（不只看字符串）。"""

        rules, _ = _real_rules_with_limits()
        assembled = so.frozen_generation_policies(
            opponent_names=_contract_opponent_names("M"), focal_seat=0,
            monotonic=lambda: 800.0)
        by_seat = [{"seat": seat, "assigned_name": name, "policy_id": "",
                    "policy_class": type(assembled[seat]).__name__,
                    "object_token": "obj:deadbeef", "windows": 1}
                   for seat, name in enumerate(
                       ["weighted_heuristic_v2", "weighted_heuristic_v2",
                        "weighted_heuristic_v2_white_guard", "weighted_heuristic_v1"])]
        verdict = so.verify_prefix_behavior_binding(
            opponent_scenario="M", expected_opponent_names=_contract_opponent_names("M"),
            policies_by_seat=assembled, focal_seat=0,
            execution={"by_seat": by_seat}, check_object_identity=True)
        assert verdict["ok"] is False
        assert any("对象" in problem for problem in verdict["problems"])

    def test_binding_check_rejects_wrong_scenario_policies(self):
        """装配的对手与合同情景不符（H 替 M）→ 判定不通过。"""

        assembled = so.frozen_generation_policies(
            opponent_names=["weighted_heuristic_v2"] * 3, focal_seat=0,
            monotonic=lambda: 800.0)
        verdict = so.verify_prefix_behavior_binding(
            opponent_scenario="M", expected_opponent_names=_contract_opponent_names("M"),
            policies_by_seat=assembled, focal_seat=0, execution=None,
            check_object_identity=False)
        assert verdict["ok"] is False
        assert any("合同情景" in problem for problem in verdict["problems"])


class TestExecutionEvidenceFromRecords:
    """A1(d)：逐桌决策计数、完成原因、费用来自执行记录；面板不再硬编码红线。"""

    def test_panel_engine_kind_and_red_line_from_execution(self, tmp_path):
        panel = _m_scenario_panel(tmp_path, "M")
        assert panel["engine_kind"] == "simulation_runtime_double"
        assert panel["execution_kind"] == so.EXECUTION_TEST_DOUBLE
        red = panel["budget_red_line"]
        assert red["execution_kind"] == so.EXECUTION_TEST_DOUBLE
        assert red["real_table_instances_started"] == 0
        assert red["double_table_instances"] == panel["prefix_attempts"]["total"]
        assert panel["strength_evidence"] is False
        assert panel["selection_eligible"] is False
        arm = panel["scenarios"][0]["double_arm"]["arms"]["baseline"]
        for table in arm["tables"]:
            assert table["decisions"] >= 0            # 逐桌决策计数来自执行记录
            assert table["completion_reason"]         # 完成原因来自执行记录
        assert arm["runtime_kind"] == so.RUNTIME_KIND_TEST_DOUBLE
        assert arm["execution_kind"] == so.EXECUTION_TEST_DOUBLE
        assert arm["decisions_total"] == sum(t["decisions"] for t in arm["tables"])

# ---------------------------------------------------------------------------
# P9b（R8 修复轮 · 复审 §4 A5 上游读数）：截取窗口内候选臂与基线臂各自的动作
#
# 依据：R8-FIX-PLAN-2026-09-17.md §2.0「P9b · A5 上游读数」——「同一可见窗口
# 双方动作」需在 sitin_opportunities.py 采集两臂动作并填入 P9 预留位置。读数
# **只来自执行记录**（resume_match 在截取帧写下的 MatchDecisionRecord）：不是
# 源码里的字段名、不是默认值、不是推测值。某臂未到达截取窗口或在该窗口无法
# 行动时，如实登记「不可用/未到达」并给原因。
#
# P9（sitin_feedback）只在产物**确实登记**时采用读数，登记位置两个：
# `snapshot.window_actions` 与 `scenarios[i].double_arm.arms[*].
# focal_action_at_cut`；都没有即记 input gap（本文件逐条实测该联动，含反向
# 对照：把字段拿掉，缺口码必须重新出现）。
# ---------------------------------------------------------------------------

#: P9 投影的读数缺失码（核对用字面值；本包不复制 P9 实现）。
P9_ARM_ACTIONS_GAP = "window.arm_actions_not_collected"


def _json_pointer(document, pointer):
    """按 JSON 指针（/a/b/0）在产物里取值（对账口径与 P9 一致）。"""

    node = document
    for part in [item for item in str(pointer).split("/") if item != ""]:
        node = node[int(part)] if isinstance(node, list) else node[part]
    return node


def _recursive_keys(payload):
    """递归收集映射键名（T09 红线核查用）。"""

    if isinstance(payload, dict):
        for key, value in payload.items():
            yield key
            yield from _recursive_keys(value)
    elif isinstance(payload, (list, tuple)):
        for item in payload:
            yield from _recursive_keys(item)


def _no_emergency_rules():
    """无紧急候选的规则桩（与 T16 同一构造：策略抛错时该窗口无动作可选）。"""

    from hangma_bot.hangma.interface import (
        RuleAnalysis, RuleCandidate, RuleCompleteness, RuleIssue,
    )
    from hangma_bot.kernel.actions import Discard, Pass, Tile

    candidates = (
        RuleCandidate(action=Pass(), action_key="pass", evidence=()),
        RuleCandidate(action=Discard(Tile("1t")), action_key="discard:1t", evidence=()),
    )
    stub = type("StubNoEmergencyP9b", (), {})()

    def analyze(observation, value_limits=None):
        return RuleAnalysis(
            legal_candidates=candidates, emergency_candidate=None,
            completeness=RuleCompleteness.COMPLETE, ruleset_version="p9b-stub",
            issues=(RuleIssue("stub", "P9b 构造：无紧急候选"),),
        )

    stub.analyze = analyze
    return stub


class _MockNaturalDrive:
    """P9 mock 迭代的自然面板替身桌驱动（0 真实桌赛；只看焦点策略身份给分）。"""

    def __call__(self, *, plan, policies_by_seat, versions_block, step_limit,
                 value_limits):
        seats = list(plan.seats())
        focal_idx = (seats.index("focal") if "focal" in seats
                     else seats.index("natural:focal"))
        policy = policies_by_seat[focal_idx]
        is_candidate = str(getattr(policy, "policy_id", "")).startswith("action_value")
        focal = 12.0 if is_candidate else -10.0
        others = iter((5.0, 3.0, 1.0))
        scores = [focal if seat == focal_idx else next(others) for seat in range(4)]
        return {"table_id": plan.table_id, "seed": int(plan.seed),
                "match_status": "complete", "wall_ms": 1.0,
                "scores_by_seat": scores, "result": {}}


class TestWindowArmActionsP9b:
    """P9b：截取窗口两臂动作读数（登记 / 身份绑定 / 诚实缺读数 / P9 联动）。"""

    def _fixture_panel(self, out_dir):
        """夹具机会面板（零真实桌赛）：两臂读数由夹具双臂续打真实执行产生。"""

        return so.build_panel(
            prefix_source="scripted_fixture", predicate_id="branch_open",
            focal_seat=0, opponent_scenario="H", root_label="p9b",
            out_dir=out_dir, ruleset_version=so.DEFAULT_RULESET_VERSION,
            base_score=1, you_cai_bi_kao=False,
            attempts_cap=so.PREFIX_ATTEMPT_CAP, panel_seed=20260916)

    def _bound_conditional_dir(self, tmp_path):
        """按 P9 的绑定口径摆放产物：<cond>/panel-<谓词>/panel.json + evaluation.json。

        evaluation.json 是**最小占位**（只为 P9 的同目录绑定口径）：本包要验的是
        P9 读窗口读数与缺口那一段，统计块不属本包。
        """

        cond = tmp_path / "conditional"
        panel = self._fixture_panel(cond / "panel-branch_open")
        (cond / "evaluation.json").write_text(
            json.dumps({
                "schema": "sitin-av-evaluation/1",
                "identity": {"candidate_id": "p9b-candidate"},
                "panel": {"generator": so.GENERATOR_SCRIPTED_FIXTURE,
                          "prefix_source": "scripted_fixture",
                          "predicate": "branch_open",
                          "prefix_attempts": panel.get("prefix_attempts")},
                "execution_kind": so.EXECUTION_SCRIPTED_FIXTURE,
                "engine_kind": panel.get("engine_kind"),
                "real_table_instances": 0,
                "double_table_instances": 0,
                "double_arm": {"valid": False, "arms": {},
                               "declared_endpoint": "stage_complete"},
                "admission": {"coverage": {"status": "PENDING"}},
                # 统计块只给程序口径条目需要的 min_roots；本包不验统计读数
                # （缺读数拒绝由 _reading_refusals 如实上报，不属本包）。
                "statistics": {"min_roots": 1, "by_candidate": {},
                               "invalid_count": 0, "uncomputable_count": 0,
                               "n_samples": 0},
            }, ensure_ascii=False),
            encoding="utf-8")
        return cond, panel

    # -- 1. 登记：产物里有两臂在截取窗口的动作读数 ---------------------------

    def test_snapshot_registers_both_arm_actions_at_cut_window(self, tmp_path):
        panel = self._fixture_panel(tmp_path)
        scenario = panel["scenarios"][0]
        assert scenario["status"] == "sampled"
        snapshot = scenario["snapshot"]
        window_actions = snapshot["window_actions"]
        assert window_actions["schema"] == so.WINDOW_ACTIONS_SCHEMA
        assert window_actions["root_id"] == snapshot["source_root_id"]
        assert window_actions["window_key"] == snapshot["cut_window"]
        assert window_actions["collected_arms"] == ["baseline", "candidate"]
        assert window_actions["source"].startswith("resume_match")
        readings = {}
        for arm_name in ("baseline", "candidate"):
            arm = scenario["double_arm"]["arms"][arm_name]
            assert arm["focal_action_at_cut_status"] == so.ARM_ACTION_COLLECTED
            reading = arm["focal_action_at_cut"]
            assert isinstance(reading, dict)
            assert reading["arm"] == arm_name
            assert reading["root_id"] == snapshot["source_root_id"]
            assert reading["window_key"] == snapshot["cut_window"]
            assert reading["seat"] == snapshot["cut_window"]["seat"]
            assert reading["arm_status"] == "complete"
            assert reading["action_key"]
            assert reading["action_key"] == \
                window_actions["arms"][arm_name]["action_key"]
            assert reading["decision_id"] and reading["policy_id"]
            readings[arm_name] = reading["action_key"]
        # 夹具两臂焦点行为策略不同（基线偏好 pass、候选偏好 peng:5w）：读数必须分叉，
        # 同一默认值/占位符不可能同时满足两侧。
        assert readings["candidate"] == "peng:5w"
        assert readings["baseline"] != readings["candidate"]
        # T09 红线：读数只含公开动作事实，键名不含 WorldState 私有字段名。
        assert set(_recursive_keys(window_actions)) & set(so.FORBIDDEN_SNAPSHOT_KEYS) \
            == set()

    # -- 2. 身份绑定与可对账（产物路径 + JSON 指针 + 臂结局交叉印证） ---------

    def test_reading_matches_arm_outcome_and_resolves_by_json_pointer(self, tmp_path):
        panel = self._fixture_panel(tmp_path)
        scenario = panel["scenarios"][0]
        snapshot = scenario["snapshot"]
        arms = scenario["double_arm"]["arms"]
        window_actions = snapshot["window_actions"]
        candidate_action = arms["candidate"]["focal_action_at_cut"]["action_key"]
        baseline_action = arms["baseline"]["focal_action_at_cut"]["action_key"]
        # 独立交叉核对：夹具 outcome_branch 以截取窗口焦点选择为键（seat0:peng:5w
        # 与 default 两支），臂的当前桌终局积分反过来印证读数——不是回读同一字段。
        assert candidate_action == "peng:5w"
        assert arms["candidate"]["tables"][0]["scores_by_seat"] == [6, -2, -2, -2]
        assert baseline_action != "peng:5w"
        assert arms["baseline"]["tables"][0]["scores_by_seat"] == [2, 0, -1, -1]
        # 截取窗口不在已执行前缀里（截取 = 首次命中谓词、该窗口尚未行动）。
        prefix_windows = [step["window_key"] for step in snapshot["legal_action_prefix"]]
        assert snapshot["cut_window"] not in prefix_windows
        # 每臂读数都带该臂在截取帧对齐的执行记录条数（续打确实从截取帧开始）。
        assert arms["baseline"]["focal_action_at_cut"]["cut_frame_records_matched"] == 2
        assert arms["candidate"]["focal_action_at_cut"]["cut_frame_records_matched"] == 2
        # 对账：读数用「产物路径 + JSON 指针」在 panel.json 里逐项取回。
        document = json.loads((tmp_path / "panel.json").read_text(encoding="utf-8"))
        pointers = window_actions["artifact_locator"]["pointers"]
        assert _json_pointer(document, pointers["snapshot.window_actions"]) \
            == window_actions
        for arm_name in ("baseline", "candidate"):
            assert _json_pointer(
                document, pointers["arms.{0}.focal_action_at_cut".format(arm_name)]
            ) == arms[arm_name]["focal_action_at_cut"]

    # -- 3. 不可用：该臂在截取窗口无法行动（策略抛错且无紧急候选） -----------

    def test_arm_unable_to_act_at_cut_window_registered_unavailable(self):
        snapshot, _ = _generate_hit_snapshot()
        opponent = so.FixtureBehaviorPolicy("fixture-opponent-standin", prefer=("pass",))
        by_seat_baseline = [opponent] * 4
        by_seat_baseline[0] = so.FixtureBehaviorPolicy(
            "fixture-baseline-focal", prefer=("pass",))
        by_seat_candidate = [opponent] * 4
        by_seat_candidate[0] = so.RaisingPolicy("p9b-candidate-focal")
        result = so.run_double_arm(
            rules=_no_emergency_rules(), snapshot=snapshot,
            baseline_policies_by_seat=by_seat_baseline,
            candidate_policies_by_seat=by_seat_candidate,
            config=so._driver_config())
        assert result["valid"] is False
        candidate = result["arms"]["candidate"]
        assert candidate["status"] == "error"
        # 该臂到达了窗口但没有可执行动作：读数不可用，且**不留空字段冒充已采集**。
        assert candidate["focal_action_at_cut"] is None
        assert candidate["focal_action_at_cut_status"] == so.ARM_ACTION_UNAVAILABLE
        assert candidate["focal_action_at_cut_reason"]
        assert "policy_error" in candidate["focal_action_at_cut_reason"]
        assert str(snapshot["cut_window"]["trigger_seq"]) in \
            candidate["focal_action_at_cut_reason"]
        baseline = result["arms"]["baseline"]
        assert baseline["focal_action_at_cut_status"] == so.ARM_ACTION_COLLECTED
        assert baseline["focal_action_at_cut"]["action_key"] == "pass"
        window_actions = result["window_actions"]
        assert window_actions["collected_arms"] == ["baseline"]
        assert window_actions["arms"]["candidate"]["status"] == so.ARM_ACTION_UNAVAILABLE
        assert window_actions["arms"]["candidate"]["action_key"] is None
        assert window_actions["arms"]["candidate"]["reason"] == \
            candidate["focal_action_at_cut_reason"]
        assert window_actions["arms"]["baseline"]["action_key"] == "pass"

    # -- 4. 未到达：该臂在截取窗口之前就失败（前缀重建被拒） ------------------

    def test_arm_never_reaching_cut_window_is_not_faked(self):
        snapshot, _ = _generate_hit_snapshot()
        tampered = copy.deepcopy(dict(snapshot))
        tampered["legal_action_prefix"][0]["action_key"] = "peng:9b"  # 非法前缀
        result = so.run_double_arm(
            rules=real_rules(), snapshot=tampered,
            baseline_policies_by_seat=[so.FixtureBehaviorPolicy("b")] * 4,
            candidate_policies_by_seat=[so.FixtureBehaviorPolicy("c")] * 4,
            config=so._driver_config())
        assert result["valid"] is False
        for arm in result["arms"].values():
            assert arm["status"] == "error"
            assert arm["focal_action_at_cut"] is None
            assert arm["focal_action_at_cut_status"] == so.ARM_ACTION_NOT_REACHED
            assert "重建" in arm["focal_action_at_cut_reason"]
        # 两臂都没有读数 → 不生成 window_actions（P9 侧宁可按缺读数上报，
        # 也不接受空壳/默认值冒充已采集）。
        assert result["window_actions"] is None
        # 单元口径：未到达分支不接受任何「动作」入参，只登记状态与原因。
        single = so.cut_window_arm_reading(
            arm_name="baseline", snapshot=snapshot, decisions=(),
            arm_status="error", reached=False, reason="测试：未到达")
        assert single["focal_action_at_cut"] is None
        assert single["focal_action_at_cut_status"] == so.ARM_ACTION_NOT_REACHED
        assert single["focal_action_at_cut_reason"] == "测试：未到达"

    # -- 5. P9 联动：投影自动采用读数（不再记 input gap） --------------------

    def test_p9_projection_adopts_readings_and_drops_input_gap(self, tmp_path):
        import sitin_feedback as sf

        cond, panel = self._bound_conditional_dir(tmp_path)
        snapshot = panel["scenarios"][0]["snapshot"]
        inputs = sf.collect_feedback_inputs(cond, parent_cid=None, candidate_cid=None)
        projection = sf.build_feedback_projection(inputs)
        codes = [gap["code"] for gap in projection["gaps"]]
        assert P9_ARM_ACTIONS_GAP not in codes
        item = next(item for item in projection["facts_items"]
                    if item["key"] == "window.actions")
        assert "本批产物未采集该读数" not in item["text"]
        assert "不推算" not in item["text"]
        for arm_name in ("baseline", "candidate"):
            assert snapshot["window_actions"]["arms"][arm_name]["action_key"] \
                in item["text"]
        # 投影条目仍带窗口身份（可追性不因新增读数而退化）。
        assert item["root_id"] == snapshot["source_root_id"]
        assert item["window"] == snapshot["cut_window"]

    def test_p9_projection_still_reports_gap_when_readings_absent(self, tmp_path):
        import sitin_feedback as sf

        cond, panel = self._bound_conditional_dir(tmp_path)
        assert panel["scenarios"][0]["snapshot"]["window_actions"]
        panel_path = cond / "panel-branch_open" / "panel.json"

        def _project():
            return sf.build_feedback_projection(
                sf.collect_feedback_inputs(cond, parent_cid=None,
                                           candidate_cid=None))

        def _actions_item(projection):
            return next(item for item in projection["facts_items"]
                        if item["key"] == "window.actions")

        # 变体 A：只去掉 snapshot.window_actions（保留 arms[*].focal_action_at_cut）
        # → P9 走第二个预留位置，仍不记缺口。
        document = json.loads(panel_path.read_text(encoding="utf-8"))
        document["scenarios"][0]["snapshot"].pop("window_actions")
        panel_path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
        projection = _project()
        assert P9_ARM_ACTIONS_GAP not in [gap["code"] for gap in projection["gaps"]]
        # P9 的第二个登记位置返回「臂名 → 读数」映射：两臂动作键都在条目里。
        text = _actions_item(projection)["text"]
        assert '"baseline"' in text and '"candidate"' in text
        for arm_name in ("baseline", "candidate"):
            assert panel["scenarios"][0]["double_arm"]["arms"][arm_name][
                "focal_action_at_cut"]["action_key"] in text

        # 变体 B：两个登记位置都去掉（= 旧产物/两臂都未到达）→ 缺口码必须回来，
        # 且条目如实写"未采集"，不拿字段名顶替读数。
        for name in ("baseline", "candidate"):
            document["scenarios"][0]["double_arm"]["arms"][name].pop(
                "focal_action_at_cut", None)
        panel_path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
        projection = _project()
        assert P9_ARM_ACTIONS_GAP in [gap["code"] for gap in projection["gaps"]]
        assert "本批产物未采集该读数" in _actions_item(projection)["text"]

    # -- 6. 端到端：正式 mock 迭代产物 → P9 投影无缺口 -----------------------

    def test_end_to_end_iteration_feedback_has_no_arm_actions_gap(self, tmp_path,
                                                                  monkeypatch):
        import sitin_feedback as sf
        import sitin_natural_panel as natural
        import sitin_search as search

        monkeypatch.setattr(natural, "execute_natural_table", _MockNaturalDrive())
        token = {"authorized": True, "batch": 7,
                 "budgets": {"tokens_input": 100000, "tokens_output": 200000,
                             "tables_full": 256, "tables_partial": 64,
                             "prefix_generation": 64}}
        run_root = tmp_path / "run"
        run_root.mkdir(parents=True, exist_ok=True)
        result = search.run_av_evolution(
            run_root, generation_mode="mock", seed_name="efficiency_seed",
            panel_seed=20260916, natural_roots=1, natural_seats=1,
            authorization=token)
        assert result.get("terminal") == "ITERATION_COMPLETE", result
        iter_dir = run_root / "iterations" / "iter-01"
        panel = json.loads(
            (iter_dir / "conditional" / "panel-branch_open" / "panel.json")
            .read_text(encoding="utf-8"))
        assert panel["scenarios"][0]["status"] == "sampled"
        snapshot = panel["scenarios"][0]["snapshot"]
        assert snapshot["window_actions"]["collected_arms"] == \
            ["baseline", "candidate"]
        # 主流程写出的反馈（同目录同一生成器）不再记该缺口。
        projection = json.loads(
            (iter_dir / "summary" / "feedback.json").read_text(encoding="utf-8"))
        assert P9_ARM_ACTIONS_GAP not in [gap["code"] for gap in projection["gaps"]]
        item = next(item for item in projection["facts_items"]
                    if item["key"] == "window.actions")
        assert "本批产物未采集该读数" not in item["text"]
        for arm_name in ("baseline", "candidate"):
            assert snapshot["window_actions"]["arms"][arm_name]["action_key"] \
                in item["text"]
        # 独立复算（同一生成器、同一产物）逐项一致：证明主流程没有自建第二套。
        state = json.loads((iter_dir / "state.json").read_text(encoding="utf-8"))
        expected = sf.build_feedback_projection(sf.collect_feedback_inputs(
            iter_dir, parent_cid=None,
            candidate_cid=state["identity"]["candidate_id"]))
        assert [gap["code"] for gap in expected["gaps"]] == \
            [gap["code"] for gap in projection["gaps"]]
        assert expected["facts"] == projection["facts"]

    # -- 7. 真实路由（v2_behavior + 显式测试替身）同样登记读数 ----------------

    def test_real_route_panel_registers_readings_too(self, tmp_path):
        """不是夹具专属：真实路由的面板同样登记两臂截取窗口动作（口径一致）。"""

        panel = _m_scenario_panel(tmp_path, "M")
        scenario = panel["scenarios"][0]
        snapshot = scenario["snapshot"]
        assert panel["prefix_source"] == "v2_behavior"
        assert snapshot["fixture_mode"] is False
        window_actions = snapshot["window_actions"]
        assert window_actions["schema"] == so.WINDOW_ACTIONS_SCHEMA
        assert window_actions["collected_arms"] == ["baseline", "candidate"]
        assert window_actions["root_id"] == snapshot["source_root_id"]
        assert window_actions["window_key"] == snapshot["cut_window"]
        for arm_name in ("baseline", "candidate"):
            arm = scenario["double_arm"]["arms"][arm_name]
            assert arm["focal_action_at_cut_status"] == so.ARM_ACTION_COLLECTED
            reading = arm["focal_action_at_cut"]
            assert reading["action_key"] == \
                window_actions["arms"][arm_name]["action_key"]
            assert reading["root_id"] == snapshot["source_root_id"]
            assert reading["window_key"] == snapshot["cut_window"]
            assert reading["arm_status"] == "complete"

