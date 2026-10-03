"""单次评分原件/可变容器隔离；不依赖牌局搜索的实现细节。"""
import importlib.util
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

PATH = Path(__file__).resolve().parents[3] / 'review/vip-route-2026-09-30/evidence/t129-s02-grouped-optimization-1/single_conversion.py'
spec = importlib.util.spec_from_file_location('t129_single_conversion_test', PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class View:
    def candidate_view(self):
        return {'nodes': [{'value': 1}]}


def test_one_call_private_mutation_and_restore():
    original = View.candidate_view
    view, other = View(), View()
    with module.installed(View) as (scope, stats):
        first = view.candidate_view()
        with scope(view, first):
            assert view.candidate_view() is first
            assert other.candidate_view() is not first
            view.candidate_view()['nodes'][0]['value'] = 7
        assert view.candidate_view()['nodes'][0]['value'] == 1
        assert stats['prepared_reuses'] == 2
    assert View.candidate_view is original


def test_thread_cannot_observe_parent_prepared_input():
    with module.installed(View) as (scope, _):
        view = View()
        first = view.candidate_view()
        with scope(view, first), ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(view.candidate_view).result() is not first


def test_exception_releases_scope_and_next_call_is_fresh():
    with module.installed(View) as (scope, _):
        view = View()
        first = view.candidate_view()
        try:
            with scope(view, first):
                raise ValueError('评分失败')
        except ValueError:
            pass
        assert view.candidate_view() is not first
