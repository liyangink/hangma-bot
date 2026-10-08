#!/usr/bin/env python3
"""G19 测量纠偏：把二摸条件收益与早已可见的当前有效容量/牌种分开。"""

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

import g19_near_win_two_draw_probe as g19


HERE = Path(__file__).resolve().parent
G14 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g14-white-reserve-frontier-20260927')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g19-near-win-two-draw-20260927/immediate-proxy-decomposition.json')


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _key(row: dict) -> tuple[str, int, int]:
    return row["game_id"], row["round_no"], row["trigger_seq"]


def main() -> None:
    """审计 G19 正向窗是否仅重复根节点既有牌效；不打开结算标签。"""

    if OUT.exists():
        raise SystemExit("G19 即时代理分解已存在，拒绝覆盖")
    source = json.loads((_project_file(_PROJECT_ROOT, G14 / "result.json")).read_text(encoding="utf-8"))
    result = json.loads(g19.OUT.read_text(encoding="utf-8"))
    if (source.get("rows_sha256") != _sha(_project_file(_PROJECT_ROOT, G14 / "rows.jsonl.gz")) or
            result.get("rows_sha256") != _sha(g19.ROWS) or
            source.get("parent_source_sha256") != result.get("parent_source_sha256")):
        raise ValueError("G14/G19 动作或结果摘要漂移")
    parent = {}
    for row in g19.g18._load_rows(_project_file(_PROJECT_ROOT, G14 / "rows.jsonl.gz")):
        key = _key(row)
        if key in parent:
            raise ValueError("G14 源窗口重复")
        parent[key] = row
    if len(parent) != 2134:
        raise ValueError("G14 母体窗口数漂移")
    counts: dict[str, Counter] = defaultdict(Counter)
    tables: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    seen = set()
    for row in g19.g18._load_rows(g19.ROWS):
        key = _key(row)
        source_row = parent.get(key)
        if (key in seen or source_row is None or
                source_row["parent_action"] != row["parent_action"] or
                source_row["alternative_action"] != row["alternative_action"]):
            raise ValueError("G19/G14 同窗动作未精确对账")
        seen.add(key)
        if "unavailable" in row:
            raise ValueError("G19 完整联合量具出现不可用窗")
        s1 = row["delta"]["1.0"]["unrestricted"]
        s05 = row["delta"]["0.5"]["unrestricted"]
        if abs(row["first_delta"]) > 1e-9 or s1 <= 1e-9:
            continue
        groups = ["first_hu_equal_free_s1_positive"]
        if s05 > 1e-9:
            groups.append("first_hu_equal_free_both_s_positive")
            if row["not_known_old_action"]:
                groups.append("known_old_action_distinct_both_s_positive")
        before = source_row["parent_shape"]
        after = source_row["alternative_shape"]
        for group in groups:
            cell = counts[group]
            cell["windows"] += 1
            tables[group]["windows"].add(key[0])
            for family in ("standard", "combined"):
                initial, changed = before[family], after[family]
                if initial is None or changed is None:
                    raise ValueError("原生产牌效摘要缺失")
                for dimension, index in (("capacity", 0), ("types", 1)):
                    difference = changed[index] - initial[index]
                    label = "up" if difference > 0 else "down" if difference < 0 else "equal"
                    cell[f"{family}_{dimension}_{label}"] += 1
                    tables[group][f"{family}_{dimension}_{label}"].add(key[0])
            cap_gain = after["combined"][0] - before["combined"][0]
            width_gain = after["standard"][1] - before["standard"][1]
            if cap_gain <= 0 and width_gain <= 0:
                cell["no_combined_capacity_or_standard_type_gain"] += 1
                tables[group]["no_combined_capacity_or_standard_type_gain"].add(key[0])
            if before["standard"] == after["standard"] and before["combined"] == after["combined"]:
                cell["same_current_immediate_summary"] += 1
                tables[group]["same_current_immediate_summary"].add(key[0])
            if row["combined_shanten"] == 1:
                cell["combined_shanten_one"] += 1
    if len(seen) != result["targets"] or len(seen) != 1415:
        raise ValueError("G19 1,415 窗未全部读入")
    output = {"schema": "g19-immediate-proxy-decomposition/1", "outcome_blind": True,
              "source_g14_rows_sha256": _sha(_project_file(_PROJECT_ROOT, G14 / "rows.jsonl.gz")),
              "source_g19_rows_sha256": _sha(g19.ROWS),
              "source_g19_result_sha256": _sha(g19.OUT),
              "script_sha256": _sha(Path(__file__)),
              "counts": {name: dict(sorted(cell.items())) for name, cell in sorted(counts.items())},
              "table_coverage": {name: {label: len(ids) for label, ids in sorted(group.items())}
                                 for name, group in sorted(tables.items())},
              "boundary": "第一摸立即胡价值为零并不代表当前有效牌事实相同；本项只拆当前生产容量和牌种，不能证明第二摸条件值对它们的独立增量，也不读整桌赛果。"}
    OUT.write_text(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps(output["counts"], ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
