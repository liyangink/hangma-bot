"""吃与暗杠根窗口、完整续打和原始分数守恒，通过公开接口检查。"""

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
import asyncio
import gzip
import hashlib
import json

from lab import ROOT
from meld_opportunity_probe import DIRECTORY,CASES,run_world


def test_five_meld_cases_reproduce_recorded_complete_worlds():
    async def run():
        for case in CASES:
            path=DIRECTORY/(case['case_id']+'.jsonl.gz')
            recorded=json.loads(next(iter(gzip.open(path,'rt'))))
            actual=await run_world(case,recorded['seed'])
            assert json.loads(json.dumps(actual))==recorded
            for arm in actual['arms'].values():
                assert sum(arm['score_delta'])==0
                assert arm['trace'][0]['phase']==('response_chi' if case['kind']=='chi' else 'draw')
    asyncio.run(run())


def test_all_meld_samples_and_sources_are_intact():
    freeze=json.loads((DIRECTORY/'freeze.json').read_text())
    summary=json.loads((DIRECTORY/'summary.json').read_text())
    for path,expected in freeze['source_sha256'].items():
        assert hashlib.sha256((_project_file(_PROJECT_ROOT, ROOT/path)).read_bytes()).hexdigest()==expected
    for case in CASES:
        path=DIRECTORY/(case['case_id']+'.jsonl.gz')
        assert hashlib.sha256(path.read_bytes()).hexdigest()==summary['cases'][case['case_id']]['sha256']
        rows=list(map(json.loads,gzip.open(path,'rt')))
        first,last=freeze['seed_ranges'][case['kind']]
        assert [r['seed'] for r in rows]==list(range(first,last+1))
        for row in rows:
            assert row['delta']==row['arms']['alternative']['score']-row['arms']['baseline']['score']
            assert all(sum(r['score_delta'])==0 and r['score']==r['score_delta'][0] for r in row['arms'].values())
