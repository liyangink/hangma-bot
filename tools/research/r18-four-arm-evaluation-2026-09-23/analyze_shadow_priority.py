"""旧 M=10 审计的只读影子排序：盯他家弃牌 vs 普通状态同步。

只检查某笔许可发出时，队列中是否已有不同场的 discard_watch 查询。
不改变真实排程，也不把事后错失相关性解释为反事实收益。
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/r18-four-arm-evaluation-2026-09-23'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import heapq
import json
from collections import Counter
from pathlib import Path

from analyze_cross_table_bursts import latest_discard, load_timeline
from analyze_local_preemption import selected_run
from analyze_state_runtime import analyze_run


def inspect_slot(run: Path) -> dict:
    requests, event_types, first_discards = load_timeline(run)
    ordinary = [row for row in requests if row["purpose"] in ("state_sync", "discard_watch")]
    ordinary.sort(key=lambda row: row["g"])
    watch_by_queue = sorted((row for row in ordinary if row["purpose"] == "discard_watch"),
                            key=lambda row: row["q"])
    pending: list[tuple[float, int, str]] = []
    pending_by_game: Counter[str] = Counter()
    next_watch = 0
    inversions = []
    for actual in ordinary:
        if actual["purpose"] != "state_sync":
            continue
        while next_watch < len(watch_by_queue) and watch_by_queue[next_watch]["q"] <= actual["g"]:
            row = watch_by_queue[next_watch]
            heapq.heappush(pending, (row["g"], next_watch, row["game"]))
            pending_by_game[row["game"]] += 1
            next_watch += 1
        while pending and pending[0][0] <= actual["g"]:
            _, _, game = heapq.heappop(pending)
            pending_by_game[game] -= 1
        waiting = len(pending) - pending_by_game[actual["game"]]
        if waiting:
            inversions.append({"at": actual["g"], "game": actual["game"],
                               "waiting_watch": waiting})
    misses = []
    chi_not_assessed = []
    for window in analyze_run(run)["no_input_rule_reconstruction"]["candidate_windows"]:
        game, trigger = window["game_id"], window["trigger_seq"]
        if window["phase"] == "response_chi":
            chi_not_assessed.append({"game": game.split("_")[-2], "trigger_seq": trigger})
            continue  # 吃窗目标是碰窗结束后的阶段查询，不是最初弃牌 GET。
        physical = latest_discard(event_types, game, trigger)
        target = first_discards.get((game, physical))
        if target is None:
            continue
        overtakes = [row for row in ordinary if row["purpose"] == "state_sync"
                     and row["game"] != game and target["q"] < row["g"] < target["g"]]
        misses.append({"game": game.split("_")[-2], "round": window["round_no"],
                       "trigger_seq": trigger, "target_purpose": target["purpose"],
                       "target_scheduler_priority": target.get("scheduler_priority"),
                       "state_sync_label_overtakes": len(overtakes),
                       "actual_poll_overtakes": (sum(row.get("scheduler_priority") == "POLL"
                                                     and row["q"] >= target["q"]
                                                     for row in overtakes)
                                                 if target.get("scheduler_priority") is not None else None),
                       "seq0_overtakes": sum(row["seq0"] for row in overtakes)})
    return {"ordinary_grants": len(ordinary),
            "state_sync_grants": sum(row["purpose"] == "state_sync" for row in ordinary),
            "state_sync_grants_with_watch_waiting": len(inversions),
            "waiting_watch_at_inversion": Counter(row["waiting_watch"] for row in inversions),
            "chi_not_assessed": chi_not_assessed,
            "misses": misses}


def inspect(audit_root: Path, version: str) -> dict:
    slots = {slot.name: inspect_slot(selected_run(slot, version))
             for slot in sorted(audit_root.glob("slot-*"))}
    misses = [row for item in slots.values() for row in item["misses"]]
    return {"version": version,
            "evidence_limit": "只读单步影子：仅对碰窗首个弃牌 GET 统计用途标签和实测调度优先级；旧运行未记录 scheduler_priority 时实际 POLL 越过为 null。吃窗需另看碰窗结束后的查询。不能据此声称排序可追回错失。",
            "summary": {
                "ordinary_grants": sum(item["ordinary_grants"] for item in slots.values()),
                "state_sync_grants": sum(item["state_sync_grants"] for item in slots.values()),
                "state_sync_grants_with_watch_waiting": sum(
                    item["state_sync_grants_with_watch_waiting"] for item in slots.values()),
                "miss_matched": len(misses),
                "watch_misses": sum(row["target_purpose"] == "discard_watch" for row in misses),
                "watch_misses_overtaken_by_state_sync": sum(
                    row["target_purpose"] == "discard_watch"
                    and row["state_sync_label_overtakes"] > 0 for row in misses),
                "watch_misses_overtaken_by_actual_poll": (sum(
                    row["target_purpose"] == "discard_watch"
                    and (row["actual_poll_overtakes"] or 0) > 0 for row in misses)
                    if all(row["actual_poll_overtakes"] is not None for row in misses) else None),
                "chi_not_assessed": sum(len(item["chi_not_assessed"]) for item in slots.values()),
            },
            "slots": {name: {key: (dict(value) if isinstance(value, Counter) else value)
                              for key, value in item.items()} for name, item in slots.items()}}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("audit_root", type=Path)
    parser.add_argument("--version", default="burst4-fair-paced-v1")
    args = parser.parse_args()
    print(json.dumps(inspect(args.audit_root, args.version), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
