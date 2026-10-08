"""不透明世界合法前缀恢复、公开相容采样与首手／持续策略贡献对照。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t182-step12-diagnosis-and-joint-evolution-1'

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
import ctypes
import fcntl
import gzip
import json
import os
import time
from dataclasses import asdict, replace
from pathlib import Path

from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.kernel.serialization import observation_to_json, window_key_to_json, window_key_from_json
from hangma_bot.offline.evaluate import MatchDriverConfig, frame_observation_summary, resume_match
from hangma_bot.offline.forced_action import ForceFirstActionPolicy
from hangma_bot.offline.qualifier_opponents import build_qualifier_runtime
from hangma_bot.offline.scoring_input_capture import ScoringInputCapture, ScoringInputCaptureLimits
from hangma_bot.offline.vip_eoh_generate import VipEohBatch
from hangma_bot.offline.vip_route_development import VipDevelopmentAuditPolicy
from hangma_bot.simulation import MatchSpec, SimulationChoice
from prepare_diagnostics import pin, save
from run_diagnostic_sources import canonical

HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT


def unchanged(plan):
    """从准备到终态核全部小文件和规则闭包，线上文件不在本任务写集合。"""
    return all(pin(Path(p)) == h for p, h in plan["files"].items()) and all(
        pin(_project_file(_PROJECT_ROOT, ROOT / p)) == h for p, h in plan["source_manifest"].items())


class EndpointEngine:
    """只经模拟公开接口终止于指定已结算单局；不读取WorldState字段。"""
    def __init__(self, engine, round_no):
        self.engine, self.round_no, self.last = engine, round_no, None

    def frame(self, world):
        self.last = world
        frame = self.engine.frame(world)
        if frame.completed_hands >= self.round_no and frame.final_scores is None:
            settled = self.engine.export_hand_settlement(world, self.round_no)
            return replace(frame, decisions=(), final_scores=tuple(settled["scores_after"]))
        return frame

    def advance(self, world, revision, choices):
        self.last = self.engine.advance(world, revision, choices)
        return self.last


def recover(runtime, composition, case, closure, batch):
    """原桌所有座位的合法动作逐帧恢复；目标完整本家观察和合法集必须精确。"""
    engine, rules = runtime.engine, runtime.rules
    match_id = "t182-diagnostic:" + composition["root_id"]
    world = engine.start(MatchSpec(match_id, composition["root_id"], runtime.config,
                                  composition["seed"], 0, (0, 0, 0, 0)))
    records, cursor = closure["outcome"]["decisions"], 0
    for _ in range(50000):
        frame = engine.frame(world)
        assert frame.blocked_reason is None and frame.final_scores is None
        focal = next((d for d in frame.decisions if window_key_to_json(d.window_key) == case["window_key"]), None)
        if focal is not None:
            assert observation_to_json(focal.observation) == case["observation"]
            legal = rules.analyze(focal.observation, route_limits=batch.route_limits)
            assert legal.completeness.value == "complete"
            assert {c.action_key for c in legal.legal_candidates} == set(case["legal_action_keys"])
            return world, frame, cursor
        old = records[cursor:cursor + len(frame.decisions)]
        assert [window_key_to_json(d.window_key) for d in frame.decisions] == [r["window_key"] for r in old]
        choices = []
        for d, r in zip(frame.decisions, old):
            analysis = rules.analyze(d.observation, route_limits=batch.route_limits)
            assert analysis.completeness.value == "complete" and r["legal"] and r["fallback_reason"] is None
            action = [c.action for c in analysis.legal_candidates if c.action_key == r["action_key"]]
            assert len(action) == 1
            choices.append(SimulationChoice(d.window_key, action[0]))
        world = engine.advance(world, frame.revision, tuple(choices))
        cursor += len(old)
    raise RuntimeError("合法前缀恢复超步数")


async def run_target(index, plan):
    """单目标持共用后台锁；B的同动作同续策可复用，但C从不按首手同就复用。"""
    target = plan["targets"][index - 1]
    case = target["case"]
    out = _project_file(_PROJECT_ROOT, HERE / "causal-continuations" / f"target-{index:03d}")
    out.mkdir(parents=True, exist_ok=False)
    save(out / "START.json", {"target": target, "plan_pin": pin(_project_file(_PROJECT_ROOT, HERE / "CAUSAL-PLAN.json")),
                              "independent_strength_sources": 0, "model_calls": 0})
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "DIAGNOSTIC-EXECUTION-BATCH.json"))
    diagnostic = json.loads((_project_file(_PROJECT_ROOT, HERE / "DIAGNOSTIC-PLAN.json")).read_text())
    composition = next(r for r in diagnostic["roots"] if r["root_id"] == case["root_id"])
    closure = json.loads((_project_file(_PROJECT_ROOT, ROOT / case["source_closure"])).read_text())
    assert closure["complete"] and unchanged(plan)
    sources = {"parent": (_project_file(_PROJECT_ROOT, HERE / "parent-source.py")).read_text()}
    sources.update({n: (_project_file(_PROJECT_ROOT, HERE / "diagnostic-prototypes" / (n + ".py"))).read_text() for n in target["prototype_first"]})
    runtime = build_qualifier_runtime(batch, sources["parent"], composition["opponent_types_logical_1_2_3"])
    results, rows = [], []
    counts = {"new_origin_worlds": 0, "hidden_samples": 0, "single_hand_dispatched": 0,
              "remaining_table_dispatched": 0, "scored_decisions": 0, "reused_exact_B": 0}
    failure, capture_result = None, None
    started = time.monotonic()
    raw = (out / "views.jsonl.gz").open("x+b")
    capture = ScoringInputCapture(raw, limits=ScoringInputCaptureLimits.from_json(plan["capture_limits"]))
    decisions = gzip.open(out / "decisions.jsonl.gz", "xb")

    def record(row):
        assert row["status"] == "chosen" and row["c_self_scored"]
        assert row["scoring_execution"]["full_legal_keys"]
        assert not row["degraded_reasons"]
        decisions.write(canonical(row) + b"\n")
        decisions.flush()
        rows.append(row)
        counts["scored_decisions"] += 1

    try:
        counts["new_origin_worlds"] += 1
        world, original, prefix_decisions = recover(runtime, composition, case, closure, batch)
        save(out / "RECOVERY.json", {"prefix_decisions": prefix_decisions,
            "focal_full_observation_and_legal_set_exact": True,
            "original_frame_summary": frame_observation_summary(original),
            "teacher_only_original_hand": runtime.engine.export_hand(world, case["window_key"]["round_no"])})
        for sample in range(1, plan["worlds_per_target"] + 1):
            assert time.monotonic() - started < plan["wall_seconds_per_target"]
            sample_key = f"t182:{case['label']}:hidden:{sample}"
            common = runtime.engine.resample_public_consistent_hidden_world(world, focal_seat=0, sample_key=sample_key)
            counts["hidden_samples"] += 1
            first = runtime.engine.frame(common)
            focal = next(d for d in first.decisions if d.window_key.seat == 0)
            assert observation_to_json(focal.observation) == case["observation"]
            endpoints = [("single_hand", case["window_key"]["round_no"])]
            if sample == 1 and target["dealer_tail_control"]:
                endpoints.append(("remaining_table", 8))
            for endpoint, last_round in endpoints:
                actions = {"A": ("parent", None)}
                for name, action in target["prototype_first"].items():
                    actions["B:" + name] = ("parent", action)
                    actions["C:" + name] = (name, None)
                for name, action in target.get("first_action_controls", {}).items():
                    actions["B:" + name] = ("parent", action)
                reusable = {}
                for arm, (name, forced) in actions.items():
                    if arm.startswith("B:") and forced in reusable:
                        original_result = reusable[forced]
                        results.append({**original_result, "arm": arm, "reused_exact_from": original_result["arm"],
                                        "actual_new_continuation": False, "forced_count": 0})
                        counts["reused_exact_B"] += 1
                        continue
                    assert time.monotonic() - started < plan["wall_seconds_per_target"]
                    fresh = build_qualifier_runtime(batch, sources[name], composition["opponent_types_logical_1_2_3"])
                    policy = VipDevelopmentAuditPolicy(fresh.policies_by_id[fresh.challenger_policy_id],
                        fresh.challenger_policy_id, lambda: {"target": index, "sample": sample, "arm": arm,
                        "endpoint": endpoint, "focal_vip": True}, record, challenger=True, capture=capture)
                    forced_policy = None
                    if forced is not None:
                        forced_policy = ForceFirstActionPolicy(policy, target_window=window_key_from_json(case["window_key"]),
                            forced_action_key=forced, policy_id="t182-force-first")
                        policy = forced_policy
                    opponents = tuple(fresh.policies_by_id[fresh.declarations[f"Q{i}"].policy_id] for i in range(1, 4))
                    engine = EndpointEngine(runtime.engine, last_round)
                    start_frame = engine.frame(common)
                    counter = "single_hand_dispatched" if endpoint == "single_hand" else "remaining_table_dispatched"
                    counts[counter] += 1
                    before = len(rows)
                    outcome = await resume_match(engine=engine, world=common, policies_by_seat=(policy, *opponents),
                        rules=fresh.rules, choice_factory=SimulationChoice,
                        config=MatchDriverConfig("logical", plan["step_limit"], BudgetPolicy(), "t182-causal", True, batch.route_limits),
                        now_monotonic=lambda: 800.0, wall_clock=None, value_limits=batch.route_limits,
                        stage_snapshot={"observation_summary": frame_observation_summary(start_frame)},
                        remaining_schedule={"declared_endpoint": endpoint})
                    assert outcome.status == "complete" and outcome.completed_hands == last_round
                    assert all(v == 0 for v in asdict(outcome.runtime_counts).values())
                    own_first = next(d for d in outcome.decisions if d.window_key == case["window_key"])
                    expected = forced or (target["parent_first"] if name == "parent" else target["prototype_first"][name])
                    assert own_first.action_key == expected
                    assert forced_policy is None or forced_policy.force_count == 1
                    settlements = [runtime.engine.export_hand_settlement(engine.last, r)
                                   for r in range(case["window_key"]["round_no"], last_round + 1)]
                    result = {"sample": sample, "sample_key": sample_key, "arm": arm, "endpoint": endpoint,
                        "actual_new_continuation": True, "first_actual": own_first.action_key,
                        "forced_count": 0 if forced_policy is None else forced_policy.force_count,
                        "settlements": settlements, "focal_net_score": sum(s["score_delta"][0] for s in settlements),
                        "focal_scores": len(rows) - before, "completed_hand_number": last_round,
                        "new_completed_hand_instances": len(settlements)}
                    save(out / f"sample-{sample}-{endpoint}-{arm.replace(':', '-')}-OUTCOME.json", outcome.to_json())
                    results.append(result)
                    if arm == "A" or arm.startswith("B:"):
                        reusable[result["first_actual"]] = result
                    print(json.dumps({"target": index, "sample": sample, "endpoint": endpoint,
                                      "arm": arm, "complete": True}), flush=True)
    except BaseException as error:
        failure = {"type": type(error).__name__, "message": str(error)}
    finally:
        decisions.close()
        try:
            capture_result = capture.finish()
        except BaseException as error:
            failure = failure or {"type": type(error).__name__, "message": str(error)}
        raw.close()
        complete = failure is None and unchanged(plan) and capture_result is not None and capture_result["terminal"]["terminal_valid"]
        save(out / "CLOSURE.json", {"complete": complete, "failure": failure, "source_stable": unchanged(plan),
            "target": target, "counts": counts, "results": results, "capture": capture_result,
            "model_calls": 0, "strength_admission": False, "deadline_admission": False,
            "elapsed_monotonic_seconds": time.monotonic() - started})
    if not complete:
        raise RuntimeError("续打失败保留原分母:" + str(failure))


async def main(indices):
    """每目标独占共享锁，目标之间释放以让后台统计；不停止活房。"""
    os.nice(15)
    assert ctypes.CDLL(None).setiopolicy_np(0, 0, 3) == 0
    plan = json.loads((_project_file(_PROJECT_ROOT, HERE / "CAUSAL-PLAN.json")).read_text())
    with (_project_file(_PROJECT_ROOT, ROOT / ".private/t165-live-watchdog/postprocess.lock")).open("a+") as lock:
        for index in indices:
            assert unchanged(plan)
            print(json.dumps({"target": index, "state": "waiting_postprocess_lock"}), flush=True)
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                await run_target(index, plan)
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)
            await asyncio.sleep(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--targets", type=int, nargs="+", required=True)
    asyncio.run(main(parser.parse_args().targets))
