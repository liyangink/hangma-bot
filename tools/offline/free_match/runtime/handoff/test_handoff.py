"""薄交接负例与临时FD真实spawn；不碰活跃control/锁，不调用watch/Token。"""
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
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parent))
import handoff as h
import probe as p


def fixture(tmp_path):
    """所有控制/三锁/状态都在临时T199目录，生产项目根不参与副作用。"""
    stage=tmp_path/'t199-local-stage';stage.mkdir();release=tmp_path/'root';release.mkdir();state=tmp_path/'t199-new-state'
    control=tmp_path/'old-control.json';h.write_state(control,{'continue_after_cycle':True,'background_enabled':True})
    shared={key:str(tmp_path/(key+'.lock')) for key in ('owner_lock','postprocess_lock','worker_lock')};shared['state_dir']=str(state)
    for key in ('owner_lock','postprocess_lock','worker_lock'):Path(shared[key]).touch()
    spec_path=tmp_path/'spec.json';spec={'release_root':str(release),'active_root':str(tmp_path),'shared':shared,'adopted_jobs':[]}
    h.gate.save_exclusive(spec_path,spec)
    old={'complete':True,'identity':{'old':'test'},'old_source_pins':{},'latest_directory':str(tmp_path/'batch-001'),
        'latest_plan_pin':{'test':1},'unknown_jobs':[],'adoptable_jobs':[],'boundary':{'complete':True},'background':{'worker_pid':12345}}
    plan={'spec_path':str(spec_path),'spec_pin':h.gate.pin(spec_path),'tool_pins':h.tool_pins(),'shared':shared,
        'old_identity':old['identity'],'old_source_pins':{},'old_batch':old['latest_directory'],'old_plan_pin':old['latest_plan_pin'],'old_control_path':str(control)}
    h.gate.save_exclusive(stage/'PLAN.json',plan);h.gate.save_exclusive(stage/'RESERVATION.json',{'complete':True})
    approval=tmp_path/'approval.json'
    h.gate.save_exclusive(approval,{'approved_for_natural_handoff':True,'pause_old_next_room':True,'stop_only_idle_old_worker':True,
        'start_new_frozen_controller':True,'plan_pin':h.gate.pin(stage/'PLAN.json'),'reservation_pin':h.gate.pin(stage/'RESERVATION.json'),'tool_pins':h.tool_pins()})
    inspector=lambda *args,**kwargs: old if args[1]=='old' else {'complete':True}
    return stage,spec_path,approval,control,old,inspector


def test_no_approval_is_zero_mutation(tmp_path):
    stage,spec,approval,control,old,inspect=fixture(tmp_path);before=control.read_bytes();approval.unlink()
    with pytest.raises(FileNotFoundError):h.execute(stage,approval,inspector=inspect)
    assert control.read_bytes()==before and not (stage/'ACTIVATION-INTENT.json').exists()


def test_later_room_refuses_before_pause(tmp_path):
    stage,spec,approval,control,old,inspect=fixture(tmp_path);before=control.read_bytes();old['latest_directory']='new-room'
    with pytest.raises(h.gate.GateError,match='旧房'):h.execute(stage,approval,inspector=inspect)
    assert control.read_bytes()==before


def test_unlisted_review_job_requires_resign():
    row={'directory':'review/T194/batch-058','plan_pin':{},'release_root':'old','config_path':'private/free.json','config_pin':{}}
    with pytest.raises(h.gate.GateError,match='重签'):h.check_adoptions({'adopted_jobs':[]},{'unknown_jobs':[],'adoptable_jobs':[row]})


def test_start_and_unknown_never_adopt():
    assert h.check_adoptions({'adopted_jobs':[]},{'unknown_jobs':[],'adoptable_jobs':[]}) is None
    with pytest.raises(h.gate.GateError,match='未知'):h.check_adoptions({'adopted_jobs':[]},{'unknown_jobs':['bad'],'adoptable_jobs':[]})


def test_boundary_failure_preserves_pause_no_launcher(tmp_path):
    stage,spec,approval,control,old,inspect=fixture(tmp_path)
    def fail_boundary(*args,**kwargs):
        if 'boundary' in kwargs:raise h.gate.GateError('自然终态未知')
        return inspect(*args,**kwargs)
    launched=[]
    with pytest.raises(h.gate.GateError,match='未知'):h.execute(stage,approval,inspector=fail_boundary,launcher=lambda *a,**k:launched.append(a))
    assert h.gate.read_json(control)['continue_after_cycle'] is False and not launched
    assert (stage/'ACTIVATION-INTENT.json').exists()


def test_spawn_uncertainty_is_not_retried(tmp_path):
    stage,spec,approval,control,old,inspect=fixture(tmp_path);calls=[]
    def fail(*args,**kwargs):calls.append(args);raise OSError('spawn uncertain')
    with pytest.raises(OSError):h.execute(stage,approval,inspector=inspect,launcher=fail)
    with pytest.raises(h.gate.GateError,match='不自动重试'):h.execute(stage,approval,inspector=inspect,launcher=fail)
    assert len(calls)==1 and (Path(h.gate.read_json(spec)['shared']['state_dir'])/'NATURAL-HANDOFF-DISPATCH-INTENT.json').exists()


def test_real_spawn_inherits_same_temp_owner_fd_and_reaper_does_not(tmp_path):
    stage,spec,approval,control,old,inspect=fixture(tmp_path);children=[];observed=[]
    def launcher(command,**kwargs):
        observed.append((command,kwargs));owner=kwargs['env'].get(h.OWNER_ENV)
        if owner is not None:
            # 真-I子进程只核临时FD及环境；不执行模拟传入的watch命令。
            code='import os,sys;fd=int(os.environ["HM_T199_OWNER_FD"]);a=os.fstat(fd);b=os.stat(sys.argv[1]);assert(a.st_dev,a.st_ino)==(b.st_dev,b.st_ino);assert os.getcwd()==sys.argv[2];assert os.environ["PYTHONPATH"]==sys.argv[2]+"/src:"+sys.argv[2]'
            child=subprocess.Popen([sys.executable,'-I','-B','-c',code,h.gate.read_json(spec)['shared']['owner_lock'],h.gate.read_json(spec)['release_root']],**kwargs)
            children.append(child);return child
        assert kwargs.get('pass_fds',())==() and h.OWNER_ENV not in kwargs['env']
        return SimpleNamespace(pid=98765)
    result=h.execute(stage,approval,inspector=inspect,launcher=launcher)
    assert result['players_terminated']==0 and children[0].wait(timeout=5)==0
    assert observed[0][0][2].endswith(h.NEW_REL) and observed[0][0][3]=='watch'
    assert not (stage/'TRANSFER-QUEUE.json').exists()  # 不把old private冒充review任务队列。


@pytest.mark.parametrize('change',[{'descendants':[42]},{'background_enabled':True},{'all_started_tasks_naturally_closed':False},
    {'identity':{'expected_command_live':None}},{'identity':{'expected_command_live':False}},{'background_state':'processing'},
    {'pid':True},{'descendants':None}])
def test_busy_unknown_reused_or_player_like_pid_never_safe(change):
    row={'pid':123,'identity':{'expected_command_live':True},'background_enabled':False,'background_state':'waiting',
        'all_started_tasks_naturally_closed':True,'descendants':[]}
    row.update(change);assert h.idle_safe(row) is False


def test_verified_idle_worker_is_safe():
    assert h.idle_safe({'pid':123,'identity':{'expected_command_live':True},'background_enabled':False,'background_state':'waiting',
        'all_started_tasks_naturally_closed':True,'descendants':[]})


def test_bounded_read_only_wait_for_confirmed_owner_exit_tail():
    """仅同命令退出尾部可短等；未知立即拒绝，超时不发信号、不启动任何进程。"""
    clock=[0.0];answers=iter((True,True,False));calls=[]
    def observe(pid,expected):calls.append((pid,expected));return {'expected_command_live':next(answers)}
    result=p.wait_owner_exit_tail(42,'old watch',observe,now=lambda:clock[0],sleep=lambda value:clock.__setitem__(0,clock[0]+value))
    assert len(calls)==3 and result['initial_confirmed_owner_live'] and result['signals_sent']==0
    assert result['elapsed_monotonic_seconds']==pytest.approx(.2)
    with pytest.raises(p.gate.GateError,match='未知'):
        p.wait_owner_exit_tail(42,'old watch',lambda *_:{'expected_command_live':None},now=lambda:clock[0],sleep=lambda _:pytest.fail('未知不等'))
    with pytest.raises(p.gate.GateError,match='超过'):
        p.wait_owner_exit_tail(42,'old watch',lambda *_:{'expected_command_live':True},max_seconds=.3,
            now=lambda:clock[0],sleep=lambda value:clock.__setitem__(0,clock[0]+value))
