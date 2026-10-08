"""研究ABI诊断：直接核计量的Python退路；不当作候选/牌局强度样本。"""

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
import itertools
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


def described(value):
    return dict(type=type(value).__name__, value=repr(value))


def run(kind, limit, used, sequence):
    """异常后继续调用也记录；检查已经超限时零计费不能跳过检查。"""
    meter = kind(limit)
    meter.used = used
    rows = []
    for count in sequence:
        try:
            meter.charge(count)
        except BaseException as exc:
            outcome = dict(error_type=type(exc).__name__, error=str(exc))
        else:
            outcome = dict(status='RETURNED')
        rows.append(dict(count=described(count), used=described(meter.used),
                         limit=described(meter.limit), **outcome))
    return rows


def main():
    out = _project_file(_PROJECT_ROOT, HERE / 'meter-semantics')
    out.mkdir(exist_ok=False)
    original = executor._Meter
    values = [0, 1, 2, -1, (1 << 63) - 2, (1 << 63) - 1,
              1 << 63, 1 << 100, 0.5, True]
    sequences = [[1, 0, 1, -1, 0], [2, 1 << 100, 0, -1],
                 [True, False, 0.5, -2], [-1, 1, 0, 2]]
    inputs = list(itertools.product(values, values, sequences))
    save(out / 'PLAN.json', dict(schema='t89-meter-abi-diagnostic/1',
        cases=len(inputs), charges=sum(len(seq) for _, _, seq in inputs),
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        build_closure_sha256=hashlib.sha256((_project_file(_PROJECT_ROOT, HERE / 'BUILD-CLOSURE.json')).read_bytes()).hexdigest(),
        actual_candidate_scoring_rules_choose_worlds_tables=0, admission=False))
    baseline = [run(original, limit, used, seq) for limit, used, seq in inputs]
    with installed() as execution:
        native = [run(executor._Meter, limit, used, seq) for limit, used, seq in inputs]
        save(out / 'ACTUAL-RETURNS.json', dict(reference=baseline, native=native))
        assert raw(native) == raw(baseline)
        # limit/used重新赋值后，同原版走相同计量；跨机器整数界不能绕回零。
        left = original((1 << 63) - 1)
        right = executor._Meter((1 << 63) - 1)
        resets = []
        for kind, value in [('used', (1 << 63) - 1), ('limit', 1 << 100),
                            ('used', True), ('limit', -1), ('used', 0), ('limit', 10)]:
            setattr(left, kind, value)
            setattr(right, kind, value)
            row = []
            for meter in (left, right):
                try:
                    meter.charge()
                except BaseException as exc:
                    outcome = dict(error_type=type(exc).__name__, error=str(exc))
                else:
                    outcome = dict(status='RETURNED')
                row.append(dict(used=described(meter.used), limit=described(meter.limit), **outcome))
            assert raw(row[0]) == raw(row[1])
            resets.append(dict(field=kind, value=described(value), rows=row))
        save(out / 'RESET-RETURNS.json', resets)
        save(out / 'CLOSURE.json', dict(cases=len(inputs),
            charges=sum(len(seq) for _, _, seq in inputs), reset_pairs=len(resets),
            exact=True, execution_identity=execution,
            actual_candidate_scoring_rules_choose_worlds_tables=0, admission=False))
    assert executor._Meter is original
    print(dict(cases=len(inputs), charges=sum(len(seq) for _, _, seq in inputs),
               reset_pairs=len(resets), exact=True), flush=True)


if __name__ == '__main__':
    main()
