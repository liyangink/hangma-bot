#!/usr/bin/env python3
"""G73：审计玄武同窗打单张非财神字牌、R18 v2 改打数牌的评分差来源。"""

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

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

import c31_action_layer_gap as c31
from hangma_bot.kernel.serialization import observation_from_json
from hangma_bot.kernel.actions import WindowKey, WindowPhase
from hangma_bot.kernel.observation import CompetitionContext
from hangma_bot.policy.interface import DecisionRequest
from hangma_bot.policy.action_value_policy import build_scoring_view
from hangma_bot.policy.action_value_seeds import ActionValueScorer


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g61-strong-draw-action-atlas-20260927')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g73-single-honor-score-audit-20260928/result.json')
HONORS = frozenset(("东", "南", "西", "北", "中", "发"))
TRACE_FIELDS = ("base_score", "wealth_part", "wealth_discard_part", "river_part",
                "risk_units", "style_part")


def sha(path: Path) -> str:
    """绑定此前结果盲动作证据和本次代码。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity(row: dict) -> tuple:
    """强手与房也入键，避免两名强手共房时误并。"""

    return row["peer"], row["room"], row["game_id"], row["round_no"], row["draw_seq"]


def target(row: dict) -> bool:
    """固定已观察到的现象；不按终局成绩、未来牌或评分来源选窗。"""

    return (row["peer"] == "xuanwu_2346"
            and row["delta"]["ordinary_delta"] == 0
            and row["delta"]["combined_delta"] == 0
            and row["strong_action"].removeprefix("discard:") in HONORS
            and row["parent_action"].startswith("discard:")
            and row["parent_action"].removeprefix("discard:") not in HONORS
            and row["parent_action"] != "discard:白")


def scored_entries(window: dict, scorer: ActionValueScorer) -> dict:
    """只用本人可见观察、生产规则和冻结父代源码重新给分。"""

    observation = observation_from_json(window["observation"])
    rules = c31.RULES.analyze(observation, value_limits=c31.VALUE_LIMITS)
    request = DecisionRequest(
        observation=observation,
        competition=CompetitionContext(
            tournament_id="g73-official-replay", stage_no=None, stage_role=None,
            stage_total=None, participant_rank=None, ranking=(), observed_at_unix_ms=0),
        rules=rules, decision_id="g73:" + str(observation.snapshot_seq),
        trigger_seq=observation.snapshot_seq,
        window_key=WindowKey(game_id=observation.game_id, round_no=observation.round_no,
                             trigger_seq=observation.snapshot_seq,
                             phase=WindowPhase.DRAW, seat=observation.seat),
        rejected_attempts=(),
    )
    plan = scorer.score(build_scoring_view(request, value_limits=c31.VALUE_LIMITS))
    if plan.status != "SCORED" or not plan.entries:
        raise ValueError("冻结父代未能评分")
    return {entry.action_key: entry for entry in plan.entries}


def main() -> None:
    if OUT.exists():
        raise SystemExit("G73 审计已存在，拒绝覆盖")
    profile_path = _project_file(_PROJECT_ROOT, SOURCE / "shape_profile.json")
    batch_path = _project_file(_PROJECT_ROOT, SOURCE / "result.json")
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    batch = json.loads(batch_path.read_text(encoding="utf-8"))
    if (profile["schema"] != "g61-strong-draw-shape-profile/1"
            or profile["batch_sha256"] != sha(batch_path)
            or profile["outcome_labels_opened"] is not False
            or batch["outcome_labels_opened"] is not False):
        raise ValueError("G61 动作事实或结果盲边界漂移")
    targets = {identity(row): row for row in profile["strict_discard_rows"] if target(row)}
    if len(targets) != 117:
        raise ValueError("玄武单张字牌现象窗数漂移")
    scorer = ActionValueScorer("g73-frozen-r18", c31.R18_INTEGRATED_POSITIVE_V2_SOURCE)
    rows = []
    room_counts: dict[str, Counter] = defaultdict(Counter)
    found = set()
    for unit, record in sorted(batch["units"].items()):
        peer, room = unit.split("/", 1)
        if peer != "xuanwu_2346":
            continue
        path = _project_file(_PROJECT_ROOT, SOURCE / "rooms" / (peer + "--" + room) / "windows.json")
        if sha(path) != record["windows_sha256"]:
            raise ValueError("G61 逐窗来源摘要漂移")
        for window in json.loads(path.read_text(encoding="utf-8"))["windows"]:
            key = (peer, room, window["game_id"], window["round_no"], window["draw_seq"])
            selected = targets.get(key)
            if selected is None:
                continue
            if key in found or window["actual_action"] != selected["strong_action"] or window["parent_top_action"] != selected["parent_action"]:
                raise ValueError("G73 动作身份或唯一性漂移")
            found.add(key)
            honor = selected["strong_action"].split(":", 1)[1]
            held = window["observation"]["my_hand"].count(honor)
            entries = scored_entries(window, scorer)
            actual = entries[selected["strong_action"]]
            parent = entries[selected["parent_action"]]
            top = min(entries.values(), key=lambda item: (-item.score, item.action_key))
            gap = parent.score - actual.score
            if (top.action_key != selected["parent_action"]
                    or abs(gap - selected["parent_score_gap"]) > 1e-8):
                raise ValueError("冻结父代首选或分差与 G61 不符")
            if any(actual.trace.get(field) is None or parent.trace.get(field) is None
                   for field in TRACE_FIELDS):
                raise ValueError("冻结父代评分分量缺失")
            delta = {field: parent.trace[field] - actual.trace[field]
                     for field in TRACE_FIELDS}
            delta["residual"] = gap - sum(delta[field] for field in TRACE_FIELDS
                                           if field != "risk_units")
            rows.append({"key": list(key), "honor": honor, "honor_held": held,
                         "parent_action": selected["parent_action"],
                         "strong_action": selected["strong_action"],
                         "parent_score_gap": gap, "trace_parent_minus_strong": delta,
                         "ordinary_capacity_delta": selected["delta"]["ordinary_support_capacity_delta_same_layer"],
                         "ordinary_codes_delta": selected["delta"]["ordinary_support_codes_delta_same_layer"],
                         "white_before": selected["white_before"],
                         "wall_remaining": selected["wall_remaining"]})
            c = room_counts[room]
            c["target_windows"] += 1
            c["singleton_honor"] += held == 1
            c["white_zero"] += selected["white_before"] == 0
            c["capacity_higher"] += (selected["delta"]["ordinary_support_capacity_delta_same_layer"] or 0) > 0
            c["capacity_equal"] += selected["delta"]["ordinary_support_capacity_delta_same_layer"] == 0
            c["capacity_lower"] += (selected["delta"]["ordinary_support_capacity_delta_same_layer"] or 0) < 0
            c["code_higher"] += (selected["delta"]["ordinary_support_codes_delta_same_layer"] or 0) > 0
            c["score_gap_explained_by_river"] += delta["river_part"] >= gap
    if found != set(targets) or len(rows) != 117 or len(room_counts) != 15:
        raise ValueError("G73 目标窗或房间覆盖不完整")
    summary = sum(room_counts.values(), Counter())
    if summary["singleton_honor"] != 114:
        raise ValueError("G73 单张字牌数漂移")
    result = {"schema": "g73-single-honor-score-audit/1", "exploratory": True,
              "source_sha256": {"g61_shape": sha(profile_path), "g61_batch": sha(batch_path),
                                "parent": hashlib.sha256(c31.R18_INTEGRATED_POSITIVE_V2_SOURCE.encode()).hexdigest()},
              "script_sha256": sha(Path(__file__)), "rooms": len(room_counts),
              "summary": dict(sorted(summary.items())),
              "by_room": {room: dict(sorted(counts.items())) for room, counts in sorted(room_counts.items())},
              "rows": sorted(rows, key=lambda row: row["key"]),
              "boundary": "玄武实际动作只是同观察行为线索；分差分量与宽度不是完整桌收益，赛后结果未用于选窗。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"rooms": result["rooms"], "summary": result["summary"]},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
