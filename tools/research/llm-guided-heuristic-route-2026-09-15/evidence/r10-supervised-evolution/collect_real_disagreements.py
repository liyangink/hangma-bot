"""重放已消费开发根，收集父子在同一合法可见观察上的分歧；不作为新增效果样本。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import argparse
import hashlib
import json
import sys
from pathlib import Path
from collections import Counter

HERE=Path(__file__).resolve().parent
ROUTE=_project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
for p in (_project_file(_PROJECT_ROOT, ROUTE/'tools'),_project_file(_PROJECT_ROOT, ROUTE/'evidence/v4-impl/r9-gate2/run')):
    sys.path.insert(0,str(p))
import sitin_search as search
import sitin_natural_panel as natural
from p12_authorization import unified_document
from hangma_bot.policy.action_value import batch_to_ranked_candidates
from hangma_bot.policy.action_value_seeds import ActionValueScorer
from hangma_bot.policy.action_value_executor import WorkloadExceeded

PILOT=_project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r9-takeover-2026-09-19/pilot/run/iterations')
SOURCES={'parent':_project_file(_PROJECT_ROOT, PILOT/'iter-02/generation/candidate.py'),'child':_project_file(_PROJECT_ROOT, PILOT/'iter-03/generation/candidate.py')}


def digest(value):
    """固定 JSON 编码摘要；元组和列表统一按候选可见 JSON 表示比较。"""
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def reading(batch,view):
    """排名只用生产适配器，避免诊断程序再实现一套平分裁决。"""
    ranked=batch_to_ranked_candidates(batch,view.actions)
    return {'status':batch.status,'preferred':ranked[0].action_key if ranked else None,
            'scores':{item.action_key:item.score for item in batch.entries},
            'traces':{item.action_key:dict(item.trace) for item in batch.entries},'reason':batch.reason}


class ShadowScorer:
    """只把主评分器结果用于动作；对照评分器只读取相同 ScoringView，不能改变真实轨迹。"""
    def __init__(self,primary,shadow,out,context):
        self.primary=primary;self.shadow=shadow;self.name=primary.name;self.out=out;self.context=context
        self.counts=Counter();self.records=[];self.saved=0
    def score(self,view):
        """返回未修改的主评分批，记录两份评分及纯公开候选输入；不读取 WorldState。"""
        own=self.primary.score(view)
        observed=reading(own,view)
        try: other=reading(self.shadow.score(view),view)
        except (Exception,WorkloadExceeded) as exc:
            other={'status':'FAILED','preferred':None,'error':type(exc).__name__+': '+str(exc)}
        self.counts['views']+=1
        changed=observed['preferred']!=other['preferred']
        self.counts['preferred_changed']+=int(changed)
        self.counts['primary_abstain']+=int(own.status=='ABSTAIN')
        self.counts['shadow_failed']+=int(other['status']=='FAILED')
        self.counts['phase:'+view.visible_state.phase]+=1
        raw=view.candidate_view(); view_hash=digest(raw)
        row={'context':self.context,'view_sha256':view_hash,'observation':{
             'game_id':view.visible_state.game_id,'round_no':view.visible_state.round_no,
             'snapshot_seq':view.visible_state.snapshot_seq,'seat':view.visible_state.seat,
             'phase':view.visible_state.phase},'primary':observed,'shadow':other,
             'preferred_changed':changed,'kind':'same_observation_comparison'}
        if changed and self.saved<20:
            path=self.out/'views'/(view_hash+'.json');path.parent.mkdir(parents=True,exist_ok=True)
            if not path.exists():natural.write_json(path,{'schema':'sitin-real-development-view/1',
                'candidate_view':raw,'source':row['observation'],'collection_context':self.context,
                'source_policy':'primary follows unchanged program','real_observation':True,
                'information_boundary':'ScoringView.candidate_view only; no private world or future outcomes'})
            row['view_file']=str(path);self.saved+=1
        self.records.append(row)
        return own


def main():
    """固定重放 H/M 的 root01、座位0、父子各一个两桌阶段，最多8桌、0模型调用。"""
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',required=True)
    args=parser.parse_args();out=Path(args.out).resolve()
    if out.exists():raise SystemExit('诊断目录已存在；保留旧证据，不隐式重放')
    out.mkdir(parents=True)
    contract=json.loads((_project_file(_PROJECT_ROOT, ROUTE/'contracts/group-dev-v1.json')).read_text())
    auth=unified_document(batch_label='r10-known-root-diagnostic',authorization_id='r10-diagnostic-8-tables',
         accounts={'tables_full':8},issued_by='lead',issued_at_utc=search.utc_now(),legacy_alias=False)
    auth['issuance_basis']='用户明确授权 root 监督算法进化；只重放已消费开发根、最多8桌、0模型、0确认'
    natural.write_json(out/'authorization.json',auth)
    natural.require_authorization(auth)
    ledger=search.ActionValueLedger.load(out/'ledger.json',authorized_budgets=search.av_ledger_budgets_from_authorization(auth))
    source_text={k:p.read_text() for k,p in SOURCES.items()}
    natural.write_json(out/'manifest.json',{'schema':'sitin-real-view-collection/1',
        'sources':{k:{'path':str(SOURCES[k]),'sha256':hashlib.sha256(v.encode()).hexdigest()} for k,v in source_text.items()},
        'panel_seed':2026091901,'root_index':1,'focal_anchor_seat':0,'opponents':['H','M'],
        'planned_tables':8,'scoring_mode':'shadow_on_identical_visible_view','selection_eligible':False,
        'purpose':'已消费开发根诊断，不是新独立样本；插桩耗时不可用于线上性能验收'})
    all_records=[];stages=[];counts=Counter()
    for mix in ('H','M'):
        plans=natural.build_seat_stage_plans(contract=contract,opponent=mix,root_index=1,
                                            focal_seat=0,panel_seed=2026091901)
        for active in ('parent','child'):
            shadow='child' if active=='parent' else 'parent'
            context={'opponent':mix,'root_index':1,'panel_seed':2026091901,'active':active,
                     'shadow':shadow,'focal_anchor_seat':0,'tables':[p.table_id for p in plans]}
            collector=ShadowScorer(ActionValueScorer(active,source_text[active]),
                ActionValueScorer(shadow,source_text[shadow]),out,context)
            reservation=ledger.reserve(step_id='diagnostic:'+mix+':'+active,account='tables_full',amount=len(plans),
                note='已消费开发根重放；逐窗对照只用公开 ScoringView；不加入选留样本')
            try:
                result=natural.run_arm_stage(arm='candidate',plans=plans,candidate_scorer=collector,
                    opponent_policies=contract['panel']['opponent_scenarios'][mix]['opponent_policies'],
                    versions_block=natural.stage.contract_versions_block(contract),
                    step_limit=int(contract['stop']['step_limit']),value_limits=natural.ValueAnalysisLimits())
            finally:
                # 中断/无完整返回仍保守保留启动前预留；不把缺结果当作0成本。
                ledger.settle(reservation,usage_unknown=True,note='按最多两桌保守结算；成功后明确复核实际桌数')
            if result['status']=='complete':ledger.settle(reservation,actual=len(result['tables']))
            original=json.loads((_project_file(_PROJECT_ROOT, PILOT/('iter-02' if active=='parent' else 'iter-03')/('natural-'+mix)/'panel.json')).read_text())
            expected=next(s['raw_arms']['candidate'] for s in original['samples'] if s['focal_anchor_seat']==0)
            same=(result['stage_totals_by_participant']==expected['stage_totals_by_participant'])
            stages.append({'context':context,'counts':dict(collector.counts),'result':result,
                'original_stage_score':expected['focal_stage_score'],'reproduced_stage_totals':same})
            all_records.extend(collector.records);counts.update(collector.counts)
            natural.write_json(out/'stages.json',stages)
            print(json.dumps({'mix':mix,'active':active,'status':result['status'],
                'views':collector.counts['views'],'differences':collector.counts['preferred_changed'],
                'same_original_totals':same},ensure_ascii=False),flush=True)
    with (out/'comparisons.jsonl').open('w') as handle:
        for r in all_records:handle.write(json.dumps(r,ensure_ascii=False)+'\n')
    summary={'schema':'sitin-real-view-diagnostic/1','counts':dict(counts),
        'saved_views':len(list((out/'views').glob('*.json'))) if (out/'views').exists() else 0,
        'all_original_totals_reproduced':all(s['reproduced_stage_totals'] for s in stages),
        'spent':ledger.account_summary(),'selection_eligible':False,
        'has_real_same_observation_disagreement':counts['preferred_changed']>0}
    natural.write_json(out/'summary.json',summary);print(json.dumps(summary,ensure_ascii=False))
    if not summary['all_original_totals_reproduced']:raise SystemExit('插桩/环境复现不一致：不得作为已验证面板来源')
if __name__=='__main__':main()
