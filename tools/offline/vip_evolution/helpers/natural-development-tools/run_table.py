"""单桌R8：公共模拟/drive_match/实际原公式native；全座合法prefix与自然结算留存。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = '.private/t199-four-step-execution/natural-development-tools'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import asyncio
import gzip
import json
import time
from dataclasses import asdict
from pathlib import Path
from common import HERE, ROOT, PLAN, canonical, pin, save, unchanged, batch, true_degradations, loaded_paths
from focal import build_focal


class CompleteRulesPolicy:
    """只在离线审计拒绝不完整规则；不改原策略动作或结算。"""
    def __init__(self, inner):
        self.inner = inner

    @property
    def executor(self):
        return self.inner.executor

    @executor.setter
    def executor(self, value):
        self.inner.executor = value

    async def choose(self, request, budget):
        if request.rules.completeness.value != "complete":
            raise ValueError("P0严格审计拒绝不完整RuleAnalysis")
        return await self.inner.choose(request, budget)


async def run(task, plan):
    from hangma_bot import bootstrap
    from hangma_bot.application.deadline import BudgetPolicy
    from hangma_bot.offline.qualifier_opponents import build_qualifier_runtime
    from hangma_bot.offline.vip_route_development import VipDevelopmentAuditEngine, VipDevelopmentAuditPolicy
    from hangma_bot.offline.scoring_input_capture import ScoringInputCapture, ScoringInputCaptureLimits
    from hangma_bot.offline.evaluate import drive_match, MatchDriverConfig
    from hangma_bot.policy.route_vip_heuristic import RouteVipHeuristicPolicy
    from hangma_bot.simulation import MatchSpec, SimulationChoice
    assert Path(bootstrap.__file__).resolve().is_relative_to(_project_file(_PROJECT_ROOT, ROOT / "src"))
    directory = _project_file(_PROJECT_ROOT, HERE / "tables" / f"table-{task['table_no']:04d}")
    directory.mkdir(parents=True, exist_ok=False)
    plan_pin = pin(PLAN)
    save(directory / "START.json", {"task": task, "plan_pin": plan_pin, "source_stable": unchanged(plan),
        "pid": __import__('os').getpid(), "table_attempt_count": 1})
    assert unchanged(plan)
    parameters = batch(plan)
    configured = build_qualifier_runtime(parameters, bootstrap.VIP_S03_SOURCE,
        task["composition"]["opponent_types_logical_1_2_3"], clock=lambda: plan["logical_now"])
    assert parameters.identity(bootstrap.VIP_S03_SOURCE) == plan["candidate_identity"]
    checked, _ = bootstrap._verify_vip_s03_runtime(plan["compiled_runtime"]["manifest_sha256"])
    assert checked == plan["compiled_runtime"]
    native = bootstrap._load_vip_s03_runtime(checked["manifest_sha256"])
    focal = build_focal(parameters, plan, native)
    raw = (directory / "views.jsonl.gz").open("x+b")
    capture = ScoringInputCapture(raw, limits=ScoringInputCaptureLimits.from_json(plan["capture_limits"]))
    decisions = gzip.open(directory / "decisions.jsonl.gz", "xb")
    settlements_file = (directory / "settlements.jsonl").open("x")
    rows = []
    failure = None
    outcome = None
    terminal = None
    started = time.monotonic()

    def settle(row):
        settlements_file.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        settlements_file.flush()

    engine = VipDevelopmentAuditEngine(configured.engine, settlement_sink=settle)
    engine.context = {"root_id": task["root_id"], "permutation": task["logical_to_physical"],
        "focal_physical_seat": task["focal_physical_seat"], "arm": plan["selected_variant"], "table_no": task["table_no"]}

    def record(row):
        actual = true_degradations(row.get("degraded_reasons", ()), row["policy_id"], plan,
            focal=row["seat"] == task["focal_physical_seat"], observation=row.get("observation"))
        row = dict(row, true_degradation_reasons=list(actual), original_reasons_preserved=True)
        decisions.write(canonical(row) + b"\n")
        decisions.flush()
        rows.append(row)
        assert row["status"] == "chosen" and not actual
        assert row["selected_action_key"] in row["legal_action_keys"]
        if row["seat"] == task["focal_physical_seat"]:
            assert row["c_self_scored"] and len(row["scoring_calls"]) == 1
            assert row["scoring_calls"][0]["actual_score_calls"] == 1
        assert time.monotonic() - started < plan["wall_seconds_per_table"]

    policies = [None] * 4
    focal_audit = VipDevelopmentAuditPolicy(CompleteRulesPolicy(focal), plan["focal_policy_id"],
        lambda: dict(engine.context), record, challenger=True, capture=capture)
    policies[task["focal_physical_seat"]] = focal_audit
    for logical in range(1, 4):
        declaration = configured.declarations[f"Q{logical}"]
        original = configured.policies_by_id[declaration.policy_id]
        policies[task["logical_to_physical"][logical]] = VipDevelopmentAuditPolicy(CompleteRulesPolicy(original),
            declaration.policy_id, lambda: dict(engine.context), record)
    spec = MatchSpec(task["match_id"], task["scenario_id"], configured.config, task["seed"], 0, (0, 0, 0, 0))
    try:
        outcome = await drive_match(engine=engine, spec=spec, policies_by_seat=tuple(policies), rules=configured.rules,
            choice_factory=SimulationChoice,
            config=MatchDriverConfig(plan["clock_mode"], plan["step_limit_per_table"], BudgetPolicy(),
                "t199-natural-development:" + plan["selected_variant"], True, parameters.route_limits),
            now_monotonic=lambda: plan["logical_now"], wall_clock=time.monotonic, value_limits=parameters.route_limits)
        save(directory / "OUTCOME.json", outcome.to_json())
        assert outcome.status == "complete" and outcome.completed_hands == 8
        assert all(type(value) is int and value == 0 for value in asdict(outcome.runtime_counts).values())
        assert len(engine.settlements) == 8 and all(row["evidence"] == "public_export_hand_settlement" for row in engine.settlements)
        assert all(record.legal is True and record.fallback_reason is None and not true_degradations(
            record.degraded_reasons, record.policy_id, plan, focal=record.seat == task["focal_physical_seat"], observation=row["observation"])
            for record, row in zip(outcome.decisions, rows))
        assert len(rows) == len(outcome.decisions)
        assert sum(outcome.final_scores) == 0
    except BaseException as error:
        failure = {"type": type(error).__name__, "message": str(error)}
    finally:
        try:
            terminal = capture.finish()
        except BaseException as error:
            failure = failure or {"type": type(error).__name__, "message": str(error)}
        raw.close()
        decisions.close()
        settlements_file.close()
    stable = unchanged(plan) and pin(PLAN) == plan_pin
    complete = failure is None and stable and terminal is not None and terminal["terminal"]["terminal_valid"]
    score_calls = sum(call["actual_score_calls"] for row in rows for call in row.get("scoring_calls", []))
    receipt = {"schema": "t199-natural-single-arm-table/1", "complete": complete, "failure": failure,
        "task": task, "plan_pin": plan_pin, "source_and_map_stable": stable,
        "started_table_instances": engine.started_table_instances,
        "completed_hands": None if outcome is None else outcome.completed_hands,
        "outcome_status": None if outcome is None else outcome.status,
        "final_scores_seat_order_0_1_2_3": None if outcome is None else outcome.final_scores,
        "runtime_counts": None if outcome is None else asdict(outcome.runtime_counts),
        "all_seat_window_count": len(rows), "focal_score_calls": score_calls,
        "scoring_failed_calls": focal_audit.scoring.failed_calls,
        "audit_sink_failed_calls": focal_audit.scoring.audit_sink_failed_calls,
        "capture": terminal, "natural_settlements": engine.settlements,
        "wall_seconds": time.monotonic() - started,
        "raw_files": {name: pin(directory / name) for name in ("decisions.jsonl.gz", "settlements.jsonl", "views.jsonl.gz")},
        "strength_admission": False, "original_deadline_admitted": False,
        "candidate_binding_id": plan["binding_id"], "selected_variant": plan["selected_variant"],
        "loaded_paths": loaded_paths(plan), "forced_first_actions": 0, "natural_full_table": True, "HTTP_calls": 0, "LLM_calls": 0}
    save(directory / "CLOSED.json", receipt)
    return receipt
