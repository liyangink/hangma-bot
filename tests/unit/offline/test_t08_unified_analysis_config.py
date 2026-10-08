"""T08：普通驱动与阶段驱动同配置产生同一可见事实；耗时含规则分析段。

权威行为 SEARCH-SPACE-REDESIGN-2026-09-16.md §14 T08：普通桌赛驱动
（offline.evaluate.drive_match）与阶段驱动（sitin_stage run_tables_supervised
→ execute_table → drive_match）必须能把**同一个** ValueAnalysisLimits 传入
rules.analyze，产出逐位相等的 B1 可见载荷；驱动记录的耗时字段包含规则
分析段。0 桌赛：假引擎只推进一个构造窗口，阶段路径拦截 drive_match 记录
透传参数。
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'tests/unit/offline'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import importlib.util
import itertools
import sys
from pathlib import Path
from types import SimpleNamespace

from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.kernel.actions import Tile, WindowKey, WindowPhase
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import (
    PlayerObservation,
    PublicDiscard,
    RulePublicState,
)
from hangma_bot.offline.evaluate import (
    MatchDriverConfig,
    MatchRunOutcome,
    drive_match,
)
from hangma_bot.offline.evaluation_results import RuntimeCounts
from hangma_bot.policy.interface import (
    DecisionPlan,
    RankedCandidate,
    ScorePart,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
SITIN_STAGE_PATH = (
    _project_file(_PROJECT_ROOT, REPO_ROOT / "review/llm-guided-heuristic-route-2026-09-15/tools/sitin_stage.py")
)
LIMITS = ValueAnalysisLimits()


def _peng_observation():
    """碰响应窗口的真实观察（沿用 hangma 载荷测试的构造口径）。"""
    hand = "5w 5w 1t 2t 3t 4t 5t 6t 7t 8t 9t 2b 3b"
    tiles = tuple(Tile(code) for code in hand.split())
    turn = 3
    return PlayerObservation(
        game_id="t08", seat=0, round_no=1, snapshot_seq=10,
        phase="response_peng", dealer_seat=0, turn_seat=turn,
        responding_seats=(0,), my_hand=tiles, drawn_tile=None,
        discards=((), (), (), (Tile("5w"),)), melds=((), (), (), ()),
        hand_counts=(13, 13, 13, 13),
        last_discard=PublicDiscard(turn, Tile("5w"), 10),
        remaining_tile_count=60, scores=(0, 0, 0, 0),
        rule_state=RulePublicState(Tile("白"), False, 0, False),
        public_history=(),
    )


def _rules():
    return HangmaRules(RuleConfig("t08-test", 1, False))


def _window_key():
    return WindowKey(
        game_id="t08", round_no=1, trigger_seq=10,
        phase=WindowPhase.RESPONSE_PENG, seat=0,
    )


class _FakeEngine:
    """单窗口假引擎：一帧决策后终局；不运行任何桌赛。"""

    def __init__(self, decision):
        self._decision = decision

    def start(self, spec):
        return "world-0"

    def frame(self, world):
        if world == "world-0":
            return SimpleNamespace(
                blocked_reason=None, final_scores=None, completed_hands=0,
                revision=1, decisions=(self._decision,),
            )
        return SimpleNamespace(
            blocked_reason=None, final_scores=(1, 2, 3, 4), completed_hands=1,
            revision=2, decisions=(),
        )

    def advance(self, world, revision, choices):
        return "world-1"


class _RecordingPolicy:
    """记录请求并选第一个合法候选的最小策略。"""

    policy_id = "t08-recording"

    def __init__(self):
        self.requests = []

    async def choose(self, request, budget):
        self.requests.append(request)
        first = request.rules.legal_candidates[0]
        return DecisionPlan(
            decision_id=request.decision_id,
            window_key=request.window_key,
            based_on_authoritative_seq=request.observation.snapshot_seq,
            revision=1,
            candidates=(
                RankedCandidate(
                    action=first.action, action_key=first.action_key,
                    rank=1, total_score=0.0,
                    score_parts=(ScorePart("t08", 0.0),), reasons=(),
                ),
            ),
        )


def _run_normal_driver(value_limits, wall_clock=None):
    """跑一次普通驱动（一个构造窗口）；返回 (策略, 结果, 规则分析记录)。"""
    import asyncio

    decision = SimpleNamespace(
        observation=_peng_observation(), window_key=_window_key(),
        timeout_seconds=1.0,
    )
    policy = _RecordingPolicy()
    outcome = asyncio.run(drive_match(
        engine=_FakeEngine(decision),
        spec=SimpleNamespace(match_id="t08-match"),
        policies_by_seat=(policy, policy, policy, policy),
        rules=_rules(),
        choice_factory=lambda window_key, action: (window_key, action),
        config=MatchDriverConfig(
            clock_mode="logical", step_limit=10, budget_policy=BudgetPolicy(),
            competition_tournament_id="t08",
        ),
        now_monotonic=lambda: 800.0,
        wall_clock=wall_clock,
        value_limits=value_limits,
    ))
    return policy, outcome


def _visible_facts(analysis):
    """抽取 T08 断言的可见载荷：分支、家族进展与路线。"""

    def item(candidate):
        facts = candidate.facts
        return (
            None if facts is None else (facts.followup_branches, facts.family_progress),
            None if candidate.value_facts is None else candidate.value_facts.routes,
        )

    return {candidate.action_key: item(candidate) for candidate in analysis.legal_candidates}


class TestNormalDriverFacts:
    def test_driver_facts_equal_direct_analyze_with_same_config(self):
        policy, outcome = _run_normal_driver(LIMITS)
        assert outcome.status == "complete"
        assert len(policy.requests) == 1
        recorded = policy.requests[0].rules
        direct = _rules().analyze(_peng_observation(), value_limits=LIMITS)
        # 同一观察 + 同一分析配置：驱动附着的可见载荷与规则分析产出逐位相等。
        assert _visible_facts(recorded) == _visible_facts(direct)
        peng = next(c for c in recorded.legal_candidates if c.action_key == "peng:5w")
        assert peng.facts.followup_branches  # 载荷真实开启（T08 拒绝离线没开事实）
        assert peng.facts.family_progress

    def test_same_config_two_runs_produce_identical_facts(self):
        first_policy, _ = _run_normal_driver(LIMITS)
        second_policy, _ = _run_normal_driver(LIMITS)
        assert _visible_facts(first_policy.requests[0].rules) == _visible_facts(
            second_policy.requests[0].rules
        )

    def test_default_driver_keeps_legacy_no_payload_behavior(self):
        policy, outcome = _run_normal_driver(None)
        assert outcome.status == "complete"
        recorded = policy.requests[0].rules
        for candidate in recorded.legal_candidates:
            # value_limits=None 的既有口径：进展/路线载荷不产出（engine.py 只在
            # value_limits 非 None 时调 attach_value_facts）；吃/碰的机械分支
            # followup_branches 属基础候选事实，默认路径本来就产出，保持不动。
            assert candidate.facts is None or candidate.facts.family_progress == ()
            assert candidate.value_facts is None

    def test_decision_record_contains_rules_analysis_timing(self):
        ticks = itertools.count(start=100.0, step=0.0005)
        _, outcome = _run_normal_driver(LIMITS, wall_clock=lambda: next(ticks))
        record = outcome.decisions[0]
        assert record.rules_elapsed_ms is not None
        assert record.rules_elapsed_ms >= 0.0
        assert "rules_elapsed_ms" in record.to_json()
        # 逻辑时钟（wall_clock=None）保持 null，不伪造耗时结论。
        _, logical = _run_normal_driver(LIMITS, wall_clock=None)
        assert logical.decisions[0].rules_elapsed_ms is None


def _load_sitin_stage():
    spec = importlib.util.spec_from_file_location(
        "sitin_stage_t08", SITIN_STAGE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["sitin_stage_t08"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _stage_plan_payload(value_limits=None):
    payload = {
        "table_id": "t08-table", "stage_no": 1, "stage_name": "8强",
        "stage_role": "qualify", "stage_kind": "group_round", "group_index": 0,
        "batch_index": 0, "tables_in_stage": 1,
        "logical_participants": ["p1", "p2", "p3", "p4"],
        "policy_names": ["safe_fallback", "safe_fallback", "safe_fallback", "safe_fallback"],
        "permutation": [0, 1, 2, 3], "seed": 7, "scenario_id": "t08-scenario",
        "match_id": "t08-match", "pair_id": "t08-pair", "initial_dealer": 0,
        "versions": {
            "ruleset_version": "t08-test", "base_score": 1,
            "you_cai_bi_kao": False, "rounds_per_game": 1, "clock_mode": "logical",
        },
        "timing": {"peng_timeout_sec": 1.0, "chi_timeout_sec": 1.0, "discard_timeout_sec": 3.0},
        "step_limit": 10,
        "participants_by_seat": ["p1", "p2", "p3", "p4"],
        "policy_names_by_seat": ["safe_fallback", "safe_fallback", "safe_fallback", "safe_fallback"],
    }
    if value_limits is not None:
        payload["value_limits"] = dict(value_limits)
    return payload


class TestStageDriverConfig:
    """阶段驱动（execute_table）把统一分析配置传入 drive_match。"""

    def _execute_with_capture(self, monkeypatch, value_limits):
        import hangma_bot.offline.evaluate as evaluate_module

        captured = {}

        async def fake_drive_match(**kwargs):
            captured.update(kwargs)
            return MatchRunOutcome(
                status="complete", completed_hands=1, final_scores=(1, 2, 3, 4),
                blocked_reason=None, error_reason=None, steps=1, decisions=(),
                runtime_counts=RuntimeCounts(
                    timeouts=0, illegal_choices=0, fallbacks=0,
                ),
            )

        monkeypatch.setattr(evaluate_module, "drive_match", fake_drive_match)
        stage = _load_sitin_stage()
        record = stage.execute_table(_stage_plan_payload(value_limits))
        return captured, record

    def test_stage_driver_passes_same_limits_into_drive_match(self, monkeypatch):
        captured, record = self._execute_with_capture(monkeypatch, {
            "max_expansions": 2048, "max_routes_per_candidate": 128,
        })
        assert record["match_status"] == "complete"
        # 与普通驱动同一 ValueAnalysisLimits（等值即同配置）。
        assert captured["value_limits"] == LIMITS

    def test_stage_driver_default_keeps_none(self, monkeypatch):
        captured, _ = self._execute_with_capture(monkeypatch, None)
        assert captured["value_limits"] is None
        assert "value_limits" not in _stage_plan_payload()

    def test_run_tables_supervised_writes_limits_only_when_given(self, tmp_path, monkeypatch):
        """受监管装配段：value_limits 给定时写入计划；缺省不写键（3.0 逐字节不变）。"""
        import json as json_module

        stage = _load_sitin_stage()

        class _FakeProcessTools:
            """不真正开子进程：伪造受监管结果并按 --out 落一行记录。"""

            @staticmethod
            def run_supervised(command, cwd, timeout_sec):
                out_path = Path(command[command.index("--out") + 1])
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(json_module.dumps({
                    "table_id": "t08-table",
                    "result": {
                        "status": "complete", "scores_after": [1, 2, 3, 4],
                        "policy_ids_by_seat": ["p1", "p2", "p3", "p4"],
                        "invalid_reasons": [],
                    },
                }), encoding="utf-8")
                return SimpleNamespace(
                    timed_out=False, returncode=0, stdout="", stderr="",
                    to_json=lambda: {"fake": True},
                )

        monkeypatch.setattr(stage, "sibling", lambda name: _FakeProcessTools())
        plan = [stage.TablePlan.from_json(_stage_plan_payload())]
        limits = {"max_expansions": 2048, "max_routes_per_candidate": 128}

        outcomes = stage.run_tables_supervised(
            out_dir=tmp_path, timeout_sec=5.0, plan=plan,
            versions_block=_stage_plan_payload()["versions"],
            timing=_stage_plan_payload()["timing"], step_limit=10,
            value_limits=limits,
        )
        assert outcomes[0].status == "complete"
        cell = tmp_path / "tables" / stage.slug("t08-table")
        written = json_module.loads((cell / "plan.json").read_text())
        assert written["value_limits"] == limits

        monkeypatch.setattr(stage, "sibling", lambda name: _FakeProcessTools())
        stage.run_tables_supervised(
            out_dir=tmp_path / "plain", timeout_sec=5.0, plan=plan,
            versions_block=_stage_plan_payload()["versions"],
            timing=_stage_plan_payload()["timing"], step_limit=10,
        )
        plain_cell = tmp_path / "plain" / "tables" / stage.slug("t08-table")
        plain = json_module.loads((plain_cell / "plan.json").read_text())
        assert "value_limits" not in plain
