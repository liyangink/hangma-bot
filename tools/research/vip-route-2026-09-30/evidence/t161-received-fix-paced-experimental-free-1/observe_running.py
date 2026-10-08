"""轻量读取本房新增审计行；不评分、不联网、不修改运行配置。

只统计已经完整落盘的行。进行中数字可能尚未完整，不能授完赛门禁。
记录读取偏移以避免每次重扫整房；时间使用UTC墙上时钟，仅作观察时间。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t161-received-fix-paced-experimental-free-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path

ROOT = _PROJECT_ROOT
HERE = Path(__file__).resolve().parent
BASE = _project_file(_PROJECT_ROOT, ROOT / "artifacts/sessions/t161-vip-s02-free-v4-paced/audit")


def main():
    """增量读取规范日志；RAW副本不重复计HTTP，完整结果由赛后工具核验。"""
    state_path = _project_file(_PROJECT_ROOT, HERE / "RUNNING-OBSERVATION-STATE.json")
    state = json.loads(state_path.read_text()) if state_path.exists() else {
        "offsets": {}, "counts": {}, "games_finished": [], "rounds_finished": {},
        "state_queue_max_ms": 0, "state_queue_count": 0, "state_queue_sum_ms": 0,
    }
    counts = Counter(state["counts"])
    paths = sorted({*BASE.glob("runs/*/participants/*/decisions.jsonl"),
                    *BASE.glob("runs/*/participants/*/games/*.jsonl")})
    for path in paths:
        name = str(path.relative_to(BASE))
        with path.open("rb") as stream:
            stream.seek(state["offsets"].get(name, 0))
            while raw := stream.readline():
                if not raw.endswith(b"\n"):
                    break
                record = json.loads(raw)
                state["offsets"][name] = stream.tell()
                kind, payload, context = record["kind"], record["payload"], record["context"]
                counts[kind] += 1
                if "/games/" in name and type(context.get("round_no")) is int:
                    latest = state.setdefault("latest_round_by_game", {})
                    game = context["game_id"]
                    latest[game] = max(latest.get(game, 0), context["round_no"])
                if kind == "game_finished" and payload.get("final_scores") is not None:
                    game = context["game_id"]
                    if game not in state["games_finished"]:
                        state["games_finished"].append(game)
                if kind == "round_finished":
                    game = context["game_id"]
                    round_no = context.get("round_no")
                    previous = state["rounds_finished"].get(game, [])
                    if round_no not in previous:
                        state["rounds_finished"][game] = previous + [round_no]
                if kind == "decision_planned":
                    counts["complete_plans" if payload.get("returned_plan") is not None else "failed_plans"] += 1
                if kind == "http_request" and payload.get("phase") == "finished":
                    endpoint = payload.get("endpoint", "")
                    category = "state" if "/api/games/" in endpoint and "/state" in endpoint else (
                        "action" if "/api/games/" in endpoint and "/action" in endpoint else "other")
                    counts[f"http_{category}_{payload.get('http_status')}"] += 1
                    timing = payload.get("request_timing", {})
                    low, high = timing.get("queued_at_monotonic"), timing.get("granted_at_monotonic")
                    if category == "state" and low is not None and high is not None:
                        wait = (high - low) * 1000
                        state["state_queue_count"] += 1
                        state["state_queue_sum_ms"] += wait
                        state["state_queue_max_ms"] = max(wait, state["state_queue_max_ms"])
    state["counts"] = dict(counts)
    state["observed_at_utc"] = datetime.now(timezone.utc).isoformat()
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    view = {"observed_at_utc": state["observed_at_utc"], "scope": "incomplete_local_observation",
            "finished_tables": len(state["games_finished"]),
            "latest_round_by_game": state.get("latest_round_by_game", {}),
            "complete_plans": counts["complete_plans"], "failed_plans": counts["failed_plans"],
            "state_429": counts["http_state_429"], "action_429": counts["http_action_429"],
            "state_queue_mean_ms": state["state_queue_sum_ms"] / max(1, state["state_queue_count"]),
            "state_queue_max_ms": state["state_queue_max_ms"]}
    with (_project_file(_PROJECT_ROOT, HERE / "RUNNING-OBSERVATIONS.jsonl")).open("a") as stream:
        stream.write(json.dumps(view, ensure_ascii=False) + "\n")
    print(json.dumps(view, ensure_ascii=False))


if __name__ == "__main__":
    main()
