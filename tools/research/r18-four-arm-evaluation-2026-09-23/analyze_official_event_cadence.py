"""按官方原始事件的 Unix 秒时间戳统计相邻事件；排除本地收包、排队和长轮询时间。"""
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
from collections import Counter, defaultdict
from pathlib import Path


def analyze(audit: Path) -> dict:
    games = defaultdict(dict)
    conflicts = 0
    for slot in sorted(audit.glob('slot-*')):
        runs = sorted((slot / 'runs').glob('run-*'), key=lambda path: path.stat().st_mtime)
        if not runs:
            raise ValueError(f'{slot}: no runs')
        for path in (runs[-1] / 'participants').glob('*/raw/t_*.jsonl'):
            with path.open(encoding='utf-8') as handle:
                for line in handle:
                    row = json.loads(line)
                    payload = row.get('payload') or {}
                    if '/state' not in str(payload.get('endpoint')):
                        continue
                    try:
                        body = json.loads(payload.get('raw') or '{}')
                    except (ValueError, TypeError):
                        continue
                    for event in body.get('events') or ():
                        seq = event.get('seq')
                        if not isinstance(seq, int):
                            continue
                        previous = games[path.stem].get(seq)
                        entry = (event.get('type'), event.get('ts'))
                        if previous is not None and previous != entry:
                            conflicts += 1
                        games[path.stem][seq] = entry
    adjacent = Counter()
    chain = defaultdict(Counter)
    discard = Counter()
    exact_adjacent = Counter()
    exact_discard = Counter()
    valid = missing_ts = sequence_gaps = 0
    for events in games.values():
        ordered = sorted(events.items())
        valid += len(ordered)
        missing_ts += sum(not isinstance(item[1][1], int) for item in ordered)
        sequence_gaps += sum(seq1 != seq0 + 1 for (seq0, _), (seq1, _) in zip(ordered, ordered[1:]))
        for (seq0, (type0, ts0)), (seq1, (type1, ts1)) in zip(ordered, ordered[1:]):
            if seq1 != seq0 + 1 or not isinstance(ts0, int) or not isinstance(ts1, int):
                continue
            gap = ts1 - ts0
            bucket = 'same_second' if gap == 0 else 'next_second' if gap == 1 else 'two_or_more_seconds' if gap >= 2 else 'negative'
            adjacent[bucket] += 1
            exact_adjacent[str(gap) if gap < 5 else '5_plus'] += 1
            chain[f'{type0}->{type1}'][bucket] += 1
        previous = None
        for _, (kind, ts) in ordered:
            if kind == 'round_ended':
                previous = None
                continue
            if kind != 'tile_discarded' or not isinstance(ts, int):
                continue
            if previous is not None:
                gap = ts - previous
                bucket = 'same_second' if gap == 0 else 'next_second' if gap == 1 else 'two_or_more_seconds' if gap >= 2 else 'negative'
                discard[bucket] += 1
                exact_discard[str(gap) if gap < 5 else '5_plus'] += 1
            previous = ts
    relevant = [
        'timeout->tile_drawn', 'pass->tile_drawn', 'tile_drawn->tile_discarded',
        'chi->tile_discarded', 'peng->tile_discarded',
        'timeout->chi', 'timeout->peng', 'pass->chi', 'pass->peng',
        'tile_discarded->chi', 'tile_discarded->peng',
        'tile_discarded->timeout', 'tile_discarded->pass',
    ]
    return {
        'source': 'official GET /api/games/{id}/state raw event seq/type/ts, deduped across four seats by game_id and seq',
        'timestamp_unit': 'Unix seconds (integer); subsecond gap cannot be identified',
        'discard_pair_scope': 'consecutive tile_discarded within observed same round; reset at round_ended',
        'games': len(games), 'unique_events': valid, 'missing_ts': missing_ts,
        'conflicting_duplicate_events': conflicts, 'sequence_gaps': sequence_gaps,
        'adjacent_seq_event_time_buckets': dict(adjacent),
        'adjacent_seq_exact_gap_seconds': dict(sorted(exact_adjacent.items())),
        'consecutive_discard_event_time_buckets': dict(discard),
        'consecutive_discard_exact_gap_seconds': dict(sorted(exact_discard.items())),
        'selected_adjacent_event_chains': {name: dict(chain[name]) for name in relevant},
    }


def main():
    parser = argparse.ArgumentParser()
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
