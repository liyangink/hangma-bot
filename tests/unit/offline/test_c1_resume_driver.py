# -*- coding: utf-8 -*-
"""C1 共享驱动循环与受控中途续打（resume_match）测试。

权威行为 SEARCH-SPACE-REDESIGN-2026-09-16.md §7.2 末段与 §14 T09/T16：

- drive_match 提取共享循环 _advance_frames 后行为不变（终态/决策/步数）；
- resume_match 从不透明世界对象续打到终点；截取帧尚未推进的响应者按该帧
  观察重新决策（不沿用基线预先选好的响应）；
- 重建核对 fail-closed：观察摘要不一致/缺失直接 ValueError；
- 全程零真实桌赛：SimpleNamespace 帧假引擎（tests/unit/offline 既有先例）。
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.hangma.interface import (
    RuleAnalysis,
    RuleCandidate,
    RuleCompleteness,
    RuleIssue,
)
from hangma_bot.kernel.actions import (
    Action,
    Discard,
    Pass,
    Tile,
    WindowKey,
    WindowPhase,
    action_key,
)
from hangma_bot.kernel.observation import PlayerObservation, RulePublicState
from hangma_bot.offline.evaluate import (
    MatchDriverConfig,
    _advance_frames,
    drive_match,
    frame_observation_summary,
    resume_match,
)


# ---------------------------------------------------------------------------
# 构造辅助：假引擎/假规则/脚本策略（只用公开类型；零真实桌赛）
# ---------------------------------------------------------------------------


def make_observation(seat: int, trigger_seq: int, *, hand=("1w", "2w", "9w")):
    return PlayerObservation(
        game_id="c1-m",
        seat=seat,
        round_no=1,
        snapshot_seq=trigger_seq,
        phase="draw",
        dealer_seat=0,
        turn_seat=seat,
        responding_seats=(),
        my_hand=tuple(Tile(code) for code in hand),
        drawn_tile=None,
        discards=((), (), (), ()),
        melds=((), (), (), ()),
        hand_counts=(3, 3, 3, 3),
        last_discard=None,
        remaining_tile_count=60,
        scores=(0, 0, 0, 0),
        rule_state=RulePublicState(Tile("白"), False, 0, False),
        public_history=(),
    )


def make_window(seat: int, trigger_seq: int, phase=WindowPhase.DRAW):
    return WindowKey(game_id="c1-m", round_no=1, trigger_seq=trigger_seq,
                     phase=phase, seat=seat)


def make_decision(seat: int, trigger_seq: int, phase=WindowPhase.DRAW):
    return SimpleNamespace(
        window_key=make_window(seat, trigger_seq, phase),
        observation=make_observation(seat, trigger_seq),
        timeout_seconds=3.0,
    )


class StubRules:
    """固定合法候选的规则桩：pass 始终合法，另给两张弃牌。"""

    def __init__(self, emergency: bool = True):
        candidates = [
            RuleCandidate(action=Pass(), action_key="pass", evidence=()),
            RuleCandidate(action=Discard(Tile("1w")), action_key="discard:1w", evidence=()),
            RuleCandidate(action=Discard(Tile("2w")), action_key="discard:2w", evidence=()),
        ]
        self.analysis = RuleAnalysis(
            legal_candidates=tuple(candidates),
            emergency_candidate=(candidates[1] if emergency else None),
            completeness=RuleCompleteness.COMPLETE,
            ruleset_version="c1-stub",
            issues=(RuleIssue("stub", "构造用规则桩"),),
        )

    def analyze(self, observation, value_limits=None):
        return self.analysis


class RecordingPolicy:
    """记录每次请求观察并按偏好选合法动作的最小策略。"""

    def __init__(self, policy_id: str, prefer: str = "pass"):
        self.policy_id = policy_id
        self.requests = []
        self._prefer = prefer

    async def choose(self, request, budget):
        self.requests.append(request)
        keys = {c.action_key: c for c in request.rules.legal_candidates}
        chosen = keys.get(self._prefer) or keys[min(keys)]
        from hangma_bot.policy.interface import DecisionPlan, RankedCandidate

        return DecisionPlan(
            decision_id=request.decision_id,
            window_key=request.window_key,
            based_on_authoritative_seq=request.observation.snapshot_seq,
            revision=1,
            degraded_reasons=(),
            candidates=(
                RankedCandidate(
                    action=chosen.action, action_key=chosen.action_key, rank=1,
                    total_score=1.0, score_parts=(), reasons=("recording",),
                ),
            ),
        )


class ScriptEngine:
    """脚本帧假引擎：start→帧 0；每次 advance 前进游标；窗口集必须整帧给出。"""

    def __init__(self, frames):
        self._frames = list(frames)
        self.frame_calls = 0
        self._cursor = 0
        self.advance_calls = []

    def start(self, spec):
        return SimpleNamespace(token=0)

    def frame(self, world):
        self.frame_calls += 1
        return self._frames[self._cursor]

    def advance(self, world, revision, choices):
        frame = self._frames[self._cursor]
        assert revision == frame.revision
        expected = [d.window_key for d in frame.decisions]
        assert [c.window_key for c in choices] == expected
        self.advance_calls.append(tuple(choices))
        self._cursor += 1
        return SimpleNamespace(token=0)


def choice(window_key, action: Action):
    return SimpleNamespace(window_key=window_key, action=action)


def driver_config(step_limit: int = 20) -> MatchDriverConfig:
    return MatchDriverConfig(
        clock_mode="logical", step_limit=step_limit, budget_policy=BudgetPolicy(),
        competition_tournament_id="c1",
    )


def frame_of(seats_seqs, revision):
    return SimpleNamespace(
        revision=revision,
        decisions=tuple(make_decision(seat, seq) for seat, seq in seats_seqs),
        completed_hands=0,
        final_scores=None,
        blocked_reason=None,
    )


def final_frame(revision, scores=(5, 0, 0, 0)):
    return SimpleNamespace(
        revision=revision, decisions=(), completed_hands=1,
        final_scores=scores, blocked_reason=None,
    )


SPEC = SimpleNamespace(match_id="c1-m", scenario_id="c1")


# ---------------------------------------------------------------------------
# 共享循环提取：drive_match 行为回归
# ---------------------------------------------------------------------------


class TestDriveMatchExtraction:
    def test_drive_match_complete_two_frames(self):
        engine = ScriptEngine([
            frame_of([(0, 1)], 1),
            frame_of([(1, 2)], 2),
            final_frame(3),
        ])
        policy = RecordingPolicy("p0")
        outcome = asyncio.run(drive_match(
            engine=engine, spec=SPEC,
            policies_by_seat=(policy, policy, policy, policy),
            rules=StubRules(), choice_factory=choice, config=driver_config(),
            now_monotonic=lambda: 800.0, wall_clock=None,
        ))
        assert outcome.status == "complete"
        assert outcome.final_scores == (5, 0, 0, 0)
        assert outcome.steps == 3
        assert len(outcome.decisions) == 2
        assert engine.advance_calls and all(len(c) == 1 for c in engine.advance_calls)

    def test_drive_match_step_limit_error_not_synthetic_draw(self):
        engine = ScriptEngine([frame_of([(0, 1)], 1)])
        policy = RecordingPolicy("p0")
        outcome = asyncio.run(drive_match(
            engine=engine, spec=SPEC,
            policies_by_seat=(policy, policy, policy, policy),
            rules=StubRules(), choice_factory=choice,
            config=driver_config(step_limit=1),
            now_monotonic=lambda: 800.0, wall_clock=None,
        ))
        assert outcome.status == "error"
        assert "步数上限" in outcome.error_reason

    def test_advance_frames_from_started_world_equals_drive_match(self):
        frames = [frame_of([(0, 1)], 1), final_frame(2)]
        policy_a = RecordingPolicy("a")
        via_drive = asyncio.run(drive_match(
            engine=ScriptEngine(frames), spec=SPEC,
            policies_by_seat=(policy_a,) * 4, rules=StubRules(),
            choice_factory=choice, config=driver_config(),
            now_monotonic=lambda: 800.0, wall_clock=None,
        ))
        engine = ScriptEngine(frames)
        policy_b = RecordingPolicy("a")
        world = engine.start(SPEC)
        via_shared = asyncio.run(_advance_frames(
            engine=engine, world=world, match_id=SPEC.match_id,
            policies_by_seat=(policy_b,) * 4, rules=StubRules(),
            choice_factory=choice, config=driver_config(),
            now_monotonic=lambda: 800.0, wall_clock=None,
        ))
        # 同一脚本：drive_match 与直接调共享循环产物逐字节一致（含审计行）。
        assert via_drive.to_json() == via_shared.to_json()


# ---------------------------------------------------------------------------
# resume_match：中途续打、未推进响应者重新决策、fail-closed 核对
# ---------------------------------------------------------------------------


class TestResumeMatch:
    def _mid_frames(self):
        # frame1 视为已在前缀中推进；续打从 frame2（含焦点 0 与未推进响应者 2）开始。
        return [
            frame_of([(1, 7)], 1),
            frame_of([(0, 10), (2, 10)], 2),
            final_frame(3, (6, -2, -2, -2)),
        ]

    def test_resume_from_mid_world_drives_to_declared_terminal(self):
        engine = ScriptEngine(self._mid_frames())
        engine.advance(engine.start(SPEC), 1, (choice(make_window(1, 7), Pass()),))
        summary = frame_observation_summary(engine.frame(SimpleNamespace(token=0)))
        policies = tuple(RecordingPolicy("s{0}".format(i)) for i in range(4))
        outcome = asyncio.run(resume_match(
            engine=engine, world=SimpleNamespace(token=0),
            policies_by_seat=policies, rules=StubRules(), choice_factory=choice,
            config=driver_config(), now_monotonic=lambda: 800.0, wall_clock=None,
            remaining_schedule={"declared_endpoint": "current_table_end"},
            stage_snapshot={"observation_summary": summary, "match_spec": {"match_id": "c1-m"}},
        ))
        assert outcome.status == "complete"
        assert outcome.final_scores == (6, -2, -2, -2)
        assert outcome.steps == 2  # 截取帧 + 终局帧

    def test_unadvanced_responder_redecides_on_frame_observation(self):
        engine = ScriptEngine(self._mid_frames())
        engine.advance(engine.start(SPEC), 1, (choice(make_window(1, 7), Pass()),))
        summary = frame_observation_summary(engine.frame(SimpleNamespace(token=0)))
        policies = tuple(RecordingPolicy("s{0}".format(i)) for i in range(4))
        asyncio.run(resume_match(
            engine=engine, world=SimpleNamespace(token=0),
            policies_by_seat=policies, rules=StubRules(), choice_factory=choice,
            config=driver_config(), now_monotonic=lambda: 800.0, wall_clock=None,
            remaining_schedule={"declared_endpoint": "current_table_end"},
            stage_snapshot={"observation_summary": summary, "match_spec": {"match_id": "c1-m"}},
        ))
        focal, responder = policies[0], policies[2]
        # 焦点与未推进响应者都在截取帧上按该帧观察重新决策（trigger_seq=10）。
        assert len(focal.requests) == 1
        assert len(responder.requests) == 1
        assert responder.requests[0].observation.snapshot_seq == 10
        assert responder.requests[0].window_key.seat == 2
        assert responder.requests[0].observation.snapshot_seq == 10
        # 续打内实际提交的响应来自该帧决策，而不是任何预选响应。
        cut_choices = engine.advance_calls[-1]
        assert {c.window_key.seat for c in cut_choices} == {0, 2}
        assert all(action_key(c.action) == "pass" for c in cut_choices)

    def test_tampered_observation_summary_fails_closed(self):
        engine = ScriptEngine(self._mid_frames())
        engine.advance(engine.start(SPEC), 1, (choice(make_window(1, 7), Pass()),))
        summary = frame_observation_summary(engine.frame(SimpleNamespace(token=0)))
        summary["decisions"][0]["hand_digest"] = "0" * 64  # 篡改摘要
        policies = tuple(RecordingPolicy("s{0}".format(i)) for i in range(4))
        with pytest.raises(ValueError, match="重建核对失败"):
            asyncio.run(resume_match(
                engine=engine, world=SimpleNamespace(token=0),
                policies_by_seat=policies, rules=StubRules(), choice_factory=choice,
                config=driver_config(), now_monotonic=lambda: 800.0, wall_clock=None,
                stage_snapshot={"observation_summary": summary},
            ))

    def test_missing_observation_summary_rejected(self):
        with pytest.raises(ValueError, match="observation_summary"):
            asyncio.run(resume_match(
                engine=SimpleNamespace(), world=SimpleNamespace(token=0),
                policies_by_seat=(RecordingPolicy("x"),) * 4, rules=StubRules(),
                choice_factory=choice, config=driver_config(),
                now_monotonic=lambda: 800.0, wall_clock=None,
                stage_snapshot={},
            ))

    def test_invalid_remaining_schedule_endpoint_rejected(self):
        engine = ScriptEngine(self._mid_frames())
        engine.advance(engine.start(SPEC), 1, (choice(make_window(1, 7), Pass()),))
        summary = frame_observation_summary(engine.frame(SimpleNamespace(token=0)))
        with pytest.raises(ValueError, match="declared_endpoint"):
            asyncio.run(resume_match(
                engine=engine, world=SimpleNamespace(token=0),
                policies_by_seat=(RecordingPolicy("x"),) * 4, rules=StubRules(),
                choice_factory=choice, config=driver_config(),
                now_monotonic=lambda: 800.0, wall_clock=None,
                remaining_schedule={"declared_endpoint": ""},
                stage_snapshot={"observation_summary": summary},
            ))

    def test_resume_reuses_shared_loop_with_prefetched_frame(self):
        import hangma_bot.offline.evaluate as evaluate_module

        engine = ScriptEngine(self._mid_frames())
        engine.advance(engine.start(SPEC), 1, (choice(make_window(1, 7), Pass()),))
        summary = frame_observation_summary(engine.frame(SimpleNamespace(token=0)))
        calls = []

        async def spy(**kwargs):
            calls.append(kwargs)
            return await _advance_frames(**kwargs)

        original = evaluate_module._advance_frames
        evaluate_module._advance_frames = spy
        try:
            asyncio.run(resume_match(
                engine=engine, world=SimpleNamespace(token=0),
                policies_by_seat=(RecordingPolicy("x"),) * 4, rules=StubRules(),
                choice_factory=choice, config=driver_config(),
                now_monotonic=lambda: 800.0, wall_clock=None,
                remaining_schedule={"declared_endpoint": "current_table_end"},
                stage_snapshot={"observation_summary": summary,
                                "match_spec": {"match_id": "c1-m"}},
            ))
        finally:
            evaluate_module._advance_frames = original
        assert len(calls) == 1
        assert calls[0]["first_frame"] is not None
        assert calls[0]["match_id"] == "c1-m"


# ---------------------------------------------------------------------------
# 观察摘要：确定性、JSON 往返、只含玩家可见事实
# ---------------------------------------------------------------------------


class TestFrameObservationSummary:
    def test_summary_deterministic_and_json_roundtrip(self):
        frame = frame_of([(0, 10), (2, 10)], 2)
        first = frame_observation_summary(frame)
        second = frame_observation_summary(frame)
        assert first == second
        roundtripped = json.loads(json.dumps(first))
        assert frame_observation_summary(frame) == roundtripped
        assert [d["seat"] for d in roundtripped["decisions"]] == [0, 2]

    def test_summary_contains_only_visible_fields(self):
        summary = frame_observation_summary(frame_of([(0, 10)], 2))
        allowed = {
            "game_id", "round_no", "trigger_seq", "phase", "seat", "snapshot_seq",
            "hand_digest", "hand_count", "drawn_tile", "remaining_tile_count", "scores",
        }
        for decision in summary["decisions"]:
            assert set(decision) == allowed
        assert set(summary) == {"revision", "completed_hands", "decision_count", "decisions"}
        # 手牌只落摘要不落原始牌值（面板产物不含可还原暗牌的明文）。
        assert "1w" not in json.dumps(summary)
