"""T182 独立128来源确认；两个固定后台槽推进原桌，模拟不持共用统计锁。"""
from __future__ import annotations

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
import gzip
import json
import os
import shutil
import sys
import time
from dataclasses import asdict
from pathlib import Path

import close_development as dev
import run_development as runtime
import confirmation_resources as resources
from prepare_confirmation import PLAN, background_priority, new_json, postprocess_lock, read_confirmation_plan

HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT


async def run_table(index, rotation, arm_index, plan, plan_pin):
    """父子同seed的八单局真实推进；策略只消费观察，教师配对证明只存摘要。"""
    root, arm = plan["roots"][index - 1], [plan["parent"], *plan["candidates"]][arm_index]
    out = _project_file(_PROJECT_ROOT, HERE / "natural-confirmation" / f"root-{index:03d}" / f"seat-{rotation}-arm-{arm_index}")
    dev.require(not out.exists(), "原确认桌目录已存在，未知/失败/完成均不得重试覆盖")
    dev.require(dev.pin(PLAN) == plan_pin, "确认计划原字节漂移")
    dev.frozen(plan)
    dev.require(shutil.disk_usage(ROOT).free >= plan["minimum_free_bytes"], "确认启动前磁盘不足")
    out.mkdir(parents=True, exist_ok=False)
    new_json(out / "START.json", {"root": root, "rotation": rotation, "arm": arm,
        "plan_pin": plan_pin, "table_starts_reserved": 1, "model_calls": 0,
        "logical_clock_not_official_deadline": True, "confirmation_only": True})
    counts, settlements, rows = {"actual_table_starts": 0}, [], []
    failure, outcome, costs, capture, engine = None, None, None, None, None
    raw, decisions, opponent_ids = None, None, None
    started = time.monotonic()  # 研究持续秒；不是官方动作截止时间

    def record(row):
        """失败也先落盘计费；正常R18降级不能让确认原桌通过。"""
        decisions.write(runtime.canonical(row) + b"\n")
        decisions.flush()
        rows.append(row)
        dev.require(time.monotonic() - started < plan["wall_seconds_per_table"], "确认桌研究时间超额")
        dev.require(row["status"] == "chosen" and row["c_self_scored"] and not row["degraded_reasons"] and
                    len(row["scoring_calls"]) == 1 and row["scoring_calls"][0]["full_legal_keys"], "确认原评分不完整/降级")

    try:
        batch = runtime.VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"))
        source = Path(arm["source_file"]).read_text()
        dev.require(batch.identity(source) == arm["identity"], "确认实际公式身份不符")
        fresh = runtime.build_qualifier_runtime(batch, source, root["opponent_types_logical_1_2_3"])
        engine = runtime.PairingAuditEngine(fresh.engine, settlement_sink=settlements.append)
        raw = (out / "views.jsonl.gz").open("x+b")
        capture = runtime.ScoringInputCapture(raw, limits=runtime.ScoringInputCaptureLimits.from_json(plan["capture_limits"]))
        decisions = gzip.open(out / "focal-decisions.jsonl.gz", "xb")
        focal = runtime.VipDevelopmentAuditPolicy(fresh.policies_by_id[fresh.challenger_policy_id], fresh.challenger_policy_id,
            lambda: {"root_id": root["root_id"], "rotation": rotation, "arm": arm_index,
                     "source_identity": arm["identity"]["candidate_id"], "focal_vip": True, "confirmation_only": True},
            record, challenger=True, capture=capture)
        policies, opponent_ids = [None] * 4, [None] * 4
        policies[rotation] = focal
        for logical in range(1, 4):
            policy_id = fresh.declarations[f"Q{logical}"].policy_id
            physical = (logical + rotation) % 4
            policies[physical] = fresh.policies_by_id[policy_id]
            opponent_ids[physical] = policy_id
        new_json(out / "PAIRING-IDENTITY.json", {"root": root, "rotation": rotation, "arm": arm,
            "opponent_policy_ids_physical": opponent_ids,
            "evidence": "本次运行实际从policies_by_id选取并传入drive_match的映射；焦点席位为None"})
        spec = runtime.MatchSpec("t182-confirmation:" + root["root_id"], root["root_id"], fresh.config, root["seed"], 0, (0, 0, 0, 0))
        outcome = await runtime.drive_match(engine=engine, spec=spec, policies_by_seat=tuple(policies), rules=fresh.rules,
            choice_factory=runtime.SimulationChoice,
            config=runtime.MatchDriverConfig("logical", plan["step_limit"], runtime.BudgetPolicy(), "t182-confirmation", True, batch.route_limits),
            now_monotonic=lambda: 800.0, wall_clock=None, value_limits=batch.route_limits)
        dev.require(outcome.status == "complete" and outcome.completed_hands == 8 and len(settlements) == 8 and
                    len(engine.pairing_proofs) == 8 and all(type(v) is int and v == 0 for v in asdict(outcome.runtime_counts).values()),
                    "确认桌未完整八单局或故障计数非零")
        dev.require(all(s["evidence"] == "public_export_hand_settlement" for s in settlements) and
                    sum(s["settlement"]["score_delta"][rotation] for s in settlements) == outcome.final_scores[rotation],
                    "确认结算证据或积分对账失败")
    except BaseException as error:
        failure = {"type": type(error).__name__, "message": str(error)}
    finally:
        # 关闭的第二错误不得抹去原失败；已有真实行与费用不删、不补跑。
        if decisions is not None:
            try:
                decisions.close()
            except BaseException as error:
                failure = failure or {"type": type(error).__name__, "message": str(error)}
        if capture is not None:
            try:
                costs = capture.finish()
            except BaseException as error:
                failure = failure or {"type": type(error).__name__, "message": str(error)}
        if raw is not None:
            try:
                raw.close()
            except BaseException as error:
                failure = failure or {"type": type(error).__name__, "message": str(error)}
        stable = False
        try:
            dev.frozen(plan)
            stable = dev.pin(PLAN) == plan_pin
        except BaseException as error:
            failure = failure or {"type": type(error).__name__, "message": str(error)}
        counts["actual_table_starts"] = 0 if engine is None else engine.started_table_instances
        complete = failure is None and stable and costs is not None and costs["terminal"]["terminal_valid"]
        pairing_path = out / "PAIRING-IDENTITY.json"
        new_json(out / "CLOSURE.json", {"complete": complete, "failure": failure, "source_stable": stable,
            "root": root, "rotation": rotation, "arm": arm, "focal_seat": rotation, "plan_pin": plan_pin,
            "outcome": None if outcome is None else outcome.to_json(), "settlements": settlements,
            **counts, "actual_focal_decisions": len(rows),
            "actual_focal_score_calls": sum(c["actual_score_calls"] for r in rows for c in r.get("scoring_calls", [])),
            "capture": costs, "normal_fallbacks_allowed": False, "model_calls": 0,
            "pairing_proofs": [] if engine is None else engine.pairing_proofs,
            "opponent_policy_ids_physical": opponent_ids,
            "pairing_identity_pin": dev.pin(pairing_path) if pairing_path.exists() else None,
            "confirmation_only": True, "deadline_or_strength_admission": False,
            "elapsed_monotonic_seconds": time.monotonic() - started})
    print(json.dumps({"root": index, "rotation": rotation, "arm": arm_index, "complete": complete,
                      "failure": failure}, ensure_ascii=False), flush=True)
    if not complete:
        raise RuntimeError("原确认桌失败/未知，保留原分母和费用，禁止重试:" + str(failure))


async def run_one(task, plan, plan_pin):
    """新资源收据夹住原确认run_table恰一次；失败费用保留，不调用另一槽。"""
    dev.frozen(plan)
    dev.require(dev.pin(PLAN) == plan_pin and not resources.table_directory(task).exists(),
                "原确认计划漂移或桌目录已有，禁止重试")
    directory = resources.task_directory(task)
    directory.mkdir(parents=True, exist_ok=False)
    identity = resources.identity(plan, plan_pin, task["worker"], task)
    new_json(directory / "BEFORE.json", {"schema": "t182-confirmation-resource-task-before/1", **identity,
        "pid": os.getpid(), "unix_seconds": time.time(), "original_directory_absent": True,
        "original_run_table_called": False, "score_based_selection": False})
    before_pin = dev.pin(directory / "BEFORE.json")
    called, complete, stable, failure, files, pin_errors = False, False, False, None, {}, {}
    started = time.monotonic()
    try:
        dev.require(not resources.table_directory(task).exists(), "调用前原确认桌目录出现，禁止重试")
        called = True
        await run_table(task["index"], task["rotation"], task["arm_index"], plan, plan_pin)
        files = {str(resources.table_directory(task) / name): dev.pin(resources.table_directory(task) / name)
                 for name in resources.TABLE_FILES}
        dev.frozen(plan)
        dev.require(dev.pin(PLAN) == plan_pin and dev.pin(directory / "BEFORE.json") == before_pin,
                    "确认任务期间原计划／前收据漂移")
        complete, stable = True, True
    except BaseException as error:
        failure = {"type": type(error).__name__, "message": str(error)}
    finally:
        if not complete:
            # 单件不可读不能抹掉其余可读原件的费用关联；文件原文仍全部保留。
            for name in resources.TABLE_FILES:
                path = resources.table_directory(task) / name
                try:
                    if path.is_file():
                        files[str(path)] = dev.pin(path)
                except BaseException as error:
                    pin_errors[str(path)] = {"type": type(error).__name__, "message": str(error)}
            try:
                dev.frozen(plan)
                stable = dev.pin(PLAN) == plan_pin and dev.pin(directory / "BEFORE.json") == before_pin
            except BaseException as error:
                stable = False
                failure = failure or {"type": type(error).__name__, "message": str(error)}
        new_json(directory / "AFTER.json", {"schema": "t182-confirmation-resource-task-after/1", **identity,
            "pid": os.getpid(), "unix_seconds": time.time(), "before_pin": before_pin,
            "original_run_table_called": called, "complete": complete, "failure": failure,
            "source_stable": stable, "original_table_files": files, "pin_errors": pin_errors,
            "elapsed_monotonic_seconds": time.monotonic() - started,
            "other_worker_interrupted": False, "normal_fallbacks_allowed": False,
            "deadline_admission": False, "release_admission": False})
    print(json.dumps({"worker": task["worker"], "ordinal": task["ordinal"], "complete": complete,
                      "failure": failure}, ensure_ascii=False), flush=True)
    if not complete:
        raise RuntimeError("该确认槽停止；原费用和收据保留，禁止重试:" + str(failure))
    return {str(directory / name): dev.pin(directory / name) for name in ("BEFORE.json", "AFTER.json")}


async def main(worker):
    """固定奇偶槽、nice>=15/后台IO；槽独占全过程，模拟无共用锁、不读中途积分。"""
    dev.require(type(worker) is int and worker in (0, 1), "只允许预登记确认worker0或1")
    background_priority()
    with resources.research_lock(worker):
        with postprocess_lock("confirmation_input_verification"):
            plan, plan_pin = read_confirmation_plan(verify_development_evidence=True)
        assigned = [t["ordinal"] for t in plan["resource_tasks"] if t["worker"] == worker]
        directory = resources.EVIDENCE / f"worker-{worker}"
        directory.mkdir(parents=True, exist_ok=False)
        identity = resources.identity(plan, plan_pin, worker)
        new_json(directory / "START.json", {"schema": "t182-confirmation-resource-worker-start/1", **identity,
            "pid": os.getpid(), "unix_seconds": time.time(), "assigned_ordinals": assigned,
            "max_cpu_workers": 2, "nice": os.getpriority(os.PRIO_PROCESS, 0), "macos_background_io": True,
            "common_postprocess_lock_held": False, "original_function": "run_confirmation.run_table",
            "normal_fallbacks_allowed": False, "score_based_selection": False})
        start_pin = dev.pin(directory / "START.json")
        attempted, completed, receipts, failure, stable = [], [], {}, None, False
        started = time.monotonic()
        try:
            for ordinal in assigned:
                attempted.append(ordinal)
                receipts.update(await run_one(plan["resource_tasks"][ordinal], plan, plan_pin))
                completed.append(ordinal)
                await asyncio.sleep(1)
            dev.frozen(plan)
            dev.require(dev.pin(PLAN) == plan_pin and dev.pin(directory / "START.json") == start_pin,
                        "确认worker终态计划／START漂移")
            resources.verify_files(receipts)
            stable = True
        except BaseException as error:
            failure = {"type": type(error).__name__, "message": str(error)}
            if attempted:
                failed = resources.task_directory(plan["resource_tasks"][attempted[-1]])
                for name in ("BEFORE.json", "AFTER.json"):
                    path = failed / name
                    if path.is_file():
                        try:
                            receipts[str(path)] = dev.pin(path)
                        except BaseException as secondary:
                            failure["receipt_pin_error"] = type(secondary).__name__ + ": " + str(secondary)
        finally:
            calls, unknown = 0, []
            for ordinal in attempted:
                try:
                    after, _ = dev.read(resources.task_directory(plan["resource_tasks"][ordinal]) / "AFTER.json")
                    called = after.get("original_run_table_called")
                    dev.require(type(called) is bool, "确认原函数调用状态未知")
                    calls += int(called)
                except BaseException:
                    unknown.append(ordinal)
            if unknown:
                failure = failure or {"type": "UnknownCallReceipt", "message": "实际调用数未知，禁止闭合"}
            complete = failure is None and stable and completed == assigned
            new_json(directory / "CLOSE.json", {"schema": "t182-confirmation-resource-worker-close/1", **identity,
                "pid": os.getpid(), "unix_seconds": time.time(), "worker_start_pin": start_pin,
                "assigned_ordinals": assigned, "attempted_ordinals": attempted, "completed_ordinals": completed,
                "complete": complete, "failure": failure, "source_stable": stable,
                "task_receipt_files": receipts, "actual_original_run_table_calls": calls,
                "unknown_call_ordinals": unknown, "elapsed_monotonic_seconds": time.monotonic() - started,
                "other_worker_interrupted": False, "models_added_by_scheduler": 0,
                "normal_fallbacks_allowed": False, "deadline_admission": False, "release_admission": False})
        print(json.dumps({"worker": worker, "closed": complete, "completed": len(completed), "failure": failure},
                         ensure_ascii=False), flush=True)
        if not complete:
            raise RuntimeError("确认worker未知／失败；原分母保留，整批不得授完成:" + str(failure))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", choices=(0, 1), type=int, required=True)
    args = parser.parse_args()
    try:
        asyncio.run(main(args.worker))
    except (OSError, ValueError, KeyError, TypeError, IndexError, RuntimeError, AttributeError) as error:
        print(json.dumps({"complete": False, "status": "unknown_or_failed_original_cost_retained",
                          "error_type": type(error).__name__, "reason": str(error)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
