"""R17 首代第二来源的预登记选择键测试。"""

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

import r17_generation1_reproduction as target


PASS = "PASS_R17_GENERATION1_DEVELOPMENT_GATE"
FAIL = "FAIL_R17_GENERATION1_DEVELOPMENT_GATE"


def _row(candidate_id, status, *, h, m, overall, candidate_fourth=0.1, baseline_fourth=0.2):
    return {
        "candidate_id": candidate_id,
        "status": status,
        "by_mix": {
            "H": {"u_delta_low_mean": h},
            "M": {"u_delta_low_mean": m},
        },
        "overall": {
            "u_delta_low_mean": overall,
            "candidate_fourth_rate": candidate_fourth,
            "baseline_fourth_rate": baseline_fourth,
        },
    }


def test_selection_prefers_robust_minimum_before_overall_mean():
    """一项 mix 很高不能补偿另一项薄弱；先比较 H/M 中的较弱者。"""

    first = {
        "candidates": [
            _row("A", PASS, h=0.0, m=0.4, overall=0.2),
            _row("B", PASS, h=0.1, m=0.1, overall=0.1),
        ]
    }
    second = [
        _row("A", PASS, h=0.0, m=0.4, overall=0.2),
        _row("B", PASS, h=0.1, m=0.1, overall=0.1),
    ]
    candidates = {"A": {"identity": "id-a"}, "B": {"identity": "id-b"}}

    combined, selected = target.select_confirmation_candidate(first, second, candidates)

    assert len(combined) == 2
    assert selected is not None
    assert selected["candidate_id"] == "B"


def test_selection_excludes_candidate_that_fails_either_source():
    """第一来源或第二来源失败都不得由合并均值补回。"""

    first = {
        "candidates": [
            _row("A", PASS, h=1.0, m=1.0, overall=1.0),
            _row("B", PASS, h=0.1, m=0.1, overall=0.1),
        ]
    }
    second = [
        _row("A", FAIL, h=1.0, m=1.0, overall=1.0),
        _row("B", PASS, h=0.1, m=0.1, overall=0.1),
    ]
    candidates = {"A": {"identity": "id-a"}, "B": {"identity": "id-b"}}

    combined, selected = target.select_confirmation_candidate(first, second, candidates)

    assert next(row for row in combined if row["candidate_id"] == "A")[
        "passed_both_sources"
    ] is False
    assert selected is not None
    assert selected["candidate_id"] == "B"
