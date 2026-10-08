#!/usr/bin/env python3
"""四开发房同观察核对 H/M 冻结对手的摸牌动作族与牌码。"""

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

import asyncio
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

import c31_action_layer_gap as c31
import g05_parent_dev_behavior as g05
import sitin_stage as stage
from hangma_bot.application.audit_codec import observation_from_json
from hangma_bot.kernel.actions import WindowKey, WindowPhase
from hangma_bot.kernel.observation import CompetitionContext
from hangma_bot.policy.action_value_policy import build_scoring_view
from hangma_bot.policy.action_value_seeds import ActionValueScorer
from hangma_bot.policy.interface import DecisionBudget, DecisionRequest


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g4-pool-draw-behavior-02')
PANEL_NAMES = (
    "weighted_heuristic_v2",
    "weighted_heuristic_v2_white_guard",
    "weighted_heuristic_v1",
)
BUDGET = DecisionBudget(100.0, 100.0, 100.0)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def family(key: str) -> str:
    return key.split(":", 1)[0]


async def run() -> tuple[dict, list[dict]]:
    """只评四开发房；规则分析与父代复算用于逐窗正控。"""
    baseline_path = _project_file(_PROJECT_ROOT, HERE / "evidence/g05-parent-dev-behavior-01/windows.json")
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))["windows"]
    by_key = {(row["game_id"], row["round_no"], row["draw_seq"]): row
              for row in baseline}
    if len(by_key) != 2293:
        raise ValueError("冻结强手摸牌分母或窗口键漂移")
    contract_path = _project_file(_PROJECT_ROOT, HERE.parent / "llm-guided-heuristic-route-2026-09-15/contracts/group-dev-v1.json")
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    pool = contract["panel"]["opponent_scenarios"]
    expected = set(pool["H"]["opponent_policies"] + pool["M"]["opponent_policies"])
    if expected != set(PANEL_NAMES):
        raise ValueError("H/M 策略身份与预登记不符")
    parent_source_sha = hashlib.sha256(c31.R18_INTEGRATED_POSITIVE_V2_SOURCE.encode("utf-8")).hexdigest()
    if parent_source_sha != c31.R18_INTEGRATED_POSITIVE_V2_SHA256:
        raise ValueError("冻结父代源码摘要漂移")
    scorer = ActionValueScorer("g4-r18-parent-positive-control",
                               c31.R18_INTEGRATED_POSITIVE_V2_SOURCE)
    counts = defaultdict(Counter)
    policy_types = {}
    for name in PANEL_NAMES:
        policy = stage.build_panel_policy(name, lambda: 0.0)
        policy_types[name] = type(policy).__module__ + "." + type(policy).__qualname__
    rows = []
    sources = {}
    seen = set()
    for source_name in g05.DISCARD_DIRS + g05.HIGH_VALUE_DIRS:
        path = _project_file(_PROJECT_ROOT, HERE / "evidence" / source_name / "windows.json")
        sources[source_name] = sha(path)
        for item in json.loads(path.read_text(encoding="utf-8"))["windows"]:
            key = (item["game_id"], item["round_no"], item["draw_seq"])
            if key in seen:
                raise ValueError("源窗口重复")
            seen.add(key)
            prior = by_key.get(key)
            if prior is None or prior["actual_action"] != item["actual_action"]:
                raise ValueError("四房冻结行为基线与源窗口不一致")
            room = item["room_id"]
            observation = observation_from_json(item["observation"])
            analysis = c31.RULES.analyze(observation, value_limits=c31.VALUE_LIMITS)
            legal = {candidate.action_key for candidate in analysis.legal_candidates}
            actual = item["actual_action"]
            if actual not in legal:
                counts[room]["actual_illegal"] += 1
                continue
            request = DecisionRequest(
                observation=observation,
                competition=CompetitionContext(
                    tournament_id="g4-official-replay", stage_no=None,
                    stage_role=None, stage_total=None, participant_rank=None,
                    ranking=(), observed_at_unix_ms=0,
                ),
                rules=analysis, decision_id="g4:" + str(item["draw_seq"]),
                trigger_seq=item["draw_seq"],
                window_key=WindowKey(
                    game_id=item["game_id"], round_no=item["round_no"],
                    trigger_seq=item["draw_seq"], phase=WindowPhase.DRAW,
                    seat=observation.seat,
                ),
                rejected_attempts=(),
            )
            result = scorer.score(build_scoring_view(request, value_limits=c31.VALUE_LIMITS))
            if result.status != "SCORED" or not result.entries:
                counts[room]["parent_scoring_failed"] += 1
                continue
            parent_top = min(result.entries, key=lambda row: (-row.score, row.action_key)).action_key
            if parent_top != prior["parent_top_action"]:
                counts[room]["parent_positive_control_mismatch"] += 1
                continue
            counts[room]["parent_positive_control_match"] += 1
            outputs = {}
            for name in PANEL_NAMES:
                policy = stage.build_panel_policy(name, lambda: 0.0)
                plan = await policy.choose(request, BUDGET)
                for reason in plan.degraded_reasons:
                    if "规则降级" in reason or "分析不完整" in reason or "未知" in reason:
                        counts[room][name + ":degraded_or_unknown"] += 1
                        break
                if any("评分保护[white-discard-guard-v1]" in reason
                       for reason in plan.degraded_reasons):
                    counts[room][name + ":white_guard_applied"] += 1
                if not plan.candidates:
                    counts[room][name + ":empty_plan"] += 1
                    outputs[name] = None
                    continue
                selected = min(plan.candidates, key=lambda row: row.rank).action_key
                if selected not in legal:
                    counts[room][name + ":illegal_plan"] += 1
                    outputs[name] = None
                    continue
                outputs[name] = selected
                actual_family, selected_family = family(actual), family(selected)
                counts[room][name + ":total"] += 1
                counts[room][name + ":actual_" + actual_family] += 1
                counts[room][name + ":chosen_" + selected_family] += 1
                counts[room][name + ":family_" + actual_family + "_to_" + selected_family] += 1
                counts[room][name + ":same_family"] += actual_family == selected_family
                counts[room][name + ":same_action"] += actual == selected
                if actual_family == "discard":
                    gap = prior["parent_score_gap_top_minus_actual"]
                    if gap == 0:
                        counts[room][name + ":same_action_on_parent_tie"] += actual == selected
                    else:
                        counts[room][name + ":same_action_on_parent_non_tie"] += actual == selected
            rows.append({
                "room_id": room, "game_id": item["game_id"],
                "round_no": item["round_no"], "draw_seq": item["draw_seq"],
                "actual_action": actual, "parent_action": parent_top,
                "parent_score_gap_top_minus_actual": prior["parent_score_gap_top_minus_actual"],
                "panel_actions": outputs,
            })
    if seen != set(by_key):
        raise ValueError("源窗口没有恰好覆盖冻结 2,293 窗")
    totals = Counter()
    for room_counts in counts.values():
        totals.update(room_counts)
    result = {
        "schema": "g4-pool-draw-behavior/1",
        "script_sha256": sha(Path(__file__)),
        "source_sha256": sources,
        "frozen_baseline_sha256": sha(baseline_path),
        "pool_contract_sha256": sha(contract_path),
        "frozen_parent_source_sha256": parent_source_sha,
        "policy_names": list(PANEL_NAMES),
        "policy_types": policy_types,
        "pool_slots": {mix: data["opponent_policies"] for mix, data in pool.items()},
        "room_counts": {room: dict(sorted(value.items())) for room, value in sorted(counts.items())},
        "total_counts": dict(sorted(totals.items())),
        "windows": len(rows),
        "outcome_labels_opened": False,
    }
    return result, rows


def main() -> None:
    """写入逐房和逐窗可见动作，不覆盖旧证据。"""
    if OUT.exists():
        raise FileExistsError("结果目录已存在，拒绝覆盖")
    result, rows = asyncio.run(run())
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    (_project_file(_PROJECT_ROOT, OUT / "windows.json")).write_text(
        json.dumps({"schema": "g4-pool-draw-windows/1", "windows": rows},
                   ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"windows": result["windows"],
                      "total_counts": result["total_counts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
