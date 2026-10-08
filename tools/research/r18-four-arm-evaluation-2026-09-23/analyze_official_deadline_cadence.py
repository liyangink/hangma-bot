"""利用官方响应窗截止与配置时长推测部分弃牌发生时间；结果有选择偏倚。"""
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


def quantile(values: list[int], fraction: float) -> int | None:
    """返回最近秩分位数，空集返回 None。"""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, int(len(ordered) * fraction + .999999) - 1))]


def analyze(audit: Path, response_sec: int) -> dict:
    """用响应窗截止减配置时长推测弃牌毫秒；只留可与官方秒时间戳互证的样本。"""
    games = defaultdict(lambda: {'events': {}, 'snapshots': []})
    for slot in sorted(audit.glob('slot-*')):
        runs = sorted((slot / 'runs').glob('run-*'), key=lambda path: path.stat().st_mtime)
        if not runs:
            raise ValueError(f'{slot}: no runs')
        for path in (runs[-1] / 'participants').glob('*/raw/t_*.jsonl'):
            game = games[path.stem]
            with path.open(encoding='utf-8') as handle:
                for line in handle:
                    payload = (json.loads(line).get('payload') or {})
                    if '/state' not in str(payload.get('endpoint')):
                        continue
                    try:
                        body = json.loads(payload.get('raw') or '{}')
                    except (TypeError, ValueError):
                        continue
                    for event in body.get('events') or ():
                        if isinstance(event.get('seq'), int):
                            game['events'][event['seq']] = event
                    snapshot = body.get('snapshot') or {}
                    if snapshot.get('phase') == 'response_peng' and isinstance(snapshot.get('window_deadline_ms'), int):
                        game['snapshots'].append((body.get('seq'), snapshot.get('last_discard'), snapshot['window_deadline_ms']))
    snapshots = no_prior = tile_mismatch = inconsistent = 0
    candidates = {}
    for game_id, game in games.items():
        discards = [(seq, event) for seq, event in sorted(game['events'].items()) if event.get('type') == 'tile_discarded']
        by_discard = defaultdict(set)
        for seq, tile, deadline in game['snapshots']:
            snapshots += 1
            preceding = [(key, event) for key, event in discards if key <= seq]
            if not preceding:
                no_prior += 1
                continue
            discard_seq, event = preceding[-1]
            if event.get('tile') != tile:
                tile_mismatch += 1
                continue
            by_discard[discard_seq].add(deadline - response_sec * 1000)
        for seq, estimates in by_discard.items():
            if len(estimates) == 1:
                candidates[(game_id, seq)] = next(iter(estimates))
            else:
                inconsistent += 1
    residuals = []
    gaps = []
    invalid_pairs = 0
    all_discard_pairs = 0
    for game_id, game in games.items():
        discards = [(seq, event) for seq, event in sorted(game['events'].items()) if event.get('type') == 'tile_discarded']
        for seq, event in discards:
            if (game_id, seq) in candidates and isinstance(event.get('ts'), int):
                residuals.append(candidates[(game_id, seq)] - event['ts'] * 1000)
        within_round_pairs = []
        previous_discard = None
        for seq, event in sorted(game['events'].items()):
            if event.get('type') == 'round_ended':
                previous_discard = None
            elif event.get('type') == 'tile_discarded':
                if previous_discard is not None:
                    within_round_pairs.append((previous_discard, (seq, event)))
                previous_discard = (seq, event)
        for (seq0, event0), (seq1, event1) in within_round_pairs:
            all_discard_pairs += 1
            key0, key1 = (game_id, seq0), (game_id, seq1)
            if key0 not in candidates or key1 not in candidates:
                continue
            if not isinstance(event0.get('ts'), int) or not isinstance(event1.get('ts'), int):
                invalid_pairs += 1
                continue
            time0, time1 = candidates[key0], candidates[key1]
            if not (0 <= time0 - 1000 * event0['ts'] < 1000 and 0 <= time1 - 1000 * event1['ts'] < 1000):
                invalid_pairs += 1
                continue
            gaps.append(time1 - time0)
    return {
        'method': 'official response_peng snapshot.window_deadline_ms minus configured PengTimeoutSec; associate latest matching tile_discarded event; compare consecutive discards within an observed round; require inferred time to fall within its official integer-ts second',
        'qualification': 'Inference, not a documented millisecond event timestamp. Matched snapshots and pairs are selected, not representative of all events or all discards.',
        'configured_peng_timeout_sec': response_sec,
        'snapshots': snapshots, 'no_prior_discard': no_prior, 'tile_mismatch': tile_mismatch,
        'inconsistent_inferences': inconsistent, 'unique_inferred_discards': len(candidates),
        'inferred_second_residual_min_ms': min(residuals), 'inferred_second_residual_max_ms': max(residuals),
        'all_consecutive_discard_pairs': all_discard_pairs, 'valid_inferred_consecutive_discard_pairs': len(gaps),
        'invalid_inferred_pairs': invalid_pairs, 'gap_min_ms': min(gaps),
        'gap_p01_ms': quantile(gaps, .01), 'gap_p05_ms': quantile(gaps, .05),
        'gap_p10_ms': quantile(gaps, .10), 'gap_p50_ms': quantile(gaps, .50),
        'gap_under_50ms': sum(0 <= value < 50 for value in gaps),
        'gap_under_100ms': sum(0 <= value < 100 for value in gaps),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('audit_roots', nargs='+', type=Path)
    parser.add_argument('--peng-timeout-sec', type=int, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = {root.parent.name: analyze(root, args.peng_timeout_sec) for root in args.audit_roots}
    document = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.write_text(document, encoding='utf-8')
    else:
        print(document, end='')

if __name__ == '__main__':
    main()
