#!/usr/bin/env python3
"""结果盲复算 G11 风险/牌效受限候选在冻结 R18 v2 官方轨迹上的改选。"""

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
from hangma_bot.application.audit_codec import decision_request_from_json
from hangma_bot.policy.action_value_policy import build_scoring_view
from hangma_bot.policy.action_value_seeds import ActionValueScorer


HERE = Path(__file__).resolve().parent
AUDIT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g11-longitudinal-route-audit-20260927/result.json')
CANDIDATE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/candidates/G11-SHAPE-RISK-PARETO-V1.py')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g11-shape-risk-behavior-20260927/result.json')


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """只测同窗合法行为；不读取终局分数、未来牌墙或他家暗手。"""

    if OUT.exists():
        raise SystemExit("G11 行为屏证据已存在，拒绝覆盖")
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    audit_result = json.loads(AUDIT.read_text(encoding="utf-8"))
    complete_ids = atlas._complete_ids()
    if audit_result["frozen_rooms_sha256"] != _sha(atlas.FROZEN):
        raise ValueError("G11 审计输入冻结文件漂移")
    scorer = ActionValueScorer("g11-shape-risk-pareto-v1", CANDIDATE.read_text(encoding="utf-8"))
    target_keys = {(row["game_id"], row["round_no"], row["trigger_seq"])
                   for row in audit_result["width_rows"]}
    counts = Counter()
    changed = []
    for room in frozen["rooms"]:
        base = atlas.source.ROOT / room["audit_dir"]
        decision_file = base / "participants" / atlas.source.ACTOR / "decisions.jsonl"
        if decision_file.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结决策文件大小漂移")
        accepted = atlas.source._accepted(decision_file)
        for context, raw, plan in atlas.source.screen._iter_decisions(base):
            if context.get("game_id") not in complete_ids:
                continue
            if (raw.get("window_key") or {}).get("phase") != "draw":
                continue
            ranked = sorted(plan.get("candidates") or [],
                            key=lambda item: item.get("rank", 10**9))
            if not ranked or not isinstance(ranked[0].get("action_key"), str):
                continue
            parent = ranked[0]["action_key"]
            if not parent.startswith("discard:") or accepted.get(context.get("decision_id")) != parent:
                continue
            counts["accepted_parent_draw_discards"] += 1
            request = decision_request_from_json(raw)
            view = build_scoring_view(request)
            scored = scorer.score(view)
            if scored.status != "SCORED" or not scored.entries:
                raise ValueError("候选在父代已接受窗口未能评分")
            best = min(scored.entries, key=lambda item: (-item.score, item.action_key))
            if best.action_key == parent:
                continue
            if best.action_key != "discard:" + raw["observation"]["drawn_tile"]:
                raise ValueError("候选出现非预定摸切改选")
            legal = {item["action_key"] for item in (raw.get("rules") or {}).get("legal_candidates") or []}
            if best.action_key not in legal:
                raise ValueError("候选改选不是规则合法动作")
            key = (context["game_id"], context["round_no"], context["trigger_seq"])
            counts["changed_windows"] += 1
            if key in target_keys:
                counts["longitudinal_audit_overlap"] += 1
            changed.append({"room_id": room["room_id"], "game_id": key[0],
                            "round_no": key[1], "trigger_seq": key[2],
                            "seat": raw["observation"]["seat"],
                            "parent_action": parent, "candidate_action": best.action_key,
                            "white_count": (raw["observation"].get("my_hand") or []).count("白"),
                            "longitudinal_audit_overlap": key in target_keys})
    result = {"schema": "g11-shape-risk-behavior/1", "outcome_blind": True,
              "parent_source_sha256": frozen["parent_source_sha256"],
              "candidate_source_sha256": _sha(CANDIDATE),
              "frozen_rooms_sha256": _sha(atlas.FROZEN),
              "longitudinal_audit_sha256": _sha(AUDIT),
              "complete_official_tables": len(complete_ids),
              "counts": dict(sorted(counts.items())),
              "changed_complete_tables": len({row["game_id"] for row in changed}),
              "changed_rooms": len({row["room_id"] for row in changed}),
              "changed": changed,
              "boundary": "冻结官方父代轨迹的结果盲候选重判；改选覆盖不是完整策略收益。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "changed"},
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
