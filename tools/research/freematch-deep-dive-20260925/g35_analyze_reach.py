#!/usr/bin/env python3
"""G35：按完整桌统计硬无碰算子的触达和旧行为同动作重合。"""

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

from collections import Counter
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g35-public-supply-reach-20260927/result.json')
G11 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g11-shape-risk-behavior-20260927/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g35-public-supply-reach-20260927/analysis.json')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """仅计算冻结行为的描述统计，不把窗口误作独立完整桌。"""

    if OUT.exists():
        raise SystemExit("G35 行为分析已存在，拒绝覆盖")
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    old = json.loads(G11.read_text(encoding="utf-8"))
    if source["counts"]["accepted_parent_draw_discards"] != 62975 or old.get("outcome_blind") is not True:
        raise ValueError("G35/G11 来源身份或结果盲性质不符")
    old_choices = {(row["game_id"], row["round_no"], row["trigger_seq"]): row["candidate_action"]
                   for row in old["changed"]}
    result = {}
    for label, predicate in (
        ("hard_no_peng_gap3", lambda row: row["hard_no_peng"]),
        ("hard_no_peng_exact_score", lambda row: row["strict_hard_no_peng"]),
        ("smaller_supply_exact_score", lambda row: row["smaller_supply"]),
    ):
        rows = [row for row in source["rows"] if predicate(row)]
        tables = {row["game_id"] for row in rows}
        rooms = {row["room_id"] for row in rows}
        overlaps = 0
        same_actions = 0
        for row in rows:
            window = row["game_id"], row["round_no"], row["trigger_seq"]
            if window in old_choices:
                overlaps += 1
                same_actions += int(old_choices[window] == row["representatives"][label]["action_key"])
        fraction = len(tables) / 909
        result[label] = {"windows": len(rows), "complete_tables_touched": len(tables),
                         "rooms_touched": len(rooms), "table_touch_fraction": fraction,
                         "conditional_gain_needed_for_2_pts_per_all_tables": 2 / fraction if fraction else None,
                         "g11_window_overlap": overlaps, "g11_same_action": same_actions,
                         "g30_same_action": sum(row["representatives"][label]["same_as_g30_action"]
                                                for row in rows),
                         "white_count_distribution": dict(sorted(Counter(
                             row["white_count"] for row in rows).items())),
                         "standard_shanten_distribution": dict(sorted(Counter(
                             row["parent_standard_shanten"] for row in rows).items()))}
    payload = {"schema": "g35-public-supply-reach-analysis/1",
               "source_sha256": sha(SOURCE), "g11_sha256": sha(G11),
               "script_sha256": sha(Path(__file__)), "cohorts": result,
               "boundary": "909 张冻结父代完整桌的结果盲行为触达；条件收益量级只是门槛算术，不是预测或收益证据。"}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
