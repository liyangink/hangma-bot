"""通过公开choose接口验证每窗计时、原截止和来源身份，避免无限增强。"""
import asyncio
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


DIRECTORY = Path(__file__).resolve().parents[3] / 'tools/research/astra-evolution-2026-10-10'
sys.path.insert(0, str(DIRECTORY))
spec = importlib.util.spec_from_file_location('astra_budgeted_test', DIRECTORY / 'stage160_budgeted.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_each_choose_counts_parent_time_preserves_original_budget_and_resets():
    time = [100.0]
    clock = module.RequestElapsedClock(monotonic=lambda: time[0])
    budget = SimpleNamespace(enhancement_deadline_monotonic=801.4)
    request = object()
    plan = object()
    readings = []

    class Inner:
        policy_id = 'fixture'
        last_details = {'status': 'fixture'}
        async def choose(self, actual_request, actual_budget):
            assert actual_request is request and actual_budget is budget
            readings.append(clock())
            time[0] += 0.3  # 模拟父策略耗时，无真实等待。
            readings.append(clock())
            assert actual_budget.enhancement_deadline_monotonic - clock() == pytest.approx(1.1)
            return plan

    wrapped = module.ElapsedPolicy(Inner(), clock)
    assert asyncio.run(wrapped.choose(request, budget)) is plan
    time[0] += 99.0
    assert asyncio.run(wrapped.choose(request, budget)) is plan
    assert readings == pytest.approx([800, 800.3, 800, 800.3])
    assert wrapped.policy_id == 'fixture' and wrapped.last_details == {'status': 'fixture'}
    with pytest.raises(RuntimeError, match='choose内'):
        clock()


def test_exception_cleans_clock_and_does_not_swallow_failure():
    clock = module.RequestElapsedClock(monotonic=lambda: 10.0)
    class Inner:
        async def choose(self, request, budget):
            assert clock() == 800
            raise ValueError('fixture')
    wrapped = module.ElapsedPolicy(Inner(), clock)
    for _ in range(2):
        with pytest.raises(ValueError, match='fixture'):
            asyncio.run(wrapped.choose(None, None))


def test_overlapping_same_policy_request_rejected():
    clock = module.RequestElapsedClock(monotonic=lambda: 10.0)
    clock.begin()
    with pytest.raises(RuntimeError, match='重叠'):
        clock.begin()
    clock.end()


def test_factory_identity_and_auxiliary_binding_checked(tmp_path):
    factory = tmp_path / 'factory.py'
    factory.write_text('''class Policy:
    candidate_id = "fixed-id"
    def __init__(self, clock): self.clock = clock
    async def choose(self, request, budget): return self.clock()
def build_policy(parent, *, clock, params=None): return Policy(clock)
''')
    auxiliary = tmp_path / 'model.py'
    auxiliary.write_text('frozen = True\n')
    candidate = {'kind': 'factory', 'factory_path': str(factory),
                 'factory_sha256': module.stage.file_sha(factory),
                 'auxiliary_files': {str(auxiliary): module.stage.file_sha(auxiliary)},
                 'expected_candidate_id': 'fixed-id'}
    policy = module.candidate_policy(None, candidate)
    assert asyncio.run(policy.choose(None, None)) >= 800
    with pytest.raises(RuntimeError, match='身份'):
        module.candidate_policy(None, dict(candidate, expected_candidate_id='wrong'))
    auxiliary.write_text('frozen = False\n')
    with pytest.raises(RuntimeError, match='辅助'):
        module.candidate_policy(None, candidate)


def test_identity_control_has_no_extra_clock_or_strategy():
    parent = object()
    assert module.candidate_policy(parent, {'kind': 'P0_identity'}) is parent
