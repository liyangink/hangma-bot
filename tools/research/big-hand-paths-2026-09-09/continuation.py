"""构造起手的同牌山单局续打：完整结束，不用短期截断后的零值充当未来价值。

本人为起庄座位 0；未知牌均匀分给他家与牌墙，未使用案例指定进张。
这是条件决策开发评估，不能替代自然发牌的完整桌赛独立确认。
"""

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
from collections import Counter
from dataclasses import replace
import hashlib
import json
import random
import time

from lab import (HERE, ROOT, RULESET, CANONICAL_TILE_ORDER, HangmaRules, RuleConfig,
                 ComparableHeuristicPolicyV2, DecisionBudget, request_for, WindowKey, WindowPhase)
from hangma_bot.simulation.engine import SimulationEngine
from hangma_bot.simulation.interface import SimulationChoice
from hangma_bot.simulation.artifacts import compute_rules_hash


def source_hand(case, seed):
    """构造 136 张守恒的完整起点；不将未来见证强塞进牌墙。"""
    hand = list(case['initial_hand'])
    used = Counter(hand)
    pool = [code for code in CANONICAL_TILE_ORDER for _ in range(4-used[code])]
    digest = hashlib.sha256(f'{case["case_id"]}:{seed}'.encode()).hexdigest()
    random.Random(int(digest, 16)).shuffle(pool)
    hands = [hand[:-1], pool[:13], pool[13:26], pool[26:39]]
    wall = pool[39:]
    assert Counter([c for group in hands for c in group] + [hand[-1]] + wall) == Counter({c:4 for c in CANONICAL_TILE_ORDER})
    payload = dict(world_schema='simulation-world/1', deal_algorithm='simulation-v1:deal-v1', scenario_id=case['case_id'],
        match_id=f'{case["case_id"]}-{seed}', seed=seed, round_no=1, dealer_seat=0,
        initial_scores=[0]*4, rule_config=dict(ruleset_version=RULESET, base_score=1,you_cai_bi_kao=False),
        timing=dict(peng_timeout_sec=1,chi_timeout_sec=1,discard_timeout_sec=3),
        hands=hands, dealer_drawn_tile=hand[-1], wall=wall, wall_front=0, wall_back=len(wall)-20, seq=0)
    return dict(replay_schema_version=1, coverage='full_world',
                initial=dict(world_schema='simulation-world/1', world_payload=payload))


async def finish(engine, world, action, policy):
    """只经公开 frame/advance/export_hand 续打；策略仅收到各自观察。"""
    frame = engine.frame(world)
    assert len(frame.decisions) == 1 and frame.decisions[0].observation.seat == 0
    world = engine.advance(world, frame.revision, (SimulationChoice(frame.decisions[0].window_key, action),))
    for step in range(5000):
        frame = engine.frame(world)
        if frame.blocked_reason:
            raise RuntimeError(frame.blocked_reason)
        if frame.final_scores is not None:
            result = engine.export_hand(world, 1)
            assert result['score_delta'] == list(frame.final_scores)
            return dict(score=frame.final_scores[0], winner=result['winner_seat'], fan=result['fan'],
                        details=result['details'], steps=step, result_hash=hashlib.sha256(
                            json.dumps(result, sort_keys=True, ensure_ascii=False).encode()).hexdigest())
        choices = []
        for decision in frame.decisions:
            obs = decision.observation
            analysis = engine.rules.analyze(obs)
            req = replace(request_for(obs, analysis), window_key=decision.window_key)
            plan = await policy.choose(req, DecisionBudget(10,11,12))
            if plan.degraded_reasons:
                raise RuntimeError(str(plan.degraded_reasons))
            choices.append(SimulationChoice(decision.window_key, plan.candidates[0].action))
        world = engine.advance(world, frame.revision, tuple(choices))
    raise RuntimeError('完整单局超过步数上限，不能合成为流局')


async def run(args):
    """预先固定案例选择和世界种子数，全部完成后输出配对差值。"""
    input_path=_project_file(_PROJECT_ROOT, HERE/('mutation-opening.json' if args.opening else 'mutation-report.json'))
    report = json.loads(input_path.read_text())
    selected = [r for r in report['cases'] if (r['baseline']['shanten'] > 0 if args.opening
                                              else r['label'] == 'same_progress_loses_seven')]
    if args.limit:
        selected = selected[args.offset:args.offset + args.limit]
    elif args.offset:
        selected = selected[args.offset:]
    rules = HangmaRules(RuleConfig(RULESET,1,False))
    engine = SimulationEngine(rules)
    policy = ComparableHeuristicPolicyV2(monotonic=lambda:0)
    label=f'continuation-{"opening-" if args.opening else ""}{args.samples}-offset{args.offset}'
    output = _project_file(_PROJECT_ROOT, HERE/f'{label}.jsonl')
    if output.exists():
        raise FileExistsError(output)
    manifest = dict(schema='conditional-continuation/1', samples_per_case=args.samples,
        seed_range=[1050000,1050000+args.samples-1], cases=[r['case']['case_id'] for r in selected],
        rules_hash=compute_rules_hash(ROOT), policy='weighted_heuristic_v2', own_seat=0, dealer_seat=0,
        sampling='uniform_unseen_full_world', continuation='V2_all_seats_until_hand_end',
        input_sha256=hashlib.sha256(input_path.read_bytes()).hexdigest(),
        source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in [_project_file(_PROJECT_ROOT, HERE/'continuation.py'), _project_file(_PROJECT_ROOT, HERE/'lab.py'), *sorted((_project_file(_PROJECT_ROOT, ROOT/'src/hangma_bot/policy')).glob('*.py'))]})
    (_project_file(_PROJECT_ROOT, HERE/f'{label}-freeze.json')).write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    started=time.monotonic()
    with output.open('w') as stream:
        for record in selected:
            case=record['case']; deltas=[]; actual_actions=None
            for seed in range(1050000,1050000+args.samples):
                source=source_hand(case,seed)
                # 每个分支必须从同一个不可变 source 分别重建 WorldState；
                # finish 会推进并修改世界，不能先跑基线再复用同一实例做候选反事实。
                baseline_world=engine.from_replay(source)
                obs=engine.frame(baseline_world).decisions[0].observation
                analysis=rules.analyze(obs)
                req=request_for(obs,analysis)
                plan=await policy.choose(req,DecisionBudget(10,11,12))
                base=plan.candidates[0]
                alternative=next(c for c in analysis.legal_candidates if c.action_key==record['alternative']['action'])
                actions=(base.action_key,alternative.action_key)
                if actual_actions is None:actual_actions=actions
                assert actual_actions == actions  # 改变隐藏发牌不能影响根决策。
                old=await finish(engine,baseline_world,base.action,policy)
                if actions[0]==actions[1]:
                    new=old
                else:
                    alternative_world=engine.from_replay(source)
                    new=await finish(engine,alternative_world,alternative.action,policy)
                row=dict(case_id=case['case_id'],seed=seed,baseline_action=actions[0],alternative_action=actions[1],
                         source_sha256=hashlib.sha256(json.dumps(source,sort_keys=True).encode()).hexdigest(),
                         baseline=old,alternative=new,delta=new['score']-old['score'])
                stream.write(json.dumps(row,ensure_ascii=False)+'\n');stream.flush()
                deltas.append(row['delta'])
            print(case['case_id'],actual_actions, 'mean_delta',sum(deltas)/len(deltas), flush=True)
    print('elapsed_seconds',time.monotonic()-started,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--samples',type=int,default=32)
    parser.add_argument('--limit',type=int)
    parser.add_argument('--offset',type=int,default=0)
    parser.add_argument('--opening',action='store_true')
    asyncio.run(run(parser.parse_args()))
