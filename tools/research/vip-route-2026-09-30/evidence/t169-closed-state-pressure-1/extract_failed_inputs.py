"""从已经封存的第二批审计提取五个可鸣牌漏评分窗口及两个开局只过窗口。

仅解码目标 decision_id 的行，逐字节验证完整源文件 SHA。比赛不暂停；
需要后台统计已暂停接新任务，以免两个处理任务竞争。不会运行策略或网络。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t169-closed-state-pressure-1'

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
import os
from pathlib import Path
import subprocess
import time

ROOT = _PROJECT_ROOT
HERE = Path(__file__).resolve().parent
T165 = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t165-live-watchdog-1')


def load(path):
    return json.loads(path.read_text())


def main():
    """读取指定关闭身份，保存原字段与来源；公开源码不读取 Token 正文。"""
    control = load(_project_file(_PROJECT_ROOT, ROOT / '.private/t165-live-watchdog/control.json'))
    assert control['background_enabled'] is False, '需要先暂停后台接新统计任务'
    background = load(_project_file(_PROJECT_ROOT, T165 / 'BACKGROUND-STATUS.json'))
    assert background['state'] in ('waiting', 'paused_new_jobs')
    os.nice(15)
    priority = subprocess.run(['/usr/sbin/taskpolicy', '-b', '-p', str(os.getpid())],
                              capture_output=True, text=True)
    assert priority.returncode == 0, '后台 IO 优先级未实际设置'
    started = time.monotonic()
    cycle = _project_file(_PROJECT_ROOT, T165 / 'cycle-002')
    summary = load(cycle / 'SUMMARY.json')
    plan = load(cycle / 'PLAN.json')
    targets_by_path = {}
    for lane_name in ('free', 'mixed'):
        assert load(cycle / (lane_name.upper() + '-CHILD-TERMINAL.json'))['actual_exit_code'] == 0
        lane = summary['lanes'][lane_name]
        assert lane['postgame_audit_complete'] and lane['postgame_bundle_verified']
        for audit in lane['audit']:
            for failure in audit['failed_plans']:
                input_data, context = failure['input'], failure['context']
                valuable = input_data['legal'] != ['pass']
                initial_pass = lane_name == 'free' and context['trigger_seq'] == 2
                if not (valuable or initial_pass):
                    continue
                source = input_data['source']
                path = _project_file(_PROJECT_ROOT, ROOT / plan[lane_name + '_session'] / source)
                group = targets_by_path.setdefault(path, {
                    'expected_sha256': lane['audit_source_sha256'][source], 'targets': []})
                group['targets'].append({'decision_id': context['decision_id'],
                    'context': context, 'input_line': input_data['line'],
                    'plan_line': failure['plan_line'], 'valuable_choice': valuable})
    assert sum(len(g['targets']) for g in targets_by_path.values()) == 7
    sources, total_bytes = [], 0
    for path, group in targets_by_path.items():
        targets = {r['decision_id']: r for r in group['targets']}
        needles = {k: k.encode() for k in targets}
        sha, records = hashlib.sha256(), {key: [] for key in targets}
        with path.open('rb') as stream:
            for line_number, raw in enumerate(stream, 1):
                total_bytes += len(raw)
                assert total_bytes < 2 * 1024**3, '提取超过有界读取上限'
                sha.update(raw)
                matching = [key for key, needle in needles.items() if needle in raw]
                if not matching:
                    continue
                row = json.loads(raw)
                key = row['context'].get('decision_id')
                if key in records:
                    records[key].append({'source_line': line_number, 'record': row})
        assert sha.hexdigest() == group['expected_sha256'], '原始关闭审计字节漂移'
        for key, items in records.items():
            target = targets[key]
            inputs = [r for r in items if r['record']['kind'] == 'decision_input']
            assert len(inputs) == 1 and inputs[0]['source_line'] == target['input_line']
            assert any(r['source_line'] == target['plan_line'] for r in items)
            value = {'original_source': str(path.relative_to(ROOT)),
                     'original_source_sha256': sha.hexdigest(),
                     'target': target, 'records': items,
                     'input_is_original_visible_decision_request': True,
                     'new_rules_policy_network_calls': 0}
            with (_project_file(_PROJECT_ROOT, HERE / (key + '.json'))).open('x') as out:
                json.dump(value, out, ensure_ascii=False, indent=2, allow_nan=False)
                out.write('\n')
        sources.append({'path': str(path.relative_to(ROOT)), 'sha256': sha.hexdigest(),
                        'targets': list(targets), 'full_byte_hash_verified': True})
    receipt = {'sources': sources, 'actual_bytes_read': total_bytes,
        'elapsed_sec': time.monotonic() - started, 'cpu_nice': os.nice(0),
        'io_background_actual_exit_code': priority.returncode,
        'only_target_json_rows_decoded': True, 'new_rules_policy_network_calls': 0,
        'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    with (_project_file(_PROJECT_ROOT, HERE / 'FAILED-INPUT-EXTRACTION.json')).open('x') as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == '__main__':
    main()
