#!/usr/bin/env python3
"""G214：只读 G213 首触局，核算行动前进张扩宽与局末结果的描述关系。"""

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
from hashlib import sha256
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g213-first-changed-hand-20260929/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g214-width-outcome-audit-20260929/result.json')
SELF_WINS = frozenset(("plain_self", "special_self"))


def summarize(rows: list[dict]) -> dict:
    """按首个改弃的普通进张码数增量分组；不把单局当独立牌山根。"""
    groups = {}
    for gain in sorted({row["first_ordinary_type_gain"] for row in rows}):
        group = [row for row in rows if row["first_ordinary_type_gain"] == gain]
        changes = [row["first_hand_delta"] for row in group]
        groups[str(gain)] = {
            "tables": len(group),
            "first_hand_positive_zero_negative": [
                sum(value > 0 for value in changes),
                sum(value == 0 for value in changes),
                sum(value < 0 for value in changes),
            ],
            "first_hand_focal_delta_sum": sum(changes),
        }
    return {
        "tables": len(rows),
        "type_gain_groups": groups,
        "capacity_gain_range": [
            min(row["first_ordinary_capacity_gain"] for row in rows),
            max(row["first_ordinary_capacity_gain"] for row in rows),
        ],
        "terminal_transitions": dict(sorted(Counter(
            row["parent_terminal"] + "->" + row["candidate_terminal"]
            for row in rows).items())),
        "new_self_win": sum(row["parent_terminal"] not in SELF_WINS
                            and row["candidate_terminal"] in SELF_WINS
                            for row in rows),
        "lost_self_win": sum(row["parent_terminal"] in SELF_WINS
                             and row["candidate_terminal"] not in SELF_WINS
                             for row in rows),
        "same_full_score_delta_vector": sum(
            row["full_score_delta_vector_match"] for row in rows),
    }


def main() -> None:
    """只产出可复算的赛后诊断；不得用本次分组选择下一候选阈值。"""
    if OUT.exists():
        raise FileExistsError("G214 证据已存在，拒绝覆盖")
    source_bytes = SOURCE.read_bytes()
    source = json.loads(source_bytes)
    rows = source["rows"]
    if (source["schema"] != "g213-first-changed-hand-audit/1"
            or len(rows) != 228
            or source["first_changed_tables"] != len(rows)
            or source["untouched_identical_tables"] != 156):
        raise ValueError("G213 来源或首触样本数改变")
    if any(row["first_ordinary_type_gain"] <= 0
           or row["first_ordinary_capacity_gain"] <= 0
           or not row["scores_before_match"] for row in rows):
        raise ValueError("首触改弃不满足严格扩宽或局前分数对账")
    by_mix = {mix: summarize([row for row in rows if row["mix"] == mix])
              for mix in ("H", "M")}
    if sum(item["tables"] for item in by_mix.values()) != len(rows):
        raise ValueError("对手池首触样本不守恒")
    output = {
        "schema": "g214-width-outcome-audit/1",
        "source_sha256": sha256(source_bytes).hexdigest(),
        "population": "G211 候选完整桌中首次 G210 改弃所在单局；已看开发根；事后选择样本",
        "by_mix": by_mix,
        "combined": summarize(rows),
        "interpretation_boundary": (
            "普通型一步进张码数及公开容量是行动前事实，不是抽牌概率或因果收益。"
            "首次改弃后的合法行动、他家行动和同局后续改弃均可能不同；"
            "同根四座与两桌相关，不能用本样本作独立显著性检验或新阈值验证。"
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"by_mix": by_mix, "combined": output["combined"]},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
