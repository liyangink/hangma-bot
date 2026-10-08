"""冻结单条极端响应的原生内部剖析，原完整输入和评分参考保持。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t125-native-internal-profile-1'

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
import sys

HERE = Path(__file__).resolve().parent
PARENT = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t123-s02-optimized-full-panel-1')
T119 = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t119-s02-native-remaining-profile-1')
RUNTIME = Path('/Users/liyang/.codex/worktrees/t54-public-count-cache/hangma-bot')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def text(name, value):
    with (_project_file(_PROJECT_ROOT, HERE / name)).open('x') as stream:
        stream.write(value)


def change(value, old, new):
    assert value.count(old) == 1, old
    return value.replace(old, new)


def main():
    """一个变量：第一方原生函数级剖析开启；不授性能改善。"""
    base = (_project_file(_PROJECT_ROOT, PARENT / 'native_base.py')).read_text()
    base = change(base, "T88 = HERE.parent / 't88-native-execution-prototype-1'",
        "T88 = Path(__file__).resolve().parent / 'profile_firstparty'")
    text('native_base.py', base)
    overlay = (_project_file(_PROJECT_ROOT, PARENT / 'native_overlay.py')).read_text()
    overlay = change(overlay, 't123-optimized-full-panel-native-execution/1',
                     't125-profiled-firstparty-execution/1')
    text('native_overlay.py', overlay)
    runner = (_project_file(_PROJECT_ROOT, T119 / 'run_profile.py')).read_text()
    runner = change(runner, "['original-T80-failed-response', 'old:public:20']",
                    "['original-T80-failed-response']")
    for old, new in [("'max_choose_attempts': 2", "'max_choose_attempts': 1"),
        ("'max_score_attempts': 2", "'max_score_attempts': 1"),
        ('len(rows) == 2', 'len(rows) == 1'),
        ("costs['rule_attempts'] == 2", "costs['rule_attempts'] == 1"),
        ("costs['choose_attempts'] == 2", "costs['choose_attempts'] == 1"),
        ("costs['direct_score_attempts'] == 2", "costs['direct_score_attempts'] == 1"),
        ("'max_rule_choose_score_attempts': 2", "'max_rule_choose_score_attempts': 1"),
        ('t119-s02-native-profile-result/1', 't125-native-internal-profile-result/1')]:
        runner = change(runner, old, new)
    runner = runner.replace('最多两次规则分析与两次完整 choose', '最多一次规则分析与一次完整 choose')
    text('run_profile.py', runner)
    plan = json.loads((_project_file(_PROJECT_ROOT, PARENT / 'PLAN.json')).read_text())
    sys.path[:0] = [str(RUNTIME), str(_project_file(_PROJECT_ROOT, RUNTIME / 'src'))]
    spec = importlib.util.spec_from_file_location('t125_profile_overlay', _project_file(_PROJECT_ROOT, HERE / 'native_overlay.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with module.installed() as binding:
        execution = {'schema': 't125-internal-profile-comparison/1',
            'base_candidate_id': plan['candidate_identity']['candidate_id'],
            'overlay': binding, 'new_formula': False, 'production_changes': 0,
            'profiled_time_is_not_deadline_evidence': True}
        raw = json.dumps(execution, ensure_ascii=False, sort_keys=True,
                         separators=(',', ':'), allow_nan=False).encode()
        execution['research_execution_id'] = hashlib.sha256(raw).hexdigest()
    plan.update(schema='t125-native-internal-profile-plan/1',
        labels=['original-T80-failed-response'],
        scope='one previously failed complete public response; diagnostic profile only',
        research_execution_identity=execution, runner_sha256=sha(_project_file(_PROJECT_ROOT, HERE / 'run_profile.py')),
        actual_preparation_business_calls=0)
    own = [_project_file(_PROJECT_ROOT, HERE / name) for name in ('build_profile.py', 'prepare_profile.py',
                                  'native_base.py', 'native_overlay.py', 'ACTUAL-BUILD.log',
                                  'ACTUAL-BUILD-WITH-TOOLS.log')]
    own += list((_project_file(_PROJECT_ROOT, HERE / 'profile_firstparty')).glob('*.pyx'))
    own += [_project_file(_PROJECT_ROOT, HERE / 'profile_firstparty' / name)
            for name in ('BUILD-PLAN.json', 'BUILD-CLOSURE.json', 'native_overlay.py')]
    own += list((_project_file(_PROJECT_ROOT, HERE / 'profile_firstparty/build/lib')).glob('*.so'))
    own += [_project_file(_PROJECT_ROOT, T119 / 'run_profile.py'), _project_file(_PROJECT_ROOT, PARENT / 'PLAN.json'),
            _project_file(_PROJECT_ROOT, HERE.parent / 't124-native-mechanical-functions-1/actual-full-1/CLOSURE.json')]
    for path in own:
        plan['frozen_files'][str(path)] = sha(path)
    with (_project_file(_PROJECT_ROOT, HERE / 'PLAN.json')).open('x') as stream:
        json.dump(plan, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'prepared': True, 'max_score_calls': 1, 'actual_business_calls': 0,
        'research_execution_id': execution['research_execution_id']}))


if __name__ == '__main__':
    main()
