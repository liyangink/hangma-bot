"""真实预算基准：同一接收时刻起计算 emergency/analyze/choose/validate。

这是本地公开核心调用的时限门禁，不包含 HTTP、SSE 或审计磁盘开销。
冷进程首个决策单列；并发 M 使用同一事件循环，不通过多线程掩盖阻塞。
"""

import asyncio
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
import time
import random

import pytest

from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.kernel.actions import Tile, WindowPhase, CANONICAL_TILE_CODES
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import PublicDiscard
from hangma_bot.policy import ReliableHeuristicPolicyV1, WeightedHeuristicPolicy
from .support import make_observation, make_request

HEAVY_HAND = ('1w','2w','4w','5w','7w','8w','1b','2b','3b','5b','6b','3t','4t','6t')


def window_observation(kind):
    """构造真实规则可分析的弃牌或响应窗口，不预计算候选事实。"""
    if kind == 'draw':
        return make_observation(my_hand=tuple(Tile(c) for c in HEAVY_HAND[:13]), drawn_tile=Tile(HEAVY_HAND[-1]))
    return make_observation(
        phase='response_peng', turn_seat=1, responding_seats=(0,),
        my_hand=tuple(Tile(c) for c in ('5w','5w','1t','2t','3t','4t','5t','6t','1b','2b','8t','9t','东')),
        last_discard=PublicDiscard(seat=1,tile=Tile('5w'),seq=9),
    )


async def measure_batch(kind, concurrency, version):
    """实时时钟秒计时；返回各窗口毫秒耗时与截止余量，无文件/网络副作用。"""
    rules = HangmaRules(RuleConfig(ruleset_version='policy-benchmark', base_score=1, you_cai_bi_kao=False))
    policy = ReliableHeuristicPolicyV1() if version == 'v1' else WeightedHeuristicPolicy()
    observations = []
    for i in range(concurrency):
        if kind == 'varied_draw':
            # 不同合法物理牌组，避免 M 场重复同一手牌仅测缓存命中。
            rng = random.Random(9100+i)
            tiles = tuple(Tile(c) for c in rng.sample(list(CANONICAL_TILE_CODES)*4,14))
            obs = make_observation(my_hand=tiles[:13],drawn_tile=tiles[-1])
        else:
            obs = window_observation(kind)
        observations.append(replace(obs,game_id='benchmark-'+str(i)))
    timeout = 1.0 if kind == 'response' else 3.0
    received = time.monotonic()
    budget = BudgetPolicy().build(received, timeout)

    async def one(obs):
        start = time.monotonic()
        emergency = rules.emergency_action(obs)
        after_emergency = time.monotonic()
        analysis = rules.analyze(obs)
        after_analysis = time.monotonic()
        assert emergency is not None
        assert analysis.legal_candidates
        phase = WindowPhase.RESPONSE_PENG if kind == 'response' else WindowPhase.DRAW
        request = make_request(obs, analysis, phase=phase)
        before_choose = time.monotonic()
        plan = await policy.choose(request, budget)
        after_choose = time.monotonic()
        assert plan.candidates
        assert after_choose <= budget.enhancement_deadline_monotonic
        assert rules.validate(obs, plan.candidates[0].action).legal
        after_validate = time.monotonic()
        assert after_validate < budget.latest_send_at_monotonic
        return {
            'queued_ms': (start-received)*1000,
            'emergency_ms': (after_emergency-start)*1000,
            'analysis_ms': (after_analysis-after_emergency)*1000,
            'choose_elapsed_ms': (after_choose-before_choose)*1000,
            'validate_ms': (after_validate-after_choose)*1000,
            'total_since_received_ms': (after_validate-received)*1000,
            'enhancement_margin_ms': (budget.enhancement_deadline_monotonic-after_choose)*1000,
            'send_margin_ms': (budget.latest_send_at_monotonic-after_validate)*1000,
        }

    return await asyncio.gather(*(one(obs) for obs in observations))


@pytest.mark.parametrize('version', ['v0','v1'])
@pytest.mark.parametrize('kind', ['draw','response'])
@pytest.mark.parametrize('concurrency', [1,10])
def test_local_path_meets_real_budget(version, kind, concurrency):
    asyncio.run(measure_batch(kind,concurrency,version))  # 热路径计时前显式预热
    runs = [asyncio.run(measure_batch(kind,concurrency,version)) for _ in range(3)]
    rows = [row for batch in runs for row in batch]
    print(json.dumps({'version':version,'kind':kind,'M':concurrency,
                      'worst_total_ms':max(r['total_since_received_ms'] for r in rows),
                      'min_enhancement_margin_ms':min(r['enhancement_margin_ms'] for r in rows),
                      'min_send_margin_ms':min(r['send_margin_ms'] for r in rows)}))


@pytest.mark.parametrize('kind,concurrency', [('draw',1),('response',1),('varied_draw',10)])
def test_v1_first_decision_in_fresh_process(kind,concurrency):
    # 子进程从导入到首个真实规则调用均不复用本 pytest 进程的规则缓存。
    code = (
        'import asyncio,json; '
        'from tests.unit.policy.test_policy_benchmark import measure_batch; '
        f'print(json.dumps(asyncio.run(measure_batch({kind!r},{concurrency},"v1"))))'
    )
    root = Path(__file__).resolve().parents[3]
    started = time.monotonic()
    result = subprocess.run([sys.executable,'-c',code],cwd=root,capture_output=True,text=True,timeout=20)
    elapsed = time.monotonic()-started
    assert result.returncode == 0, result.stderr
    rows = json.loads(result.stdout)
    assert all(r['enhancement_margin_ms'] > 0 for r in rows)
    print(json.dumps({'version':'v1','kind':kind,'M':concurrency,
                      'cold_process_total_ms':elapsed*1000,
                      'worst_total_ms':max(r['total_since_received_ms'] for r in rows),
                      'min_send_margin_ms':min(r['send_margin_ms'] for r in rows)}))
