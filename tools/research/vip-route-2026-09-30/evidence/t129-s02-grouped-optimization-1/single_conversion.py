"""仅单次评分复用已完整保存的候选私有 DTO；不缓存跨窗口可变输入。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t129-s02-grouped-optimization-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from contextlib import contextmanager
from contextvars import ContextVar


@contextmanager
def installed(view_type):
    """研究进程显式装配；每任务/线程独立，只对同一原件的评分调用命中。

    先调用原 candidate_view，完整编码/保存成功后才能进入 returned scope。
    DTO 可以被候选修改，已落盘字节和冻结视图不受影响。退出 scope 后该
    DTO 不再提供给任何下一次调用；外部 candidate_view 仍返回全新容器。
    """
    original = view_type.candidate_view
    current = ContextVar('t129_single_scoring_input', default=None)
    stats = {'ordinary_conversions': 0, 'prepared_reuses': 0}

    def candidate_view(self):
        prepared = current.get()
        if prepared is not None and prepared[0] is self:
            stats['prepared_reuses'] += 1
            return prepared[1]
        stats['ordinary_conversions'] += 1
        return original(self)

    @contextmanager
    def scope(view, dto):
        if current.get() is not None:
            raise RuntimeError('单次评分输入作用域不允许嵌套')
        if not isinstance(view, view_type) or type(dto) is not dict:
            raise ValueError('评分输入必须是同次实际视图生成的原始映射')
        token = current.set((view, dto))
        try:
            yield
        finally:
            current.reset(token)

    view_type.candidate_view = candidate_view
    try:
        yield scope, stats
    finally:
        view_type.candidate_view = original
        stats['restored'] = view_type.candidate_view is original
