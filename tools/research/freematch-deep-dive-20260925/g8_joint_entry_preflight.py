#!/usr/bin/env python3
"""结果盲核对强手鸣/过分歧与弃牌分歧是否在同局事件序列中聚集。"""

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

from collections import defaultdict
import hashlib
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
DISCARDS = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g05-discard-divergence-01/windows.json')
RESPONSES = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g4-pool-response-behavior-01/windows.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g8-policy-search-20260927/joint-entry-preflight.json')


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _group(rows: list[dict]) -> dict[tuple[str, int], list[int]]:
    by_hand: dict[tuple[str, int], list[int]] = defaultdict(list)
    for row in rows:
        by_hand[(row["game_id"], row["round_no"])].append(row["draw_seq"])
    return by_hand


def _summary(rows: list[dict], draw_seqs: dict[tuple[str, int], list[int]]) -> dict:
    distances: list[int | None] = []
    by_room: dict[str, dict[str, int]] = defaultdict(
        lambda: {"windows": 0, "same_round": 0, "within_10_seq": 0}
    )
    for row in rows:
        near = draw_seqs.get((row["game_id"], row["round_no"]), [])
        distance = min((abs(seq - row["discard_seq"]) for seq in near), default=None)
        distances.append(distance)
        room = by_room[row["room_id"]]
        room["windows"] += 1
        room["same_round"] += distance is not None
        room["within_10_seq"] += distance is not None and distance <= 10
    return {
        "windows": len(rows),
        "same_round_discard_divergence": sum(d is not None for d in distances),
        "within_10_seq": sum(d is not None and d <= 10 for d in distances),
        "within_20_seq": sum(d is not None and d <= 20 for d in distances),
        "by_room": dict(sorted(by_room.items())),
    }


def main() -> None:
    if OUT.exists():
        raise SystemExit("结果已存在，拒绝覆盖冻结预检")
    discard_rows = json.loads(DISCARDS.read_text(encoding="utf-8"))["windows"]
    response_rows = json.loads(RESPONSES.read_text(encoding="utf-8"))["windows"]
    if len(discard_rows) != 680 or len(response_rows) != 642:
        raise ValueError("四房已冻结输入规模漂移")
    discard_keys = {(r["game_id"], r["round_no"], r["draw_seq"]) for r in discard_rows}
    response_keys = {
        (r["game_id"], r["round_no"], r["discard_seq"], r["seat"])
        for r in response_rows
    }
    if len(discard_keys) != len(discard_rows) or len(response_keys) != len(response_rows):
        raise ValueError("输入动作窗口有重复键")
    draw_seqs = _group(discard_rows)
    different = [r for r in response_rows if r["actual_claim"] != r["parent_claim"]]
    same = [r for r in response_rows if r["actual_claim"] == r["parent_claim"]]
    report = {
        "schema": "g8-joint-entry-preflight/1",
        "inputs": {"discard_windows_sha256": _sha(DISCARDS),
                   "response_windows_sha256": _sha(RESPONSES),
                   "script_sha256": _sha(Path(__file__))},
        "scope": "四间既有官方强手开发房；同局事件序号距离，未读结局",
        "discard_divergence_windows": len(discard_rows),
        "response_divergent": _summary(different, draw_seqs),
        "response_same": _summary(same, draw_seqs),
        "interpretation_boundary": (
            "事件序号距离不是动作因果或时间间隔；同场/同局窗口相关，"
            "不能把窗口作为独立显著性样本。该筛查仅判断是否值得继续追相邻联动入口。"
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("discard_divergence_windows",
                                           "response_divergent", "response_same")},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
