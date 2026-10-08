#!/usr/bin/env python3
"""G158：原 G14 全房 Q1 用生产公开牌去重口径完整重算。"""

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
import time

import g11_cross_family_action_atlas as atlas
import g11_longitudinal_route_audit as hands
import g14_discard_width_baseline as width
import g14_latent_natural_links_probe as latent
from g14_route_support_loss_fast import route_support_fast
from hangma_bot.hangma.candidate_facts import FactsAnalysisError, _remaining
from hangma_bot.hangma.internal_types import TILE_ORDER, counts_from_tiles
from hangma_bot.hangma.public_tile_counts import count_public_tiles
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G158-FULL-ROUTE-SUPPORT-PUBLIC-COUNT-PREREG-2026-09-28.md')
OLD = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g14-route-support-full-20260927/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g158-full-route-support-public-count-20260928/result.json')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _eligible(parent: dict, alternative: dict) -> bool:
    """同普通/综合进度，七对与即时公开支持均不退。"""
    if any(parent[field] is None or alternative[field] != parent[field]
           for field in ("standard_shanten", "combined_shanten")):
        return False
    if parent["seven_shanten"] is not None and (
            alternative["seven_shanten"] is None or
            alternative["seven_shanten"] > parent["seven_shanten"]):
        return False
    for field in ("standard", "combined"):
        if parent[field] is None or alternative[field] is None:
            return False
        if (alternative[field][0] < parent[field][0] or
                alternative[field][1] < parent[field][1]):
            return False
    return True


def production_capacity(after: Counter, public_counts: tuple,
                        action: str) -> dict[str, int]:
    """按生产去重公开数及本次新弃牌计算 33 种自然牌的剩余上界。"""
    waiting = counts_from_tiles(tuple(Tile(code) for code in TILE_ORDER
                                      for _ in range(after[code])))
    new_public = {action.split(":", 1)[1]: 1}
    return {code: _remaining(code, waiting, public_counts, new_public)
            for code in TILE_ORDER[:33]}


def row_key(row: dict) -> tuple:
    """窗口唯一身份，不把强手动作或后续结算写进键。"""
    return (row["game_id"], row["round_no"], row["trigger_seq"])


def main() -> None:
    """同原 G14 筛选与排序完整重放 91 房，仅替换公开容量来源。"""
    if OUT.exists():
        raise SystemExit("G158 生产公开计数结果已存在，拒绝覆盖")
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    old_result = json.loads(OLD.read_text(encoding="utf-8"))
    if (len(frozen["rooms"]) != 91
            or old_result["schema"] != "g14-route-support-pilot/1"
            or old_result["room_limit"] != 91
            or old_result["source_frozen_rooms_sha256"] != sha(atlas.FROZEN)
            or old_result["parent_source_sha256"] != frozen["parent_source_sha256"]
            or old_result["counts"]["q1_positive_windows"] != 719):
        raise ValueError("G14 全房旧母体或正向窗数量漂移")
    selected = frozen["rooms"]
    complete = atlas._complete_ids()
    old10, old11, old28a, old28b = latent._known_old_actions()
    counts = Counter()
    scopes = defaultdict(set)
    rows = []
    selected_rooms = []
    started = time.monotonic()
    for room in selected:
        selected_rooms.append(room["room_id"])
        audit = atlas.source.ROOT / room["audit_dir"]
        decisions = audit / "participants" / atlas.source.ACTOR / "decisions.jsonl"
        if decisions.stat().st_size != room["decision_bytes"]:
            raise ValueError("父代审计字节数漂移")
        release = ((json.loads((audit / "manifest.json").read_text(encoding="utf-8"))
                    .get("payload") or {}).get("policy_release") or {})
        if release.get("candidate_source_sha256") != frozen["parent_source_sha256"]:
            raise ValueError("父代源码身份漂移")
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
            legal_raw = (raw.get("rules") or {}).get("legal_candidates") or []
            legal = {item["action_key"]: item.get("facts") or {} for item in legal_raw}
            if (len(legal) != len(legal_raw) or parent_action not in legal or
                    any(key.split(":", 1)[0] == "hu" for key in legal)):
                continue
            parsed = hands._hand(raw["observation"])
            if parsed is None:
                continue
            full, _, melds = parsed
            parent_after = hands._after_discard(full, parent_action)
            if parent_after is None or parent_after["白"] == 0:
                continue
            counts["parent_keeps_white"] += 1
            public_counts = count_public_tiles(
                observation_from_json(raw["observation"]))
            pshape = width._shape(legal[parent_action])
            try:
                parent_cap = production_capacity(parent_after, public_counts,
                                                 parent_action)
            except FactsAnalysisError:
                counts["unknown_public_parent_windows"] += 1
                continue
            parent_q = route_support_fast(parent_after, melds, parent_cap)
            if parent_q["natural_need"] not in (2, 3):
                continue
            counts["parent_gap_2_or_3"] += 1
            counts["tested_states"] += parent_q["tested_states"]
            scores = {item["action_key"]: item.get("total_score") for item in ranked}
            if type(scores.get(parent_action)) not in (int, float):
                raise ValueError("父代已接受动作评分不是数值")
            options = []
            alternative_unknown = False
            for action, facts in legal.items():
                if action == parent_action or not action.startswith("discard:"):
                    continue
                after = hands._after_discard(full, action)
                if after is None or after["白"] != parent_after["白"]:
                    continue
                if not _eligible(pshape, width._shape(facts)):
                    continue
                score = scores.get(action)
                if type(score) not in (int, float):
                    continue
                gap = float(scores[parent_action]) - float(score)
                if not 0 <= gap <= 6:
                    continue
                counts["eligible_alternatives"] += 1
                try:
                    capacity = production_capacity(after, public_counts, action)
                except FactsAnalysisError:
                    alternative_unknown = True
                    break
                q = route_support_fast(after, melds, capacity)
                if q["natural_need"] != parent_q["natural_need"]:
                    raise ValueError("同白同普通向听但全自然缺口不同")
                counts["tested_states"] += q["tested_states"]
                options.append((action, q, gap, facts))
            if alternative_unknown:
                counts["unknown_public_alternative_windows"] += 1
                continue
            if not options:
                continue
            counts["windows_with_eligible_alternative"] += 1
            best = min(options, key=lambda item: (-item[1]["q1"], item[2], item[0]))
            action, q, gap, facts = best
            if q["q1"] <= parent_q["q1"]:
                continue
            counts["q1_positive_windows"] += 1
            scopes["q1_positive_windows"].add(context["game_id"])
            route_relation = ("higher" if q["routes"] > parent_q["routes"] else
                              "equal" if q["routes"] == parent_q["routes"] else
                              "lower")
            counts["q1_positive_route_count_" + route_relation] += 1
            scopes["q1_positive_route_count_" + route_relation].add(
                context["game_id"])
            key = (context["game_id"], context["round_no"], context["trigger_seq"])
            old = {"g10": old10.get(key) == action, "g11": old11.get(key) == action,
                   "p28_observed": key in old28a,
                   "p28a": old28a.get(key) == action,
                   "p28b": old28b.get(key) == action}
            if not old["g10"] and not old["g11"]:
                counts["q1_positive_outside_g10_g11"] += 1
                scopes["q1_positive_outside_g10_g11"].add(context["game_id"])
                if route_relation == "equal":
                    counts["q1_positive_route_count_equal_outside_g10_g11"] += 1
                    scopes["q1_positive_route_count_equal_outside_g10_g11"].add(
                        context["game_id"])
            exact = (latent._support_vector(legal[parent_action],
                                            "standard_useful_tiles") ==
                     latent._support_vector(facts, "standard_useful_tiles") and
                     latent._support_vector(legal[parent_action],
                                            "useful_tiles") ==
                     latent._support_vector(facts, "useful_tiles"))
            counts["q1_positive_exact_immediate_vectors"] += exact
            rows.append({"room_id": room["room_id"], "game_id": key[0],
                         "round_no": key[1], "trigger_seq": key[2],
                         "parent_action": parent_action, "alternative_action": action,
                         "white_after": parent_after["白"],
                         "parent_q1": parent_q["q1"], "alternative_q1": q["q1"],
                         "parent_routes": parent_q["routes"],
                         "alternative_routes": q["routes"],
                         "route_count_relation": route_relation,
                         "parent_shape": pshape,
                         "alternative_shape": width._shape(facts),
                         "natural_need": q["natural_need"], "score_gap": gap,
                         "exact_immediate_vectors": exact, "old_action": old})
    old_by_key = {row_key(row): row for row in old_result["positive_rows"]}
    new_by_key = {row_key(row): row for row in rows}
    if len(old_by_key) != 719 or len(new_by_key) != len(rows):
        raise ValueError("G14 新旧正向窗口身份重复")
    old_keys, new_keys = set(old_by_key), set(new_by_key)
    strict = [row for row in rows
              if row["parent_shape"]["standard"] == row["alternative_shape"]["standard"]
              and row["parent_shape"]["combined"] == row["alternative_shape"]["combined"]
              and row["parent_routes"] == row["alternative_routes"]]
    old_strict = [row for row in old_result["positive_rows"]
                  if row["parent_shape"]["standard"] == row["alternative_shape"]["standard"]
                  and row["parent_shape"]["combined"] == row["alternative_shape"]["combined"]
                  and row["parent_routes"] == row["alternative_routes"]]
    if len(old_strict) != 9:
        raise ValueError("旧 G14 严格层 9 窗的身份漂移")
    comparison = {
        "old_positive": len(old_keys), "new_positive": len(new_keys),
        "retained_positive": len(old_keys & new_keys),
        "lost_positive": len(old_keys - new_keys),
        "newly_positive": len(new_keys - old_keys),
        "same_window_different_alternative": sum(
            old_by_key[key]["alternative_action"] != new_by_key[key]["alternative_action"]
            for key in old_keys & new_keys),
        "old_strict_summary_and_route_count": len(old_strict),
        "new_strict_summary_and_route_count": len(strict),
        "old_strict_keys_retained": len({row_key(row) for row in old_strict} &
                                        {row_key(row) for row in strict}),
        "new_strict_complete_tables": len({row["game_id"] for row in strict}),
        "new_strict_outside_g10_g11": sum(
            not row["old_action"]["g10"] and not row["old_action"]["g11"]
            for row in strict),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    result = {"schema": "g158-full-route-support-public-count/1", "outcome_blind": True,
              "source_frozen_rooms_sha256": sha(atlas.FROZEN),
              "parent_source_sha256": frozen["parent_source_sha256"],
              "route_fast_script_sha256": sha(_project_file(_PROJECT_ROOT, HERE / "g14_route_support_loss_fast.py")),
              "prereg_sha256": sha(PREREG),
              "old_result_sha256": sha(OLD),
              "script_sha256": sha(Path(__file__)), "room_limit": 91,
              "selected_rooms": selected_rooms,
              "counts": dict(sorted(counts.items())),
              "scopes": {name: len(ids) for name, ids in sorted(scopes.items())},
              "old_new_comparison": comparison,
              "elapsed_seconds": round(time.monotonic() - started, 3),
              "positive_rows": rows,
              "boundary": "冻结 91 房全合法弃牌；只替换自然牌公开剩余数为生产口径。不读未来墙或桌终成绩，Q1 不是行动收益。"}
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True,
                              indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"counts": result["counts"], "scopes": result["scopes"],
                      "old_new_comparison": comparison,
                      "elapsed_seconds": result["elapsed_seconds"]},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
