# -*- coding: utf-8 -*-
"""P25 包 C 专属测试：C6「已完成但损坏/不足」的条件面板恢复必须具名阻断。

复审条目：R9-P25-ADMISSION-REPAIR-REVIEW-2026-09-19 §C6（P1）。
本文件只覆盖 C6 恢复三态；不改既有测试、不改生产评分语义。

覆盖（全部离线、零模型、零桌赛：评价与运行时装配被替换成立即报错的守卫）：
  1. 没有完成记录 → 正常走评价（唯一允许重新评价的情形）；
  2. 完成且可核（事务件 + 不可变结果摘要一致）→ 复用，不重跑、不重复计费；
  3. 改值 + **删除摘要** → 具名阻断：状态不推进、不建档、不自动重跑（复审反例）；
  4. 改值 + 保留旧摘要 → 同样具名阻断（不得静默重跑）；
  5. 事务件读不出 / 结果文件缺失 → 具名阻断。
"""

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
import hashlib
import json
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import sitin_search as search  # noqa: E402


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def _fixture(candidate_u: float) -> dict:
    """合成条件面板结果（与档案单元测试同类结构，不宣称任何真实运行）。"""
    sample = {
        "source_root_id": "c6-unit-root", "scenario": "branch_open",
        "opponent_mix": "H", "candidate_id": "c6-unit-candidate",
        "root_role": "core", "invalid": False, "selection_eligible": True,
        "root_expected": {"seats": 1, "arms": ["baseline", "candidate"],
                          "tables_per_arm": 1},
        "arms": {"baseline": {"candidate_id": "V2_BASE", "u": 0.0,
                              "status": "complete", "usable": True},
                 "candidate": {"candidate_id": "c6-unit-candidate", "u": candidate_u,
                               "status": "complete", "usable": True}},
        "cost": 2.0,
    }
    return {"ok": True, "identity": {"candidate_id": "c6-unit-candidate",
                                     "evaluation_id": "c6-unit-evaluation"},
            "panel": {"predicate": "branch_open"}, "samples": [sample],
            "execution_kind": "real_runtime", "runtime_kind": "real_simulation_engine",
            "usable_for_selection": True, "result_admission": {"ok": True}}


def _setup(tmp_path: Path, *, result_u: float, tx: str,
           mutate_to: float = None):
    """搭一个迭代目录：结果文件 + 完成事务件。返回 (state, iter_dir, result_path)。

    tx 取值：absent（无事务件）/ missing_digest（有事务件但**缺摘要**）/
    matching_digest（摘要与结果一致）/ stale_digest（摘要停留在旧值）/ unreadable（坏事务件）。
    mutate_to 给出时，写完事务件后把结果改成该候选值（模拟"结果被改写"）。
    result_u 为 None 表示结果文件不落盘（"结果缺失"）。
    """
    iter_dir = Path(tmp_path) / "iterations" / "iter-01"
    result_path = iter_dir / "conditional" / "evaluation.json"
    original = _fixture(-0.5)
    original_bytes = (json.dumps(original, ensure_ascii=False, indent=2) + "\n").encode()
    if result_u is not None:
        _write_json(result_path, original)
    tx_path = iter_dir / "transactions" / "tx-eval-conditional-complete.json"
    if tx == "absent":
        pass
    elif tx == "unreadable":
        tx_path.parent.mkdir(parents=True, exist_ok=True)
        tx_path.write_text('{"schema": "sitin-av-tx-eval-complete/1", "panel"',
                           encoding="utf-8")
    else:
        payload = {"schema": "sitin-av-tx-eval-complete/1", "panel": "conditional",
                   "immutable_summary_path": str(result_path),
                   "evaluation_id": "c6-unit-evaluation"}
        if tx == "matching_digest":
            payload["immutable_summary_sha256"] = hashlib.sha256(original_bytes).hexdigest()
        elif tx == "stale_digest":
            payload["immutable_summary_sha256"] = hashlib.sha256(original_bytes).hexdigest()
        _write_json(tx_path, payload)
    if mutate_to is not None:
        _write_json(result_path, _fixture(mutate_to))
    state = {"iter_dir": str(iter_dir), "run_id": "c6-unit", "iteration_no": 1,
             "identity": {"candidate_id": "c6-unit-candidate"},
             "plan": {"predicate": "branch_open", "prefix_source": "v2_behavior"}}
    return state, iter_dir, result_path


@pytest.fixture()
def no_real_work(monkeypatch):
    """把评价与运行时装配替换成立即报错的守卫：任何真实评价都会让测试失败。"""
    calls = []

    def guard(*args, **kwargs):
        calls.append(1)
        raise AssertionError("C6 恢复测试不得进入评价/装配路径（零桌赛）")

    monkeypatch.setattr(search, "run_av_evaluation", guard, raising=True)
    monkeypatch.setattr(search, "_av_assemble_conditional_runtime", guard, raising=True)
    return calls


def _archived_d_points(state):
    entries = search._av_archive_entries_with(state, {})
    rows = []
    for entry in entries:
        for _sub, by_root in (entry.get("family_evaluations") or {}).items():
            for _root, record in (by_root or {}).items():
                if isinstance(record, dict):
                    rows.append(record.get("d_point"))
    return rows


def test_no_completion_record_evaluates_normally(tmp_path, no_real_work):
    """没有完成事务件 = 从未完成过该步 ⇒ 正常评价（守卫命中即证明走了评价）。"""
    state, _iter_dir, _ = _setup(tmp_path, result_u=-0.5, tx="absent")
    with pytest.raises(AssertionError):
        search._step_conditional(state, Path(tmp_path), None, None)
    assert state["conditional_recovery"]["state"] == "no_completion_record"


def test_verified_completion_is_reused_without_rerun(tmp_path, no_real_work):
    """完成且可核（摘要一致）⇒ 复用：不重跑、不重复计费、档案取原值 −0.5。"""
    state, _iter_dir, _ = _setup(tmp_path, result_u=-0.5, tx="matching_digest")
    result = search._step_conditional(state, Path(tmp_path), None, None)
    assert result == {"advanced": "CONDITIONAL_EVALUATED", "restored": True}
    assert no_real_work == [], "已可核的完成结果被重跑"
    assert state["conditional_recovery"]["state"] == "verified"
    assert _archived_d_points(state) == [-0.5]


@pytest.mark.parametrize("tx", ["missing_digest", "stale_digest"])
def test_damaged_completion_blocks_without_advance_or_archive(tmp_path, no_real_work,
                                                              tx):
    """复审 C6 反例：改值 + 缺摘要（或摘要不符）⇒ 具名阻断，不推进、不建档、不重跑。"""
    state, _iter_dir, _ = _setup(tmp_path, result_u=-0.5, tx=tx, mutate_to=0.5)
    result = search._step_conditional(state, Path(tmp_path), None, None)
    assert result == {"terminal": "EXECUTION_FAILED"}
    assert state["status"] == "EXECUTION_FAILED"
    assert state["stop_reason"].startswith("conditional_recovery_blocked:")
    assert state["conditional_recovery"]["state"] == "damaged"
    assert state["conditional_recovery"]["archived"] is False
    assert state["conditional_recovery"]["auto_rerun"] is False
    assert state.get("conditional_result") is None
    assert no_real_work == [], "损坏的完成事务被当作没有结果重新评价"
    assert _archived_d_points(state) == [], "改值结果进入了候选档案"


def test_missing_digest_names_the_specific_block(tmp_path, no_real_work):
    """缺摘要必须是**具名**阻断（而不是泛化成"没有结果"）。"""
    state, _iter_dir, _ = _setup(tmp_path, result_u=-0.5, tx="missing_digest",
                                 mutate_to=0.5)
    search._step_conditional(state, Path(tmp_path), None, None)
    assert state["conditional_recovery"]["code"] == "COMPLETION_SUMMARY_DIGEST_MISSING"


def test_stale_digest_names_the_specific_block(tmp_path, no_real_work):
    state, _iter_dir, _ = _setup(tmp_path, result_u=-0.5, tx="stale_digest",
                                 mutate_to=0.5)
    search._step_conditional(state, Path(tmp_path), None, None)
    assert (state["conditional_recovery"]["code"]
            == "COMPLETION_SUMMARY_DIGEST_MISMATCH")


def test_unreadable_transaction_blocks(tmp_path, no_real_work):
    state, _iter_dir, _ = _setup(tmp_path, result_u=-0.5, tx="unreadable")
    result = search._step_conditional(state, Path(tmp_path), None, None)
    assert result == {"terminal": "EXECUTION_FAILED"}
    assert (state["conditional_recovery"]["code"]
            == "COMPLETION_TRANSACTION_UNREADABLE")


def test_missing_result_file_blocks(tmp_path, no_real_work):
    state, _iter_dir, _ = _setup(tmp_path, result_u=None, tx="matching_digest")
    result = search._step_conditional(state, Path(tmp_path), None, None)
    assert result == {"terminal": "EXECUTION_FAILED"}
    assert state["conditional_recovery"]["code"] == "COMPLETION_RESULT_MISSING"
