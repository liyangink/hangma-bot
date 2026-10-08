"""T185胜者验证的窄接缝：确认门、原请求及启动期工厂，不注册线上策略。"""
from __future__ import annotations

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

import hashlib
import importlib.util
import math
from dataclasses import asdict, dataclass
from pathlib import Path

from common import HERE, ROOT, canonical, pin
import t185_close_development as dev

TOOLS_CHECKED = _project_file(_PROJECT_ROOT, HERE / "CANDIDATE-VERIFICATION-TOOLS-CHECKED-V2.json")
RESOURCE_KEYS = ("owned", "pending", "active", "ready", "live_processes", "current",
    "transport_inflight", "transport_threads_alive", "late_reap_inflight",
    "late_reap_threads_alive", "bound_games", "releasing_games")
DEADLINES = ("enhancement_deadline_monotonic", "fallback_deadline_monotonic", "latest_send_at_monotonic")


def digest(value):
    """有限JSON的规范摘要；比较全输出，不只比较第一动作。"""
    return hashlib.sha256(canonical(value)).hexdigest()


def check_files(files):
    """逐项验证实际字节；本工具只读已冻结来源，不读取活房流。"""
    dev.require(all(pin(Path(p)) == expected for p, expected in files.items()), "验证输入字节漂移")


def require_tools():
    """工具负例及实际输入封存通过后才允许真实评分或计算进程。"""
    checked, checked_pin = dev.read(TOOLS_CHECKED)
    dev.require(checked["complete"] is True and checked["new_scores_worlds_tables_HTTP"] == 0,
        "候选验证工具未完成零费用检查")
    check_files(checked["files"])
    return {str(TOOLS_CHECKED): checked_pin, **checked["files"]}


def require_strength(closed, plan, dispatch):
    """唯一公式的1024桌确认及128来源净分增强门；不把工具准备当算法成绩。"""
    comparison = closed["comparison"]
    mean, interval = comparison["mean_delta"]["net"], comparison["net_source_bootstrap95"]
    dev.require(type(mean) in (int, float) and math.isfinite(mean) and type(interval) is list and
        len(interval) == 2 and all(type(v) in (int, float) and math.isfinite(v) for v in interval) and
        0 < interval[0] <= interval[1] and mean >= 0.5, "确认均值或来源区间未通过")
    dev.require(closed["complete"] is True and closed["source_stable"] is True and
        type(closed["actual_table_instances"]) is int and closed["actual_table_instances"] == 1024 and
        closed["completed_hand_instances"] == 8192 and closed["independent_strength_evidence_passed"] is True and
        comparison["independent_mother_sources"] == 128 and comparison["paired_complete_tables"] == 512 and
        dispatch["complete"] is True and dispatch["resources_released"] is True and
        len(plan["candidates"]) == 1 and comparison["identity"] == plan["candidates"][0]["identity"] and
        comparison["candidate_id"] == plan["selected_candidate_id"], "确认完整资源或候选身份未通过")


def validated_candidate():
    """真实确认闭合后取得唯一胜者；缺确认文件时评分前拒绝，不自动造候选。"""
    from t185_prepare_confirmation import read_confirmation_plan
    from prepare_candidate_native import load_checked_runtime
    from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents
    files = require_tools()
    plan, plan_pin = read_confirmation_plan(verify_development_evidence=True)
    closed, closed_pin = dev.read(_project_file(_PROJECT_ROOT, HERE / "CONFIRMATION-CLOSED.json"))
    dispatch, dispatch_pin = dev.read(_project_file(_PROJECT_ROOT, HERE / "confirmation-dispatch/CLOSED.json"))
    require_strength(closed, plan, dispatch)
    dev.require(dispatch["confirmation_closed_pin"] == closed_pin and
        closed["files"][str(_project_file(_PROJECT_ROOT, HERE / "CONFIRMATION-PLAN.json"))] == plan_pin, "确认文件相互绑定缺失")
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"))
    arm = plan["candidates"][0]
    loaded, = load_vip_parents([Path(arm["package"])], batch)
    dev.require(loaded["identity"] == arm["identity"], "实际候选身份不同")
    native_plan, native_plan_pin = dev.read(_project_file(_PROJECT_ROOT, HERE / "native-candidate/BUILD-PLAN.json"))
    native_closed, native_closed_pin = dev.read(_project_file(_PROJECT_ROOT, HERE / "native-candidate/BUILD-CLOSED.json"))
    dev.require(native_plan["candidate_identity"] == arm["identity"] and
        native_plan["confirmation_plan_pin"] == plan_pin and native_plan["confirmation_closed_pin"] == closed_pin and
        native_plan["confirmation_dispatch_pin"] == dispatch_pin, "编译制品未绑定本次确认")
    runtime = load_checked_runtime()
    files.update({str(_project_file(_PROJECT_ROOT, HERE / "CONFIRMATION-PLAN.json")): plan_pin,
        str(_project_file(_PROJECT_ROOT, HERE / "CONFIRMATION-CLOSED.json")): closed_pin,
        str(_project_file(_PROJECT_ROOT, HERE / "confirmation-dispatch/CLOSED.json")): dispatch_pin,
        str(_project_file(_PROJECT_ROOT, HERE / "native-candidate/BUILD-PLAN.json")): native_plan_pin,
        str(_project_file(_PROJECT_ROOT, HERE / "native-candidate/BUILD-CLOSED.json")): native_closed_pin,
        str(Path(arm["qualification_file"])): pin(Path(arm["qualification_file"])),
        **native_plan["files"], native_closed["binary_path"]: native_closed["binary_pin"]})
    return batch, arm, runtime, files


def relative_spans(record):
    """原单调记录时刻到三个原截止的余量秒；布尔、非有限、非正或逆序均拒绝。"""
    from hangma_bot.application.audit_codec import decision_budget_from_json
    dev.require(type(record["monotonic_ns"]) is int and record["monotonic_ns"] >= 0, "原单调纳秒非整数")
    raw = record["payload"]["budget"]
    dev.require(all(type(raw[k]) in (int, float) and math.isfinite(raw[k]) for k in DEADLINES), "原截止不是有限数")
    budget = decision_budget_from_json(raw)
    spans = tuple(getattr(budget, k) - record["monotonic_ns"] / 1e9 for k in DEADLINES)
    dev.require(0 < spans[0] <= spans[1] <= spans[2], "原余量非正或逆序，不扩窗")
    return spans


def original_cases():
    """原七压力窗、十二片段和两个十桌首摸，共39原请求，27真实不同桌。"""
    from hangma_bot.application.audit_codec import decision_request_from_json
    from prepare_live_deadline_supplement import cases as live_cases, ORIGINS
    path = _project_file(_PROJECT_ROOT, HERE.parent / "t179-production-wiring-1/probe_real_factory.py")
    spec = importlib.util.spec_from_file_location("_t185_frozen_pressure_inputs", path)
    pressure = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pressure)
    original, _ = dev.read(_project_file(_PROJECT_ROOT, HERE / "ORIGINAL-DEADLINE-INPUTS.json"))
    live, _ = dev.read(_project_file(_PROJECT_ROOT, HERE / "LIVE-DEADLINE-SUPPLEMENT.json"))
    supplement, _ = dev.read(_project_file(_PROJECT_ROOT, HERE / "SUPPLEMENT-PLAN.json"))
    check_files(original["files"])
    check_files(live["files"])
    audit = _project_file(_PROJECT_ROOT, HERE / "SUPPLEMENT-ORIGINAL-AUDIT.jsonl")
    dev.require(pin(audit) == supplement["files"][str(audit)], "二十首摸原输入漂移")
    # 原解码器先经过原始数字校验；避免旧codec把True转为1.0后丢失类型证据。
    for p in (*ORIGINS, *sorted((_project_file(_PROJECT_ROOT, HERE.parent / "t169-closed-state-pressure-1")).glob("dec-*.json"))):
        raw = p.read_bytes()
        rows = [r["record"] for r in dev.decode(raw)["records"]] if p.suffix == ".json" else [dev.decode(v) for v in raw.splitlines()]
        for row in rows:
            if row.get("kind") == "decision_input":
                relative_spans(row)
    cases = [(q, spans, {"group": "original-pressure", "old_S02_values_not_gold": True}) for q, spans, _ in pressure.cases()]
    cases += [(q, spans, {"group": "original-live", **source}) for q, spans, source in live_cases()]
    for raw in audit.read_bytes().splitlines():
        row = dev.decode(raw)
        if row.get("kind") != "decision_input":
            continue
        request = decision_request_from_json(row["payload"]["request"])
        cases.append((request, relative_spans(row), {"group": "supplement-" + request.window_key.game_id.split("_r1_")[0],
            "origin": str(audit), "line_sha256": hashlib.sha256(raw).hexdigest(), "old_S02_values_not_gold": True}))
    dev.require(len(cases) == len({r.decision_id for r, _, _ in cases}) == 39 and
        len({r.window_key.game_id for r, _, _ in cases}) == 27, "原请求或桌分母不同")
    extra = cases[19:]
    groups = sorted({s["group"] for _, _, s in extra})
    dev.require(len(groups) == 2 and all(sum(s["group"] == group for _, _, s in extra) == 10 and
        len({r.window_key.game_id for r, _, s in extra if s["group"] == group}) == 10 for group in groups), "十桌并发输入未独立")
    return cases


def resource_zero(snapshot):
    """只接受生产计算服务的实际已闭快照；缺项不能视为零。"""
    return snapshot.get("closed") is True and all(type(snapshot.get(k)) is int and snapshot[k] == 0 for k in RESOURCE_KEYS)


def make_policy(batch, source, compiled=None):
    """与生产相同研究策略；不创建HTTP、不读取隐藏世界，不改预算或公式。"""
    from hangma_bot.policy.route_vip_heuristic import RouteVipHeuristicPolicy
    return RouteVipHeuristicPolicy(batch.rule_config, source=source, max_operations=batch.max_operations,
        projection_limits=batch.projection_limits, compiled_runtime=compiled)


@dataclass(frozen=True)
class ConfirmedCandidateFactory:
    """可spawn的离线工厂；只携源码路径、候选及执行摘要，不含凭证或完整世界。"""
    source_file: str  # 已确认受限源码；仅启动期读取
    candidate_id: str  # 本批唯一已确认算法身份
    execution_id: str  # 原编译BUILD与实际二进制绑定摘要

    def __call__(self):
        """启动期核小型编译绑定并装配；不在动作窗口验签大评测原件。"""
        from hangma_bot.application.decision_compute import PreparedDecisionPolicy
        from hangma_bot.offline.vip_eoh_generate import VipEohBatch
        from prepare_candidate_native import load_checked_runtime
        native, _ = dev.read(_project_file(_PROJECT_ROOT, HERE / "native-candidate/BUILD-PLAN.json"))
        identity = native["candidate_identity"]
        dev.require(identity["candidate_id"] == self.candidate_id and
            native["files"].get(self.source_file) == pin(Path(self.source_file)) and
            pin(Path(self.source_file))["sha256"] == identity["source_sha256"], "工厂实际源码身份漂移")
        runtime = load_checked_runtime()
        dev.require(runtime.execution_id == self.execution_id, "工厂实际执行身份漂移")
        batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"))
        params = {"max_operations": batch.max_operations, "max_local_collection_size": batch.projection_limits.max_nodes,
            "projection_limits": asdict(batch.projection_limits),
            "route_limits": asdict(batch.route_limits),
            "rule_config": asdict(batch.rule_config)}
        dev.require(params == identity["params"], "工厂框架预算不同")
        return PreparedDecisionPolicy(make_policy(batch, Path(self.source_file).read_text(), runtime), runtime.execution_id)
