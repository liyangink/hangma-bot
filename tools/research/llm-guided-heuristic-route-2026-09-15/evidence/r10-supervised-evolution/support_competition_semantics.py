"""作者交付前冻结表示等价与缺事实保底，不预设作者的结构公式。"""

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
import argparse
import strong_seed_batch as b
import support_competition_batch as task
from check_discard_arithmetic import action, view
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.observation import PublicMeld
from hangma_bot.policy.action_value_seeds import ActionValueScorer

PATH=task.OUT/'semantic-inputs.json'
BASE=b.HERE/'v2-seed-terra-02/run/iterations/iter-01/generation/candidate.py'
FULL=('1w','1w','4w','5w','7w','7w','9b','1b','2b','3b','东','东','南','白')

def sample(hand, drawn=None, meld=False):
    """合成合同输入；向听与支持只测试评分数学，不声称由该手牌规则计算产生。"""
    actions=[]
    for code in ('1w','9b','东','南','白'):
        a=action(code,16,1)
        actions.append(replace(a,standard_shanten_after=1,standard_useful_tiles=a.useful_tiles))
    v=view(tuple(actions),familiar=())
    obs=replace(v.visible_state,my_hand=tuple(Tile(c) for c in hand),drawn_tile=Tile(drawn) if drawn else None)
    if meld:obs=replace(obs,melds=((PublicMeld(0,'chi',tuple(Tile(c) for c in ('1b','2b','3b')),3),),(),(),()))
    return replace(v,visible_state=obs)

def cases():
    """同一完整手牌的不同合法表示应完全同分；退化应等于无结构基线。"""
    v=sample(FULL);new=list(FULL);new.remove('9b');dup=list(FULL);dup.remove('东')
    short=list(FULL)
    for c in ('1b','2b','3b'):short.remove(c)
    short_draw=list(short);short_draw.remove('东')
    return [
        ('hand_only',v,'finite'),
        ('drawn_new_code',sample(new,'9b'),'equals:hand_only'),
        ('drawn_duplicate',sample(dup,'东'),'equals:hand_only'),
        ('hand_reverse',sample(tuple(reversed(FULL))),'equals:hand_only'),
        ('meld_hand_only',sample(short,meld=True),'finite'),
        ('meld_duplicate_draw',sample(short_draw,'东',True),'equals:meld_hand_only'),
        ('missing_draw',sample(new),'base'),
        ('extra_draw',sample(FULL,'9b'),'base'),
        ('missing_standard',replace(v,actions=tuple(replace(a,standard_shanten_after=None) for a in v.actions)),'base'),
        ('empty_standard_useful',replace(v,actions=tuple(replace(a,standard_useful_tiles=()) for a in v.actions)),'base'),
        ('nonbest_standard',replace(v,actions=tuple(replace(a,standard_shanten_after=2) for a in v.actions)),'base'),
    ]

def main(mode):
    """先保存原件与不变量，交付后只校验现存冻结输入。"""
    if mode=='freeze':
        assert not PATH.exists()
        b.write(PATH,{'at_utc':b.search.utc_now(),'runner_sha256':b.digest(b.Path(__file__).read_bytes()),
            'rows':[{'name':n,'view':v.candidate_view(),'invariant':i} for n,v,i in cases()],
            'base_sha256':b.digest(BASE.read_bytes()),'scope':'合成合同，不计效果样本；预期与候选公式无关'})
        print('frozen',len(cases()));return
    frozen=b.read(PATH)
    assert frozen['runner_sha256']==b.digest(b.Path(__file__).read_bytes())
    assert frozen['base_sha256']==b.digest(BASE.read_bytes())
    sub=task.OUT/task.NAME;state=b.search.av_state_load(b.search.av_latest_state_path(sub/'run'))
    source=b.Path(state['iter_dir'])/'generation/candidate.py'
    scorers={'candidate':ActionValueScorer('candidate',source.read_text()),'base':ActionValueScorer('base',BASE.read_text())}
    rows=[];seen={}
    for (name,v,invariant),raw in zip(cases(),frozen['rows'],strict=True):
        assert raw['name']==name and b.behavior.digest(raw['view'])==b.behavior.digest(v.candidate_view())
        results={k:s.score(v) for k,s in scorers.items()}
        scores={k:{e.action_key:e.score for e in r.entries} for k,r in results.items()};errors=[]
        if any(r.status!='SCORED' for r in results.values()):errors.append('status')
        if invariant=='base' and scores['candidate']!=scores['base']:errors.append('base_fallback')
        if invariant.startswith('equals:') and scores['candidate']!=seen[invariant[7:]]:errors.append('representation_equivalence')
        seen[name]=scores['candidate'];rows.append({'name':name,'invariant':invariant,'scores':scores,'errors':errors})
    report={'status':'PASS' if all(not r['errors'] for r in rows) else 'FAIL','rows':rows,'source_sha256':b.digest(source.read_bytes()),'input_sha256':b.digest(PATH.read_bytes())}
    out=sub/'semantic-check.json';assert not out.exists();b.write(out,report)
    print(report['status'],[(r['name'],r['errors']) for r in rows if r['errors']])

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','check']);main(p.parse_args().action)
