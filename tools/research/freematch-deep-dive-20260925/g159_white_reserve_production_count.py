#!/usr/bin/env python3
"""G159 结果盲复核 G14 白板保留前沿，改用生产公开牌计数。"""

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
from functools import lru_cache
import gzip
import hashlib
import json
from pathlib import Path

import g11_cross_family_action_atlas as atlas
import g11_longitudinal_route_audit as g11
import g14_discard_width_baseline as width
from hangma_bot.hangma.candidate_facts import _remaining
from hangma_bot.hangma.hand_analysis import _chiitoi_pairs, _need_std
from hangma_bot.hangma.internal_types import TILE_ORDER, counts_from_tiles
from hangma_bot.hangma.public_tile_counts import count_public_tiles
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g159-white-reserve-production-count-20260928')
OLD = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g14-white-reserve-frontier-20260927/result.json')
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G159-WHITE-RESERVE-PRODUCTION-COUNT-PREREG-2026-09-28.md')
G10 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g10-route-option-screen-20260927/result.json')
G11 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g11-shape-risk-behavior-20260927/result.json')
NATURAL_CODES = tuple(TILE_ORDER[:33])


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@lru_cache(maxsize=300_000)
def _need(natural: tuple[int, ...], usable_white: int, sets_needed: int) -> int:
    """生产标准型最小自然补牌数；保留白板不参加当前面子/将最优化。"""

    return _need_std(natural, usable_white, sets_needed, True)


def _frontier(hand: Counter, melds: int, public_counts: tuple,
              just_discarded: str) -> dict:
    """返回每个保留白板数的缺口及全保留时下一自然摸牌支持面。"""

    codes = tuple(Tile(code) for code in NATURAL_CODES + ("白",)
                  for _ in range(hand[code]))
    counts = counts_from_tiles(codes)
    whites = counts[33]
    if sum(counts) != 13 - 3 * melds:
        raise ValueError("弃后暗牌数不符合副露数")
    natural = counts[:33]
    sets_needed = 4 - melds
    needs = [_need(natural, whites - reserved, sets_needed)
             for reserved in range(whites + 1)]
    if any(needs[i + 1] < needs[i] for i in range(len(needs) - 1)):
        raise ValueError("保留更多白板却减少自然补牌缺口")
    seven_pair_needs = None
    if melds == 0:
        seven_pair_needs = [7 - _chiitoi_pairs(natural, whites - reserved)
                            for reserved in range(whites + 1)]
    target = needs[-1]
    new_public = {just_discarded: 1}
    useful = {}
    for index, code in enumerate(NATURAL_CODES):
        upper = _remaining(code, counts, public_counts, new_public)
        if upper == 0:
            continue
        next_counts = natural[:index] + (natural[index] + 1,) + natural[index + 1:]
        next_need = _need(next_counts, 0, sets_needed)
        if next_need < target:
            useful[code] = upper
    return {"whites_held": whites,
            "standard_natural_draws_needed_by_reserved_whites": needs,
            "seven_pair_natural_draws_needed_by_reserved_whites": seven_pair_needs,
            "all_whites_reserved_natural_tile_types": len(useful),
            "all_whites_reserved_public_capacity_upper": sum(useful.values()),
            "all_whites_reserved_useful_by_tile": useful}


def _comparable(parent: dict, alternate: dict, p: dict, a: dict) -> bool:
    """保持白板数、普通/综合向听及七对保护，放宽公开容量最多 2。"""

    if p["whites_held"] != a["whites_held"]:
        return False
    for name in ("standard_shanten", "combined_shanten"):
        if parent[name] is None or alternate[name] != parent[name]:
            return False
    if (parent["seven_shanten"] is not None and
            (alternate["seven_shanten"] is None or
             alternate["seven_shanten"] > parent["seven_shanten"])):
        return False
    for name in ("standard", "combined"):
        if (parent[name] is None or alternate[name] is None or
                alternate[name][0] < parent[name][0] - 2):
            return False
    return True


def main() -> None:
    """扫描冻结父代合法弃牌；赛后未来墙与桌分不进此量具。"""

    if OUT.exists():
        raise SystemExit("G159 生产计数结果已存在，拒绝覆盖")
    if (_sha(atlas.FROZEN) !=
            "3869f77156945329065db36ba67e3c68d60b3e5776cac19e3ca49a38a25cecfd"
            or _sha(OLD) !=
            "c5dd370668f92bfd2eea7f99996ea420e117e50ae8d89384e4ea16501afd9254"
            or _sha(_project_file(_PROJECT_ROOT, HERE / "g14_white_reserve_frontier.py")) !=
            "e9c0c8df75584272e0df5b69ed86b6de2b281bb857e3bd2d28af7fc0f7172aa5"
            or _sha(_project_file(_PROJECT_ROOT, HERE.parents[1] / "src/hangma_bot/hangma/public_tile_counts.py")) !=
            "ffbe6bb3fb75e0970bddf3d377681f3a9fc98704c02d3ec29084ccd1344d6e29"
            or _sha(_project_file(_PROJECT_ROOT, HERE.parents[1] / "src/hangma_bot/hangma/candidate_facts.py")) !=
            "1318a08e8d51c67d1f07256dfd7f6d8d90bb9b85fc7d1e09b7d9146c40df08f9"):
        raise ValueError("G159 预登记的旧母体摘要漂移")
    old_result = json.loads(OLD.read_text(encoding="utf-8"))
    if (old_result["counts"]["accepted_normal_draw_discards"] != 55170
            or old_result["counts"]["parent_keeps_white"] != 23165
            or old_result["counts"]["any_natural_frontier_improvement"] != 2134):
        raise ValueError("G14 旧结果计数漂移")
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    complete = atlas._complete_ids()
    g10 = json.loads(G10.read_text(encoding="utf-8"))
    g11_old = json.loads(G11.read_text(encoding="utf-8"))
    if (len(complete) != 909 or g10.get("outcome_blind") is not True
            or g11_old.get("outcome_blind") is not True
            or g10["source_parent_sha256"] != frozen["parent_source_sha256"]
            or g11_old["parent_source_sha256"] != frozen["parent_source_sha256"]):
        raise ValueError("父代、旧行为或完整桌母体漂移")
    old_g10 = {(r["game_id"], r["round_no"], r["trigger_seq"]): r["alternate_action"]
               for r in g10["rows"]}
    old_g11 = {(r["game_id"], r["round_no"], r["trigger_seq"]): r["candidate_action"]
               for r in g11_old["changed"]}
    counts = Counter()
    scopes = defaultdict(set)
    strata = defaultdict(Counter)
    rows = []
    for room in frozen["rooms"]:
        audit = atlas.source.ROOT / room["audit_dir"]
        decisions = audit / "participants" / atlas.source.ACTOR / "decisions.jsonl"
        if decisions.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结父代审计字节数漂移")
        release = ((json.loads((audit / "manifest.json").read_text(encoding="utf-8"))
                    .get("payload") or {}).get("policy_release") or {})
        if release.get("candidate_source_sha256") != frozen["parent_source_sha256"]:
            raise ValueError("冻结父代源码漂移")
        accepted = atlas.source._accepted(decisions)
        for context, raw, plan in atlas.source.screen._iter_decisions(audit):
            if (context.get("game_id") not in complete or
                    (raw.get("window_key") or {}).get("phase") != "draw"):
                continue
            ranked = sorted(plan.get("candidates") or [],
                            key=lambda item: item.get("rank", 10**9))
            if not ranked:
                continue
            parent_action = ranked[0].get("action_key")
            if (not isinstance(parent_action, str) or
                    not parent_action.startswith("discard:") or
                    accepted.get(context.get("decision_id")) != parent_action):
                continue
            observation = raw.get("observation") or {}
            hand = g11._hand(observation)
            if hand is None:
                continue
            full, _, melds = hand
            parent_after = g11._after_discard(full, parent_action)
            if parent_after is None:
                raise ValueError("已接受父代弃牌不在本人手牌")
            counts["accepted_normal_draw_discards"] += 1
            if parent_after["白"] < 1:
                counts["parent_no_white_after_discard"] += 1
                if full["白"] >= 1:
                    counts["parent_discarded_last_white"] += 1
                    scopes["parent_discarded_last_white"].add(context["game_id"])
                continue
            legal_raw = (raw.get("rules") or {}).get("legal_candidates") or []
            legal = {item["action_key"]: item.get("facts") or {} for item in legal_raw}
            if len(legal) != len(legal_raw) or parent_action not in legal:
                raise ValueError("规则合法动作重复或父代缺失")
            public_counts = count_public_tiles(observation_from_json(observation))
            parent = _frontier(parent_after, melds, public_counts,
                               parent_action.split(":", 1)[1])
            parent_shape = width._shape(legal[parent_action])
            if parent["standard_natural_draws_needed_by_reserved_whites"][0] - 1 != parent_shape["standard_shanten"]:
                raise ValueError("保留零白与生产普通型向听不符")
            if (parent["seven_pair_natural_draws_needed_by_reserved_whites"] is not None
                    and parent["seven_pair_natural_draws_needed_by_reserved_whites"][0] - 1
                    != parent_shape["seven_shanten"]):
                raise ValueError("保留零白与生产七对向听不符")
            counts["parent_keeps_white"] += 1
            parent_needs = parent["standard_natural_draws_needed_by_reserved_whites"]
            if all(parent_needs[k] == parent_needs[0] + k
                   for k in range(len(parent_needs))):
                counts["parent_reserve_need_linear"] += 1
            white_stratum = str(parent["whites_held"])
            strata[white_stratum]["windows"] += 1
            key = (context["game_id"], context["round_no"], context["trigger_seq"])
            candidates = []
            for action, facts in legal.items():
                if action == parent_action or not action.startswith("discard:"):
                    continue
                after = g11._after_discard(full, action)
                if after is None or after["白"] != parent["whites_held"]:
                    continue
                shape = width._shape(facts)
                # Conventional protection is cheap; only then run full natural frontier.
                if (shape["standard_shanten"] != parent_shape["standard_shanten"] or
                        shape["combined_shanten"] != parent_shape["combined_shanten"] or
                        parent_shape["seven_shanten"] is not None and
                        (shape["seven_shanten"] is None or
                         shape["seven_shanten"] > parent_shape["seven_shanten"])):
                    continue
                if any(parent_shape[name] is None or shape[name] is None or
                       shape[name][0] < parent_shape[name][0] - 2
                       for name in ("standard", "combined")):
                    continue
                alt = _frontier(after, melds, public_counts,
                                action.split(":", 1)[1])
                if not _comparable(parent_shape, shape, parent, alt):
                    raise ValueError("候选保护筛查前后不一致")
                p_need = parent["standard_natural_draws_needed_by_reserved_whites"][-1]
                a_need = alt["standard_natural_draws_needed_by_reserved_whites"][-1]
                p_width = parent["all_whites_reserved_natural_tile_types"]
                a_width = alt["all_whites_reserved_natural_tile_types"]
                p_cap = parent["all_whites_reserved_public_capacity_upper"]
                a_cap = alt["all_whites_reserved_public_capacity_upper"]
                if a_need < p_need:
                    marker = "strictly_fewer_natural_draws"
                elif a_need == p_need and a_width > p_width and a_cap >= p_cap:
                    marker = "same_natural_need_wider_and_capacity_nondecrease"
                else:
                    continue
                candidates.append((action, marker, alt, shape))
            if not candidates:
                continue
            counts["any_natural_frontier_improvement"] += 1
            scopes["any_natural_frontier_improvement"].add(context["game_id"])
            strata[white_stratum]["any_natural_frontier_improvement"] += 1
            chosen = min(candidates, key=lambda item: (
                item[2]["standard_natural_draws_needed_by_reserved_whites"][-1],
                -item[2]["all_whites_reserved_public_capacity_upper"],
                -item[2]["all_whites_reserved_natural_tile_types"], item[0]))
            for marker in set(item[1] for item in candidates):
                counts[marker] += 1
                scopes[marker].add(context["game_id"])
                strata[white_stratum][marker] += 1
            novel = [item for item in candidates
                     if item[3]["standard"][1] <= parent_shape["standard"][1]]
            if novel:
                counts["any_natural_wider_without_conventional_type_gain"] += 1
                scopes["any_natural_wider_without_conventional_type_gain"].add(
                    context["game_id"])
                strata[white_stratum]["any_natural_wider_without_conventional_type_gain"] += 1
            novel_best = (min(novel, key=lambda item: (
                item[2]["standard_natural_draws_needed_by_reserved_whites"][-1],
                -item[2]["all_whites_reserved_public_capacity_upper"], item[0]))
                if novel else None)
            action, marker, alt, shape = chosen
            if old_g10.get(key) == action:
                counts["chosen_g10_same_action"] += 1
            if old_g11.get(key) == action:
                counts["chosen_g11_same_action"] += 1
            rows.append({"room_id": room["room_id"], "game_id": context["game_id"],
                         "round_no": context["round_no"], "seat": observation["seat"],
                         "trigger_seq": context["trigger_seq"],
                         "wall_remaining": observation.get("remaining_tile_count"),
                         "parent_action": parent_action, "alternative_action": action,
                         "chosen_marker": marker, "eligible_alternatives": len(candidates),
                         "natural_wider_without_conventional_type_gain_count": len(novel),
                         "best_natural_novel": None if novel_best is None else {
                             "action": novel_best[0], "marker": novel_best[1],
                             "frontier": novel_best[2], "shape": novel_best[3],
                             "same_action_g10": old_g10.get(key) == novel_best[0],
                             "same_action_g11": old_g11.get(key) == novel_best[0]},
                         "parent_policy_score": ranked[0].get("total_score"),
                         "alternate_policy_score": next((x.get("total_score") for x in ranked
                                                         if x.get("action_key") == action), None),
                         "parent_shape": parent_shape,
                         "alternative_shape": shape,
                         "parent_frontier": parent, "alternative_frontier": alt,
                         "same_action_g10": old_g10.get(key) == action,
                         "same_action_g11": old_g11.get(key) == action})
    if counts["accepted_normal_draw_discards"] != 55170:
        raise ValueError("G14 已接受正常弃牌母体漂移")
    OUT.mkdir(parents=True)
    rows_path = _project_file(_PROJECT_ROOT, OUT / "rows.jsonl.gz")
    with rows_path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            for row in rows:
                compressed.write((json.dumps(row, ensure_ascii=False, sort_keys=True,
                                             separators=(",", ":")) + "\n").encode("utf-8"))
    old_rows = {}
    with gzip.open(_project_file(_PROJECT_ROOT, HERE / "evidence/g14-white-reserve-frontier-20260927/rows.jsonl.gz"),
                   "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            key = (row["game_id"], row["round_no"], row["trigger_seq"])
            if key in old_rows:
                raise ValueError("G14 旧窗口身份重复")
            old_rows[key] = row
    new_rows = {(row["game_id"], row["round_no"], row["trigger_seq"]): row
                for row in rows}
    if len(new_rows) != len(rows) or len(old_rows) != old_result["rows"]:
        raise ValueError("旧新窗口身份重复或旧汇总不一致")
    overlap = set(old_rows) & set(new_rows)
    identity = {"old_windows": len(old_rows), "new_windows": len(new_rows),
                "retained": len(overlap),
                "lost": len(set(old_rows) - set(new_rows)),
                "gained": len(set(new_rows) - set(old_rows)),
                "retained_changed_action": sum(
                    old_rows[key]["alternative_action"] != new_rows[key]["alternative_action"]
                    for key in overlap)}
    result = {"schema": "g159-white-reserve-production-count/1", "outcome_blind": True,
              "prereg_sha256": _sha(PREREG), "old_result_sha256": _sha(OLD),
              "source_frozen_rooms_sha256": _sha(atlas.FROZEN),
              "parent_source_sha256": frozen["parent_source_sha256"],
              "g14_width_baseline_sha256": _sha(width.OUT),
              "analysis_script_sha256": _sha(Path(__file__)),
              "complete_official_tables": len(complete),
              "counts": dict(sorted(counts.items())),
              "scopes": {name: len(ids) for name, ids in sorted(scopes.items())},
              "strata_by_whites": {name: dict(sorted(c.items()))
                                   for name, c in sorted(strata.items())},
              "rows": len(rows), "rows_sha256": _sha(rows_path),
              "window_identity": identity,
              "boundary": "同生产分组数学的保留白板路线是诊断反事实；公开剩余上界含他家暗手；未建模对手先胡、未来摸牌顺序和最终收益。"}
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8")
    print(json.dumps({"counts": result["counts"], "scopes": result["scopes"]},
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
