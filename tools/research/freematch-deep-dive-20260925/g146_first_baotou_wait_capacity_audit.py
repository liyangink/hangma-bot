#!/usr/bin/env python3
"""G146：首次普通型爆头机会窗的合法弃牌等待容量审计。"""

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

import g138_official_plain_baotou_opportunity as g138
import g61_strong_draw_batch as g61
import g69_route_chain_analysis as g69
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g146-first-baotou-wait-capacity-20260928/result.json')


def sha(path: Path) -> str:
    """绑定现有官方窗口与本程序的原始字节。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def key(row: dict, peer: str, room: str, actor: str, seq_field: str) -> tuple:
    """生成强手、房、完整桌、单局、座位、行动序号联合键。"""
    return (peer, room, row["game_id"], row["round_no"], actor, row[seq_field])


def main() -> None:
    """只在已冻结的首次机会窗复算合法弃牌，不按候选结果重新选窗。"""
    if OUT.exists():
        raise FileExistsError("G146 已有结果，拒绝覆盖")
    first = json.loads(g138.OUT.read_text(encoding="utf-8"))[
        "first_plain_baotou_rows"]
    wanted = {key(row, row["peer"], row["room"], row["actor"],
                  "first_draw_seq"): row for row in first}
    if len(wanted) != 239:
        raise ValueError("G138 首次机会键重复或母体不足")
    counters: dict[str, Counter] = {}
    source_hashes = {}
    seen = set()
    for peer, room in sorted({(row["peer"], row["room"]) for row in first}):
        for actor, path in (
            ("peer", g61.room_dir((peer, room)) / "windows.json"),
            ("us", g69.G69 / "rooms" / room / "windows.json.gz"),
        ):
            rows, observed_sha = g69.load_windows(path)
            source_hashes[f"{peer}/{room}/{actor}"] = observed_sha
            for row in rows:
                marker = key(row, peer, room, actor, "draw_seq")
                if marker not in wanted:
                    continue
                if marker in seen or row["room_id"] != room:
                    raise ValueError("首次机会窗口重复或房身份漂移")
                seen.add(marker)
                observation = observation_from_json(row["observation"])
                rules = g138.c31.RULES.analyze(
                    observation, value_limits=g138.c31.VALUE_LIMITS)
                discards = {candidate.action_key: candidate
                            for candidate in rules.legal_candidates
                            if candidate.action_key.startswith("discard:")}
                capacities = {}
                for action_key, candidate in discards.items():
                    fact, complete = g138.action_opportunity(candidate)
                    if not complete:
                        raise ValueError("首次机会窗合法弃牌条件路线不完整")
                    capacities[action_key] = fact["plain_baotou"]
                actual = row["actual_action"]
                if actual not in capacities or capacities[actual] <= 0:
                    raise ValueError("首次机会窗实际弃牌未保持正容量")
                maximum = max(capacities.values())
                summary = counters.setdefault(f"{peer}/{actor}", Counter())
                summary["first_opportunity_windows"] += 1
                summary["actual_is_capacity_max"] += capacities[actual] == maximum
                summary["actual_below_max"] += capacities[actual] < maximum
                summary["capacity_gap_to_max_sum"] += maximum - capacities[actual]
                summary["actual_capacity_sum"] += capacities[actual]
    if seen != wanted.keys():
        raise ValueError("首次机会窗未全部复核")
    result = {
        "schema": "g146-first-baotou-wait-capacity/1",
        "inputs_sha256": {
            "g138_result": sha(g138.OUT),
            "g61_result": sha(g61.OUT / "result.json"),
            "g69_batch": sha(g69.G69 / "batch_result.json"),
            "hangma_value_analysis": sha(
                _project_file(_PROJECT_ROOT, HERE.parents[1] / "src/hangma_bot/hangma/value_analysis.py")),
            "script": sha(Path(__file__)),
        },
        "window_source_sha256": source_hashes,
        "groups": {name: dict(value) for name, value in sorted(counters.items())},
        "boundary": "已看强手官方正常摸打首次机会窗的事后描述；公开未见容量可超过当前墙余且含他家暗手，不是概率或反事实净分。该审计只说明临门同窗容量排序，不证明更早弃牌的价值。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps(result["groups"], ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
