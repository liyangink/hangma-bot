"""以官方上周/本周榜单快照给 R18 自由赛牌谱做只读对手分层。"""

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
import hashlib
import json
from pathlib import Path
from statistics import mean

from analyze_free_opponents import analyze_campaign, expected_r18, source_index


ROOT = _PROJECT_ROOT
DEFAULT_SESSION = _project_file(_PROJECT_ROOT, ROOT / "artifacts/sessions/r18-auto-match-campaign-20260923")


def _profile(tables: list[dict], user_id: str) -> dict:
    """只从该身份实际坐过的座位统计；不把单局当独立样本。"""

    exposures = [(table, opponent) for table in tables
                 for opponent in table["opponents"] if opponent["user_id"] == user_id]
    wins = [round_row for table, opponent in exposures for round_row in table["rounds"]
            if round_row["winner_seat"] == opponent["seat"]]
    return {
        "tables": len(exposures),
        "rooms": len({table["room_id"] for table, _ in exposures}),
        "round_wins": len(wins),
        "round_win_fraction": len(wins) / (8 * len(exposures)) if exposures else None,
        "winning_fan_mean": mean(row["fan"] for row in wins) if wins else None,
        "net_per_table": mean(opponent["final_score"] for _, opponent in exposures)
        if exposures else None,
        "claims_per_hand": sum(opponent["claims"] for _, opponent in exposures)
        / (8 * len(exposures)) if exposures else None,
    }


def analyze(snapshot: Path, session: Path) -> dict:
    """验证榜单血缘与 31 房 310 桌结算，再做用户 ID 级描述。"""

    week_path = snapshot / "leaderboard-week.json"
    week = json.loads(week_path.read_text(encoding="utf-8"))
    meta = json.loads((snapshot / "snapshot.json").read_text(encoding="utf-8"))
    if meta["endpoints"]["leaderboard-week"]["http_status"] != 200:
        raise ValueError("本周榜单不是官方 200 快照")
    previous = (week.get("prev") or {}).get("top") or []
    current = week.get("top") or []
    if len(previous) < 4 or len(current) < 8:
        raise ValueError("上周前四或本周前八不完整")
    result = analyze_campaign(expected_r18(), source_index(session))
    if result["downloaded_tables"] != 310 or result["missing_tables"]:
        raise ValueError("R18 31 房官方完整桌赛不足 310")
    tables = result["tables"]
    sections = {}
    for label, board_rows in (("last_week_top4", previous[:4]),
                              ("current_week_top8", current[:8])):
        ids = {row["user_id"] for row in board_rows}
        sections[label] = {
            "board_rows": [{key: row.get(key) for key in ("rank", "user_id", "name", "score", "rooms")}
                           for row in board_rows],
            "profiles": {policy: {
                row["user_id"]: _profile([table for table in tables if table["policy"] == policy],
                                         row["user_id"])
                for row in board_rows
            } for policy in ("r18_v1", "r18_v2")},
            "segments": {},
        }
        for policy in ("r18_v1", "r18_v2"):
            selected = [table for table in tables if table["policy"] == policy
                        and ids.intersection(table["opponent_user_ids"])]
            remaining = [table for table in tables if table["policy"] == policy
                         and not ids.intersection(table["opponent_user_ids"])]
            sections[label]["segments"][policy] = {
                "tagged_tables": len(selected),
                "tagged_rooms": len({table["room_id"] for table in selected}),
                "tagged_focal_net": sum(table["focal_score"] for table in selected),
                "other_tables": len(remaining),
                "other_rooms": len({table["room_id"] for table in remaining}),
                "other_focal_net": sum(table["focal_score"] for table in remaining),
            }
    return {
        "schema": "r18-leaderboard-opponent-profile/1",
        "snapshot": str(snapshot.relative_to(ROOT)),
        "snapshot_sha256": hashlib.sha256(week_path.read_bytes()).hexdigest(),
        "captured_at_unix_ms": meta["captured_at_unix_ms"],
        "guide_version_at_capture": meta["guide_version"],
        "week_from_unix": week.get("from"),
        "previous_week": {key: (week.get("prev") or {}).get(key)
                          for key in ("label", "from", "to")},
        "source_tables": result["downloaded_tables"],
        "r18_segments": {policy: {key: segment[key] for key in
                                   ("rooms", "complete_tables", "focal_score_total")}
                         for policy, segment in result["segments"].items()},
        "groups": sections,
        "limitations": [
            "榜单取自 2026-09-25；R18 对局在 2026-09-23，榜单标签不是当时已知的预测标签。",
            "同房 10 桌共享对手与时段；玩家画像与我方分数是描述关联，不是策略因果效应。",
            "赛后官方牌谱不含对手内部决策候选，不能据此宣称复原其算法。",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--session", type=Path, default=DEFAULT_SESSION)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    body = analyze(args.snapshot.resolve(), args.session.resolve())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
    print(args.out)


if __name__ == "__main__":
    main()
