#!/usr/bin/env python3
"""我方白板与庄家利用率的自测：只用本会话审计的权威 rule_state，避开按结果筛选的对手偏差。

口径：
- 爆头状态：任一决策窗口 `rule_state.baotou=True` 记该单局为"持爆头"；
- 飘链：任一窗口 `chain_count>=1` 记该单局为"已开链"；
- 抓打圈：任一窗口 `catch_play=True`；
- 庄家：该单局 `window.turn_seat` 与本人座位关系由 observation 快照给出（沿用 seats 映射）。

输出：按单局聚合的持爆头/开链/抓打圈比例，与 `hands` 特征（赢家、番型、分差）连接后的转化率。
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
ME = 'u_13495c3d79c8'


def main() -> None:
    files = sorted(glob.glob(str(_project_file(_PROJECT_ROOT, MAIN / 'artifacts/sessions/auto-match-a_*/audit/runs/*/participants' / ME / 'decisions.jsonl'))))
    hands = collections.defaultdict(lambda: collections.Counter())
    for path in files:
        with open(path, encoding='utf-8') as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if record.get('kind') != 'decision_input':
                    continue
                request = record['payload'].get('request') or {}
                window = request.get('window_key') or {}
                observation = request.get('observation') or {}
                state = observation.get('rule_state') or {}
                key = (window.get('game_id'), window.get('round_no'))
                entry = hands[key]
                entry['窗口'] += 1
                if state.get('baotou'):
                    entry['持爆头'] = 1
                if (state.get('chain_count') or 0) >= 1:
                    entry['已开链'] = 1
                if state.get('catch_play'):
                    entry['抓打圈'] = 1
                if any(tile == '白' for tile in (observation.get('my_hand') or [])):
                    entry['手握白'] = 1
                entry['剩余牌数'] = observation.get('remaining_tile_count') or entry['剩余牌数']
                entry['座位'] = window.get('seat')
    total = len(hands)
    stats = collections.Counter()
    for entry in hands.values():
        for key in ('持爆头', '已开链', '抓打圈', '手握白'):
            if entry.get(key):
                stats[key] += 1
    print('单局数', total)
    for key in ('手握白', '持爆头', '已开链', '抓打圈'):
        print('  %-6s %5d 单局（%.2f%%）' % (key, stats[key], 100 * stats[key] / max(1, total)))


if __name__ == '__main__':
    main()
