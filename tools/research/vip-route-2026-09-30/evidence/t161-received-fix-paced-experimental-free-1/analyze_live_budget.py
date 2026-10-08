"""流式重读T161规范审计及RAW快照，定位预算损失，不发请求或续打。

只在原始可见快照中核对零规划窗口的基础合法动作；不补造当时策略输入，
不计算完整评分，也不把同水位/同快照重复观测等同于安全可省请求。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t161-received-fix-paced-experimental-free-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from bisect import bisect_right
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import statistics

from hangma_bot.adapters.official.dto import parse_state_response
from hangma_bot.adapters.official.projector import observation
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.kernel.config import RuleConfig

HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
RUN = _project_file(_PROJECT_ROOT, ROOT / 'artifacts/sessions/t161-vip-s02-free-v4-paced/audit/runs/run-2ed31bb1bf184a5c84e0329b883094e0')


def file_sha(path):
    """按1MiB块计算摘要，避免一次读入整个RAW文件。"""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def rows(path):
    """按原始行流式读，gzip与普通文件同口径；不合并成巨大状态字典。"""
    op = gzip.open if path.suffix == '.gz' else open
    with op(path, 'rt') as stream:
        for n, line in enumerate(stream, 1):
            yield n, json.loads(line)


def stats(values):
    """毫秒样本的观测摘要；p95按排序的95%位置，不拟合概率。"""
    values = sorted(values)
    return {'n': len(values), 'mean_ms': statistics.mean(values),
            'p95_ms': values[int(.95 * (len(values) - 1))], 'max_ms': values[-1]} if values else {'n': 0}


def main():
    """原件已自然闭合；保留失效窗与原快照的来源身份，读后验签不变。"""
    files = [_project_file(_PROJECT_ROOT, RUN / 'participants/u_13495c3d79c8/decisions.jsonl'),
             *sorted(RUN.glob('participants/*/games/*.jsonl')),
             *sorted(RUN.glob('participants/*/raw/*.jsonl*'))]
    assert (_project_file(_PROJECT_ROOT, RUN / 'summary.json')).is_file(), '仅能在本身份自然关闭后读取'
    sources = {str(p.relative_to(ROOT)): file_sha(p) for p in files}
    recovery, zero, cancel, frames = Counter(), [], [], defaultdict(list)
    for path in files:
        if 'raw' in path.parts:
            continue
        for n, record in rows(path):
            kind, d, c = record['kind'], record['payload'], record['context']
            if kind == 'protocol_recovered':
                reasons = d.get('reasons', []) + ([d['reason']] if d.get('reason') else [])
                for reason in reasons:
                    recovery[reason] += 1
                if any('零动作尝试' in reason for reason in d.get('reasons', [])):
                    zero.append({'source': str(path.relative_to(ROOT)), 'line': n, 'record': record})
            if kind == 'authoritative_state':
                if d.get('state_query_cancel_reason'):
                    cancel.append({'game': c['game_id'], 'time': record['monotonic_ns'] / 1e9, 'payload': d})
                if d.get('sse_frame_not_skipped'):
                    frames[c['game_id']].append((record['monotonic_ns'] / 1e9, d))
    by_game = defaultdict(list)
    for target in zero:
        by_game[target['record']['context']['game_id']].append(target)
    for targets in by_game.values():
        targets.sort(key=lambda x: x['record']['monotonic_ns'])
    frame_times = {}
    for game, values in frames.items():
        values.sort()
        frame_times[game] = [t for t, _ in values]
    requests, by_purpose, duplicates = set(), defaultdict(lambda: defaultdict(list)), Counter()
    same_seq, previous = Counter(), {}
    cancel_waits = defaultdict(list)
    for row in cancel:
        cancel_waits[row['payload']['state_query_cancel_reason']].append(row['payload'].get('purpose_wait_sec', 0) * 1000)
    for path in files:
        if 'raw' not in path.parts:
            continue
        for n, record in rows(path):
            d, c = record['payload'], record['context']
            if record['kind'] != 'raw_protocol_state' or d.get('source') != 'state_response':
                continue
            t, game = d.get('request_timing', {}), c['game_id']
            rid, purpose = t['request_id'], t.get('query_purpose')
            assert rid not in requests
            requests.add(rid)
            by_purpose[purpose]['statuses'].append(d.get('http_status'))
            for lo, hi, metric in [('queued_at_monotonic','granted_at_monotonic','queue'),
                                    ('transport_started_at_monotonic','completed_at_monotonic','transport')]:
                if lo in t and hi in t:
                    by_purpose[purpose][metric].append((t[hi] - t[lo]) * 1000)
            if d.get('http_status') != 200:
                continue
            body = json.loads(d['raw'])
            if 'snapshot' not in body:
                continue
            signature = hashlib.sha256(json.dumps(body['snapshot'], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            old = previous.get(game)
            if old and old['seq'] == body['seq']:
                same_seq[purpose] += 1
                if old['signature'] == signature:
                    duplicates[purpose] += 1
            previous[game] = {'seq': body['seq'], 'signature': signature}
            when = record['monotonic_ns'] / 1e9
            pos = bisect_right(frame_times.get(game, []), t['queued_at_monotonic']) - 1
            last_frame = frames[game][pos] if pos >= 0 else None
            for target in by_game[game]:
                previous_raw = target.get('latest_visible_raw')
                if (when <= target['record']['monotonic_ns'] / 1e9 and
                        (previous_raw is None or record['monotonic_ns'] > previous_raw['record']['monotonic_ns'])):
                    target['latest_visible_raw'] = {'source': str(path.relative_to(ROOT)), 'line': n,
                        'record': record, 'preceding_sse_frame': last_frame}
    # 这只验证最近完整可见快照的基础动作，不声称恢复遗漏增量后的全部当时事实。
    rules = HangmaRules(RuleConfig('hangma-v34', base_score=1, you_cai_bi_kao=False))
    for target in zero:
        raw = target.get('latest_visible_raw')
        if raw is None:
            target['legal_reconstruction_status'] = 'no_prior_visible_snapshot'
            continue
        parsed = parse_state_response(json.loads(raw['record']['payload']['raw']))
        obs = observation(parsed.snapshot, (), target['record']['context']['game_id'])
        window = target['record']['payload']['window']
        target['visible_snapshot_age_ms'] = (target['record']['monotonic_ns'] - raw['record']['monotonic_ns']) / 1e6
        target['same_phase_and_round'] = obs.phase == window['phase'] and obs.round_no == window['round_no']
        target['legal_reconstruction_status'] = 'prior_visible_snapshot_only_not_exact_original_request'
        target['prior_snapshot_legal_keys'] = [x.action_key for x in rules.analyze(obs).legal_candidates]
        # 控制输出量：原始RAW另包已封存；此文件保留直接来源行和所见完整快照。
    result = {'scope': 'read_only_closed_T161_budget_diagnostic', 'raw_state_response_records': len(requests),
        'recovery_reasons_all_canonical_game_and_decision_files': dict(recovery),
        'zero_plan_count': len(zero), 'zero_plan_visible_snapshot_reconstructions': zero,
        'query_stats_by_purpose': {k: {'http_status_counts': dict(Counter(v['statuses'])),
                 'queue': stats(v['queue']), 'transport': stats(v['transport']),
                 'same_seq_as_previous_state': same_seq[k], 'exact_same_snapshot_as_previous_state': duplicates[k]}
                 for k,v in by_purpose.items()},
        'expired_query_purpose_waits': {k: stats(v) for k,v in cancel_waits.items()},
        'interpretation': '重复观测不证明可安全跳过。零规划最近快照重建不是补造完整候选评分；未授强度、时限或发布。',
        'official_calls': 0, 'llm_calls': 0, 'full_candidate_score_calls': 0, 'sources_sha256': sources}
    assert all(file_sha(_project_file(_PROJECT_ROOT, ROOT/name)) == sha for name,sha in sources.items())
    with (_project_file(_PROJECT_ROOT, HERE / 'LIVE-BUDGET-DIAGNOSIS.json')).open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'zero_plan_count': len(zero), 'raw_state_response_records': len(requests),
                      'recovery_counts': dict(recovery), 'exact_same_snapshot_counts': dict(duplicates)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
