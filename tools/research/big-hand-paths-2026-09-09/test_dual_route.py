"""双路线选择的真实牌例；不把综合向听相同误认为两条路线均未受损。"""

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

from lab import observation,HangmaRules,RuleConfig,RULESET,request_for,DecisionBudget,ValueAnalysisLimits
from dual_route import DualRouteCombinedPolicy
from progress_guard import ProgressGuardCombinedPolicy
from upgrade_persistent import upgrade_policy


def request(hand='5t 2t 2w 发 5t 白 发 2w 2t 3w 4b 4w 4t 5t'):
    obs=observation(hand.split(),case_id='dual-route-test',wall=83,dealer=0)
    rules=HangmaRules(RuleConfig(RULESET,1,False))
    return request_for(obs,rules.analyze(obs,value_limits=ValueAnalysisLimits()))


def test_same_seven_distance_prefers_the_closer_standard_route():
    async def run():
        req=request();f={c.action_key:c.facts for c in req.rules.legal_candidates}
        old=await ProgressGuardCombinedPolicy().choose(req,DecisionBudget(10,11,12))
        new=await DualRouteCombinedPolicy().choose(req,DecisionBudget(10,11,12))
        assert old.candidates[0].action_key=='discard:5t'
        assert new.candidates[0].action_key=='discard:4t'
        assert f['discard:5t'].shanten_after==f['discard:4t'].shanten_after==1
        assert f['discard:5t'].seven_pairs_shanten_after==f['discard:4t'].seven_pairs_shanten_after==1
        assert f['discard:5t'].standard_shanten_after==2
        assert f['discard:4t'].standard_shanten_after==1
        assert {c.action_key for c in new.candidates}=={c.action_key for c in old.candidates}
        assert any(c.is_emergency for c in new.candidates)
        assert all(c.total_score==sum(p.value for p in c.score_parts) for c in new.candidates)
        assert await DualRouteCombinedPolicy().choose(req,DecisionBudget(10,11,12))==new
    asyncio.run(run())


def test_current_hu_upgrade_and_unknown_wall_keep_original_guarded_plan():
    async def run():
        req=request('1w 1w 3w 3w 5w 5w 2b 2b 4b 4b 6b 6b 8t 白')
        assert await DualRouteCombinedPolicy().choose(req,DecisionBudget(10,11,12))==await upgrade_policy().choose(req,DecisionBudget(10,11,12))
        req=request();req=replace(req,observation=replace(req.observation,remaining_tile_count=None))
        assert await DualRouteCombinedPolicy().choose(req,DecisionBudget(10,11,12))==await ProgressGuardCombinedPolicy().choose(req,DecisionBudget(10,11,12))
    asyncio.run(run())
