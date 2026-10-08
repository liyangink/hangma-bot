"""单批事后读回控制器；等待现有派发自然退出，不启动或重试任何牌桌。"""

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
import argparse
import fcntl
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1')
sys.path.insert(0, str(PRIOR))
from common import ROOT, pin, save
from four_worker_campaign import validate
from t185_prepare_confirmation import background_priority


def command(pid):
    """只读实际派发命令；无进程返回None，查询失败保留为异常，不据此重启。"""
    p = subprocess.run(["ps", "-p", str(pid), "-o", "command="], text=True, capture_output=True)
    if p.returncode == 1 and not p.stdout.strip():
        return None
    if p.returncode:
        raise RuntimeError("真实派发进程查询失败")
    return p.stdout.strip()


def main(plan_path):
    """自然闭合后顺序核全部原评分及来源分账；任何失败终止后续，不自动加样本。"""
    background_priority()
    plan, plan_pin, _ = validate(plan_path)
    original = Path(plan["dispatch_directory"])
    start = json.loads((original / "START.json").read_text())
    dispatcher_pid = start["pid"]
    directory = _project_file(_PROJECT_ROOT, HERE / Path(plan["dispatch_directory"]).name.replace("-dispatch", "-followup"))
    directory.mkdir(exist_ok=False)
    with (_project_file(_PROJECT_ROOT, HERE / ".stage-readback-owner.lock")).open("a+") as owner:
        fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        actual = command(dispatcher_pid)
        assert actual is not None and "four_worker_campaign.py" in actual and Path(plan_path).name in actual
        save(directory / "START.json", {"pid": os.getpid(), "dispatcher_pid": dispatcher_pid,
            "dispatcher_start_pin": pin(original / "START.json"), "actual_dispatcher_command_at_start": actual,
            "plan_pin": plan_pin, "observer_pin": pin(Path(__file__)), "new_tables_or_scores": 0,
            "next_stage_auto_dispatch": False})
        phases, failure = [], None
        try:
            while True:
                actual = command(dispatcher_pid)
                if actual is None:
                    break
                assert "four_worker_campaign.py" in actual and Path(plan_path).name in actual
                assert pin(Path(plan_path)) == plan_pin
                time.sleep(5)  # 后台控制器间隔秒；模型工具不在此阻塞等待
            terminal = json.loads((original / "CLOSED.json").read_text())
            assert terminal["complete"] and terminal["resources_released"] and terminal["worker_returncodes"] == [0] * 4
            assert terminal["plan_pin"] == plan_pin and terminal["actual_table_calls"] == plan["planned_table_instances"]
            for name, script in [("full-readback", "staged_readout.py"), ("source-summary", "read_natural_stage.py"), ("cumulative-summary", "read_natural_cumulative.py")]:
                log = directory / (name + ".log")
                save(directory / (name + "-BEFORE.json"), {"script_pin": pin(_project_file(_PROJECT_ROOT, HERE / script)), "plan_pin": plan_pin,
                    "new_scores_worlds_tables_models_HTTP": 0})
                with log.open("x") as stream:
                    result = subprocess.run([sys.executable, str(_project_file(_PROJECT_ROOT, HERE / script)), "--plan", str(Path(plan_path).resolve())],
                        cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
                phases.append({"phase": name, "exit_code": result.returncode, "log_pin": pin(log)})
                assert result.returncode == 0, "读回失败，原日志保留；不重跑牌桌"
            summary = json.loads((original / "SUMMARY.json").read_text())
            assert summary["complete"] and summary["plan_pin"] == plan_pin and summary["natural_strength_or_online_admission"] is False
        except BaseException as error:
            failure = {"type": type(error).__name__, "message": str(error)}
        save(directory / "CLOSED.json", {"complete": failure is None, "failure": failure, "phases": phases,
            "plan_pin": plan_pin, "new_scores_worlds_tables_models_HTTP": 0, "next_stage_auto_dispatch": False})
        if failure:
            raise RuntimeError("小批后续读回失败，保留原件：" + str(failure))
    print(json.dumps({"complete": True, "readback_and_summary": True, "new_tables_or_scores": 0}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    main(parser.parse_args().plan)
