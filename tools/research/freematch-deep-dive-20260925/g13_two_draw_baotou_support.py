#!/usr/bin/env python3
"""G13 近留白路线：结果盲枚举下一摸牌码与再弃牌的静态爆头支持面。"""

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
import hashlib
import json
from pathlib import Path

import g11_cross_family_action_atlas as atlas
import g11_longitudinal_route_audit as g11
import g12_reserved_white_route_audit as g12
from hangma_bot.hangma.hand_analysis import any_tile_win
from hangma_bot.kernel.actions import CANONICAL_TILE_ORDER, Tile


HERE = Path(__file__).resolve().parent
CONTINUATION = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g13-near-white-continuation-20260927/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g13-two-draw-baotou-support-20260927/result.json')


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@lru_cache(maxsize=100_000)
def _any_tile_win(codes: tuple[str, ...], meld_count: int) -> bool:
    """只缓存生产规则的静态任意听结果，不自创胡牌判定。"""

    return any_tile_win(tuple(Tile(code) for code in codes), meld_count)


def _public_counts(observation: dict) -> tuple[Counter, Counter]:
    """公开弃牌与副露按牌码分别计数；重叠处采用较大者作可见下界。"""

    discards = Counter()
    for pile in observation.get("discards") or []:
        discards.update(pile)
    exposed = Counter()
    for seat_melds in observation.get("melds") or []:
        for meld in seat_melds:
            exposed.update(meld.get("tiles") or [])
    return discards, exposed


def _support(full: Counter, *, meld_count: int, first_action: str,
             discards: Counter, exposed: Counter) -> dict:
    """枚举首弃、下一摸及再弃的静态见证；公开剩余张数仅作上界。"""

    after_first = g11._after_discard(full, first_action)
    if after_first is None:
        raise ValueError("首弃不在本人当前手牌")
    discard_code = first_action.split(":", 1)[1]
    visible_discards = discards.copy()
    visible_discards[discard_code] += 1
    support = []
    for drawn in CANONICAL_TILE_ORDER:
        remaining_upper = (4 - after_first[drawn]
                           - max(visible_discards[drawn], exposed[drawn]))
        if remaining_upper < 0 or remaining_upper > 4:
            raise ValueError("公开可见计数与本人牌超过四张物理上限")
        if remaining_upper == 0:
            continue
        next_full = after_first.copy()
        next_full[drawn] += 1
        any_witnesses = []
        reserve_witnesses = []
        for second_discard in sorted(next_full):
            after_second = g11._after_discard(next_full, "discard:" + second_discard)
            if after_second is None or after_second["白"] < 1:
                continue
            codes = tuple(sorted(code for code, amount in after_second.items()
                                 for _ in range(amount)))
            if not _any_tile_win(codes, meld_count):
                continue
            any_witnesses.append("discard:" + second_discard)
            if g12._reserved_white_need(after_second, meld_count) == 0:
                reserve_witnesses.append("discard:" + second_discard)
        if any_witnesses:
            support.append({"drawn_tile": drawn,
                            "public_remaining_upper": remaining_upper,
                            "second_discard_witnesses": any_witnesses,
                            "reserved_standard_witnesses": reserve_witnesses})
    reserve = [item for item in support if item["reserved_standard_witnesses"]]
    return {"after_first_white_count": after_first["白"],
            "any_baotou_tile_types": len(support),
            "any_baotou_public_capacity_upper": sum(
                item["public_remaining_upper"] for item in support),
            "reserved_standard_tile_types": len(reserve),
            "reserved_standard_public_capacity_upper": sum(
                item["public_remaining_upper"] for item in reserve),
            "support": support}


def main() -> None:
    """仅在冻结 57 个非 G10 近留白窗读取动作前公开事实，绝不使用后续结果。"""

    if OUT.exists():
        raise SystemExit("G13 两次摸打支持面已存在，拒绝覆盖")
    continuation = json.loads(CONTINUATION.read_text(encoding="utf-8"))
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    if (continuation.get("outcome_blind") is not True
            or continuation.get("frozen_rooms_sha256") != _sha(atlas.FROZEN)
            or continuation.get("parent_source_sha256") != frozen["parent_source_sha256"]):
        raise ValueError("结果盲父代输入身份不符")
    targets = {(row["game_id"], row["round_no"], row["trigger_seq"]): row
               for row in continuation["records"]}
    if len(targets) != len(continuation["records"]):
        raise ValueError("待审动作窗重复")
    by_room = defaultdict(set)
    for key, row in targets.items():
        by_room[row["room_id"]].add(key)
    rows = []
    counts = Counter()
    scopes = defaultdict(set)
    for room in frozen["rooms"]:
        if room["room_id"] not in by_room:
            continue
        audit = atlas.source.ROOT / room["audit_dir"]
        file = audit / "participants" / atlas.source.ACTOR / "decisions.jsonl"
        if file.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结房决策字节数漂移")
        release = ((json.loads((audit / "manifest.json").read_text(encoding="utf-8"))
                    .get("payload") or {}).get("policy_release") or {})
        if release.get("candidate_source_sha256") != frozen["parent_source_sha256"]:
            raise ValueError("冻结房父代源码摘要漂移")
        accepted = atlas.source._accepted(file)
        for context, raw, plan in atlas.source.screen._iter_decisions(audit):
            key = (context.get("game_id"), context.get("round_no"),
                   context.get("trigger_seq"))
            target = targets.get(key)
            if target is None:
                continue
            ranked = sorted(plan.get("candidates") or [],
                            key=lambda item: item.get("rank", 10**9))
            if (not ranked or ranked[0].get("action_key") != target["parent_action"]
                    or accepted.get(context.get("decision_id")) != target["parent_action"]
                    or (raw.get("window_key") or {}).get("phase") != "draw"):
                raise ValueError("冻结父代目标动作未被明确接受")
            observation = raw["observation"]
            parsed = g11._hand(observation)
            if parsed is None:
                raise ValueError("目标本人摸后手牌无法复原")
            full, _, own_melds = parsed
            if full["白"] != target["white_count"] or observation["seat"] != target["seat"]:
                raise ValueError("目标本人座位或白板数漂移")
            discards, exposed = _public_counts(observation)
            parent = _support(full, meld_count=own_melds,
                              first_action=target["parent_action"],
                              discards=discards, exposed=exposed)
            alternate = _support(full, meld_count=own_melds,
                                 first_action=target["alternate"]["action"],
                                 discards=discards, exposed=exposed)
            if parent["after_first_white_count"] != alternate["after_first_white_count"]:
                raise ValueError("改选改变首弃后的白板数，与 G12 入口不符")
            counts["compared_windows"] += 1
            scopes["all"].add(target["game_id"])
            if alternate["any_baotou_tile_types"] > parent["any_baotou_tile_types"]:
                counts["alternate_more_baotou_tile_types"] += 1
                scopes["more_types"].add(target["game_id"])
            if (alternate["any_baotou_public_capacity_upper"]
                    > parent["any_baotou_public_capacity_upper"]):
                counts["alternate_more_baotou_public_capacity_upper"] += 1
                scopes["more_capacity_upper"].add(target["game_id"])
            if (alternate["reserved_standard_public_capacity_upper"]
                    > parent["reserved_standard_public_capacity_upper"]):
                counts["alternate_more_reserved_capacity_upper"] += 1
                scopes["more_reserved_capacity_upper"].add(target["game_id"])
            rows.append({"room_id": room["room_id"], "game_id": key[0],
                         "round_no": key[1], "trigger_seq": key[2],
                         "seat": observation["seat"],
                         "white_count": target["white_count"],
                         "wall_remaining": target["wall_remaining"],
                         "parent_action": target["parent_action"],
                         "alternate_action": target["alternate"]["action"],
                         "parent_score_gap": target["alternate"]["parent_score_gap"],
                         "parent": parent, "alternate": alternate})
    if len(rows) != len(targets):
        raise ValueError("冻结目标窗口未全部找到")
    result = {"schema": "g13-two-draw-baotou-support/1", "outcome_blind": True,
              "frozen_rooms_sha256": _sha(atlas.FROZEN),
              "continuation_sha256": _sha(CONTINUATION),
              "parent_source_sha256": frozen["parent_source_sha256"],
              "complete_official_tables": continuation["complete_official_tables"],
              "counts": dict(sorted(counts.items())),
              "scopes": {name: {"complete_tables": len(ids),
                                "conditional_gain_for_plus2_all_tables":
                                    2 * continuation["complete_official_tables"] / len(ids)}
                         for name, ids in sorted(scopes.items())},
              "rows": rows,
              "boundary": "同窗公开未见计数是未来自摸张数上界（含他家暗手/保留牌）；第二弃只检验静态牌型、不验对手响应与抓打圈合法性，不能当作摸牌概率、净积分或完整桌反事实。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "rows"},
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
