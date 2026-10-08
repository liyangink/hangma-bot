"""固定104输入的策略耗时诊断：不含规则分析、HTTP、并发调度，不作为发布时限门禁。"""

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
import asyncio
import math
import statistics
import time

import strong_seed_batch as b
import discard_tradeoff_batch as experiment
import discard_tradeoff_checks as checks
from hangma_bot.policy.action_value_seeds import ActionValueScorer
from hangma_bot.policy.action_value_policy import ActionValuePolicy


async def measure():
    """父子交错测量3遍，使用单调墙钟毫秒；已有请求的规则事实不重新计算。"""
    sub = experiment.OUT / experiment.NAME
    output = sub / 'policy-latency-diagnostic.json'
    assert not output.exists()
    state = b.search.av_state_load(b.search.av_latest_state_path(sub / 'run'))
    candidate = b.Path(state['iter_dir']) / 'generation/candidate.py'
    parent = b.Path(b.read(experiment.OUT / 'manifest.json')['parent']) / 'candidate.py'
    sources = {'parent': parent, 'candidate': candidate}
    assert b.read(sub / 'source-review.json')['source_sha256'] == b.digest(candidate.read_bytes())
    panel = b.read(checks.PANEL)
    assert panel['deps_digest'] == b.search.av_gates().av_deps_digest()
    inputs = [(row['origin'], row['name'], checks.inherited.helper.decision_request_from_json(row['record']['request'])) for row in panel['rows']]
    policies, load_ms, rows = {}, {}, []
    for label, source in sources.items():
        begin = time.perf_counter()
        policies[label] = ActionValuePolicy(ActionValueScorer(label, source.read_text()))
        load_ms[label] = (time.perf_counter() - begin) * 1000
    for repeat in range(3):
        for origin, name, request in inputs:
            labels = ('parent', 'candidate') if repeat % 2 == 0 else ('candidate', 'parent')
            for label in labels:
                now = time.monotonic()
                budget = b.behavior.DecisionBudget(now + 0.8, now + 0.9, now + 1.0)
                start = time.perf_counter()
                plan = await policies[label].choose(request, budget)
                elapsed = (time.perf_counter() - start) * 1000
                rows.append({'repeat': repeat, 'origin': origin, 'name': name, 'source': label,
                    'elapsed_ms': elapsed, 'first': plan.candidates[0].action_key if plan.candidates else None,
                    'legal_actions': len(request.rules.legal_candidates)})
    summaries = {}
    for label in policies:
        values = sorted(r['elapsed_ms'] for r in rows if r['source'] == label)
        summaries[label] = {'calls': len(values), 'load_ms': load_ms[label], 'median_ms': statistics.median(values),
            'p95_ms': values[math.ceil(0.95 * len(values)) - 1], 'max_ms': max(values),
            'over_800ms': sum(v > 800 for v in values)}
    b.write(output, {'scope': '104固定输入各3遍策略choose墙钟；含评分视图投影/受限评分/计划组装，不含规则分析、协议、并发、网络或生产截止调度',
        'sources': {k: {'path': str(v), 'sha256': b.digest(v.read_bytes())} for k, v in sources.items()},
        'panel_sha256': b.digest(checks.PANEL.read_bytes()), 'deps_digest': panel['deps_digest'],
        'summary': summaries, 'rows': rows, 'background': '同机完整自然评测进行中，时间含该负载且有测量噪声',
        'additional_tables': 0, 'model_calls': 0, 'release_eligible': False,
        'limitations': '样本有限，重复不独立；未覆盖最坏输入和真实1秒/3秒动作闭环，不按此测量放行发布'})
    print(summaries, flush=True)


if __name__ == '__main__':
    asyncio.run(measure())
