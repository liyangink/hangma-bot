"""打开已提交冻结包中的多根双白机会反事实；仅为离线教师。"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import RuleCompleteness, ValueAnalysisLimits
from hangma_bot.kernel.actions import Discard
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.serialization import observation_from_json
from hangma_bot.offline.vip_reference import choose_reference_action
from hangma_bot.simulation import SimulationChoice, SimulationEngine

from scripts.vip_p3_competing_tail_audit import _label
from scripts.vip_p3_first_event_preflight import _event_key, _finish_hand, _first_event
from scripts.vip_p3_highfan_probe_teacher import _selected_world
from scripts.vip_p3_payoff_frontier import extract_payoff_frontier


_LIMITS = ValueAnalysisLimits(max_expansions=8192)


def _verify_freeze(freeze_path: Path, manifest_path: Path) -> tuple[dict, dict]:
    """结局打开前先核预冻结来源与本地核心源码未漂移。"""

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("scope") != "pre_outcome_source_and_selection_identity_no_teacher_results":
        raise ValueError("机会冻结摘要清单口径不符")
    for item in manifest["files"]:
        path = Path(item["path"])
        if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError("机会冻结来源摘要漂移: " + str(path))
    frozen = json.loads(freeze_path.read_text(encoding="utf-8"))
    if (frozen.get("scope") !=
            "pre_outcome_multi_root_paired_actions_not_algorithm_confirmation"
            or frozen.get("continuation_references") != ["shape", "r18_frozen"]
            or frozen.get("natural_seed_frame") != [4101, 4400]
            or frozen.get("rule_config") != {"BaseScore": 1, "YouCaiBiKao": False}
            or frozen.get("focal_seat") != 0):
        raise ValueError("机会冻结包比较口径不符")
    selection_path = Path(frozen["selection_report"])
    source = selection_path.read_bytes()
    if hashlib.sha256(source).hexdigest() != frozen["selection_report_sha256"]:
        raise ValueError("冻结包选根报告摘要漂移")
    selection = json.loads(gzip.decompress(source)
                           if selection_path.suffix == ".gz" else source)
    by_id = {item["root_id"]: item for item in selection["selected_roots"]}
    if (len(by_id) != len(selection["selected_roots"])
            or set(by_id) != {row["root_id"] for row in frozen["roots"]}
            or len(frozen["roots"]) != 36):
        raise ValueError("冻结包与结果盲选根集合不守恒")
    return frozen, by_id


def audit(freeze_path: Path, manifest_path: Path) -> dict:
    """同根锁定动作共享隐藏世界，逐动作两名参考者走完当前单局。"""

    frozen, selected = _verify_freeze(freeze_path, manifest_path)
    rules = HangmaRules(RuleConfig("hangma-mvp-v10-public-counts", 1, False))
    engine = SimulationEngine(rules)
    rows = []
    root_summaries = []
    payoff_checks = Counter()
    for root in frozen["roots"]:
        picked = selected[root["root_id"]]
        observation = observation_from_json(picked["observation"])
        if hashlib.sha256(repr(observation).encode()).hexdigest() != root["root_id"]:
            raise ValueError("选中玩家观察摘要与冻结根不符")
        context = {**frozen, **root}
        world, frame, decision = _selected_world(engine, rules, context, observation)
        analysis = rules.analyze(observation, value_limits=_LIMITS, route_limits=_LIMITS)
        actions = {item.action_key: item.action for item in analysis.legal_candidates}
        if (analysis.completeness is not RuleCompleteness.COMPLETE
                or list(actions) != picked["legal_action_keys"]
                or any(key not in actions for key in root["forced_first_actions"])):
            raise ValueError("冻结动作不属于重建观察的同次合法动作")
        direct_cells = {}
        for candidate, conditional in zip(analysis.legal_candidates,
                                          analysis.conditional_roots):
            if candidate.action_key not in root["forced_first_actions"] or not isinstance(
                candidate.action, Discard
            ):
                continue
            frontier = extract_payoff_frontier(candidate, conditional, observation.seat)
            direct_cells[candidate.action_key] = {
                cell.draw_code: cell for path in frontier.paths
                if path.conditions.draw_kind == "normal" for cell in path.cells
            }
        by_ref = {ref: {key: [] for key in root["forced_first_actions"]}
                  for ref in frozen["continuation_references"]}
        for sample in range(root["worlds_per_root"]):
            hidden = engine.resample_public_consistent_hidden_world(
                world, focal_seat=frozen["focal_seat"],
                sample_key=f"{root['resample_key_prefix']}-{sample}",
            )
            sampled_frame = engine.frame(hidden)
            focal = [item for item in sampled_frame.decisions
                     if item.window_key == decision.window_key]
            if len(focal) != 1 or focal[0].observation != observation:
                raise ValueError("相关隐藏世界改变冻结玩家观察或窗口")
            for key in root["forced_first_actions"]:
                after = engine.advance(hidden, sampled_frame.revision, tuple(
                    SimulationChoice(
                        item.window_key,
                        actions[key] if item.window_key == decision.window_key else
                        choose_reference_action(rules, item,
                                                mode=frozen["selection_reference"]),
                    ) for item in sampled_frame.decisions
                ))
                for reference in frozen["continuation_references"]:
                    event = _first_event(engine, rules, after, seat=observation.seat,
                                         reference=reference)
                    terminal = _finish_hand(engine, rules, after, reference=reference)
                    if event["kind"] in ("self_win", "other_win", "draw") and (
                        event["score_delta"] != terminal["score_delta"]
                    ):
                        raise ValueError("首次终局事件与完整单局四座结算不同")
                    if key in direct_cells and event["kind"] == "self_normal_draw":
                        expected = direct_cells[key].get(event["tile"])
                        actual = event["immediate_hu"]
                        if (expected is None) != (actual is None):
                            raise ValueError("条件下一普通摸牌胡资格与实际规则不同")
                        payoff_checks["normal_draw_checked"] += 1
                        if expected is not None:
                            if (expected.fan != actual["fan"]
                                    or list(expected.score_delta) != actual["score_delta"]):
                                raise ValueError("条件下一普通摸牌胡支付与实际规则不同")
                            payoff_checks["direct_hu_checked"] += 1
                    payload = {
                        "seed": root["seed"], "root_id": root["root_id"],
                        "sample": sample, "first_action_key": key,
                        "continuation_reference": reference,
                        "first_event_key": _event_key(event),
                        "first_event_kind": event["kind"],
                        "first_event_immediate_hu": event.get("immediate_hu"),
                        "terminal_category": _label(terminal, observation.seat),
                        "terminal": terminal,
                    }
                    rows.append(payload)
                    by_ref[reference][key].append(payload)
        ref_summary = {}
        for reference, actions_by_key in by_ref.items():
            action_summary = {}
            for key, action_rows in actions_by_key.items():
                if [item["sample"] for item in action_rows] != list(
                    range(root["worlds_per_root"])
                ):
                    raise ValueError("相关隐藏世界编号或动作世界数不守恒")
                nets = [item["terminal"]["score_delta"][observation.seat]
                        for item in action_rows]
                action_summary[key] = {
                    "mean_own_net": sum(nets) / len(nets),
                    "self_high_count": sum(item["terminal_category"] == "self_high"
                                           for item in action_rows),
                    "other_win_count": sum(item["terminal_category"] == "other_win"
                                           for item in action_rows),
                    "draw_count": sum(item["terminal_category"] == "draw"
                                      for item in action_rows),
                }
            baseline = root["roles"]["r18"]
            model = root["roles"]["anchored"]
            paired = None
            if model is not None:
                paired = [left["terminal"]["score_delta"][observation.seat] -
                          right["terminal"]["score_delta"][observation.seat]
                          for left, right in zip(actions_by_key[model],
                                                 actions_by_key[baseline])]
            ref_summary[reference] = {
                "actions": action_summary,
                "anchored_minus_r18_paired": {
                    "mean_own_net": sum(paired) / len(paired),
                    "positive": sum(value > 0 for value in paired),
                    "negative": sum(value < 0 for value in paired),
                    "zero": sum(value == 0 for value in paired),
                } if paired is not None else None,
            }
        root_summaries.append({
            "seed": root["seed"], "root_id": root["root_id"],
            "tags": root["tags"], "roles": root["roles"],
            "worlds_per_root": root["worlds_per_root"],
            "references": ref_summary,
        })
    expected_rows = sum(row["worlds_per_root"] * len(row["forced_first_actions"])
                        * len(frozen["continuation_references"]) for row in frozen["roots"])
    if len(rows) != expected_rows:
        raise ValueError("全机会根动作世界结果数不守恒")
    return {
        "scope": "opened_multi_root_forced_first_action_teacher_not_full_VIP_strength",
        "freeze_path": str(freeze_path),
        "freeze_sha256": hashlib.sha256(freeze_path.read_bytes()).hexdigest(),
        "pre_outcome_freeze_commit": "c4615a378",
        "root_count": len(frozen["roots"]),
        "natural_seed_count": len({row["seed"] for row in frozen["roots"]}),
        "row_count": len(rows),
        "rule_payoff_checks": dict(sorted(payoff_checks.items())),
        "root_summaries": root_summaries,
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.freeze, args.manifest)
    payload = (json.dumps(result, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":")) + "\n").encode("utf-8")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.suffix == ".gz":
        with args.output.open("wb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0,
                               compresslevel=9) as stream:
                stream.write(payload)
    else:
        args.output.write_bytes(payload)


if __name__ == "__main__":
    main()
