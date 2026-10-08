"""冻结新根联合作者的公开反例与新来源；不评分、不生成世界。

原T75包因工程依赖变化不是当前可装载父代。它只作为明示的历史源码
参考，采用现有i1无父初始化接口，禁止伪造m1父身份或迁移旧成绩。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t97-natural-preparation-joint-root-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from pathlib import Path
from datetime import datetime, timezone
import gzip
import hashlib
import json

from hangma_bot.offline.vip_eoh_generate import VipEohBatch, run_vip_eoh_generate
from hangma_bot.offline.scoring_sources import REPO_ROOT

HERE = Path(__file__).resolve().parent
EVIDENCE = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence')


def canonical(value):
    """严格规范JSON用于身份，不将端点或公开容量解释为概率。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def pin(path):
    """流式核验只读原件的字节数和SHA256。"""
    h, size = hashlib.sha256(), 0
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1 << 20), b''):
            h.update(block)
            size += len(block)
    return {'sha256':h.hexdigest(),'bytes':size}


def save(name, value):
    """仅创建新文件，保留旧回复、失败和冻结计划。"""
    with (_project_file(_PROJECT_ROOT, HERE/name)).open('xb') as stream:
        stream.write(canonical(value)+b'\n')


def main():
    endpoints, targets, views, pins = [], [], {}, {}
    for label, directory in [
        ('T94','t94-eightfan-gap-known-case-1'),
        ('T95','t95-earlier-route-choice-known-case-1'),
        ('T96','t96-natural-set-single-action-known-case-1')]:
        d = _project_file(_PROJECT_ROOT, EVIDENCE/directory)
        reader = json.loads((d/'ROOT-READBACK.json').read_text())
        closure = json.loads((d/'CAUSAL-CLOSURE.json').read_text())
        assert reader['complete'] and closure['complete'] and closure['source_stable']
        assert all(pin(d/n) == h for n,h in reader['artifacts'].items())
        expected_paths = 3 if label == 'T96' else 6
        assert reader['actual_completed_continuations'] == expected_paths
        for n in ('ROOT-READBACK.json','CAUSAL-CLOSURE.json','PUBLIC-TARGETS.json','ORIGINAL-C-VIEWS.json.gz'):
            pins[str(d/n)] = pin(d/n)
        endpoints.append({'batch':label,'results':closure['results'],
            'scope':'known same root044; given-state conditional effect, not probability or gold action'})
        selected_windows = [r['source_window'] for r in closure['results']]
        selected = [r for r in json.loads((d/'PUBLIC-TARGETS.json').read_text())['targets']
                    if r['arm'] == 'C' and r['window_key'] in selected_windows]
        assert len(selected) == len(selected_windows)
        targets += [{**r,'label':label+':'+str(r['window_key']['trigger_seq'])} for r in selected]
        with gzip.open(d/'ORIGINAL-C-VIEWS.json.gz','rt') as stream:
            material = json.load(stream)
        collection = material['views'] if 'views' in material else list(material.values())
        for row in collection:
            digest = row['view_sha256']
            assert hashlib.sha256(canonical(row['view'])).hexdigest() == digest
            if digest in views:
                assert canonical(views[digest]) == canonical(row['view'])
            views[digest] = row['view']
    # 只给真正对应五个目标的公开输入，排除其他座位观察与后继牌码序列。
    assert len(targets) == 5 and len({r['window_key']['trigger_seq'] for r in targets}) == 5
    for row in targets:
        assert row['view_sha256'] in views
    save('PUBLIC-CAUSAL-FEEDBACK.json',{'schema':'t97-public-mechanism-feedback/1',
        'targets':targets,'endpoints':endpoints,'independent_sources':1,
        'hidden_world_or_future_draw_sequence_included':False,
        'scope':'all five targets are exposed development from one source; endpoint results are teacher labels'})
    with gzip.open(_project_file(_PROJECT_ROOT, HERE/'PUBLIC-TARGET-VIEWS.jsonl.gz'),'xb') as stream:
        for row in targets:
            stream.write(canonical({'label':row['label'],'view_sha256':row['view_sha256'],
                                    'view':views[row['view_sha256']]})+b'\n')
    reference = _project_file(_PROJECT_ROOT, EVIDENCE/'t75-net-upgrade-joint-author-1/S01-model-output/candidate.py')
    (_project_file(_PROJECT_ROOT, HERE/'T75-REFERENCE-SOURCE.py')).write_bytes(reference.read_bytes())
    old = _project_file(_PROJECT_ROOT, EVIDENCE/'t75-net-upgrade-joint-author-1/S01-generation.batch.json')
    raw = json.loads(old.read_text())
    raw['batch_id'] = 'vip-t97-natural-preparation-joint-root-20261003'
    raw['budgets']['model_calls'] = 1
    save('S01-generation.batch.json',raw)
    batch_file = _project_file(_PROJECT_ROOT, HERE/'S01-generation.batch.json')
    batch = VipEohBatch.read(batch_file)
    save('REFERENCE-IDENTITY.json',{'schema':'t97-explicit-historical-source-reference/1',
        'source':str(reference),'source_pin':pin(reference),
        'current_research_raw_source_identity':batch.identity(reference.read_text()),
        'original_generation':str(reference.parent/'generation.json'),
        'current_loadable_parent':False,'operator':'i1','formal_parents':[],
        'old_admission_or_scores_transferred':False,
        'reason':'current deps differ; use documented historical reference and existing root initialization, not a fabricated rebound role'})
    fresh = {}
    for stage, count in [('pilot',8),('reserved_confirmation',128)]:
        fresh[stage] = []
        for i in range(count):
            root = f't97-natural-preparation:{stage}:{i+1:03d}'
            seed = int.from_bytes(hashlib.sha256((root+':20261003:unseen').encode()).digest()[:8],'big') % 2**63
            fresh[stage].append({'root_id':root,'seed':seed,
                'permutations':[[(s+t)%4 for s in range(4)] for t in range(4)]})
    seeds = [r['seed'] for group in fresh.values() for r in group]
    assert len(set(seeds)) == 136
    save('FRESH-ROOTS-BEFORE-AUTHOR.json',{'schema':'t97-new-root-reservation/1',**fresh,
        'rounds':8,'initial_scores':[0,0,0,0],
        'main_weak_fraction_setting':0.6,'weak_type_split':[0.5,0.5],
        'comparison':'registered R18, fixed T75 raw research reference, one new joint root; paired same-wall four seats',
        'worlds_generated':0,'author_read_forbidden':True,
        'scope':'reserved only, no natural run authorized by this file alone'})
    feedback = (_project_file(_PROJECT_ROOT, HERE/'FROZEN-FEEDBACK.txt')).read_text()
    emission = run_vip_eoh_generate(batch_file=batch_file,out_dir=_project_file(_PROJECT_ROOT, HERE/'S01-prompt-emission'),
        operator='i1',parent_paths=(),feedback=feedback)
    assert emission['status'] == 'prompt_emitted' and emission['identity_stable']
    owned = ['prepare_author.py','FROZEN-FEEDBACK.txt','AUTHOR-TASK.txt',
             'PUBLIC-CAUSAL-FEEDBACK.json','PUBLIC-TARGET-VIEWS.jsonl.gz','T75-REFERENCE-SOURCE.py',
             'REFERENCE-IDENTITY.json','S01-generation.batch.json','FRESH-ROOTS-BEFORE-AUTHOR.json']
    pins.update({str(_project_file(_PROJECT_ROOT, HERE/n)):pin(_project_file(_PROJECT_ROOT, HERE/n)) for n in owned})
    report = _project_file(_PROJECT_ROOT, HERE.parent.parent/'T94-T96-METHOD-RECHECK.md')
    assert report.exists()
    pins[str(report)] = pin(report)
    save('AUTHOR-PREPARATION-CLOSED.json',{'schema':'t97-joint-root-author-preparation/1',
        'operator':'i1','formal_parents':[],'historical_reference_source_unmodified':True,
        'max_new_proposals_in_joint_batch':2,'proposal_number':1,
        'requested_model':'gpt-6.1-sol','requested_effort':'max',
        'underlying_calls_and_tokens':None,'prompt_sha256':emission['prompt_sha256'],
        'frozen_files':pins,'created_at_utc':datetime.now(timezone.utc).isoformat(),
        'status':'prepared_no_author','actual_new_model_scores_rules_worlds_tables':0,
        'family':'existing natural composition research, not a fourth admitted family',
        'current_batch_formula_limit':2,'specialist_admission':False,'release':False})
    print({'prepared':True,'public_targets':5,'independent_sources':1,'fresh_roots_reserved':136,
           'operator':'i1','new_business_calls':0})


if __name__ == '__main__':
    main()
