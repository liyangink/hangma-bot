#!/usr/bin/env python3
"""能力缺口记分卡：以真实自由赛牌谱为准，量化白板利用率与连庄收益，并与前沿选手对照。

数据源（主仓，只读）：
- `datasets/derived/auto-match-v10-2026-09-10/features-v10.jsonl`（夜间战役 47 房 3,760 单局的逐座位特征）
- `datasets/leaderboard/opponent-tags.json` 与 `snapshots/*/leaderboard-best-game.json`

指标口径（全部为真实对手牌局，非模拟）：
- 白板：`P(胡 | 摸到 k 张白)`、爆头/财飘占胜局比、手握白分布、打白率；
- 连庄：庄位份额、`P(胡 | 庄)` 与 `P(胡 | 闲)`、庄/闲每手净分、连庄长度分布、单场最多胜局数。
分组：我方（v10 等于胡实验版 / v2 基线）、压制组（同场配对差 ≤ −8/场）、榜上强手（带标签）、其余对手。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/heuristic-balanced-2026-09-10'

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
from pathlib import Path

MAIN = Path('/Users/liyang/Projects/Opensource/hangma-bot')
FEATURES = _project_file(_PROJECT_ROOT, MAIN / 'datasets/derived/auto-match-v10-2026-09-10/features-v10.jsonl')
TAGS = _project_file(_PROJECT_ROOT, MAIN / 'datasets/leaderboard/opponent-tags.json')
BEST_GAME = _project_file(_PROJECT_ROOT, MAIN / 'datasets/leaderboard/snapshots/20260909T124019Z/leaderboard-best-game.json')
ME = 'u_13495c3d79c8'


def dominators() -> set:
    doc = json.loads((_project_file(_PROJECT_ROOT, MAIN / 'datasets/derived/auto-match-v10-2026-09-10/opponents.json')).read_text())
    return {row['user_id'] for row in doc['dominators'] if row.get('paired_diff_per_game', 0) <= -8.0}


def group_of(user_id, doms, tagged):
    if user_id == ME:
        return '我方(v10 实验版)'
    if user_id in doms:
        return '压制组'
    if user_id in tagged:
        return '榜上强手(非压制)'
    return '其他对手'


def main() -> None:
    rows = [json.loads(line) for line in FEATURES.open()]
    doms = dominators()
    tagged = {uid for uid, entry in json.loads(TAGS.read_text())['tags'].items() if entry.get('tags')}
    size = collections.Counter()

    white = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0]))
    dealers = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0, 0.0]))
    marks = collections.defaultdict(collections.Counter)
    stints = collections.defaultdict(collections.Counter)
    wins_per_game = collections.defaultdict(list)
    game_wins = collections.Counter()

    for row in rows:
        for seat in range(4):
            users = row['seat_users'] or []
            user = users[seat] if seat < len(users) else None
            group = group_of(user, doms, tagged)
            size[group] += 1
            stats = row['seat_stats'][str(seat)]
            whites = min(stats['whites_drawn'] + stats['init_whites'], 4)
            won = row['winner'] == seat and not row['is_draw']
            bucket = white[group][whites]
            bucket[0] += 1
            bucket[1] += 1 if won else 0
            if won:
                for mark in ('爆头', '财飘', '七对'):
                    if mark in set(row['detail'] or []):
                        marks[group][mark] += 1
                marks[group]['胜局'] += 1
                game_wins[(row['game_id'], seat)] += 1

    first_row_by_game = {}
    for row in rows:
        first_row_by_game.setdefault(row['game_id'], row)
    for (game_id, seat), count in game_wins.items():
        users = first_row_by_game[game_id]['seat_users'] or []
        user = users[seat] if seat < len(users) else None
        wins_per_game[group_of(user, doms, tagged)].append(count)

    # 连庄：按"庄家连续手数"重建（赢家坐庄、庄赢连庄）
    by_game = collections.defaultdict(list)
    for row in rows:
        by_game[row['game_id']].append(row)
    # 必须按同一玩家计连庄：按组统计会被组规模污染（对手占三席自然连得更长）。
    for game_id, hands in by_game.items():
        hands.sort(key=lambda item: item['round_no'])
        users = hands[0]['seat_users'] or []
        current_user = None
        length = 0
        for hand in hands:
            dealer = hand['dealer']
            user = users[dealer] if dealer < len(users) else None
            if current_user is not None and user == current_user:
                length += 1
            else:
                if current_user is not None:
                    stints[group_of(current_user, doms, tagged)][length] += 1
                current_user, length = user, 1
        if current_user is not None:
            stints[group_of(current_user, doms, tagged)][length] += 1

    def dealer_stats(group):
        total = dealer_wins = 0
        score = 0.0
        for row in rows:
            users = row['seat_users'] or []
            for seat in range(4):
                if row['dealer'] != seat:
                    continue
                user = users[seat] if seat < len(users) else None
                if group_of(user, doms, tagged) != group:
                    continue
                total += 1
                score += row['scores'][seat]
                if row['winner'] == seat and not row['is_draw']:
                    dealer_wins += 1
        return total, dealer_wins, score

    first_white = collections.defaultdict(lambda: [0, 0, 0])  # [首白次数, 首白后胜, 参与手数]
    for row in rows:
        users = row['seat_users'] or []
        for seat in range(4):
            user = users[seat] if seat < len(users) else None
            group = group_of(user, doms, tagged)
            first_white[group][2] += 1
            if row.get('first_white_seat') == seat:
                first_white[group][0] += 1
                if row['winner'] == seat and not row['is_draw']:
                    first_white[group][1] += 1

    report = {}
    for group in ('我方(v10 实验版)', '压制组', '榜上强手(非压制)', '其他对手'):
        dealer_total, dealer_wins, dealer_score = dealer_stats(group)
        entry = dict(
            seat_hands=size[group],
            white=dict(
                zero=[white[group][0][0], white[group][0][1]],
                one=[white[group][1][0], white[group][1][1]],
                two_plus=[sum(v[0] for k, v in white[group].items() if k >= 2),
                          sum(v[1] for k, v in white[group].items() if k >= 2)],
                baotou_share=(marks[group]['爆头'] / marks[group]['胜局']) if marks[group]['胜局'] else None,
                piao_share=(marks[group]['财飘'] / marks[group]['胜局']) if marks[group]['胜局'] else None,
            ),
            dealer=dict(hands=dealer_total, win_rate=(dealer_wins / dealer_total) if dealer_total else None,
                        net_per_hand=(dealer_score / dealer_total) if dealer_total else None,
                        stints=sum(stints[group].values())),
            stint=dict(mean=(sum(k * v for k, v in stints[group].items()) / max(1, sum(stints[group].values()))),
                       share_ge2=(sum(v for k, v in stints[group].items() if k >= 2) / max(1, sum(stints[group].values()))),
                       dist={str(k): v for k, v in sorted(stints[group].items())}),
            best_game_wins=max(wins_per_game[group]) if wins_per_game[group] else None,
            first_white=dict(share=(first_white[group][0] / first_white[group][2]) if first_white[group][2] else None,
                             conversion=(first_white[group][1] / first_white[group][0]) if first_white[group][0] else None),
        )
        report[group] = entry

    board = json.loads(BEST_GAME.read_text())
    board_rows = []
    def walk(node):
        if isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            if 'user_id' in node:
                board_rows.append(node)
            for value in node.values():
                walk(value)
    walk(board)
    board_rows.sort(key=lambda row: -(row.get('score') or 0))
    report['榜单·单场分前八'] = [dict(name=row.get('name'), score=row.get('score'), wins=row.get('wins'),
                                      lianzhuang=row.get('lianzhuang'), baotou=row.get('baotou'))
                                 for row in board_rows[:8]]
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
