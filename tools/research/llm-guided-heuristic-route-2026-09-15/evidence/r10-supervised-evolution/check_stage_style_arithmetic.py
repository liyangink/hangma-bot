"""按手工枚举名次区间与分项验证阶段风格，不复用候选排名循环。"""

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
from dataclasses import replace

import strong_seed_batch as b
import stage_style_batch as experiment
import stage_style_boundary_inputs as frozen
from check_discard_arithmetic import action, view
from hangma_bot.policy.action_value import CompetitionView
from hangma_bot.policy.action_value_seeds import ActionValueScorer


def result(scorer, sample):
    """通过生产评分器取得可核对分项，分数单位为启发式评分点。"""
    scored = scorer.score(sample)
    return {'status': scored.status, 'scores': {e.action_key: e.score for e in scored.entries},
        'order': [e.action_key for e in sorted(scored.entries, key=lambda e: (-e.score, e.action_key))],
        'trace': {e.action_key: dict(e.trace) for e in scored.entries}}


def main():
    """24个事前输入，加原答手算复核；不将合成分数当赛事效果。"""
    sub = experiment.OUT / experiment.NAME
    state = b.search.av_state_load(b.search.av_latest_state_path(sub / 'run'))
    path = b.Path(state['iter_dir']) / 'generation/candidate.py'
    parent = b.Path(b.read(experiment.OUT / 'manifest.json')['parent']) / 'candidate.py'
    scorers = {name: ActionValueScorer(name, source.read_text())
        for name, source in [('parent', parent), ('candidate', path)]}
    expected_positions = {
        'strict_first': ('IN', 1, 1), 'strict_second': ('IN', 2, 2),
        'strict_third': ('OUT', 3, 3), 'strict_last': ('OUT', 4, 4),
        'tie_first_two': ('IN', 1, 2), 'tie_second_third': ('UNRESOLVED', 2, 3),
        'tie_first_three': ('UNRESOLVED', 1, 3), 'tie_all': ('UNRESOLVED', 1, 4),
        'tie_last_two': ('OUT', 3, 4),
    }
    # 4b: -100+15=-85；熟8t: -100+10+3=-87；风格独立加4或2。
    expected_scores = {'IN': {'discard:4b': -85, 'discard:8t': -83},
        'OUT': {'discard:4b': -83, 'discard:8t': -85},
        'UNRESOLVED': {'discard:4b': -85, 'discard:8t': -87}}
    inputs = b.read(frozen.PATH)
    assert inputs['runner_sha256'] == b.digest(b.Path(frozen.__file__).read_bytes())
    cases = frozen.cases()
    assert len(cases) == len(inputs['rows']) == 24
    rows = []
    for (name, sample), saved in zip(cases, inputs['rows'], strict=True):
        assert saved['name'] == name
        assert b.behavior.digest(saved['view']) == b.behavior.digest(sample.candidate_view())
        actual = {label: result(scorer, sample) for label, scorer in scorers.items()}
        got, old = actual['candidate'], actual['parent']
        base_name = name.removesuffix('_split')
        errors = []
        if base_name in expected_positions:
            status, low, high = expected_positions[base_name]
            if got['scores'] != expected_scores[status]:
                errors.append('independent_arithmetic')
            for trace in got['trace'].values():
                if (trace['stage_status'], trace['stage_rank_low'], trace['stage_rank_high']) != (status, low, high):
                    errors.append('rank_interval')
        elif name in ('no_competition', 'stage_account:absent', 'stage_account:unmappable', 'no_discard'):
            if got['status'] != old['status'] or got['scores'] != old['scores'] or got['order'] != old['order']:
                errors.append('fallback_or_non_target')
        elif name == 'hu_present':
            if got['scores'] != {**expected_scores['IN'], 'hu': -82} or got['order'][0] != 'hu':
                errors.append('hu_layer')
        elif name == 'unknown_floor':
            if got['scores'] != {**expected_scores['IN'], 'pass': -86}:
                errors.append('unknown_anchor')
        if name != 'no_discard' and got['status'] != 'SCORED':
            errors.append('unexpected_abstention')
        rows.append({'name': name, 'pass': not errors, 'errors': errors, 'actual': actual})
    # 原答手算漏掉熟张+3：保留原答，实际计算应为父(-94,-94)，子(-96,-92)。
    example = view((action('1w', 4), action('2w', 1)), familiar=('2w',))
    live = (-10, 30, 0, 0)
    current = (100, 80, 20, 0)
    example = replace(example, visible_state=replace(example.visible_state, scores=live),
        competition=CompetitionView(stage_scores=tuple(current[i]-live[i] for i in range(4)),
            table_scores=live, current_stage_scores=current,
            freshness_masks=('stage_account:complete', 'table_account:live')))
    example_results = {label: result(scorer, example) for label, scorer in scorers.items()}
    assert example_results['parent']['scores'] == {'discard:1w': -94, 'discard:2w': -94}
    assert example_results['candidate']['scores'] == {'discard:1w': -96, 'discard:2w': -92}
    assert example_results['parent']['order'][0] == 'discard:1w'
    assert example_results['candidate']['order'][0] == 'discard:2w'
    output = sub / 'independent-arithmetic.json'
    assert not output.exists()
    report = {'status': 'PASS' if all(r['pass'] for r in rows) else 'FAIL',
        'cases': len(rows), 'rows': rows, 'source_sha256': b.digest(path.read_bytes()),
        'boundary_input_sha256': b.digest(frozen.PATH.read_bytes()),
        'author_example': {'status': 'EXPLANATION_ARITHMETIC_CORRECTED',
            'error': '原答漏熟张基础+3；代码保留该项，首选反转方向仍成立',
            'results': example_results,
            'scope': '合成合同示例，不声称真实可达；非新的作者答复或源码修复'},
        'scope': '独立算术、排名边界与账拆分检查，不是强度样本', 'release_eligible': False}
    b.write(output, report)
    print(report['status'], [(r['name'], r['errors']) for r in rows if not r['pass']], flush=True)
    assert report['status'] == 'PASS'


if __name__ == '__main__':
    main()
