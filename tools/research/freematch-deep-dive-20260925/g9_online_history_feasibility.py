#!/usr/bin/env python3
"""结果盲统计线上观察历史与前次本人决策的可用性。"""

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

import g8_public_response_training_rows as source


HERE = Path(__file__).resolve().parent
FROZEN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g8-two-white-next-draw-20260927/frozen_rooms.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g9-online-history-feasibility-20260927/result.json')


def main() -> None:
    """不看牌谱结局，仅查当前观察和同一场同一单局的既有本人窗口。"""

    if OUT.exists():
        raise SystemExit("历史可用性结果已冻结，拒绝覆盖")
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    totals = Counter()
    by_room = {}
    for room in frozen["rooms"]:
        audit = source.ROOT / room["audit_dir"]
        decision_file = audit / "participants" / source.ACTOR / "decisions.jsonl"
        if decision_file.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结决策记录漂移")
        counts = Counter()
        previous = {}
        previous_draw = {}
        for context, request, _plan in source.screen._iter_decisions(audit):
            observation = request["observation"]
            phase = (request.get("window_key") or {}).get("phase")
            key = (context["game_id"], context["round_no"])
            seq = context["trigger_seq"]
            if key in previous and seq < previous[key]:
                raise ValueError("同一单局本人决策序号回退")
            history = observation.get("public_history")
            if not isinstance(history, list):
                raise ValueError("线上观察历史类型不符")
            counts["all_decisions"] += 1
            counts["history_complete_true"] += observation.get("history_complete") is True
            counts["history_nonempty"] += len(history) > 0
            if phase == "draw":
                counts["draw_decisions"] += 1
                counts["draw_has_previous_own_decision_same_round"] += key in previous
                counts["draw_has_previous_own_draw_same_round"] += key in previous_draw
                if key in previous_draw:
                    counts["draw_previous_draw_seq_delta_le_100"] += seq - previous_draw[key] <= 100
                previous_draw[key] = seq
            previous[key] = seq
        by_room[room["room_id"]] = dict(sorted(counts.items()))
        totals.update(counts)
    result = {
        "schema": "g9-online-history-feasibility/1",
        "source_rooms": len(by_room),
        "source_frozen_rooms_sha256": hashlib.sha256(FROZEN.read_bytes()).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "outcome_blind": True,
        "totals": dict(sorted(totals.items())),
        "rooms_with_nonempty_history": sum(row.get("history_nonempty", 0) > 0
                                           for row in by_room.values()),
        "by_room": by_room,
        "boundary": "前次本人决策在赛后审计可见，不证明线上重连/进程重启后可用；需另设失忆降级"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "by_room"},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
