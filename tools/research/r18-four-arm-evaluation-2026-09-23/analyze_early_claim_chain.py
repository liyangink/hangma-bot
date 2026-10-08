"""对拍响应窗绝对截止与官方鸣牌、随后弃牌事件的最早本地到达。"""
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


def median(values: list[int]) -> int | None:
    """计算整数毫秒中位数；空样本返回 None。"""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def analyze(root: Path) -> dict:
    """四席事件按官方序号去重，使用同机最早收到时间核对碰窗截止。"""
    games = defaultdict(lambda: {'events': {}, 'snapshots': []})
    for slot in sorted(root.glob('slot-*')):
        runs = sorted((slot / 'runs').glob('run-*'), key=lambda p: p.stat().st_mtime)
        if not runs:
            raise ValueError(f'{slot.name}: no audit run')
        for path in (runs[-1] / 'participants').glob('*/raw/t_*.jsonl'):
            game = games[path.stem]
            with path.open(encoding='utf-8') as handle:
                for line in handle:
                    payload = json.loads(line).get('payload') or {}
                    if payload.get('http_status') != 200 or not str(payload.get('endpoint', '')).endswith('/state'):
                        continue
                    timing = payload.get('request_timing') or {}
                    completed = timing.get('completed_wall_unix_ms')
                    try:
                        body = json.loads(payload.get('raw') or '{}')
                    except (TypeError, ValueError):
                        continue
                    for event in body.get('events') or ():
                        seq = event.get('seq')
                        if not isinstance(seq, int):
                            continue
                        previous = game['events'].get(seq)
                        if previous is None or (completed is not None and
                                                (previous[1] is None or completed < previous[1])):
                            game['events'][seq] = (event, completed)
                    snapshot = body.get('snapshot') or {}
                    if (snapshot.get('phase') == 'response_peng'
                            and isinstance(snapshot.get('window_deadline_ms'), int)):
                        game['snapshots'].append((body.get('seq'), snapshot.get('last_discard'),
                                                  snapshot['window_deadline_ms']))
    claim_offsets = []
    next_discard_offsets = []
    examples = []
    for game_id, game in games.items():
        events = game['events']
        ordered = sorted(events.items())
        discards = [(seq, event) for seq, (event, _) in ordered if event.get('type') == 'tile_discarded']
        deadline_by_discard = {}
        for snapshot_seq, tile, deadline in game['snapshots']:
            previous = [(seq, event) for seq, event in discards if seq <= snapshot_seq]
            if previous and previous[-1][1].get('tile') == tile:
                deadline_by_discard[previous[-1][0]] = deadline
        for claim_seq, (event, claim_completed) in ordered:
            if event.get('type') != 'peng' or claim_completed is None:
                continue
            earlier_discards = [seq for seq, _ in discards if seq < claim_seq]
            if not earlier_discards:
                continue
            discard_seq = earlier_discards[-1]
            deadline = deadline_by_discard.get(discard_seq)
            if deadline is None:
                continue
            claim_offsets.append(claim_completed - deadline)
            later = [(seq, item, completed) for seq, (item, completed) in ordered if seq > claim_seq]
            next_discard = None
            for seq, item, completed in later:
                if item.get('type') == 'round_ended':
                    break
                if item.get('type') == 'tile_discarded':
                    next_discard = (seq, completed)
                    break
            if next_discard is not None and next_discard[1] is not None:
                next_discard_offsets.append(next_discard[1] - deadline)
                if len(examples) < 3 and next_discard[1] - deadline < -500:
                    examples.append({'game_id': game_id, 'trigger_discard_seq': discard_seq,
                                     'peng_seq': claim_seq, 'next_discard_seq': next_discard[0],
                                     'peng_first_seen_minus_deadline_ms': claim_completed - deadline,
                                     'next_discard_first_seen_minus_deadline_ms': next_discard[1] - deadline})
    return {
        'method': 'For each official peng event, associate the latest preceding official tile_discarded and a matching response_peng snapshot.window_deadline_ms; compare earliest local response completion across four seats with that absolute deadline.',
        'caveat': 'Local wall clock may differ from server clock and first observation can lag event generation. Roughly 0.7-1.0 second early gaps are far larger than typical clock offset. This shows the original response_peng deadline is not a safe no-event boundary after a valid claim.',
        'matched_peng_events': len(claim_offsets),
        'peng_seen_before_original_deadline': sum(offset < 0 for offset in claim_offsets),
        'peng_seen_500ms_before_original_deadline': sum(offset <= -500 for offset in claim_offsets),
        'peng_first_seen_minus_deadline_median_ms': median(claim_offsets),
        'followed_by_same_round_discard': len(next_discard_offsets),
        'next_discard_seen_before_original_deadline': sum(offset < 0 for offset in next_discard_offsets),
        'next_discard_first_seen_minus_deadline_median_ms': median(next_discard_offsets),
        'examples': examples,
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
