#!/usr/bin/env python3
"""G22 D1/D2：冻结父代同分层中“可证不可叫”与末墩改选的结果盲覆盖。"""

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
import g14_latent_natural_links_probe as g14
from hangma_bot.hangma.engine import _build_context
from hangma_bot.hangma.internal_types import TILE_INDEX
from hangma_bot.hangma.public_tile_counts import count_unseen_tiles
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g22-diverse-author-wave-20260927/d1-coverage.json')


def safe(code: str, unknown: tuple[int | None, ...]) -> bool:
    """只在四张物理上界能证伪所有碰、明杠与吃时返回真。"""

    if code == "白":
        return False
    amount = unknown[TILE_INDEX[code]]
    if amount is None or amount > 1:
        return False
    if code[-1] not in "wbt":
        return True
    rank = int(code[0])
    suffix = code[1]
    for start in range(max(1, rank - 2), min(rank, 7) + 1):
        others = [f"{value}{suffix}" for value in range(start, start + 3) if value != rank]
        if all(unknown[TILE_INDEX[other]] is None or
               unknown[TILE_INDEX[other]] > 0 for other in others):
            return False
    return True


def main() -> None:
    """只读动作前观察、父代分数和合法候选，不查看赛果标签。"""

    if OUT.exists():
        raise SystemExit("G22 D1 覆盖结果已存在，拒绝覆盖")
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    complete = atlas._complete_ids()
    if len(complete) != 909:
        raise ValueError("冻结完整桌数漂移")
    old10, old11, old28a, old28b = g14._known_old_actions()
    counts = Counter()
    tables: dict[str, set[str]] = defaultdict(set)
    examples = []
    d2_examples = []
    for room in frozen["rooms"]:
        audit = atlas.source.ROOT / room["audit_dir"]
        decisions = audit / "participants" / atlas.source.ACTOR / "decisions.jsonl"
        if decisions.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结决策文件字节数漂移")
        release = ((json.loads((audit / "manifest.json").read_text(encoding="utf-8"))
                    .get("payload") or {}).get("policy_release") or {})
        if release.get("candidate_source_sha256") != frozen["parent_source_sha256"]:
            raise ValueError("冻结父代源码身份漂移")
        accepted = atlas.source._accepted(decisions)
        for context, raw, plan in atlas.source.screen._iter_decisions(audit):
            gid = context.get("game_id")
            if gid not in complete or (raw.get("window_key") or {}).get("phase") != "draw":
                continue
            ranked = sorted(plan.get("candidates") or [], key=lambda row: row.get("rank", 10**9))
            if not ranked or not (ranked[0].get("action_key") or "").startswith("discard:"):
                continue
            parent = ranked[0]["action_key"]
            if accepted.get(context.get("decision_id")) != parent:
                continue
            counts["accepted_discard_windows"] += 1
            obs = observation_from_json(raw["observation"])
            if obs.rule_state.catch_play:
                counts["catch_play_excluded"] += 1
                continue
            legal_rows = (raw.get("rules") or {}).get("legal_candidates") or []
            legal = {row["action_key"]: row.get("facts") or {} for row in legal_rows}
            if len(legal) != len(legal_rows) or parent not in legal:
                raise ValueError("冻结合法候选漂移")
            top = ranked[0].get("total_score")
            if type(top) not in (int, float):
                raise ValueError("父代总分缺失")
            tied_all = [row["action_key"] for row in ranked
                    if row.get("total_score") == top and
                    (row.get("action_key") or "").startswith("discard:") and
                    row["action_key"] in legal]
            if len(tied_all) >= 2:
                counts["all_top_tie_windows"] += 1
            wall = obs.remaining_tile_count
            unknown = None
            if (len(tied_all) >= 2 and type(wall) is int and
                    wall - 20 in {1, 2, 3, 5, 6, 7} and
                    all(len(groups) < 3 for groups in obs.melds)):
                counts["d2_tie_eligible"] += 1
                unknown = count_unseen_tiles(obs)
                if any(value is None for value in unknown):
                    counts["d2_unknown_count_invalid"] += 1
                else:
                    def d2_uncallable(action: str) -> bool:
                        code = action.split(":", 1)[1]
                        return code == "白" or safe(code, unknown)
                    if d2_uncallable(parent):
                        possible = [action for action in tied_all if not d2_uncallable(action)]
                        if possible:
                            counts["d2_changed"] += 1
                            tables["d2_changed"].add(gid)
                            if len(d2_examples) < 12:
                                d2_examples.append({"game_id": gid, "round_no": context.get("round_no"),
                                                    "trigger_seq": context.get("trigger_seq"),
                                                    "parent": parent, "alternative": possible[0],
                                                    "wall_remaining": wall, "score": top})
            if type(legal[parent].get("shanten_after")) is not int or legal[parent]["shanten_after"] < 1:
                continue
            counts["nonready_parent_windows"] += 1
            tied = [action for action in tied_all
                    if type(legal[action].get("shanten_after")) is int and
                    legal[action]["shanten_after"] >= 1]
            if len(tied) < 2:
                continue
            counts["nonready_tie_windows"] += 1
            if unknown is None:
                unknown = count_unseen_tiles(obs)
            if any(value is None for value in unknown):
                counts["unknown_count_invalid"] += 1
                continue
            safer = [action for action in tied if safe(action.split(":", 1)[1], unknown)]
            if not safer:
                continue
            counts["tie_has_proven_uncallable"] += 1
            if parent in safer:
                counts["parent_already_uncallable"] += 1
                continue
            chosen = safer[0]
            key = (gid, context.get("round_no"), context.get("trigger_seq"))
            counts["changed"] += 1
            tables["changed"].add(gid)
            white_after = sum(tile.code == "白" for tile in _build_context(obs).full_hand())
            if white_after:
                counts["changed_held_white"] += 1
                tables["changed_held_white"].add(gid)
            for name, actions in (("g10", old10), ("g11", old11), ("p28a", old28a), ("p28b", old28b)):
                if key in actions:
                    counts[f"{name}_covered"] += 1
                    if actions[key] == chosen:
                        counts[f"{name}_same_action"] += 1
            if len(examples) < 12:
                examples.append({"game_id": gid, "round_no": key[1], "trigger_seq": key[2],
                                 "parent": parent, "alternative": chosen,
                                 "score": top, "held_white": white_after,
                                 "same_score_actions": tied})
    result = {"schema": "g22-certified-uncallable-screen/2", "outcome_blind": True,
              "frozen_rooms_sha256": hashlib.sha256(atlas.FROZEN.read_bytes()).hexdigest(),
              "parent_source_sha256": frozen["parent_source_sha256"],
              "complete_tables": len(complete), "counts": dict(sorted(counts.items())),
              "table_coverage": {name: len(ids) for name, ids in sorted(tables.items())},
              "examples": examples, "d2_examples": d2_examples,
              "boundary": "只证明吃碰明杠物理上不可能；不证明避免被叫改善自身摸牌时机或完整桌净分。"}
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"counts": result["counts"], "table_coverage": result["table_coverage"]},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
