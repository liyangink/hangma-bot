"""离线差分诊断：已准入候选在标准Python和受限执行器上的评分与trace是否一致。"""

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
import builtins
import json
import subprocess
import sys

import strong_seed_batch as b
import diverse_proposal_batch as experiment
import diverse_proposal_checks as checks
import wealth_branch_probe as helper
from hangma_bot.policy.action_value_executor import ALLOWED_BUILTINS, static_check
from hangma_bot.policy.action_value_seeds import ActionValueScorer


def worker(name, source_path=None):
    """限时子进程仅执行静态校验通过的源码，白名单builtins与冻结可见输入。"""
    sub = experiment.OUT / name
    source = b.Path(source_path) if source_path is not None else sub / 'run/iterations/iter-01/generation/candidate.py'
    text = source.read_text()
    static_check(text)
    assert b.read(sub / 'source-review.json')['source_sha256'] == b.digest(source.read_bytes())
    panel = b.read(checks.PANEL)
    assert panel['deps_digest'] == b.search.av_gates().av_deps_digest()
    namespace = {'__builtins__': {key: getattr(builtins, key) for key in ALLOWED_BUILTINS}}
    exec(compile(text, 'reviewed-candidate-reference', 'exec'), namespace)
    scorer = ActionValueScorer('restricted-semantics-check', text)
    rows = []
    for row in panel['rows']:
        record = row['record']
        assert b.behavior.digest(record['request']) == record['request_sha256']
        request = helper.decision_request_from_json(record['request'])
        view = helper.build_scoring_view(request)
        plain = view.candidate_view()
        assert b.behavior.digest(plain) == record['candidate_view_sha256']
        native = namespace['score_actions'](plain)
        restricted = scorer.score(view)
        left = {'status': native['status'], 'entries': {e['action_key']: {'score': e['score'], 'trace': e['trace']} for e in native.get('entries', [])}}
        right = {'status': restricted.status, 'entries': {e.action_key: {'score': e.score, 'trace': dict(e.trace)} for e in restricted.entries}}
        # JSON统一元组/列表承载形态；分值、键和trace内容必须完全一致。
        same = json.dumps(left, sort_keys=True) == json.dumps(right, sort_keys=True)
        rows.append({'origin': row['origin'], 'name': row['name'], 'equal': same,
                     'native_sha256': b.behavior.digest(left), 'restricted_sha256': b.behavior.digest(right),
                     'difference': None if same else {'native': left, 'restricted': right}})
    print(json.dumps({'status': 'PASS' if all(r['equal'] for r in rows) else 'FAIL',
        'rows': rows, 'cases': len(rows), 'source_sha256': b.digest(source.read_bytes()),
        'panel_sha256': b.digest(checks.PANEL.read_bytes()), 'deps_digest': panel['deps_digest'],
        'scope': '80固定输入的跨执行器语义差分；不证明全域等价，不作为评分替代通道或强度样本',
        'selection_eligible': False, 'release_eligible': False}, ensure_ascii=False))


def run(name):
    """只作诊断，标准Python参考子进程最多30秒；不绕开生产评分器。"""
    output = experiment.OUT / name / 'python-semantics-check.json'
    assert not output.exists()
    completed = subprocess.run([sys.executable, __file__, name, '--worker'], capture_output=True,
                               text=True, timeout=30, check=True)
    result = json.loads(completed.stdout)
    b.write(output, result)
    print(name, result['status'], result['cases'], flush=True)
    assert result['status'] == 'PASS'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('name', choices=experiment.CONFIGS)
    parser.add_argument('--worker', action='store_true')
    args = parser.parse_args()
    worker(args.name) if args.worker else run(args.name)
