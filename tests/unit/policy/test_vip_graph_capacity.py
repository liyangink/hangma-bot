"""真实多杠窗口的完整构图与受限评分容量回归，只走公开策略接缝。"""

import json
from pathlib import Path

import pytest

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import CompetitionContext
from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
from hangma_bot.policy.action_value_executor import ActionValueExecutor, WorkloadExceeded
from hangma_bot.policy.interface import DecisionRequest
from hangma_bot.policy.route_vip_heuristic import (
    RouteVipHeuristicPolicy, VipRouteProjectionLimits,
)

from .support import make_budget, run_choose


def test_original_multi_gang_window_completes_all_legal_roots():
    """原T39构图失败牌形必须由新策略自身完整评分，不能靠R18补齐。"""
    path = Path('review/vip-route-2026-09-30/evidence/'
                't42-semantic-node-sharing-prototype-1/FAILED-PUBLIC-WINDOWS.json')
    material = json.loads(path.read_text())['rows'][0]['actual_failed_row']
    obs = observation_from_json(material['observation'])
    window = window_key_from_json(material['window_key'])
    config = RuleConfig('hangma-mvp-v10-public-counts', 1, False)
    analysis = HangmaRules(config).analyze(obs, route_limits=ValueAnalysisLimits(max_expansions=8192))
    request = DecisionRequest(obs, CompetitionContext('multi-gang-regression',None,None,None,None,(),0),
                              analysis,'multi-gang',window.trigger_seq,window,())
    policy = RouteVipHeuristicPolicy(config, max_operations=2_400_000,
        projection_limits=VipRouteProjectionLimits(8192,16384,65536))
    plan = run_choose(policy, request, make_budget())
    assert {item.action_key for item in plan.candidates} == set(material['legal_action_keys'])
    assert not plan.degraded_reasons
    assert policy.executor.last_operation_count <= 2_400_000


def test_collection_capacity_is_per_executor_not_a_global_relaxation():
    """VIP可用声明容量；同进程的旧默认执行器仍拒绝超过4096的集合。"""
    from .test_route_vip_heuristic import _request, _draw_observation, CONFIG
    from hangma_bot.policy.route_vip_heuristic import build_vip_route_scoring_view
    view = build_vip_route_scoring_view(_request(_draw_observation((
        '1w','2w','3w','1t','2t','3t','1b','2b','3b','7w','8w','白','白',
    ))),CONFIG)
    source = '''
def score_actions(view):
    values = list(range(4097))
    return {"status": "SCORED", "entries": [{"action_key": a["action_key"], "score": len(values), "trace": {}} for a in view["actions"]]}
'''
    enlarged = ActionValueExecutor(source,max_operations=100_000,max_local_collection_size=8192)
    assert enlarged.score_vip_route(view).status == 'SCORED'
    with pytest.raises(WorkloadExceeded,match='4096'):
        ActionValueExecutor(source,max_operations=100_000).score_vip_route(view)


@pytest.mark.parametrize('invalid',[True,0,-1,8192.0,16385])
def test_local_capacity_must_be_a_bounded_positive_integer(invalid):
    with pytest.raises(ValueError):
        ActionValueExecutor('def score_actions(view):\n    return {}\n',
                            max_local_collection_size=invalid)
