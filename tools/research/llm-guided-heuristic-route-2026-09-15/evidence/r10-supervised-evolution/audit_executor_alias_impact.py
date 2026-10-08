"""在固定80个输入上比较修复前后公开评分入口；不外推为全域等价。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import importlib.util
import sys

import strong_seed_batch as b
import route_group_batch as experiment
import wealth_branch_probe as helper
from hangma_bot.policy.action_value_executor import ActionValueExecutor


def run():
    """封存差异范围；旧执行器仅从已保存源码装载，不还原工作区核心。"""
    sub = experiment.ROOT / experiment.NAME
    out = sub / 'executor-alias-impact.json'
    assert not out.exists()
    old_path = sub / 'executor-before-alias-fix.py'
    spec = importlib.util.spec_from_file_location('hangma_bot.policy.executor_before_alias_fix', old_path)
    old = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = old
    spec.loader.exec_module(old)
    _, real = b.behavior.load_panel(b.HERE / 'batch03-known-root-diagnostic/panel.json')
    requests = [('real-' + name, request) for name, request in real]
    for label, panel in [('condition', helper.PANEL), ('fault', b.HERE / 'branch-wealth-20260920/wealth-branch-terra-max/missing-branches-fault-probe.json')]:
        data = b.read(panel)
        for index, row in enumerate(data['rows']):
            record = row['record']
            assert b.behavior.digest(record['request']) == record['request_sha256']
            request = helper.decision_request_from_json(record['request'])
            assert b.behavior.digest(helper.build_scoring_view(request).candidate_view()) == record['candidate_view_sha256']
            requests.append((label + '-' + str(index), request))
    paths = {name: b.Path(b.search.av_state_load(b.search.av_latest_state_path(b.BATCH / name / 'run'))['iter_dir']) / 'generation/candidate.py'
             for name in b.CONFIGS}
    for name in ('parent-a', 'parent-b'):
        paths[name] = b.Path(b.read(b.BATCH / name / 'manifest.json')['source_path'])
    paths['branch-terra-max'] = b.HERE / 'branch-refinement-20260920/branch-terra-max/run/iterations/iter-01/generation/candidate.py'
    paths['wealth-branch-terra-max'] = b.HERE / 'branch-wealth-20260920/wealth-branch-terra-max/run/iterations/iter-01/generation/candidate.py'
    paths[experiment.NAME] = sub / 'run/iterations/iter-01/generation/candidate.py'
    reports = []
    for name, path in paths.items():
        left, right = old.ActionValueExecutor(path.read_text()), ActionValueExecutor(path.read_text())
        rows = []
        for label, request in requests:
            view = helper.build_scoring_view(request)
            a, z = left.score(view), right.score(view)
            sa, sz = {e.action_key: e.score for e in a.entries}, {e.action_key: e.score for e in z.entries}
            ta, tz = {e.action_key: dict(e.trace) for e in a.entries}, {e.action_key: dict(e.trace) for e in z.entries}
            rows.append({'input': label, 'status_before': a.status, 'status_after': z.status,
                         'scores_equal': sa == sz, 'trace_equal': ta == tz,
                         'before': sa, 'after': sz})
        report = {'name': name, 'source_sha256': b.digest(path.read_bytes()), 'cases': len(rows),
                  'changed_scores': sum(not r['scores_equal'] for r in rows),
                  'changed_trace': sum(not r['trace_equal'] for r in rows), 'rows': rows}
        reports.append(report)
        print({k: report[k] for k in ('name', 'cases', 'changed_scores', 'changed_trace')}, flush=True)
    b.write(out, {'old_executor_sha256': b.digest(old_path.read_bytes()),
                  'new_execution_deps_digest': b.search.av_gates().av_deps_digest(),
                  'reports': reports, 'scope': '有限真实/条件/故障输入差分，不证明未触发状态不受影响',
                  'selection_eligible': False, 'release_eligible': False})


if __name__ == '__main__':
    run()
