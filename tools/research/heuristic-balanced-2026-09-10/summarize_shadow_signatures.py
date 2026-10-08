"""汇总影子审计中的路线签名，避免把低频候选误判为收益来源。"""
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
import json
import re
from pathlib import Path

SIGNATURE = re.compile(r"路线签名=([^；]+)")


def main(path: Path, output: Path | None = None) -> None:
    counts: collections.Counter[str] = collections.Counter()
    frontier_sizes: collections.Counter[int] = collections.Counter()
    windows = 0
    raw = path.read_text(encoding="utf-8")
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            rows = parsed.get("notes", parsed.get("changes", [parsed] if "reason" in parsed else []))
        else:
            rows = parsed
    except json.JSONDecodeError:
        rows = (json.loads(line) for line in raw.splitlines() if line.strip())
    for row in rows:
            reason = str(row.get("reason", ""))
            match = SIGNATURE.search(reason)
            if not match:
                continue
            windows += 1
            signatures = [item for item in match.group(1).split(";") if item]
            frontier_sizes[len(signatures)] += 1
            for signature in signatures:
                counts[signature] += 1
    result = {
        "windows": windows,
        "unique_signatures": len(counts),
        "frontier_size_distribution": {str(k): v for k, v in sorted(frontier_sizes.items())},
        "signatures": dict(counts),
    }
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if output is not None:
        output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    main(args.path, args.output)
