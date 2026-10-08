"""作者前冻结公开输入、实际v3参考评分及新来源；不读取未来世界。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t48-v3-natural-highfan-joint-author-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import gzip
import hashlib
import json
import random
from pathlib import Path
from dataclasses import asdict

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.kernel.observation import CompetitionContext
from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
from hangma_bot.offline.vip_eoh_generate import VipEohBatch, run_vip_eoh_generate, write_vip_seed_parent
from hangma_bot.policy.action_value_executor import ActionValueExecutor
from hangma_bot.policy.interface import DecisionRequest
from hangma_bot.policy.route_vip_heuristic import build_vip_route_scoring_view

HERE=Path(__file__).resolve().parent
E=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence')


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def save(name,value):
    with (_project_file(_PROJECT_ROOT, HERE/name)).open('xb') as stream: stream.write(canonical(value)+b'\n')


def sha(raw): return hashlib.sha256(raw).hexdigest()


def main():
    batch=VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE/'S01-generation.batch.json'))
    source=(_project_file(_PROJECT_ROOT, E/'t25-public-assistance-cost-control-author-1/S01-model-output/candidate.py')).read_text()
    old_path=_project_file(_PROJECT_ROOT, E/'t35-same-input-mechanics-1/SLOTS.json')
    slots=json.loads(old_path.read_text())
    cases=[{'label':r['source_group'],'observation':r['observation'],'window_key':r['window_key'],
            'original_slot':r['slot_no'],'source_path':str(old_path),'source_sha256':sha(old_path.read_bytes())}
           for r in slots if r['slot_no']>=258]
    for i in range(1,5):
        path=_project_file(_PROJECT_ROOT, E/f't40-t25-ordinary-first-choice-causal-1/root-{i:02}/original_C_start/COMMON-START.json')
        row=json.loads(path.read_text())
        cases.append({'label':f'T40-ordinary-public-start-{i}', 'observation':row['focal_observation'],
            'window_key':row['target_window'],'source_path':str(path),'source_sha256':sha(path.read_bytes())})
    save('PUBLIC-CASES.json',{'schema':'t48-public-casebook/1','cases':cases,
        'scope':'20 exposed development public observations; not confirmation or action gold'})
    summary=[]
    executor=ActionValueExecutor(source,max_operations=batch.max_operations,
        max_local_collection_size=batch.projection_limits.max_nodes)
    with gzip.open(_project_file(_PROJECT_ROOT, HERE/'ACTUAL-V3-REFERENCE-INPUTS.jsonl.gz'),'wb') as stream:
        for i,row in enumerate(cases):
            obs=observation_from_json(row['observation']);key=window_key_from_json(row['window_key'])
            rules=HangmaRules(batch.rule_config).analyze(obs,route_limits=batch.route_limits)
            request=DecisionRequest(obs,CompetitionContext('T48-author-development',None,None,None,None,(),0),
                rules,f'T48-public-{i}',key.trigger_seq,key,())
            view=build_vip_route_scoring_view(request,batch.rule_config,limits=batch.projection_limits)
            dto=view.candidate_view();raw=canonical(dto)
            # 完整真实候选输入先持久保存，参考源码评分才发生。
            stream.write(canonical({'case_index':i,'view_sha256':sha(raw),'candidate_view':dto})+b'\n');stream.flush()
            score=executor.score_vip_route(view)
            roots={n.node_key:n for n in view.nodes}
            summary.append({'case_index':i,'label':row['label'],'window_key':row['window_key'],
                'white_count':sum(t.code=='白' for t in obs.my_hand)+int(obs.drawn_tile is not None and obs.drawn_tile.code=='白'),
                'wall':obs.remaining_tile_count,'current_legal_hu':any(a.action_type=='hu' for a in view.actions),
                'nodes':len(view.nodes),'complete_reference_score':score.status=='SCORED',
                'operations':executor.last_operation_count,'view_sha256':sha(raw),'view_json_bytes':len(raw),
                'scores':[{'action_key':x.action_key,'score':x.score} for x in score.entries],
                'direct_waiting_roots':[{'action_key':a.action_key,'waiting':asdict(roots[a.node_key].waiting)}
                    for a in view.actions if roots[a.node_key].waiting is not None]})
    save('AUTHOR-INPUT-SUMMARY.json',{'schema':'t48-v3-reference/1','reference_identity':batch.identity(source),
        'reference_role':'historical T25 source re-scored under current v3 engineering identity; not generation parent or admission',
        'cases':summary,'source_manifest_stable':batch.identity(source)==batch.identity(source),'new_model_world_table_calls':0})
    # 作者只看公开开发输入；此独立来源未生成手牌、未执行世界或评分。
    rng=random.SystemRandom();used=set()
    def roots(n,prefix):
        out=[]
        for i in range(n):
            seed=rng.randrange(1<<48,1<<63)
            while seed in used: seed=rng.randrange(1<<48,1<<63)
            used.add(seed);out.append({'root_id':f'{prefix}:{i+1:03}','seed':seed,
                'permutations':[[0,1,2,3],[1,2,3,0],[2,3,0,1],[3,0,1,2]]})
        return out
    save('FRESH-ROOTS-BEFORE-AUTHOR.json',{'schema':'t48-fresh-source-prereg/1','pilot':roots(8,'t48-qualifier-pilot'),
        'reserved_confirmation':roots(128,'t48-qualifier-confirmation'),'scope':'never generated here; pilot development, confirmation not sent to author',
        'initial_scores':[0,0,0,0],'rounds':8,'weak_fraction_primary':0.6,'sensitivity':[0.5,0.75],
        'opponent_composition_frozen_before_execution':True,'no_table_START':True})
    write_vip_seed_parent(_project_file(_PROJECT_ROOT, HERE/'current-manual-seed'),_project_file(_PROJECT_ROOT, HERE/'S01-generation.batch.json'))
    feedback=(_project_file(_PROJECT_ROOT, HERE/'FROZEN-FEEDBACK.txt')).read_text()
    result=run_vip_eoh_generate(batch_file=_project_file(_PROJECT_ROOT, HERE/'S01-generation.batch.json'),out_dir=_project_file(_PROJECT_ROOT, HERE/'S01-prompt-emission'),
        operator='i1',feedback=feedback)
    save('AUTHOR-PREPARATION-CLOSED.json',{'status':'prepared','public_cases':len(cases),'actual_v3_reference_scores':len(summary),
        'new_models':0,'new_worlds':0,'new_tables':0,'prompt_sha256':result['prompt_sha256'],
        'reference_identity':batch.identity(source)})
    print({'prepared':len(summary),'all_reference_scored':all(x['complete_reference_score'] for x in summary)})


if __name__=='__main__': main()
