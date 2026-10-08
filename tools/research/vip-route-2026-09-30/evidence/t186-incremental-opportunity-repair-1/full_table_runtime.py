"""T186开发原桌；复用已核八单局推进，所有焦点评分完整录制。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t186-incremental-opportunity-repair-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import gzip
import json
import shutil
import time
from dataclasses import asdict
from pathlib import Path
from common import ROOT, save as new_json
HERE = Path(__file__).resolve().parent
import t185_close_development as dev
import t185_run_development as runtime


async def run_table(index, rotation, arm_index, plan, plan_pin):
    """父子同seed的八单局真实推进；策略只消费观察，教师配对证明只存摘要。"""
    root, arm = plan["roots"][index - 1], [plan["parent"], *plan["candidates"]][arm_index]
    out = Path(plan["output_directory"]) / f"root-{index:03d}" / f"seat-{rotation}-arm-{arm_index}"
    dev.require(not out.exists(), "原开发桌目录已存在，未知/失败/完成均不得重试覆盖")
    dev.require(dev.pin(Path(plan["plan_path"])) == plan_pin, "开发计划原字节漂移")
    dev.frozen(plan)
    dev.require(shutil.disk_usage(ROOT).free >= plan["minimum_free_bytes"], "开发启动前磁盘不足")
    out.mkdir(parents=True, exist_ok=False)
    new_json(out / "START.json", {"root": root, "rotation": rotation, "arm": arm,
        "plan_pin": plan_pin, "table_starts_reserved": 1, "model_calls": 0,
        "logical_clock_not_official_deadline": True, "development_only": True})
    counts, settlements, rows = {"actual_table_starts": 0}, [], []
    failure, outcome, costs, capture, engine = None, None, None, None, None
    raw, decisions, opponent_ids = None, None, None
    started = time.monotonic()  # 研究持续秒；不是官方动作截止时间

    def record(row):
        """失败也先落盘计费；正常R18降级不能让开发原桌通过。"""
        decisions.write(runtime.canonical(row) + b"\n")
        decisions.flush()
        rows.append(row)
        dev.require(time.monotonic() - started < plan["wall_seconds_per_table"], "开发桌研究时间超额")
        dev.require(row["status"] == "chosen" and row["c_self_scored"] and not row["degraded_reasons"] and
                    len(row["scoring_calls"]) == 1 and row["scoring_calls"][0]["full_legal_keys"], "开发原评分不完整/降级")

    try:
        batch = runtime.VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"))
        source = Path(arm["source_file"]).read_text()
        dev.require(batch.identity(source) == arm["identity"], "开发实际公式身份不符")
        fresh = runtime.build_qualifier_runtime(batch, source, root["opponent_types_logical_1_2_3"])
        engine = runtime.PairingAuditEngine(fresh.engine, settlement_sink=settlements.append, focal_seat=rotation)
        raw = (out / "views.jsonl.gz").open("x+b")
        capture = runtime.ScoringInputCapture(raw, limits=runtime.ScoringInputCaptureLimits.from_json(plan["capture_limits"]))
        decisions = gzip.open(out / "focal-decisions.jsonl.gz", "xb")
        focal = runtime.VipDevelopmentAuditPolicy(fresh.policies_by_id[fresh.challenger_policy_id], fresh.challenger_policy_id,
            lambda: {"root_id": root["root_id"], "rotation": rotation, "arm": arm_index,
                     "source_identity": arm["identity"]["candidate_id"], "focal_vip": True, "development_only": True},
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
        spec = runtime.MatchSpec("t186-development:" + root["root_id"], root["root_id"], fresh.config, root["seed"], 0, (0, 0, 0, 0))
        outcome = await runtime.drive_match(engine=engine, spec=spec, policies_by_seat=tuple(policies), rules=fresh.rules,
            choice_factory=runtime.SimulationChoice,
            config=runtime.MatchDriverConfig("logical", plan["step_limit"], runtime.BudgetPolicy(), "t186-development", True, batch.route_limits),
            now_monotonic=lambda: 800.0, wall_clock=None, value_limits=batch.route_limits)
        dev.require(outcome.status == "complete" and outcome.completed_hands == 8 and len(settlements) == 8 and
                    len(engine.pairing_proofs) == 8 and all(type(v) is int and v == 0 for v in asdict(outcome.runtime_counts).values()),
                    "开发桌未完整八单局或故障计数非零")
        dev.require(all(s["evidence"] == "public_export_hand_settlement" for s in settlements) and
                    sum(s["settlement"]["score_delta"][rotation] for s in settlements) == outcome.final_scores[rotation],
                    "开发结算证据或积分对账失败")
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
            stable = dev.pin(Path(plan["plan_path"])) == plan_pin
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
            "development_only": True, "deadline_or_strength_admission": False,
            "elapsed_monotonic_seconds": time.monotonic() - started})
    print(json.dumps({"root": index, "rotation": rotation, "arm": arm_index, "complete": complete,
                      "failure": failure}, ensure_ascii=False), flush=True)
    if not complete:
        raise RuntimeError("原开发桌失败/未知，保留原分母和费用，禁止重试:" + str(failure))
