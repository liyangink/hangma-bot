"""核对三批条件实验的输入、原始数据、冻结源码与完成条数；不重跑策略。"""

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
import gzip
import hashlib
import json

from lab import HERE, ROOT
from continuation import source_hand
from piao_bridge_stress import stressed_source


def main():
    verified={}
    for name in ('piao-bridge','piao-bridge-stress','response-opportunity'):
        directory=_project_file(_PROJECT_ROOT, HERE/name)
        freeze=json.loads((directory/'freeze.json').read_text())
        summary=json.loads((directory/'summary.json').read_text())
        for path,expected in freeze['source_sha256'].items():
            assert hashlib.sha256((_project_file(_PROJECT_ROOT, ROOT/path)).read_bytes()).hexdigest()==expected,path
        count=0
        for case in freeze['cases']:
            path=directory/(case['case_id']+'.jsonl.gz')
            assert hashlib.sha256(path.read_bytes()).hexdigest()==summary['cases'][case['case_id']]['sha256']
            rows=list(map(json.loads,gzip.open(path,'rt')))
            assert [r['seed'] for r in rows]==list(range(freeze['seed_range'][0],freeze['seed_range'][1]+1))
            for row in rows:
                if name=='response-opportunity':
                    source=source_hand(dict(case_id=case['case_id'],initial_hand=case['hand']+[case['offer']]),row['seed'])
                    source['initial']['world_payload']['dealer_seat']=1
                    difference=row['arms']['pass']['score']-row['arms']['peng']['score']
                else:
                    source=(stressed_source if name=='piao-bridge-stress' else source_hand)(case,row['seed'])
                    difference=row['arms']['bridge']['score']-row['arms']['hu']['score']
                assert hashlib.sha256(json.dumps(source,sort_keys=True).encode()).hexdigest()==row['source_sha256']
                assert row['delta']==difference
                for arm in row['arms'].values():
                    if 'score_delta' in arm:
                        assert sum(arm['score_delta'])==0 and arm['score_delta'][0]==arm['score']
            count+=len(rows)
        verified[name]=dict(worlds=count,hands=count*2,source_hashes='all_match',raw_hashes='all_match',
                            paired_scores='all_match')
    directory=_project_file(_PROJECT_ROOT, HERE/'piao-bridge/official')
    manifest=json.loads((directory/'manifest.json').read_text())
    for path,expected in manifest['sha256'].items():
        assert hashlib.sha256((directory/path).read_bytes()).hexdigest()==expected
    rows=list(map(json.loads,(directory/'responses.jsonl').read_text().splitlines()))
    assert len(rows)==manifest['cases']==12
    assert all(r['http_status']==200 and r['guide_version']==27 and not r['mismatch'] for r in rows)
    assert all(json.loads(r['response_raw'])==r['response'] for r in rows)
    verified['official']=dict(cases=12,guide_version=27,mismatches=0,raw_hashes='all_match')
    (_project_file(_PROJECT_ROOT, HERE/'opportunities-verification.json')).write_text(json.dumps(verified,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(verified,ensure_ascii=False))


if __name__=='__main__':
    main()
