"""P24 改选窗语义审计（硬纪律）：逐条列出 16 个开发状态的改选动作对与状态标志。

目的：在跑 1,024 张完整桌之前，确认「臂 B 相对臂 A」的改动**在语义上不是空转**——
即不是「番值不变、只是推迟一摸」那类改选。本审计只读 targets.json 的冻结特征，不读任何结果。
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p24-deferral-complement-01-20260925'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import collections
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p24-deferral-complement-01-20260925/teacher')


def main() -> int:
    document = json.loads((_project_file(_PROJECT_ROOT, OUT / "targets.json")).read_text(encoding="utf-8"))
    rows = document["targets"]
    counters = collections.Counter()
    print("| # | 根 | mix | 座 | 局 | 立刻胡番 | 胡结算 | 臂 B 弃牌 | B 后向听 | B 后有效牌种数 |",
          "手留白 | 弃牌后爆头 | 剩余牌 |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for row in rows:
        f = row["features"]
        settle = f["hu_settlement"]
        self_delta = settle["score_delta"][row["focal_physical_seat"]]
        counters["fan_" + str(f["hu_fan"])] += 1
        counters["baotou_after_" + str(f["intervention_baotou_after"])] += 1
        counters["shanten_after_" + str(f["intervention_shanten_after"])] += 1
        counters["self_delta_" + str(self_delta)] += 1
        print("| {0} | {1} | {2} | {3} | {4} | {5} | {6} | {7} | {8} | {9} | {10} | {11} | {12} |".format(
            row["target_id"].rsplit("-", 1)[1], row["source"]["source_root_id"][-10:],
            row["source"]["mix"], row["focal_physical_seat"], f["round_no"], f["hu_fan"],
            self_delta, row["intervention_action"], f["intervention_shanten_after"],
            f["intervention_useful_kinds"], f["wealth_count_in_hand"],
            f["intervention_baotou_after"], f["remaining_tile_count"]))
    print()
    print("计数：", json.dumps(dict(sorted(counters.items())), ensure_ascii=False))
    print()
    print("判读：")
    print("- 臂 A（立即 hu）的 shanten_after 是 -1 的「已成牌」哨兵，不是真实向听；")
    print("  「B 比 A 向听更慢」在数值上是必然的假象，不作为语义判据。")
    print("- 语义判据 = 立即胡番数（=1，平价）与弃牌后向听/有效牌种数：")
    print("  若 B 后仍听牌且有效牌种数可观，则改选是「用 1 番换更宽的听口」的真实取舍；")
    print("  若 B 后向听 > 0，则是「放弃已成牌去继续做牌」，代价更大。")
    print("- 若某状态 B 后 baotou_after 为 True，则该状态应被剔除（本批的谓词要求为假）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
