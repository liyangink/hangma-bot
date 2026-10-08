"""T199一次自然交接：只切不可变入口；执行需根审核的确切预约/工具批准。"""
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

import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
import release_gate as gate
from controller import write_state

NEW_REL='tools/offline/free_match/runtime/controller.py'
OWNER_ENV='HM_T199_OWNER_FD'


def probe(spec_path,side,*,boundary=None,worker_pid=None):
    """不同root使用不同-I进程；只允许探针内ps，不加载凭据或运行watch。"""
    spec=gate.read_json(spec_path);root=Path(spec['release_root'] if side=='new' else spec['active_root'])
    env=dict(os.environ);env['PYTHONPATH']=os.pathsep.join((str(root/'src'),str(root)));env['PYTHONDONTWRITEBYTECODE']='1'
    command=[sys.executable,'-I','-B',str(_project_file(_PROJECT_ROOT, HERE/'probe.py')),side,'--spec',str(spec_path)]
    if boundary is not None:command+=['--boundary',str(boundary)]
    if worker_pid is not None:command+=['--worker-pid',str(worker_pid)]
    result=subprocess.run(command,cwd=root,env=env,capture_output=True,text=True,timeout=30)
    if result.returncode:raise gate.GateError('隔离'+side+'预检失败:'+result.stderr[-1800:])
    return json.loads(result.stdout)


def check_adoptions(spec,old):
    """逐实际review批次绑定；后来出现的房保持缺依赖，不自动改已冻spec。"""
    if old['unknown_jobs']:raise gate.GateError('旧任务PLAN/配置未知，不重做')
    rows=spec.get('adopted_jobs',[])
    for actual in old['adoptable_jobs']:
        match=[row for row in rows if row['directory']==actual['directory']]
        if len(match)!=1 or any(match[0].get(key)!=actual[key] for key in ('plan_pin','release_root','config_path','config_pin')):
            raise gate.GateError('旧新房需明确外部adoption并正常重签spec:'+actual['directory'])


def tool_pins():
    """确切薄入口和只读探针由根审；既有controller/gate已经新根冻结。"""
    return {str(path):gate.pin(path) for path in (_project_file(_PROJECT_ROOT, HERE/'handoff.py'),_project_file(_PROJECT_ROOT, HERE/'probe.py'),_project_file(_PROJECT_ROOT, HERE.parent/'release_gate.py'),_project_file(_PROJECT_ROOT, HERE.parent/'controller.py'))}


def prepare(spec_path,stage):
    """仅预检和持久预约；不写旧开关，不获取活跃三锁，不启动参赛者。"""
    spec_path=spec_path.resolve();stage.mkdir(parents=True,exist_ok=False)
    spec=gate.read_json(spec_path);new=probe(spec_path,'new');old=probe(spec_path,'old')
    gate.save_exclusive(stage/'READONLY-PRECHECK.json',{'new':new,'old':old,'Token_reads':0,'live_mutations':0})
    check_adoptions(spec,old)
    plan={'schema':'t199-single-natural-handoff/1','spec_path':str(spec_path),'spec_pin':gate.pin(spec_path),
        'tool_pins':tool_pins(),'old_source_pins':old['old_source_pins'],'old_identity':old['identity'],
        'old_control_path':old['control_path'],'old_batch':old['latest_directory'],'old_plan_pin':old['latest_plan_pin'],
        'shared':spec['shared'],'release_root':spec['release_root'],'adopted_jobs':spec['adopted_jobs'],
        'old_ROOT_kept':spec['active_root'],'natural_players_only':True,'postprocess_never_blocks_new_match':True}
    gate.save_exclusive(stage/'PLAN.json',plan)
    gate.save_exclusive(stage/'RESERVATION.json',{'plan_pin':gate.pin(stage/'PLAN.json'),'complete':True,'live_mutations':0,'at_unix':time.time()})
    return plan


def approved(stage,approval_path):
    """有意允许范围只来自根绑定的明确票据；缺票据0控制写入/0启动。"""
    plan=gate.read_json(stage/'PLAN.json');approval=gate.read_json(approval_path)
    if not (approval.get('approved_for_natural_handoff') is True and approval.get('pause_old_next_room') is True
            and approval.get('stop_only_idle_old_worker') is True and approval.get('start_new_frozen_controller') is True
            and approval.get('plan_pin')==gate.pin(stage/'PLAN.json') and approval.get('reservation_pin')==gate.pin(stage/'RESERVATION.json')
            and approval.get('tool_pins')==tool_pins() and plan['tool_pins']==tool_pins()):raise gate.GateError('根未批准确切交接预约/动作/工具')
    if gate.pin(Path(plan['spec_path']))!=plan['spec_pin']:raise gate.GateError('已预约spec漂移')
    return plan


def idle_safe(row):
    """只有实际旧worker、后台禁下一项、全部本人START自然闭合且无子任务才可回收。"""
    return (type(row.get('pid')) is int and row['pid']>0 and row.get('identity',{}).get('expected_command_live') is True
        and row.get('background_enabled') is False and row.get('background_state') in ('waiting','waiting_existing_postprocess')
        and row.get('all_started_tasks_naturally_closed') is True and row.get('descendants')==[])


def execute(stage,approval_path,*,launcher=subprocess.Popen,inspector=probe):
    """唯一owner FD自然接棒；意图落盘后任何不确定均拒绝重启，不向玩家发信号。"""
    plan=approved(stage,approval_path);spec_path=Path(plan['spec_path']);spec=gate.read_json(spec_path)
    with (stage/'activation.lock').open('a+') as guard:
        fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (stage/'ACTIVATION-INTENT.json').exists():raise gate.GateError('已有交接意图，核真实状态，不自动重试')
        inspector(spec_path,'new');old=inspector(spec_path,'old');check_adoptions(spec,old)
        if old['identity']!=plan['old_identity'] or old['old_source_pins']!=plan['old_source_pins'] or old['latest_directory']!=plan['old_batch'] or old['latest_plan_pin']!=plan['old_plan_pin']:
            raise gate.GateError('旧房或旧动态运行闭包变化，重新准备')
        gate.save_exclusive(stage/'ACTIVATION-INTENT.json',{'approval_pin':gate.pin(approval_path),'at_unix':time.time()})
        control_path=Path(plan['old_control_path']);before=gate.read_json(control_path)
        gate.save_exclusive(stage/'OLD-CONTROL-BEFORE.json',before)
        write_state(control_path,{**before,'continue_after_cycle':False})
        gate.save_exclusive(stage/'OLD-NEXT-ROOM-PAUSED.json',{'continue_after_cycle':False,'player_signal_sent':False})
        with Path(plan['shared']['owner_lock']).open('a+') as owner:
            while True:
                try:fcntl.flock(owner,fcntl.LOCK_EX|fcntl.LOCK_NB);break
                except BlockingIOError:
                    write_state(stage/'STATUS.json',{'phase':'waiting_old_natural_boundary','at_unix':time.time()});time.sleep(2)
            boundary=inspector(spec_path,'old',boundary=Path(plan['old_batch']))
            if boundary['identity']!=plan['old_identity'] or boundary['old_source_pins']!=plan['old_source_pins']:raise gate.GateError('旧ROOT动态依赖漂移')
            check_adoptions(spec,boundary);gate.save_exclusive(stage/'NATURAL-BOUNDARY.json',boundary['boundary'])
            before_background=gate.read_json(control_path)
            write_state(control_path,{**before_background,'background_enabled':False})
            gate.save_exclusive(stage/'OLD-BACKGROUND-NEXT-DISABLED.json',{'current_task_natural_only':True,'old_worker_pid':boundary['background']['worker_pid']})
            inspector(spec_path,'new');state=Path(spec['shared']['state_dir']);state.mkdir(parents=True,exist_ok=True)
            global_intent=state/'NATURAL-HANDOFF-DISPATCH-INTENT.json'
            gate.save_exclusive(global_intent,{'stage':str(stage),'plan_pin':gate.pin(stage/'PLAN.json'),'spec_pin':plan['spec_pin']})
            gate.verify_owner_fd(owner.fileno(),Path(plan['shared']['owner_lock']))
            environment=dict(os.environ);environment['PYTHONPATH']=os.pathsep.join((str(Path(spec['release_root'])/'src'),spec['release_root']))
            environment['PYTHONDONTWRITEBYTECODE']='1';environment[OWNER_ENV]=str(owner.fileno())
            for key in ('HM_T199_ADOPT_STATE','HM_T199_ROLLBACK_ACTIVATION','HM_WATCHDOG_OWNER_FD'):environment.pop(key,None)
            command=[sys.executable,'-B',str(Path(spec['release_root'])/NEW_REL),'watch','--spec',str(spec_path)]
            with (stage/'NEW-CONTROLLER.log').open('x') as log:
                child=launcher(command,cwd=Path(spec['release_root']),env=environment,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,pass_fds=(owner.fileno(),))
            gate.save_exclusive(stage/'DISPATCHED.json',{'controller_pid':child.pid,'owner_fd_inherited':True,'actual_watch_live_pending':True,'at_unix':time.time()})
            # 后台reaper不继承owner FD，等待当前统计不会挡新自由赛；意图未知不自动重发。
            reaper_env=dict(environment);reaper_env.pop(OWNER_ENV,None)
            gate.save_exclusive(stage/'REAPER-DISPATCH-INTENT.json',{'old_worker_pid':boundary['background']['worker_pid'],'at_unix':time.time()})
            with (stage/'REAPER.log').open('x') as log:
                reaper=launcher([sys.executable,'-B',str(_project_file(_PROJECT_ROOT, HERE/'handoff.py')),'reap-idle-worker','--stage',str(stage),'--approval',str(approval_path)],
                    cwd=Path(spec['active_root']),env=reaper_env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            gate.save_exclusive(stage/'REAPER-DISPATCHED.json',{'pid':reaper.pid,'does_not_block_new_match':True,'owner_FD_not_inherited':True})
            write_state(stage/'STATUS.json',{'phase':'successor_dispatched','controller_pid':child.pid,'reaper_pid':reaper.pid,'first_room_pending':True})
            return {'controller_pid':child.pid,'reaper_pid':reaper.pid,'owner_fd_continuously_inherited':True,'players_terminated':0}


def reap(stage,approval_path,*,max_seconds=1800):
    """仅回收已空闲旧后台；拿postprocess锁后再核PID/子任务/自然CLOSED，不杀忙任务。"""
    plan=approved(stage,approval_path);spec_path=Path(plan['spec_path']);pid=gate.read_json(stage/'OLD-BACKGROUND-NEXT-DISABLED.json')['old_worker_pid'];started=time.monotonic()
    with Path(plan['shared']['postprocess_lock']).open('a+') as postprocess:
        while time.monotonic()-started<max_seconds:
            try:fcntl.flock(postprocess,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:time.sleep(2);continue
            try:
                row=probe(spec_path,'old',worker_pid=pid)['idle_worker']
                if row['identity']['pid_exists'] is False:
                    gate.save_exclusive(stage/'REAPER-CLOSED.json',{'complete':True,'worker_already_absent':True,'signal_sent':False});return
                if idle_safe(row):
                    gate.save_exclusive(stage/'IDLE-WORKER-SIGNAL-INTENT.json',{'pid':pid,'evidence':row,'signal':'SIGTERM','players_signalled':0,'at_unix':time.time()})
                    os.kill(pid,signal.SIGTERM)
                    gone=False
                    for _ in range(20):
                        if probe(spec_path,'old',worker_pid=pid)['idle_worker']['identity']['pid_exists'] is False:
                            gone=True;break
                        time.sleep(.25)
                    gate.save_exclusive(stage/'REAPER-CLOSED.json',{'idle_worker_SIGTERM_sent':True,'pid':pid,'current_tasks_naturally_closed':True,
                        'complete':gone,'singleton_released_by_old_pid_exit_verified':gone,'players_signalled':0});return
                if row['identity']['expected_command_live'] is not True:
                    raise gate.GateError('旧worker PID复用或未知，不发信号')
            finally:fcntl.flock(postprocess,fcntl.LOCK_UN)
            time.sleep(2)
    gate.save_exclusive(stage/'REAPER-CLOSED.json',{'complete':False,'failure':'busy_or_unknown_at_bounded_timeout','signal_sent':False,'next_match_not_blocked':True})


def main():
    """prepare只写T199预约；execute/reap须绑定根审批，当前研发不调用真实动作。"""
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=('prepare','execute','reap-idle-worker'))
    parser.add_argument('--spec',type=Path);parser.add_argument('--stage',type=Path,required=True);parser.add_argument('--approval',type=Path);args=parser.parse_args()
    if not any(part.startswith('t199-') for part in args.stage.resolve().parts):raise gate.GateError('只允许T199新收据目录')
    try:
        if args.command=='prepare':value=prepare(args.spec,args.stage.resolve())
        elif args.command=='execute':value=execute(args.stage.resolve(),args.approval.resolve())
        else:value=reap(args.stage.resolve(),args.approval.resolve())
        print(json.dumps(value,ensure_ascii=False))
    except Exception as error:
        if args.stage.is_dir():write_state(args.stage/'STATUS.json',{'phase':'failed_preserve_intent_no_auto_retry','type':type(error).__name__,'reason':str(error),'at_unix':time.time()})
        raise


if __name__=='__main__':main()
