"""财神后继机制的规则生成条件探针；不作为自然轨迹或效果样本。"""

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
import json
import sys

import strong_seed_batch as b
import branch_wealth_batch as experiment
sys.path.insert(0, str(b.ROUTE.parents[1]))
from tests.unit.hangma.test_value_analysis import _observation
from tests.unit.policy.support import make_request
from hangma_bot.application.audit_codec import decision_request_from_json
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.policy.action_value_policy import build_scoring_view
from hangma_bot.policy.action_value_seeds import ActionValueScorer

PANEL = experiment.ROOT / 'rule-condition-panel.json'
HANDS = (
    ('peng_two_wealth', '5w 5w 1t 2t 3t 4t 5t 6t 7t 8t 9t 白 白', '5w', 'response_peng'),
    ('peng_one_wealth', '5w 5w 1t 2t 3t 4t 5t 6t 7t 8t 9t 东 白', '5w', 'response_peng'),
    ('peng_three_wealth', '5w 5w 1t 2t 3t 4t 5t 6t 7t 8t 白 白 白', '5w', 'response_peng'),
    ('chi_two_wealth', '1w 2w 1t 2t 3t 4t 5t 6t 7t 8t 9t 白 白', '3w', 'response_chi'),
    ('chi_one_wealth', '1w 2w 1t 2t 3t 4t 5t 6t 7t 8t 9t 东 白', '3w', 'response_chi'),
    ('peng_no_wealth_control', '5w 5w 1t 2t 3t 4t 5t 6t 7t 8t 9t 东 东', '5w', 'response_peng'),
)


def freeze():
    """候选交付前冻结六种牌形×两种既有飘数×庄闲，全部动作由规则引擎产生。"""
    if PANEL.exists():
        raise SystemExit('条件清单已冻结，不覆盖')
    rules = HangmaRules(RuleConfig('hangma-mvp-v10-public-counts', 1, False))
    rows = []
    for name, hand, response, phase in HANDS:
        for piao in (0, 1):
            for dealer in (0, 1):
                obs = _observation(hand, response=response, dealer=dealer,
                                   chain=piao, piao=piao)
                rivers = list(obs.discards)
                rivers[0] = (Tile('白'),) * piao
                state = dataclasses.replace(obs.rule_state, catch_play=bool(piao),
                                            catch_play_owner_seat=0 if piao else None,
                                            baotou=bool(piao))
                obs = dataclasses.replace(obs, phase=phase, discards=tuple(rivers),
                                          rule_state=state)
                assert hand.split().count('白') + piao <= 4
                analysis = rules.analyze(obs, value_limits=ValueAnalysisLimits())
                request = make_request(obs, analysis)
                view = build_scoring_view(request)
                calls = [a for a in view.candidate_view()['actions']
                         if a['action_type'] in ('chi', 'peng')]
                assert calls and any(a.action_key == 'pass' for a in view.actions)
                assert all(a.get('followup_branches') for a in calls)
                rows.append({'name': f'{name}-piao{piao}-dealer{dealer}',
                             'record': b.behavior.capture_request(request)})
    b.write(PANEL, {'schema': 'wealth-branch-rule-condition/1',
                    'purpose': 'rule_generated_condition_probe',
                    'scope': '合成可见观察由唯一规则引擎生成合法动作和分值；不证明历史可达或官方赛事强度',
                    'created_at_utc': b.search.utc_now(),
                    'runner_sha256': b.digest(b.Path(__file__).read_bytes()),
                    'execution_deps_digest': b.search.av_gates().av_deps_digest(),
                    'rows': rows, 'selection_eligible': False})
    print({'frozen_conditions': len(rows), 'path': str(PANEL)})


def check():
    """经生产受限评分与 choose 检查完整排序，同时保存实际分支修正追踪。"""
    sub = experiment.ROOT / experiment.NAME
    output = sub / 'rule-condition-comparison.json'
    if output.exists():
        raise SystemExit('已有探针结果，不覆盖')
    panel = b.read(PANEL)
    assert panel['execution_deps_digest'] == b.search.av_gates().av_deps_digest()
    paths = {'parent': experiment.PARENT / 'candidate.py',
             'candidate': sub / 'run/iterations/iter-01/generation/candidate.py'}
    scorers = {name: ActionValueScorer(name, path.read_text()) for name, path in paths.items()}
    rows = []
    for row in panel['rows']:
        record = row['record']
        assert b.behavior.digest(record['request']) == record['request_sha256']
        request = decision_request_from_json(record['request'])
        view = build_scoring_view(request)
        assert b.behavior.digest(view.candidate_view()) == record['candidate_view_sha256']
        results = {}
        for name, scorer in scorers.items():
            result = b.behavior.evaluate_request(scorer, row['name'], request)
            batch = scorer.score(view)
            result['traces'] = {entry.action_key: dict(entry.trace) for entry in batch.entries}
            results[name] = result
        rows.append({'name': row['name'], 'results': results})
    report = {'scope': panel['scope'], 'panel_sha256': b.digest(PANEL.read_bytes()),
              'source_sha256': {name: b.digest(path.read_bytes()) for name, path in paths.items()},
              'conditions': len(rows),
              'fully_scored': all(r['status'] == 'SCORED' for row in rows for r in row['results'].values()),
              'changed_first_choices': sum(row['results']['parent']['action_key'] !=
                                           row['results']['candidate']['action_key'] for row in rows),
              'changed_scores': sum(row['results']['parent']['scores'] !=
                                     row['results']['candidate']['scores'] for row in rows),
              'rows': rows, 'selection_eligible': False}
    b.write(output, report)
    print(json.dumps({key: report[key] for key in ('conditions', 'fully_scored',
                                                   'changed_first_choices', 'changed_scores')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['freeze', 'check'])
    if parser.parse_args().action == 'freeze':
        freeze()
    else:
        check()
