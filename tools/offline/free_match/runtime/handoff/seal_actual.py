"""T199实际自然交接只读封存；只调ps/lsof，不启动owner、统计或网络。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t199-four-step-execution-1/runtime/handoff'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import json
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
import release_gate as gate

BASE=_project_file(_PROJECT_ROOT, '.private/t199-four-step-execution/runtime-workspace')
STAGE=_project_file(_PROJECT_ROOT, '.private/t199-four-step-execution/runtime-workspace/natural-handoff-002')


def command(args):
    """只读系统观测；失败保持未知，不能猜实际进程或锁。"""
    if args[0] not in ('ps','lsof'):raise gate.GateError('封存只准ps/lsof')
    result=subprocess.run(args,capture_output=True,text=True,timeout=15)
    if result.returncode:raise gate.GateError('系统观测失败:'+args[0])
    return result.stdout


def process(pid,expected):
    """PID和确切入口同时匹配，排除历史PID复用。"""
    raw=command(['ps','-p',str(pid),'-o','pid=,ppid=,nice=,stat=,command='])
    if expected not in raw:raise gate.GateError('实际命令不符:'+str(pid))
    return {'pid':pid,'expected_entry':expected,'actual_command_confirmed':True,'observation':raw.strip()}


def lsof(pid):
    """只保存cwd及三锁字段，避免复制其他打开文件或环境。"""
    raw=command(['lsof','-n','-P','-p',str(pid)])
    return [line for line in raw.splitlines() if ' cwd ' in line or any('/'+name in line for name in ('controller.lock','postprocess.lock','worker.lock'))]


def main():
    """成功交接收据与当前首房状态分开；不得把players_running当首房合格。"""
    plan=gate.read_json(_project_file(_PROJECT_ROOT, STAGE/'PLAN.json'));spec_path=Path(plan['spec_path']);spec=gate.read_json(spec_path)
    if gate.pin(spec_path)!=plan['spec_pin']:raise gate.GateError('实际使用spec漂移')
    root_check=gate.preflight(spec);root=Path(spec['release_root']);state=Path(spec['shared']['state_dir'])
    boundary=gate.read_json(_project_file(_PROJECT_ROOT, STAGE/'NATURAL-BOUNDARY.json'));reaper=gate.read_json(_project_file(_PROJECT_ROOT, STAGE/'REAPER-CLOSED.json'))
    if boundary['complete'] is not True or boundary['verified']['unique_tables']!=10:raise gate.GateError('旧真实房界不闭')
    if any(type(boundary['compute'].get(key)) is not int or boundary['compute'][key]!=0 for key in gate.RESOURCE_COUNTS):raise gate.GateError('旧12资源不零')
    if not reaper['complete'] or not reaper['singleton_released_by_old_pid_exit_verified'] or reaper['players_signalled']!=0:raise gate.GateError('旧空闲worker回收未闭')
    status=gate.read_json(state/'STATUS.json');control=gate.read_json(state/'control.json');watch=status['controller_pid'];player=status['active_children']['free']
    entry=str(root/'tools/offline/free_match/runtime/controller.py')
    watch_process=process(watch,entry+' watch');player_process=process(player,str(root/'scripts/run_auto_match.py'))
    old_batch=Path(plan['old_batch']);adopted_start=gate.read_json(old_batch/'POSTPROCESS-START.json');worker=adopted_start['worker_pid']
    worker_process=process(worker,entry+' worker');locks={str(pid):lsof(pid) for pid in (watch,player,worker)}
    owner_inode=Path(spec['shared']['owner_lock']).stat().st_ino
    for pid in (watch,player):
        rows=[row for row in locks[str(pid)] if row.endswith(spec['shared']['owner_lock'])]
        if len(rows)!=1 or str(owner_inode) not in rows[0].split():raise gate.GateError('当前owner FD不是同inode')
        if not any(row.endswith(str(root)) and ' cwd ' in row for row in locks[str(pid)]):raise gate.GateError('当前玩家/controller cwd不是新根')
    if any(row.endswith(spec['shared']['owner_lock']) for row in locks[str(worker)]):raise gate.GateError('后台错误继承owner FD')
    if not any(row.endswith(spec['shared']['worker_lock']) for row in locks[str(worker)]):raise gate.GateError('后台未持原singleton')
    batch=state/('batch-%03d'%status['batch']);runs=list((batch/'session/audit/runs').glob('*'))
    if len(runs)!=1:raise gate.GateError('新首房run不唯一')
    manifest=gate.read_json(runs[0]/'manifest.json')['payload'];release=manifest['policy_release']
    if release['release_package_id']!=spec['identity']['package_ids']['free'] or manifest['policy_version']!=spec['identity']['free_strategy']:
        raise gate.GateError('首房实际自由赛包不符')
    pins={name:{'path':str(_project_file(_PROJECT_ROOT, STAGE/name)),'pin':gate.pin(_project_file(_PROJECT_ROOT, STAGE/name))} for name in
        ('PLAN.json','RESERVATION.json','APPROVAL.json','ACTIVATION-INTENT.json','NATURAL-BOUNDARY.json','DISPATCHED.json',
         'REAPER-DISPATCHED.json','REAPER-CLOSED.json','IDLE-WORKER-SIGNAL-INTENT.json')}
    gate.save_exclusive(_project_file(_PROJECT_ROOT, STAGE/'HANDOFF-ACTUAL-CLOSED.json'),{
        'schema':'t199-natural-handoff-actual-close/1','complete':True,'at_unix':time.time(),'spec_pin':gate.pin(spec_path),
        'root_verified_files':root_check['verified_files'],'release_root':str(root),'owner_same_inode':owner_inode,
        'continuous_FD_scope':'预约进程取得旧自然释放的同一锁后，FD连续传新watch，再传新player；不声称旧watch到预约共用同一open description',
        'actual_processes':{'watch':watch_process,'player':player_process,'worker':worker_process},'actual_cwd_lock_rows':locks,
        'source_receipts':pins,'old_058_boundary':boundary,'idle_old_worker_reaping':reaper,
        'adopted_old_job':{'directory':str(old_batch),'source_root':spec['active_root'],'start_pin':gate.pin(old_batch/'POSTPROCESS-START.json'),
            'worker_pid':worker,'already_STARTED_jobs_never_repeated':True,'postprocess_complete_at_snapshot':(old_batch/'POSTPROCESS-CLOSED.json').exists()},
        'current_new_control':control,'first_room':{'batch':status['batch'],'run_id':runs[0].name,'actual_policy':manifest['policy_version'],
            'actual_package_id':release['release_package_id'],'actual_core_id':release['candidate_identity']['candidate_id'],
            'actual_rules_source_hash':release['rules_source_hash'],'M':manifest['max_games'],'Rounds':manifest['rounds_per_game'],
            'SSE_effective':manifest['sse_effective'],'discard_pacing_enabled':manifest['discard_pacing_enabled'],
            'first_room_light_gate_pending':not(batch/'LIGHT-GATE.json').exists(),'full_postprocess_does_not_block_next_room':True},
        'observer_HTTP_Token_scores_spawns_signals':0,'observer_source_pin':gate.pin(Path(__file__))})
    print({'complete':True,'watch':watch,'player':player,'worker':worker,'old_tables':10,'resources_zero':True,
        'handoff_receipt':str(_project_file(_PROJECT_ROOT, STAGE/'HANDOFF-ACTUAL-CLOSED.json')),'first_room_pending':True})


if __name__=='__main__':main()
