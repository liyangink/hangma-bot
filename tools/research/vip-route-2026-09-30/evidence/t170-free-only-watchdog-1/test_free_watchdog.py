"""独立自由赛实际终态验证：旧混合失败不挡续赛，真实资源/身份仍硬保护。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t170-free-only-watchdog-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from copy import deepcopy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('t170_test_driver', _project_file(_PROJECT_ROOT, HERE / 'free_watchdog.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
SOURCE = m.OLD / 'cycle-004'
PLAN = m.h.load(SOURCE / 'PLAN.json')


class ClosedFreeChecks(unittest.TestCase):
    def with_terminal(self, **overrides):
        """基于真正第四批 free 终态，只替换需验证的计算服务字段。"""
        rows = deepcopy(m.a.end_records(SOURCE / 'FREE-STDOUT-STDERR.log', 'free'))
        rows[0]['decision_compute'].update(overrides)
        return patch.object(m.a, 'end_records', return_value=rows)

    def test_actual_closed_free_not_blocked_by_actual_mixed_failure(self):
        # 真实旧 controller 的 mixed policy_failures 原失败仍保留。
        self.assertEqual(m.h.load(m.OLD / 'STATUS.json')['state'], 'blocked_new_rooms')
        value = m.verify_free(SOURCE, PLAN)
        self.assertEqual(value['room_id'], 'a_7ec582aed82b')
        self.assertTrue(value['full_score_gate_not_granted'])

    def test_diagnostic_policy_error_retained_without_stopping_experiment(self):
        with self.with_terminal(policy_failures=2):
            value = m.verify_free(SOURCE, PLAN)
        self.assertEqual(value['compute_diagnostics']['policy_failures'], 2)
        self.assertTrue(value['full_score_gate_not_granted'])

    def test_diagnostic_late_reply_is_not_resource_leak(self):
        with self.with_terminal(discarded=8, faults=1, restarts=1):
            self.assertEqual(m.verify_free(SOURCE, PLAN)['compute_diagnostics']['discarded'], 8)

    def test_actual_live_worker_blocks_new_owner(self):
        with self.with_terminal(live_processes=1), self.assertRaisesRegex(AssertionError, '资源未回收'):
            m.verify_free(SOURCE, PLAN)

    def test_unclosed_compute_blocks_new_owner(self):
        with self.with_terminal(closed=False), self.assertRaises(AssertionError):
            m.verify_free(SOURCE, PLAN)

    def test_wrong_package_is_not_a_soft_diagnostic(self):
        plan = deepcopy(PLAN)
        plan['identity']['package_ids']['free'] = 'wrong-package'
        with self.assertRaises(AssertionError):
            m.verify_free(SOURCE, plan)

    def test_missing_natural_terminal_blocks_new_owner(self):
        original = m.h.load
        def load(path):
            if path == SOURCE / 'FREE-CHILD-TERMINAL.json':
                return {'actual_exit_code': 11}
            return original(path)
        with patch.object(m.h, 'load', side_effect=load), self.assertRaises(AssertionError):
            m.verify_free(SOURCE, PLAN)

    def test_old_mixed_history_does_not_enter_new_prior_scan(self):
        with tempfile.TemporaryDirectory() as path, patch.object(m, 'HERE', Path(path)):
            self.assertEqual(m.prior_closed(), [])

    def test_postprocess_failure_is_terminal_not_automatic_retry(self):
        with tempfile.TemporaryDirectory() as path, patch.object(m, 'HERE', Path(path)):
            batch = Path(path) / 'batch-001'
            batch.mkdir()
            (batch / 'RUN-CLOSED.json').write_text('{}')
            self.assertEqual(m.pending(), [batch])
            (batch / 'POSTPROCESS-START.json').write_text('{}')
            self.assertEqual(m.pending(), [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
