"""冷进程验证两种房规下特殊胡牌分析与复核的真实截止余量。

一次批次共用接收时刻，串行执行核心，防止把每个场次预算重新起算。
只包含规则核心，不包含HTTP、策略和磁盘；完整策略预算另有专用基准。
"""
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
import time

import pytest

from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.kernel.actions import Hu
from hangma_bot.kernel.config import RuleConfig
from tests.unit.hangma.test_youcai_integration import CASES, make_observation


def measure(enabled, concurrency):
    """返回本进程单调时钟测得的毫秒耗时；校验禁止胡时仍可及时弃牌。"""
    rules=HangmaRules(RuleConfig('youcai-benchmark',1,enabled))
    started=time.monotonic()
    budget=BudgetPolicy().build(started,3.0)
    emergency_ms=[]
    for index in range(concurrency):
        _,hand,draw,melds=CASES[index%len(CASES)]
        obs=replace(make_observation(hand,draw,melds=melds,chain=1,gang=True),game_id=f'benchmark-{index}')
        before=time.monotonic()
        emergency=rules.emergency_action(obs)
        emergency_ms.append((time.monotonic()-before)*1000)
        analysis=rules.analyze(obs)
        assert rules.validate(obs,Hu()).legal is (not enabled)
        assert emergency is not None
        assert rules.validate(obs,emergency.action).legal
        assert analysis.emergency_candidate is not None
        assert time.monotonic()<budget.latest_send_at_monotonic
    finished=time.monotonic()
    return dict(enabled=enabled,M=concurrency,total_ms=(finished-started)*1000,
                max_emergency_ms=max(emergency_ms),send_margin_ms=(budget.latest_send_at_monotonic-finished)*1000)


@pytest.mark.parametrize('enabled',[False,True])
@pytest.mark.parametrize('concurrency',[4,10])
def test_cold_youcai_rule_batch_meets_deadline(enabled,concurrency):
    code=(
        'import json; from tests.unit.hangma.test_youcai_benchmark import measure; '
        f'print(json.dumps(measure({enabled!r},{concurrency})))'
    )
    result=subprocess.run([sys.executable,'-c',code],cwd=Path(__file__).resolve().parents[3],
                          capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stderr
    print(result.stdout.strip())
