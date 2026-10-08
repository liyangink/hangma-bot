"""复用生产评分与参考执行器，核验作者前冻结的112个诊断输入。"""

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
import json
import subprocess
import sys

import strong_seed_batch as b
import pattern_option_batch as batch
import diverse_proposal_checks as inherited
import check_candidate_python_semantics as semantics
from hangma_bot.policy.action_value_seeds import ActionValueScorer

PANEL = b.HERE / 'stage-rank-preflight-20260920/panel.json'


def behavior():
    """保存全112窗分数/顺序差异，额外报告没有弃牌的输入是否被意外改动。"""
    inherited.PANEL = PANEL
    inherited.experiment.OUT = batch.OUT
    inherited.check(batch.NAME)
    sub = batch.OUT / batch.NAME
    base = b.read(sub / 'diagnostic-comparison.json')
    panel = b.read(PANEL)
    by_name = {(row['origin'], row['name']): row for row in panel['rows']}
    origins = {}
    no_discard = []
    for row in base['rows']:
        origin = row['origin']
        counts = origins.setdefault(origin, {'inputs': 0, 'candidate_scored': 0, 'first_changed': 0, 'order_changed': 0, 'scores_changed': 0})
        counts['inputs'] += 1
        counts['candidate_scored'] += row['results']['candidate']['status'] == 'SCORED'
        for key in ('first_changed', 'order_changed', 'scores_changed'):
            counts[key] += row[key]
        original = by_name[(origin, row['name'])]['record']
        request = inherited.helper.decision_request_from_json(original['request'])
        view = inherited.helper.build_scoring_view(request)
        if not any(action.action_type == 'discard' for action in view.actions):
            no_discard.append({'origin': origin, 'name': row['name'],
                'first_changed': row['first_changed'], 'order_changed': row['order_changed'],
                'scores_changed': row['scores_changed']})
    # 单独输出扩展统计，保留复用检查器原始证据，不把新24窗漏出总结。
    b.write(sub / 'diagnostic-scope-summary.json', {'summary': origins, 'no_discard': no_discard,
        'source_sha256': base['source_sha256'], 'panel_sha256': base['panel_sha256'],
        'scope': '有限输入行为验收；非弃牌排序/评分变化需源码裁定，不直接当强度收益',
        'release_eligible': False})
    print(origins, flush=True)


def reference(worker=False):
    """重用已有白名单参考实现，独立子进程限30秒；不替换生产评分通道。"""
    semantics.experiment.OUT = batch.OUT
    semantics.checks.PANEL = PANEL
    if worker:
        state = b.search.av_state_load(b.search.av_latest_state_path(batch.OUT / batch.NAME / 'run'))
        semantics.worker(batch.NAME, b.Path(state['iter_dir']) / 'generation/candidate.py')
        return
    output = batch.OUT / batch.NAME / 'python-semantics-check.json'
    assert not output.exists()
    completed = subprocess.run([sys.executable, __file__, 'reference', '--worker'],
        capture_output=True, text=True, timeout=30, check=True)
    result = json.loads(completed.stdout)
    result['scope'] = '112个作者前冻结输入的标准Python/受限执行器分数与trace逐项对照；非全域证明'
    result['reference_runner_sha256'] = b.digest(b.Path(semantics.__file__).read_bytes())
    result['adapter_runner_sha256'] = b.digest(b.Path(__file__).read_bytes())
    assert result['cases'] == len(b.read(PANEL)['rows']) == 112
    b.write(output, result)
    assert result['status'] == 'PASS'
    print('PASS', result['cases'], flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['behavior', 'reference'])
    parser.add_argument('--worker', action='store_true')
    args = parser.parse_args()
    behavior() if args.action == 'behavior' else reference(args.worker)
