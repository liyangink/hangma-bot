"""新弃牌结构作者交付前冻结的边界；不指定结构公式或最优动作。"""

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
from dataclasses import replace
import math
import strong_seed_batch as b
import discard_shape_batch as batch
from check_discard_arithmetic import action, view
from hangma_bot.policy.action_value_seeds import ActionValueScorer

PATH=batch.OUT/'boundary-inputs.json'


def cases():
    """真实正负首分歧及合同形状反例；合成项不证明规则历史可达。"""
    folder=b.HERE/'pattern-generalization-diagnostic-v2-20260920'
    audit=b.read(folder/'audit.json');rows=[]
    for i,row in enumerate(audit['first_cases']):
        record=b.read(folder/'windows'/(row['window_id']+'.json'))
        request=b.behavior.decision_request_from_json(record['request'])
        sample=b.behavior.build_scoring_view(request)
        rows.append((f'real_{i}',sample,'finite_complete'))
    original=rows[0][1]
    def add(sample,new):return replace(sample,actions=tuple(sorted(sample.actions+(new,),key=lambda a:a.action_key)))
    rows.extend([
        ('unknown_guard',add(original,action('',kind='pass')),'unknown_below_known'),
        ('hu_guard',add(original,action('',kind='hu')),'hu_first'),
        ('missing_hand',replace(original,visible_state=replace(original.visible_state,my_hand=(),drawn_tile=None)),'parent_scores'),
        ('hand_order',replace(original,visible_state=replace(original.visible_state,my_hand=tuple(reversed(original.visible_state.my_hand)))),'same_as_real_0'),
        ('missing_wall',replace(original,visible_state=replace(original.visible_state,remaining_tile_count=None)),'finite_complete'),
        ('missing_patterns',replace(original,actions=tuple(replace(a,standard_shanten_after=None,seven_pairs_shanten_after=None,standard_useful_tiles=None,seven_pairs_useful_tiles=None) for a in original.actions)),'finite_complete'),
        ('non_discard',view((action('4b',11,kind='peng'),action('',10,kind='pass'))),'parent_scores'),
        ('all_unknown',view((action('4b'),action('8t'))),'abstain'),
    ])
    return rows


def freeze():
    """保存父代预期；本步不读取作者原答。"""
    assert not PATH.exists()
    source=b.Path(b.read(batch.OUT/'manifest.json')['parent'])/'candidate.py'
    scorer=ActionValueScorer('parent-boundaries',source.read_text())
    rows=[]
    for name,sample,invariant in cases():
        got=scorer.score(sample)
        rows.append({'name':name,'view':sample.candidate_view(),'invariant':invariant,
            'parent_status':got.status,'parent_scores':{e.action_key:e.score for e in got.entries}})
    b.write(PATH,{'at_utc':b.search.utc_now(),'rows':rows,'parent_sha256':b.digest(source.read_bytes()),
        'runner_sha256':b.digest(b.Path(__file__).read_bytes()),'scope':'交付前冻结；合成反例不计效果样本'})
    print('frozen',len(rows),flush=True)


def check():
    """验收既定合同不变量；新公式另做独立手算。"""
    frozen=b.read(PATH);assert frozen['runner_sha256']==b.digest(b.Path(__file__).read_bytes())
    sub=batch.OUT/batch.NAME;state=b.search.av_state_load(b.search.av_latest_state_path(sub/'run'))
    source=b.Path(state['iter_dir'])/'generation/candidate.py';scorer=ActionValueScorer('shape-boundary',source.read_text())
    rows=[];real_scores=None
    for (name,sample,invariant),saved in zip(cases(),frozen['rows'],strict=True):
        assert name==saved['name'] and b.behavior.digest(sample.candidate_view())==b.behavior.digest(saved['view'])
        got=scorer.score(sample);scores={e.action_key:e.score for e in got.entries};errors=[]
        if got.status!=('ABSTAIN' if invariant=='abstain' else 'SCORED'):errors.append('status')
        if any(not math.isfinite(v) for v in scores.values()):errors.append('finite')
        if got.status=='SCORED' and set(scores)!={a.action_key for a in sample.actions}:errors.append('coverage')
        if name=='real_0':real_scores=scores
        if invariant=='parent_scores' and scores!=saved['parent_scores']:errors.append('parent_fallback')
        if invariant=='same_as_real_0' and scores!=real_scores:errors.append('hand_order_sensitive')
        if invariant=='unknown_below_known' and not (scores and scores.get('pass',math.inf)<min(v for k,v in scores.items() if k!='pass')):errors.append('unknown_guard')
        if invariant=='hu_first' and (not scores or sorted(scores,key=lambda k:(-scores[k],k))[0]!='hu'):errors.append('hu_guard')
        rows.append({'name':name,'invariant':invariant,'status':got.status,'scores':scores,'errors':errors})
    report={'status':'PASS' if all(not r['errors'] for r in rows) else 'FAIL','rows':rows,'source_sha256':b.digest(source.read_bytes()),'input_sha256':b.digest(PATH.read_bytes())}
    output=sub/'boundary-check.json';assert not output.exists();b.write(output,report)
    print(report['status'],[(r['name'],r['errors']) for r in rows if r['errors']],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','check']);a=p.parse_args()
    freeze() if a.action=='freeze' else check()
