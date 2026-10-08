"""补齐原生采样的构图覆盖：采样先启动，业务固定延后2秒。

首份原生报告2097/2354主线程栈落在等待，不能用于整体CPU归因。
本项只追加一次完整原S02选择，去掉提前符号解析，采样5秒。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t127-s02-precision-diagnosis-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import argparse
import inspect
import json
from pathlib import Path

import diagnose as base

HERE = Path(__file__).resolve().parent


def prepare():
    """按已确认覆盖不足登记一次诊断，不改前两份采样原件。"""
    sample = _project_file(_PROJECT_ROOT, HERE / 'actual-sample2/NATIVE-SAMPLE.txt')
    content = sample.read_text()
    assert '2097 time_sleep' in content and '2354 Thread_' in content
    original = base.static_check()[0]
    frozen = dict(original['frozen_files'])
    for path in [Path(__file__), _project_file(_PROJECT_ROOT, HERE / 'PLAN.json'), _project_file(_PROJECT_ROOT, HERE / 'DEPTH-PLAN.json'), sample,
                 _project_file(_PROJECT_ROOT, HERE / 'actual-sample2/SAMPLE-RECEIPT.json')]:
        frozen[str(path)] = base.sha(path)
    base.save(_project_file(_PROJECT_ROOT, HERE / 'ALIGNED-SAMPLE-PLAN.json'), {
        'schema': 't127-aligned-native-sample-plan/1', 'frozen_files': frozen,
        'max_additional_rule_choose_score_calls_each': 1, 'max_total_calls_each': 9,
        'sample_seconds': 5, 'sample_interval_ms': 1, 'delay_before_business_seconds': 2,
        'mayDie_option': False, 'coverage_failure_preserved': True,
        'source_and_production_changes': 0, 'new_algorithm_or_optimization': False})
    print(json.dumps({'prepared': True, 'additional_call_limit': 1, 'actual_business_calls': 0}))


def check():
    plan = base.read(_project_file(_PROJECT_ROOT, HERE / 'ALIGNED-SAMPLE-PLAN.json'))
    for path, digest in plan['frozen_files'].items():
        assert base.sha(path) == digest, path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true')
    args = parser.parse_args()
    if args.prepare:
        prepare()
        return 0
    check()
    original_check, original_labels = base.static_check, dict(base.LABELS)
    expanded = dict(original_labels, sample_aligned=['original-T80-failed-response'])
    def checked():
        check()
        base.LABELS = original_labels
        try:
            return original_check()
        finally:
            base.LABELS = expanded
    base.static_check = checked
    base.LABELS = expanded
    source = inspect.getsource(base.execute)
    replacements = [("if mode == 'sample':", "if mode == 'sample_aligned':"),
        ("'3', '1', '-mayDie', '-fullPaths'", "'5', '1', '-fullPaths'"),
        ('await asyncio.sleep(0.2)', 'await asyncio.sleep(2.0)')]
    for before, after in replacements:
        assert source.count(before) == 1
        source = source.replace(before, after)
    namespace = dict(base.__dict__)
    exec(compile(source, str(_project_file(_PROJECT_ROOT, HERE / 'diagnose.py')), 'exec'), namespace)
    return base.asyncio.run(namespace['execute']('sample_aligned'))


if __name__ == '__main__':
    raise SystemExit(main())
