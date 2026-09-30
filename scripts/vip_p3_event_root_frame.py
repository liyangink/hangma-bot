"""结果盲冻结早、中、晚巡与响应窗口的 VIP 首事件训练抽样框。

只沿冻结 R18 参考者的单局路径读取当下 PlayerObservation；
不重采样隐藏世界，不强制其他首动作，也不读取这些动作的未来结局。
固定本人正常摸牌序号、墙余阈值与每种可行动响应的首次窗口构成抽样层。
入框条件依赖所选参考者的到达路径，不能外推为自然赛事总体。
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import RuleCompleteness
from hangma_bot.kernel.config import RuleConfig, TimingConfig, TournamentConfig
from hangma_bot.kernel.serialization import observation_to_json
from hangma_bot.offline.vip_reference import choose_reference_action
from hangma_bot.simulation import MatchSpec, SimulationChoice, SimulationEngine


_DRAW_ORDINALS = (1, 6, 10, 12)
_WALL_THRESHOLDS = (40, 28)
_SCENARIO_PREFIX = "vip-p3-event-frame"
_REFERENCE = "r18_frozen"


def scan(*, start_seed: int, seeds: int) -> dict:
    """按当前观察选根；只输出预结局身份与行动前分层。"""

    if type(start_seed) is not int or start_seed < 0 or type(seeds) is not int or seeds < 1:
        raise ValueError("事件抽样框牌山种子范围无效")
    rules = HangmaRules(RuleConfig("hangma-mvp-v10-public-counts", 1, False))
    engine = SimulationEngine(rules)
    selected = []
    reached = Counter()
    root_tags = Counter()
    observed_windows = Counter()
    for seed in range(start_seed, start_seed + seeds):
        spec = MatchSpec(
            match_id=f"{_SCENARIO_PREFIX}-{seed}",
            scenario_id=f"{_SCENARIO_PREFIX}-{seed}",
            config=TournamentConfig(1, 1, rules.config, TimingConfig(1.0, 1.0, 3.0)),
            seed=seed, initial_dealer=seed % 4,
            initial_scores=(0, 0, 0, 0),
        )
        world = engine.start(spec)
        own_normal_draw_index = 0
        first_response = set()
        first_special = set()
        first_wall_threshold = set()
        for _ in range(500):
            frame = engine.frame(world)
            if frame.blocked_reason is not None:
                raise ValueError("选根参考路径被模拟器阻塞: " + frame.blocked_reason)
            if frame.final_scores is not None:
                break
            for decision in frame.decisions:
                if decision.window_key.seat != 0:
                    continue
                observation = decision.observation
                analysis = rules.analyze(observation)
                if analysis.completeness is not RuleCompleteness.COMPLETE:
                    raise ValueError("选根当前合法动作分析不完整")
                keys = [item.action_key for item in analysis.legal_candidates]
                if not keys:
                    raise ValueError("选根本人动作窗口没有合法候选")
                tags = []
                if observation.phase == "draw":
                    observed_windows["draw"] += 1
                    if observation.drawn_tile is not None and not observation.gang_draw:
                        own_normal_draw_index += 1
                        if own_normal_draw_index in _DRAW_ORDINALS:
                            tags.append(f"normal_draw_{own_normal_draw_index}")
                    if "hu" in keys and "hu" not in first_special:
                        first_special.add("hu")
                        tags.append("first_current_hu")
                    if any(key.startswith("gang:") for key in keys) and "gang" not in first_special:
                        first_special.add("gang")
                        tags.append("first_gang_choice")
                elif observation.phase in ("response_peng", "response_chi"):
                    observed_windows[observation.phase] += 1
                    if len(keys) > 1 and observation.phase not in first_response:
                        first_response.add(observation.phase)
                        tags.append("first_actionable_" + observation.phase)
                else:
                    raise ValueError("选根遇到未知本人动作窗口")
                if (observation.remaining_tile_count is not None
                        and (observation.phase == "draw" or len(keys) > 1)):
                    for threshold in _WALL_THRESHOLDS:
                        if (observation.remaining_tile_count <= threshold
                                and threshold not in first_wall_threshold):
                            first_wall_threshold.add(threshold)
                            tags.append(f"first_wall_le_{threshold}")
                if not tags:
                    continue
                root_id = hashlib.sha256(repr(observation).encode()).hexdigest()
                selected.append({
                    "seed": seed, "frame_revision": frame.revision,
                    "initial_dealer": seed % 4,
                    "root_id": root_id, "phase": observation.phase,
                    "own_normal_draw_index": (own_normal_draw_index
                                              if observation.phase == "draw" else None),
                    "remaining_tile_count": observation.remaining_tile_count,
                    "tags": tags, "legal_action_keys": keys,
                    "observation": observation_to_json(observation),
                })
                root_tags.update(tags)
            world = engine.advance(world, frame.revision, tuple(
                SimulationChoice(item.window_key,
                                 choose_reference_action(rules, item, mode=_REFERENCE))
                for item in frame.decisions
            ))
        else:
            raise ValueError("选根参考路径超过 500 帧")
        for ordinal in _DRAW_ORDINALS:
            reached[f"normal_draw_{ordinal}"] += own_normal_draw_index >= ordinal
        for phase in ("response_peng", "response_chi"):
            reached[f"actionable_{phase}"] += phase in first_response
        for threshold in _WALL_THRESHOLDS:
            reached[f"first_wall_le_{threshold}"] += threshold in first_wall_threshold
    identities = [(row["seed"], row["frame_revision"], row["root_id"])
                  for row in selected]
    if len(set(identities)) != len(identities):
        raise ValueError("事件抽样框观察根身份重复")
    return {
        "scope": "vip_p3_pre_outcome_event_root_frame_not_training_result",
        "scenario_prefix": _SCENARIO_PREFIX,
        "rule_config": {"BaseScore": 1, "YouCaiBiKao": False},
        "selection_reference": _REFERENCE,
        "initial_dealer_rule": "seed_mod_4",
        "start_seed": start_seed, "requested_seeds": seeds,
        "normal_draw_ordinals": list(_DRAW_ORDINALS),
        "first_wall_thresholds": list(_WALL_THRESHOLDS),
        "root_count": len(selected),
        "natural_seed_count": len({row["seed"] for row in selected}),
        "reached_counts": dict(sorted(reached.items())),
        "observed_window_counts": dict(sorted(observed_windows.items())),
        "selected_tag_counts": dict(sorted(root_tags.items())),
        "selected_roots": selected,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-seed", type=int, required=True)
    parser.add_argument("--seeds", type=int, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    data = (json.dumps(scan(start_seed=args.start_seed, seeds=args.seeds),
                       ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode()
    if args.output is None:
        print(data.decode(), end="")
    elif args.output.suffix == ".gz":
        with args.output.open("wb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0,
                               compresslevel=9) as stream:
                stream.write(data)
    else:
        args.output.write_bytes(data)


if __name__ == "__main__":
    main()
