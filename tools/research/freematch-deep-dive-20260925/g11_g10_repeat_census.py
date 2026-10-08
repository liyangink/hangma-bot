#!/usr/bin/env python3
"""仅用 G10 已冻结动作前行，审计同一牌局单局内的重复路线机会。"""

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

from collections import defaultdict
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g10-route-option-screen-20260927/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g11-g10-repeat-census-20260927/result.json')


def main() -> None:
    """按审计 game_id 和 round_no 分组，不把未核实的 ID 冒充完整桌。"""

    if OUT.exists():
        raise SystemExit("G11 重复机会审计已存在，拒绝覆盖")
    source_bytes = SOURCE.read_bytes()
    source = json.loads(source_bytes)
    if source.get("outcome_blind") is not True or source.get("schema") != "g10-route-option-outcome-blind-screen/1":
        raise ValueError("G10 来源不是冻结的结果盲筛查")
    groups: dict[tuple[str, int], list[dict]] = defaultdict(list)
    seen = set()
    for row in source["rows"]:
        window = (row["game_id"], row["round_no"], row["trigger_seq"])
        if window in seen:
            raise ValueError("重复的动作窗口")
        seen.add(window)
        groups[window[:2]].append(row)

    def count(kind: str | None) -> dict[str, int]:
        sizes = [sum(kind is None or kind in row["route_improvements"] for row in group)
                 for group in groups.values()]
        positive = [size for size in sizes if size]
        return {"screened_rounds": len(positive), "rows": sum(positive),
                "rounds_with_2_or_more": sum(size >= 2 for size in positive),
                "rounds_with_3_or_more": sum(size >= 3 for size in positive),
                "max_rows_in_round": max(positive, default=0)}

    mixed = sum(any("standard" in row["route_improvements"] for row in group)
                and any("seven_pairs" in row["route_improvements"] for row in group)
                for group in groups.values())
    result = {"schema": "g11-g10-repeat-census/1", "outcome_blind": True,
              "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
              "source_parent_sha256": source["source_parent_sha256"],
              "all": count(None), "standard": count("standard"),
              "seven_pairs": count("seven_pairs"), "mixed_route_rounds": mixed,
              "white_2_or_more_rows": sum(row["white_count"] >= 2 for row in source["rows"]),
              "boundary": "仅 G10 窄谓词的同一 game_id/round_no 重复；非 G11 覆盖、非核验完整桌、非收益。"}
    OUT.parent.mkdir(parents=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
