"""事前生成T185独立确认工具；复用已核规则推进、收据和来源统计，不选择候选。"""

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
from pathlib import Path

from common import HERE, OLD, pin, save


def function(path, name):
    """保留原函数源码；只按列明的T185命名／资源／判据差异生成新文件。"""
    raw = path.read_text()
    tree = ast.parse(raw)
    node = next(n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
    return "\n".join(raw.splitlines()[node.lineno - 1:node.end_lineno]) + "\n"


def main():
    """不读取完整桌成绩或生成确认世界；所有新文件排他创建并留来源摘要。"""
    for name in ("t185_run_confirmation.py", "t185_close_confirmation.py", "run_confirmation_workers.py",
                 "CONFIRMATION-TOOLS-PREPARED.json"):
        assert not (_project_file(_PROJECT_ROOT, HERE / name)).exists(), "已存在的准备或失败不得覆盖"
    run = function(OLD / "run_confirmation.py", "run_table").replace("t182-confirmation", "t185-confirmation")
    run = run.replace("settlement_sink=settlements.append)", "settlement_sink=settlements.append, focal_seat=rotation)")
    run_header = '''"""T185确认原桌；复用已核完整八单局推进，新增起手白数只作赛后分层。"""
import gzip
import json
import shutil
import time
from dataclasses import asdict
from pathlib import Path
from common import HERE, ROOT, save as new_json
import t185_close_development as dev
import t185_run_development as runtime
from t185_prepare_confirmation import PLAN

'''
    (_project_file(_PROJECT_ROOT, HERE / "t185_run_confirmation.py")).write_text(run_header + run)
    base = OLD / "close_confirmation.py"
    snippets = [function(base, n).replace("t182-confirmation", "t185-confirmation").replace("t182-development", "t185-development")
                for n in ("preflight", "account", "bootstrap_interval", "summarize")]
    snippets[2] = snippets[2].replace("20261004", "20261005")
    snippets[3] = snippets[3].replace("net_signal, opportunity = interval[0] > 0, len(large_positive) >= 2",
        "net_signal, opportunity = interval[0] > 0 and means['net'] >= 0.5, len(large_positive) >= 2")
    snippets[3] = snippets[3].replace('"independent_strength_evidence_passed": net_signal and opportunity',
        '"independent_strength_evidence_passed": net_signal')
    readout = function(base, "_readout").replace("t182-natural-confirmation-closed/2", "t185-natural-confirmation-closed/1")
    readout = readout.replace("resource_files = resources.confirmation_worker_evidence(plan, plan_pin)",
        "resource_files = confirmation_worker_evidence(plan, plan_pin)")
    readout = readout.replace("repair.score_receipts", "dev.score_receipts")
    start = readout.index('    dependencies = dict(plan["development_resource_evidence_files"])')
    stop = readout.index('    result = {', start)
    readout = readout[:start] + '''    for path, expected in plan["development_evidence_files"].items():
        dev.require(dev.pin(Path(path)) == expected, "确认期间开发原证据漂移:" + path)
''' + readout[stop:]
    readout = readout.replace('"development_resource_closed_pin": plan["development_resource_closed_pin"]',
        '"development_dispatch_closed_pin": plan["development_dispatch_closed_pin"]')
    header = '''"""T185独立确认：1024原桌全闭后一次读回，128来源聚类，不继承上线资格。"""
import argparse
import json
import random
from fractions import Fraction
from pathlib import Path
from common import HERE
import t185_close_development as dev
from t185_prepare_confirmation import PLAN, CONTRACT, background_priority, new_json, postprocess_lock, read_confirmation_plan, confirmation_worker_evidence
OUTPUT = HERE / "CONFIRMATION-CLOSED.json"

'''
    footer = '''
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    background_priority()
    with postprocess_lock("confirmation_readout"):
        _readout(args.preflight_only)
'''
    (_project_file(_PROJECT_ROOT, HERE / "t185_close_confirmation.py")).write_text(header + "\n".join(snippets) + "\n" + readout + footer)
    worker = (_project_file(_PROJECT_ROOT, HERE / "run_development_workers.py")).read_text()
    worker = worker.replace("import t185_run_development as runtime", "import t185_run_confirmation as runtime")
    worker = worker.replace("import t185_close_development as reader", "import t185_prepare_confirmation as reader")
    start = worker.index('    old_terminal = OLD / "RESOURCE-SCHEDULING-CLOSED.json"')
    stop = worker.index('    lock_path =', start)
    worker = worker[:start] + '''    old_terminal = HERE / "development-dispatch/CLOSED.json"
    reader.require_development_dispatch()
''' + worker[stop:]
    worker = worker.replace('"DEVELOPMENT-PLAN.json"', '"CONFIRMATION-PLAN.json"')
    worker = worker.replace('        plan = json.loads(plan_path.read_text())\n        reader.validate_plan(plan)\n        reader.frozen(plan)',
        '        with reader.postprocess_lock("confirmation_start_verification"):\n            plan, _ = reader.read_confirmation_plan(verify_development_evidence=True)')
    worker = worker.replace('range(1, 33)', 'range(1, 129)')
    worker = worker.replace('"development-workers"', '"confirmation-workers"').replace('"natural-development"', '"natural-confirmation"')
    worker = worker.replace('task["arm"], plan)', 'task["arm"], plan, plan_pin)')
    (_project_file(_PROJECT_ROOT, HERE / "run_confirmation_workers.py")).write_text(worker)
    targets = [_project_file(_PROJECT_ROOT, HERE / n) for n in ("t185_run_confirmation.py", "t185_close_confirmation.py", "run_confirmation_workers.py")]
    for path in targets:
        ast.parse(path.read_bytes(), filename=str(path))
    save(_project_file(_PROJECT_ROOT, HERE / "CONFIRMATION-TOOLS-PREPARED.json"), {"complete": True,
        "origin_files": {str(p): pin(p) for p in (OLD / "run_confirmation.py", base, _project_file(_PROJECT_ROOT, HERE / "run_development_workers.py"))},
        "files": {str(p): pin(p) for p in (Path(__file__), *targets)},
        "changes": ["T185命名及当前读回器", "追加白数仅教师分层", "bootstrap seed20261005",
            "事前均值至少0.5且来源区间下端>0", "大牌跨来源证据单列，不另加准入条件", "T185开发完整资源绑定"],
        "new_scores_worlds_tables": 0, "candidate_selected": False})


if __name__ == "__main__":
    main()
