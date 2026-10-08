"""复算 R18 P4 配对试点的事件级结果，不改变已冻结的首轮结果。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution'

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
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))
sys.path.insert(0, str(HERE))

import r18_p4_counterfactual_pilot as pilot  # noqa: E402
from hangma_bot.offline.evaluate import (  # noqa: E402
    frame_observation_summary,
    resume_match,
)
from hangma_bot.offline.forced_action import ForceFirstActionPolicy  # noqa: E402
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2  # noqa: E402
from hangma_bot.simulation import SimulationChoice, SimulationEngine  # noqa: E402


PILOT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p4-counterfactual-pilot-01-20260922')
SUPERSEDED = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p4-counterfactual-pilot-01-20260922/event-audit.json')
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p4-counterfactual-pilot-01-20260922/event-audit-v2.json')


class RecordingEngine:
    """只包裹模拟器公开接口，并保留最近一次不透明世界供最终导出。"""

    def __init__(self, rules: Any, rules_hash: str) -> None:
        self._inner = SimulationEngine(rules, rules_hash=rules_hash)
        self.world: Any = None

    def from_replay(self, row: dict[str, Any]) -> Any:
        self.world = self._inner.from_replay(row)
        return self.world

    def frame(self, world: Any) -> Any:
        return self._inner.frame(world)

    def advance(self, world: Any, revision: int, choices: tuple[Any, ...]) -> Any:
        self.world = self._inner.advance(world, revision, choices)
        return self.world

    def export_hand(self) -> dict[str, Any]:
        return self._inner.export_hand(self.world, 1)


async def trace_arm(
    row: dict[str, Any], focal_seat: int, forced_action_key: str
) -> dict[str, Any]:
    """重放一条臂并只保留动作序列与最终结算，不落隐藏世界。"""

    engine = RecordingEngine(pilot.RULES, str(row["rules_hash"]))
    world = engine.from_replay(row)
    frame = engine.frame(world)
    target = frame.decisions[0].window_key
    policies: list[Any] = [
        ComparableHeuristicPolicyV2(monotonic=lambda: 800.0) for _ in range(4)
    ]
    forced = ForceFirstActionPolicy(
        policies[focal_seat],
        target_window=target,
        forced_action_key=forced_action_key,
        policy_id="r18-p4-event-audit-" + forced_action_key,
    )
    policies[focal_seat] = forced
    outcome = await resume_match(
        engine=engine,
        world=world,
        policies_by_seat=tuple(policies),
        rules=pilot.RULES,
        choice_factory=SimulationChoice,
        config=pilot.driver_config(),
        now_monotonic=lambda: 800.0,
        wall_clock=None,
        remaining_schedule={"declared_endpoint": "hand_complete"},
        stage_snapshot={
            "observation_summary": frame_observation_summary(frame),
            "match_spec": {"match_id": row["initial"]["world_payload"]["match_id"]},
        },
        value_limits=None,
    )
    hand = engine.export_hand()
    return {
        "status": outcome.status,
        "force_count": forced.force_count,
        "actions": [
            {
                "seat": item.seat,
                "phase": item.window_key["phase"],
                "action_key": item.action_key,
                "fallback_reason": item.fallback_reason,
            }
            for item in outcome.decisions
        ],
        "final_scores": list(outcome.final_scores or ()),
        "winner_seat": hand["winner_seat"],
        "is_draw": hand["is_draw"],
        "fan": hand["fan"],
        "details": list(hand["details"]),
        "score_delta": list(hand["score_delta"]),
    }


async def trace_pair(case: dict[str, Any], pair_index: int) -> dict[str, Any]:
    row = pilot.build_world_row(case, pair_index)
    focal = int(row["initial"]["dealer_seat"])
    return {
        "pair_index": pair_index,
        "focal_seat": focal,
        "world_sha256": pilot.digest_value(row["initial"]["world_payload"]),
        "hu": await trace_arm(row, focal, "hu"),
        "piao": await trace_arm(row, focal, "discard:白"),
    }


def main() -> None:
    """核对 64 对结果身份和最终番型，并写聚合事件证据。"""

    if OUT.exists():
        raise SystemExit("event-audit.json 已存在；拒绝覆盖")
    manifest = json.loads((_project_file(_PROJECT_ROOT, PILOT / "manifest.json")).read_text(encoding="utf-8"))
    result = json.loads((_project_file(_PROJECT_ROOT, PILOT / "result.json")).read_text(encoding="utf-8"))
    pilot.verify_manifest(manifest)
    case = pilot.read_case()
    traces = [asyncio.run(trace_pair(case, index)) for index in range(1, pilot.PAIRS + 1)]
    expected_worlds = {
        item["pair_index"]: item["world_sha256"] for item in result["pairs"]
    }
    world_identity_ok = all(
        expected_worlds[item["pair_index"]] == item["world_sha256"] for item in traces
    )
    hu_details = Counter(tuple(item["hu"]["details"]) for item in traces)
    piao_details = Counter(tuple(item["piao"]["details"]) for item in traces)
    piao_action_shapes = Counter(
        tuple((action["seat"], action["phase"], action["action_key"])
              for action in item["piao"]["actions"])
        for item in traces
    )
    audit = {
        "schema": "r18-p4-counterfactual-event-audit/2",
        "supersedes_event_audit_sha256": hashlib.sha256(
            SUPERSEDED.read_bytes()
        ).hexdigest(),
        "supersession_reason": "v1 的 second_focal_action 把响应窗口 pass 误称为下一次本人摸牌动作；v2 按 phase=draw 过滤",
        "pilot_manifest_sha256": hashlib.sha256(
            (_project_file(_PROJECT_ROOT, PILOT / "manifest.json")).read_bytes()
        ).hexdigest(),
        "pilot_result_sha256": hashlib.sha256(
            (_project_file(_PROJECT_ROOT, PILOT / "result.json")).read_bytes()
        ).hexdigest(),
        "audit_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "world_identity_ok": world_identity_ok,
        "pairs": len(traces),
        "all_complete": all(
            item[arm]["status"] == "complete" and item[arm]["force_count"] == 1
            for item in traces for arm in ("hu", "piao")
        ),
        "hu_fan_histogram": dict(sorted(Counter(item["hu"]["fan"] for item in traces).items())),
        "piao_fan_histogram": dict(sorted(Counter(item["piao"]["fan"] for item in traces).items())),
        "hu_details_histogram": [
            {"details": list(details), "count": count}
            for details, count in sorted(hu_details.items())
        ],
        "piao_details_histogram": [
            {"details": list(details), "count": count}
            for details, count in sorted(piao_details.items())
        ],
        "piao_decision_count_histogram": dict(sorted(
            Counter(len(item["piao"]["actions"]) for item in traces).items()
        )),
        "piao_unique_full_action_sequences": len(piao_action_shapes),
        "piao_next_focal_draw_action_histogram": dict(sorted(Counter(
            next(
                (
                    action["action_key"]
                    for action in item["piao"]["actions"][1:]
                    if action["seat"] == item["focal_seat"]
                    and action["phase"] == "draw"
                ),
                None,
            )
            for item in traces
        ).items(), key=lambda pair: str(pair[0]))),
        "interpretation": "飘白后牌局继续；在三家各完成一轮动作后焦点再次摸牌并由稳定V2胡牌。64对同分来自任意牌胡与同一确定番型在本批均兑现，不是弃白动作立即结算。",
        "hidden_bank_read": False,
        "selection_eligible": False,
        "release_eligible": False,
    }
    pilot.write_json(OUT, audit)
    pilot.verify_manifest(manifest)
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
