"""T199共同P0余桌的薄装配；先验文件冻结，随后只调既有生产公开接口。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = '.private/t199-four-step-execution/joint-continuation'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

from dataclasses import dataclass
import gzip
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
STAGE = _project_file(_PROJECT_ROOT, '.private/t199-four-step-execution')
RUNNER = _project_file(_PROJECT_ROOT, '.private/t199-four-step-execution/strategy-runner')


def canonical(value):
    """严格有限JSON摘要；持续时间另记单调秒，四座分数另标座序。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def pin(path):
    """声明文件的字节/SHA；不触碰凭据或确认牌山。"""
    raw = Path(path).read_bytes()
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def read(path):
    """只读取传入的私有计划/收据，数据不成为执行指令。"""
    return json.loads(Path(path).read_text())


def save(path, value):
    """新输出独占创建；失败与旧费用不覆盖。"""
    with Path(path).open("xb") as stream:
        stream.write(canonical(value) + b"\n")


def verify_files(files):
    """精确核冻结的有限映射；漂移立即拒绝。"""
    for path, expected in files.items():
        if pin(path) != expected:
            raise ValueError("冻结文件漂移:" + path)


def verify_impact(source_path, *, require_full_map=True):
    """核当前P032批的完整源码；原失败批没有32 CLOSED则不可用。"""
    source_path = Path(source_path).resolve()
    source = read(source_path)
    root = Path(source["runtime_root"]).resolve()
    if root != _project_file(_PROJECT_ROOT, STAGE / "runtime-workspace/runtime-root-p0"):
        raise ValueError("来源不是冻结当前P0 runtime root")
    verify_files(source["files"])
    verify_files({str(root / name): expected for name, expected in source["runtime_files"].items()})
    tasks = source["tasks"]
    if (not 1 <= len(tasks) <= 32 or len({(t["root"], t["rotation"]) for t in tasks}) != len(tasks)
            or any(t["rounds"] != 8 or t["root"] not in range(1, 9) or t["rotation"] not in range(4) for t in tasks)
            or require_full_map and (len(tasks) != 32 or {t["root"] for t in tasks} != set(range(1, 9)))):
        raise ValueError("来源不是事前8母×4换座位R8")
    return source, root


def composite_origins(reference_path, manifest_path):
    """逐桌绑定真实成功来源；仅外层测量修正可异，核心/公式/墙/对手须精确同。"""
    reference_path, manifest_path = Path(reference_path).resolve(), Path(manifest_path).resolve()
    reference, _ = verify_impact(reference_path)
    manifest = read(manifest_path)
    if not (manifest["schema"] == "t199-p0-impact-composite-origins/1" and manifest["complete"] is True
            and Path(manifest["reference_plan_path"]).resolve() == reference_path
            and manifest["reference_plan_pin"] == pin(reference_path)
            and manifest["runtime_root"] == reference["runtime_root"]
            and manifest["candidate_identity"] == reference["candidate_identity"]
            and manifest["compiled_runtime"] == reference["compiled_runtime"]):
        raise ValueError("32复合来源身份未闭")
    table_rows = manifest["tables"]
    if len(table_rows) != 32 or {row["table_no"] for row in table_rows} != set(range(1, 33)):
        raise ValueError("复合来源不是32唯一成功桌")
    reference_tasks = {t["table_no"]: t for t in reference["tasks"]}
    plans, origins, files = {}, {}, {str(reference_path): pin(reference_path), str(manifest_path): pin(manifest_path)}
    for row in table_rows:
        origin_path = Path(row["origin_plan_path"]).resolve()
        if pin(origin_path) != row["origin_plan_pin"]:
            raise ValueError("逐桌origin PLAN漂移")
        if origin_path not in plans:
            origin, _ = verify_impact(origin_path, require_full_map=False)
            if (origin["candidate_identity"] != reference["candidate_identity"]
                    or origin["compiled_runtime"] != reference["compiled_runtime"]
                    or origin["runtime_files"] != reference["runtime_files"]):
                raise ValueError("origin核心/公式/配置/编译身份不同；不是单纯测量修正")
            plans[origin_path] = origin
        origin = plans[origin_path]
        task = reference_tasks[row["table_no"]]
        matches = [t for t in origin["tasks"] if t["table_no"] == row["table_no"]]
        if matches != [task] or row["task"] != task:
            raise ValueError("origin任务/scene/seed/换座位/对手不同")
        closed_path = Path(row["closed_path"]).resolve()
        if pin(closed_path) != row["closed_pin"]:
            raise ValueError("逐桌成功收据漂移")
        closed = read(closed_path)
        if not (closed["complete"] is True and closed["source_and_map_stable"] is True
                and closed["completed_hands"] == 8 and closed["outcome_status"] == "complete"
                and closed["task"] == task and closed["plan_pin"] == row["origin_plan_pin"]
                and all(type(v) is int and v == 0 for v in closed["runtime_counts"].values())):
            raise ValueError("origin不是自然成功R8；失败prefix不可用")
        files[str(origin_path)] = row["origin_plan_pin"]
        files[str(closed_path)] = row["closed_pin"]
        raw_paths = {}
        for name in ("decisions.jsonl.gz", "views.jsonl.gz"):
            raw = row["raw_files"][name]
            path = Path(raw["path"]).resolve()
            expected = {key: raw[key] for key in ("bytes", "sha256")}
            if pin(path) != expected or expected != closed["raw_files"][name]:
                raise ValueError("逐桌原公开prefix/捕获SHA不同")
            files[str(path)] = expected
            raw_paths[name] = str(path)
        origins[row["table_no"]] = {"task": task, "origin_plan_path": str(origin_path),
            "origin_plan_pin": row["origin_plan_pin"], "closed_path": str(closed_path),
            "closed_pin": row["closed_pin"], "raw_paths": raw_paths}
    return reference, origins, files, plans


def measurement_gate(reference, measurement_path):
    """复用总筹已冻结的精确信息说明检测；其修正不成为策略父代变化。"""
    path = Path(measurement_path).resolve()
    measurement, _ = verify_impact(path, require_full_map=False)
    if (measurement["candidate_identity"] != reference["candidate_identity"]
            or measurement["compiled_runtime"] != reference["compiled_runtime"]
            or measurement["runtime_files"] != reference["runtime_files"]):
        raise ValueError("测量helper和P0核心身份不同")
    helper = path.parent / "common.py"
    if str(helper) not in measurement["files"] or pin(helper) != measurement["files"][str(helper)]:
        raise ValueError("精确测量helper没有被来源计划冻结")
    return {"plan_path": str(path), "plan_pin": pin(path), "helper_path": str(helper), "helper_pin": pin(helper)}


def load_measurement_gate(gate):
    """只载已读且验签的外部stdlib薄helper；focal严格和当前catch旗保持原函数。"""
    import importlib.util
    path = Path(gate["helper_path"])
    if pin(path) != gate["helper_pin"] or pin(gate["plan_path"]) != gate["plan_pin"]:
        raise ValueError("精确说明helper漂移")
    name = "t199_joint_frozen_measurement_helper"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module.true_degradations, read(gate["plan_path"])


def activate(source):
    """干净进程绑定私有P0；不清模块或替换生产全局。"""
    if any(name == "hangma_bot" or name.startswith("hangma_bot.") for name in sys.modules):
        raise ValueError("需要干净进程；不能混载旧规则")
    sys.path.insert(0, str(Path(source["runtime_root"]) / "src"))
    sys.path.insert(1, str(RUNNER))


def verify_loaded(source):
    """所有项目模块必须来自同冻结root；自然对手和规则不准混main。"""
    root = Path(source["runtime_root"]) / "src"
    loaded = {}
    for name, module in tuple(sys.modules.items()):
        if name == "hangma_bot" or name.startswith("hangma_bot."):
            path = Path(module.__file__).resolve()
            if not path.is_relative_to(root):
                raise ValueError("混载项目模块:" + name)
            loaded[name] = str(path)
    return loaded


@dataclass(frozen=True)
class FrozenParameters:
    """只供既有对手装配所需的规则和图预算，不建立新训练平台。"""
    rule_config: object
    route_limits: object
    projection_limits: object
    max_operations: int

    def identity(self, source):
        """复用生产完整公式身份口径。"""
        from hangma_bot.offline.vip_heuristic_smoke import freeze_vip_identity
        return freeze_vip_identity(source, max_operations=self.max_operations,
            projection_limits=self.projection_limits, rule_config=self.rule_config, route_limits=self.route_limits)


def parameters(source):
    """来源P0 PLAN里的实际配置；不把客户端规则标签称官方指南版本。"""
    from hangma_bot.kernel.config import RuleConfig
    from hangma_bot.hangma.interface import ValueAnalysisLimits
    from hangma_bot.policy.route_vip_heuristic import VipRouteProjectionLimits
    p = source["candidate_identity"]["params"]
    return FrozenParameters(RuleConfig(**p["rule_config"]), ValueAnalysisLimits(**p["route_limits"]),
                            VipRouteProjectionLimits(**p["projection_limits"]), p["max_operations"])


def native_parent(source):
    """仅载已冻结checked原S03 native；草稿manifest不代表上线资格。"""
    from hangma_bot import bootstrap
    checked, _ = bootstrap._verify_vip_s03_runtime(source["compiled_runtime"]["manifest_sha256"])
    if checked != source["compiled_runtime"]:
        raise ValueError("父native身份不同")
    return bootstrap._load_vip_s03_runtime(checked["manifest_sha256"])


def rows(path):
    """全座公开决策原行序；不读OUTCOME/settlements或最终成绩。"""
    with gzip.open(path, "rt") as stream:
        for number, line in enumerate(stream):
            yield number, json.loads(line)


def checked_plan(path):
    """续打用冻结点和全部原件；不重新选点或重抽有利世界。"""
    plan = read(path)
    if plan["schema"] != "t199-common-P0-continuation-plan/1":
        raise ValueError("不是共同P0余桌冻结计划")
    verify_files(plan["files"])
    source, _ = verify_impact(plan["source_impact_plan"])
    composite_origins(plan["source_impact_plan"], plan["source_origin_manifest"])
    if pin(plan["source_impact_plan"]) != plan["source_impact_plan_pin"]:
        raise ValueError("来源PLAN漂移")
    body = {k: v for k, v in plan.items() if k != "binding_id"}
    if hashlib.sha256(canonical(body)).hexdigest() != plan["binding_id"]:
        raise ValueError("续打完整身份不同")
    if len(plan["points"]) > 12 or plan["max_continuations"] != len(plan["points"]) * 4:
        raise ValueError("超事前48轨迹上限")
    return plan, source


def recover(engine, rules, config, task, prefix_file, target_row, route_limits, counts):
    """按真实全座已提交前缀恢复不透明世界，目标整个同步帧保留未推进。"""
    from hangma_bot.kernel.serialization import observation_to_json, window_key_to_json
    from hangma_bot.simulation import MatchSpec, SimulationChoice
    source_rows = list(rows(prefix_file))
    spec = MatchSpec(task["match_id"], task["scenario_id"], config, task["seed"],
                     task["initial_dealer_physical"], tuple(task["initial_scores"]))
    counts["historical_world_recoveries"] += 1
    world = engine.start(spec)
    cursor = 0
    while True:
        frame = engine.frame(world)
        if frame.blocked_reason or frame.final_scores is not None:
            raise ValueError("前缀尚未到目标已阻塞/桌末；不虚造官方World")
        decisions = frame.decisions
        chunk = source_rows[cursor:cursor + len(decisions)]
        if len(chunk) != len(decisions):
            raise ValueError("全座合法prefix不足")
        choices, target = [], None
        for decision, (row_no, row) in zip(decisions, chunk):
            if window_key_to_json(decision.window_key) != row["window_key"]:
                raise ValueError("prefix帧/座位顺序不同")
            if observation_to_json(decision.observation) != row["observation"]:
                raise ValueError("prefix完整公开观察不同")
            counts["prefix_rule_analyses"] += 1
            analysis = rules.analyze(decision.observation, route_limits=route_limits)
            if (analysis.completeness.value != "complete" or sorted(c.action_key for c in analysis.legal_candidates)
                    != sorted(row["legal_action_keys"])):
                raise ValueError("prefix合法集合/规则完整性不同")
            by_key = {c.action_key: c.action for c in analysis.legal_candidates}
            if row["status"] != "chosen" or row["selected_action_key"] not in by_key:
                raise ValueError("prefix含未合法提交选择")
            choices.append(SimulationChoice(decision.window_key, by_key[row["selected_action_key"]]))
            if row_no == target_row:
                target = (decision, row)
        if target is not None:
            return world, frame, target, cursor
        world = engine.advance(world, frame.revision, tuple(choices))
        cursor += len(decisions)
        counts["prefix_decisions_replayed"] += len(decisions)


def attempt_ledger(plan_path, plan, point_no, *, result=None):
    """同冻结计划每点仅一次登记四轨迹上限；失败槽保留，跨输出目录也不补试。"""
    import fcntl
    import os
    ledger_path = Path(plan_path).parent / "CONTINUATION-ATTEMPT-LEDGER.json"
    with ledger_path.with_suffix(".lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        ledger = read(ledger_path) if ledger_path.exists() else {
            "schema": "t199-common-P0-continuation-attempt-ledger/1", "binding_id": plan["binding_id"],
            "plan_pin": pin(plan_path), "max_reserved_remaining_table_continuations": plan["max_continuations"], "attempts": []}
        if ledger["binding_id"] != plan["binding_id"] or ledger["plan_pin"] != pin(plan_path):
            raise ValueError("余桌账绑定漂移")
        previous = [r for r in ledger["attempts"] if r["point"] == point_no]
        if result is None:
            if previous or sum(r["reserved_remaining_table_continuations"] for r in ledger["attempts"]) + 4 > plan["max_continuations"]:
                raise ValueError("该点已有尝试或48轨迹预算耗尽；失败不补槽")
            ledger["attempts"].append({"point": point_no, "reserved_remaining_table_continuations": 4,
                "pid": os.getpid(), "status": "reserved_unsettled", "actual": None})
        else:
            if len(previous) != 1 or previous[0]["status"] != "reserved_unsettled":
                raise ValueError("费用关闭找不到唯一原预留")
            previous[0].update(status="closed", actual=result)
        temporary = ledger_path.with_name(ledger_path.name + ".tmp." + str(os.getpid()))
        with temporary.open("xb") as stream:
            stream.write(canonical(ledger) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, ledger_path)
        return pin(ledger_path)
