"""纯读首次评分失败及完整成功前缀，保留失败和未启动分母。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t110-compact-target-cost-joint-evolution-1'

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
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent


def canonical(value):
    """按完整有限JSON核验捕获，不删除未知或解释字段。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def main():
    """核15实际尝试、14完成、20窗口和1失败，余82未启动不能记零收益。"""
    out = _project_file(_PROJECT_ROOT, HERE / 'S01-public-probe')
    closed = json.loads((out / 'CLOSURE.json').read_text())
    terminal = json.loads((out / 'ACTUAL-TOOL-TERMINAL.json').read_text())
    assert terminal['verified_tool_terminal'] and terminal['exit_code'] == 1
    assert not closed['complete'] and closed['source_stable'] and not closed['cleanup_errors']
    assert closed['primary_failure']['type'] == 'WorkloadExceeded'
    cases = json.loads((_project_file(_PROJECT_ROOT, HERE / 'PUBLIC-PANEL.json')).read_text())['cases']
    rows = [json.loads(line) for line in (out / 'ROWS.jsonl').read_text().splitlines()]
    assert rows == closed['rows'] and len(rows) == len(cases) == 103
    archive = {}
    with gzip.open(out / 'VIEWS.jsonl.gz', 'rt') as stream:
        for row in map(json.loads, stream):
            digest = hashlib.sha256(canonical(row['view'])).hexdigest()
            assert digest == row['view_sha256'] and digest not in archive
            archive[digest] = row['view']
    done, calls, outputs, changed, failed, not_started = [], 0, 0, [], [], 0
    used = set()
    for case, row in zip(cases, rows):
        assert row['label'] == case['label']
        if row['status'] == 'not_started':
            not_started += 1
            continue
        assert row['view_sha256'] == case['view_sha256'] and row['view_sha256'] in archive
        if row['status'] == 'failed':
            assert row['error'] == closed['primary_failure']
            failed.append({'label': row['label'], 'input_sha256': row['view_sha256'], 'error': row['error']})
            continue
        assert row['status'] == 'complete'
        entries = row['child_scores']['entries']
        keys = {a['action_key'] for a in archive[row['view_sha256']]['actions']}
        assert len(entries) == len(keys) and {e['action_key'] for e in entries} == keys
        assert all(type(e['score']) in (int, float) and math.isfinite(e['score']) for e in entries)
        assert sorted(entries, key=lambda e: (-e['score'], e['action_key']))[0]['action_key'] == row['child_first']
        assert row['child_scores']['capture_receipt']['saved_before_score']
        assert row['child_scores']['operations'] <= 4800000
        if not row['child_score_reused']:
            calls += 1; outputs += len(entries); used.add(row['view_sha256'])
        done.append({'label': row['label'], 'input_sha256': row['view_sha256'],
            'parent_first': row['parent_first'], 'child_first': row['child_first'],
            'operations': row['child_scores']['operations'], 'score_reused': row['child_score_reused']})
        if row['child_first'] != row['parent_first']:
            changed.append(done[-1])
    assert len(done) == 20 and calls == len(used) == 14 and len(failed) == 1 and not_started == 82
    assert len(archive) == closed['counts']['actual_child_score_calls'] == 15
    assert used | {r['input_sha256'] for r in failed} == set(archive)
    assert closed['input_capture']['terminal']['terminal_valid']
    assert closed['input_capture']['terminal']['store_calls_reconciled']
    result = {'schema': 't110-failed-mechanical-readback/1', 'readback_complete': True,
        'mechanical_passed': False, 'whole_panel_requested_windows': 103,
        'completed_windows': len(done), 'actual_child_score_attempts': 15, 'actual_completed_scores': calls,
        'actual_finite_legal_outputs': outputs, 'failed_attempts': 1, 'not_started_windows': not_started,
        'input_capture_complete': True, 'normal_R18_fallbacks': 0, 'changed_first_windows': changed,
        'completed_rows': done, 'failures': failed, 'candidate_identity': closed['candidate_identity'],
        'actual_tool_terminal': terminal, 'scope': 'partial exposed development only; no strength/deadline/admission',
        'new_rules_scores_models_worlds_tables_in_readback': 0}
    with (out / 'FAILED-MECHANICAL-READBACK.json').open('xb') as stream:
        stream.write(canonical(result) + b'\n')
    print({k: result[k] for k in ('readback_complete', 'mechanical_passed', 'actual_child_score_attempts',
                                 'actual_completed_scores', 'actual_finite_legal_outputs', 'changed_first_windows')})


if __name__ == '__main__':
    main()
