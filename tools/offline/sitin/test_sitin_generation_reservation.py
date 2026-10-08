"""真实作者调用的 token 预留：显式容量、授权余额与旧令牌兼容性。"""
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

import sys
from pathlib import Path

import pytest


HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import sitin_search as search  # noqa: E402


@pytest.mark.parametrize("existing", ["in", "out"])
@pytest.mark.parametrize("settled", [False, True])
def test_partial_existing_reservation_rejected_without_new_ledger_write(tmp_path, existing, settled):
    ledger = search.ActionValueLedger.load(tmp_path / "ledger.json",
                  authorized_budgets={"tokens_input": 100, "tokens_output": 100})
    account = "tokens_input" if existing == "in" else "tokens_output"
    row = ledger.reserve(step_id="iter1:gen-tokens-" + existing, account=account, amount=10)
    if settled:
        ledger.settle(row, actual=10)
    before = ledger.path.read_bytes()
    with pytest.raises((search.DuplicateReservation, search.TaskAlreadySettled)):
        search._av_reserve_generation_tokens(ledger, iteration_no=1, tokens_input=10, tokens_output=10)
    assert ledger.path.read_bytes() == before
    assert len(ledger.reservations) == 1


def test_generation_pair_is_persisted_in_one_atomic_write(tmp_path, monkeypatch):
    ledger = search.ActionValueLedger.load(tmp_path / "ledger.json",
                  authorized_budgets={"tokens_input": 100, "tokens_output": 100})
    snapshots = []
    original_save = ledger.save

    def save():
        snapshots.append([row["account"] for row in ledger.reservations])
        original_save()

    monkeypatch.setattr(ledger, "save", save)
    search._av_reserve_generation_tokens(ledger, iteration_no=1, tokens_input=10, tokens_output=20)
    assert snapshots == [["tokens_input", "tokens_output"]]


def _authorization(*, tokens_input: float, tokens_output: float,
                   call_limits: object = None) -> dict:
    """最小授权令牌；None 表示不登记可选单次生成上界。"""
    authorization = {
        "schema": "sitin-authorization/1",
        "allowed_accounts": {
            "tokens_input": tokens_input,
            "tokens_output": tokens_output,
        },
    }
    if call_limits is not None:
        authorization["generation_call_limits"] = call_limits
    return authorization


def test_explicit_generation_call_limits_reserve_declared_capacity(tmp_path):
    """显式作者容量高于旧固定值时，预留必须保留声明上界而非 min 成旧值。"""
    state = search.av_start_iteration(
        tmp_path / "enough",
        authorization=_authorization(
            tokens_input=64000.0,
            tokens_output=48000.0,
            call_limits={"tokens_input": 32000.0, "tokens_output": 24000.0},
        ),
    )

    assert state["reservations"]["tokens_input"] == 32000.0
    assert state["reservations"]["tokens_output"] == 24000.0
    ledger = search.ActionValueLedger.load(
        tmp_path / "enough" / "av-ledger.json",
        authorized_budgets={"tokens_input": 64000.0, "tokens_output": 48000.0},
    )
    assert ledger.spent("tokens_input") == 32000.0
    assert ledger.spent("tokens_output") == 24000.0


def test_explicit_generation_call_limits_reject_low_budget_without_partial_reservation(tmp_path):
    """账户余额小于任一显式容量时，开轮直接拒绝且不能只留下另一维预留。"""
    authorization = _authorization(
        tokens_input=31999.0,
        tokens_output=24000.0,
        call_limits={"tokens_input": 32000.0, "tokens_output": 24000.0},
    )

    with pytest.raises(search.LedgerOverAuthorized, match="生成预留被拒"):
        search.av_start_iteration(tmp_path / "low-budget", authorization=authorization)

    ledger = search.ActionValueLedger.load(
        tmp_path / "low-budget" / "av-ledger.json",
        authorized_budgets=search.av_ledger_budgets_from_authorization(authorization),
    )
    assert ledger.reservations == []


@pytest.mark.parametrize(
    "call_limits",
    [
        {},
        {"tokens_input": 1},
        {"tokens_input": True, "tokens_output": 1},
        {"tokens_input": 1, "tokens_output": 0},
        {"tokens_input": 1, "tokens_output": float("inf")},
        [("tokens_input", 1), ("tokens_output", 1)],
    ],
    ids=["missing-both", "missing-output", "bool", "zero", "infinite", "not-mapping"],
)
def test_invalid_generation_call_limits_are_refused(tmp_path, call_limits):
    """只要声明该块，输入和输出都必须是正有限非布尔数。"""
    authorization = _authorization(tokens_input=100000.0, tokens_output=100000.0,
                                   call_limits=call_limits)

    with pytest.raises(ValueError, match="generation_call_limits"):
        search.av_start_iteration(tmp_path / "invalid", authorization=authorization)


def test_missing_generation_call_limits_keeps_legacy_min_reservation(tmp_path):
    """旧令牌不含该块时，仍使用历史固定值再按账户额度缩小的兼容路径。"""
    state = search.av_start_iteration(
        tmp_path / "legacy",
        authorization=_authorization(tokens_input=1000.0, tokens_output=5000.0),
    )

    assert state["reservations"]["tokens_input"] == 1000.0
    assert state["reservations"]["tokens_output"] == 5000.0
