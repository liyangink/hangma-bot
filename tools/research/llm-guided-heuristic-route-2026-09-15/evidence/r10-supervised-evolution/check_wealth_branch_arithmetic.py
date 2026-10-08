"""通过规则生成的必弃白后继及去代价消融，检查候选实际评分算术。"""

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
import sys

import strong_seed_batch as b
import branch_wealth_batch as experiment
import wealth_branch_probe as probe
from hangma_bot.kernel.observation import PublicMeld


def main():
    """只执行评分；工程消融不属于作者交付，不产生完整桌赛效果成绩。"""
    sub = experiment.ROOT / experiment.NAME
    source_path = sub / 'run/iterations/iter-01/generation/candidate.py'
    source = source_path.read_text()
    target = 'wealth_part_value = -65.0'
    assert source.count(target) == 2
    ablated = source.replace(target, 'wealth_part_value = 0.0')
    scorers = {'candidate': probe.ActionValueScorer('candidate', source),
               'without_call_wealth_cost': probe.ActionValueScorer('engineering-ablation', ablated)}
    output = sub / 'wealth-arithmetic-check.json'
    if output.exists():
        raise SystemExit('已检查，不覆盖')
    views = []
    _, real = b.behavior.load_panel(b.HERE / 'batch03-known-root-diagnostic/panel.json')
    views.extend(('real-' + name, probe.build_scoring_view(request)) for name, request in real)
    for row in b.read(probe.PANEL)['rows']:
        request = probe.decision_request_from_json(row['record']['request'])
        views.append((row['name'], probe.build_scoring_view(request)))
    # 补充探针在读完作者源码后设计，显式与此前冻结24条件分开；不用于强度选留。
    supplementary = []
    rules = probe.HangmaRules(probe.RuleConfig('hangma-mvp-v10-public-counts', 1, False))
    melds = tuple(PublicMeld(0, 'peng', (probe.Tile(code),) * 3, 3)
                  for code in ('1t', '2t', '3t'))
    for kind, hand, claim in (('chi', '1b 2b 白 白', '3b'),
                              ('peng', '5w 5w 白 白', '5w')):
        for dealer in (0, 1):
            obs = probe._observation(hand, response=claim, dealer=dealer, melds=melds)
            obs = dataclasses.replace(obs, phase='response_' + kind)
            analysis = rules.analyze(obs, value_limits=probe.ValueAnalysisLimits())
            request = probe.make_request(obs, analysis)
            view = probe.build_scoring_view(request)
            calls = [a for a in view.candidate_view()['actions'] if a['action_type'] == kind]
            assert calls and all(len(a['followup_branches']) == 1 and
                                 a['followup_branches'][0]['followup_discard'] == '白' for a in calls)
            name = 'supplementary-required-wealth-' + kind + '-dealer' + str(dealer)
            supplementary.append({'name': name, 'record': b.behavior.capture_request(request)})
            views.append((name, view))
    changes = []
    active_selected = 0
    call_actions = 0
    noncall_actions = 0
    for name, view in views:
        batches = {key: scorer.score(view) for key, scorer in scorers.items()}
        assert all(batch.status == 'SCORED' for batch in batches.values())
        indexed = {key: {entry.action_key: entry for entry in batch.entries}
                   for key, batch in batches.items()}
        for action in view.actions:
            a = indexed['candidate'][action.action_key]
            z = indexed['without_call_wealth_cost'][action.action_key]
            if action.action_type not in ('chi', 'peng'):
                noncall_actions += 1
                assert a.score == z.score
                continue
            call_actions += 1
            delta = a.score - z.score
            assert -65.00000001 <= delta <= 0.00000001
            if not math.isclose(delta, 0, abs_tol=1e-10):
                changes.append({'window': name, 'action': action.action_key,
                                'candidate': a.score, 'without_cost': z.score})
            trace = a.trace
            if trace['wealth_retained_delta'] == -1:
                active_selected += 1
                assert trace['wealth_discard_penalty'] == -65
                if trace['selected_lane'] == 'bound_conditional_route':
                    expected = trace['route_raw_score'] - 65 + trace['call_commitment']
                else:
                    assert trace['selected_lane'] == 'followup_branch'
                    expected = trace['branch_card_score'] - 65 + trace['call_commitment']
                assert math.isclose(a.score, expected, abs_tol=1e-10)
    assert active_selected >= 4 and changes
    ablation_path = sub / 'engineering-no-call-wealth-cost.py'
    with ablation_path.open('x') as handle:
        handle.write(ablated)
    b.write(output, {'purpose': 'mechanism_arithmetic_only',
                     'candidate_source_sha256': b.digest(source.encode()),
                     'ablation_source_sha256': b.digest(ablated.encode()),
                     'runner_sha256': b.digest(b.Path(__file__).read_bytes()),
                     'execution_deps_digest': b.search.av_gates().av_deps_digest(),
                     'windows': len(views), 'noncall_unchanged': noncall_actions,
                     'call_actions': call_actions, 'selected_wealth_cost_verified': active_selected,
                     'changes': changes, 'supplementary_post_author_conditions': supplementary,
                     'scope': '32真实窗+24预冻结条件+4交付后补充条件；消融只去掉吃碰财神代价，不去掉同时发生的家族项变化；没有完整桌赛效果结论',
                     'selection_eligible': False, 'release_eligible': False})
    print({'windows': len(views), 'noncall_unchanged': noncall_actions,
           'selected_wealth_cost_verified': active_selected, 'changed_call_scores': len(changes)})


if __name__ == '__main__':
    main()
