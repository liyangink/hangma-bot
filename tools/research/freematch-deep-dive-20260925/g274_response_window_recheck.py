#!/usr/bin/env python3
"""只读复算一间已完成自由赛房的官方响应超时、R18 首选和 SSE 预约取态。

从仓库根目录运行，输出必须显式指定到 /tmp。脚本不访问网络，也不读取 Token。
同相位 /state 缺失单列；赛后投影得到的候选不能冒充线上已见的权威快照。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/freematch-deep-dive-20260925'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import collections
import gzip
import hashlib
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True


def _quantiles(values: list[float]) -> dict:
    if not values:
        return {'n': 0, 'p50': None, 'p95': None, 'p99': None, 'max': None}
    ordered = sorted(values)
    return {'n': len(ordered),
            'p50': ordered[int((len(ordered) - 1) * .50)],
            'p95': ordered[int((len(ordered) - 1) * .95)],
            'p99': ordered[int((len(ordered) - 1) * .99)],
            'max': ordered[-1]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--room-id', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--repo-root', type=Path, default=Path.cwd(),
                        help='仓库根目录；默认当前目录')
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    if not (repo / 'tools/research/freematch-deep-dive-20260925/g265_expired_response_audit.py').is_file():
        parser.error('--repo-root 不是此仓库根目录')
    sys.path.insert(0, str(repo / 'tools/research/freematch-deep-dive-20260925'))
    import c31_action_layer_gap as c31
    import g265_expired_response_audit as g265

    state = g265.read(g265.STATE)
    rooms = [room for room in state['rooms'] if room['room_id'] == args.room_id]
    if len(rooms) != 1:
        raise ValueError('账本中该房不唯一或不存在')
    room = rooms[0]
    if room['terminal_reason'] != 'tournament_finished' or len(room['games']) != 10:
        raise ValueError('只接受 10 张完整桌的已完成房')
    game_ids = {item['game_id'] for item in room['games']}
    if len(game_ids) != 10:
        raise ValueError('账本桌 ID 不唯一')
    audit_dir = repo / room['audit_dir']
    manifest_path = audit_dir / 'manifest.json'
    manifest = g265.live.read_manifest(manifest_path)
    release_error = g265.live.verify_manifest_release(manifest)
    if release_error:
        raise ValueError('运行清单发布包不符：' + release_error)
    manifest_payload = g265.read(manifest_path)['payload']
    sources, official_hashes = g265.official_sources(game_ids)
    parent = c31.load_parent()
    counts = collections.Counter()
    nonpass_rows = []
    missing_authority_rows = []
    projection_mismatch_rows = []
    for game_id, source_path in sorted(sources.items()):
        document = g265.read(source_path)
        if document.get('status') != 'finished' or document.get('room_id') != args.room_id:
            raise ValueError('官方桌身份或终态不符：' + game_id)
        seats = [item.get('user_id') for item in document.get('seats') or []]
        if seats.count(g265.live.ME) != 1:
            raise ValueError('我方座位不唯一：' + game_id)
        seat = seats.index(g265.live.ME)
        states, _ = g265.raw_snapshots(audit_dir, game_id)
        table_scores = [0, 0, 0, 0]
        blocks = list(c31.AL.round_blocks(document))
        if len(blocks) != 8:
            raise ValueError('官方桌不是八局：' + game_id)
        for round_no, events, start_hands in blocks:
            ended_dealer, delta = c31.round_end_facts(events)
            dealer = next((i for i, hand in enumerate(start_hands)
                           if len(hand) == 14), ended_dealer)
            if dealer is None or delta is None:
                raise ValueError('官方局庄位或结算缺失：' + game_id)
            snapshots = c31.reconstruct(events, start_hands, table_scores, dealer)
            discard_seq = None
            discard_index = None
            for index, event in enumerate(events):
                if event['type'] == 'tile_discarded':
                    discard_seq = event['seq']
                    discard_index = index
                data = event.get('data') or {}
                if not (event['type'] == 'timeout' and event.get('seat') == seat
                        and data.get('kind') == 'response'):
                    continue
                if data.get('window') not in ('peng', 'chi'):
                    raise ValueError('未知官方响应窗类型：' + str(data.get('window')))
                if discard_seq not in snapshots or discard_index is None:
                    raise ValueError('响应超时前缺弃牌快照')
                between = events[discard_index + 1:index]
                if any(item['type'] not in ('pass', 'timeout') for item in between):
                    raise ValueError('弃牌与响应超时之间出现别的动作：' + game_id)
                phase = 'response_' + data['window']
                counts['official_response_timeout'] += 1
                counts['official_' + phase + '_timeout'] += 1
                observation = c31.build_observation(
                    snapshots[discard_seq], seat, phase, game_id, round_no)
                analysis = c31.RULES.analyze(observation, value_limits=c31.VALUE_LIMITS)
                keys = [candidate.action_key for candidate in analysis.legal_candidates]
                if 'pass' not in keys:
                    raise ValueError('官方响应超时未得到 pass 候选：' + game_id)
                nonpass_legal = any(key != 'pass' for key in keys)
                if nonpass_legal:
                    counts['nonpass_legal_timeout'] += 1
                else:
                    counts['pass_only_timeout'] += 1
                _, scores, status, reason, *_ = c31.score_window(observation, parent)
                if status != 'SCORED' or scores is None or set(scores) != set(keys):
                    raise ValueError('受控 R18 评分不可用：' + str(reason))
                top = min(scores, key=lambda key: (-scores[key], key))
                if top != 'pass':
                    counts['parent_top_nonpass_timeout'] += 1
                exact = [state for state in states
                         if discard_seq <= state.get('seq', -1) <= event['seq']
                         and state['snapshot'].get('round_no') == round_no
                         and state['snapshot'].get('seat') == seat
                         and state['snapshot'].get('phase') == phase
                         and state['snapshot'].get('last_discard') == snapshots[discard_seq]['tile']]
                authority = max(exact, key=lambda state: state['seq']) if exact else None
                row = {'game_id': game_id, 'round_no': round_no,
                       'discard_seq': discard_seq, 'timeout_seq': event['seq'],
                       'phase': phase, 'seat': seat,
                       'discard_tile': snapshots[discard_seq]['tile'],
                       'legal_actions': keys, 'r18_scores': scores,
                       'r18_top_action': top,
                       'state_seq': None if authority is None else authority['seq']}
                if authority is None:
                    counts['missing_same_phase_authority'] += 1
                    if nonpass_legal:
                        counts['nonpass_legal_missing_authority'] += 1
                    missing_authority_rows.append(row)
                else:
                    matches = g265.compare_state(authority['snapshot'], observation)
                    if len(matches) == 9 and all(matches.values()):
                        counts['nine_fields_match'] += 1
                        if nonpass_legal:
                            counts['nonpass_legal_nine_fields_match'] += 1
                    else:
                        counts['projection_mismatch'] += 1
                        if nonpass_legal:
                            counts['nonpass_legal_projection_mismatch'] += 1
                        projection_mismatch_rows.append({**row, 'nine_field_matches': matches})
                if nonpass_legal:
                    nonpass_rows.append(row)
            table_scores = [old + change for old, change in zip(table_scores, delta)]

    anticipated = []
    raw_dir = audit_dir / 'participants' / g265.live.ME / 'raw'
    for path in sorted(raw_dir.glob('*.jsonl.gz')):
        with gzip.open(path, 'rt') as handle:
            for line in handle:
                record = json.loads(line)
                payload = record.get('payload') or {}
                timing = payload.get('request_timing') or {}
                if (payload.get('source') != 'state_response' or
                        timing.get('query_purpose') != 'anticipated_chi_sync'):
                    continue
                body = payload.get('raw') or {}
                if isinstance(body, str):
                    body = json.loads(body) if body else {}
                snapshot = body.get('snapshot') or {}
                queued = timing.get('queued_at_monotonic')
                granted = timing.get('granted_at_monotonic')
                anticipated.append({
                    'game_id': snapshot.get('game_id'), 'phase': snapshot.get('phase'),
                    'seq': body.get('seq'), 'http_status': payload.get('http_status'),
                    'queue_ms': (None if queued is None or granted is None else
                                 round((granted - queued) * 1000, 3)),
                    'completed_wall_unix_ms': timing.get('completed_wall_unix_ms')})
    anticipated.sort(key=lambda row: (row['completed_wall_unix_ms'] or -1,
                                      row['game_id'] or '', row['seq'] or -1))

    decisions_path = audit_dir / 'participants' / g265.live.ME / 'decisions.jsonl'
    expired = []
    with decisions_path.open() as handle:
        for line in handle:
            record = json.loads(line)
            payload = record.get('payload') or {}
            window = payload.get('window') or {}
            if (record.get('kind') == 'decision_ended' and
                    payload.get('end_reason') == 'deadline' and
                    str(window.get('phase', '')).startswith('response_')):
                expired.append({'window': window,
                                'sent_attempts': payload.get('sent_attempts'),
                                'decision_id': (record.get('context') or {}).get('decision_id'),
                                'wall_time_unix_ms': record.get('wall_time_unix_ms')})
    expired.sort(key=lambda row: (row['wall_time_unix_ms'], row['window']['game_id']))
    nonpass_rows.sort(key=lambda row: (row['game_id'], row['round_no'],
                                       row['discard_seq'], row['phase']))
    missing_authority_rows.sort(key=lambda row: (row['game_id'], row['round_no'],
                                                 row['discard_seq'], row['phase']))
    projection_mismatch_rows.sort(key=lambda row: (row['game_id'], row['round_no'],
                                                   row['discard_seq'], row['phase']))
    queue = [row['queue_ms'] for row in anticipated if row['queue_ms'] is not None]
    report = {
        'room_id': args.room_id, 'run_id': manifest_payload.get('run_id'),
        'terminal_reason': room['terminal_reason'],
        'official_game_count': len(sources), 'ledger_game_count': len(room['games']),
        'manifest_git_dirty': manifest_payload.get('git_dirty'),
        'manifest_git_commit': manifest_payload.get('git_commit'),
        'manifest_state_scheduler_version': manifest_payload.get('state_scheduler_version'),
        'release_package_id': manifest['release_package_id'],
        'counts': dict(sorted(counts.items())),
        'all_timeout_projection_verified': (counts['missing_same_phase_authority'] == 0 and
                                            counts['projection_mismatch'] == 0),
        'nonpass_timeout_projection_verified': (counts['nonpass_legal_missing_authority'] == 0 and
                                                counts['nonpass_legal_projection_mismatch'] == 0),
        'nonpass_legal_timeout_rows': nonpass_rows,
        'missing_authority_rows': missing_authority_rows,
        'projection_mismatch_rows': projection_mismatch_rows,
        'anticipated_chi_sync': {
            'count': len(anticipated),
            'phases': dict(sorted(collections.Counter(row['phase'] for row in anticipated).items(),
                                  key=lambda item: str(item[0]))),
            'http_status': dict(sorted(collections.Counter(
                str(row['http_status']) for row in anticipated).items())),
            'queue_ms': _quantiles(queue), 'rows': anticipated},
        'local_expired_response_windows': expired,
        'official_sha256': dict(sorted(official_hashes.items())),
        'decisions_sha256': hashlib.sha256(decisions_path.read_bytes()).hexdigest(),
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    concise = {k: report[k] for k in ('room_id', 'counts',
                                       'all_timeout_projection_verified',
                                       'nonpass_timeout_projection_verified')}
    concise['anticipated_chi_sync'] = {k: v for k, v in report['anticipated_chi_sync'].items()
                                       if k != 'rows'}
    concise['local_expired_response_windows'] = expired
    concise['output'] = str(args.output)
    print(json.dumps(concise, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
