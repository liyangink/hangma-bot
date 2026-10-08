"""坐隐 1.7 诊断工具自测。

守住四件"错了就会污染 L1 效果结论"的事：
  1. 影子包装器必须**原样返回驱动策略的计划对象**（身份相同，不是副本）；
  2. 影子抛异常/记录失败**绝不影响**真实动作，且要留下 shadow_error；
  3. 漏斗四阶段必须**严格嵌套**，且最深阶段构成一个划分（计数之和 = 记录数）；
  4. 实验设计级标识能从 `match_id` 正确推得。
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

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_REPO = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, _REPO / "src")))
sys.path.insert(0, str(_HERE))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _project_file(_PROJECT_ROOT, _HERE / (name + ".py")))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


diag = _load("sitin_diagnostics")

from hangma_bot.hangma.interface import (  # noqa: E402
    CandidateFactKind,
    CandidateFacts,
    RuleAnalysis,
    RuleCandidate,
    RuleCompleteness,
)
from hangma_bot.kernel.actions import (  # noqa: E402
    Chi,
    Discard,
    Pass,
    Peng,
    Tile,
    WindowKey,
    WindowPhase,
    action_key,
)
from hangma_bot.kernel.observation import (  # noqa: E402
    CompetitionContext,
    PlayerObservation,
    RulePublicState,
)
from hangma_bot.policy.interface import (  # noqa: E402
    DecisionBudget,
    DecisionPlan,
    DecisionRequest,
    RankedCandidate,
    ScorePart,
)


def _facts(shanten=3, useful=(("1w", 3), ("2w", 4))):
    from hangma_bot.hangma.interface import UsefulTileFact

    return CandidateFacts(
        CandidateFactKind.HAND_PROGRESS, shanten,
        useful_tiles=tuple(UsefulTileFact(code, n) for code, n in useful))


def _cand(action, facts=None):
    return RuleCandidate(action=action, action_key=action_key(action), evidence=(),
                         facts=facts)


def _observation(hand=()):
    return PlayerObservation(
        game_id="g1", seat=0, round_no=1, snapshot_seq=10, phase="draw",
        dealer_seat=0, turn_seat=0, responding_seats=(), my_hand=hand, drawn_tile=None,
        discards=((), (), (), ()), melds=((), (), (), ()),
        hand_counts=(13, 13, 13, 13), last_discard=None, remaining_tile_count=60,
        scores=(0, 0, 0, 0),
        rule_state=RulePublicState(wealth_god=Tile("白"), baotou=False,
                                   chain_count=0, catch_play=False),
        public_history=())


def _request(candidates, match_id="sitin-L1:scale-3:0123:weighted_heuristic_v2"):
    observation = _observation()
    return DecisionRequest(
        observation=observation,
        competition=CompetitionContext(
            tournament_id="scale-3", stage_no=None, stage_role=None, stage_total=None,
            participant_rank=None, ranking=(), observed_at_unix_ms=0),
        rules=RuleAnalysis(legal_candidates=tuple(candidates), emergency_candidate=None,
                           completeness=RuleCompleteness.COMPLETE,
                           ruleset_version="test", issues=()),
        decision_id="d1", trigger_seq=10,
        window_key=WindowKey(game_id=match_id, round_no=1, trigger_seq=10,
                             phase=WindowPhase.DRAW, seat=0),
        rejected_attempts=())


def _plan(rows, decision_id="d1"):
    return DecisionPlan(
        decision_id=decision_id,
        window_key=WindowKey(game_id="sitin-L1:scale-3:0123:x", round_no=1,
                             trigger_seq=10, phase=WindowPhase.DRAW, seat=0),
        based_on_authoritative_seq=10, revision=1,
        candidates=tuple(
            RankedCandidate(action=action, action_key=key, rank=rank,
                            total_score=score, score_parts=(ScorePart("测试分项", score),),
                            reasons=(), is_emergency=False)
            for rank, (key, action, score) in enumerate(rows, start=1)),
        degraded_reasons=())


class _FixedPolicy:
    def __init__(self, plan, policy_id="p"):
        self._plan = plan
        self.policy_id = policy_id
        self.calls = 0

    async def choose(self, request, budget):
        self.calls += 1
        return self._plan


class _BoomPolicy:
    policy_id = "boom"

    async def choose(self, request, budget):
        raise RuntimeError("injected shadow failure")


def _sink(tmp_path) -> "diag.DiagnosticSink":
    return diag.DiagnosticSink(tmp_path / "diag.jsonl")


def _wrapped(tmp_path, driver, shadow, arm_role="baseline", **over):
    kwargs = dict(arm_role=arm_role, driver_identity="driver-id", shadow_identity="shadow-id",
                  baseline_identity="weighted_heuristic_v2", candidate_identity="m4-id",
                  ruleset_version="test", rule_config={"base_score": 1},
                  rules_hash="deadbeef", source_fingerprints={"x": "y"},
                  seed_by_scenario={"scale-3": 2026092003},
                  funnel=diag.m4_funnel, natural_of=lambda cands: 7)
    kwargs.update(over)
    return diag.ShadowPolicy(driver=driver, shadow=shadow, sink=kwargs.pop("sink"),
                             **kwargs)


# --- 硬性要求①②③ ----------------------------------------------------------

def test_shadow_policy_returns_the_driver_plan_object_unchanged(tmp_path):
    """影子绝不能改变真实动作：必须返回**同一个对象**，不是等值副本。"""

    plan = _plan([("pass", Pass(), -5.0), ("peng:1w", Peng(Tile("1w")), -9.0)])
    request = _request([_cand(Peng(Tile("1w")), _facts()), _cand(Pass(), _facts())])
    sink = _sink(tmp_path)
    policy = _wrapped(tmp_path, _FixedPolicy(plan), _FixedPolicy(plan), sink=sink)
    returned = asyncio.run(policy.choose(request, DecisionBudget(1.0, 2.0, 3.0)))
    assert returned is plan
    sink.close()


def test_shadow_failure_is_recorded_and_does_not_change_the_action(tmp_path):
    """影子抛异常：记录 shadow_error，但仍返回驱动计划，且真实动作不受影响。"""

    plan = _plan([("pass", Pass(), -5.0)])
    request = _request([_cand(Peng(Tile("1w")), _facts()), _cand(Pass(), _facts())])
    sink = _sink(tmp_path)
    driver = _FixedPolicy(plan)
    policy = _wrapped(tmp_path, driver, _BoomPolicy(), sink=sink)
    returned = asyncio.run(policy.choose(request, DecisionBudget(1.0, 2.0, 3.0)))
    assert returned is plan and driver.calls == 1
    sink.close()
    record = json.loads((tmp_path / "diag.jsonl").read_text().splitlines()[0])
    assert "RuntimeError" in record["shadow_error"]
    assert record["shadow_plan"] is None
    assert record["driver_plan"]["first"] == "pass"


def test_policy_id_is_forwarded(tmp_path):
    """不转发 policy_id 会让驱动记录该字段变 null。"""

    plan = _plan([("pass", Pass(), -5.0)])
    sink = _sink(tmp_path)
    policy = _wrapped(tmp_path, _FixedPolicy(plan, policy_id="weighted_heuristic_v2"),
                      _FixedPolicy(plan, policy_id="m4"), sink=sink)
    assert policy.policy_id == "weighted_heuristic_v2"
    sink.close()


# --- 标识推导 ---------------------------------------------------------------

def test_experiment_level_identifiers_are_derived_from_match_id(tmp_path):
    """seed / 换座 / 臂角色 / split_group_id 都必须能从 match_id 推得。"""

    plan = _plan([("pass", Pass(), -5.0)])
    request = _request([_cand(Peng(Tile("1w")), _facts()), _cand(Pass(), _facts())],
                       match_id="sitin-L1:scale-3:1230:weighted_heuristic_v2")
    sink = _sink(tmp_path)
    policy = _wrapped(tmp_path, _FixedPolicy(plan), _FixedPolicy(plan), sink=sink)
    asyncio.run(policy.choose(request, DecisionBudget(1.0, 2.0, 3.0)))
    sink.close()
    record = json.loads((tmp_path / "diag.jsonl").read_text().splitlines()[0])
    assert record["scenario_id"] == "scale-3"
    assert record["seat_permutation_label"] == "1230"
    assert record["arm_policy_id"] == "weighted_heuristic_v2"
    assert record["arm_role"] == "baseline"
    assert record["seed"] == 2026092003
    assert record["pair_id"] == "scale-3:1230"
    assert record["split_group_id"].startswith("split-")
    assert record["result_id"].startswith("r-")
    assert record["hand_id"].startswith("hand-")


def test_observation_digest_tracks_content_and_is_stable():
    assert diag.observation_digest(_observation()) == diag.observation_digest(_observation())
    changed = diag.observation_digest(_observation(hand=(Tile("1w"),)))
    assert changed != diag.observation_digest(_observation())


# --- plan_to_json -----------------------------------------------------------

def test_plan_to_json_preserves_rank_order_and_exposes_parts():
    # 分值随 rank 递减（-5 ≥ -9）→ 计划顺序就是分值顺序
    plan = _plan([("peng:1w", Peng(Tile("1w")), -5.0), ("pass", Pass(), -9.0)])
    out = diag.plan_to_json(plan)
    assert [row["action_key"] for row in out["candidates"]] == ["peng:1w", "pass"]
    assert [row["rank"] for row in out["candidates"]] == [1, 2]
    assert out["candidates"][0]["score_parts"] == {"测试分项": -5.0}
    assert out["first"] == "peng:1w"
    assert out["scores_monotone_non_increasing"] is True


def test_plan_to_json_flags_cross_tier_ordering():
    """跨可信层时分值不再单调，必须被标出来（否则会跨层相减）。"""

    plan = _plan([("peng:1w", Peng(Tile("1w")), -9.0), ("pass", Pass(), 5.0)])
    out = diag.plan_to_json(plan)
    assert out["scores_monotone_non_increasing"] is False


# --- 漏斗：严格嵌套 + 最深阶段构成划分 --------------------------------------

def _funnel_case(tmp_path, cands, base_rows, cand_rows):
    request = _request(cands)
    base = diag.plan_to_json(_plan(base_rows))
    cand = diag.plan_to_json(_plan(cand_rows))
    return diag.m4_funnel(request, base, cand, 7)


def test_funnel_reports_not_mechanism_window():
    # 没有吃碰候选 → 目标窗口不成立
    out = _funnel_case(None, [_cand(Discard(Tile("1w"))), _cand(Pass(), _facts())],
                       [("discard:1w", Discard(Tile("1w")), -1.0)],
                       [("discard:1w", Discard(Tile("1w")), -1.0)])
    assert out["mechanism_applicable"] is False
    assert out["deepest_stage"] == "not_mechanism_window"


def test_funnel_reports_facts_insufficient():
    request = _request([_cand(Peng(Tile("1w")), _facts()), _cand(Pass(), _facts())])
    base = diag.plan_to_json(_plan([("peng:1w", Peng(Tile("1w")), -9.0)]))
    cand = diag.plan_to_json(_plan([("peng:1w", Peng(Tile("1w")), -29.0)]))
    out = diag.m4_funnel(request, base, cand, None)   # natural=None
    assert out["mechanism_applicable"] is True
    assert out["facts_sufficient"] is False
    assert out["deepest_stage"] == "facts_insufficient"
    # 事实不足时即使分值变了也不算触发
    assert out["score_changed"] is False and out["triggered"] is False


def test_funnel_reports_score_unchanged():
    out = _funnel_case(None, [_cand(Peng(Tile("1w")), _facts()), _cand(Pass(), _facts())],
                       [("peng:1w", Peng(Tile("1w")), -9.0), ("pass", Pass(), -5.0)],
                       [("peng:1w", Peng(Tile("1w")), -9.0), ("pass", Pass(), -5.0)])
    assert out["score_changed"] is False
    assert out["deepest_stage"] == "score_unchanged"


def test_funnel_reports_first_choice_unchanged_despite_score_change():
    """评分变了但首选没变——这正是"没涨分"最需要区分的一类。"""

    out = _funnel_case(None, [_cand(Peng(Tile("1w")), _facts()), _cand(Pass(), _facts())],
                       [("pass", Pass(), -5.0), ("peng:1w", Peng(Tile("1w")), -9.0)],
                       [("pass", Pass(), -5.0), ("peng:1w", Peng(Tile("1w")), -29.0)])
    assert out["score_changed"] is True
    assert out["first_changed"] is False
    assert out["deepest_stage"] == "first_choice_unchanged"


def test_funnel_reports_triggered_when_first_choice_flips():
    out = _funnel_case(None, [_cand(Peng(Tile("1w")), _facts()), _cand(Pass(), _facts())],
                       [("peng:1w", Peng(Tile("1w")), -9.0), ("pass", Pass(), -5.0)],
                       [("pass", Pass(), -5.0), ("peng:1w", Peng(Tile("1w")), -29.0)])
    assert out["triggered"] is True
    assert out["deepest_stage"] == "first_changed"
    assert out["candidate_first_kind"] == "pass"
    assert out["baseline_first_kind"] == "peng"
    assert out["affected_score_deltas"] == {"peng:1w": -20.0}


def test_funnel_stages_are_strictly_nested(tmp_path):
    """阶段必须嵌套：后一阶段成立必然要求前一阶段成立。"""

    cases = [
        ([("pass", Pass(), -5.0)], None),
        ([("peng:1w", Peng(Tile("1w")), -9.0), ("pass", Pass(), -5.0)], 7),
    ]
    for rows, natural in cases:
        request = _request([_cand(Peng(Tile("1w")), _facts()), _cand(Pass(), _facts())])
        base = diag.plan_to_json(_plan(rows))
        out = diag.m4_funnel(request, base, base, natural)
        assert not (out["facts_sufficient"] and not out["mechanism_applicable"])
        assert not (out["score_changed"] and not out["facts_sufficient"])
        assert not (out["first_changed"] and not out["score_changed"])


# --- sink 聚合 --------------------------------------------------------------

def test_sink_counts_are_a_partition_of_records(tmp_path):
    plan = _plan([("pass", Pass(), -5.0), ("peng:1w", Peng(Tile("1w")), -9.0)])
    request = _request([_cand(Peng(Tile("1w")), _facts()), _cand(Pass(), _facts())])
    sink = _sink(tmp_path)
    policy = _wrapped(tmp_path, _FixedPolicy(plan), _FixedPolicy(plan), sink=sink)
    for _ in range(3):
        asyncio.run(policy.choose(request, DecisionBudget(1.0, 2.0, 3.0)))
    sink.close()
    assert sink.count == 3
    assert sum(sink.stage_counts.values()) == sink.count, sink.stage_counts
    assert sink.error_count == 0


def test_record_contains_the_review_required_field_groups(tmp_path):
    """逐条核对 REVIEW-6 §4 第二步要求的最小字段。"""

    plan = _plan([("peng:1w", Peng(Tile("1w")), -9.0), ("pass", Pass(), -5.0),
                  ("chi:1w2w3w", Chi((Tile("1w"), Tile("2w"), Tile("3w"))), -19.0)])
    request = _request([_cand(Peng(Tile("1w")), _facts()),
                        _cand(Chi((Tile("1w"), Tile("2w"), Tile("3w"))), _facts()),
                        _cand(Pass(), _facts())])
    sink = _sink(tmp_path)
    policy = _wrapped(tmp_path, _FixedPolicy(plan), _FixedPolicy(plan), sink=sink)
    asyncio.run(policy.choose(request, DecisionBudget(1.0, 2.0, 3.0)))
    sink.close()
    record = json.loads((tmp_path / "diag.jsonl").read_text().splitlines()[0])
    for field in ("decision_id", "match_id", "scenario_id", "pair_id", "split_group_id",
                  "arm_role", "seat_permutation_label", "seat", "round_no", "trigger_seq",
                  "phase", "hand_id", "observation_digest", "result_id",
                  "ruleset_version", "rule_config", "rules_hash", "rules_complete",
                  "baseline_identity", "candidate_identity", "source_fingerprints",
                  "waiting_tiles", "legal_candidates", "funnel",
                  "driver_plan", "shadow_plan", "driver_choice", "shadow_choice",
                  "baseline_plan", "candidate_plan", "shadow_error"):
        assert field in record, field
    # 事实要含"动作后"向听与有效牌，供诊断解释
    facts = record["legal_candidates"][0]["facts"]
    assert facts["shanten_after"] == 3 and facts["useful_total"] == 7
