"""候选真实改选的A/B/C单局续打，复用生产规则和不透明世界公开接口。"""

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
from dataclasses import asdict
from pathlib import Path

from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.kernel.serialization import observation_to_json, window_key_from_json
from hangma_bot.offline.evaluate import MatchDriverConfig, frame_observation_summary, resume_match
from hangma_bot.offline.forced_action import ForceFirstActionPolicy
from hangma_bot.offline.qualifier_opponents import build_qualifier_runtime
from hangma_bot.offline.scoring_input_capture import ScoringInputCapture, ScoringInputCaptureLimits
from hangma_bot.offline.vip_eoh_generate import VipEohBatch
from hangma_bot.offline.vip_route_development import VipDevelopmentAuditPolicy
from hangma_bot.simulation import SimulationChoice
from prepare_diagnostics import pin, save
from run_causal import EndpointEngine, recover, unchanged
from run_diagnostic_sources import canonical

HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT


async def run_target(index, plan):
    """先恢复全部合法前缀，改变首手后用模拟推进未来；不照搬旧牌谱续行。"""
    target = plan["targets"][index - 1]
    case = target["case"]
    out = _project_file(_PROJECT_ROOT, HERE / "candidate-causal-continuations" / f"target-{index:03d}")
    out.mkdir(parents=True, exist_ok=False)
    save(out / "START.json", {"target": target, "plan_pin": pin(_project_file(_PROJECT_ROOT, HERE / "CANDIDATE-CAUSAL-PLAN.json")),
                              "model_calls": 0, "logical_clock_not_official_deadline": True})
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"))
    diagnostic = json.loads((_project_file(_PROJECT_ROOT, HERE / "DIAGNOSTIC-PLAN.json")).read_text())
    composition = next(r for r in diagnostic["roots"] if r["root_id"] == case["root_id"])
    closure = json.loads((_project_file(_PROJECT_ROOT, ROOT / case["source_closure"])).read_text())
    assert closure["complete"] and unchanged(plan)
    sources = {"parent": (_project_file(_PROJECT_ROOT, HERE / "parent-source.py")).read_text(),
               "child": Path(target["candidate_source_file"]).read_text()}
    assert batch.identity(sources["child"]) == target["identity"]
    runtime = build_qualifier_runtime(batch, sources["parent"], composition["opponent_types_logical_1_2_3"])
    results, rows = [], []
    counts = {"new_origin_worlds": 0, "hidden_samples": 0, "single_hand_dispatched": 0,
              "scored_decisions": 0, "actual_score_calls": 0}
    failure, capture_result = None, None
    started = time.monotonic()
    raw = (out / "views.jsonl.gz").open("x+b")
    capture = ScoringInputCapture(raw, limits=ScoringInputCaptureLimits.from_json(plan["capture_limits"]))
    decisions = gzip.open(out / "decisions.jsonl.gz", "xb")

    def record(row):
        """失败也先落盘、计费；强制首动作在完整原计划之后另行干预。"""
        decisions.write(canonical(row) + b"\n")
        decisions.flush()
        rows.append(row)
        counts["scored_decisions"] += 1
        counts["actual_score_calls"] += sum(c["actual_score_calls"] for c in row.get("scoring_calls", []))
        assert row["status"] == "chosen" and row["c_self_scored"] and not row["degraded_reasons"]
        assert len(row["scoring_calls"]) == 1 and row["scoring_calls"][0]["full_legal_keys"]
        assert time.monotonic() - started < plan["wall_seconds_per_target"]

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
            focal = next(d for d in runtime.engine.frame(common).decisions if d.window_key.seat == 0)
            assert observation_to_json(focal.observation) == case["observation"]
            for arm, name, forced in (("A", "parent", None), ("B", "parent", target["candidate_first"]),
                                      ("C", "child", None)):
                assert time.monotonic() - started < plan["wall_seconds_per_target"]
                fresh = build_qualifier_runtime(batch, sources[name], composition["opponent_types_logical_1_2_3"])
                policy = VipDevelopmentAuditPolicy(fresh.policies_by_id[fresh.challenger_policy_id],
                    fresh.challenger_policy_id, lambda: {"target": index, "sample": sample, "arm": arm,
                        "candidate_id": target["identity"]["candidate_id"], "focal_vip": True},
                    record, challenger=True, capture=capture)
                forced_policy = None
                if forced is not None:
                    forced_policy = ForceFirstActionPolicy(policy, target_window=window_key_from_json(case["window_key"]),
                        forced_action_key=forced, policy_id="t182-force-first")
                    policy = forced_policy
                opponents = tuple(fresh.policies_by_id[fresh.declarations[f"Q{i}"].policy_id] for i in range(1, 4))
                last_round = case["window_key"]["round_no"]
                engine = EndpointEngine(runtime.engine, last_round)
                start_frame = engine.frame(common)
                counts["single_hand_dispatched"] += 1
                before = len(rows)
                outcome = await resume_match(engine=engine, world=common, policies_by_seat=(policy, *opponents),
                    rules=fresh.rules, choice_factory=SimulationChoice,
                    config=MatchDriverConfig("logical", plan["step_limit"], BudgetPolicy(), "t182-child-causal", True, batch.route_limits),
                    now_monotonic=lambda: 800.0, wall_clock=None, value_limits=batch.route_limits,
                    stage_snapshot={"observation_summary": frame_observation_summary(start_frame)},
                    remaining_schedule={"declared_endpoint": "single_hand"})
                save(out / f"sample-{sample}-{arm}-OUTCOME.json", outcome.to_json())
                assert outcome.status == "complete" and outcome.completed_hands == last_round
                assert all(v == 0 for v in asdict(outcome.runtime_counts).values())
                own_first = next(d for d in outcome.decisions if d.window_key == case["window_key"])
                expected = target["parent_first"] if arm == "A" else target["candidate_first"]
                assert own_first.action_key == expected
                assert forced_policy is None or forced_policy.force_count == 1
                settlement = runtime.engine.export_hand_settlement(engine.last, last_round)
                results.append({"sample": sample, "sample_key": sample_key, "arm": arm,
                    "actual_new_continuation": True, "first_actual": own_first.action_key,
                    "forced_count": 0 if forced_policy is None else forced_policy.force_count,
                    "settlements": [settlement], "focal_net_score": settlement["score_delta"][0],
                    "focal_scores": len(rows) - before, "completed_hand_number": last_round,
                    "new_completed_hand_instances": 1})
                print(json.dumps({"target": index, "sample": sample, "arm": arm, "complete": True}), flush=True)
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
        raise RuntimeError("候选续打失败，保留原目标与支出，不重抽:" + str(failure))


async def main(indices):
    """每目标释放共同后台锁；不停止自由赛玩家，也不读取中途分数调式。"""
    os.nice(15)
    assert ctypes.CDLL(None).setiopolicy_np(0, 0, 3) == 0
    plan = json.loads((_project_file(_PROJECT_ROOT, HERE / "CANDIDATE-CAUSAL-PLAN.json")).read_text())
    assert plan["planned_single_hand_continuations"] <= plan["maximum_actual_single_hand_continuations"] == 108
    assert len(indices) == len(set(indices))
    with (_project_file(_PROJECT_ROOT, ROOT / ".private/t165-live-watchdog/postprocess.lock")).open("a+") as lock:
        for index in indices:
            assert 1 <= index <= len(plan["targets"]) and unchanged(plan)
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
