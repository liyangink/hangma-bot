#!/usr/bin/env python3
"""决策族普查：在真实自由赛审计上统计各类决策窗口的自然频率。

用途：给出"已验证/未验证"覆盖面的量化地图——哪些窗口族已被反事实筛选覆盖、
哪些仍是空白，以及它们的出现频率（决定值不值得投入）。

统计项（每座位决策窗口）：
- 阶段分布（draw / response_peng / response_chi）；
- 抓打圈活跃窗口（rule_state.catch_play 为真）；
- 摸牌窗口中"弃牌后即听牌"的比例（是否具备一摸价值见证的可能）；
- 响应窗口中合法鸣牌候选数 ≥2 的窗口（同时可吃可碰等）；
- 含杠候选的窗口；
- 保底动作族分布（弃牌/过/吃/碰/杠/胡）。
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


def main(main_root: Path, output: Path | None) -> None:
    pattern = str(main_root / 'artifacts/sessions/auto-match-a_*/audit/runs/*/participants/u_13495c3d79c8/decisions.jsonl')
    files = sorted(glob.glob(pattern))
    stats = collections.Counter()
    chosen = collections.Counter()
    for path in files:
        with open(path, encoding='utf-8') as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if record.get('kind') != 'decision_input':
                    continue
                payload = record['payload']
                window = payload.get('window') or {}
                phase = window.get('phase')
                request = payload.get('request') or {}
                observation = request.get('observation') or {}
                rules = request.get('rules') or {}
                stats['窗口总数'] += 1
                stats['阶段-{0}'.format(phase)] += 1
                rule_state = (observation.get('rule_state') or {})
                if rule_state.get('catch_play'):
                    stats['抓打圈活跃窗口'] += 1
                candidates = rules.get('legal_candidates') or []
                kinds = collections.Counter((c.get('action') or {}).get('kind') for c in candidates)
                if phase != 'draw':
                    claims = kinds.get('chi', 0) + kinds.get('peng', 0) + kinds.get('gang', 0)
                    if claims >= 2:
                        stats['响应窗口·鸣牌候选≥2'] += 1
                    if kinds.get('gang', 0) >= 1:
                        stats['响应窗口·含杠候选'] += 1
                else:
                    discards = [c for c in candidates if (c.get('action') or {}).get('kind') == 'discard']
                    tenpai = 0
                    for candidate in discards:
                        facts = candidate.get('facts') or {}
                        if facts.get('shanten_after') == 0:
                            tenpai += 1
                    if tenpai:
                        stats['摸牌窗口·存在听牌候选'] += 1
                    if kinds.get('hu', 0):
                        stats['摸牌窗口·可胡'] += 1
                if kinds.get('hu', 0):
                    stats['含胡候选窗口'] += 1
    total = stats['窗口总数'] or 1
    report = dict(files=len(files), stats=dict(stats),
                  shares={key: round(value / total, 4) for key, value in stats.items() if key != '窗口总数'})
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
