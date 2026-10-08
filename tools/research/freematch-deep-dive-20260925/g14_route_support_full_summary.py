#!/usr/bin/env python3
"""机械汇总 Q1 结果盲正向窗的旧指标与路线条数交集。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/freematch-deep-dive-20260925'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g14-route-support-full-20260927/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g14-route-support-full-20260927/analysis.json')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """按完成桌聚类，明确哪些所谓增益其实已有即时/路线宽度。"""
    if OUT.exists():
        raise SystemExit("全房路线压力分析已存在，拒绝覆盖")
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    rows = source["positive_rows"]
    if (source["outcome_blind"] is not True or source["room_limit"] != 91 or
            len(source["selected_rooms"]) != 91 or
            len(rows) != source["counts"]["q1_positive_windows"]):
        raise ValueError("全房结果身份或窗口数漂移")
    counts = Counter()
    scopes = defaultdict(set)
    whites = Counter()
    examples = []
    for row in rows:
        p, a = row["parent_shape"], row["alternative_shape"]
        summary_equal = all(p[name] == a[name] for name in ("standard", "combined"))
        exact_vectors = row["exact_immediate_vectors"]
        route_equal = row["parent_routes"] == row["alternative_routes"]
        outside_g10_g11 = not (row["old_action"]["g10"] or row["old_action"]["g11"])
        flags = {
            "positive": True,
            "old_summary_equal": summary_equal,
            "exact_immediate_vectors": exact_vectors,
            "route_count_equal": route_equal,
            "outside_g10_g11": outside_g10_g11,
            "old_summary_equal_and_route_count_equal": summary_equal and route_equal,
            "exact_vectors_and_route_count_equal": exact_vectors and route_equal,
            "old_summary_equal_route_count_equal_outside_g10_g11": (
                summary_equal and route_equal and outside_g10_g11),
            "exact_vectors_outside_g10_g11": exact_vectors and outside_g10_g11,
            "p28_observed": row["old_action"]["p28_observed"],
            "same_p28_action": (row["old_action"]["p28a"] or
                                 row["old_action"]["p28b"]),
        }
        for name, enabled in flags.items():
            if enabled:
                counts[name] += 1
                scopes[name].add(row["game_id"])
        whites[str(row["white_after"])] += 1
        if summary_equal and route_equal:
            examples.append({key: row[key] for key in (
                "room_id", "game_id", "round_no", "trigger_seq",
                "parent_action", "alternative_action", "white_after",
                "parent_q1", "alternative_q1", "parent_routes",
                "alternative_routes", "score_gap", "old_action")})
    result = {"schema": "g14-route-support-full-analysis/1",
              "outcome_blind": True, "source_result_sha256": sha(SOURCE),
              "script_sha256": sha(Path(__file__)),
              "counts": dict(sorted(counts.items())),
              "complete_tables": {name: len(ids) for name, ids in sorted(scopes.items())},
              "whites": dict(sorted(whites.items())),
              "old_summary_and_route_count_equal_rows": examples,
              "boundary": "仅父代已观察到的完整桌触达数；改选后轨迹可能变化，不是收益上界。"}
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True,
                              indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"counts": result["counts"],
                      "complete_tables": result["complete_tables"]},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
