"""待root执行的极小真实spawn回收检查；纯标准库睡眠/文件假worker，无牌局/native。

三场景串行，峰值2worker+控制；结果不能授真实策略、效果或线上时限资格。
"""
import argparse,json,multiprocessing,signal,time
from pathlib import Path
from controller import OwnedPhase,BatchDeadline

def fake_worker(job):
    """只验证进程生命周期；hard场景忽略TERM迫使控制器走KILL。"""
    if job['mode']=='hard':signal.signal(signal.SIGTERM,signal.SIG_IGN)
    time.sleep(job['duration'])
    Path(job['file']).write_text(json.dumps({'status':'worker_failed'if job['mode']=='fault'and job['job_id']=='0'else'complete','task':job['job_id']}))

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();out=Path(a.out)
    if out.exists():raise ValueError('不覆盖')
    out.mkdir(parents=True);rows=[]
    for mode in ('normal','fault','hard'):
        start=time.monotonic();deadline=start+(1. if mode=='hard' else 5.);events=[]
        phase=OwnedPhase(multiprocessing.get_context('spawn'),limit=2,work_deadline=deadline,hard_deadline=deadline+4,event=lambda k,s:events.append({'event':k,**s}))
        jobs=[{'job_id':str(i),'mode':mode,'work_deadline':deadline,'file':str(out/f'{mode}-{i}.json'),
               'duration':30. if mode=='hard' else (.05 if mode=='fault'and i==0 else .15)}for i in range(4)]
        error=None;result=None
        try:result=phase.run(jobs,fake_worker,lambda j:json.loads(Path(j['file']).read_text()))
        except BatchDeadline:error='BatchDeadline'
        snap=phase.snapshot();assert snap['owned']==snap['live']==0 and not snap['start_outcome_uncertain']
        if mode=='normal':assert result['complete'] and len(phase.started)==4
        if mode=='fault':assert not result['complete'] and result['all_started_naturally_joined'] and len(phase.started)==2 and all(not r['forced_cleanup']for r in phase.retired)
        if mode=='hard':assert error=='BatchDeadline' and len(phase.started)==2 and all(r['forced_cleanup']for r in phase.retired) and any(r['exitcode']==-9 for r in phase.retired)
        rows.append({'mode':mode,'result':result,'error':error,'resources':snap,'events':events,'elapsed_seconds':time.monotonic()-start})
    (out/'RECEIPT.json').write_text(json.dumps({'complete':True,'rows':rows,'native':0,'worlds':0,'choose':0,'max_workers':2,'owned_live_final':0},ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'complete':True,'native':0,'worlds':0,'choose':0,'owned_live':0}))
if __name__=='__main__':main()
