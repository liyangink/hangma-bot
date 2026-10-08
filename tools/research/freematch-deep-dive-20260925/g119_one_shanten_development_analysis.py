#!/usr/bin/env python3
"""G119：只读 G118 开发根的自然成面、胡牌入口与结算转移。"""

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
from statistics import mean

import g100_analyze_visible_trajectory as g100
import g118_one_shanten_route_branch as g118


HERE = Path(__file__).resolve().parent
SOURCE = g118.BASE / "development/rows.jsonl"
OUT = g118.BASE / "development/analysis.json"


def sha(path: Path) -> str:
    """绑定开发分支原件及分析程序。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def first_tenpai(branch: dict) -> tuple[str, int | None]:
    """沿同一实际摸打链找弃牌后首次 0 向听；未知不能记为失败。"""
    draws = g100.draw_discards(branch)
    for index, record in enumerate(draws):
        shanten = record["standard_shanten_after"]
        if type(shanten) is int and shanten <= 0:
            return "reached", index
    if any(record["standard_shanten_after"] is None for record in draws):
        return "unknown", None
    return "not_reached", None


def compare_entry(parent: tuple[str, int | None], alternate: tuple[str, int | None]) -> str:
    """区分单边到达、双边先后与依法可见事实未知。"""
    ps, pi = parent
    as_, ai = alternate
    if "unknown" in (ps, as_):
        return "unknown"
    if ps == "reached" and as_ == "reached":
        if ai < pi:
            return "alternate_earlier"
        if pi < ai:
            return "parent_earlier"
        return "same_index"
    if ps == "reached":
        return "parent_only"
    if as_ == "reached":
        return "alternate_only"
    return "neither"


def route_state(pair: dict, arm: str, route: str) -> tuple[str, int | None]:
    """复用 G118 经生产规则和实际行动链核算的入口。"""
    row = pair["route_entry"][arm][route]
    return row["status"], row["first_normal_draw_discard_index"]


def main() -> None:
    """根级保留逐窗账，不读取 G118 锁定评估分支。"""
    if OUT.exists():
        raise FileExistsError("G119 开发分析已存在，拒绝覆盖")
    status = json.loads((g118.BASE / "development/result.json").read_text(
        encoding="utf-8"))
    if status["status"] != "complete":
        raise ValueError("G119 开发分支未全量完成")
    rows = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines()]
    if len(rows) != status["windows_planned"]:
        raise ValueError("G119 分支行数与清单不符")
    groups: dict[str, Counter] = defaultdict(Counter)
    windows = []
    for row in rows:
        counts = Counter()
        deltas = []
        for pair in row["world_pairs"]:
            if len(row["world_pairs"]) != 9:
                raise ValueError("G119 一个窗口不是九世界")
            delta = pair["focal_delta_alt_minus_parent"]
            deltas.append(delta)
            counts["world_pairs"] += 1
            counts["positive_pairs"] += delta > 0
            counts["negative_pairs"] += delta < 0
            counts["zero_pairs"] += delta == 0
            for label, states in (
                ("tenpai", (first_tenpai(pair["parent"]),
                            first_tenpai(pair["alternate"]))),
                ("ordinary", (route_state(pair, "parent", "ordinary"),
                              route_state(pair, "alternate", "ordinary"))),
                ("highfan", (route_state(pair, "parent", "highfan"),
                             route_state(pair, "alternate", "highfan"))),
            ):
                counts[label + "/" + compare_entry(*states)] += 1
                counts[label + "/parent_reached"] += states[0][0] == "reached"
                counts[label + "/alternate_reached"] += states[1][0] == "reached"
            counts["parent_special_win"] += pair["parent_class"] == "special_self_win"
            counts["alternate_special_win"] += pair["alternate_class"] == "special_self_win"
            counts["parent_plain_win"] += pair["parent_class"] == "plain_self_win"
            counts["alternate_plain_win"] += pair["alternate_class"] == "plain_self_win"
            counts["parent_other_win"] += pair["parent_class"] == "other_win"
            counts["alternate_other_win"] += pair["alternate_class"] == "other_win"
            for arm in ("parent", "alternate"):
                counts[arm + "_white_discards"] += sum(
                    record["action_key"] == "discard:白"
                    for record in pair[arm]["focal_trajectory"])
        group = row["mix"] + "/" + row["white_bin"]
        groups[group].update(counts)
        windows.append({
            "mix": row["mix"], "white_bin": row["white_bin"],
            "root_index": row["root_index"], "focal_seat": row["focal_seat"],
            "round_no": row["round_no"],
            "observation_sha256": row["observation_sha256"],
            "score_facts": row["score_facts"],
            "mean_focal_delta_alt_minus_parent": mean(deltas),
            "historical_focal_delta_alt_minus_parent": deltas[0],
            "counts": dict(sorted(counts.items())),
        })
    result = {
        "schema": "g119-one-shanten-development-analysis/1",
        "input_sha256": {
            "script": sha(Path(__file__)), "development_rows": sha(SOURCE),
            "selection": sha(g118.g118_select.OUT),
        },
        "windows": windows,
        "groups": {key: dict(sorted(value.items())) for key, value in sorted(groups.items())},
        "boundary": "只看 G118 开发根；九世界同窗相关，路线入口非最终胡，"
                    "不能根据已看分支拟合后再称其为确认。",
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"windows": len(windows),
                      "groups": result["groups"]}, ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
