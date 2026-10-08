"""两个新续打臂与已封存旧臂配对；完整性核对后才给条件案例统计。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/big-hand-paths-2026-09-09'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from collections import Counter
import gzip
import hashlib
import json
import random

from lab import ROOT


def analyze(directory,previous_directory,comparisons,bootstrap_seed,*,output_filename='analysis.json'):
    """固定案例内配对重采样，再对案例等权平均；不推断自然桌赛总体。"""
    manifest=json.loads((directory/'persistent-freeze.json').read_text())
    summary=json.loads((directory/'persistent-summary.json').read_text())
    previous_summary=json.loads((previous_directory/'persistent-summary.json').read_text())
    if '/' in output_filename or not output_filename.endswith('.json'):
        raise ValueError('分析输出必须是目录内独立JSON文件，不能覆盖压缩原始记录')
    assert len(summary['cases'])==len(manifest['cases'])==len(previous_summary['cases'])
    for name,expected in manifest['source_sha256'].items():
        assert hashlib.sha256((_project_file(_PROJECT_ROOT, ROOT/name)).read_bytes()).hexdigest()==expected,name
    new_hashes={r['case_id']:r['sha256'] for r in summary['cases']}
    old_hashes={r['case_id']:r['sha256'] for r in previous_summary['cases']}
    per_case=[];outcomes={};grouped={name:[] for name in comparisons};rng=random.Random(bootstrap_seed)
    for case in manifest['cases']:
        cid=case['case']['case_id'];rows_filename=f'persistent-{cid}.jsonl.gz'
        assert hashlib.sha256((directory/rows_filename).read_bytes()).hexdigest()==new_hashes[cid]
        assert hashlib.sha256((previous_directory/rows_filename).read_bytes()).hexdigest()==old_hashes[cid]
        new=[json.loads(x) for x in gzip.open(directory/rows_filename,'rt')]
        old=[json.loads(x) for x in gzip.open(previous_directory/rows_filename,'rt')]
        assert [r['seed'] for r in new]==list(range(manifest['seed_range'][0],manifest['seed_range'][1]+1))
        groups={name:[] for name in comparisons}
        for a,b in zip(new,old,strict=True):
            assert (a['case_id'],a['seed'],a['source_sha256'])==(b['case_id'],b['seed'],b['source_sha256'])
            arms={**a['arms'],**b['arms']}
            for name,(new_arm,old_arm) in comparisons.items():groups[name].append(arms[new_arm]['score']-arms[old_arm]['score'])
            for name,result in arms.items():outcomes.setdefault(name,[]).append(result)
        per_case.append(dict(case_id=cid,deltas={name:sum(v)/len(v) for name,v in groups.items()}))
        for name,values in groups.items():grouped[name].append(values)
    effects={}
    for name,groups in grouped.items():
        boot=sorted(sum(sum(rng.choices(v,k=len(v)))/len(v) for v in groups)/len(groups) for _ in range(4000))
        effects[name]=dict(mean=sum(sum(v)/len(v) for v in groups)/len(groups),ci95=[boot[99],boot[3899]])
    stats={}
    for arm,results in outcomes.items():
        wins=[r for r in results if r['winner']==0]
        stats[arm]=dict(worlds=len(results),mean_score=sum(r['score'] for r in results)/len(results),own_hu=len(wins),
            mean_win_score=sum(r['score'] for r in wins)/len(wins) if wins else None,
            fan=dict(Counter(r['fan'] for r in wins)),details=dict(Counter('·'.join(r['details']) for r in wins)),
            changed_decisions=sum(sum(t['enhanced'] for t in r['trace']) for r in results),
            hu_declines=sum(r.get('hu_declines',0) for r in results))
    report=dict(schema='paired-conditional-analysis/1',
        scope=f'固定{len(per_case)}个构造起手，案例内重采样完整条件世界，再等权平均；非自然桌赛效果或新独立确认',
        sources_and_worlds_verified=True,bootstrap_seed=bootstrap_seed,stats=stats,effects=effects,cases=per_case)
    (directory/output_filename).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(effects=effects,stats=stats),ensure_ascii=False,indent=2))
    return report
