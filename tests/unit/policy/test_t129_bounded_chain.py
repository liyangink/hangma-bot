"""杠链预算只截断未来事实，不截断当前合法动作或跨窗口继续杠。"""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest
from hangma_bot.hangma.route_transition import ConditionalPhase

PATH = Path(__file__).resolve().parents[3] / 'review/vip-route-2026-09-30/evidence/t129-s02-grouped-optimization-1/bounded_chain.py'
spec = importlib.util.spec_from_file_location('t129_chain_test', PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Base:
    def replacement_key(self, state): return ('state',)
    def choices_key(self, analysis, followup_keys): return ('choices',)
    def compatible_codes(self, state): return ('1w', '2w')
    def waiting(self, state, qualification):
        assert qualification is False
        return {'qualification_scope': 'unanalysed'}
    def add(self, key, kind, **kwargs): return {'key': key, 'kind': kind, **kwargs}
    def replacement(self, state, key):
        if state.structural_only:
            raise ValueError('非法来源')
        return {'key': key, 'children': tuple(self.replacement(state, key + '/' + code)
                for code in self.compatible_codes(state))}


def state():
    return SimpleNamespace(phase=ConditionalPhase.REPLACEMENT_DRAW,
                           structural_only=False, wall_remaining=60)


def test_preserves_first_draw_codes_and_next_window_restarts():
    stats = {'bounded_successors': 0, 'max_observed_expanded_depth': 0}
    projection = module.make_projection(Base, 1, stats)()
    result = projection.replacement(state(), 'gang')
    assert len(result['children']) == 2
    assert all(child['kind'] == 'unknown_draw' for child in result['children'])
    assert all(child['waiting']['qualification_scope'] == 'unanalysed' for child in result['children'])
    assert projection._chain_depth == 0
    again = projection.replacement(state(), 'next-window-gang')
    assert len(again['children']) == 2
    assert stats['bounded_successors'] == 4
    assert stats['max_observed_expanded_depth'] == 1


def test_invalid_source_is_error_not_budget_unknown_and_depth_restored():
    projection = module.make_projection(Base, 1, {'bounded_successors': 0, 'max_observed_expanded_depth': 0})()
    invalid = state()
    invalid.structural_only = True
    with pytest.raises(ValueError, match='非法来源'):
        projection.replacement(invalid, 'gang')
    assert projection._chain_depth == 0


@pytest.mark.parametrize('limit', [True, 0, -1, 1.0])
def test_invalid_depth_rejected(limit):
    with pytest.raises(ValueError):
        module.make_projection(Base, limit, {})
