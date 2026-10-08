"""汇总已落盘的同观察评分差异；不执行模型、规则模拟或候选代码。"""
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

import json
from collections import Counter
from pathlib import Path


def main() -> None:
    """写出可复核的方向计数和例子；重复观察保留，另报告去重数量。"""
    root = _project_file(_PROJECT_ROOT, Path(__file__).resolve().parent / "known-root-diagnostic")
    pairs: Counter[tuple[str, str, str]] = Counter()
    views: set[str] = set()
    examples = []
    total = 0
    for line in (root / "comparisons.jsonl").read_text().splitlines():
        row = json.loads(line)
        total += 1
        if not row["preferred_changed"]:
            continue
        assert row["primary"]["status"] == row["shadow"]["status"] == "SCORED"
        parent, child = (row["primary"], row["shadow"])
        if row["context"]["active"] == "child":
            parent, child = child, parent
        pair = (row["observation"]["phase"], parent["preferred"].split(":")[0],
                child["preferred"].split(":")[0])
        pairs[pair] += 1
        if row["view_sha256"] not in views and len(examples) < 3:
            examples.append({"view_sha256": row["view_sha256"],
                             "observation": row["observation"],
                             "parent_preferred": parent["preferred"],
                             "child_preferred": child["preferred"],
                             "parent_scores": parent["scores"],
                             "child_scores": child["scores"]})
        views.add(row["view_sha256"])
    result = {"schema": "sitin-real-disagreement-summary/1",
              "comparison_count": total,
              "changed_comparison_count": sum(pairs.values()),
              "distinct_changed_candidate_views": len(views),
              "pairs": [{"phase": p, "parent_action_type": a,
                         "child_action_type": b, "count": n}
                        for (p, a, b), n in sorted(pairs.items())],
              "examples": examples,
              "interpretation": "已消费开发根上的描述性计数；不同观察及轨迹有相关性，不是独立效果样本"}
    summary = json.loads((root / "summary.json").read_text())
    assert total == summary["counts"]["views"]
    assert sum(pairs.values()) == summary["counts"]["preferred_changed"]
    assert len(views) == summary["saved_views"]
    (root / "disagreement-summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
