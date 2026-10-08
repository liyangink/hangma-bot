# -*- coding: utf-8 -*-
"""D 包搜索路线测试（test_sitin_search_v4.py，新文件；不改现有测试）。

覆盖：T17 四类账目分列/12 上限/confirm 硬禁、T11 门禁版（mean_delta 为负
但家族专长仍入档并当父代）、新路线不读 resolved_positive、同源对账
（TaskContract 渲染 ↔ 执行器 ↔ 合同 JSON）、七命令 --help 与零预算
fail-closed 路由、resume 身份不符拒绝、§9.4 迭代顺序账完整性。
E 批次追加：evaluate-action-value 的 v2_behavior 前缀路由（参数校验/缺授权
拒绝/tables_partial 记账）与 sitin_natural_panel 自然面板的 0 桌结构测试
（假驱动：每根 2 臂 × 4 座位 × 2 桌、同 seed 断言、T16 失败路径）。
全部离线（mock/夹具），不调真实 LLM、不跑真实桌赛。
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
import argparse
import inspect
import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import sitin_search as search  # noqa: E402
import sitin_generate as generate  # noqa: E402
import sitin_gates as gates  # noqa: E402
from hangma_bot.policy.action_value_seeds import SEEDS  # noqa: E402

GOOD_SOURCE = SEEDS["route_value_seed"].source
TOOL = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/tools/sitin_search.py')
PY = sys.executable


def _tmp(path_base, tag):
    out = Path(path_base) / ("v4-" + tag + "-" + uuid.uuid4().hex[:6])
    out.mkdir(parents=True, exist_ok=True)
    return out


# ============================================================ T17 账目


def test_t17_ledger_four_account_columns_verifiable(tmp_path):
    """四类账目分列可核：token 输入/输出、桌赛完整/部分、前缀生成、确认预留。"""
    ledger = search.ActionValueLedger(tmp_path / "av-ledger.json",
                                      authorized_budgets=BUDGETS)
    ledger.reserve(step_id="s1", account="tokens_input", amount=120.0)
    ledger.reserve(step_id="s2", account="tokens_output", amount=3400.0)
    ledger.reserve(step_id="s3", account="tables_full", amount=2.0)
    ledger.reserve(step_id="s4", account="tables_partial", amount=1.0)
    ledger.reserve(step_id="s5", account="prefix_generation", amount=3.0)
    summary = ledger.account_summary()
    assert summary["tokens_input"] == 120.0
    assert summary["tokens_output"] == 3400.0
    assert summary["tables_full"] == 2.0
    assert summary["tables_partial"] == 1.0
    assert summary["prefix_generation"] == 3.0
    assert summary["confirm_reserved"] == 0.0
    # 台账可回读复核（先落盘后执行）。
    reloaded = search.ActionValueLedger.load(tmp_path / "av-ledger.json")
    assert reloaded.spent("tokens_output") == 3400.0
    assert reloaded.to_json()["worker_cap"] == 12


def test_t17_confirm_hard_frozen_without_authorization(tmp_path):
    """confirm 硬禁继承现状：无授权时任何 confirm 记账直接拒绝。"""
    ledger = search.ActionValueLedger(tmp_path / "av-ledger.json")
    with pytest.raises(search.ConfirmAccountFrozen):
        ledger.reserve(step_id="confirm:x", account="confirm_reserved", amount=1.0)
    assert ledger.spent("confirm_reserved") == 0.0
    # 授权文件语义：confirm_budget>0 且 authorized=true 才可动用。
    authorized = search.ActionValueLedger(tmp_path / "av-ledger2.json",
                                          confirm_authorized_budget=4.0)
    reservation = authorized.reserve(step_id="confirm:y",
                                     account="confirm_reserved", amount=1.0)
    authorized.settle(reservation, actual=1.0)
    assert authorized.spent("confirm_reserved") == 1.0


def test_t17_worker_cap_thirteen_processes_rejected(tmp_path):
    """全机工作进程上限 12：构造 13 进程请求 → 拒绝（T17）。"""
    ledger = search.ActionValueLedger(tmp_path / "av-ledger.json")
    ledger.request_workers(12, purpose="full machine")
    with pytest.raises(search.WorkerCapExceeded):
        ledger.request_workers(1, purpose="13th process")
    ledger.release_workers(12)
    ledger.request_workers(12)  # 释放后整批 12 可再次获批
    with pytest.raises(search.WorkerCapExceeded):
        ledger.request_workers(13)


def test_t17_confirm_command_refuses_without_budget(tmp_path):
    """confirm-action-value：无确认额度即拒并说明（退出码 3）。"""
    archive = tmp_path / "archive.json"
    archive.write_text(json.dumps({"schema": "sitin-archive/1", "entries": {},
                                   "slots": {}}), encoding="utf-8")
    epoch = tmp_path / "epoch.json"
    epoch.write_text(json.dumps({"schema": "sitin-channel-epoch/1"}), encoding="utf-8")
    result = search.run_av_confirm(_tmp(tmp_path, "confirm"), archive, epoch)
    assert result["ok"] is False
    assert "无确认额度" in result["refused"]
    assert "不从开发额度划拨" in result["refused"]


# ============================================================ T11 与 resolved_positive 弃用


def _panel_block(mean_delta):
    """构造 C2 可消费的面板块材料（样本由 build_evaluation_sample 形状简化）。"""
    return {"declared_mix": {"mean_delta": mean_delta}}


def test_t11_negative_overall_delta_family_specialty_still_archived(tmp_path):
    """T11 门禁版：mean_delta 为负但有家族专长的候选照样进入档案与父代调度。"""
    archive_mod = search.av_archive()

    def sample(root, scenario, mix, u_candidate, u_baseline=0.0):
        return {
            "source_root_id": root, "candidate_id": "av-cand-specialist",
            "scenario": scenario, "opponent_mix": mix,
            "arms": {
                "baseline": {"candidate_id": search.AV_BASELINE_ID,
                             "status": "complete", "usable": True,
                             "u": u_baseline, "u_low": u_baseline, "u_high": u_baseline},
                "candidate": {"candidate_id": "av-cand-specialist",
                              "status": "complete", "usable": True,
                              "u": u_candidate, "u_low": u_candidate,
                              "u_high": u_candidate},
            },
            "cost": 1.0,
        }

    samples = [
        # 正常面板：总体 mean_delta 为负（-0.5）。
        sample("nr-1", "normal", "H", 0.0, 0.5),
        sample("nr-2", "normal", "M", 0.0, 0.5),
        # 分支家族：机会/代价两子场景都为正（+0.5）。
        sample("br-1", "branch_open", "H", 1.0, 0.5),
        sample("br-2", "branch_open", "M", 1.0, 0.5),
        sample("br-3", "branch_cost", "H", 1.0, 0.5),
        sample("br-4", "branch_cost", "M", 1.0, 0.5),
    ]
    statistics = archive_mod.paired_stage_statistics(samples, min_roots=1)
    panels = statistics["by_candidate"]["av-cand-specialist"]["panels"]
    assert panels["normal"]["declared_mix"]["mean_delta"] == pytest.approx(-0.5)
    assert panels["normal"]["declared_mix"]["mean_delta"] < 0
    # 新路线档案更新：不读 resolved_positive；家族席按家族值入席。
    entries = [archive_mod.build_archive_entry("av-cand-specialist", samples,
                                               safety="PASS", min_roots=1)]
    archive = archive_mod.update_archive(entries)
    assert "av-cand-specialist" in archive["entries"]
    assert "av-cand-specialist" in archive["slots"]["branch"], archive["slots"]
    # 父代调度：家族席可被选为 M1 父代（§9.3 专长通道）。
    plan = archive_mod.next_generation_plan(archive, [])
    assert plan["operator"] in ("I1", "M1")
    plan_with_history = archive_mod.next_generation_plan(archive, [
        {"proposal_no": 1, "operator": "I1"}])
    if plan_with_history["operator"] == "M1":
        assert plan_with_history.get("parent_candidate_id") == "av-cand-specialist"


def test_new_route_never_reads_resolved_positive():
    """新 action_value_v1 路线阶段推进不得读 resolved_positive（源级红线）。

    检查实际访问形态（键访问/属性访问）；注释里说明"不读"不构成读取。
    旧 describe_statistics 用引号键访问，作为判别力对照。
    """
    import re
    pattern = re.compile(r"['\"]resolved_positive['\"]|\.resolved_positive\b")
    for func in (search.run_av_evaluation, search.run_av_iteration,
                 search.run_av_confirm, search.run_av_resume,
                 search.validate_action_value_contracts):
        source = inspect.getsource(func)
        assert not pattern.search(source), func.__name__
    # 判别力对照：旧函数的引号键访问必须命中（证明该检查不是永远绿）。
    assert pattern.search(inspect.getsource(search.describe_statistics))


# ============================================================ 同源对账


def test_task_contract_rendered_from_machine_contract_json(tmp_path):
    """TaskContract 渲染 ↔ 合同 JSON ↔ 执行器三方对账一致（§10 同源）。"""
    payload = generate.render_action_value_task_contract(
        objective_summary="测试目标", panel_boundary="测试面板", prompt_role="I1")
    text = generate.render_action_value_contract_text(payload)
    contract, digest = generate.load_action_value_contract()
    # 1) 渲染值 == JSON 值（不是手抄第二套）。
    assert str(contract["limits"]["candidate"]["max_counted_operations"]) in text
    assert contract["entry_point"]["signature"] in text
    assert "hu_mode={0}".format(contract["entry_point"]["hu_mode"]) in text
    assert payload["contract_sha256"] == digest
    # 2) JSON 值 == 执行器实际校验值。
    from hangma_bot.policy import action_value_executor as executor
    assert contract["limits"]["candidate"]["max_counted_operations"] == executor.MAX_COUNTED_OPERATIONS
    assert contract["limits"]["candidate"]["max_source_bytes"] == executor.MAX_SOURCE_BYTES
    assert set(contract["whitelist"]["builtins"]) == set(executor.ALLOWED_BUILTINS)
    # 3) 门禁与生成端读的是同一份合同（同源同一 sha）。
    gates_contract, gates_digest = gates.av_contract()
    assert gates_digest == digest
    assert gates_contract == contract


def test_task_contract_changes_when_json_limit_changes(tmp_path):
    """同源测试核心：改 JSON 一个限额值 → 渲染文本变化、sha 变化。"""
    raw = (search.REPO_ROOT / "review/llm-guided-heuristic-route-2026-09-15"
           / "contracts/action-value-v1.json").read_text(encoding="utf-8")
    modified = raw.replace('"max_counted_operations": 100000',
                           '"max_counted_operations": 12345')
    assert modified != raw
    mutated_path = tmp_path / "action-value-v1.json"
    mutated_path.write_text(modified, encoding="utf-8")
    generate._AV_CONTRACT_CACHE.clear()
    contract_orig, sha_orig = generate.load_action_value_contract()
    contract_mod, sha_mod = generate.load_action_value_contract(mutated_path)
    assert sha_mod != sha_orig
    text_mod = generate.render_action_value_contract_text(
        generate.render_action_value_task_contract(
            objective_summary="x", panel_boundary="y", prompt_role="z"))
    generate._AV_CONTRACT_CACHE.clear()
    assert "12345" in json.dumps(contract_mod)
    assert "100000" in json.dumps(contract_orig)


def test_validate_contract_rejects_drifted_contract(tmp_path):
    """validate-contract：与执行器对账；限额漂移的合同必须 ok=False。"""
    verdict = search.validate_action_value_contracts()
    assert verdict["ok"] is True, verdict["problems"]
    drifted = tmp_path / "drifted.json"
    raw = (search.REPO_ROOT / "review/llm-guided-heuristic-route-2026-09-15"
           / "contracts/action-value-v1.json").read_text(encoding="utf-8")
    drifted.write_text(raw.replace('"max_counted_operations": 100000',
                                   '"max_counted_operations": 99999'),
                       encoding="utf-8")
    bad = search.validate_action_value_contracts(action_value_path=drifted)
    assert bad["ok"] is False
    assert any("max_counted_operations" in problem for problem in bad["problems"])


# ============================================================ 七命令路由


SEVEN_COMMANDS = ("validate-contract", "build-panel", "admit-action-value",
                  "evaluate-action-value", "evolve-action-value",
                  "confirm-action-value", "resume")


def test_seven_commands_help_exit_zero():
    """§13.1 七命令 --help 全部退出码 0，且帮助里写真实调用示例。"""
    for command in SEVEN_COMMANDS:
        result = subprocess.run([PY, str(TOOL), command, "--help"],
                                capture_output=True, text=True, timeout=120)
        assert result.returncode == 0, (command, result.stderr[-400:])
        assert "usage:" in result.stdout or command in result.stdout


def test_seven_commands_router_help_lists_real_invocations():
    """--help 证据写真实调用（不是空壳子命令）。"""
    result = subprocess.run([PY, str(TOOL), "evolve-action-value", "--help"],
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "--seed" in combined and "--out" in combined
    top_help = subprocess.run([PY, str(TOOL), "--help"], capture_output=True,
                              text=True, timeout=120)
    for command in SEVEN_COMMANDS:
        assert command in top_help.stdout


def test_zero_budget_real_llm_fail_closed(tmp_path):
    """零预算红线：api/headless 真实 LLM 调用无授权 → fail-closed（不读私凭据）。"""
    out = _tmp(tmp_path, "gen-api")
    result = subprocess.run(
        [PY, str(_project_file(_PROJECT_ROOT, _HERE / "sitin_generate.py")), "i1",
         "--candidate-kind", "action_value_v1", "--backend", "api",
         "--out", str(out)],
        capture_output=True, text=True, timeout=120, cwd=str(search.REPO_ROOT))
    assert result.returncode == 3
    assert "fail-closed" in result.stdout
    assert ".private/sitin-llm.json" in result.stdout


def test_zero_budget_real_table_fail_closed(tmp_path):
    """零预算红线：真实桌赛请求无授权 → fail-closed（evaluate/evolve 路由）。"""
    with pytest.raises(search.BudgetExhausted):
        search.run_av_evaluation(_tmp(tmp_path, "eval-real"), GOOD_SOURCE,
                                 real_tables=True, authorization=None)


def test_offline_replay_generation_route_allowed(tmp_path):
    """离线路由可用：replay 夹具跑通 action_value 生成路径（不调真实 LLM）。"""
    source = SEEDS["efficiency_seed"].source
    fence = chr(96) * 3
    reply = ("{效率种子机制（测试夹具）}\n\n" + fence + "json\n"
             + json.dumps({key: SEEDS["efficiency_seed"].mechanism[key]
                           for key in generate.AV_MECHANISM_FIELDS},
                          ensure_ascii=False) + "\n" + fence + "\n\n"
             + fence + "python\n" + source + fence + "\n")
    envelope = tmp_path / "reply.json"
    envelope.write_text(json.dumps({
        "schema": "sitin-generation-reply/1", "origin": "format_fixture",
        "prompt_sha256": None, "reply": reply,
        "author": "test", "purpose": "offline route validation"},
        ensure_ascii=False), encoding="utf-8")
    # prompt_sha256 需逐字节一致：先 dry-run 拿提示词哈希再封套。
    out = _tmp(tmp_path, "gen-replay")
    dry = subprocess.run(
        [PY, str(_project_file(_PROJECT_ROOT, _HERE / "sitin_generate.py")), "i1",
         "--candidate-kind", "action_value_v1", "--backend", "replay",
         "--out", str(out), "--dry-run"],
        capture_output=True, text=True, timeout=120, cwd=str(search.REPO_ROOT))
    assert dry.returncode == 0
    prompt_sha = dry.stderr.strip().split("prompt_sha256:")[-1].strip()
    envelope.write_text(json.dumps({
        "schema": "sitin-generation-reply/1", "origin": "format_fixture",
        "prompt_sha256": prompt_sha, "reply": reply,
        "author": "test", "purpose": "offline route validation"},
        ensure_ascii=False), encoding="utf-8")
    run = subprocess.run(
        [PY, str(_project_file(_PROJECT_ROOT, _HERE / "sitin_generate.py")), "i1",
         "--candidate-kind", "action_value_v1", "--backend", "replay",
         "--replay", str(envelope), "--out", str(out)],
        capture_output=True, text=True, timeout=300, cwd=str(search.REPO_ROOT))
    assert run.returncode == 0, run.stdout[-400:] + run.stderr[-400:]
    summary = json.loads(run.stdout)
    assert summary["parse_status"] == "ok"
    assert summary["precheck_ok"] is True
    assert summary["load_ok"] is True
    assert summary["candidate_id"]


# ============================================================ 迭代与 resume


def test_iteration_follows_fixed_order_with_complete_ledger(tmp_path):
    """§9.4 迭代顺序账完整性：九步按固定顺序落账、账目分列、真实桌赛恒 0。"""
    result = search.run_av_iteration(_tmp(tmp_path, "iter"), authorization=BUDGET_TOKEN)
    assert result["ok"] is True
    assert [item["step"] for item in result["steps"]] == list(search.AV_ITERATION_ORDER)
    assert all(item["status"] in ("ok", "PASS") for item in result["steps"])
    assert result["ledger"]["spent"]["tokens_input"] == 0.0
    assert result["ledger"]["spent"]["tables_full"] == 0
    assert result["ledger"]["spent"]["prefix_generation"] >= 1.0
    assert result["ledger"]["spent"]["confirm_reserved"] == 0
    assert "real_table_instances" not in result  # 迭代层不直存；评估层恒为 0（另有专测）


def test_evaluation_zero_real_tables_and_identity_binding(tmp_path):
    """evaluate 产物：evaluation_id 身份绑定齐全；真实桌赛实例恒 0（夹具）。"""
    evaluation = search.run_av_evaluation(_tmp(tmp_path, "eval"), GOOD_SOURCE,
                                          authorization=BUDGET_TOKEN)
    assert evaluation["ok"] is True
    identity = evaluation["identity"]
    for key in ("candidate_id", "evaluation_id", "baseline_id",
                "target_contract_sha256", "opponent_mix", "panel_epoch",
                "executor_version", "contract_sha256"):
        assert identity.get(key), key
    assert evaluation["real_table_instances"] == 0
    assert evaluation["panel"]["budget_red_line"]["real_table_instances_started"] == 0
    assert evaluation["fixture_mode"] is True
    feedback = evaluation["feedback"]
    for segment in ("facts", "associated_results", "mechanism_hypothesis"):
        assert segment in feedback
    assert "确认集" in feedback["boundary"]


def test_resume_identity_mismatch_rejected(tmp_path):
    """resume：run_id + 完整身份核验恢复；任何身份不符拒绝续写。"""
    out = _tmp(tmp_path, "iter-resume")
    result = search.run_av_iteration(out, authorization=BUDGET_TOKEN)
    run_id = result["run_id"]
    identity = dict(result["identity"])
    ok = search.run_av_resume(out, run_id=run_id, identity=identity)
    assert ok["ok"] is True
    # 逐字段篡改 → 拒绝。
    for field in ("candidate_id", "evaluation_id", "panel_epoch", "contract_sha256"):
        tampered = dict(identity)
        tampered[field] = "tampered-" + field
        refused = search.run_av_resume(out, run_id=run_id, identity=tampered)
        assert refused["ok"] is False
        assert field in refused["refused"], field
    # run_id 不符 → 拒绝。
    wrong_run = search.run_av_resume(out, run_id="deadbeef", identity=identity)
    assert wrong_run["ok"] is False and "run_id 不符" in wrong_run["refused"]


def test_legacy_search_subcommands_untouched():
    """旧 delta 分流回归：旧子命令仍在、旧入口函数未被新节改名。"""
    for name in ("plan", "run", "stage", "status", "freeze", "correct"):
        assert callable(getattr(search, "cmd_" + name, None)), name
    # 旧 resolved_positive 语义原样保留在旧函数里（只在新路线弃用）。
    legacy = inspect.getsource(search.describe_statistics)
    assert "resolved_positive" in legacy


# ============================================================ E 批次：v2_behavior 真实评估路由


#: P14：自然面板授权门统一到 Q6 受信校验入口（与状态机同一判据）：legacy 形态
#: 照样接受，但"本次操作所需账户须已声明额度"必须满足，故令牌带最小 budgets；
#: 具体额度由 BUDGET_TOKEN/BUDGETS 提供（台账测试用）。
BATCH7_TOKEN = {"authorized": True, "batch": 7,
                "scope": "批次7(E最小真实闭环) 测试令牌",
                "budgets": {"tables_full": 1.0}}

#: Q3（R4）：开发账户授权额度——fail-closed 后正数记账必须在授权总额内。
BUDGETS = {"tokens_input": 8_000_000.0, "tokens_output": 8_000_000.0,
           "tables_full": 512.0, "tables_partial": 512.0, "prefix_generation": 64.0}
BUDGET_TOKEN = {**BATCH7_TOKEN, "budgets": BUDGETS}


def test_v2_behavior_route_without_authorization_refused(tmp_path):
    """v2_behavior 路由缺授权：fail-closed 抛 BudgetExhausted，不建面板不记账。"""
    out = _tmp(tmp_path, "v2-noauth")
    with pytest.raises(search.BudgetExhausted):
        search.run_av_evaluation(out, GOOD_SOURCE, prefix_source="v2_behavior")
    assert not (out / "panel-branch_open").exists()


def test_v2_behavior_invalid_prefix_source_rejected(tmp_path):
    """prefix_source 白名单：未知值直接 ValueError（不静默按夹具跑）。"""
    with pytest.raises(ValueError):
        search.run_av_evaluation(_tmp(tmp_path, "v2-badsrc"), GOOD_SOURCE,
                                 prefix_source="replay_phantom",
                                 authorization=BATCH7_TOKEN)


def test_v2_behavior_authorized_run_marks_test_double_honestly(tmp_path):
    """授权 v2_behavior（唯一合法替身来源=显式测试入口）：生成器
    v2-behavior-prefix-v1；替身不启动真实桌赛 → tables_partial/tables_full 恒 0，
    替身次数另记 double_table_instances（费用账不再暗示真实执行）。"""
    out = _tmp(tmp_path, "v2-auth")
    ledger = search.ActionValueLedger(out / "av-ledger.json",
                                      authorized_budgets=BUDGETS)
    evaluation = search.run_av_evaluation(
        out, GOOD_SOURCE, prefix_source="v2_behavior",
        authorization=BATCH7_TOKEN, attempts_cap=16, ledger=ledger,
        test_runtime=_test_double_runtime())
    attempts = evaluation["panel"]["prefix_attempts"]
    assert attempts["total"] >= 1 and attempts["hit"] >= 1
    assert evaluation["prefix_source"] == "v2_behavior"
    assert evaluation["panel"]["generator"] == "v2-behavior-prefix-v1"
    assert evaluation["fixture_mode"] is False
    assert evaluation["execution_kind"] == "test_double"
    assert evaluation["engine_kind"] == "simulation_runtime_double"
    assert evaluation["real_table_instances"] == 0
    assert evaluation["double_table_instances"] == attempts["total"]
    assert ledger.spent("tables_partial") == 0.0
    assert ledger.spent("tables_full") == 0.0
    assert ledger.spent("prefix_generation") == 1.0
    sample = evaluation["samples"][0]
    assert sample["fixture_mode"] is False
    assert sample["real_table_instances"] == 0
    # R6 缺口1 修复：双臂消费 build_panel 的完整阶段结果——真策略身份
    # （非 fixture* 替身）、阶段 U 识别区间为数字、完整阶段桌记 tables_full。
    for name, arm in sample["arms"].items():
        assert not str(arm["policy_id"]).startswith("fixture"), (name, arm)
        assert arm["u_low"] is not None and arm["u_high"] is not None, (name, arm)
    raw_arms = (evaluation.get("double_arm") or {}).get("arms") or {}
    assert all(len(arm.get("tables") or []) == 2 for arm in raw_arms.values())
    panel_block = evaluation["panel"]
    assert panel_block["tables_full_executed"] == 4  # 2 臂 × 2 桌（替身执行）
    assert isinstance(panel_block.get("prefix_attempt_errors"), list)


def test_scripted_fixture_route_unchanged_no_partial_charge(tmp_path):
    """回归守卫：缺省 scripted_fixture 原行为不变（tables_partial 恒 0）。"""
    out = _tmp(tmp_path, "fixture-regress")
    ledger = search.ActionValueLedger(out / "av-ledger.json",
                                      authorized_budgets=BUDGETS)
    evaluation = search.run_av_evaluation(out, GOOD_SOURCE, ledger=ledger)
    assert evaluation["prefix_source"] == "scripted_fixture"
    assert evaluation["fixture_mode"] is True
    assert evaluation["real_table_instances"] == 0
    assert ledger.spent("tables_partial") == 0.0
    assert ledger.spent("prefix_generation") == 1.0


def test_build_evaluation_sample_fixture_flags_threaded(tmp_path):
    """build_evaluation_sample：缺省 fixture 标注不变；v2 路由如实透传。"""
    from hangma_bot.policy.action_value_seeds import SEEDS as _SEEDS
    opportunities = search.av_opportunities()
    panel = opportunities.build_panel(
        prefix_source="scripted_fixture", predicate_id="branch_open", focal_seat=0,
        opponent_scenario="H", root_label="flag-probe",
        out_dir=tmp_path / "panel", ruleset_version="v26", base_score=1,
        you_cai_bi_kao=False, attempts_cap=4, panel_seed=20260916)
    scenario = next(item for item in panel["scenarios"] if item.get("status") == "sampled")
    double_arm = opportunities.run_double_arm(
        rules=opportunities.HangmaRules(opportunities.RuleConfig(
            ruleset_version="v26", base_score=1, you_cai_bi_kao=False)),
        snapshot=scenario["snapshot"],
        baseline_policies_by_seat=[
            opportunities.FixtureBehaviorPolicy("b", prefer=("pass",))] * 4,
        candidate_policies_by_seat=[
            opportunities.FixtureBehaviorPolicy("c", prefer=("peng:5w",))] * 4,
        config=opportunities._driver_config(),
        value_limits=opportunities.ValueAnalysisLimits())
    default = search.build_evaluation_sample(
        panel=panel, double_arm=double_arm, candidate_id="cid",
        scenario="branch_open", opponent_mix="H")
    assert default["fixture_mode"] is True and default["real_table_instances"] == 0
    flagged = search.build_evaluation_sample(
        panel=panel, double_arm=double_arm, candidate_id="cid",
        scenario="branch_open", opponent_mix="H", fixture_mode=False,
        real_table_instances=5)
    assert flagged["fixture_mode"] is False
    assert flagged["real_table_instances"] == 5


def test_cli_v2_behavior_requires_both_authorizations(tmp_path, capsys):
    """CLI 真实模式：--prefix-source v2_behavior 缺 --v2-authorization 即拒（码 3）。"""
    token_path = tmp_path / "token.json"
    token_path.write_text(json.dumps(BATCH7_TOKEN), encoding="utf-8")
    args = argparse.Namespace(
        candidate_source=_write_source(tmp_path), sub_scenario="branch_open",
        opponent="H", out=str(tmp_path / "out"), attempts_cap=4,
        panel_seed=20260916, prefix_source="v2_behavior",
        real_authorization=str(token_path), v2_authorization=None)
    assert search.cmd_evaluate_action_value(args) == 3
    refused = json.loads(capsys.readouterr().out)
    assert "--v2-authorization" in refused["refused"]


def test_cli_v2_behavior_accepts_same_file_both_flags(tmp_path):
    """CLI 真实模式：--real-authorization 与 --v2-authorization 同文件即可跑通。"""
    token_path = tmp_path / "token.json"
    token_path.write_text(json.dumps(BUDGET_TOKEN), encoding="utf-8")
    args = argparse.Namespace(
        candidate_source=_write_source(tmp_path), sub_scenario="branch_open",
        opponent="H", out=str(tmp_path / "out"), attempts_cap=4,
        panel_seed=20260916, prefix_source="v2_behavior",
        real_authorization=str(token_path), v2_authorization=str(token_path))
    assert search.cmd_evaluate_action_value(args) == 0
    evaluation = json.loads((tmp_path / "out" / "evaluation.json").read_text(encoding="utf-8"))
    assert evaluation["prefix_source"] == "v2_behavior"


def _write_source(tmp_path):
    source = tmp_path / "candidate.py"
    source.write_text(GOOD_SOURCE, encoding="utf-8")
    return str(source)


# ============================================================ E 批次：自然面板（0 桌结构测试）


def _contract():
    return json.loads((_project_file(_PROJECT_ROOT, _HERE.parent / "contracts" / "group-dev-v1.json"))
                      .read_text(encoding="utf-8"))


class _FakeDrive:
    """假驱动：记录每次 (计划, per-seat 策略) 并按焦点臂给确定性分数；0 真实桌赛。

    分数语义：焦点座位候选臂 +12、基线臂 -10（按 seed 微扰），对手座位拿小分；
    保证 group_advance_utility 可算（候选臂 U=1，基线臂 U=0）。
    """

    def __init__(self, fail_candidate_at_seat=None, fail_baseline_at_seat=None):
        self.calls = []
        self.fail_candidate_at_seat = fail_candidate_at_seat
        self.fail_baseline_at_seat = fail_baseline_at_seat

    def __call__(self, *, plan, policies_by_seat, versions_block, step_limit,
                 value_limits):
        seats = list(plan.seats())
        focal_idx = seats.index("natural:focal") if "natural:focal" in seats \
            else seats.index("focal")
        focal_policy = policies_by_seat[focal_idx]
        is_candidate = str(getattr(focal_policy, "policy_id", "")).startswith(
            "action_value")
        anchor_seat = int(plan.table_id.split("-s")[-1].split("-")[0])
        if is_candidate and self.fail_candidate_at_seat == anchor_seat:
            raise RuntimeError("T16 构造：候选臂在座位 {0} 执行失败".format(anchor_seat))
        if not is_candidate and self.fail_baseline_at_seat == anchor_seat:
            raise RuntimeError("Q4 构造：基线臂在座位 {0} 执行失败".format(anchor_seat))
        offset = plan.seed % 7 - 3
        scores = []
        for seat in range(4):
            if seat == focal_idx:
                scores.append(12 + offset if is_candidate else -10 + offset)
            else:
                scores.append(2 - seat + (offset if seat % 2 else -offset))
        self.calls.append({"table_id": plan.table_id, "seed": plan.seed,
                           "seats": seats, "focal_idx": focal_idx,
                           "is_candidate": is_candidate,
                           "policy_ids": [str(getattr(p, "policy_id", "?"))
                                          for p in policies_by_seat]})
        return {"table_id": plan.table_id, "seed": int(plan.seed),
                "match_status": "complete", "wall_ms": 1.0,
                "scores_by_seat": scores, "result": {}}


def _run_natural(tmp_path, fake, **kwargs):
    import sitin_natural_panel as natural
    original = natural.execute_natural_table
    natural.execute_natural_table = fake
    try:
        return natural.run_natural_panel(
            candidate_source=GOOD_SOURCE, opponent=kwargs.pop("opponent", "H"),
            roots=kwargs.pop("roots", 1), seats_per_root=kwargs.pop("seats_per_root", 4),
            contract=_contract(), out_dir=kwargs.pop("out_dir", tmp_path / "np"),
            authorization=BATCH7_TOKEN, **kwargs)
    finally:
        natural.execute_natural_table = original


def test_natural_panel_structure_two_arms_four_seats_two_tables(tmp_path):
    """0 桌结构：每根 2 臂 × 4 座位 × 2 桌 = 16 次编排调用；无真实驱动。"""
    fake = _FakeDrive()
    panel = _run_natural(tmp_path, fake, roots=2)
    assert len(fake.calls) == 2 * 2 * 4 * 2
    assert len(panel["samples"]) == 2 * 4
    assert panel["cost"]["tables_full_planned"] == 32
    assert panel["cost"]["tokens_input"] == 0 and panel["cost"]["tokens_output"] == 0


def test_natural_panel_same_seed_and_table_ids_both_arms(tmp_path):
    """配对红线：同根两臂拿到逐字相同的 table_id/seed（不含臂标识）。"""
    fake = _FakeDrive()
    _run_natural(tmp_path, fake, roots=1)
    by_table = {}
    for call in fake.calls:
        by_table.setdefault(call["table_id"], set()).add(
            (call["seed"], call["is_candidate"]))
    assert len(by_table) == 8  # 4 座位 × 2 桌；每桌恰有基线/候选两次调用
    for table_id, pairs in by_table.items():
        seeds = {seed for seed, _ in pairs}
        arms = {is_candidate for _, is_candidate in pairs}
        assert len(seeds) == 1, table_id
        assert arms == {False, True}, table_id


def test_natural_panel_opponents_identical_across_arms(tmp_path):
    """红线：focal 之外座位两臂策略完全一致；唯一差别在焦点位。"""
    fake = _FakeDrive()
    _run_natural(tmp_path, fake, roots=1)
    by_table = {}
    for call in fake.calls:
        by_table.setdefault(call["table_id"], {})[call["is_candidate"]] = call
    for table_id, arms in by_table.items():
        baseline, candidate = arms[False], arms[True]
        for seat in range(4):
            if seat == baseline["focal_idx"]:
                assert baseline["policy_ids"][seat] != candidate["policy_ids"][seat]
            else:
                assert baseline["policy_ids"][seat] == candidate["policy_ids"][seat], \
                    table_id


def test_natural_panel_t16_candidate_failure_invalidates_whole_root(tmp_path):
    """T16：候选臂任一座位失败 ⇒ 整根 4 座位样本全 invalid，费用照记。"""
    fake = _FakeDrive(fail_candidate_at_seat=1)
    panel = _run_natural(tmp_path, fake, roots=1)
    samples = panel["samples"]
    assert all(sample["completeness"] == "invalid" for sample in samples)
    assert all("T16" in reason for sample in samples
               for reason in sample["invalid_reasons"])
    # 候选臂失败座位无数值冒充：usable=False；其余座位数值保留但根级 invalid。
    failed = next(s for s in samples if s["focal_anchor_seat"] == 1)
    assert failed["arms"]["candidate"]["usable"] is False
    # 费用照记：失败臂没跑的 2 桌不执行，其余 14 桌实跑。
    assert panel["cost"]["tables_full_planned"] == 16
    assert panel["cost"]["tables_full_executed"] == 14


def test_natural_panel_authorization_gate_batch7_only(tmp_path):
    """授权门：authorized=true 但 batch≠7 或缺令牌 → SystemExit（fail-closed）。"""
    import sitin_natural_panel as natural
    for bad_token in ({"authorized": True, "batch": 6}, {"authorized": False},
                      None):
        with pytest.raises(SystemExit):
            natural.run_natural_panel(
                candidate_source=GOOD_SOURCE, opponent="H", roots=1,
                seats_per_root=1, contract=_contract(),
                out_dir=tmp_path / ("np-" + str(bad_token)), authorization=bad_token)


def test_natural_panel_ledger_records_tables_full(tmp_path):
    """台账：--ledger 路径上预留并按实结算 tables_full（先预留后执行）。"""
    ledger_path = tmp_path / "shared-av-ledger.json"
    _run_natural(tmp_path, _FakeDrive(), roots=1, ledger_path=ledger_path,
                 ledger_authorized_budgets={"tables_full": 64.0})
    ledger = search.ActionValueLedger.load(ledger_path)
    assert ledger.spent("tables_full") == 16.0
    reservation = ledger.reservations[-1]
    assert reservation["account"] == "tables_full"
    assert reservation["status"] == "settled"


def test_natural_panel_samples_archive_compatible(tmp_path):
    """样本形状：sitin_archive.classify_sample 判 usable（根级统计可直接消费）。"""
    from sitin_archive import classify_sample
    panel = _run_natural(tmp_path, _FakeDrive(), roots=1)
    for sample in panel["samples"]:
        status, reason = classify_sample(sample)
        assert status == "usable", reason
        arms = sample["arms"]
        assert arms["candidate"]["u"] == 1.0
        assert arms["baseline"]["u"] == 0.0


def test_natural_panel_seat_rotation_and_permutation(tmp_path):
    """座位轮换：4 座位实例覆盖 0..3 锚位；第 2 桌按合同 rotate_permutation 换座。"""
    fake = _FakeDrive()
    _run_natural(tmp_path, fake, roots=1)
    anchors = sorted({int(call["table_id"].split("-s")[-1].split("-")[0])
                      for call in fake.calls})
    assert anchors == [0, 1, 2, 3]
    by_id = {call["table_id"]: call for call in fake.calls}
    for anchor in range(4):
        # Q7：table_id 绑定 panel_seed（np-H-20260916-r01-sN-tM）。
        first = by_id["np-H-20260916-r01-s{0}-t1".format(anchor)]
        second = by_id["np-H-20260916-r01-s{0}-t2".format(anchor)]
        assert first["seats"].index("focal") == anchor
        assert second["seats"].index("focal") == (anchor + 1) % 4


def test_q4_baseline_arm_failure_invalidates_whole_root(tmp_path):
    """Q4/T16：基线臂单座位失败 ⇒ 整根失效（不用剩余 3 座位算选择值）。"""
    fake = _FakeDrive(fail_baseline_at_seat=0)
    panel = _run_natural(tmp_path, fake, roots=1)
    samples = panel["samples"]
    assert all(sample["completeness"] == "invalid" for sample in samples)
    failed = next(s for s in samples if s["focal_anchor_seat"] == 0)
    assert failed["arms"]["baseline"]["usable"] is False
    assert any("基线" in reason for sample in samples
               for reason in sample["invalid_reasons"])
    cid = panel["identity"]["candidate_id"]
    mix_panel = panel["statistics"]["by_candidate"][cid]["panels"]["normal"]["panels"]["H"]
    assert mix_panel["status"] == "invalid_only"
    assert mix_panel["n_roots"] == 0
    assert mix_panel["mean_delta"] is None  # 不再用剩余座位给出 mean_delta=1.0
    assert mix_panel["manifest_complete"] is False
    assert mix_panel["n_invalid_roots"] == 1
    # 费用照记：基线失败座位 2 桌未执行，其余 14 桌照跑（失败桌不抹账）。
    assert panel["cost"]["tables_full_planned"] == 16
    assert panel["cost"]["tables_full_executed"] == 14


def test_q4_root_expected_checklist_frozen_on_samples(tmp_path):
    """Q4：每样本携带冻结期望清单（座位/双臂/每臂桌数）。"""
    panel = _run_natural(tmp_path, _FakeDrive(), roots=1)
    for sample in panel["samples"]:
        expected = sample["root_expected"]
        assert expected == {"seats": 4, "arms": ["baseline", "candidate"],
                            "tables_per_arm": 2}


def test_q7_root_id_binds_panel_seed_and_digest(tmp_path):
    """Q7：根 ID 绑定 panel_seed；样本带根内容摘要；不同 seed 根 ID 不同。"""
    panel = _run_natural(tmp_path, _FakeDrive(), roots=1)
    root_ids = {sample["source_root_id"] for sample in panel["samples"]}
    assert root_ids == {"np-H-20260916-root01"}
    digests = {sample["root_content_digest"] for sample in panel["samples"]}
    assert len(digests) == 1  # 同根同摘要
    panel2 = _run_natural(tmp_path, _FakeDrive(), roots=1, panel_seed=99999999,
                          out_dir=tmp_path / "np-seed2")
    root_ids2 = {sample["source_root_id"] for sample in panel2["samples"]}
    assert root_ids2 == {"np-H-99999999-root01"}
    assert not (root_ids & root_ids2)  # 不同批次根身份不碰撞（无需目录后缀补丁）


# ============================================================ R4 账本加固（Q3）

def test_q3_over_authorized_reserve_rejected(tmp_path):
    """Q3：授权 1 额度预留 1,000,000 → 拒绝；台账不进账（评审复现反例）。"""
    ledger = search.ActionValueLedger(tmp_path / "av-ledger.json",
                                      confirm_authorized_budget=1.0)
    with pytest.raises(search.LedgerOverAuthorized):
        ledger.reserve(step_id="over-budget-fixture",
                       account="confirm_reserved", amount=1_000_000)
    assert ledger.spent("confirm_reserved") == 0.0
    # 开发账户同样受限：授权 4，已预留 3，再预留 2 → 拒绝。
    dev = search.ActionValueLedger(tmp_path / "dev.json",
                                   authorized_budgets={"tables_full": 4.0})
    dev.reserve(step_id="d1", account="tables_full", amount=3.0)
    with pytest.raises(search.LedgerOverAuthorized):
        dev.reserve(step_id="d2", account="tables_full", amount=2.0)
    assert dev.spent("tables_full") == 3.0
    assert dev.remaining("tables_full") == 1.0


def test_q3_unauthorized_positive_amount_fail_closed(tmp_path):
    """Q3：未声明授权额度的账户记正数账 → fail-closed；amount=0 纯登记不受限。"""
    ledger = search.ActionValueLedger(tmp_path / "av-ledger.json")
    with pytest.raises(search.LedgerUnauthorized):
        ledger.reserve(step_id="x", account="tokens_input", amount=1.0)
    assert ledger.spent("tokens_input") == 0.0
    ledger.reserve(step_id="zero-bookkeeping", account="tokens_input", amount=0.0)
    assert ledger.spent("tokens_input") == 0.0


def test_q3_invalid_amount_rejected(tmp_path):
    """Q3：负数/NaN/Inf 金额直接拒绝（不写坏账）。"""
    ledger = search.ActionValueLedger(tmp_path / "av.json",
                                      authorized_budgets={"tables_full": 100.0})
    for bad in (-1.0, float("nan"), float("inf")):
        with pytest.raises(search.LedgerAmountInvalid):
            ledger.reserve(step_id="bad", account="tables_full", amount=bad)
    reservation = ledger.reserve(step_id="ok", account="tables_full", amount=1.0)
    with pytest.raises(search.LedgerAmountInvalid):
        ledger.settle(reservation, actual=-3.0)


def test_q3_duplicate_reservation_rejected(tmp_path):
    """Q3：同 step/账户/金额在途预留重复提交 → 拒绝双计（恢复走 settle）。"""
    ledger = search.ActionValueLedger(tmp_path / "av.json",
                                      authorized_budgets={"tables_full": 10.0})
    ledger.reserve(step_id="retry-step", account="tables_full", amount=2.0)
    with pytest.raises(search.DuplicateReservation):
        ledger.reserve(step_id="retry-step", account="tables_full", amount=2.0)
    assert ledger.spent("tables_full") == 2.0  # 只有一笔在途


def test_q3_usage_unknown_conservative_settle(tmp_path):
    """Q3：模型 usage 未知 → 保守按预留额计费并标 usage_unknown。"""
    ledger = search.ActionValueLedger(tmp_path / "av.json",
                                      authorized_budgets={"tokens_input": 100.0})
    reservation = ledger.reserve(step_id="call", account="tokens_input", amount=5.0)
    ledger.settle(reservation, usage_unknown=True)
    assert ledger.spent("tokens_input") == 5.0  # 不下调（保守）
    row = next(r for r in ledger.reservations if r["step_id"] == "call")
    assert row["usage_unknown"] is True


def test_q3_crash_inflight_reserves_count_against_budget(tmp_path):
    """Q3：崩溃后在途（reserved 未结算）仍占额度——恢复不许免费超额。"""
    ledger = search.ActionValueLedger(tmp_path / "av.json",
                                      authorized_budgets={"tables_full": 6.0})
    ledger.reserve(step_id="crashed", account="tables_full", amount=4.0)  # 未 settle
    with pytest.raises(search.LedgerOverAuthorized):
        ledger.reserve(step_id="after-crash", account="tables_full", amount=3.0)
    reloaded = search.ActionValueLedger.load(tmp_path / "av.json")
    assert reloaded.remaining("tables_full") == 2.0


def test_q3_worker_lease_shared_across_ledger_instances(tmp_path):
    """Q3：全机 12 上限走共享租约文件——跨账本实例（跨进程语义）同样拒绝。"""
    path = tmp_path / "av.json"
    first = search.ActionValueLedger(path)
    first.request_workers(8, purpose="panel-a")
    second = search.ActionValueLedger(path)  # 另一实例=另一进程视角：无对象内共享
    with pytest.raises(search.WorkerCapExceeded):
        second.request_workers(5, purpose="panel-b")  # 8+5 > 12
    second.release_workers(4)
    second.request_workers(5, purpose="panel-b")  # 4+5 ≤ 12
    assert first.workers_active == second.workers_active == 9
    assert first.to_json()["worker_cap"] == 12


def test_q3_load_never_raises_file_caps(tmp_path):
    """Q3：回读不抬高限额——文件额度 10 与参数 20 取较小者。"""
    path = tmp_path / "av.json"
    ledger = search.ActionValueLedger(path, authorized_budgets={"tables_full": 10.0})
    ledger.save()
    reloaded = search.ActionValueLedger.load(path,
                                             authorized_budgets={"tables_full": 20.0})
    with pytest.raises(search.LedgerOverAuthorized):
        reloaded.reserve(step_id="raise", account="tables_full", amount=11.0)


def test_natural_panel_seats_per_root_bounds_validated(tmp_path):
    """seats_per_root 边界：0 或 5 直接 ValueError（不静默截断）。"""
    import sitin_natural_panel as natural
    for bad in (0, 5):
        with pytest.raises(ValueError):
            natural.run_natural_panel(
                candidate_source=GOOD_SOURCE, opponent="H", roots=1,
                seats_per_root=bad, contract=_contract(),
                out_dir=tmp_path / ("np-bad-" + str(bad)),
                authorization=BATCH7_TOKEN)


# ============================================================ 跨迭代档案传递（R6 修复）
#
# 缺口：每个 `evolve-action-value --out iter-N` 是独立运行目录，前序迭代提交的
# 档案落在 <iter-N>/archive/av-archive.json，而开轮时只读本目录 → 恒判"档案空"
# → 恒 i1、无父代（rep1/iter-01..04 实测）。以下用 mock 生成步 + 替身桌赛
# （0 真实桌赛 0 LLM）覆盖：链上自动发现、显式 --archive 优先、无前序回退 I1、
# 显式失效 fail-closed、增量提交基数。


def _patch_natural_drive(monkeypatch, drive):
    """替身桌赛驱动换进自然面板执行入口（0 真实桌赛；语义同 R5 测试）。"""

    import sitin_natural_panel as natural
    monkeypatch.setattr(natural, "execute_natural_table", drive, raising=True)


def _chain_token():
    """批次 7 授权令牌 + 账户额度（替身 runtime：0 真实桌赛，账面照记）。"""

    return {"authorized": True, "batch": 7,
            "budgets": {"tokens_input": 100000, "tokens_output": 200000,
                        "tables_full": 256, "prefix_generation": 64}}


def _completed_iteration(chain, name, **kwargs):
    """跑完一个 mock 迭代（状态机全链）并返回 (运行目录, 状态)。"""

    root = Path(chain) / name
    result = search.run_av_evolution(root, generation_mode="mock", **kwargs)
    assert result.get("terminal") == "ITERATION_COMPLETE", result
    return root, search.av_state_load(search.av_latest_state_path(root))


def _plan_of(run_root):
    """运行目录里最新迭代的 plan（开轮时冻结：算子/父代/调度输入档案）。"""

    state_path = search.av_latest_state_path(Path(run_root))
    assert state_path is not None
    return search.av_state_load(state_path)["plan"]


def test_evolve_chain_discovers_previous_archive_and_plans_m1_parent(tmp_path,
                                                                    monkeypatch):
    """跨迭代档案链：第二个迭代目录自动发现前序 ARCHIVE_COMMITTED 档案 →
    plan operator=m1、父代=第一个候选；档案增量提交不清空前序条目与席位。"""
    _patch_natural_drive(monkeypatch, _FakeDrive())
    chain = tmp_path / "rep1"
    first_root, first_state = _completed_iteration(chain, "iter-01",
                                                   authorization=_chain_token())
    first_cid = first_state["identity"]["candidate_id"]
    first_archive = json.loads((first_root / "archive" / "av-archive.json")
                               .read_text(encoding="utf-8"))
    assert first_cid in first_archive["slots"]["overall"]  # 前序候选占整体席
    first_attempt = first_root / "iterations" / "iter-01" / "generation"
    # 第二迭代目录：本目录还没有档案 → 自动发现兄弟链上最新提交的那一份。
    second_root = chain / "iter-02"
    started = search.run_av_evolution(second_root, generation_mode="mock",
                                      seed_name="route_value_seed",
                                      authorization=_chain_token(),
                                      stop_after="RESERVED")
    assert started.get("stopped_after") == "RESERVED"
    plan = _plan_of(second_root)
    archive_in = plan["archive_in"]
    assert archive_in["source"] == "chain_committed"
    assert Path(archive_in["path"]).resolve() == (
        first_root / "archive" / "av-archive.json").resolve()
    assert archive_in["entries"] == 1
    assert archive_in["seated_slots"]["overall"] == 1
    assert archive_in["history_count"] == 1 and archive_in["proposal_no"] == 2
    assert plan["operator"] == "m1"
    assert archive_in["planned_operator"] == "M1"
    assert archive_in["planned_parent_candidate_id"] == first_cid
    assert Path(plan["parent_dir"]).resolve() == first_attempt.resolve()
    # 续跑：M1 父代真的进了提示词与调用前事务（不是只写进计划字段）。
    state = search.av_state_load(search.av_latest_state_path(second_root))
    resumed = search.run_av_machine_resume(second_root, run_id=state["run_id"],
                                           authorization=_chain_token())
    assert resumed.get("terminal") == "ITERATION_COMPLETE"
    final = search.av_state_load(search.av_latest_state_path(second_root))
    second_cid = final["identity"]["candidate_id"]
    assert second_cid != first_cid
    tx = json.loads((Path(final["iter_dir"]) / "transactions"
                     / search.AV_TX_FILES["model_call_before"])
                    .read_text(encoding="utf-8"))
    assert Path(tx["parent"]).resolve() == first_attempt.resolve()
    prompt = (Path(final["iter_dir"]) / "pending" / "m1"
              / "prompt.txt").read_text(encoding="utf-8")
    assert first_cid in prompt
    # 档案增量提交：前序条目与席位都还在（跨目录链不被截断成单候选）。
    merged = json.loads((second_root / "archive" / "av-archive.json")
                        .read_text(encoding="utf-8"))
    assert set(merged["entries"]) == {first_cid, second_cid}
    assert any(first_cid in ids for ids in merged["slots"].values())


def test_evolve_explicit_archive_wins_over_auto_discovery(tmp_path, monkeypatch):
    """--archive 显式优先：链上存在可自动发现的前序档案时，显式档案仍是调度输入。"""
    _patch_natural_drive(monkeypatch, _FakeDrive())
    chain = tmp_path / "rep1"
    first_root, first_state = _completed_iteration(chain, "iter-01",
                                                   authorization=_chain_token())
    first_cid = first_state["identity"]["candidate_id"]
    chain_archive = json.loads((first_root / "archive" / "av-archive.json")
                               .read_text(encoding="utf-8"))
    # 显式共享档案 = 链上档案 + 一个安全 FAIL 的额外条目：条目数 2 ≠ 自动发现的
    # 1（该条目不合格不占席），用来判别"计划到底读的是哪一份档案"。
    explicit_path = tmp_path / "shared" / "av-archive.json"
    explicit_path.parent.mkdir(parents=True, exist_ok=True)
    explicit_path.write_text(json.dumps(search.av_archive().update_archive(
        list(chain_archive["entries"].values()) + [
            {"candidate_id": "explicit-only-cand", "kind": "action_value_v1",
             "safety": {"status": "FAIL"}, "overall": {}, "family": {}}]),
        ensure_ascii=False), encoding="utf-8")
    # 判别力对照：不给 --archive 时自动发现确实命中链上那一份（否则本测试无意义）。
    auto_root = chain / "iter-02"
    auto_discovered, auto_info = search.av_discover_archive(auto_root)
    assert auto_info["source"] == "chain_committed"
    assert Path(auto_discovered).resolve() == (
        first_root / "archive" / "av-archive.json").resolve()
    search.run_av_evolution(auto_root, generation_mode="mock",
                            authorization=_chain_token(), stop_after="RESERVED")
    auto_plan = _plan_of(auto_root)
    assert auto_plan["archive_in"]["source"] == "chain_committed"
    assert auto_plan["archive_in"]["entries"] == 1
    # 显式 --archive：同一链环境下按显式那一份生成计划。
    explicit_root = chain / "iter-03"
    search.run_av_evolution(explicit_root, generation_mode="mock",
                            authorization=_chain_token(),
                            stop_after="RESERVED", archive_path=explicit_path)
    plan = _plan_of(explicit_root)
    archive_in = plan["archive_in"]
    assert archive_in["source"] == "explicit"
    assert Path(archive_in["path"]).resolve() == explicit_path.resolve()
    assert archive_in["entries"] == 2
    assert plan["operator"] == "m1"
    assert archive_in["planned_parent_candidate_id"] == first_cid


def test_evolve_without_predecessor_falls_back_to_empty_archive_i1(tmp_path):
    """无前序档案且未给 --archive：回退空档案 → next_generation_plan 返回 I1。"""
    solo = tmp_path / "solo" / "iter-01"
    result = search.run_av_evolution(solo, generation_mode="mock",
                                     authorization=_chain_token(),
                                     stop_after="RESERVED")
    assert result.get("stopped_after") == "RESERVED"
    plan = _plan_of(solo)
    archive_in = plan["archive_in"]
    assert archive_in["source"] == "empty" and archive_in["path"] is None
    assert archive_in["entries"] == 0 and archive_in["seated_slots"] == {}
    assert archive_in["history_count"] == 0 and archive_in["proposal_no"] == 1
    assert plan["operator"] == "i1" and plan["parent_dir"] is None
    assert archive_in["applied_operator"] == "i1"


def test_evolve_missing_explicit_archive_refused_fail_closed(tmp_path):
    """显式 --archive 指向不存在的文件：拒绝开轮（不静默回退自动发现/空档案）。"""
    root = tmp_path / "solo" / "iter-01"
    missing = tmp_path / "shared" / "not-there.json"
    result = search.run_av_evolution(root, generation_mode="mock",
                                     authorization=_chain_token(),
                                     archive_path=missing)
    assert result.get("ok") is False
    assert "不存在" in result["refused"] and str(missing) in result["refused"]
    assert search.av_latest_state_path(root) is None  # 未开轮、未落迭代状态


def test_evolve_cli_exposes_archive_flag():
    """CLI 面：evolve-action-value 提供 --archive（缺省自动发现，见上四条）。"""
    result = subprocess.run([PY, str(TOOL), "evolve-action-value", "--help"],
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr[-400:]
    assert "--archive" in result.stdout.replace("\n", "")


def test_run_av_iteration_records_and_merges_shared_archive(tmp_path):
    """§9.4 mock 演示路径同接共享档案：记账 archive_in + 在案条目增量合并。"""
    explicit = tmp_path / "shared-archive.json"
    explicit.write_text(json.dumps({
        "schema": "sitin-archive/1",
        "entries": {"prior-cand": {"candidate_id": "prior-cand",
                                   "kind": "action_value_v1",
                                   "safety": {"status": "FAIL"},
                                   "overall": {}, "family": {}}},
        "slots": {}}, ensure_ascii=False), encoding="utf-8")
    out = _tmp(tmp_path, "iter-archive")
    result = search.run_av_iteration(out, authorization=BUDGET_TOKEN,
                                     archive_path=explicit)
    assert result["ok"] is True
    assert [item["step"] for item in result["steps"]] == list(search.AV_ITERATION_ORDER)
    assert result["archive_in"]["source"] == "explicit"
    assert Path(result["archive_in"]["path"]).resolve() == explicit.resolve()
    # mock 演示路径的计划基于**本步刚更新过的档案**（在案 1 条 + 本迭代 1 条）。
    assert result["archive_in"]["entries"] == 2
    # 增量合并：在案条目与本迭代候选同时在档（不重建单候选档案）。
    assert set(result["archive"]["entries"]) == {
        "prior-cand", result["identity"]["candidate_id"]}
    # 显式失效同样 fail-closed：开工前拒绝，不计费不落步。
    refused = search.run_av_iteration(_tmp(tmp_path, "iter-badarchive"),
                                      authorization=BUDGET_TOKEN,
                                      archive_path=tmp_path / "not-there.json")
    assert refused["ok"] is False
    assert "不存在" in refused["refused"]
    assert refused["steps"] == []



# ============================================================ P5（R7）：A1 评价装配正确性


def _test_double_runtime():
    """显式测试入口装配的验证替身（0 真实桌赛；唯一合法替身来源）。"""

    from hangma_bot.hangma.engine import HangmaRules
    from hangma_bot.hangma.interface import ValueAnalysisLimits
    from hangma_bot.kernel.config import RuleConfig

    opportunities = search.av_opportunities()
    return opportunities.build_test_runtime_double(
        rules=HangmaRules(RuleConfig("v26", 1, False)),
        value_limits=ValueAnalysisLimits())


def test_evaluation_refuses_missing_runtime_fail_closed(tmp_path):
    """(a)：正式入口不注入替身——缺 runtime 即拒绝，且不留任何产物。"""

    out = _tmp(tmp_path, "p5-missing")
    opportunities = search.av_opportunities()
    with pytest.raises(opportunities.RuntimeAssemblyError, match="显式装配"):
        search.run_av_evaluation(out, GOOD_SOURCE, prefix_source="v2_behavior",
                                 authorization=BATCH7_TOKEN, attempts_cap=4)
    assert not (out / "panel-branch_open").exists()
    assert not (out / "evaluation.json").is_file()


def test_evaluation_refuses_unlabelled_runtime(tmp_path):
    """无装配标签的运行时无法区分真伪：拒绝（不按「传了 runtime」猜）。"""

    import c1_runtime_double as double
    from hangma_bot.hangma.engine import HangmaRules
    from hangma_bot.hangma.interface import ValueAnalysisLimits
    from hangma_bot.kernel.config import RuleConfig

    opportunities = search.av_opportunities()
    raw = double.build_runtime_double(
        HangmaRules(RuleConfig("v26", 1, False)), ValueAnalysisLimits())
    out = _tmp(tmp_path, "p5-unlabelled")
    with pytest.raises(opportunities.RuntimeAssemblyError, match="runtime_kind"):
        search.run_av_evaluation(out, GOOD_SOURCE, prefix_source="v2_behavior",
                                 authorization=BATCH7_TOKEN, attempts_cap=4,
                                 runtime=raw)
    assert not (out / "evaluation.json").is_file()


def test_test_double_route_is_marked_and_not_selection_usable(tmp_path):
    """(c)(d)：替身路由如实标注 engine_kind/execution_kind，且不参与选留。"""

    out = _tmp(tmp_path, "p5-double")
    ledger = search.ActionValueLedger(out / "av-ledger.json",
                                      authorized_budgets=BUDGETS)
    evaluation = search.run_av_evaluation(
        out, GOOD_SOURCE, prefix_source="v2_behavior", authorization=BATCH7_TOKEN,
        attempts_cap=4, ledger=ledger, test_runtime=_test_double_runtime())
    attempts = evaluation["panel"]["prefix_attempts"]
    assert evaluation["execution_kind"] == "test_double"
    assert evaluation["engine_kind"] == "simulation_runtime_double"
    assert evaluation["panel"]["engine_kind"] == "simulation_runtime_double"
    assert evaluation["fixture_mode"] is False
    # 替身没有跑真实桌赛：真实桌赛实例恒 0（不再把尝试数冒充真实桌数）。
    assert evaluation["real_table_instances"] == 0
    assert evaluation["double_table_instances"] == attempts["total"]
    assert evaluation["strength_evidence"] is False
    assert evaluation["usable_for_selection"] is False
    assert ledger.spent("tables_partial") == 0.0
    assert ledger.spent("tables_full") == 0.0
    assert ledger.spent("prefix_generation") == 1.0
    admission = evaluation["result_admission"]
    assert admission["ok"] is True, admission["problems"]


def test_result_admission_rejects_zero_real_tables_with_real_claim():
    """同一产物不得同时声明「零真实桌赛」与「真实完成」（准入交叉校验）。"""

    opportunities = search.av_opportunities()
    panel = {"engine_kind": "simulation_engine_public",
             "execution_kind": "real_runtime",
             "budget_red_line": {"real_table_instances_started": 0,
                                 "execution_kind": "real_runtime"}}
    evaluation = {"ok": True, "fixture_mode": False, "execution_kind": "real_runtime",
                  "engine_kind": "simulation_engine_public",
                  "real_table_instances": 0, "double_table_instances": 0,
                  "strength_evidence": True, "usable_for_selection": True,
                  "prefix_source": "v2_behavior",
                  "double_arm": {"arms": {}}, "tables_partial_charged": 0.0}
    verdict = search.admit_evaluation_result(evaluation, panel=panel)
    assert verdict["ok"] is False
    assert any("零真实桌赛" in problem or "真实桌赛实例" in problem
               for problem in verdict["problems"])
    assert opportunities is not None


def test_result_admission_is_enforced_in_output(tmp_path, monkeypatch):
    """准入不通过 → 正式产物 ok=False 且带 refused（不只写在旁注里）。"""

    def broken_admission(evaluation, *, panel):
        return {"ok": False, "problems": ["构造的准入失败"], "checks": {}}

    monkeypatch.setattr(search, "admit_evaluation_result", broken_admission)
    out = _tmp(tmp_path, "p5-admission")
    evaluation = search.run_av_evaluation(
        out, GOOD_SOURCE, prefix_source="v2_behavior", authorization=BUDGET_TOKEN,
        attempts_cap=4, test_runtime=_test_double_runtime())
    assert evaluation["ok"] is False
    assert "结果准入未通过" in evaluation["refused"]
    written = json.loads((out / "evaluation.json").read_text(encoding="utf-8"))
    assert written["ok"] is False
    assert "结果准入未通过" in written["refused"]


def test_real_runtime_evaluation_records_execution_evidence(tmp_path):
    """真实小样本：组合根真实运行时 → 引擎/根/座位/动作轨迹/阶段终点可串联。"""

    from hangma_bot.kernel.config import RuleConfig

    opportunities = search.av_opportunities()
    runtime = opportunities.build_real_runtime(
        rules_config=RuleConfig("v26", 1, False), rounds_per_game=8)
    out = _tmp(tmp_path, "p5-real")
    ledger = search.ActionValueLedger(out / "av-ledger.json",
                                      authorized_budgets=BUDGETS)
    evaluation = search.run_av_evaluation(
        out, GOOD_SOURCE, prefix_source="v2_behavior", authorization=BATCH7_TOKEN,
        attempts_cap=4, ledger=ledger, runtime=runtime)
    attempts = evaluation["panel"]["prefix_attempts"]
    assert evaluation["ok"] is True, evaluation.get("refused")
    assert evaluation["execution_kind"] == "real_runtime"
    assert evaluation["engine_kind"] == "simulation_engine_public"
    assert evaluation["panel"]["engine_kind"] == "simulation_engine_public"
    assert evaluation["real_table_instances"] == attempts["total"] >= 1
    assert evaluation["double_table_instances"] == 0
    assert evaluation["usable_for_selection"] is True
    assert evaluation["panel"]["budget_red_line"]["real_table_instances_started"]         == attempts["total"]
    assert evaluation["result_admission"]["ok"] is True,         evaluation["result_admission"]["problems"]
    # 引擎身份来自装配对象（真实引擎版本 = 规则源摘要；非替身）。
    assert evaluation["engine_identity"]["class"] == "SimulationEngine"
    assert evaluation["engine_identity"]["engine_version"]
    # 逐桌决策计数 / 完成原因 / 终点来自执行记录。
    sample = evaluation["samples"][0]
    assert sample["source_root_id"]
    for name, arm in sample["arms"].items():
        assert arm["execution_kind"] == "real_runtime", name
        assert arm["runtime_kind"] == "real_simulation_engine", name
        assert arm["decisions_total"] >= 1, name
        assert len(arm["tables"]) == 2, name
        for table in arm["tables"]:
            assert table["decisions"] >= 1
            assert table["completion_reason"] == "complete"
    assert evaluation["double_arm"]["declared_endpoint"] == "stage_complete"
    assert ledger.spent("tables_partial") == float(attempts["total"])
    # 可串联到引擎/根/座位/动作轨迹/阶段终点（读实际落盘的面板产物）。
    panel_json = json.loads(
        (out / "panel-branch_open" / "panel.json").read_text(encoding="utf-8"))
    assert panel_json["runtime_assembly"]["entry"] == "build_real_runtime"
    assert panel_json["engine_identity"]["class"] == "SimulationEngine"
    snapshot = panel_json["scenarios"][0]["snapshot"]
    assert snapshot["seating"]["focal_seat"] == panel_json["focal_seat"] == 0
    assert len(snapshot["stage_plan"]["participant_ids_by_seat"]) == 4
    # 动作轨迹（R9/A3 起改为**身份锚定**断言）：前缀按该根的实际执行种子如实记录。
    # 旧期望把"root000 的焦点座位首个窗口即命中、截取前缀为空"钉死——那绑的是旧
    # "prefix" 命名空间派生出的那一座牌山；A3 把执行种子统一到唯一根描述符后，
    # 同一个根换了牌山，钉死世界内容就变成"改实现即改期望"。这里核对的是更强的
    # 事实：快照身份 = 描述符身份、实际种子的确是该描述符种子的那一个。
    assert isinstance(snapshot["legal_action_prefix"], list)
    descriptor = snapshot["root_descriptor"]
    assert descriptor["root_id"] == snapshot["source_root_id"], snapshot["source_root_id"]
    assert snapshot["match_spec"]["seed"] == descriptor["root_seed"]
    assert descriptor["root_seed"] == search.av_family_root_seed(
        prefix_source="v2_behavior", sub_scenario=descriptor["sub_scenario"],
        opponent_mix=descriptor["opponent_mix"], panel_seed=descriptor["panel_seed"],
        root_index=descriptor["root_index"])
    for name, arm in sample["arms"].items():
        assert int(arm["decisions_after_cut"] or 0) >= 1, name
    assert snapshot["real"]["engine_kind"] == "simulation_engine_public"
    assert snapshot["prefix_behavior"]["verified"] is True   # 前缀对手身份绑定
    assert snapshot["remaining_schedule"]["declared_endpoint"] == "stage_complete"


def test_cli_assembles_real_runtime_at_composition_point(tmp_path, monkeypatch):
    """(a)：正式 CLI 在组合处显式装配真实运行时并显式传入（装配断言）。"""

    captured = {}
    opportunities = search.av_opportunities()
    real = opportunities.build_real_runtime(
        rules_config=__import__("hangma_bot.kernel.config", fromlist=["RuleConfig"])
        .RuleConfig("v26", 1, False),
        rounds_per_game=8)

    def spy_build_real_runtime(**kwargs):
        captured["kwargs"] = kwargs
        return real

    def spy_run_av_evaluation(out_dir, candidate_source, **kwargs):
        captured["runtime"] = kwargs.get("runtime")
        return {"ok": True, "identity": {"evaluation_id": "x"},
                "prefix_source": "v2_behavior", "real_table_instances": 0}

    monkeypatch.setattr(opportunities, "build_real_runtime", spy_build_real_runtime)
    monkeypatch.setattr(search, "run_av_evaluation", spy_run_av_evaluation)
    token_path = tmp_path / "token.json"
    token_path.write_text(json.dumps(BUDGET_TOKEN), encoding="utf-8")
    args = argparse.Namespace(
        candidate_source=_write_source(tmp_path), sub_scenario="branch_open",
        opponent="H", out=str(tmp_path / "out"), attempts_cap=4,
        panel_seed=20260916, prefix_source="v2_behavior",
        real_authorization=str(token_path), v2_authorization=str(token_path))
    assert search.cmd_evaluate_action_value(args) == 0
    assert captured["kwargs"], "CLI 未在组合处装配真实运行时"
    assert captured["runtime"] is real
    assert captured["runtime"]["runtime_kind"] == opportunities.RUNTIME_KIND_REAL


def test_evaluation_identity_differs_between_real_and_double(tmp_path):
    """身份区分真实/替身：替身结果不得复用为真实结果（evaluation_id 不同）。"""

    real_id = search.evaluation_identity(
        candidate_id="c", target_contract_sha256="t", opponent_mix="H",
        source_root_id="r", panel_generator="v2-behavior-prefix-v1",
        execution_kind="real_runtime", endpoint="stage_complete")
    double_id = search.evaluation_identity(
        candidate_id="c", target_contract_sha256="t", opponent_mix="H",
        source_root_id="r", panel_generator="v2-behavior-prefix-v1",
        execution_kind="test_double", endpoint="stage_complete")
    assert real_id != double_id
