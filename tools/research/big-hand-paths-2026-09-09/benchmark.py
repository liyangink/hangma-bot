"""真实单调预算内测规则分析加路线策略；不把逻辑桌赛零超时当作性能证据。"""

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
import json
from pathlib import Path
import sys
import time

parser=argparse.ArgumentParser()
parser.add_argument('--python',action='store_true')
parser.add_argument('--output',type=Path)
args=parser.parse_args()
if args.python:
    sys.modules['hangma_bot.hangma._grouped_native']=None

from lab import HERE, RULESET, observation, request_for, HangmaRules, RuleConfig
from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.policy.route_preserve import V2RoutePreservePolicy
from hangma_bot.simulation.artifacts import hand_math_runtime_metadata


async def main():
    """首遍样本与十窗口共用起点分别记录；包含排队，不覆盖网络或最坏牌形。"""
    rows=json.loads((_project_file(_PROJECT_ROOT, HERE/'mutation-opening.json')).read_text())['cases']
    cases=[r['case'] for r in rows if r['baseline']['shanten']>0]
    rules=HangmaRules(RuleConfig(RULESET,1,False));policy=V2RoutePreservePolicy()
    obs=[observation(c['initial_hand'],case_id=c['case_id'],wall=83,dealer=0) for c in cases]
    results=[]
    async def one(observation,received,mode):
        budget=BudgetPolicy().build(received,1)
        analysis=rules.analyze(observation)
        req=request_for(observation,analysis)
        plan=await policy.choose(req,budget)
        finished=time.monotonic()
        results.append(dict(case=observation.game_id,mode=mode,elapsed_ms=(finished-received)*1000,
                            action=plan.candidates[0].action_key,degraded=list(plan.degraded_reasons),
                            within_send=finished<=budget.latest_send_at_monotonic))
    for o in obs:
        await one(o,time.monotonic(),'first_pass')
    received=time.monotonic()
    await asyncio.gather(*(one(obs[i%len(obs)],received,'ten_shared_received') for i in range(10)))
    assert all(r['within_send'] for r in results)
    output=dict(backend=hand_math_runtime_metadata(),scope='八个开发场景首遍及十协程CPU总预算，不含网络/磁盘/全场景冷启动',results=results)
    path=args.output or _project_file(_PROJECT_ROOT, HERE/('benchmark-python.json' if args.python else 'benchmark-c.json'))
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
    print(path.name,'max_ms',max(r['elapsed_ms'] for r in results))


asyncio.run(main())
