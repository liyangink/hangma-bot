"""原玩家自然终态后迁移已验收源码，启动唯一新自由赛owner；不终止玩家。"""

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

ROOT = _PROJECT_ROOT
HERE = Path(__file__).resolve().parent
WORK = _project_file(_PROJECT_ROOT, '.private/t179-wiring/workspace')
OLD = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t170-free-only-watchdog-1')


def load(path):
    return json.loads(path.read_text())


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def main():
    assert load(_project_file(_PROJECT_ROOT, HERE / 'REAL-FACTORY-RESULT-001.json'))['all_original_deadlines_and_scores_exact']
    assert load(_project_file(_PROJECT_ROOT, HERE / 'official-verification-001/CLOSED.json'))['actual_exit_code'] == 0
    state = load(_project_file(_PROJECT_ROOT, OLD / 'STATUS.json'))
    assert state['state'] == 'stopped_after_natural_finish'
    requested = load(_project_file(_PROJECT_ROOT, HERE / 'NATURAL-TRANSFER-REQUEST.json'))['predecessor']
    assert state['controller_pid'] == requested['controller_pid']
    batch = requested['batch']
    assert batch == max(int(p.name.split('-')[1]) for p in OLD.glob('batch-*'))
    predecessor = _project_file(_PROJECT_ROOT, OLD / ('batch-%03d' % batch))
    assert load(predecessor / 'RUN-CLOSED.json')['run_safety_verified'] is True
    assert not load(_project_file(_PROJECT_ROOT, ROOT / '.private/t170-free-watchdog/control.json'))['continue_after_cycle']
    assert not load(_project_file(_PROJECT_ROOT, ROOT / '.private/t170-free-watchdog/control.json'))['background_enabled']
    spec = importlib.util.spec_from_file_location('t179_activation_helpers', _project_file(_PROJECT_ROOT, HERE / 'free_watchdog.py'))
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    assert not driver.h.process_identity(state['controller_pid'], str(_project_file(_PROJECT_ROOT, OLD / 'free_watchdog.py')) + ' watch')['pid_exists']
    player = load(predecessor / 'FREE-START.json')['pid']
    assert not driver.h.process_identity(player, 'run_auto_match.py')['pid_exists']
    assert not driver.h.other_players(), '仍有真实玩家；拒绝修改生产源码'
    prior = driver.verify_free(predecessor, load(predecessor / 'PLAN.json'))
    import hangma_bot.bootstrap as old_bootstrap
    old_package = old_bootstrap._load_vip_free_manifest()
    assert old_package['strategy'] == 'vip_s02_bounded_d1_free_v5'

    with driver.OWNER_LOCK.open('a+') as owner, driver.POSTPROCESS_LOCK.open('a+') as post:
        fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(post, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # 前任后台已经停接新统计，且没有持锁子任务。仅清理这个闲置统计器，
        # 不向控制器、玩家或计算子进程发送任何信号。
        background = load(_project_file(_PROJECT_ROOT, OLD / 'BACKGROUND-STATUS.json'))
        assert background['state'] in ('waiting', 'waiting_existing_postprocess')
        worker = background['worker_pid']
        identity = driver.h.process_identity(worker, str(_project_file(_PROJECT_ROOT, OLD / 'free_watchdog.py')) + ' worker')
        if identity['pid_exists']:
            assert identity['expected_command_live']
            os.kill(worker, signal.SIGTERM)
            for _ in range(50):
                if not driver.h.process_identity(worker, str(_project_file(_PROJECT_ROOT, OLD / 'free_watchdog.py')) + ' worker')['pid_exists']:
                    break
                time.sleep(.1)
            else:
                raise RuntimeError('闲置前任统计器未退出；保留旧生产源码')

        expected = load(_project_file(_PROJECT_ROOT, HERE / 'REGRESSION-CLOSED.json'))['source_manifest']
        changed = [name for name, digest in expected.items()
                   if not (_project_file(_PROJECT_ROOT, ROOT / name)).exists() or hashlib.sha256((_project_file(_PROJECT_ROOT, ROOT / name)).read_bytes()).hexdigest() != digest]
        tests = [str(p.relative_to(WORK)) for p in (_project_file(_PROJECT_ROOT, WORK / 'tests')).rglob('*.py')
                 if not (_project_file(_PROJECT_ROOT, ROOT / p.relative_to(WORK))).exists()
                 or p.read_bytes() != (_project_file(_PROJECT_ROOT, ROOT / p.relative_to(WORK))).read_bytes()]
        artifacts = ['prebuilt/vip-s02-bounded-d1-testroom-v8/manifest.json',
                     'prebuilt/vip-s02-bounded-d1-free-v6/manifest.json',
                     'configs/vip-s02-bounded-d1-v8.test-room.example.json',
                     'configs/vip-s02-bounded-d1-v6.free-match.example.json']
        artifacts += [str(p.relative_to(WORK)) for p in
                      (_project_file(_PROJECT_ROOT, WORK / 'prebuilt/vip-s02-compiled-runtime-v1')).iterdir() if p.is_file()]
        save(_project_file(_PROJECT_ROOT, HERE / 'ACTIVATION-START.json'), {'at_unix': time.time(), 'predecessor': prior,
            'source_files': changed, 'test_files': tests, 'artifact_files': artifacts,
            'official_players_terminated': False, 'idle_old_stat_worker': worker})
        backup = _project_file(_PROJECT_ROOT, ROOT / '.private/t179-wiring/production-before-cutover')
        backup.mkdir(exist_ok=False)
        for name in changed + tests + artifacts:
            original = _project_file(_PROJECT_ROOT, ROOT / name)
            if original.exists():
                target = backup / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(original, target)
            original.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(_project_file(_PROJECT_ROOT, WORK / name), original)
        for name, digest in expected.items():
            assert hashlib.sha256((_project_file(_PROJECT_ROOT, ROOT / name)).read_bytes()).hexdigest() == digest
        # 新解释器复核，不复用迁移前已import的模块。
        check = subprocess.run([sys.executable, '-c',
            'import json; import hangma_bot.bootstrap as b; '
            'print(json.dumps({"free":b._load_vip_free_manifest()["release_package_id"],'
            '"testroom":b._load_vip_testroom_manifest()["release_package_id"]}))'],
            cwd=ROOT, env=driver.h.env(), capture_output=True, text=True)
        assert check.returncode == 0, check.stderr
        assert json.loads(check.stdout) == load(_project_file(_PROJECT_ROOT, HERE / 'FROZEN-PACKAGES.json'))['package_ids']
        save(_project_file(_PROJECT_ROOT, HERE / 'TRANSFER.json'), {'directory': str(predecessor.relative_to(ROOT)),
            'old_run_closed_sha256': hashlib.sha256((predecessor / 'RUN-CLOSED.json').read_bytes()).hexdigest(),
            'old_player_pid': player, 'old_controller_pid': state['controller_pid'],
            'predecessor_unstarted_postprocess_adopted': True, 'players_natural_end_only': True})
        code = ('import importlib.util,json; from pathlib import Path; '
                'p=Path(' + repr(str(_project_file(_PROJECT_ROOT, HERE / 'free_watchdog.py'))) + '); '
                's=importlib.util.spec_from_file_location("new_driver",p); '
                'm=importlib.util.module_from_spec(s);s.loader.exec_module(m); '
                'print(json.dumps({"identity":m.identity(),"driver_sha256":m.hashes()}))')
        result = subprocess.run([sys.executable, '-c', code], cwd=ROOT, env=driver.h.env(),
                                capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        approval = json.loads(result.stdout)
        save(_project_file(_PROJECT_ROOT, HERE / 'START-APPROVAL.json'), {**approval, 'approved': True,
            'formal_release': False, 'strength_admission': False,
            'authorization': '用户已授权测试房、实验自由赛及本次完成接线和独立计算调整',
            'at_unix': time.time()})
        private = _project_file(_PROJECT_ROOT, ROOT / '.private/t179-free-watchdog')
        private.mkdir(mode=0o700, exist_ok=True)
        save(private / 'control.json', {'continue_after_cycle': True, 'background_enabled': True,
            'minimum_free_bytes': 8589934592})
        with (private / 'controller.stdout.log').open('a') as stream:
            controller = subprocess.Popen([sys.executable, '-u', str(_project_file(_PROJECT_ROOT, HERE / 'free_watchdog.py')), 'watch'],
                cwd=ROOT, env=driver.h.env(), stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        save(_project_file(_PROJECT_ROOT, HERE / 'ACTIVATION-CLOSED.json'), {'actual_exit_code': 0,
            'source_manifest_exact': True, 'controller_pid': controller.pid,
            'package_ids': approval['identity']['package_ids'], 'at_unix': time.time(),
            'official_players_terminated': False, 'new_owner_started_after_natural_completion': True})
        print(json.dumps({'controller_pid': controller.pid, 'source_files_copied': len(changed),
            'strategy': approval['identity']['free_strategy']}), flush=True)


if __name__ == '__main__':
    main()
