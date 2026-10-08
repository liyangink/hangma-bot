#!/usr/bin/env python3
"""结果盲核对合法胡/弃白续飘窗口及父代实际动作，筛查 GLM 提议的新增入口。"""

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
import g8_two_white_next_draw_census as g8
from hangma_bot.hangma.hand_analysis import any_tile_win
from hangma_bot.kernel.actions import Tile


HERE = Path(__file__).resolve().parent
FROZEN = atlas.FROZEN
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g12-baotou-piao-entry-census-20260927/result.json')


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """只读父代当前可见手牌、合法弃白和计划/官方已确认动作。"""

    if OUT.exists():
        raise SystemExit("G12 财飘入口普查已存在，拒绝覆盖")
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    complete_ids = atlas._complete_ids()
    counts = Counter()
    scopes = defaultdict(set)
    rows = []
    for room in frozen["rooms"]:
        audit = atlas.source.ROOT / room["audit_dir"]
        path = audit / "participants" / atlas.source.ACTOR / "decisions.jsonl"
        if path.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结房决策文件大小漂移")
        release = ((json.loads((audit / "manifest.json").read_text(encoding="utf-8"))
                    .get("payload") or {}).get("policy_release") or {})
        if release.get("candidate_source_sha256") != frozen["parent_source_sha256"]:
            raise ValueError("冻结房父代源码摘要漂移")
        accepted = atlas.source._accepted(path)
        for context, raw, plan in atlas.source.screen._iter_decisions(audit):
            if context.get("game_id") not in complete_ids:
                continue
            if (raw.get("window_key") or {}).get("phase") != "draw":
                continue
            ranked = sorted(plan.get("candidates") or [],
                            key=lambda item: item.get("rank", 10**9))
            if not ranked:
                continue
            parent_key = ranked[0].get("action_key")
            if accepted.get(context.get("decision_id")) != parent_key:
                continue
            legal_items = {item.get("action_key"): item
                           for item in (raw.get("rules") or {}).get("legal_candidates") or []}
            if len(legal_items) != len((raw.get("rules") or {}).get("legal_candidates") or []):
                raise ValueError("规则合法动作键重复")
            legal = {key: item.get("facts") or {} for key, item in legal_items.items()}
            if "hu" not in legal:
                continue
            if parent_key not in legal:
                raise ValueError("父代已提交动作不在规则合法候选")
            counts["legal_hu_accepted_parent_action"] += 1
            if parent_key == "hu":
                counts["accepted_parent_hu"] += 1
            observation = raw["observation"]
            try:
                hand, own_melds = g8._complete_hand(observation)
            except ValueError:
                counts["hu_hand_not_reconstructed"] += 1
                continue
            whites = hand.count("白")
            if whites < 2:
                continue
            counts["legal_hu_with_two_plus_white"] += 1
            if parent_key == "hu":
                counts["hu_with_two_plus_white"] += 1
            already_baotou = (observation.get("rule_state") or {}).get("baotou") is True
            if already_baotou and parent_key == "hu":
                counts["hu_two_plus_white_already_baotou"] += 1
            discard_white = legal.get("discard:白")
            if discard_white is None:
                continue
            counts["legal_hu_two_plus_white_legal_discard_white"] += 1
            if parent_key == "hu":
                counts["hu_two_plus_white_legal_discard_white"] += 1
                if already_baotou:
                    counts["hu_two_plus_white_already_baotou_legal_discard_white"] += 1
            after = hand.copy()
            after.remove("白")
            rule_baotou = discard_white.get("baotou_after")
            actual_baotou = any_tile_win(tuple(Tile(code) for code in after), own_melds)
            if rule_baotou != actual_baotou:
                raise ValueError("弃白后任意听与规则候选事实不一致")
            if not rule_baotou:
                continue
            counts["legal_hu_two_plus_white_discard_white_keeps_baotou"] += 1
            scopes["all_keeps_baotou"].add(context["game_id"])
            counts["keeps_baotou_parent_" + parent_key] += 1
            if parent_key == "hu":
                counts["hu_two_plus_white_discard_white_keeps_baotou"] += 1
                scopes["parent_hu_keeps_baotou"].add(context["game_id"])
            if already_baotou:
                counts["already_baotou_keeps_baotou"] += 1
                scopes["already_baotou_keeps_baotou"].add(context["game_id"])
            # 胡与弃白的当前评分差只用于判断父代是否已覆盖，不是收益标签。
            scores = {item["action_key"]: item.get("total_score") for item in ranked}
            hu_settlement = ((legal_items["hu"].get("value_facts") or {})
                             .get("immediate_settlement") or {})
            row = {"room_id": room["room_id"], "game_id": context["game_id"],
                   "round_no": context["round_no"], "seat": observation.get("seat"),
                   "trigger_seq": context["trigger_seq"], "parent_action": parent_key,
                   "white_count": whites, "own_melds": own_melds,
                   "already_baotou": already_baotou,
                   "rule_chain_count": (observation.get("rule_state") or {}).get("chain_count"),
                   "wall_remaining": observation.get("remaining_tile_count"),
                   "hu_fan": hu_settlement.get("fan"),
                   "hu_score": scores.get("hu"),
                   "discard_white_score": scores.get("discard:白")}
            rows.append(row)
    result = {"schema": "g12-baotou-piao-entry-census/3", "outcome_blind": True,
              "frozen_rooms_sha256": _sha(FROZEN),
              "parent_source_sha256": frozen["parent_source_sha256"],
              "complete_official_tables": len(complete_ids),
              "counts": dict(sorted(counts.items())),
              "scopes": {name: {"complete_tables": len(ids),
                                "conditional_gain_for_plus2_all_tables":
                                    2 * len(complete_ids) / len(ids)}
                         for name, ids in sorted(scopes.items())},
              "rows": rows,
              "boundary": "只读父代已确认动作的合法胡/弃白窗口及规则后态；不使用未来牌墙/他家暗手/终局，不把倍率当期望收益。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "rows"},
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
