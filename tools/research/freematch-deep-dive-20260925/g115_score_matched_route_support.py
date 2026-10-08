#!/usr/bin/env python3
"""G115：只用 G114 行动前可见事实锁定高番差异与无差异对照。"""

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

import g114_fresh_score_matched_route_exposure as g114


HERE = Path(__file__).resolve().parent
SOURCE = g114.OUT / "rows.jsonl"
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g115-score-matched-route-support-20260928/result.json')


def sha(path: Path) -> str:
    """冻结源程序、预登记与目标窗证据的字节摘要。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity(row: dict, target: dict) -> tuple:
    """构成唯一真实决策窗的面板索引。"""
    return row["mix"], row["root_index"], row["focal_seat"], target["round_no"]


def is_high(target: dict) -> bool:
    """仅局部机会量具完整且至少一侧有独有高番机会才为真。"""
    if target["status"] != "complete":
        return False
    delta = target["delta"]["high_opportunities"]
    return bool(delta["parent_only"] or delta["alternate_only"])


def comparable(high: tuple[dict, dict], control: tuple[dict, dict]) -> bool:
    """强制相同对手池、白板数及普通型向听。"""
    row, target = high
    other_row, other = control
    return (row["mix"] == other_row["mix"]
            and target["white_before"] == other["white_before"]
            and target["score_facts"]["standard_shanten_after"]
            == other["score_facts"]["standard_shanten_after"])


def distances(high: dict, control: dict) -> dict:
    """匹配变量全部在行动前可见。"""
    a, b = high["score_facts"], control["score_facts"]
    return {
        "parent_score_gap": abs(a["parent_score_gap"] - b["parent_score_gap"]),
        "ordinary_codes_delta": abs(a["ordinary_codes_delta"] - b["ordinary_codes_delta"]),
        "public_unseen_capacity_delta": abs(a["public_unseen_capacity_delta"]
                                             - b["public_unseen_capacity_delta"]),
        "round_no": abs(high["round_no"] - control["round_no"]),
        "remaining_tile_count": abs(a["remaining_tile_count"]
                                    - b["remaining_tile_count"]),
    }


def within_caliper(d: dict) -> bool:
    """评分、码数及容量差距不超过 G114 预登记的上限。"""
    return (d["parent_score_gap"] <= 3
            and d["ordinary_codes_delta"] <= 2
            and d["public_unseen_capacity_delta"] <= 5)


def main() -> None:
    """按父代表原行序贪心锁定独有对照，不读取结算。"""
    if OUT.exists():
        raise FileExistsError("G115 匹配结果已存在，拒绝覆盖")
    exposure = json.loads((g114.OUT / "result.json").read_text(encoding="utf-8"))
    if exposure["status"] != "complete" or exposure["tables_completed"] != 256:
        raise ValueError("G115 只能在完整 G114 结果盲面板上匹配")
    rows = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines()]
    if len(rows) != 256:
        raise ValueError("G115 G114 父代表行数不守恒")
    high = []
    controls = []
    unavailable = []
    for row in rows:
        for target in row["target_windows"]:
            if target["status"] == "unavailable":
                unavailable.append(identity(row, target))
            elif is_high(target):
                high.append((row, target))
            else:
                controls.append((row, target))
    used = set()
    matches = []
    unmatched = []
    for row, target in high:
        pool = [(other_row, other_target) for other_row, other_target in controls
                if comparable((row, target), (other_row, other_target))]
        eligible = [(other_row, other_target,
                     distances(target, other_target))
                    for other_row, other_target in pool
                    if within_caliper(distances(target, other_target))]
        available = [(other_row, other_target, distance)
                     for other_row, other_target, distance in eligible
                     if identity(other_row, other_target) not in used]
        def rank(item: tuple[dict, dict, dict]) -> tuple:
            other_row, other_target, distance = item
            return (distance["parent_score_gap"],
                    distance["ordinary_codes_delta"],
                    distance["public_unseen_capacity_delta"],
                    distance["round_no"], distance["remaining_tile_count"],
                    other_row["root_index"], other_row["focal_seat"],
                    other_target["round_no"])
        record = {
            "high_window": list(identity(row, target)),
            "high_observation_sha256": target["observation_sha256"],
            "same_stratum_controls": len(pool),
            "within_caliper_controls": len(eligible),
            "unused_within_caliper_controls": len(available),
        }
        if not available:
            record["reason"] = ("no_same_stratum" if not pool else
                                "no_caliper" if not eligible else "already_used")
            unmatched.append(record)
            continue
        other_row, other_target, distance = min(available, key=rank)
        used.add(identity(other_row, other_target))
        record.update({
            "control_window": list(identity(other_row, other_target)),
            "control_observation_sha256": other_target["observation_sha256"],
            "distance": distance,
        })
        matches.append(record)
    matched_by_mix = Counter(record["high_window"][0] for record in matches)
    high_by_mix = Counter(row["mix"] for row, _ in high)
    result = {
        "schema": "g115-score-matched-route-support/1",
        "input_sha256": {
            "script": sha(Path(__file__)),
            "g114_prereg": sha(g114.PREREG),
            "g114_script": sha(Path(g114.__file__)),
            "g114_manifest": sha(g114.OUT / "manifest.json"),
            "g114_rows": sha(SOURCE),
        },
        "high_windows": len(high), "control_windows": len(controls),
        "opportunity_unavailable": len(unavailable),
        "high_by_mix": dict(high_by_mix),
        "matched_by_mix": dict(matched_by_mix),
        "matched_pairs": len(matches), "unmatched_high": len(unmatched),
        "unavailable_windows": unavailable,
        "matches": matches, "unmatched": unmatched,
        "next_gate_support": (len(matches) >= 10
                              and matched_by_mix["H"] >= 3
                              and matched_by_mix["M"] >= 3),
        "boundary": "只读行动前可见量匹配；尚未查看同局反事实收益。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({key: result[key] for key in (
        "high_windows", "control_windows", "opportunity_unavailable",
        "high_by_mix", "matched_by_mix", "matched_pairs", "unmatched_high",
        "next_gate_support")}, ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
