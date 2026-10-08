"""冻结编译验证的既有公开输入；只解码，不分析规则、不评分、不生成世界。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1/runtime-preparation-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import ast
import hashlib
import json
import os
import pickle
import subprocess
import sys
from pathlib import Path

from prepare_runtime_inputs import HERE, PLAN, PRIOR, ROOT, STAGE, background_priority, pin, postprocess_lock, require, save
from verification_common import (ConfirmedCandidateFactory, INPUTS, TOOLS, check_files, digest,
    original_cases, original_module, resource_zero, historical_input_files, HISTORICAL_SOURCE_REBINDINGS)


def main():
    """按公开观察与窗口键去重；不以候选分数、终局或高番结果挑选样本。"""
    background_priority()
    with postprocess_lock("t191-runtime-validation-input-freeze"):
        names = ("verification_common.py", "verify_candidate_native.py", "probe_candidate_deadlines.py",
            "freeze_validation_inputs.py", "VALIDATION-HELPER-PROVENANCE.json", "build_candidate_native.py",
            "confirmation_gate.py", "prepare_runtime_inputs.py", "GATE-TOOLS-CHECKED.json", "CLOSED.json")
        files = {str(_project_file(_PROJECT_ROOT, HERE / n)): pin(_project_file(_PROJECT_ROOT, HERE / n)) for n in names}
        for name in names:
            if name.endswith(".py"):
                ast.parse((_project_file(_PROJECT_ROOT, HERE / name)).read_text(), filename=name)
        files[str(PLAN)] = pin(PLAN)
        files[str(PLAN.with_name("EXECUTION-BATCH.json"))] = pin(PLAN.with_name("EXECUTION-BATCH.json"))
        control_path = STAGE / "wait-reassessment-1/PUBLIC-CONTROLS.json"
        mechanical_plan_path = control_path.with_name("PLAN.json")
        mechanical = json.loads(mechanical_plan_path.read_text())
        require(pin(control_path) == mechanical["public_controls_pin"], "35原机械公开输入漂移")
        records = json.loads(control_path.read_text())["records"]
        require(len(records) == 35, "机械控制分母不是35")
        input_files = {str(control_path): pin(control_path), str(mechanical_plan_path): pin(mechanical_plan_path)}
        panel, positions, origins, duplicate_rows = [], {}, {}, []

        def add(case, origin, known_view=None):
            """只保留实际公开观察及窗口；精确重复的来源均记账但不重复评分。"""
            key = digest({"observation": case["observation"], "window_key": case["window_key"]})
            if key in positions:
                existing = panel[positions[key]]
                require(known_view is None or existing["known_view_sha256"] in (None, known_view), "相同公开输入图摘要冲突")
                if known_view is not None:
                    existing["known_view_sha256"] = known_view
                existing["origins"].append(origin)
                duplicate_rows.append({"label": case["label"], "existing_label": existing["label"], "input_sha256": key})
                return
            positions[key] = len(panel)
            panel.append({"label": f"validation-{len(panel):03d}:" + case["label"],
                "observation": case["observation"], "window_key": case["window_key"],
                "known_view_sha256": known_view, "input_sha256": key, "origins": [origin]})

        for record in records:
            require(digest(record["view"]) == record["view_sha256"], "原机械公开图字节不符")
            add(record["case"], {"kind": "T191-mechanical-control", "path": str(control_path),
                "original_label": record["case"]["label"]}, record["view_sha256"])
        old_rows = 0
        for name in ("CASES.json", "SUPPLEMENT-CASES.json"):
            path = PRIOR / name
            input_files[str(path)] = pin(path)
            cases = json.loads(path.read_text())["cases"]
            old_rows += len(cases)
            for case in cases:
                add(case, {"kind": "T185-public-panel", "path": str(path), "original_label": case["label"]})
        require(old_rows == 115 and len(panel) + len(duplicate_rows) == 150, "原公开面板或去重计数不符")
        from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
        for case in panel:
            observation_from_json(case["observation"])
            window_key_from_json(case["window_key"])
        values = original_cases()
        rows = [{"decision_id": q.decision_id, "game_id": q.window_key.game_id, "phase": q.observation.phase,
            "original_remaining_seconds": list(spans), "origin": origin} for q, spans, origin in values]
        require(len(rows) == 39 and len({r["game_id"] for r in rows}) == 27 and
            sum(r["phase"] == "draw" for r in rows) == 24, "原请求解码分母不符")
        for name in ("ORIGINAL-DEADLINE-INPUTS.json", "LIVE-DEADLINE-SUPPLEMENT.json", "SUPPLEMENT-PLAN.json"):
            path = PRIOR / name
            input_files[str(path)] = pin(path)
            data = json.loads(path.read_text())
            if name != "SUPPLEMENT-PLAN.json":
                input_files.update(historical_input_files(data["files"]))
            else:
                audit = PRIOR / "SUPPLEMENT-ORIGINAL-AUDIT.jsonl"
                input_files[str(audit)] = data["files"][str(audit)]
        for name in ("candidate_verification_common.py", "prepare_live_deadline_supplement.py"):
            input_files[str(PRIOR / name)] = pin(PRIOR / name)
        check_files(input_files)
        expected_scores = 4 * len(panel) + 4 + 78
        save(INPUTS, {"schema": "t191-candidate-runtime-validation-inputs/1", "complete": True,
            "input_files": input_files, "public_cases": panel, "input_public_rows_before_dedup": 150,
            "distinct_public_cases": len(panel), "duplicates": duplicate_rows,
            "original_requests": rows, "original_required_requests": 19, "additional_original_requests": 20,
            "original_distinct_game_ids": 27, "planned_equivalence_score_attempts": expected_scores,
            "planned_original_deadline_service_choose": 59, "functional_reference_seconds": [30, 31, 32],
            "functional_budget_not_timing_evidence": True, "score_or_outcome_not_used_for_selection": True,
            "historical_policy_source_rebindings": HISTORICAL_SOURCE_REBINDINGS,
            "candidate_equivalence_deadline_strength_or_online_admitted": False,
            "new_rule_analyses_scores_compilations_worlds_tables_HTTP_models_compute_workers": 0})
        factory = ConfirmedCandidateFactory("not-loaded-source", "not-loaded-candidate", "not-loaded-execution")
        require(pickle.loads(pickle.dumps(factory, protocol=5)) == factory, "新spawn工厂不能序列化")
        keys = original_module().RESOURCE_KEYS
        snapshot = {"closed": True, **{k: 0 for k in keys}}
        require(resource_zero(snapshot) and not resource_zero({**snapshot, "owned": 1}) and
            not resource_zero({**snapshot, "ready": False}) and not resource_zero({"closed": True}), "资源未知被放行")
        # 真实验证入口必须先拒绝当前尚未闭合的确认，不能误用T185旧胜者。
        terminal = PLAN.with_name("wait-confirmation-001-READBACK-TERMINAL.json")
        require(not terminal.exists(), "本准备预检只适用于确认仍在运行期间")
        proc = subprocess.run([sys.executable, "-c", "from verification_common import validated_candidate; validated_candidate()"],
            cwd=HERE, env={**os.environ, "PYTHONPATH": str(_project_file(_PROJECT_ROOT, ROOT / "src")), "PYTHONDONTWRITEBYTECODE": "1"}, capture_output=True)
        require(proc.returncode != 0 and str(terminal).encode() in proc.stderr and b"FileNotFoundError" in proc.stderr,
            "实际验证装配未在本轮缺终态时拒绝")
        log = proc.stdout + proc.stderr
        (_project_file(_PROJECT_ROOT, HERE / "VALIDATION-MISSING-TERMINAL-REJECTION.log")).write_bytes(log)
        files[str(INPUTS)] = pin(INPUTS)
        check_files(files)
        save(TOOLS, {"complete": True, "files": files, "decoded_public_inputs": len(panel),
            "decoded_original_requests": 39, "factory_pickle_roundtrip": True, "resource_unknown_rejected": True,
            "real_missing_terminal_exit_code": proc.returncode, "real_missing_terminal": str(terminal),
            "real_missing_terminal_log_sha256": hashlib.sha256(log).hexdigest(),
            "planned_equivalence_score_attempts": expected_scores, "planned_original_deadline_service_choose": 59,
            "cpu_nice": os.getpriority(os.PRIO_PROCESS, 0), "background_io_actual_success": True,
            "new_scores_compilations_worlds_tables_HTTP_models_compute_workers": 0,
            "candidate_equivalence_deadline_strength_or_online_admitted": False})
        print(json.dumps({"prepared": True, "public_cases": len(panel), "deduplicated_rows": len(duplicate_rows),
            "original_requests": 39, "planned_scores": expected_scores, "new_scores_or_compilations": 0}), flush=True)


if __name__ == "__main__":
    main()
