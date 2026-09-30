"""将结果盲选中的机会动作与冻结 R18 首选作同世界单局积分对照。

这只是冻结 ``shape`` 续打者下的离线诊断，不是候选策略评估。
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.kernel.actions import WindowKey, WindowPhase
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import CompetitionContext
from hangma_bot.kernel.serialization import observation_from_json
from hangma_bot.policy.action_value_policy import build_scoring_view
from hangma_bot.policy.action_value_seeds import ActionValueScorer
from hangma_bot.policy.interface import DecisionRequest
from hangma_bot.policy.r18_integrated_positive_v2 import (
    R18_INTEGRATED_POSITIVE_V2_SOURCE,
)


def compare(selection: dict, teacher: dict) -> dict:
    """复核根身份，并用行动前评分确定 R18 首选及逐世界积分差。"""

    if (selection.get("scope") !=
            "result_blind_opportunity_root_selection_not_outcome_or_probability"
            or teacher.get("scope") !=
            "P3_offline_teacher_labels_only_not_candidate_policy_value"
            or teacher.get("selection_tag") != "high_fan_witness"
            or teacher.get("continuation_reference", "shape") not in
            ("shape", "r18_frozen")):
        raise ValueError("输入不是高番机会层的冻结选根与教师账")
    selected = {(row["seed"], row["observation_sha256"]): row
                for row in selection["selected_roots"]
                if "high_fan_witness" in row["tags"]}
    if len(selected) != teacher["root_count"]:
        raise ValueError("选根与教师账根数不一致")
    rules = HangmaRules(RuleConfig("hangma-mvp-v10-public-counts", 1, False))
    scorer = ActionValueScorer("vip-p3-r18-opportunity-reference",
                               R18_INTEGRATED_POSITIVE_V2_SOURCE)
    limits = ValueAnalysisLimits(max_expansions=8192)
    rows = []
    for teacher_row in teacher["rows"]:
        observation = observation_from_json(teacher_row["observation"])
        digest = hashlib.sha256(repr(observation).encode("utf-8")).hexdigest()
        key = (teacher_row["seed"], digest)
        if (key not in selected or digest != teacher_row["root_id"]
                or teacher_row["sampling_mode"] != "resampled_same_observation"):
            raise ValueError("教师根与冻结行动前玩家观察不一致")
        target = selected.pop(key)
        analysis = rules.analyze(observation, route_limits=limits)
        window = WindowKey(observation.game_id, observation.round_no,
                           observation.snapshot_seq, WindowPhase(observation.phase),
                           observation.seat)
        request = DecisionRequest(
            observation=observation,
            competition=CompetitionContext(
                tournament_id="vip-p3-opportunity-sim", stage_no=None,
                stage_role=None, stage_total=None, participant_rank=None,
                ranking=(), observed_at_unix_ms=0,
            ),
            rules=analysis, decision_id=f"vip-p3-opportunity:{digest}",
            trigger_seq=window.trigger_seq, window_key=window,
            rejected_attempts=(),
        )
        scored = scorer.score(build_scoring_view(request, value_limits=limits))
        if scored.status != "SCORED" or not scored.entries:
            raise ValueError("R18 在教师根无法评分")
        parent = min(scored.entries, key=lambda item: (-item.score, item.action_key))
        outcomes = teacher_row["outcomes_by_action"]
        if (set(outcomes) != set(teacher_row["legal_action_keys"])
                or target["action_key"] not in outcomes
                or parent.action_key not in outcomes):
            raise ValueError("冻结机会动作或 R18 首选不在全合法臂中")
        selected_values = [item["terminal"]["score_delta"][observation.seat]
                           for item in outcomes[target["action_key"]]]
        parent_values = [item["terminal"]["score_delta"][observation.seat]
                         for item in outcomes[parent.action_key]]
        if (len(selected_values) != teacher_row["sample_count"]
                or len(parent_values) != teacher_row["sample_count"]):
            raise ValueError("配对隐藏世界数量不一致")
        delta = [a - b for a, b in zip(selected_values, parent_values)]
        rows.append({
            "seed": teacher_row["seed"],
            "own_draw_index": target["own_draw_index"],
            "root_id": digest,
            "high_fan_capacity": target["high_fan_capacity"],
            "high_fan_codes": target["high_fan_codes"],
            "selected_action": target["action_key"],
            "r18_top_action": parent.action_key,
            "r18_top_score": parent.score,
            "sample_count": len(delta),
            "selected_score_delta": selected_values,
            "r18_score_delta": parent_values,
            "paired_delta": delta,
            "paired_mean_delta": sum(delta) / len(delta),
        })
    if selected:
        raise ValueError("有冻结机会根没有进入教师账")
    return {
        "scope": "diagnostic_shape_continuation_not_candidate_policy_value",
        "rule_config": selection["rule_config"],
        "continuation_reference": teacher.get("continuation_reference", "shape"),
        "selected_root_count": len(rows),
        "same_action_roots": sum(row["selected_action"] == row["r18_top_action"]
                                 for row in rows),
        "r18_source_sha256": hashlib.sha256(
            R18_INTEGRATED_POSITIVE_V2_SOURCE.encode("utf-8")).hexdigest(),
        "rows": sorted(rows, key=lambda row: row["seed"]),
    }


def _load(path: Path) -> dict:
    """读取 JSON 或 gzip JSON；不执行输入中的代码。"""

    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            return json.load(handle)
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def main() -> None:
    """从冻结选根和全动作教师文件打印可复算的 R18 配对诊断。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection-file", type=Path, required=True)
    parser.add_argument("--teacher-file", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(compare(_load(args.selection_file), _load(args.teacher_file)),
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
