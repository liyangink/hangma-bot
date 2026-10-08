#!/usr/bin/env python3
"""G52 结果盲交叉审计：分开报告主七对路线与次级普通型路线。"""

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
from statistics import mean, median


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g52-g49-shared-horizon-20260927')
G48 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g48-cross-layer-natural-gap-reach-20260927/result.json')
G49 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g49-official-behavior-20260927/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g52-g49-shared-horizon-20260927/analysis.json')


def sha(path: Path) -> str:
    """返回输入或分析脚本的内容摘要。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def sign(value: float) -> str:
    """固定数值方向容差，避免条件值浮点误差。"""

    return "+" if value > 1e-9 else "-" if value < -1e-9 else "0"


def stats(values: list[float]) -> dict:
    """保留分母、方向和尺度；这些条件量均不等于真实桌分。"""

    return {"n": len(values), "sign": dict(Counter(sign(v) for v in values)),
            "mean": mean(values), "median": median(values),
            "min": min(values), "max": max(values)}


def main() -> None:
    """核对 G48、G49、G52 同一 102 窗并输出不含任何赛果的汇总。"""

    if OUT.exists():
        raise SystemExit("G52 分析已存在，拒绝覆盖")
    result_path = _project_file(_PROJECT_ROOT, SOURCE / "result.json")
    rows_path = _project_file(_PROJECT_ROOT, SOURCE / "rows.jsonl.gz")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if (result.get("outcome_blind") is not True or result.get("targets") != 102 or
            result.get("rows_sha256") != sha(rows_path)):
        raise ValueError("G52 原始结果或逐窗摘要漂移")
    g48 = json.loads(G48.read_text(encoding="utf-8"))
    g49 = json.loads(G49.read_text(encoding="utf-8"))
    if (g48.get("outcome_blind") is not True or
            g49.get("outcome_blind") is not True or
            result.get("source_g49_sha256") != sha(G49)):
        raise ValueError("G48/G49 冻结入口漂移")
    with gzip.open(rows_path, "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    key = lambda row: (row["game_id"], row["round_no"], row["trigger_seq"])
    by48 = {key(row): row for row in g48["rows"]}
    by49 = {key(row): row for row in g49["changed"]}
    if (len(rows) != 102 or len(by49) != 102 or
            set(map(key, rows)) != set(by49) or
            len(set(map(key, rows))) != 102 or
            any("unavailable" in row for row in rows)):
        raise ValueError("G52 不可算、动作窗重复或漏行")
    structural = Counter()
    route = {mode: {family: [] for family in ("ordinary", "seven")}
             for mode in ("restricted", "unrestricted")}
    conditional = {s: {mode: [] for mode in ("restricted", "unrestricted")}
                   for s in ("0.0", "0.5", "1.0")}
    for row in rows:
        source, changed = by48[key(row)], by49[key(row)]
        if (row["parent_action"] != source["parent_action"] or
                row["candidate_action"] != changed["candidate_action"]):
            raise ValueError("G52 动作身份与 G48/G49 不符")
        alternative = next((item for item in source["alternatives"]
                            if item["action"] == row["candidate_action"]), None)
        if alternative is None:
            raise ValueError("G52 改选不在 G48 生产合法备选中")
        structural["parent_combined_equals_seven"] += (
            source["parent_combined_shanten"] == source["parent_seven_pairs_shanten"]
        )
        structural["parent_standard_two_behind_seven"] += (
            source["parent_standard_shanten"] == source["parent_seven_pairs_shanten"] + 2
        )
        structural["candidate_standard_one_step_improved"] += (
            alternative["delta_standard_shanten"] == -1
        )
        structural["candidate_combined_unchanged"] += (
            alternative["delta_combined_shanten"] == 0
        )
        structural["candidate_seven_unchanged"] += (
            alternative["delta_seven_pairs_shanten"] == 0
        )
        structural["root_whites_same"] += (
            row["parent"]["root_whites_held"] == row["candidate"]["root_whites_held"]
        )
        for s in conditional:
            for mode in conditional[s]:
                conditional[s][mode].append(row["delta"][s][mode])
        for mode in route:
            for family in route[mode]:
                # 值为候选－父代；负数代表自然补牌缺口较小。
                route[mode][family].append(
                    row["route_delta"][mode][family]["expected_natural_need"]
                )
    g48_gaps = {}
    for gap in sorted({row["parent_standard_shanten"] - row["parent_seven_pairs_shanten"]
                       for row in g48["rows"]}):
        matched = [row for row in g48["rows"]
                   if row["parent_standard_shanten"] - row["parent_seven_pairs_shanten"] == gap]
        g48_gaps[str(gap)] = {
            "windows": len(matched),
            "tables": len({row["game_id"] for row in matched}),
            "rooms": len({row["room_id"] for row in matched}),
        }
    output = {"schema": "g52-shared-horizon-analysis/1", "outcome_blind": True,
              "g48_sha256": sha(G48), "g49_sha256": sha(G49),
              "g52_result_sha256": sha(result_path), "g52_rows_sha256": sha(rows_path),
              "analysis_script_sha256": sha(Path(__file__)),
              "rows": len(rows), "tables": len({row["game_id"] for row in rows}),
              "rooms": len({row["room_id"] for row in rows}),
              "g48_parent_standard_minus_seven": g48_gaps,
              "structural": dict(structural),
              "conditional_score_delta": {s: {mode: stats(values)
                                               for mode, values in modes.items()}
                                          for s, modes in conditional.items()},
              "expected_natural_need_delta": {
                  mode: {family: stats(values) for family, values in families.items()}
                  for mode, families in route.items()},
              "boundary": "无赛果；公开容量是条件权重，不是牌墙后验；七对与普通型自然缺口分别选后继，s 不是继续概率。"}
    OUT.write_text(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"structural": output["structural"],
                      "conditional_score_delta": output["conditional_score_delta"]},
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
