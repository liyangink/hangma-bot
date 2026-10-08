#!/usr/bin/env python3
"""扫描 decision_input 中的多路线覆盖；只读 JSONL，不重写审计。"""

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
import sys


def pareto(signatures):
    return [sig for sig in signatures if not any(
        other != sig and other[0] <= sig[0] and other[1] <= sig[1] and other[2] >= sig[2]
        for other in signatures
    )]


def main(root: str) -> None:
    counts = collections.Counter()
    for path in glob.glob(root.rstrip("/") + "/**/participants/u_13495c3d79c8/decisions.jsonl", recursive=True):
        with open(path, encoding="utf-8") as stream:
            for line in stream:
                if '"kind": "decision_input"' not in line:
                    continue
                record = json.loads(line)
                request = record.get("payload", {}).get("request", {})
                window = request.get("window_key", {})
                if window.get("phase") != "draw":
                    continue
                signatures = []
                for candidate in request.get("rules", {}).get("legal_candidates", ()):
                    if (candidate.get("action") or {}).get("kind") != "discard":
                        continue
                    facts = candidate.get("facts") or {}
                    if facts.get("fact_kind") != "hand_progress":
                        continue
                    if facts.get("completeness") != "complete":
                        continue
                    standard = facts.get("standard_shanten_after")
                    pairs = facts.get("seven_pairs_shanten_after")
                    if standard is None or pairs is None:
                        continue
                    outs = sum(tile.get("remaining_estimate", 0) for tile in facts.get("useful_tiles", ()))
                    signatures.append((standard, pairs, outs, candidate.get("action_key")))
                counts["draw_windows"] += 1
                counts["complete_candidates"] += len(signatures)
                frontier = pareto(signatures)
                if len(frontier) > 1:
                    counts["multi_route_windows"] += 1
                    counts["frontier_candidates"] += len(frontier)
    print(json.dumps(dict(counts), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main(sys.argv[1])
