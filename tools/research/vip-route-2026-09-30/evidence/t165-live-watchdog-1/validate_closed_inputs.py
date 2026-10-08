"""用历史自然闭合原件验证 T165 分账，不产生新比赛或算法成绩。

混合统计的臂标签在本验证中是人工算术 fixture：T163 真实四席均为 T110，
绝不把其中两席改标 R18 后称作真实对照。这里只验证两席聚合不会虚增桌数。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t165-live-watchdog-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT


def main():
    spec = importlib.util.spec_from_file_location('t165_analysis_validate', _project_file(_PROJECT_ROOT, HERE / 'analyze.py'))
    analysis = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(analysis)
    directory = _project_file(_PROJECT_ROOT, HERE / 'validation-old-closed-inputs')
    directory.mkdir()
    plan = {'free_session': 'artifacts/sessions/t161-vip-s02-free-v4-paced',
            'mixed_session': 'artifacts/sessions/t163-vip-s02-testroom-v6'}
    identities = set()
    tables, _ = analysis.official_tables(_project_file(_PROJECT_ROOT, ROOT / plan['mixed_session']))
    for table in tables.values():
        identities.update(p['user_id'] for p in table['seats'])
    assert len(identities) == 4
    plan['owner_map'] = {uid: {'arm': 'T110' if i % 2 == 0 else 'R18', 'slot': 'fixture-%d' % i}
                         for i, uid in enumerate(sorted(identities))}
    for lane, old_name, runner in (
        ('free', 't161-received-fix-paced-experimental-free-1', 'AUTO-MATCH-CHILD-TERMINAL.json'),
        ('mixed', 't163-received-fix-fast-four-seat-testroom-1', 'ROOM-RUNNER-CHILD-TERMINAL.json')):
        old = _project_file(_PROJECT_ROOT, HERE.parent / old_name)
        for kind, original in (('CHILD', runner), ('POSTGAME', 'POSTGAME-CHILD-TERMINAL.json')):
            row = analysis.load(old / original)
            analysis.save(directory / (lane.upper() + '-' + kind + '-TERMINAL.json'),
                {'actual_exit_code': row['exit_code'], 'source': str((old / original).relative_to(ROOT)),
                 'validation_only_historical_terminal_translation': True})
        original_log = old / ('FREE-STDOUT-STDERR.log' if lane == 'free' else 'ROOM-STDOUT-STDERR.log')
        with (directory / (lane.upper() + '-STDOUT-STDERR.log')).open('x') as stream:
            stream.write(original_log.read_text())
    free = analysis.analyze_lane(directory, plan, 'free')
    mixed = analysis.analyze_lane(directory, plan, 'mixed')
    assert free['mutually_exclusive_accounts']['T110']['total_score'] == -141
    assert free['unique_tables'] == mixed['unique_tables'] == 10
    assert free['unique_hands'] == mixed['unique_hands'] == 80
    assert mixed['seat_hand_observations'] == 320
    assert sum(row['total_score'] for row in mixed['mutually_exclusive_accounts'].values()) == 0
    assert sum(a['complete_plans'] for a in mixed['audit']) == 11861
    assert sum(a['plans'] for a in mixed['audit']) == 11862
    assert len(mixed['zero_attempt_windows_unclassified']) == 2
    result = {'passed': True, 'official_calls': 0, 'new_rooms': 0,
        'scope': 'historical arithmetic fixture only; T163 actually all four T110, not an R18 comparison',
        'free_original_net': -141, 'free_accounts': free['mutually_exclusive_accounts'],
        'mixed_fixture_accounts': mixed['mutually_exclusive_accounts'],
        'mixed_fixture_unique_tables': 10, 'mixed_fixture_unique_hands': 80,
        'mixed_four_view_seat_hands': 320, 'full_plans': 11861, 'total_plans': 11862,
        'only_pass_missing_full_score_warning_tables': len(mixed['engineering_warning_tables']),
        'unclassified_zero_windows': 2, 'strength_admission': False}
    analysis.save(directory / 'RESULT.json', result)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
