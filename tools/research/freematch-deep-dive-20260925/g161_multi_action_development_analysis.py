#!/usr/bin/env python3
"""G161 开发层描述性拆账；不在此脚本中选候选阈值或打开锁定根。"""

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
import random
from statistics import mean


HERE = Path(__file__).resolve().parent
BASE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g161-multi-action-development-teacher-20260928')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g161-multi-action-development-teacher-20260928/analysis.json')
BOOTSTRAP_SEED = 20260928161
BOOTSTRAP_REPLICATES = 20_000


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parts(arm: dict, seat: int) -> dict[str, float]:
    """按本座官方结算拆普通自摸、高番自摸、他家胡付分与流局。"""
    final = arm["settlement"]
    delta = float(final["score_delta"][seat])
    parts = {"plain_self_win": 0.0, "special_self_win": 0.0,
             "other_win_payment": 0.0, "draw_delta": 0.0}
    if final["is_draw"]:
        parts["draw_delta"] = delta
    elif final["winner_seat"] == seat:
        parts["plain_self_win" if final["fan"] == 1
              else "special_self_win"] = delta
    else:
        parts["other_win_payment"] = delta
    if abs(sum(parts.values()) - delta) > 1e-9:
        raise ValueError("G161 单局本座积分拆账不守恒")
    return parts


def _first_compare(parent: int | None, alternate: int | None) -> str:
    if parent is None and alternate is None:
        return "neither"
    if parent is None:
        return "alternate_only"
    if alternate is None:
        return "parent_only"
    if alternate < parent:
        return "alternate_earlier"
    if alternate > parent:
        return "parent_earlier"
    return "same_index"


def _root_interval(rows: list[dict]) -> dict:
    """以独立牌山根重采样窗口均值；仅作开发描述区间。"""
    by_root = defaultdict(list)
    for row in rows:
        by_root[row["root_index"]].append(mean(
            pair["focal_delta_alt_minus_parent"] for pair in row["world_pairs"]))
    roots = [mean(values) for _, values in sorted(by_root.items())]
    if not roots:
        return {"roots": 0, "root_equal_mean": None, "bootstrap_95": None}
    rng = random.Random(BOOTSTRAP_SEED)
    estimates = sorted(mean(rng.choice(roots) for _ in roots)
                       for _ in range(BOOTSTRAP_REPLICATES))
    return {"roots": len(roots), "root_equal_mean": mean(roots),
            "bootstrap_95": [estimates[int(0.025 * BOOTSTRAP_REPLICATES)],
                             estimates[int(0.975 * BOOTSTRAP_REPLICATES)]]}


def analyse_group(rows: list[dict]) -> dict:
    """每窗先对 33 个相关世界求平均，再按窗口或根汇总。"""
    transitions = Counter()
    ready = Counter()
    highfan = Counter()
    paired_worlds = 0
    window_deltas = []
    component_window = defaultdict(list)
    for row in rows:
        seat = row["focal_seat"]
        pair_deltas = []
        component_pair = defaultdict(list)
        for pair in row["world_pairs"]:
            parent, alternate = pair["parent"], pair["alternate"]
            p, a = _parts(parent, seat), _parts(alternate, seat)
            parts_delta = {name: a[name] - p[name] for name in p}
            if abs(sum(parts_delta.values()) -
                   pair["focal_delta_alt_minus_parent"]) > 1e-9:
                raise ValueError("G161 父代／备选积分差拆账不守恒")
            for name, value in parts_delta.items():
                component_pair[name].append(value)
            pair_deltas.append(pair["focal_delta_alt_minus_parent"])
            transitions[pair["parent_class"] + " -> " + pair["alternate_class"]] += 1
            ready[_first_compare(parent["first_ready_draw_index"],
                                 alternate["first_ready_draw_index"])] += 1
            highfan[_first_compare(parent["first_highfan_draw_index"],
                                   alternate["first_highfan_draw_index"])] += 1
            paired_worlds += 1
        if len(pair_deltas) != 33:
            raise ValueError("G161 窗口未完成固定 33 个相关世界")
        window_deltas.append(mean(pair_deltas))
        for name, values in component_pair.items():
            component_window[name].append(mean(values))
    components = {name: mean(values) if values else None
                  for name, values in sorted(component_window.items())}
    if window_deltas and abs(sum(components.values()) - mean(window_deltas)) > 1e-9:
        raise ValueError("G161 窗口等权分量不守恒")
    return {"windows": len(rows), "related_world_pairs": paired_worlds,
            "window_equal_mean_delta": mean(window_deltas) if rows else None,
            "positive_windows": sum(x > 0 for x in window_deltas),
            "negative_windows": sum(x < 0 for x in window_deltas),
            "zero_windows": sum(x == 0 for x in window_deltas),
            "components_window_equal": components,
            "terminal_class_transitions": dict(sorted(transitions.items())),
            "first_ordinary_ready_comparison": dict(sorted(ready.items())),
            "first_highfan_entry_comparison": dict(sorted(highfan.items())),
            "root_cluster": _root_interval(rows)}


def main() -> None:
    if OUT.exists():
        raise FileExistsError("G161 描述拆账已存在，拒绝覆盖")
    result = json.loads((_project_file(_PROJECT_ROOT, BASE / "result.json")).read_text(encoding="utf-8"))
    source_rows = _project_file(_PROJECT_ROOT, BASE / "rows.jsonl")
    if (result["status"] != "complete" or result["windows_completed"] != 49
            or sha(source_rows) != result["rows_sha256"]):
        raise ValueError("G161 开发层结果不完整或摘要漂移")
    rows = [json.loads(line) for line in source_rows.read_text(
        encoding="utf-8").splitlines()]
    if len(rows) != 49:
        raise ValueError("G161 逐窗行数不符")
    groups = {"H": analyse_group([r for r in rows if r["mix"] == "H"]),
              "M": analyse_group([r for r in rows if r["mix"] == "M"])}
    for mix in ("H", "M"):
        for white in (0, 1):
            groups[f"{mix}/{white}"] = analyse_group([
                r for r in rows if r["mix"] == mix and r["white_before"] == white])
    payload = {"schema": "g161-multi-action-development-analysis/1",
               "source_rows_sha256": sha(source_rows),
               "source_result_sha256": sha(_project_file(_PROJECT_ROOT, BASE / "result.json")),
               "analysis_script_sha256": sha(Path(__file__)),
               "bootstrap_seed": BOOTSTRAP_SEED,
               "bootstrap_replicates": BOOTSTRAP_REPLICATES,
               "groups": groups,
               "boundary": "同世界相关单局、根级开发描述；非新候选完整桌效果。"}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                              indent=2) + "\n", encoding="utf-8")
    print(json.dumps({mix: {name: groups[mix][name] for name in (
        "windows", "window_equal_mean_delta", "components_window_equal",
        "root_cluster", "first_ordinary_ready_comparison",
        "first_highfan_entry_comparison")} for mix in ("H", "M")},
        ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
