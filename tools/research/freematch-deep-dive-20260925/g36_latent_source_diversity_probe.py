#!/usr/bin/env python3
"""G36：冻结教师动作对中检验自然潜在源码分散度；不评估赛事收益。"""

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
import gzip
import hashlib
import json
from pathlib import Path

from hangma_bot.hangma.hand_analysis import analyse_counts_progress
from hangma_bot.kernel.actions import CANONICAL_TILE_INDEX, CANONICAL_TILE_ORDER


HERE = Path(__file__).resolve().parent
EVIDENCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence')
G23 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g23-three-draw-teacher-20260927/rows.jsonl.gz')
G29 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g29-room-disjoint-edge-20260927/rows.jsonl.gz')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g36-latent-source-diversity-20260927/result.json')
NATURAL = tuple(code for code in CANONICAL_TILE_ORDER if code != "白")
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G36-LATENT-SOURCE-DIVERSITY-PREREG-2026-09-27.md')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _degree(counts: tuple[int, ...], code: str) -> int:
    """自家自然牌中，可由摸入该码补成的不同刻子/顺子几何结构数。"""

    index = CANONICAL_TILE_INDEX[code]
    degree = int(counts[index] >= 2)
    if code[-1] in "wbt":
        rank, suit = int(code[0]), code[1]
        for start in range(max(1, rank - 2), min(rank, 7) + 1):
            others = (f"{value}{suit}" for value in range(start, start + 3)
                      if value != rank)
            degree += int(all(counts[CANONICAL_TILE_INDEX[other]] > 0
                              for other in others))
    return degree


def primitives(counts: tuple[int, ...], unseen: tuple[int, ...], melds: int) -> dict[str, int]:
    """只用生产数学排除当前有效码；未知供给不可当作零。"""

    if len(counts) != 34 or len(unseen) != 34 or any(type(x) is not int or x < 0 for x in unseen):
        raise ValueError("34 维公开未知牌计数缺失或非法")
    progress = analyse_counts_progress(counts, melds)
    useful = set(progress.useful_codes)
    degrees = []
    for code in NATURAL:
        amount = unseen[CANONICAL_TILE_INDEX[code]]
        if amount <= 0 or code in useful:
            continue
        degree = _degree(counts, code)
        if degree:
            degrees.append((degree, amount))
    return {"T": sum(degree for degree, _ in degrees),
            "N": len(degrees),
            "weighted_T": sum(degree * amount for degree, amount in degrees),
            "max_degree": max((degree for degree, _ in degrees), default=0)}


def _prediction(parent: dict[str, int], alternative: dict[str, int], strict: bool) -> int:
    """仅正向改选或弃权；不把低 N 当成反向改选证据。"""

    if parent["T"] != alternative["T"] or (strict and parent["weighted_T"] != alternative["weighted_T"]):
        return 0
    return int(alternative["N"] > parent["N"])


def _scan(path: Path, label: str) -> tuple[dict, list[dict]]:
    metrics: dict[str, Counter] = {}
    cases = []
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row["white_after"] != 1:
                continue
            unseen = tuple(row["unknown_counts34"])
            melds = row["meld_count"]
            p = primitives(tuple(row["parent"]["counts34"]), unseen, melds)
            a = primitives(tuple(row["alternative"]["counts34"]), unseen, melds)
            truth = (row["delta_3"] > 0) - (row["delta_3"] < 0)
            split = row["split"] if label == "g23" else "all"
            depth2 = "two_equal" if row["delta_2"] == 0 else "two_different"
            for gate, strict in (("primary", True), ("secondary", False)):
                prediction = _prediction(p, a, strict)
                for cohort in (f"{label}_{split}", f"{label}_{split}_{depth2}"):
                    bucket = metrics.setdefault(f"{cohort}_{gate}", Counter())
                    bucket["pairs"] += 1
                    if not prediction:
                        bucket["abstain"] += 1
                    elif truth > 0:
                        bucket["correct"] += 1
                    elif truth < 0:
                        bucket["wrong"] += 1
                    else:
                        bucket["zero_alarm"] += 1
                    if label == "g29" and prediction:
                        edge = row["predictions"]["edge"]
                        bucket["edge_same_positive"] += int(edge > 0)
                        bucket["edge_not_positive"] += int(edge <= 0)
            if _prediction(p, a, True):
                cases.append({"room_id": row["room_id"], "game_id": row["game_id"],
                              "round_no": row["round_no"], "trigger_seq": row["trigger_seq"],
                              "parent_action": row["parent_action"],
                              "alternative_action": row["alternative_action"],
                              "parent": p, "alternative": a, "delta_2": row["delta_2"],
                              "delta_3": row["delta_3"], "split": split})
    return {key: dict(sorted(value.items())) for key, value in sorted(metrics.items())}, cases


def main() -> None:
    """保存可复算结果；结果文件存在时拒绝覆盖。"""

    if OUT.exists():
        raise SystemExit("G36 结果已存在，拒绝覆盖")
    if not all(path.exists() for path in (G23, G29, PREREG)):
        raise ValueError("冻结输入或预登记缺失")
    metrics23, cases23 = _scan(G23, "g23")
    metrics29, cases29 = _scan(G29, "g29")
    result = {"schema": "g36-latent-source-diversity/1",
              "g23_rows_sha256": sha(G23), "g29_rows_sha256": sha(G29),
              "prereg_sha256": sha(PREREG), "script_sha256": sha(Path(__file__)),
              "metrics": {**metrics23, **metrics29},
              "primary_cases": {"g23": cases23, "g29": cases29},
              "boundary": "已有理想化三摸教师的探索性特征复核；不是独立确认、合法候选行为或整桌净分。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps(result["metrics"], ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
