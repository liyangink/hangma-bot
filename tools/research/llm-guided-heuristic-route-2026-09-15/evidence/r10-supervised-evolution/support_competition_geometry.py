"""作者交付前冻结结构样例及手牌排列不变量；新公式数值另行独立手算。"""

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
from hangma_bot.hangma.interface import UsefulTileFact
from hangma_bot.policy.action_value_seeds import ActionValueScorer

PATH=task.OUT/'geometry-inputs-v2.json'


def cases():
    """合成评分合同形状，不声称这些手牌的真实向听与这里的直接事实一致。"""
    specs=[
        ('shared_pair_support',('5b','5b','6b','1w','1w','1w','东','东','东','南','南','8t','8t','白'),('5b','6b','8t')),
        ('recombined_sequence_and_adjacent',('4b','4b','5b','5b','6b','1w','1w','1w','东','东','东','南','南','白'),('4b','5b','6b')),
        ('made_sequence_and_triplets',('4b','5b','6b','1w','1w','1w','东','东','东','南','南','8t','8t','白'),('4b','5b','6b')),
        ('overlapping_sequence_chain',('1b','2b','3b','4b','5b','1w','1w','1w','东','东','东','南','南','白'),('1b','3b','5b')),
        ('four_copies_with_neighbors',('4b','4b','4b','4b','5b','6b','1w','1w','1w','东','东','东','白','白'),('4b','5b','6b')),
        ('honor_pair_and_number_pair',('5b','5b','6b','1w','1w','1w','东','东','东','南','南','北','北','白'),('5b','6b','南','北','白')),
    ]
    rows=[]
    for name,hand,codes in specs:
        assert len(hand)==14 and max(hand.count(c) for c in hand)<=4
        facts=tuple(UsefulTileFact(t,4-hand.count(t)) for t in ('2b','3b','4b','5b','6b','7b'))
        acts=tuple(replace(action(c,16,1),useful_tiles=facts,standard_shanten_after=1,standard_useful_tiles=facts) for c in codes)
        v=view(acts,familiar=());v=replace(v,visible_state=replace(v.visible_state,my_hand=tuple(Tile(c) for c in hand),drawn_tile=None))
        rows.append((name,v,None))
        for suffix,sequence in [('reverse',tuple(reversed(hand))),('rotate',hand[5:]+hand[:5])]:
            rows.append((name+'_'+suffix,replace(v,visible_state=replace(v.visible_state,my_hand=tuple(Tile(c) for c in sequence))),name))
    return rows


def main(mode):
    """保存结构原件；交付后要求同一多重集同分，不指定应选哪张牌。"""
    if mode=='freeze':
        assert not PATH.exists()
        b.write(PATH,{'at_utc':b.search.utc_now(),'runner_sha256':b.digest(b.Path(__file__).read_bytes()),
            'rows':[{'name':n,'view':v.candidate_view(),'equals':target} for n,v,target in cases()],
            'scope':'6类结构各原序/反序/轮转，共18个合成合同输入；非效果样本'})
        print('frozen geometry',len(cases()));return
    frozen=b.read(PATH);assert frozen['runner_sha256']==b.digest(b.Path(__file__).read_bytes())
    sub=task.OUT/task.NAME;state=b.search.av_state_load(b.search.av_latest_state_path(sub/'run'))
    source=b.Path(state['iter_dir'])/'generation/candidate.py';scorer=ActionValueScorer('competition-geometry',source.read_text())
    seen={};rows=[]
    for (name,v,target),raw in zip(cases(),frozen['rows'],strict=True):
        assert name==raw['name'] and b.behavior.digest(v.candidate_view())==b.behavior.digest(raw['view'])
        got=scorer.score(v);scores={e.action_key:e.score for e in got.entries};errors=[]
        if got.status!='SCORED':errors.append('status')
        if target and scores!=seen[target]:errors.append('hand_permutation_changed_scores')
        seen[name]=scores;rows.append({'name':name,'status':got.status,'scores':scores,'errors':errors})
    result={'status':'PASS' if all(not r['errors'] for r in rows) else 'FAIL','rows':rows,
            'source_sha256':b.digest(source.read_bytes()),'input_sha256':b.digest(PATH.read_bytes()),
            'scope':'只证明范围内排列不变量，不能代替新公式的独立算术或效果检验'}
    output=sub/'geometry-invariance.json';assert not output.exists();b.write(output,result)
    print(result['status'],[(r['name'],r['errors']) for r in rows if r['errors']])

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','check']);main(p.parse_args().action)
