"""接线验收独占统计锁：暂停接新统计，不停止自由赛；实际正常CPU优先级。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t179-production-wiring-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import fcntl, json, os, subprocess, sys, time
from pathlib import Path
ROOT=_PROJECT_ROOT
HERE=Path(__file__).resolve().parent
CONTROL=_project_file(_PROJECT_ROOT, '.private/t170-free-watchdog/control.json')
def put(path, value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def change(value):
    state=json.loads(CONTROL.read_text());state['background_enabled']=value
    temp=CONTROL.with_name('t179-control-'+str(os.getpid())+'.tmp')
    put(temp,state);os.replace(temp,CONTROL)
def main():
    name=sys.argv[1];command=sys.argv[2:]
    assert name.replace('-','').isalnum() and command
    directory=_project_file(_PROJECT_ROOT, HERE/name);directory.mkdir(exist_ok=False)
    original=json.loads(CONTROL.read_text())['background_enabled']
    change(False)
    try:
        with (_project_file(_PROJECT_ROOT, ROOT/'.private/t165-live-watchdog/postprocess.lock')).open('a+') as lock:
            print('waiting_existing_postprocess',flush=True)
            fcntl.flock(lock,fcntl.LOCK_EX)
            assert os.nice(0)==0,'原截止验证必须保持线上正常CPU优先级'
            put(directory/'START.json',{'command':command,'at_unix':time.time(),'cpu_nice':os.nice(0),'official_players_terminated':False})
            begin=time.monotonic()
            with (directory/'OUTPUT.log').open('x') as stream:
                proc=subprocess.run(command,cwd=_project_file(_PROJECT_ROOT, ROOT/'.private/t179-wiring/workspace'),stdout=stream,stderr=subprocess.STDOUT,pass_fds=(lock.fileno(),))
            put(directory/'CLOSED.json',{'actual_exit_code':proc.returncode,'elapsed_seconds':time.monotonic()-begin,'official_players_terminated':False})
            print(json.dumps({'name':name,'exit_code':proc.returncode}),flush=True)
            return proc.returncode
    finally:
        change(original)
        put(directory/'CONTROL-RESTORED.json',{'background_enabled':original,'free_continue_enabled':json.loads(CONTROL.read_text())['continue_after_cycle']})
if __name__=='__main__':raise SystemExit(main())
