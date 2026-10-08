#!/usr/bin/env python3
"""四开发房近分弃牌：只拆行动前规则事实，不把强手动作当质量标签。"""

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

import c31_action_layer_gap as c31
import g05_parent_dev_behavior as g05
from hangma_bot.application.audit_codec import observation_from_json
from hangma_bot.kernel.actions import WindowKey, WindowPhase
from hangma_bot.kernel.observation import CompetitionContext
from hangma_bot.policy.action_value_policy import build_scoring_view
from hangma_bot.policy.action_value_seeds import ActionValueScorer
from hangma_bot.policy.interface import DecisionRequest


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g5-near-tie-facts-01')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def width(action: dict) -> int:
    """当前一步有效张数的公开估计；仅用于描述，不当作路线价值。"""
    return sum(item["remaining_estimate"] for item in action.get("useful_tiles") or ())


def run() -> tuple[dict, list[dict]]:
    """按已见四房近分分母重算，不读未来墙或单局结算标签。"""
    baseline_path = _project_file(_PROJECT_ROOT, HERE / "evidence/g05-parent-dev-behavior-01/windows.json")
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))["windows"]
    targets = {
        (row["game_id"], row["round_no"], row["draw_seq"]): row
        for row in baseline
        if row["actual_family"] == "discard"
        and row["parent_family"] == "discard"
        and not row["same_action"]
        and 0 < row["parent_score_gap_top_minus_actual"] <= 10
    }
    if len(targets) != 257:
        raise ValueError("四房近分窗口分母漂移")
    parent_source_sha = hashlib.sha256(c31.R18_INTEGRATED_POSITIVE_V2_SOURCE.encode("utf-8")).hexdigest()
    if parent_source_sha != c31.R18_INTEGRATED_POSITIVE_V2_SHA256:
        raise ValueError("冻结父代源码摘要漂移")
    scorer = ActionValueScorer("g5-r18-parent-positive-control",
                               c31.R18_INTEGRATED_POSITIVE_V2_SOURCE)
    rows = []
    counts = defaultdict(Counter)
    sources = {}
    for source_name in g05.DISCARD_DIRS + g05.HIGH_VALUE_DIRS:
        path = _project_file(_PROJECT_ROOT, HERE / "evidence" / source_name / "windows.json")
        sources[source_name] = sha(path)
        for item in json.loads(path.read_text(encoding="utf-8"))["windows"]:
            key = (item["game_id"], item["round_no"], item["draw_seq"])
            prior = targets.pop(key, None)
            if prior is None:
                continue
            observation = observation_from_json(item["observation"])
            analysis = c31.RULES.analyze(observation, value_limits=c31.VALUE_LIMITS)
            request = DecisionRequest(
                observation=observation,
                competition=CompetitionContext(
                    tournament_id="g5-official-replay", stage_no=None,
                    stage_role=None, stage_total=None, participant_rank=None,
                    ranking=(), observed_at_unix_ms=0,
                ),
                rules=analysis, decision_id="g5:" + str(item["draw_seq"]),
                trigger_seq=item["draw_seq"],
                window_key=WindowKey(
                    game_id=item["game_id"], round_no=item["round_no"],
                    trigger_seq=item["draw_seq"], phase=WindowPhase.DRAW,
                    seat=observation.seat,
                ),
                rejected_attempts=(),
            )
            view = build_scoring_view(request, value_limits=c31.VALUE_LIMITS)
            scored = scorer.score(view)
            if scored.status != "SCORED":
                raise ValueError("父代正控无法评分")
            entries = {entry.action_key: entry for entry in scored.entries}
            actions = {entry["action_key"]: entry for entry in view.candidate_view()["actions"]}
            actual_key, parent_key = prior["actual_action"], prior["parent_top_action"]
            if actual_key not in entries or parent_key not in entries:
                raise ValueError("父代评分缺少已核合法动作")
            top = min(scored.entries, key=lambda entry: (-entry.score, entry.action_key))
            if (top.action_key != parent_key
                    or abs(top.score - entries[actual_key].score
                           - prior["parent_score_gap_top_minus_actual"]) > 1e-9):
                raise ValueError("冻结父代近分正控不一致")
            actual, parent = actions[actual_key], actions[parent_key]
            ae, pe = entries[actual_key], entries[parent_key]
            row = {
                "room_id": item["room_id"], "game_id": item["game_id"],
                "round_no": item["round_no"], "draw_seq": item["draw_seq"],
                "actual_action": actual_key, "parent_action": parent_key,
                "score_gap": prior["parent_score_gap_top_minus_actual"],
                "actual_shanten": actual["shanten_after"],
                "parent_shanten": parent["shanten_after"],
                "actual_standard_shanten": actual["standard_shanten_after"],
                "parent_standard_shanten": parent["standard_shanten_after"],
                "actual_seven_pairs_shanten": actual["seven_pairs_shanten_after"],
                "parent_seven_pairs_shanten": parent["seven_pairs_shanten_after"],
                "actual_width": width(actual), "parent_width": width(parent),
                "actual_route_count": len(actual.get("routes") or ()),
                "parent_route_count": len(parent.get("routes") or ()),
                "actual_baotou": actual["baotou_after"],
                "parent_baotou": parent["baotou_after"],
                "actual_risk_units": ae.trace.get("risk_units"),
                "parent_risk_units": pe.trace.get("risk_units"),
                "actual_wealth_part": ae.trace.get("wealth_part"),
                "parent_wealth_part": pe.trace.get("wealth_part"),
                "drawn_tile": observation.drawn_tile.code,
                "wall_remaining": observation.remaining_tile_count,
                "dealer": observation.seat == observation.dealer_seat,
                "rule_issue_areas": [issue.area for issue in analysis.issues],
            }
            rows.append(row)
            c = counts[item["room_id"]]
            c["windows"] += 1
            c["same_shanten"] += row["actual_shanten"] == row["parent_shanten"]
            c["actual_wider"] += row["actual_width"] > row["parent_width"]
            c["actual_narrower"] += row["actual_width"] < row["parent_width"]
            c["same_width"] += row["actual_width"] == row["parent_width"]
            c["actual_has_route"] += row["actual_route_count"] > 0
            c["parent_has_route"] += row["parent_route_count"] > 0
            c["baotou_difference"] += row["actual_baotou"] != row["parent_baotou"]
            c["risk_difference"] += row["actual_risk_units"] != row["parent_risk_units"]
            c["wealth_difference"] += row["actual_wealth_part"] != row["parent_wealth_part"]
            c["actual_drawn_tile_discard"] += actual_key == "discard:" + row["drawn_tile"]
            c["parent_drawn_tile_discard"] += parent_key == "discard:" + row["drawn_tile"]
            c["any_rule_issue"] += bool(row["rule_issue_areas"])
    if targets or len(rows) != 257:
        raise ValueError("四房近分窗口未恰好覆盖")
    totals = Counter()
    for c in counts.values():
        totals.update(c)
    return ({
        "schema": "g5-near-tie-facts/1", "script_sha256": sha(Path(__file__)),
        "baseline_sha256": sha(baseline_path), "source_sha256": sources,
        "frozen_parent_source_sha256": parent_source_sha,
        "room_counts": {room: dict(sorted(c.items())) for room, c in sorted(counts.items())},
        "total_counts": dict(sorted(totals.items())),
        "quality_label_used": False,
        "actual_action_is_observation_not_quality_label": True,
    }, rows)


def main() -> None:
    """写出可复算的行动前事实，不覆盖既有证据。"""
    if OUT.exists():
        raise FileExistsError("结果目录已存在，拒绝覆盖")
    result, rows = run()
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    (_project_file(_PROJECT_ROOT, OUT / "windows.json")).write_text(
        json.dumps({"schema": "g5-near-tie-fact-windows/1", "windows": rows},
                   ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result["total_counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
