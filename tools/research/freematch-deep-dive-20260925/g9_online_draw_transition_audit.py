#!/usr/bin/env python3
"""结果盲审计：连续本人摸牌窗口的上一接受动作是否必为弃牌。"""

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
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g9-online-draw-transition-20260927/result.json')


def main() -> None:
    """仅读冻结训练房动作审计，不读官方后续牌谱或终局分。"""
    if OUT.exists():
        raise SystemExit("G9 摸牌转移预检已冻结，拒绝覆盖")
    frozen_bytes = FROZEN.read_bytes()
    frozen = json.loads(frozen_bytes)
    totals = Counter()
    by_room = {}
    for room in frozen["rooms"]:
        audit = source.ROOT / room["audit_dir"]
        decision_file = audit / "participants" / source.ACTOR / "decisions.jsonl"
        if decision_file.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结房动作审计漂移")
        accepted = source._accepted(decision_file)
        prior: dict[tuple[str, int], tuple[str, int]] = {}
        counts = Counter()
        for context, request, _plan in source.screen._iter_decisions(audit):
            window = request.get("window_key") or {}
            if window.get("phase") != "draw":
                continue
            key = (context["game_id"], context["round_no"])
            action_key = accepted.get(context["decision_id"])
            action_kind = "unconfirmed" if action_key is None else action_key.split(":", 1)[0]
            seq = window.get("trigger_seq")
            if type(seq) is not int:
                raise ValueError("摸牌窗口缺官方触发序号")
            if key in prior:
                prior_kind, prior_seq = prior[key]
                if seq <= prior_seq:
                    raise ValueError("同局连续摸牌窗口水位未严格递增")
                counts["repeated_draw"] += 1
                counts["prior_" + prior_kind] += 1
                counts["prior=" + prior_kind + "|current=" + action_kind] += 1
            else:
                counts["first_draw"] += 1
            counts["current_" + action_kind] += 1
            prior[key] = (action_kind, seq)
        by_room[room["room_id"]] = dict(sorted(counts.items()))
        totals.update(counts)
    result = {
        "schema": "g9-online-draw-transition-audit/1",
        "source_rooms": len(by_room),
        "source_frozen_rooms_sha256": hashlib.sha256(frozen_bytes).hexdigest(),
        "source_parent_sha256": frozen["parent_source_sha256"],
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "outcome_blind": True,
        "totals": dict(sorted(totals.items())),
        "by_room": by_room,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "by_room"},
                     ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
