"""T191可执行A/B/C单局条件续打；只显式批准后运行，不启动自然完整桌。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1/evaluation'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import asyncio
import fcntl
import gzip
import json
import os
import time
from dataclasses import asdict
from pathlib import Path

from abc_support import *
from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.kernel.observation import CompetitionContext
from hangma_bot.kernel.serialization import observation_to_json, window_key_from_json, window_key_to_json
from hangma_bot.offline.evaluate import MatchDriverConfig, frame_observation_summary, resume_match
from hangma_bot.offline.forced_action import ForceFirstActionPolicy
from hangma_bot.offline.qualifier_opponents import build_qualifier_runtime
from hangma_bot.offline.scoring_input_capture import ScoringInputCapture, ScoringInputCaptureLimits
from hangma_bot.offline.vip_eoh_generate import VipEohBatch
from hangma_bot.offline.vip_route_development import VipDevelopmentAuditPolicy
from hangma_bot.policy.interface import DecisionRequest
from hangma_bot.simulation import SimulationChoice


def request_for(runtime, focal, batch):
    """按现有模拟驱动同款公开请求与1/3秒预算构造首手评分输入，不注入暗牌。"""
    rules = runtime.rules.analyze(focal.observation, route_limits=batch.route_limits)
    require(rules.completeness.value == "complete", "首手规则分析不完整")
    request = DecisionRequest(observation=focal.observation,
        competition=CompetitionContext(tournament_id="t191-condition", stage_no=None, stage_role=None,
            stage_total=None, participant_rank=None, ranking=(), observed_at_unix_ms=0),
        rules=rules, decision_id="t191-candidate-first:" + str(focal.window_key),
        trigger_seq=focal.window_key.trigger_seq, window_key=focal.window_key, rejected_attempts=())
    return request, BudgetPolicy().build(800.0, focal.timeout_seconds)


class FirstActionReceiptPolicy:
    """仅记录实际一次强制动作，分开保留其S02委托评分；强制行绝不算自行评分。"""

    def __init__(self, inner, sink):
        self.inner, self.sink, self.policy_id = inner, sink, inner.policy_id

    async def choose(self, request, budget):
        """原样返回ForceFirstActionPolicy计划；只在force_count变化时写强制小收据。"""
        before = self.inner.force_count
        plan = await self.inner.choose(request, budget)
        if self.inner.force_count != before:
            self.sink({"record_kind": "forced_first_action", "window_key": window_key_to_json(request.window_key),
                "selected_action_key": plan.candidates[0].action_key, "c_self_scored": False,
                "actual_formula_full_scored": False, "scoring_calls": [],
                "degraded_reasons": list(plan.degraded_reasons), "force_count": self.inner.force_count})
        return plan


def valid_score_row(row):
    """验证实际完整评分；此属性独立于动作是否由候选自行选择。"""
    calls = row.get("scoring_calls", [])
    return (row.get("status") == "chosen" and row.get("actual_formula_full_scored") is True
        and not row.get("degraded_reasons") and len(calls) == 1
        and calls[0]["actual_score_calls"] == 1 and calls[0]["full_legal_keys"]
        and calls[0]["score_completed"] and calls[0]["input_capture"]["saved_before_score"])


async def run_target(index, plan, plan_path, output):
    """恢复公共窗口并复用同一个不透明世界给三组；历史世界另账，未来真实模拟推进。"""
    target = plan["targets"][index - 1]
    case, seat = target["case"], target["focal_seat"]
    directory = output / f"target-{index:03d}"
    directory.mkdir(exist_ok=False)
    plan_pin = pin(plan_path)
    save(directory / "START.json", {"target": target, "plan_pin": plan_pin, "pid": os.getpid()})
    batch = VipEohBatch.read(plan["batch_file"])
    sources = {k: Path(v["source_file"]).read_text() for k, v in plan["arms_sources"].items()}
    require(all(batch.identity(sources[k]) == v["identity"] for k, v in plan["arms_sources"].items()), "公式身份漂移")
    kinds = target["composition"]["opponent_types_logical_1_2_3"]
    runtime = build_qualifier_runtime(batch, sources["parent"], kinds)
    counts = {"recovered_historical_worlds": 0, "hidden_samples": 0, "single_hand_dispatched": 0,
        "single_hand_completed": 0, "scored_decisions": 0, "actual_score_calls": 0,
        "selector_score_calls": 0, "forced_first_actions": 0, "failed_or_missing_full_scores": 0,
        "new_complete_table_instances": 0, "model_calls": 0, "HTTP_calls": 0}
    results, failure, terminal, selector = [], None, None, None
    raw = (directory / "views.jsonl.gz").open("x+b")
    capture = ScoringInputCapture(raw, limits=ScoringInputCaptureLimits.from_json(plan["capture_limits"]))
    stream = gzip.open(directory / "decisions.jsonl.gz", "xb")
    started = time.monotonic()  # 离线研究持续秒，不是官方动作截止时间。
    current = {"sample": None, "arm": "selector", "role": "candidate_first_selector"}
    rows = []

    def record(row):
        # 原审计c_self_scored表达其executor完整评分；在此明确区分C自行选择、S02委托和强制动作。
        full = row.get("c_self_scored", False)
        row = {**row, "record_kind": "formula_score", "actual_formula_full_scored": full,
            "c_self_scored": bool(full and current["arm"] == "C"),
            "score_source_name": "child" if current["arm"] in ("selector", "C") else "parent"}
        stream.write(canonical({**current, "row": row}) + b"\n")
        stream.flush()
        rows.append({**current, "row": row})
        counts["scored_decisions"] += 1
        calls = sum(c["actual_score_calls"] for c in row.get("scoring_calls", []))
        counts["actual_score_calls"] += calls
        counts["selector_score_calls"] += calls if current["arm"] == "selector" else 0
        counts["failed_or_missing_full_scores"] += int(not valid_score_row(row))
        require(valid_score_row(row), "真实评分不完整，已保留失败费用")
        require(time.monotonic() - started < plan["wall_seconds_per_target"], "研究持续秒超限")

    def force_record(row):
        stream.write(canonical({**current, "row": row}) + b"\n")
        stream.flush()
        counts["forced_first_actions"] += 1

    try:
        require(unchanged(plan), "冻结材料漂移")
        counts["recovered_historical_worlds"] += 1
        world, cursor = recover(runtime, target, batch)
        frame = runtime.engine.frame(world)
        focal = next(d for d in frame.decisions if window_key_to_json(d.window_key) == case["window_key"])
        selector_runtime = build_qualifier_runtime(batch, sources["child"], kinds)
        selector_policy = VipDevelopmentAuditPolicy(selector_runtime.policies_by_id[selector_runtime.challenger_policy_id],
            selector_runtime.challenger_policy_id, lambda: {"target": index, "focal_seat": seat}, record,
            challenger=True, capture=capture)
        request, budget = request_for(selector_runtime, focal, batch)
        first_plan = await selector_policy.choose(request, budget)
        candidate_first = first_plan.candidates[0].action_key
        selector = rows[-1]["row"]
        require(selector["scoring_calls"][0]["input_capture"]["view_sha256"] == case["view_sha256"], "规则复原完整公开图不同")
        require(sorted(c.action_key for c in request.rules.legal_candidates) == case["legal_action_keys"], "首手合法根不同")
        save(directory / "RECOVERY.json", {"prefix_decisions": cursor, "focal_seat": seat,
            "full_public_observation_window_legal_and_view_exact": True,
            "candidate_first": candidate_first, "selector_actual_score_calls": 1,
            "selector_view_sha256": case["view_sha256"], "historical_world_not_exported": True,
            "budget": asdict(budget), "logical_clock_monotonic_seconds": 800.0})
        samples = list(range(1, 3))
        if target["historical_control"] and plan["historical_original_world_for_first_14"]:
            samples = [0] + samples
        for sample in samples:
            require(unchanged(plan) and pin(plan_path) == plan_pin, "冻结材料漂移")
            sample_key = f"{plan['sample_key_prefix']}:{case['label']}:hidden:{sample}"
            common = world if sample == 0 else runtime.engine.resample_public_consistent_hidden_world(
                world, focal_seat=seat, sample_key=sample_key)
            counts["hidden_samples"] += int(sample > 0)
            first = runtime.engine.frame(common)
            same = next(d for d in first.decisions if window_key_to_json(d.window_key) == case["window_key"])
            require(observation_to_json(same.observation) == case["observation"], "重采样改变公开观察")
            for arm, name in (("A", "parent"), ("B", "parent"), ("C", "child")):
                current.update(sample=sample, arm=arm, role="continuation_formula")
                fresh = build_qualifier_runtime(batch, sources[name], kinds)
                audit = VipDevelopmentAuditPolicy(fresh.policies_by_id[fresh.challenger_policy_id],
                    fresh.challenger_policy_id, lambda: {"target": index, "focal_seat": seat}, record,
                    challenger=True, capture=capture)
                forced = None
                policy = audit
                if arm == "B":
                    forced = ForceFirstActionPolicy(audit, target_window=window_key_from_json(case["window_key"]),
                        forced_action_key=candidate_first, policy_id="t191-force-first:" + plan["arms_sources"]["parent"]["identity"]["candidate_id"])
                    policy = FirstActionReceiptPolicy(forced, force_record)
                policies = [None] * 4
                policies[seat] = policy
                for logical in range(1, 4):
                    policies[(logical + seat) % 4] = fresh.policies_by_id[fresh.declarations[f"Q{logical}"].policy_id]
                endpoint = EndpointEngine(runtime.engine, case["window_key"]["round_no"])
                counts["single_hand_dispatched"] += 1
                before = counts["actual_score_calls"]
                outcome = await resume_match(engine=endpoint, world=common, policies_by_seat=tuple(policies),
                    rules=fresh.rules, choice_factory=SimulationChoice,
                    config=MatchDriverConfig("logical", plan["step_limit"], BudgetPolicy(), "t191-condition", True, batch.route_limits),
                    now_monotonic=lambda: 800.0, wall_clock=None, value_limits=batch.route_limits,
                    stage_snapshot={"observation_summary": frame_observation_summary(first)},
                    remaining_schedule={"declared_endpoint": "single_hand"})
                save(directory / f"sample-{sample}-{arm}-OUTCOME.json", outcome.to_json())
                require(outcome.status == "complete" and outcome.completed_hands == case["window_key"]["round_no"] and
                    all(type(v) is int and v == 0 for v in asdict(outcome.runtime_counts).values()), "单局未完整或故障")
                own = [d for d in outcome.decisions if d.seat == seat]
                actual = next(d for d in own if d.window_key == case["window_key"])
                require(all(d.legal is True and d.fallback_reason is None for d in own), "存在非法或降级动作")
                if arm in ("B", "C"):
                    require(actual.action_key == candidate_first, "候选首手或强制首手不同")
                require(forced is None or forced.force_count == 1, "B未仅强制一次")
                own_rows = [r["row"] for r in rows if r["sample"] == sample and r["arm"] == arm]
                require(len(own) == len(own_rows), "动作与真实评分分母不同")
                for decision, row in zip(own, own_rows):
                    require(decision.window_key == row["window_key"], "动作与评分窗口不同")
                    expected = candidate_first if arm == "B" and decision.window_key == case["window_key"] else row["selected_action_key"]
                    require(decision.action_key == expected, "后续动作不是实际公式首选")
                    if decision.window_key == case["window_key"]:
                        require(row["scoring_calls"][0]["input_capture"]["view_sha256"] == case["view_sha256"], "A/B/C首手公共图不同")
                settlement = runtime.engine.export_hand_settlement(endpoint.last, case["window_key"]["round_no"])
                counts["single_hand_completed"] += 1
                results.append({"sample": sample, "sample_key": sample_key, "arm": arm,
                    "world_kind": "historical_exposed" if sample == 0 else "public_compatible_uniform",
                    "first_actual": actual.action_key, "candidate_first": candidate_first,
                    "forced_count": 0 if forced is None else forced.force_count,
                    "settlement": settlement, "focal_net_score": settlement["score_delta"][seat],
                    "focal_score_calls": counts["actual_score_calls"] - before})
    except BaseException as error:
        failure = {"type": type(error).__name__, "message": str(error)}
    finally:
        stream.close()
        try:
            terminal = capture.finish()
        except BaseException as error:
            failure = failure or {"type": type(error).__name__, "message": str(error)}
        raw.close()
        complete = failure is None and unchanged(plan) and pin(plan_path) == plan_pin and terminal is not None and terminal["terminal"]["terminal_valid"]
        save(directory / "CLOSURE.json", {"complete": complete, "failure": failure, "source_stable": unchanged(plan),
            "target": target, "counts": counts, "results": results, "capture": terminal,
            "candidate_first": None if selector is None else selector["selected_action_key"],
            "elapsed_monotonic_seconds": time.monotonic() - started, "strength_or_deadline_admission": False})
    require(complete, "条件续打失败，保留原费用，不重抽：" + str(failure))


async def worker(args):
    """持一个既有共用研究槽，唯一分片自然执行；不持自由赛锁、不自动重试。"""
    background_priority()
    plan_path, output = Path(args.plan).resolve(), Path(args.output).resolve()
    plan = read(plan_path)
    approval = read(args.approval)
    require(approval.get("approved_for_condition_execution") is True and approval.get("plan_pin") == pin(plan_path)
        and approval.get("candidate_id") == plan["arms_sources"]["child"]["identity"]["candidate_id"], "未获此冻结计划的总筹执行批准")
    require(unchanged(plan) and plan["cpu_worker_count"] == 4 and 0 <= args.worker < 4, "冻结或槽配置不同")
    preflight = None
    if args.reuse_preflight:
        preflight = read(args.reuse_preflight)
        require(preflight["complete"] and preflight["source_stable"] and preflight["plan_pin"] == pin(plan_path)
            and preflight["candidate_identity"] == plan["arms_sources"]["child"]["identity"]
            and preflight["target"] == plan["preflight"]["target"], "首目标工具预检未核齐或不同计划")
    output.mkdir(parents=True, exist_ok=True)
    lane = list(range(args.worker + 1, len(plan["targets"]) + 1, 4))
    directory = output / f"worker-{args.worker}"
    directory.mkdir(exist_ok=False)
    with resource_slot_paths(OLD, 4)[args.worker].open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        save(directory / "START.json", {"pid": os.getpid(), "slot": args.worker, "targets": lane,
            "plan_pin": pin(plan_path), "approval_pin": pin(Path(args.approval)),
            "nice": os.getpriority(os.PRIO_PROCESS, 0), "background_io": True})
        attempted, completed, failure = [], [], None
        try:
            for index in lane:
                attempted.append(index)
                if preflight is not None and index == preflight["target"]:
                    require(preflight["target_closure_pin"] == pin(output / f"target-{index:03d}" / "CLOSURE.json"), "复用预检闭合原件漂移")
                else:
                    await run_target(index, plan, plan_path, output)
                completed.append(index)
        except BaseException as error:
            failure = {"type": type(error).__name__, "message": str(error)}
        save(directory / "CLOSE.json", {"pid": os.getpid(), "slot": args.worker, "attempted": attempted,
            "completed": completed, "complete": completed == lane and failure is None, "failure": failure})
        require(failure is None, "worker自然失败，禁止同输出重试")


async def preflight(args):
    """仅执行同计划首目标，其9次续打以后复用；输出只报工具终态，不打印积分。"""
    background_priority()
    plan_path, output = Path(args.plan).resolve(), Path(args.output).resolve()
    plan, approval = read(plan_path), read(args.approval)
    require(approval.get("approved_for_condition_execution") is True and approval.get("plan_pin") == pin(plan_path)
        and approval.get("candidate_id") == plan["arms_sources"]["child"]["identity"]["candidate_id"]
        and args.preflight_target == plan["preflight"]["target"], "预检未获冻结计划批准或目标不符")
    require(unchanged(plan), "冻结材料漂移")
    output.mkdir(parents=True, exist_ok=True)
    slot = (args.preflight_target - 1) % 4
    with resource_slot_paths(OLD, 4)[slot].open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        await run_target(args.preflight_target, plan, plan_path, output)
    print(json.dumps({"preflight_complete": True, "target": args.preflight_target,
        "planned_cost_reused_in_whole_block": True, "performance_scores_printed": False}))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--plan", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--approval", required=True)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--worker", type=int)
    mode.add_argument("--preflight-target", type=int)
    p.add_argument("--reuse-preflight")
    p.add_argument("--execute", action="store_true", required=True)
    args = p.parse_args()
    asyncio.run(preflight(args) if args.preflight_target is not None else worker(args))
