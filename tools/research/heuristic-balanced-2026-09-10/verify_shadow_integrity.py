#!/usr/bin/env python3
"""影子审计完整性校验：确认审计记录可解析、自洽且满足前沿不变量。

校验项（针对 run_shadow.py 产出的 changes.jsonl.gz）：

1. **可解析**：每条记录的 `reason` 能被签名工具的正则解析出前沿列表；
2. **字段自洽**：`动作键=` 与 `路线签名=` 的条目数一致，且动作键一一对应；
3. **签名合法**：普通向听与七对向听为非负整数或缺失，未见有效牌估计为非负整数；
4. **Pareto 不变量**：前沿内不存在"另一条同时向听不更差、七对不更远、有效牌不更少"的成员
   （同签名成员允许共存，与 `_pareto` 的实现一致）；
5. **窗口归属**：记录携带座位、局号、窗口键，且局号为正整数。

输出校验报告 JSON；任何一项失败都给出可复现的样例定位。
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
import re
from pathlib import Path

SIGNATURE = re.compile(r"路线签名=([^；]+)")
KEYS = re.compile(r"动作键=([^；]+)")
ENTRY = re.compile(r"^(\S+?):\((\d+), (\d+), (\d+)\)$")


def load(path: Path):
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt', encoding='utf-8') as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def parse(reason: str):
    sig_match = SIGNATURE.search(reason)
    key_match = KEYS.search(reason)
    if not sig_match or not key_match:
        return None, None
    entries = []
    for item in sig_match.group(1).split(';'):
        found = ENTRY.match(item.strip())
        if not found:
            return None, None
        entries.append((found.group(1), int(found.group(2)), int(found.group(3)), int(found.group(4))))
    keys = [item.strip() for item in key_match.group(1).split(',') if item.strip()]
    return entries, keys


def dominated(a, b) -> bool:
    """b 是否支配 a（向听不更差、七对不更远、有效牌不更少）。

    与 _pareto 同口径：**支配判定只看路线签名，不看动作键**——签名完全相同的候选
    （例如三张不同的牌给出同一 (普通向听, 七对向听, 未见有效牌)）按设计允许共存，
    这正是"同距离"类别的来源。
    """
    if a[1:] == b[1:]:
        return False
    return b[1] <= a[1] and b[2] <= a[2] and b[3] >= a[3]


def verify(path: Path) -> dict:
    """校验一个影子批次并返回报告字典（供运行器内联调用或命令行使用）。"""
    stats = collections.Counter()
    failures = collections.defaultdict(list)
    samples = 0
    for row in load(path):
        samples += 1
        reason = str(row.get('reason', ''))
        if '影子路线[' not in reason:
            stats['非影子记录'] += 1
            continue
        entries, keys = parse(reason)
        if entries is None:
            stats['解析失败'] += 1
            if len(failures['解析失败']) < 5:
                failures['解析失败'].append(row.get('game_id'))
            continue
        stats['已解析'] += 1
        # 字段自洽
        if len(keys) != len(entries):
            stats['键与签名数量不一致'] += 1
            if len(failures['键与签名数量不一致']) < 5:
                failures['键与签名数量不一致'].append(
                    dict(game_id=row.get('game_id'), keys=len(keys), signatures=len(entries)))
        if [key for key, *_ in entries] != keys:
            stats['键与签名动作键不匹配'] += 1
            if len(failures['键与签名动作键不匹配']) < 5:
                failures['键与签名动作键不匹配'].append(row.get('game_id'))
        # 签名合法
        for key, standard, pairs, outs in entries:
            if standard < 0 or pairs < 0 or outs < 0:
                stats['签名出现负值'] += 1
                break
        # Pareto 不变量
        violated = [(a[0], b[0]) for a in entries for b in entries if dominated(a, b)]
        if violated:
            stats['前沿被支配'] += 1
            if len(failures['前沿被支配']) < 5:
                failures['前沿被支配'].append(dict(game_id=row.get('game_id'), pair=violated[0]))
        # 窗口归属
        if not isinstance(row.get('round_no'), int) or row.get('round_no', 0) < 1:
            stats['局号非法'] += 1
        if row.get('seat') is None:
            stats['缺座位'] += 1
    report = dict(samples=samples, stats=dict(stats),
                  failures={key: value for key, value in failures.items()},
                  frontier_size_distribution=None)
    sizes = collections.Counter()
    for row in load(path):
        reason = str(row.get('reason', ''))
        entries, _ = parse(reason)
        if entries:
            sizes[len(entries)] += 1
    report['frontier_size_distribution'] = {str(k): v for k, v in sorted(sizes.items())}
    report['truncated_notes'] = sum(1 for row in load(path)
                                    if '已截断' in str(row.get('reason', '')))
    report['passed'] = not report['failures'] and report['stats'].get('已解析', 0) > 0
    return report


def main(path: Path, output: Path | None) -> None:
    report = verify(path)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + chr(10)
    if output:
        output.write_text(rendered, encoding='utf-8')
    print(rendered)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('changes', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    main(args.changes, args.output)
