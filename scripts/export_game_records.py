#!/usr/bin/env python3
# 从本地审计目录导出多身份审计视图，用于牌效分析与规则核对。
#
# 用途：
# - 读取若干 run 目录（测试房四身份各自的 runs/slot-*/runs/run-*），按官方 gameId
#   合并四个座位视角的原始协议留痕（raw_protocol_state），导出供人工定位的 JSON 视图。
# - events：只合并本机实际收到的事件，不代表官方完整牌谱；快照超前/跨手可能缺史。
#   多身份视角不能直接作为学生观察。正式制品优先使用 audit_tool.py postgame。
# - snapshots：四座位各自观察到的官方快照原样保留（my_hand 是观察权限字段，仅记录
#   观察者本人手牌），按 (seq, 观察座位) 去重。牌效分析以 my_hand 演进 + 全桌
#   discards/melds 为输入。
# - submissions：我方四身份全部动作提交（含被拒与 adapter 原始响应），按提交墙钟排序。
#   字段说明见 doc/implementation/notes/test-room-20260905-retrospective.md。
#
# 约束：纯标准库；只读审计目录，不访问网络，不读取/输出任何 Token；
#       输出写入 artifacts/exports/game-records/<game_id>.json（不入库）。

import argparse
import glob
import json
import os
import sys

RAW_KIND = 'raw_protocol_state'


def iter_raw_records(run_dir):
    # 遍历一个 run 目录下所有参与者原始留痕，逐条产出审计记录字典。
    for path in sorted(glob.glob(os.path.join(run_dir, 'participants', '*', 'raw', '*.jsonl'))):
        with open(path, 'r', encoding='utf-8') as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                if record.get('kind') == RAW_KIND:
                    yield record


def parse_raw_text(text):
    # raw 字段可能是 JSON 字符串或已解码对象；空串返回 None。
    if not text:
        return None
    if isinstance(text, dict):
        return text
    try:
        return json.loads(text)
    except ValueError:
        return None


def collect_game(run_dirs, game_id):
    # 合并多视角原始留痕。events 按 seq 全局去重；snapshots 按 (seq, 观察座位) 去重。
    events = {}
    snapshots = {}
    seat_of_slot = {}
    pid_of_slot = {}
    tournament_id = None
    submissions = []

    for slot, run_dir in sorted(run_dirs.items()):
        for record in iter_raw_records(run_dir):
            payload = record.get('payload') or {}
            ctx = record.get('context') or {}
            if ctx.get('game_id') != game_id:
                continue
            tournament_id = ctx.get('tournament_id') or tournament_id
            pid_of_slot[slot] = ctx.get('participant_id')
            raw = parse_raw_text(payload.get('raw'))
            source = payload.get('source')
            if source == 'state_response' and raw:
                snap = raw.get('snapshot') or {}
                seat = snap.get('seat')
                if seat is not None:
                    seat_of_slot[slot] = seat
                seq = raw.get('seq')
                if seq is not None and seat is not None and (seq, seat) not in snapshots:
                    snapshots[(seq, seat)] = {
                        'seq': seq,
                        'wall_ms': record.get('wall_time_unix_ms'),
                        'observed_by_seat': seat,
                        'gap': raw.get('gap'),
                        'snapshot': snap,
                    }
                for event in raw.get('events') or []:
                    eseq = event.get('seq')
                    if eseq is not None and eseq not in events:
                        events[eseq] = event
            elif source == 'action_submit_response':
                submissions.append({
                    'wall_ms': record.get('wall_time_unix_ms'),
                    'slot': slot,
                    'seat': seat_of_slot.get(slot),
                    'trigger_seq': ctx.get('trigger_seq'),
                    'round_no': ctx.get('round_no'),
                    'decision_id': ctx.get('decision_id'),
                    'attempt_no': ctx.get('attempt_no'),
                    'response': raw if raw else {'raw_empty': True},
                })

    # 我方动作结果：decisions.jsonl 只取应用层规范记录（含 outcome_type 字段），
    # adapter 层同事件的另一视角（payload 仅含 outcome/window）跳过，避免双写重复。
    for slot, run_dir in sorted(run_dirs.items()):
        for path in sorted(glob.glob(os.path.join(run_dir, 'participants', '*', 'decisions.jsonl'))):
            with open(path, 'r', encoding='utf-8') as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    record = json.loads(line)
                    ctx = record.get('context') or {}
                    if ctx.get('game_id') != game_id:
                        continue
                    if record.get('kind') != 'submission_outcome':
                        continue
                    payload = record.get('payload') or {}
                    if 'outcome_type' not in payload:
                        continue
                    submissions.append({
                        'wall_ms': record.get('wall_time_unix_ms'),
                        'slot': slot,
                        'seat': seat_of_slot.get(slot),
                        'trigger_seq': ctx.get('trigger_seq'),
                        'round_no': ctx.get('round_no'),
                        'decision_id': ctx.get('decision_id'),
                        'attempt_no': ctx.get('attempt_no'),
                        'action_key': payload.get('action_key'),
                        'outcome_type': payload.get('outcome_type'),
                        'official_code': payload.get('official_code'),
                    })

    # 终局信息：games/<game_id>.jsonl 的 game_finished（各视角一致，取最后读到的一份）。
    finish_info = {}
    for slot, run_dir in sorted(run_dirs.items()):
        pattern = os.path.join(run_dir, 'participants', '*', 'games', game_id + '.jsonl')
        for path in sorted(glob.glob(pattern)):
            with open(path, 'r', encoding='utf-8') as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    record = json.loads(line)
                    if record.get('kind') == 'game_finished':
                        payload = record.get('payload') or {}
                        finish_info = {
                            'final_scores': payload.get('final_scores'),
                            'final_seq': payload.get('seq') or payload.get('authoritative_seq'),
                            'finished_wall_ms': record.get('wall_time_unix_ms'),
                        }
    meta = {
        'game_id': game_id,
        'information_scope': 'merged_player_views_not_official_replay',
        'training_eligible': False,
        'tournament_id': tournament_id,
        'source_runs': {slot: os.path.basename(d.rstrip('/')) for slot, d in run_dirs.items()},
        'participants': {slot: pid_of_slot.get(slot) for slot in sorted(run_dirs)},
        'seat_of_slot': dict(sorted(seat_of_slot.items())),
        'slot_of_seat': {v: k for k, v in sorted(seat_of_slot.items())},
    }
    meta.update(finish_info)
    return meta, events, snapshots, submissions


def main(argv=None):
    parser = argparse.ArgumentParser(description='导出多身份审计视图')
    parser.add_argument('--run', action='append', required=True,
                        help='run 目录，可重复；格式 slot=path（如 baihu=runs/slot-baihu/runs/run-xxx）')
    parser.add_argument('--game', action='append', required=True, help='官方 gameId，可重复')
    parser.add_argument('--out-dir', default='artifacts/exports/game-records', help='输出目录（默认 artifacts/exports/game-records）')
    args = parser.parse_args(argv)

    run_dirs = {}
    for item in args.run:
        if '=' not in item:
            parser.error('--run 需要 slot=path 形式: %s' % item)
        slot, path = item.split('=', 1)
        if not os.path.isdir(path):
            parser.error('run 目录不存在: %s' % path)
        run_dirs[slot] = path

    os.makedirs(args.out_dir, exist_ok=True)
    results = []
    for game_id in args.game:
        meta, events, snapshots, submissions = collect_game(run_dirs, game_id)
        if not snapshots:
            print('RESULT game=%s status=no_data' % game_id, file=sys.stderr)
            continue
        doc = {
            'schema_version': 1,
            'meta': meta,
            'events': [events[k] for k in sorted(events)],
            'snapshots': [snapshots[k] for k in sorted(snapshots)],
            'submissions': sorted(submissions, key=lambda s: (s.get('wall_ms') or 0)),
        }
        out_path = os.path.join(args.out_dir, game_id + '.json')
        with open(out_path, 'w', encoding='utf-8') as fh:
            json.dump(doc, fh, ensure_ascii=False)
        size_kb = os.path.getsize(out_path) // 1024
        print('RESULT game=%s status=ok events=%d snapshots=%d submissions=%d seats=%s file=%s size_kb=%d'
              % (game_id, len(doc['events']), len(doc['snapshots']), len(doc['submissions']),
                 meta['seat_of_slot'], out_path, size_kb))
        results.append(out_path)
    return 0 if results else 2


if __name__ == '__main__':
    sys.exit(main())
