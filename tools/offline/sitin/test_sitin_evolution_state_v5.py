# -*- coding: utf-8 -*-
"""R5 测试：进化编排状态机、五事务边界与中断恢复（新文件；不改现有测试）。

覆盖（REVIEW-V4 Q5 修复验收 / CONTINUOUS-EVOLUTION-PLAN §5 §7 §11）：
- 步骤状态机（state.json 原子落盘，§5 状态名逐个经过）；
- 真实生成步（delegate 文件式通道：产 pending 交接件停下等回复；恢复从
  已存在回复继续解析，不免费重发）；
- 真实评价步（R3 run_av_evaluation + R4 natural_panel 强制共享账本）；
- 真实档案步（R4 update_archive/apply_challenge(persist_dir) 持久档案）；
- 真实 resume（读落盘状态 → 核验身份 → 从当前步续跑，不重不漏）；
- ≥5 处中断点注入恢复（RESERVED 后 / GENERATED 后等待回复 / 评价中途 /
  刷新部分完成 / 批次结束前）；
- mock 生成保留为显式测试模式（--generation-mock 标注）；
- confirm 诚实化（confirmation_executor=pending，不冒充确认结果）。

真实验证全部用替身 runtime（0 真实桌赛 0 LLM）。
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
import shutil
import sys
import uuid
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import sitin_search as search  # noqa: E402
import sitin_generate as generate  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402
from hangma_bot.policy.action_value_seeds import SEEDS  # noqa: E402

#: 批次 7 授权令牌 + 账户额度（替身 runtime：0 真实桌赛，账面照记）。
TOKEN = {"authorized": True, "batch": 7,
         "budgets": {"tokens_input": 100000, "tokens_output": 200000,
                     "tables_full": 256, "tables_partial": 64,
                     "prefix_generation": 64}}


class FakeDrive:
    """替身桌赛驱动（0 真实桌赛）：焦点臂候选 +12 / 基线 -10（确定性 U 分离）。"""

    def __call__(self, *, plan, policies_by_seat, versions_block, step_limit,
                 value_limits):
        seats = list(plan.seats())
        focal_idx = seats.index("focal") if "focal" in seats \
            else seats.index("natural:focal")
        is_candidate = str(getattr(policies_by_seat[focal_idx], "policy_id",
                                   "")).startswith("action_value")
        offset = plan.seed % 7 - 3
        scores = []
        for seat in range(4):
            if seat == focal_idx:
                scores.append(12 + offset if is_candidate else -10 + offset)
            else:
                scores.append(2 - seat + (offset if seat % 2 else -offset))
        return {"table_id": plan.table_id, "seed": int(plan.seed),
                "match_status": "complete", "wall_ms": 1.0,
                "scores_by_seat": scores, "result": {}}


@pytest.fixture
def fake_runtime(monkeypatch):
    monkeypatch.setattr(natural, "execute_natural_table", FakeDrive(), raising=True)


def _run(tmp_path, tag, **kwargs):
    out = Path(tmp_path) / ("r5-" + tag + "-" + uuid.uuid4().hex[:6])
    return out, search.run_av_evolution(out, **kwargs)


def _state_of(run_root):
    state_path = search.av_latest_state_path(Path(run_root))
    assert state_path is not None
    return state_path, search.av_state_load(state_path)


def _mock_reply_text(seed_name):
    seed = SEEDS[seed_name]
    fence = chr(96) * 3
    return ("{" + seed_name + " 机制（R5 测试 mock）}\n\n"
            + fence + "json\n"
            + json.dumps({key: seed.mechanism[key]
                          for key in generate.AV_MECHANISM_FIELDS},
                         ensure_ascii=False) + "\n" + fence + "\n\n"
            + fence + "python\n" + seed.source + fence + "\n")


def _write_envelope(state, *, usage=None, origin="delegated_model_reply"):
    envelope = Path(state["iter_dir"]) / "reply-envelope.json"
    envelope.write_text(json.dumps({
        "schema": "sitin-generation-reply/1", "origin": origin,
        "prompt_sha256": state["generation"]["prompt_sha256"],
        "reply": _mock_reply_text("efficiency_seed"),
        "provider": "r5-test", "model": "fake-model",
        "captured_at_utc": "2026-09-17T00:00:00Z", "delegator": "r5-tests",
        **({"usage": usage} if usage else {})}, ensure_ascii=False),
        encoding="utf-8")
    return envelope


# ============================================================ 状态机主路径


def test_state_machine_happy_path_with_fake_runtime(tmp_path, fake_runtime):
    """状态机全链（mock 生成显式标注 + 替身桌赛）：§5 状态逐个经过 + 批次报告。"""
    out, result = _run(tmp_path, "happy", generation_mode="mock",
                       authorization=TOKEN)
    assert result.get("terminal") == "ITERATION_COMPLETE"
    state_path, state = _state_of(out)
    statuses = [item["status"] for item in state["step_history"]]
    # §5 主链（REFRESH_PENDING 是条件分支态，由刷新部分完成的专测覆盖）。
    for expected in ("RESERVED", "GENERATED", "ADMITTED", "BEHAVIOR_CHECKED",
                     "CONDITIONAL_EVALUATED", "NATURAL_EVALUATED", "SUMMARIZED",
                     "ARCHIVE_COMMITTED", "ITERATION_COMPLETE"):
        assert expected in statuses, expected
    # 五事务边界（§5 表）逐文件落盘。
    tx_dir = Path(state["iter_dir"]) / "transactions"
    for key in ("model_call_before", "generation_complete",
                "eval_conditional_begin", "eval_conditional_complete",
                "eval_natural_begin", "eval_natural_complete", "batch_end"):
        assert (tx_dir / search.AV_TX_FILES[key]).is_file(), key
    # §11 批次报告要素。
    report = json.loads((Path(state["iter_dir"]) / "batch-report.json")
                        .read_text(encoding="utf-8"))
    for field in ("completion_status", "stop_reason", "remaining_budget",
                  "evidence_refs", "next_task_package"):
        assert field in report, field
    assert report["completion_status"] == "ITERATION_COMPLETE"
    assert report["next_task_package"]["operator"] in ("I1", "M1")
    # 账目：生成 token 结算、自然桌赛按替身计划入账（0 真实桌赛）。
    ledger = search.ActionValueLedger.load(Path(out) / "av-ledger.json")
    # 声明混合 H+M：1 根×1 座×2 臂×2 桌×2 情景 = 8 桌（替身 runtime，0 真实）。
    assert ledger.spent("tables_full") == 8.0
    assert ledger.spent("prefix_generation") == 1.0
    # 持久档案与正常根台账。
    archive = json.loads((Path(out) / "archive" / "av-archive.json")
                         .read_text(encoding="utf-8"))
    assert state["identity"]["candidate_id"] in archive["entries"]
    assert (Path(out) / "archive" / "normal-roots.json").is_file()


def test_mock_generation_mode_explicitly_marked(tmp_path, fake_runtime):
    """mock 生成保留为显式测试模式：状态与批次报告都标注，不冒充模型输出。"""
    out, _ = _run(tmp_path, "mockmark", generation_mode="mock",
                  authorization=TOKEN)
    _, state = _state_of(out)
    assert state["generation"]["mode"] == "mock"
    assert state["generation"]["provenance"] == "offline_mock_fixture"
    tx = json.loads((Path(state["iter_dir"]) / "transactions"
                     / search.AV_TX_FILES["generation_complete"])
                    .read_text(encoding="utf-8"))
    assert tx["provenance"] == "offline_mock_fixture"
    assert tx["usage_unknown"] is True  # mock 无 usage：保守未知，不标 0 免费


# ============================================================ 中断注入与恢复（≥5 处）


def test_interrupt_after_reserved_no_duplicate_reservations(tmp_path, fake_runtime):
    """中断点 1（RESERVED 后）：恢复续跑，token 预留不重复、状态历史不重。"""
    out, result = _run(tmp_path, "int1", generation_mode="mock",
                       authorization=TOKEN, stop_after="RESERVED")
    assert result.get("stopped_after") == "RESERVED"
    state_path, state = _state_of(out)
    assert state["status"] == "RESERVED"
    ledger = search.ActionValueLedger.load(Path(out) / "av-ledger.json")
    token_reservations = [item for item in ledger.reservations
                          if item["account"].startswith("tokens")]
    assert len(token_reservations) == 2
    resumed = search.run_av_machine_resume(out, run_id=state["run_id"],
                                           authorization=TOKEN)
    assert resumed.get("terminal") == "ITERATION_COMPLETE"
    ledger2 = search.ActionValueLedger.load(Path(out) / "av-ledger.json")
    token2 = [item for item in ledger2.reservations
              if item["account"].startswith("tokens")]
    assert len(token2) == 2  # 不重发不重记
    _, final = _state_of(out)
    statuses = [item["status"] for item in final["step_history"]]
    assert statuses.count("GENERATED") == 1
    assert statuses.count("ITERATION_COMPLETE") == 1


def test_interrupt_during_generation_waits_then_ingests_once(tmp_path, fake_runtime):
    """中断点 2（生成中途/等待回复）：delegate 产交接件后自然停下等待；
    不重发提示词，回复出现后继续解析一次。"""
    out, first = _run(tmp_path, "int2", generation_mode="delegate",
                      authorization=TOKEN)
    assert first.get("waiting_for_reply") is True
    state_path, state = _state_of(out)
    assert state["generation"]["phase"] == "prompt_emitted"
    pending = Path(state["generation"]["pending_dir"])
    prompt_sha = hashlib.sha256((pending / "prompt.txt").read_bytes()).hexdigest()
    tx_before = Path(state["iter_dir"]) / "transactions" / search.AV_TX_FILES[
        "model_call_before"]
    tx_sha = hashlib.sha256(tx_before.read_bytes()).hexdigest()
    # 回复未出现：恢复仍在等待，提示词与调用前事务逐字节不变。
    again = search.run_av_machine_resume(out, run_id=state["run_id"],
                                         authorization=TOKEN)
    assert again.get("waiting_for_reply") is True
    assert hashlib.sha256((pending / "prompt.txt").read_bytes()).hexdigest() == prompt_sha
    assert hashlib.sha256(tx_before.read_bytes()).hexdigest() == tx_sha
    # 回复出现：继续解析并跑完全链。
    _write_envelope(state, usage={"input_tokens": 111, "output_tokens": 222})
    done = search.run_av_machine_resume(out, run_id=state["run_id"],
                                        authorization=TOKEN)
    assert done.get("terminal") == "ITERATION_COMPLETE"
    assert hashlib.sha256((pending / "prompt.txt").read_bytes()).hexdigest() == prompt_sha
    _, final = _state_of(out)
    assert final["generation"]["phase"] == "ingested"
    gen_tx = json.loads((Path(final["iter_dir"]) / "transactions"
                         / search.AV_TX_FILES["generation_complete"])
                        .read_text(encoding="utf-8"))
    assert gen_tx["usage"] == {"input_tokens": 111, "output_tokens": 222}
    ledger = search.ActionValueLedger.load(Path(out) / "av-ledger.json")
    assert ledger.spent("tokens_input") == 111.0
    assert ledger.spent("tokens_output") == 222.0


def test_interrupt_mid_evaluation_reuses_conditional_result(tmp_path, fake_runtime):
    """中断点 3（评价中途）：条件评价产物复用不重跑、账不双计。"""
    out, result = _run(tmp_path, "int3", generation_mode="mock",
                       authorization=TOKEN, stop_after="CONDITIONAL_EVALUATED")
    assert result.get("stopped_after") == "CONDITIONAL_EVALUATED"
    state_path, state = _state_of(out)
    eval_path = Path(state["conditional"]["evaluation_path"])
    eval_sha = hashlib.sha256(eval_path.read_bytes()).hexdigest()
    resumed = search.run_av_machine_resume(out, run_id=state["run_id"],
                                           authorization=TOKEN)
    assert resumed.get("terminal") == "ITERATION_COMPLETE"
    # 条件评价未被重跑（文件逐字节不变）。
    assert hashlib.sha256(eval_path.read_bytes()).hexdigest() == eval_sha
    ledger = search.ActionValueLedger.load(Path(out) / "av-ledger.json")
    prefix = [item for item in ledger.reservations
              if item["account"] == "prefix_generation"]
    assert len(prefix) == 1
    _, final = _state_of(out)
    statuses = [item["status"] for item in final["step_history"]]
    assert statuses.count("CONDITIONAL_EVALUATED") == 1


def test_refresh_partial_keeps_old_epoch_and_resume_is_idempotent(tmp_path,
                                                                  fake_runtime):
    """中断点 4（刷新部分完成）：REFRESH_PENDING 保持旧席位；恢复幂等不重计。

    迭代 1（H+M 声明混合）建 epoch；迭代 2 新候选用**不同 panel_seed** 产生
    epoch 外新根 → 在位者缺刷新根 → apply_challenge pending_partial →
    REFRESH_PENDING（旧席位保留，不混新旧均值）。

    P7b（R7 修复）：状态机不再永久停在补根态——它按剩余 tables_full 预算补根后重试
    同一条提交路径（提交条件不变）。本用例因此把"停在 pending"的断言换成**补根路径
    + 续跑幂等**断言：事务基准仍是原席（补根只补证据）、补根逐（身份 × 情景）只评
    一次、第二次恢复零费用零改动、实例台账逐键最多完成一次。
    """
    out1, r1 = _run(tmp_path, "rf1", generation_mode="mock", opponent="H",
                    seed_name="efficiency_seed", authorization=TOKEN)
    assert r1.get("terminal") == "ITERATION_COMPLETE"
    epoch_path = Path(out1) / "archive" / "normal-epoch.json"
    assert epoch_path.is_file()  # H+M 首轮即齐，首次提交即建通道 epoch
    epoch = json.loads(epoch_path.read_text(encoding="utf-8"))
    archive_before = json.loads((Path(out1) / "archive" / "av-archive.json")
                                .read_text(encoding="utf-8"))
    # 迭代 2：新候选 + 不同 panel_seed + 2 根×H/M（=4 根冻结刷新批）→在位者缺刷新根。
    r3 = search.run_av_evolution(out1, generation_mode="mock", opponent="H",
                                 seed_name="route_value_seed",
                                 panel_seed=20270101, natural_roots=2,
                                 authorization=TOKEN,
                                 stop_after="SUMMARIZED")
    ledger_path = Path(out1) / "av-ledger.json"
    spent_before_resume = search.ActionValueLedger.load(
        ledger_path).spent("tables_full")
    # 桌赛账（恢复前）：迭代 1（1根×H/M=8）+迭代 2（2根×H/M=16）=24。
    assert spent_before_resume == 24.0
    r3b = search.run_av_machine_resume(out1, run_id=r3["run_id"],
                                       authorization=TOKEN)
    _, state3 = _state_of(out1)
    statuses3 = [item["status"] for item in state3["step_history"]]
    # P7b（R7 修复）：状态机不再永久停在补根态——它按剩余 tables_full 预算为缺失身份
    # 补根后重试**同一条提交路径**（提交条件不变：全员在旧根+新根齐备才换 epoch）。
    # 因此断言改为核对补根路径与续跑幂等（旧断言断言的是"状态机永不自行补根"这一缺陷）。
    assert "REFRESH_PENDING" in statuses3
    assert statuses3.index("REFRESH_PENDING") < statuses3.index("ITERATION_COMPLETE")
    fill_tx = json.loads((Path(state3["iter_dir"]) / "transactions"
                          / search.AV_TX_FILES["refresh_fill"]).read_text(
                              encoding="utf-8"))
    # 事务基准仍是**原席位**：补根只补证据（entries），不自行换席。
    assert fill_tx["seats_before"] == archive_before["slots"]["overall"]
    assert fill_tx["rounds"][0]["refresh_status"] == "pending_partial"
    assert fill_tx["outcome"]["status"] == "committed"
    filled = [row for rnd in fill_tx["rounds"] for row in rnd["filled"]]
    # 补根逐（身份 × 情景）执行一次且确有新根入账（挑战者通道根 H/M + 原席者刷新根 H/M）。
    assert len(filled) == 4
    assert all(row["roots_added"] for row in filled)
    assert len({(row["candidate_id"], row["opponent_mix"]) for row in filled}) == 4
    # 补根账目：逐（身份 × 情景）一行、全额结算、费用与执行桌数一致，恢复后不留卡账。
    ledger = search.ActionValueLedger.load(ledger_path)
    refresh_rows = [row for row in ledger.reservations
                    if str(row["step_id"]).startswith("refresh:")]
    assert [row["charged"] for row in refresh_rows] == [4.0, 4.0, 8.0, 8.0]
    assert all(row["status"] == "settled" for row in refresh_rows)
    assert all(row["status"] == "settled" for row in ledger.reservations)
    assert ledger.spent("tables_full") == spent_before_resume + 24.0
    # 实例台账：补根按身份落账，且**同一实例最多完成一次**（不重复评价、不重复计费）。
    instances = search.av_instances_load(out1)["instances"]
    assert {row.get("participant_id") for row in instances.values()
            if row.get("participant_id")} == {row["candidate_id"] for row in filled}
    assert all(len([item for item in (row.get("attempts") or [])
                    if item.get("status") == "completed"]) <= 1
               for row in instances.values())
    # epoch 由"补根齐备后的提交"推进：旧根集仍是新根集前缀（不偷换比较基准）。
    epoch_after = json.loads(epoch_path.read_text(encoding="utf-8"))
    assert epoch_after["epoch"] == epoch["epoch"] + 1
    assert [row["root_id"] for row in epoch_after["roots"]][:len(epoch["roots"])] == [
        row["root_id"] for row in epoch["roots"]]
    # 续跑幂等（至少与旧断言同强）：终态再恢复零费用、零账目变化、零新实例、
    # 席位与 epoch 不动；实例台账逐键只完成一次（不重复评价同一实例）。
    spent_after_first = ledger.spent("tables_full")
    instances_before_again = json.loads((Path(out1) / "instances.json")
                                        .read_text(encoding="utf-8"))["instances"]
    seats_after_first = json.loads((Path(out1) / "archive" / "av-archive.json")
                                   .read_text(encoding="utf-8"))["slots"]
    again = search.run_av_machine_resume(out1, run_id=r3["run_id"],
                                         authorization=TOKEN)
    assert again.get("terminal") == "ITERATION_COMPLETE"
    ledger_again = search.ActionValueLedger.load(ledger_path)
    assert ledger_again.spent("tables_full") == spent_after_first
    assert json.loads((Path(out1) / "instances.json").read_text(
        encoding="utf-8"))["instances"] == instances_before_again
    assert json.loads((Path(out1) / "archive" / "av-archive.json").read_text(
        encoding="utf-8"))["slots"] == seats_after_first
    assert json.loads(epoch_path.read_text(encoding="utf-8"))["epoch"] == 2


def test_interrupt_before_batch_end_completes_report(tmp_path, fake_runtime):
    """中断点 5（批次结束前）：ARCHIVE_COMMITTED 停 → resume 写批次报告收尾。"""
    out, result = _run(tmp_path, "int5", generation_mode="mock",
                       authorization=TOKEN, stop_after="ARCHIVE_COMMITTED")
    assert result.get("stopped_after") == "ARCHIVE_COMMITTED"
    state_path, state = _state_of(out)
    assert not (Path(state["iter_dir"]) / "batch-report.json").is_file()
    resumed = search.run_av_machine_resume(out, run_id=state["run_id"],
                                           authorization=TOKEN)
    assert resumed.get("terminal") == "ITERATION_COMPLETE"
    _, final = _state_of(out)
    report = json.loads((Path(final["iter_dir"]) / "batch-report.json")
                        .read_text(encoding="utf-8"))
    assert report["schema"] == search.AV_BATCH_REPORT_SCHEMA
    tx_end = json.loads((Path(final["iter_dir"]) / "transactions"
                         / search.AV_TX_FILES["batch_end"]).read_text(encoding="utf-8"))
    assert tx_end["stop_reason"] == report["stop_reason"]


# ============================================================ 身份核验与诚实化


def test_machine_resume_identity_mismatch_rejected(tmp_path, fake_runtime):
    """resume 身份核验：提供的身份字段与在案不符 → 拒绝续写。"""
    out, _ = _run(tmp_path, "ident", generation_mode="mock",
                  authorization=TOKEN, stop_after="GENERATED")
    state_path, state = _state_of(out)
    good = {"candidate_id": state["identity"]["candidate_id"],
            "contract_sha256": state["identity"]["contract_sha256"]}
    ok = search.run_av_machine_resume(out, run_id=state["run_id"], identity=good,
                                      authorization=TOKEN)
    assert not ok.get("refused")
    tampered = dict(good)
    tampered["candidate_id"] = "0" * 64
    refused = search.run_av_machine_resume(out, run_id=state["run_id"],
                                           identity=tampered, authorization=TOKEN)
    assert refused.get("refused") and "candidate_id" in refused["refused"]
    wrong_run = search.run_av_machine_resume(out, run_id="deadbeef",
                                             identity=good, authorization=TOKEN)
    assert wrong_run.get("refused") and "run_id" in wrong_run["refused"]


def test_confirm_output_marks_confirmation_executor_pending(tmp_path):
    """confirm 诚实化：有授权时输出只到提名，confirmation_executor=pending。"""
    archive_mod = search.av_archive()
    roots = [{"root_id": "np-H-x-r01", "opponent_mix": "H"},
             {"root_id": "np-M-x-r01", "opponent_mix": "M"}]
    epoch = archive_mod.build_channel_epoch("normal", roots)
    archive_path = Path(tmp_path) / "archive.json"
    archive_path.write_text(json.dumps(
        {"schema": "sitin-archive/1", "entries": {}, "slots": {}},
        ensure_ascii=False), encoding="utf-8")
    epoch_path = Path(tmp_path) / "epoch.json"
    epoch_path.write_text(json.dumps(epoch, ensure_ascii=False), encoding="utf-8")
    result = search.run_av_confirm(
        Path(tmp_path) / "confirm-out", archive_path, epoch_path,
        confirm_authorization={"authorized": True, "confirm_budget": 8.0})
    assert result["ok"] is True
    assert result["confirmation_executor"] == "pending"
    assert "不冒充确认结果" in result["note"]
    assert "提名" in result["note"]


def test_evolve_cli_help_reflects_state_machine():
    """--help 反映真实流程（状态机/等待回复/显式 mock 模式）。"""
    import subprocess

    result = subprocess.run([sys.executable, str(_project_file(_PROJECT_ROOT, _HERE / "sitin_search.py")),
                             "evolve-action-value", "--help"],
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0
    text = result.stdout
    # argparse/textwrap 会对超长无空格 token 折行：先按行拼回再断言。
    joined = text.replace("\n", "")
    for marker in ("RESERVED", "ITERATION_COMPLETE", "--generation-mock",
                   "--reply-envelope", "state.json"):
        assert marker in joined, marker
    resume_help = subprocess.run([sys.executable, str(_project_file(_PROJECT_ROOT, _HERE / "sitin_search.py")),
                                  "resume", "--help"],
                                 capture_output=True, text=True, timeout=120)
    assert resume_help.returncode == 0
    assert "state.json" in resume_help.stdout


# ============================================================ P5（R7）：条件步运行时装配


def _test_double_runtime():
    """显式测试入口装配的验证替身（0 真实桌赛）。"""

    from hangma_bot.hangma.engine import HangmaRules
    from hangma_bot.hangma.interface import ValueAnalysisLimits
    from hangma_bot.kernel.config import RuleConfig

    return search.av_opportunities().build_test_runtime_double(
        rules=HangmaRules(RuleConfig("v26", 1, False)),
        value_limits=ValueAnalysisLimits())


def test_conditional_step_assembles_runtime_explicitly(tmp_path, fake_runtime):
    """(a)(b)：状态机在组合处显式装配运行时；替身只经显式测试入口注入。"""

    calls = []

    def factory():
        calls.append(1)
        return _test_double_runtime()

    out, result = _run(tmp_path, "p5-asm", generation_mode="mock",
                       prefix_source="v2_behavior", authorization=TOKEN,
                       test_runtime_factory=factory)
    assert result.get("terminal") == "ITERATION_COMPLETE", result.get("refused")
    assert calls == [1], "状态机未在组合处装配运行时"
    _, state = _state_of(out)
    assembly = state["plan"]["runtime_assembly"]
    assert assembly["entry"] == "build_test_runtime_double"
    assert assembly["explicit_test_entry"] is True
    assert assembly["runtime_kind"] == "test_double_runtime"
    assert assembly["execution_kind"] == "test_double"
    assert state["conditional"]["execution_kind"] == "test_double"
    assert state["conditional"]["engine_kind"] == "simulation_runtime_double"
    assert state["conditional"]["real_table_instances"] == 0
    evaluation = json.loads(
        Path(state["conditional"]["evaluation_path"]).read_text(encoding="utf-8"))
    assert evaluation["execution_kind"] == "test_double"
    assert evaluation["engine_kind"] == "simulation_runtime_double"
    assert evaluation["usable_for_selection"] is False
    assert evaluation["result_admission"]["ok"] is True
    tx = json.loads((Path(state["iter_dir"]) / "transactions"
                     / search.AV_TX_FILES["eval_conditional_complete"])
                    .read_text(encoding="utf-8"))
    assert tx["cost"]["real_table_instances"] == 0
    assert tx["execution_kind"] == "test_double"


def test_conditional_step_refuses_without_real_runtime(tmp_path, fake_runtime,
                                                       monkeypatch):
    """(a)：真实运行时装配失败即拒绝为终态，绝不回退替身或夹具。"""

    opportunities = search.av_opportunities()

    def boom(**kwargs):
        raise opportunities.RuntimeAssemblyError("构造：组合根运行时不可用")

    monkeypatch.setattr(opportunities, "build_real_runtime", boom)
    out, result = _run(tmp_path, "p5-nort", generation_mode="mock",
                       prefix_source="v2_behavior", authorization=TOKEN)
    assert result.get("terminal") == "EXECUTION_FAILED"
    _, state = _state_of(out)
    assert state["stop_reason"] == "runtime_assembly_missing"
    assert state["conditional"]["ok"] is False
    assert "运行时装配失败" in state["conditional"]["refused"]
    assert "不回退替身" in state["conditional"]["refused"]
    conditional_dir = Path(state["iter_dir"]) / "conditional"
    assert not (conditional_dir / "evaluation.json").is_file()
    # 未回退：没有替身/夹具产物，也没有 fake 面板。
    assert not list(conditional_dir.glob("panel-*/*.json"))


# ============================================================ P5（R7）：选留闸门


def test_fixture_conditional_samples_excluded_from_selection(tmp_path, fake_runtime):
    """A1：夹具/替身条件样本不参与统计与建档（排除量如实入 summary，不静默丢）。"""

    out, result = _run(tmp_path, "p5-gate", generation_mode="mock",
                       authorization=TOKEN)
    assert result.get("terminal") == "ITERATION_COMPLETE"
    _, state = _state_of(out)
    assert state["summary"]["n_samples_excluded_non_selectable"] == 1
    statistics_text = Path(state["summary"]["statistics_path"]).read_text(
        encoding="utf-8")
    # 条件面板（夹具）来源根不在统计里：只有自然面板样本参与。
    assert "av-eval-branch_open" not in statistics_text
    feedback = json.loads(Path(state["summary"]["feedback_path"])
                          .read_text(encoding="utf-8"))
    assert any("非真实运行时样本" in fact for fact in feedback["facts"])
    # 条件样本本身仍完整留档（原始产物保留，只是不参与选留）。
    evaluation = json.loads(
        Path(state["conditional"]["evaluation_path"]).read_text(encoding="utf-8"))
    assert evaluation["samples"][0]["selection_eligible"] is False
    assert evaluation["execution_kind"] == "scripted_fixture"
