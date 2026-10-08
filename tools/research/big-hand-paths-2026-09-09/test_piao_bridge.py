"""双财飘盲区的根事实与真实续打回归；不把构造结果当成策略上线资格。"""

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

from piao_bridge_probe import DIRECTORY, cases, run_world
from piao_bridge_official import inputs


def test_three_gold_roots_match_one_draw_plateau_and_reproduce_full_world():
    async def run():
        for case in cases():
            original=json.loads(next(iter(gzip.open(DIRECTORY/(case['case_id']+'.jsonl.gz'),'rt'))))
            actual=await run_world(case, original['seed'])
            assert json.loads(json.dumps(actual))==original
            assert actual['first_wait_scores']==[actual['immediate_score']]
            assert any(t['action']=='discard:白' for t in actual['arms']['bridge']['trace'])
            assert actual['arms']['bridge']['fan']>=actual['immediate_fan']*2
    asyncio.run(run())


def test_official_inputs_are_physical_and_keep_discarded_white_count():
    from collections import Counter
    rows=inputs()
    assert len(rows)>=12
    assert {r['request']['chain']['piao'] for r in rows}=={0,1,2,3}
    for row in rows:
        request=row['request']
        assert len(request['hand'])==13
        inventory=Counter(request['hand']+[request['draw']])
        inventory['白']+=request['chain']['piao']
        assert inventory['白']==4 and max(inventory.values())<=4
