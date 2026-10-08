"""活隔张双端计数、正负截顶与缺普通型事实的独立算术及真实首选核验。"""

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
import discard_shape_batch as task
from check_discard_shape_arithmetic import sample
from hangma_bot.hangma.interface import UsefulTileFact
from hangma_bot.policy.action_value_seeds import ActionValueScorer


def main():
    """预期由明确残余牌集合手算，随后对照候选实际分差和trace。"""
    sub=task.OUT/task.NAME;state=b.search.av_state_load(b.search.av_latest_state_path(sub/'run'))
    source=b.Path(state['iter_dir'])/'generation/candidate.py';parent=b.Path(b.read(task.OUT/'manifest.json')['parent'])/'candidate.py'
    scorers={'parent':ActionValueScorer('parent',parent.read_text()),'candidate':ActionValueScorer('candidate',source.read_text())}
    gap=sample(('1w','3w','5w','7w','9w','9b','东','东','南','南','西','西','北','北'),None)
    gap=replace(gap,actions=tuple(replace(a,standard_useful_tiles=tuple(UsefulTileFact(code,4) for code in ('2w','4w','6w','8w'))) for a in gap.actions))
    orphan=sample(('1w','5w','9w','1b','5b','9b','1t','5t','9t','东','东','南','南','西'),None)
    empty=replace(gap,actions=tuple(replace(a,standard_useful_tiles=()) for a in gap.actions))
    missing=replace(gap,actions=tuple(replace(a,standard_shanten_after=None) for a in gap.actions))
    specs=[('live_gaps_and_positive_cap',gap,{'discard:1w':(1.5,1,4),'discard:9b':(2.,0,5)},True),
        ('orphan_negative_cap',orphan,{'discard:1w':(-2.,8,0),'discard:9b':(-2.,8,0)},True),
        ('empty_standard_support',empty,{'discard:1w':(0.,None,None),'discard:9b':(0.,None,None)},False),
        ('missing_standard',missing,{'discard:1w':(0.,None,None),'discard:9b':(0.,None,None)},False)]
    rows=[]
    for name,v,expected,active in specs:
        outputs={k:s.score(v) for k,s in scorers.items()};before={e.action_key:e.score for e in outputs['parent'].entries};errors=[]
        if any(r.status!='SCORED' for r in outputs.values()):errors.append('status')
        actual={}
        for e in outputs['candidate'].entries:
            t=e.trace['shape_v1'];actual[e.action_key]=(e.score-before[e.action_key],t['orphan_slots'],t['live_gap_slots'])
            if actual[e.action_key]!=expected[e.action_key] or t['active']!=active:errors.append(e.action_key)
        rows.append({'name':name,'expected':expected,'actual':actual,'errors':errors,'view':v.candidate_view()})
    diagnostic=b.read(sub/'diagnostic-comparison.json');inputs=b.read(task.OUT/'diagnostic-panel.json');changes=[]
    for row,raw in zip(diagnostic['rows'],inputs['rows'],strict=True):
        if not row['first_changed']:continue
        request=b.behavior.decision_request_from_json(raw['record']['request'])
        choices={k:b.behavior.evaluate_request(s,row['name'],request) for k,s in scorers.items()}
        assert all(x['status']=='SCORED' for x in choices.values())
        changes.append({'origin':row['origin'],'name':row['name'],'parent':choices['parent']['action_key'],
            'candidate':choices['candidate']['action_key'],'actual_first_changed':choices['parent']['action_key']!=choices['candidate']['action_key']})
    report={'status':'PASS' if all(not r['errors'] for r in rows) and any(r['actual_first_changed'] for r in changes) else 'FAIL',
        'source_sha256':b.digest(source.read_bytes()),'runner_sha256':b.digest(b.Path(__file__).read_bytes()),
        'arithmetic':rows,'production_choice_changes':changes,'scope':'合成合同算术与已有真实窗口实际choose；不是新增效果样本'}
    output=sub/'extra-arithmetic-and-production-trigger.json';assert not output.exists();b.write(output,report)
    print(report['status'],[(r['name'],r['errors']) for r in rows],changes,flush=True)


if __name__=='__main__':main()
