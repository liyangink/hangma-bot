"""验签两项实际终态，保存费用和闭合清单；不调用规则、候选或模拟。"""

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
import json
from pathlib import Path
import pstats

HERE = Path(__file__).resolve().parent
T124 = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t124-native-mechanical-functions-1')
ROUTE = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30')
ROOT = _PROJECT_ROOT


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')


def verify_plan(directory, runner):
    plan = read(directory / 'PLAN.json')
    assert sha(directory / runner) == plan['runner_sha256']
    for path, digest in plan['frozen_files'].items():
        assert sha(path) == digest, path
    return plan


def prepend(path, entry, marker):
    text = path.read_text()
    assert marker in text
    assert entry not in text
    title, tail = text.split('\n', 1)
    path.write_text(title + '\n\n' + entry + '\n' + tail.lstrip('\n'))


def main():
    """只按实际业务计数结账，公开回归fixture不算自然候选强度。"""
    verify_plan(T124, 'run_full.py')
    verify_plan(HERE, 'run_profile.py')
    panel = read(_project_file(_PROJECT_ROOT, T124 / 'actual-full-1/CLOSURE.json'))
    profile = read(_project_file(_PROJECT_ROOT, HERE / 'actual-full-1/CLOSURE.json'))
    unit = read(_project_file(_PROJECT_ROOT, T124 / 'MECHANICAL-CONTRACT-RESULT.json'))
    assert panel['full_math_exact'] and profile['full_math_exact']
    assert not panel['local_full_panel_deadline_pass']
    assert unit['pytest_exit_code'] == 0 and '199 passed' in (_project_file(_PROJECT_ROOT, T124 / 'ACTUAL-MECHANICAL-CONTRACT.log')).read_text()
    assert len(panel['rows']) == 8 and sum(row['ready_before_fallback'] for row in panel['rows']) == 7
    for result, count in ((panel, 8), (profile, 1)):
        assert not result['issues'] and result['capture']['terminal']['terminal_valid']
        for key in ('rule_attempts', 'choose_attempts', 'direct_score_attempts'):
            assert result['actual_costs'][key] == count
        assert result['actual_costs']['reference_score_attempts'] == 0
        assert result['actual_costs']['failed_score_attempts'] == 0
    stats = pstats.Stats(str(_project_file(_PROJECT_ROOT, HERE / 'actual-full-1/PROFILE-01.prof')))
    native = [key for key in stats.stats if '.pyx' in key[0]]
    assert len(native) == 81
    summary = {'schema': 't124-t125-stage-closure/1',
        'full_math_exact': True, 'full_panel_deadline_pass': False,
        'full_panel_math_cases': 8, 'full_panel_timing_pass_cases': 7,
        'current_S02_rule_choose_score_attempts_each': 9,
        'current_S02_score_failures': 0, 'new_reference_scores': 0,
        'public_regression_tests_passed': 199,
        'actual_unit_fixture_costs': unit['actual_unit_fixture_costs'],
        'native_profile_rows': len(native), 'profile_is_not_latency_evidence': True,
        'new_model_authors': 0, 'natural_whole_tables': 0, 'production_changes': 0,
        'online_admission': False, 'mechanical_variant_promoted': False,
        'goal_status_at_closure': 'active',
        'next': 'separate experiments for full value conversion and compatible-code reuse; preserve mutable ownership and all qualification evidence'}
    save(_project_file(_PROJECT_ROOT, HERE / 'STAGE-CLOSURE.json'), summary)
    report = 'T124-T125-MECHANICAL-RESULT-AND-INTERNAL-PROFILE.md'
    index_entry = '**2026-10-04 T124—T125：机械编译没有明确提速，原生内部剖析已打通，仍无VIP上线资格。** 199项公开回归通过；原8选择完整输入／分数／解释／操作精确一致，时限仍7／8，极端碰响应1.892秒。另一条同S02原生函数级剖析看到81项原生记录，2527116次冻结值转换、22825次相容码计算；剖析时间不授时限。当前S02新增9评分、0作者／自然桌，fixture费用另账。首次Cython路径失败、机械负结果及原工具终态保留；下一项分别研究容器转换和同请求相容码复用。线上R18 v2、goal active。[结果与下一步](./vip-route-2026-09-30/' + report + ')'
    prepend(_project_file(_PROJECT_ROOT, ROOT / 'review/INDEX.md'), index_entry, 'T120—T123')
    progress_entry = index_entry.replace('./vip-route-2026-09-30/', './')
    prepend(_project_file(_PROJECT_ROOT, ROUTE / 'PROGRESS.md'), progress_entry, 'T120')
    paths = []
    for directory in (T124, HERE):
        rows = []
        for path in sorted(directory.rglob('*')):
            if not path.is_file() or '__pycache__' in path.parts or path.suffix in ('.c', '.o', '.pyc'):
                continue
            if path.name == 'CLOSED-ARTIFACT-MANIFEST.json':
                continue
            rows.append({'path': str(path.relative_to(ROOT)), 'bytes': path.stat().st_size,
                         'sha256': sha(path)})
            paths.append(path)
        manifest = directory / 'CLOSED-ARTIFACT-MANIFEST.json'
        save(manifest, {'schema': 'closed-research-artifacts/1', 'files': rows,
            'rebuildable_C_and_object_files_excluded': True,
            'native_binaries_and_complete_inputs_included': True})
        paths.append(manifest)
    paths.extend([_project_file(_PROJECT_ROOT, ROOT / 'review/INDEX.md'), _project_file(_PROJECT_ROOT, ROUTE / 'PROGRESS.md'), _project_file(_PROJECT_ROOT, ROUTE / report)])
    target = Path('/private/tmp/hangma-t124-t125-stage-paths.nul')
    with target.open('xb') as stream:
        for path in paths:
            stream.write(str(path.relative_to(ROOT)).encode() + b'\0')
    print(json.dumps({'closed': True, 'selected_files': len(paths),
        'stage_paths': str(target), 'actual_S02_scores': 9, 'native_profile_rows': 81}))


if __name__ == '__main__':
    main()
