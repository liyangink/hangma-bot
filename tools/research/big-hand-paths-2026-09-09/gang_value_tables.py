"""缓杠候选对等胡基线的完整桌赛；按新根牌山/四换座预登记评估。"""

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
import argparse
import asyncio
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
import gzip
import hashlib
import json
import time

from lab import HERE,ROOT,RULESET,HangmaRules,RuleConfig,ComparableHeuristicPolicyV2,ValueAnalysisLimits
from gang_value_delay import GangValueDelayPolicy
from upgrade_persistent import upgrade_policy
from run_tables import RecordingEngine
from hangma_bot.application.audit_codec import decision_request_to_json
from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.kernel.config import TournamentConfig,TimingConfig
from hangma_bot.offline.evaluate import MatchExperiment,PolicyDeclaration,MatchSeedSpec,run_match_experiment,write_report_files
from hangma_bot.offline.evaluation_results import write_results_jsonl
from hangma_bot.offline.evaluation_statistics import summarize_results
from hangma_bot.simulation.engine import SimulationEngine
from hangma_bot.simulation.interface import MatchSpec,SimulationChoice
from hangma_bot.simulation.artifacts import compute_rules_hash

BASE='v2_hu_upgrade_v1';CAND='v2_gang_value_research_v1'


class ValuesWhenNeeded:
    """胡、已有爆头或有杠且有七对听牌弃牌时计算生产价值事实。"""
    def __init__(self,rules):self.rules=rules
    def analyze(self,observation):
        analysis=self.rules.analyze(observation)
        if observation.rule_state.baotou or any(c.action_key=='hu' for c in analysis.legal_candidates) or (any(c.action_key.startswith('gang:') for c in analysis.legal_candidates) and any(c.action_key.startswith('discard:') and c.facts is not None and c.facts.seven_pairs_shanten_after==0 for c in analysis.legal_candidates)):
            return self.rules.analyze(observation,value_limits=ValueAnalysisLimits())
        return analysis


class AuditPolicy:
    """改选保留完整可见请求，未来牌墙及对手暗牌不会进入策略。"""
    def __init__(self,policy):self.policy=policy;self.changes=[]
    async def choose(self,request,budget):
        plan=await self.policy.choose(request,budget)
        old = await upgrade_policy().choose(request,budget) if isinstance(self.policy,GangValueDelayPolicy) else plan
        if plan.candidates and plan.candidates[0].action_key != old.candidates[0].action_key:
            self.changes.append(dict(baseline_action=old.candidates[0].action_key,request=decision_request_to_json(request),action=plan.candidates[0].action_key,
                reasons=plan.candidates[0].reasons,score_parts=[asdict(p) for p in plan.candidates[0].score_parts]))
        return plan


def root_run(item):
    phase,index,seed=item;raw=HangmaRules(RuleConfig(RULESET,1,False));rules_hash=compute_rules_hash(ROOT)
    config=TournamentConfig(1,8,raw.config,TimingConfig(1,1,3))
    ids=[BASE,CAND,'opp-v2-1','opp-v2-2','opp-v2-3']
    policies={BASE:AuditPolicy(upgrade_policy()),CAND:AuditPolicy(GangValueDelayPolicy()),
        **{pid:AuditPolicy(ComparableHeuristicPolicyV2(monotonic=lambda:0)) for pid in ids[2:]}}
    exp=MatchExperiment('matches','logical',PolicyDeclaration(BASE,BASE),PolicyDeclaration(CAND,CAND),
        tuple(PolicyDeclaration(pid,'weighted_heuristic_v2') for pid in ids[2:]),config,
        (MatchSeedSpec(seed,f'gang-value-{phase}-{index}'),),
        ((0,1,2,3),(1,2,3,0),(2,3,0,1),(3,0,1,2)),index%4,(0,0,0,0),
        simulation_version='simulation-v1',match_id_prefix='gang-value')
    engine=RecordingEngine(SimulationEngine(raw,rules_hash=rules_hash))
    out=asyncio.run(run_match_experiment(exp,engine=engine,spec_factory=MatchSpec,choice_factory=SimulationChoice,
        policies_by_id=policies,rules=ValuesWhenNeeded(raw),rules_hash=rules_hash,now_monotonic=lambda:0,
        wall_clock=None,budget_policy=BudgetPolicy()))
    return out.results,engine.hands,policies[CAND].changes,list(out.excluded)


def run(args):
    directory=_project_file(_PROJECT_ROOT, HERE/f'gang-value-{args.phase}');directory.mkdir(exist_ok=False)
    count,start={'smoke':(1,1182000),'development':(32,1180000),'confirmation':(128,1190000)}[args.phase]
    if args.phase=='confirmation':
        prior=json.loads((_project_file(_PROJECT_ROOT, HERE/'gang-value-development/verification.json')).read_text())
        assert prior['mean_delta']>0 and prior['reliability_pass']
        # 只读取预先声明的开发许可，不以确认结果追加调参。
    files=sorted(p for p in (_project_file(_PROJECT_ROOT, ROOT/'src/hangma_bot')).rglob('*') if p.suffix in ('.py','.c','.h','.so'))
    files += [_project_file(_PROJECT_ROOT, HERE/name) for name in ['gang_value_tables.py','gang_value_delay.py','persistent_seven.py',
        'upgrade_persistent.py','run_tables.py','lab.py']]
    freeze=dict(schema='gang-value-tables/1',phase=args.phase,roots=count,seed_range=[start,start+count-1],
        hands_per_table=8,seat_rotations=4,initial_dealer='root_index % 4',ruleset=RULESET,you_cai_bi_kao=False,
        baseline=BASE,candidate=CAND,opponents=['weighted_heuristic_v2']*3,
        value_scope='optional production value facts when Hu/baotou or Gang and seven-ready discard coexist',
        scope='完整自然桌赛增量；研究策略逻辑时钟，不代表线上计时门禁或可用枚举',
        candidate_rule='只改原等胡选门清暗杠的零链非胡窗口；弃牌保留自然四张且七对已听，普通进张数不低于杠补，折扣后下一摸质量高于立即杠补1.1倍；模型近似，未成胡后的剩余价值不在标尺内',
        gate='development mean>0 and reliability pass permits consideration of new independent confirmation; release still requires original goals, real timing and human review',
        source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
    (directory/'freeze.json').write_text(json.dumps(freeze,ensure_ascii=False,indent=2)+'\n')
    results=[];hands=[];changes=[];excluded=[];started=time.monotonic()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for index,(rows,h,c,e) in enumerate(pool.map(root_run,[(args.phase,i,start+i) for i in range(count)])):
            results.extend(rows);hands.extend(h);changes.extend(c);excluded.extend(e)
            print(args.phase,index+1,'/',count,'route_changes',len(changes),flush=True)
    write_results_jsonl(directory/'results.jsonl',results)
    for name,rows in [('hands',hands),('changes',changes)]:
        with gzip.open(directory/f'{name}.jsonl.gz','xt',encoding='utf8') as stream:
            for row in rows:stream.write(json.dumps(row,ensure_ascii=False)+'\n')
    summary=summarize_results(results,baseline_policy_id=BASE,challenger_policy_id=CAND,
        tie_method='strict',resample_seed=20260910,n_resamples=10000)
    write_report_files(directory,summary)
    metadata=dict(elapsed_seconds=time.monotonic()-started,tables=len(results),hands=len(hands),changes=len(changes),
        excluded=excluded,runtime_totals={key:sum(asdict(r.runtime_counts)[key] for r in results)
            for key in asdict(results[0].runtime_counts)})
    (directory/'completion.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n')
    for name,expected in freeze['source_sha256'].items():assert hashlib.sha256((_project_file(_PROJECT_ROOT, ROOT/name)).read_bytes()).hexdigest()==expected,name
    print(json.dumps(metadata,ensure_ascii=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--phase',choices=['smoke','development','confirmation'],required=True)
    parser.add_argument('--workers',type=int,default=4);run(parser.parse_args())
