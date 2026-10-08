"""原生计量研究源；常规非负内建整数快路径，其他值保留原Python计算。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t89-fast-meter-prototype-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

METER_SOURCE = '''
cdef unsigned long long _FAST_MAX = 9223372036854775807

cdef class _Meter:
    """独占操作计数；先累计再拒绝，保留Python大整数和特殊类型语义。"""

    def __init__(self, limit):
        self._used_obj = 0
        self._limit_obj = limit
        self._fast = False
        self._try_fast()

    property used:
        def __get__(self):
            if self._fast:
                return self._used_fast
            return self._used_obj
        def __set__(self, value):
            self._used_obj = value
            self._fast = False
            self._try_fast()

    property limit:
        def __get__(self):
            return self._limit_obj
        def __set__(self, value):
            self._leave_fast()
            self._limit_obj = value
            self._try_fast()

    cdef void _try_fast(self) except *:
        # 精确类型排除bool和重载数值子类；不把任意Python整数截成机器整数。
        if (type(self._used_obj) is int and type(self._limit_obj) is int
                and 0 <= self._used_obj <= _FAST_MAX
                and 0 <= self._limit_obj <= _FAST_MAX):
            self._used_fast = self._used_obj
            self._limit_fast = self._limit_obj
            self._fast = True
        else:
            self._fast = False

    cdef void _leave_fast(self) except *:
        if self._fast:
            self._used_obj = self._used_fast
            self._fast = False

    cdef void _check_fast(self) except *:
        if self._used_fast > self._limit_fast:
            raise WorkloadExceeded(
                "计数操作超限：已用 {0}，上限 {1}".format(self.used, self.limit)
            )

    cdef void _charge_slow(self, object count) except *:
        self._leave_fast()
        self._used_obj += count
        if self._used_obj > self._limit_obj:
            raise WorkloadExceeded(
                "计数操作超限：已用 {0}，上限 {1}".format(self.used, self.limit)
            )

    cdef void _charge_one(self) except *:
        if self._fast and self._used_fast < _FAST_MAX:
            self._used_fast += 1
            self._check_fast()
        else:
            self._charge_slow(1)

    cdef void _charge_zero(self) except *:
        # 零计费也须复核已经超限的计数；不能把它无条件消掉。
        if self._fast:
            self._check_fast()
        else:
            self._charge_slow(0)

    cpdef charge(self, object count=1):
        if type(count) is int:
            if count == 1:
                self._charge_one()
                return
            if count == 0:
                self._charge_zero()
                return
            if self._fast and count >= 0 and count <= _FAST_MAX - self._used_fast:
                self._used_fast += <unsigned long long>count
                self._check_fast()
                return
        self._charge_slow(count)
'''
