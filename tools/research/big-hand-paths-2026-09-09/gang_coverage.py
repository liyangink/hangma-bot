"""零改选原因审计：只重放原开发每根的0123变体，不增加独立强度样本。"""

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
from collections import Counter
from dataclasses import asdict
import gzip
import hashlib
import json
import time

from gang_value_tables import HERE,ROOT,RULESET,HangmaRules,RuleConfig,ValueAnalysisLimits,ValuesWhenNeeded
from upgrade_persistent import upgrade_policy
from hangma_bot.kernel.actions import Gang,GangKind,Discard
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2
from hangma_bot.policy.hu_upgrade import upgrade_risk_key
from hangma_bot.policy.hu_upgrade_calibration import RISK_CELLS
from hangma_bot.kernel.config import TournamentConfig,TimingConfig
from hangma_bot.application.audit_codec import decision_request_to_json
from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.offline.evaluate import drive_match,MatchDriverConfig
from hangma_bot.simulation.engine import SimulationEngine
from hangma_bot.simulation.interface import MatchSpec,SimulationChoice

DIRECTORY=_project_file(_PROJECT_ROOT, HERE/'gang-value-development')


class CoveragePolicy:
    """只记候选资格和原策略动作，不改变排序或为追求触发修改阈值。"""
    def __init__(self):
        self.policy=upgrade_policy()
        self.counts=Counter()
        self.records=[]
    async def choose(self,request,budget):
        plan=await self.policy.choose(request,budget)
        obs=request.observation
        if any(isinstance(c.action,Gang) for c in request.rules.legal_candidates):
            self.counts['any_legal_gang']+=1
        if not isinstance(plan.candidates[0].action,Gang):
            return plan
        self.counts['selected_gang']+=1
        if plan.candidates[0].action.kind is not GangKind.CONCEALED:
            self.counts['not_concealed']+=1
            return plan
        self.counts['selected_concealed']+=1
        blocked=[]
        if obs.melds[obs.seat]:blocked.append('already_open')
        if obs.rule_state.catch_play or obs.rule_state.chain_count or obs.gang_draw:blocked.append('special_lifecycle')
        if any(c.action_key=='hu' for c in request.rules.legal_candidates):blocked.append('hu_available')
        if not any((c.wall_band,c.threat)==upgrade_risk_key(obs) for c in RISK_CELLS):blocked.append('no_risk_group')
        discards=[c for c in request.rules.legal_candidates if isinstance(c.action,Discard)]
        seven=[c for c in discards if c.facts is not None and c.facts.seven_pairs_shanten_after==0]
        if not seven:blocked.append('not_seven_ready')
        for reason in blocked:self.counts[reason]+=1
        if not blocked:self.counts['structural_eligibility']+=1
        self.records.append(dict(blocked=blocked,request=decision_request_to_json(request),action=plan.candidates[0].action_key,
                                 seven_ready=[c.action_key for c in seven]))
        return plan


async def main():
    prior=json.loads((DIRECTORY/'freeze.json').read_text())
    for name,expected in prior['source_sha256'].items():
        assert hashlib.sha256((_project_file(_PROJECT_ROOT, ROOT/name)).read_bytes()).hexdigest()==expected
    old=list(map(json.loads,(DIRECTORY/'results.jsonl').read_text().splitlines()))
    selected=[r for r in old if r['seat_permutation']==[0,1,2,3] and 'v2_hu_upgrade_v1' in r['policy_ids_by_seat']]
    assert len(selected)==32
    manifest=dict(scope='重复32个开发根的0123基线桌赛，只用于零触发原因诊断；256个重复单局不增加强度样本',
        original_freeze_sha256=hashlib.sha256((DIRECTORY/'freeze.json').read_bytes()).hexdigest(),
        script_sha256=hashlib.sha256((_project_file(_PROJECT_ROOT, HERE/'gang_coverage.py')).read_bytes()).hexdigest(),
        source_hashes_verified=True)
    (DIRECTORY/'coverage-freeze.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    counts=Counter()
    started=time.monotonic()
    with gzip.open(DIRECTORY/'coverage-requests.jsonl.gz','xt',encoding='utf8') as stream:
        for index,row in enumerate(selected):
            assert row['scenario_id']==f'gang-value-development-{index}'
            rules=HangmaRules(RuleConfig(RULESET,1,False))
            config=TournamentConfig(1,8,rules.config,TimingConfig(1,1,3))
            policy=CoveragePolicy()
            spec=MatchSpec(row['game_key']['game_id'],row['scenario_id'],config,1180000+index,index%4,(0,0,0,0))
            outcome=await drive_match(engine=SimulationEngine(rules),spec=spec,
                policies_by_seat=(policy,*(ComparableHeuristicPolicyV2(monotonic=lambda:0) for _ in range(3))),
                rules=ValuesWhenNeeded(rules),choice_factory=SimulationChoice,
                config=MatchDriverConfig('logical',100000,BudgetPolicy(),row['scenario_id']),now_monotonic=lambda:0,wall_clock=None)
            assert outcome.status=='complete' and list(outcome.final_scores)==row['scores_after']
            assert not any(asdict(outcome.runtime_counts).values())
            counts.update(policy.counts)
            for record in policy.records:
                stream.write(json.dumps(record,ensure_ascii=False)+'\n')
    result=dict(tables_reexecuted=32,duplicate_hands=256,counts=counts,elapsed_seconds=time.monotonic()-started,
                table_scores_match_original=True)
    (DIRECTORY/'coverage.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    asyncio.run(main())
