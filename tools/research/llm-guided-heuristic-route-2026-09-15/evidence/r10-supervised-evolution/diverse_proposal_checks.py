"""新提案共用的80输入诊断：固定旧真实、规则条件与捕获故障，不计效果样本。"""

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

import strong_seed_batch as b
import diverse_proposal_batch as experiment
import wealth_branch_probe as helper
from hangma_bot.policy.action_value_seeds import ActionValueScorer

PANEL = experiment.OUT / 'diagnostic-panel.json'


def freeze():
    """作者交付前冻结输入清单；不会根据新源码挑选有利输入。"""
    assert not PANEL.exists()
    _, real = b.behavior.load_panel(b.HERE / 'batch03-known-root-diagnostic/panel.json')
    rows = [{'origin': 'real', 'name': name, 'record': b.behavior.capture_request(request)}
            for name, request in real]
    provenance = []
    for label, path in [('condition', helper.PANEL),
                        ('fault', b.HERE / 'branch-wealth-20260920/wealth-branch-terra-max/missing-branches-fault-probe.json')]:
        source = b.read(path)
        provenance.append({'path': str(path), 'sha256': b.digest(path.read_bytes())})
        for index, row in enumerate(source['rows']):
            record = row['record']
            assert b.behavior.digest(record['request']) == record['request_sha256']
            rows.append({'origin': label, 'name': label + '-' + str(index), 'record': record})
    assert len(rows) == 80
    b.write(PANEL, {'created_at_utc': b.search.utc_now(), 'rows': rows, 'provenance': provenance,
        'deps_digest': b.search.av_gates().av_deps_digest(), 'selection_eligible': False,
        'scope': '32既有真实窗、24规则条件夹具、24故障捕获输入；只检查确定行为，非80独立强度样本'})


def check(name):
    """通过公开评分器比较父代与新提案；记录变化及故障，不把它自动判为强度收益。"""
    panel = b.read(PANEL)
    assert panel['deps_digest'] == b.search.av_gates().av_deps_digest()
    manifest = b.read(experiment.OUT / 'manifest.json')
    parent = b.Path(manifest['parent']) / 'candidate.py'
    assert b.digest(parent.read_bytes()) == manifest['parent_sha256']
    sub = experiment.OUT / name
    state = b.search.av_state_load(b.search.av_latest_state_path(sub / 'run'))
    assert b.search.av_verify_run_identity(state)[0]
    source = b.Path(state['iter_dir']) / 'generation/candidate.py'
    output = sub / 'diagnostic-comparison.json'
    assert not output.exists()
    scorers = {'parent': ActionValueScorer('diagnostic-parent', parent.read_text()),
               'candidate': ActionValueScorer('diagnostic-candidate', source.read_text())}
    rows = []
    for row in panel['rows']:
        record = row['record']
        assert b.behavior.digest(record['request']) == record['request_sha256']
        request = helper.decision_request_from_json(record['request'])
        view = helper.build_scoring_view(request)
        assert b.behavior.digest(view.candidate_view()) == record['candidate_view_sha256']
        results = {}
        for label, scorer in scorers.items():
            try:
                batch = scorer.score(view)
                entries = [{'action_key': e.action_key, 'score': e.score, 'trace': dict(e.trace)} for e in batch.entries]
                order = [e['action_key'] for e in sorted(entries, key=lambda e: (-e['score'], e['action_key']))]
                results[label] = {'status': batch.status, 'reason': batch.reason, 'entries': entries, 'order': order}
            except Exception as error:
                results[label] = {'status': 'EXCEPTION', 'reason': type(error).__name__ + ': ' + str(error),
                                  'entries': [], 'order': []}
        a, z = results['parent'], results['candidate']
        rows.append({'origin': row['origin'], 'name': row['name'], 'request_sha256': record['request_sha256'],
            'results': results, 'first_changed': a['order'][:1] != z['order'][:1],
            'order_changed': a['order'] != z['order'],
            'scores_changed': {e['action_key']: e['score'] for e in a['entries']} != {e['action_key']: e['score'] for e in z['entries']}})
    summary = {}
    for origin in ('real', 'condition', 'fault'):
        selected = [r for r in rows if r['origin'] == origin]
        summary[origin] = {'inputs': len(selected),
            'candidate_scored': sum(r['results']['candidate']['status'] == 'SCORED' for r in selected),
            **{key: sum(r[key] for r in selected) for key in ('first_changed', 'order_changed', 'scores_changed')}}
    b.write(output, {'source_sha256': b.digest(source.read_bytes()), 'parent_sha256': manifest['parent_sha256'],
        'panel_sha256': b.digest(PANEL.read_bytes()), 'deps_digest': panel['deps_digest'],
        'summary': summary, 'rows': rows, 'selection_eligible': False, 'release_eligible': False,
        'scope': '独立算术另行审查；改选与SCORED不等于数学正确或算法更强'})
    print(name, summary, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['freeze', 'check'])
    parser.add_argument('--name', choices=experiment.CONFIGS)
    args = parser.parse_args()
    if args.action == 'freeze':
        freeze()
    elif args.name:
        check(args.name)
    else:
        parser.error('check需要name')
