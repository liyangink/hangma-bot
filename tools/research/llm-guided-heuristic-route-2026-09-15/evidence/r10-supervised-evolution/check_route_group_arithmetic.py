"""路线归并的独立算术、条件隔离与未知计数检查；合成合同输入，不是牌局样本。"""

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
import copy
import argparse
import dataclasses
import math
from fractions import Fraction

import strong_seed_batch as b
import route_group_batch as experiment
from hangma_bot.kernel.actions import Pass, Peng, Tile
from hangma_bot.policy.action_value import ActionView
from hangma_bot.policy.action_value_seeds import ActionValueScorer, build_sample_view


def route(code, support, delta, fan):
    """组装算术输入；四座积分向量按0—3座，焦点固定为0，不宣称规则引擎生成。"""
    return {'followup_discard': '8b', 'shanten': 0,
            'useful_tiles': ({'code': code, 'remaining_estimate': support},),
            'conditional_settlement': {'score_delta': (delta, -delta / 3, -delta / 3, -delta / 3),
                                       'self_delta': delta, 'fan': fan},
            'conditions': {'draw_kind': 'normal',
                           'pre_draw_hand': ('1w', '2w', '3w', '4w', '5w', '6w', '东', '东', '白', '白'),
                           'meld_count': 1, 'chain_count': 0, 'chain_piao': 0, 'baotou': False}}


def check(output_name='route-arithmetic-check.json'):
    """手算期望值与候选生产评分比较；不借用候选内部函数当参考实现。"""
    sub = experiment.ROOT / experiment.NAME
    output = sub / output_name
    if output.exists():
        raise SystemExit('已有证据，不覆盖')
    source = sub / 'run/iterations/iter-01/generation/candidate.py'
    scorer = ActionValueScorer('group-arithmetic', source.read_text())
    high = route('1t', 1, 96, 16)
    low = route('2t', 3, 24, 4)
    weighted_delta = Fraction(96 + 3 * 24, 4)
    weighted_fan = Fraction(16 + 3 * 4, 4)
    grouped = float(4 + weighted_delta / 10 + weighted_fan / 2)
    single_high = 1 + 0.10 * 96 + 0.50 * 16
    cases = [('same_successor', (high, low), grouped, False)]
    for field, value in (('followup_discard', '9b'), ('draw_kind', 'replacement'),
                         ('pre_draw_hand', ('白',) * 10), ('meld_count', 2),
                         ('chain_count', 1), ('chain_piao', 1), ('baotou', True)):
        other = copy.deepcopy(low)
        target = other if field == 'followup_discard' else other['conditions']
        target[field] = value
        cases.append(('separate_' + field, (high, other), single_high, False))
    duplicate = copy.deepcopy(low)
    duplicate['useful_tiles'] = ({'code': '1t', 'remaining_estimate': 3},)
    cases.append(('duplicate_conflict', (high, duplicate), -1.0, True))
    zero_high, zero_low = copy.deepcopy(high), copy.deepcopy(low)
    zero_high['useful_tiles'] = ({'code': '1t', 'remaining_estimate': 0},)
    zero_low['useful_tiles'] = ({'code': '2t', 'remaining_estimate': 0},)
    cases.append(('known_zero_support', (zero_high, zero_low), 0.0, False))
    boolean = copy.deepcopy(low)
    boolean['useful_tiles'] = ({'code': '2t', 'remaining_estimate': True},)
    cases.append(('boolean_support_not_counted', (high, boolean), single_high, False))
    unknown = copy.deepcopy(low)
    unknown['useful_tiles'] = ({'code': '2t', 'remaining_estimate': None},)
    cases.append(('unknown_support_not_counted', (high, unknown), single_high, False))
    limited = copy.deepcopy(high)
    limited['conditions'].pop('chain_piao')
    cases.append(('missing_condition_single_route_fallback', (limited,), single_high, False))
    rows = []
    for name, routes, expected, is_unknown in cases:
        call = ActionView(action_key='peng:5w', action=Peng(Tile('5w')), action_type='peng',
            is_legal=True, fact_kind='analysis_failed', routes=routes, value_coverage='partial')
        passed = ActionView(action_key='pass', action=Pass(), action_type='pass',
                           is_legal=True, fact_kind='not_applicable')
        view = dataclasses.replace(build_sample_view(), actions=(passed, call))
        assert view.candidate_view()['visible_state']['seat'] == 0
        batch = scorer.score(view)
        assert batch.status == 'SCORED', (name, batch.status)
        entry = next(e for e in batch.entries if e.action_key == 'peng:5w')
        passed_check = (math.isclose(entry.score, expected, rel_tol=0, abs_tol=1e-9)
                        and entry.trace['unknown'] is is_unknown
                        and (is_unknown or entry.trace['coverage_scope'] == 'limited_produced_routes'))
        rows.append({'name': name, 'expected': expected, 'actual': entry.score,
                     'passed': passed_check,
                     'trace': dict(entry.trace), 'routes': routes})
    status = 'PASS' if all(row['passed'] for row in rows) else 'FAIL'
    b.write(output, {'status': status, 'cases': len(rows), 'rows': rows,
        'source_sha256': b.digest(source.read_bytes()),
        'runner_sha256': b.digest(b.Path(__file__).read_bytes()),
        'execution_deps_digest': b.search.av_gates().av_deps_digest(),
        'scope': '合成合同算术：7个条件维度逐一隔离，重复冲突、零/布尔/未知支持、缺条件回退；不判断牌局可达或策略强度',
        'selection_eligible': False, 'release_eligible': False})
    print({'status': status, 'cases': len(rows), 'passed': sum(row['passed'] for row in rows)})
    assert status == 'PASS', '算术或退化合同检查失败；完整证据已保存'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-name', default='route-arithmetic-check.json')
    check(parser.parse_args().output_name)
