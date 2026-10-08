#!/usr/bin/env python3
"""影子签名分层：把 Pareto 前沿按"七对是否更近"分类，给出下一轮优先级。

输入：run_shadow.py 产出的 changes.jsonl(.gz)。每条记录含
`路线签名=discard:X:(普通向听,七对向听,未见有效牌)` 形式的前沿列表。
输出：窗口级类别分布与高频签名，供"有限多路线候选"筛选使用。
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
ENTRY = re.compile(r"^(\S+?):\((\d+), (\d+), (\d+)\)$")


def load_rows(path: Path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def classify(entries) -> str:
    """按七对相对普通型的距离差分类。

    - 七对更近：前沿中存在七对向听严格小于普通向听的候选；
    - 普通更近：前沿中全部候选的七对向听都严格大于普通向听；
    - 同距离：全部候选两者相等；
    - 混合：同一前沿内既有相等又有更远，或方向不一致。
    """
    near = any(pairs < standard for _, standard, pairs, _ in entries)
    far = any(pairs > standard for _, standard, pairs, _ in entries)
    same = any(pairs == standard for _, standard, pairs, _ in entries)
    if near:
        return "七对更近" if not same and not far else "七对更近(混合)"
    if far and same:
        return "混合"
    if far:
        return "普通更近"
    return "同距离"

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    windows = 0
    classes = collections.Counter()
    signatures = collections.Counter()
    by_class_signature = collections.defaultdict(collections.Counter)
    frontier_sizes = collections.Counter()
    for row in load_rows(args.path):
        match = SIGNATURE.search(str(row.get("reason", "")))
        if not match:
            continue
        entries = []
        for item in match.group(1).split(";"):
            found = ENTRY.match(item.strip())
            if found:
                entries.append((found.group(1), int(found.group(2)), int(found.group(3)), int(found.group(4))))
        if not entries:
            continue
        windows += 1
        frontier_sizes[len(entries)] += 1
        label = classify(entries)
        classes[label] += 1
        for key, standard, pairs, outs in entries:
            signatures[f"{key}:({standard},{pairs},{outs})"] += 1
            by_class_signature[label][f"{key}:({standard},{pairs},{outs})"] += 1

    result = {
        "windows": windows,
        "class_distribution": dict(classes),
        "class_share": {k: round(v / windows, 4) for k, v in classes.items()} if windows else {},
        "frontier_size_distribution": {str(k): v for k, v in sorted(frontier_sizes.items())},
        "top_signatures": dict(signatures.most_common(20)),
        "top_same_distance": dict(by_class_signature["同距离"].most_common(10)),
        "top_pairs_nearer": dict(by_class_signature["七对更近"].most_common(10)),
    }
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + chr(10)
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
