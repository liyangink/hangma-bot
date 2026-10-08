"""字节/失败差分和真实既有DTO编码检查；不调用规则、choose、候选或模拟。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t120-s02-bounded-native-capture-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import gzip
import hashlib
import json
from pathlib import Path
import random
import sys
import time

HERE = Path(__file__).resolve().parent
RUNTIME = Path('/Users/liyang/.codex/worktrees/t54-public-count-cache/hangma-bot')
sys.path[:0] = [str(RUNTIME), str(_project_file(_PROJECT_ROOT, RUNTIME / 'src'))]
from hangma_bot.offline import scoring_input_capture as capture
from codec_overlay import load_native


def outcome(call):
    """比较完整成功字节或原错误类型/消息；不是候选分数测试。"""
    try:
        return ('ok', call())
    except Exception as exc:
        return ('error', type(exc).__name__, str(exc))


class DictSubclass(dict):
    """原录制器允许字典子类；快路径必须在调用其方法前旁路。"""


def main():
    native, identity = load_native()
    original = capture._encode
    rng = random.Random(120)
    values = [None, True, False, 0, -1, 2**2048 - 1, 2**2049,
        0.0, -0.0, 5e-324, 1e308, 1e-308,
        '', ''.join(chr(i) for i in range(128)), '中文🀆😀\\\"',
        [], (), {}, {'z': [None, (True, 1, -0.0)], 'a': '白板'},
        DictSubclass({'a': 1})]
    values.extend(rng.uniform(-1e20, 1e20) for _ in range(1000))
    values.extend(''.join(chr(rng.choice([rng.randrange(0xD800),
        rng.randrange(0xE000, 0x110000)])) for _ in range(rng.randrange(30)))
        for _ in range(200))
    valid_cases, exact_preflights, fallback_cases = 0, 0, 0
    for value in values:
        expected = original(value, 1 << 22)
        for ceiling in [len(expected)-1, len(expected), len(expected)+1, 1 << 22,
                        0, -1, False, 1 << 27]:
            left = outcome(lambda: original(value, ceiling))
            right = outcome(lambda: native.bounded_encode(value, ceiling, original)[0])
            assert left == right, (repr(value)[:100], ceiling, left, right)
            size = native.encoded_size(value, ceiling)
            if size is not None:
                assert size == len(expected) <= ceiling
                exact_preflights += 1
            else:
                fallback_cases += 1
            valid_cases += 1
    invalid = [float('nan'), float('inf'), -float('inf'), {1: 'bad'},
        {'a': object()}, {True: 0}, {'bad': b'x'}, '\ud800', ['\udfff'],
        {'z': '\ud800', 'a': 'x'*100}, set(), bytearray(b'x')]
    invalid_cases = 0
    for value in invalid:
        for ceiling in [1, 32, 1 << 22]:
            left = outcome(lambda: original(value, ceiling))
            right = outcome(lambda: native.bounded_encode(value, ceiling, original)[0])
            assert left == right, (repr(value), ceiling, left, right)
            assert native.encoded_size(value, ceiling) is None
            invalid_cases += 1
    # 过深与循环输入旁路，原验证器仍负责RecursionError；错误文本依赖栈位置。
    deep = 1
    for _ in range(160):
        deep = [deep]
    assert native.encoded_size(deep, 1 << 22) is None
    assert native.bounded_encode(deep, 1 << 22, original)[0] == original(deep, 1 << 22)
    cyclic = []
    cyclic.append(cyclic)
    assert native.encoded_size(cyclic, 1 << 22) is None
    assert outcome(lambda: native.bounded_encode(cyclic, 1 << 22, original)[0])[1] == 'RecursionError'
    rows = []
    source = _project_file(_PROJECT_ROOT, HERE.parent/'t118-s02-native-slice-lowering-1/actual-full-1/ACTUAL-INPUTS.jsonl.gz')
    with gzip.open(source, 'rt') as stream:
        for line in stream:
            record = json.loads(line)
            value = record['view']
            begin = time.monotonic(); reference = original(value, 1 << 26)
            original_time = time.monotonic()-begin
            begin = time.monotonic(); actual, fast = native.bounded_encode(value, 1 << 26, original)
            native_time = time.monotonic()-begin
            assert fast and actual == reference
            assert len(actual) == record['json_bytes']
            assert hashlib.sha256(actual).hexdigest() == record['view_sha256']
            rows.append({'bytes':len(actual), 'sha256':record['view_sha256'],
                'original_seconds':original_time, 'native_seconds':native_time,
                'full_bytes_equal':True, 'not_choose_deadline_evidence':True})
    result = {'schema':'t120-codec-differential/1','native_identity':identity,
        'valid_differential_cases':valid_cases, 'invalid_differential_cases':invalid_cases,
        'exact_preflight_cases':exact_preflights, 'fallback_cases':fallback_cases,
        'deep_fallback_success':True,'cyclic_original_error_preserved':True,
        'existing_complete_dtos':rows, 'actual_rule_choose_score_world_table_calls':0}
    with (_project_file(_PROJECT_ROOT, HERE/'CODEC-DIFFERENTIAL.json')).open('x') as stream:
        json.dump(result,stream,ensure_ascii=False,sort_keys=True,indent=2);stream.write('\n')
    print(json.dumps({'valid_cases':valid_cases, 'invalid_cases':invalid_cases,
        'dtos':rows, 'all_exact':True},ensure_ascii=False))


if __name__ == '__main__':
    main()
