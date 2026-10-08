"""P12 结果盲冻结：每个自然来源至多一个七对竞争状态。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ROOT = _PROJECT_ROOT
for path in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROUTE / "tools"), HERE):
    sys.path.insert(0, str(path))

import confirmation_execution_identity as guard  # noqa: E402
import r18_p12_natural_seven_pairs_frontier as p12  # noqa: E402


OUT = p12.OUT / "frozen-frontier.json"
QUOTAS = {0: 8, 1: 10, 2: 10}


def rank(split: str, row: dict[str, Any]) -> str:
    return hashlib.sha256(
        ("r18-p12-frontier-freeze|" + split + "|" + row["request_sha256"]).encode()
    ).hexdigest()


def select(rows: list[dict[str, Any]], split: str) -> list[dict[str, Any]]:
    chosen: list[dict[str, Any]] = []
    used_sources: set[str] = set()
    for shanten, quota in QUOTAS.items():
        eligible = sorted(
            [row for row in rows if row["split"] == split and
             row["seven_pairs_frontier"]["seven_pairs_shanten_after"] == shanten],
            key=lambda row: rank(split, row),
        )
        for row in eligible:
            if len([x for x in chosen if x["seven_pairs_frontier"]["seven_pairs_shanten_after"] == shanten]) >= quota:
                break
            if row["source_id"] in used_sources:
                continue
            chosen.append(row)
            used_sources.add(row["source_id"])
    target = min(28, len({row["source_id"] for row in rows if row["split"] == split}))
    for row in sorted([row for row in rows if row["split"] == split],
                      key=lambda item: rank(split, item)):
        if len(chosen) >= target:
            break
        if row["source_id"] not in used_sources:
            chosen.append(row)
            used_sources.add(row["source_id"])
    chosen.sort(key=lambda row: (row["source_id"], row["request_sha256"]))
    return chosen


def main() -> None:
    if OUT.exists():
        raise SystemExit("P12 冻结文件已存在；拒绝覆盖")
    p12.verify()
    dataset = json.loads((p12.OUT / "dataset.json").read_text(encoding="utf-8"))
    rows = dataset["rows"]
    development = select(rows, "development")
    hidden = select(rows, "hidden")
    if len(development) != 28 or len(hidden) != 28:
        raise ValueError("开发/隐藏各需 28 个独立来源状态")
    if len({row["source_id"] for row in development}) != len(development):
        raise ValueError("开发集来源重复")
    if len({row["source_id"] for row in hidden}) != len(hidden):
        raise ValueError("隐藏集来源重复")
    if {row["root_index"] for row in development} & {row["root_index"] for row in hidden}:
        raise ValueError("开发/隐藏根重叠")
    value = {
        "schema": "r18-p12-frozen-frontier/1",
        "runtime": guard.capture(source_paths=[
            Path(__file__), Path(p12.__file__), p12.OUT / "manifest.json",
            p12.OUT / "dataset.json",
        ]),
        "selection": "结果盲；七对向听0/1/2配额8/10/10，不足时按冻结哈希补齐；每来源最多一状态",
        "development": development,
        "hidden": hidden,
        "counts": {
            "development": len(development), "hidden": len(hidden),
            "development_shanten": dict(Counter(
                str(row["seven_pairs_frontier"]["seven_pairs_shanten_after"])
                for row in development)),
            "hidden_shanten": dict(Counter(
                str(row["seven_pairs_frontier"]["seven_pairs_shanten_after"])
                for row in hidden)),
        },
        "hidden_labels_opened": False,
        "development_only": True,
        "selection_eligible": False,
        "release_eligible": False,
    }
    OUT.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps(value["counts"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
