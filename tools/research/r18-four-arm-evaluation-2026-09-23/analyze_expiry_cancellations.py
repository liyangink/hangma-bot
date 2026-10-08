"""核对漏窗是否在官方截止仍有效时取消了估算期限的快照用途。"""

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
import json
from pathlib import Path

from analyze_local_preemption import load_run, selected_run
from analyze_state_runtime import rows


def inspect(root: Path, version: str, missed_path: Path) -> dict:
    runs = {slot.name: selected_run(slot, version) for slot in root.glob("slot-*")}
    data = {slot: load_run(run) for slot, run in runs.items()}
    missed = json.loads(missed_path.read_text())
    result = []
    for slot, report in missed.items():
        for window in report["no_input_rule_reconstruction"]["candidate_windows"]:
            game, seq, phase = window["game_id"], window["trigger_seq"], window["phase"]
            cancelled = []
            for path in (runs[slot] / "participants").glob(f"*/games/{game}.jsonl"):
                for row in rows(path):
                    payload = row.get("payload") or {}
                    context = row.get("context") or {}
                    if (payload.get("state_query_cancel_reason") == "expired_window_purpose"
                            and payload.get("query_purpose") == "known_window_refresh"
                            and (payload.get("window") or {}).get("trigger_seq") == seq
                            and (payload.get("window") or {}).get("phase") == phase):
                        cancelled.append(row["monotonic_ns"] / 1e9)
            # 碰窗用同一事件序号与官方快照精确对应。吃窗可能换序号，
            # 只报告取消相关性，不捏造官方剩余时间。
            snapshots = [s for peer in data.values() for s in peer["snapshots"]
                         if s["game"] == game and s["round"] == window["round_no"]
                         and s["phase"] == phase and s["seq"] == seq]
            official_deadline = min((s["deadline_ms"] for s in snapshots), default=None)
            official_remaining_ms = None
            if cancelled and official_deadline is not None:
                official_remaining_ms = round(official_deadline - 1000 * (
                    min(cancelled) + data[slot]["clock_offset"]), 1)
            result.append({
                "slot": slot, "game": game.rsplit("_", 2)[-2], "round_no": window["round_no"],
                "trigger_seq": seq, "phase": phase,
                "expired_refresh_cancelled": bool(cancelled),
                "official_remaining_at_cancel_ms": official_remaining_ms,
            })
    summary = {
        "candidate": len(result),
        "cancelled": sum(row["expired_refresh_cancelled"] for row in result),
        "peng_candidate": sum(row["phase"] == "response_peng" for row in result),
        "peng_cancelled": sum(row["phase"] == "response_peng" and row["expired_refresh_cancelled"]
                              for row in result),
        "peng_cancelled_while_official_open": sum(
            row["phase"] == "response_peng" and row["expired_refresh_cancelled"]
            and row["official_remaining_at_cancel_ms"] is not None
            and row["official_remaining_at_cancel_ms"] > 0 for row in result),
        "peng_cancelled_with_100ms_left": sum(
            row["phase"] == "response_peng" and row["expired_refresh_cancelled"]
            and row["official_remaining_at_cancel_ms"] is not None
            and row["official_remaining_at_cancel_ms"] > 100 for row in result),
    }
    return {"summary": summary, "windows": result}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("version")
    parser.add_argument("missed", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = json.dumps(inspect(args.root, args.version, args.missed), ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(output)
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
