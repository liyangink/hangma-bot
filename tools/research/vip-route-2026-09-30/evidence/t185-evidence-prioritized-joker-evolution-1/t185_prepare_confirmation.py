"""T185确认准备与资源证据：开发完整闭合后才选唯一候选，不提前生成确认牌山。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import ctypes
import fcntl
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path

from common import HERE, ROOT, pin, save as new_json
import t185_close_development as dev

PLAN = _project_file(_PROJECT_ROOT, HERE / "CONFIRMATION-PLAN.json")
CONTRACT = _project_file(_PROJECT_ROOT, HERE / "CONFIRMATION-READOUT-CONTRACT.md")
frozen = dev.frozen


def background_priority():
    """确认CPU降至nice15、磁盘置后台；与线上计算隔离，不操作比赛进程。"""
    dev.require(sys.platform == "darwin", "确认使用冻结的macOS后台IO配置")
    priority = os.getpriority(os.PRIO_PROCESS, 0)
    if priority < 15:
        os.nice(15 - priority)
    dev.require(ctypes.CDLL(None).setiopolicy_np(0, 0, 3) == 0, "后台IO设置失败")


@contextmanager
def postprocess_lock(label):
    """只在统一验证和读回阶段持共同赛后锁；模拟本身不持有。"""
    with (_project_file(_PROJECT_ROOT, ROOT / ".private/t165-live-watchdog/postprocess.lock")).open("a+") as lock:
        print(json.dumps({"waiting_postprocess_lock": label, "scores_read": False}), flush=True)
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def require_development_dispatch():
    """开发统计落盘不足以启动确认，还须两个真实槽自然退出与资源终态齐全。"""
    directory = _project_file(_PROJECT_ROOT, HERE / "development-dispatch")
    terminal, terminal_pin = dev.read(directory / "CLOSED.json")
    workers, workers_pin = dev.read(directory / "WORKERS-CLOSED.json")
    dev.require(terminal.get("complete") is True and terminal.get("resources_released") is True and
        terminal.get("worker_returncodes") == [0, 0] and terminal.get("readout_exit_code") == 0 and
        terminal.get("workers_closed_pin") == workers_pin and
        terminal.get("development_closed_pin") == pin(_project_file(_PROJECT_ROOT, HERE / "DEVELOPMENT-CLOSED.json")) and
        terminal.get("plan_pin") == workers.get("plan_pin") == pin(_project_file(_PROJECT_ROOT, HERE / "DEVELOPMENT-PLAN.json")) and
        workers.get("complete") is True and workers.get("actual_table_calls") == 512 and
        workers.get("completed_ordinals") == list(range(512)) and workers.get("slots_released") == [0, 1],
        "开发资源未完全闭合或身份不同")
    dev.require(all(pin(Path(p)) == h for p, h in workers["files"].items()), "开发worker原收据漂移")
    return terminal_pin, {str(directory / "CLOSED.json"): terminal_pin,
        str(directory / "WORKERS-CLOSED.json"): workers_pin, **workers["files"]}


def selected_from_development(closure, plan):
    """原32来源四座净差和正、至少两正来源；最高净差及candidate_id决胜，禁止临时挑选。"""
    dev.require(closure.get("schema") == "t185-natural-development-closed/1" and closure.get("complete") is True and
        closure.get("source_stable") is True and closure.get("actual_table_instances") == 512 and
        closure.get("planned_table_instances") == 512 and closure.get("completed_hand_instances") == 4096 and
        closure.get("parent_identity") == plan["parent"]["identity"], "开发全批或身份无效")
    rows = closure["candidates"]
    expected = {c["identity"]["candidate_id"]: c for c in plan["candidates"]}
    dev.require(len(rows) == len(expected) and {r["candidate_id"] for r in rows} == set(expected), "开发候选缺失或重复")
    eligible = []
    for row in rows:
        dev.require(row["identity"] == expected[row["candidate_id"]]["identity"] and len(row["sources"]) == 32,
            "开发候选身份或来源分母不同")
        totals, positive = [], []
        for source, root in zip(row["sources"], plan["roots"]):
            dev.require(source["root_id"] == root["root_id"] and source["seed"] == root["seed"], "来源顺序或seed漂移")
            pairs = source["paired_tables"]
            dev.require([p["rotation"] for p in pairs] == [0, 1, 2, 3], "缺四换座")
            value = dev.integer(source["four_seat_delta_sums"]["net"], "来源净差")
            dev.require(value == sum(dev.integer(p["delta"]["net"], "桌净差") for p in pairs), "来源差与四桌不对账")
            totals.append(value)
            if value > 0:
                positive.append(root["root_id"])
        total = sum(totals)
        passes = total > 0 and len(positive) >= 2
        dev.require(row["net_delta_sum_128_tables"] == total and row["mean_delta"]["net"] == total / 128 and
            row["positive_sources"] == positive and row["development_selection_eligible"] is passes,
            "原开发选择算术不一致")
        if passes:
            eligible.append((total, row["candidate_id"]))
    eligible.sort(key=lambda r: (-r[0], r[1]))
    selected = None if not eligible else eligible[0][1]
    dev.require(selected == closure["selected_candidate_id_for_confirmation_preparation"], "原选择不符合冻结排序")
    dev.require(selected is not None, "本批未选出候选，禁止启动独立确认")
    return expected[selected]


def validate_plan(plan):
    """确认全部128未读来源、唯一公式及冻结框架；不生成世界或读取中途分。"""
    dev.require(plan.get("schema") == "t185-natural-confirmation/1" and plan.get("rotations") == [0, 1, 2, 3] and
        plan.get("rounds") == 8 and plan.get("planned_table_instances") == 1024 and
        plan.get("maximum_new_complete_table_instances") == 1024 and len(plan.get("candidates", [])) == 1,
        "确认规模或schema错误")
    comps, _ = dev.read(_project_file(_PROJECT_ROOT, HERE / "FROZEN-OPPONENT-COMPOSITIONS.json"))
    roots = plan["roots"]
    dev.require(roots == comps["pools"]["confirmation"] and len(roots) == 128 and
        len({r["root_id"] for r in roots}) == len({r["seed"] for r in roots}) == 128, "确认不是事前全部128来源")
    for pool in ("development", "diagnostic_fresh"):
        dev.require(not {r["seed"] for r in roots} & {r["seed"] for r in comps["pools"][pool]}, "确认来源交叉")
    child, parent = plan["candidates"][0], plan["parent"]
    dev.require(plan["selected_candidate_id"] == child["identity"]["candidate_id"] and
        parent["identity"]["source_sha256"] == dev.PARENT_SHA and
        parent["identity"]["params"] == child["identity"]["params"] and
        parent["identity"]["params"]["max_operations"] == 4800000 and
        parent["identity"]["params"]["projection_limits"]["max_replacement_depth"] == 1 and
        parent["identity"]["candidate_id"] != child["identity"]["candidate_id"], "确认框架或公式身份错误")
    dev.require(plan["bootstrap"] == {"seed": 20261005, "replicates": 20000, "sources": 128,
        "interval": "percentile_linear_0.025_0.975"} and plan["minimum_mean_points_per_complete_table"] == 0.5 and
        plan["no_early_score_peeking_or_additional_roots"] is True and plan["normal_fallbacks_allowed"] is False and
        plan["wall_seconds_per_table"] == 600, "确认事前判据漂移")
    dev.require(plan["initial_dealer_physical"] == 0 and plan["initial_scores_0_1_2_3"] == [0, 0, 0, 0], "确认初庄或积分错误")
    for name in ("t185_prepare_confirmation.py", "t185_run_confirmation.py", "t185_close_confirmation.py",
        "run_confirmation_workers.py", "dispatch_confirmation.py", "CONFIRMATION-READOUT-CONTRACT.md",
        "CONFIRMATION-TOOLS-CHECKED.json", "DEVELOPMENT-CLOSED.json", "DEVELOPMENT-PLAN.json"):
        dev.require(str(_project_file(_PROJECT_ROOT, HERE / name)) in plan["files"], "确认未冻结关键文件:" + name)
    for arm in (parent, child):
        dev.require(pin(Path(arm["source_file"]))["sha256"] == arm["identity"]["source_sha256"], "实际公式字节不同")


def read_confirmation_plan(*, verify_development_evidence=False):
    """逐桌核小型版本清单；统一IO阶段才重复核完整开发大原件。"""
    plan, plan_pin = dev.read(PLAN)
    validate_plan(plan)
    frozen(plan)
    terminal, terminal_pin = dev.read(_project_file(_PROJECT_ROOT, HERE / "development-dispatch/CLOSED.json"))
    dev.require(terminal_pin == plan["development_dispatch_closed_pin"] and terminal["complete"], "开发资源终态漂移")
    if verify_development_evidence:
        for p, h in plan["development_evidence_files"].items():
            dev.require(pin(Path(p)) == h, "开发原件漂移:" + p)
    return plan, plan_pin


def confirmation_worker_evidence(plan, plan_pin):
    """全两槽1024次真实调用收据核齐后方可读分；有失败或缺件不给统计准入。"""
    files = {}
    for slot in (0, 1):
        directory = _project_file(_PROJECT_ROOT, HERE / "confirmation-workers" / f"worker-{slot}")
        start, start_pin = dev.read(directory / "START.json")
        end, end_pin = dev.read(directory / "CLOSE.json")
        expected = list(range(slot, 1024, 2))
        dev.require(start["plan_pin"] == end["plan_pin"] == plan_pin and start["pid"] == end["pid"] and
            start["nice"] >= 15 and start["background_io"] is True and not start["common_postprocess_lock_held"] and
            end["complete"] is True and end["failure"] is None and end["actual_table_calls"] == 512 and
            end["start_pin"] == start_pin and end["attempted_ordinals"] == end["completed_ordinals"] == expected,
            "确认worker分母、身份、资源或终态错误")
        files.update({str(directory / "START.json"): start_pin, str(directory / "CLOSE.json"): end_pin})
        for ordinal in expected:
            before_file = directory / f"task-{ordinal:04d}" / "BEFORE.json"
            after_file = before_file.with_name("AFTER.json")
            before, before_pin = dev.read(before_file)
            after, after_pin = dev.read(after_file)
            task = start["tasks"][ordinal // 2]
            dev.require(before["task"] == after["task"] == task and task["ordinal"] == ordinal and
                before["plan_pin"] == after["plan_pin"] == plan_pin and before["pid"] == after["pid"] == start["pid"] and
                not before["run_table_called"] and after["run_table_called"] and after["complete"] and
                after["failure"] is None and after["before_pin"] == before_pin, "确认原调用前后证据错误")
            required = {str(_project_file(_PROJECT_ROOT, HERE / "natural-confirmation" / f"root-{task['root']:03d}" /
                f"seat-{task['rotation']}-arm-{task['arm']}" / n))
                for n in ("START.json", "CLOSURE.json", "PAIRING-IDENTITY.json", "views.jsonl.gz", "focal-decisions.jsonl.gz")}
            dev.require(required <= set(after["table_files"]), "确认AFTER缺原桌文件")
            files.update(after["table_files"])
            files.update({str(before_file): before_pin, str(after_file): after_pin})
    return files


def main():
    """选中后排他冻结确认；准备仍为零评分、零世界、零完整桌。"""
    dev.require(not PLAN.exists(), "确认计划已存在，不覆盖")
    background_priority()
    with postprocess_lock("confirmation_preparation"):
        development, development_pin = dev.read(_project_file(_PROJECT_ROOT, HERE / "DEVELOPMENT-CLOSED.json"))
        development_plan, development_plan_pin = dev.read(_project_file(_PROJECT_ROOT, HERE / "DEVELOPMENT-PLAN.json"))
        dev.validate_plan(development_plan)
        dev.frozen(development_plan)
        selected = selected_from_development(development, development_plan)
        dispatch_pin, resource_files = require_development_dispatch()
        dependencies = {**development["files"], **resource_files}
        for p, h in dependencies.items():
            dev.require(pin(Path(p)) == h, "开发原证据漂移:" + p)
        checked, checked_pin = dev.read(_project_file(_PROJECT_ROOT, HERE / "CONFIRMATION-TOOLS-CHECKED.json"))
        dev.require(checked["complete"] and checked["synthetic_statistics_checked"] and checked["new_scores_worlds_tables"] == 0,
            "确认工具未实际验证")
        dev.require(all(pin(Path(p)) == h for p, h in checked["files"].items()), "确认工具验证后漂移")
        comps, _ = dev.read(_project_file(_PROJECT_ROOT, HERE / "FROZEN-OPPONENT-COMPOSITIONS.json"))
        files = dict(development_plan["files"])
        files.update(checked["files"])
        files.update({str(_project_file(_PROJECT_ROOT, HERE / "CONFIRMATION-TOOLS-CHECKED.json")): checked_pin,
            str(_project_file(_PROJECT_ROOT, HERE / "DEVELOPMENT-CLOSED.json")): development_pin,
            str(_project_file(_PROJECT_ROOT, HERE / "DEVELOPMENT-PLAN.json")): development_plan_pin,
            str(_project_file(_PROJECT_ROOT, HERE / "development-dispatch/CLOSED.json")): dispatch_pin,
            str(CONTRACT): pin(CONTRACT)})
        plan = {"schema": "t185-natural-confirmation/1", "roots": comps["pools"]["confirmation"],
            "parent": development_plan["parent"], "candidates": [selected],
            "selected_candidate_id": selected["identity"]["candidate_id"], "files": files,
            "source_manifest": development_plan["source_manifest"], "development_evidence_files": dependencies,
            "development_dispatch_closed_pin": dispatch_pin, "rotations": [0, 1, 2, 3], "rounds": 8,
            "initial_dealer_physical": 0, "initial_scores_0_1_2_3": [0, 0, 0, 0],
            "planned_table_instances": 1024, "maximum_new_complete_table_instances": 1024,
            "step_limit": development_plan["step_limit"], "wall_seconds_per_table": 600,
            "minimum_free_bytes": development_plan["minimum_free_bytes"], "capture_limits": development_plan["capture_limits"],
            "bootstrap": {"seed": 20261005, "replicates": 20000, "sources": 128, "interval": "percentile_linear_0.025_0.975"},
            "minimum_mean_points_per_complete_table": 0.5, "lower_bound_strictly_above": 0,
            "no_early_score_peeking_or_additional_roots": True, "normal_fallbacks_allowed": False,
            "deadline_admission": False, "runtime_reliability_admission": False, "release_admission": False}
        validate_plan(plan)
        frozen(plan)
        new_json(PLAN, plan)
    print(json.dumps({"prepared": True, "planned_tables": 1024, "new_scores_worlds_tables": 0}))


if __name__ == "__main__":
    main()
