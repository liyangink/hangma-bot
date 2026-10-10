"""纯标准库内存假进程测试；不启动OS子进程、不导入项目/native。"""
import unittest
from controller import OwnedPhase,BatchDeadline
class Clock:
    def __init__(self):self.t=100.
    def __call__(self):return self.t
    def sleep(self,s):self.t+=s
class Process:
    def __init__(self,c,j):self.c=c;self.j=j;self.pid=None;self.exitcode=None;self.closed=False;self.daemon=False
    def start(self):
        if self.j['job_id']==self.c.start_failure:raise OSError('start uncertain')
        self.pid=len(self.c.started)+1;self.c.started.append(self.j['job_id']);self.end=self.c.clock()+self.c.durations.get(self.j['job_id'],.1)
    def is_alive(self):
        if self.pid is None:return False
        if self.exitcode is None and self.c.clock()>=self.end:self.exitcode=7 if self.j['job_id']==self.c.nonzero else 0
        return self.exitcode is None
    def join(self,timeout=0):self.c.clock.sleep(timeout);self.is_alive()
    def terminate(self):
        self.c.terminations.append(self.j['job_id'])
        if not self.c.ignore_term:self.exitcode=-15
    def kill(self):
        self.c.kills.append(self.j['job_id'])
        if not self.c.unkillable:self.exitcode=-9
    def close(self):
        if self.is_alive():raise ValueError('alive')
        self.closed=True
class Context:
    def __init__(self):
        self.clock=Clock();self.started=[];self.processes=[];self.durations={};self.nonzero=None;self.start_failure=None
        self.ignore_term=False;self.unkillable=False;self.terminations=[];self.kills=[]
    def Process(self,*,target,args,name):
        p=Process(self,args[0]);self.processes.append(p);return p

def jobs(n):return [{'job_id':str(i),'work_deadline':102.}for i in range(n)]
def make(c,limit=10):return OwnedPhase(c,limit=limit,work_deadline=102.,hard_deadline=107.,event=lambda *a:None,clock=c.clock,sleep=c.clock.sleep)
def result(j):return {'status':'complete','task':j}
class Tests(unittest.TestCase):
    def test_all_once_original_order_cap10(self):
        c=Context();p=make(c);r=p.run(jobs(25),None,result)
        self.assertTrue(r['complete']);self.assertEqual(c.started,[str(i)for i in range(25)]);self.assertEqual(p.peak,10)
        self.assertEqual([x['task']['job_id']for x in r['results']],c.started);self.assertEqual(p.snapshot()['owned'],0)
        self.assertTrue(all(x.closed for x in c.processes));self.assertFalse(c.terminations)
    def test_fault_stops_new_and_drains_naturally(self):
        c=Context();c.durations={'0':.02,**{str(i):.5 for i in range(1,10)}};p=make(c)
        r=p.run(jobs(20),None,lambda j:dict(result(j),status='worker_failed'if j['job_id']=='0'else'complete'))
        self.assertFalse(r['complete']);self.assertEqual(len(c.started),10);self.assertEqual(len(r['results']),10)
        self.assertTrue(r['all_started_naturally_joined']);self.assertFalse(c.terminations);self.assertGreaterEqual(c.clock(),100.5)
    def test_nonzero_drains_no_replacement(self):
        c=Context();c.nonzero='0';p=make(c);r=p.run(jobs(11),None,result)
        self.assertFalse(r['complete']);self.assertEqual(r['started_without_result'],['0']);self.assertEqual(len(c.started),10);self.assertFalse(c.terminations)
    def test_bad_result_drains(self):
        c=Context();p=make(c)
        def read(j):
            if j['job_id']=='0':raise ValueError('missing result')
            return result(j)
        r=p.run(jobs(20),None,read);self.assertFalse(r['complete']);self.assertEqual(len(c.started),10);self.assertFalse(c.terminations)
    def test_soft_stop_drains(self):
        c=Context();p=make(c);r=p.run(jobs(20),None,result,stop_requested=lambda:len(c.started)>=10)
        self.assertFalse(r['complete']);self.assertEqual(len(c.started),10);self.assertFalse(c.terminations)
    def test_soft_stop_during_batch_start(self):
        c=Context();p=make(c);calls={'n':0}
        def stop():
            calls['n']+=1;return calls['n']>=5
        r=p.run(jobs(20),None,result,stop_requested=stop)
        self.assertFalse(r['complete']);self.assertEqual(len(c.started),2);self.assertFalse(c.terminations)
    def test_hard_deadline_terminate_kill_reap(self):
        c=Context();c.durations={str(i):100 for i in range(20)};c.ignore_term=True;p=make(c)
        with self.assertRaises(BatchDeadline):p.run(jobs(20),None,result)
        self.assertEqual(len(c.started),10);self.assertEqual(len(c.kills),10);self.assertEqual(p.snapshot()['owned'],0);self.assertTrue(all(x.closed for x in c.processes))
    def test_deadline_not_refreshed(self):
        c=Context();p=make(c);j=jobs(2);j[-1]['work_deadline']=103.
        with self.assertRaises(ValueError):p.run(j,None,result)
        self.assertFalse(c.started)
    def test_duplicate_id_rejected_before_start(self):
        c=Context();p=make(c)
        with self.assertRaises(ValueError):p.run(jobs(1)*2,None,result)
        self.assertFalse(c.started)
    def test_unreapable_not_false_zero(self):
        c=Context();c.durations={'0':100};c.ignore_term=c.unkillable=True;p=make(c)
        with self.assertRaises(RuntimeError):p.run(jobs(1),None,result)
        self.assertEqual((p.snapshot()['owned'],p.snapshot()['live']),(1,1))
    def test_start_uncertain_not_recovered(self):
        c=Context();c.start_failure='0';p=make(c)
        with self.assertRaises(RuntimeError):p.run(jobs(1),None,result)
        self.assertEqual(p.snapshot()['start_outcome_uncertain'],['0'])
    def test_worker_OS_deadline_not_swallowable(self):
        from pathlib import Path
        source=(Path(__file__).parent/'worker.py').read_text()
        self.assertIn('signal.signal(signal.SIGALRM,signal.SIG_DFL)',source)
        self.assertIn('signal.pthread_sigmask(signal.SIG_UNBLOCK,{signal.SIGALRM})',source)
        self.assertLess(source.index('signal.setitimer'),source.index('import stage160_budgeted'))
    def test_limit11_rejected(self):
        with self.assertRaises(ValueError):make(Context(),11)
    def test_cleanup_guard_runs_before_term(self):
        c=Context();c.durations={'0':100};events=[];p=make(c);p.begin_cleanup=lambda:events.append(len(c.terminations))
        with self.assertRaises(BatchDeadline):p.run(jobs(1),None,result)
        self.assertEqual(events,[0])
if __name__=='__main__':unittest.main()
