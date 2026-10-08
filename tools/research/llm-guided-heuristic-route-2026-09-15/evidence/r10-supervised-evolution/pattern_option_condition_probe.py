"""最多四个预登记规则条件：去除牌河与积分偏好，检查牌型机制能否影响首选。"""

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
from dataclasses import replace
import strong_seed_batch as b
import pattern_option_batch as batch
import wealth_branch_probe as helper
import sitin_natural_panel as natural
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.policy.action_value_seeds import ActionValueScorer


def main():
    """仅按父代输入字段挑前四个条件，先冻结变换，再运行规则及候选。"""
    source=b.HERE/'stage-rank-preflight-20260920/panel.json'
    chosen=[]
    for row in b.read(source)['rows']:
        if row['origin'] not in ('real','new_real','piao_real'):continue
        req=helper.decision_request_from_json(row['record']['request'])
        v=helper.build_scoring_view(req).candidate_view()
        if any(a['action_type']=='hu' for a in v['actions']):continue
        acts=[a for a in v['actions'] if a['action_type']=='discard' and a['fact_kind']=='hand_progress']
        if not acts:continue
        best=min(a['shanten_after'] for a in acts)
        eligible=False
        for a in acts:
            n,q=a['standard_shanten_after'],a['seven_pairs_shanten_after']
            if n is None or q is None or a['shanten_after']!=best or abs(n-q) not in (1,2):continue
            primary=a['standard_useful_tiles'] if n<q else a['seven_pairs_useful_tiles']
            secondary=a['seven_pairs_useful_tiles'] if n<q else a['standard_useful_tiles']
            if primary is None or secondary is None:continue
            codes={t['code'] for t in primary}
            if any(t['code'] not in codes and t['remaining_estimate']>0 for t in secondary):eligible=True
        if eligible:chosen.append(row)
        if len(chosen)==4:break
    plan_path=batch.OUT/'conditional-trigger-plan.json'
    assert not plan_path.exists()
    b.write(plan_path,{'created_at_utc':b.search.utc_now(),'source_panel':str(source),'source_sha256':b.digest(source.read_bytes()),
        'selection':'按已冻结面板顺序，前四个无Hu、最小综合向听弃牌具有差1/2的次优牌型独有正支持的真实输入；仅用父代输入字段，未用候选分数筛选',
        'selected':[{'name':r['name'],'origin':r['origin'],'request_sha256':r['record']['request_sha256']} for r in chosen],
        'transform':'保留本人手牌、摸牌、规则状态、副露和墙余量；四座牌河置空、桌积分置0；用HangmaRules重新分析全部动作，不手填牌型事实',
        'maximum_rule_analyses':4,'decision':'条件首选仍0则停止，不追加第五例或改变变换；正例只证实可触发，不证明效果或历史可达',
        'model_calls':0,'simulated_tables':0,'release_eligible':False})
    sub=batch.OUT/batch.NAME
    state=b.search.av_state_load(b.search.av_latest_state_path(sub/'run'))
    parent=b.Path(b.read(batch.OUT/'manifest.json')['parent'])/'candidate.py'
    child=b.Path(state['iter_dir'])/'generation/candidate.py'
    scorers={n:ActionValueScorer(n,p.read_text()) for n,p in [('parent',parent),('candidate',child)]}
    rules=HangmaRules(RuleConfig('hangma-mvp-v10-public-counts',1,False))
    rows=[]
    for old in chosen:
        req=helper.decision_request_from_json(old['record']['request'])
        obs=replace(req.observation, discards=((),(),(),()), scores=(0,0,0,0))
        analysis=rules.analyze(obs,value_limits=natural.ValueAnalysisLimits())
        current=replace(req,observation=obs,rules=analysis)
        view=helper.build_scoring_view(current)
        results={}
        for label,scorer in scorers.items():
            answer=scorer.score(view)
            results[label]={'status':answer.status,'order':[e.action_key for e in sorted(answer.entries,key=lambda e:(-e.score,e.action_key))],
                'entries':[{'key':e.action_key,'score':e.score,'trace':dict(e.trace)} for e in answer.entries]}
        rows.append({'source_name':old['name'],'record':b.behavior.capture_request(current),'results':results,
            'first_changed':results['parent']['order'][:1]!=results['candidate']['order'][:1]})
    report={'cases':len(rows),'first_changed':sum(r['first_changed'] for r in rows),'rows':rows,
        'plan_sha256':b.digest(plan_path.read_bytes()),'source_sha256':b.digest(child.read_bytes()),
        'scope':'来自真实手牌的合成公开条件，经唯一规则模块计算；无完整历史可达证明，无效果样本',
        'selection_eligible':False,'release_eligible':False}
    b.write(sub/'rule-conditional-trigger-check.json',report)
    print('rule conditions',len(rows),'first changes',report['first_changed'],flush=True)


if __name__=='__main__':main()
