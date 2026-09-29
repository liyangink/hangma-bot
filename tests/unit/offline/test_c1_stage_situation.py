# -*- coding: utf-8 -*-
"""Q8（阶段处境投影）测试：驱动注入模拟已完成桌账，桌序另行记录。

权威依据 REVIEW-V4-COMPLETION-2026-09-17.md 补充缺口 Q8 与
CONTINUOUS-EVOLUTION-PLAN-2026-09-17.md R3：第二桌起策略可见自己座位的
阶段累计积分/名次分；模拟剩余桌数保留在 StageSituationProjection，
不占用官方阶段字段。验收形态：同手牌不同已知模拟阶段积分产生可见差异。

零真实桌赛：SimpleNamespace 帧假引擎（tests/unit/offline 既有先例）。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.hangma.interface import (
    RuleAnalysis,
    RuleCandidate,
    RuleCompleteness,
    RuleIssue,
)
from hangma_bot.kernel.actions import Pass, Tile, WindowKey, WindowPhase
from hangma_bot.kernel.observation import PlayerObservation, RulePublicState
from hangma_bot.offline.evaluate import (
    MatchDriverConfig,
    StageSituationProjection,
    drive_match,
    frame_observation_summary,
    resume_match,
)


def make_observation(seat: int, trigger_seq: int):
    return PlayerObservation(
        game_id="q8-m", seat=seat, round_no=1, snapshot_seq=trigger_seq,
        phase="draw", dealer_seat=0, turn_seat=seat, responding_seats=(),
        my_hand=(Tile("1w"), Tile("2w"), Tile("9w")), drawn_tile=None,
        discards=((), (), (), ()), melds=((), (), (), ()),
        hand_counts=(3, 3, 3, 3), last_discard=None, remaining_tile_count=60,
        scores=(0, 0, 0, 0), rule_state=RulePublicState(Tile("白"), False, 0, False),
        public_history=(),
    )


class StubRules:
    """固定合法候选（pass + 两张弃牌），无紧急依赖。"""

    def __init__(self):
        candidates = (
            RuleCandidate(action=Pass(), action_key="pass", evidence=()),
            RuleCandidate(action=Discard_tile("1w"), action_key="discard:1w", evidence=()),
            RuleCandidate(action=Discard_tile("2w"), action_key="discard:2w", evidence=()),
        )
        self.analysis = RuleAnalysis(
            legal_candidates=candidates, emergency_candidate=candidates[1],
            completeness=RuleCompleteness.COMPLETE, ruleset_version="q8",
            issues=(RuleIssue("stub", "Q8 构造"),),
        )

    def analyze(self, observation, value_limits=None):
        return self.analysis


def Discard_tile(code):  # noqa: N802  小构造器（避免与 kernel Discard 重名导入噪音）
    from hangma_bot.kernel.actions import Discard

    return Discard(Tile(code))


class StageAwarePolicy:
    """读 request.competition 的阶段处境并按焦点累计积分切换动作的测试策略。"""

    def __init__(self, policy_id: str, seat: int = 0):
        self.policy_id = policy_id
        self.seat = seat
        self.seen = []

    async def choose(self, request, budget):
        from hangma_bot.policy.interface import DecisionPlan, RankedCandidate

        own = next(
            (entry for entry in request.competition.ranking
             if entry.participant_id == "focal"), None)
        self.seen.append({
            "stage_no": request.competition.stage_no,
            "stage_total": request.competition.stage_total,
            "participant_rank": request.competition.participant_rank,
            "own_stage_score": None if own is None else own.total_score,
            "own_place_points": None if own is None else own.place_points,
            "games_played": None if own is None else own.games_played,
        })
        keys = {c.action_key: c for c in request.rules.legal_candidates}
        # 落后（累计 < -20）→ 保守 pass；否则激进弃 2w。
        behind = own is not None and own.total_score < -20
        chosen = keys["pass"] if behind else keys["discard:2w"]
        return DecisionPlan(
            decision_id=request.decision_id, window_key=request.window_key,
            based_on_authoritative_seq=request.observation.snapshot_seq,
            revision=1, degraded_reasons=(),
            candidates=(
                RankedCandidate(action=chosen.action, action_key=chosen.action_key,
                                rank=1, total_score=1.0, score_parts=(),
                                reasons=("stage-aware",)),
            ),
        )


class OneWindowEngine:
    """单决策帧 + 终局帧的最小公开契约引擎。"""

    def __init__(self):
        self._cursor = 0

    def start(self, spec):
        self._cursor = 0
        return SimpleNamespace(token=0)

    def frame(self, world):
        if self._cursor == 0:
            decision = SimpleNamespace(
                window_key=WindowKey(game_id="q8-m", round_no=2, trigger_seq=11,
                                     phase=WindowPhase.DRAW, seat=0),
                observation=make_observation(0, 11), timeout_seconds=3.0)
            return SimpleNamespace(revision=1, decisions=(decision,),
                                   completed_hands=1, final_scores=None,
                                   blocked_reason=None)
        return SimpleNamespace(revision=2, decisions=(), completed_hands=2,
                               final_scores=(1, 0, 0, 0), blocked_reason=None)

    def advance(self, world, revision, choices):
        self._cursor += 1
        return SimpleNamespace(token=0)


def driver_config() -> MatchDriverConfig:
    return MatchDriverConfig(clock_mode="logical", step_limit=10,
                             budget_policy=BudgetPolicy(),
                             competition_tournament_id="q8")


SPEC = SimpleNamespace(match_id="q8-m", scenario_id="q8")


def _situation(scores, *, table_no=2, tables=2, completed=1, places=(0, 0, 0, 0)):
    return StageSituationProjection(
        stage_table_no=table_no, tables_in_stage=tables,
        tables_completed=completed, rounds_per_game=8,
        stage_scores_by_seat=scores, place_points_by_seat=places,
        participant_ids_by_seat=("focal", "opp-0", "opp-1", "opp-2"),
    )


class TestStageSituationProjection:
    def test_construct_rejects_invalid_shapes(self):
        with pytest.raises(ValueError):
            StageSituationProjection(stage_table_no=0, tables_in_stage=2)
        with pytest.raises(ValueError):
            StageSituationProjection(stage_table_no=1, tables_in_stage=0)
        with pytest.raises(ValueError):
            StageSituationProjection(stage_table_no=1, tables_in_stage=2,
                                     stage_scores_by_seat=(1, 2, 3))

    def test_known_key_ranks_use_average_on_ties(self):
        situation = _situation((10, 10, -5, -5))
        ranks = situation.known_key_ranks()
        # 两块并列（10/10 与 -5/-5）→ 各共享区间平均 1.5 / 3.5。
        assert ranks == (1.5, 1.5, 3.5, 3.5)

    def test_competition_context_exposes_own_stage_facts(self):
        situation = _situation((3, -7, 1, 0), places=(1, -1, 0, 0))
        context = situation.competition_context("t", seat=0)
        # 模拟第 2 桌不能冒充官方第 2 阶段及官方阶段总数。
        assert context.stage_no is None and context.stage_total is None
        assert situation.stage_table_no == 2 and situation.tables_in_stage == 2
        own = context.ranking[0]
        assert own.participant_id == "focal"
        assert own.total_score == 3 and own.place_points == 1
        assert own.games_played == 8  # tables_completed(1) × rounds_per_game(8)
        assert context.participant_rank == 1

    def test_to_json_carries_remaining_tables(self):
        payload = _situation((0, 0, 0, 0)).to_json()
        assert payload["schema_version"] == "offline-stage-situation/2"
        assert payload["source_kind"] == "offline_simulation"
        assert payload["tables_remaining_after_current"] == 0
        assert payload["tables_completed"] == 1
        assert "god_count_modeling" in payload

    def test_official_stage_identity_is_not_inferred_from_simulated_table_progress(self):
        situation = _situation((0, 0, 0, 0), table_no=7, tables=9, completed=6)
        context = situation.competition_context("simulation", seat=0)
        assert (situation.stage_table_no, situation.tables_in_stage) == (7, 9)
        assert (context.stage_no, context.stage_total) == (None, None)
        assert context.ranking[0].games_played == 6 * situation.rounds_per_game


class TestDriverStageSituation:
    def test_same_hand_different_stage_scores_change_visible_action(self):
        """Q8 验收：同手牌（同帧/同规则）不同已知阶段积分 → 策略可见差异。"""
        rules = StubRules()
        outcomes = {}
        for label, scores in (("even", (0, 0, 0, 0)), ("behind", (-30, 5, 5, 20))):
            policy = StageAwarePolicy(label)
            outcome = asyncio.run(drive_match(
                engine=OneWindowEngine(), spec=SPEC,
                policies_by_seat=(policy, policy, policy, policy),
                rules=rules,
                choice_factory=lambda window_key, action: SimpleNamespace(
                    window_key=window_key, action=action),
                config=driver_config(), now_monotonic=lambda: 800.0,
                wall_clock=None, stage_situation=_situation(scores),
            ))
            assert outcome.status == "complete"
            outcomes[label] = (policy, outcome)
        even_policy, even_outcome = outcomes["even"]
        behind_policy, behind_outcome = outcomes["behind"]
        # 两个 run 的窗口观察逐字节一致（同手牌）。
        assert even_policy.seen[0]["own_stage_score"] == 0
        assert behind_policy.seen[0]["own_stage_score"] == -30
        # 同一可见观察下，已知阶段处境不同 → 选择不同动作（可见差异）。
        even_action = even_outcome.decisions[0].action_key
        behind_action = behind_outcome.decisions[0].action_key
        assert even_action == "discard:2w"
        assert behind_action == "pass"
        assert even_action != behind_action

    def test_resume_match_injects_stage_situation_after_cut(self):
        engine = OneWindowEngine()
        world = engine.start(SPEC)
        summary = frame_observation_summary(engine.frame(world))
        policy = StageAwarePolicy("resume")
        outcome = asyncio.run(resume_match(
            engine=engine, world=world,
            policies_by_seat=(policy, policy, policy, policy), rules=StubRules(),
            choice_factory=lambda window_key, action: SimpleNamespace(
                window_key=window_key, action=action),
            config=driver_config(), now_monotonic=lambda: 800.0, wall_clock=None,
            remaining_schedule={"declared_endpoint": "stage_complete"},
            stage_snapshot={"observation_summary": summary,
                            "match_spec": {"match_id": "q8-m"}},
            stage_situation=_situation((-25, 10, 8, 7)),
        ))
        assert outcome.status == "complete"
        assert policy.seen[0]["own_stage_score"] == -25
        assert outcome.decisions[0].action_key == "pass"

    def test_default_none_keeps_legacy_empty_context(self):
        policy = StageAwarePolicy("legacy")
        outcome = asyncio.run(drive_match(
            engine=OneWindowEngine(), spec=SPEC,
            policies_by_seat=(policy, policy, policy, policy), rules=StubRules(),
            choice_factory=lambda window_key, action: SimpleNamespace(
                window_key=window_key, action=action),
            config=driver_config(), now_monotonic=lambda: 800.0, wall_clock=None,
        ))
        assert outcome.status == "complete"
        seen = policy.seen[0]
        assert seen["stage_no"] is None and seen["stage_total"] is None
        assert seen["own_stage_score"] is None  # 旧口径：ranking 为空
        # 无处境时策略回退到默认偏好（激进弃牌），与 Q8 注入路径可区分。
        assert outcome.decisions[0].action_key == "discard:2w"
