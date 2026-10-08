#!/usr/bin/env python3
"""G125：按 G124 预登记判据一次性分析 G118 锁定机制集。"""

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

import g118_one_shanten_route_branch as g118
import g118_one_shanten_route_select as select


HERE = Path(__file__).resolve().parent
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G124-TWO-CLAIM-NATURAL-WIDTH-LOCKED-PREREG-2026-09-28.md')
SOURCE = g118.BASE / "locked_evaluation/rows.jsonl"
SUMMARY = g118.BASE / "locked_evaluation/result.json"
OUT = g118.BASE / "locked_evaluation/g125-analysis.json"


def sha(path: Path) -> str:
    """绑定事前判据、选样和只读输入原件。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """以窗口而非九个相关世界为比较单位，逐项固定判据签发。"""
    if OUT.exists():
        raise FileExistsError("G125 锁定分析已存在，拒绝覆盖")
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    selected = [item for item in json.loads(select.OUT.read_text(encoding="utf-8"))["selected"]
                if item["split"] == "locked_evaluation"]
    rows = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines()]
    if (summary["status"] != "complete" or len(rows) != 31 or len(selected) != 31
            or summary["windows_completed"] != 31):
        raise ValueError("G125 锁定分支未完整，不得分析")
    groups = defaultdict(list)
    windows = []
    for item, row in zip(selected, rows):
        if ([row["mix"], row["root_index"], row["focal_seat"], row["round_no"]]
                != item["window"] or row["observation_sha256"] != item["observation_sha256"]
                or row["score_facts"] != item["score_facts"]):
            raise ValueError("G125 锁定行与结果盲选样不一致")
        if (len(row["world_pairs"]) != 9 or
                [pair["sample_key"] for pair in row["world_pairs"]]
                != ["historical", *g118.g95.SAMPLES]):
            raise ValueError("G125 同窗九个世界的身份或顺序漂移")
        high_meld = item["score_facts"]["own_chi_peng_count"] >= 2
        key = row["mix"], "2plus" if high_meld else "1"
        deltas = [pair["focal_delta_alt_minus_parent"] for pair in row["world_pairs"]]
        value = mean(deltas)
        classes = Counter(pair["parent_class"] + "->" + pair["alternate_class"]
                          for pair in row["world_pairs"])
        groups[key].append(value)
        windows.append({
            "mix": row["mix"], "root_index": row["root_index"],
            "focal_seat": row["focal_seat"], "round_no": row["round_no"],
            "white_bin": row["white_bin"],
            "own_chi_peng_count": item["score_facts"]["own_chi_peng_count"],
            "parent_action": row["parent_action"],
            "alternate_action": row["alternate_action"],
            "mean_focal_delta_alt_minus_parent": value,
            "historical_focal_delta_alt_minus_parent": deltas[0],
            "outcome_transitions": dict(sorted(classes.items())),
        })
    expected = {("H", "2plus"): 3, ("H", "1"): 13,
                ("M", "2plus"): 4, ("M", "1"): 11}
    if {key: len(values) for key, values in groups.items()} != expected:
        raise ValueError("G125 预登记的副露组数分层不守恒")
    summaries = {}
    for key, values in sorted(groups.items()):
        summaries["/".join(key)] = {
            "windows": len(values), "mean_delta": mean(values),
            "positive_windows": sum(value > 0 for value in values),
            "negative_windows": sum(value < 0 for value in values),
            "zero_windows": sum(value == 0 for value in values),
        }
    gate = {
        "H_two_claim_positive": summaries["H/2plus"]["mean_delta"] > 0,
        "M_two_claim_positive": summaries["M/2plus"]["mean_delta"] > 0,
        "H_two_claim_signs": summaries["H/2plus"]["positive_windows"] >= 2,
        "M_two_claim_signs": summaries["M/2plus"]["positive_windows"] >= 3,
        "H_contrast_positive": summaries["H/2plus"]["mean_delta"]
                               > summaries["H/1"]["mean_delta"],
        "M_contrast_positive": summaries["M/2plus"]["mean_delta"]
                               > summaries["M/1"]["mean_delta"],
    }
    result = {
        "schema": "g125-two-claim-locked-analysis/1",
        "input_sha256": {"script": sha(Path(__file__)), "prereg": sha(PREREG),
                         "selection": sha(select.OUT), "rows": sha(SOURCE),
                         "summary": sha(SUMMARY)},
        "groups": summaries, "gate": gate,
        "carry_forward_to_new_panel": all(gate.values()),
        "windows": windows,
        "boundary": "本组只检验 G124 单阈值机制；通过亦非完整桌收益或发布证明。"
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"groups": summaries, "gate": gate,
                      "carry_forward_to_new_panel": result["carry_forward_to_new_panel"]},
                     ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
