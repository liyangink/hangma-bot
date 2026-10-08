"""只读已关闭批次的状态请求时序；不调用规则、策略、HTTP 或完整决策流。

时刻使用本机单调秒，等待和间隔使用毫秒。只提取 /state 响应的调度事实；
429 未必出现在 raw_protocol_state，须与既有完整审计摘要分别报告。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t169-closed-state-pressure-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

from collections import Counter, defaultdict, deque
import argparse
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import time

ROOT = _PROJECT_ROOT
HERE = Path(__file__).resolve().parent
T165 = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t165-live-watchdog-1')


def load(path):
    """读取指定本地 JSON，不寻找或加载其他历史材料。"""
    return json.loads(path.read_text())


def digest(data):
    return hashlib.sha256(data).hexdigest()


def stats(values):
    """输出样本量、均值和最近秩百分位；空样本保持未知。"""
    ordered = sorted(values)
    return {'count': len(ordered), 'mean_ms': statistics.mean(ordered) if ordered else None,
            'p95_ms': ordered[math.ceil(.95 * len(ordered)) - 1] if ordered else None,
            'max_ms': ordered[-1] if ordered else None}


def extract(cycle_number):
    """仅核自然关闭 free；允许其他隔离批次继续比赛。"""
    cycle = _project_file(_PROJECT_ROOT, T165 / f'cycle-{cycle_number:03d}')
    assert load(cycle / 'FREE-CHILD-TERMINAL.json')['actual_exit_code'] == 0
    summary_bytes = (cycle / 'SUMMARY.json').read_bytes()
    lane = json.loads(summary_bytes)['lanes']['free']
    assert lane['postgame_audit_complete'] and lane['postgame_bundle_verified']
    plan = load(cycle / 'PLAN.json')
    session = _project_file(_PROJECT_ROOT, ROOT / plan['free_session'])
    runs = sorted(session.glob('audit/runs/*'))
    assert len(runs) == 1
    run = runs[0]
    assert load(run / 'summary.json')['audit_degraded'] is False
    raw_files = sorted(run.glob('participants/u_*/raw/a_*.jsonl.gz'))
    assert len(raw_files) == 10
    requests, frames, sources = [], [], []
    total_bytes = 0
    for path in raw_files:
        compressed = path.read_bytes()
        uncompressed = gzip.decompress(compressed)  # 本步同时验证已关闭 gzip 的 CRC。
        total_bytes += len(uncompressed)
        assert total_bytes < 128 * 1024**2, '禁止扩大成无界扫描'
        sources.append({'path': str(path.relative_to(ROOT)), 'sha256': digest(compressed),
                        'gzip_crc_verified': True, 'uncompressed_bytes': len(uncompressed)})
        for number, line in enumerate(uncompressed.splitlines(), 1):
            row = json.loads(line)
            payload, context = row['payload'], row['context']
            if row['kind'] != 'raw_protocol_state':
                continue
            endpoint = payload.get('endpoint', '')
            if endpoint.endswith('/notify'):
                frames.append({'game_id': context['game_id'], 'seq': payload.get('seq'),
                               'monotonic_sec': row['monotonic_ns'] / 1e9})
            if not endpoint.endswith('/state') or 'request_timing' not in payload:
                continue
            timing = payload['request_timing']
            assert all(timing.get(k) is not None for k in (
                'queued_at_monotonic', 'granted_at_monotonic',
                'transport_started_at_monotonic', 'completed_at_monotonic'))
            raw_body_parse_error = False
            try:
                body = json.loads(payload['raw'])
            except ValueError:
                # 传输失败可以保留空正文；不能删掉其真实调度时序或伪造快照。
                body = {}
                raw_body_parse_error = True
            if not isinstance(body, dict):
                body = {}
                raw_body_parse_error = True
            snapshot = body.get('snapshot', {})
            if not isinstance(snapshot, dict):
                snapshot = {}
            requests.append({'game_id': context['game_id'], 'round_no': context['round_no'],
                'seq_requested': payload.get('seq_requested'), 'seq_observed': payload.get('seq_observed'),
                'snapshot_phase': snapshot.get('phase'), 'snapshot_round_no': snapshot.get('round_no'),
                'snapshot_window_deadline_ms': snapshot.get('window_deadline_ms'),
                'raw_body_parse_error': raw_body_parse_error,
                'request_id': timing['request_id'], 'http_status': payload.get('http_status'),
                'queued': timing['queued_at_monotonic'], 'granted': timing['granted_at_monotonic'],
                'started': timing['transport_started_at_monotonic'], 'completed': timing['completed_at_monotonic'],
                'purpose': timing.get('query_purpose'), 'origin': timing.get('query_origin'),
                'priority': timing.get('scheduler_priority'),
                'latest_start': timing.get('latest_start_monotonic'),
                'queue_at_grant': timing.get('state_queue_at_grant'),
                'source': str(path.relative_to(ROOT)), 'source_line': number})
    requests.sort(key=lambda row: row['started'])
    assert len({r['request_id'] for r in requests}) == len(requests)
    by_purpose, by_origin, by_game = defaultdict(list), defaultdict(list), defaultdict(list)
    buckets = defaultdict(list)
    for r in requests:
        wait = (r['granted'] - r['queued']) * 1000
        by_purpose[r['purpose']].append(wait)
        by_origin[r['origin']].append(wait)
        by_game[r['game_id']].append(r)
        buckets[math.floor(r['started'])].append(r)
    rolling, max_count, max_window = deque(), 0, []
    for row in requests:
        while rolling and rolling[0]['started'] <= row['started'] - 1.0:
            rolling.popleft()
        rolling.append(row)
        if len(rolling) > max_count:
            max_count, max_window = len(rolling), list(rolling)
    failed = lane['audit'][0]['failed_plans']
    correlations = []
    for failure in failed:
        if failure['input']['legal'] == ['pass']:
            continue
        data, context = failure['input'], failure['context']
        arrived = [r for r in by_game[context['game_id']]
                   if r['completed'] <= data['budget_origin_monotonic']]
        preceding = max(arrived, key=lambda r: r['completed']) if arrived else None
        same_window = (preceding is not None
                       and preceding['seq_observed'] == context['trigger_seq']
                       and preceding['snapshot_round_no'] == context['round_no']
                       and preceding['snapshot_phase'] == data['phase'])
        correlations.append({'context': context, 'legal': data['legal'],
            'input_source': data['source'], 'input_source_line': data['line'],
            'policy_elapsed_ms': failure['policy_elapsed_ms'],
            'rule_elapsed_ms': data['rule_ms'],
            'enhancement_remaining_at_input_ms':
                (data['budget']['enhancement_deadline_monotonic'] - data['input_monotonic']) * 1000,
            'action_send_remaining_at_input_ms':
                (data['budget']['latest_send_at_monotonic'] - data['input_monotonic']) * 1000,
            'nearest_preceding_state': preceding,
            'preceding_state_to_budget_origin_ms':
                (data['budget_origin_monotonic'] - preceding['completed']) * 1000 if preceding else None,
            'same_window_identity_verified': same_window,
            'causality_not_proven': True})
    repeated_sequences, sequence_queries = Counter(), Counter()
    for rows in by_game.values():
        previous = None
        for row in rows:
            sequence_queries[(row['purpose'], 'snapshot' if row['seq_requested'] == 0 else 'incremental')] += 1
            if previous is not None and row['seq_observed'] == previous['seq_observed']:
                repeated_sequences[row['purpose']] += 1
            previous = row
    first, last = requests[0]['started'], requests[-1]['started']
    return {'cycle': cycle_number, 'run_id': run.name, 'summary_sha256': digest(summary_bytes),
        'sources': sources, 'uncompressed_bytes_read': total_bytes,
        'raw_state_responses': len(requests), 'notify_frames': len(frames),
        'summary_state_requests_including_errors': lane['audit'][0]['http_categories']['state'],
        'sample_start_span_sec': last - first,
        'raw_response_start_rate_per_second': len(requests) / (last - first),
        'queue_wait': stats([(r['granted'] - r['queued']) * 1000 for r in requests]),
        'queue_by_purpose': {k: stats(v) for k, v in by_purpose.items()},
        'queue_by_origin': {k: stats(v) for k, v in by_origin.items()},
        'request_forms_by_purpose': {purpose: dict(Counter({form: n for (p, form), n in sequence_queries.items()
                                               if p == purpose})) for purpose in by_purpose},
        'same_observed_seq_as_previous_response': dict(repeated_sequences),
        'same_seq_is_not_a_proven_skippable_query': True,
        'max_observed_rolling_one_second_starts': max_count,
        'max_rolling_window_requests': max_window,
        'busiest_nonoverlapping_seconds': [
            {'monotonic_second': second, 'raw_responses_started': len(rows),
             'purposes': dict(Counter(r['purpose'] for r in rows)),
             'queue_wait': stats([(r['granted'] - r['queued']) * 1000 for r in rows])}
            for second, rows in sorted(buckets.items(), key=lambda x: (-len(x[1]), x[0]))[:10]],
        'valuable_missing_scores': correlations,
        'max_request_scope_bytes': 128 * 1024**2,
        'network_server_arrival_times_known': False,
        'raw_state_missing_failed_http_not_fabricated': True,
        'full_decision_stream_scanned': False, 'new_http_rules_policy_calls': 0}


def main():
    """指定关闭批次只读提取；结果独占写，不能覆盖历史结论。"""
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    os.nice(15)
    started = time.monotonic()
    results = [extract(number) for number in (1, 2)]
    value = {'scope': '只读已自然关闭的两批自由赛状态原件；不改活房源码',
             'script_sha256': digest(Path(__file__).read_bytes()),
             'elapsed_sec': time.monotonic() - started, 'cpu_nice': os.nice(0),
             'cycles': results, 'runtime_fix_verified': False}
    with args.output.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'elapsed_sec': value['elapsed_sec'], 'cycles': [
        {'cycle': r['cycle'], 'raw_state_responses': r['raw_state_responses'],
         'mean_queue_ms': r['queue_wait']['mean_ms'],
         'valuable_missing_scores': len(r['valuable_missing_scores'])} for r in results]}, ensure_ascii=False))


if __name__ == '__main__':
    main()
