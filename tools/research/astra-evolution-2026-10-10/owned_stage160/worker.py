"""拥有进程的一桌入口：截止先绑定，再验冻结字节，最后调用原budgeted.worker。"""
import hashlib,json,signal,sys,time
from pathlib import Path
class WorkerDeadline(BaseException):
    """原阶段绝对截止；不刷新每窗或每桌的可用时长。"""

def save(path,value):
    """原子输出包装收据；不改原stage worker的CLOSED/FAILED。"""
    p=Path(path);tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,allow_nan=False)+'\n');tmp.replace(p)

def run(job):
    """每进程只运行一条原task，无子池，无second driver。"""
    deadline=job['work_deadline']
    # 原stage.worker会捕获BaseException，必须使用OS默认信号终止，
    # 不能把硬截止变成可被业务捕获的Python异常。父仍拥有Process负责join/close。
    signal.signal(signal.SIGALRM,signal.SIG_DFL)
    signal.pthread_sigmask(signal.SIG_UNBLOCK,{signal.SIGALRM})
    remaining=deadline-time.monotonic()
    if remaining<=0:raise WorkerDeadline('expired before project import')
    signal.setitimer(signal.ITIMER_REAL,remaining)
    out=Path(job['task']['out']);out.parent.mkdir(parents=True,exist_ok=True)
    if out.exists():raise ValueError('original task output must not exist')
    # 原run_table拥有out的独占创建；启动收据放在同父目录的侧文件。
    start_file=out.parent/(out.name+'-OWNED-WORKER-START.json')
    if start_file.exists():raise ValueError('original start record must not exist')
    save(start_file,{'job_id':job['job_id'],'pid':__import__('os').getpid(),
        'work_deadline_monotonic':deadline,'hard_deadline_monotonic':job['hard_deadline'],
        'deadline_bound_before_project_import':True,'worker_child_pools':0})
    for path,digest in job['method_pins'].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest:raise RuntimeError('stage method drift')
    sys.path.insert(0,job['method_root'])
    import stage160_budgeted
    if Path(stage160_budgeted.__file__).resolve()!=Path(job['method_root'])/'stage160_budgeted.py':raise RuntimeError('wrong stage worker module')
    result=stage160_budgeted.worker(job['task'])
    if result.get('task')!=job['task']:raise RuntimeError('worker returned a different original task')
    save(out/'OWNED-WORKER-RESULT.json',{'job_id':job['job_id'],'work_deadline_monotonic':deadline,
        'deadline_bound_before_project_import':True,'result':result})
    if time.monotonic()>=deadline:raise WorkerDeadline('result recorded after original pool deadline')
    signal.setitimer(signal.ITIMER_REAL,0)
