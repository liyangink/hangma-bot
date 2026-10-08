"""复用已验续打读取器，并核新来源父子整条路径与公开原评分。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t108-target-cost-joint-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import ast
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    """只生成纯读取器；不触发规则、评分或模拟。"""
    original = (_project_file(_PROJECT_ROOT, HERE / 'S01-continuation-root009/readback.py')).read_text()
    assert original.count("    assert len(groups) == plan['max_continuations'] == 6") == 1
    extra = '''    # 两臂原尾段都必须逐动作复现，场次标识仅作命名空间归一。
    def normalize(value):
        if isinstance(value, dict):
            return {k: normalize(v) for k, v in value.items() if k != 'game_id'}
        if isinstance(value, list):
            return [normalize(v) for v in value]
        return value
    with gzip.open(HERE / 'TEACHER-SOURCE-TRACES.json.gz', 'rt') as stream:
        traces = {r['arm']: r for r in json.load(stream)['traces']}
    public = json.loads((HERE / 'PUBLIC-TARGETS.json').read_text())['targets']
    score_counts = {'P': 0, 'C': 0}
    for target in plan['targets']:
        for arm in ('P', 'C'):
            trace = traces[arm]
            cuts = [i for i, frame in enumerate(trace['frames']) if any(
                d['seat'] == plan['focal_seat'] and d['window_key']['round_no'] == plan['hand_no']
                and d['window_key']['trigger_seq'] == target['trigger_seq']
                and d['window_key']['phase'] == 'draw' for d in frame)]
            assert len(cuts) == 1
            expected = [(normalize(d['window_key']), d['selected_action_key'], d['seat'])
                for f in trace['frames'][cuts[0]:] if f[0]['window_key']['round_no'] == plan['hand_no'] for d in f]
            actual = groups[(target['name'], arm)]
            assert [(normalize(d['window_key']), d['selected_action_key'], d['seat']) for d in actual] == expected
            known = next(r for r in public if r['arm'] == arm)
            current = next(r for r in actual if r['seat'] == plan['focal_seat']
                and r['window_key']['trigger_seq'] == target['trigger_seq'])
            assert normalize(current['observation']) == normalize(known['observation'])
            assert canonical(current['candidates']) == canonical(known['original_full_scores'])
            score_counts[arm] += sum(r['focal_vip'] for r in actual)
        for arm in ('P', 'C', 'A'):
            result = json.loads((HERE / target['name'] / (arm + '-RESULT.json')).read_text())
            settlement = result['settlement']
            assert sum(settlement['score_delta']) == 0
            assert result['focal_net_score'] == settlement['score_delta'][plan['focal_seat']]
    assert sum(score_counts.values()) == len(calls)
    assert len(groups) == plan['max_continuations'] == 3
'''
    reader = original.replace("    assert len(groups) == plan['max_continuations'] == 6", extra)
    reader = reader.replace("'actual_candidate_scores': len(calls),", "'actual_candidate_scores': len(calls), 'actual_score_counts_by_arm':score_counts, 'P_and_C_original_whole_tail_exact':True,")
    ast.parse(reader)
    for case in ('root003-loss', 'root030-gain'):
        path = _project_file(_PROJECT_ROOT, HERE / ('S01-fresh-' + case) / 'readback.py')
        with path.open('x') as stream:
            stream.write(reader)
    print({'readers_prepared': 2, 'business_calls': 0})


if __name__ == '__main__':
    main()
