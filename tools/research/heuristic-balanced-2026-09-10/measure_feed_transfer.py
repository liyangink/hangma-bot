#!/usr/bin/env python3
"""喂牌风险结构的跨环境对照：真实对手牌谱 vs 本地模拟表。

用与 build_feed_table.py 完全相同的单元格（牌张类别 × 墙余带）与被鸣判定，在
夜间战役官方牌谱上复算，检验"中路 > 幺九 > 字牌""早局高于残局"的结构是否迁移。
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

import argparse
import collections
import gzip
import json
from pathlib import Path

HONORS = ('东', '南', '西', '北', '中', '发', '白')


def category(tile: str) -> str:
    if tile in HONORS:
        return 'honor'
    if len(tile) == 2 and tile[0] in '19':
        return 'terminal'
    return 'middle'


def band(wall: int) -> str:
    return 'opening' if wall >= 80 else '64_79' if wall >= 64 else '40_63' if wall >= 40 else 'le39'


def main(pool: Path, output: Path | None):
    cells = collections.defaultdict(lambda: [0, 0])
    kinds = collections.Counter()
    hands = 0
    for path in sorted(pool.glob('hands/*.hands.jsonl.gz')):
        with gzip.open(path, 'rt', encoding='utf-8') as handle:
            for line in handle:
                hand = json.loads(line)
                hands += 1
                events = hand.get('events') or []
                draws = 0
                pending = None  # (seat, tile, wall_after)
                for event in events:
                    kind = event.get('type')
                    if kind == 'tile_drawn':
                        draws += 1
                        pending = None
                    elif kind == 'tile_discarded':
                        if pending is not None:
                            # 上一条弃牌未在本次弃牌前被鸣，记为未被鸣
                            pass
                        wall = 83 - draws
                        pending = (event.get('seat'), event.get('tile'), wall)
                    elif kind in ('chi', 'peng', 'gang') and pending is not None:
                        claimed_tiles = str(event.get('tile') or '').split(',')
                        if pending[1] in claimed_tiles:
                            cell = (category(pending[1]), band(pending[2]))
                            cells[cell][0] += 1
                            cells[cell][1] += 1
                            kinds[kind] += 1
                            pending = None
    # 分母：所有弃牌（含未被鸣）；重新遍历一次以统计分母
    totals = collections.defaultdict(int)
    for path in sorted(pool.glob('hands/*.hands.jsonl.gz')):
        with gzip.open(path, 'rt', encoding='utf-8') as handle:
            for line in handle:
                hand = json.loads(line)
                draws = 0
                for event in hand.get('events') or []:
                    kind = event.get('type')
                    if kind == 'tile_drawn':
                        draws += 1
                    elif kind == 'tile_discarded':
                        totals[(category(event.get('tile')), band(83 - draws))] += 1
    report = dict(source='night_real_opponents', hands=hands,
                  by_kind=dict(kinds),
                  cells={f'{key[0]}|{key[1]}': dict(discards=totals[key], claimed=value[1],
                                                    rate=value[1] / totals[key] if totals[key] else None)
                         for key, value in sorted(cells.items())},
                  category_rates={name: dict(
                      discards=sum(v for k, v in totals.items() if k[0] == name),
                      claimed=sum(v[1] for k, v in cells.items() if k[0] == name),
                      rate=(sum(v[1] for k, v in cells.items() if k[0] == name) /
                            max(1, sum(v for k, v in totals.items() if k[0] == name))))
                      for name in ('honor', 'terminal', 'middle')})
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + chr(10)
    if output:
        output.write_text(rendered, encoding='utf-8')
    print(rendered)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('pool', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    main(args.pool, args.output)
