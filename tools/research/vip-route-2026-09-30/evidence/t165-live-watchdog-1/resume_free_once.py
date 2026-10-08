"""混合通道待诊断时，独占同锁接续一房自由赛；只等自然退出。"""
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

import fcntl
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('t165_nonblocking_read_helpers', _project_file(_PROJECT_ROOT, HERE / 'watchdog_nonblocking.py'))
n = importlib.util.module_from_spec(spec)
spec.loader.exec_module(n)
h = n.h


def main():
    """核第四批自由赛硬保护，启动同一冻结包，混合原失败不改。"""
    with (h.PRIVATE / 'controller.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert not h.other_players(), '存在官方玩家或旧owner，拒绝重复接续'
        identity = n.approved_preflight()
        prior = _project_file(_PROJECT_ROOT, HERE / 'cycle-004')
        plan = h.load(prior / 'PLAN.json')
        closed_free = n.verify_lane(prior, plan, 'free')
        assert closed_free['unique_tables'] == 10
        control = h.load(h.PRIVATE / 'control.json')
        assert control['continue_after_cycle'] is True
        directory = _project_file(_PROJECT_ROOT, HERE / 'free-independent-005')
        directory.mkdir(exist_ok=False)
        config_path = h.PRIVATE / 'free-independent-005.json'
        config = h.load(h.PRIVATE / 'cycle-004/free.json')
        session = h.ROOT / 'artifacts/sessions/t165-free-independent-005'
        config['audit_root'] = str(session / 'audit')
        with config_path.open('x') as stream:
            json.dump(config, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        os.chmod(config_path, 0o600)
        h.write(directory / 'PLAN.json', {'at_utc': h.now(),
            'identity': identity, 'free_session': str(session.relative_to(h.ROOT)),
            'strategy': config['strategy'], 'expected_policy_release_id': config['expected_policy_release_id'],
            'previous_free_run_safety_verified': closed_free,
            'mixed_failure_not_waived': True, 'new_test_room_started': False,
            'root_authorization': '本次用户要求自由赛持续自动续、无必要不续测试；root明确委派独立free一次接续',
            'player_termination_allowed': False, 'strength_admission': False}, exclusive=True)
        signal.signal(signal.SIGINT, lambda *_: None)
        signal.signal(signal.SIGTERM, lambda *_: None)
        command = [sys.executable, 'scripts/run_auto_match.py', '--config', str(config_path),
                   '--token-file', str(h.TOKEN)]
        with (directory / 'FREE-STDOUT-STDERR.log').open('x') as stream:
            child = subprocess.Popen(command, cwd=h.ROOT, env=h.env(), stdout=stream,
                stderr=subprocess.STDOUT, start_new_session=True, pass_fds=(lock.fileno(),))
            h.write(directory / 'FREE-START.json', {'at_utc': h.now(), 'wrapper_pid': os.getpid(),
                'pid': child.pid, 'session': str(session.relative_to(h.ROOT)),
                'inherits_controller_lock': True, 'config_kept_private': True,
                'previous_mixed_failure_retained': True}, exclusive=True)
            print(json.dumps({'started': True, 'wrapper_pid': os.getpid(), 'free_pid': child.pid,
                              'session': str(session.relative_to(h.ROOT))}), flush=True)
            code = child.wait()
        h.write(directory / 'FREE-CHILD-TERMINAL.json', {'at_utc': h.now(),
            'actual_exit_code': code, 'controller_sent_termination_signal': False}, exclusive=True)
        print(json.dumps({'natural_exit_code': code}), flush=True)


if __name__ == '__main__':
    main()
