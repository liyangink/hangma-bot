"""只读复算 VIP P2 的有限官方夹具根登记；输出 JSON，不作全域验收。"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import replace
from pathlib import Path

from hangma_bot.adapters.official.dto import parse_state_response
from hangma_bot.adapters.official.projector import observation, public_event
from hangma_bot.hangma.engine import HangmaRules, _build_context
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.hangma.route_frontier import RouteGapKind
from hangma_bot.hangma.route_transition import project_legal_roots
from hangma_bot.kernel.config import RuleConfig

REPO = Path(__file__).resolve().parents[1]
V18 = "tests/fixtures/official/v18/action-chain/chi-gang-draw.json"
V35 = "tests/fixtures/official/v35/vip-p2-natural"
# (动作前快照 seq, 已执行动作键, 官方动作事件 seq, 后继权威快照 seq)。
# 这是仅四条轨迹的索引，不是按结果挑选的全域抽样框。
TRACES = {
    V18: ((2266, "chi:7t,8t,9t", 2267, 2267),
          (2267, "gang:concealed:2w", 2268, 2269),
          (2269, "discard:7t", 2270, 2270)),
    f"{V35}/peng-followup-1114-1117.json": (
        (1114, "peng:6b", 1115, 1115), (1115, "discard:9w", 1116, 1117)),
    f"{V35}/bugang-replenish-1510-1514.json": (
        (1510, "gang:added:2t", 1511, 1512),
        (1512, "discard:6t", 1513, 1514)),
    f"{V35}/minggang-replenish-hu-1228-1231.json": (
        (1228, "gang:exposed:4b", 1229, 1230),
        (1230, "hu", 1231, 1231)),
}
EXTENDED_TRACES = {
    **TRACES,
    f"{V35}/other-minggang-1201-1209.json": (),
    f"{V35}/other-angang-1218-1222.json": (),
    f"{V35}/other-bugang-781-787.json": (),
    f"{V35}/exhaustive-draw-1147-1159.json": (),
}


def _family(key: str) -> str:
    """按合法动作键归并；三种杠保留独立动作族。"""

    parts = key.split(":")
    return ":".join(parts[:2]) if parts[0] == "gang" else parts[0]


def _load(path: str):
    """仅从完整本座快照投影观察；缺快照的水位记跳过原因。"""

    data = json.loads((REPO / path).read_text())
    v18 = path == V18
    raw_events = data["events"] if v18 else data["public_or_own_events"]
    if not v18 and any(e["type"] == "tile_drawn" and e["seat"] != data["seat"]
                      and e.get("tile")
                      for e in raw_events):
        raise ValueError(path + ": 夹具含他座私有摸牌")
    events = tuple(public_event(e) for e in
                   parse_state_response({"events": raw_events}).events)
    raw_states = (data["snapshots"].values() if v18 else
                  (entry["response"] for entry in data["state_responses"]))
    views, skipped = {}, []
    for raw in raw_states:
        parsed = parse_state_response(raw)
        seq = raw.get("seq")
        if parsed.gap or parsed.snapshot is None:
            skipped.append({"fixture": path, "seq": seq, "reason": "缺完整权威快照或 gap=true"})
            continue
        snap = parsed.snapshot
        game_id = raw["snapshot"]["game_id"] if v18 else data["game_id"]
        views[snap.seq] = replace(observation(
            snap, tuple(e for e in events if e.seq <= snap.seq),
            game_id), consumed_seq=snap.seq)
    if v18:
        # source.json 只有 v18 指南版本，不包含本次房间的官方 /rules。
        config = RuleConfig("hangma-mvp-v10-public-counts", 1, False)
        provenance = "v18_target_config_assumed"
    else:
        declared = data["provenance"]["rule_config"]
        if (declared["base_score"], declared["you_cai_bi_kao"]) != (1, False):
            raise ValueError(path + ": 非目标运行配置")
        config = RuleConfig(declared["ruleset_version"], 1, False)
        provenance = "v35_local_run_config_recorded_no_official_rules_response"
    return views, raw_events, events, config, provenance, skipped


def _pair_matches(root, after, event) -> bool:
    """只核本人暗牌单步或已结算结果；不冒充完整公开事件闭包。"""

    if root.settlement is not None:
        return (root.settlement.fan == event.result_fan and
                root.settlement.score_delta == event.result_scores)
    state = (root.claim_state if root.claim_state is not None else
             root.branches[0].state if root.branches else None)
    if state is None:
        return False
    expected = Counter(state.concealed)
    if root.action_key.startswith("gang:") and after.drawn_tile is not None:
        expected[after.drawn_tile] += 1
    return expected == Counter(_build_context(after).full_hand())


def audit(*, traces: dict | None = None) -> dict:
    """登记指定本座轨迹的所有合法根；默认保留冻结四轨迹基线。"""

    if traces is None:
        traces = TRACES
    rows, skipped = [], []
    for path, anchors in traces.items():
        views, raw_events, events, config, provenance, missing = _load(path)
        skipped.extend(missing)
        event_by_seq = {e.seq: e for e in events}
        raw_by_seq = {e["seq"]: e for e in raw_events}
        anchor_by_seq = {before: (key, event_seq, after)
                         for before, key, event_seq, after in anchors}
        rules = HangmaRules(config)
        for seq, view in sorted(views.items()):
            if view.phase not in ("draw", "response_peng", "response_chi"):
                skipped.append({"fixture": path, "seq": seq,
                                "reason": "非本人可决策窗口"})
                continue
            analysis = rules.analyze(view, value_limits=ValueAnalysisLimits())
            if not analysis.legal_candidates:
                skipped.append({"fixture": path, "seq": seq,
                                "reason": "该公开窗口本座无合法候选，不进入根分母"})
                continue
            roots = project_legal_roots(
                view, _build_context(view), analysis.legal_candidates, config=config)
            if tuple(r.action_key for r in roots) != tuple(
                    c.action_key for c in analysis.legal_candidates):
                raise AssertionError(path + f": {seq} 根登记与合法候选不一致")
            anchor = anchor_by_seq.get(seq)
            if anchor is not None:
                key, event_seq, after_seq = anchor
                event = event_by_seq.get(event_seq)
                raw_event = raw_by_seq.get(event_seq)
                expected_kind = ("round_ended" if key == "hu" else
                                 "tile_discarded" if key.startswith("discard:") else
                                 key.split(":")[0])
                if (event is None or event.kind != expected_kind or
                        raw_event is None or raw_event["seat"] != view.seat or
                        key not in {r.action_key for r in roots}):
                    raise AssertionError(path + f": {seq} 官方锚点与合法根不符")
                if after_seq not in views:
                    skipped.append({"fixture": path, "seq": after_seq,
                                    "reason": "锚点缺后继完整权威快照"})
                    anchor = None
            for root in roots:
                gaps = set(root.gap_kinds or (() if root.gap_kind is None else (root.gap_kind,)))
                issue_areas = [issue.area for issue in root.issues]
                future_condition_open = root.pending_condition is not None
                root_projection_mechanical_gap = RouteGapKind.MECHANICAL_GAP in gaps
                if root.settlement is not None:
                    structure = "settlement"
                elif root.branches:
                    structure = ("structural_only" if all(
                        branch.state.structural_only for branch in root.branches)
                        else "conditional_branches")
                elif root.claim_state is not None or root.proposal_state is not None:
                    structure = "claim_or_proposal_only"
                else:
                    structure = "none"
                anchored = bool(anchor and root.action_key == anchor[0])
                rows.append({
                    "fixture": path, "guide_version": 18 if path == V18 else 35,
                    "config_provenance": provenance, "game_id": view.game_id,
                    "seq": seq, "window": view.phase, "family": _family(root.action_key),
                    "action_key": root.action_key, "structure": structure,
                    "branch_count": len(root.branches),
                    "mechanical_gap": RouteGapKind.MECHANICAL_GAP in gaps,
                    "legacy_mechanical_or_future_placeholder": (
                        RouteGapKind.MECHANICAL_GAP in gaps or future_condition_open),
                    "root_projection_mechanical_gap": root_projection_mechanical_gap,
                    "future_condition_open": future_condition_open,
                    "pending_condition": (root.pending_condition.value
                                          if root.pending_condition is not None else None),
                    "input_evidence_gap": RouteGapKind.INPUT_EVIDENCE_GAP in gaps,
                    "issue_areas": issue_areas,
                    "official_pair_anchor": anchored,
                    "official_pair_state_match": (
                        _pair_matches(root, views[anchor[2]], event) if anchored else False),
                })
    matrix = []
    for window, family in sorted({(r["window"], r["family"]) for r in rows}):
        cell = [r for r in rows if (r["window"], r["family"]) == (window, family)]
        structures = Counter(r["structure"] for r in cell)
        matrix.append({"window": window, "family": family, "legal_roots": len(cell),
                       "structures": dict(sorted(structures.items())),
                       "mechanical_gap": sum(r["mechanical_gap"] for r in cell),
                       "legacy_mechanical_or_future_placeholder": sum(
                           r["legacy_mechanical_or_future_placeholder"] for r in cell),
                       "root_projection_mechanical_gap": sum(
                           r["root_projection_mechanical_gap"] for r in cell),
                       "future_condition_open": sum(r["future_condition_open"]
                                                    for r in cell),
                       "input_evidence_gap": sum(r["input_evidence_gap"] for r in cell),
                       "both_gaps": sum(r["mechanical_gap"] and r["input_evidence_gap"]
                                        for r in cell),
                       "official_pair_anchors": sum(r["official_pair_anchor"] for r in cell),
                       "official_pair_state_matches": sum(
                           r["official_pair_state_match"] for r in cell)})
    return {"scope": ("four_selected_official_traces_not_global_coverage"
                      if traces is TRACES else
                      "eight_selected_official_traces_not_global_coverage"),
            "target_config": {"BaseScore": 1, "YouCaiBiKao": False},
            "fixture_count": len(traces), "snapshot_count": len({(r["fixture"], r["seq"])
                                                                for r in rows}),
            "legal_root_count": len(rows), "official_pair_anchor_count": sum(
                r["official_pair_anchor"] for r in rows),
            "official_pair_state_match_count": sum(
                r["official_pair_state_match"] for r in rows),
            "matrix": matrix, "rows": rows, "skipped": skipped}


if __name__ == "__main__":
    print(json.dumps(audit(), ensure_ascii=False, sort_keys=True, indent=2))
