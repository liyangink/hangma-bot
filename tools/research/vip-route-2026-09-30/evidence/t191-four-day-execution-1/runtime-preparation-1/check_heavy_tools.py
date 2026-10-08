"""只验重型工具接线和真实未结束拒绝；不扫逐窗流、不评分、不运行计算服务。"""
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
import difflib
import json
import os
import subprocess
import sys
from pathlib import Path

from prepare_runtime_inputs import HERE, PLAN, PRIOR, ROOT, background_priority, pin, require, save
# 原工具共享依赖位于PRIOR；同名本轮工具必须显式恢复当前目录优先级。
sys.path.insert(0, str(HERE))
from prepare_heavy_development_inputs import GROUPS, development_metadata, tags


def main():
    """语法、已闭开发索引、工作量标签和两个真实CLI拒绝均保存原件。"""
    background_priority()
    names = ("prepare_heavy_development_inputs.py", "probe_heavy_complete_choices.py")
    files = {str(_project_file(_PROJECT_ROOT, HERE / name)): pin(_project_file(_PROJECT_ROOT, HERE / name)) for name in (
        *names, "check_heavy_tools.py", "verification_common.py", "confirmation_gate.py",
        "prepare_runtime_inputs.py", "VALIDATION-TOOLS-CHECKED.json")}
    provenance = []
    for name in names:
        current, original = _project_file(_PROJECT_ROOT, HERE / name), PRIOR / name
        ast.parse(current.read_text(), filename=str(current))
        files[str(original)] = pin(original)
        provenance.append({"original": str(original), "original_pin": pin(original),
            "current": str(current), "current_pin": pin(current),
            "exact_diff": "".join(difflib.unified_diff(original.read_text().splitlines(True),
                current.read_text().splitlines(True), fromfile=str(original), tofile=str(current)))})
    # 原名义窗口从规则分析前起算，三段预算及服务往返计时逐字节保留。
    def hot_region(path):
        text = path.read_text()
        start = text.index("            now = time.monotonic()\n            budget = budget_policy.build")
        end = text.index("            returned = time.monotonic()", start)
        return text[start:end]
    require(hot_region(_project_file(_PROJECT_ROOT, HERE / names[1])) == hot_region(PRIOR / names[1]), "重型原名义计时热区变化")
    metadata, _, development_plan, _, metadata_files = development_metadata()
    require(len(metadata["tables"]) == 256 and len(development_plan["roots"]) == 32 and
        metadata["identity"] == json.loads(PLAN.read_text())["candidates"][0]["identity"],
        "开发索引不属于本轮唯一候选")
    files.update(metadata_files)
    files[str(PLAN)] = pin(PLAN)
    base = {"legal_action_keys": ["discard:西"], "observation": {"chain_piao": 0, "gang_draw": False}, "phase": "draw"}
    ordinary = {"operations", "graph_bytes", "target_evaluations", "waiting_witnesses"}
    require(tags(base) == ordinary and len(GROUPS) == 8, "普通工作量标签错误")
    variants = (
        ("concealed", {**base, "legal_action_keys": ["gang:concealed:西"]}, {"self_gang"}),
        ("added", {**base, "legal_action_keys": ["gang:added:西"]}, {"self_gang"}),
        ("exposed", {**base, "phase": "response", "legal_action_keys": ["gang:exposed:西"]}, {"exposed_gang", "response"}),
        ("replacement", {**base, "observation": {"chain_piao": 0, "gang_draw": True}}, {"replacement"}),
        ("chain", {**base, "observation": {"chain_piao": 2, "gang_draw": False}}, {"replacement"}),
    )
    for name, row, extra in variants:
        require(tags(row) == ordinary | extra, "工作量类别错误:" + name)
    terminal = PLAN.with_name("wait-confirmation-001-READBACK-TERMINAL.json")
    require(not terminal.exists(), "只针对当前真实未结束的确认做拒绝检查，不伪造缺文件")
    env = {**os.environ, "PYTHONPATH": str(_project_file(_PROJECT_ROOT, ROOT / "src")), "PYTHONDONTWRITEBYTECODE": "1"}
    attempts = []
    for name, extra in ((names[0], ()), (names[1], ("--phase", "reference"))):
        proc = subprocess.run([sys.executable, str(_project_file(_PROJECT_ROOT, HERE / name)), *extra], cwd=ROOT, env=env,
            capture_output=True, timeout=30)
        require(proc.returncode != 0 and b"FileNotFoundError" in proc.stderr and str(terminal).encode() in proc.stderr,
            "真实入口未在缺确认终态时拒绝:" + name)
        log = _project_file(_PROJECT_ROOT, HERE / (name.removesuffix(".py") + "-MISSING-TERMINAL.log"))
        with log.open("xb") as stream:
            stream.write(proc.stdout + proc.stderr)
        files[str(log)] = pin(log)
        attempts.append({"tool": name, "actual_exit_code": proc.returncode, "log": str(log), "log_pin": pin(log)})
    require(not any((_project_file(_PROJECT_ROOT, HERE / name)).exists() for name in (
        "development-heavy-inputs", "heavy-complete-reference", "heavy-nominal-deadline-probe")),
        "未结束拒绝仍产生重型输出")
    provenance_path = _project_file(_PROJECT_ROOT, HERE / "HEAVY-HELPER-PROVENANCE.json")
    save(provenance_path, {"schema": "t191-heavy-helper-provenance/1", "files": provenance,
        "nominal_timing_hot_region_exact": True,
        "changes": "T191三块闭合开发绑定；最多32图/动态计费；全新公式全choose等价；原桌逐个绑定释放；研究槽；不增加时限"})
    files[str(provenance_path)] = pin(provenance_path)
    require(all(pin(Path(p)) == expected for p, expected in files.items()), "零评分检查后输入漂移")
    save(_project_file(_PROJECT_ROOT, HERE / "HEAVY-TOOLS-CHECKED.json"), {"complete": True, "files": files,
        "development_metadata_complete_tables": 256, "development_metadata_score_calls": 97566,
        "development_raw_streams_scanned": 0, "synthetic_tags_not_actual_coverage": [v[0] for v in variants],
        "nominal_timing_hot_region_exact": True, "real_incomplete_gate_attempts": attempts,
        "maximum_selected_unique_views": 32, "maximum_planned_reference_score_attempts": 64,
        "maximum_planned_nominal_service_choose": 32,
        "new_rule_analyses_scores_compilations_worlds_tables_HTTP_models_compute_workers": 0,
        "CPU_nice": os.getpriority(os.PRIO_PROCESS, 0), "background_IO_actual_success": True,
        "candidate_runtime_deadline_or_online_admitted": False})
    print(json.dumps({"complete": True, "real_missing_terminal_rejections": len(attempts),
        "new_scores_compilations_or_tables": 0}), flush=True)


if __name__ == "__main__":
    main()
