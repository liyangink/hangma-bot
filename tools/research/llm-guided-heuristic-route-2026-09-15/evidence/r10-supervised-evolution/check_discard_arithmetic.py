"""独立合成算术与多动作反例检查；只用合法评分合同形状，不冒充历史可达牌局。"""

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
import math

import strong_seed_batch as b
import discard_tradeoff_batch as experiment
from hangma_bot.kernel.actions import Discard, Hu, Pass, Peng, Tile
from hangma_bot.kernel.observation import PublicMeld
from hangma_bot.hangma.interface import UsefulTileFact
from hangma_bot.policy.action_value import ActionView
from hangma_bot.policy.action_value_seeds import ActionValueScorer, build_sample_view


def action(code, support=None, shanten=1, kind='discard'):
    """支持枚数分摊到不同牌码，每牌至多4张；None表示无直接牌效事实。"""
    obj = Discard(Tile(code)) if kind == 'discard' else Peng(Tile(code)) if kind == 'peng' else Hu() if kind == 'hu' else Pass()
    key = kind + ':' + code if kind in ('discard', 'peng') else kind
    facts = []
    if support is not None:
        remaining = support
        for tile in ('1t', '2t', '3t', '4t', '5t'):
            amount = min(remaining, 4)
            if amount > 0:
                facts.append(UsefulTileFact(tile, amount))
            remaining -= amount
        assert remaining == 0
    return ActionView(action_key=key, action=obj, action_type=kind, is_legal=True,
        fact_kind='hand_progress' if support is not None else 'analysis_failed',
        shanten_after=shanten if support is not None else None, useful_tiles=tuple(facts),
        family_progress='UNKNOWN', value_coverage='partial')


def view(actions, familiar=('8t',), near=False):
    """四座信息按0到3；焦点座位0并列领先，熟张公开于座位1。"""
    sample = build_sample_view()
    melds = ((), (PublicMeld(1, 'chi', tuple(Tile(c) for c in ('4b', '5b', '6b')), 0),), (), ()) if near else ((), (), (), ())
    obs = dataclasses.replace(sample.visible_state, discards=((), tuple(Tile(c) for c in familiar), (), ()), melds=melds)
    return dataclasses.replace(sample, visible_state=obs, actions=tuple(sorted(actions, key=lambda a: a.action_key)))


def cases():
    """期望来自独立分项与声明边界；不复制候选的锚点循环作为判据。"""
    a, z = action('4b', 11), action('8t', 10)
    return [
        ('two_discard_nonzero', view((a, z)), {'scores': {'discard:4b': -89, 'discard:8t': -89.001}, 'first': 'discard:4b'}),
        ('equal_support_keeps_public_preference', view((a, action('8t', 11))), {'same_parent': True, 'first': 'discard:8t'}),
        ('one_support_public_near_exception', view((a, z), near=True), {'same_parent': True, 'first': 'discard:8t'}),
        ('two_support_not_exception', view((action('4b', 12), z), near=True), {'scores': {'discard:4b': -94, 'discard:8t': -94.001}, 'first': 'discard:4b'}),
        ('three_discard_stale_anchor', view((action('4b', 12), action('8t', 11), action('9w', 10)), familiar=('8t', '9w')), {'first': 'discard:4b', 'known_max_support_must_win': True}),
        ('different_shanten_unchanged', view((action('4b', 12, 2), z)), {'same_parent': True}),
        ('wealth_cost_group_unchanged', view((action('白', 12), z)), {'same_parent': True}),
        ('single_known_unchanged', view((a,)), {'same_parent': True}),
        ('non_discard_unchanged', view((action('4b', 11, kind='peng'), action('', 10, kind='pass'))), {'same_parent': True}),
        ('unknown_below_guarded_negative', view((a, z, action('', kind='pass'))), {'unknown_floor': True, 'first': 'discard:4b'}),
        ('hu_dynamic_priority', view((a, z, action('', kind='hu'))), {'first': 'hu'}),
        ('all_unknown_abstains', view((action('4b'), action('8t'))), {'status': 'ABSTAIN'}),
    ]


def run(initial=False):
    """首答必须暴露反例；修复以同一组预先实现的检查验收，不重写历史结果。"""
    sub = experiment.OUT / experiment.NAME
    state = b.search.av_state_load(b.search.av_latest_state_path(sub / 'run'))
    idir = sub / 'run/iterations/iter-01' if initial else b.Path(state['iter_dir'])
    source = idir / 'generation/candidate.py'
    output = sub / ('first-answer' if initial else '.') / 'independent-arithmetic.json'
    assert not output.exists()
    parent = b.Path(b.read(experiment.OUT / 'manifest.json')['parent']) / 'candidate.py'
    scorers = {'parent': ActionValueScorer('parent', parent.read_text()), 'candidate': ActionValueScorer('candidate', source.read_text())}
    rows = []
    for name, sample, expected in cases():
        actual = {}
        for label, scorer in scorers.items():
            scored = scorer.score(sample)
            actual[label] = {'status': scored.status, 'scores': {e.action_key: e.score for e in scored.entries},
                'order': [e.action_key for e in sorted(scored.entries, key=lambda e: (-e.score, e.action_key))],
                'trace': {e.action_key: dict(e.trace) for e in scored.entries}}
        got, old = actual['candidate'], actual['parent']
        problems = []
        if got['status'] != expected.get('status', 'SCORED'):
            problems.append('status')
        if 'first' in expected and got['order'][:1] != [expected['first']]:
            problems.append('first')
        if expected.get('same_parent') and (got['scores'] != old['scores'] or got['order'] != old['order']):
            problems.append('non_target_change')
        for key, target in expected.get('scores', {}).items():
            if key not in got['scores'] or not math.isclose(got['scores'][key], target, rel_tol=0, abs_tol=1e-9):
                problems.append('arithmetic:' + key)
        if expected.get('unknown_floor'):
            target = min(value for key, value in got['scores'].items() if key != 'pass') - 1
            if got['scores'].get('pass') != target:
                problems.append('unknown_floor')
        rows.append({'name': name, 'expected': expected, 'pass': not problems, 'problems': problems, 'actual': actual})
    report = {'status': 'PASS' if all(r['pass'] for r in rows) else 'FAIL', 'cases': len(rows), 'rows': rows,
        'source_sha256': b.digest(source.read_bytes()), 'parent_sha256': b.digest(parent.read_bytes()),
        'runner_sha256': b.digest(b.Path(__file__).read_bytes()), 'scope': '合成合同算术，不证明规则可达或效果；三动作首选期望独立于锚点实现',
        'release_eligible': False}
    b.write(output, report)
    print(report['status'], [(r['name'], r['problems']) for r in rows if not r['pass']], flush=True)
    if not initial:
        assert report['status'] == 'PASS'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--initial', action='store_true')
    run(parser.parse_args().initial)
