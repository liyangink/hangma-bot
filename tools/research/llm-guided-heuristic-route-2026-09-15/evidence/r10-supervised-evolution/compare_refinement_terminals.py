"""比较分支 M1 与直接父代的逐桌终局，不把终局一致当逐动作一致。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import strong_seed_batch as b
import refinement_batch as refinement


def compare(experiment=refinement):
    """要求完整结案后对齐同根同配置双臂，返回逐桌差异和可靠性计数。"""
    sub = experiment.ROOT / experiment.NAME
    closure = b.read(sub / 'batch-closure.json')
    assert closure['full_natural_results_verified'] == 256
    child = b.Path(getattr(experiment, 'ITER_DIR', sub / 'run/iterations/iter-01'))
    parent = experiment.PARENT.parent
    rows = []
    counts = {k: 0 for k in ('illegal_choices', 'fallbacks', 'timeouts',
                              'audit_missing', 'auto_actions')}
    equal = {'baseline': 0, 'candidate': 0}
    for mix in ('H', 'M'):
        cp = b.read(child / ('natural-' + mix) / 'panel.json')
        pp = b.read(parent / ('natural-' + mix) / 'panel.json')
        index = {(s['root_index'], s['focal_anchor_seat']): s for s in pp['samples']}
        assert len(index) == len(cp['samples']) == 32
        for c in cp['samples']:
            p = index[(c['root_index'], c['focal_anchor_seat'])]
            assert c['root_content_digest'] == p['root_content_digest']
            for arm in ('baseline', 'candidate'):
                ct = c['raw_arms'][arm]['tables']
                pt = p['raw_arms'][arm]['tables']
                assert len(ct) == len(pt) == 2
                for a, z in zip(ct, pt, strict=True):
                    assert a['table_id'] == z['table_id'] and a['seed'] == z['seed']
                    ar, zr = a['result'], z['result']
                    keys = ('scores_before', 'scores_after', 'completed_hands',
                            'expected_hands', 'runtime_counts', 'status', 'invalid_reasons')
                    differences = [key for key in keys if ar[key] != zr[key]]
                    equal[arm] += int(not differences)
                    if differences:
                        rows.append({'mix': mix, 'root': c['root_index'],
                                     'seat': c['focal_anchor_seat'], 'arm': arm,
                                     'table': a['table_id'], 'changed': differences})
                    if arm == 'candidate':
                        for key in counts:
                            counts[key] += ar['runtime_counts'][key]
    assert equal['baseline'] == 128
    return {'scope': '128个候选桌赛及128个共同V2臂的终局比较；未保存逐动作轨迹，不证明逐动作相同',
            'candidate_source_sha256': closure['candidate_source_sha256'],
            'parent_source_sha256': b.digest((experiment.PARENT / 'candidate.py').read_bytes()),
            'equal_terminal_tables': equal, 'differences': rows,
            'candidate_runtime_counts': counts, 'clock_mode': 'logical',
            'release_eligible': False}


if __name__ == '__main__':
    output = refinement.ROOT / refinement.NAME / 'parent-terminal-comparison.json'
    if output.exists():
        raise SystemExit('保留原结果，不覆盖')
    result = compare()
    b.write(output, result)
    print({key: value for key, value in result.items() if key != 'differences'})
