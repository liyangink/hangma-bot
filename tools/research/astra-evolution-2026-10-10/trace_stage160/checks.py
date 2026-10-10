"""只审查公开codec字典；不导入策略，不以dataclass相等推定trace相同。"""
from copy import deepcopy
AUDIT='bounded_runtime_audit'
EXTRA=('experimental_candidate_sha256','experimental_execution_sha256',
       'runtime_audit_experimental','runtime_audit_production_admission')

def core(plan):
    """排除逐候选score_trace；其余计划字段全部逐值比较。"""
    value=deepcopy(plan)
    for candidate in value['candidates']:candidate.pop('score_trace',None)
    return value

def inspect(inner, result, cid, eid, status, reason):
    """返回缺失/不一致清单；任何缺trace都使trace_ok为False，不能静默通过。"""
    problems=[]
    if core(inner)!=core(result):problems.append('core_changed')
    expected=deepcopy(inner)
    candidates=result.get('candidates',[])
    if not candidates:return {'trace_ok':False,'problems':problems+['no_candidates']}
    trace=candidates[0].get('score_trace')
    detail=trace.get('detail') if type(trace) is dict else None
    summary=detail.get(AUDIT) if type(detail) is dict else None
    release=detail.get('policy_release') if type(detail) is dict else None
    if type(summary) is not dict:problems.append('summary_missing_or_malformed')
    elif (summary.get('schema')!='white-circle-runtime-audit/1' or summary.get('status')!=status
          or summary.get('reason')!=reason.replace('_',' ') or summary.get('reason_encoding')!='underscores_as_spaces'):
        problems.append('summary_mismatch')
    added=dict(zip(EXTRA,(cid,eid,True,False)))
    if type(release) is not dict:problems.append('release_missing_or_malformed')
    elif any(type(release.get(k)) is not type(v) or release.get(k)!=v for k,v in added.items()):
        problems.append('execution_identity_mismatch')
    if type(summary) is dict and type(release) is dict:
        oldtrace=expected['candidates'][0].get('score_trace') or {}
        olddetail=oldtrace.get('detail') or {}
        newtrace=deepcopy(oldtrace);newdetail=deepcopy(olddetail)
        newrelease=deepcopy(olddetail.get('policy_release',{}));newrelease.update(added)
        newdetail.update({AUDIT:summary,'policy_release':newrelease});newtrace['detail']=newdetail
        expected['candidates'][0]['score_trace']=newtrace
        if result!=expected:problems.append('trace_outside_allowed_additions')
    return {'trace_ok':not problems,'problems':problems,'summary':summary,'policy_release':release}
