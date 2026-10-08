"""接线验证工具的零评分预检：实际39输入、纯门禁负例和spawn工厂序列化。"""

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
import ast
import copy
import math
import pickle
from pathlib import Path

from common import HERE, pin, save
import t185_close_development as dev
import candidate_verification_common as common


def rejected(function, *args):
    """坏输入必须在真实评分前明确拒绝；意外放行使工具准备失败。"""
    try:
        function(*args)
    except (ValueError, KeyError, TypeError):
        return True
    raise AssertionError("坏输入未拒绝")


def main():
    """实际输入解码不做规则分析或评分；不启动进程，不生成世界，不编译候选。"""
    names = ("candidate_verification_common.py", "verify_candidate_native.py", "probe_candidate_deadlines.py",
        "check_candidate_verification_tools.py", "CANDIDATE-VERIFICATION-CONTRACT.md",
        "prepare_candidate_native.py", "prepare_live_deadline_supplement.py", "common.py",
        "AUTHOR-BATCH.json", "ORIGINAL-DEADLINE-INPUTS.json", "LIVE-DEADLINE-SUPPLEMENT.json",
        "SUPPLEMENT-PLAN.json", "SUPPLEMENT-ORIGINAL-AUDIT.jsonl", "NATIVE-TOOLS-MATERIAL-CHECKED.json")
    files = {str(_project_file(_PROJECT_ROOT, HERE / name)): pin(_project_file(_PROJECT_ROOT, HERE / name)) for name in names}
    for name in ("CANDIDATE-VERIFICATION-TOOLS-CHECKED.json", "verification-tools-precheck-001-originals/SUPERSEDED.json"):
        files[str(_project_file(_PROJECT_ROOT, HERE / name))] = pin(_project_file(_PROJECT_ROOT, HERE / name))
    for name in names:
        if name.endswith(".py"):
            ast.parse((_project_file(_PROJECT_ROOT, HERE / name)).read_text(), filename=name)
    values = common.original_cases()
    originals, _ = dev.read(_project_file(_PROJECT_ROOT, HERE / "ORIGINAL-DEADLINE-INPUTS.json"))
    live, _ = dev.read(_project_file(_PROJECT_ROOT, HERE / "LIVE-DEADLINE-SUPPLEMENT.json"))
    supplement, _ = dev.read(_project_file(_PROJECT_ROOT, HERE / "SUPPLEMENT-PLAN.json"))
    files.update(originals["files"])
    files.update(live["files"])
    files.update({str(_project_file(_PROJECT_ROOT, HERE / "SUPPLEMENT-ORIGINAL-AUDIT.jsonl")): supplement["files"][str(_project_file(_PROJECT_ROOT, HERE / "SUPPLEMENT-ORIGINAL-AUDIT.jsonl"))]})
    from hangma_bot.application import audit_codec, decision_compute
    from hangma_bot.policy import action_value_executor, route_vip_heuristic
    files.update({str(Path(m.__file__)): pin(Path(m.__file__)) for m in (audit_codec, decision_compute, action_value_executor, route_vip_heuristic)})
    rows = [{"decision_id": request.decision_id, "game_id": request.window_key.game_id,
        "phase": request.observation.phase, "legal_action_keys": [c.action_key for c in request.rules.legal_candidates],
        "original_remaining_seconds": list(spans), "origin": source} for request, spans, source in values]
    dev.require(sum(r["phase"] == "draw" for r in rows) == 24 and sum(r["phase"] != "draw" for r in rows) == 15,
        "实际输入摸打/响应分母不同")
    sample = {"monotonic_ns": 10_000_000_000, "payload": {"budget": {"codec_version": 1,
        "enhancement_deadline_monotonic": 10.1, "fallback_deadline_monotonic": 10.2, "latest_send_at_monotonic": 10.3}}}
    common.relative_spans(sample)
    negative = []
    for name, key, value in (("bool_deadline", "enhancement_deadline_monotonic", True),
        ("nan_deadline", "fallback_deadline_monotonic", math.nan),
        ("zero_remaining", "enhancement_deadline_monotonic", 10),
        ("reversed_deadline", "fallback_deadline_monotonic", 10.05)):
        bad = copy.deepcopy(sample)
        bad["payload"]["budget"][key] = value
        rejected(common.relative_spans, bad)
        negative.append(name)
    bad = copy.deepcopy(sample)
    bad["monotonic_ns"] = True
    rejected(common.relative_spans, bad)
    negative.append("bool_monotonic_ns")
    identity = {"candidate_id": "synthetic-only-not-an-actual-candidate"}
    plan = {"candidates": [{"identity": identity}], "selected_candidate_id": identity["candidate_id"]}
    closed = {"complete": True, "source_stable": True, "actual_table_instances": 1024,
        "completed_hand_instances": 8192, "independent_strength_evidence_passed": True,
        "comparison": {"mean_delta": {"net": 0.5}, "net_source_bootstrap95": [0.1, 1.0],
            "independent_mother_sources": 128, "paired_complete_tables": 512,
            "identity": identity, "candidate_id": identity["candidate_id"]}}
    dispatch = {"complete": True, "resources_released": True}
    common.require_strength(closed, plan, dispatch)
    for name, mutate in (("mean_below_gate", lambda c: c["comparison"]["mean_delta"].update(net=0.49)),
        ("mean_bool", lambda c: c["comparison"]["mean_delta"].update(net=True)),
        ("interval_zero_lower", lambda c: c["comparison"].update(net_source_bootstrap95=[0, 1])),
        ("interval_nan", lambda c: c["comparison"].update(net_source_bootstrap95=[0.1, math.nan])),
        ("missing_complete_table", lambda c: c.update(actual_table_instances=1023)),
        ("identity_drift", lambda c: c["comparison"].update(identity={"candidate_id": "other"}))):
        bad = copy.deepcopy(closed)
        mutate(bad)
        rejected(common.require_strength, bad, plan, dispatch)
        negative.append(name)
    rejected(common.require_strength, closed, plan, {"complete": True, "resources_released": False})
    negative.append("confirmation_resource_not_released")
    snapshot = {"closed": True, **{k: 0 for k in common.RESOURCE_KEYS}}
    dev.require(common.resource_zero(snapshot) and not common.resource_zero({**snapshot, "owned": 1}) and
        not common.resource_zero({**snapshot, "ready": False}) and not common.resource_zero({"closed": True}), "资源坏例放行")
    negative += ["live_resource", "bool_zero_resource", "missing_resource_keys"]
    factory = common.ConfirmedCandidateFactory("not-loaded-test-source", "not-loaded-test-candidate", "not-loaded-test-execution")
    dev.require(pickle.loads(pickle.dumps(factory, protocol=5)) == factory, "spawn工厂不能序列化")
    # 当前未产生确认计划：验证同一真实读取接缝确实拒绝，不能凭资格面板提前编译。
    from t185_prepare_confirmation import read_confirmation_plan
    missing_confirmation = None
    if not (_project_file(_PROJECT_ROOT, HERE / "CONFIRMATION-PLAN.json")).exists():
        try:
            read_confirmation_plan()
        except FileNotFoundError as error:
            dev.require(Path(error.filename) == _project_file(_PROJECT_ROOT, HERE / "CONFIRMATION-PLAN.json"), "拒绝原因不是未确认")
            missing_confirmation = {"type": type(error).__name__, "path": str(Path(error.filename)), "new_scores_worlds_tables": 0}
        else:
            raise AssertionError("不存在的确认计划未拒绝")
    common.check_files(files)
    groups = sorted({source["group"] for _, _, source in values[19:]})
    save(common.TOOLS_CHECKED, {"complete": True, "files": files, "decoded_original_requests": len(rows),
        "original_required_requests": 19, "additional_first_draw_requests": 20, "real_distinct_game_ids": 27,
        "rows": rows, "two_ten_distinct_table_groups": {g: [r["game_id"] for r in rows if r["origin"]["group"] == g] for g in groups},
        "negative_checks_passed": negative, "factory_pickle_roundtrip": True,
        "missing_confirmation_real_read_rejection": missing_confirmation,
        "first_precheck_preserved": pin(_project_file(_PROJECT_ROOT, HERE / "CANDIDATE-VERIFICATION-TOOLS-CHECKED.json")),
        "concurrency_timing_refinement": "先存全波输入，共享波起点；全波choose返回后做摘要，无热区工具写盘",
        "new_scores_worlds_tables_HTTP": 0, "candidate_compilations": 0, "compute_processes_started": 0,
        "planned_equivalence_scores_after_confirmation": 542, "planned_actual_deadline_choose_after_equivalence": 59,
        "no_candidate_equivalence_deadline_or_strength_admission": True})
    print({"decoded_requests": len(rows), "negative_checks_passed": len(negative), "new_scores_worlds_tables_HTTP": 0}, flush=True)


if __name__ == "__main__":
    main()
