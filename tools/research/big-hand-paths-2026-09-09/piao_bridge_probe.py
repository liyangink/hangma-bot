"""检验首次财飘同分、后续财飘增分的短视盲区；只做条件开发，不发布策略。

三例起手锚来自官方存档。首步分别强制胡/弃白，此后本人使用原等胡策略、
他家使用 V2，到真实单局终局。未知牌均匀分配，不预装有利未来进张。
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
import asyncio
from collections import Counter
import gzip
import hashlib
import json
import random
import time

from lab import HERE, ROOT, GOLD, RULESET, HangmaRules, RuleConfig, request_for, DecisionBudget
from continuation import source_hand
from continuation_notes import finish
from upgrade_persistent import upgrade_policy, AuditedContinuation, ValueEvaluationEngine
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2
from hangma_bot.simulation.engine import SimulationEngine

DIRECTORY = _project_file(_PROJECT_ROOT, HERE / 'piao-bridge')
ANCHORS = (330, 639, 649)
SEEDS = range(1110000, 1110128)


def cases():
    """返回原始零起始行号及完整十四张锚；不由实验结果筛选案例。"""
    rows = [json.loads(line) for line in GOLD.read_text().splitlines()]
    return [dict(case_id=f'piao-bridge-{i}', anchor_line=i,
                 initial_hand=rows[i]['request']['hand']+[rows[i]['request']['draw']],
                 expected=rows[i]['response']) for i in ANCHORS]


async def run_world(case, seed):
    """同一完整发牌配对两动作；根和每个续打选择都只消费各自可见信息。"""
    raw = SimulationEngine(HangmaRules(RuleConfig(RULESET, 1, False)))
    engine = ValueEvaluationEngine(raw)
    source = source_hand(case, seed)
    world = raw.from_replay(source)
    frame = raw.frame(world)
    assert len(frame.decisions) == 1
    obs = frame.decisions[0].observation
    analysis = engine.rules.analyze(obs)
    request = request_for(obs, analysis)
    policy = upgrade_policy()
    plan = await policy.choose(request, DecisionBudget(10, 11, 12))
    assert plan.candidates[0].action_key == 'hu'
    candidates = {c.action_key: c for c in analysis.legal_candidates}
    score = candidates['hu'].value_facts.immediate_settlement
    assert score.fan == case['expected']['fan']
    assert score.details == tuple(case['expected']['detail'])
    wait = candidates['discard:白'].value_facts
    assert wait.routes and all(r.conditions.baotou and
        r.conditional_settlement.score_delta[0] == score.score_delta[0] for r in wait.routes)
    base = ComparableHeuristicPolicyV2(monotonic=lambda: 0)
    arms = {}
    for label, key in [('hu', 'hu'), ('bridge', 'discard:白')]:
        audited = AuditedContinuation(upgrade_policy())
        result = await finish(engine, world, candidates[key].action, audited, base)
        result['hu_choices'] = audited.hu_choices
        arms[label] = result
    assert arms['hu']['score'] == score.score_delta[0]
    return dict(case_id=case['case_id'], seed=seed,
        source_sha256=hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest(),
        immediate_fan=score.fan, immediate_score=score.score_delta[0],
        first_wait_scores=sorted({r.conditional_settlement.score_delta[0] for r in wait.routes}),
        arms=arms, delta=arms['bridge']['score']-arms['hu']['score'])


def summarize(rows):
    """按完整条件世界自助抽样；三个固定案例分别汇报，不外推自然赛频率。"""
    differences = [r['delta'] for r in rows]
    rng = random.Random(1110999)
    bootstrap = sorted(sum(rng.choices(differences, k=len(rows)))/len(rows) for _ in range(10000))
    bridge = [r['arms']['bridge'] for r in rows]
    return dict(worlds=len(rows), hands=2*len(rows), mean_delta=sum(differences)/len(rows),
        interval95=[bootstrap[249], bootstrap[9749]],
        immediate_score=rows[0]['immediate_score'],
        mean_bridge_score=sum(r['score'] for r in bridge)/len(rows),
        own_hu=sum(r['winner']==0 for r in bridge),
        opponent_hu=sum(r['winner'] not in (None, 0) for r in bridge),
        draw=sum(r['winner'] is None for r in bridge),
        own_fan_counts=dict(Counter(r['fan'] for r in bridge if r['winner']==0)),
        own_details=dict(Counter('·'.join(r['details']) for r in bridge if r['winner']==0)),
        followup_white_discards=sum(t['action']=='discard:白' for r in bridge for t in r['trace']))


async def main():
    """运行前冻结三个锚与 128 个世界；任何失败不生成完成报告。"""
    DIRECTORY.mkdir(exist_ok=False)
    sources = [_project_file(_PROJECT_ROOT, HERE/n) for n in ('piao_bridge_probe.py','lab.py','continuation.py',
                                'continuation_notes.py','upgrade_persistent.py','persistent_seven.py')]
    sources += sorted((_project_file(_PROJECT_ROOT, ROOT/'src/hangma_bot')).rglob('*.py'))
    sources += sorted((_project_file(_PROJECT_ROOT, ROOT/'src/hangma_bot/hangma')).glob('*.so'))
    manifest = dict(schema='piao-bridge-conditional/1', cases=cases(), seed_range=[SEEDS.start, SEEDS.stop-1],
        you_cai_bi_kao=False, own_seat=0, dealer_seat=0, wall=83, base_score=1,
        sampling='uniform_unseen_full_world_hash_case_and_seed',
        root_actions=['hu','discard:白'], own_continuation='v2_hu_upgrade_v1', opponents='weighted_heuristic_v2',
        stopping='3案例×128世界×2首步，全部到单局真实终局；失败保留原始数据，不生成完成报告',
        limitation='条件开发，非自然桌赛，逻辑时钟，不能声称策略强度或线上时限通过',
        gold_sha256=hashlib.sha256(GOLD.read_bytes()).hexdigest(),
        source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
    (DIRECTORY/'freeze.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    started = time.monotonic()
    results = {}
    for case in manifest['cases']:
        rows = []
        path = DIRECTORY/(case['case_id']+'.jsonl.gz')
        with gzip.open(path, 'xt', encoding='utf8') as stream:
            for seed in SEEDS:
                row = await run_world(case, seed)
                stream.write(json.dumps(row, ensure_ascii=False)+'\n')
                rows.append(row)
        results[case['case_id']] = {**summarize(rows), 'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        print(case['case_id'], json.dumps(results[case['case_id']], ensure_ascii=False), flush=True)
    (DIRECTORY/'summary.json').write_text(json.dumps(dict(cases=results,
        elapsed_seconds=time.monotonic()-started), ensure_ascii=False, indent=2)+'\n')


if __name__ == '__main__':
    asyncio.run(main())
