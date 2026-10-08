#!/usr/bin/env python3
"""结果盲盘点 R18 v2 在合法胡窗口主动继续追爆头的覆盖范围。"""

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

import g8_public_response_training_rows as source
import g8_public_response_train_model as fit


HERE = Path(__file__).resolve().parent
FROZEN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g8-two-white-next-draw-20260927/frozen_rooms.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g9-hu-deferral-scope-20260927/result.json')


def main() -> None:
    """按房与完整桌 ID 去重，只读取动作前请求和父代评分。"""
    if OUT.exists():
        raise SystemExit("G9 弃胡范围审计已冻结，拒绝覆盖")
    frozen_bytes = FROZEN.read_bytes()
    frozen = json.loads(frozen_bytes)
    source_meta = json.loads(fit.RESULT.read_text(encoding="utf-8"))
    official_tables = source_meta["counts"]["official_games"]
    missing_official_games = set(source_meta["missing_official_games_excluded"])
    totals = Counter()
    by_room = {}
    games = defaultdict(set)
    deferral_windows = []
    for room in frozen["rooms"]:
        audit = source.ROOT / room["audit_dir"]
        decision_file = audit / "participants" / source.ACTOR / "decisions.jsonl"
        if decision_file.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结房决策审计漂移")
        accepted = source._accepted(decision_file)
        release = ((json.loads((audit / "manifest.json").read_text(encoding="utf-8"))
                    .get("payload") or {}).get("policy_release") or {})
        if release.get("candidate_source_sha256") != frozen["parent_source_sha256"]:
            raise ValueError("冻结 R18 v2 源码身份漂移")
        counts = Counter()
        seen = set()
        for context, request, plan in source.screen._iter_decisions(audit):
            window = request.get("window_key") or {}
            if window.get("phase") != "draw":
                continue
            key = (context["game_id"], context["round_no"], context["trigger_seq"])
            if key in seen:
                raise ValueError("同一动作窗口重复，不能计作新机会")
            seen.add(key)
            legal = (request.get("rules") or {}).get("legal_candidates") or []
            if not any(item.get("action_key") == "hu" for item in legal):
                continue
            ranked = sorted(plan.get("candidates") or [], key=lambda row: row.get("rank", 10**9))
            if not ranked:
                raise ValueError("合法胡窗口缺父代评分计划")
            top = ranked[0]
            detail = (top.get("score_trace") or {}).get("detail") or {}
            cf = detail.get("hu_vs_nonwealth_baotou_cf") or {}
            if cf.get("triggered") is True:
                if top.get("action_key") != cf.get("target_action") or not str(top.get("action_key")).startswith("discard:"):
                    raise ValueError("爆头弃胡覆盖触发与首选动作不一致")
                category = "nonwealth_baotou_deferral"
                accepted_action = accepted.get(context["decision_id"])
                counts["deferral_accepted_as_planned"] += accepted_action == top["action_key"]
                counts["deferral_not_accepted_as_planned"] += accepted_action != top["action_key"]
                deferral_windows.append({"room_id": room["room_id"], "game_id": key[0],
                                         "round_no": key[1], "discard_seq": key[2] + 1,
                                         "parent_action": top["action_key"],
                                         "accepted_as_planned": accepted_action == top["action_key"]})
                support = cf.get("support_remaining")
                if type(support) not in (int, float):
                    raise ValueError("触发覆盖缺有效张容量")
                counts["deferral_support_le40"] += support <= 40
                wall = request["observation"].get("remaining_tile_count")
                counts["deferral_wall_le40"] += type(wall) is int and wall <= 40
            elif top.get("action_key") == "hu":
                category = "accept_hu"
            else:
                category = "other_deferral"
            counts["hu_legal"] += 1
            counts[category] += 1
            games[category].add(key[0])
            observation = request["observation"]
            wealth = (observation.get("rule_state") or {}).get("wealth_god")
            if isinstance(wealth, str):
                hand = observation.get("my_hand") or []
                count = hand.count(wealth) + int(observation.get("drawn_tile") == wealth)
                counts[f"{category}_wealth_{count}"] += 1
        by_room[room["room_id"]] = dict(sorted(counts.items()))
        totals.update(counts)
    scopes = {kind: {"action_windows": totals[kind], "parent_trace_game_ids": len(ids),
                     "official_complete_table_ids": len(ids - missing_official_games),
                     "required_net_gain_per_affected_table_for_plus2_overall":
                         2.0 * official_tables / len(ids - missing_official_games)}
              for kind, ids in games.items()}
    result = {
        "schema": "g9-hu-deferral-scope/1",
        "source_rooms": len(by_room),
        "source_official_complete_tables": official_tables,
        "source_missing_official_games_excluded": sorted(missing_official_games),
        "source_frozen_rooms_sha256": hashlib.sha256(frozen_bytes).hexdigest(),
        "source_parent_sha256": frozen["parent_source_sha256"],
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "outcome_blind": True,
        "totals": dict(sorted(totals.items())),
        "scopes": scopes,
        "by_room": by_room,
        "deferral_windows": deferral_windows,
        "boundary": "只量化父代自然轨迹的覆盖；算术量级不是收益预测、因果上界或策略准入",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items()
                      if key not in ("by_room", "deferral_windows")},
                     ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
