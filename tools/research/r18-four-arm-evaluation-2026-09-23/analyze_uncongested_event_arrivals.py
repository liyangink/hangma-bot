"""在排队极短的官方状态查询中测量本地响应与去重事件到达差。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/r18-four-arm-evaluation-2026-09-23'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import argparse
import json
from collections import defaultdict
from pathlib import Path

THRESHOLDS_MS = (5, 10, 20, 50)


def quantile(values: list[float], fraction: float) -> float | None:
    """以最近秩计算毫秒分位数；空样本返回 None。"""
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[max(0, min(len(ordered) - 1, int(len(ordered) * fraction + .999999) - 1))], 1)


def distribution(values: list[float]) -> dict:
    """报告样本量和尾部分布，保留能影响最小间隔试验的快响应计数。"""
    return {
        'count': len(values), 'min_ms': quantile(values, 0),
        'p01_ms': quantile(values, .01), 'p05_ms': quantile(values, .05),
        'p10_ms': quantile(values, .10), 'p50_ms': quantile(values, .50),
        'p90_ms': quantile(values, .90),
        'under_20ms': sum(0 <= value < 20 for value in values),
        'under_50ms': sum(0 <= value < 50 for value in values),
        'under_100ms': sum(0 <= value < 100 for value in values),
    }


def load(root: Path) -> tuple[list[dict], dict[str, dict[int, dict]]]:
    """四席只选最后完整运行；原始事件按场次和官方序号取最早本地响应。"""
    requests = []
    earliest: dict[str, dict[int, dict]] = defaultdict(dict)
    for slot in sorted(root.glob('slot-*')):
        runs = sorted((slot / 'runs').glob('run-*'), key=lambda path: path.stat().st_mtime)
        if not runs:
            raise ValueError(f'{slot.name}: no audit run')
        for path in (runs[-1] / 'participants').glob('*/raw/t_*.jsonl'):
            with path.open(encoding='utf-8') as handle:
                for line in handle:
                    payload = json.loads(line).get('payload') or {}
                    if payload.get('http_status') != 200 or not str(payload.get('endpoint', '')).endswith('/state'):
                        continue
                    timing = payload.get('request_timing') or {}
                    queued, started, completed = (timing.get(key) for key in (
                        'queued_at_monotonic', 'transport_started_at_monotonic', 'completed_at_monotonic'))
                    if queued is None or started is None or completed is None:
                        continue
                    try:
                        body = json.loads(payload.get('raw') or '{}')
                    except (TypeError, ValueError):
                        continue
                    events = body.get('events') or ()
                    if not events:
                        continue
                    game_id = path.stem
                    request = {
                        'game_id': game_id, 'slot': slot.name,
                        'request_id': timing.get('request_id'),
                        'seq_requested': payload.get('seq_requested'),
                        'purpose': timing.get('query_purpose'),
                        'priority': timing.get('scheduler_priority'),
                        'queue_ms': 1000 * (started - queued),
                        'transport_ms': 1000 * (completed - started),
                        'completed': completed, 'event_count': len(events),
                    }
                    requests.append(request)
                    for event in events:
                        seq = event.get('seq')
                        if not isinstance(seq, int):
                            continue
                        candidate = {**request, 'seq': seq, 'event_type': event.get('type')}
                        previous = earliest[game_id].get(seq)
                        if previous is None or completed < previous['completed']:
                            earliest[game_id][seq] = candidate
    return requests, earliest


def analyze(root: Path) -> dict:
    """排队敏感性与跨席首次到达差同时输出，避免把打包事件视为零间隔。"""
    requests, earliest = load(root)
    results = {}
    for threshold in THRESHOLDS_MS:
        watch = defaultdict(list)
        for request in requests:
            if request['seq_requested'] == 0 or request['queue_ms'] > threshold:
                continue
            watch[f"{request['purpose']}/{request['priority']}"].append(request['transport_ms'])
        by_purpose = {name: distribution(values) for name, values in sorted(watch.items())}
        adjacent = 0
        same_response = 0
        separate = []
        single_event = []
        chains = defaultdict(list)
        for events in earliest.values():
            for seq, previous in events.items():
                current = events.get(seq + 1)
                if current is None or previous['queue_ms'] > threshold or current['queue_ms'] > threshold:
                    continue
                adjacent += 1
                if (previous['slot'], previous['request_id']) == (current['slot'], current['request_id']):
                    same_response += 1
                    continue
                gap_ms = 1000 * (current['completed'] - previous['completed'])
                if gap_ms < 0:
                    continue
                separate.append(gap_ms)
                chains[f"{previous['event_type']}->{current['event_type']}"].append(gap_ms)
                if previous['event_count'] == current['event_count'] == 1:
                    single_event.append(gap_ms)
        results[str(threshold)] = {
            'eventful_incremental_get_by_purpose': by_purpose,
            'adjacent_official_seq_both_first_seen_queue_within_threshold': adjacent,
            'same_http_response_pairs': same_response,
            'separate_http_response_gap_ms': distribution(separate),
            'separate_single_event_response_gap_ms': distribution(single_event),
            'selected_chains': {name: distribution(chains[name]) for name in (
                'tile_drawn->tile_discarded', 'chi->tile_discarded',
                'peng->tile_discarded', 'tile_discarded->peng',
                'timeout->chi', 'timeout->tile_drawn')},
        }
    return {
        'room': root.parent.name,
        'source': 'Four seats official /state raw events plus local monotonic request timing; one latest complete run per seat',
        'queue_definition': 'transport_started_at_monotonic - queued_at_monotonic; threshold in milliseconds',
        'response_interval_definition': 'completed_at_monotonic - transport_started_at_monotonic for eventful seq>0 GET; includes server longpoll and network latency',
        'event_gap_definition': 'difference between earliest local completed_at_monotonic for adjacent unique official seq in a game; separate HTTP responses only; still includes variable network delay',
        'caveat': 'Low queue does not prove the event happened after GET started; some replies contain already generated events. Same HTTP response pairs have unidentifiable sub-batch spacing. The filtered sample is selective, not server event-time truth.',
        'unique_events_first_seen': sum(map(len, earliest.values())),
        'thresholds_ms': results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('audit_roots', nargs='+', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = {root.parent.name: analyze(root) for root in args.audit_roots}
    document = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.write_text(document, encoding='utf-8')
    else:
        print(document, end='')

if __name__ == '__main__':
    main()
