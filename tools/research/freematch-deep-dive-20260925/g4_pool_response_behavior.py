#!/usr/bin/env python3
"""四开发房玄武吃碰机会：同观察复算冻结 H/M 面板的鸣或过。"""

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
import anatomy_lib as anatomy
from extract_room_scores import load_rooms
import g05_response_dev_behavior as baseline_module
import g05_strong_draw_reconstruction as g05
import sitin_stage as stage
from hangma_bot.kernel.actions import WindowKey, WindowPhase
from hangma_bot.kernel.observation import CompetitionContext
from hangma_bot.policy.interface import DecisionBudget, DecisionRequest


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g4-pool-response-behavior-01')
PANEL_NAMES = (
    "weighted_heuristic_v2",
    "weighted_heuristic_v2_white_guard",
    "weighted_heuristic_v1",
)
BUDGET = DecisionBudget(100.0, 100.0, 100.0)
CLAIM_FAMILIES = {"chi", "peng", "gang"}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def run() -> tuple[dict, list[dict]]:
    """固定四开发房、复核 642 个响应机会，所有策略只读同一依法可见观察。"""
    baseline_path = _project_file(_PROJECT_ROOT, HERE / "evidence/g05-response-dev-behavior-01/windows.json")
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))["windows"]
    by_key = {(row["game_id"], row["round_no"], row["discard_seq"], row["seat"]): row
              for row in baseline}
    if len(by_key) != 642:
        raise ValueError("冻结吃碰响应分母或窗口键漂移")
    contract_path = _project_file(_PROJECT_ROOT, HERE.parent / "llm-guided-heuristic-route-2026-09-15/contracts/group-dev-v1.json")
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    pool = contract["panel"]["opponent_scenarios"]
    expected = set(pool["H"]["opponent_policies"] + pool["M"]["opponent_policies"])
    if expected != set(PANEL_NAMES):
        raise ValueError("H/M 策略身份与预登记不符")
    policy_types = {}
    for name in PANEL_NAMES:
        policy = stage.build_panel_policy(name, lambda: 0.0)
        policy_types[name] = type(policy).__module__ + "." + type(policy).__qualname__
    selected = []
    for _, room, _, game_id, doc in load_rooms():
        if room in baseline_module.ROOMS:
            users = [seat.get("user_id") for seat in doc.get("seats") or []]
            if g05.XUANWU in users:
                selected.append((room, game_id, doc, users.index(g05.XUANWU)))
    by_room = Counter(room for room, *_ in selected)
    if any(by_room[room] != 10 for room in baseline_module.ROOMS):
        raise ValueError("四开发房不是各十场：" + str(by_room))
    parent = c31.load_parent()
    parent_source_sha = hashlib.sha256(c31.R18_INTEGRATED_POSITIVE_V2_SOURCE.encode("utf-8")).hexdigest()
    counts = defaultdict(Counter)
    rows = []
    seen = set()
    for room, game_id, doc, target in selected:
        scores = [0, 0, 0, 0]
        metadata = c31.round_metadata(doc)
        for round_no, events, start_hands in anatomy.round_blocks(doc):
            if start_hands is None:
                continue
            dealer = metadata.get(round_no, {}).get("dealer")
            if dealer is None:
                continue
            snaps = c31.reconstruct(events, start_hands, scores, dealer)
            for seq in sorted(snaps):
                snap = snaps[seq]
                if snap["tile"] == c31.WEALTH or target == snap["discarder"]:
                    continue
                phases = []
                if target in c31._peng_members(snap["discarder"], snap["tile"], snap["owner"]):
                    phases.append("response_peng")
                if target in c31._chi_members(snap["discarder"], snap["tile"], snap["owner"]):
                    phases.append("response_chi")
                if not phases:
                    continue
                window, per_phase, _audit = c31.evaluate_window(
                    snap, target, phases, game_id, round_no, parent)
                if window is None:
                    continue
                key = (game_id, round_no, seq, target)
                if key in seen:
                    raise ValueError("重复响应机会")
                seen.add(key)
                prior = by_key.get(key)
                if prior is None:
                    raise ValueError("新响应机会不在冻结基线")
                actual = bool(snap["claim_seat"] == target
                              and snap["claim_kind"] in CLAIM_FAMILIES)
                if (prior["actual_claim"] != actual
                        or prior["parent_claim"] != (window["margin"] > 0)
                        or prior["parent_claim_key"] != window["claim"]["action_key"]
                        or abs(prior["parent_margin"] - window["margin"]) > 1e-9):
                    raise ValueError("父代响应正控与冻结基线不一致")
                counts[room]["parent_positive_control_match"] += 1
                outputs = {}
                phase_actions = {}
                for name in PANEL_NAMES:
                    selected_by_phase = {}
                    for entry in per_phase:
                        if "margin" not in entry:
                            continue
                        observation = entry["observation"]
                        analysis = entry["analysis"]
                        legal = {candidate.action_key for candidate in analysis.legal_candidates}
                        request = DecisionRequest(
                            observation=observation,
                            competition=CompetitionContext(
                                tournament_id="g4-official-replay", stage_no=None,
                                stage_role=None, stage_total=None, participant_rank=None,
                                ranking=(), observed_at_unix_ms=0,
                            ),
                            rules=analysis, decision_id="g4:" + str(seq),
                            trigger_seq=seq,
                            window_key=WindowKey(
                                game_id=game_id, round_no=round_no, trigger_seq=seq,
                                phase=(WindowPhase.RESPONSE_PENG if observation.phase == "response_peng"
                                       else WindowPhase.RESPONSE_CHI), seat=target,
                            ),
                            rejected_attempts=(),
                        )
                        policy = stage.build_panel_policy(name, lambda: 0.0)
                        plan = await policy.choose(request, BUDGET)
                        if not plan.candidates:
                            raise ValueError("面板响应计划为空")
                        selected_action = min(plan.candidates, key=lambda row: row.rank).action_key
                        if selected_action not in legal:
                            raise ValueError("面板响应计划选择了非法动作")
                        selected_by_phase[observation.phase] = selected_action
                        if any("规则降级" in reason or "分析不完整" in reason or "未知" in reason
                               for reason in plan.degraded_reasons):
                            counts[room][name + ":degraded_or_unknown_phase"] += 1
                    if not selected_by_phase:
                        raise ValueError("已纳入响应机会却无可评分 phase")
                    chosen_claim = any(action.split(":", 1)[0] in CLAIM_FAMILIES
                                       for action in selected_by_phase.values())
                    outputs[name] = chosen_claim
                    phase_actions[name] = selected_by_phase
                    counts[room][name + ":total"] += 1
                    counts[room][name + ":claim"] += chosen_claim
                    counts[room][name + ":same_actual"] += chosen_claim == actual
                    counts[room][name + ":actual_claim_panel_pass"] += actual and not chosen_claim
                    counts[room][name + ":actual_pass_panel_claim"] += not actual and chosen_claim
                    counts[room][name + ":same_parent"] += chosen_claim == prior["parent_claim"]
                rows.append({
                    "room_id": room, "game_id": game_id, "round_no": round_no,
                    "discard_seq": seq, "seat": target,
                    "actual_claim": actual, "parent_claim": prior["parent_claim"],
                    "panel_claims": outputs, "panel_phase_actions": phase_actions,
                })
            ended = next((event for event in events if event.get("type") == "round_ended"), None)
            if ended is None:
                raise ValueError("缺权威局结算")
            delta = (ended.get("data") or {}).get("scores")
            if not isinstance(delta, list) or len(delta) != 4:
                raise ValueError("局分数向量缺失")
            scores = [a + b for a, b in zip(scores, delta)]
    if seen != set(by_key):
        raise ValueError("源窗口没有恰好覆盖冻结 642 窗")
    totals = Counter()
    for room_counts in counts.values():
        totals.update(room_counts)
    return ({
        "schema": "g4-pool-response-behavior/1",
        "script_sha256": sha(Path(__file__)),
        "baseline_sha256": sha(baseline_path),
        "pool_contract_sha256": sha(contract_path),
        "frozen_parent_source_sha256": parent_source_sha,
        "reconstruction_source_sha256": sha(Path(c31.__file__)),
        "policy_names": list(PANEL_NAMES), "policy_types": policy_types,
        "pool_slots": {mix: data["opponent_policies"] for mix, data in pool.items()},
        "room_counts": {room: dict(sorted(value.items())) for room, value in sorted(counts.items())},
        "total_counts": dict(sorted(totals.items())),
        "windows": len(rows),
        "future_outcome_as_quality_label_used": False,
        "past_round_scores_used_for_observation_reconstruction": True,
        "response_aggregation": "each legal phase independently; claim if any phase first action is chi/peng/gang",
    }, rows)


def main() -> None:
    """输出逐窗动作及逐房计数；拒绝覆盖证据目录。"""
    if OUT.exists():
        raise FileExistsError("结果目录已存在，拒绝覆盖")
    result, rows = asyncio.run(run())
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    (_project_file(_PROJECT_ROOT, OUT / "windows.json")).write_text(
        json.dumps({"schema": "g4-pool-response-windows/1", "windows": rows},
                   ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"windows": result["windows"],
                      "total_counts": result["total_counts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
