"""复用已成功 v1 的五臂接线；只有 execute 调用方可进入此业务函数。

本批次专用，不新增生产接口。输入同一个不透明单局句柄、目标窗口、冻结
对手装配和共享费用/捕获器；输出五臂实际结果及差额。异常保留传入 arms
的已完成/正在派发状态及流中的合法前缀；不重试、不换根、不读暗字段。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t10-abc-implementation-preparation-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from dataclasses import asdict
import hashlib
import time
from recover_natural_start import ROOT, require, window_id
from run_abc_pilot import ORDER, PACKAGES

async def run_five_arms(*, plan, batch, sources, rules, engine, common, stage_snapshot,
                        focal, target, root_id, match_id, round_no, event, call, charge,
                        capture, counts, output, output_dir, arms):
    """单世界 A/Sol-C/B/S02-C/B；耗时秒、操作整数，积分按物理座位0–3。

    call/charge/event 和 output 为父批共享费用及独占记录入口；每臂构造全新
    策略实例。B仅强制同世界C实际首选一次，再用新R18；终点仅当前单局。
    """
    from hangma_bot.application.deadline import BudgetPolicy
    from hangma_bot.hangma.engine import HangmaRules
    from hangma_bot.kernel.actions import action_key
    from hangma_bot.kernel.serialization import observation_to_json, window_key_to_json
    from hangma_bot.policy.action_value_policy import ActionValuePolicy
    from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2
    from hangma_bot.policy.hu_upgrade import UpgradeRiskCell
    from hangma_bot.policy.v2_hu_upgrade import V2HuUpgradePolicy
    from hangma_bot.policy.weights_v1 import HeuristicWeightsV1
    from hangma_bot.policy.research_candidates import build_research_candidate_scorer
    from hangma_bot.policy.route_vip_heuristic import RouteVipHeuristicPolicy
    from hangma_bot.simulation.engine import SimulationEngine
    from hangma_bot.simulation.interface import SimulationChoice
    from hangma_bot.offline.forced_action import ForceFirstActionPolicy
    from hangma_bot.offline.evaluate import MatchDriverConfig, frame_observation_summary, resume_match
    from hangma_bot.offline.scoring_input_capture import ScoringInputCapture, ScoringInputCaptureLimits
    from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents
    first_keys = {}

    class AuditScore:
        """包装两种公开评分接口，先保存实际DTO，再派发真实评分。"""
        def __init__(self, inner, kind, arm, seat, limit):
            self.inner, self.kind, self.arm, self.seat, self.limit = inner, kind, arm, seat, limit
            self.name, self.max_operations = getattr(inner, "name", kind), limit
            self.rows, self.context = [], {}

        @property
        def last_operation_count(self):
            return self.inner.last_operation_count

        @last_operation_count.setter
        def last_operation_count(self, value):
            require(self.kind == "C", "R18只读操作数不能重置")
            self.inner.last_operation_count = value

        def score(self, view):
            return self.perform(view, False)

        def score_vip_route(self, view):
            return self.perform(view, True)

        def perform(self, view, vip):
            row = {"event": "score_call", "kind": self.kind, "arm": self.arm, "seat": self.seat, **self.context,
                "status": "failed", "score_dispatched": False, "operation_limit": self.limit,
                "operations": None, "input_capture": None}
            self.rows.append(row)
            tick = time.monotonic()
            try:
                charge(self.kind + ":score_entries")
                row["score_entry"] = counts[self.kind + ":score_entries"]
                dto = view.candidate_view()
                receipt = capture.store(dto)
                row["input_capture"] = asdict(receipt)
                require(receipt.saved_before_score, "完整实际输入捕获失败，禁止评分")
                keys = [a.action_key for a in view.actions]
                charge(self.kind + ":score_calls")
                row["score_dispatched"] = True
                scored = self.inner.score_vip_route(view) if vip else self.inner.score(view)
                entries = list(scored.entries)
                require(scored.status == "SCORED" and len(entries) == len(keys)
                        and len({e.action_key for e in entries}) == len(keys)
                        and {e.action_key for e in entries} == set(keys), "实际评分未完整逐合法键SCORED")
                ops = self.inner.last_operation_count
                require(type(ops) is int and 0 <= ops <= self.limit, "真实评分操作数不在冻结额度内")
                # trace可含计费dict/list子类；原样交canonical JSON，避免asdict深拷贝重构子类。
                row.update(status="SCORED", legal_action_keys=keys,
                    scores={"status": scored.status, "reason": scored.reason,
                        "entries": [{"action_key": e.action_key, "score": e.score, "trace": e.trace} for e in entries]},
                    ranking=[e.action_key for e in sorted(entries, key=lambda e: (-e.score, e.action_key))])
                return scored
            except BaseException as exc:
                row["error"] = type(exc).__name__ + ": " + str(exc)
                raise
            finally:
                if row["score_dispatched"]:
                    row["operations"] = self.inner.last_operation_count
                row["elapsed_monotonic_seconds"] = time.monotonic() - tick
                event(row)

    class AuditPolicy:
        """记录完整公开请求与实际计划；is_emergency同键自身评分仍为正常成功。"""
        def __init__(self, inner, policy_id, arm, seat, scorer=None):
            self.inner, self.policy_id, self.arm, self.seat, self.scorer = inner, policy_id, arm, seat, scorer

        async def choose(self, request, budget):
            charge("policy_choose_calls")
            begin = len(self.scorer.rows) if self.scorer else 0
            if self.scorer is not None:
                self.scorer.context = {"policy_call_no": counts["policy_choose_calls"],
                    "decision_id": request.decision_id, "window_key": window_key_to_json(request.window_key)}
            row = {"event": "policy_choose", "arm": self.arm, "seat": self.seat, "policy_id": self.policy_id,
                "policy_call_no": counts["policy_choose_calls"], "decision_id": request.decision_id,
                "window_key": window_key_to_json(request.window_key), "observation": observation_to_json(request.observation),
                "legal_action_keys": [c.action_key for c in request.rules.legal_candidates], "status": "failed"}
            try:
                require(request.rules.completeness.value == "complete", "当前规则分析不完整")
                if self.scorer is not None:
                    charge(self.scorer.kind + ":scoring_projection_attempts")
                chosen = await self.inner.choose(request, budget)
                require(bool(chosen.candidates), "空计划")
                require(not any("action_value_failed" in reason for reason in chosen.degraded_reasons), "R18内部评分回退")
                if self.scorer:
                    calls = self.scorer.rows[begin:]
                    require(len(calls) == 1 and calls[0]["status"] == "SCORED"
                            and calls[0]["input_capture"]["saved_before_score"], "本次策略没有自身完整成功评分")
                    require(len(chosen.candidates) == len(row["legal_action_keys"])
                            and {c.action_key for c in chosen.candidates} == set(row["legal_action_keys"]), "计划未完整合法键覆盖")
                row.update(status="chosen", selected_action_key=chosen.candidates[0].action_key,
                    ordered_action_keys=[c.action_key for c in chosen.candidates],
                    degraded_reasons=list(chosen.degraded_reasons), is_emergency=chosen.candidates[0].is_emergency,
                    scored_by_self=self.scorer is not None)
                if self.seat == focal and request.window_key == target:
                    first_keys[self.arm] = chosen.candidates[0].action_key
                return chosen
            except BaseException as exc:
                row["error"] = type(exc).__name__ + ": " + str(exc)
                raise
            finally:
                event(row)

    class TraceEngine:
        """透传公开frame/advance，留最后句柄与成功合法前缀供结算导出。"""
        def __init__(self, arm):
            self.arm, self.last_world, self.prefix = arm, None, []

        def frame(self, world):
            self.last_world = world
            return call("world_frame_calls", engine.frame, world)

        def advance(self, world, revision, choices):
            row = {"event": "advance", "arm": self.arm, "revision": revision,
                "choices": [{"window_key": window_key_to_json(c.window_key), "action_key": action_key(c.action)} for c in choices]}
            event({**row, "status": "advance_pending"})
            next_world = call("world_advance_calls", engine.advance, world, revision, choices)
            self.last_world = next_world
            self.prefix.append(row)
            event({**row, "status": "advanced"})
            return next_world

    def policy(label, arm, seat, candidate=None, forced=None):
        meta, scored = plan["policy_metadata"][label], None
        if candidate is not None:
            inner = call("candidate_policy_constructors", RouteVipHeuristicPolicy, batch.rule_config,
                source=sources[candidate], max_operations=batch.max_operations, projection_limits=batch.projection_limits)
            scored = AuditScore(inner.executor, "C", arm, seat, batch.max_operations)
            inner.executor = scored
            identity = "vip:" + plan["packages"][candidate]["identity"]["candidate_id"]
        elif "registered_name" in meta:
            raw_scorer = call("r18_scorer_constructors", build_research_candidate_scorer, meta["registered_name"])
            require(raw_scorer.max_operations == meta["max_operations"]
                    and hashlib.sha256(raw_scorer.source.encode()).hexdigest() == meta["source_sha256"], "真实R18源码/额度不符")
            scored = AuditScore(raw_scorer, "R18", arm, seat, raw_scorer.max_operations)
            inner = call("r18_policy_constructors", ActionValuePolicy, scored, value_limits=batch.route_limits)
            identity = meta["policy_id"]
        else:
            params = meta["params"]
            weights = HeuristicWeightsV1(**params["weights"])
            if label == "M2":
                inner = call("opponent_policy_constructors", ComparableHeuristicPolicyV2, weights=weights, monotonic=lambda: 800.0)
            else:
                require(label == "M3", "没有公开对应的原对手工厂")
                inner = call("opponent_policy_constructors", V2HuUpgradePolicy, weights=weights, monotonic=lambda: 800.0,
                    risk_cells=tuple(UpgradeRiskCell(**c) for c in params["risk_cells"]),
                    risk_version=params["risk_version"], safety_margin=params["safety_margin"], upgrade_weight=params["upgrade_weight"])
            identity = meta["policy_id"]
        if forced is not None:
            inner = ForceFirstActionPolicy(inner, target_window=target, forced_action_key=forced, policy_id=identity + ":" + arm)
        return AuditPolicy(inner, identity, arm, seat, scored)

    for row in arms:
        current_arm = row
        row["status"] = "preparing_arm"
        arm = row["arm"]
        name = arm.split("-")[0] if arm != "A" else None
        forced = None
        if arm.endswith("-B"):
            require(name + "-C" in first_keys, "C目标首选缺失，B不允许补猜")
            forced = first_keys[name + "-C"]
        policies = [None] * 4
        for logical, label in enumerate(plan["logical_labels"]):
            seat = plan["permutation"][logical]
            policies[seat] = policy(label, arm, seat, candidate=name if logical == 0 and arm.endswith("-C") else None,
                                    forced=forced if logical == 0 else None)
        traced = TraceEngine(arm)
        frame = traced.frame(common)
        require(frame_observation_summary(frame) == stage_snapshot["observation_summary"], "臂未从共同目标帧开始")
        charge("continuation_instances")
        require(counts["continuation_instances"] <= plan["budgets"]["continuation"]["max_instances"], "续打实例超出冻结分母")
        row.update(status="dispatched", dispatched=True)
        snapshot = dict(stage_snapshot, match_spec={"match_id": match_id + ":" + arm})
        outcome = await resume_match(engine=traced, world=common, policies_by_seat=tuple(policies), rules=rules,
            choice_factory=SimulationChoice, config=MatchDriverConfig("logical", plan["budgets"]["continuation"]["steps_per_arm"], BudgetPolicy(),
                root_id, True, batch.route_limits),
            now_monotonic=lambda: 800.0, wall_clock=None, value_limits=batch.route_limits,
            stage_snapshot=snapshot, remaining_schedule={"declared_endpoint": "current_single_hand_end"})
        row.update(simulation_outcome_status=outcome.status, outcome=outcome.to_json(), successful_advance_frames=len(traced.prefix))
        require(outcome.status == "complete" and outcome.completed_hands == 1, "臂未完整结束当前单局")
        target_decisions = [d for d in outcome.decisions if window_id(dict(d.window_key)) == window_id(window_key_to_json(target))]
        require(len(target_decisions) == 1 and target_decisions[0].action_key == first_keys[arm], "目标实际执行与自己首选不符")
        if arm.endswith("-B"):
            force = policies[focal].inner
            require(force.force_count == 1 and target_decisions[0].action_key == forced, "B干预次数/实际动作与C首选不符")
            row["force_count"] = force.force_count
        settlement = call("world_export_settlement_calls", engine.export_hand_settlement, traced.last_world,
                          round_no)
        row.update(settlement=settlement, focal_net_score=settlement["score_delta"][focal], first_action_key=first_keys[arm])
        if arm.endswith("-B") and first_keys[arm] == first_keys["A"]:
            require(outcome.final_scores == tuple(arms[0]["outcome"]["final_scores"])
                    and outcome.completed_hands == arms[0]["outcome"]["completed_hands"], "同首动作B与A终局不一致")
            # 去除arm/decision_id诊断标识，严格核整段实际窗口/动作与费用无关轨迹。
            shape = lambda d: [(x["window_key"], x["action_key"]) for x in d]
            require(shape(row["outcome"]["decisions"]) == shape(arms[0]["outcome"]["decisions"]), "同首动作B与A实际路径不一致")
            row["same_first_action_determinism"] = "verified_by_actual_B_execution"
        row["status"] = "complete"
        output.save(output_dir / (arm + "-outcome.json"), row)
        current_arm = None
    deltas = {name: {"B_minus_A": arms[ORDER.index(name + "-B")]["focal_net_score"] - arms[0]["focal_net_score"],
        "C_minus_A": arms[ORDER.index(name + "-C")]["focal_net_score"] - arms[0]["focal_net_score"],
        "C_minus_B": arms[ORDER.index(name + "-C")]["focal_net_score"] - arms[ORDER.index(name + "-B")]["focal_net_score"]}
        for name in PACKAGES}
    return {"arms": arms, "deltas": deltas}
