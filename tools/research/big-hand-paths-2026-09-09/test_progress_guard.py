"""实际续打分歧的回归；约束真实向听，仍允许普通型不退步时保留较远七对。"""

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
import json

from lab import HERE,DecisionBudget,HangmaRules,RuleConfig,RULESET,observation,request_for,ValueAnalysisLimits
from hangma_bot.application.audit_codec import decision_request_from_json,decision_request_to_json
from progress_guard import ProgressGuardCombinedPolicy
from upgrade_persistent import UpgradePersistentPolicy,upgrade_policy


def captured():return decision_request_from_json(json.loads((_project_file(_PROJECT_ROOT, HERE/'guard-ready-request.json')).read_text())['request'])


def test_real_trace_stays_ready_and_does_not_change_rule_facts_or_legal_plan():
    async def run():
        req=captured();before=decision_request_to_json(req)
        old=await UpgradePersistentPolicy().choose(req,DecisionBudget(10,11,12))
        new=await ProgressGuardCombinedPolicy().choose(req,DecisionBudget(10,11,12))
        facts={c.action_key:c.facts for c in req.rules.legal_candidates}
        assert old.candidates[0].action_key=='discard:2t'
        assert facts[old.candidates[0].action_key].shanten_after==1
        assert new.candidates[0].action_key=='discard:7w'
        assert facts[new.candidates[0].action_key].shanten_after==0
        assert facts[new.candidates[0].action_key].seven_pairs_shanten_after==1
        assert decision_request_to_json(req)==before
        assert {c.action_key for c in old.candidates}=={c.action_key for c in new.candidates}
        assert any(c.is_emergency for c in new.candidates)
        assert all(c.total_score==sum(p.value for p in c.score_parts) for c in new.candidates)
    asyncio.run(run())


def test_already_legal_seven_to_baotou_upgrade_is_unchanged():
    async def run():
        obs=observation('1w 1w 3w 3w 5w 5w 2b 2b 4b 4b 6b 6b 8t 白'.split(),case_id='guard-hu',wall=83,dealer=0)
        rules=HangmaRules(RuleConfig(RULESET,1,False));req=request_for(obs,rules.analyze(obs,value_limits=ValueAnalysisLimits()))
        a=await upgrade_policy().choose(req,DecisionBudget(10,11,12))
        b=await ProgressGuardCombinedPolicy().choose(req,DecisionBudget(10,11,12))
        assert a==b and b.candidates[0].action_key=='discard:8t'
    asyncio.run(run())


def test_same_distance_preference_is_preserved_without_a_five_percent_threshold():
    async def run():
        obs=observation('5t 2t 2w 发 5t 白 发 2w 2t 3w 4b 4w 4t 5t'.split(),case_id='guard-same',wall=83,dealer=0)
        rules=HangmaRules(RuleConfig(RULESET,1,False));req=request_for(obs,rules.analyze(obs))
        a=await UpgradePersistentPolicy().choose(req,DecisionBudget(10,11,12))
        b=await ProgressGuardCombinedPolicy().choose(req,DecisionBudget(10,11,12))
        assert a.candidates[0].action_key==b.candidates[0].action_key
        assert any(p.name=='七对持续续打消融' for p in b.candidates[0].score_parts)
    asyncio.run(run())
