"""生成回复结算只可触及当前预留，不能重写已 supersede 的失败成本。"""
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

import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import sitin_generate as generate  # noqa: E402
import sitin_search as search  # noqa: E402
from hangma_bot.policy.action_value_seeds import SEEDS  # noqa: E402


AUTHORIZATION = {
    "schema": "sitin-authorization/1",
    "allowed_accounts": {
        "tokens_input": 100000.0,
        "tokens_output": 100000.0,
    },
}


def _fixture_reply() -> str:
    """构造可由真实解析和预检接受的本地夹具回复，不调用模型。"""
    seed = SEEDS["efficiency_seed"]
    fence = chr(96) * 3
    return (
        "{结算回归夹具机制}\n\n"
        + fence + "json\n"
        + json.dumps({name: seed.mechanism[name]
                      for name in generate.AV_MECHANISM_FIELDS}, ensure_ascii=False)
        + "\n" + fence + "\n\n"
        + fence + "python\n" + seed.source + fence + "\n"
    )


def _row(ledger, reservation_id: str):
    return next(item for item in ledger.reservations
                if item["reservation_id"] == reservation_id)


def test_generation_usage_settles_only_current_reservation_after_recovery(tmp_path):
    """已结算并让位的失败调用保留原成本；本次 usage 只能结算新预留。

    真实 `_step_generate` 首先以 delegate 模式产生提示词，再摄入本地 envelope。
    中间模拟恢复对账：旧调用已结算失败、被标记 superseded，随后同一 step_id
    预留了一次新调用。旧行的 401/503 是失败成本，绝不能被本次 111/222 覆盖。
    """
    run_root = tmp_path / "settlement"
    state = search.av_start_iteration(run_root, authorization=AUTHORIZATION)
    ledger = search._av_ledger_for_run(run_root, AUTHORIZATION)

    # 真实生成入口先发出 delegate 交接件；没有网络或模型调用。
    assert search._step_generate(state, run_root, ledger, None) == {
        "waiting_for_reply": True,
    }

    old_input = _row(ledger, "iter1:gen-tokens-in#1")
    old_output = _row(ledger, "iter1:gen-tokens-out#2")
    ledger.settle(old_input, actual=401.0, note="旧调用失败，成本保留")
    ledger.settle(old_output, actual=503.0, note="旧调用失败，成本保留")
    ledger.supersede(step_id="iter1:gen-tokens-in", account="tokens_input",
                     reason="恢复后重试")
    ledger.supersede(step_id="iter1:gen-tokens-out", account="tokens_output",
                     reason="恢复后重试")
    current_input = ledger.reserve(step_id="iter1:gen-tokens-in",
                                   account="tokens_input", amount=2048.0,
                                   note="恢复后的当前调用")
    current_output = ledger.reserve(step_id="iter1:gen-tokens-out",
                                    account="tokens_output", amount=8192.0,
                                    note="恢复后的当前调用")

    envelope = Path(state["iter_dir"]) / "reply-envelope.json"
    envelope.write_text(json.dumps({
        "schema": "sitin-generation-reply/1",
        "origin": "delegated_model_reply",
        "prompt_sha256": state["generation"]["prompt_sha256"],
        "reply": _fixture_reply(),
        "provider": "local-test", "model": "fixture",
        "captured_at_utc": "2026-09-19T00:00:00Z",
        "delegator": "settlement-regression",
        "usage": {"input_tokens": 111, "output_tokens": 222},
    }, ensure_ascii=False), encoding="utf-8")

    assert search._step_generate(state, run_root, ledger, None) == {
        "advanced": "GENERATED",
    }

    # 失败成本在 supersede 后仍可审计；本次 envelope 的实际用量只属于新预留。
    old_input_after = _row(ledger, old_input["reservation_id"])
    old_output_after = _row(ledger, old_output["reservation_id"])
    assert old_input_after["status"] == "settled"
    assert old_output_after["status"] == "settled"
    assert old_input_after["superseded"] is True
    assert old_output_after["superseded"] is True
    assert old_input_after["charged"] == 401.0
    assert old_output_after["charged"] == 503.0
    assert _row(ledger, current_input["reservation_id"])["charged"] == 111.0
    assert _row(ledger, current_output["reservation_id"])["charged"] == 222.0
