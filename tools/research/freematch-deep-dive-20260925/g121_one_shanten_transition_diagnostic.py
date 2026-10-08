#!/usr/bin/env python3
"""G121：只读一向听开发集，核更早听牌与真实结算的错位。"""

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
import g119_one_shanten_development_analysis as g119


HERE = Path(__file__).resolve().parent
SOURCE = g119.SOURCE
OUT = g119.OUT.parent / "transition_diagnostic.json"


def first_tenpai_record(branch: dict) -> tuple[int, dict] | None:
    """按实际本人正常摸打链取首个普通型听牌后的公开事实。"""
    for index, record in enumerate(g100.draw_discards(branch)):
        if record["standard_shanten_after"] == 0:
            return index, record
    return None


def entry_relation(parent: tuple[int, dict] | None,
                   alternate: tuple[int, dict] | None) -> str:
    """比较两臂首次普通型听牌的本人正常摸打序号。"""
    if parent is None and alternate is None:
        return "neither"
    if parent is None:
        return "alternate_only"
    if alternate is None:
        return "parent_only"
    if alternate[0] < parent[0]:
        return "alternate_earlier"
    if parent[0] < alternate[0]:
        return "parent_earlier"
    return "same_index"


def main() -> None:
    """九世界保留配对关系；每窗均值仍是最小效果摘要。"""
    if OUT.exists():
        raise FileExistsError("G121 已有诊断，拒绝覆盖")
    rows = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines()]
    if len(rows) != 28 or any(len(row["world_pairs"]) != 9 for row in rows):
        raise ValueError("G121 开发分支不完整")
    groups = defaultdict(Counter)
    wait_deltas = defaultdict(list)
    windows = []
    for row in rows:
        group = row["mix"] + "/" + row["white_bin"]
        deltas = []
        local = Counter()
        for pair in row["world_pairs"]:
            delta = pair["focal_delta_alt_minus_parent"]
            deltas.append(delta)
            parent = first_tenpai_record(pair["parent"])
            alternate = first_tenpai_record(pair["alternate"])
            relation = entry_relation(parent, alternate)
            transition = pair["parent_class"] + "->" + pair["alternate_class"]
            for counts in (groups[group], local):
                counts["pairs"] += 1
                counts["entry/" + relation] += 1
                counts["outcome/" + transition] += 1
                counts["delta_sum"] += delta
                counts["entry_delta/" + relation] += delta
                counts["entry_negative/" + relation] += delta < 0
                counts["entry_positive/" + relation] += delta > 0
            if parent is not None and alternate is not None:
                p_tiles = parent[1]["standard_useful_tiles"]
                a_tiles = alternate[1]["standard_useful_tiles"]
                wait_deltas[group].append({
                    "code_count": len(a_tiles) - len(p_tiles),
                    "public_unseen_capacity":
                        sum(tile["public_unseen_capacity"] for tile in a_tiles)
                        - sum(tile["public_unseen_capacity"] for tile in p_tiles),
                })
        windows.append({
            "mix": row["mix"], "white_bin": row["white_bin"],
            "root_index": row["root_index"], "focal_seat": row["focal_seat"],
            "round_no": row["round_no"],
            "mean_focal_delta_alt_minus_parent": mean(deltas),
            "counts": dict(sorted(local.items())),
        })
    result = {
        "schema": "g121-one-shanten-transition-diagnostic/1",
        "input_sha256": {"script": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                         "development_rows": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                         "g119_analysis": hashlib.sha256(g119.OUT.read_bytes()).hexdigest()},
        "groups": {key: dict(sorted(value.items())) for key, value in sorted(groups.items())},
        "first_tenpai_wait_deltas_both_reached": {
            key: {"pairs": len(values),
                  "mean_code_count_delta": mean(item["code_count"] for item in values),
                  "mean_public_unseen_capacity_delta":
                      mean(item["public_unseen_capacity"] for item in values)}
            for key, values in sorted(wait_deltas.items())},
        "windows": windows,
        "boundary": "这是已看开发集的赛后诊断。九个隐藏世界同窗相关；首听牌等待面是后处理事实，"
                    "公开未见容量不是牌墙命中概率，不能作为线上未来信息或候选确认。",
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"groups": result["groups"],
                      "wait_deltas": result["first_tenpai_wait_deltas_both_reached"]},
                     ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
