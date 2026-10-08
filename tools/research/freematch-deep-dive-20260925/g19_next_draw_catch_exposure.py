#!/usr/bin/env python3
"""G19 冻结父代实到下一本人摸牌的抓打限制诊断；不推断改选反事实。"""

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

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

import g11_cross_family_action_atlas as atlas
import g19_near_win_two_draw_probe as g19


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g19-near-win-two-draw-20260927/next-draw-catch-exposure.json')


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """只观察 G19 根后真实父代下一次物理本人摸牌，统计抓打圈状态。"""

    if OUT.exists():
        raise SystemExit("G19 下一摸抓打诊断已存在，拒绝覆盖")
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    targets = g19._target_rows(frozen)
    g19_result = json.loads(g19.OUT.read_text(encoding="utf-8"))
    if (g19_result.get("outcome_blind") is not True or
            g19_result.get("targets") != len(targets) or
            g19_result.get("rows_sha256") != _sha(g19.ROWS)):
        raise ValueError("G19 联合量具结果或逐窗摘要漂移")
    by_round: dict[tuple[str, int, int], list[tuple[int, dict]]] = defaultdict(list)
    for room in frozen["rooms"]:
        audit = atlas.source.ROOT / room["audit_dir"]
        decisions = audit / "participants" / atlas.source.ACTOR / "decisions.jsonl"
        if decisions.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结房动作文件字节数漂移")
        for context, raw, _ in atlas.source.screen._iter_decisions(audit):
            if (raw.get("window_key") or {}).get("phase") != "draw":
                continue
            observation = raw.get("observation") or {}
            seat = observation.get("seat")
            seq = context.get("trigger_seq")
            if type(seat) is int and type(seq) is int:
                by_round[(context.get("game_id"), context.get("round_no"), seat)].append(
                    (seq, observation))
    counts = Counter()
    tables: dict[str, set[str]] = defaultdict(set)
    for (game_id, round_no, root_seq), target in targets.items():
        events = sorted(by_round[(game_id, round_no, target["seat"])], key=lambda item: item[0])
        if not any(seq == root_seq for seq, _ in events):
            raise ValueError("G19 根动作窗口未在父代审计中复原")
        future = [observation for seq, observation in events
                  if seq > root_seq and isinstance(observation.get("drawn_tile"), str)]
        if not future:
            label = "no_next_physical_draw"
        else:
            rules = future[0].get("rule_state") or {}
            active = rules.get("catch_play")
            owner = rules.get("catch_play_owner_seat")
            if active is False:
                label = "next_free_no_circle"
            elif active is True and owner == target["seat"]:
                label = "next_free_owner"
            elif active is True and type(owner) is int and 0 <= owner < 4:
                label = "next_restricted"
            else:
                label = "next_unknown_circle_or_owner"
        counts[label] += 1
        tables[label].add(game_id)
    if sum(counts.values()) != len(targets):
        raise ValueError("G19 根的实到下一摸牌分类未覆盖全体")
    result = {"schema": "g19-next-draw-catch-exposure/1",
              "observational_parent_path": True,
              "source_g19_result_sha256": _sha(g19.OUT),
              "source_g19_rows_sha256": _sha(g19.ROWS),
              "source_frozen_rooms_sha256": _sha(atlas.FROZEN),
              "parent_source_sha256": frozen["parent_source_sha256"],
              "script_sha256": _sha(Path(__file__)), "targets": len(targets),
              "counts": dict(sorted(counts.items())),
              "table_coverage": {name: len(ids) for name, ids in sorted(tables.items())},
              "boundary": "仅冻结父代同单局实到的下一次物理本人摸牌；没有下一次可能由他家先胡、本人先胡或局终等造成。改选弃牌可能改变后续时序，不可把本频率当候选的真实继续概率。"}
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps(result["counts"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
