"""一次性研究接续：等指定旧读回真实结束，再显式恢复零桌开发派发。

不负责官方比赛，不是自由赛watchdog，也不重试任何失败或已开始的桌。
"""

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
import asyncio
import os
import subprocess
import time
from pathlib import Path

from common import HERE, OLD, pin, save
import t185_close_development as dev
from readout_compat import addon_files, prior_resource_evidence
from dispatch_with_readout_compat import main as dispatch, require_zero_table_recovery


def expected_reader_live(pid):
    """只检查指定PID的程序身份，不打印全系统命令或认证参数。"""
    result=subprocess.run(["ps","-p",str(pid),"-o","command="],text=True,capture_output=True)
    return result.returncode==0 and result.stdout.strip().endswith("close_prior_with_readout_compat.py") and "python" in result.stdout.lower()


async def main():
    """冻结自己的START后等待；旧读回没有有效资源终态则停止，不盲目续评。"""
    if os.getpriority(os.PRIO_PROCESS,0)<15:
        os.nice(15-os.getpriority(os.PRIO_PROCESS,0))
    source=Path(__file__).resolve()
    files={**addon_files(),str(source):pin(source)}
    require_zero_table_recovery()
    observation,_=dev.read(_project_file(_PROJECT_ROOT, HERE / "LIVE-READOUT-RECOVERY-007.json"))
    pid=observation["actual_expected_readout_pid"]
    directory=_project_file(_PROJECT_ROOT, HERE / "readout-recovery-supervision")
    directory.mkdir(exist_ok=False)
    save(directory / "START.json",{"pid":os.getpid(),"prior_reader_pid":pid,"prior_reader_live_at_start":expected_reader_live(pid),
        "files":files,"nice":os.getpriority(os.PRIO_PROCESS,0),"unix_seconds":time.time(),
        "new_table_starts":0,"official_players_signalled":False,"not_official_free_watchdog":True})
    try:
        number=0
        while expected_reader_live(pid):
            dev.require(all(pin(Path(p))==h for p,h in files.items()),"等待期间研究兼容工具漂移")
            save(directory / f"WAIT-{number:04d}.json",{"prior_reader_pid":pid,"expected_command_live":True,
                "old_resource_closed_exists":(OLD / "RESOURCE-SCHEDULING-CLOSED.json").exists(),
                "scores_read":False,"new_table_starts":0,"unix_seconds":time.time()})
            number+=1
            await asyncio.sleep(30)
        closure,closure_pin=prior_resource_evidence(pin(OLD / "DEVELOPMENT-CLOSED.json"),pin(OLD / "DEVELOPMENT-PLAN.json"))
        dev.require(closure["complete"],"旧资源不是已成功闭合")
        save(directory / "PRIOR-READER-CLOSED.json",{"prior_reader_pid":pid,"expected_command_absent":True,
            "old_resource_pin":closure_pin,"new_table_starts":0,"old_scores_read":False,"unix_seconds":time.time()})
        await dispatch("development")
        dev.require(all(pin(Path(p))==h for p,h in files.items()),"接续执行期间工具漂移")
        save(directory / "CLOSED.json",{"complete":True,"new_development_dispatch_closed_pin":pin(_project_file(_PROJECT_ROOT, HERE / "development-dispatch/CLOSED.json")),
            "resources_released":True,"strength_or_deadline_admission":False,"unix_seconds":time.time()})
    except BaseException as error:
        save(directory / "FAILED.json",{"failure":{"type":type(error).__name__,"message":str(error)},
            "children_signalled":False,"automatic_retry":False,"unix_seconds":time.time()})
        raise


if __name__ == "__main__":
    asyncio.run(main())
