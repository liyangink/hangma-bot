"""运行与身份汇总组装器的纯函数测试。"""

import json

from hangma_bot.adapters.recording.summary import (
    build_participant_summary,
    build_run_summary,
    participant_ids_from_paths,
    paths_for_participant,
)

_PATHS = [
    "manifest.json",
    "lifecycle.jsonl",
    "participants/P1/decisions.jsonl",
    "participants/P1/games/G1.jsonl",
    "participants/P2/decisions.jsonl",
]


class TestPathHelpers:
    def test_participant_ids_extracted_and_sorted(self):
        assert participant_ids_from_paths(_PATHS) == ["P1", "P2"]

    def test_paths_filtered_per_participant(self):
        assert paths_for_participant(_PATHS, "P1") == [
            "participants/P1/decisions.jsonl",
            "participants/P1/games/G1.jsonl",
        ]
        assert paths_for_participant(_PATHS, "P9") == []


class TestBuilders:
    def test_run_summary_is_json_serializable_and_complete(self):
        summary = build_run_summary(
            run_id="run-1",
            written=10,
            written_by_kind={"submission_intent": 6, "lifecycle_changed": 4},
            written_by_path={"participants/P1/decisions.jsonl": 6, "lifecycle.jsonl": 4},
            dropped_low_priority=1,
            missing_high_priority=0,
            serialization_failures=0,
            write_failures=0,
            audit_degraded=False,
            participants=["P1"],
            extra_detail={"note": "写入器正常退出"},
        )
        assert summary["level"] == "run"
        assert summary["run_id"] == "run-1"
        assert summary["participants"] == ["P1"]
        assert summary["detail"] == {"note": "写入器正常退出"}
        assert json.loads(json.dumps(summary, ensure_ascii=False)) == summary

    def test_participant_summary_carries_global_loss_counters(self):
        summary = build_participant_summary(
            run_id="run-1",
            participant_id="P1",
            written=6,
            written_by_kind={"submission_intent": 6},
            written_by_path={"participants/P1/decisions.jsonl": 6},
            dropped_low_priority=2,
            missing_high_priority=1,
            serialization_failures=0,
            write_failures=1,
            audit_degraded=True,
        )
        assert summary["level"] == "participant"
        assert summary["participant_id"] == "P1"
        # 丢失/失败计数是运行级全局值，身份级汇总原样引用。
        assert summary["missing_high_priority"] == 1
        assert summary["dropped_low_priority"] == 2
        assert json.loads(json.dumps(summary, ensure_ascii=False)) == summary
