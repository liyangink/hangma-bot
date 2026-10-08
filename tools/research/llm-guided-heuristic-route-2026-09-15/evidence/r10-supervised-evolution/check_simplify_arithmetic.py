"""独立核验路线兜底门控：手算分值、非零触发、已知零及完全未知，不代替牌局评测。"""

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
import math

import strong_seed_batch as b
import diverse_proposal_batch as experiment
from hangma_bot.kernel.actions import Discard, Tile
from hangma_bot.hangma.interface import UsefulTileFact
from hangma_bot.policy.action_value import ActionView
from hangma_bot.policy.action_value_seeds import ActionValueScorer, build_sample_view


def action(code, shanten=None, support=None, routes=(), family='UNKNOWN'):
    """合成公开评分输入；全部为弃牌族，不宣称由规则引擎生成或牌局历史可达。"""
    return ActionView(action_key='discard:' + code, action=Discard(Tile(code)),
        action_type='discard', is_legal=True,
        fact_kind='hand_progress' if shanten is not None else 'analysis_failed',
        shanten_after=shanten, useful_tiles=() if support is None else (UsefulTileFact('1t', support),),
        routes=routes, family_progress=family, value_coverage='partial')


def run():
    """独立期望来自明确算术；另逐字逆变换证明只改一项门控和说明。"""
    sub = experiment.OUT / 'simplify-terra-max'
    output = sub / 'independent-arithmetic.json'
    assert not output.exists()
    manifest = b.read(experiment.OUT / 'manifest.json')
    parent_path = b.Path(manifest['parent']) / 'candidate.py'
    source_path = sub / 'run/iterations/iter-01/generation/candidate.py'
    parent, source = parent_path.read_text(), source_path.read_text()
    expected_source = parent.replace(parent.splitlines()[0], source.splitlines()[0], 1)
    removed = '        route = route_record(action.get("routes"), seat)\n        if route is not None:\n            records.append(route)\n\n'
    inserted = '        if len(records) == 0:\n            route = route_record(action.get("routes"), seat)\n            if route is not None:\n                records.append(route)\n\n'
    assert expected_source.count(removed) == 1
    expected_source = expected_source.replace(removed, '').replace('        selected = pick_record(records)\n', inserted + '        selected = pick_record(records)\n')
    expected_source = expected_source.replace('conditional_route_wealth_recompute_v1', 'conditional_route_fallback_v1').replace('single_best_witness', 'fallback_only').replace('条件路线仅取单个已证实见证；未分析动作按已知最终最低分减一锚定', '条件路线只在无其他已证实读数时兜底；未分析动作按已知最终最低分减一锚定')
    assert source == expected_source, '出现门控之外未声明的可执行差异'
    scorers = {'parent': ActionValueScorer('parent', parent), 'candidate': ActionValueScorer('candidate', source)}
    route = {'shanten': 0, 'followup_discard': None,
        'useful_tiles': ({'code': '1t', 'remaining_estimate': 4},),
        'conditional_settlement': {'score_delta': (96, -32, -32, -32), 'self_delta': 96},
        'conditions': {'draw_kind': 'normal'}}
    direct = action('3w', 1, 4, (route,))
    competing = action('5b', 1, 3)
    # 非路线-90+4=-86，竞争者-90+3=-87；加一个不同有效牌使竞争者总支持5，分数-85。
    competing = dataclasses.replace(competing, useful_tiles=(UsefulTileFact('1t', 3), UsefulTileFact('2t', 2)))
    cases = [
        ('direct_route_override_removed', (direct, competing), {'parent': [13.6, -85], 'candidate': [-86, -85]}),
        ('independent_route_fallback_retained', (action('3w', routes=(route,)), competing), {'parent': [13.6, -85], 'candidate': [13.6, -85]}),
        ('no_route_unchanged', (dataclasses.replace(direct, routes=()), competing), {'parent': [-86, -85], 'candidate': [-86, -85]}),
        ('known_zero_is_not_missing', (action('3w', 0, 0, (route,)), competing), {'parent': [13.6, -85], 'candidate': [0, -85]}),
        ('family_known_zero_blocks_override', (action('3w', routes=(route,), family='SAME'), competing), {'parent': [13.6, -85], 'candidate': [0, -85]}),
        ('unknown_below_negative_known', (action('3w'), competing), {'parent': [-86, -85], 'candidate': [-86, -85]}),
        ('missing_route_settlement_no_fake_value', (action('3w', routes=({**route, 'conditional_settlement': None},)), competing), {'parent': [-86, -85], 'candidate': [-86, -85]}),
        ('all_unknown_abstains', (action('3w'), action('5b')), None),
    ]
    rows = []
    for name, actions, expected in cases:
        view = dataclasses.replace(build_sample_view(), actions=actions)
        assert view.candidate_view()['visible_state']['seat'] == 0
        result = {}
        for label, scorer in scorers.items():
            batch = scorer.score(view)
            if expected is None:
                assert batch.status == 'ABSTAIN'
            else:
                assert batch.status == 'SCORED', (name, label, batch.status)
                scores = {e.action_key: e.score for e in batch.entries}
                for action_item, value in zip(actions, expected[label], strict=True):
                    assert math.isclose(scores[action_item.action_key], value, rel_tol=0, abs_tol=1e-9), (name, label, scores, expected[label])
            result[label] = {'status': batch.status, 'entries': [{'key': e.action_key, 'score': e.score, 'trace': dict(e.trace)} for e in batch.entries]}
        rows.append({'name': name, 'expected': expected, 'actual': result})
    b.write(output, {'status': 'PASS', 'cases': len(rows), 'rows': rows,
        'source_sha256': b.digest(source_path.read_bytes()), 'parent_sha256': b.digest(parent_path.read_bytes()),
        'deps_digest': b.search.av_gates().av_deps_digest(), 'mechanical_scope_check': 'PASS',
        'scope': '合成合同算术，不判断规则可达；逆变换核对只有一处路线门控及说明变更',
        'selection_eligible': False, 'release_eligible': False})
    print({'status': 'PASS', 'cases': len(rows), 'mechanical_scope_check': 'PASS'})


if __name__ == '__main__':
    run()
