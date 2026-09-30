"""从已冻结行动前事件抽样框选择训练、诊断与未开确认根。

每个标签使用预定哈希筛选率；同一根命中任一标签即纳入，
独立标签的根包含概率按并集计算。按原始牌山种子分割三池，
使同一种子的多个动作窗口不会跨池泄漏。此脚本不读结局。
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

from hangma_bot.kernel.serialization import observation_from_json


_TAG_RATES = {
    "normal_draw_1": 0.125,
    "normal_draw_6": 0.25,
    "normal_draw_10": 0.5,
    "normal_draw_12": 1.0,
    "first_wall_le_40": 0.5,
    "first_wall_le_28": 1.0,
    "first_actionable_response_peng": 0.125,
    "first_actionable_response_chi": 0.125,
    "first_current_hu": 0.5,
    "first_gang_choice": 1.0,
}
_ROOT_FIELDS = frozenset({
    "seed", "frame_revision", "initial_dealer", "root_id", "phase", "own_normal_draw_index",
    "remaining_tile_count", "tags", "legal_action_keys", "observation",
})


def _uniform(key: str) -> float:
    """用固定 SHA-256 前 64 位得到半开区间 [0,1) 的分层数。"""

    return int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big") / 2**64


def select(frame: dict, source_sha256: str) -> dict:
    """从行动前根中结果盲抽样；同一牌山种子始终留在同一池。"""

    if (frame.get("scope") != "vip_p3_pre_outcome_event_root_frame_not_training_result"
            or frame.get("scenario_prefix") != "vip-p3-event-frame"
            or frame.get("selection_reference") != "r18_frozen"
            or frame.get("initial_dealer_rule") != "seed_mod_4"
            or frame.get("rule_config") != {"BaseScore": 1, "YouCaiBiKao": False}
            or frame.get("root_count") != len(frame.get("selected_roots", ()))
            or len(source_sha256) != 64):
        raise ValueError("事件根抽样框身份或数量不符")
    selected = []
    split_seeds = {"fit": set(), "diagnostic": set(), "confirmation": set()}
    seen = set()
    for row in frame["selected_roots"]:
        if set(row) != _ROOT_FIELDS:
            raise ValueError("事件根携带非行动前字段或缺少身份字段")
        seed = row["seed"]
        if type(seed) is not int or not frame["start_seed"] <= seed < (
            frame["start_seed"] + frame["requested_seeds"]
        ):
            raise ValueError("事件根牌山种子超出冻结框")
        if row["initial_dealer"] != seed % 4:
            raise ValueError("事件根初始庄家轮换身份不符")
        observation = observation_from_json(row["observation"])
        if (observation.dealer_seat != row["initial_dealer"]
                or observation.phase != row["phase"]
                or observation.remaining_tile_count != row["remaining_tile_count"]):
            raise ValueError("事件根玩家观察与行动前分层字段不符")
        root_id = hashlib.sha256(repr(observation).encode()).hexdigest()
        identity = (seed, row["frame_revision"], root_id)
        if root_id != row["root_id"] or identity in seen:
            raise ValueError("事件根玩家观察摘要或窗口身份重复")
        seen.add(identity)
        if (not isinstance(row["tags"], list) or not row["tags"]
                or len(row["tags"]) != len(set(row["tags"]))
                or any(tag not in _TAG_RATES for tag in row["tags"])):
            raise ValueError("事件根出现未知或重复行动前标签")
        matched = [tag for tag in row["tags"] if _uniform(
            f"vip-p3-event-select:{seed}:{row['frame_revision']}:{tag}"
        ) < _TAG_RATES[tag]]
        if not matched:
            continue
        chance = 1.0 - math.prod(1.0 - _TAG_RATES[tag] for tag in row["tags"])
        if not 0 < chance <= 1:
            raise ValueError("事件根包含概率无效")
        quantile = _uniform(f"vip-p3-event-split:{seed}")
        split = "fit" if quantile < 0.6 else (
            "diagnostic" if quantile < 0.8 else "confirmation")
        split_seeds[split].add(seed)
        selected.append({**row, "split": split,
                         "inclusion_probability": chance,
                         "matched_selection_tags": matched})
    counts = Counter(row["split"] for row in selected)
    tags = {split: dict(sorted(Counter(
        tag for row in selected if row["split"] == split for tag in row["tags"]
    ).items())) for split in split_seeds}
    return {
        "scope": "vip_p3_pre_outcome_event_root_selection_no_teacher_results",
        "frame_sha256": source_sha256,
        "scenario_prefix": frame["scenario_prefix"],
        "rule_config": frame["rule_config"],
        "selection_reference": frame["selection_reference"],
        "initial_dealer_rule": frame["initial_dealer_rule"],
        "start_seed": frame["start_seed"],
        "requested_seeds": frame["requested_seeds"],
        "population_root_count": frame["root_count"],
        "tag_inclusion_rates": _TAG_RATES,
        "split_seed_quantiles": {"fit": [0, 0.6],
                                 "diagnostic": [0.6, 0.8],
                                 "confirmation": [0.8, 1]},
        "selected_root_count": len(selected),
        "selected_split_counts": dict(sorted(counts.items())),
        "selected_split_seed_counts": {split: len(seeds) for split, seeds in
                                       split_seeds.items()},
        "selected_tag_counts_by_split": tags,
        "selected_roots": selected,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frame", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    raw = args.frame.read_bytes()
    frame = json.loads(gzip.decompress(raw) if args.frame.suffix == ".gz" else raw)
    data = (json.dumps(select(frame, hashlib.sha256(raw).hexdigest()),
                       ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode()
    if args.output is None:
        print(data.decode(), end="")
    elif args.output.suffix == ".gz":
        with args.output.open("wb") as target:
            with gzip.GzipFile(fileobj=target, mode="wb", filename="", mtime=0,
                               compresslevel=9) as stream:
                stream.write(data)
    else:
        args.output.write_bytes(data)


if __name__ == "__main__":
    main()
