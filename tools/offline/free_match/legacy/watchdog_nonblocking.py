"""T165 非阻塞监督：参赛自然闭合即续批，赛后任务独立排队。

原始审计、身份、终态与唯一 owner 是续赛硬保护；统计成功不是续赛前提。
后处理单进程低优先级执行，包含压缩。异常或积压只暂停接新后处理任务，
不终止正在参赛的玩家，也不覆写旧失败。运行源码和冻结包仍逐批核验。
"""
from __future__ import annotations

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

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent


def module(name, path):
    """复用独立旧监督器与只读统计接口；不调用旧自动续赛入口。"""
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


h = module('t165_existing_watch', _project_file(_PROJECT_ROOT, HERE / 'watchdog.py'))
a = module('t165_existing_analysis', _project_file(_PROJECT_ROOT, HERE / 'analyze.py'))
ROOT, PRIVATE = h.ROOT, h.PRIVATE
DRIVER = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t165-live-watchdog-1/watchdog_nonblocking.py')


def driver_hashes():
    """绑定监督器、借用入口和统计器，防止审核后静默漂移。"""
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (DRIVER, _project_file(_PROJECT_ROOT, HERE / 'watchdog.py'), _project_file(_PROJECT_ROOT, HERE / 'analyze.py'))}


def approved_preflight():
    """延续三个冻结包的根批准，并单独核新监督执行器批准。"""
    identity = h.preflight(require_review=True)
    approval = h.load(_project_file(_PROJECT_ROOT, HERE / 'NONBLOCKING-START-APPROVAL.json'))
    assert approval.get('approved') is True
    assert approval.get('driver_sha256') == driver_hashes()
    assert approval.get('package_ids') == identity['package_ids']
    assert approval.get('formal_release') is False
    return identity


def tail_finished(path):
    """只读每桌末尾64KiB的终态；不扫描大型 decision_input。"""
    with path.open('rb') as stream:
        stream.seek(max(0, path.stat().st_size - 65536))
        lines = stream.read().splitlines()
    records = []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue  # 有界读取的首行可能从中间开始。
        if row['kind'] == 'game_finished':
            records.append(row)
    assert records, '缺明确 game_finished，不能以文件存在冒充完成：' + str(path)
    vectors = {tuple(r['payload']['final_scores']) for r in records}
    assert len(vectors) == 1
    vector = next(iter(vectors))
    assert len(vector) == 4 and all(type(x) is int for x in vector) and sum(vector) == 0
    assert all(r['context']['game_id'] == path.stem for r in records)
    return {'game_id': path.stem, 'final_scores_seat_order_0_3': list(vector),
            'source': str(path.relative_to(ROOT)), 'tail_checked_bytes_max': 65536}


def written_path_present(run, relative, summary):
    """审计计数记逻辑raw文件名；gzip旋转文件只查存在与头，不冒充CRC核验。"""
    path = run / relative
    if path.is_file():
        return True
    if path.parent.name != 'raw' or summary['raw_retention'].get('gzip') is not True:
        return False
    chunks = sorted(path.parent.glob(path.stem + '.*.jsonl.gz'))
    if not chunks or any(p.stat().st_size < 18 for p in chunks):
        return False
    for chunk in chunks:
        with chunk.open('rb') as stream:
            if stream.read(2) != b'\x1f\x8b':
                return False
    return True


def verify_lane(directory, plan, lane):
    """核自然终态、无审计丢失、实际冻结身份、资源归零和十桌结束。

    此处只核原始审计自报计数及存在性，不冒充封存的全字节完整性检查。
    后者仍由 postgame 独立执行。discarded 属待诊断计数，保留在软警告中。
    """
    assert h.load(directory / (lane.upper() + '-CHILD-TERMINAL.json'))['actual_exit_code'] == 0
    session = _project_file(_PROJECT_ROOT, ROOT / plan[lane + '_session'])
    runs = sorted(session.glob('audit/runs/*')) if lane == 'free' else sorted(session.glob('audit/slot-*/runs/*'))
    terminals = a.end_records(directory / (lane.upper() + '-STDOUT-STDERR.log'), lane)
    assert len(runs) == (1 if lane == 'free' else 4)
    assert {r.name for r in runs} == {t['run_id'] for t in terminals}
    records, finals_by_game, soft = [], {}, []
    for run in runs:
        terminal = next(t for t in terminals if t['run_id'] == run.name)
        assert terminal['terminal_reason'] == 'tournament_finished'
        if lane == 'mixed':
            assert terminal['outcome'] == 'completed' and terminal['exit_code'] == 0
        else:
            assert terminal['audit_degraded'] is False
        summary_path, manifest_path = run / 'summary.json', run / 'manifest.json'
        summary, payload = h.load(summary_path), h.load(manifest_path)['payload']
        assert summary['run_id'] == run.name and summary['audit_degraded'] is False
        for key in ('dropped_low_priority', 'missing_high_priority', 'serialization_failures', 'write_failures'):
            assert summary[key] == 0, '原始审计缺口：' + key
        assert summary['raw_retention']['dropped'] == 0
        assert summary['raw_retention']['emitted_attempts'] > 0
        assert all(written_path_present(run, path, summary) for path in summary['written_by_path'])
        owners = [p for p in (run / 'participants').glob('u_*') if p.is_dir()]
        assert len(owners) == 1
        owner = owners[0]
        if lane == 'free':
            key, strategy = 'free', plan['identity']['free_strategy']
        else:
            slot = run.parents[1].name.removeprefix('slot-')
            arm = plan['slot_arms'][slot]
            key = 'mixed_t110' if arm == 'T110' else 'mixed_r18'
            strategy = plan['identity']['test_strategy'] if arm == 'T110' else plan['identity']['r18_strategy']
        assert payload['policy_version'] == strategy
        assert payload['policy_release']['release_package_id'] == plan['identity']['package_ids'][key]
        expected_math = plan['identity']['hand_math']
        assert payload['policy_release']['hand_math'] == expected_math
        # 顶层运行摘要会脱敏 native_sha256；冻结身份内同字段仍完整，单独核验。
        for name, value in expected_math.items():
            assert payload['hand_math'][name] == value or (
                name == 'native_sha256' and payload['hand_math'][name] == '[REDACTED]')
        assert payload['sse_effective'] is True and payload['discard_pacing_enabled'] is False
        assert payload['max_games'] == 10 and payload['rounds_per_game'] == 8
        compute = terminal.get('decision_compute')
        if compute is not None:
            assert compute['closed'] is True
            for name in ('active', 'current', 'live_processes', 'owned', 'pending', 'ready',
                         'transport_inflight', 'transport_threads_alive', 'late_reap_inflight', 'late_reap_threads_alive',
                         'faults', 'policy_failures', 'restarts'):
                assert compute[name] == 0, '运行或资源终态异常：' + name
            if compute['discarded']:
                soft.append({'run_id': run.name, 'compute_discarded_pending_diagnosis': compute['discarded']})
        files = sorted((owner / 'games').glob('*.jsonl'))
        assert len(files) == 10
        finals = [tail_finished(p) for p in files]
        room_ids = {row['game_id'].split('_r', 1)[0] for row in finals}
        assert len(room_ids) == 1
        if lane == 'mixed':
            assert room_ids == {plan['test_room_id']}
        for final in finals:
            previous = finals_by_game.setdefault(final['game_id'], final['final_scores_seat_order_0_3'])
            assert previous == final['final_scores_seat_order_0_3'], '四视角终分冲突'
        records.append({'run_id': run.name, 'owner': owner.name, 'policy_version': strategy,
            'release_package_id': payload['policy_release']['release_package_id'],
            'summary_sha256': hashlib.sha256(summary_path.read_bytes()).hexdigest(),
            'manifest_sha256': hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            'reported_audit_complete': True, 'raw_byte_integrity_not_yet_checked': True,
            'game_finished': finals, 'terminal': terminal})
    assert len(finals_by_game) == 10
    return {'lane': lane, 'unique_tables': 10, 'runs': records, 'soft_warnings': soft,
            'unique_rounds_not_yet_officially_reconciled': True}


def pending_jobs():
    """只排原始参赛已核闭合、且尚无后处理终态的批次；失败不自动覆盖重跑。"""
    return [p for p in sorted(HERE.glob('cycle-*')) if (p / 'RUN-CLOSED.json').is_file()
            and not (p / 'POSTPROCESS-START.json').exists()
            and not (p / 'POSTPROCESS-CLOSED.json').exists()]


def retain_interrupted_jobs():
    """重获worker锁后保留中断未知，不重跑原START、不覆写原件。"""
    for path in sorted(HERE.glob('cycle-*')):
        started, closed, receipt = (path / name for name in
            ('POSTPROCESS-START.json', 'POSTPROCESS-CLOSED.json', 'POSTPROCESS-INTERRUPTED.json'))
        if started.exists() and not closed.exists() and not receipt.exists():
            h.write(receipt, {'at_utc': h.now(), 'state': 'interrupted_result_unknown',
                'original_start_sha256': hashlib.sha256(started.read_bytes()).hexdigest(),
                'automatically_retried': False, 'worker_lock_reacquired': True,
                'requires_explicit_recovery': True}, exclusive=True)


def prior_runs_closed():
    """先拒绝尚活或身份不明的旧批；统计错误不使已核参赛被重新执行。"""
    prior = []
    for path in sorted(HERE.glob('cycle-*')):
        assert (path / 'PLAN.json').is_file(), '不完整建房目录禁止重试POST'
        plan = h.load(path / 'PLAN.json')
        if (path / 'RUN-CLOSED.json').is_file():
            assert h.load(path / 'RUN-CLOSED.json')['run_safety_verified'] is True
        else:
            # 迁移旧入口只接受已完整闭合或显式恢复的批次。
            assert (path / 'SUMMARY.json').is_file()
            success = ((path / 'CYCLE-CLOSED.json').is_file()
                       and h.load(path / 'CYCLE-CLOSED.json')['failures'] == [])
            recovered = ((path / 'RECOVERY-CLOSED.json').is_file()
                         and h.load(path / 'RECOVERY-CLOSED.json')['closed_verified'] is True)
            assert success or recovered
        for lane in ('free', 'mixed'):
            verify_lane(path, plan, lane)
        prior.append(plan['cycle'])
    return prior


def worker_command():
    """后处理有独立进程组，自身设置并记录CPU/IO优先级结果。"""
    return [sys.executable, str(DRIVER), 'worker']


def run_postprocess_step(directory, name, command, logfile, lock_fd):
    """子进程继承后处理锁；父意外退出时仍不能启动第二个重任务。"""
    with logfile.open('x') as stream:
        child = subprocess.Popen(command, cwd=ROOT, env=h.env(), stdout=stream,
            stderr=subprocess.STDOUT, start_new_session=True, pass_fds=(lock_fd,))
        h.write(directory / (name + '-PROCESS-START.json'), {'at_utc': h.now(), 'pid': child.pid,
            'inherits_postprocess_lock': True}, exclusive=True)
        code = child.wait()  # 仅等待本后处理子进程；不持比赛controller锁或Token。
    h.write(directory / (name + '-TERMINAL.json'), {'at_utc': h.now(), 'actual_exit_code': code}, exclusive=True)
    return code


def postprocess(directory, lock_fd):
    """仅处理已关的隔离session；捕获/封存/统计任何失败只记录本作业失败。"""
    plan = h.load(directory / 'PLAN.json')
    failures = []
    try:
        h.write(directory / 'POSTPROCESS-START.json', {'at_utc': h.now(), 'worker_pid': os.getpid(),
            'single_worker': True, 'cpu_nice': os.nice(0), 'contains_compression': True}, exclusive=True)
        private = PRIVATE / directory.name
        for lane in ('free', 'mixed'):
            session = _project_file(_PROJECT_ROOT, ROOT / plan[lane + '_session'])
            output = directory / (lane + '-capture')
            room = h.free_room(session) if lane == 'free' else plan['test_room_id']
            h.capture(session, h.load(private / (lane + '.json')), room, output)
        for lane in ('free', 'mixed'):
            code = run_postprocess_step(directory, lane.upper() + '-POSTGAME',
                [sys.executable, 'scripts/audit_tool.py', 'postgame', plan[lane + '_session'],
                 '--rule-config', str(private / 'rules.json')], directory / (lane.upper() + '-POSTGAME.log'), lock_fd)
            assert code == 0, 'postgame非0：' + lane
        code = run_postprocess_step(directory, 'ANALYSIS',
            [sys.executable, str(_project_file(_PROJECT_ROOT, HERE / 'analyze.py')), '--cycle', str(directory)],
            directory / 'BACKGROUND-ANALYSIS.log', lock_fd)
        assert code == 0, '统计非0，保留原失败；后续参赛不依赖此结果'
    except Exception as error:
        failures.append({'stage': 'postprocess', 'error': type(error).__name__ + ': ' + str(error)})
    closure = {'at_utc': h.now(), 'failures': failures, 'controller_sent_termination_signal': False,
               'strength_admission': False, 'does_not_block_next_match': True}
    h.write(directory / 'POSTPROCESS-CLOSED.json', closure, exclusive=True)
    h.write(directory / 'CYCLE-CLOSED.json', closure, exclusive=True)


def worker():
    """单锁、单队列、低优先级；暂停只影响新任务，已开始任务正常收尾。"""
    with (PRIVATE / 'postprocess.lock').open('a+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        approved_preflight()
        retain_interrupted_jobs()
        os.nice(15)
        taskpolicy = shutil.which('taskpolicy')
        io_command = ([taskpolicy, '-b', '-p', str(os.getpid())]
                      if sys.platform == 'darwin' and taskpolicy else
                      [shutil.which('ionice'), '-c', '3', '-p', str(os.getpid())]
                      if shutil.which('ionice') else None)
        io_result = subprocess.run(io_command, capture_output=True, text=True) if io_command else None
        priority = {'cpu_nice': os.nice(0), 'io_priority_actual_exit_code':
                    io_result.returncode if io_result else None,
                    'io_background_confirmed': io_result is not None and io_result.returncode == 0}
        h.write(PRIVATE / 'postprocess-priority.json', {'at_utc': h.now(), 'worker_pid': os.getpid(), **priority})
        if not priority['io_background_confirmed']:
            h.write(_project_file(_PROJECT_ROOT, HERE / 'BACKGROUND-STATUS.json'), {'at_utc': h.now(), 'worker_pid': os.getpid(),
                'state': 'blocked_priority_setup', **priority})
            return  # 后处理资源配置失败不阻断参赛；不得假称低IO优先级已设置。
        stop = [False]
        signal.signal(signal.SIGINT, lambda *_: stop.__setitem__(0, True))
        signal.signal(signal.SIGTERM, lambda *_: stop.__setitem__(0, True))
        while not stop[0]:
            queue = pending_jobs()
            control = h.load(PRIVATE / 'control.json')
            paused = not control.get('background_enabled', True)
            h.write(_project_file(_PROJECT_ROOT, HERE / 'BACKGROUND-STATUS.json'), {'at_utc': h.now(), 'worker_pid': os.getpid(),
                'state': 'paused_new_jobs' if paused else 'waiting', 'pending_cycles': [p.name for p in queue],
                **priority, 'contains_compression': True})
            if queue and not paused:
                h.write(_project_file(_PROJECT_ROOT, HERE / 'BACKGROUND-STATUS.json'), {'at_utc': h.now(), 'worker_pid': os.getpid(),
                    'state': 'processing', 'cycle': queue[0].name, 'cpu_nice': os.nice(0),
                    'pending_cycles': [p.name for p in queue], **priority, 'contains_compression': True})
                postprocess(queue[0], lock.fileno())
                continue
            state = h.load(PRIVATE / 'state.json')
            live = h.process_identity(state.get('controller_pid'), DRIVER.name + ' watch')
            if live['expected_command_live'] is False and not queue:
                return
            time.sleep(5)


def one_cycle(number, identity):
    """两路自然完赛后仅做有界硬保护，入队立即返回；没有玩家kill路径。"""
    directory, private, plan = h.prepare_cycle(number, identity)
    lanes = {}
    for lane in ('free', 'mixed'):
        command = [sys.executable, 'scripts/run_auto_match.py' if lane == 'free' else 'scripts/run_test_room.py',
                   '--config', str(private / (lane + '.json'))]
        command += ['--token-file', str(h.TOKEN)] if lane == 'free' else ['--once']
        stream = (directory / (lane.upper() + '-STDOUT-STDERR.log')).open('x')
        process = subprocess.Popen(command, cwd=ROOT, env=h.env(), stdout=stream,
            stderr=subprocess.STDOUT, start_new_session=True)
        lanes[lane] = {'process': process, 'stream': stream, 'closed': False}
        h.write(directory / (lane.upper() + '-START.json'), {'at_utc': h.now(), 'pid': process.pid,
            'session': plan[lane + '_session'], 'config_kept_private': True}, exclusive=True)
        h.publish_status({'state': 'players_running', 'cycle': number, 'driver': DRIVER.name,
            'active_children': {k: j['process'].pid for k, j in lanes.items()},
            'no_heavy_research_while_players_live': True, 'single_low_priority_postprocess_allowed': True})
    while any(not job['closed'] for job in lanes.values()):
        for lane, job in lanes.items():
            code = job['process'].poll()
            if code is None or job['closed']:
                continue
            job['stream'].close()
            h.write(directory / (lane.upper() + '-CHILD-TERMINAL.json'), {'at_utc': h.now(),
                'actual_exit_code': code, 'controller_sent_termination_signal': False}, exclusive=True)
            job['closed'] = True
        h.publish_status({'state': 'players_running', 'cycle': number, 'driver': DRIVER.name,
            'active_children': {k: j['process'].pid for k, j in lanes.items() if j['process'].poll() is None},
            'single_low_priority_postprocess_allowed': True})
        if any(not job['closed'] for job in lanes.values()):
            time.sleep(15)
    assert not h.other_players(), '有遗留玩家或别的owner，不能续新房'
    lanes_verified = {lane: verify_lane(directory, plan, lane) for lane in ('free', 'mixed')}
    h.write(directory / 'OWNER-MAP.json', h.mixed_owners(_project_file(_PROJECT_ROOT, ROOT / plan['mixed_session']), plan['slot_arms']), exclusive=True)
    # 入队前再次核冻结包；同样保证参赛硬保护不会因分析器变化被略过。
    assert approved_preflight() == identity
    h.write(directory / 'RUN-CLOSED.json', {'at_utc': h.now(), 'run_safety_verified': True,
        'lanes': lanes_verified, 'raw_byte_integrity_pending_postgame': True,
        'no_live_players_verified': True, 'driver_sha256': driver_hashes(),
        'controller_sent_termination_signal': False, 'strength_admission': False}, exclusive=True)
    h.publish_status({'state': 'run_closed_postprocess_queued', 'cycle': number, 'driver': DRIVER.name,
        'active_children': {}, 'pending_postprocess_cycles': [p.name for p in pending_jobs()]})


def watch():
    """复用同一controller锁和Token owner约束；旧watch活跃时拒绝并存。"""
    PRIVATE.mkdir(mode=0o700, exist_ok=True)
    with (PRIVATE / 'controller.lock').open('a+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('已有 T165 控制器，拒绝重复启动', flush=True)
            return
        assert not h.other_players()
        prior_runs_closed()
        identity = approved_preflight()
        stop = [False]
        signal.signal(signal.SIGINT, lambda *_: stop.__setitem__(0, True))
        signal.signal(signal.SIGTERM, lambda *_: stop.__setitem__(0, True))
        worker_process = None
        try:
            while not stop[0] and h.load(PRIVATE / 'control.json')['continue_after_cycle']:
                assert not h.other_players()
                identity = approved_preflight()
                prior = prior_runs_closed()
                # 真实低磁盘空间会危及原始审计；纯分析积压本身不停止比赛。
                available = shutil.disk_usage(ROOT).free
                minimum = h.load(PRIVATE / 'control.json').get('minimum_free_bytes', 8 * 1024**3)
                assert type(minimum) is int and minimum > 0
                assert available >= minimum, '原始审计存储余量不足，停止新房但不停止已有玩家'
                # 启动前发布当前真实controller，使后台只处理已闭合的批次。
                h.publish_status({'state': 'preparing_next_batch', 'driver': DRIVER.name, 'active_children': {}})
                if worker_process is None or worker_process.poll() is not None:
                    with (PRIVATE / 'postprocess.stdout.log').open('a') as stream:
                        worker_process = subprocess.Popen(worker_command(), cwd=ROOT, env=h.env(),
                            stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
                one_cycle(1 + max(prior, default=0), identity)
            h.publish_status({'state': 'stopped_after_natural_cycle', 'driver': DRIVER.name, 'active_children': {}})
        except Exception as error:
            previous = h.load(PRIVATE / 'state.json')
            h.write(PRIVATE / 'control.json', {**h.load(PRIVATE / 'control.json'), 'background_enabled': False})
            h.publish_status({'state': 'blocked_new_rooms', 'driver': DRIVER.name,
                'active_children': {k: pid for k, pid in previous.get('active_children', {}).items() if h.pid_alive(pid)},
                'reason': type(error).__name__ + ': ' + str(error)})
            raise


def status():
    """核本入口真实命令及独立后台状态，避免旧status误判新controller。"""
    state = h.load(_project_file(_PROJECT_ROOT, HERE / 'STATUS.json'))
    expected_driver = state.get('driver', 'watchdog.py')
    assert expected_driver in ('watchdog.py', DRIVER.name), '未知监督器入口，禁止推测owner'
    state['controller_process_now'] = h.process_identity(state.get('controller_pid'), expected_driver + ' watch')
    state['active_children_now'] = {key: h.process_identity(pid,
        'run_auto_match.py' if key == 'free' else 'run_test_room.py')
        for key, pid in state.get('active_children', {}).items()}
    if (_project_file(_PROJECT_ROOT, HERE / 'BACKGROUND-STATUS.json')).exists():
        background = h.load(_project_file(_PROJECT_ROOT, HERE / 'BACKGROUND-STATUS.json'))
        background['worker_process_now'] = h.process_identity(background.get('worker_pid'), DRIVER.name + ' worker')
        state['background'] = background
    state['pending_postprocess_cycles_now'] = [p.name for p in pending_jobs()]
    state['failed_postprocess_cycles_now'] = [p.parent.name for p in sorted(HERE.glob('cycle-*/POSTPROCESS-CLOSED.json'))
                                            if h.load(p)['failures']]
    state['interrupted_postprocess_cycles_now'] = [p.parent.name for p in sorted(HERE.glob('cycle-*/POSTPROCESS-INTERRUPTED.json'))]
    children = []
    for path in sorted(HERE.glob('cycle-*/*-PROCESS-START.json')):
        phase = path.name.removesuffix('-PROCESS-START.json')
        plan = h.load(path.parent / 'PLAN.json')
        if phase in ('FREE-POSTGAME', 'MIXED-POSTGAME'):
            lane = phase.split('-', 1)[0].lower()
            expected = 'audit_tool.py postgame ' + plan[lane + '_session']
        elif phase == 'ANALYSIS':
            expected = 'analyze.py --cycle ' + str(path.parent)
        else:
            raise AssertionError('未知后处理子阶段，不能猜命令：' + phase)
        process = h.process_identity(h.load(path)['pid'], expected)
        terminal = path.parent / (phase + '-TERMINAL.json')
        children.append({'cycle': path.parent.name, 'phase': phase, 'source': str(path.relative_to(ROOT)),
            'process_now': process, 'terminal_record_present': terminal.exists(),
            'result_unknown': not terminal.exists()})
    state['background_children_now'] = children
    state['background_job_still_running_or_unknown'] = any(
        c['process_now']['expected_command_live'] is not False for c in children)
    print(json.dumps(state, ensure_ascii=False, indent=2))


def main():
    """预检不发HTTP；worker不持赛事Token，watch才会创建与参赛。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('watch', 'worker', 'preflight', 'status'))
    args = parser.parse_args()
    if args.command == 'watch':
        watch()
    elif args.command == 'worker':
        worker()
    elif args.command == 'status':
        status()
    else:
        print(json.dumps({'identity': h.preflight(require_review=True), 'driver_sha256': driver_hashes(),
                          'new_http_calls': 0, 'new_players': 0}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
