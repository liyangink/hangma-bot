"""纯读实际评分收据和完整输入；不重跑父子评分、规则或模拟。"""

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
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent


def canonical(value):
    """用原捕获的有限JSON规范核摘要，保留未知与版本字段。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def main(slot):
    """全部窗口、输出、输入与真实调用对账后报告变化，不授策略最优或强度。"""
    out = _project_file(_PROJECT_ROOT, HERE / (slot + '-public-probe'))
    terminal = json.loads((out / 'ACTUAL-TOOL-TERMINAL.json').read_text())
    assert terminal['verified_tool_terminal'] and terminal['exit_code'] == 0
    closure = json.loads((out / 'CLOSURE.json').read_text())
    assert closure['complete'] and closure['source_stable'] and closure['normal_R18_fallbacks'] == 0
    cases = json.loads((_project_file(_PROJECT_ROOT, HERE / 'S02-PUBLIC-PANEL.json')).read_text())['cases']
    rows = [json.loads(line) for line in (out / 'ROWS.jsonl').read_text().splitlines()]
    assert rows == closure['rows'] and len(rows) == len(cases) == 100
    views = {}
    with gzip.open(out / 'VIEWS.jsonl.gz', 'rt') as stream:
        for line in stream:
            row = json.loads(line)
            assert row['view_sha256'] not in views
            assert hashlib.sha256(canonical(row['view'])).hexdigest() == row['view_sha256']
            views[row['view_sha256']] = row['view']
    calls, outputs, changed = 0, 0, []
    for row, case in zip(rows, cases):
        assert row['label'] == case['label'] and row['status'] == 'complete'
        assert row['view_sha256'] == case['view_sha256'] and row['parent_scores'] == case['parent_scores']
        scored = row['child_scores']
        view = views[row['view_sha256']]
        keys = {a['action_key'] for a in view['actions']}
        entries = scored['entries']
        assert len(entries) == len(keys) and {e['action_key'] for e in entries} == keys
        assert all(type(e['score']) in (int, float) and math.isfinite(e['score']) for e in entries)
        assert scored['capture_receipt']['saved_before_score']
        assert scored['capture_receipt']['view_sha256'] == row['view_sha256']
        assert scored['operations'] <= closure['candidate_identity']['params']['max_operations']
        assert sorted(entries, key=lambda e: (-e['score'], e['action_key']))[0]['action_key'] == row['child_first']
        assert row['child_score_reused'] == (scored['actual_score_origin'] != row['label'])
        if not row['child_score_reused']:
            calls += 1; outputs += len(entries)
        if row['behavior_changed']:
            assert row['child_first'] != row['parent_first']
            changed.append({k: row[k] for k in ('label', 'parent_first', 'child_first')})
        else:
            assert row['child_first'] == row['parent_first']
    assert calls == len(views) == closure['unique_scored_views'] == closure['counts']['actual_child_score_calls']
    assert closure['input_capture']['terminal']['terminal_valid']
    result = {'complete': True, 'scope': 'pure mechanical and behavior readback; no strength/deadline/admission',
         'actual_tool_terminal': terminal, 'candidate_identity': closure['candidate_identity'],
         'windows': 100, 'actual_child_score_calls': calls, 'unique_full_inputs': len(views),
         'finite_legal_outputs_actual_calls': outputs, 'behavior_changed': changed,
         'max_operations': max(r['child_scores']['operations'] for r in rows),
         'new_models_rules_scores_worlds_tables_in_readback': 0}
    with (out / 'ROOT-READBACK.json').open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, sort_keys=True, indent=2); stream.write('\n')
    print({k: result[k] for k in ('complete', 'windows', 'actual_child_score_calls', 'finite_legal_outputs_actual_calls', 'behavior_changed')})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--slot', choices=('S01', 'S02'), required=True)
    main(parser.parse_args().slot)
