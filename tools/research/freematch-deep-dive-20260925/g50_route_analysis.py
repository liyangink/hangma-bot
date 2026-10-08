#!/usr/bin/env python3
"""G50：从冻结复跑轨迹复算自然成面、留白及收益方向的可比子集。"""

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
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g50-g49-route-forensic-20260927/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g50-g49-route-forensic-20260927/analysis.json')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def direction(after: int, before: int) -> str:
    return "lower" if after < before else "higher" if after > before else "same"


def main() -> None:
    """只统计结果已看的开发轨迹；没有下一窗口时按截尾，不补造牌山概率。"""

    if OUT.exists():
        raise SystemExit("G50 分析已存在，拒绝覆盖")
    frozen = json.loads(SOURCE.read_text(encoding="utf-8"))
    rows = frozen["rows"]
    if len(rows) != 23 or frozen["adoption_count"] != 34:
        raise ValueError("G50 冻结改选入口漂移")
    if sum(row["table_delta"] for row in rows) != 289:
        raise ValueError("G50 触达桌与 G49 全批净分不守恒")
    counts = Counter()
    strict = []
    for row in rows:
        before, after = row["baseline_next_two"], row["candidate_next_two"]
        if not before or not after:
            raise ValueError("G50 首个后续本人出牌窗口缺失")
        if (row["first_candidate"]["natural_standard_need_after"] -
                row["first_baseline"]["natural_standard_need_after"] != -1):
            raise ValueError("G49 首次改选没有自然缺口下降")
        counts["first|natural_gap_lower"] += 1
        counts["next1|natural_gap|" + direction(
            after[0]["natural_standard_need_after"], before[0]["natural_standard_need_after"])] += 1
        counts["next1|white|" + direction(after[0]["white_after"], before[0]["white_after"])] += 1
        if len(before) > 1 and len(after) > 1:
            counts["next2|both_present"] += 1
            counts["next2|natural_gap|" + direction(
                after[1]["natural_standard_need_after"], before[1]["natural_standard_need_after"])] += 1
            counts["next2|white|" + direction(after[1]["white_after"], before[1]["white_after"])] += 1
        else:
            counts["next2|censored"] += 1
        if row["same_intervening_actions"]:
            if (before[0]["drawn_tile"] is None or
                    before[0]["drawn_tile"] != after[0]["drawn_tile"]):
                raise ValueError("同中间行动不满足双方下一次真实摸牌相同")
            strict.append(row)
            counts["strict|score|" + ("positive" if row["table_delta"] > 0 else
                                      "negative" if row["table_delta"] < 0 else "zero")] += 1
            counts["strict|next1|natural_gap|" + direction(
                after[0]["natural_standard_need_after"], before[0]["natural_standard_need_after"])] += 1
            counts["strict|next1|white|" + direction(after[0]["white_after"], before[0]["white_after"])] += 1
            for field in ("standard_shanten_after", "seven_pairs_shanten_after",
                          "combined_shanten_after"):
                if type(before[0][field]) is int and type(after[0][field]) is int:
                    counts["strict|next1|" + field + "|" +
                           direction(after[0][field], before[0][field])] += 1
            if len(before) > 1 and len(after) > 1:
                counts["strict|next2|natural_gap|" + direction(
                    after[1]["natural_standard_need_after"], before[1]["natural_standard_need_after"])] += 1
                counts["strict|next2|white|" + direction(after[1]["white_after"], before[1]["white_after"])] += 1
                if (before[1]["drawn_tile"] is not None and
                        before[1]["drawn_tile"] == after[1]["drawn_tile"]):
                    counts["strict|next2|same_actual_draw"] += 1
    if len(strict) != 16 or counts["next2|both_present"] != 22:
        raise ValueError("G50 严格同路径可比子集漂移")
    top = sorted(rows, key=lambda row: row["table_delta"], reverse=True)[:2]
    top_cases = []
    for row in top:
        details = row["candidate_hand_result"]["details"]
        if (row["candidate_hand_result"]["winner_seat"] != row["actual_focal_seat"]
                or not {"七对", "爆头"}.issubset(details)):
            raise ValueError("G50 顶部两张正分桌非我方七对爆头")
        top_cases.append({"table_id": row["table_id"], "delta": row["table_delta"],
                          "first_action": {"baseline": row["first_baseline"]["choice"],
                                           "candidate": row["first_candidate"]["choice"]},
                          "candidate_first_hand_details": details,
                          "first_hand_white_after": row["first_candidate"]["white_after"],
                          "next1_white_same": (row["candidate_next_two"][0]["white_after"] ==
                                               row["baseline_next_two"][0]["white_after"])})
    output = {"schema": "g50-g49-route-analysis/1",
              "source_sha256": sha(SOURCE), "script_sha256": sha(Path(__file__)),
              "counts": dict(sorted(counts.items())),
              "strict_table_count": len(strict),
              "top_two_positive_delta": sum(row["table_delta"] for row in top),
              "all_touched_table_delta": sum(row["table_delta"] for row in rows),
              "top_cases": top_cases,
              "strict_negative_cases": [
                  {"table_id": row["table_id"], "table_delta": row["table_delta"],
                   "next1_natural_gap": {"baseline": row["baseline_next_two"][0]["natural_standard_need_after"],
                                         "candidate": row["candidate_next_two"][0]["natural_standard_need_after"]}}
                  for row in strict if row["table_delta"] < 0],
              "boundary": "严格子集按赛后响应/下一真实摸牌筛出，仅用于检验机制可兑现性；不能据此推断总体因果收益或作为在线特征。"}
    OUT.write_text(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"counts": output["counts"], "strict_table_count": len(strict),
                      "top_two_positive_delta": output["top_two_positive_delta"],
                      "strict_negative_cases": output["strict_negative_cases"]},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
