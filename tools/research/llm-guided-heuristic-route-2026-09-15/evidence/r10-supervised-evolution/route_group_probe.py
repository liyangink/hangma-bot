"""同一条件路线等价拆分/重排的变形检查，独立于完整桌赛效果评价。"""

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
import argparse
import dataclasses
import copy
import strong_seed_batch as b
import route_group_batch as experiment
import wealth_branch_probe as helper

PANEL = experiment.ROOT / 'route-group-invariance-panel.json'


def freeze():
    """从既有请求固定选取最长可拆分路线；不根据新作者结果挑输入。"""
    if PANEL.exists():
        raise SystemExit('面板已冻结')
    _, real = b.behavior.load_panel(b.HERE / 'batch03-known-root-diagnostic/panel.json')
    groups = [('real', real), ('condition', [
        (row['name'], helper.decision_request_from_json(row['record']['request']))
        for row in b.read(helper.PANEL)['rows']])]
    rows = []
    for source, requests in groups:
        kept = 0
        for name, request in requests:
            view = helper.build_scoring_view(request).candidate_view()
            choices = []
            for action in view['actions']:
                for index, route in enumerate(action.get('routes') or ()):
                    size = len(route.get('useful_tiles') or ())
                    if size >= 2:
                        choices.append((-size, action['action_key'], index))
            if not choices:
                continue
            _, key, index = min(choices)
            rows.append({'name': source + '-' + name, 'action_key': key,
                         'route_index': index, 'record': b.behavior.capture_request(request)})
            kept += 1
            if kept == 6:
                break
    assert len(rows) == 12
    b.write(PANEL, {'purpose': 'equivalent_route_partition_and_order',
        'created_at_utc': b.search.utc_now(), 'execution_deps_digest': b.search.av_gates().av_deps_digest(),
        'rows': rows, 'selection_eligible': False,
        'scope': '6真实开发请求与6规则条件请求；等价拆分仅改变分组，不新增牌种/条件；不计强度样本'})
    print({'frozen': len(rows)})


def compare_source(path):
    """通过公开评分器比较原样、等价拆分及路线重排；返回未通过项而不改判据。"""
    panel = b.read(PANEL)
    assert panel['execution_deps_digest'] == b.search.av_gates().av_deps_digest()
    scorer = helper.ActionValueScorer('route-partition-probe', path.read_text())
    reports = []
    for row in panel['rows']:
        record = row['record']
        assert b.behavior.digest(record['request']) == record['request_sha256']
        request = helper.decision_request_from_json(record['request'])
        original = helper.build_scoring_view(request)
        plain = original.candidate_view()
        assert b.behavior.digest(plain) == record['candidate_view_sha256']
        projected = {action['action_key']: action for action in plain['actions']}
        cases = {'original': original}
        for mode in ('split_identical_condition', 'reverse_route_order'):
            actions = []
            for action in original.actions:
                routes = copy.deepcopy(list(projected[action.action_key].get('routes') or ()))
                if mode == 'reverse_route_order':
                    routes.reverse()
                elif action.action_key == row['action_key']:
                    index = row['route_index']
                    route = routes[index]
                    first, rest = copy.deepcopy(route), copy.deepcopy(route)
                    first['useful_tiles'] = route['useful_tiles'][:1]
                    rest['useful_tiles'] = route['useful_tiles'][1:]
                    routes[index:index + 1] = [first, rest]
                actions.append(dataclasses.replace(action, routes=tuple(routes)))
            cases[mode] = dataclasses.replace(original, actions=tuple(actions))
        results = {}
        for mode, view in cases.items():
            batch = scorer.score(view)
            results[mode] = {'status': batch.status,
                            'scores': {e.action_key: e.score for e in batch.entries}}
        ok = all(result['status'] == 'SCORED' and result['scores'] == results['original']['scores']
                 for result in results.values())
        reports.append({'name': row['name'], 'invariant': ok, 'results': results})
    return {'source_sha256': b.digest(path.read_bytes()), 'panel_sha256': b.digest(PANEL.read_bytes()),
            'cases': len(reports), 'invariant': sum(r['invariant'] for r in reports),
            'rows': reports, 'selection_eligible': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['freeze', 'parent', 'candidate'])
    action = parser.parse_args().action
    if action == 'freeze':
        freeze()
    else:
        source = (experiment.PARENT / 'candidate.py' if action == 'parent' else
                  experiment.ROOT / experiment.NAME / 'run/iterations/iter-01/generation/candidate.py')
        output = experiment.ROOT / (action + '-route-invariance.json')
        if output.exists():
            raise SystemExit('已有结果，不覆盖')
        result = compare_source(source)
        b.write(output, result)
        print({key: result[key] for key in ('cases', 'invariant')})
