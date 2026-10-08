"""诊断反馈闭合后发起一次已授权GLM作者提案；失败计槽，不自动重试。"""

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
import json
from pathlib import Path

from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents, run_vip_eoh_generate
from glm_max_transport import make_factory
from prepare_diagnostics import pin, save

HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT


def closed_author_feedback():
    """给后续调用补已闭合资格与真实失败；失败源码不是有效父代。"""
    result = {}
    natural = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-natural-1-model-output-qualification/CLOSURE.json")
    if natural.exists():
        gate = json.loads(natural.read_text())
        assert gate["complete"] and gate["source_stable"]
        result["natural_first_actual_qualification"] = {
            "mechanical_passed": gate["mechanical_passed"],
            "meaningful_changed_windows": gate["meaningful_changed_windows"],
            "actual_changed_rows": [{k: r.get(k) for k in (
                "label", "root_id", "parent_first", "candidate_first", "classes",
                "parent_normalized_gap", "child_normalized_gap")} for r in gate["rows"] if r.get("meaningful_first_changed")],
            "interpretation": "实际改选仅当前可胡/杠窗口，尚未观察早期普通弃牌改善；不是强度证据"}
    diagnostic = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-pay-1-FAILURE-DIAGNOSTIC.json")
    if diagnostic.exists():
        failure = json.loads(diagnostic.read_text())
        result["pay_first_failure"] = failure
        reply = (_project_file(_PROJECT_ROOT, HERE / "AUTHOR-pay-1-model-output/reply.txt")).read_text()
        # 完整失败回复只作反例输入；不建立候选身份或把它当可装载父代。
        assert len(reply.encode()) <= 131072
        result["pay_first_failed_reply_not_valid_parent"] = reply
        result["mandatory_contract_reminder"] = (
            "机制changed_branches必须是非空字符串，不能返回列表；静态只读语言不支持list.extend，"
            "改用for循环append。保持所有合法动作，不能因为格式/语言失败改动规则或预算。")
    return result


def main(mechanism, slot):
    """基于公开诊断生成完整联合公式；封存确认输入不读取、不发送。"""
    assert mechanism in ("natural", "pay", "joint") and slot in (1, 2)
    preparation = json.loads((_project_file(_PROJECT_ROOT, HERE / "AUTHOR-PREPARATION.json")).read_text())
    assert all(pin(Path(p)) == h for p, h in preparation["files"].items())
    assert all(pin(_project_file(_PROJECT_ROOT, ROOT / p)) == h for p, h in preparation["source_manifest"].items())
    diagnosis = json.loads((_project_file(_PROJECT_ROOT, HERE / "DIAGNOSIS-CLOSED.json")).read_text())
    assert diagnosis["complete"] and all(pin(Path(p)) == h for p, h in diagnosis["files"].items())
    out = _project_file(_PROJECT_ROOT, HERE / f"AUTHOR-{mechanism}-{slot}-model-output")
    assert not out.exists()
    feedback = (_project_file(_PROJECT_ROOT, HERE / f"AUTHOR-{mechanism}-BASE-FEEDBACK.txt")).read_text()
    feedback += "\n本次调用前已闭合诊断（条件收益仍非自然频率/真实后验）：\n" + json.dumps({
        k: diagnosis[k] for k in ("panel_windows", "prototype_first_changes", "causal_targets",
            "causal_mother_sources", "causal_actual_counts", "comparisons", "remaining_unknowns")}, ensure_ascii=False)
    operator, parents = "i1", []
    if slot == 2:
        prior = _project_file(_PROJECT_ROOT, HERE / f"AUTHOR-{mechanism}-1-model-output")
        generation = json.loads((prior / "generation.json").read_text())
        previous = {"status": generation["status"], "error": generation.get("error")}
        gate = _project_file(_PROJECT_ROOT, HERE / (prior.name + "-qualification/CLOSURE.json"))
        if gate.exists():
            qualification = json.loads(gate.read_text())
            previous["qualification"] = {k: qualification[k] for k in (
                "complete", "failure", "actual_completed_views", "new_behavior_sources", "changed_windows", "meaningful_changed_windows", "development_eligible")}
        if generation["status"] == "loaded_not_admitted":
            load_vip_parents([prior], VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json")))
            operator, parents = "m1", [prior]
            previous["lineage"] = "有效第一槽提案为唯一正式父代；强度仍对比固定S02"
        elif (prior / "candidate.py").exists():
            raw = (prior / "candidate.py").read_bytes()
            if len(raw) <= 131072:
                previous["failed_source_not_valid_parent"] = raw.decode()
        feedback += "\n第一槽真实失败/行为反馈（不是成功父代成绩）：\n" + json.dumps(previous, ensure_ascii=False)
    feedback += "\n请提出与仅加小常数不同的完整联合机制；不要照搬条件诊断收益为概率，不将目标改成复刻历史动作。"
    numerical = _project_file(_PROJECT_ROOT, HERE / "NUMERICAL-TIE-AUDIT.json")
    if numerical.exists():
        feedback += "\n原诊断追加核对（早于此追加件发出的第一调用未收到此信息）：\n" + numerical.read_text()
    additional = closed_author_feedback()
    feedback += "\n已闭合作者反馈及合同失败反例：\n" + json.dumps(additional, ensure_ascii=False)
    plan_file = _project_file(_PROJECT_ROOT, HERE / f"AUTHOR-{mechanism}-{slot}-START.json")
    save(plan_file, {"mechanism": mechanism, "slot": slot, "operator": operator, "baseline_comparison_fixed": True,
        "baseline_is_reference_not_formal_parent": True, "actual_parent_paths": [str(p) for p in parents],
        "diagnosis_pin": pin(_project_file(_PROJECT_ROOT, HERE / "DIAGNOSIS-CLOSED.json")),
        "numerical_addendum_pin": pin(numerical) if numerical.exists() else None,
        "runner_pin": pin(Path(__file__)), "transport_pin": pin(_project_file(_PROJECT_ROOT, HERE / "glm_max_transport.py")),
        "closed_feedback_files": {str(p): pin(p) for p in (
            _project_file(_PROJECT_ROOT, HERE / "AUTHOR-natural-1-model-output-qualification/CLOSURE.json"),
            _project_file(_PROJECT_ROOT, HERE / "AUTHOR-pay-1-FAILURE-DIAGNOSTIC.json"),
            _project_file(_PROJECT_ROOT, HERE / "AUTHOR-pay-1-model-output/reply.txt")) if p.exists()},
        "this_attempt_request_not_started_at_start_record": True, "retry": False})
    result = run_vip_eoh_generate(batch_file=_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"), out_dir=out,
        operator=operator, backend="api", parent_paths=parents, feedback=feedback,
        config=_project_file(_PROJECT_ROOT, ROOT / ".private/vip-zai-api.json"), endpoint="zai-coding-cn", model="glm-5.3", tier="senior",
        backend_factory=make_factory(out / "ACTUAL-REASONING-REQUEST.json"))
    print({k: result.get(k) for k in ("status", "identity_stable", "attempt_id", "operator_actual", "error")}, flush=True)
    if result["status"] != "loaded_not_admitted" or not result["identity_stable"]:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mechanism", choices=("natural", "pay", "joint"), required=True)
    parser.add_argument("--slot", type=int, choices=(1, 2), required=True)
    args = parser.parse_args()
    main(args.mechanism, args.slot)
