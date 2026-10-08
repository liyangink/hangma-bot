"""从八个预登记新来源采样机会；全桌严格续打，不按成功/积分删题。"""

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
from pathlib import Path
import sys
import time
from dataclasses import asdict

from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.kernel.serialization import observation_to_json, window_key_to_json
from hangma_bot.offline.evaluate import MatchDriverConfig, drive_match
from hangma_bot.offline.qualifier_opponents import build_qualifier_runtime
from hangma_bot.offline.scoring_input_capture import ScoringInputCapture, ScoringInputCaptureLimits
from hangma_bot.offline.vip_eoh_generate import VipEohBatch
from hangma_bot.offline.vip_route_development import VipDevelopmentAuditEngine
from hangma_bot.simulation import MatchSpec, SimulationChoice

HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT


def canonical(value):
    """有限JSON；保持未知、合法根和完整候选分数。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode()


def pin(path):
    """只读小源码/计划；不全扫线上审计。"""
    raw = Path(path).read_bytes()
    return {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def save(path, value):
    """本来源收据独占创建；运行进度另用追加日志，不覆盖失败。"""
    with Path(path).open("xb") as stream:
        stream.write(canonical(value) + b"\n")


class ScoreTap:
    """透传同一typed view；只有已事前选中的窗保存整图，原评分仍逐根核齐。"""

    def __init__(self, executor, capture):
        self.inner, self.capture = executor, capture
        self.selected = False
        self.last = None
        self.calls = 0
        self.failures = 0

    @property
    def last_operation_count(self):
        return self.inner.last_operation_count

    @last_operation_count.setter
    def last_operation_count(self, value):
        self.inner.last_operation_count = value

    def score_vip_route(self, view):
        """图记录先于实际评分；不截断合法根、补造分数或隐藏弃权。"""
        row = {"score_attempted": False, "complete": False, "capture": None}
        self.last = row
        try:
            keys = {a.action_key for a in view.actions}
            if self.selected:
                receipt = self.capture.store(view.candidate_view())
                row["capture"] = asdict(receipt)
                if not receipt.saved_before_score:
                    raise ValueError("选中整图录制失败:" + str(receipt.error))
            self.calls += 1
            row["score_attempted"] = True
            scored = self.inner.score_vip_route(view)
            entries = [dict(action_key=e.action_key, score=e.score, trace=dict(e.trace))
                       for e in scored.entries]
            assert scored.status == "SCORED"
            assert len(entries) == len(keys) and {e["action_key"] for e in entries} == keys
            row.update(complete=True, entries=entries, operations=self.last_operation_count)
            return scored
        except BaseException as error:
            self.failures += 1
            row["error"] = type(error).__name__ + ": " + str(error)
            raise


class PanelPolicy:
    """只按行动前公开机会选窗；对所有窗口仍调用固定父代。"""

    def __init__(self, inner, capture, stream, root_id):
        self.inner, self.stream, self.root_id = inner, stream, root_id
        self.tap = ScoreTap(inner.executor, capture)
        inner.executor = self.tap
        self.seen = set()
        self.draws_by_hand = {}
        self.rows = 0
        self.selected_rows = []
        self.started = time.monotonic()

    async def choose(self, request, budget):
        """保存依法可见观察和计划；失败仍入分母，整个来源停止而不回退。"""
        obs = request.observation
        own = list(obs.my_hand)
        size = 13 - 3 * len(obs.melds[obs.seat])
        if len(own) == size and obs.drawn_tile is not None:
            own.append(obs.drawn_tile)
        whites = sum(t.code == "白" for t in own)
        keys = [c.action_key for c in request.rules.legal_candidates]
        draw = obs.phase == "draw" and obs.turn_seat == obs.seat
        number = self.draws_by_hand.get(obs.round_no, 0) + int(draw)
        self.draws_by_hand[obs.round_no] = number
        tags = []
        if draw and number <= 3:
            tags.append("early_no_white" if whites == 0 else
                        "early_one_white" if whites == 1 else "early_multi_white")
        if "hu" in keys:
            tags.append("current_hu")
        if any(k.startswith(("chi:", "peng:")) for k in keys):
            tags.append("claim_option")
        if any(k.startswith("gang:") for k in keys):
            tags.append("gang_option")
        if draw and obs.remaining_tile_count is not None and obs.remaining_tile_count <= 40:
            tags.append("late_draw")
        if draw and number >= 4:
            tags.append("later_draw")
        new_tags = [tag for tag in tags if tag not in self.seen]
        selected = bool(new_tags)
        self.seen.update(new_tags)
        self.tap.selected, self.tap.last = selected, None
        row = {"root_id": self.root_id, "window_key": window_key_to_json(request.window_key),
            "decision_id": request.decision_id, "observation": observation_to_json(obs),
            "legal_action_keys": keys, "rules_completeness": request.rules.completeness.value,
            "rules_issues": [asdict(issue) for issue in request.rules.issues],
            "classes": tags, "new_selected_classes": new_tags, "selected_before_choice": selected,
            "white_count_current": whites, "own_draw_ordinal": number,
            "status": "unfinished"}
        started = time.monotonic()
        try:
            if started - self.started > 600:
                raise TimeoutError("来源墙钟预算耗尽")
            plan = await self.inner.choose(request, budget)
            assert self.tap.last is not None and self.tap.last["complete"]
            assert {c.action_key for c in plan.candidates} == set(keys)
            assert not plan.degraded_reasons
            row.update(status="complete", selected_action=plan.candidates[0].action_key,
                       scores=self.tap.last["entries"], scoring=self.tap.last)
            return plan
        except BaseException as error:
            row.update(status="failed", error=type(error).__name__ + ": " + str(error),
                       scoring=self.tap.last)
            raise
        finally:
            row["policy_monotonic_seconds"] = time.monotonic() - started
            self.rows += 1
            self.stream.write(canonical(row) + b"\n")
            self.stream.flush()
            if selected:
                self.selected_rows.append(row)
                print(json.dumps({"root": self.root_id, "selected": len(self.selected_rows),
                                  "classes": new_tags, "status": row["status"]}), flush=True)


def stable(plan):
    """启动与终态逐字核当前源码、公式、计划，不继承历史成绩。"""
    return (all(pin(_project_file(_PROJECT_ROOT, ROOT / p)) == h for p, h in plan["frozen_files"].items())
            and all(pin(_project_file(_PROJECT_ROOT, ROOT / p)) == h for p, h in plan["source_manifest"].items()))


async def run_root(index, plan):
    """一个新牌山完整八单局；只采一次、不按结果重抽、不重跑已开始来源。"""
    composition = plan["roots"][index - 1]
    out = _project_file(_PROJECT_ROOT, HERE / "diagnostic-sources" / f"root-{index:03d}")
    out.mkdir(parents=True, exist_ok=False)
    save(out / "START.json", {"root": composition, "source_manifest": plan["source_manifest"],
         "baseline_identity": plan["baseline_identity"], "plan_pin": pin(_project_file(_PROJECT_ROOT, HERE / "DIAGNOSTIC-PLAN.json")),
         "planned_tables": 1, "planned_hands": 8, "selection_before_choice": True,
         "old_results_transferred": False, "model_calls": 0})
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "DIAGNOSTIC-EXECUTION-BATCH.json"))
    source = (_project_file(_PROJECT_ROOT, HERE / "parent-source.py")).read_text()
    assert batch.identity(source) == plan["baseline_identity"] and stable(plan)
    runtime = build_qualifier_runtime(batch, source, composition["opponent_types_logical_1_2_3"])
    settlements = []
    engine = VipDevelopmentAuditEngine(runtime.engine, settlement_sink=settlements.append)
    started = time.monotonic()
    costs = None
    outcome = None
    error = None
    policy = None
    stream = (out / "views.jsonl.gz").open("x+b")
    capture = ScoringInputCapture(stream, limits=ScoringInputCaptureLimits.from_json(plan["capture_limits"]))
    try:
        with gzip.open(out / "decisions.jsonl.gz", "xb") as decisions:
            policy = PanelPolicy(runtime.policies_by_id[runtime.challenger_policy_id],
                                 capture, decisions, composition["root_id"])
            opponents = tuple(runtime.policies_by_id[runtime.declarations[f"Q{i}"].policy_id]
                              for i in range(1, 4))
            spec = MatchSpec("t182-diagnostic:" + composition["root_id"], composition["root_id"],
                             runtime.config, composition["seed"], 0, (0, 0, 0, 0))
            config = MatchDriverConfig("logical", plan["step_limit_per_table"], BudgetPolicy(),
                                       "t182-diagnostic", strict_policy=True, route_limits=batch.route_limits)
            outcome = await drive_match(engine=engine, spec=spec, policies_by_seat=(policy, *opponents),
                rules=runtime.rules, choice_factory=SimulationChoice, config=config,
                now_monotonic=lambda: 800.0, wall_clock=None, value_limits=batch.route_limits)
            assert outcome.status == "complete" and outcome.completed_hands == 8
            assert all(value == 0 for value in asdict(outcome.runtime_counts).values())
            assert not any("action_value_failed" in reason for d in outcome.decisions
                           for reason in d.degraded_reasons)
            assert len(settlements) == 8
    except BaseException as exc:
        error = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        try:
            costs = capture.finish()
        except BaseException as exc:
            error = error or {"type": type(exc).__name__, "message": str(exc)}
        stream.close()
        complete = (error is None and stable(plan) and costs is not None
                    and costs["terminal"]["terminal_valid"])
        save(out / "CLOSURE.json", {"complete": complete, "error": error,
            "outcome": None if outcome is None else outcome.to_json(),
            "settlements": settlements, "selected_windows": [] if policy is None else policy.selected_rows,
            "actual_table_starts": engine.started_table_instances, "capture": costs,
            "actual_score_calls": 0 if policy is None else policy.tap.calls,
            "score_failures": 0 if policy is None else policy.tap.failures,
            "focal_decisions": 0 if policy is None else policy.rows,
            "elapsed_monotonic_seconds": time.monotonic() - started,
            "source_stable": stable(plan), "normal_fallbacks_allowed": False,
            "deadline_admission": False, "strength_admission": False, "model_calls": 0})
    print(json.dumps({"root": index, "complete": complete, "error": error,
                      "elapsed_seconds": round(time.monotonic() - started, 2)}), flush=True)
    if not complete:
        raise RuntimeError("新来源未完整，保留原分母并停止：" + str(error))


async def main(indices):
    """单个低优先级进程；每来源持公共锁，等待不终止玩家或赛后进程。"""
    os.nice(15)
    libc = ctypes.CDLL(None, use_errno=True)
    assert libc.setiopolicy_np(0, 0, 3) == 0
    plan = json.loads((_project_file(_PROJECT_ROOT, HERE / "DIAGNOSTIC-PLAN.json")).read_text())
    assert stable(plan)
    for index in indices:
        assert 1 <= index <= 8
        out = _project_file(_PROJECT_ROOT, HERE / "diagnostic-sources" / f"root-{index:03d}")
        if out.exists():
            raise FileExistsError("不得重复已开始来源：" + str(out))
        print(json.dumps({"root": index, "state": "waiting_for_postprocess_lock",
                          "pid": os.getpid()}), flush=True)
        with (_project_file(_PROJECT_ROOT, ROOT / ".private/t165-live-watchdog/postprocess.lock")).open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            await run_root(index, plan)
        # 主动放锁；后台统计可在下一来源之前获得，不改变已开玩家生命周期。
        await asyncio.sleep(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roots", type=int, nargs="+", required=True)
    asyncio.run(main(parser.parse_args().roots))
