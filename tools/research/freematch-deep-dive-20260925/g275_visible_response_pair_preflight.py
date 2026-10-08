#!/usr/bin/env python3
"""G275：只读重建 G76 已确认响应窗，枚举过牌与全部合法吃碰＋跟打。"""

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

import argparse
from collections import Counter, defaultdict
from dataclasses import replace
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import types

HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "review" / "baotou-anatomy-20260925")))

import anatomy_lib as anatomy  # noqa: E402
import c31_action_layer_gap as current_c31  # noqa: E402
import c32_cards as c32  # noqa: E402
from extract_room_scores import load_rooms  # noqa: E402
from hangma_bot.kernel.observation import PublicEvent  # noqa: E402


SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g76-confirmed-response-atlas-20260928/rows.jsonl.gz')
SOURCE_SHA256 = "2a26d239e79ce863311b4be2681a86a9d7d94b50648ab4f4a5355f6d3cd08fc6"
C31_PATH = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/c31_action_layer_gap.py')
FROZEN_REF = "328aa938e^:review/freematch-deep-dive-20260925/c31_action_layer_gap.py"
FROZEN_C31_SHA256 = "c6a2cd34288bbc7aff2a25b8e5f7ca5beab37c9a81d057f181c7794b7f3d2e32"
PEERS = ("xuanwu_2346", "tengshe_0638")
ROW_KEY = ("peer", "room", "game_id", "round_no", "discard_seq", "seat", "phase")


def sha(path: Path) -> str:
    """以文件原始字节绑定冻结输入和脚本。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_frozen_c31():
    """从 G76 所在提交的父版本装配只读 C31，拒绝源码摘要漂移。"""
    completed = subprocess.run(
        ["git", "show", FROZEN_REF], cwd=ROOT, check=True, capture_output=True,
    )
    source = completed.stdout
    actual = hashlib.sha256(source).hexdigest()
    if actual != FROZEN_C31_SHA256:
        raise ValueError(f"G76 冻结 C31 源码摘要漂移：{actual}")
    module = types.ModuleType("g275_g76_frozen_c31")
    module.__file__ = str(C31_PATH)
    sys.modules[module.__name__] = module
    exec(compile(source, str(C31_PATH), "exec"), module.__dict__)
    return module


def window_key(row: dict) -> tuple:
    """玩家、场次和官方弃牌序号共同标识一个已确认响应阶段。"""
    return tuple(row[field] for field in ROW_KEY)


def source_targets(mode: str) -> list[dict]:
    """仅筛 G76 行动前身份；明确超时不进入主动过牌负控。"""
    if sha(SOURCE) != SOURCE_SHA256:
        raise ValueError("G76 行动前压缩源摘要漂移")
    with gzip.open(SOURCE, "rt", encoding="utf-8") as stream:
        rows = [json.loads(line) for line in stream]
    positive = [row for row in rows if row["actor"] == "peer" and
                row["actual"] == "claim" and row["parent_key"] == "pass" and
                row["r6_key"] == "pass" and row["own_meld_count"] > 0]
    controls = [row for row in rows if row["actor"] == "peer" and
                row["peer"] == "xuanwu_2346" and row["actual"] == "pass" and
                row["own_meld_count"] > 0]
    if (len(positive) != 52 or Counter(row["peer"] for row in positive) !=
            {"xuanwu_2346": 27, "tengshe_0638": 25} or len(controls) != 406):
        raise ValueError("G76 正例或玄武明确过牌支持域漂移")
    if mode == "smoke":
        positive = [row for peer in PEERS for row in
                    sorted((row for row in positive if row["peer"] == peer), key=window_key)[:2]]
        controls = sorted(controls, key=window_key)[:2]
    selected = sorted(positive + controls, key=window_key)
    if len({window_key(row) for row in selected}) != len(selected):
        raise ValueError("目标响应阶段键重复")
    return selected


def perturbed_observation(c31, snap: dict, row: dict):
    """改写他家暗牌牌码但保留张数，验证本人观察不依赖其内容。"""
    changed = dict(snap)
    changed["hands"] = [Counter(hand) for hand in snap["hands"]]
    for seat in range(4):
        if seat != row["seat"]:
            total = sum(changed["hands"][seat].values())
            changed["hands"][seat] = Counter({c31.TILE_ORDER[seat]: total})
    return c31.build_observation(changed, row["seat"], row["phase"],
                                 row["game_id"], row["round_no"])


def tile_facts(tiles, *, applicable: bool = True) -> dict:
    """只汇总本人公开未见牌码及容量；不适用与未知明确分开。"""
    if tiles is None:
        return {"status": "unknown" if applicable else "not_applicable",
                "codes": None, "capacity": None}
    items = [{"code": tile.code, "public_remaining": tile.remaining_estimate}
             for tile in tiles]
    return {"status": "known", "codes": items,
            "capacity": sum(item["public_remaining"] for item in items)}


def fact_view(candidate) -> dict:
    """投影生产 CandidateFacts；不自行解牌、估墙或预测他家手牌。"""
    facts = candidate.facts
    if facts is None:
        return {"status": "unknown", "reason": "candidate_facts_absent"}
    progress = [{"family": item.family.value, "progress": item.progress.value,
                 "route_status": item.route_status.value}
                for item in facts.family_progress]
    return {
        "status": "known" if facts.completeness.value == "complete" else "unknown",
        "fact_kind": facts.fact_kind.value,
        "completeness": facts.completeness.value,
        "note": facts.note,
        "combined_shanten": facts.shanten_after,
        "standard_shanten": facts.standard_shanten_after,
        "seven_pairs_shanten": facts.seven_pairs_shanten_after,
        "combined_useful": tile_facts(facts.useful_tiles),
        "standard_useful": tile_facts(facts.standard_useful_tiles),
        "seven_pairs_useful": tile_facts(
            facts.seven_pairs_useful_tiles,
            applicable=(facts.seven_pairs_shanten_after is not None or
                        facts.completeness.value != "complete")),
        "best_followup_discard": facts.best_followup_discard,
        "baotou_after": facts.baotou_after,
        "family_progress": progress,
    }


def value_view(candidate) -> dict:
    """条件一摸胡仅记规则路线覆盖和番数，不当实际兑现或收益。"""
    value = candidate.value_facts
    if value is None:
        return {"coverage": "unavailable", "route_count": None,
                "max_conditional_fan": None, "high_fan_route_count": None,
                "issues": ["candidate_value_facts_absent"]}
    fans = [route.conditional_settlement.fan for route in value.routes]
    return {"coverage": value.coverage.value, "route_count": len(fans),
            "max_conditional_fan": max(fans, default=None),
            "high_fan_route_count": sum(fan >= 2 for fan in fans),
            "issues": [issue.area for issue in value.issues]}


def pass_chi_contingency(c31, snap: dict, row: dict) -> dict:
    """碰窗过牌后仅标可能出现的吃窗，绝不当成已发生的下一摸。"""
    if row["phase"] != "response_peng":
        return {"status": "not_applicable", "conditional_phase": None,
                "legal_keys_if_open": None}
    members = c31._chi_members(snap["discarder"], snap["tile"], snap["owner"])
    if row["seat"] not in members:
        return {"status": "not_eligible", "conditional_phase": "response_chi",
                "legal_keys_if_open": None}
    possible = c31.build_observation(snap, row["seat"], "response_chi",
                                     row["game_id"], row["round_no"])
    analysis = c31.RULES.analyze(possible)
    legal_keys = sorted(item.action_key for item in analysis.legal_candidates)
    return {"status": "possible_if_official_stage_opens",
            "conditional_phase": "response_chi",
            "legal_keys_if_open": legal_keys,
            "has_legal_chi_if_open": any(item.startswith("chi:") for item in legal_keys),
            "completeness": analysis.completeness.value,
            "unknown_reason": "other_responses_may_preempt_chi_stage"}


def post_claim_variant(current, observation, claim, *, remove: bool):
    """同一个合法动作分别按供牌离河/留河构造条件观察并补本次鸣牌证据。

    留河分支必须把已知的供牌来源交给生产公开牌去重器，否则同一张被鸣牌
    同时出现在牌河和新增副露，造成伪造的有效牌容量差异。
    """
    post = current.post_claim_observation(
        observation, claim.action, remove_claimed_from_river=remove,
    )
    if post is None:
        return None, {}
    claimed = observation.last_discard
    if claimed is None or claimed.seat == observation.seat:
        return None, {}
    kind = "chi" if claim.action_key.startswith("chi:") else "peng"
    event_tiles = claim.action.tiles if kind == "chi" else (claimed.tile,)
    # 这是动作发生后的条件状态：本次被鸣牌来源来自触发弃牌与动作本身，
    # 不读取真实后继；合成序号仅供规则模块的紧邻事件配对使用。
    history = (
        PublicEvent(seq=observation.snapshot_seq, kind="tile_discarded",
                    seat=claimed.seat, tiles=(claimed.tile,)),
        PublicEvent(seq=observation.snapshot_seq + 1, kind=kind,
                    seat=observation.seat, tiles=tuple(event_tiles),
                    claimed_tile=claimed.tile if kind == "chi" else None),
    )
    melds = [tuple(group) for group in post.melds]
    melds[observation.seat] = melds[observation.seat][:-1] + (
        replace(melds[observation.seat][-1], from_seat=claimed.seat),
    )
    post = replace(post, melds=tuple(melds), public_history=history,
                   consumed_seq=observation.snapshot_seq + 1)
    analysis = current.RULES.analyze(post, value_limits=current.VALUE_LIMITS)
    discards = {item.action_key: item for item in analysis.legal_candidates
                if item.action_key.startswith("discard:")}
    return analysis, discards


def common_rule_facts(left, right) -> dict:
    """未获独立官方状态校准时只留双口径共同事实；差异显式未知。"""
    before, after = fact_view(left), fact_view(right)
    stable = {name: value for name, value in before.items()
              if name in after and value == after[name] and name != "status"}
    unknown = sorted(set(before) - set(stable) - {"status"})
    complete = before["status"] == after["status"] == "known"
    return {"status": "known" if not unknown and complete else "partial",
            "stable_fields": stable, "unknown_fields": unknown,
            "unknown_reason": None if not unknown and complete else
                              "river_regime_unverified_or_incomplete"}


def action_pairs(current, observation, claim, *, actually_accepted: bool) -> dict:
    """所有鸣牌均比对双口径；已接受动作也不把 C31 重建结果当官方校准。"""
    retained_analysis, retained = post_claim_variant(
        current, observation, claim, remove=False)
    removed_analysis, removed = post_claim_variant(
        current, observation, claim, remove=True)
    if retained_analysis is None or removed_analysis is None:
        return {"status": "unknown", "reason": "post_claim_observation_unavailable",
                "claim_key": claim.action_key, "followups": []}
    before_branches = claim.facts.followup_branches if claim.facts else None
    if before_branches is None:
        return {"status": "unknown", "reason": "preclaim_followup_branches_unavailable",
                "claim_key": claim.action_key, "followups": []}
    before_keys = {"discard:" + branch.followup_discard for branch in before_branches}
    retained_keys, removed_keys = set(retained), set(removed)
    if before_keys != retained_keys or before_keys != removed_keys or not before_keys:
        raise ValueError(f"双口径吃碰跟打合法全集漂移：{claim.action_key}, "
                         f"{before_keys ^ retained_keys}, {before_keys ^ removed_keys}")
    followups = []
    for discard_key in sorted(before_keys):
        left, right = retained[discard_key], removed[discard_key]
        facts = common_rule_facts(left, right)
        if (left.value_facts == right.value_facts and
                value_view(left)["coverage"] == "complete"):
            value = value_view(left)
            value_status = "known_dual_regime_invariant"
        else:
            value = {"status": "unknown",
                     "reason": "river_regime_unverified_value_difference_or_incomplete"}
            value_status = "unknown"
        followups.append({
            "discard_key": discard_key,
            "status": "known_dual_regime_invariant" if facts["status"] == "known" and
                      value_status != "unknown" else "partial_or_unknown",
            "rule_facts": facts,
            "conditional_value": value,
            "unknown_reasons": ([] if facts["status"] == "known" else
                                ["river_regime_unverified_facts"]) +
                               ([] if value_status != "unknown" else
                                ["river_regime_unverified_value"]),
        })
    return {
        "status": "dual_regime_audit",
        "claim_key": claim.action_key,
        "claim_type": type(claim.action).__name__.lower(),
        "actually_accepted": actually_accepted,
        "official_river_regime": ({"status": "unknown", "regime": None,
                                   "reason": "independent_official_state_snapshot_absent"}
                                  if actually_accepted else
                                  {"status": "not_observed_counterfactual", "regime": None}),
        "post_claim_rule_completeness": {
            "retained": retained_analysis.completeness.value,
            "removed": removed_analysis.completeness.value,
        },
        "followups": followups,
        "unknown_reasons": [issue.area for analysis in
                            (retained_analysis, removed_analysis)
                            for issue in analysis.issues],
    }


def analyze_target(frozen, current, parent_frozen, parent_current, r6,
                   row: dict, events: list[dict], start_hands, scores, dealer: int,
                   *, corrected_chain: bool = False) -> dict:
    """只将触发弃牌及此前事件送入重建器，防止未来事件参与特征。"""
    positions = [i for i, event in enumerate(events) if event.get("seq") == row["discard_seq"]]
    if len(positions) != 1 or events[positions[0]].get("type") != "tile_discarded":
        raise ValueError("G76 触发弃牌序号非唯一")
    prefix = events[:positions[0] + 1]
    old_snap = frozen.reconstruct(prefix, start_hands, scores, dealer)[row["discard_seq"]]
    new_snap = current.reconstruct(prefix, start_hands, scores, dealer)[row["discard_seq"]]
    old_window, _, _ = frozen.evaluate_window(
        old_snap, row["seat"], [row["phase"]], row["game_id"], row["round_no"], parent_frozen)
    new_window, _, _ = current.evaluate_window(
        new_snap, row["seat"], [row["phase"]], row["game_id"], row["round_no"], parent_current)
    if old_window is None or new_window is None:
        raise ValueError("G76 已确认合法窗无法由冻结/当前规则重现")
    changed = (old_window["observation"] != new_window["observation"] or
               old_window["view"] != new_window["view"] or
               old_window["analysis"] != new_window["analysis"] or
               old_window["scores"] != new_window["scores"] or
               old_window["margin"] != new_window["margin"])
    if changed and not corrected_chain:
        raise ValueError("G76 冻结源码与当前源码行动前结果不一致")
    if corrected_chain and changed:
        old_ob = old_window["observation"]
        new_ob = new_window["observation"]
        only_chain_changed = replace(
            old_ob,
            rule_state=replace(
                old_ob.rule_state,
                chain_count=new_ob.rule_state.chain_count),
            chain_piao=new_ob.chain_piao) == new_ob
        if (not only_chain_changed or
                old_window["scores"] != new_window["scores"] or
                old_window["margin"] != new_window["margin"] or
                {item.action_key for item in old_window["analysis"].legal_candidates} !=
                {item.action_key for item in new_window["analysis"].legal_candidates}):
            raise ValueError("修正后不止弃牌动作链变化，停止旧支持域复用")
    if old_window["degraded"] or new_window["degraded"]:
        raise ValueError("G76 合法窗的生产规则降级")
    if old_window["margin"] != row["parent_margin"]:
        raise ValueError("G76 冻结父代分差漂移")
    view = old_window["view"]
    old_parent_key, _ = c32.scored_plan(view, old_window["scores"])
    if old_parent_key != row["parent_key"]:
        raise ValueError("G76 冻结父代动作漂移")
    r6_result = r6(view)
    if r6_result.get("status") != "SCORED":
        raise ValueError("G76 旧 +6 评分器弃权")
    r6_scores = {item["action_key"]: item["score"] for item in r6_result["entries"]}
    old_r6_key, _ = c32.scored_plan(view, r6_scores)
    if old_r6_key != row["r6_key"]:
        raise ValueError("G76 旧 +6 首选动作漂移")
    observation = (new_window if corrected_chain else old_window)["observation"]
    if (len(observation.melds[row["seat"]]) != row["own_meld_count"] or
            old_window["observation"] != perturbed_observation(frozen, old_snap, row) or
            new_window["observation"] != perturbed_observation(current, new_snap, row)):
        raise ValueError("本人既有面子或他家暗手扰动不变性失败")
    selected_window = new_window if corrected_chain else old_window
    candidates = {item.action_key: item for item in selected_window["analysis"].legal_candidates}
    if set(candidates) != {item["action_key"] for item in view["actions"]}:
        raise ValueError("生产规则合法表与评分视图动作键不一致")
    pas = candidates.get("pass")
    if pas is None:
        raise ValueError("已确认响应窗缺合法过牌")
    claims = sorted((item for item in candidates.values()
                     if item.action_key.startswith(("chi:", "peng:"))),
                    key=lambda item: item.action_key)
    if not claims:
        raise ValueError("已确认响应窗缺合法吃碰")
    if row["actual"] == "claim" and row["accepted_key"] not in {item.action_key for item in claims}:
        raise ValueError("G76 官方已接受动作不在合法吃碰表")
    best_claim_key = old_window["claim"]["action_key"]
    if (old_window["claim"].get("shanten_after") != row["claim_shanten"] or
            frozen.width_of(old_window["claim"]) != row["claim_width"]):
        raise ValueError("G76 冻结父代最佳鸣牌指纹漂移")
    pairs = [action_pairs(current, observation, item,
                          actually_accepted=(row["actual"] == "claim" and
                                             item.action_key == row["accepted_key"]))
             for item in claims]
    contingent = pass_chi_contingency(
        current if corrected_chain else frozen,
        new_snap if corrected_chain else old_snap, row)
    return {
        "schema": "g275-visible-response-window/3" if corrected_chain else
                  "g275-visible-response-window/2",
        "window_key": {field: row[field] for field in ROW_KEY},
        "label": {"actual": row["actual"], "accepted_key": row["accepted_key"]},
        "prior_own_meld_count": row["own_meld_count"],
        "ruleset_version": selected_window["analysis"].ruleset_version,
        "chain_calibration": {
            "historical_chain_count": old_window["observation"].rule_state.chain_count,
            "corrected_chain_count": new_window["observation"].rule_state.chain_count,
            "historical_chain_piao": old_window["observation"].chain_piao,
            "corrected_chain_piao": new_window["observation"].chain_piao,
        } if corrected_chain else None,
        "legal_response_keys": sorted(candidates),
        "pass": {"rule_facts": fact_view(pas),
                 "conditional_value": value_view(pas),
                 "possible_chi_stage_after_peng_pass": contingent},
        "best_claim_old_fingerprint": {
            "action_key": best_claim_key,
            "combined_shanten": row["claim_shanten"],
            "combined_public_capacity": row["claim_width"],
            "is_accepted_key": best_claim_key == row["accepted_key"],
        },
        "claim_followup_pairs": pairs,
        "official_river_regime_validation": (
            {"status": "unknown", "regime": None,
             "reason": "no_independent_official_state_snapshot_matched_to_window"}
            if row["actual"] == "claim" else
            {"status": "not_applicable_pass", "regime": None}),
        "first_future_own_opportunity": {
            "status": "unknown", "reason": "unobserved_intervening_responses_and_wall_order"},
        "second_future_own_opportunity": {
            "status": "unknown", "reason": "unobserved_intervening_responses_and_wall_order"},
        "information_permission": "other_hands_tile_codes_perturbed_same_player_observation",
        "reconstruction_scope": "prior_events_through_trigger_discard_inclusive",
    }


def production_dependencies_sha() -> dict[str, str]:
    """记录本次实际装载的生产规则与评分依赖，避免声称复现旧运行环境。"""
    files = sorted((_project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/hangma")).rglob("*.py"))
    files.extend((_project_file(_PROJECT_ROOT, ROOT / path) for path in (
        "src/hangma_bot/kernel/observation.py",
        "src/hangma_bot/policy/action_value_policy.py",
    )))
    return {str(path.relative_to(ROOT)): sha(path) for path in files}


def write_evidence(out_dir: Path, rows: list[dict], source_count: int, mode: str,
                   frozen, current, *, corrected_chain: bool = False) -> None:
    """只在完整性通过后写新的确定性压缩行和机读摘要。"""
    out_dir.mkdir(parents=True, exist_ok=False)
    rows_path = out_dir / "rows.jsonl.gz"
    with rows_path.open("wb") as stream:
        with gzip.GzipFile(filename="", mode="wb", fileobj=stream, mtime=0) as zipped:
            for row in rows:
                zipped.write((json.dumps(row, ensure_ascii=False, sort_keys=True,
                                         allow_nan=False) + "\n").encode("utf-8"))
    counts = Counter()
    unknown_reasons = Counter()
    for row in rows:
        counts["windows"] += 1
        counts["positive"] += row["label"]["actual"] == "claim"
        counts["explicit_pass"] += row["label"]["actual"] == "pass"
        counts["legal_chi_peng_actions"] += len(row["claim_followup_pairs"])
        counts["legal_claim_followup_pairs"] += sum(
            len(claim["followups"]) for claim in row["claim_followup_pairs"])
        validation = row["official_river_regime_validation"]
        counts["actual_claim_river_verified"] += (
            row["label"]["actual"] == "claim" and validation["status"] == "verified")
        counts["actual_claim_river_unknown"] += (
            row["label"]["actual"] == "claim" and validation["status"] == "unknown")
        counts["accepted_differs_from_parent_best_claim"] += (
            row["label"]["actual"] == "claim" and
            not row["best_claim_old_fingerprint"]["is_accepted_key"])
        counts["possible_chi_after_peng_pass"] += (
            row["pass"]["possible_chi_stage_after_peng_pass"]["status"] ==
            "possible_if_official_stage_opens")
        counts["legal_chi_if_peng_pass_continues"] += (
            row["pass"]["possible_chi_stage_after_peng_pass"].get(
                "has_legal_chi_if_open") is True)
        counts["post_claim_unknown"] += sum(
            claim["status"] == "unknown" for claim in row["claim_followup_pairs"])
        counts["post_claim_degraded"] += sum(
            "degraded" in claim.get("post_claim_rule_completeness", {}).values()
            for claim in row["claim_followup_pairs"])
        for claim in row["claim_followup_pairs"]:
            counts["accepted_claim_actions"] += claim["actually_accepted"]
            counts["counterfactual_claim_actions"] += not claim["actually_accepted"]
            for followup in claim["followups"]:
                counts["accepted_followup_pairs"] += claim["actually_accepted"]
                counts["counterfactual_followup_pairs"] += not claim["actually_accepted"]
                counts["followup_known_dual_regime"] += (
                    followup["status"] == "known_dual_regime_invariant")
                counts["followup_partial_or_unknown"] += (
                    followup["status"] == "partial_or_unknown")
                unknown_reasons.update(followup["unknown_reasons"])
        counts["first_future_own_opportunity_unknown"] += (
            row["first_future_own_opportunity"]["status"] == "unknown")
        counts["second_future_own_opportunity_unknown"] += (
            row["second_future_own_opportunity"]["status"] == "unknown")
    result = {
        "schema": "g275-visible-response-preflight/3" if corrected_chain else
                  "g275-visible-response-preflight/2", "mode": mode,
        "corrected_chain": corrected_chain,
        "source_target_count": source_count, "produced_windows": len(rows),
        "counts": dict(sorted(counts.items())),
        "unknown_reasons": dict(sorted(unknown_reasons.items())),
        "by_peer_and_label": [{"peer": peer, "actual": actual,
                               "windows": sum(row["window_key"]["peer"] == peer and
                                              row["label"]["actual"] == actual for row in rows)}
                              for peer in PEERS for actual in ("claim", "pass")],
        "hashes": {"g76_rows_gzip": sha(SOURCE),
                   "g76_frozen_c31": FROZEN_C31_SHA256,
                   "current_c31": sha(C31_PATH),
                   "current_production_dependencies": production_dependencies_sha(),
                   "g275_script": sha(Path(__file__)),
                   "rows_gzip": sha(rows_path)},
        "post_claim_river_rule": (
            "No independent official post-claim state snapshot is matched. "
            "Both accepted and counterfactual claims compare retained and removed regimes; "
            "only invariant fields are exposed, otherwise unknown. "
            "Legal followup keys must match in both regimes."
        ),
        "information_boundary": (
            "每窗重建只用该局触发弃牌及以前事件；前局结算仅恢复当时可见桌分。"
            "他家暗手牌码扰动后 PlayerObservation 不变。C31 自身的鸣牌后重建会离河，"
            "故不能作为独立官方状态证据。实际已接受与反事实鸣牌的两种牌河口径"
            "若有不同，其事实显式 unknown；未来本人机会保持 unknown。"
        ),
    }
    (out_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2,
                   allow_nan=False) + "\n", encoding="utf-8")


def main() -> None:
    """先烟测 6 个窗，再用同一程序完整处理 52＋406 个窗。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("smoke", "full"), required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--corrected-chain", action="store_true",
                        help="仅容忍已单独审计过的 C31 弃牌动作链修正，并用修正观察计算后继事实")
    args = parser.parse_args()
    if args.out_dir.exists():
        raise FileExistsError(f"拒绝覆盖已有目录：{args.out_dir}")
    selected = source_targets(args.mode)
    frozen = load_frozen_c31()
    parent_frozen = frozen.load_parent()
    parent_current = current_c31.load_parent()
    r6, _ = c32.load_scorer(c32.R6_FILE)
    if r6 is None:
        raise ValueError("G76 旧 +6 评分器无法装配")
    by_round = defaultdict(list)
    for row in selected:
        by_round[(row["game_id"], row["round_no"])].append(row)
    wanted_games = {row["game_id"] for row in selected}
    found = set()
    output = []
    for _, room, _, game_id, doc in load_rooms():
        if game_id not in wanted_games:
            continue
        metadata = frozen.round_metadata(doc)
        scores = [0, 0, 0, 0]
        for round_no, events, start_hands in anatomy.round_blocks(doc):
            for row in by_round.get((game_id, round_no), ()):
                if room != row["room"] or start_hands is None:
                    raise ValueError("G76 官方房或起手记录漂移")
                dealer = metadata[round_no]["dealer"]
                result = analyze_target(
                    frozen, current_c31, parent_frozen, parent_current, r6,
                    row, events, start_hands, scores, dealer,
                    corrected_chain=args.corrected_chain,
                )
                output.append(result)
                found.add(window_key(row))
            ended = next((event for event in events if event.get("type") == "round_ended"), None)
            if ended is None:
                raise ValueError("官方单局缺终局，后续局可见桌分不可重建")
            delta = (ended.get("data") or {}).get("scores")
            if not isinstance(delta, list) or len(delta) != 4 or sum(delta) != 0:
                raise ValueError("既往单局四座结算不守恒")
            scores = [a + b for a, b in zip(scores, delta)]
    if found != {window_key(row) for row in selected}:
        raise ValueError("G76 目标窗口未全部在原始官方牌谱重建")
    output.sort(key=lambda row: tuple(row["window_key"][field] for field in ROW_KEY))
    write_evidence(args.out_dir, output, len(selected), args.mode, frozen, current_c31,
                   corrected_chain=args.corrected_chain)
    print(json.dumps({"mode": args.mode, "windows": len(output),
                      "out_dir": str(args.out_dir)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
