#!/usr/bin/env python3
"""G34：结果盲查 GLM 普通活听保护案在冻结官方父代轨迹的真实触达。"""

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

import g11_cross_family_action_atlas as atlas


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g34-live-tenpai-guard-reach-20260927/result.json')
AUTHOR = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g33-glm-breadth-pilot-20260927/d01_plain_hu_guard.answer.txt')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def live_standard_tenpai(facts: dict) -> bool:
    """普通型向听为零，且生产有效牌中有至少一个非白、公开未证死的牌码。"""

    return facts.get("standard_shanten_after") == 0 and any(
        item.get("code") != "白" and type(item.get("remaining_estimate")) is int
        and item["remaining_estimate"] > 0
        for item in (facts.get("standard_useful_tiles") or ()))


def main() -> None:
    """仅遍历已接受父代摸牌弃牌，不借用后局得分筛样本。"""

    if OUT.exists():
        raise SystemExit("G34 触达结果已存在，拒绝覆盖")
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    complete = atlas._complete_ids()
    if len(complete) != 909 or frozen.get("parent_source_sha256") != "a2d9b8af93beabdba75716fccae56b0668a6fd84f0bdce558d2ff3e569443618":
        raise ValueError("冻结父代或完整桌清单漂移")
    author = json.loads(AUTHOR.read_text(encoding="utf-8"))
    if author["task_id"] != "d01_plain_hu_guard" or not author["hypotheses"][0]["name"].startswith("M1_live_tenpai_veto"):
        raise ValueError("G33 作者目标漂移")
    counts = Counter()
    rows = []
    table_ids = set()
    room_ids = set()
    for room in frozen["rooms"]:
        audit = atlas.source.ROOT / room["audit_dir"]
        decision_file = audit / "participants" / atlas.source.ACTOR / "decisions.jsonl"
        if decision_file.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结房审计大小漂移")
        accepted = atlas.source._accepted(decision_file)
        for context, raw, plan in atlas.source.screen._iter_decisions(audit):
            game = context.get("game_id")
            if game not in complete or (raw.get("window_key") or {}).get("phase") != "draw":
                continue
            ranked = sorted(plan.get("candidates") or [], key=lambda item: item.get("rank", 10**9))
            if not ranked or not (ranked[0].get("action_key") or "").startswith("discard:"):
                continue
            parent_key = ranked[0]["action_key"]
            if accepted.get(context.get("decision_id")) != parent_key:
                continue
            counts["accepted_parent_draw_discards"] += 1
            legal = {item["action_key"]: item.get("facts") or {}
                     for item in (raw.get("rules") or {}).get("legal_candidates") or []
                     if (item.get("action_key") or "").startswith("discard:")}
            parent = legal[parent_key]
            if parent.get("standard_shanten_after") is None or parent["standard_shanten_after"] <= 0:
                continue
            live = [(key, facts) for key, facts in legal.items()
                    if key != "discard:白" and live_standard_tenpai(facts)]
            if not live:
                continue
            best = min(live, key=lambda pair: pair[0])
            scores = {item["action_key"]: item.get("total_score") for item in ranked}
            counts["windows_with_live_standard_tenpai_veto"] += 1
            table_ids.add(game)
            room_ids.add(room["room_id"])
            rows.append({"room_id": room["room_id"], "game_id": game,
                         "round_no": context.get("round_no"), "trigger_seq": context.get("trigger_seq"),
                         "parent_action": parent_key, "parent_standard_shanten": parent["standard_shanten_after"],
                         "parent_combined_shanten": parent.get("shanten_after"),
                         "parent_seven_pairs_shanten": parent.get("seven_pairs_shanten_after"),
                         "example_alternative": best[0],
                         "alternative_combined_shanten": best[1].get("shanten_after"),
                         "alternative_seven_pairs_shanten": best[1].get("seven_pairs_shanten_after"),
                         "parent_score": scores[parent_key],
                         "alternative_score": scores.get(best[0]),
                         "live_alternative_count": len(live)})
    result = {"schema": "g34-live-tenpai-guard-reach/1",
              "frozen_source_sha256": sha(atlas.FROZEN), "author_answer_sha256": sha(AUTHOR),
              "source_sha256": sha(Path(__file__)), "counts": dict(counts),
              "complete_tables_touched": len(table_ids), "rooms_touched": len(room_ids),
              "rows": rows,
              "boundary": "结果盲行为触达；没有构造候选，也未证明改选会改善整桌净分。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"counts": result["counts"], "tables": len(table_ids),
                      "rooms": len(room_ids)}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
