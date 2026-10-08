"""复算 P7 自然桌首尺中的全部七对价值触发窗口。"""

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

import json
from pathlib import Path
import sys
from typing import Any


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ROOT = _PROJECT_ROOT
for path in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROUTE / "tools"), HERE):
    sys.path.insert(0, str(path))

import r18_p7_table_effect_pilot as pilot  # noqa: E402
from hangma_bot.application.audit_codec import decision_request_to_json  # noqa: E402
from hangma_bot.policy.action_value_policy import build_scoring_view  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402


OUT = pilot.OUT / "natural-trigger-diagnosis.json"
TRIGGER_SOURCES = (
    {"mix": "H", "root_index": 1, "focal_seat": 3, "source_id": "H:r01:s3"},
    {"mix": "H", "root_index": 3, "focal_seat": 1, "source_id": "H:r03:s1"},
    {"mix": "M", "root_index": 3, "focal_seat": 2, "source_id": "M:r03:s2"},
)


def top(batch: Any) -> Any:
    """按正式合同排序返回首选评分项。"""

    return sorted(batch.entries, key=lambda item: (-item.score, item.action_key))[0]


def entry_json(item: Any) -> dict[str, Any]:
    """保留复核一个动作所需的评分与轨迹。"""

    return {
        "action_key": item.action_key,
        "score": item.score,
        "trace": item.trace,
    }


def main() -> None:
    """重放三个已知触发来源，并固化父子分歧请求。"""

    if OUT.exists():
        raise SystemExit("P7 自然触发诊断已存在；拒绝覆盖")
    pilot.verify_manifest()
    contract = json.loads(pilot.CONTRACT.read_text(encoding="utf-8"))
    candidate_source = pilot.CANDIDATE.read_text(encoding="utf-8")
    parent_source = pilot.PARENT.read_text(encoding="utf-8")
    candidate_scorer = ActionValueScorer("r18-P7-trigger-diagnosis", candidate_source)
    parent_scorer = ActionValueScorer("r18-P7-parent-trigger-diagnosis", parent_source)
    rows = []
    source_checks = []
    for source_row in TRIGGER_SOURCES:
        requests: list[Any] = []
        plans = pilot.natural.build_seat_stage_plans(
            contract=contract,
            opponent=str(source_row["mix"]),
            root_index=int(source_row["root_index"]),
            focal_seat=int(source_row["focal_seat"]),
            panel_seed=pilot.PANEL_SEED,
        )
        stage = pilot.natural.run_arm_stage(
            arm="candidate",
            plans=plans,
            candidate_scorer=ActionValueScorer(
                "r18-P7-trigger-replay-" + str(source_row["source_id"]),
                candidate_source,
            ),
            opponent_policies=contract["panel"]["opponent_scenarios"][
                str(source_row["mix"])
            ]["opponent_policies"],
            versions_block=pilot.natural.stage.contract_versions_block(contract),
            step_limit=int(contract["stop"]["step_limit"]),
            value_limits=pilot.LIMITS,
            decision_observer=requests.append,
        )
        changed = 0
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
            changed += 1
            rows.append({
                "source_id": source_row["source_id"],
                "request": decision_request_to_json(request),
                "candidate_top": entry_json(candidate_top),
                "parent_top": entry_json(parent_top),
                "all_candidate_entries": [entry_json(item) for item in candidate_batch.entries],
                "all_parent_entries": [entry_json(item) for item in parent_batch.entries],
                "candidate_operations": candidate_scorer.last_operation_count,
            })
        original = json.loads(
            pilot.stage_path("candidate", source_row).read_text(encoding="utf-8")
        )
        source_checks.append({
            "source_id": source_row["source_id"],
            "replay_status": stage["status"],
            "replay_scores": [table["scores_by_seat"] for table in stage["tables"]],
            "original_scores": [
                table["scores_by_seat"] for table in original["stage"]["tables"]
            ],
            "changed_windows": changed,
            "original_changed_windows": original["request_audit"]["counts"][
                "changed_top_actions"
            ],
        })
    checks = {
        "three_trigger_rows": len(rows) == 3,
        "every_source_reproduced": all(
            item["replay_status"] == "complete"
            and item["replay_scores"] == item["original_scores"]
            and item["changed_windows"] == item["original_changed_windows"] == 1
            for item in source_checks
        ),
    }
    pilot.write_json(OUT, {
        "schema": "r18-p7-natural-trigger-diagnosis/1",
        "status": "COMPLETE" if all(checks.values()) else "INVALID",
        "candidate_sha256": pilot.digest(pilot.CANDIDATE),
        "parent_sha256": pilot.digest(pilot.PARENT),
        "panel_seed": pilot.PANEL_SEED,
        "source_checks": source_checks,
        "checks": checks,
        "rows": rows,
    })
    print(json.dumps({"status": "COMPLETE", "rows": len(rows), "checks": checks}, ensure_ascii=False))


if __name__ == "__main__":
    main()
