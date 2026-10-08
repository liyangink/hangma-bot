"""按作者固定公式手工推导的结构分与手牌口径反例；不复制候选循环。"""

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
import strong_seed_batch as b
import discard_shape_batch as batch
from check_discard_arithmetic import action, view
from hangma_bot.kernel.actions import Tile
from hangma_bot.policy.action_value_seeds import ActionValueScorer

FULL=('1w','1w','4w','5w','7w','7w','9b','1b','2b','3b','4b','5b','6b','6b')


def sample(hand,drawn):
    """仅合成评分合同事实，不声明给定向听/有效牌来自该合成手牌的规则计算。"""
    actions=[]
    for code in ('1w','9b'):
        a=action(code,16,1)
        actions.append(replace(a,standard_shanten_after=1,standard_useful_tiles=a.useful_tiles))
    v=view(tuple(actions),familiar=())
    return replace(v,visible_state=replace(v.visible_state,my_hand=tuple(Tile(c) for c in hand),
        drawn_tile=Tile(drawn) if drawn else None))


def cases():
    """弃1w拆对子留下1w、9b两孤张，弃9b无孤张；两者无活隔张。"""
    without_9b=list(FULL);without_9b.remove('9b')
    white=list(FULL);white[-1]='白'
    return [
        ('drawn_new_code',sample(without_9b,'9b'),{'discard:1w':-1.,'discard:9b':0.},True),
        ('no_separate_draw',sample(FULL,None),{'discard:1w':-1.,'discard:9b':0.},True),
        ('drawn_duplicate_code',sample(FULL[:-1],'6b'),{'discard:1w':-1.,'discard:9b':0.},True),
        ('missing_draw',sample(without_9b,None),{'discard:1w':0.,'discard:9b':0.},False),
        ('contradictory_extra_draw',sample(FULL,'9b'),{'discard:1w':0.,'discard:9b':0.},False),
        ('white_not_orphan',sample(white[:-1],'白'),{'discard:1w':-1.,'discard:9b':0.},True),
    ]


def run(initial=False):
    """独立预期同时检查实际总分差、trace与触发；不将“能评分”当机制有效。"""
    sub=batch.OUT/batch.NAME
    state=b.search.av_state_load(b.search.av_latest_state_path(sub/'run'))
    source=(sub/'run/iterations/iter-01/generation/candidate.py') if initial else b.Path(state['iter_dir'])/'generation/candidate.py'
    parent=b.Path(b.read(batch.OUT/'manifest.json')['parent'])/'candidate.py'
    scorers={k:ActionValueScorer(k,p.read_text()) for k,p in [('parent',parent),('candidate',source)]}
    rows=[]
    for name,v,expected,active in cases():
        results={k:s.score(v) for k,s in scorers.items()};before={e.action_key:e.score for e in results['parent'].entries}
        after={e.action_key:e.score for e in results['candidate'].entries};trace={e.action_key:dict(e.trace) for e in results['candidate'].entries}
        delta={k:after[k]-before[k] for k in before if k in after};errors=[]
        if any(r.status!='SCORED' for r in results.values()):errors.append('status')
        if delta!=expected:errors.append('independent_score_delta')
        for key in expected:
            detail=trace.get(key,{}).get('shape_v1',{})
            if detail.get('active')!=active:errors.append('activation:'+key)
            if detail.get('part')!=expected[key]:errors.append('trace_part:'+key)
            if active and (detail.get('orphan_slots')!=(2 if key=='discard:1w' else 0) or detail.get('live_gap_slots')!=0):errors.append('trace_counts:'+key)
        rows.append({'name':name,'view':v.candidate_view(),'expected_delta':expected,'expected_active':active,'actual_delta':delta,'errors':errors})
    out=sub/('first-answer' if initial else '.')/'hand-structure-arithmetic.json';assert not out.exists()
    report={'status':'PASS' if all(not r['errors'] for r in rows) else 'FAIL','source_sha256':b.digest(source.read_bytes()),
        'runner_sha256':b.digest(b.Path(__file__).read_bytes()),'rows':rows,
        'scope':'独立固定公式算术，非规则历史可达或效果样本；首答失败原样保留'}
    b.write(out,report);print(report['status'],[(r['name'],r['errors']) for r in rows if r['errors']],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--initial',action='store_true');a=p.parse_args();run(a.initial)
