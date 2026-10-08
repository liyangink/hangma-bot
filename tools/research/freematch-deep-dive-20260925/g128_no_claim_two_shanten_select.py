#!/usr/bin/env python3
"""G128：只凭 G126 行动前事实冻结未吃碰二向听目标窗。"""

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

import g126_all_draw_natural_width_exposure as g126


HERE = Path(__file__).resolve().parent
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G128-NO-CLAIM-TWO-SHANTEN-BRANCH-PREREG-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g128-no-claim-two-shanten-20260928/selection.json')


def sha(path: Path) -> str:
    """冻结目标列表来源与选样程序字节。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """每个牌山根、池、白板格只选一个确定身份的目标窗。"""
    if OUT.exists():
        raise FileExistsError("G128 选样已经冻结，拒绝覆盖")
    summary = json.loads((g126.OUT / "result.json").read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in (g126.OUT / "rows.jsonl").read_text(
        encoding="utf-8").splitlines()]
    if summary["status"] != "complete" or len(rows) != 256:
        raise ValueError("G128 来源父代表不完整")
    first = {}
    eligible = Counter()
    for row in rows:
        for target in row["target_windows"]:
            facts = target["score_facts"]
            if (facts["own_chi_peng_count"] != 0
                    or facts["standard_shanten_after"] != 2
                    or facts["white_before"] not in (0, 1)):
                continue
            split = "development" if row["root_index"] <= 16 else "locked_evaluation"
            group = (split, row["mix"], str(facts["white_before"]))
            eligible[group] += 1
            rank = (target["observation_sha256"], row["mix"],
                    row["root_index"], row["focal_seat"], target["round_no"])
            key = (*group, row["root_index"])
            if key not in first or rank < first[key][0]:
                first[key] = (rank, row, target)
    selected = []
    strata = {}
    for split in ("development", "locked_evaluation"):
        for mix in ("H", "M"):
            for white in ("0", "1"):
                group = (split, mix, white)
                items = sorted(item for key, item in first.items() if key[:3] == group)
                strata["/".join(group)] = {
                    "eligible_windows": eligible[group],
                    "selected_roots": len(items), "selected_windows": len(items),
                }
                for _, row, target in items:
                    selected.append({
                        "split": split, "mix": mix, "white_bin": white,
                        "window": [row["mix"], row["root_index"],
                                   row["focal_seat"], target["round_no"]],
                        "observation_sha256": target["observation_sha256"],
                        "parent_action": target["parent_action"],
                        "alternate_action": target["alternate_action"],
                    })
    if (len(selected) != 80
            or sum(item["split"] == "development" for item in selected) != 38
            or sum(item["split"] == "locked_evaluation" for item in selected) != 42
            or len({tuple(item["window"]) for item in selected}) != 80):
        raise ValueError("G128 事前选样规模或身份不守恒")
    result = {
        "schema": "g128-no-claim-two-shanten-selection/1",
        "selected_windows": len(selected), "strata": strata,
        "selected": selected,
        "input_sha256": {"prereg": sha(PREREG), "script": sha(Path(__file__)),
                         "g126_rows": sha(g126.OUT / "rows.jsonl"),
                         "g126_manifest": sha(g126.OUT / "manifest.json")},
        "boundary": "仅依行动前可见特征选样，未读备选续打结果。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"selected_windows": len(selected), "strata": strata},
                     ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
