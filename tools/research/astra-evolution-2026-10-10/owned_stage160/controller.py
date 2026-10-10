"""标准库有界子进程所有权；只管调度/终止/回收，不读取积分或实现规则。"""
import time,signal

class BatchDeadline(TimeoutError):
    """同一批次绝对单调截止已到，不能派发或补样。"""


class OwnedPhase:
    """一个最多10进程的阶段；成功必须全部自然join并close，失败终止自己所拥有的进程。"""
    def __init__(self,context,*,limit,work_deadline,hard_deadline,event,clock=time.monotonic,sleep=time.sleep,begin_cleanup=lambda:None):
        if not 1<=limit<=10 or not work_deadline<hard_deadline:raise ValueError('invalid bounded phase')
        self.context=context;self.limit=limit;self.work_deadline=work_deadline;self.hard_deadline=hard_deadline
        self.begin_cleanup=begin_cleanup;self.event=event;self.clock=clock;self.sleep=sleep;self.owned={};self.retired=[];self.started=[];self.peak=0;self.start_uncertain=[]

    def snapshot(self):
        """公开本控制器尚拥有/仍存活的进程；不把未知或未close计为零。"""
        return {'owned':len(self.owned),'live':sum(p.is_alive() for p in self.owned.values()),'pids':[p.pid for p in self.owned.values() if p.pid is not None],'started_job_ids':list(self.started),'peak_owned':self.peak,'owned_workers':[{'job_id':i,'pid':p.pid}for i,p in self.owned.items()],'start_outcome_uncertain':list(self.start_uncertain),'retired':list(self.retired)}

    def check(self):
        if self.clock()>=self.work_deadline:raise BatchDeadline('shared absolute work deadline')

    def retire(self,ident,*,forced):
        """仅已经退出的子进程可join/close；成功以后才撤销所有权。"""
        p=self.owned[ident]
        if p.is_alive():raise RuntimeError('cannot retire live worker')
        if p.pid is not None:p.join(timeout=0)
        row={'job_id':ident,'pid':p.pid,'exitcode':p.exitcode,'forced_cleanup':forced,'join_called':p.pid is not None,'close_complete':False}
        p.close();row['close_complete']=True;del self.owned[ident];self.retired.append(row);self.event('worker_reaped',self.snapshot())
        return row

    def stop_and_reap(self):
        """异常只终止本阶段持有子进程；先同时terminate，再kill存活者，共享清理余量。"""
        self.begin_cleanup()
        errors=[]
        for ident,p in list(self.owned.items()):
            try:
                if p.is_alive():p.terminate()
            except BaseException as error:errors.append({'job_id':ident,'step':'terminate','type':type(error).__name__})
        for p in list(self.owned.values()):
            if p.pid is not None:
                try:p.join(timeout=max(0,min(.10,self.hard_deadline-self.clock())))
                except BaseException:pass
        for ident,p in list(self.owned.items()):
            try:
                if p.is_alive():p.kill()
            except BaseException as error:errors.append({'job_id':ident,'step':'kill','type':type(error).__name__})
        for ident,p in list(self.owned.items()):
            try:
                if p.pid is not None:p.join(timeout=max(0,min(.25,self.hard_deadline-self.clock())))
                if not p.is_alive():self.retire(ident,forced=True)
            except BaseException as error:errors.append({'job_id':ident,'step':'reap','type':type(error).__name__})
        snap=self.snapshot();snap['cleanup_errors']=errors;snap['resource_recovered']=snap['owned']==snap['live']==0 and not snap['start_outcome_uncertain']
        self.event('phase_cleanup',snap);return snap

    def run(self,jobs,target,read_result,*,stop_requested=lambda:False):
        """原序只派一次；失败/软停只停新派发，在途继续自然join；硬异常统一回收。

        read_result只验证原任务返回值，不按分数决定调度。非零退出或读取失败
        留进程故障证据，并停止新任务，不把失败伪装成一个完成桌。
        """
        ids=[x['job_id']for x in jobs]
        if len(ids)!=len(set(ids)):raise ValueError('duplicate job ids')
        lookup={x['job_id']:x for x in jobs}
        if any(j['work_deadline']!=self.work_deadline for j in jobs):raise ValueError('per-job deadline refresh forbidden')
        cursor=0;results={};natural=False;stopped=False;failures=[]
        try:
            while (cursor<len(jobs) and not stopped) or self.owned:
                self.check()
                if stop_requested():stopped=True
                # 先收全部已退出进程，再决定补位，避免同一轮有fault还派新桌。
                for ident,p in list(self.owned.items()):
                    if p.is_alive():continue
                    row=self.retire(ident,forced=False)
                    if row['exitcode']!=0:
                        stopped=True;failures.append({'job_id':ident,'kind':'nonzero_exit','exitcode':row['exitcode']});continue
                    try:
                        value=read_result(lookup[ident]);results[ident]=value
                        if value.get('status')!='complete':
                            stopped=True;failures.append({'job_id':ident,'kind':'task_returned_fault'})
                    except Exception as error:
                        stopped=True;failures.append({'job_id':ident,'kind':'invalid_result','error_type':type(error).__name__})
                if stop_requested():stopped=True
                while not stopped and cursor<len(jobs)and len(self.owned)<self.limit:
                    if stop_requested():
                        stopped=True;break
                    self.check();job=jobs[cursor]
                    p=self.context.Process(target=target,args=(job,),name=job['job_id']);p.daemon=True
                    self.owned[job['job_id']]=p
                    # 避免本机SIGALRM恰在spawn后/PID登记前打断所有权。
                    # 子worker显式解除继承的屏蔽，再绑定同一绝对截止。
                    previous_mask=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGALRM})
                    try:
                        try:p.start()
                        except BaseException:
                            if p.pid is None:self.start_uncertain.append(job['job_id'])
                            raise
                        self.started.append(job['job_id']);cursor+=1
                        self.peak=max(self.peak,len(self.owned))
                    finally:signal.pthread_sigmask(signal.SIG_SETMASK,previous_mask)
                    self.event('worker_started',self.snapshot())
                if self.owned:self.sleep(min(.02,max(0,self.work_deadline-self.clock())))
            natural=True
            result={'complete':not stopped and set(results)==set(ids),'results':[results[x]for x in ids if x in results],
                'failures':failures,'stopped_new_dispatch':stopped,'unstarted_job_ids':ids[cursor:],
                'started_without_result':[x for x in self.started if x not in results],
                'all_started_naturally_joined':True,'resources':self.snapshot()}
            self.event('phase_naturally_joined',self.snapshot());return result
        finally:
            if not natural or self.owned:
                result=self.stop_and_reap()
                if not result['resource_recovered']:raise RuntimeError('owned/live workers remain; no recovered receipt')
