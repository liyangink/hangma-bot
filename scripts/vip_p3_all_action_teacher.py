"""P3 全合法动作的结果盲离线教师；仅为统一积分估值提供训练账。

选根只看冻结的 ``shape`` 续打路径及当前玩家观察。每根重采样的同一隐藏
世界供全部合法动作共用；完整世界绝不进入策略输入。首次事件与最终单局
结算分别记录，不能把教师的续打价值直接称为新策略价值。
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from typing import Mapping

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import RuleCompleteness, ValueAnalysisLimits
from hangma_bot.kernel.actions import Gang, Hu, action_key
from hangma_bot.kernel.config import RuleConfig, TimingConfig, TournamentConfig
from hangma_bot.kernel.serialization import observation_to_json
from hangma_bot.offline.vip_reference import choose_reference_action
from hangma_bot.simulation import MatchSpec, SimulationChoice, SimulationEngine

if __package__:
    from scripts.vip_p3_first_event_preflight import _event_key, _finish_hand, _first_event
else:
    from vip_p3_first_event_preflight import _event_key, _finish_hand, _first_event


_DRAW_ORDINALS = (1, 5, 10)


def _selected_roots(engine: SimulationEngine, rules: HangmaRules, world, *,
                    target_draws: Mapping[int, tuple[str, ...]] | None = None):
    """按行动前窗口属性留根；同一窗口命中多个标签时只计算一次。"""

    selected = []
    by_window = {}
    seen_tags = set()
    draw_ordinal = 0
    for _ in range(500):
        frame = engine.frame(world)
        if frame.blocked_reason is not None:
            raise ValueError("选根期间模拟器阻塞: " + frame.blocked_reason)
        if frame.final_scores is not None:
            return selected
        for decision in frame.decisions:
            if decision.window_key.seat != 0:
                continue
            analysis = rules.analyze(decision.observation)
            tags = []
            if decision.observation.phase == "draw":
                if decision.observation.drawn_tile is not None:
                    draw_ordinal += 1
                if target_draws is not None:
                    tags.extend(target_draws.get(draw_ordinal, ())
                                if decision.observation.drawn_tile is not None else ())
                else:
                    if draw_ordinal in _DRAW_ORDINALS:
                        tags.append("draw_" + str(draw_ordinal))
                    if any(isinstance(item.action, Hu) for item in analysis.legal_candidates):
                        tags.append("draw_hu")
                    if any(isinstance(item.action, Gang) for item in analysis.legal_candidates):
                        tags.append("draw_gang")
            elif decision.observation.phase in ("response_peng", "response_chi"):
                if target_draws is None and len(analysis.legal_candidates) > 1:
                    tags.append(decision.observation.phase + "_actionable")
            else:
                raise ValueError("未知本人动作窗口")
            for tag in tags:
                # 每种标签只取首次命中的窗口；标签来自行动前公开事实。
                if tag in seen_tags:
                    continue
                seen_tags.add(tag)
                if decision.window_key in by_window:
                    selected[by_window[decision.window_key]][3].append(tag)
                else:
                    by_window[decision.window_key] = len(selected)
                    selected.append((world, frame, decision, [tag]))
        world = engine.advance(world, frame.revision, tuple(
            SimulationChoice(item.window_key,
                             choose_reference_action(rules, item, mode="shape"))
            for item in frame.decisions
        ))
    raise ValueError("选根续打超过 500 帧")


def audit(*, start_seed: int, seeds: int, worlds_per_root: int,
          selection_report: dict | None = None,
          selection_tag: str | None = None) -> dict:
    """全部合法臂同隐藏世界配对，并分别核互斥事件和四座净积分。"""

    if start_seed < 0 or seeds < 1 or worlds_per_root < 1:
        raise ValueError("教师抽样范围无效")
    selected_by_seed: dict[int, dict[int, tuple[str, ...]]] = {}
    selected_hashes: dict[tuple[int, int], str] = {}
    if selection_report is not None:
        if (selection_report.get("scope") !=
                "result_blind_opportunity_root_selection_not_outcome_or_probability"
                or selection_report.get("reference") != "shape"
                or selection_report.get("rule_config") !=
                {"BaseScore": 1, "YouCaiBiKao": False}
                or selection_report.get("start_seed") != start_seed
                or selection_report.get("requested_seeds") != seeds):
            raise ValueError("机会选根报告的范围、配置或参考者与教师不一致")
        for row in selection_report["selected_roots"]:
            tags = tuple(tag for tag in row["tags"]
                         if selection_tag is None or tag == selection_tag)
            if not tags:
                continue
            seed, index = row["seed"], row["own_draw_index"]
            if (seed, index) in selected_hashes:
                raise ValueError("同一种子的本人摸牌序号重复选根")
            selected_by_seed.setdefault(seed, {})[index] = tags
            selected_hashes[(seed, index)] = row["observation_sha256"]
    elif selection_tag is not None:
        raise ValueError("选择标签需要结果盲机会选根报告")
    rules = HangmaRules(RuleConfig("hangma-mvp-v10-public-counts", 1, False))
    engine = SimulationEngine(rules)
    limits = ValueAnalysisLimits(max_expansions=8192)
    rows = []
    tag_counts: Counter[str] = Counter()
    action_worlds = 0
    for seed in range(start_seed, start_seed + seeds):
        if selection_report is not None and seed not in selected_by_seed:
            continue
        prefix = "vip-p3-opportunity" if selection_report is not None else "vip-p3-all-action"
        spec = MatchSpec(
            match_id=f"{prefix}-{seed}",
            scenario_id=f"{prefix}-{seed}",
            config=TournamentConfig(1, 1, rules.config, TimingConfig(1.0, 1.0, 3.0)),
            seed=seed, initial_dealer=0, initial_scores=(0, 0, 0, 0),
        )
        for world, frame, decision, tags in _selected_roots(
            engine, rules, engine.start(spec),
            target_draws=(selected_by_seed[seed] if selection_report is not None else None),
        ):
            observation = decision.observation
            analysis = rules.analyze(observation, route_limits=limits)
            roots = analysis.conditional_roots
            if (analysis.completeness is not RuleCompleteness.COMPLETE or roots is None
                    or tuple(root.action_key for root in roots) != tuple(
                        item.action_key for item in analysis.legal_candidates)
                    or any(root.gap_kind is not None for root in roots)):
                raise ValueError("选中窗口的同次合法候选与条件根不完整")
            candidates = analysis.legal_candidates
            root_id = hashlib.sha256(repr(observation).encode("utf-8")).hexdigest()
            if selection_report is not None:
                selected_indexes = [
                    index for index, selected_tags in selected_by_seed[seed].items()
                    if tuple(tags) == selected_tags
                ]
                if len(selected_indexes) != 1 or root_id != selected_hashes[
                    (seed, selected_indexes[0])
                ]:
                    raise ValueError("机会根玩家观察与冻结扫描身份不一致")
            arms = {item.action_key: [] for item in candidates}
            # 摸牌和响应窗均使用同一观察下的相关隐藏世界；每个样本的
            # 全部合法臂共享同一个重采样世界，不把动作世界当独立根。
            sample_count = worlds_per_root
            for sample in range(sample_count):
                hidden = engine.resample_public_consistent_hidden_world(
                    world, focal_seat=0,
                    sample_key=f"{prefix}-{seed}-{sample}",
                )
                sampled_frame = engine.frame(hidden)
                focal = [item for item in sampled_frame.decisions
                         if item.window_key == decision.window_key]
                if len(focal) != 1 or focal[0].observation != observation:
                    raise ValueError("相关世界改变本座依法可见观察或窗口")
                for candidate in candidates:
                    choices = tuple(SimulationChoice(
                        item.window_key,
                        candidate.action if item.window_key == decision.window_key else
                        choose_reference_action(rules, item, mode="shape"),
                    ) for item in sampled_frame.decisions)
                    after = engine.advance(hidden, sampled_frame.revision, choices)
                    event = _first_event(
                        engine, rules, after, seat=0, reference="shape",
                        include_next_observation=True,
                    )
                    terminal = _finish_hand(engine, rules, after, reference="shape")
                    if event["kind"] in ("self_win", "other_win", "draw") and (
                        event["score_delta"] != terminal["score_delta"]
                    ):
                        raise ValueError("首次终局事件与完整单局四座结算不一致")
                    arms[candidate.action_key].append({
                        "sample": sample,
                        "first_event_key": _event_key(event),
                        "first_event": event,
                        "terminal": terminal,
                    })
                    action_worlds += 1
            if (any(len(values) != sample_count for values in arms.values())
                    or any(action_key(item.action) != item.action_key for item in candidates)):
                raise ValueError("全合法臂或相关世界计数不守恒")
            rows.append({
                "seed": seed,
                "root_id": root_id,
                "phase": observation.phase,
                "tags": tags,
                "sampling_mode": "resampled_same_observation",
                "sample_count": sample_count,
                "observation": observation_to_json(observation),
                "legal_action_keys": [item.action_key for item in candidates],
                "outcomes_by_action": arms,
            })
            tag_counts.update(tags)
    if selection_report is not None and len(rows) != len(selected_hashes):
        raise ValueError("冻结机会根未全部在同一参考续打路径到达")
    report = {
        "scope": "P3_offline_teacher_labels_only_not_candidate_policy_value",
        "rule_config": {"BaseScore": 1, "YouCaiBiKao": False},
        "reference": "shape",
        "start_seed": start_seed,
        "requested_seeds": seeds,
        "worlds_per_root": worlds_per_root,
        "root_count": len(rows),
        "action_worlds": action_worlds,
        "tag_counts": dict(sorted(tag_counts.items())),
        "rows": rows,
    }
    if selection_report is not None:
        report["selection_scope"] = selection_report["scope"]
        report["selection_tag"] = selection_tag
        report["selection_root_count"] = len(selected_hashes)
    return report


def main() -> None:
    """输出独立于 R18 的全合法动作教师账；证据文件由调用方保存。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-seed", type=int, default=1001)
    parser.add_argument("--seeds", type=int, default=1)
    parser.add_argument("--worlds-per-root", type=int, default=2)
    parser.add_argument("--selection-file", type=str)
    parser.add_argument("--selection-tag", type=str)
    args = parser.parse_args()
    selection = None if args.selection_file is None else json.loads(
        open(args.selection_file, encoding="utf-8").read())
    start_seed = args.start_seed if selection is None else selection["start_seed"]
    seeds = args.seeds if selection is None else selection["requested_seeds"]
    print(json.dumps(audit(
        start_seed=start_seed, seeds=seeds,
        worlds_per_root=args.worlds_per_root,
        selection_report=selection, selection_tag=args.selection_tag,
    ), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
