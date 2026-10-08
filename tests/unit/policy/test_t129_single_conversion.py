"""单次评分原件/可变容器隔离；不依赖牌局搜索的实现细节。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'tests/unit/policy'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import importlib.util
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

PATH = _project_file(_PROJECT_ROOT, Path(__file__).resolve().parents[3] / 'review/vip-route-2026-09-30/evidence/t129-s02-grouped-optimization-1/single_conversion.py')
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
