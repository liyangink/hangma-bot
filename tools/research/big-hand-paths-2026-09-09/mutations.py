"""生成有干扰结构的选择题：新增牌可组成顺子，避免所有案例都只需弃孤字。"""

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
import argparse
from collections import Counter
from dataclasses import asdict
import json
import random

from lab import (ANCHORS, HERE, RULESET, Case, HangmaRules, RuleConfig, Tile,
                 CANONICAL_TILE_ORDER, observation, request_for, describe, generate,
                 witness, ComparableHeuristicPolicyV2, DecisionBudget)


def generated_cases():
    """重建全部去重输入，不按策略结果筛选；保持首批生成顺序和随机种子。"""
    rows, _ = generate()
    rng = random.Random(2026090901)
    seen = set()
    for line in ANCHORS:
        req = rows[line]['request']
        for variant in range(192):
            steps = 1 + variant % 4
            pre = list(req['hand'])
            removed = [pre.pop(rng.randrange(len(pre))) for _ in range(steps-1)]
            terminal_counts = Counter(req['hand'] + [req['draw']])
            junk = []
            for _ in range(steps):
                choices = [c for c in CANONICAL_TILE_ORDER[:-1] if terminal_counts[c] + junk.count(c) < 4]
                junk.append(rng.choice(choices))
            case = Case(f'mutation-{line}-{variant}', line, tuple(pre+junk),
                        tuple(reversed(junk)), tuple(removed+[req['draw']]))
            fingerprint = tuple(sorted(case.initial_hand)) + (case.initial_hand[-1],)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            yield case


async def run(opening=False):
    """固定生成种子；仅用于发现与开发，永不作为独立确认的赛事种子。"""
    rows, _ = generate()
    rules = HangmaRules(RuleConfig(RULESET, 1, False))
    policy = ComparableHeuristicPolicyV2(monotonic=lambda: 0)
    counts, selected = Counter(), []
    for case in generated_cases():
        obs = observation(case.initial_hand, case_id=case.case_id, reserve=case.future_draws,
                          wall=83 if opening else 80, dealer=0 if opening else 1)
        analysis = rules.analyze(obs)
        counts['generated'] += 1
        if any(c.action_key == 'hu' for c in analysis.legal_candidates):
            counts['already_hu'] += 1
            continue
        plan = await policy.choose(request_for(obs, analysis), DecisionBudget(10,11,12))
        descriptions = [describe(c, obs) for c in analysis.legal_candidates]
        base = next(d for d in descriptions if d['action'] == plan.candidates[0].action_key)
        if 'seven' not in base:
            counts['baseline_not_discard'] += 1
            continue
        alternatives = [d for d in descriptions if 'seven' in d and d['seven'] < base['seven'] and d['seven'] <= 2]
        if not alternatives:
            continue
        best = min(alternatives, key=lambda d:(d['seven'], d['shanten'], -d['unseen'], d['action']))
        if best['shanten'] <= base['shanten'] and best['unseen'] >= base['unseen']:
            label = 'same_progress_loses_seven'
        elif best['shanten'] <= base['shanten']:
            label = 'seven_vs_outs'
        else:
            label = 'seven_vs_shanten'
        counts[label] += 1
        proof = witness(case, rows, False)
        selected.append(dict(case=asdict(case), label=label, baseline=base, alternative=best,
                             candidates=descriptions, proof=proof,
                             score_parts=[dict(action=c.action_key,
                               parts=[dict(name=p.name,value=p.value) for p in c.score_parts]) for c in plan.candidates]))
    path=_project_file(_PROJECT_ROOT, HERE/('mutation-opening.json' if opening else 'mutation-report.json'))
    path.write_text(json.dumps(dict(seed=2026090901, opening=opening, counts=counts, cases=selected),
                                                       ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(counts, ensure_ascii=False))


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--opening',action='store_true')
    asyncio.run(run(parser.parse_args().opening))
