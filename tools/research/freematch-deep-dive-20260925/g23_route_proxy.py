#!/usr/bin/env python3
"""G23：预登记自然两张牌原语在分房留出上的三摸方向检验。"""

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
import gzip
import hashlib
import json
from pathlib import Path

from hangma_bot.hangma.hand_analysis import analyse_counts_progress
from hangma_bot.hangma.internal_types import TILE_INDEX, TILE_ORDER


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g23-three-draw-teacher-20260927')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g23-three-draw-teacher-20260927/proxy.json')
FEATURES = ("latent_types", "latent_capacity", "route_mass", "extra_route_mass",
            "route_square_mass", "max_route_count", "natural_pair_types")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def primitives(counts: tuple[int, ...], unseen: tuple[int, ...], melds: int) -> dict[str, int]:
    """逐码自然两张牌可成刻/顺的模式，不预绑白板、不重写规则向听。"""

    if len(counts) != 34 or len(unseen) != 34:
        raise ValueError("G23 自然原语需要规范 34 维牌/公开未知向量")
    current = analyse_counts_progress(counts, melds)
    useful = set(current.useful_codes)
    supports = []
    for code in TILE_ORDER:
        if code == "白" or code in useful:
            continue
        idx = TILE_INDEX[code]
        available = unseen[idx]
        if type(available) is not int or available <= 0:
            continue
        n = 1 if counts[idx] >= 2 else 0  # 自然双张 + 该码可成刻
        if code[-1] in "wbt":
            rank = int(code[0])
            suffix = code[1]
            for start in range(max(1, rank - 2), min(rank, 7) + 1):
                others = [f"{value}{suffix}" for value in range(start, start + 3)
                          if value != rank]
                if all(counts[TILE_INDEX[other]] > 0 for other in others):
                    n += 1
        if n:
            supports.append((available, n))
    return {
        "latent_types": len(supports),
        "latent_capacity": sum(amount for amount, _ in supports),
        "route_mass": sum(amount * n for amount, n in supports),
        "extra_route_mass": sum(amount * max(0, n - 1) for amount, n in supports),
        "route_square_mass": sum(amount * n * n for amount, n in supports),
        "max_route_count": max((n for _, n in supports), default=0),
        "natural_pair_types": sum(counts[i] >= 2 for i, code in enumerate(TILE_ORDER)
                                  if code != "白"),
    }


def _sign(value: int) -> int:
    return (value > 0) - (value < 0)


def _metrics(rows: list[dict], feature: str | None, orient: int = 1) -> dict[str, int]:
    """只报告方向，不把理想化容量当真实收益。"""

    result = Counter()
    for row in rows:
        truth = _sign(row["delta_3"])
        guess = 1 if feature is None else _sign(orient * row["features"][feature])
        result["pairs"] += 1
        if truth == 0:
            result["zero_label"] += 1
            result["zero_false_alarm" if guess else "zero_abstain"] += 1
        elif guess == 0:
            result["nonzero_abstain"] += 1
        else:
            result["nonzero_correct" if guess == truth else "nonzero_wrong"] += 1
        if guess:
            result["nonzero_prediction"] += 1
    return dict(sorted(result.items()))


def main() -> None:
    """开发房选择一个固定原语；仅对此原语读取留出房判定。"""

    if OUT.exists():
        raise SystemExit("G23 代理评估已存在，拒绝覆盖")
    teacher = json.loads((_project_file(_PROJECT_ROOT, SOURCE / "result.json")).read_text(encoding="utf-8"))
    rows_path = _project_file(_PROJECT_ROOT, SOURCE / "rows.jsonl.gz")
    if (teacher.get("outcome_blind") is not True or
            teacher.get("rows_sha256") != sha(rows_path) or
            teacher.get("sampled_pairs") != 184):
        raise ValueError("G23 教师来源或分层样本数漂移")
    rows = []
    with gzip.open(rows_path, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            a = primitives(tuple(row["parent"]["counts34"]),
                           tuple(row["unknown_counts34"]), row["meld_count"])
            b = primitives(tuple(row["alternative"]["counts34"]),
                           tuple(row["unknown_counts34"]), row["meld_count"])
            row["features"] = {name: b[name] - a[name] for name in FEATURES}
            rows.append(row)
    if len(rows) != teacher["sampled_pairs"]:
        raise ValueError("G23 教师逐对行数漂移")
    primary = [row for row in rows if row["delta_2"] == 0]
    dev = [row for row in primary if row["split"] == "development"]
    holdout = [row for row in primary if row["split"] == "holdout"]
    if not dev or not holdout:
        raise ValueError("G23 分房开发/留出样本缺失")
    scores = []
    for index, feature in enumerate(FEATURES):
        for orient in (1, -1):
            metric = _metrics(dev, feature, orient)
            if metric.get("nonzero_prediction", 0) < 12:
                continue
            score = (metric.get("nonzero_correct", 0) - metric.get("nonzero_wrong", 0)) / len(dev)
            scores.append({"feature": feature, "orientation": orient,
                           "score": score, "development_metrics": metric,
                           "order": index})
    scores.sort(key=lambda row: (-row["score"], row["order"], -row["orientation"]))
    chosen = scores[0] if scores else None
    result = {"schema": "g23-route-proxy/1", "outcome_blind": True,
              "source_result_sha256": sha(_project_file(_PROJECT_ROOT, SOURCE / "result.json")),
              "source_rows_sha256": sha(rows_path), "script_sha256": sha(Path(__file__)),
              "feature_order": FEATURES, "primary_condition": "depth2 difference = 0",
              "primary_development_pairs": len(dev), "primary_holdout_pairs": len(holdout),
              "development_feature_scores": scores,
              "chosen": ({key: chosen[key] for key in
                          ("feature", "orientation", "score", "development_metrics")}
                         if chosen else None),
              "development_always_alternative": _metrics(dev, None),
              "holdout_always_alternative": _metrics(holdout, None),
              "holdout_selected_proxy": (_metrics(holdout, chosen["feature"],
                                                  chosen["orientation"]) if chosen else None),
              "holdout_by_white": ({str(white): _metrics(
                  [row for row in holdout if min(row["white_after"], 2) == white],
                  chosen["feature"], chosen["orientation"])
                                    for white in (0, 1, 2)} if chosen else None),
              "teacher_nonzero_by_white": {str(white): dict(Counter(
                  "positive" if row["delta_3"] > 0 else "negative" if row["delta_3"] < 0 else "equal"
                  for row in primary if min(row["white_after"], 2) == white))
                                            for white in (0, 1, 2)},
              "boundary": "开发房选特征，留出房只评价一次；预测理想化三摸方向，不是桌赛净分。"}
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"chosen": result["chosen"],
                      "holdout": result["holdout_selected_proxy"],
                      "control": result["holdout_always_alternative"]},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
