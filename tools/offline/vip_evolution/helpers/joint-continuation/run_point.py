"""单个冻结点：两相容世界×两首动作臂，随后共同P0到R8桌末；不自动重试。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = '.private/t199-four-step-execution/joint-continuation'

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
from dataclasses import asdict
import fcntl
import gzip
import os
from pathlib import Path
import time

from common import activate, attempt_ledger, canonical, checked_plan, load_measurement_gate, native_parent, parameters, pin, read, recover, save, verify_files, verify_loaded


class CompleteRulesPolicy:
    """原样透传策略，拒不完整规则；完整评分与合法保底语义不改变。"""
    def __init__(self, inner, guard=None):
        self.inner, self.guard = inner, guard

    @property
    def executor(self):
        return self.inner.executor

    @executor.setter
    def executor(self, value):
        self.inner.executor = value

    async def choose(self, request, budget):
        """不读取完整世界或终分，只验证规则完整后委托生产choose。"""
        if request.rules.completeness.value != "complete":
            raise ValueError("共同P0余桌规则不完整")
        if self.guard is not None:
            self.guard(request)
        return await self.inner.choose(request, budget)


class RememberEngine:
    """只保留公开advance返回的不透明对象，供公开结算导出；不读取World字段。"""
    def __init__(self, inner, world):
        self.inner, self.last = inner, world

    def frame(self, world):
        """保持原完整桌终点，不截到单局末。"""
        self.last = world
        return self.inner.frame(world)

    def advance(self, world, revision, choices):
        """同生产公开推进，不实现第二套结算。"""
        self.last = self.inner.advance(world, revision, choices)
        return self.last


class FirstReceipt:
    """强制首动作单独记账；其委托P0评分仍由原审计记录。"""
    def __init__(self, inner, sink):
        self.inner, self.sink, self.policy_id = inner, sink, inner.policy_id

    async def choose(self, request, budget):
        """仅在原ForceFirstActionPolicy实际计数增一时记录，不算候选自行评分。"""
        before = self.inner.force_count
        result = await self.inner.choose(request, budget)
        if self.inner.force_count != before:
            self.sink({"record_kind": "forced_first_action", "decision_id": request.decision_id,
                "action_key": result.candidates[0].action_key, "force_count": self.inner.force_count,
                "candidate_self_scored": False, "delegate_source": "frozen_P0_original_S03"})
        return result


def bins(settlements, seat):
    """已发生支付按公开结算分解；四番界限仅收入分类，不推断未来机会。"""
    result = {"ordinary_hu_income_lt4": 0, "high_fan_hu_income_ge4": 0, "payments": 0, "net": 0,
              "completed_remaining_hands": len(settlements)}
    for row in settlements:
        delta = row["score_delta"][seat]
        result["net"] += delta
        if row["is_draw"]:
            if delta != 0:
                raise ValueError("流局积分不为零")
        elif row["winner_seat"] == seat:
            if type(row["fan"]) is not int or row["fan"] <= 0 or delta <= 0:
                raise ValueError("自己胡牌番/支付未知")
            key = "ordinary_hu_income_lt4" if row["fan"] < 4 else "high_fan_hu_income_ge4"
            result[key] += delta
        else:
            if delta > 0:
                raise ValueError("他家胡牌收到正积分")
            result["payments"] += -delta
    if result["ordinary_hu_income_lt4"] + result["high_fan_hu_income_ge4"] - result["payments"] != result["net"]:
        raise ValueError("余桌积分分解不闭")
    return result


async def run(args):
    """绑定根、候选点、资源槽和调用预算；缺冻结执行收据则0恢复/续打拒绝。"""
    plan_path = Path(args.plan).resolve()
    plan, source = checked_plan(plan_path)
    approval = read(args.approval)
    if not (approval.get("approved_for_common_continuation") is True and approval.get("plan_pin") == pin(plan_path)
            and approval.get("binding_id") == plan["binding_id"] and args.point in approval.get("allowed_points", [])
            and approval.get("max_remaining_table_continuations") == plan["max_continuations"]):
        raise ValueError("缺此冻结点与余桌费用的执行依赖；0World恢复/续打")
    if plan["zero_changed_stop"] or not plan["same_action_negative_control_present"]:
        raise ValueError("无改选或缺同动作负控；不购买续打")
    if plan["selection_failures"]:
        raise ValueError("选择阶段有工程失败或图/合法集合不闭；不进入续打")
    if not 1 <= args.point <= len(plan["points"]) or not 0 <= args.slot < 4:
        raise ValueError("点或资源槽越界")
    activate(source)
    true_degradations, measurement = load_measurement_gate(plan["measurement_gate"])
    from hangma_bot import bootstrap
    from hangma_bot.application.deadline import BudgetPolicy
    from hangma_bot.kernel.serialization import observation_to_json, window_key_from_json, window_key_to_json
    from hangma_bot.offline.evaluate import MatchDriverConfig, frame_observation_summary, resume_match
    from hangma_bot.offline.forced_action import ForceFirstActionPolicy
    from hangma_bot.offline.qualifier_opponents import build_qualifier_runtime
    from hangma_bot.offline.scoring_input_capture import ScoringInputCapture, ScoringInputCaptureLimits
    from hangma_bot.offline.vip_route_development import VipDevelopmentAuditPolicy
    from hangma_bot.policy.action_value_executor import ActionValueExecutor
    from hangma_bot.policy.route_vip_heuristic import RouteVipHeuristicPolicy
    from hangma_bot.simulation import SimulationChoice
    params = parameters(source)
    source_text = bootstrap.VIP_S03_SOURCE
    if params.identity(source_text) != source["candidate_identity"]:
        raise ValueError("父规则/公式身份漂移")
    # 原受限构造器廉价准入必须在任何World恢复前完成；只核将被使用的原S03。
    ActionValueExecutor(source_text, max_operations=params.max_operations,
                        max_local_collection_size=params.projection_limits.max_nodes)
    native = native_parent(source)
    point = plan["points"][args.point - 1]
    task, seat = point["task"], point["task"]["focal_physical_seat"]
    kinds = task["composition"]["opponent_types_logical_1_2_3"]
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    directory = output / f"point-{args.point:03d}"
    directory.mkdir(exist_ok=False)
    counts = {"historical_world_recoveries": 0, "prefix_rule_analyses": 0, "prefix_decisions_replayed": 0,
        "sampled_compatible_worlds": 0, "remaining_table_continuations_started": 0, "remaining_table_continuations_complete": 0,
        "focal_actual_scores": 0, "all_seat_decision_windows": 0, "forced_first_actions": 0,
        "new_complete_natural_tables": 0, "API": 0, "LLM": 0}
    started = time.monotonic()
    failure, terminal, results, records, force_rows = None, None, [], [], []
    current = {"sample": None, "arm": None}
    with Path(plan["slot_paths"][args.slot]).open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        reservation_pin = attempt_ledger(plan_path, plan, args.point)
        save(directory / "START.json", {"point": args.point, "plan_pin": pin(plan_path), "approval_pin": pin(args.approval),
            "task": task, "source_mother": task["root"], "slot": args.slot, "pid": os.getpid(),
            "requested_nice": None, "actual_nice": os.getpriority(os.PRIO_PROCESS, 0), "planned_remaining_table_continuations": 4,
            "ledger_reservation_pin": reservation_pin})
        raw = (directory / "views.jsonl.gz").open("x+b")
        capture = ScoringInputCapture(raw, limits=ScoringInputCaptureLimits.from_json(plan["capture_limits"]))
        decisions = gzip.open(directory / "decisions.jsonl.gz", "xb")

        def record(row):
            """保留每座实际choose，包括精确R18成功说明；未知说明仍是错误。"""
            envelope = {**current, "record_kind": "delegate_actual_choose", "row": row}
            decisions.write(canonical(envelope) + b"\n")
            decisions.flush()
            records.append(envelope)
            counts["all_seat_decision_windows"] += 1
            if row["seat"] == seat:
                calls = row.get("scoring_calls", [])
                counts["focal_actual_scores"] += sum(c["actual_score_calls"] for c in calls)
            if row["status"] != "chosen" or row["selected_action_key"] not in row["legal_action_keys"]:
                raise ValueError("余桌实际choose非法/失败")
            if true_degradations(row.get("degraded_reasons", ()), row["policy_id"], measurement,
                                 focal=row["seat"] == seat, observation=row["observation"]):
                raise ValueError("余桌实际choose真降级或未知说明")
            if row["seat"] == seat:
                calls = row.get("scoring_calls", [])
                if not (row["c_self_scored"] and len(calls) == 1 and calls[0]["actual_score_calls"] == 1
                        and calls[0]["full_legal_keys"] and calls[0]["score_completed"]
                        and calls[0]["input_capture"]["saved_before_score"]):
                    raise ValueError("共同P0实际完整评分不闭")
                if row["window_key"] == point["window_key"] and calls[0]["input_capture"]["view_sha256"] != point["view_sha256"]:
                    raise ValueError("恢复/采样后的同次焦点完整图不同")
            if time.monotonic() - started > plan["wall_seconds_per_point"]:
                raise ValueError("点总单调持续秒耗尽；不重抽")

        def force_record(row):
            """首动作干預单账，绝不算候选在余桌里自己评分。"""
            force_rows.append({**current, **row})
            counts["forced_first_actions"] += 1
            decisions.write(canonical({**current, **row}) + b"\n")
            decisions.flush()

        def guard(request):
            """在受限评分前执行已冻结资源边界，失败不续窗或延长动作预算。"""
            if (time.monotonic() - started > plan["wall_seconds_per_point"]
                    or counts["all_seat_decision_windows"] >= plan["max_all_seat_choose_windows_per_point"]
                    or request.observation.seat == seat and counts["focal_actual_scores"] >= plan["max_focal_scores_per_point"]):
                raise ValueError("冻结点单调秒/窗/评分资源耗尽")

        try:
            configured = build_qualifier_runtime(params, source_text, kinds, clock=lambda: plan["logical_now"])
            world, frame, target, cursor = recover(configured.engine, configured.rules, configured.config, task,
                point["prefix_file"], point["target_row"], params.route_limits, counts)
            focal, row = target
            if (window_key_to_json(focal.window_key) != point["window_key"] or observation_to_json(focal.observation) != point["observation"]
                    or row["legal_action_keys"] != point["legal_action_keys"]):
                raise ValueError("冻结公开目标/合法集不同")
            save(directory / "RECOVERY.json", {"prefix_cursor": cursor, "counts": dict(counts),
                "focal_observation_window_legal_exact": True, "full_world_exported": False,
                "wall_semantics": "new_P0_simulated_source_then_public_compatible_uniform_not_official_wall"})
            for sample in (1, 2):
                key = point["window_key"]
                sample_key = (f"t199-common-p0-v1:{task['root_id']}:rotation-{task['rotation']}:round-{key['round_no']}:"
                              f"seq-{key['trigger_seq']}:phase-{key['phase']}:sample-{sample}")
                common_world = configured.engine.resample_public_consistent_hidden_world(world, focal_seat=seat, sample_key=sample_key)
                counts["sampled_compatible_worlds"] += 1
                first = configured.engine.frame(common_world)
                focal_sample = next(d for d in first.decisions if window_key_to_json(d.window_key) == point["window_key"])
                if observation_to_json(focal_sample.observation) != point["observation"]:
                    raise ValueError("相容采样改变焦点公开观察")
                for arm, forced_key in (("parent", point["parent_first"]), ("candidate", point["candidate_first"])):
                    verify_files(plan["files"])
                    current.update(sample=sample, arm=arm)
                    fresh = build_qualifier_runtime(params, source_text, kinds, clock=lambda: plan["logical_now"])
                    focal_policy = RouteVipHeuristicPolicy(params.rule_config, source=source_text,
                        max_operations=params.max_operations, projection_limits=params.projection_limits, compiled_runtime=native)
                    audited = VipDevelopmentAuditPolicy(CompleteRulesPolicy(focal_policy, guard), "t199-common-P0",
                        lambda: {"source_mother": task["root"], "point": args.point, **current}, record, challenger=True, capture=capture)
                    forced = ForceFirstActionPolicy(audited, target_window=window_key_from_json(point["window_key"]),
                        forced_action_key=forced_key, policy_id="t199-force-common-P0:" + arm)
                    policies = [None] * 4
                    policies[seat] = FirstReceipt(forced, force_record)
                    for logical in range(1, 4):
                        declaration = fresh.declarations[f"Q{logical}"]
                        policies[task["logical_to_physical"][logical]] = VipDevelopmentAuditPolicy(
                            CompleteRulesPolicy(fresh.policies_by_id[declaration.policy_id], guard), declaration.policy_id,
                            lambda: {"source_mother": task["root"], "point": args.point, **current}, record)
                    engine = RememberEngine(configured.engine, common_world)
                    counts["remaining_table_continuations_started"] += 1
                    before = len(records)
                    outcome = await resume_match(engine=engine, world=common_world, policies_by_seat=tuple(policies),
                        rules=fresh.rules, choice_factory=SimulationChoice,
                        config=MatchDriverConfig("logical", plan["step_limit_per_continuation"], BudgetPolicy(), "t199-common-P0", True, params.route_limits),
                        now_monotonic=lambda: plan["logical_now"], wall_clock=time.monotonic, value_limits=params.route_limits,
                        stage_snapshot={"observation_summary": frame_observation_summary(first), "match_spec": {"match_id": task["match_id"]}},
                        remaining_schedule={"declared_endpoint": "current_complete_table_end", "Rounds": 8})
                    save(directory / f"sample-{sample}-{arm}-OUTCOME.json", outcome.to_json())
                    if outcome.status != "complete" or outcome.completed_hands != 8 or forced.force_count != 1:
                        raise ValueError("未到完整余桌末/强制首动作不为一次")
                    if any(type(value) is not int or value != 0 for value in asdict(outcome.runtime_counts).values()):
                        raise ValueError("余桌工程故障计数非零")
                    arm_records = records[before:]
                    if len(outcome.decisions) != len(arm_records):
                        raise ValueError("全座实际提交/choose分母不同")
                    for decision, envelope in zip(outcome.decisions, arm_records):
                        delegate = envelope["row"]
                        first_action = decision.window_key == point["window_key"]
                        if (decision.legal is not True or decision.fallback_reason is not None
                                or decision.window_key != delegate["window_key"]
                                or decision.action_key != (forced_key if first_action else delegate["selected_action_key"])):
                            raise ValueError("实际提交不等原choose或唯一首动作")
                        reasons = tuple(reason for reason in decision.degraded_reasons
                            if not (first_action and reason == "offline_counterfactual_force_first:" + forced_key))
                        if true_degradations(reasons, delegate["policy_id"], measurement,
                                             focal=decision.seat == seat, observation=delegate["observation"]):
                            raise ValueError("driver实际提交真降级/未知说明")
                    settlements = [configured.engine.export_hand_settlement(engine.last, number)
                                   for number in range(key["round_no"], 9)]
                    result = {"sample": sample, "sample_key": sample_key, "sampler_version": "simulation-v1:public-consistent-hidden-resample-v1",
                        "arm": arm, "source_mother": task["root"], "compatible_world_not_independent_mother": True,
                        "first_action": forced_key, "force_count": forced.force_count, "settlements": settlements,
                        "bins": bins(settlements, seat), "final_scores_seat_order_0_1_2_3": outcome.final_scores,
                        "actual_remaining_hands": 9 - key["round_no"]}
                    if result["bins"]["net"] != outcome.final_scores[seat] - point["observation"]["scores"][seat]:
                        raise ValueError("完整余桌净分与公开当前积分不闭")
                    results.append(result)
                    counts["remaining_table_continuations_complete"] += 1
                if point["same_action_negative_control"] and results[-2]["settlements"] != results[-1]["settlements"]:
                    raise ValueError("同动作负控两臂结算不同，批次失效")
        except BaseException as error:
            failure = {"type": type(error).__name__, "message": str(error)}
        finally:
            decisions.close()
            try:
                terminal = capture.finish()
            except BaseException as error:
                failure = failure or {"type": type(error).__name__, "message": str(error)}
            raw.close()
            complete = failure is None and counts["remaining_table_continuations_complete"] == 4 and terminal is not None and terminal["terminal"]["terminal_valid"]
            verify_files(plan["files"])
            attempt_ledger(plan_path, plan, args.point, result={"counts": counts, "complete": complete, "failure": failure,
                "elapsed_monotonic_seconds": time.monotonic() - started})
            save(directory / "CLOSED.json", {"schema": "t199-common-P0-point-close/1", "complete": complete,
                "failure": failure, "point": args.point, "source_mother": task["root"], "counts": counts, "results": results,
                "forced_first_rows": force_rows, "capture": terminal, "plan_pin": pin(plan_path), "source_stable": True,
                "elapsed_monotonic_seconds": time.monotonic() - started, "loaded_modules": verify_loaded(source),
                "raw_files": {name: pin(directory / name) for name in ("decisions.jsonl.gz", "views.jsonl.gz")},
                "full_natural_table_strength_deadline_release_admitted": False})
    print({"point": args.point, "complete": complete, "failure": failure, "counts": counts})
    if not complete:
        raise ValueError("冻结点自然失败；原费用保留，不重抽/重试")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--approval", required=True)
    parser.add_argument("--point", type=int, required=True)
    parser.add_argument("--slot", type=int, default=0)
    parser.add_argument("--output", required=True)
    asyncio.run(run(parser.parse_args()))
