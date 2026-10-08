#!/usr/bin/env python3
"""G218：只读 G217 已见官方行为窗，逐项定位两步路线候选停线原因。"""

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
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

import g217_two_step_natural_route_policy as candidate
import g217_two_step_natural_route_preflight as preflight
from hangma_bot.application.deadline import BudgetPolicy


HERE = Path(__file__).resolve().parent
SOURCE = preflight.OUT
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g218-g217-guard-audit-20260929/result.json')
EPS = candidate.EPSILON


def digest(path: Path) -> str:
    """已看行为与候选源码内容摘要。"""
    return sha256(path.read_bytes()).hexdigest()


def failures(parent: candidate.RouteProjection,
             alt: candidate.RouteProjection) -> list[str]:
    """与 G217 不退守卫逐条件同义；一窗可有多个失败分量。"""
    bad = []
    if alt.first_hu_expected_score + EPS < parent.first_hu_expected_score:
        bad.append("immediate_hu")
    for mode in ("restricted", "unrestricted"):
        p, a = getattr(parent, mode), getattr(alt, mode)
        if a.natural_need > p.natural_need + EPS:
            bad.append(mode + "/natural_need")
        if a.natural_progress_capacity + EPS < p.natural_progress_capacity:
            bad.append(mode + "/natural_progress")
        if a.whites_held + EPS < p.whites_held:
            bad.append(mode + "/whites")
        if a.baotou + EPS < p.baotou:
            bad.append(mode + "/baotou")
        if a.second_hu_option + EPS < p.second_hu_option:
            bad.append(mode + "/second_hu_option")
        if (p.seven_need is None) != (a.seven_need is None):
            bad.append(mode + "/seven_applicability")
        if p.seven_need is not None:
            if a.seven_need > p.seven_need + EPS:
                bad.append(mode + "/seven_need")
            if a.seven_progress_capacity + EPS < p.seven_progress_capacity:
                bad.append(mode + "/seven_progress")
    a, p = alt.unrestricted, parent.unrestricted
    if not (a.natural_need + EPS < p.natural_need
            or a.natural_progress_capacity > p.natural_progress_capacity + EPS):
        bad.append("no_strict_unrestricted_progress")
    if bool(bad) == candidate._non_regress(parent, alt):
        raise ValueError("逐条件诊断与 G217 守卫分歧")
    return bad


def one(row: dict, batch: dict, source_hashes: dict) -> dict:
    """重放同一玩家可见请求，不读取牌局结算或调候选。"""
    observation = preflight._observation(row, batch["units"], source_hashes)
    request = preflight.g87.request_for(observation)
    budget = BudgetPolicy().build(800.0, 3.0)
    plan = asyncio.run(candidate.g210.parent_factory(None).choose(request, budget))
    if plan.candidates[0].action_key != row["parent_action"]:
        raise ValueError("G218 父代首选与 G217 不一致")
    original = plan.candidates[0]
    legal = {item.action_key: item for item in request.rules.legal_candidates}
    root = legal[original.action_key]
    same = []
    wealth = observation.rule_state.wealth_god.code
    for ranked in plan.candidates[1:]:
        fact = legal.get(ranked.action_key)
        if (not ranked.action_key.startswith("discard:")
                or ranked.action_key == "discard:" + wealth
                or fact is None or fact.facts is None
                or fact.facts.standard_shanten_after != root.facts.standard_shanten_after
                or candidate._width(fact) is None):
            continue
        same.append(ranked)
    shortlist = same[:candidate.MAX_ALTERNATES]
    if same:
        widest = max(same, key=lambda ranked: (
            candidate._width(legal[ranked.action_key])[1],
            candidate._width(legal[ranked.action_key])[0], -ranked.rank))
        if widest.action_key not in {item.action_key for item in shortlist}:
            shortlist.append(widest)
    parent_route = candidate.project(request, original.action_key)
    parent_risk = candidate.g210._risk(original)
    reach = candidate.reach_weight(observation.remaining_tile_count)
    items = []
    for alternate in shortlist:
        risk = candidate.g210._risk(alternate)
        if risk is None or risk > parent_risk + EPS:
            items.append({"action": alternate.action_key, "status": "risk_guard"})
            continue
        route = candidate.project(request, alternate.action_key)
        bad = failures(parent_route, route)
        future_gain = (route.unrestricted.natural_score
                       - parent_route.unrestricted.natural_score)
        margin = reach * future_gain - (original.total_score - alternate.total_score)
        items.append({"action": alternate.action_key,
                      "status": "route_guard" if bad else
                                "score_gap" if margin <= EPS else "would_adopt",
                      "failed_guards": bad,
                      "future_natural_gain": round(future_gain, 6),
                      "adjusted_margin": round(margin, 6),
                      "base_gap": round(original.total_score - alternate.total_score, 6)})
    return {"peer": row["peer"], "room": row["room"],
            "game_id": row["game_id"], "round_no": row["round_no"],
            "draw_seq": row["draw_seq"], "shortlisted": len(shortlist),
            "same_layer_alternates": len(same),
            "strong_action_parent_rank": next(
                (ranked.rank for ranked in plan.candidates
                 if ranked.action_key == row["strong_action"]), None),
            "alternates": items}


def main() -> None:
    """本项为失败机制诊断；不得把重放结果称独立行为验证。"""
    if OUT.exists():
        raise FileExistsError(OUT)
    done = json.loads(SOURCE.read_text(encoding="utf-8"))
    if done["schema"] != "g217-two-step-natural-route-preflight/1" or done["preflight_pass"]:
        raise ValueError("G217 停线结果身份改变")
    batch = json.loads((preflight.G61 / "result.json").read_text(encoding="utf-8"))
    hashes = {}
    result_rows = []
    for count, row in enumerate(preflight.selected_rows(), 1):
        result_rows.append(one(row, batch, hashes))
        if count % 16 == 0:
            print(json.dumps({"windows": count}), flush=True)
    if len(result_rows) != len(done["rows"]):
        raise ValueError("G218 窗口数量改变")
    guard_counts = Counter()
    status_counts = Counter()
    with_positive_margin = Counter()
    possible_rooms = {peer: set() for peer in preflight.PEERS}
    for row in result_rows:
        for item in row["alternates"]:
            status_counts[item["status"]] += 1
            for reason in item.get("failed_guards", ()):
                guard_counts[reason] += 1
            if item.get("adjusted_margin", 0) > EPS:
                with_positive_margin[item["status"]] += 1
                possible_rooms[row["peer"]].add(row["room"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    output = {
        "schema": "g218-g217-guard-audit/1",
        "source_sha256": {"g217_result": digest(SOURCE),
                          "g217_candidate": digest(_project_file(_PROJECT_ROOT, HERE / "g217_two_step_natural_route_policy.py")),
                          "g217_preflight": digest(_project_file(_PROJECT_ROOT, HERE / "g217_two_step_natural_route_preflight.py"))},
        "windows": len(result_rows),
        "status_counts": dict(sorted(status_counts.items())),
        "failed_guard_counts": dict(sorted(guard_counts.items())),
        "positive_adjusted_margin_by_status": dict(sorted(with_positive_margin.items())),
        "positive_margin_rooms_even_without_route_guards": {
            peer: len(rooms) for peer, rooms in possible_rooms.items()},
        "strong_action_rank_gt_7": sum(
            row["strong_action_parent_rank"] is not None
            and row["strong_action_parent_rank"] > 7 for row in result_rows),
        "windows_with_more_than_7_same_layer_alternates": sum(
            row["same_layer_alternates"] > 7 for row in result_rows),
        "rows": result_rows,
        "boundary": "同一已见 G217 官方行为窗的守卫拆解；多原因可并存，不能按本结果删守卫后宣称独立准入。",
    }
    OUT.write_text(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({key: output[key] for key in
                      ("status_counts", "failed_guard_counts",
                       "positive_adjusted_margin_by_status",
                       "positive_margin_rooms_even_without_route_guards",
                       "strong_action_rank_gt_7")},
                     ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
