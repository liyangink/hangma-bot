"""一根原世界五臂当前单局原型；prepare 纯文件，execute 需明确 ROOT START。

固定 A、Sol-C/B、S02-C/B 顺序；各臂新策略实例，共同不透明单局世界。
候选与 R18 的同次真实评分前 DTO 去重保存；评分失败不以保底续打。
不复制规则、不读 WorldState 字段、不调用模型/API、不自动扩预算或重试。
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

import argparse
import asyncio
from collections import Counter
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Any

from recover_natural_start import (ROOT, canonical, fingerprint, load_material,
                                  read_json, require, recover_natural_start, window_id, write_new)

HERE = Path(__file__).resolve().parent
INPUT_SHA = "b4465a97adad408323e542d3a8b03be38ecd2cd1acc33fead95f34d69b2faebe"
VIP = _project_file(_PROJECT_ROOT, ROOT / "review/vip-route-2026-09-30")
BATCH = VIP / "evidence/t9-joint-author-execution-preparation-1/author-three-slot.batch.json"
PACKAGES = {"Sol": VIP / "evidence/t9-sol-joint-author-1/model-output",
            "S02": VIP / "evidence/t9-joint-author-execution-preparation-1/S02-m1-author/model-output"}
ORDER = ("A", "Sol-C", "Sol-B", "S02-C", "S02-B")
BUDGETS = {"recovery": {"max_replay_frames": 5000, "wall_clock_seconds": 600},
    "continuation": {"max_instances": 5, "steps_per_arm": 5000, "wall_clock_seconds": 1200},
    "capture": {"max_unique_views": 64, "max_view_json_bytes": 64 * 1024**2,
                "max_total_json_bytes": 256 * 1024**2}, "max_output_bytes": 256 * 1024**2}


def prepare(panel_file: Path, input_sha256: str, output_dir: Path) -> dict:
    """标准库纯文件准备；创建唯一 PREPARED，不装载候选或执行业务。"""
    require(input_sha256 == INPUT_SHA, "此原型只接受事前固定首根，不自动换目标")
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    try:
        recovery, _ = load_material(panel_file, input_sha256, output_dir / "recovery")
        batch = read_json(BATCH)
        manifest_path = next(Path(r["path"]) for r in recovery["source_refs"] if Path(r["path"]).name == "manifest.json")
        manifest = read_json(manifest_path)
        pool = recovery["origin"]["pool"]
        labels = ["A"] + (["H1", "H2", "H3"] if pool == "H" else ["M1", "M2", "M3"])
        require(pool in {"H", "M"}, "原对手池未识别")
        metadata = {label: manifest["policy_metadata"][label] for label in labels}
        require(batch["route_limits"] == recovery["value_limits"]
                and batch["rule_config"] == recovery["match_spec"]["config"]["rules"], "冻结候选批与自然规则/预算不符")
        files = {str(BATCH.resolve()): fingerprint(BATCH)}
        packages = {}
        for name, directory in PACKAGES.items():
            record_path, source_path = directory / "generation.json", directory / "candidate.py"
            record = read_json(record_path)
            identity = record["identity"]
            require(record["schema"] == "vip-route-eoh-generation/1" and record["status"] == "loaded_not_admitted"
                    and record["load"]["ok"] is True and record["identity_stable"] is True, "不是冻结已装载研究提案")
            require(identity["params"] == {k: batch[k] for k in
                ("max_operations", "projection_limits", "route_limits", "rule_config")}, "候选参数与同批装配不符")
            require(fingerprint(source_path)["sha256"] == identity["source_sha256"] == record["source_sha256"], "候选源码摘要不符")
            for relative, expected in identity["source_manifest"].items():
                require(fingerprint(_project_file(_PROJECT_ROOT, ROOT / relative)) == expected, "冻结候选依赖漂移: " + relative)
            for path in (record_path, source_path):
                files[str(path.resolve())] = fingerprint(path)
            packages[name] = {"path": str(directory.resolve()), "identity": identity}
        for label, meta in metadata.items():
            for relative, expected in meta["source_manifest"].items():
                require(fingerprint(_project_file(_PROJECT_ROOT, ROOT / relative)) == expected, "原对手/基线实现已变: " + label + ":" + relative)
        r18 = metadata["A"]
        require(r18["registered_name"] == "r18_integrated_positive_v2" and r18["max_operations"] == 100000,
                "本批 R18 真实冻结额度不是 100000")
        prepared = {"schema": "t10-abc-pilot-prepared/1", "tool_file": str(Path(__file__).resolve()),
            "tool_sha256": fingerprint(Path(__file__))["sha256"], "recovery_tool_sha256": recovery["tool_sha256"],
            "recovery": recovery, "batch_file": str(BATCH.resolve()), "files": files, "packages": packages,
            "policy_metadata": metadata, "logical_labels": labels, "pool": pool,
            "permutation": recovery["origin"]["permutation"], "arm_order": list(ORDER), "budgets": BUDGETS,
            "python_version": sys.version, "endpoint": "current_single_hand_end", "model_api_calls": 0,
            "claims": "one_root_development_tool_pilot_not_strength_or_confirmation"}
        write_new(output_dir / "PREPARED.json", prepared)
        return prepared
    except BaseException as exc:
        write_new(output_dir / "PREPARE-FAILED.json", {"status": "failed", "business_calls": 0,
                                                    "error": type(exc).__name__ + ": " + str(exc)})
        raise


class OutputLedger:
    """全批输出硬上限；预留64KiB终态费用，不把预留作为额外预算。"""
    def __init__(self, directory: Path, limit: int, reserve: int = 65536):
        self.directory, self.limit, self.reserve = directory, limit, reserve
        self.bytes = sum(p.stat().st_size for p in directory.rglob("*") if p.is_file())
        self.terminal = False
        self.write_attempts, self.write_failures = 0, 0
        require(0 < reserve < limit and self.bytes <= limit - reserve, "准备文件已耗尽输出预算")

    def open(self, path: Path, mode: str):
        """独占输出流；路径必须在本批目录内，读回/定位不计新字节。"""
        require(path.resolve().is_relative_to(self.directory), "输出越出本批目录")
        return LimitedStream(path.open(mode), self)

    def save(self, path: Path, value: Any):
        """写完整JSON；非有限/超预算/I/O错误抛出，不截字段冒充原件。"""
        stream = self.open(path, "xb")
        try:
            stream.write(canonical(value) + b"\n")
            stream.flush()
        finally:
            stream.close()


class LimitedStream:
    """计所有实际写入字节；其余二进制接口透传给公开捕获器。"""
    def __init__(self, stream, ledger):
        self.stream, self.ledger = stream, ledger

    def write(self, value):
        ledger = self.ledger
        ledger.write_attempts += 1
        ceiling = ledger.limit if ledger.terminal else ledger.limit - ledger.reserve
        if ledger.bytes + len(value) > ceiling:
            ledger.write_failures += 1
            raise RuntimeError("batch_output_byte_limit")
        try:
            size = self.stream.write(value)
            ledger.bytes += size
            require(size == len(value), "输出短写")
            return size
        except BaseException:
            ledger.write_failures += 1
            raise

    def __getattr__(self, name):
        return getattr(self.stream, name)


async def execute(output_dir: Path, start_path: Path) -> dict:
    """消费一份ROOT START；恢复加五臂全部失败与未启动臂保留原分母。"""
    output_dir, start_path = output_dir.resolve(), start_path.resolve()
    prepared_path = output_dir / "PREPARED.json"
    plan, start = read_json(prepared_path), read_json(start_path)
    require(plan["schema"] == "t10-abc-pilot-prepared/1" and start.get("schema") == "t10-abc-pilot-start/1"
            and start.get("status") == "START", "缺明确ABC ROOT START")
    require(Path(start["prepared_file"]).resolve() == prepared_path
            and start["prepared_sha256"] == fingerprint(prepared_path)["sha256"]
            and start["tool_sha256"] == plan["tool_sha256"] == fingerprint(Path(__file__))["sha256"]
            and start["budgets"] == plan["budgets"] == BUDGETS and plan["python_version"] == sys.version,
            "ROOT START/工具/预算/Python身份不符，不允许扩容")
    output = OutputLedger(output_dir, plan["budgets"]["max_output_bytes"])
    output.save(output_dir / "EXECUTION-ENTRY.json", {"start_path": str(start_path),
        "start_sha256": fingerprint(start_path)["sha256"], "status": "entered", "arm_order": list(ORDER)})
    events = output.open(output_dir / "calls-and-choices.jsonl", "xb")
    counts, begun, continued = Counter(), time.monotonic(), None
    arms = [{"arm": arm, "status": "not_started", "dispatched": False} for arm in ORDER]
    result = {"status": "unfinished", "arms": arms, "planned_roots": 1, "planned_original_worlds": 1,
              "planned_continuation_instances": 5, "model_api_calls": 0, "claims": plan["claims"]}
    capture, view_stream, primary, current_arm = None, None, None, None

    def charge(name):
        # 恢复自己检查600秒；后续1200秒从恢复成功后起算，均为协作时限。
        if continued is not None and time.monotonic() - continued >= plan["budgets"]["continuation"]["wall_clock_seconds"]:
            raise RuntimeError("continuation_wall_clock_limit")
        counts[name] += 1

    def event(value):
        events.write(canonical(value) + b"\n")
        events.flush()

    def call(name, fn, *args, **kwargs):
        charge(name)
        return fn(*args, **kwargs)

    try:
        for name, expected in plan["files"].items():
            require(fingerprint(Path(name)) == expected, "候选/批配置漂移: " + name)
        recovery_dir = output_dir / "recovery"
        recovery_dir.mkdir(exist_ok=False)
        recovered = recover_natural_start(Path(plan["recovery"]["panel_file"]), INPUT_SHA, recovery_dir,
            start_path=start_path, parent_prepared_file=prepared_path, charge=lambda name: charge("recovery:" + name),
            save_json=output.save, open_output=output.open)
        continued = time.monotonic()
        sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))
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
        batch = call("generation_batch_reads", VipEohBatch.read, Path(plan["batch_file"]))
        sources = {}
        for name, package in plan["packages"].items():
            loaded = call("candidate_package_validation_entries", load_vip_parents, [Path(package["path"])], batch)
            require(len(loaded) == 1 and loaded[0]["identity"] == package["identity"], "候选公开装载身份不等")
            sources[name] = loaded[0]["source"]
        view_stream = output.open(output_dir / "views.jsonl.gz", "x+b")
        capture = ScoringInputCapture(view_stream, limits=ScoringInputCaptureLimits(**plan["budgets"]["capture"]))

        class CountRules(HangmaRules):
            """统计同源规则调用；不实现第二套规则。"""
            def analyze(self, *args, **kwargs):
                return call("rules_analyze_calls", super().analyze, *args, **kwargs)

        rules = call("rules_constructors", CountRules, batch.rule_config)
        recovery_receipt = read_json(recovered.receipt_path)
        engine = call("world_engine_constructors", SimulationEngine, rules, rules_hash=recovery_receipt["rules_hash"])
        common = recovered.world
        common_frame = call("world_frame_calls", engine.frame, common)
        require(frame_observation_summary(common_frame) == recovered.stage_snapshot["observation_summary"], "共同句柄与恢复帧不符")
        focal, target = plan["permutation"][0], recovered.target_window
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
            require(frame_observation_summary(frame) == recovered.stage_snapshot["observation_summary"], "臂未从共同目标帧开始")
            charge("continuation_instances")
            require(counts["continuation_instances"] <= 5, "续打实例超出冻结分母")
            row.update(status="dispatched", dispatched=True)
            snapshot = dict(recovered.stage_snapshot, match_spec={"match_id": recovery_receipt["origin"]["mother_single_hand"][0] + ":" + arm})
            outcome = await resume_match(engine=traced, world=common, policies_by_seat=tuple(policies), rules=rules,
                choice_factory=SimulationChoice, config=MatchDriverConfig("logical", 5000, BudgetPolicy(),
                    plan["recovery"]["origin"]["mother_root"], True, batch.route_limits),
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
                              plan["recovery"]["origin"]["mother_single_hand"][1])
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
        result["deltas"] = {name: {"B_minus_A": arms[ORDER.index(name + "-B")]["focal_net_score"] - arms[0]["focal_net_score"],
            "C_minus_A": arms[ORDER.index(name + "-C")]["focal_net_score"] - arms[0]["focal_net_score"],
            "C_minus_B": arms[ORDER.index(name + "-C")]["focal_net_score"] - arms[ORDER.index(name + "-B")]["focal_net_score"]}
            for name in PACKAGES}
        for name, expected in plan["files"].items():
            require(fingerprint(Path(name)) == expected, "执行后候选/批漂移: " + name)
        for name, expected in plan["recovery"]["runtime_files"].items():
            require(fingerprint(Path(name)) == expected, "执行后运行代码漂移: " + name)
        require(fingerprint(prepared_path)["sha256"] == start["prepared_sha256"]
                and fingerprint(Path(__file__))["sha256"] == start["tool_sha256"], "执行后ROOT身份漂移")
        result["status"] = "five_arm_pilot_complete_not_strength_confirmation"
    except BaseException as exc:
        primary = exc
        result.update(status="failed_original_denominator_retained", error=type(exc).__name__ + ": " + str(exc))
        if current_arm is not None:
            current_arm.update(status="failed", error=result["error"])
        for row in arms:
            if row["status"] == "not_started":
                row["status"] = "not_started_after_first_failure"
            elif row["status"] == "dispatched":
                row.update(status="failed", error=result["error"])
        raise
    finally:
        # 终态先压缩闭流验签，再用预留空间保存精简费用；失败不被下一次成功覆盖。
        cleanup_errors = []
        if capture is not None:
            try:
                capture.finish()
            except BaseException as exc:
                cleanup_errors.append(type(exc).__name__ + ": " + str(exc))
            result["input_capture"] = capture.costs
            if not capture.costs["terminal"]["terminal_valid"]:
                result["status"] = "failed_input_capture_terminal"
        for stream in (view_stream, events):
            if stream is not None:
                try:
                    stream.close()
                except BaseException as exc:
                    cleanup_errors.append(type(exc).__name__ + ": " + str(exc))
        result.update(actual_calls=dict(counts), elapsed_monotonic_seconds=time.monotonic() - begun,
            continuation_monotonic_seconds=None if continued is None else time.monotonic() - continued,
            completed_arms=sum(r["status"] == "complete" for r in arms), dispatched_arms=sum(r["dispatched"] for r in arms),
            missing_or_failed_arms=sum(r["status"] != "complete" for r in arms), cleanup_errors=cleanup_errors,
            output_bytes_before_terminal=output.bytes, output_write_attempts=output.write_attempts,
            output_write_failures=output.write_failures, timing_scope="local_cooperative_monotonic_duration")
        output.terminal = True
        # 逐臂详细原件单列；终态收据不重复巨大decisions数组，以免失败收口再次耗尽。
        receipt = {**result, "arms": [{k: v for k, v in r.items() if k != "outcome"} for r in arms]}
        try:
            output.save(output_dir / "COSTS-AND-RESULT.json", receipt)
        except BaseException as secondary:
            if primary is None:
                raise
            primary.add_note("ABC费用收口再次失败: " + type(secondary).__name__ + ": " + str(secondary))
        if primary is None and (cleanup_errors or result["status"] != "five_arm_pilot_complete_not_strength_confirmation"):
            raise RuntimeError("ABC输入/输出终态不完整，详见费用收据")
    return result


def main():
    """CLI：prepare不导入业务；execute只接受准备目录及显式ROOT START。"""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--panel-file", required=True, type=Path)
    p.add_argument("--input-sha256", default=INPUT_SHA)
    p.add_argument("--output-dir", required=True, type=Path)
    e = sub.add_parser("execute")
    e.add_argument("--output-dir", required=True, type=Path)
    e.add_argument("--start", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        plan = prepare(args.panel_file, args.input_sha256, args.output_dir)
        print(canonical({"status": "prepared_no_business_calls", "tool_sha256": plan["tool_sha256"],
                         "prepared_sha256": fingerprint(args.output_dir / "PREPARED.json")["sha256"],
                         "arm_order": plan["arm_order"], "pool": plan["pool"]}).decode())
    else:
        result = asyncio.run(execute(args.output_dir, args.start))
        print(canonical({"status": result["status"], "actual_calls": result["actual_calls"]}).decode())


if __name__ == "__main__":
    main()
