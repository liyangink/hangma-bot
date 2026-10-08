"""每桌完整八单局，父子同墙四换座；后台锁/低优先级，不抢自由赛owner。"""

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
import hashlib
import json
import os
import shutil
import time
from dataclasses import asdict
from pathlib import Path

from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.offline.evaluate import MatchDriverConfig, drive_match
from hangma_bot.offline.qualifier_opponents import build_qualifier_runtime
from hangma_bot.offline.scoring_input_capture import ScoringInputCapture, ScoringInputCaptureLimits
from hangma_bot.offline.vip_eoh_generate import VipEohBatch
from hangma_bot.offline.vip_route_development import VipDevelopmentAuditEngine, VipDevelopmentAuditPolicy
from hangma_bot.simulation import MatchSpec, SimulationChoice
from hangma_bot.simulation.shuffle import wall_for_round, deal_hands
from prepare_diagnostics import pin, save
from run_diagnostic_sources import canonical

HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT


class PairingAuditEngine(VipDevelopmentAuditEngine):
    """仅离线审计完整世界导出；策略仍只收到PlayerObservation。

    逐单局用生产洗牌器核实际起手和剩余牌墙，仅保存摘要。不同策略改变
    后续庄家时起手可以变化；相同来源同单局的洗牌物理顺序仍须一致。
    """
    def __init__(self, engine, *, settlement_sink):
        super().__init__(engine, settlement_sink=settlement_sink)
        self.pairing_proofs = []
        self.spec = None

    def start(self, spec):
        self.spec = spec
        return super().start(spec)

    def frame(self, world):
        frame = super().frame(world)
        for round_no in range(len(self.pairing_proofs) + 1, frame.completed_hands + 1):
            row = self.engine.export_hand(world, round_no)
            initial = row["initial"]
            shuffled = wall_for_round(self.spec.scenario_id, self.spec.seed, round_no)
            hands, drawn, wall = deal_hands(shuffled, initial["dealer_seat"])
            expected_hands = [[t.code for t in hand] for hand in hands]
            expected_hands[initial["dealer_seat"]].append(drawn.code)
            assert initial["hands"] == expected_hands and initial["drawn_tile"] == drawn.code
            assert initial["wall"] == [t.code for t in wall]
            assert initial["world_payload"]["scenario_id"] == self.spec.scenario_id
            assert initial["world_payload"]["seed"] == self.spec.seed
            self.pairing_proofs.append({"round_no": round_no, "dealer_seat": initial["dealer_seat"],
                "physical_wall_sha256": hashlib.sha256(canonical([t.code for t in shuffled])).hexdigest(),
                "actual_initial_sha256": hashlib.sha256(canonical({k: initial[k] for k in (
                    "hands", "drawn_tile", "wall", "dealer_seat")})).hexdigest(),
                "export_matches_frozen_sampler": True, "teacher_only_not_policy_input": True})
        return frame


def stable(plan):
    """冻源码/公式/组成/门禁到终态，不在开发中修改配方。"""
    return all(pin(Path(p)) == h for p, h in plan["files"].items()) and all(
        pin(_project_file(_PROJECT_ROOT, ROOT / p)) == h for p, h in plan["source_manifest"].items())


async def run_table(index, rotation, arm_index, plan):
    """完整桌为统计单位；每桌所有焦点调用录完整输入与候选分数，不正常回退。"""
    arms = [plan["parent"], *plan["candidates"]]
    arm = arms[arm_index]
    root = plan["roots"][index - 1]
    out = _project_file(_PROJECT_ROOT, HERE / "natural-development" / f"root-{index:03d}" / f"seat-{rotation}-arm-{arm_index}")
    out.mkdir(parents=True, exist_ok=False)
    assert shutil.disk_usage(ROOT).free >= plan["minimum_free_bytes"] and stable(plan)
    save(out / "START.json", {"root": root, "rotation": rotation, "arm": arm,
        "plan_pin": pin(_project_file(_PROJECT_ROOT, HERE / "DEVELOPMENT-PLAN.json")), "table_starts_reserved": 1,
        "logical_clock_not_official_deadline": True, "model_calls": 0})
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"))
    source = Path(arm["source_file"]).read_text()
    assert batch.identity(source) == arm["identity"]
    runtime = build_qualifier_runtime(batch, source, root["opponent_types_logical_1_2_3"])
    settlements, rows = [], []
    engine = PairingAuditEngine(runtime.engine, settlement_sink=settlements.append)
    raw = (out / "views.jsonl.gz").open("x+b")
    capture = ScoringInputCapture(raw, limits=ScoringInputCaptureLimits.from_json(plan["capture_limits"]))
    decisions = gzip.open(out / "focal-decisions.jsonl.gz", "xb")
    started = time.monotonic()
    failure, outcome, costs = None, None, None

    def record(row):
        """真实调用先计费再核验，失败也落盘；不拿最后成功掩盖此前失败。"""
        decisions.write(canonical(row) + b"\n")
        decisions.flush()
        rows.append(row)
        assert time.monotonic() - started < plan["wall_seconds_per_table"]
        assert row["status"] == "chosen" and row["c_self_scored"] and not row["degraded_reasons"]
        assert len(row["scoring_calls"]) == 1 and row["scoring_calls"][0]["full_legal_keys"]

    try:
        focal = VipDevelopmentAuditPolicy(runtime.policies_by_id[runtime.challenger_policy_id],
            runtime.challenger_policy_id, lambda: {"root_id": root["root_id"], "rotation": rotation,
                "arm": arm_index, "source_identity": arm["identity"]["candidate_id"], "focal_vip": True},
            record, challenger=True, capture=capture)
        policies = [None] * 4
        opponent_ids = [None] * 4
        policies[rotation] = focal
        for logical in range(1, 4):
            policy_id = runtime.declarations[f"Q{logical}"].policy_id
            physical = (logical + rotation) % 4
            policies[physical] = runtime.policies_by_id[policy_id]
            opponent_ids[physical] = policy_id
        save(out / "PAIRING-IDENTITY.json", {"root": root, "rotation": rotation, "arm": arm,
            "opponent_policy_ids_physical": opponent_ids,
            "evidence": "本次运行实际从policies_by_id选取并传入drive_match的映射；焦点席位为None"})
        spec = MatchSpec("t182-development:" + root["root_id"], root["root_id"], runtime.config,
                         root["seed"], 0, (0, 0, 0, 0))
        outcome = await drive_match(engine=engine, spec=spec, policies_by_seat=tuple(policies),
            rules=runtime.rules, choice_factory=SimulationChoice,
            config=MatchDriverConfig("logical", plan["step_limit"], BudgetPolicy(), "t182-development", True, batch.route_limits),
            now_monotonic=lambda: 800.0, wall_clock=None, value_limits=batch.route_limits)
        assert outcome.status == "complete" and outcome.completed_hands == 8
        assert all(v == 0 for v in asdict(outcome.runtime_counts).values()) and len(settlements) == 8
        assert len(engine.pairing_proofs) == 8
        assert all(s["evidence"] == "public_export_hand_settlement" for s in settlements)
        assert sum(s["settlement"]["score_delta"][rotation] for s in settlements) == outcome.final_scores[rotation]
    except BaseException as error:
        failure = {"type": type(error).__name__, "message": str(error)}
    finally:
        decisions.close()
        try:
            costs = capture.finish()
        except BaseException as error:
            failure = failure or {"type": type(error).__name__, "message": str(error)}
        raw.close()
        complete = failure is None and stable(plan) and costs is not None and costs["terminal"]["terminal_valid"]
        save(out / "CLOSURE.json", {"complete": complete, "failure": failure, "source_stable": stable(plan),
            "root": root, "rotation": rotation, "arm": arm, "focal_seat": rotation,
            "outcome": None if outcome is None else outcome.to_json(), "settlements": settlements,
            "actual_table_starts": engine.started_table_instances, "actual_focal_decisions": len(rows),
            "actual_focal_score_calls": sum(c["actual_score_calls"] for r in rows for c in r.get("scoring_calls", [])),
            "capture": costs, "normal_fallbacks_allowed": False, "model_calls": 0,
            "pairing_proofs": engine.pairing_proofs,
            "opponent_policy_ids_physical": opponent_ids if "opponent_ids" in locals() else None,
            "pairing_identity_pin": pin(out / "PAIRING-IDENTITY.json") if (out / "PAIRING-IDENTITY.json").exists() else None,
            "deadline_or_strength_admission": False, "elapsed_monotonic_seconds": time.monotonic() - started})
    print(json.dumps({"root": index, "rotation": rotation, "arm": arm_index,
                      "complete": complete, "error": failure}), flush=True)
    if not complete:
        raise RuntimeError("完整桌未通过，保留已花费和计划分母，不重抽:" + str(failure))


async def main(indices):
    """每完整桌释放统计锁，允许后台赛后任务；不看成绩作动态筛选。"""
    os.nice(15)
    assert ctypes.CDLL(None).setiopolicy_np(0, 0, 3) == 0
    plan = json.loads((_project_file(_PROJECT_ROOT, HERE / "DEVELOPMENT-PLAN.json")).read_text())
    assert plan["planned_table_instances"] <= 512 and len(set(indices)) == len(indices)
    with (_project_file(_PROJECT_ROOT, ROOT / ".private/t165-live-watchdog/postprocess.lock")).open("a+") as lock:
        for index in indices:
            assert 1 <= index <= 32 and stable(plan)
            for rotation in plan["rotations"]:
                for arm in range(1 + len(plan["candidates"])):
                    print(json.dumps({"root": index, "rotation": rotation, "arm": arm,
                                      "state": "waiting_postprocess_lock"}), flush=True)
                    fcntl.flock(lock, fcntl.LOCK_EX)
                    try:
                        await run_table(index, rotation, arm, plan)
                    finally:
                        fcntl.flock(lock, fcntl.LOCK_UN)
                    await asyncio.sleep(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--roots", type=int, nargs="+", required=True)
    asyncio.run(main(parser.parse_args().roots))
