#!/usr/bin/env python3
"""G28 事后诊断：C01 近邻键与更简单的弃边张/字牌控制比较。"""

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


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g28-c01-context-gate-20260927')
ROWS = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g28-c01-context-gate-20260927/rows.jsonl.gz')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g28-c01-context-gate-20260927/simple-controls.json')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sign(value: int) -> int:
    return (value > 0) - (value < 0)


def edge_key(action: str) -> tuple[int, str]:
    """完全不读本人近邻数：字牌 0、1/9 为 1、2/8 为 2、其他为 3。"""

    code = action.split(":", 1)[1]
    if code[-1] not in "wbt":
        return 0, code
    rank = int(code[0])
    return (1 if rank in (1, 9) else 2 if rank in (2, 8) else 3), code


def honor_key(action: str) -> tuple[int, str]:
    """只看是否字牌，作为明显的简约负控。"""

    code = action.split(":", 1)[1]
    return (0 if code[-1] not in "wbt" else 1), code


def main() -> None:
    """证据已审视，仅作事后复杂度控制，不称独立确认。"""

    if OUT.exists():
        raise SystemExit("G28 简约控制已存在，拒绝覆盖")
    prior = json.loads((_project_file(_PROJECT_ROOT, SOURCE / "result.json")).read_text(encoding="utf-8"))
    if prior["rows_sha256"] != sha(ROWS) or prior["pairs"] != 184:
        raise ValueError("G28 输入漂移")
    rows = [json.loads(line) for line in gzip.open(ROWS, "rt", encoding="utf-8")]
    counts = Counter()
    for row in rows:
        teacher = sign(row["teacher_delta_3"])
        directions = {
            "c01": sign(int(row["alternative_key"] < row["parent_key"]) -
                        int(row["alternative_key"] > row["parent_key"])),
            "edge": sign(int(edge_key(row["alternative_action"]) < edge_key(row["parent_action"])) -
                         int(edge_key(row["alternative_action"]) > edge_key(row["parent_action"]))),
            "honor": sign(int(honor_key(row["alternative_action"]) < honor_key(row["parent_action"])) -
                          int(honor_key(row["alternative_action"]) > honor_key(row["parent_action"]))),
        }
        group = f"{row['split']}_white_{min(row['white_after'], 2)}"
        for name, direction in directions.items():
            outcome = ("correct" if direction == teacher and teacher else
                       "wrong" if direction and teacher else
                       "zero_alarm" if direction else "abstain")
            counts[f"{group}_{name}_{outcome}"] += 1
            if row["gate_open"]:
                counts[f"gate_open_{group}_{name}_{outcome}"] += 1
        if directions["c01"] != directions["edge"]:
            counts[f"{group}_c01_edge_disagree"] += 1
            if teacher:
                counts[f"{group}_c01_edge_disagree_teacher_nonzero"] += 1
                counts[f"{group}_c01_edge_disagree_c01_correct"] += int(directions["c01"] == teacher)
                counts[f"{group}_c01_edge_disagree_edge_correct"] += int(directions["edge"] == teacher)
    result = {"schema": "g28-c01-simple-controls/1", "post_hoc": True,
              "source_g28_rows_sha256": sha(ROWS), "script_sha256": sha(Path(__file__)),
              "pairs": len(rows), "counts": dict(sorted(counts.items())),
              "boundary": "G27 作者与分析者已看过 G23 开发/旧留出，简约基线是事后诊断；方向只指理想三摸，不是赛事收益。"}
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({key: value for key, value in result["counts"].items()
                      if "holdout_white_1" in key and not key.startswith("gate_open_")},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
