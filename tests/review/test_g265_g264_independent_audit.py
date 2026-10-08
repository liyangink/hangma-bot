"""G265 只读验收：部分批不得声称效果，缺段、审计失败和提前开根均拒绝。"""

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

from argparse import Namespace
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
REVIEW = _project_file(_PROJECT_ROOT, ROOT / "review/freematch-deep-dive-20260925")
if str(REVIEW) not in sys.path:
    sys.path.insert(0, str(REVIEW))

import g265_g264_independent_audit as subject  # noqa: E402


def _smoke_table() -> dict:
    """用已冻结的完整桌产物检验真实审计结构。"""

    evidence = ROOT / "tests/fixtures/research/freematch-deep-dive-20260925/evidence/g264-first-divergence-smoke-20260929/stages"
    stage = json.loads(sorted(evidence.glob("*.json"))[0].read_text(encoding="utf-8"))
    return stage["stage"]["tables"][0]


def test_real_smoke_table_passes_and_audit_missing_fails() -> None:
    """真实结构可验；驱动未审计动作不可借其他四项全零通过。"""

    table = _smoke_table()
    subject.verify_execution(table)
    altered = deepcopy(table)
    altered["result"]["runtime_counts"]["audit_missing"] = 1
    with pytest.raises(ValueError, match="audit_missing"):
        subject.verify_execution(altered)


def test_internal_failure_and_audit_digest_tamper_fail(monkeypatch) -> None:
    """评分失败与审计摘要漂移各自阻断效果验收。"""

    table = _smoke_table()
    altered = deepcopy(table)
    altered["result"]["versions"]["policy_execution_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="摘要"):
        subject.verify_execution(altered)

    original = subject.g264.panel.natural.execution_audit.verify_table

    def failed_audit(value):
        audit = deepcopy(original(value))
        audit["action_value_failed"] = 1
        return audit

    monkeypatch.setattr(subject.g264.panel.natural.execution_audit,
                        "verify_table", failed_audit)
    with pytest.raises(ValueError, match="action_value_failed"):
        subject.verify_execution(table)


def test_partial_has_no_effect_claim_and_full_requires_all_stages(tmp_path) -> None:
    """运行中的空批可核冻结身份，但完整模式必须收齐 768 阶段。"""

    out = tmp_path / "g264-first-divergence-development-20260929"
    out.mkdir()
    args = Namespace(panel_seed=subject.PANEL_SEED,
                     root_start=subject.ROOT_START,
                     roots_per_mix=subject.ROOTS_PER_MIX)
    (out / "manifest.json").write_text(
        json.dumps(subject.g264.manifest(args), ensure_ascii=False), encoding="utf-8")
    state = subject.audit(out, partial=True)
    assert state["verified_stages"] == 0
    assert state["effect_claim_allowed"] is False
    with pytest.raises(ValueError, match="未收齐"):
        subject.audit(out, partial=False)


def test_confirmation_tmp_stage_is_already_opened(tmp_path) -> None:
    """即使文件尚在原子写入中，35–66 的预留根也不能提前启动。"""

    directory = tmp_path / "g264-first-divergence-confirmation" / "stages"
    directory.mkdir(parents=True)
    (directory / "H-r0035-s0-g49_continuous.json.tmp").touch()
    with pytest.raises(ValueError, match="确认根已提前打开"):
        subject.verify_confirmation_closed(tmp_path)
