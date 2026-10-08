#!/usr/bin/env python3
"""G189：官方父代高白板摸打的无白自然进张逐码对账。"""

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

from hangma_bot.application.audit_codec import (
    candidate_facts_from_json, observation_from_json,
)
from hangma_bot.hangma import hand_analysis, public_tile_counts
from hangma_bot.hangma.engine import _build_context

import c31_action_layer_gap as c31
import g11_cross_family_action_atlas as atlas
import g178_natural_vs_standard_support as g178


HERE = Path(__file__).resolve().parent
PLAN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G189-HIGH-WHITE-NATURAL-SUPPORT-PREREG-2026-09-29.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g189-high-white-natural-support-20260929/result.json')


def sha(path: Path) -> str:
    """绑定公开来源、研究口径及生产数学的原始字节。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _before(raw: dict) -> tuple:
    """恢复行动前玩家观察与本人暗手；不读取赛后完整世界。"""

    observation = observation_from_json(raw["observation"])
    if observation.phase != "draw":
        raise ValueError("G189 来源不是正常摸打窗口")
    full = _build_context(observation).full_hand()
    return observation, full


def _one(raw: dict, room_id: str, game_id: str, round_no: int,
         trigger_seq: int, parent: str) -> dict | None:
    """高白板窗逐合法非白弃牌比较；低白板窗不进入分析。"""

    observation, full = _before(raw)
    whites = sum(tile.code == "白" for tile in full)
    if whites < 2:
        return None
    if whites > 4:
        raise ValueError("本人手留白板超过物理四张")
    meld_count = len(observation.melds[observation.seat])
    unseen = public_tile_counts.count_unseen_tiles(observation)
    if any(value is None for value in unseen[:33]):
        raise ValueError("自然进张所需的公开未知容量不完整")
    old = (raw.get("rules") or {}).get("legal_candidates") or []
    by_key = {candidate["action_key"]: candidate for candidate in old}
    if len(old) != len(by_key) or parent not in by_key:
        raise ValueError("冻结父代首选或合法动作身份不符")
    actions = []
    for key, item in sorted(by_key.items()):
        if not key.startswith("discard:") or key == "discard:白":
            continue
        facts = candidate_facts_from_json(item["facts"])
        root = g178._drop(full, key.split(":", 1)[1])
        need, natural = g178.natural(root, unseen, meld_count)
        production = g178.production(facts)
        natural_only = {code: amount for code, amount in natural.items()
                        if code not in production}
        production_only = {code: amount for code, amount in production.items()
                           if code not in natural}
        changed = {code: [natural[code], production[code]]
                   for code in natural.keys() & production.keys()
                   if natural[code] != production[code]}
        actions.append({
            "action_key": key, "natural_need": need,
            "standard_shanten_after": facts.standard_shanten_after,
            "natural_types": len(natural), "natural_capacity": sum(natural.values()),
            "production_types": len(production),
            "production_capacity": sum(production.values()),
            "natural_only": natural_only, "production_only": production_only,
            "capacity_mismatch": changed,
            "equal_vector": natural == production,
        })
    if not actions:
        raise ValueError("高白板正常摸打没有合法非白弃牌")
    natural_best = min(actions, key=lambda row: (
        -row["natural_types"], -row["natural_capacity"], row["action_key"]))
    production_best = min(actions, key=lambda row: (
        -row["production_types"], -row["production_capacity"], row["action_key"]))
    mismatches = [action for action in actions if not action["equal_vector"]]
    if mismatches:
        # 只有错位窗才重新调用当前规则，以区分旧审计字段与当前生产数学。
        current = c31.RULES.analyze(observation, value_limits=c31.VALUE_LIMITS)
        current_by_key = {candidate.action_key: candidate
                          for candidate in current.legal_candidates}
        if set(current_by_key) != set(by_key):
            raise ValueError("当前规则合法动作与冻结父代窗口不同")
        for action in mismatches:
            key = action["action_key"]
            facts = current_by_key[key].facts
            if (facts is None
                    or g178.production(facts)
                    != g178.production(candidate_facts_from_json(by_key[key]["facts"]))):
                raise ValueError("当前生产普通进张与冻结审计不同")
    return {
        "room_id": room_id, "game_id": game_id, "round_no": round_no,
        "trigger_seq": trigger_seq, "seat": observation.seat,
        "white_held": whites, "own_meld_count": meld_count,
        "parent_action": parent, "parent_discards_white": parent == "discard:白",
        "legal_nonwhite_discards": len(actions),
        "mismatch_actions": len(mismatches),
        "natural_best": natural_best["action_key"],
        "production_best": production_best["action_key"],
        "natural_best_differs": natural_best["action_key"] != production_best["action_key"],
        "parent_facts_mismatch": any(action["action_key"] == parent
                                     for action in mismatches),
        "natural_need_min": min(action["natural_need"] for action in actions),
        "natural_need_max": max(action["natural_need"] for action in actions),
        "mismatches": mismatches,
    }


def main() -> None:
    """只读完整官方父代桌，结果一次写入且不覆盖。"""

    if OUT.exists():
        raise FileExistsError("G189 结果已存在，拒绝覆盖")
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    complete_ids = atlas._complete_ids()
    if len(frozen["rooms"]) != 91 or len(complete_ids) != 909:
        raise ValueError("冻结房或完整八局桌来源漂移")
    counts = Counter()
    layers: dict[str, Counter] = defaultdict(Counter)
    mismatch_rows = []
    unavailable_rows = []
    seen = set()
    for room in frozen["rooms"]:
        audit = atlas.source.ROOT / room["audit_dir"]
        decision_file = audit / "participants" / atlas.source.ACTOR / "decisions.jsonl"
        if decision_file.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结官方父代决策文件长度漂移")
        release = ((json.loads((audit / "manifest.json").read_text(encoding="utf-8"))
                    .get("payload") or {}).get("policy_release") or {})
        if release.get("candidate_source_sha256") != frozen["parent_source_sha256"]:
            raise ValueError("冻结 R18 v2 发布源码摘要漂移")
        accepted = atlas.source._accepted(decision_file)
        for context, raw, plan in atlas.source.screen._iter_decisions(audit):
            game_id = context.get("game_id")
            if game_id not in complete_ids:
                continue
            if (raw.get("window_key") or {}).get("phase") != "draw":
                continue
            counts["all_complete_table_draw_windows"] += 1
            ranked = sorted(plan.get("candidates") or [],
                            key=lambda item: item.get("rank", 10**9))
            if not ranked:
                counts["unranked"] += 1
                continue
            parent = ranked[0].get("action_key")
            if accepted.get(context.get("decision_id")) != parent:
                counts["parent_not_confirmed"] += 1
                continue
            key = (game_id, context.get("round_no"), context.get("trigger_seq"),
                   context.get("seat"))
            if key in seen:
                raise ValueError("完整桌同一已确认正常摸打窗口重复")
            seen.add(key)
            counts["accepted_parent_draw_windows"] += 1
            try:
                row = _one(raw, room["room_id"], game_id,
                           context["round_no"], context["trigger_seq"], parent)
            except (ValueError, TypeError, KeyError) as exc:
                # 失败单列，不把数学未知或规则矛盾算成相等；来源身份异常上方已失败。
                counts["unavailable_or_inconsistent"] += 1
                unavailable_rows.append({"room_id": room["room_id"], "game_id": game_id,
                                         "round_no": context["round_no"],
                                         "trigger_seq": context["trigger_seq"],
                                         "reason": type(exc).__name__ + ": " + str(exc)[:200]})
                continue
            if row is None:
                continue
            counts["high_white_windows"] += 1
            layer = f"white{row['white_held']}/" + (
                "meld" if row["own_meld_count"] else "closed") + "/" + (
                "parent_white" if row["parent_discards_white"] else "parent_other")
            layer_counts = layers[layer]
            layer_counts["windows"] += 1
            layer_counts["actions"] += row["legal_nonwhite_discards"]
            layer_counts["mismatch_actions"] += row["mismatch_actions"]
            layer_counts["mismatch_windows"] += bool(row["mismatch_actions"])
            layer_counts["best_differs"] += row["natural_best_differs"]
            layer_counts["parent_facts_mismatch"] += row["parent_facts_mismatch"]
            layer_counts["need_min_ge_3"] += row["natural_need_min"] >= 3
            if row["mismatch_actions"]:
                mismatch_rows.append(row)
    result = {
        "schema": "g189-high-white-natural-support/1",
        "source_sha256": {name: sha(path) for name, path in {
            "prereg": PLAN, "script": Path(__file__),
            "frozen_rooms": atlas.FROZEN,
            "g178_math_audit": Path(g178.__file__),
            "hand_math": Path(hand_analysis.__file__),
            "public_counts": Path(public_tile_counts.__file__),
        }.items()},
        "parent_source_sha256": frozen["parent_source_sha256"],
        "complete_tables": len(complete_ids),
        "counts": dict(sorted(counts.items())),
        "layers": {key: dict(sorted(value.items()))
                   for key, value in sorted(layers.items())},
        "mismatch_rows": mismatch_rows,
        "unavailable_rows": unavailable_rows,
        "boundary": "无白自然缺口一步进展是行动前诊断，不是下一摸牌墙概率、白板机会价值或候选收益。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False,
                              sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items()
                      if key not in ("mismatch_rows", "unavailable_rows")},
                     ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
