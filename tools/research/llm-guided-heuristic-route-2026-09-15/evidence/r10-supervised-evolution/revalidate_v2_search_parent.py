"""重新启用既有V2相近种子：当前核心重验、固定自然读数和正式M1反馈，零作者。"""

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
import diverse_second_panel as second
import route_executor_recovery as engine
import revalidate_route_feedback as feedback

OUT = b.HERE / 'v2-parent-revalidation-20260920'


def prepare():
    """诊断支持换回已有搜索起点；预登记260完整桌上限，不称该父代已增强。"""
    assert not OUT.exists()
    diagnosis = b.HERE / 'route-decision-diagnostic-20260920'
    assert b.read(diagnosis / 'summary.json')['status'] == 'COMPLETE_DIAGNOSTIC_ONLY'
    assert b.read(diagnosis / 'v2-seed-comparison.json')['summary']['seed_v2_first_equal'] == 24
    source = b.HERE / 'v2-seed-terra-02/run/iterations/iter-01/generation/candidate.py'
    plan = {**b.read(second.OUT / 'manifest.json'), 'created_at_utc': b.search.utc_now(),
        'sources': {'parent': {'path': str(source), 'sha256': b.digest(source.read_bytes())}},
        'panel_seed': 2026092001, 'tables_per_source': 256, 'max_full_tables': 256,
        'scope': '既有V2相近种子当前核心开发重验；非新增算法、非独立确认',
        'decision_rule': '完整结案及正式反馈可消费后才签发至多一份单机制M1；不由此晋升父代',
        'reason': '失利诊断24首选分歧窗中该种子与V2全匹配，原路线父代19处同分；这是行为保留证据而非最优性证明',
        'diagnostic_sha256': b.digest((diagnosis / 'v2-seed-comparison.json').read_bytes()),
        'model_calls': 0, 'confirmation_roots': 0, 'release_eligible': False}
    engine.verify(plan)
    OUT.mkdir()
    sub = OUT / 'parent'
    sub.mkdir()
    b.write(OUT / 'manifest.json', plan)
    admission = b.search.av_gates().admit_action_value(source.read_text())
    b.write(sub / 'admission.json', admission)
    assert admission['execution_safety_pass']
    auth = b.unified_document(batch_label='v2-parent-revalidation', authorization_id='r10-v2-parent-revalidation',
        accounts={'tables_full': 256}, issued_by='lead', issued_at_utc=b.search.utc_now(), legacy_alias=False)
    auth['issuance_basis'] = '用户持续监督搜索授权；新核心父代H/M各8根固定重验，256桌，零模型'
    b.write(sub / 'authorization.json', auth)
    engine.OUT = OUT
    engine.NAMES = ('parent',)
    feedback.prepare()
    b.write(OUT / 'prepared.json', {'status': 'READY', 'at_utc': b.search.utc_now()})
    print('prepared; natural256 + conditional<=4 full, no model', flush=True)


def close():
    """自然及条件两份账本结清后，消费公开M1反馈身份验证。"""
    plan = b.read(OUT / 'manifest.json')
    engine.verify(plan)
    assert not (OUT / 'summary.json').exists()
    sub = OUT / 'parent'
    natural_closure = b.read(sub / 'closure.json')
    condition = b.read(sub / 'feedback-conditional-closure.json')
    assert natural_closure['status'] == 'COMPLETE_DEVELOPMENT_ONLY' and condition['status'] == 'COMPLETE'
    statistics = {}
    for mix in ('H', 'M'):
        panel = b.read(sub / ('natural-' + mix) / 'panel.json')
        statistics[mix] = next(iter(panel['statistics']['by_candidate'].values()))['panels']['normal']['panels'][mix]
    b.write(OUT / 'summary.json', {'status': 'COMPLETE_DEVELOPMENT_ONLY', 'statistics': statistics,
        'full_natural_verified': 256, 'condition_spent': condition['spent'], 'model_calls': 0,
        'release_eligible': False, 'scope': '当前核心搜索父代；不声称全域V2等价或效果增强'})
    feedback.feedback()
    print({mix: s['mean_delta'] for mix, s in statistics.items()}, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'natural', 'conditional', 'close'])
    args = parser.parse_args()
    engine.OUT = OUT
    engine.NAMES = ('parent',)
    if args.action == 'prepare':
        prepare()
    elif args.action == 'natural':
        engine.run('parent')
    elif args.action == 'conditional':
        feedback.conditional('parent')
    else:
        close()
