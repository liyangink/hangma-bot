"""只验已自然闭合的四席小房；复用规范审计检查，按完整桌去重。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t179-production-wiring-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = _PROJECT_ROOT
HERE = Path(__file__).resolve().parent
DIRECTORY = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t179-production-wiring-1/official-engineering-001')
SESSION = _project_file(_PROJECT_ROOT, ROOT / 'artifacts/sessions/t179-official-engineering-001')


def load(path):
    return json.loads(path.read_text())


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def main():
    assert load(_project_file(_PROJECT_ROOT, DIRECTORY / 'CHILD-TERMINAL.json'))['actual_exit_code'] == 0
    plan = load(_project_file(_PROJECT_ROOT, DIRECTORY / 'PLAN.json'))
    driver = module('t179_engineering_helpers', _project_file(_PROJECT_ROOT, HERE / 'free_watchdog.py'))
    terminals = driver.a.end_records(_project_file(_PROJECT_ROOT, DIRECTORY / 'STDOUT-STDERR.log'), 'mixed')
    assert all(t['outcome'] == 'completed' and t['terminal_reason'] == 'tournament_finished'
               and t['exit_code'] == 0 for t in terminals)
    for terminal in terminals:
        compute = terminal['decision_compute']
        assert compute['closed'] and compute['process_starts'] == 10
        assert all(compute[k] == 0 for k in ('owned', 'pending', 'active', 'ready',
            'current', 'live_processes', 'transport_inflight', 'transport_threads_alive',
            'late_reap_inflight', 'late_reap_threads_alive', 'bound_games', 'releasing_games'))
    runs = sorted((_project_file(_PROJECT_ROOT, SESSION / 'audit')).glob('slot-*/runs/*'))
    assert len(runs) == 4
    assert {r.name for r in runs} == {t['run_id'] for t in terminals}
    for run in runs:
        manifest = load(run / 'manifest.json')['payload']
        assert manifest['policy_release']['release_package_id'] == plan['package_id']
        assert manifest['policy_version'] == plan['strategy']
        assert manifest['sse_effective'] and not manifest['discard_pacing_enabled']
        assert manifest['max_games'] == 2 and manifest['rounds_per_game'] == 2
        summary = load(run / 'summary.json')
        assert not summary['audit_degraded']
        assert all(summary[k] == 0 for k in ('dropped_low_priority', 'missing_high_priority',
            'serialization_failures', 'write_failures'))
        assert summary['raw_retention']['dropped'] == 0

    from hangma_bot.bootstrap import build_public_archive_client
    from hangma_bot.adapters.official.archive_download import collect_test_room
    config = load(_project_file(_PROJECT_ROOT, ROOT / '.private/t179-wiring/official-engineering-001/room.json'))
    with build_public_archive_client(config) as client:
        captured = [collect_test_room(client, plan['room_id'], batch, SESSION) for batch in range(2)]
    save(_project_file(_PROJECT_ROOT, DIRECTORY / 'CAPTURE-RESULT.json'), {'batches': captured})
    started = time.monotonic()
    with (_project_file(_PROJECT_ROOT, DIRECTORY / 'POSTGAME.log')).open('x') as stream:
        process = subprocess.run([sys.executable, 'scripts/audit_tool.py', 'postgame', str(SESSION)],
                                 stdout=stream, stderr=subprocess.STDOUT)
    save(_project_file(_PROJECT_ROOT, DIRECTORY / 'POSTGAME-CLOSED.json'), {'actual_exit_code': process.returncode,
        'elapsed_seconds': time.monotonic() - started})
    assert process.returncode == 0

    helper = module('t179_engineering_score_audit', _project_file(_PROJECT_ROOT, HERE.parent /
                    't163-received-fix-fast-four-seat-testroom-1/summarize_closed.py'))
    helper.BASE = SESSION
    sources = {}
    audits = [helper.audit_run(run, sources) for run in runs]
    tables, timeouts = {}, []
    for path in sorted(SESSION.glob('official/dl-*/events.json')):
        original, body = load(path.parent / 'source.json'), load(path)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == original['original_sha256']
        assert body['status'] == 'finished'
        events = {}
        for block in body['blocks']:
            for event in block['events']:
                if event['seq'] in events:
                    assert events[event['seq']] == event
                events[event['seq']] = event
        endings = [e for e in events.values() if e['type'] == 'round_ended']
        finals = [e['data']['final_scores'] for e in events.values() if e['type'] == 'game_ended']
        assert len(endings) == 2 and len(finals) == 1
        table = {'game_id': body['game_id'], 'complete_rounds': 2, 'scores_seat_order': finals[0]}
        if table['game_id'] in tables:
            assert tables[table['game_id']] == table
            continue
        tables[table['game_id']] = table
        timeouts.extend({'game_id': body['game_id'], 'event': e} for e in events.values()
                        if e['type'] == 'timeout')
    assert len(tables) == 2
    http_429 = sum(a['http_categories'].get(c, {}).get('429', 0)
                   for a in audits for c in ('state', 'action'))
    result = {'terminals': terminals, 'tables': list(tables.values()), 'complete_tables': 2,
        'complete_rounds': 4, 'audits': audits, 'source_sha256': sources,
        'game_http_429': http_429, 'official_timeouts': timeouts,
        'official_discard_timeouts': [t for t in timeouts if t['event'].get('data', {}).get('kind') == 'discard'],
        'full_M10_stress_not_claimed': True, 'strength_admission': False, 'formal_release': False}
    save(_project_file(_PROJECT_ROOT, DIRECTORY / 'VERIFIED.json'), result)
    assert http_429 == 0 and not result['official_discard_timeouts']
    assert all(not a['policy_errors'] and not a['full_plan_legal_key_mismatches'] for a in audits)
    print(json.dumps({'complete_tables': 2, 'complete_rounds': 4, '429': http_429,
        'plans': sum(a['plans'] for a in audits),
        'full_plans': sum(a['complete_plans'] for a in audits)}), flush=True)


if __name__ == '__main__':
    main()
