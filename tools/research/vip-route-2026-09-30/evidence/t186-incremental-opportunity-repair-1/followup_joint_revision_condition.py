"""只等本批四研究worker自然终态，再读回一次；无续桌、模型或匹配副作用。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t186-incremental-opportunity-repair-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import asyncio
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1')
sys.path.insert(0, str(PRIOR))
from common import ROOT, pin, save
from t185_prepare_confirmation import background_priority


async def main():
    """无新终态时只等；失败原样封存，未知不自动重做。"""
    background_priority()
    out = _project_file(_PROJECT_ROOT, HERE / "joint-revision-condition-followup")
    out.mkdir(exist_ok=False)
    reader = _project_file(_PROJECT_ROOT, HERE / "close_joint_revision_condition.py")
    plan = _project_file(_PROJECT_ROOT, HERE / "JOINT-REVISION-CONDITION-PLAN.json")
    reader_pin, plan_pin = pin(reader), pin(plan)
    save(out / "START.json", {"pid": os.getpid(), "reader_pin": reader_pin, "plan_pin": plan_pin,
        "automatic_next_phase_dispatch": False, "actual_scores_worlds_tables_models_HTTP": 0})
    failure, process, code = None, None, None
    started = time.monotonic()  # 本地等候持续秒，不是官方动作截止时间。
    try:
        terminal = _project_file(_PROJECT_ROOT, HERE / "joint-revision-condition/DISPATCH-CLOSED.json")
        while not terminal.exists():
            assert time.monotonic() - started < 15000, "自然终态仍未知，保留原START不重做"
            await asyncio.sleep(5)
        record = json.loads(terminal.read_text())
        assert record["complete"] and record["all_processes_naturally_waited"], "条件原批自然失败，禁止重做"
        assert pin(reader) == reader_pin and pin(plan) == plan_pin, "读回或冻结计划漂移"
        with (out / "readback.log").open("x") as log:
            process = await asyncio.create_subprocess_exec(sys.executable, str(reader), cwd=ROOT,
                stdout=log, stderr=asyncio.subprocess.STDOUT, env={**os.environ, "PYTHONUNBUFFERED": "1"})
            save(out / "READER-START.json", {"pid": process.pid, "reader_pin": reader_pin})
            code = await process.wait()
        assert code == 0 and pin(reader) == reader_pin and pin(plan) == plan_pin, "一次读回未通过"
    except BaseException as error:
        failure = {"type": type(error).__name__, "message": str(error)}
    save(out / "CLOSED.json", {"complete": failure is None, "failure": failure, "reader_returncode": code,
        "reader_pid": None if process is None else process.pid, "reader_pin": reader_pin, "plan_pin": plan_pin,
        "elapsed_monotonic_seconds": time.monotonic() - started,
        "actual_scores_worlds_tables_models_HTTP": 0, "automatic_next_phase_dispatch": False})
    assert failure is None, str(failure)
    print(json.dumps({"complete": True, "readback_returncode": code}), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
