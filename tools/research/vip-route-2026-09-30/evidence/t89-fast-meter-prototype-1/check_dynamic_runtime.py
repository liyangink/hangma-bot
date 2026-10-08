"""计量接缝诊断：替身和Python重载子类仍能收到逐次原计费调用。"""

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
import hashlib
import json
from pathlib import Path

from hangma_bot.policy import action_value_executor as executor
from fast_overlay import installed

HERE = Path(__file__).resolve().parent


def raw(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def save(path, value):
    with path.open('xb') as stream:
        stream.write(raw(value) + b'\n')


class DuckMeter:
    """调用记录只属于本实例；逐次实现既有计量协议，不访问比赛信息。"""
    def __init__(self, limit):
        self.limit, self.used, self.calls = limit, 0, []

    def charge(self, count=1):
        self.calls.append(count)
        self.used += count
        if self.used > self.limit:
            raise executor.WorkloadExceeded(
                '计数操作超限：已用 {0}，上限 {1}'.format(self.used, self.limit))


def subclass(base):
    class TrackingMeter(base):
        """显式重载charge；原生快速运行时不得绕过这次重载。"""
        def __init__(self, limit):
            super().__init__(limit)
            self.calls = []

        def charge(self, count=1):
            self.calls.append(count)
            super().charge(count)
    return TrackingMeter


def run(runtime_factory, meter_factory):
    meter = meter_factory(10000)
    runtime = runtime_factory(meter, 16)
    rows = []
    operations = [
        ('pass', lambda: runtime['_av_pass'](3)),
        ('add', lambda: runtime['_av_bin'](2, '+', 3)),
        ('dict-read-zero-charge', lambda: runtime['_av_sub']({'x': 5}, 'x')),
        ('compare', lambda: runtime['_av_cmp'](2, '<', 3)),
        ('list', lambda: runtime['list']((1, 2, 3))),
        ('sum', lambda: runtime['sum']((1, 2, 3))),
        ('sorted', lambda: runtime['sorted']((3, 2, 1))),
        ('loop', lambda: list(runtime['_av_iter']((1, 2)))),
        ('long-string-reject', lambda: runtime['_av_pass']('x' * 65537)),
        ('after-error', lambda: runtime['_av_pass'](4)),
    ]
    for label, call in operations:
        try:
            value = call()
        except BaseException as exc:
            result = dict(error_type=type(exc).__name__, error=str(exc))
        else:
            result = dict(value=value)
        rows.append(dict(label=label, used=meter.used, calls=list(meter.calls), **result))
    return rows


def main():
    out = _project_file(_PROJECT_ROOT, HERE / 'dynamic-runtime')
    out.mkdir(exist_ok=False)
    original_meter, original_runtime = executor._Meter, executor._make_runtime
    save(out / 'PLAN.json', dict(schema='t89-dynamic-runtime-diagnostic/1',
        pairs=3, helper_calls_per_side_per_pair=10,
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        actual_candidate_scoring_rules_choose_worlds_tables=0, admission=False))
    rows = []
    with installed(direct_pass=False) as identity:
        for label, meter_type in [('duck', DuckMeter), ('original-subclass', subclass(original_meter)),
                                 ('native-subclass', subclass(executor._Meter))]:
            reference = run(original_runtime, meter_type)
            native = run(executor._make_runtime, meter_type)
            save(out / (label + '-ACTUAL-RETURN.json'), dict(reference=reference, native=native))
            assert raw(reference) == raw(native)
            assert reference[-1]['calls'] and 0 in reference[-1]['calls']
            rows.append(dict(label=label, exact=True, recorded_charges=len(reference[-1]['calls'])))
        save(out / 'CLOSURE.json', dict(rows=rows, execution_identity=identity,
            exact=True, actual_candidate_scoring_rules_choose_worlds_tables=0, admission=False))
    assert executor._Meter is original_meter and executor._make_runtime is original_runtime
    print(dict(pairs=len(rows), exact=True, rows=rows), flush=True)


if __name__ == '__main__':
    main()
