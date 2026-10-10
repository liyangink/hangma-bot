"""标准库假字段正负控，不执行真实策略、native或生产日志。"""
import unittest
from copy import deepcopy
from dataclasses import dataclass,field,replace
from checks import core,inspect,AUDIT
CID='a'*64;EID='b'*64

def pair():
    p={'decision_id':'x','candidates':[{'action_key':'discard:1w','rank':1,'total_score':3.,'score_parts':[3.],
       'score_trace':{'detail':{'pay':[1,2,3],'policy_release':{'release_package_id':'c'*64,'old':True}}}}],
       'degraded_reasons':[]}
    q=deepcopy(p);d=q['candidates'][0]['score_trace']['detail']
    d[AUDIT]={'schema':'white-circle-runtime-audit/1','status':'parent_preserved','reason':'insufficient extra budget','reason_encoding':'underscores_as_spaces'}
    d['policy_release'].update(experimental_candidate_sha256=CID,experimental_execution_sha256=EID,
       runtime_audit_experimental=True,runtime_audit_production_admission=False)
    return p,q

def check(p,q):return inspect(p,q,CID,EID,'parent_preserved','insufficient_extra_budget')
class Tests(unittest.TestCase):
    def test_addition(self):
        p,q=pair();self.assertTrue(check(p,q)['trace_ok']);self.assertEqual(core(p),core(q))
    def test_equality_ignores_trace(self):
        @dataclass
        class Fake:
            score:int
            score_trace:dict=field(compare=False)
        p=Fake(2,{});q=replace(p,score_trace={'audit':1});self.assertEqual(p,q);self.assertNotEqual(p.score_trace,q.score_trace)
    def test_missing(self):
        p,q=pair();self.assertFalse(check(p,p)['trace_ok'])
    def test_wrong_identity(self):
        p,q=pair();q['candidates'][0]['score_trace']['detail']['policy_release']['experimental_execution_sha256']='c'*64
        self.assertIn('execution_identity_mismatch',check(p,q)['problems'])
    def test_lost_parent_release(self):
        p,q=pair();del q['candidates'][0]['score_trace']['detail']['policy_release']['release_package_id']
        self.assertFalse(check(p,q)['trace_ok'])
    def test_wrong_core(self):
        p,q=pair();q['candidates'][0]['total_score']=4.;self.assertIn('core_changed',check(p,q)['problems'])
    def test_wrong_reason(self):
        p,q=pair();q['candidates'][0]['score_trace']['detail'][AUDIT]['reason']='other';self.assertFalse(check(p,q)['trace_ok'])
    def test_extra_trace_change(self):
        p,q=pair();q['candidates'][0]['score_trace']['detail']['pay']=[9];self.assertFalse(check(p,q)['trace_ok'])
    def test_identity_bool_type(self):
        p,q=pair();q['candidates'][0]['score_trace']['detail']['policy_release']['runtime_audit_experimental']=1
        self.assertFalse(check(p,q)['trace_ok'])
    def test_promoted_status(self):
        p,q=pair();d=q['candidates'][0]['score_trace']['detail'][AUDIT];d.update(status='white_circle_promoted',reason='protected singlewhite control')
        self.assertTrue(inspect(p,q,CID,EID,'white_circle_promoted','protected_singlewhite_control')['trace_ok'])
if __name__=='__main__':unittest.main()
