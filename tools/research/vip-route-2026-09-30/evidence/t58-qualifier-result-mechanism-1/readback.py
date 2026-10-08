"""只读核验T58全批分账、16窗与原实际输入复现，不重新评分或开桌。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t58-qualifier-result-mechanism-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import argparse
import gzip
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=_PROJECT_ROOT


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1<<20),b''):
            digest.update(block)
    return digest.hexdigest()


def locate(recorded):
    parts=Path(recorded).parts
    suffix=Path(*parts[parts.index('review'):])
    assert '..' not in suffix.parts
    return _project_file(_PROJECT_ROOT, REPO/suffix)


def audit():
    ledger=json.loads((_project_file(_PROJECT_ROOT, HERE/'CLOSURE.json')).read_text())
    extraction=json.loads((_project_file(_PROJECT_ROOT, HERE/'PUBLIC-EXTRACTION-CLOSURE.json')).read_text())
    replay=json.loads((_project_file(_PROJECT_ROOT, HERE/'PARENT-REPLAY-CLOSURE.json')).read_text())
    membership=json.loads((_project_file(_PROJECT_ROOT, HERE/'INPUT-MEMBERSHIP-CLOSURE.json')).read_text())
    assert all(x['complete'] for x in [ledger,extraction,replay,membership])
    assert ledger['actual_hand_rows']==8192 and ledger['actual_ge4_net_delta']==-48
    assert sum(ledger['actual_net_delta_by_mutually_exclusive_band'].values())==2337
    assert len(ledger['root_rows'])==128
    assert ledger['actual_ge8_source_clusters']=={'A':2,'C':3}
    assert extraction['raw_rows']['raw_rows']==1531520
    assert extraction['raw_rows']['candidate_self_scored_rows']==190837
    assert extraction['natural_cases']==extraction['natural_independent_roots']==16
    assert extraction['rare_paths']==10
    cases=json.loads((_project_file(_PROJECT_ROOT, HERE/'NATURAL-PUBLIC-CASES.json')).read_text())['cases']
    assert len(cases)==len({r['root_id'] for r in cases})==16
    assert replay['actual_score_calls']==replay['actual_full_inputs_readback']==16
    assert replay['normal_r18_fallbacks']==0
    assert not replay['strength_or_online_admission']
    seen=set()
    by_label={r['label']:r for r in replay['rows']}
    with gzip.open(_project_file(_PROJECT_ROOT, HERE/'PARENT-ACTUAL-INPUTS-BEFORE-SCORE.jsonl.gz'),'rt',encoding='utf-8') as stream:
        for line in stream:
            item=json.loads(line)
            label=item['label']
            assert label not in seen
            seen.add(label)
            index=int(label.split(':')[1])
            row,old=by_label[label],cases[index]
            assert row['status']=='SCORED' and row['all_legal_scores_traces_and_choice_equal']
            assert hashlib.sha256(canonical(item['candidate_view'])).hexdigest()==item['view_sha256']==row['actual_input_sha256']
            expected={c['action_key']:{'score':c['score'],'trace':c['trace']['detail']} for c in old['actual_recorded_candidates']}
            assert canonical(row['full_scores'])==canonical(expected)
            assert set(row['full_scores'])=={a['action_key'] for a in item['candidate_view']['actions']}
            assert row['selected_action_key']==old['selected_action_key']
    assert len(seen)==16 and membership['full_original_inputs_matched']==16
    assert set(membership['matches'])=={r['actual_input_sha256'] for r in replay['rows']}
    with gzip.open(_project_file(_PROJECT_ROOT, HERE/'RARE-PUBLIC-PREFIXES.json.gz'),'rt',encoding='utf-8') as stream:
        rare=json.load(stream)
    assert len(rare['paths'])==10
    assert sum(len(rows) for rows in rare['paths'].values())==extraction['rare_recorded_windows']
    # 文件映射去重后只哈希一次；不会重复评分，四个大原件也不全装内存。
    frozen={}
    for name in ['PLAN.json','PUBLIC-EXTRACTION-PLAN.json','PARENT-REPLAY-PLAN.json','INPUT-MEMBERSHIP-PLAN.json']:
        plan=json.loads((_project_file(_PROJECT_ROOT, HERE/name)).read_text())
        for path,digest in plan['frozen_files'].items():
            assert path not in frozen or frozen[path]==digest
            frozen[path]=digest
    assert all(sha(locate(path))==digest for path,digest in frozen.items())
    files={path.name:sha(path) for path in HERE.iterdir() if path.is_file() and path.name!='ROOT-READBACK.json'}
    return {'schema':'t58-root-readback/1','complete':True,'full_hand_ledger_rows':8192,
        'actual_parent_scores_full_inputs':16,'all_legal_scores_traces_and_choices_equal':True,
        'actual_inputs_match_original_T52':16,'development_roots':16,
        'rare_result_selected_paths_not_confirmation':10,'net_delta':2337,'ge4_net_delta':-48,
        'full_archive_sha256':files,'new_scores_models_worlds_tables_in_readback':0,
        'strength_or_online_admission':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--write-receipt',action='store_true')
    args=parser.parse_args()
    result=audit()
    if args.write_receipt:
        with (_project_file(_PROJECT_ROOT, HERE/'ROOT-READBACK.json')).open('xb') as stream:
            stream.write(canonical(result)+b'\n')
    else:
        assert result==json.loads((_project_file(_PROJECT_ROOT, HERE/'ROOT-READBACK.json')).read_text())
    print({'verified':True,'full_hand_ledger_rows':8192,'actual_parent_scores_inputs':16,
        'original_inputs_matched':16,'new_scores_worlds_tables_in_readback':0})
