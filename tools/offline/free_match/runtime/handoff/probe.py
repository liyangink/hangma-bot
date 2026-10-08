"""T199自然交接的隔离只读探针：新/旧根各自独立解释器，不读凭据。"""
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
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=_PROJECT_ROOT
OLD_REL='tools/offline/free_match/legacy/free_watchdog.py'
NEW_REL='tools/offline/free_match/runtime/controller.py'
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import release_gate as gate


def load(name,path):
    """仅导入指定源码；调用方安装审计钩子，不调用watch/worker。"""
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module;spec.loader.exec_module(module)
    return module


def deny_credentials_and_mutations(credential):
    """旧探针仅允许ps子进程；网络、凭据、文件写入和信号均拒绝。"""
    def guard(event,values):
        if event in ('socket.connect','socket.getaddrinfo','os.system','os.rename','os.remove','os.mkdir') or event=='os.kill' and values[1]!=0:
            raise gate.GateError('只读交接探针禁止副作用:'+event)
        if event=='subprocess.Popen' and Path(os.fsdecode(values[0])).name!='ps':
            raise gate.GateError('只读探针仅准ps，不启动玩家/后台')
        if event=='open' and values and isinstance(values[0],(str,bytes)):
            path=Path(os.fsdecode(values[0])).resolve()
            if 'token' in path.parts or path.name=='.env' or str(path)==credential:
                raise gate.GateError('只读探针禁止凭据读取')
            mode=values[1] if len(values)>1 else None;flags=values[2] if len(values)>2 else 0
            if isinstance(mode,str) and any(value in mode for value in 'wax+') or isinstance(flags,int) and flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND):
                raise gate.GateError('只读探针禁止文件写入')
    sys.addaudithook(guard)


def process_children(pid):
    """只读实际父子进程；ps失败保持未知，不猜空闲。"""
    result=subprocess.run(['ps','-Ao','pid=,ppid=,command='],capture_output=True,text=True)
    if result.returncode:raise gate.GateError('不能确认后台真实子任务')
    pairs=[]
    for line in result.stdout.splitlines():
        bits=line.strip().split(None,2)
        if len(bits)>=2 and bits[0].isdigit() and bits[1].isdigit():pairs.append((int(bits[0]),int(bits[1])))
    descendants=set();parents={pid}
    while True:
        new={child for child,parent in pairs if parent in parents and child not in descendants}
        if not new:break
        descendants.update(new);parents=new
    return sorted(descendants)


def wait_owner_exit_tail(pid,expected,observe,*,max_seconds=2.0,now=time.monotonic,sleep=time.sleep):
    """只等已确认同命令旧owner的退出尾部；未知/换命令不反复猜测，无信号副作用。"""
    started=now();value=observe(pid,expected);initial=value.get('expected_command_live')
    while value.get('expected_command_live') is True:
        if now()-started>=max_seconds:raise gate.GateError('旧owner退出尾部超过有界等待，不自动重启')
        sleep(min(.1,max_seconds-(now()-started)));value=observe(pid,expected)
    if value.get('expected_command_live') is not False:raise gate.GateError('旧owner退出核验未知，不重试')
    return {'initial_confirmed_owner_live':initial is True,'max_monotonic_seconds':max_seconds,
        'elapsed_monotonic_seconds':now()-started,'terminal_process_observation':value,'signals_sent':0}


def old_probe(spec,boundary=None,worker_pid=None):
    """原ROOT复用可信verify_free；当前统计/未来子进程继续用原main，不覆盖源码。"""
    old_root=Path(spec['active_root']).resolve();sys.path[:0]=[str(old_root/'src'),str(old_root)]
    old=load('t199_old_handoff_tools',old_root/OLD_REL)
    if any(value.resolve()!=old_root for value in (old.ROOT,old.h.ROOT,old.n.ROOT)):raise gate.GateError('旧helper ROOT泄漏')
    if str(Path.cwd())!=str(old_root):raise gate.GateError('旧探针cwd错误')
    if os.environ.get('PYTHONPATH')!=os.pathsep.join((str(old_root/'src'),str(old_root))):raise gate.GateError('旧spawn PYTHONPATH错误')
    expected={'owner_lock':str(old.OWNER_LOCK),'postprocess_lock':str(old.POSTPROCESS_LOCK),'worker_lock':str(old.PRIVATE/'worker.lock')}
    if any(spec['shared'][key]!=value for key,value in expected.items()):raise gate.GateError('未共用旧真实三锁')
    frozen=old.preflight();state=old.h.load(old.HERE/'STATUS.json');background=old.h.load(old.HERE/'BACKGROUND-STATUS.json')
    jobs=[];skipped=[];unknown=[];directories=sorted(old.HERE.glob('batch-*'))
    for directory in directories:
        if (directory/'POSTPROCESS-START.json').exists():skipped.append(str(directory));continue
        plan=directory/'PLAN.json';config=old.PRIVATE/directory.name/'free.json'
        if not plan.is_file() or not config.is_file():unknown.append(str(directory));continue
        jobs.append({'directory':str(directory),'plan_pin':gate.pin(plan),'release_root':str(old_root),
            'config_path':str(config),'config_pin':gate.pin(config),'natural_closed_at_preparation':(directory/'RUN-CLOSED.json').exists()})
    value={'complete':True,'ROOT':str(old.ROOT),'helper_ROOT':str(old.h.ROOT),'postprocess_ROOT':str(old.n.ROOT),
        'actual_locks':expected,'actual_cwd':str(Path.cwd()),'actual_pythonpath':os.environ['PYTHONPATH'],
        'identity':frozen,'state':state,'background':background,'adoptable_jobs':jobs,'existing_START_skipped':skipped,'unknown_jobs':unknown,
        'control':old.h.load(old.CONTROL),'control_path':str(old.CONTROL),'latest_directory':str(directories[-1]),
        'latest_plan_pin':gate.pin(directories[-1]/'PLAN.json'),
        'other_players':old.h.other_players(),'old_source_pins':{str(path):gate.pin(path) for path in
            (old_root/OLD_REL,old.OLD/'watchdog.py',old.OLD/'watchdog_nonblocking.py',old.OLD/'analyze.py')},
        'other_players_source':old.h.other_players.__code__.co_filename,'watch_called':False,'Token_reads':0,'HTTP_calls':0}
    if boundary is not None:
        directory=Path(boundary).resolve()
        if directory.parent!=old.HERE:raise gate.GateError('旧自然房界必须是真实T194 review批次')
        plan=old.h.load(directory/'PLAN.json');verified=old.verify_free(directory,plan)
        closed=old.h.load(directory/'RUN-CLOSED.json');terminal=old.a.end_records(directory/'FREE-STDOUT-STDERR.log','free')[0]
        compute=terminal['decision_compute']
        if compute.get('closed') is not True or any(type(compute.get(key)) is not int or compute[key]!=0 for key in gate.RESOURCE_COUNTS):
            raise gate.GateError('旧房12资源项缺失或未自然归零')
        if closed.get('continuation_safety_verified') is not True or state['state']!='stopped_after_natural_finish' or state['active_children']:
            raise gate.GateError('旧controller尚未自然停止或房界未闭合')
        if value['other_players']:raise gate.GateError('真实玩家仍活，不等旧owner尾部')
        tail=wait_owner_exit_tail(state['controller_pid'],str(old_root/OLD_REL)+' watch',old.h.process_identity)
        if old.h.other_players():raise gate.GateError('退出尾部核验后出现真实玩家，不启动新owner')
        value['boundary']={'complete':True,'verified':verified,'compute':compute,'old_owner_exit_tail':tail,
            'closed_pin':gate.pin(directory/'RUN-CLOSED.json'),'plan_pin':gate.pin(directory/'PLAN.json')}
    if worker_pid is not None:
        identity=old.h.process_identity(worker_pid,str(old_root/OLD_REL)+' worker');tasks=[]
        for directory in sorted(old.HERE.glob('batch-*')):
            start=directory/'POSTPROCESS-START.json'
            if start.is_file() and old.h.load(start).get('worker_pid')==worker_pid:
                tasks.append({'directory':str(directory),'started_pin':gate.pin(start),'closed':(directory/'POSTPROCESS-CLOSED.json').is_file()})
        value['idle_worker']={'pid':worker_pid,'identity':identity,'descendants':process_children(worker_pid),
            'background_enabled':old.h.load(old.CONTROL)['background_enabled'],'background_state':background['state'],
            'all_started_tasks_naturally_closed':all(row['closed'] for row in tasks),'started_tasks':tasks}
    return value


def main():
    """此命令只有只读探针；永不处理控制开关或真实匹配。"""
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('side',choices=('new','old'));parser.add_argument('--spec',type=Path,required=True)
    parser.add_argument('--boundary',type=Path);parser.add_argument('--worker-pid',type=int);args=parser.parse_args()
    spec=gate.read_json(args.spec);deny_credentials_and_mutations(str(Path(spec['credential_path']).resolve()))
    if args.side=='old':value=old_probe(spec,args.boundary,args.worker_pid)
    else:
        root=Path(spec['release_root']);sys.path[:0]=[str(root/'src'),str(root)]
        frozen_gate=load('release_gate',root/Path(NEW_REL).parent/'release_gate.py')
        module=load('t199_actual_handoff_controller',root/NEW_REL);controller=module.Controller(args.spec)
        value=controller.inspect();value['admission']=controller.check_admission()
        value.update(actual_cwd=str(Path.cwd()),actual_pythonpath=os.environ.get('PYTHONPATH'),
            actual_four_packages={mode:frozen_gate.read_json(root/relative)['release_package_id'] for mode,relative in spec['mode_manifests'].items()},
            actual_controller_file=str(Path(module.__file__).resolve()),actual_gate_file=str(Path(module.gate.__file__).resolve()),Token_reads=0,HTTP_calls=0)
    print(json.dumps(value,ensure_ascii=False))


if __name__=='__main__':main()
