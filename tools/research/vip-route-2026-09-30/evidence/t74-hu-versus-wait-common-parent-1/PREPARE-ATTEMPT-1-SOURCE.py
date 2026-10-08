"""先按公开面板冻来源，再读原全座位路径；不评分、不推进完整世界。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t74-hu-versus-wait-common-parent-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from pathlib import Path
import gzip, hashlib, json, sys

HERE=Path(__file__).resolve().parent
REPO=_PROJECT_ROOT
E=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence')
T67=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t67-second-joint-fixed-qualifier-confirmation-1')
PANEL=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t71-public-feedback-selector-1/selection-t67-1')
SCORES=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t67-closed-mechanism-readback-1/PANEL-ORIGINAL-SCORES.json')
AUTHOR=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t62-earned-highfan-joint-revision-preparation-1')

def canonical(value):
    """规范化审计JSON，不改变观察、牌、积分或事件序号。"""
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()

def pin(path):
    """流式内容身份，字节单位；无业务执行。"""
    h=hashlib.sha256();size=0
    with Path(path).open('rb') as stream:
        for piece in iter(lambda:stream.read(1<<20),b''):h.update(piece);size+=len(piece)
    return {'sha256':h.hexdigest(),'bytes':size}

def save(path,value):
    """预登记与结果仅新建，禁止覆盖旧失败、START或成绩。"""
    with Path(path).open('xb') as stream:stream.write(canonical(value)+b'\n')

def frame_key(window):
    return tuple(window[k] for k in ('game_id','round_no','trigger_seq','phase'))

def main():
    campaign=json.loads((_project_file(_PROJECT_ROOT, T67/'CAMPAIGN-CLOSURE.json')).read_text())
    assert campaign['whole_batch_valid'] and campaign['actual_started_tables']==1024
    selector=json.loads((_project_file(_PROJECT_ROOT, PANEL/'CLOSURE.json')).read_text());assert selector['complete']
    assert pin(_project_file(_PROJECT_ROOT, PANEL/'SELECTED-INPUTS.jsonl.gz'))['sha256']==selector['selected_archive_sha256']
    old=json.loads(SCORES.read_text());assert old['complete'] and old['selected_original_scores_read']==32
    with gzip.open(_project_file(_PROJECT_ROOT, PANEL/'SELECTED-INPUTS.jsonl.gz'),'rt') as stream:cases=[json.loads(line) for line in stream]
    chosen=[case for case in cases if case['public_facts']['direct_root_upgrade_actions'] or case['assigned_stratum']=='current_hu_no_local_upgrade']
    assert len(chosen)==18 and all(case['public_facts']['current_hu_net'] is not None for case in chosen)
    assert len({canonical(c['window_key']) for c in chosen})==18
    rows=[]
    for c in chosen:
        original=next(row for row in old['diagnostics'] if row['view_sha256']==c['view_sha256'] and row['window_key']==c['window_key'])
        scores=original['original_full_finite_candidate_scores_and_traces']
        first=original['original_selected_action_key'];wait=original['best_non_hu_action_key']
        assert first in ['hu',wait] and wait!='hu' and 'hu' in c['legal_action_keys']
        rows.append({'root_id':'t74:'+c['root_id'].split(':')[-1]+':'+str(c['window_key']['trigger_seq']),
            'mother_root':c['root_id'],'category':c['assigned_stratum'],'source_block':c['source_block'],
            'source_window':c['window_key'],'focal_observation':c['observation'],'focal_seat':c['window_key']['seat'],
            'match_id':c['window_key']['game_id'],'expected_input_sha256':c['view_sha256'],
            'expected_parent_scores':{row['action_key']:{'score':row['score'],'trace':row['trace']['detail']} for row in scores},
            'parent_first':first,'hu_first':'hu','wait_first':wait,
            'forced_first':wait if first=='hu' else 'hu','public_facts':c['public_facts']})
    save(_project_file(_PROJECT_ROOT, HERE/'SOURCE-SELECTION.json'),{'schema':'t74-public-frozen-hu-wait-selection/1',
        'selection_rule':'all14 previously selected direct-upgrade windows plus4 selected no-local-upgrade controls; original parent best non-Hu from full scores',
        'roots':[{k:r[k] for k in ('root_id','mother_root','category','source_window','parent_first','hu_first','wait_first')} for r in rows],
        'windows':18,'mothers':len({r['mother_root'] for r in rows}),
        'source_selection_uses_new_terminal_results':False,'new_business_calls':0,
        'arms':'P true parent, F one opposite first action then same parent; H/W results alias one of actual P/F, not re-executed duplicates'})
    files={}
    def bind(path):files[str(Path(path).resolve())]=pin(path)
    for p in [Path(__file__),_project_file(_PROJECT_ROOT, HERE/'run.py'),_project_file(_PROJECT_ROOT, HERE/'SOURCE-SELECTION.json'),_project_file(_PROJECT_ROOT, T67/'CAMPAIGN-CLOSURE.json'),_project_file(_PROJECT_ROOT, T67/'ROOT-READBACK.json'),
              _project_file(_PROJECT_ROOT, PANEL/'PLAN.json'),_project_file(_PROJECT_ROOT, PANEL/'CLOSURE.json'),_project_file(_PROJECT_ROOT, PANEL/'SELECTED-INPUTS.jsonl.gz'),SCORES,
              _project_file(_PROJECT_ROOT, AUTHOR/'S02-generation.batch.json'),_project_file(_PROJECT_ROOT, AUTHOR/'S02-model-output/candidate.py'),_project_file(_PROJECT_ROOT, AUTHOR/'S02-model-output/generation.json')]:
        bind(p)
    # 不以终局挑源；完整原路径只用于同起点恢复及P臂重现。
    for block in sorted({r['source_block'] for r in rows}):
        directory=_project_file(_PROJECT_ROOT, T67/('block-'+format(block,'02')))
        start=json.loads((directory/'START.json').read_text());bind(directory/'START.json');bind(directory/'end-freeze.json')
        wanted={r['match_id']:[] for r in rows if r['source_block']==block}
        for root in rows:
            if root['source_block']==block:
                root['composition']=next(x for x in start['opponent_compositions'] if x['root_id']==root['mother_root'])
                root['candidate_identity']=start['candidate_identity']
        source=directory/'decisions.jsonl.gz';bind(source)
        for rel,h in start['source_manifest'].items():
            assert pin(_project_file(_PROJECT_ROOT, REPO/rel))['sha256']==h,rel
            assert pin(directory/'code_snapshot'/rel)['sha256']==h,rel
            bind(_project_file(_PROJECT_ROOT, REPO/rel))
        with gzip.open(source,'rt') as stream:
            for line in stream:
                if not any(mid in line for mid in wanted):continue
                d=json.loads(line)
                if d['match_id'] not in wanted:continue
                assert d['status']=='chosen' and not any('action_value_failed' in x for x in d['degraded_reasons'])
                wanted[d['match_id']].append({k:d[k] for k in ('window_key','observation','legal_action_keys','selected_action_key','seat','permutation','initial_dealer_physical')})
        for root in rows:
            if root['source_block']!=block:continue
            original=wanted[root['match_id']];assert original
            root['permutation']=original[0]['permutation'];root['initial_dealer']=original[0]['initial_dealer_physical']
            assert root['permutation'][0]==root['focal_seat']
            frames=[];seen=set()
            for d in original:
                assert d['permutation']==root['permutation'] and d['initial_dealer_physical']==root['initial_dealer']
                key=canonical(d['window_key']);assert key not in seen;seen.add(key)
                if not frames or frame_key(frames[-1][0]['window_key'])!=frame_key(d['window_key']):frames.append([])
                frames[-1].append(d)
            cuts=[i for i,f in enumerate(frames) if any(d['window_key']==root['source_window'] for d in f)];assert len(cuts)==1
            cut=cuts[0];target=next(d for d in frames[cut] if d['window_key']==root['source_window'])
            assert target['observation']==root['focal_observation'] and target['selected_action_key']==root['parent_first']
            root['whole_prefix']=frames[:cut];root['current_hand_prefix']=[f for f in frames[:cut] if f[0]['window_key']['round_no']==root['source_window']['round_no']]
            root['target_frame']=frames[cut]
            root['original_hand_suffix']=[d for f in frames[cut:] if f[0]['window_key']['round_no']==root['source_window']['round_no'] for d in f]
        print({'source_block_read':block,'selected_tables':len(wanted)},flush=True)
    with gzip.open(_project_file(_PROJECT_ROOT, HERE/'SOURCE-MATERIALS.json.gz'),'xb') as stream:stream.write(canonical({'schema':'t74-known-natural-public-prefix/1','roots':rows})+b'\n')
    bind(_project_file(_PROJECT_ROOT, HERE/'SOURCE-MATERIALS.json.gz'))
    assert all(pin(Path(name))==digest for name,digest in files.items())
    save(_project_file(_PROJECT_ROOT, HERE/'PREPARED.json'),{'schema':'t74-hu-wait-common-parent-prepared/1','status':'prepared_no_START','files':files,
        'python_version':sys.version,'parent_package':str((_project_file(_PROJECT_ROOT, AUTHOR/'S02-model-output')).resolve()),
        'batch_file':str((_project_file(_PROJECT_ROOT, AUTHOR/'S02-generation.batch.json')).resolve()),'parent_identity':rows[0]['candidate_identity'],
        'windows':18,'mothers':len({r['mother_root'] for r in rows}),
        'budgets':{'wall_clock_seconds':5400,'max_continuations':36,'max_recovery_frames_per_root':5000,'steps_per_continuation':5000,
            'capture':{'max_view_json_bytes':67108864,'max_total_json_bytes':2147483648,'max_unique_views':12000}},
        'arm_order':['P','F'],'new_author_calls':0,'new_independent_roots_or_natural_tables':0,
        'scope':'same18 public frozen current-hand sources; one first-action cause under same continuation; not probabilities, full-table strength, deadlines or admission'})
    print({'prepared':True,'windows':18,'mothers':len({r['mother_root'] for r in rows}),'max_continuations':36})

if __name__=='__main__':main()
