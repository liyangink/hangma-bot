#!/usr/bin/env python3
"""复算已开放 P86 开发根中单次弃胡改收胡的有限样本最好可能均值。"""

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
import statistics


HERE = Path(__file__).resolve().parent
P86 = (_project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p86-hu-deferral-development-teacher-02-20260925/result.json'))
SCOPE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g9-hu-deferral-scope-20260927/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g9-hu-switch-finite-envelope-20260927/result.json')


def main() -> None:
    """按独立根先平均未来墙，再逐根选择收胡或保持父代；不作跨根外推。"""

    if OUT.exists():
        raise SystemExit("有限样本价值边界已存在，拒绝覆盖")
    p86_bytes = P86.read_bytes()
    p86 = json.loads(p86_bytes)
    scope_bytes = SCOPE.read_bytes()
    scope = json.loads(scope_bytes)
    states = p86["states"]
    if len(states) != 16 or Counter(row["source"]["mix"] for row in states) != Counter({"H": 8, "M": 8}):
        raise ValueError("P86 十六个 H/M 开发根身份漂移")
    if (p86["mechanical_ok"] is not True or p86["paired_future_walls"] != 512
            or p86["current_full_tables"] != 1024):
        raise ValueError("P86 双臂完整桌机械账不符")
    roots = [row["source"]["source_root_id"] for row in states]
    if len(set(roots)) != 16:
        raise ValueError("开发根重复")
    rows = []
    for row in states:
        values = row["future_wall_recheck_table_values"]
        if len(values) != 16:
            raise ValueError("每根的独立未来墙复查不是十六份")
        mean = statistics.mean(values)
        if mean != row["future_wall_recheck_mean_hu_minus_discard_current_table_score"]:
            raise ValueError("P86 根均值与未来墙原数不一致")
        rows.append({"source_root_id": row["source"]["source_root_id"],
                     "mix": row["source"]["mix"],
                     "hu_minus_parent_table_mean": mean,
                     "hindsight_root_choice_gain": max(0.0, mean)})
    by_mix = {}
    for mix in ("H", "M"):
        group = [row for row in rows if row["mix"] == mix]
        by_mix[mix] = {"roots": len(group),
                       "positive_hu_roots": sum(row["hu_minus_parent_table_mean"] > 0 for row in group),
                       "always_hu_mean": statistics.mean(row["hu_minus_parent_table_mean"] for row in group),
                       "hindsight_root_choice_mean": statistics.mean(row["hindsight_root_choice_gain"] for row in group)}
    overall = statistics.mean(row["hindsight_root_choice_gain"] for row in rows)
    scope_row = scope["scopes"]["nonwealth_baotou_deferral"]
    if scope_row["official_complete_table_ids"] != 281 or scope["source_official_complete_tables"] != 909:
        raise ValueError("官方目标动作影响量级漂移")
    result = {"schema": "g9-hu-switch-finite-envelope/1",
              "p86_result_sha256": hashlib.sha256(p86_bytes).hexdigest(),
              "official_scope_sha256": hashlib.sha256(scope_bytes).hexdigest(),
              "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "development_roots": 16, "by_mix": by_mix,
              "hindsight_root_choice_mean": overall,
              "required_net_gain_per_affected_official_table_for_plus2_overall":
                  scope_row["required_net_gain_per_affected_table_for_plus2_overall"],
              "rows": rows,
              "boundary": "只对 P86 已开放的十六个自然开发根、每根固定动作前观察和十六份复查未来墙成立；逐根事后最优选择不能上线，也不是总体收益上界"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "rows"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
