"""核对工程胡牌消融只改变胡牌优先级；公开规则生成事实，非强度评测。"""

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
import sys
from dataclasses import replace
from pathlib import Path
import json
import strong_seed_batch as b
sys.path.insert(0,str(b.ROUTE.parents[1]))
from tests.unit.hangma.test_value_analysis import _observation
from tests.unit.policy.support import make_request
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.actions import Tile
from hangma_bot.policy.action_value_seeds import ActionValueScorer
from hangma_bot.policy.action_value_policy import build_scoring_view

out=b.HERE/'route-hu-priority-ablation-20260920'
manifest=b.read(out/'manifest.json')
original=Path(manifest['source_parent']).read_text();source=(out/'candidate.py').read_text()
assert b.digest(original.encode())==manifest['parent_sha256']
assert b.digest(source.encode())==manifest['candidate_sha256']
assert source==original.replace('    known_floor = min(known_scores)\n',(out/'replacement.txt').read_text())
left=ActionValueScorer('original-route',original);right=ActionValueScorer('hu-priority-ablation',source)
_,real=b.behavior.load_panel(b.HERE/'batch03-known-root-diagnostic/panel.json')
requests=[('real-development',name,r) for name,r in real]
golden=b.read(b.BATCH/'official-seed-rule-probes.json')
fixtures=[json.loads(line) for line in (b.ROUTE.parents[1]/'tests/fixtures/official/v23/fan-calc/cases.jsonl').read_text().splitlines()]
rules=HangmaRules(RuleConfig('hangma-mvp-v10-public-counts',1,False))
for case in golden['cases']:
    q=case['request'];matched=next(r for r in fixtures if r['request']==q and r['http_status']==200)
    chain=q.get('chain',{'count':0,'piao':0})
    obs=_observation(q['hand'],q['draw'],chain=chain['count'],piao=chain['piao'],baotou=matched['response']['baotou'])
    rivers=list(obs.discards);rivers[0]=(Tile('白'),)*chain['piao'];obs=replace(obs,discards=tuple(rivers))
    for label,o in [('separate',obs),('included',replace(obs,my_hand=obs.my_hand+(obs.drawn_tile,)))]:
        analysis=rules.analyze(o,value_limits=ValueAnalysisLimits())
        hu=next(c for c in analysis.legal_candidates if c.action_key=='hu')
        assert hu.value_facts.immediate_settlement.fan==case['expected_fan']
        requests.append(('official-condition-fixture',case['tags'][0]+'/'+label,make_request(o,analysis)))
rows=[]
for origin,name,request in requests:
    view=build_scoring_view(request);a=left.score(view);z=right.score(view)
    sa={e.action_key:e.score for e in a.entries};sz={e.action_key:e.score for e in z.entries}
    assert a.status==z.status=='SCORED' and sa.keys()==sz.keys()
    assert {k:v for k,v in sa.items() if k!='hu'}=={k:v for k,v in sz.items() if k!='hu'}
    before=min(sa,key=lambda k:(-sa[k],k));after=min(sz,key=lambda k:(-sz[k],k))
    if 'hu' in sz:assert after=='hu'
    else:assert sa==sz
    rows.append({'origin':origin,'case':name,'input_sha256':b.behavior.digest(view.candidate_view()),'before_first':before,'after_first':after,'non_hu_scores_unchanged':True,'before_hu':sa.get('hu'),'after_hu':sz.get('hu')})
b.write(out/'mechanical-difference-check.json',{'status':'PASS','script_sha256':b.digest(Path(__file__).read_bytes()),'source_sha256':manifest['candidate_sha256'],'rows':rows,'total_cases':len(rows),'changed_first':sum(r['before_first']!=r['after_first'] for r in rows),'note':'32真实开发窗+20官方算分条件各两种手牌表示；后40不等于40独立轨迹，不计效果样本'})
print({'cases':len(rows),'changed_first':sum(r['before_first']!=r['after_first'] for r in rows)})
