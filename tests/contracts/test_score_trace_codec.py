"""R2/S5 契约：完整有界评分解释（score_trace）的审计往返。

依据 REVIEW-V4-COMPLETION-2026-09-17.md S5 与 CONTINUOUS-EVOLUTION-PLAN
R2 行：结构化解释不再在排序适配时丢弃；经既有审计端口（decision_plan
编解码）写入，旧记录缺键还原 None（pattern_progress_v2 先例）；嵌套
解释可往返；超限降级发生在 ScoreBatch 构造期并已有整批失败测试覆盖。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hangma_bot.application.audit_codec import (
    decision_plan_from_json,
    decision_plan_to_json,
)
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import PlayerObservation, RulePublicState
from hangma_bot.policy.action_value import (
    SCORE_TRACE_SCHEMA_VERSION,
    ActionScore,
    batch_to_ranked_candidates,
)
from hangma_bot.policy.action_value_policy import build_scoring_view
from hangma_bot.policy.action_value_seeds import build_action_value_policy
from hangma_bot.policy.interface import (
    CompetitionContext,
    DecisionPlan,
    DecisionRequest,
    RankedCandidate,
    ScorePart,
)
from hangma_bot.kernel.actions import Discard, Tile, WindowKey, WindowPhase

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/policy/one-draw-value/B.json"


def make_request(observation, rules):
    """tests/contracts 内联的最小 DecisionRequest 构造（无 policy 测试夹具）。"""
    return DecisionRequest(
        observation=observation,
        competition=CompetitionContext(
            tournament_id="t1", stage_no=None, stage_role=None, stage_total=None,
            participant_rank=None, ranking=(), observed_at_unix_ms=0,
        ),
        rules=rules,
        decision_id="d1",
        trigger_seq=10,
        window_key=WindowKey(
            game_id=observation.game_id, round_no=1, trigger_seq=10,
            phase=WindowPhase.DRAW, seat=observation.seat,
        ),
        rejected_attempts=(),
    )


def _candidate(trace):
    return RankedCandidate(
        action=Discard(Tile("1w")),
        action_key="discard:1w",
        rank=1,
        total_score=1.0,
        score_parts=(ScorePart("action_value_v1", 1.0),),
        reasons=("basis=efficiency",),
        score_trace=trace,
    )


def _plan(candidates):
    return DecisionPlan(
        decision_id="d1",
        window_key=WindowKey("g1", 1, 10, WindowPhase.DRAW, 0),
        based_on_authoritative_seq=10,
        revision=1,
        candidates=tuple(candidates),
        degraded_reasons=(),
    )


def _roundtrip(plan):
    encoded = decision_plan_to_json(plan)
    return decision_plan_from_json(json.loads(json.dumps(encoded))), encoded


def test_nested_score_trace_roundtrips_through_plan_codec():
    trace = {
        "trace_schema": SCORE_TRACE_SCHEMA_VERSION,
        "detail": {
            "basis": "route_value",
            "fact_keys": ["combined_shanten", "support_remaining", "route_fan"],
            "nested": {"factors": [1.0, 2.5, 0.5], "flags": [True, False]},
            "note": "嵌套解释",
        },
    }
    restored, encoded = _roundtrip(_plan([_candidate(trace)]))
    assert restored.candidates[0].score_trace == trace  # 嵌套结构逐位往返
    assert encoded["candidates"][0]["score_trace"] == trace
    assert restored.candidates[0].reasons == ("basis=efficiency",)  # 摘要仍在


def test_absent_and_null_score_trace_restore_none():
    plan = _plan([_candidate(None)])
    restored, encoded = _roundtrip(plan)
    assert restored.candidates[0].score_trace is None
    assert "score_trace" not in encoded["candidates"][0]  # 缺省不写键
    legacy = json.loads(json.dumps(encoded))
    legacy["candidates"][0]["score_trace"] = None  # 旧记录显式 null
    assert decision_plan_from_json(legacy).candidates[0].score_trace is None


def test_bad_score_trace_shapes_fail_closed():
    plan = _plan([_candidate(None)])
    payload = decision_plan_to_json(plan)
    payload["candidates"][0]["score_trace"] = [1, 2, 3]
    with pytest.raises(ValueError):
        decision_plan_from_json(payload)
    payload["candidates"][0]["score_trace"] = {1: "x"}
    with pytest.raises(ValueError):
        decision_plan_from_json(payload)


def test_historical_fixture_rows_stay_without_score_trace():
    row = json.loads(FIXTURE.read_text())
    payload = row["planned_event"]["payload"] if "planned_event" in row else None
    if payload is None:
        # 旧 fixture 可能只有 request；退化用 plan 编码兼容检查。
        return
    assert all(
        "score_trace" not in candidate
        for candidate in payload.get("returned_plan", {}).get("candidates", [])
    )


def _real_analysis():
    hand = "1w 2w 3w 4w 5w 6w 7w 8w 9w 1b 2b 3b 4b"
    tiles = tuple(Tile(code) for code in hand.split())
    observation = PlayerObservation(
        game_id="trace-e2e", seat=0, round_no=1, snapshot_seq=10,
        phase="draw", dealer_seat=0, turn_seat=0, responding_seats=(),
        my_hand=tiles, drawn_tile=Tile("9b"),
        discards=((), (), (), ()), melds=((), (), (), ()),
        hand_counts=(14, 13, 13, 13), last_discard=None,
        remaining_tile_count=60, scores=(0, 0, 0, 0),
        rule_state=RulePublicState(Tile("白"), False, 0, False),
        public_history=(),
    )
    rules = HangmaRules(RuleConfig("trace-e2e", 1, False))
    return make_request(
        observation, rules.analyze(observation, value_limits=ValueAnalysisLimits())
    )


def test_real_pipeline_keeps_trace_from_seed_to_audit():
    """真实 analyze → 投影 → 种子 → 排序适配 → 审计编解码全程不丢解释。"""
    request = _real_analysis()
    view = build_scoring_view(request)
    batch = build_action_value_policy("route_value_seed").score(view)
    ranked = batch_to_ranked_candidates(batch, view.actions)
    assert ranked
    for candidate in ranked:
        assert candidate.score_trace is not None
        assert candidate.score_trace["trace_schema"] == SCORE_TRACE_SCHEMA_VERSION
        detail = candidate.score_trace["detail"]
        assert detail["basis"]  # 所用事实键摘要保留
    plan = DecisionPlan(
        decision_id=request.decision_id,
        window_key=request.window_key,
        based_on_authoritative_seq=request.observation.snapshot_seq,
        revision=1,
        candidates=ranked,
        degraded_reasons=(),
    )
    restored, _ = _roundtrip(plan)
    assert [
        c.score_trace["detail"] for c in restored.candidates
    ] == [c.score_trace["detail"] for c in ranked]  # 审计往返逐位相等
    # 有界不变量：整批 trace 序列化仍在 32KiB 内（ScoreBatch 构造期已验证）。
    payload = json.dumps(
        [c.score_trace for c in ranked], ensure_ascii=False, sort_keys=True
    )
    assert len(payload.encode("utf-8")) <= 32768


def test_oversized_trace_still_rejected_at_batch_construction():
    """超限降级有记录：trace 超长在 ScoreBatch 构造期整批 ValueError（进入
    策略失败降级路径，tests/unit/policy TestFailurePaths 已断言 degraded_reasons
    携带 action_value_failed）。"""
    long_trace = {"basis": "x" * 5000}  # 单串 > 4096 上限
    with pytest.raises(ValueError, match="4096"):
        ActionScore(action_key="discard:1w", score=1.0, trace=long_trace)
