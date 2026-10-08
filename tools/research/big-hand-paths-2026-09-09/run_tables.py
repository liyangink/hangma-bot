"""路线保留候选的预登记完整桌赛检验；只调用既有生产评估与模拟公开入口。"""

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
import hashlib
import json
import time

from lab import HERE, ROOT, RULESET, HangmaRules, RuleConfig, ComparableHeuristicPolicyV2
from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.kernel.config import TournamentConfig, TimingConfig
from hangma_bot.offline.evaluate import (MatchExperiment, PolicyDeclaration, MatchSeedSpec,
                                       run_match_experiment, write_report_files)
from hangma_bot.offline.evaluation_results import write_results_jsonl
from hangma_bot.offline.evaluation_statistics import summarize_results
from hangma_bot.policy.route_preserve import V2RoutePreservePolicy
from hangma_bot.simulation.engine import SimulationEngine
from hangma_bot.simulation.interface import MatchSpec, SimulationChoice
from hangma_bot.simulation.artifacts import compute_rules_hash

BASE='weighted_heuristic_v2'
CAND='v2_route_preserve_v1'


class AuditPolicy:
    """仅保存已经选择的变化；审计信息不反向进入策略。"""
    def __init__(self,policy_id,policy):
        self.policy_id,self.policy=policy_id,policy
        self.changes=[]
    async def choose(self,request,budget):
        plan=await self.policy.choose(request,budget)
        if any(p.name=='路线保留优先' for p in plan.candidates[0].score_parts):
            obs=request.observation
            self.changes.append(dict(game_id=obs.game_id,round_no=obs.round_no,seat=obs.seat,
                trigger_seq=request.trigger_seq,hand=[t.code for t in obs.my_hand],
                drawn=obs.drawn_tile.code,action=plan.candidates[0].action_key,
                reason=plan.candidates[0].reasons[-1]))
        return plan


class RecordingEngine:
    """旁路保存公开导出的单局结果；不读取不透明 WorldState 字段。"""
    def __init__(self,engine):
        self.engine=engine;self.hands=[];self.reported=0;self.match_id=None
    def start(self,spec):
        self.reported=0;self.match_id=spec.match_id
        return self.engine.start(spec)
    def frame(self,world):
        frame=self.engine.frame(world)
        for number in range(self.reported+1,frame.completed_hands+1):
            hand=self.engine.export_hand(world,number)
            self.hands.append(dict(game_id=self.match_id,round_no=number,winner=hand['winner_seat'],
                fan=hand['fan'],details=hand['details'],score_delta=hand['score_delta']))
        self.reported=frame.completed_hands
        return frame
    def advance(self,world,revision,choices):
        return self.engine.advance(world,revision,choices)


def root_run(item):
    """一个进程顺序完成一个根组的八场桌赛；进程间不共享可变规则缓存。"""
    phase,index,seed=item
    rules=HangmaRules(RuleConfig(RULESET,1,False))
    rules_hash=compute_rules_hash(ROOT)
    config=TournamentConfig(1,8,rules.config,TimingConfig(1,1,3))
    ids=[BASE,CAND,'opp-v2-1','opp-v2-2','opp-v2-3']
    policies={pid:AuditPolicy(pid,V2RoutePreservePolicy(monotonic=lambda:0) if pid==CAND
                             else ComparableHeuristicPolicyV2(monotonic=lambda:0)) for pid in ids}
    exp=MatchExperiment('matches','logical',PolicyDeclaration(BASE,BASE),PolicyDeclaration(CAND,CAND),
        tuple(PolicyDeclaration(pid,BASE) for pid in ids[2:]),config,
        (MatchSeedSpec(seed,f'route-preserve-{phase}-{index}'),),
        ((0,1,2,3),(1,2,3,0),(2,3,0,1),(3,0,1,2)),index%4,(0,0,0,0),
        simulation_version='simulation-v1',match_id_prefix='route-preserve')
    engine=RecordingEngine(SimulationEngine(rules,rules_hash=rules_hash))
    out=asyncio.run(run_match_experiment(exp,engine=engine,spec_factory=MatchSpec,choice_factory=SimulationChoice,
        policies_by_id=policies,rules=rules,rules_hash=rules_hash,now_monotonic=lambda:0,wall_clock=None,
        budget_policy=BudgetPolicy()))
    return out.results,engine.hands,policies[CAND].changes,list(out.excluded)


def run(args):
    """开发均值不为正或可靠性失败时不进入确认；新阶段拒绝覆盖旧文件。"""
    target=_project_file(_PROJECT_ROOT, HERE/args.phase)
    target.mkdir(exist_ok=False)
    count,start=(32,1060000) if args.phase=='development' else (128,1070000)
    files=sorted(p for folder in ['hangma','policy','simulation','offline']
                 for p in (_project_file(_PROJECT_ROOT, ROOT/'src/hangma_bot'/folder)).rglob('*') if p.suffix in ('.py','.c','.h','.so'))
    files += [_project_file(_PROJECT_ROOT, HERE/'run_tables.py')]
    freeze=dict(phase=args.phase,seed_range=[start,start+count-1],roots=count,
        hands_per_table=8,seat_rotations=4,initial_dealer='root_index % 4',ruleset=RULESET,
        you_cai_bi_kao=False,baseline=BASE,candidate=CAND,opponents=['V2']*3,
        candidate_rule='wall>=48; shanten in [1,2]; seven closer and <=shanten; outs>=95%; no extra white discard',
        gate='development mean>0 and reliability pass; confirmation mean>=10, CI lower>0, first point>=0/lower>=-0.03',
        source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
    (target/'freeze.json').write_text(json.dumps(freeze,ensure_ascii=False,indent=2)+'\n')
    results=[];hands=[];changes=[];errors=[];started=time.monotonic()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for index,(rows,h,c,e) in enumerate(pool.map(root_run,[(args.phase,i,start+i) for i in range(count)])):
            results.extend(rows);hands.extend(h);changes.extend(c);errors.extend(e)
            print(args.phase,index+1,'/',count,'changes',len(changes),flush=True)
    write_results_jsonl(target/'results.jsonl',results)
    for name,rows in [('hands',hands),('changes',changes)]:
        (target/f'{name}.jsonl').write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in rows))
    summary=summarize_results(results,baseline_policy_id=BASE,challenger_policy_id=CAND,
                              tie_method='strict',resample_seed=20260909,n_resamples=10000)
    write_report_files(target,summary)
    metadata=dict(elapsed_seconds=time.monotonic()-started,tables=len(results),hands=len(hands),
                  changes=len(changes),excluded=errors,
                  runtime_totals={key:sum(asdict(r.runtime_counts)[key] for r in results)
                                  for key in asdict(results[0].runtime_counts)})
    (target/'completion.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(metadata,ensure_ascii=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--phase',choices=['development','confirmation'],required=True)
    parser.add_argument('--workers',type=int,default=4)
    run(parser.parse_args())
