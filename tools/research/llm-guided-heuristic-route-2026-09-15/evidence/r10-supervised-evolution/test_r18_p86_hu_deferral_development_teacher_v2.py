"""P86-02 的座位积分映射和断点恢复身份回归。"""

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

import copy
import json
import unittest

import r18_p86_hu_deferral_development_teacher_v2 as p86


class P86TeacherV2Test(unittest.TestCase):
    def test_second_table_prior_scores_follow_physical_seats(self) -> None:
        """真实 P85 第二桌的逻辑顺序不同，已完成桌分应跟随当前物理座位。"""

        target = next(row for row in p86.targets()
                      if row["source"]["table_no"] == 2)
        contract = json.loads(p86.CONTRACT.read_text(encoding="utf-8"))
        source = target["source"]
        plans = p86.natural.build_seat_stage_plans(
            contract=contract, opponent=source["mix"],
            root_index=int(source["root_index"]),
            focal_seat=int(source["focal_seat"]),
            panel_seed=int(source["panel_seed"]),
        )
        plan = plans[1]
        by_id = {entry["participant_id"]: int(entry["total_score"])
                 for entry in target["competition"]["ranking"]}
        physical = [by_id[participant] for participant in plan.seats()]
        logical = [by_id[participant] for participant in plan.logical_participants]
        self.assertNotEqual(physical, logical)
        self.assertEqual(p86.completed_table_scores_for_snapshot(target, plan), [physical])

    def test_resume_rejects_corrupted_pair_identity_even_if_marked_ok(self) -> None:
        """旧文件即使伪称 mechanical_ok，也不得挪用为另一目标或未来墙。"""

        target = p86.targets()[0]
        immediate = target["expected_hu_settlement"]
        focal = int(target["focal_physical_seat"])
        reference_delta = [0, 0, 0, 0]
        row = {
            "schema": "r18-p86-hu-deferral-development-rollout/1",
            "target_id": target["target_id"], "rollout_index": 1,
            "sample_key": "frozen-wall-01",
            "reference_action": target["reference_action"],
            "intervention_action": "hu",
            "actual_actions": {"baseline": target["reference_action"],
                               "candidate": "hu"},
            "force_count": {"reference": 1, "intervention": 1},
            "tables_executed": {"baseline": 1, "candidate": 1},
            "mechanical_ok": True,
            "reference": {"round_no": target["features"]["round_no"],
                          "score_delta": reference_delta,
                          "focal_settlement": 0},
            "intervention": {
                "round_no": target["features"]["round_no"],
                "winner_seat": focal, "terminal": "focal_hu",
                "fan": immediate["fan"],
                "score_delta": immediate["score_delta"],
                "focal_settlement": immediate["score_delta"][focal],
            },
            "focal_current_round_settlement_delta": immediate["score_delta"][focal],
            "focal_current_table_score": {
                "reference": 0, "intervention": 20, "delta": 20,
            },
        }
        p86.validate_rollout_row(row, target, 1, "frozen-wall-01")
        corruptions = {
            "target_id": "another-target",
            "rollout_index": 2,
            "sample_key": "other-wall",
            "reference_action": "hu",
            "intervention_action": "discard:1t",
            "actual_actions": {"baseline": "hu", "candidate": "hu"},
            "force_count": {"reference": 0, "intervention": 1},
            "tables_executed": {"baseline": 1, "candidate": 0},
            "mechanical_ok": False,
        }
        for field, value in corruptions.items():
            with self.subTest(field=field):
                altered = copy.deepcopy(row)
                altered[field] = value
                with self.assertRaises(ValueError):
                    p86.validate_rollout_row(altered, target, 1, "frozen-wall-01")


if __name__ == "__main__":
    unittest.main()
