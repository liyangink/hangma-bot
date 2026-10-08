#!/usr/bin/env python3
"""G24：在冻结父代全轨迹盲筛 G23 留出后的持白自然路线质量改选。"""

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
import g17_one_draw_value_gap as g17
import g23_route_proxy as proxy
from hangma_bot.hangma.engine import _build_context
from hangma_bot.hangma.internal_types import counts_from_tiles
from hangma_bot.hangma.public_tile_counts import count_unseen_tiles
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g24-route-mass-behavior-20260927/result.json')
PROXY = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g23-three-draw-teacher-20260927/proxy.json')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _eligible(facts: dict) -> bool:
    std, seven = facts.get("standard_shanten_after"), facts.get("seven_pairs_shanten_after")
    return type(std) is int and std == 1 and (seven is None or type(seven) is int and seven > 2)


def main() -> None:
    """只读父代已接受动作、规则事实和可见观察，不读取赛果。"""

    if OUT.exists():
        raise SystemExit("G24 行为结果已存在，拒绝覆盖")
    learned = json.loads(PROXY.read_text(encoding="utf-8"))
    chosen = learned.get("chosen") or {}
    if (learned.get("primary_condition") != "depth2 difference = 0" or
            chosen.get("feature") != "route_mass" or chosen.get("orientation") != 1):
        raise ValueError("G23 冻结代理身份漂移")
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    complete = atlas._complete_ids()
    if len(complete) != 909:
        raise ValueError("冻结完整桌数量漂移")
    old10, old11, old28a, old28b = g14._known_old_actions()
    counts = Counter()
    tables: dict[str, set[str]] = defaultdict(set)
    examples = []
    for room in frozen["rooms"]:
        audit = atlas.source.ROOT / room["audit_dir"]
        decisions = audit / "participants" / atlas.source.ACTOR / "decisions.jsonl"
        if decisions.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结房决策字节数漂移")
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
            if parent == "discard:白" or accepted.get(context.get("decision_id")) != parent:
                continue
            counts["accepted_nonwhite_discard_windows"] += 1
            legal_rows = (raw.get("rules") or {}).get("legal_candidates") or []
            legal = {row["action_key"]: row.get("facts") or {} for row in legal_rows}
            if len(legal) != len(legal_rows) or parent not in legal:
                raise ValueError("生产合法候选事实漂移")
            pf = legal[parent]
            if not _eligible(pf):
                continue
            counts["parent_standard_shanten_one"] += 1
            pstd, pcombined = (g17._vector(pf, field) for field in
                              ("standard_useful_tiles", "useful_tiles"))
            if pstd is None or pcombined is None:
                continue
            top_score = ranked[0].get("total_score")
            if type(top_score) not in (int, float):
                raise ValueError("父代评分缺失")
            alternative = None
            gap = None
            for item in ranked[1:]:
                action = item.get("action_key")
                if not isinstance(action, str) or not action.startswith("discard:") or action == "discard:白":
                    continue
                af = legal.get(action)
                if af is None or not _eligible(af):
                    continue
                if (g17._vector(af, "standard_useful_tiles") != pstd or
                        g17._vector(af, "useful_tiles") != pcombined):
                    continue
                score = item.get("total_score")
                if type(score) not in (int, float) or not 0 <= top_score - score <= 3:
                    continue
                alternative = action
                gap = top_score - score
                break
            if alternative is None:
                continue
            counts["comparable_pairs"] += 1
            obs = observation_from_json(raw["observation"])
            full = _build_context(obs).full_hand()
            white = sum(tile.code == "白" for tile in full)
            if white == 0:
                counts["no_white_excluded"] += 1
                continue
            unseen = count_unseen_tiles(obs)
            if any(amount is None for amount in unseen):
                counts["unseen_invalid"] += 1
                continue
            meld_count = len(obs.melds[obs.seat])
            values = {}
            for name, action in (("parent", parent), ("alternative", alternative)):
                tiles = list(full)
                discard = action.split(":", 1)[1]
                for index, tile in enumerate(tiles):
                    if tile.code == discard:
                        del tiles[index]
                        break
                else:
                    raise ValueError("候选弃牌不在本人完整暗手")
                values[name] = proxy.primitives(counts_from_tiles(tuple(tiles)), unseen,
                                                 meld_count)["route_mass"]
            delta = values["alternative"] - values["parent"]
            if delta <= 0:
                counts["route_mass_not_positive"] += 1
                continue
            counts["changed"] += 1
            tables["changed"].add(gid)
            bucket = min(white, 2)
            counts[f"changed_white_{bucket}"] += 1
            tables[f"changed_white_{bucket}"].add(gid)
            if gap == 0:
                counts["changed_same_parent_score"] += 1
            key = (gid, context.get("round_no"), context.get("trigger_seq"))
            for name, actions in (("g10", old10), ("g11", old11),
                                  ("p28a", old28a), ("p28b", old28b)):
                if key in actions:
                    counts[f"{name}_covered"] += 1
                    if actions[key] == alternative:
                        counts[f"{name}_same_action"] += 1
            if len(examples) < 12:
                examples.append({"room_id": room["room_id"], "game_id": gid,
                                 "round_no": key[1], "trigger_seq": key[2],
                                 "parent": parent, "alternative": alternative,
                                 "white_after": white, "score_gap": gap,
                                 "route_mass_parent": values["parent"],
                                 "route_mass_alternative": values["alternative"]})
    result = {"schema": "g24-route-mass-behavior/1", "outcome_blind": True,
              "source_frozen_rooms_sha256": sha(atlas.FROZEN),
              "parent_source_sha256": frozen["parent_source_sha256"],
              "source_proxy_sha256": sha(PROXY),
              "script_sha256": sha(Path(__file__)), "complete_tables": len(complete),
              "counts": dict(sorted(counts.items())),
              "table_coverage": {name: len(ids) for name, ids in sorted(tables.items())},
              "examples": examples,
              "boundary": "结果盲动作覆盖，不是替代行为的完整桌收益；旧方法重叠仅在记录覆盖范围精确核。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"counts": result["counts"], "tables": result["table_coverage"]},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
