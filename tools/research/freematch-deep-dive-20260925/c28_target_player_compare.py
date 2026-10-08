#!/usr/bin/env python3
"""C28：与周榜榜首「玄武-2346」的逐项对照（用户点名问题）。

问：强手的白板（财神）利用率是不是比我们高很多？胡牌率、连庄率等其他数据如何？
据此判断决策时哪一维更重要。

数据：review/baotou-anatomy-20260925/rounds.jsonl + 官方周榜快照（top-32 与上周榜）。
分组：target=玄武-2346 / elite=其他周榜 top-32 / me=我方 / other=其余对手。
统计：组均值 + 同局配对（按房聚类 bootstrap）。
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

import collections
import glob
import json
import random
import statistics
from pathlib import Path

ROOT = _PROJECT_ROOT
ROUNDS = _project_file(_PROJECT_ROOT, 'review/baotou-anatomy-20260925/rounds.jsonl')


def load_board():
    paths = sorted(glob.glob(str(_project_file(_PROJECT_ROOT, ROOT / 'datasets' / 'leaderboard' / 'snapshots' / '*' / 'leaderboard-week.json'))))
    payload = json.load(open(paths[-1], encoding='utf-8'))
    top = list(payload.get('top') or [])
    prev = list((payload.get('prev') or {}).get('top') or [])
    ids = {}
    for row in top + prev:
        if row.get('user_id'):
            ids.setdefault(row['user_id'], row)
    target = None
    for row in top + prev:
        if '玄武' in str(row.get('name') or ''):
            target = row['user_id']
            break
    return ids, target


def boot(values, iters=2000, seed=17):
    if len(values) < 3:
        return (float('nan'), float('nan'))
    rng = random.Random(seed)
    means = [statistics.fmean([rng.choice(values) for _ in values]) for _ in range(iters)]
    means.sort()
    return (means[int(0.025 * iters)], means[int(0.975 * iters)])


def wait_width(waits):
    for row in waits or ():
        if len(row) >= 8 and row[4] == 0 and isinstance(row[6], int) and isinstance(row[7], int):
            return row[6], row[7]
    return None, None


def main() -> int:
    board, target = load_board()
    print('周榜 top-32 标签 %d 人；目标 = %s' % (len(board), target))
    groups = ('target', 'elite', 'me', 'other')

    acc = {g: collections.Counter() for g in groups}
    fan = {g: [] for g in groups}
    entry_turn = {g: [] for g in groups}
    entry_whites = {g: [] for g in groups}
    first_tenpai = {g: [] for g in groups}
    wait_kinds = {g: [] for g in groups}
    wait_tiles = {g: [] for g in groups}
    win_white_pair = {g: [] for g in groups}
    paired_rounds = collections.defaultdict(list)
    room_scores = collections.defaultdict(float)
    rooms_with_target = set()
    rooms_with_me = set()
    streak_max = collections.defaultdict(int)
    streak_now = collections.defaultdict(int)
    uid_group = {}

    rows = [json.loads(line) for line in ROUNDS.open(encoding='utf-8') if line.strip()]
    rows.sort(key=lambda r: (r.get('game_id') or '', r.get('round_no') or 0))
    for row in rows:
        seats = row.get('seats') or []
        if len(seats) != 4:
            continue
        scores = row.get('scores') or []
        detail = row.get('detail') or []
        baotou_win = any('爆头' in str(x) for x in detail)
        winner = row.get('winner_seat')
        is_draw = bool(row.get('is_draw'))
        room = row.get('room_id')
        game = row.get('game_id')
        round_fan = row.get('fan')
        assign = {}
        for s in seats:
            uid = s.get('user_id')
            if uid == target:
                assign[s['seat']] = 'target'
            elif uid in board:
                assign[s['seat']] = 'elite'
            elif s.get('is_me'):
                assign[s['seat']] = 'me'
            else:
                assign[s['seat']] = 'other'
            uid_group[uid] = assign[s['seat']]
        if 'target' in assign.values():
            rooms_with_target.add(room)
        if 'me' in assign.values():
            rooms_with_me.add(room)
        points_by_group = collections.defaultdict(list)
        for s in seats:
            g = assign[s['seat']]
            c = acc[g]
            seat = s['seat']
            points = float(scores[seat]) if len(scores) == 4 else 0.0
            points_by_group[g].append(points)
            room_scores[(room, s.get('user_id'))] += points
            c['rounds'] += 1
            c['points_x10'] += int(round(points * 10))
            if winner == seat and not is_draw:
                c['wins'] += 1
                c['win_points_x10'] += int(round(points * 10))
                if isinstance(round_fan, (int, float)):
                    fan[g].append(float(round_fan))
                if baotou_win:
                    c['baotou_wins'] += 1
            elif not is_draw:
                c['loss_points_x10'] += int(round(points * 10))
                c['losses'] += 1
            if s.get('is_dealer'):
                c['dealer'] += 1
                if winner == seat and not is_draw:
                    c['dealer_wins'] += 1
                uid = s.get('user_id')
                streak_now[(game, uid)] += 1
                streak_max[(game, uid)] = max(streak_max[(game, uid)], streak_now[(game, uid)])
            else:
                streak_now[(game, s.get('user_id'))] = 0
            if s.get('entered_baotou') is True:
                c['entered_baotou'] += 1
            for key in ('whites_drawn', 'whites_discarded', 'whites_end', 'melds_end', 'draws_n', 'discards_n'):
                v = s.get(key)
                if isinstance(v, (int, float)):
                    c[key + '_x10'] += int(round(float(v) * 10))
            if isinstance(s.get('entry_turn'), int):
                entry_turn[g].append(s['entry_turn'])
            if isinstance(s.get('entry_whites'), int):
                entry_whites[g].append(s['entry_whites'])
            if isinstance(s.get('first_tenpai_turn'), int):
                first_tenpai[g].append(s['first_tenpai_turn'])
            k, t = wait_width(s.get('waits'))
            if k is not None:
                wait_kinds[g].append(k)
                wait_tiles[g].append(t)
            if s.get('won') and isinstance(s.get('white_in_pair'), int):
                win_white_pair[g].append(s['white_in_pair'])
            wd = s.get('whites_drawn')
            if isinstance(wd, int) and wd >= 1:
                c['drew_white'] += 1
                if s.get('entered_baotou') is True:
                    c['drew_white_entered'] += 1
        if 'target' in points_by_group and 'me' in points_by_group:
            paired_rounds['me'].append((statistics.fmean(points_by_group['me']) - statistics.fmean(points_by_group['target']), room))
        if 'target' in points_by_group and 'other' in points_by_group:
            paired_rounds['other'].append((statistics.fmean(points_by_group['other']) - statistics.fmean(points_by_group['target']), room))

    def pct(c, num, den, digits=2):
        if not c[den]:
            return '—'
        return ('%.' + str(digits) + 'f%%') % (100.0 * c[num] / c[den])

    def mean(values, digits=3):
        if not values:
            return '—'
        return ('%.' + str(digits) + 'f') % statistics.fmean(values)

    def per_round(c, key, digits=3):
        if not c['rounds']:
            return '—'
        return ('%.' + str(digits) + 'f') % (c[key + '_x10'] / c['rounds'] / 10.0)

    print()
    print('| 指标 | 玄武-2346 | 其他周榜强手 | 我方 | 其他对手 |')
    print('| --- | --- | --- | --- | --- |')
    def line(label, fn):
        print('| %s | %s |' % (label, ' | '.join(fn(acc[g], g) for g in groups)))
    line('座位-局数', lambda c, g: str(c['rounds']))
    line('每局得分', lambda c, g: ('%+.3f' % (c['points_x10'] / max(1, c['rounds']) / 10.0)))
    line('胡牌率', lambda c, g: pct(c, 'wins', 'rounds'))
    line('赢时得分', lambda c, g: ('%+.2f' % (c['win_points_x10'] / max(1, c['wins']) / 10.0)))
    line('输时付分', lambda c, g: ('%+.2f' % (c['loss_points_x10'] / max(1, c['losses']) / 10.0)))
    line('胡牌均番', lambda c, g: mean(fan[g]))
    line('爆头胡占胡牌', lambda c, g: pct(c, 'baotou_wins', 'wins'))
    line('坐庄局数', lambda c, g: str(c['dealer']))
    line('坐庄胡率=连庄率', lambda c, g: pct(c, 'dealer_wins', 'dealer'))
    line('曾进入爆头', lambda c, g: pct(c, 'entered_baotou', 'rounds'))
    line('摸到白板/局', lambda c, g: per_round(c, 'whites_drawn'))
    line('终局手留白板/局', lambda c, g: per_round(c, 'whites_end'))
    line('弃白板/局', lambda c, g: per_round(c, 'whites_discarded', 4))
    line('★抽到白板后进爆头', lambda c, g: pct(c, 'drew_white_entered', 'drew_white'))
    line('★每张白板的爆头产出', lambda c, g: ('%.3f' % (c['entered_baotou'] / max(1e-9, c['whites_drawn_x10'] / 10.0))))
    line('进爆头时手留白板', lambda c, g: mean(entry_whites[g]))
    line('爆头进入巡目', lambda c, g: mean(entry_turn[g]))
    line('首次听牌巡目', lambda c, g: mean(first_tenpai[g]))
    line('听牌等待种数', lambda c, g: mean(wait_kinds[g]))
    line('听牌等待张数', lambda c, g: mean(wait_tiles[g]))
    line('胡牌时白作将', lambda c, g: mean(win_white_pair[g]))
    line('终局副露数', lambda c, g: per_round(c, 'melds_end'))
    line('摸牌数/局', lambda c, g: per_round(c, 'draws_n'))
    line('弃牌数/局', lambda c, g: per_round(c, 'discards_n'))
    print()
    print('得分恒等式分解（每局）：E = 胡率 × 赢时得分 − (1−胡率) × 输时付分')
    for g in groups:
        c = acc[g]
        if not c['rounds']:
            continue
        pwin = c['wins'] / c['rounds']
        win_pts = c['win_points_x10'] / max(1, c['wins']) / 10.0
        loss_pts = -c['loss_points_x10'] / max(1, c['losses']) / 10.0
        total = pwin * win_pts - (1 - pwin) * loss_pts
        print('  %-7s 胡率 %.4f × 赢 %+.2f − %.4f × 付 %+.2f = %+.3f'
              % (g, pwin, win_pts, 1 - pwin, loss_pts, total))
    print()
    for key in ('me', 'other'):
        entries = paired_rounds[key]
        if not entries:
            continue
        by_room = collections.defaultdict(list)
        for value, room in entries:
            by_room[room].append(value)
        room_means = [statistics.fmean(v) for v in by_room.values()]
        lo, hi = boot(room_means)
        print('同局配对（%s − 玄武）：%+.3f 分/局，房聚类 95%% CI [%+.3f, %+.3f]（%d 局 / %d 房）'
              % (key, statistics.fmean([v for v, _ in entries]), lo, hi, len(entries), len(by_room)))
    shared = sorted(rooms_with_target & rooms_with_me)
    print('含玄武的房 = %d；含我方的房 = %d；交集 = %d' % (len(rooms_with_target), len(rooms_with_me), len(shared)))
    leads = []
    for room in shared:
        totals = {uid: v for (rm, uid), v in room_scores.items() if rm == room}
        if target not in totals:
            continue
        mine = [v for uid, v in totals.items() if uid_group.get(uid) == 'me']
        others = [v for uid, v in totals.items() if uid != target and uid_group.get(uid) != 'me']
        if mine and others:
            leads.append((totals[target] - max(others), totals[target] - mine[0]))
    if leads:
        print('这些房里 玄武房总分 相对其最强对手：均值 %+.1f、中位 %+.1f；相对我方：均值 %+.1f、中位 %+.1f（n=%d 房）'
              % (statistics.fmean([a for a, _ in leads]), statistics.median([a for a, _ in leads]),
                 statistics.fmean([b for _, b in leads]), statistics.median([b for _, b in leads]), len(leads)))
    top_streaks = collections.Counter()
    for (game, uid), value in streak_max.items():
        if value >= 2:
            top_streaks[uid_group.get(uid, '?')] += 1
    print('出现过 ≥2 连庄的（局,座位）计数 =', dict(top_streaks))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
