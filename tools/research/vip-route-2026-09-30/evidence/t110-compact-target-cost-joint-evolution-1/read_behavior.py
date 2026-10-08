"""纯读已核实际分值，统计首选、排序及当前胡变化；不评分或续打。"""

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
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def canonical(value):
    """分值使用原有限JSON，不用解释摘要替代实际执行结果。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def rank(entries):
    """和执行器相同：分值降序，同分按动作键确定顺序。"""
    return [r['action_key'] for r in sorted(entries, key=lambda r: (-r['score'], r['action_key']))]


def main(slot):
    """完整机械读回后统计103开发窗；不能从行为变化推断强度。"""
    out = _project_file(_PROJECT_ROOT, HERE / (slot + '-public-probe'))
    read = json.loads((out / 'ROOT-READBACK.json').read_text())
    closed = json.loads((out / 'CLOSURE.json').read_text())
    panel = json.loads((_project_file(_PROJECT_ROOT, HERE / 'PUBLIC-PANEL.json')).read_text())['cases']
    assert read['complete'] and closed['complete'] and read['actual_tool_terminal']['exit_code'] == 0
    assert len(panel) == len(closed['rows']) == read['windows'] == 103
    kinds, rows, changed_score_outputs, trace_only_outputs = Counter(), [], 0, 0
    for case, actual in zip(panel, closed['rows']):
        assert case['label'] == actual['label'] and actual['status'] == 'complete'
        old, new = case['parent_scores'], actual['child_scores']['entries']
        a = {r['action_key']: r for r in old}
        b = {r['action_key']: r for r in new}
        assert len(a) == len(old) and len(b) == len(new) and set(a) == set(b)
        parent_rank, child_rank = rank(old), rank(new)
        assert parent_rank[0] == case['parent_first'] and child_rank[0] == actual['child_first']
        score_changed = [key for key in a if a[key]['score'] != b[key]['score']]
        trace_only = [key for key in a if a[key]['score'] == b[key]['score'] and a[key]['trace'] != b[key]['trace']]
        changed_score_outputs += len(score_changed)
        trace_only_outputs += len(trace_only)
        hu_keys = [key for key in a if key.split(':')[0] == 'hu']
        first_changed = parent_rank[0] != child_rank[0]
        if first_changed:
            kinds[parent_rank[0].split(':')[0] + '->' + child_rank[0].split(':')[0]] += 1
        gap_old = a[parent_rank[0]]['score'] - a[parent_rank[1]]['score'] if len(a) > 1 else None
        gap_new = b[child_rank[0]]['score'] - b[child_rank[1]]['score'] if len(b) > 1 else None
        rows.append({'label': case['label'], 'phase': case['window_key']['phase'],
            'parent_first': parent_rank[0], 'child_first': child_rank[0], 'first_changed': first_changed,
            'full_ranking_changed': parent_rank != child_rank, 'has_current_legal_hu': bool(hu_keys),
            'changed_score_outputs': len(score_changed), 'trace_only_outputs': len(trace_only),
            'parent_first_gap': gap_old, 'child_first_gap': gap_new,
            'input_sha256': case['view_sha256']})
    result = {'schema': 't110-closed-behavior-summary/1', 'complete': True,
        'source_closure_sha256': hashlib.sha256((out / 'CLOSURE.json').read_bytes()).hexdigest(),
        'windows': len(rows), 'distinct_full_inputs': read['unique_full_inputs'],
        'actual_child_scores': read['actual_child_score_calls'],
        'first_changed_windows': sum(r['first_changed'] for r in rows),
        'ranking_changed_windows': sum(r['full_ranking_changed'] for r in rows),
        'changed_score_outputs_window_counted': changed_score_outputs,
        'trace_only_outputs_window_counted': trace_only_outputs,
        'first_change_kinds': dict(kinds), 'rows': rows,
        'scope': 'exposed development behavior only; window counts not independent sources or probability',
        'new_rules_scores_models_worlds_tables': 0, 'strength_deadline_admission': False}
    with (out / 'BEHAVIOR-SUMMARY.json').open('xb') as stream:
        stream.write(canonical(result) + b'\n')
    print({k: result[k] for k in ('complete', 'windows', 'first_changed_windows',
                                  'ranking_changed_windows', 'first_change_kinds')})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--slot', choices=('S01', 'S02'), required=True)
    main(parser.parse_args().slot)
