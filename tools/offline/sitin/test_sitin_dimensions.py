"""坐隐 1.6 维度工具自测。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/tools'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import importlib.util
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_REPO = _PROJECT_ROOT


def _load():
    spec = importlib.util.spec_from_file_location("sitin_dimensions", _project_file(_PROJECT_ROOT, _HERE / "sitin_dimensions.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules["sitin_dimensions"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


dims = _load()

PROBE = _project_file(_PROJECT_ROOT, _REPO / "runs/probe-scale-20260915/out/results.jsonl")


def _row(label, scores, seat_policies, scenario="s0"):
    return {
        "status": "complete",
        "scenario_id": scenario,
        "pair_id": scenario + ":0123",
        "game_key": {"game_id": "t:%s:0123:%s" % (scenario, label)},
        "policy_ids_by_seat": seat_policies,
        "scores_after": scores,
    }


def test_top2_rate_uses_in_table_ranking_not_first_place():
    """前二率按**同一桌内**四家得分排名；同分按座位序（确定性）。"""

    rows = [
        # 被测在第 0 座，得 30：排名第 1 → 计入前二
        _row("p", [30, 10, 20, 5], ["p", "o1", "o2", "o3"]),
        # 被测在第 0 座，得 5：排名第 4 → 不计入
        _row("p", [5, 30, 10, 20], ["p", "o1", "o2", "o3"], scenario="s1"),
        # 被测在第 0 座，得 20：与第 3 名并列，按座位序判为第 2 → 计入
        _row("p", [20, 30, 5, 20], ["p", "o1", "o2", "o3"], scenario="s2"),
    ]
    out = dims.collect_score_dimensions(rows)
    top2 = out["arms"]["p"]["top2_rate_in_table"]
    assert top2["n"] == 3
    # 三行里第 1、3 行落入前二 → 2/3；工具输出保留 4 位小数，容差据此设定
    assert top2["mean"] == pytest.approx(2 / 3, abs=1e-4)


def test_own_tail_is_not_the_paired_difference_tail():
    """工具报的是**候选自身**积分下尾，不是配对差下尾（审查 R-6）。"""

    rows = [
        _row("p", [-100, 0, 0, 100], ["p", "o1", "o2", "o3"]),
        _row("p", [10, 0, 0, 0], ["p", "o1", "o2", "o3"], scenario="s1"),
    ]
    out = dims.collect_score_dimensions(rows)
    net = out["arms"]["p"]["net_score_per_table"]
    assert net["min"] == -100
    assert net["q05"] <= 10        # 自身下尾，而非"相对基线的退步"


def test_incomplete_rows_are_reported_not_silently_dropped():
    rows = [
        _row("p", [10, 0, 0, 0], ["p", "o1", "o2", "o3"]),
        dict(_row("p", [10, 0, 0, 0], ["p", "o1", "o2", "o3"], scenario="s1"), status="error"),
    ]
    out = dims.collect_score_dimensions(rows)
    assert out["used_rows"] == 1
    assert len(out["skipped"]) == 1 and "status=error" in out["skipped"][0]


def test_process_dimensions_are_marked_not_computable():
    """过程类维度必须标为**不可计算**，不得假装可从既有结果后处理。"""

    table = dims.build_source_table()
    assert set(table["computable_now"]) == {
        "桌内积分 / 场均净分", "桌内前二率", "候选**自身**积分下尾 Q05"}
    for blocked in ("番型分布", "链长分布 / 圈开闭 / 白板条件分布", "机制触发 / 实际改选率"):
        assert blocked in table["blocked"]
    mechanism = [d for d in table["dimensions"] if d["dimension"].startswith("机制触发")][0]
    assert "不得把分叉后的两条轨迹" in mechanism["blocker"]


def test_own_tail_dimension_carries_the_warning():
    table = dims.build_source_table()
    item = [d for d in table["dimensions"] if "下尾" in d["dimension"]][0]
    assert "不得**用 Q05(候选−基线) 代替" in item["warning"]


@pytest.mark.skipif(not PROBE.exists(), reason="缺少 probe 产物")
def test_probe_pair_delta_matches_power_tool():
    """两工具的自洽性：维度工具的行序配对差应与 1.1 的根级点估计一致。"""

    import json
    rows = [json.loads(l) for l in PROBE.read_text(encoding="utf-8").splitlines() if l.strip()]
    out = dims.collect_score_dimensions(rows)
    assert out["used_rows"] == 128
    assert out["delta"]["delta_mean"] == pytest.approx(2.75, abs=1e-9)
