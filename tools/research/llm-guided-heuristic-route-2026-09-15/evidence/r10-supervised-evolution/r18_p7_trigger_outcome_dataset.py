"""把 P7 安全扩样中的自然七对触发整理成可观测特征与配对结果。"""

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

from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ROOT = _PROJECT_ROOT
for path in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROUTE / "tools"), HERE):
    sys.path.insert(0, str(path))

import r18_p7_table_safety_topup as topup  # noqa: E402
from hangma_bot.application.audit_codec import decision_request_to_json  # noqa: E402
from hangma_bot.policy.action_value_policy import build_scoring_view  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402


OUT = topup.OUT / "natural-trigger-outcome-dataset.json"


def digest_value(value: Any) -> str:
    """返回稳定 JSON 值的 SHA-256。"""

    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def top(batch: Any) -> Any:
    """按正式排序返回首选评分项。"""

    return sorted(batch.entries, key=lambda item: (-item.score, item.action_key))[0]


def useful_total(items: Any) -> int:
    """求公开剩余估计总张数。"""

    return sum(int(item.remaining_estimate) for item in items)


def action_features(view: Any, action_key: str) -> dict[str, Any]:
    """抽取一个动作的规则事实；不重新计算规则。"""

    action = next(item for item in view.actions if item.action_key == action_key)
    return {
        "action_key": action.action_key,
        "shanten_after": action.shanten_after,
        "standard_shanten_after": action.standard_shanten_after,
        "seven_pairs_shanten_after": action.seven_pairs_shanten_after,
        "useful_tiles": [item.code for item in action.useful_tiles],
        "useful_total": useful_total(action.useful_tiles),
        "standard_useful_tiles": [item.code for item in action.standard_useful_tiles],
        "standard_useful_total": useful_total(action.standard_useful_tiles),
        "seven_pairs_useful_tiles": [item.code for item in action.seven_pairs_useful_tiles],
        "seven_pairs_useful_total": useful_total(action.seven_pairs_useful_tiles),
        "route_count": len(action.routes),
    }


def main() -> None:
    """重放所有已知触发来源并固化 29 个自然窗口。"""

    if OUT.exists():
        raise SystemExit("P7 自然触发结果数据集已存在；拒绝覆盖")
    manifest = topup.verify_manifest()
    result = json.loads((topup.OUT / "result.json").read_text(encoding="utf-8"))
    if result.get("status") != "INCONCLUSIVE_R18_P7_RETAIN_SPECIALIST":
        raise ValueError("P7 安全扩样结果状态漂移")
    contract = json.loads(topup.CONTRACT.read_text(encoding="utf-8"))
    candidate_source = topup.CANDIDATE.read_text(encoding="utf-8")
    parent_source = topup.PARENT.read_text(encoding="utf-8")
    candidate_scorer = ActionValueScorer("r18-P7-trigger-dataset", candidate_source)
    parent_scorer = ActionValueScorer("r18-P7-parent-trigger-dataset", parent_source)
    trigger_sources = []
    for source_row in topup.sources():
        stored = json.loads(
            topup.stage_path("candidate", source_row).read_text(encoding="utf-8")
        )
        changed = int((stored.get("request_audit") or {}).get("counts", {}).get(
            "changed_top_actions", 0
        ))
        if changed:
            trigger_sources.append((source_row, stored, changed))
    rows = []
    source_checks = []
    for source_row, stored, expected_changed in trigger_sources:
        requests: list[Any] = []
        plans = topup.natural.build_seat_stage_plans(
            contract=contract,
            opponent=str(source_row["mix"]),
            root_index=int(source_row["root_index"]),
            focal_seat=int(source_row["focal_seat"]),
            panel_seed=topup.PANEL_SEED,
        )
        replay = topup.natural.run_arm_stage(
            arm="candidate",
            plans=plans,
            candidate_scorer=ActionValueScorer(
                "r18-P7-trigger-replay-" + str(source_row["source_id"]),
                candidate_source,
            ),
            opponent_policies=contract["panel"]["opponent_scenarios"][
                str(source_row["mix"])
            ]["opponent_policies"],
            versions_block=topup.natural.stage.contract_versions_block(contract),
            step_limit=int(contract["stop"]["step_limit"]),
            value_limits=topup.LIMITS,
            decision_observer=requests.append,
        )
        parent_stage = json.loads(
            topup.stage_path("parent", source_row).read_text(encoding="utf-8")
        )["stage"]
        stage_delta = (
            int(stored["stage"]["focal_stage_score"])
            - int(parent_stage["focal_stage_score"])
        )
        found = 0
        for request in requests:
            view = build_scoring_view(request)
            candidate_batch = candidate_scorer.score(view)
            parent_batch = parent_scorer.score(view)
            candidate_top = top(candidate_batch)
            parent_top = top(parent_batch)
            if candidate_top.action_key == parent_top.action_key:
                continue
            overlay = candidate_top.trace.get("r18_seven_pairs_value_overlay")
            if not isinstance(overlay, dict) or overlay.get("triggered") is not True:
                continue
            found += 1
            observation = request.observation
            hand_codes = [tile.code for tile in observation.my_hand]
            if observation.drawn_tile is not None:
                hand_codes.append(observation.drawn_tile.code)
            counts = Counter(hand_codes)
            focal_score = int(observation.scores[observation.seat])
            request_json = decision_request_to_json(request)
            rows.append({
                "source_id": source_row["source_id"],
                "mix": source_row["mix"],
                "stage_score_delta_candidate_minus_parent": stage_delta,
                "score_trajectory_equal": [
                    table["scores_by_seat"] for table in stored["stage"]["tables"]
                ] == [table["scores_by_seat"] for table in parent_stage["tables"]],
                "request_sha256": digest_value(request_json),
                "request": request_json,
                "observable_features": {
                    "round_no": observation.round_no,
                    "seat": observation.seat,
                    "dealer": observation.seat == observation.dealer_seat,
                    "remaining_tile_count": observation.remaining_tile_count,
                    "focal_score": focal_score,
                    "leader_gap": max(observation.scores) - focal_score,
                    "meld_count": len(observation.melds[observation.seat]),
                    "river_length": len(observation.discards[observation.seat]),
                    "wealth_count": counts[observation.rule_state.wealth_god.code],
                    "pair_kinds": sum(value >= 2 for value in counts.values()),
                    "triplet_kinds": sum(value >= 3 for value in counts.values()),
                    "single_kinds": sum(value == 1 for value in counts.values()),
                    "candidate": action_features(view, candidate_top.action_key),
                    "parent": action_features(view, parent_top.action_key),
                    "parent_expected_value": float(overlay["parent_expected_value"]),
                    "candidate_expected_value": float(overlay["dominant_expected_value"]),
                    "expected_value_gain": (
                        float(overlay["dominant_expected_value"])
                        - float(overlay["parent_expected_value"])
                    ),
                    "expected_value_ratio": (
                        float(overlay["dominant_expected_value"])
                        / float(overlay["parent_expected_value"])
                    ),
                },
                "candidate_score": candidate_top.score,
                "parent_score": parent_top.score,
                "candidate_operations": candidate_scorer.last_operation_count,
            })
        source_checks.append({
            "source_id": source_row["source_id"],
            "expected_changed": expected_changed,
            "found_changed": found,
            "replay_status": replay["status"],
            "scores_reproduced": [
                table["scores_by_seat"] for table in replay["tables"]
            ] == [table["scores_by_seat"] for table in stored["stage"]["tables"]],
        })
    checks = {
        "trigger_count_matches_safety_result": len(rows) == int(
            result["request_audit_counts"]["seven_pairs_triggered"]
        ),
        "all_sources_reproduced": all(
            row["replay_status"] == "complete"
            and row["scores_reproduced"]
            and row["expected_changed"] == row["found_changed"]
            for row in source_checks
        ),
    }
    topup.write_json(OUT, {
        "schema": "r18-p7-natural-trigger-outcome-dataset/1",
        "status": "COMPLETE" if all(checks.values()) else "INVALID",
        "candidate_sha256": manifest["candidate_sha256"],
        "parent_sha256": manifest["parent_sha256"],
        "panel_seed": topup.PANEL_SEED,
        "checks": checks,
        "source_checks": source_checks,
        "rows": rows,
    })
    print(json.dumps({
        "status": "COMPLETE" if all(checks.values()) else "INVALID",
        "sources": len(source_checks), "triggers": len(rows), "checks": checks,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
