"""用官方算分金例投影的规则条件夹具检查候选；非自然强度样本。"""

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
import sys,json,dataclasses
from pathlib import Path
sys.path.insert(0,'tools/research/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution')
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
path=Path('tests/fixtures/official/v23/fan-calc/cases.jsonl')
rows=[json.loads(line) for line in path.read_text().splitlines()]
rows=[r for r in rows if r['http_status']==200 and r['response'].get('hu') and r['request'].get('base',1)==1]
selected={}
for r in sorted(rows,key=lambda r:r['response']['fan']):
 key=(r['response']['fan'],r['request']['draw']=='白')
 if key not in selected:selected[key]=r
selected=list(selected.values())
assert len(selected)<=32
scorers={}
for name in b.CONFIGS:
 state=b.search.av_state_load(b.search.av_latest_state_path(b.BATCH/name/'run'));p=Path(state['iter_dir'])/'generation/candidate.py'
 scorers[name]=(ActionValueScorer('official-seed-rule-probe',p.read_text()),b.digest(p.read_bytes()))
rules=HangmaRules(RuleConfig('hangma-mvp-v10-public-counts',1,False));reports=[]
for number,r in enumerate(selected):
 q=r['request'];exp=r['response'];chain=q.get('chain',{'count':0,'piao':0})
 obs=_observation(q['hand'],q['draw'],chain=chain['count'],piao=chain['piao'],baotou=exp['baotou'])
 rivers=list(obs.discards);rivers[0]=(Tile('白'),)*chain['piao'];obs=dataclasses.replace(obs,discards=tuple(rivers))
 analysis=rules.analyze(obs,value_limits=ValueAnalysisLimits());cs={c.action_key:c for c in analysis.legal_candidates}
 hu=cs.get('hu');immediate=hu.value_facts.immediate_settlement if hu and hu.value_facts else None
 row={'tags':r['tags'],'request':q,'expected_fan':exp['fan'],'engine_hu':bool(hu),'engine_fan':immediate.fan if immediate else None,'cases':{}}
 if not hu or not immediate or immediate.fan!=exp['fan']:
  row['status']='RULE_PROJECTION_MISMATCH';reports.append(row);continue
 request=make_request(obs,analysis);full=dataclasses.replace(obs,my_hand=obs.my_hand+(obs.drawn_tile,));full_analysis=rules.analyze(full,value_limits=ValueAnalysisLimits());full_request=make_request(full,full_analysis)
 for name,(scorer,sha) in scorers.items():
  try:
   a=scorer.score(build_scoring_view(request));z=scorer.score(build_scoring_view(full_request));scores={e.action_key:e.score for e in a.entries};zs={e.action_key:e.score for e in z.entries};ordered=sorted(scores,key=lambda k:(-scores[k],k))
   row['cases'][name]={'status':a.status,'hu_first':bool(ordered) and ordered[0]=='hu','first':ordered[0] if ordered else None,'scores':scores,'hand_layout_same':a.status==z.status and scores==zs}
  except Exception as e:row['cases'][name]={'status':'ERROR','error':str(e)}
 row['status']='ENGINE_MATCHED_OFFICIAL_FAN';reports.append(row)
summary={name:{'scored':sum(r['cases'].get(name,{}).get('status')=='SCORED' for r in reports),'hu_not_first':sum(r['cases'].get(name,{}).get('hu_first') is False for r in reports),'layout_different':sum(r['cases'].get(name,{}).get('hand_layout_same') is False for r in reports)} for name in scorers}
b.write(b.BATCH/'official-seed-rule-probes.json',{'source_fixture_sha256':b.digest(path.read_bytes()),'candidate_sources':{n:v[1] for n,v in scorers.items()},'selection':'每个官方fan与是否财神摸牌组合固定取第一条','cases':reports,'summary':summary,'scope':'v23官方算分金例投影出的规则条件夹具，非完整自然轨迹，非当前平台重新抓取；只用当前规则产生动作/分值，不作为强度或赛事发布证据'})
print(json.dumps({'cases':len(reports),'rules_matched':sum(r['status']=='ENGINE_MATCHED_OFFICIAL_FAN' for r in reports),'summary':summary},ensure_ascii=False))
