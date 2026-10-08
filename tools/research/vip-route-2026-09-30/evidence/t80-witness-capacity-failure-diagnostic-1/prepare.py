"""只读终态确认批，保存费用分母和首个失败的合法公开观察，不开新桌。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t80-witness-capacity-failure-diagnostic-1'

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
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t78-net-upgrade-fixed-qualifier-confirmation-1')


def sha(path):
    """流式核原件，避免巨量决策记录进入内存。"""
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for part in iter(lambda: stream.read(1 << 20), b''):
            h.update(part)
    return h.hexdigest()


def save(path, value):
    """仅新建收据；重复执行拒绝覆盖原失败。"""
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2,
                  allow_nan=False)
        stream.write('\n')


def main():
    blocks, issues, refs = [], [], {}
    for i in range(1, 5):
        out = _project_file(_PROJECT_ROOT, SOURCE / f'block-{i:02d}')
        path = out / 'summary.json'
        summary = json.loads(path.read_text())
        results = [json.loads(line) for line in (out / 'results.jsonl').open()]
        counts = Counter(row['status'] for row in results)
        assert len(results) == summary['actual_started_table_instances']
        assert sum(row['completed_hands'] for row in results) == summary['completed_hands']
        assert summary['identity_stable'] and not summary['development_complete']
        assert summary['charged_table_instances'] == len(results)
        for p in (path, out / 'results.jsonl', out / 'end-freeze.json'):
            refs[str(p.resolve())] = sha(p)
        blocks.append({'block': i, 'started_tables': len(results),
                       'charged_tables': summary['charged_table_instances'],
                       'status_counts': dict(counts),
                       'completed_hands': summary['completed_hands'],
                       'decision_windows': summary['decision_windows'],
                       'terminal_capture': summary['scoring_input_capture']['terminal'],
                       'issues': summary['issues']})
        issues.extend(summary['issues'])
    failed = []
    raw_path = _project_file(_PROJECT_ROOT, SOURCE / 'block-03/decisions.jsonl.gz')
    for line in gzip.open(raw_path, 'rt'):
        row = json.loads(line)
        if row['status'] != 'chosen':
            failed.append(row)
    assert len(failed) == 1
    assert failed[0]['error'].endswith('终点胡条件见证达到冻结上限')
    refs[str(raw_path.resolve())] = sha(raw_path)
    save(_project_file(_PROJECT_ROOT, HERE / 'FAILED-PUBLIC-WINDOW.json'), {'schema': 't80-public-failure/1',
         'actual_failed_row': failed[0], 'source_sha256': refs[str(raw_path.resolve())],
         'source': str(raw_path.resolve()), 'new_models_scores_worlds_tables': 0})
    started = sum(b['started_tables'] for b in blocks)
    complete = sum(b['status_counts'].get('complete', 0) for b in blocks)
    assert started == 250 and complete == 249
    save(_project_file(_PROJECT_ROOT, HERE / 'T78-FAILURE-COST-CLOSURE.json'), {
        'schema': 't78-failed-campaign-cost-readback/1', 'all_four_handles_terminal_exit1': True,
        'handle_ids': [91886, 61223, 39284, 69235], 'blocks': blocks,
        'planned_actual_tables': 1024, 'charged_and_started_tables': started,
        'complete_tables': complete, 'partial_tables': started-complete,
        'unstarted_tables_retained_in_plan': 1024-started,
        'completed_hands': sum(b['completed_hands'] for b in blocks),
        'actual_decision_windows': sum(b['decision_windows'] for b in blocks),
        'whole_batch_valid': False, 'confirmation_claim': False, 'online_admission': False,
        'failure': failed[0]['error'], 'source_files': refs,
        'scope': '纯终态文件核账；不把幸存桌均值当完整确认，不重评分或推进世界',
        'new_models_scores_worlds_tables': 0})
    print({'started': started, 'complete': complete, 'partial': started-complete,
           'actual_failed_window': failed[0]['window_key'], 'confirmation_claim': False})


if __name__ == '__main__':
    main()
