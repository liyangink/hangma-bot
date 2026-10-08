"""多人响应收集器通过真实公开模拟接口复现两臂，并验证压力世界能被抢先胡。"""

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
import json

import response_probe
import piao_bridge_stress
from piao_bridge_probe import cases


def test_response_root_and_complete_results_match_recorded_worlds():
    async def run():
        for case in response_probe.CASES:
            path=response_probe.DIRECTORY/(case['case_id']+'.jsonl.gz')
            recorded=json.loads(next(iter(gzip.open(path,'rt'))))
            actual=await response_probe.run_world(case,recorded['seed'])
            assert json.loads(json.dumps(actual))==recorded
            assert {r['trace'][0]['action'] for r in actual['arms'].values()}=={'pass','peng:'+case['offer']}
            assert all(sum(r['score_delta'])==0 for r in actual['arms'].values())
    asyncio.run(run())


def test_catch_play_does_not_prevent_opponent_self_draw_hu():
    async def run():
        for case in cases():
            path=piao_bridge_stress.DIRECTORY/(case['case_id']+'.jsonl.gz')
            rows=map(json.loads,gzip.open(path,'rt'))
            recorded=next(r for r in rows if r['arms']['bridge']['winner'] not in (None,0))
            actual=await piao_bridge_stress.run_world(case,recorded['seed'])
            assert json.loads(json.dumps(actual))==recorded
            assert actual['arms']['bridge']['score']<0
    asyncio.run(run())
