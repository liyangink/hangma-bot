"""已开结果的宽面条件对照只能用于诊断，不可伪装成确认集。"""

import json
from pathlib import Path

import pytest

from scripts.vip_p3_width_pair_diagnostic import _read, diagnose


_BASE = Path("review/vip-route-2026-09-30/evidence/p3-competing-terminal-20260930")


def test_width_pair_diagnostic_recomputes_from_frozen_evidence():
    """核每根一对、动作身份和两套续打的均分账可从原教师复算。"""

    report = diagnose(
        _read(_BASE / "new-root-scan.json.gz"),
        _read(_BASE / "new-shape-teacher.json.gz"),
        _read(_BASE / "new-r18_frozen-teacher.json.gz"),
    )
    saved = json.loads((_BASE / "width-pair-diagnostic.json").read_text(encoding="utf-8"))
    assert report == saved
    assert report["root_count"] == 10
    assert len({row["root_id"] for row in report["rows"]}) == 10
    assert all(row["positive_code_difference"] > 0
               and -2 <= row["unseen_capacity_difference"] <= 0
               for row in report["rows"])
    assert report["summary"]["shape"]["mean_net_per_root"] == 0.0
    assert report["summary"]["r18_frozen"]["mean_net_per_root"] == -4.2


def test_width_pair_diagnostic_rejects_cross_batch_teacher():
    """教师若改绑其他自然牌山批次，不能拼成貌似可复算的对照。"""

    scan = _read(_BASE / "new-root-scan.json.gz")
    shape = _read(_BASE / "new-shape-teacher.json.gz")
    r18 = _read(_BASE / "new-r18_frozen-teacher.json.gz")
    shape["start_seed"] += 1
    with pytest.raises(ValueError, match="来源不符"):
        diagnose(scan, shape, r18)
