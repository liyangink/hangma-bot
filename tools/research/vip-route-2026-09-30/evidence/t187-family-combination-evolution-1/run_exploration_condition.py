"""T187第二作者四研究槽条件续打；按真实座位恢复旧公开窗口，不改生产规则。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t187-family-combination-evolution-1'

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
import sys
import time
from dataclasses import asdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1')
sys.path.insert(0, str(PRIOR))
from common import ROOT, OLD, canonical, pin, save
from evaluation_sharding import resource_slot_paths
from t185_prepare_confirmation import background_priority
from reuse_causal_helpers import EndpointEngine, unchanged
from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.kernel.serialization import observation_to_json, window_key_to_json
from hangma_bot.offline.evaluate import MatchDriverConfig, frame_observation_summary, resume_match
from hangma_bot.offline.qualifier_opponents import build_qualifier_runtime
from hangma_bot.offline.scoring_input_capture import ScoringInputCapture, ScoringInputCaptureLimits
from hangma_bot.offline.vip_eoh_generate import VipEohBatch
from hangma_bot.offline.vip_route_development import VipDevelopmentAuditPolicy
from hangma_bot.simulation import MatchSpec, SimulationChoice

PLAN = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t187-family-combination-evolution-1/EXPLORATION-CONDITION-PLAN.json')
OUT = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t187-family-combination-evolution-1/exploration-condition')


def require(ok, message):
    """任一原件、观察或费用不符即失败；不自动换样本或删失败。"""
    if not ok:
        raise ValueError(message)


def recover(runtime, target, batch):
    """从原seed和全部座位合法动作恢复，窗口/完整本家观察/合法集逐字段核同。"""
    case, root = target["case"], target["composition"]
    closure = json.loads(Path(target["source_closure"]).read_text())
    require(closure["complete"] and closure["root"] == root and
            closure["rotation"] == target["focal_seat"], "原桌或物理座位不符")
    world = runtime.engine.start(MatchSpec(case["window_key"]["game_id"], root["root_id"],
        runtime.config, root["seed"], 0, (0, 0, 0, 0)))
    records, cursor = closure["outcome"]["decisions"], 0
    for _ in range(50000):
        frame = runtime.engine.frame(world)
        require(frame.blocked_reason is None and frame.final_scores is None, "目标前出现阻塞/终态")
        focal = next((d for d in frame.decisions if window_key_to_json(d.window_key) == case["window_key"]), None)
        if focal is not None:
            require(observation_to_json(focal.observation) == case["observation"], "恢复本家观察不同")
            rules = runtime.rules.analyze(focal.observation, route_limits=batch.route_limits)
            require(rules.completeness.value == "complete" and
                sorted(c.action_key for c in rules.legal_candidates) == case["legal_action_keys"], "恢复合法集不同")
            return world, cursor
        old = records[cursor:cursor + len(frame.decisions)]
        require([window_key_to_json(d.window_key) for d in frame.decisions] == [r["window_key"] for r in old],
                "恢复原动作窗口序列不同")
        choices = []
        for d, r in zip(frame.decisions, old):
            rules = runtime.rules.analyze(d.observation, route_limits=batch.route_limits)
            require(rules.completeness.value == "complete" and r["legal"] and r["fallback_reason"] is None,
                    "原前缀动作不合法或降级")
            actions = [c.action for c in rules.legal_candidates if c.action_key == r["action_key"]]
            require(len(actions) == 1, "原动作无唯一合法映射")
            choices.append(SimulationChoice(d.window_key, actions[0]))
        world = runtime.engine.advance(world, frame.revision, tuple(choices))
        cursor += len(old)
    raise RuntimeError("恢复超步数")


async def run_target(index, plan, plan_pin):
    """原历史及两相容抽样共享给A线上S02、C新提案；积分物理座位0—3。"""
    target = plan["targets"][index - 1]
    case, seat = target["case"], target["focal_seat"]
    directory = _project_file(_PROJECT_ROOT, OUT / f"target-{index:03d}")
    directory.mkdir(exist_ok=False)
    save(directory / "START.json", {"target": target, "plan_pin": plan_pin, "pid": os.getpid()})
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"))
    sources = {k: Path(v["source_file"]).read_text() for k, v in plan["arms_sources"].items()}
    require(all(batch.identity(sources[k]) == v["identity"] for k, v in plan["arms_sources"].items()), "公式身份漂移")
    runtime = build_qualifier_runtime(batch, sources["parent"], target["composition"]["opponent_types_logical_1_2_3"])
    counts = {"new_origin_worlds": 0, "hidden_samples": 0, "single_hand_dispatched": 0,
              "scored_decisions": 0, "actual_score_calls": 0}
    results, failure, terminal = [], None, None
    raw = (directory / "views.jsonl.gz").open("x+b")
    capture = ScoringInputCapture(raw, limits=ScoringInputCaptureLimits.from_json(plan["capture_limits"]))
    stream = gzip.open(directory / "decisions.jsonl.gz", "xb")
    started = time.monotonic()  # 研究持续秒，不是官方动作截止时间
    current = {}

    def record(row):
        stream.write(canonical({"sample": current["sample"], "arm": current["arm"], "row": row}) + b"\n")
        stream.flush()
        counts["scored_decisions"] += 1
        counts["actual_score_calls"] += sum(c["actual_score_calls"] for c in row.get("scoring_calls", []))
        require(row["status"] == "chosen" and row["c_self_scored"] and not row["degraded_reasons"] and
            len(row["scoring_calls"]) == 1 and row["scoring_calls"][0]["full_legal_keys"], "真实评分不完整")
        require(time.monotonic() - started < plan["wall_seconds_per_target"], "研究持续秒超限")

    try:
        counts["new_origin_worlds"] += 1
        world, cursor = recover(runtime, target, batch)
        save(directory / "RECOVERY.json", {"prefix_decisions": cursor, "full_public_observation_and_legal_set_exact": True,
            "focal_seat": seat, "historical_world_not_exported": True})
        for sample in range(0, plan["worlds_per_target"] + 1):
            require(unchanged(plan) and pin(PLAN) == plan_pin, "冻结材料漂移")
            sample_key = f"t187-family:{case['label']}:hidden:{sample}"
            # 0是已暴露原历史世界，不与1—4相容抽样合并成自然频率估计。
            common = world if sample == 0 else runtime.engine.resample_public_consistent_hidden_world(world, focal_seat=seat, sample_key=sample_key)
            if sample > 0:
                counts["hidden_samples"] += 1
            focal = next(d for d in runtime.engine.frame(common).decisions if d.window_key.seat == seat)
            require(observation_to_json(focal.observation) == case["observation"], "重采样改变可见状态")
            for arm, source_name in (("A", "parent"), ("C", "child")):
                current.update(sample=sample, arm=arm)
                fresh = build_qualifier_runtime(batch, sources[source_name], target["composition"]["opponent_types_logical_1_2_3"])
                inner = fresh.policies_by_id[fresh.challenger_policy_id]
                focal_policy = VipDevelopmentAuditPolicy(inner, fresh.challenger_policy_id,
                    lambda: {"target": index, "sample": sample, "arm": arm, "focal_seat": seat, "focal_vip": True},
                    record, challenger=True, capture=capture)
                policies = [None] * 4
                policies[seat] = focal_policy
                for logical in range(1, 4):
                    policies[(logical + seat) % 4] = fresh.policies_by_id[fresh.declarations[f"Q{logical}"].policy_id]
                endpoint = EndpointEngine(runtime.engine, case["window_key"]["round_no"])
                counts["single_hand_dispatched"] += 1
                before = counts["actual_score_calls"]
                outcome = await resume_match(engine=endpoint, world=common, policies_by_seat=tuple(policies),
                    rules=fresh.rules, choice_factory=SimulationChoice,
                    config=MatchDriverConfig("logical", plan["step_limit"], BudgetPolicy(), "t187-family-opportunity", True, batch.route_limits),
                    now_monotonic=lambda: 800.0, wall_clock=None, value_limits=batch.route_limits,
                    stage_snapshot={"observation_summary": frame_observation_summary(endpoint.frame(common))},
                    remaining_schedule={"declared_endpoint": "single_hand"})
                save(directory / f"sample-{sample}-{arm}-OUTCOME.json", outcome.to_json())
                require(outcome.status == "complete" and outcome.completed_hands == case["window_key"]["round_no"] and
                    all(type(v) is int and v == 0 for v in asdict(outcome.runtime_counts).values()), "单局未完整或故障")
                actual = next(d for d in outcome.decisions if d.window_key == case["window_key"])
                expected = target["parent_first"] if arm == "A" else target["candidate_first"]
                require(actual.action_key in case["legal_action_keys"] and (expected is None or actual.action_key == expected), "首手不符")
                settlement = runtime.engine.export_hand_settlement(endpoint.last, case["window_key"]["round_no"])
                results.append({"sample": sample, "sample_key": sample_key, "arm": arm, "first_actual": actual.action_key,
                    "forced_count": 0,
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
        complete = failure is None and unchanged(plan) and pin(PLAN) == plan_pin and terminal is not None and terminal["terminal"]["terminal_valid"]
        save(directory / "CLOSURE.json", {"complete": complete, "failure": failure, "source_stable": unchanged(plan),
            "target": target, "counts": counts, "results": results, "capture": terminal,
            "elapsed_monotonic_seconds": time.monotonic() - started, "strength_or_deadline_admission": False})
    require(complete, "条件续打失败，保留原费用，不重抽：" + str(failure))


async def worker(slot):
    """每槽自然跑完唯一目标分片；不持比赛赛后锁，不自动重试。"""
    background_priority()
    plan = json.loads(PLAN.read_text())
    plan_pin = pin(PLAN)
    require(unchanged(plan) and plan["cpu_worker_count"] == 4 and 0 <= slot < 4, "冻结或槽配置不符")
    lane = list(range(slot + 1, len(plan["targets"]) + 1, 4))
    directory = _project_file(_PROJECT_ROOT, OUT / f"worker-{slot}")
    directory.mkdir(exist_ok=False)
    with resource_slot_paths(OLD, 4)[slot].open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        save(directory / "START.json", {"pid": os.getpid(), "slot": slot, "targets": lane, "plan_pin": pin(PLAN),
            "nice": os.getpriority(os.PRIO_PROCESS, 0), "background_io": True})
        attempted, completed, failure = [], [], None
        try:
            for index in lane:
                attempted.append(index)
                require(pin(PLAN) == plan_pin and unchanged(plan), "worker冻结材料漂移")
                await run_target(index, plan, plan_pin)
                completed.append(index)
        except BaseException as error:
            failure = {"type": type(error).__name__, "message": str(error)}
        save(directory / "CLOSE.json", {"pid": os.getpid(), "slot": slot, "attempted": attempted,
            "completed": completed, "complete": completed == lane and failure is None, "failure": failure})
        require(failure is None, "worker自然失败，禁止重试")


async def dispatch():
    """保存四个实际PID，等待所有自然退出；不读中途成绩或启动新批。"""
    background_priority()
    plan = json.loads(PLAN.read_text())
    plan_pin = pin(PLAN)
    require(unchanged(plan) and len(plan["targets"]) == 14 and plan["worlds_per_target"] == 2 and plan["planned_single_hand_continuations"] == 84,
            "实验规模或冻结不符")
    OUT.mkdir(exist_ok=False)
    with (_project_file(_PROJECT_ROOT, HERE / ".campaign-owner.lock")).open("a+") as owner:
        fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        handles_for_slots = []
        try:
            for path in resource_slot_paths(OLD, 4):
                handle = path.open("a+")
                handles_for_slots.append(handle)
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            for handle in handles_for_slots:
                handle.close()
        processes, handles = [], []
        for slot in range(4):
            log = (_project_file(_PROJECT_ROOT, OUT / f"worker-{slot}.log")).open("x")
            handles.append(log)
            processes.append(await asyncio.create_subprocess_exec(sys.executable, str(Path(__file__)), "--slot", str(slot),
                cwd=ROOT, stdout=log, stderr=asyncio.subprocess.STDOUT,
                env={**os.environ, "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "PYTHONUNBUFFERED": "1"}))
        save(_project_file(_PROJECT_ROOT, OUT / "DISPATCH.json"), {"pid": os.getpid(), "children": [p.pid for p in processes], "plan_pin": pin(PLAN)})
        codes = await asyncio.gather(*(p.wait() for p in processes))
        for handle in handles:
            handle.close()
        complete = codes == [0, 0, 0, 0] and unchanged(plan) and pin(PLAN) == plan_pin
        save(_project_file(_PROJECT_ROOT, OUT / "DISPATCH-CLOSED.json"), {"complete": complete, "worker_returncodes": codes, "plan_pin": pin(PLAN),
            "children": [p.pid for p in processes], "all_processes_naturally_waited": True,
            "next_phase_auto_dispatch": False})
        require(complete, "有条件续打失败，全部原件保留")
    print(json.dumps({"complete": True, "cpu_workers": 4, "planned_single_hand_continuations": 84}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--slot", type=int)
    args = parser.parse_args()
    asyncio.run(dispatch() if args.slot is None else worker(args.slot))
