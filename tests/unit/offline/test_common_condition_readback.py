"""条件诊断按实际消费事件排序；人工最小记录不生成牌局或评分。"""
from __future__ import annotations

import gzip
import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def reader():
    """装载公开薄读回入口，不导入策略或读取私有牌谱。"""
    path = (Path(__file__).resolve().parents[3] / "review/vip-route-2026-09-30/evidence"
            / "t200-eoh-fast-evolution-1/common_readback.py")
    spec = importlib.util.spec_from_file_location("common_condition_readback", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def record(phase, consumed_seq, seat):
    """复现同一弃牌先碰后吃；序号与真实T211反例的排序条件相同。"""
    return {
        "record_kind": "delegate_actual_choose", "sample": 1, "arm": "parent",
        "row": {"seat": seat, "window_key": {"round_no": 2, "trigger_seq": 650, "phase": phase},
                "observation": {"consumed_seq": consumed_seq}},
    }


def write_records(path, records):
    """只创建本测试的严格JSON gzip，字节上限由被测公开入口检查。"""
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        for row in records:
            stream.write(json.dumps(row) + "\n")


def test_peng_precedes_chi_even_when_trigger_seq_equal_and_records_reversed(reader, tmp_path):
    path = tmp_path / "events.jsonl.gz"
    write_records(path, [record("response_chi", 654, 3), record("response_peng", 651, 0)])
    groups, _ = reader.decisions(path, 4096)
    assert [r["window_key"]["phase"] for r in groups[(1, "parent")]] == ["response_peng", "response_chi"]


@pytest.mark.parametrize("seq", [True, None, 649])
def test_missing_or_invalid_consumed_seq_cannot_be_silently_sorted(reader, tmp_path, seq):
    path = tmp_path / "events.jsonl.gz"
    write_records(path, [record("response_peng", seq, 0)])
    with pytest.raises(ValueError, match="观察消费序号"):
        reader.decisions(path, 4096)


def test_duplicate_actual_window_is_not_a_second_decision(reader, tmp_path):
    path = tmp_path / "events.jsonl.gz"
    row = record("response_peng", 651, 0)
    write_records(path, [row, row])
    with pytest.raises(ValueError, match="同期座位窗口重复"):
        reader.decisions(path, 4096)


@pytest.mark.parametrize("points", [[], [{"task": {"root_id": "unclosed"}}]])
def test_three_arm_empty_or_unclosed_batch_never_creates_pass_report(reader, tmp_path, points):
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({
        "parent_identity": {"candidate_id": "p0"},
        "candidate_identities": {"G31": {"candidate_id": "g31"}, "G32": {"candidate_id": "g32"}},
        "arms": ["P0", "G31", "G32"], "points": points,
    }))
    output = tmp_path / "result.json"
    with pytest.raises(ValueError):
        reader.run(plan, tmp_path / "not_run", output, 4096)
    assert not output.exists()
