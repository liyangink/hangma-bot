#!/usr/bin/env python3
"""G35：结果盲查 GLM 的“硬无碰/公开供给”机制是否有独有触达。"""

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
import g17_one_draw_value_gap as g17
from hangma_bot.hangma.engine import _build_context
from hangma_bot.hangma.public_tile_counts import count_unseen_tiles
from hangma_bot.kernel.actions import CANONICAL_TILE_INDEX
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g35-public-supply-reach-20260927/result.json')
G30 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g30-edge-behavior-20260927/result.json')
AUTHOR = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g33-glm-breadth-pilot-20260927/d04_novelty_control.answer.txt')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def same_progress(left: dict, right: dict) -> bool:
    """即时普通型与综合逐码事实均已知且完全相同。"""

    if (type(left.get("shanten_after")) is not int
            or type(left.get("standard_shanten_after")) is not int
            or left.get("shanten_after") != right.get("shanten_after")
            or left.get("standard_shanten_after") != right.get("standard_shanten_after")
            or left.get("seven_pairs_shanten_after") != right.get("seven_pairs_shanten_after")):
        return False
    return all(g17._vector(left, field) is not None
               and g17._vector(left, field) == g17._vector(right, field)
               for field in ("standard_useful_tiles", "useful_tiles"))


def main() -> None:
    """仅统计规则同源公开未见数的可达改选，不执行任何新策略。"""

    if OUT.exists():
        raise SystemExit("G35 触达结果已存在，拒绝覆盖")
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    complete = atlas._complete_ids()
    if len(complete) != 909 or frozen.get("parent_source_sha256") != "a2d9b8af93beabdba75716fccae56b0668a6fd84f0bdce558d2ff3e569443618":
        raise ValueError("冻结父代或完整桌清单漂移")
    author = json.loads(AUTHOR.read_text(encoding="utf-8"))
    if author["task_id"] != "d04_novelty_control" or not author["hypotheses"][1]["name"].startswith("M2_"):
        raise ValueError("G33 作者目标漂移")
    old = json.loads(G30.read_text(encoding="utf-8"))
    old_changes = {(row["game_id"], row["round_no"], row["trigger_seq"]): row["candidate_action"]
                   for row in old["changed"]}
    counts = Counter()
    rows = []
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
            if parent_key == "discard:白" or type(parent.get("standard_shanten_after")) is not int:
                continue
            candidate_pairs = [(key, facts) for key, facts in legal.items()
                               if key != parent_key and key != "discard:白"
                               and same_progress(parent, facts)]
            if not candidate_pairs:
                continue
            counts["same_progress_windows"] += 1
            observation = observation_from_json(raw["observation"])
            unseen = count_unseen_tiles(observation)
            parent_unseen = unseen[CANONICAL_TILE_INDEX[parent_key[8:]]]
            if parent_unseen is None:
                counts["unknown_parent_supply"] += 1
                continue
            scores = {item["action_key"]: item.get("total_score") for item in ranked}
            eligible = []
            for key, facts in candidate_pairs:
                amount = unseen[CANONICAL_TILE_INDEX[key[8:]]]
                if amount is None:
                    counts["unknown_alternative_supply"] += 1
                    continue
                gap = scores[parent_key] - scores[key]
                if type(gap) not in (int, float) or gap < 0 or gap > 3:
                    continue
                eligible.append((key, amount, gap))
            if not eligible:
                continue
            counts["same_progress_gap3_windows"] += 1
            hard = [item for item in eligible if parent_unseen >= 2 and item[1] <= 1]
            strict = [item for item in hard if item[2] == 0]
            supply = [item for item in eligible if item[1] < parent_unseen and item[2] == 0]
            if not hard and not supply:
                continue
            window = (game, context.get("round_no"), context.get("trigger_seq"))
            representatives = {}
            for cohort, options in (("hard_no_peng_gap3", hard),
                                    ("hard_no_peng_exact_score", strict),
                                    ("smaller_supply_exact_score", supply)):
                if options:
                    choice = min(options, key=lambda item: (item[1], item[2], item[0]))
                    representatives[cohort] = {
                        "action_key": choice[0], "unseen": choice[1],
                        "parent_score_gap": choice[2],
                        "same_as_g30_action": old_changes.get(window) == choice[0]}
            counts["hard_no_peng_gap3_windows"] += int(bool(hard))
            counts["hard_no_peng_exact_score_windows"] += int(bool(strict))
            counts["smaller_supply_exact_score_windows"] += int(bool(supply))
            rows.append({"room_id": room["room_id"], "game_id": game,
                         "round_no": window[1], "trigger_seq": window[2],
                         "parent_action": parent_key, "parent_unseen": parent_unseen,
                         "white_count": sum(tile.code == "白" for tile in _build_context(observation).full_hand()),
                         "parent_shanten": parent["shanten_after"],
                         "parent_standard_shanten": parent["standard_shanten_after"],
                         "parent_seven_pairs_shanten": parent.get("seven_pairs_shanten_after"),
                         "hard_no_peng": bool(hard), "strict_hard_no_peng": bool(strict),
                         "smaller_supply": bool(supply), "representatives": representatives})
    tables = {row["game_id"] for row in rows}
    rooms = {row["room_id"] for row in rows}
    result = {"schema": "g35-public-supply-reach/1",
              "frozen_source_sha256": sha(atlas.FROZEN), "author_answer_sha256": sha(AUTHOR),
              "g30_result_sha256": sha(G30), "source_sha256": sha(Path(__file__)),
              "counts": dict(counts), "complete_tables_touched": len(tables),
              "rooms_touched": len(rooms), "rows": rows,
              "boundary": "生产牌张去重口径的结果盲硬供给触达；不把未知容量当零或墙内概率，亦无候选收益证据。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"counts": result["counts"], "tables": len(tables),
                      "rooms": len(rooms)}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
