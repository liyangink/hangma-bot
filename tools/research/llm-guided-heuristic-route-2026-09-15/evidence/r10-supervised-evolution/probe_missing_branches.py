"""隔离分支牌效故障，验证独立已知条件路线是否被候选错误降为未知。"""

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
from unittest.mock import patch
import wealth_branch_probe as p
from hangma_bot.hangma.candidate_facts import FactsAnalysisError


if __name__ == '__main__':
    sub = p.experiment.ROOT / p.experiment.NAME
    output = sub / 'missing-branches-fault-probe.json'
    if output.exists():
        raise SystemExit('已有故障证据，不覆盖')
    sources = {'parent': p.experiment.PARENT / 'candidate.py',
               'candidate': sub / 'run/iterations/iter-01/generation/candidate.py'}
    scorers = {name: p.ActionValueScorer(name, path.read_text()) for name, path in sources.items()}
    rules = p.HangmaRules(p.RuleConfig('hangma-mvp-v10-public-counts', 1, False))
    rows = []
    for entry in p.b.read(p.PANEL)['rows']:
        observation = p.decision_request_from_json(entry['record']['request']).observation
        # 只故障注入一个事实生产子步骤；合法性、条件路线、进展及投影仍走生产入口。
        with patch('hangma_bot.hangma.candidate_facts._followup_branches',
                   side_effect=FactsAnalysisError('supervised isolated branch analysis fault')):
            analysis = rules.analyze(observation, value_limits=p.ValueAnalysisLimits())
        request = p.make_request(observation, analysis)
        view = p.build_scoring_view(request)
        actions = {a['action_key']: a for a in view.candidate_view()['actions']}
        batches = {name: scorer.score(view) for name, scorer in scorers.items()}
        assert all(batch.status == 'SCORED' for batch in batches.values())
        results = {name: {e.action_key: {'score': e.score, 'trace': dict(e.trace)}
                          for e in batch.entries} for name, batch in batches.items()}
        for key, action in actions.items():
            if action['action_type'] not in ('chi', 'peng') or not action['routes']:
                continue
            assert action['followup_branches'] is None
            assert results['parent'][key]['trace']['unknown'] is False
            rows.append({'name': entry['name'], 'action_key': key,
                         'known_route_count': len(action['routes']),
                         'results': {name: result[key] for name, result in results.items()},
                         'record': p.b.behavior.capture_request(request)})
    assert rows
    report = {'scope': '显式故障注入；证明生产故障隔离后输入可出现，不表示自然频率',
              'source_sha256': {name: p.b.digest(path.read_bytes()) for name, path in sources.items()},
              'runner_sha256': p.b.digest(p.b.Path(__file__).read_bytes()),
              'execution_deps_digest': p.b.search.av_gates().av_deps_digest(),
              'known_route_actions': len(rows),
              'candidate_marked_unknown': sum(row['results']['candidate']['trace']['unknown']
                                              for row in rows),
              'rows': rows, 'release_eligible': False}
    p.b.write(output, report)
    print({key: report[key] for key in ('known_route_actions', 'candidate_marked_unknown')})
