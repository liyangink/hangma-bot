"""冻结机械原生执行的完整面板；准备阶段不分析规则、不选择或评分。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t124-native-mechanical-functions-1'

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
RUNTIME = Path('/Users/liyang/.codex/worktrees/t54-public-count-cache/hangma-bot')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')


def copy_text(name, text):
    with (_project_file(_PROJECT_ROOT, HERE / name)).open('x') as stream:
        stream.write(text)


def main():
    """承接既有完整数学参考和原预算，只添加一种执行实现。"""
    tests = json.loads((_project_file(_PROJECT_ROOT, HERE / 'MECHANICAL-CONTRACT-RESULT.json')).read_text())
    assert tests['pytest_exit_code'] == 0
    assert tests['complete_capture']['terminal']['terminal_valid']
    assert '199 passed' in (_project_file(_PROJECT_ROOT, HERE / 'ACTUAL-MECHANICAL-CONTRACT.log')).read_text()
    plan = json.loads((_project_file(_PROJECT_ROOT, PARENT / 'PLAN.json')).read_text())
    copy_text('native_base.py', (_project_file(_PROJECT_ROOT, PARENT / 'native_base.py')).read_text())
    copy_text('native_parent.py', (_project_file(_PROJECT_ROOT, PARENT / 'native_overlay.py')).read_text())
    runner = (_project_file(_PROJECT_ROOT, PARENT / 'run_full.py')).read_text()
    old_schema = 't123-s02-optimized-full-panel-result/1'
    assert runner.count(old_schema) == 1
    runner = runner.replace(old_schema, 't124-s02-native-mechanical-full-panel-result/1')
    copy_text('run_full.py', runner)
    sys.path[:0] = [str(RUNTIME), str(_project_file(_PROJECT_ROOT, RUNTIME / 'src'))]
    spec = importlib.util.spec_from_file_location('t124_execution_freeze', _project_file(_PROJECT_ROOT, HERE / 'native_overlay.py'))
    overlay = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(overlay)
    with overlay.installed() as binding:
        execution = {'schema': 't124-native-mechanical-research-comparison/1',
            'base_candidate_id': plan['candidate_identity']['candidate_id'],
            'overlay': binding, 'new_formula': False, 'production_changes': 0,
            'scope': 'original eight choices and complete inputs; same formula and budgets'}
        raw = json.dumps(execution, ensure_ascii=False, sort_keys=True,
                         separators=(',', ':'), allow_nan=False).encode()
        execution['research_execution_id'] = hashlib.sha256(raw).hexdigest()
    plan['schema'] = 't124-native-mechanical-full-panel-plan/1'
    plan['scope'] = execution['scope']
    plan['research_execution_identity'] = execution
    plan['runner_sha256'] = sha(_project_file(_PROJECT_ROOT, HERE / 'run_full.py'))
    for name in ('prepare_full.py', 'native_base.py', 'native_parent.py', 'native_overlay.py',
                 'mechanical_overlay.py', 'build_mechanical.py', '_t124_mechanical.pyx',
                 'BUILD-PLAN.json', 'BUILD-CLOSURE.json', 'run_mechanical_tests.py',
                 'MECHANICAL-CONTRACT-RESULT.json', 'UNIT-INPUTS.jsonl.gz',
                 'ACTUAL-MECHANICAL-CONTRACT.log'):
        path = _project_file(_PROJECT_ROOT, HERE / name)
        plan['frozen_files'][str(path)] = sha(path)
    closure = json.loads((_project_file(_PROJECT_ROOT, HERE / 'BUILD-CLOSURE.json')).read_text())
    binary = _project_file(_PROJECT_ROOT, HERE / closure['binary']['path'])
    plan['frozen_files'][str(binary)] = sha(binary)
    plan['frozen_files'][str(_project_file(_PROJECT_ROOT, PARENT / 'PLAN.json'))] = sha(_project_file(_PROJECT_ROOT, PARENT / 'PLAN.json'))
    plan['frozen_files'][str(_project_file(_PROJECT_ROOT, PARENT / 'actual-full-1/CLOSURE.json'))] = sha(_project_file(_PROJECT_ROOT, PARENT / 'actual-full-1/CLOSURE.json'))
    plan['max_rule_choose_S02_score_attempts'] = 8
    plan['actual_preparation_business_calls'] = 0
    save(_project_file(_PROJECT_ROOT, HERE / 'PLAN.json'), plan)
    print(json.dumps({'prepared': True, 'research_execution_id': execution['research_execution_id'],
        'actual_rule_choose_score_calls': 0, 'max_original_panel_choose_calls': 8}))


if __name__ == '__main__':
    main()
