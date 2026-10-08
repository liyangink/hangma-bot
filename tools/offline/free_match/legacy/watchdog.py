"""T165 隔离实战监督器：两路自然完赛、及时采集、空闲期分析后续开。

只调用现有官方运行/采集/赛后入口，不实现牌型规则。凭证仅驻留私有目录；
没有对子进程的 timeout、terminate 或 kill。根审核收据、冻结身份和独占锁
必须同时成立才能开房。status/preflight 均不发送 HTTP。
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
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = _PROJECT_ROOT
HERE = Path(__file__).resolve().parent
PRIVATE = _project_file(_PROJECT_ROOT, '.private/t165-live-watchdog')
TOKEN = _project_file(_PROJECT_ROOT, ROOT / 'token/global/全局自由赛token')
HOST = '10.240.169.190'
SLOTS = ('qinglong', 'baihu', 'zhuque', 'xuanwu')
R18 = 'r18_v2_current_rules_testroom_20261004'
sys.path[:0] = [str(ROOT), str(_project_file(_PROJECT_ROOT, ROOT / 'src'))]


def now():
    """UTC 墙上时钟用于人读收据；耗时只用单调时钟。"""
    return datetime.now(timezone.utc).isoformat()


def load(path):
    """读取指定 JSON；缺文件不猜旧状态。"""
    return json.loads(path.read_text())


def write(path, value, *, exclusive=False):
    """原子更新状态，或独占写原始收据；不覆盖历史收据。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    if exclusive:
        with path.open('x') as stream:
            if PRIVATE in path.parents:
                os.fchmod(stream.fileno(), 0o600)
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
    else:
        temporary = path.with_name(path.name + '.tmp')
        with temporary.open('w') as stream:
            if PRIVATE in path.parents:
                os.fchmod(stream.fileno(), 0o600)
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
        temporary.replace(path)


def pid_alive(pid):
    """只探测已有 PID 是否存在；不凭账本把任务当成活跃。"""
    if type(pid) is not int or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def process_identity(pid, expected):
    """只读 PID 当前命令，排除历史 PID 已被别的程序复用；权限失败保持未知。"""
    if not pid_alive(pid):
        return {'pid_exists': False, 'expected_command_live': False, 'status': 'pid_absent'}
    result = subprocess.run(['ps', '-p', str(pid), '-o', 'command='], capture_output=True, text=True)
    if result.returncode:
        return {'pid_exists': True, 'expected_command_live': None, 'status': 'command_check_unavailable'}
    matches = expected in result.stdout
    return {'pid_exists': True, 'expected_command_live': matches,
            'status': 'expected_process_confirmed' if matches else 'pid_reused_or_unexpected_command'}


def preflight(require_review=False):
    """实际装配三身份，拒绝旧规则、模式扩大、缺数学后端或审核失配。"""
    import hangma_bot.bootstrap as b
    free = b._load_vip_manifest(b.VIP_S02_FREE_STRATEGY, None)
    test = b._load_vip_testroom_manifest()
    if R18 not in b.AVAILABLE_STRATEGIES:
        raise RuntimeError('R18 当前规则 test_room 专用实验包尚未合入')
    policy = b._STRATEGY_FACTORIES[R18]()
    r18 = dict(policy.release_metadata)
    assert list(r18['allowed_modes']) == ['test_room']
    assert r18.get('strength_admission') is False and r18.get('production_default') is False
    ids = {'free': free['release_package_id'], 'mixed_t110': test['release_package_id'],
           'mixed_r18': r18['release_package_id']}
    if require_review:
        approval = load(_project_file(_PROJECT_ROOT, HERE / 'ROOT-START-APPROVAL.json'))
        assert approval.get('approved') is True and approval.get('package_ids') == ids, '根审核身份不匹配'
        assert approval.get('formal_release') is False
    return {'package_ids': ids, 'free_strategy': b.VIP_S02_FREE_STRATEGY,
            'test_strategy': b.VIP_S02_TESTROOM_STRATEGY, 'r18_strategy': R18,
            'rules_source_hash': b.compute_rules_hash(ROOT), 'hand_math': b.hand_math_runtime_metadata()}


def other_players():
    """读取实际进程命令，仅返回 PID；系统权限失败时拒绝猜无 owner。"""
    result = subprocess.run(['ps', '-Ao', 'pid=,command='], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError('无法核对实际参赛进程；不能假定 Token 无 owner')
    rows = []
    for line in result.stdout.splitlines():
        bits = line.strip().split(None, 1)
        if len(bits) != 2:
            continue
        command = bits[1]
        # 只看真实 Python 启动脚本，避免把 shell 读代码命令误判成玩家。
        if 'python' in command.split()[0].lower() and (
            '/run_auto_match.py ' in command or ' scripts/run_auto_match.py ' in command
            or '/run_test_room.py ' in command or ' scripts/run_test_room.py ' in command
            or '/run_participant.py ' in command or ' scripts/run_participant.py ' in command):
            rows.append(int(bits[0]))
    return rows


class PublicClient:
    """公开档案 GET 降频与有界 429 恢复；逐尝试保留真实原件。"""
    def __init__(self, client, out):
        self.client, self.out, self.previous, self.number = client, out, None, 0

    def get(self, endpoint):
        for attempt in range(1, 5):
            if self.previous is not None:
                time.sleep(max(0, self.previous + 2 - time.monotonic()))
            self.previous = time.monotonic()
            self.number += 1
            response = self.client.get(endpoint)
            name = 'capture-%03d.bin' % self.number
            (self.out / name).write_bytes(response.content)
            with (self.out / 'CAPTURE-ACTUAL-HTTP.jsonl').open('a') as stream:
                stream.write(json.dumps({'at_utc': now(), 'endpoint': endpoint, 'attempt': attempt,
                    'http_status': response.status_code, 'body_file': name,
                    'body_sha256': hashlib.sha256(response.content).hexdigest(),
                    'elapsed_seconds': time.monotonic() - self.previous}, ensure_ascii=False) + '\n')
            if response.status_code != 429:
                return response
            if attempt < 4:
                try:
                    delay = max(2, float(response.headers.get('retry-after', '2')))
                except ValueError:
                    delay = 2
                time.sleep(min(delay, 60))
        return response


def env():
    """只为赛事内网增加当前子进程代理例外，不改变系统代理。"""
    values = dict(os.environ)
    for key in ('NO_PROXY', 'no_proxy'):
        values[key] = ','.join(filter(None, (values.get(key, ''), HOST)))
    return values


def prepare_cycle(number, identity):
    """新批次独占配置与建房收据；POST 一次，未知结果不自动重试。"""
    import httpx
    from scripts.test_room_campaign_watchdog import portal_cookie
    directory = _project_file(_PROJECT_ROOT, HERE / ('cycle-%03d' % number))
    directory.mkdir()
    private = _project_file(_PROJECT_ROOT, PRIVATE / directory.name)
    private.mkdir(mode=0o700)
    free_session = _project_file(_PROJECT_ROOT, ROOT / 'artifacts/sessions' / ('t165-%s-free' % directory.name))
    mixed_session = _project_file(_PROJECT_ROOT, ROOT / 'artifacts/sessions' / ('t165-%s-mixed' % directory.name))
    assert not free_session.exists() and not mixed_session.exists()
    template = identity['free_strategy'].replace('_', '-').replace('-free-v', '-v')
    free = load(_project_file(_PROJECT_ROOT, ROOT / 'configs' / (template + '.free-match.example.json')))
    # 文件名优先由准确版本常量对应模板；不读历史 local 配置。
    free.pop('token_env', None)
    free['audit_root'] = str(free_session / 'audit')
    free['discard_pacing_enabled'] = False
    assert free['base_url'] == 'https://%s:18080' % HOST and free['sse_enabled'] is True
    assert free['expected_policy_release_id'] == identity['package_ids']['free']
    write(private / 'free.json', free, exclusive=True)
    from scripts.run_auto_match import load_config
    runtime, settings = load_config(private / 'free.json', token_file=str(TOKEN))
    assert runtime.expected_policy_release_id == identity['package_ids']['free']
    assert settings.declared_max_games == 10 and settings.declared_rounds == 8
    payload = {'m': 10, 'rounds': 8, 'base_score': 1, 'you_cai_bi_kao': False,
               'peng_timeout_sec': 1, 'chi_timeout_sec': 1, 'discard_timeout_sec': 3, 'timeout_min': 30}
    with httpx.Client(verify=False, trust_env=False, timeout=40,
                      headers={'Cookie': portal_cookie()}) as client:
        response = client.post('https://%s:18080/portal/api/test-rooms' % HOST, json=payload)
        raw = private / 'create-response.bin'
        raw.write_bytes(response.content)
        raw.chmod(0o600)
        write(directory / 'CREATE-HTTP-RECEIPT.json', {'at_utc': now(), 'http_status': response.status_code,
              'raw_sha256': hashlib.sha256(response.content).hexdigest(), 'raw_kept_private': True}, exclusive=True)
        assert response.status_code == 200, '建房非200；私有原件保留，不重复POST'
        room = response.json()
    assert room['room_id'].startswith('t_') and len(room['players']) == 4
    identities, slot_arms = [], {}
    t110_slots = {SLOTS[0], SLOTS[2]} if number % 2 else {SLOTS[1], SLOTS[3]}
    for slot, player in zip(SLOTS, room['players']):
        path = private / (slot + '.token')
        with path.open('x') as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(player['token'].strip() + '\n')
        arm = 'T110' if slot in t110_slots else 'R18'
        identities.append({'slot': slot, 'token_file': str(path),
            'strategy': identity['test_strategy'] if arm == 'T110' else R18,
            'expected_policy_release_id': identity['package_ids']['mixed_t110' if arm == 'T110' else 'mixed_r18']})
        # 门户建房响应只有name/token，不能假定存在user_id或按昵称归因。
        # 身份由已闭合的每个slot审计目录读取，再与官方seats逐桌核对。
        slot_arms[slot] = arm
    mixed = {'mode': 'test_room', 'base_url': 'https://%s:18080' % HOST,
        'expected_tournament_id': room['room_id'], 'known_guide_version': 35,
        'audit_root': str(mixed_session / 'audit'), 'strategy': identity['test_strategy'],
        'insecure_hosts': [HOST], 'sse_enabled': True, 'discard_pacing_enabled': False,
        'max_completed_batches': 1, 'identities': identities, 'restart': {'max_restarts': 0}}
    write(private / 'mixed.json', mixed, exclusive=True)
    write(private / 'rules.json', {'base_score': 1, 'you_cai_bi_kao': False}, exclusive=True)
    from scripts.run_test_room import load_room_config, child_config_mapping
    import hangma_bot.bootstrap as b
    parsed = load_room_config(private / 'mixed.json')
    for seat in parsed.identities:
        data = child_config_mapping(parsed, seat)
        data.pop('token_env')
        data['token'] = 'offline-preflight-no-network'
        b.runtime_config_from_mapping(data)
    record = {'cycle': number, 'created_at_utc': now(), 'test_room_id': room['room_id'],
        'identity': identity, 'slot_arms': slot_arms, 'requested_rules': payload,
        'slot_rotation': sorted(t110_slots), 'player_termination_allowed': False,
        'unique_tables_per_lane_expected': 10, 'unique_hands_per_lane_expected': 80,
        'free_session': str(free_session.relative_to(ROOT)), 'mixed_session': str(mixed_session.relative_to(ROOT)),
        'strength_admission': False, 'formal_release': False}
    write(directory / 'PLAN.json', record, exclusive=True)
    return directory, private, record


def free_room(session):
    """从已关闭审计识别唯一房号；不会从旧账本猜测。"""
    rooms = {p.stem.split('_r', 1)[0] for p in session.glob('audit/runs/*/participants/*/games/*.jsonl')}
    assert len(rooms) == 1
    return next(iter(rooms))


def mixed_owners(session, slot_arms):
    """由自然关闭的逐槽位审计识别身份，不增发 /api/me 或凭昵称归因。"""
    mapping = {}
    for slot in SLOTS:
        runs = list((session / 'audit' / ('slot-' + slot) / 'runs').glob('*'))
        assert len(runs) == 1 and (runs[0] / 'summary.json').is_file()
        owners = [p.name for p in (runs[0] / 'participants').glob('u_*') if p.is_dir()]
        assert len(owners) == 1 and owners[0] not in mapping
        mapping[owners[0]] = {'slot': slot, 'arm': slot_arms[slot],
            'audit_source': str(runs[0].relative_to(ROOT))}
    return mapping


def capture(session, config, room, out):
    """一批自然结束后，及时下载十桌；后续开房必须等采集完成。"""
    from hangma_bot.bootstrap import build_public_archive_client
    from hangma_bot.adapters.official.archive_download import collect_test_room
    out.mkdir()
    results = []
    with build_public_archive_client(config) as client:
        wrapped = PublicClient(client, out)
        for batch in range(10):
            time.sleep(2)
            results.append(collect_test_room(wrapped, room, batch, session))
    write(out / 'CAPTURE.json', {'room_id': room, 'ten_tables': results}, exclusive=True)


def publish_status(state):
    """私有运行态和公共摘要一致更新；不包含凭证。"""
    state = {**state, 'updated_at_utc': now(), 'controller_pid': os.getpid(),
             'formal_release': False, 'strength_admission': False}
    write(_project_file(_PROJECT_ROOT, PRIVATE / 'state.json'), state)
    write(_project_file(_PROJECT_ROOT, HERE / 'STATUS.json'), state)


def one_cycle(number, identity):
    """同时运行两路；所有玩家自然终态后才做耗 CPU 的赛后封存。"""
    directory, private, plan = prepare_cycle(number, identity)
    lanes = {}
    for lane in ('free', 'mixed'):
        session = _project_file(_PROJECT_ROOT, ROOT / plan[lane + '_session'])
        command = [sys.executable, 'scripts/run_auto_match.py' if lane == 'free' else 'scripts/run_test_room.py',
                   '--config', str(private / (lane + '.json'))]
        command += ['--token-file', str(TOKEN)] if lane == 'free' else ['--once']
        logfile = (directory / (lane.upper() + '-STDOUT-STDERR.log')).open('x')
        # 玩家独立进程组；父handler只能挡父进程信号，不能挡终端对同组的广播。
        process = subprocess.Popen(command, cwd=ROOT, env=env(), stdout=logfile,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        lanes[lane] = {'process': process, 'logfile': logfile, 'session': session, 'captured': False}
        write(directory / (lane.upper() + '-START.json'), {'at_utc': now(), 'pid': process.pid,
            'session': plan[lane + '_session'], 'config_kept_private': True}, exclusive=True)
        # 每个真正创建的子进程立即落状态，第二路启动失败也不能漏报第一路 owner。
        publish_status({'state': 'starting_players', 'cycle': number,
            'active_children': {k: v['process'].pid for k, v in lanes.items()},
            'plan': str((directory / 'PLAN.json').relative_to(ROOT))})
    state = {'state': 'players_running', 'cycle': number, 'active_children': {k: v['process'].pid for k, v in lanes.items()},
             'plan': str((directory / 'PLAN.json').relative_to(ROOT)), 'no_heavy_research_while_players_live': True}
    publish_status(state)
    failures = []
    while any(v['process'].poll() is None or not v['captured'] for v in lanes.values()):
        for lane, job in lanes.items():
            code = job['process'].poll()
            if code is None or job['captured']:
                continue
            job['logfile'].close()
            write(directory / (lane.upper() + '-CHILD-TERMINAL.json'), {'at_utc': now(), 'actual_exit_code': code,
                'controller_sent_termination_signal': False}, exclusive=True)
            try:
                if code:
                    raise RuntimeError('参赛子进程自然退出非0: %s' % code)
                if lane == 'mixed':
                    write(directory / 'OWNER-MAP.json', mixed_owners(job['session'], plan['slot_arms']), exclusive=True)
                room = free_room(job['session']) if lane == 'free' else plan['test_room_id']
                capture(job['session'], load(private / (lane + '.json')), room, directory / (lane + '-capture'))
            except Exception as error:
                failures.append({'lane': lane, 'stage': 'capture', 'error': type(error).__name__ + ': ' + str(error)})
            job['captured'] = True
            state['active_children'] = {k: v['process'].pid for k, v in lanes.items() if v['process'].poll() is None}
            publish_status(state)
        if any(v['process'].poll() is None for v in lanes.values()):
            time.sleep(15)
    publish_status({**state, 'state': 'players_closed_postgame', 'active_children': {}})
    if not failures:
        for lane, job in lanes.items():
            with (directory / (lane.upper() + '-POSTGAME.log')).open('x') as logfile:
                result = subprocess.run([sys.executable, 'scripts/audit_tool.py', 'postgame', str(job['session']),
                    '--rule-config', str(private / 'rules.json')], cwd=ROOT, env=env(), stdout=logfile, stderr=subprocess.STDOUT)
            write(directory / (lane.upper() + '-POSTGAME-TERMINAL.json'), {'at_utc': now(), 'actual_exit_code': result.returncode}, exclusive=True)
            if result.returncode:
                failures.append({'lane': lane, 'stage': 'postgame', 'exit_code': result.returncode})
    if not failures:
        result = subprocess.run([sys.executable, str(_project_file(_PROJECT_ROOT, HERE / 'analyze.py')), '--cycle', str(directory)], cwd=ROOT, env=env())
        write(directory / 'ANALYSIS-TERMINAL.json', {'at_utc': now(), 'actual_exit_code': result.returncode}, exclusive=True)
        if result.returncode:
            failures.append({'stage': 'analysis', 'exit_code': result.returncode})
    write(directory / 'CYCLE-CLOSED.json', {'at_utc': now(), 'failures': failures,
          'controller_sent_termination_signal': False, 'strength_admission': False}, exclusive=True)
    if failures:
        raise RuntimeError('本批失败，原件保留并阻止新房：' + json.dumps(failures, ensure_ascii=False))
    publish_status({'state': 'cycle_closed', 'cycle': number, 'active_children': {},
                    'summary': str((directory / 'SUMMARY.json').relative_to(ROOT))})


def status():
    """只读真实 PID 与已写状态，不触发比赛、采集或重启。"""
    state = load(_project_file(_PROJECT_ROOT, HERE / 'STATUS.json'))
    state['controller_process_now'] = process_identity(state.get('controller_pid'), 'watchdog.py watch')
    state['active_children_now'] = {k: process_identity(pid, 'run_auto_match.py' if k == 'free' else 'run_test_room.py')
                                    for k, pid in state.get('active_children', {}).items()}
    print(json.dumps(state, ensure_ascii=False, indent=2))


def require_prior_closed():
    """所有历史批次必须真的闭合；不以最大编号跳过失败或无人监督的旧房。"""
    prior = []
    for directory in sorted(HERE.glob('cycle-*')):
        assert directory.is_dir()
        plan, closure, summary = directory / 'PLAN.json', directory / 'CYCLE-CLOSED.json', directory / 'SUMMARY.json'
        assert plan.is_file(), '已有不完整建房目录；不能自动重试POST或跳过：' + directory.name
        assert summary.is_file(), '旧批次缺赛后摘要，禁止续新房：' + directory.name
        accepted = (load(closure).get('failures') == []) if closure.is_file() else False
        recovery = directory / 'RECOVERY-CLOSED.json'
        if not accepted and recovery.is_file():
            accepted = load(recovery).get('closed_verified') is True
        assert accepted, '旧批次尚未成功闭合；需显式恢复，不自动跳过：' + directory.name
        for lane in ('free', 'mixed'):
            assert load(directory / (lane.upper() + '-CHILD-TERMINAL.json'))['actual_exit_code'] == 0
            assert load(directory / (lane.upper() + '-POSTGAME-TERMINAL.json'))['actual_exit_code'] == 0
        prior.append(load(plan)['cycle'])
    return prior


def analyze_closed_cycle(number):
    """仅恢复已有成功自然终态及postgame的统计；不重新参赛、采集或猜未知退出码。"""
    assert type(number) is int and number > 0
    assert not other_players(), '仍有实际玩家，禁止恢复统计争CPU'
    directory = _project_file(_PROJECT_ROOT, HERE / ('cycle-%03d' % number))
    assert not (directory / 'SUMMARY.json').exists(), '已有摘要不可覆盖；先人工复查原失败'
    for lane in ('free', 'mixed'):
        assert load(directory / (lane.upper() + '-CHILD-TERMINAL.json'))['actual_exit_code'] == 0
        assert load(directory / (lane.upper() + '-POSTGAME-TERMINAL.json'))['actual_exit_code'] == 0
    result = subprocess.run([sys.executable, str(_project_file(_PROJECT_ROOT, HERE / 'analyze.py')), '--cycle', str(directory)], cwd=ROOT, env=env())
    write(directory / 'RECOVERY-ANALYSIS-TERMINAL.json', {'at_utc': now(), 'actual_exit_code': result.returncode}, exclusive=True)
    assert result.returncode == 0
    write(directory / 'RECOVERY-CLOSED.json', {'at_utc': now(), 'closed_verified': True,
          'scope': 'existing successful natural runs and postgame only; old failures retained',
          'new_official_calls': 0, 'original_cycle_closed_rewritten': False}, exclusive=True)


def main():
    """执行显式入口；锁冲突只报告，不开启第二 owner。"""
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument('command', choices=('status', 'preflight', 'watch', 'analyze-closed'))
    args.add_argument('--cycle', type=int)
    parsed_args = args.parse_args()
    command = parsed_args.command
    if command == 'status':
        status()
        return
    if command == 'preflight':
        print(json.dumps(preflight(), ensure_ascii=False, indent=2))
        return
    if command == 'analyze-closed':
        analyze_closed_cycle(parsed_args.cycle)
        return
    PRIVATE.mkdir(mode=0o700, exist_ok=True)
    with (_project_file(_PROJECT_ROOT, PRIVATE / 'controller.lock')).open('a+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('已有 T165 控制器，拒绝重复启动', flush=True)
            return
        assert not other_players(), '检测到已有官方参赛进程，禁止新 owner'
        require_prior_closed()
        if not (_project_file(_PROJECT_ROOT, PRIVATE / 'control.json')).exists():
            write(_project_file(_PROJECT_ROOT, PRIVATE / 'control.json'), {'continue_after_cycle': True}, exclusive=True)
        stop = [False]
        def finish_current(_signum, _frame):
            stop[0] = True  # 不向参赛子进程转发；当前两路自然结束。
        signal.signal(signal.SIGINT, finish_current)
        signal.signal(signal.SIGTERM, finish_current)
        try:
            while not stop[0] and load(_project_file(_PROJECT_ROOT, PRIVATE / 'control.json'))['continue_after_cycle']:
                identity = preflight(require_review=True)
                prior = require_prior_closed()
                number = 1 + max(prior, default=0)
                one_cycle(number, identity)
                print(json.dumps({'cycle_closed': number, 'at_utc': now()}, ensure_ascii=False), flush=True)
            publish_status({'state': 'stopped_after_natural_cycle', 'active_children': {}})
        except Exception as error:
            previous = load(_project_file(_PROJECT_ROOT, PRIVATE / 'state.json')) if (_project_file(_PROJECT_ROOT, PRIVATE / 'state.json')).exists() else {}
            children = {k: pid for k, pid in previous.get('active_children', {}).items() if pid_alive(pid)}
            publish_status({'state': 'blocked_new_rooms', 'active_children': children,
                            'reason': type(error).__name__ + ': ' + str(error)})
            raise


if __name__ == '__main__':
    main()
