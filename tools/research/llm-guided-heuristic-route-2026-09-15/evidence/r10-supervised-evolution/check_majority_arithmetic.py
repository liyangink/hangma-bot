"""成对多数结构的独立手算：三轴多数、循环平票、未知锚定及四座门线重算。"""

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
import dataclasses

import strong_seed_batch as b
import diverse_proposal_batch as experiment
from check_simplify_arithmetic import action
from hangma_bot.hangma.interface import Settlement
from hangma_bot.kernel.actions import Hu
from hangma_bot.policy.action_value import ActionView, CompetitionView
from hangma_bot.policy.action_value_seeds import ActionValueScorer, build_sample_view


def route(delta, support=4):
    """生成合成合同算术输入；条件结算向量按0—3座，焦点为0。"""
    return {'shanten': 0, 'useful_tiles': ({'code': '1t', 'remaining_estimate': support},),
        'conditional_settlement': {'score_delta': (delta, -delta / 3, -delta / 3, -delta / 3),
                                   'self_delta': delta, 'fan': delta / 6},
        'conditions': {'draw_kind': 'normal'}}


def run():
    """期望值是独立列举的两两投票，不调用候选内部函数产生答案。"""
    sub = experiment.OUT / 'structure-sol-high'
    source = sub / 'run/iterations/iter-01/generation/candidate.py'
    output = sub / 'independent-arithmetic.json'
    assert not output.exists()
    scorer = ActionValueScorer('majority-arithmetic', source.read_text())
    a = action('1w', 1, 4, (route(24),), 'SAME')
    z = action('2w', 2, 4, (route(72),), 'ADVANCE')
    empty = CompetitionView()
    cases = [
        ('two_to_one_majority', (a, z), empty, [-1, 1]),
        ('remove_family_axis_tie', (dataclasses.replace(a, family_progress='UNKNOWN'), dataclasses.replace(z, family_progress='UNKNOWN')), empty, [0, 0]),
        # A胜B（速度+家族），B胜C（速度+条件幅度），C胜A（幅度+家族）：三者净胜负均0。
        ('three_action_cycle', (action('1w', 0, 4, (route(24),), 'SAME'), action('2w', 1, 4, (route(72),), 'RETREAT'), action('3w', 2, 4, (route(48),), 'ADVANCE')), empty, [0, 0, 0]),
        ('unknown_below_negative_known', (a, z, action('3w')), empty, [-1, 1, -2]),
        ('only_route_and_only_tempo_remain_known', (action('1w', routes=(route(24),)), action('2w', 1, 4)), empty, [0, 0]),
        ('all_unknown_abstains', (action('1w'), action('2w')), empty, None),
        ('boolean_route_support_is_unknown', (action('1w', routes=(route(24, True),)), action('2w', routes=(route(24, None),))), empty, [0, 0]),
    ]
    hu = ActionView(action_key='hu', action=Hu(), action_type='hu', is_legal=True,
                    fact_kind='win', shanten_after=-1, immediate_settlement=Settlement((24, -8, -8, -8), 4, ()), family_progress='SAME')
    comp = CompetitionView(stage_scores=(0, 10, 20, 30), table_scores=(0, 0, 0, 0),
        current_stage_scores=(0, 10, 20, 30), freshness_masks=('stage_account:complete', 'table_account:live'))
    cases.append(('four_seat_moving_threshold', (a, hu), comp, [-1, 1]))
    cases.append(('stale_stage_not_substituted_by_table', (a, hu), dataclasses.replace(comp, freshness_masks=('stage_account:stale', 'table_account:live')), [-1, 1]))
    rows = []
    for name, actions, competition, expected in cases:
        view = dataclasses.replace(build_sample_view(), actions=actions, competition=competition)
        batch = scorer.score(view)
        if expected is None:
            assert batch.status == 'ABSTAIN'
        else:
            assert batch.status == 'SCORED', (name, batch.status, batch.reason)
            entries = {e.action_key: e for e in batch.entries}
            actual = [entries[item.action_key].score for item in actions]
            assert actual == expected, (name, actual, expected)
            if name == 'four_seat_moving_threshold':
                # 0座加24后，向量为(24,2,12,22)，第2名线22、第3名线12。
                assert entries['hu'].trace['stage'] == {'mode': 'recompute', 'class': 3, 'inside_gap': 2.0, 'outside_gap': 12.0}
                assert entries['discard:1w'].trace['stage']['inside_gap'] == -20
                assert entries['discard:1w'].trace['stage']['outside_gap'] == -10
            if name == 'stale_stage_not_substituted_by_table':
                assert all(e.trace['stage']['class'] is None for e in entries.values())
            if name == 'boolean_route_support_is_unknown':
                assert all(e.trace['settlement_opportunity']['support_remaining'] is None for e in entries.values())
            if name == 'only_route_and_only_tempo_remain_known':
                assert entries['discard:1w'].trace['settlement_opportunity']['self_delta'] == 24
                assert entries['discard:2w'].trace['tempo']['shanten'] == 1
        rows.append({'name': name, 'expected': expected, 'status': batch.status,
                     'entries': [{'key': e.action_key, 'score': e.score, 'trace': dict(e.trace)} for e in batch.entries]})
    b.write(output, {'status': 'PASS', 'cases': len(rows), 'rows': rows,
        'source_sha256': b.digest(source.read_bytes()), 'deps_digest': b.search.av_gates().av_deps_digest(),
        'scope': '合成合同算术，不代替规则可达或强度；多数循环和信息稀疏平票为已知结构局限',
        'selection_eligible': False, 'release_eligible': False})
    print({'status': 'PASS', 'cases': len(rows)})


if __name__ == '__main__':
    run()
