#!/usr/bin/env python3
"""四间开发房同观察上的冻结 R18 v2 行为基线；只读动作，不用结算训练。"""

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

import g05_strong_draw_reconstruction as g05
import c31_action_layer_gap as c31
from hangma_bot.application.audit_codec import observation_from_json
from hangma_bot.kernel.actions import WindowKey, WindowPhase
from hangma_bot.kernel.observation import CompetitionContext
from hangma_bot.policy.action_value_policy import build_scoring_view
from hangma_bot.policy.action_value_seeds import ActionValueScorer
from hangma_bot.policy.interface import DecisionRequest


HERE = Path(__file__).resolve().parent
EVIDENCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g05-parent-dev-behavior-01')
DISCARD_DIRS = (
    "g05-strong-draw-feasibility-10games-01",
    "g05-strong-draw-replication-01",
    "g05-strong-draw-devroom-03",
    "g05-strong-draw-devroom-04",
)
HIGH_VALUE_DIRS = (
    "g05-draw-hu-gang-01",
    "g05-draw-hu-gang-devrooms-03-04",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def family(key: str) -> str:
    return key.split(":", 1)[0]


def score_high_value(row: dict, scorer: ActionValueScorer) -> tuple[str, float]:
    """与普通摸打重建器相同的中性赛事上下文，只比较同观察首选。"""
    observation = observation_from_json(row["observation"])
    rules = c31.RULES.analyze(observation, value_limits=c31.VALUE_LIMITS)
    request = DecisionRequest(
        observation=observation,
        competition=CompetitionContext(
            tournament_id="g05-official-replay", stage_no=None,
            stage_role=None, stage_total=None, participant_rank=None,
            ranking=(), observed_at_unix_ms=0,
        ),
        rules=rules, decision_id="g05:" + str(row["draw_seq"]),
        trigger_seq=row["draw_seq"],
        window_key=WindowKey(
            game_id=row["game_id"], round_no=row["round_no"],
            trigger_seq=row["draw_seq"], phase=WindowPhase.DRAW,
            seat=observation.seat,
        ),
        rejected_attempts=(),
    )
    scored = scorer.score(build_scoring_view(request, value_limits=c31.VALUE_LIMITS))
    if scored.status != "SCORED" or not scored.entries:
        raise ValueError("父代未能评分：" + scored.status + ":" + str(scored.reason))
    ordered = sorted(scored.entries, key=lambda item: (-item.score, item.action_key))
    actual = row["actual_action"]
    chosen = next((item for item in ordered if item.action_key == actual), None)
    if chosen is None:
        raise ValueError("真实合法动作没有父代分值：" + actual)
    return ordered[0].action_key, ordered[0].score - chosen.score


def main() -> None:
    """按房/动作族给出描述性混淆矩阵，拒绝覆盖及来源混淆。"""
    if OUT.exists():
        raise FileExistsError("行为基线目录已存在，拒绝覆盖")
    scorer = ActionValueScorer("g05-parent-dev", c31.R18_INTEGRATED_POSITIVE_V2_SOURCE)
    sources = {}
    rows = []
    for name in DISCARD_DIRS + HIGH_VALUE_DIRS:
        path = _project_file(_PROJECT_ROOT, EVIDENCE / name / "windows.json")
        sources[name] = digest(path)
        dataset = json.loads(path.read_text(encoding="utf-8"))["windows"]
        for row in dataset:
            actual = row["actual_action"]
            if name in DISCARD_DIRS:
                parent = row["parent_top_action"]
                gap = row["parent_score_gap_top_minus_actual"]
            else:
                parent, gap = score_high_value(row, scorer)
            rows.append({
                "room_id": row["room_id"], "game_id": row["game_id"],
                "round_no": row["round_no"], "draw_seq": row["draw_seq"],
                "actual_action": actual, "actual_family": family(actual),
                "parent_top_action": parent, "parent_family": family(parent),
                "parent_score_gap_top_minus_actual": gap,
                "same_action": parent == actual,
            })
    by_key = {(row["game_id"], row["round_no"], row["draw_seq"]) for row in rows}
    if len(by_key) != len(rows):
        raise ValueError("跨来源重复窗口")
    counts = defaultdict(Counter)
    for row in rows:
        count = counts[row["room_id"]]
        count["total"] += 1
        count["actual_" + row["actual_family"]] += 1
        count["parent_" + row["parent_family"]] += 1
        count["family_" + row["actual_family"] + "_to_" + row["parent_family"]] += 1
        count["same_action"] += row["same_action"]
        count["different_zero_score_gap"] += (
            not row["same_action"] and row["parent_score_gap_top_minus_actual"] == 0
        )
    result = {
        "schema": "g05-parent-dev-behavior/1",
        "script_sha256": digest(Path(__file__)),
        "parent_source_sha256": hashlib.sha256(
            c31.R18_INTEGRATED_POSITIVE_V2_SOURCE.encode("utf-8")).hexdigest(),
        "source_windows_sha256": sources,
        "room_counts": {room: dict(sorted(value.items())) for room, value in sorted(counts.items())},
        "total_windows": len(rows),
        "no_outcome_value_used_as_action_quality_label": True,
    }
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    (_project_file(_PROJECT_ROOT, OUT / "windows.json")).write_text(
        json.dumps({"schema": "g05-parent-dev-behavior-windows/1", "windows": rows},
                   ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"total_windows": len(rows),
                      "room_counts": result["room_counts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
