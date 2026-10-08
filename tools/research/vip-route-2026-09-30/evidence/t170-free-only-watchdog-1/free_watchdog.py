"""T170 独立自由赛守护：自然完赛先续赛，单个后台再采集和统计。

测试房及其历史失败不参与自由赛续赛判定。身份、原始审计、资源未回收和
官方永久停止仍为硬保护；实验策略失败、迟回信及成绩只记工程告警。
任何入口都不终止已经开打的官方玩家，不盲目重试未知匹配结果。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t170-free-only-watchdog-1'

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
ROOT = _PROJECT_ROOT
OLD = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t165-live-watchdog-1')
sys.path[:0] = [str(ROOT), str(_project_file(_PROJECT_ROOT, ROOT / 'src'))]


def module(name, path):
    """复用已审核的只读工具，不执行旧的两路自动续赛入口。"""
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


n = module('t170_closed_audit', _project_file(_PROJECT_ROOT, OLD / 'watchdog_nonblocking.py'))
h, a = n.h, n.a
PRIVATE = _project_file(_PROJECT_ROOT, '.private/t170-free-watchdog')
CONTROL = _project_file(_PROJECT_ROOT, '.private/t170-free-watchdog/control.json')
# 与旧控制器及临时自由赛 wrapper 共用锁，避免同 Token 的两个 owner。
OWNER_LOCK = h.PRIVATE / 'controller.lock'
POSTPROCESS_LOCK = h.PRIVATE / 'postprocess.lock'
DRIVER = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t170-free-only-watchdog-1/free_watchdog.py')


def hashes():
    """绑定本入口及真正复用的三个来源；不绑定运行状态和统计结果。"""
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in
            (DRIVER, _project_file(_PROJECT_ROOT, OLD / 'watchdog_nonblocking.py'), _project_file(_PROJECT_ROOT, OLD / 'watchdog.py'), _project_file(_PROJECT_ROOT, OLD / 'analyze.py'))}


def identity():
    """只核当前自由赛包，不让历史测试房或 R18 的门禁卡住自由赛。"""
    import hangma_bot.bootstrap as b
    manifest = b._load_vip_manifest(b.VIP_S02_FREE_STRATEGY, None)
    assert 'auto_match' in manifest['allowed_modes']
    return {'free_strategy': b.VIP_S02_FREE_STRATEGY,
            'package_ids': {'free': manifest['release_package_id']},
            'rules_source_hash': b.compute_rules_hash(ROOT),
            'hand_math': b.hand_math_runtime_metadata()}


def preflight():
    """离线预检只装配，不发 HTTP；源码或冻结身份漂移必须明确重新审核。"""
    value = identity()
    approval = h.load(_project_file(_PROJECT_ROOT, HERE / 'START-APPROVAL.json'))
    assert approval['approved'] is True and approval['formal_release'] is False
    assert approval['driver_sha256'] == hashes()
    assert approval['identity'] == value
    return value


def publish(state):
    """公共状态不含 Token；UTC 墙上时钟仅用于审计关联。"""
    h.write(_project_file(_PROJECT_ROOT, HERE / 'STATUS.json'), {**state, 'updated_at_utc': h.now(),
        'controller_pid': os.getpid(), 'driver': DRIVER.name,
        'test_room_enabled': False, 'formal_release': False, 'strength_admission': False})


def verify_free(directory, plan):
    """有界验证真实自然终态、十桌终分、冻结身份和审计资源。

    错误计数是诊断事实，不与 live_processes 等当前资源计数混淆；本入口
    用于已授权实验自由赛，允许保留降级告警继续累积，不授全评分门。
    全字节 CRC、规则复核和完整评分仍由后台做，不阻塞匹配。
    """
    assert h.load(directory / 'FREE-CHILD-TERMINAL.json')['actual_exit_code'] == 0
    terminals = a.end_records(directory / 'FREE-STDOUT-STDERR.log', 'free')
    assert len(terminals) == 1 and terminals[0]['terminal_reason'] == 'tournament_finished'
    terminal = terminals[0]
    assert terminal['audit_degraded'] is False
    runs = list((_project_file(_PROJECT_ROOT, ROOT / plan['free_session'] / 'audit/runs')).glob('*'))
    assert len(runs) == 1 and runs[0].name == terminal['run_id']
    run = runs[0]
    summary, manifest = h.load(run / 'summary.json'), h.load(run / 'manifest.json')['payload']
    assert summary['run_id'] == run.name and summary['audit_degraded'] is False
    for key in ('dropped_low_priority', 'missing_high_priority', 'serialization_failures', 'write_failures'):
        assert summary[key] == 0, '原始审计缺口：' + key
    assert summary['raw_retention']['dropped'] == 0 and summary['raw_retention']['emitted_attempts'] > 0
    assert all(n.written_path_present(run, p, summary) for p in summary['written_by_path'])
    frozen = plan['identity']
    assert manifest['policy_version'] == frozen['free_strategy']
    assert manifest['policy_release']['release_package_id'] == frozen['package_ids']['free']
    assert manifest['policy_release']['hand_math'] == frozen['hand_math']
    for key, expected in frozen['hand_math'].items():
        assert manifest['hand_math'][key] == expected or (key == 'native_sha256' and manifest['hand_math'][key] == '[REDACTED]')
    assert manifest['sse_effective'] is True and manifest['discard_pacing_enabled'] is False
    assert manifest['max_games'] == 10 and manifest['rounds_per_game'] == 8
    compute = terminal['decision_compute']
    assert compute['closed'] is True
    for key in ('active', 'current', 'live_processes', 'owned', 'pending', 'ready',
                'transport_inflight', 'transport_threads_alive', 'late_reap_inflight', 'late_reap_threads_alive'):
        assert compute[key] == 0, '资源未回收：' + key
    owners = list((run / 'participants').glob('u_*'))
    assert len(owners) == 1
    files = sorted((owners[0] / 'games').glob('*.jsonl'))
    assert len(files) == 10
    finals = [n.tail_finished(p) for p in files]
    rooms = {r['game_id'].split('_r', 1)[0] for r in finals}
    assert len(rooms) == 1
    diagnostics = {k: compute[k] for k in ('faults', 'policy_failures', 'restarts', 'discarded')}
    return {'run_id': run.name, 'room_id': rooms.pop(), 'unique_tables': 10,
            'game_finished': finals, 'compute_diagnostics': diagnostics,
            'summary_sha256': hashlib.sha256((run / 'summary.json').read_bytes()).hexdigest(),
            'manifest_sha256': hashlib.sha256((run / 'manifest.json').read_bytes()).hexdigest(),
            'raw_byte_integrity_pending_postgame': True, 'full_score_gate_not_granted': True}


def prepare(number, frozen):
    """每房使用新审计目录；不建测试房，不自行执行匹配 POST。"""
    directory = _project_file(_PROJECT_ROOT, HERE / ('batch-%03d' % number))
    directory.mkdir()
    private = _project_file(_PROJECT_ROOT, PRIVATE / directory.name)
    private.mkdir(mode=0o700)
    session = _project_file(_PROJECT_ROOT, ROOT / 'artifacts/sessions' / ('t170-%s-free' % directory.name))
    assert not session.exists()
    template = frozen['free_strategy'].replace('_', '-').replace('-free-v', '-v')
    config = h.load(_project_file(_PROJECT_ROOT, ROOT / 'configs' / (template + '.free-match.example.json')))
    config.pop('token_env', None)
    config['audit_root'] = str(session / 'audit')
    config['discard_pacing_enabled'] = False
    assert config['expected_tournament_id'] is None
    assert config['base_url'] == 'https://%s:18080' % h.HOST and config['sse_enabled'] is True
    h.write(private / 'free.json', config, exclusive=True)
    from scripts.run_auto_match import load_config
    runtime, settings = load_config(private / 'free.json', token_file=str(h.TOKEN))
    assert runtime.expected_policy_release_id == frozen['package_ids']['free']
    assert settings.declared_max_games == 10 and settings.declared_rounds == 8
    plan = {'batch': number, 'created_at_utc': h.now(), 'identity': frozen,
            'free_session': str(session.relative_to(ROOT)), 'test_room_enabled': False,
            'strength_admission': False, 'formal_release': False}
    h.write(directory / 'PLAN.json', plan, exclusive=True)
    return directory, private, plan


def run_free(number, frozen, owner_fd):
    """子进程继承 owner 锁，即使父进程崩溃也不能启动第二个 Token owner。"""
    directory, private, plan = prepare(number, frozen)
    with (directory / 'FREE-STDOUT-STDERR.log').open('x') as stream:
        child = subprocess.Popen([sys.executable, 'scripts/run_auto_match.py', '--config',
            str(private / 'free.json'), '--token-file', str(h.TOKEN)], cwd=ROOT, env=h.env(),
            stdout=stream, stderr=subprocess.STDOUT, start_new_session=True, pass_fds=(owner_fd,))
        h.write(directory / 'FREE-START.json', {'at_utc': h.now(), 'pid': child.pid,
            'inherits_owner_lock': True, 'session': plan['free_session']}, exclusive=True)
        publish({'state': 'players_running', 'batch': number, 'active_children': {'free': child.pid}})
        code = child.wait()  # 只等自然终态；没有 timeout/kill/terminate。
    h.write(directory / 'FREE-CHILD-TERMINAL.json', {'at_utc': h.now(), 'actual_exit_code': code,
            'controller_sent_termination_signal': False}, exclusive=True)
    verified = verify_free(directory, plan)
    assert preflight() == frozen
    h.write(directory / 'RUN-CLOSED.json', {'at_utc': h.now(), 'run_safety_verified': True,
            'free': verified, 'driver_sha256': hashes(), 'strength_admission': False}, exclusive=True)
    publish({'state': 'run_closed_postprocess_queued', 'batch': number, 'active_children': {}})


def prior_closed():
    """拒绝本入口未知旧房；历史测试房失败无需伪造为通过。"""
    prior = []
    for directory in sorted(HERE.glob('batch-*')):
        assert h.load(directory / 'RUN-CLOSED.json')['run_safety_verified'] is True
        verify_free(directory, h.load(directory / 'PLAN.json'))
        prior.append(h.load(directory / 'PLAN.json')['batch'])
    return prior


def watch():
    """一直自动续自由赛；独立后台的速度、失败或测试房状态不阻塞续房。"""
    PRIVATE.mkdir(mode=0o700, exist_ok=True)
    stop = [False]
    signal.signal(signal.SIGINT, lambda *_: stop.__setitem__(0, True))
    signal.signal(signal.SIGTERM, lambda *_: stop.__setitem__(0, True))
    with OWNER_LOCK.open('a+') as owner:
        while not stop[0] and h.load(CONTROL)['continue_after_cycle']:
            try:
                fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                publish({'state': 'waiting_existing_owner_natural_finish', 'active_children': {}})
                time.sleep(2)
        else:
            return
        try:
            assert not h.other_players(), '真实玩家仍活，不启动第二个 owner'
            transfer = h.load(_project_file(_PROJECT_ROOT, HERE / 'TRANSFER.json'))
            predecessor = _project_file(_PROJECT_ROOT, ROOT / transfer['directory'])
            verify_free(predecessor, h.load(predecessor / 'PLAN.json'))
            preflight()
            # 后台不拿 Token，不持 owner 锁；只允许一个共用 postprocess 锁。
            with (_project_file(_PROJECT_ROOT, PRIVATE / 'background.stdout.log')).open('a') as stream:
                subprocess.Popen([sys.executable, str(DRIVER), 'worker'], cwd=ROOT, env=h.env(),
                    stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
            prior = prior_closed()
            number = 1 + max(prior, default=0)
            while not stop[0] and h.load(CONTROL)['continue_after_cycle']:
                assert not h.other_players()
                assert shutil.disk_usage(ROOT).free >= h.load(CONTROL)['minimum_free_bytes'], '原始审计磁盘余量不足'
                frozen = preflight()
                run_free(number, frozen, owner.fileno())
                number += 1
            publish({'state': 'stopped_after_natural_finish', 'active_children': {}})
        except Exception as error:
            publish({'state': 'blocked_new_rooms', 'active_children': {},
                     'reason': type(error).__name__ + ': ' + str(error)})
            raise


def pending():
    """后台失败不自动覆盖，已关闭的自由赛排队一次。"""
    return [p for p in sorted(HERE.glob('batch-*')) if (p / 'RUN-CLOSED.json').exists()
            and not (p / 'POSTPROCESS-START.json').exists()]


def postprocess(directory, lock_fd):
    """只处理已经自然完成的房；官方规则缺信息保持未知，不补造默认规则。"""
    h.write(directory / 'POSTPROCESS-START.json', {'at_utc': h.now(), 'worker_pid': os.getpid()}, exclusive=True)
    plan = h.load(directory / 'PLAN.json')
    failures = []
    try:
        session = _project_file(_PROJECT_ROOT, ROOT / plan['free_session'])
        config = h.load(_project_file(_PROJECT_ROOT, PRIVATE / directory.name / 'free.json'))
        h.capture(session, config, h.free_room(session), directory / 'free-capture')
        code = n.run_postprocess_step(directory, 'FREE-POSTGAME',
            [sys.executable, 'scripts/audit_tool.py', 'postgame', plan['free_session']],
            directory / 'FREE-POSTGAME.log', lock_fd)
        assert code == 0, 'postgame退出非0，保留原失败'
        code = n.run_postprocess_step(directory, 'ANALYSIS',
            [sys.executable, str(DRIVER), 'analyze', '--batch', str(plan['batch'])],
            directory / 'BACKGROUND-ANALYSIS.log', lock_fd)
        assert code == 0, '分析退出非0，保留原失败'
    except Exception as error:
        failures.append({'error': type(error).__name__ + ': ' + str(error)})
    h.write(directory / 'POSTPROCESS-CLOSED.json', {'at_utc': h.now(), 'failures': failures,
            'does_not_block_next_match': True}, exclusive=True)


def worker():
    """与旧后台共用独占锁；单次重任务低优先级，不压缩正在参赛的原件。"""
    singleton = (_project_file(_PROJECT_ROOT, PRIVATE / 'worker.lock')).open('a+')
    try:
        fcntl.flock(singleton, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        singleton.close()
        return
    os.nice(15)
    priority = subprocess.run(['taskpolicy', '-b', '-p', str(os.getpid())], capture_output=True)
    assert priority.returncode == 0, '后台 IO 优先级未确认，停止后台而不停止参赛'
    with POSTPROCESS_LOCK.open('a+') as lock:
        while True:
            control = h.load(CONTROL)
            jobs = pending()
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except BlockingIOError:
                acquired = False
            h.write(_project_file(_PROJECT_ROOT, HERE / 'BACKGROUND-STATUS.json'), {'at_utc': h.now(), 'worker_pid': os.getpid(),
                'state': 'waiting' if acquired else 'waiting_existing_postprocess',
                'cpu_nice': os.nice(0), 'io_priority_actual_exit_code': priority.returncode,
                'pending_batches': [p.name for p in jobs]})
            if acquired and control['background_enabled'] and jobs:
                preflight()
                h.write(_project_file(_PROJECT_ROOT, HERE / 'BACKGROUND-STATUS.json'), {'at_utc': h.now(), 'worker_pid': os.getpid(),
                    'state': 'processing', 'batch': jobs[0].name, 'cpu_nice': os.nice(0),
                    'io_priority_actual_exit_code': priority.returncode})
                postprocess(jobs[0], lock.fileno())
            if acquired:
                fcntl.flock(lock, fcntl.LOCK_UN)
            time.sleep(5)


def status():
    """实际核控制器、当前玩家和单后台，不能只凭旧 PID 推断正在比赛。"""
    state = h.load(_project_file(_PROJECT_ROOT, HERE / 'STATUS.json'))
    state['controller_process_now'] = h.process_identity(state.get('controller_pid'), DRIVER.name + ' watch')
    state['active_children_now'] = {key: h.process_identity(pid, 'run_auto_match.py')
        for key, pid in state.get('active_children', {}).items()}
    if state['state'] == 'waiting_existing_owner_natural_finish':
        predecessor = _project_file(_PROJECT_ROOT, ROOT / h.load(HERE / 'TRANSFER.json')['directory'])
        start = h.load(predecessor / 'FREE-START.json')
        state['predecessor_player_now'] = h.process_identity(start['pid'], 'run_auto_match.py')
    if (_project_file(_PROJECT_ROOT, HERE / 'BACKGROUND-STATUS.json')).exists():
        state['background'] = h.load(_project_file(_PROJECT_ROOT, HERE / 'BACKGROUND-STATUS.json'))
        state['background']['worker_process_now'] = h.process_identity(state['background'].get('worker_pid'), DRIVER.name + ' worker')
    state['control'] = h.load(CONTROL)
    print(json.dumps(state, ensure_ascii=False, indent=2))


def main():
    """watch/worker 为运行入口；preflight/status 只读，analyze 仅已闭合房。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('watch', 'worker', 'preflight', 'status', 'analyze'))
    parser.add_argument('--batch', type=int)
    args = parser.parse_args()
    if args.command == 'analyze':
        assert args.batch is not None
        directory = _project_file(_PROJECT_ROOT, HERE / ('batch-%03d' % args.batch))
        h.write(directory / 'SUMMARY.json', a.analyze_lane(directory, h.load(directory / 'PLAN.json'), 'free'), exclusive=True)
    elif args.command == 'preflight':
        print(json.dumps({'identity': preflight(), 'driver_sha256': hashes(), 'new_http_calls': 0}, ensure_ascii=False))
    else:
        globals()[args.command]()


if __name__ == '__main__':
    main()
