#!/usr/bin/env python3
"""白板开链机会测量：在手握白且持爆头的真实窗口中，量化"弃白开链"的可选空间。

背景：我方手握白的单局占 51.2%，但打白率仅 0.03%、财飘占胜局 0.48%（压制组 1.14%）。
本脚本从真实审计（含候选事实与 rule_state）统计：

1. 持爆头且有白的摸牌窗口数；
2. 其中"弃白"为合法候选的窗口数；
3. 弃白候选**不损向听**（普通型向听 ≤ 当前所选）的窗口数——这是可无痛开链的子集；
4. 其中弃白候选带有"任意摸均成胡"路线（baotou 路线）的窗口数——开链后仍保任意听的窄集；
5. 对照：我方实际选择是弃白还是别的。

口径局限：真实审计批次多数未开价值分析，路线层（value_facts.routes）覆盖有限；本脚本同时
报告覆盖数，避免把"无证据"误读为"无机会"。
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
import glob
import json
from pathlib import Path

MAIN = Path('/Users/liyang/Projects/Opensource/hangma-bot')
ME = 'u_13495c3d79c8'


def standard_shanten(facts) -> int | None:
    if not isinstance(facts, dict):
        return None
    if facts.get('fact_kind') != 'hand_progress' or facts.get('completeness') != 'complete':
        return None
    value = facts.get('standard_shanten_after')
    if isinstance(value, int):
        return value
    value = facts.get('shanten_after')
    return value if isinstance(value, int) else None


def outs(facts) -> int:
    if not isinstance(facts, dict):
        return 0
    return sum(tile.get('remaining_estimate', 0) for tile in (facts.get('useful_tiles') or []))


def has_any_draw_route(candidate) -> bool:
    value_facts = candidate.get('value_facts') or {}
    for route in value_facts.get('routes') or []:
        conditions = route.get('conditions') or {}
        if conditions.get('draw_kind') == 'normal' and conditions.get('baotou'):
            return True
    return False


def main(main_root: Path, output: Path | None) -> None:
    files = sorted(glob.glob(str(main_root / 'artifacts/sessions/auto-match-a_*/audit/runs/*/participants' / ME / 'decisions.jsonl')))
    stats = collections.Counter()
    samples = []
    for path in files:
        planned = {}
        with open(path, encoding='utf-8') as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                kind = record.get('kind')
                context = record.get('context') or {}
                decision_id = context.get('decision_id')
                payload = record.get('payload') or {}
                if kind == 'decision_input':
                    window = payload.get('window') or {}
                    if window.get('phase') != 'draw':
                        continue
                    request = payload.get('request') or {}
                    planned[decision_id] = dict(window=window, request=request)
                elif kind == 'decision_planned' and decision_id in planned:
                    entry = planned.pop(decision_id)
                    request = entry['request']
                    observation = request.get('observation') or {}
                    state = observation.get('rule_state') or {}
                    hand = observation.get('my_hand') or []
                    if not state.get('baotou') or '白' not in hand:
                        continue
                    stats['持爆头且有白的摸牌窗口'] += 1
                    rules = request.get('rules') or {}
                    candidates = rules.get('legal_candidates') or []
                    chosen = ((payload.get('returned_plan') or {}).get('candidates') or [{}])[0].get('action_key')
                    chosen_candidate = next((c for c in candidates if c.get('action_key') == chosen), None)
                    chosen_shanten = standard_shanten((chosen_candidate or {}).get('facts'))
                    if chosen_shanten is None:
                        stats['所选无向听事实'] += 1
                        continue
                    white = next((c for c in candidates if c.get('action_key') == 'discard:白'), None)
                    if white is None:
                        stats['弃白不合法'] += 1
                        continue
                    stats['弃白合法'] += 1
                    white_shanten = standard_shanten(white.get('facts'))
                    if white_shanten is None:
                        stats['弃白无向听事实'] += 1
                        continue
                    stats['弃白有向听事实'] += 1
                    if white_shanten <= chosen_shanten:
                        stats['弃白不损向听'] += 1
                        if outs(white.get('facts')) >= outs((chosen_candidate or {}).get('facts')):
                            stats['弃白不损向听且不损有效牌'] += 1
                        if has_any_draw_route(white):
                            stats['弃白仍保任意听（可开链窄集）'] += 1
                            if len(samples) < 8:
                                samples.append(dict(game_id=entry['window'].get('game_id'),
                                                    round_no=entry['window'].get('round_no'),
                                                    chosen=chosen, chain=state.get('chain_count'),
                                                    white_shanten=white_shanten, chosen_shanten=chosen_shanten,
                                                    remaining=observation.get('remaining_tile_count')))
                    if chosen == 'discard:白':
                        stats['实际弃白'] += 1
    report = dict(data=dict(files=len(files), me=ME), stats=dict(stats), samples=samples)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + chr(10)
    if output:
        output.write_text(rendered, encoding='utf-8')
    print(rendered)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--main-root', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    main(args.main_root, args.output)
