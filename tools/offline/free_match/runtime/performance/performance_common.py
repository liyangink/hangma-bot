"""T199 P0性能窄接缝：只用冻结P0、公开观察、当前规则和离线草稿工厂。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t199-four-step-execution-1/runtime/performance'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

from contextlib import contextmanager
from dataclasses import dataclass
from dataclasses import asdict
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = _PROJECT_ROOT
P0 = _project_file(_PROJECT_ROOT, '.private/t199-four-step-execution/runtime-workspace/runtime-root-p0')
HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, '.private/t199-four-step-execution/runtime-workspace/performance-p0')
sys.path[:0] = [str(_project_file(_PROJECT_ROOT, P0 / 'src')), str(P0), str(HERE)]
os.environ['PYTHONPATH'] = os.pathsep.join((str(_project_file(_PROJECT_ROOT, P0 / 'src')), str(P0), str(HERE)))
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
_PACKAGE = None


def read(path):
    """只读小型公开／冻结证据，不打开凭据文件。"""
    return json.loads(Path(path).read_text())


def pin(path):
    """完整字节身份，含原输入和实际二进制。"""
    raw = Path(path).read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def digest(value):
    """规范JSON全计划摘要，不把旧策略输出当P0参考。"""
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def save(path, value):
    """独占保存每次尝试；失败不覆盖，也不自动重跑。"""
    with Path(path).open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


@contextmanager
def slots(count):
    """与32桌共享T182原四锁；未取得就拒绝启动，不拿postprocess全局锁。"""
    base = _project_file(_PROJECT_ROOT, ROOT / 'review/vip-route-2026-09-30/evidence/t182-step12-diagnosis-and-joint-evolution-1')
    handles = []
    try:
        for index in range(4):
            stream = (base / ('.resource-scheduling-worker-%d.lock' % index)).open('r+')
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                stream.close()
                continue
            handles.append(stream)
            if len(handles) == count:
                break
        if len(handles) != count:
            raise BlockingIOError('T182自然空闲资源槽不足')
        yield [stream.name for stream in handles]
    finally:
        for stream in reversed(handles):
            stream.close()


def package():
    """显式离线草稿验装；默认启动仍拒绝，不读取Token或创建HTTP客户端。"""
    global _PACKAGE
    from hangma_bot import bootstrap as b
    if Path(b.__file__).resolve() != _project_file(_PROJECT_ROOT, P0 / 'src/hangma_bot/bootstrap.py'):
        raise ValueError('P0组合根导入泄漏')
    if _PACKAGE is None:
        _PACKAGE = b._load_vip_s03_rulefix_p0_manifest('vip_s03_rulefix_p0_free_v1', offline_validation_only=True)
    return _PACKAGE


def policy(compiled):
    """同生产RouteVip及冻结操作数／投影预算，compiled=False为新P0 Python参考。"""
    from hangma_bot import bootstrap as b
    from hangma_bot.kernel.config import RuleConfig
    from hangma_bot.policy.route_vip_heuristic import RouteVipHeuristicPolicy
    payload = package()
    params = payload['candidate_identity']['params']
    if asdict(b.VIP_S02_PROJECTION_LIMITS) != params['projection_limits'] or asdict(b.VIP_S02_ROUTE_LIMITS) != params['route_limits']:
        raise ValueError('P0投影／路线预算不符')
    native = b._load_vip_s03_runtime(payload['compiled_runtime']['manifest_sha256']) if compiled else None
    return RouteVipHeuristicPolicy(RuleConfig(**params['rule_config']), source=b.VIP_S03_SOURCE,
        max_operations=params['max_operations'], projection_limits=b.VIP_S02_PROJECTION_LIMITS,
        compiled_runtime=native)


@dataclass(frozen=True)
class P0Factory:
    """可spawn离线工厂；只携执行摘要，启动期验草稿制品，动作热区不读盘。"""
    expected_execution_id: str

    def __call__(self):
        from hangma_bot.application.decision_compute import PreparedDecisionPolicy
        from hangma_bot import bootstrap as b
        payload = package()
        native = b._load_vip_s03_runtime(payload['compiled_runtime']['manifest_sha256'])
        if native.execution_id != self.expected_execution_id:
            raise ValueError('P0工厂执行摘要不符')
        return PreparedDecisionPolicy(policy(True), native.execution_id)


def make_request(case):
    """按原公开观察／窗口重算P0规则和合法保底，保留原请求其余事实。"""
    from hangma_bot.application.audit_codec import decision_request_from_json
    from hangma_bot.hangma.engine import HangmaRules
    from hangma_bot.kernel.config import RuleConfig
    from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
    from hangma_bot.kernel.observation import CompetitionContext
    from hangma_bot.policy.interface import DecisionRequest
    from hangma_bot import bootstrap as b
    from dataclasses import replace
    params = package()['candidate_identity']['params']
    obs = observation_from_json(case['observation'])
    rules = HangmaRules(RuleConfig(**params['rule_config'])).analyze(obs, route_limits=b.VIP_S02_ROUTE_LIMITS)
    if rules.emergency_candidate is None:
        raise ValueError('P0规则分析未先提供合法保底')
    if case.get('original_request'):
        old = decision_request_from_json(case['original_request'])
        return replace(old, rules=rules), rules
    key = window_key_from_json(case['window_key'])
    context = CompetitionContext('t199-p0-performance', None, None, None, None, (), 0)
    return DecisionRequest(obs, context, rules, case['decision_id'], key.trigger_seq, key, ()), rules


def resource_zero(snapshot):
    """12资源项逐项真实零；缺字段不能当作回收。"""
    keys = ('owned','pending','active','ready','live_processes','current','transport_inflight',
        'transport_threads_alive','late_reap_inflight','late_reap_threads_alive','bound_games','releasing_games')
    return snapshot.get('closed') is True and all(type(snapshot.get(k)) is int and snapshot[k] == 0 for k in keys)


def root_unchanged():
    """按冻结根的完整文件清单复核；仅此P0，不推断上线资格。"""
    manifest_path=_project_file(_PROJECT_ROOT, P0.parent/'P0-RUNTIME-ROOT-FINAL.json')
    manifest=read(manifest_path)
    changed=[name for name,expected in manifest['files'].items() if pin(_project_file(_PROJECT_ROOT, P0/name))!=expected]
    if changed:raise ValueError('冻结P0发生漂移:'+repr(changed))
    return {'manifest_pin':pin(manifest_path),'verified_files':len(manifest['files']),'changed':changed}
