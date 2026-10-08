"""非阻塞监督器的小验证：只读首批；隔离复制小元数据做负例，零HTTP。"""

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
import copy
import fcntl
import io
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('t165_nb_validation', _project_file(_PROJECT_ROOT, HERE / 'watchdog_nonblocking.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def fixture(base):
    """仅复制已闭合小文件，大审计文件只建只读指向，不修改原件。"""
    original = _project_file(_PROJECT_ROOT, HERE / 'cycle-001')
    plan = copy.deepcopy(m.h.load(original / 'PLAN.json'))
    cycle = base / 'cycle-001'
    cycle.mkdir()
    for lane in ('free', 'mixed'):
        old_session = m.ROOT / plan[lane + '_session']
        session = base / ('session-' + lane)
        plan[lane + '_session'] = str(session.relative_to(m.ROOT))
        for source in old_session.glob('audit/**/runs/*'):
            target = session / source.relative_to(old_session)
            target.mkdir(parents=True)
            shutil.copy2(source / 'summary.json', target / 'summary.json')
            shutil.copy2(source / 'manifest.json', target / 'manifest.json')
            # 计数的文件存在性与尾部读取保持真实；这些链接从不写入。
            for p in source.iterdir():
                if p.name not in ('summary.json', 'manifest.json'):
                    (target / p.name).symlink_to(p.resolve(), target_is_directory=p.is_dir())
        for name in (lane.upper() + '-CHILD-TERMINAL.json', lane.upper() + '-STDOUT-STDERR.log'):
            shutil.copy2(original / name, cycle / name)
    m.h.write(cycle / 'PLAN.json', plan)
    return cycle, plan


def rejected(operation):
    """要求护栏实际拒绝；不把异常缺失当测试通过。"""
    try:
        operation()
    except AssertionError as error:
        return {'rejected': True, 'reason': str(error)}
    raise AssertionError('预期护栏拒绝但没有拒绝')


def main():
    """所有fixture随调用清理，仅保留无凭据验证收据。"""
    results = {'new_official_calls': 0, 'new_players': 0, 'driver_sha256': m.driver_hashes(), 'checks': {}}
    with tempfile.TemporaryDirectory(prefix='nb-validation-', dir=m.PRIVATE) as temporary:
        base = Path(temporary)
        cycle, plan = fixture(base)
        for lane in ('free', 'mixed'):
            row = m.verify_lane(cycle, plan, lane)
            results['checks']['real_' + lane + '_closure'] = {'passed': True, 'unique_tables': row['unique_tables']}
        failure = cycle / 'FREE-CHILD-TERMINAL.json'
        original = m.h.load(failure)
        m.h.write(failure, {**original, 'actual_exit_code': 1})
        results['checks']['actual_run_failure_blocks'] = rejected(lambda: m.verify_lane(cycle, plan, 'free'))
        m.h.write(failure, original)
        run = next((m.ROOT / plan['free_session']).glob('audit/runs/*'))
        summary_path = run / 'summary.json'
        summary = m.h.load(summary_path)
        m.h.write(summary_path, {**summary, 'missing_high_priority': 1})
        results['checks']['raw_audit_gap_blocks'] = rejected(lambda: m.verify_lane(cycle, plan, 'free'))
        m.h.write(summary_path, summary)
        manifest_path = run / 'manifest.json'
        manifest = m.h.load(manifest_path)
        bad = copy.deepcopy(manifest)
        bad['payload']['policy_release']['release_package_id'] = 'unexpected-identity'
        m.h.write(manifest_path, bad)
        results['checks']['release_identity_drift_blocks'] = rejected(lambda: m.verify_lane(cycle, plan, 'free'))
        m.h.write(manifest_path, manifest)
        logfile = cycle / 'FREE-STDOUT-STDERR.log'
        original_log = logfile.read_text()
        logfile.write_text(original_log.replace('"active": 0', '"active": 1'))
        results['checks']['resource_leak_blocks'] = rejected(lambda: m.verify_lane(cycle, plan, 'free'))
        logfile.write_text(original_log)
        fake = base / 'unfinished.jsonl'
        fake.write_text(json.dumps({'kind': 'authoritative_state', 'context': {}, 'payload': {}}) + '\n')
        results['checks']['game_filename_is_not_completion'] = rejected(lambda: m.tail_finished(fake))
        # 纯分析失败不重跑赛事；新的硬保护仍重新核真实首批的元数据。
        old_here = m.HERE
        m.HERE = base
        results['checks']['unclosed_batch_blocks'] = rejected(m.prior_runs_closed)
        m.h.write(cycle / 'RUN-CLOSED.json', {'run_safety_verified': True})
        m.h.write(cycle / 'POSTPROCESS-CLOSED.json', {'failures': ['intentional-statistics-failure']})
        assert m.prior_runs_closed() == [1]
        results['checks']['statistics_failure_does_not_block_safe_runs'] = {'passed': True}
        pending = base / 'cycle-002'
        interrupted = base / 'cycle-003'
        for p in (pending, interrupted):
            p.mkdir()
            m.h.write(p / 'RUN-CLOSED.json', {'run_safety_verified': True})
        m.h.write(interrupted / 'POSTPROCESS-START.json', {'worker_pid': -1})
        assert m.pending_jobs() == [pending]
        m.retain_interrupted_jobs()
        assert m.h.load(interrupted / 'POSTPROCESS-INTERRUPTED.json')['automatically_retried'] is False
        assert m.pending_jobs() == [pending]
        results['checks']['interrupted_and_failed_jobs_not_retried'] = {'passed': True}
        # 父worker已不存在，但真实命令核验仍认为后处理子活跃时，status不得报已结束。
        m.h.write(base / 'STATUS.json', {'controller_pid': -1, 'driver': m.DRIVER.name, 'active_children': {}})
        m.h.write(base / 'BACKGROUND-STATUS.json', {'worker_pid': -1})
        m.h.write(cycle / 'FREE-POSTGAME-PROCESS-START.json', {'pid': 123})
        original_identity = m.h.process_identity
        m.h.process_identity = lambda pid, expected: {
            'pid_exists': pid == 123, 'expected_command_live': pid == 123,
            'status': 'fixture_actual_command_check'}
        output = io.StringIO()
        with redirect_stdout(output):
            m.status()
        status = json.loads(output.getvalue())
        assert status['background']['worker_process_now']['expected_command_live'] is False
        assert status['background_job_still_running_or_unknown'] is True
        assert status['background_children_now'][0]['result_unknown'] is True
        m.h.process_identity = original_identity
        results['checks']['status_retains_orphan_job_running_unknown'] = {'passed': True, 'fixture_only': True}
        m.HERE = old_here
        # 真实POSIX锁继承：父关闭句柄，未退出子仍挡第二worker；子自然退出后才释放。
        lockpath = base / 'inherited.lock'
        lock = lockpath.open('a+')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        child = subprocess.Popen([sys.executable, '-c', 'import sys; print("ready",flush=True);sys.stdin.read(1)'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, pass_fds=(lock.fileno(),), start_new_session=True)
        assert child.stdout.readline().strip() == 'ready'
        lock.close()
        probe = lockpath.open('a+')
        try:
            fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            held = True
        else:
            held = False
        child.stdin.write('x')
        child.stdin.flush()
        assert child.wait() == 0 and held
        fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
        probe.close()
        results['checks']['orphan_postprocess_inherits_single_worker_lock'] = {'passed': True}
    m.h.write(_project_file(_PROJECT_ROOT, HERE / 'NONBLOCKING-VALIDATION.json'), results)
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
