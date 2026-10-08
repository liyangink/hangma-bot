"""归因脚本的行为回归：每个原因码都要能被合成记录触发，且顺序稳定。

原因码决定了 F2 往哪个方向改（新鲜度 / 鸣牌兴趣 / 周期身份），顺序错了就会把
"快照落后"误判成"有鸣牌兴趣"，从而改错地方。这里逐条钉死。
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'tests/review'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = (_project_file(_PROJECT_ROOT, Path(__file__).resolve().parents[2]
          / "review/wiring-queue-rootcause-2026-09-25/analyze_skip_attribution.py"))


def _load():
    spec = importlib.util.spec_from_file_location("skip_attr", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


attr = _load()


def _row(**overrides):
    """一条"一切正常、只差深条件"的基线记录；逐个覆盖字段构造各原因码。"""

    base = {
        "sse_frame_not_skipped": True,
        "observed_seq": 104,
        "base_seq": 101,
        "seq_delta": 3,
        "last_seq": 101,
        "skipped_seq": 0,
        "filter_active": True,
        "claim_interest": False,
        "cycle_known": True,
        "cycle": [3, 101, "5w", 2],
        "gate_in_flight": False,
        "gate_blocked": False,
        "snapshot_phase": "draw",
        "skip_expectations": 0,
    }
    base.update(overrides)
    return base


def test_deep_condition_is_the_residual_not_a_failure():
    assert attr.classify(_row()) == "deep_condition"


@pytest.mark.parametrize("overrides,expected", [
    ({"filter_active": False}, "filter_inactive"),
    ({"gate_in_flight": True}, "gate_busy"),
    ({"gate_blocked": True}, "gate_busy"),
    # delta 不在任何规则覆盖的偏移上（no_rule_for_offset）——第一次实现把它
    # 误报成 offset_unsupported，且会连带把"没有规则覆盖"说成"快照落后"。
    ({"seq_delta": 9}, "no_rule_for_offset"),
    ({"seq_delta": None}, "no_rule_for_offset"),
    # +1 帧只有"我方弃牌回显"规则覆盖；没有待回显就不可能跳过
    # （基线行是 delta=3，属碰超时规则，因此这里必须显式给 delta=1）。
    ({"seq_delta": 1, "expected_own_discard_seq": None}, "no_pending_own_discard"),
    ({"seq_delta": 1, "expected_own_discard_seq": 104}, "deep_condition"),
    ({"base_seq": 100, "last_seq": 101}, "freshness"),
    ({"cycle": None, "cycle_known": False}, "cycle_unknown"),
    ({"cycle": [3, 99, "5w", 2]}, "cycle_mismatch"),
    ({"claim_interest": True}, "claim_interest"),
])
def test_each_reason_code_is_reachable(overrides, expected):
    assert attr.classify(_row(**overrides)) == expected


def test_precedence_freshness_before_claim_interest():
    """"快照落后"必须先于"有鸣牌兴趣"判定：两者的修法完全不同。"""

    row = _row(base_seq=100, last_seq=101, claim_interest=True)
    assert attr.classify(row) == "freshness"


def test_offset_routing_precedes_gate_and_freshness():
    """先按偏移路由到能覆盖它的规则，再判该规则的前提。

    顺序错了会把"根本没有规则覆盖这个偏移"报成"快照落后"或"动作门忙"——这正是第一次
    实现（未按偏移路由）把 78% 的 +1 帧误报为 freshness 的原因。
    """

    assert attr.classify(_row(gate_in_flight=True, seq_delta=99)) == "no_rule_for_offset"
    assert attr.classify(_row(gate_in_flight=True, seq_delta=3)) == "gate_busy"
    assert attr.classify(_row(base_seq=100, last_seq=101, seq_delta=2)) == "freshness"


def _write(audit_root: Path, rows: list) -> None:
    directory = audit_root / "runs" / "run-x" / "participants" / "u_1" / "games"
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "g1.jsonl").open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps({"kind": "authoritative_state", "payload": row}) + "\n")


def test_analyze_aggregates_counts_and_shares(tmp_path):
    audit = tmp_path / "audit"
    _write(audit, [
        _row(),
        _row(base_seq=100, last_seq=101),
        _row(base_seq=100, last_seq=101),
        _row(seq_delta=2, base_seq=102, last_seq=102),
    ])
    summary = attr.analyze(audit)
    assert summary["frames_not_skipped"] == 4
    assert summary["reason_counts"]["freshness"] == 2
    assert summary["reason_share"]["freshness"] == pytest.approx(0.5)
    assert summary["seq_delta_histogram"][3] == 3
    assert summary["seq_delta_histogram"][2] == 1


def test_analyze_ignores_records_without_the_marker(tmp_path):
    audit = tmp_path / "audit"
    _write(audit, [{"sse_skip_reason": "plain_peng_timeout_group"}, _row()])
    summary = attr.analyze(audit)
    assert summary["frames_not_skipped"] == 1


def test_analyze_reports_zero_on_pre_instrumentation_audits(tmp_path):
    audit = tmp_path / "audit"
    _write(audit, [{"something": "else"}])
    summary = attr.analyze(audit)
    assert summary["frames_not_skipped"] == 0
    assert summary["reason_share"] == {}
