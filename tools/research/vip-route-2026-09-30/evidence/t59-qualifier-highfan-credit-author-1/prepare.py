"""父代16窗闭合后冻结新来源和联合m1作者输入；不再评分或开桌。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t59-qualifier-highfan-credit-author-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from pathlib import Path
import hashlib
import json
import random

from hangma_bot.offline.qualifier_opponents import freeze_qualifier_compositions
from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents, run_vip_eoh_generate

HERE = Path(__file__).resolve().parent
PARENT = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t51-t48-same-formula-efficiency-author-1')
DIAG = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t58-qualifier-result-mechanism-1')


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def save(name,value):
    with (_project_file(_PROJECT_ROOT, HERE/name)).open('xb') as stream:
        stream.write(canonical(value)+b'\n')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    replay = json.loads((_project_file(_PROJECT_ROOT, DIAG/'PARENT-REPLAY-CLOSURE.json')).read_text())
    assert replay['complete'] and replay['actual_score_calls']==replay['actual_full_inputs_readback']==16
    old = json.loads((_project_file(_PROJECT_ROOT, PARENT/'S01-research.batch.json')).read_text())
    old['batch_id'] = 'vip-t59-qualifier-joint-highfan-credit-20261002'
    old['budgets']['model_calls'] = 2
    save('S01-generation.batch.json',old)
    batch_file = _project_file(_PROJECT_ROOT, HERE/'S01-generation.batch.json')
    batch = VipEohBatch.read(batch_file)
    parents = load_vip_parents([_project_file(_PROJECT_ROOT, PARENT/'S01-research-capacity')],batch)
    assert len(parents)==1 and parents[0]['identity']==replay['candidate_identity']
    save('PARENTS-FROZEN.json',parents)
    rng = random.SystemRandom()
    used = set()
    def roots(n,prefix):
        result=[]
        for index in range(n):
            seed=rng.randrange(1<<48,1<<63)
            while seed in used:
                seed=rng.randrange(1<<48,1<<63)
            used.add(seed)
            result.append({'root_id':f'{prefix}:{index+1:03}','seed':seed,
                'permutations':[[0,1,2,3],[1,2,3,0],[2,3,0,1],[3,0,1,2]]})
        return result
    fresh={'schema':'t59-new-source-before-author/1','pilot':roots(8,'t59-qualifier-pilot'),
        'reserved_confirmation':roots(128,'t59-qualifier-confirmation'),
        'rounds':8,'initial_scores':[0,0,0,0],
        'scope':'no WorldState/table generated here; pilot development, reserved confirmation withheld from author'}
    save('FRESH-ROOTS-BEFORE-AUTHOR.json',fresh)
    composition = {'schema':'t59-compositions-before-author/1','main_weak_fraction':0.6,
        'weak_split_automatic_normal_v0':[0.5,0.5],'human_prior_not_platform_measured':True,
        'A_C_same_per_root_four_rotations':True,
        'pilot':{str(f):freeze_qualifier_compositions(fresh['pilot'],weak_fraction=f) for f in (0.5,0.6,0.75)},
        'reserved_confirmation':{str(f):freeze_qualifier_compositions(fresh['reserved_confirmation'],weak_fraction=f) for f in (0.5,0.6,0.75)}}
    save('COMPOSITIONS-BEFORE-AUTHOR.json',composition)
    feedback=(_project_file(_PROJECT_ROOT, HERE/'FROZEN-FEEDBACK.txt')).read_text()
    emission=run_vip_eoh_generate(batch_file=batch_file,out_dir=_project_file(_PROJECT_ROOT, HERE/'S01-prompt-emission'),
        operator='m1',parent_paths=(_project_file(_PROJECT_ROOT, PARENT/'S01-research-capacity'),),feedback=feedback)
    files={str(p):sha(p) for p in [Path(__file__),batch_file,_project_file(_PROJECT_ROOT, HERE/'PARENTS-FROZEN.json'),
        _project_file(_PROJECT_ROOT, HERE/'FROZEN-FEEDBACK.txt'),_project_file(_PROJECT_ROOT, HERE/'FRESH-ROOTS-BEFORE-AUTHOR.json'),_project_file(_PROJECT_ROOT, HERE/'COMPOSITIONS-BEFORE-AUTHOR.json'),
        _project_file(_PROJECT_ROOT, DIAG/'NATURAL-PUBLIC-CASES.json'),_project_file(_PROJECT_ROOT, DIAG/'PARENT-REPLAY-CLOSURE.json'),_project_file(_PROJECT_ROOT, DIAG/'PARENT-ACTUAL-INPUTS-BEFORE-SCORE.jsonl.gz')]}
    save('AUTHOR-PREPARATION-CLOSED.json',{'schema':'t59-joint-author-preparation/1','status':'prepared',
        'operator':'m1','parent_candidate_id':parents[0]['identity']['candidate_id'],
        'prompt_sha256':emission['prompt_sha256'],'frozen_files':files,
        'actual_new_score_model_world_table_calls_in_preparation':0,'batch_max_new_proposals':2,
        'next':'one explicit delegated author only; root closes real mechanics and mechanism tests before fresh tables'})
    print({'prepared':True,'parents':1,'prior_actual_reference_scores':16,'new_scores_models_worlds_tables':0})


if __name__=='__main__':
    main()
