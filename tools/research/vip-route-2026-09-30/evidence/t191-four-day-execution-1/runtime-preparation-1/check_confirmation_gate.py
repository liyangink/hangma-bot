"""零评分检查确认到编译的连接；合成数据只验证拒绝行为，不代表候选成绩。"""
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

import copy
import hashlib
import json
import math
import os
import subprocess
import sys
from pathlib import Path

from confirmation_gate import strength_gate
from prepare_runtime_inputs import HERE, PLAN, ROOT, background_priority, pin, require, save


def main():
    """检查未知/跨零/错身份/少来源不能提前编译，并调用真实入口验证未闭合拒绝。"""
    background_priority()
    identity = {"candidate_id": "synthetic-structure-check-only"}
    roots = [{"root_id": f"synthetic-{i}"} for i in range(1, 129)]
    plan = {"schema": "t191-single-confirmation/1", "candidates": [{"identity": identity}],
        "root_indices": list(range(1, 129)), "planned_table_instances": 1024, "roots": roots,
        "minimum_mean_points_per_complete_table": 0.5, "strictly_positive_lower95_required": True}
    sources = [{"root": i, "root_id": roots[i - 1]["root_id"],
        "paired_tables": [{"rotation": r, "delta": {"net": 256 if i == 1 and r == 0 else 0}} for r in range(4)],
        "four_seat_delta_sums": {"net": 256 if i == 1 else 0}} for i in range(1, 129)]
    row = {"identity": identity, "sources": sources, "mean_delta_per_complete_table": {"net": 0.5},
        "independent_net_bootstrap95": [0.01, 1], "independent_strength_admission": True}
    summary = {"schema": "t191-independent-confirmation-readout/1", "complete": True, "source_stable": True,
        "actual_complete_tables": 1024, "actual_single_hands": 8192, "actual_focal_scores": 1,
        "all_resources_naturally_released": True, "comparisons": [row], "independent_strength_admission": True}
    dispatch = {"complete": True, "failure": None, "resources_released": True,
        "worker_returncodes": [0, 0, 0, 0], "actual_table_calls": 1024, "verified_complete_table_calls": 1024}
    terminal = {"complete": True, "failure": None, "observation_timed_out": False,
        "observed_job_terminal_claimed": True, "actual_reader_exit_code": 0}
    strength_gate(summary, plan, dispatch, terminal)
    variants = (
        ("missing_table", lambda s, p, d, t: s.update(actual_complete_tables=1023)),
        ("missing_hand", lambda s, p, d, t: s.update(actual_single_hands=8191)),
        ("zero_scores", lambda s, p, d, t: s.update(actual_focal_scores=0)),
        ("wrong_candidate", lambda s, p, d, t: s["comparisons"][0].update(identity={"candidate_id": "other"})),
        ("mean_boolean", lambda s, p, d, t: s["comparisons"][0]["mean_delta_per_complete_table"].update(net=True)),
        ("mean_below_gate", lambda s, p, d, t: s["comparisons"][0]["mean_delta_per_complete_table"].update(net=0.49)),
        ("interval_crosses_zero", lambda s, p, d, t: s["comparisons"][0].update(independent_net_bootstrap95=[0, 1])),
        ("interval_nonfinite", lambda s, p, d, t: s["comparisons"][0].update(independent_net_bootstrap95=[0.1, math.nan])),
        ("duplicate_mother", lambda s, p, d, t: s["comparisons"][0]["sources"][1].update(root_id="synthetic-1")),
        ("missing_rotation", lambda s, p, d, t: s["comparisons"][0]["sources"][0]["paired_tables"].pop()),
        ("ledger_mismatch", lambda s, p, d, t: s["comparisons"][0]["sources"][0]["four_seat_delta_sums"].update(net=257)),
        ("resources_unknown", lambda s, p, d, t: d.update(resources_released=None)),
        ("reader_failed", lambda s, p, d, t: t.update(actual_reader_exit_code=1)),
        ("reader_boolean", lambda s, p, d, t: t.update(actual_reader_exit_code=False)),
        ("observation_expired", lambda s, p, d, t: t.update(observation_timed_out=True)),
    )
    passed = []
    for label, mutate in variants:
        values = copy.deepcopy((summary, plan, dispatch, terminal))
        mutate(*values)
        try:
            strength_gate(*values)
        except (ValueError, KeyError, TypeError):
            passed.append(label)
        else:
            raise AssertionError("坏确认数据放行:" + label)
    target = PLAN.with_name("wait-confirmation-001-READBACK-TERMINAL.json")
    require(not target.exists(), "本预检针对当前尚未自然闭合的真实作业；不可在闭合后伪造缺文件")
    env = {**os.environ, "PYTHONPATH": str(_project_file(_PROJECT_ROOT, ROOT / "src")), "PYTHONDONTWRITEBYTECODE": "1"}
    proc = subprocess.run([sys.executable, str(_project_file(_PROJECT_ROOT, HERE / "confirmation_gate.py"))], cwd=ROOT,
        env=env, capture_output=True)
    require(proc.returncode != 0 and str(target).encode() in proc.stderr and b"FileNotFoundError" in proc.stderr,
        "真实入口未在缺终态时拒绝")
    log = proc.stdout + proc.stderr
    (_project_file(_PROJECT_ROOT, HERE / "MISSING-TERMINAL-REJECTION.log")).write_bytes(log)
    save(_project_file(_PROJECT_ROOT, HERE / "GATE-TOOLS-CHECKED.json"), {"complete": True, "synthetic_only_not_candidate_strength": True,
        "negative_checks_passed": passed, "real_gate_exit_code": proc.returncode,
        "real_missing_terminal": str(target), "missing_rejection_log_sha256": hashlib.sha256(log).hexdigest(),
        "files": {str(p): pin(p) for p in (Path(__file__), _project_file(_PROJECT_ROOT, HERE / "confirmation_gate.py"), _project_file(_PROJECT_ROOT, HERE / "prepare_runtime_inputs.py"), PLAN)},
        "cpu_nice": os.getpriority(os.PRIO_PROCESS, 0), "background_io_actual_success": True,
        "new_compilations_scores_worlds_tables_HTTP_models_compute_workers": 0})
    print(json.dumps({"negative_checks": len(passed), "real_gate_rejected_incomplete_confirmation": True,
        "new_scores_or_compilations": 0}), flush=True)


if __name__ == "__main__":
    main()
