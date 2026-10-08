"""实际暗杠机会成本根案例及保持其他动作完整计划的回归。"""

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
from dataclasses import replace

from gang_value_delay import GangValueDelayPolicy
from meld_opportunity_probe import CASES,root
from lab import request_for,DecisionBudget
from upgrade_persistent import ValueEvaluationEngine,upgrade_policy


def test_delays_only_the_proven_luxury_seven_waiting_conflict():
    async def run():
        for case in CASES[:3]:
            _,raw,world=root(case,1160000)
            decision=raw.frame(world).decisions[0]
            request=replace(request_for(decision.observation,ValueEvaluationEngine(raw).rules.analyze(decision.observation)),window_key=decision.window_key)
            baseline=await upgrade_policy().choose(request,DecisionBudget(10,11,12))
            actual=await GangValueDelayPolicy().choose(request,DecisionBudget(10,11,12))
            if case['case_id']=='gang-E':
                assert baseline.candidates[0].action_key=='gang:concealed:东'
                assert actual.candidates[0].action_key=='discard:中'
                assert {c.action_key for c in actual.candidates}=={c.action_key for c in baseline.candidates}
                missing=replace(request,rules=replace(request.rules,legal_candidates=tuple(replace(c,value_facts=None) for c in request.rules.legal_candidates)))
                assert await GangValueDelayPolicy().choose(missing,DecisionBudget(10,11,12))==await upgrade_policy().choose(missing,DecisionBudget(10,11,12))
            else:
                assert actual==baseline
    asyncio.run(run())
