"""独立单池10worker控制器；原任务、真实choose预算与原stage worker不变。"""
import time
STARTED=time.monotonic()
import argparse,hashlib,json,multiprocessing,os,signal,sys
from pathlib import Path
from controller import OwnedPhase,BatchDeadline
from worker import run as worker_run
HERE=Path(__file__).resolve().parent
class HardLimit(BaseException):pass

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,value):
    path=Path(path);tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n');tmp.replace(path)
def read(path):return json.loads(Path(path).read_text())

def main():
    """必须显式root离线AUTH；不接受线上批准或Token，不执行后处理/下一池。"""
    parser=argparse.ArgumentParser();parser.add_argument('--declaration',required=True);parser.add_argument('--out',required=True);parser.add_argument('--auth',required=True)
    args=parser.parse_args();out=Path(args.out).resolve()
    if out.exists():raise ValueError('不得覆盖或自动续跑已有池')
    hard=STARTED+7200.;work=hard-15.
    def timeout(*a):raise HardLimit('absolute pool work deadline; cleanup within7200')
    signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,max(.001,work-time.monotonic()))
    auth=read(args.auth);declaration=read(args.declaration);delivery=read(HERE/'DELIVERY.json')
    if (auth.get('schema')!='white-circle-stage-owned-auth/1' or auth.get('execution_allowed') is not True
            or auth.get('declaration_sha256')!=sha(args.declaration) or auth.get('controller_delivery_sha256')!=sha(HERE/'DELIVERY.json')
            or auth.get('candidate_id')!=declaration['candidate']['expected_candidate_id']
            or auth.get('execution_id')!=declaration['candidate_execution_id'] or auth.get('other_heavy_processes')!=0
            or auth.get('mechanical_complete_passed') is not True or not auth.get('mechanical_receipt_sha256')
            or auth.get('maximum_workers')!=10):raise ValueError('缺root机械/身份/独占调度AUTH')
    for name,digest in delivery['files'].items():
        if sha(HERE/name)!=digest:raise ValueError('controller source drift')
    for path,digest in delivery['method_pins'].items():
        if sha(path)!=digest:raise ValueError('original method drift')
    if declaration['workers']!=10 or declaration['cpu_cores']!=14:raise ValueError('固定10worker+1control/14核')
    sys.path.insert(0,delivery['method_root'])
    import stage160_budgeted as budgeted
    stage=budgeted.stage
    stage.verify_declaration(declaration)
    tasks=stage.build_tasks(declaration,out)
    if len({t['id']for t in tasks})!=len(tasks):raise ValueError('原任务ID重复')
    out.mkdir(parents=True)
    save(out/'PLAN.json',{'declaration':declaration,'declaration_sha256':sha(args.declaration),
        'driver_sha256':sha(HERE/'harness.py'),'original_budgeted_driver_sha256':sha(Path(delivery['method_root'])/'stage160_budgeted.py'),
        'tasks':tasks,'logical_budget_not_live_admission':True,'auth_sha256':sha(args.auth)})
    stopped={'value':False}
    def soft_stop(*a):stopped['value']=True
    signal.signal(signal.SIGINT,soft_stop);signal.signal(signal.SIGTERM,soft_stop)
    def event(kind,snapshot):
        snapshot=dict(snapshot,event=kind,controller_pid=os.getpid(),work_deadline_monotonic=work,hard_deadline_monotonic=hard)
        save(out/'RESOURCES.json',snapshot)
    def begin_cleanup():
        # 移除work闹钟，避免它在异常回收过程中第二次打断；不刷新原hard截止。
        signal.setitimer(signal.ITIMER_REAL,0)
        def final_alarm(*a):
            for process in list(phase.owned.values()):
                try:
                    if process.is_alive():process.kill()
                except BaseException:pass
            raise HardLimit('original7200 hard deadline during cleanup; recovery unknown')
        signal.signal(signal.SIGALRM,final_alarm)
        signal.setitimer(signal.ITIMER_REAL,max(.001,hard-time.monotonic()))
    phase=OwnedPhase(multiprocessing.get_context('spawn'),limit=10,work_deadline=work,hard_deadline=hard,event=event,begin_cleanup=begin_cleanup)
    jobs=[{'job_id':t['id'],'task':t,'work_deadline':work,'hard_deadline':hard,
        'method_root':delivery['method_root'],'method_pins':delivery['method_pins']}for t in tasks]
    results=[];status=None;error=None
    def collect(job):
        r=read(Path(job['task']['out'])/'OWNED-WORKER-RESULT.json')
        if (r['job_id']!=job['job_id'] or r['work_deadline_monotonic']!=work
                or r['deadline_bound_before_project_import'] is not True or r['result']['task']!=job['task']):raise ValueError('原task/截止绑定失配')
        results.append(r['result']);save(out/'PROGRESS.json',{'closed':len(results),'planned':len(tasks),'results':results})
        return r['result']
    try:
        status=phase.run(jobs,worker_run,collect,stop_requested=lambda:stopped['value'] or (out/'STOP-REQUESTED').exists())
    except BaseException as exc:error={'type':type(exc).__name__,'message':str(exc)}
    finally:
        # 原work闹钟到此取消；清理没有新7200秒，只剩原hard绝对截止。
        signal.setitimer(signal.ITIMER_REAL,0)
        snap=phase.snapshot();recovered=snap['owned']==snap['live']==0 and not snap['start_outcome_uncertain']
        pins_unchanged=all(sha(HERE/name)==digest for name,digest in delivery['files'].items()) and all(sha(path)==digest for path,digest in delivery['method_pins'].items())
        closed={'complete':bool(status and status['complete']) and recovered and error is None and pins_unchanged and time.monotonic()<hard,
            'closed':len(results),'planned':len(tasks),'results':results,'controller_status':status,'error':error,'controller_and_method_pins_unchanged':pins_unchanged}
        save(out/'RUN-CLOSED.json',closed)
        save(out/'FINAL-RESOURCES.json',dict(snap,resource_recovered=recovered,controller_pid=os.getpid(),
            all_started_naturally_joined=bool(status and status['all_started_naturally_joined']),
            elapsed_seconds=time.monotonic()-STARTED,within7200=time.monotonic()<=hard))
        if not recovered or error or not closed['complete']:raise RuntimeError('阶段不完整；保留原件，禁止后续效果门或自动补样')
    print(json.dumps({'complete':True,'closed':len(results),'owned':0,'live':0,'elapsed_seconds':time.monotonic()-STARTED}))
if __name__=='__main__':main()
