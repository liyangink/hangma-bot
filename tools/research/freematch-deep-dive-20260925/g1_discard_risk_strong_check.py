#!/usr/bin/env python3
"""四开发房强手同观察：风险消融的行为变化，仅作描述不作收益标签。"""

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

import c31_action_layer_gap as c31
import g05_parent_dev_behavior as g05
import g1_discard_risk_ablation as risk
from hangma_bot.application.audit_codec import observation_from_json
from hangma_bot.kernel.actions import WindowKey, WindowPhase
from hangma_bot.kernel.observation import CompetitionContext
from hangma_bot.policy.action_value_policy import build_scoring_view
from hangma_bot.policy.action_value_seeds import ActionValueScorer
from hangma_bot.policy.interface import DecisionRequest
from hangma_bot.policy.r18_integrated_positive_v2 import R18_INTEGRATED_POSITIVE_V2_SOURCE


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g1-discard-risk-strong-check-01')


def main() -> None:
    """按固定四房生产等价重放两源码，并逐房报纠错与新错。"""
    if OUT.exists():
        raise FileExistsError("证据目录已存在，拒绝覆盖")
    source = R18_INTEGRATED_POSITIVE_V2_SOURCE
    if source.count(risk.OLD) != 1:
        raise ValueError("候选锚点不唯一")
    parent_scorer = ActionValueScorer("g1-risk-strong-parent", source)
    candidate_scorer = ActionValueScorer(
        "g1-risk-strong-candidate", source.replace(risk.OLD, risk.NEW, 1)
    )
    counts = {}
    sources = {}
    rows = []
    for name in g05.DISCARD_DIRS:
        path = _project_file(_PROJECT_ROOT, HERE / "evidence" / name / "windows.json")
        sources[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        for row in json.loads(path.read_text(encoding="utf-8"))["windows"]:
            room = row["room_id"]
            count = counts.setdefault(room, Counter())
            count["actual_discard_windows"] += 1
            observation = observation_from_json(row["observation"])
            analysis = c31.RULES.analyze(observation, value_limits=c31.VALUE_LIMITS)
            request = DecisionRequest(
                observation=observation,
                competition=CompetitionContext(
                    tournament_id="g1-risk-official-replay", stage_no=None,
                    stage_role=None, stage_total=None, participant_rank=None,
                    ranking=(), observed_at_unix_ms=0,
                ),
                rules=analysis, decision_id="g1:" + str(row["draw_seq"]),
                trigger_seq=row["draw_seq"],
                window_key=WindowKey(
                    game_id=row["game_id"], round_no=row["round_no"],
                    trigger_seq=row["draw_seq"], phase=WindowPhase.DRAW,
                    seat=observation.seat,
                ),
                rejected_attempts=(),
            )
            view = build_scoring_view(request, value_limits=c31.VALUE_LIMITS)
            parent_result = parent_scorer.score(view)
            candidate_result = candidate_scorer.score(view)
            if parent_result.status != "SCORED" or candidate_result.status != "SCORED":
                raise ValueError("强手窗口无法受限评分")
            parent_top = risk.ranked_top(parent_result.entries).action_key
            candidate_top = risk.ranked_top(candidate_result.entries).action_key
            if parent_top != row["parent_top_action"]:
                count["parent_positive_control_mismatch"] += 1
                continue
            count["parent_positive_control_match"] += 1
            actual = row["actual_action"]
            count["parent_matches_strong"] += parent_top == actual
            count["candidate_matches_strong"] += candidate_top == actual
            if candidate_top != parent_top:
                count["changed"] += 1
                count["corrected"] += parent_top != actual and candidate_top == actual
                count["new_error"] += parent_top == actual and candidate_top != actual
                rows.append({
                    "room_id": room, "game_id": row["game_id"],
                    "round_no": row["round_no"], "draw_seq": row["draw_seq"],
                    "actual_action": actual, "parent_action": parent_top,
                    "candidate_action": candidate_top,
                })
    total = Counter()
    for count in counts.values():
        total.update(count)
    result = {
        "schema": "g1-discard-risk-strong-check/1",
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "source_sha256": sources,
        "room_counts": {room: dict(sorted(count.items())) for room, count in sorted(counts.items())},
        "total_counts": dict(sorted(total.items())),
        "outcome_labels_opened": False,
        "strong_action_is_not_value_label": True,
    }
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    (_project_file(_PROJECT_ROOT, OUT / "changed.json")).write_text(
        json.dumps({"schema": "g1-discard-risk-strong-changed/1", "windows": rows},
                   ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result["total_counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
