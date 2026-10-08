"""核验已完成强模型候选，按同根父代比较完整阶段开发效用。"""

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
import json
import statistics

import strong_seed_batch as batch
from verify_full_natural_results import verify_full_panel
from hangma_bot.simulation.artifacts import compute_rules_hash


def summarize(name, *, candidate_dir=None, parent_specs=None):
    """只处理完整提案；不删坏根、不用中途成绩决定停止。"""
    sub=batch.Path(candidate_dir) if candidate_dir is not None else batch.BATCH/name
    if parent_specs is None:
        parent_specs={parent_name:{'dir':batch.BATCH/parent_name,
            'source_sha256':batch.read(batch.BATCH/parent_name/'manifest.json')['source_sha256']}
            for parent_name in ['parent-a','parent-b']}
    if (sub/'batch-closure.json').exists():
        raise SystemExit('提案已关闭，禁止重写裁定')
    state=batch.search.av_state_load(batch.search.av_latest_state_path(sub/'run'))
    if state['status']!='ITERATION_COMPLETE':
        raise SystemExit('提案尚未完整结束')
    ok,why,_=batch.search.av_verify_run_identity(state)
    if not ok: raise SystemExit(why)
    idir=batch.Path(state['iter_dir'])
    source_sha=batch.digest((idir/'generation/candidate.py').read_bytes())
    contract=batch.read(batch.ROUTE/'contracts/group-dev-v1.json')
    rules_hash=compute_rules_hash(batch.ROUTE.parents[1])
    verification=[]; rows=[]; parents={}; own={}
    for mix in ['H','M']:
        child=batch.read(idir/('natural-'+mix)/'panel.json')
        if child['identity']['candidate_source_sha256']!=source_sha:
            raise ValueError('面板候选源码身份不一致')
        if child['identity']['panel_seed']!=2026092001:
            raise ValueError('面板来源种子改变')
        verification.append(verify_full_panel(child,contract,expected_identity=child['identity'],
            expected_root_indices=list(range(1,9)),expected_rules_hash=rules_hash))
        stats=next(iter(child['statistics']['by_candidate'].values()))['panels']['normal']['panels'][mix]
        own[mix]={k:stats[k] for k in ['mean_delta','standard_error','n_roots']}
        for parent_name,spec in parent_specs.items():
            parent=batch.read(batch.Path(spec['dir'])/('natural-'+mix)/'panel.json')
            if parent['identity']['candidate_source_sha256']!=spec['source_sha256']:
                raise ValueError('父代源码身份不一致')
            index={(s['root_index'],s['focal_anchor_seat']):s for s in parent['samples']}
            root_values={i:[] for i in range(1,9)}
            for sample in child['samples']:
                p=index[(sample['root_index'],sample['focal_anchor_seat'])]
                if p['root_content_digest']!=sample['root_content_digest']:
                    raise ValueError('父子根实际内容不一致')
                for key in ['stage_totals_by_participant','stage_place_points_by_participant','u_low','u_high']:
                    if p['raw_arms']['baseline'][key]!=sample['raw_arms']['baseline'][key]:
                        raise ValueError('共同V2臂未复现')
                a=sample['arms']['candidate'];b=p['arms']['candidate']
                root_values[sample['root_index']].append((a['u_low']-b['u_high'],a['u_high']-b['u_low']))
            for root,values in root_values.items():
                if len(values)!=4:raise ValueError('根缺座位配置')
                rows.append({'parent':parent_name,'opponent':mix,'root':root,
                    'delta_low':sum(x[0] for x in values)/4,'delta_high':sum(x[1] for x in values)/4})
    for parent_name in parent_specs:
        selected=[r for r in rows if r['parent']==parent_name]
        parents[parent_name]={'equal_mix_low':statistics.mean(r['delta_low'] for r in selected),
            'equal_mix_high':statistics.mean(r['delta_high'] for r in selected)}
    ledger=batch.read(sub/'run/av-ledger.json')
    if any(r['status']=='reserved' for r in ledger['reservations']):
        raise ValueError('仍有未结算预留')
    result={'status':'COMPLETE_DEVELOPMENT_ONLY','candidate_source_sha256':source_sha,
        'full_natural_results_verified':sum(x['full_results_verified'] for x in verification),
        'versus_v2':own,'equal_mix_vs_v2':sum(x['mean_delta'] for x in own.values())/2,
        'versus_parents':parents,'root_rows':rows,'common_v2_arms_reproduced':True,
        'spent':ledger['spent'],'usage_note':'native token charges are conservative reservation amounts, not actual usage',
        'release_eligible':False,'limitations':['16根开发评价，不是独立确认','不按改选数或模型名称选优','完整终端结果不是逐动作结算重算']}
    batch.write(sub/'full-result-reconciliation.json',{'results':verification})
    batch.write(sub/'batch-closure.json',result)
    print(json.dumps({k:result[k] for k in ['status','equal_mix_vs_v2','versus_parents','full_natural_results_verified']},ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('name',choices=list(batch.CONFIGS))
    summarize(p.parse_args().name)
