"""向后兼容回归：用 2026-09-04 官方测试赛真实运行目录验证验证器结论不变。

基线：runs/runs/run-29a71a10ad12441eb15e0ac4cfb55c1d/（70,720 条记录、
dropped=0、audit_degraded=false）。升级前的验证结论为
violation_count=0 / audit_complete=true / secret_scan_clean=true。
本测试在目录存在时锁定该结论：新增的原始事件严格检查被 legacy 门控
整体跳过，任何回归都会在这里变成红测试。目录缺失（其他环境）时跳过。
"""

from pathlib import Path

import pytest

from hangma_bot.adapters.recording import validate_run

# 仓库根的 runs 目录（相对本文件向上 3 级：recording → adapters → tests → 仓库根）。
_BASELINE = (
    Path(__file__).resolve().parents[3]
    / "runs"
    / "runs"
    / "run-29a71a10ad12441eb15e0ac4cfb55c1d"
)


@pytest.mark.skipif(not _BASELINE.is_dir(), reason="基线运行目录不存在")
def test_baseline_run_validation_conclusion_unchanged():
    """今晚真实 run 目录：验证器结论必须与升级前一致。"""

    report = validate_run(_BASELINE)
    assert report["violation_count"] == 0
    assert report["audit_complete"] is True
    assert report["ok"] is True
    assert report["secret_scan_clean"] is True
    assert report["raw_events"]["retention_mode"] == "legacy"
    # 旧目录没有任何原始事件记录（基线事实），统计必须诚实为零。
    assert report["raw_events"]["records_total"] == 0
