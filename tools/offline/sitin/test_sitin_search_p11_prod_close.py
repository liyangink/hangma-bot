# -*- coding: utf-8 -*-
"""P11 PRODCLOSE 定向测试：R9 独立验收裁定（2026-09-18）的生产侧收口。

覆盖五条修复 + 一条注释更正，全部**离线纯数据**（0 真实桌赛、0 模型调用、0 网络）：

  G2：指定旧根重评 与 新根发现 分开表达——旧根逐字使用冻结描述符、被替换即拒绝；
  Q3：RootWitness 真实内容见证——两个生产入口共用规范序列化、真实捕获、落盘；
  S4：启用家族范围收口——仅 branch，其余三族显式 inactive 并由调度跳过（不产生样本/epoch）；
  Q6：统一受信授权校验（sitin-authorization/1 + legacy 兼容）；
  跨目录连续恢复：archive_in 内容身份绑定（开轮固化 + 固定快照 + 漂移即拒绝恢复）。
"""
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
import math
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import sitin_opportunities as opportunities  # noqa: E402
import sitin_search as search  # noqa: E402
from hangma_bot.policy.action_value_seeds import SEEDS  # noqa: E402

CHANNEL = "branch"
SUB_OPEN = "branch_open"
SUB_COST = "branch_cost"
SEED = 20260916
GOOD_SOURCE = SEEDS["route_value_seed"].source

#: 统一授权文档（Lead 定义 schema，字段名照写）——正例。
AUTH_FULL = {
    "schema": "sitin-authorization/1",
    "authorization_id": "auth-p11-0001",
    "batch_label": "p11-prod-close",
    "trusted": True,
    "allowed_operations": ["natural_panel", "conditional_prefix", "family_fill",
                           "conditional_refill", "evaluate", "summarize"],
    "allowed_accounts": {"tables_full": 256.0, "tables_partial": 64.0,
                         "prefix_generation": 64.0, "tokens_input": 100000.0,
                         "tokens_output": 200000.0, "confirm_reserved": 0.0},
    "issued_by": "lead",
    "issued_at_utc": "2026-09-18T00:00:00Z",
}
#: legacy 形态（原已授权的 batch7 同范围复验）。
AUTH_LEGACY = {"authorized": True, "batch": 7,
               "batch_label": "p11-prod-close",
               "budgets": {"tables_full": 256, "tables_partial": 64,
                           "prefix_generation": 64, "tokens_input": 100000,
                           "tokens_output": 200000, "confirm_reserved": 0.0}}


def _row(sub, mix, index, *, intent=None, seats=1):
    row = {"channel": CHANNEL, "sub_scenario": sub, "opponent_mix": mix,
           "panel_seed": SEED, "root_index": index, "seats_per_root": seats,
           "source": "plan.family_refresh"}
    if intent is not None:
        row["intent"] = intent
    return row


def _state(tmp_path: Path, rows, *, channel=CHANNEL):
    return {"plan": {"prefix_source": "v2_behavior", "panel_seed": SEED,
                     "family_channel": channel, "family_refresh": rows},
            "iter_dir": str(tmp_path), "iteration_no": 1, "run_id": "r9-p11"}


class _Probe:
    """探针替身：按 (子场景, 情景, 根序号) 声明哪些根见证谓词（不付费、不跑桌）。"""

    def __init__(self, witnessed):
        self.witnessed = set(witnessed)
        self.calls = []

    def __call__(self, *, descriptor, sub_scenario, mix, panel_seed, root_index,
                 step_id):
        self.calls.append({"sub_scenario": sub_scenario, "mix": mix,
                           "root_index": int(root_index),
                           "root_id": str(descriptor["root_id"]),
                           "root_seed": int(descriptor["root_seed"])})
        hit = (sub_scenario, mix, int(root_index)) in self.witnessed
        return {"status": "hit" if hit else "miss", "witnessed": hit,
                "readings": {"frames": 9, "wall_left_min": 5 if hit else 40},
                "reason": "" if hit else "root_not_witnessed（替身：该根不见证）"}


class _FakeLedger:
    """假账本：remaining 可配；reserve/settle 记录但不写盘（零真实执行）。"""

    def __init__(self, remaining=None):
        self._remaining = dict(remaining or {"prefix_generation": 40.0,
                                             "tables_partial": 40.0,
                                             "tables_full": 40.0})
        self.reserved = []
        self.settled = []
        self.reservations = []
        self.superseded = []

    def supersede(self, *, step_id, account, reason=""):
        self.superseded.append({"step_id": step_id, "account": account})

    def remaining(self, account):
        return self._remaining.get(account)

    def reserve(self, *, step_id, account, amount, note=""):
        self.reserved.append({"step_id": step_id, "account": account,
                              "amount": float(amount)})
        return {"step_id": step_id, "account": account, "amount": float(amount)}

    def settle(self, reservation, *, actual, note=""):
        self.settled.append({"step_id": reservation["step_id"], "actual": float(actual)})
        return {}


def _register_roots(tmp_path: Path, rows, *, channel=CHANNEL):
    """把给定的（子场景, 情景, 根序号）登记进家族根台账（跨目录链的本地一份）。"""

    archive = tmp_path / "archive"
    archive.mkdir(parents=True, exist_ok=True)
    roots = []
    for sub, mix, index in rows:
        descriptor = search.av_family_root_descriptor(
            prefix_source="v2_behavior", sub_scenario=sub, opponent_mix=mix,
            panel_seed=SEED, root_index=index)
        roots.append({"root_id": descriptor["root_id"], "sub_scenario": sub,
                      "opponent_mix": mix, "panel_seed": SEED, "root_index": index,
                      "root_seed": descriptor["root_seed"], "seats_per_root": 1})
    (archive / "family-roots.json").write_text(json.dumps(
        {"schema": search.AV_FAMILY_ROOTS_SCHEMA,
         "channels": {channel: {"roots": roots}}}), encoding="utf-8")
    return roots


# ===========================================================================
# G2 · 指定旧根重评 与 新根发现 分开表达
# ===========================================================================


def test_g2_reevaluate_registered_root_uses_frozen_descriptor(tmp_path):
    """指定旧根重评：逐字使用冻结描述符（登记过也照跑），产物按实例身份可定位。"""

    rows = [_row(SUB_OPEN, "H", 0, intent=search.AV_FAMILY_REFRESH_INTENT_REEVALUATE)]
    _register_roots(tmp_path, [(SUB_OPEN, "H", 0)])
    state = _state(tmp_path, rows)
    probe = _Probe({(SUB_OPEN, "H", 0)})
    payload = search.av_resolve_family_declarations(state, tmp_path, ledger=None,
                                                    probe=probe)
    assert payload["complete"] is True
    assert payload["stop_reason"] is None
    assert [call["root_index"] for call in probe.calls] == [0]
    frozen = search.av_family_root_descriptor(
        prefix_source="v2_behavior", sub_scenario=SUB_OPEN, opponent_mix="H",
        panel_seed=SEED, root_index=0)
    assert probe.calls[0]["root_id"] == frozen["root_id"]
    assert probe.calls[0]["root_seed"] == frozen["root_seed"]
    resolved = payload["resolved"][0]
    assert resolved["intent"] == search.AV_FAMILY_REFRESH_INTENT_REEVALUATE
    assert resolved["purpose"] == "指定旧根重评"
    assert resolved["registered_before"] is True
    assert resolved["root_id"] == frozen["root_id"]
    assert resolved["root_seed"] == frozen["root_seed"]
    assert resolved["root_index"] == 0
    # 产物按**实例身份**定位来源（不靠固定目录名猜用途）。
    entry = [item for item in payload["purpose_index"]
             if item["root_id"] == frozen["root_id"]][0]
    assert entry["intent"] == search.AV_FAMILY_REFRESH_INTENT_REEVALUATE
    assert entry["resolved"] is True
    artifact = Path(entry["artifact"])
    assert artifact.is_file(), entry
    assert json.loads(artifact.read_text(encoding="utf-8"))["entry"]["root_id"] == \
        frozen["root_id"]
    # 声明层携带用途（下游按同一用途记账）。
    declared = search._av_family_declarations(state, CHANNEL)["declared"]
    assert declared[0]["intent"] == search.AV_FAMILY_REFRESH_INTENT_REEVALUATE
    assert declared[0]["purpose"] == "指定旧根重评"


def test_g2_reevaluate_not_witnessed_rejects_task_without_substitution(tmp_path):
    """反例①：指定旧根不见证 ⇒ **拒绝该验证任务**，不得换成别的根（fail closed）。"""

    rows = [_row(SUB_OPEN, "H", 0, intent=search.AV_FAMILY_REFRESH_INTENT_REEVALUATE)]
    _register_roots(tmp_path, [(SUB_OPEN, "H", 0)])
    state = _state(tmp_path, rows)
    # 替身声明：只有 idx3 见证——若实现去"搜索替换根"，它会选中 3。
    probe = _Probe({(SUB_OPEN, "H", 3)})
    payload = search.av_resolve_family_declarations(state, tmp_path, ledger=None,
                                                    probe=probe)
    assert payload["complete"] is False
    assert payload["stop_reason"].startswith(search.AV_FAMILY_REEVALUATION_REJECTED)
    assert payload["resolved"] == []
    assert [call["root_index"] for call in probe.calls] == [0], probe.calls
    rejection = payload["reevaluation_rejections"][0]
    assert rejection["root_index"] == 0
    assert search.AV_FAMILY_REEVALUATION_REJECTED in rejection["reason"]
    assert "不得替换成别的根" in rejection["reason"]
    assert payload["intents"][search.AV_FAMILY_REFRESH_INTENT_REEVALUATE] == 1


def test_g2_discover_intent_still_excludes_registered_roots(tmp_path):
    """新根发现：保持"排除已登记根"的行为不变（对已登记候选不花探针）。"""

    rows = [_row(SUB_OPEN, "H", 0, intent="discover_new_root"),
            _row(SUB_OPEN, "H", 1, intent="discover_new_root")]
    _register_roots(tmp_path, [(SUB_OPEN, "H", 0)])
    state = _state(tmp_path, rows)
    probe = _Probe({(SUB_OPEN, "H", 1), (SUB_OPEN, "H", 2)})
    payload = search.av_resolve_family_declarations(state, tmp_path, ledger=None,
                                                    probe=probe)
    assert payload["complete"] is True
    # 已登记的请求根**不花探针、不进有效声明**（原行为逐字不变）；缺的那一格由后续
    # 独立根补上（这正是"新根发现"的语义）。
    assert 0 not in [call["root_index"] for call in probe.calls]
    assert [call["root_index"] for call in probe.calls][:2] == [1, 2]
    assert [row["root_index"] for row in payload["resolved"]] == [1, 2]
    assert payload["search"]["cells"]["{0}|H".format(SUB_OPEN)][
        "candidates_skipped"] == 1
    assert all(row["intent"] == search.AV_FAMILY_REFRESH_INTENT_DISCOVER
               for row in payload["resolved"])
    skipped = [item for item in payload["purpose_index"]
               if item["status"] == "skipped"]
    assert skipped and "root_already_registered" in skipped[0]["reason"]


def test_g2_registered_root_without_intent_is_refused_not_replaced(tmp_path):
    """反例②：声明点了已登记的根却没写用途 ⇒ 拒绝（不静默替换成别的根）。"""

    rows = [_row(SUB_OPEN, "H", 0), _row(SUB_OPEN, "H", 1)]
    _register_roots(tmp_path, [(SUB_OPEN, "H", 0)])
    state = _state(tmp_path, rows)
    probe = _Probe({(SUB_OPEN, "H", 1), (SUB_OPEN, "H", 3)})
    payload = search.av_resolve_family_declarations(state, tmp_path, ledger=None,
                                                    probe=probe)
    assert payload["complete"] is False
    assert payload["stop_reason"] == search.AV_FAMILY_INTENT_AMBIGUOUS_REGISTERED
    ambiguous = [item for item in payload["trace"]
                 if item["status"] == "rejected"
                 and search.AV_FAMILY_INTENT_AMBIGUOUS_REGISTERED in item["reason"]]
    assert ambiguous and ambiguous[0]["root_index"] == 0
    # 拒绝的那一格**没有**被别的根填上（idx3 从未被探针触碰）。
    assert 3 not in [call["root_index"] for call in probe.calls]
    assert all(row["root_index"] != 3 for row in payload["resolved"])


def test_g2_reevaluate_requires_explicit_intent_and_is_audited_in_identity(tmp_path):
    """用途进冻结身份面：同一声明换 intent ⇒ 身份摘要变化（配置不可静默漂移）。"""

    base = {"prefix_source": "v2_behavior", "panel_seed": SEED,
            "family_channel": CHANNEL}
    discover = search.av_family_refresh_identity(dict(
        base, family_refresh=[_row(SUB_OPEN, "H", 0, intent="discover_new_root")]))
    reevaluate = search.av_family_refresh_identity(dict(
        base, family_refresh=[_row(SUB_OPEN, "H", 0,
                                   intent="reevaluate_registered_root")]))
    assert search._av_digest_mapping(discover) != search._av_digest_mapping(reevaluate)
    assert search.av_family_refresh_intent({"intent": "something_else"}) is None
    assert search.av_family_refresh_intent({}) == \
        search.AV_FAMILY_REFRESH_INTENT_DISCOVER


# ===========================================================================
# Q3 · RootWitness 真实内容见证（两个真实入口共用规范序列化）
# ===========================================================================


def _fixture_evaluation(tmp_path, tag, **kwargs):
    return search.run_av_evaluation(
        tmp_path / ("q3-" + tag), GOOD_SOURCE, predicate=SUB_OPEN, opponent="H",
        panel_seed=SEED, authorization=AUTH_FULL, **kwargs)


def test_q3_root_witness_captured_from_both_entries_and_matches(tmp_path):
    """两个生产入口各捕获一次 RootWitness：逐项可比且对拍一致（同根同内容）。"""

    first = _fixture_evaluation(tmp_path, "normal")
    assert first["ok"] is True
    records_first = first["root_witnesses"]
    assert len(records_first) == 1
    witness_first = records_first[0]["witness"]
    index = int(witness_first["root_descriptor"]["root_index"])
    assert records_first[0]["instance"]["entry"] == "conditional_first_hit_root"
    # —— 指定根入口：只跑被冻结的那一个根（同一个根序号）——
    root_seed = search.av_family_root_seed(
        prefix_source="scripted_fixture", sub_scenario=SUB_OPEN, opponent_mix="H",
        panel_seed=SEED, root_index=index)
    second = _fixture_evaluation(tmp_path, "specified", root_indexes=[index],
                                 root_seed=int(root_seed))
    assert second["ok"] is True
    records_second = second["root_witnesses"]
    assert len(records_second) == 1
    witness_second = records_second[0]["witness"]
    assert records_second[0]["instance"]["entry"] == "conditional_specified_root"
    # 逐项可比：见证核心完全一致。
    assert opportunities.root_witness_comparison(witness_first) == \
        opportunities.root_witness_comparison(witness_second)
    verdict = opportunities.root_witness_verdict(
        witness_first, requirement=witness_second.get("requirement_digest"),
        expected=witness_second)
    assert verdict["status"] == "MATCHED", verdict
    assert verdict["content_captured"] is True
    assert verdict["content_matched"] is True
    assert verdict["requirement_recomputable"] is True
    # 见证字段齐备（裁定要求的最小集合）+ 序列化版本。
    for field in ("root_descriptor", "actual_seed", "prefix_sha256", "cut_window_key",
                  "observation_summary_sha256", "content_digest",
                  "serialization_version"):
        assert witness_first.get(field) not in (None, ""), field
    assert witness_first["serialization_version"] == \
        opportunities.ROOT_WITNESS_SCHEMA


def test_q3_witness_is_persisted_to_production_audit_files(tmp_path):
    """落生产审计附属文件：JSONL + 按实例身份命名的单文件（长期恢复可取）。"""

    evaluation = _fixture_evaluation(tmp_path, "persist")
    out = tmp_path / "q3-persist"
    sidecar = out / search.AV_ROOT_WITNESS_SIDECAR
    assert sidecar.is_file()
    lines = [json.loads(line) for line in sidecar.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 1
    record = lines[0]
    assert record["schema"] == search.AV_ROOT_WITNESS_RECORD_SCHEMA
    root_id = record["instance"]["root_id"]
    witness_snapshot = out / search.AV_ROOT_WITNESS_DIR / \
        "{0}.json".format(search.sha256_text(root_id)[:16])
    assert witness_snapshot.is_file()
    assert json.loads(witness_snapshot.read_text(encoding="utf-8"))["witness"][
        "content_digest"] == record["witness"]["content_digest"]
    assert evaluation["root_witness_sidecar"] == str(sidecar)


def test_q3_plan_parameter_reconstruction_is_not_a_witness(tmp_path):
    """反例：只按计划参数重算摘要 ⇒ 判为**未对拍**（与"可重算"分开两个结论）。"""

    evaluation = _fixture_evaluation(tmp_path, "recompute")
    witness = evaluation["root_witnesses"][0]["witness"]
    requirement = witness["requirement_digest"]
    assert requirement, "见证必须带可重算的要求摘要"
    # ① 用计划参数"重算"出来的东西只是要求摘要，不是内容见证。
    fabricated = {
        "schema": opportunities.ROOT_WITNESS_SCHEMA,
        "serialization_version": opportunities.ROOT_WITNESS_SCHEMA,
        "root_descriptor": dict(witness["root_descriptor"]),
        "actual_seed": witness["root_descriptor"]["root_seed"],
        "requirement_digest": requirement,
        "content_digest": search.sha256_text(search.canonical_json({
            "root_id": witness["root_descriptor"]["root_id"],
            "root_seed": witness["root_descriptor"]["root_seed"]})),
    }
    verdict = opportunities.root_witness_verdict(fabricated, requirement=requirement)
    assert verdict["status"] == "NOT_CAPTURED"
    assert verdict["content_captured"] is False
    assert verdict["requirement_recomputable"] is True      # 可重算成立
    assert verdict["content_matched"] is None               # 但**没有**对拍对象
    assert any("现场捕获物" in item for item in verdict["problems"])
    # ② 见证只能从真实执行结果捕获：给参数不给结果 → 直接拒绝。
    with pytest.raises(TypeError):
        opportunities.root_witness(
            attempt={"status": "hit"}, prefix_source="scripted_fixture",
            predicate_id=SUB_OPEN, focal_seat=0, opponent_scenario="H",
            descriptor=dict(witness["root_descriptor"]))
    # ③ 改写内容摘要 ⇒ 判为不自洽（捕获物与摘要必须一致）。
    tampered = dict(witness, prefix_sha256="0" * 64)
    tampered_verdict = opportunities.root_witness_verdict(tampered)
    assert tampered_verdict["status"] == "INCONSISTENT"
    assert tampered_verdict["content_captured"] is False


def test_q3_witness_carries_no_hidden_world_fields(tmp_path):
    """见证与模型可见输入同权限：不含世界私有字段（完整世界只留离线内部核验）。"""

    evaluation = _fixture_evaluation(tmp_path, "hidden")
    witness = evaluation["root_witnesses"][0]["witness"]
    text = json.dumps(witness, ensure_ascii=False)
    for name in opportunities.FORBIDDEN_SNAPSHOT_KEYS:
        assert name not in text, name
    # 只放摘要/键，不放观察全文（观察本体在快照里，见证是紧凑审计产物）。
    assert isinstance(witness["observation_summary_sha256"], str)
    assert "observation" not in {key for key in witness}


# ===========================================================================
# S4 · 启用家族范围收口（仅 branch；其余显式 inactive 并由调度跳过）
# ===========================================================================


def test_s4_scope_and_identity_expose_enabled_family_set():
    scope = search.av_family_scope("branch")
    assert scope["status"] == "enabled" and scope["stop_reason"] is None
    inactive = search.av_family_scope("chain")
    assert inactive["status"] == "inactive"
    assert "UNKNOWN" in inactive["reason"] and "None" in inactive["reason"]
    identity = search.av_family_channel_identity({"family_channel": "chain"})
    assert identity["enabled_families"] == ["branch"]
    assert identity["inactive_families"] == ["chain", "four_white", "baotou"]
    assert identity["scope"]["status"] == "inactive"
    assert any("inactive" in str(item.get("reason"))
               for item in identity["problems"])


def test_s4_inactive_family_is_skipped_at_iteration_start(tmp_path):
    """开轮即跳过：不解析声明、不花探针、不产生该族任何样本或 epoch。"""

    rows = [_row(SUB_OPEN, "H", 0, intent="discover_new_root")]
    called = []

    def _probe(**kwargs):
        called.append(kwargs)
        raise AssertionError("未启用家族不得发起任何探针")

    state = search.av_start_iteration(
        tmp_path / "run-s4", family_channel="chain", family_refresh=rows,
        prefix_source="v2_behavior", panel_seed=SEED, authorization=AUTH_FULL,
        declaration_probe=_probe)
    assert called == []
    assert state["family_scope"]["status"] == "inactive"
    resolved = state["family_refresh_resolved"]
    assert resolved["resolved"] == [] and resolved["trace"] == []
    assert resolved["complete"] is False
    assert resolved["stop_reason"] == search.AV_FAMILY_INACTIVE_STOP_REASON
    assert not (tmp_path / "run-s4" / "archive" / "family-epochs.json").exists()


def test_s4_inactive_family_scheduler_skips_without_tables_or_epoch(tmp_path):
    """调度跳过：零桌赛（账本一次 reserve 都没有）、零 epoch、具名原因。"""

    class _NoSpendLedger(_FakeLedger):
        def reserve(self, *, step_id, account, amount, note=""):
            raise AssertionError("未启用家族不得启动桌赛/不得计费")

    run_root = tmp_path / "run-s4-fill"
    run_root.mkdir(parents=True, exist_ok=True)
    rows = [_row(SUB_OPEN, "H", 0, intent="discover_new_root")]
    state = _state(run_root, rows, channel="chain")
    verdict = search._av_family_fill(state, run_root, _NoSpendLedger(),
                                     AUTH_FULL)
    assert verdict["status"] == "skipped_inactive_family"
    assert verdict["stop_reason"] == search.AV_FAMILY_INACTIVE_STOP_REASON
    assert verdict["samples_or_epoch_produced"] is False
    assert state["stop_reason"] == search.AV_FAMILY_INACTIVE_STOP_REASON
    assert not (run_root / "archive" / "family-epochs.json").exists()
    skip = state["family_fill"]["skipped"][0]
    assert skip["channel"] == "chain" and skip["reason"]
    tx = json.loads((Path(state["iter_dir"]) / "transactions"
                     / search.AV_TX_FILES["family_refresh"]).read_text(encoding="utf-8"))
    assert tx["outcome"] == "skipped_inactive_family"
    assert "未启动任何桌赛" in tx["note"]
    # 声明层同样拒绝物化（不产生该族声明）。
    parsed = search._av_family_declarations(state, "chain")
    assert parsed["declared"] == []
    assert parsed["declaration_source"] == "inactive_family"
    commit = search._av_commit_family(state, run_root, attempt_refresh=True,
                                      budget=None)
    assert commit["status"] == "skipped_inactive_family"
    assert commit["samples_or_epoch_produced"] is False


def test_s4_predicate_module_states_no_none_as_zero():
    """注释层同口径：谓词模块显式声明 None 不得当 0（防结论方向被篡改）。"""

    text = (Path(search.__file__).resolve().parent / "sitin_predicates_v4.py"
            ).read_text(encoding="utf-8")
    assert "把 None 当 0 一律禁止" in text
    assert "只启用 branch" in text


# ===========================================================================
# Q6 · 统一受信授权校验
# ===========================================================================


def test_q6_full_form_positive_and_audit_fields():
    verdict = opportunities.av_authorization_check(
        AUTH_FULL, operation="family_fill", required={"tables_full": 4.0},
        expected_batch_label="p11-prod-close",
        expected_authorization_id="auth-p11-0001")
    assert verdict["ok"] is True, verdict["problems"]
    assert verdict["authorization_form"] == "sitin-authorization/1"
    for field in ("authorization_id", "batch_label", "trusted", "issued_by",
                  "issued_at_utc", "operation_allowed", "allowed_operations",
                  "allowed_accounts", "required", "accounts_sufficient",
                  "problems", "checked_at_utc"):
        assert field in verdict, field
    assert verdict["accounts_sufficient"] is True


def test_q6_negative_cases_fail_closed():
    """错 authorization_id / 越权 operation / 超额账户 / trusted=false 各一条。"""

    wrong_id = opportunities.av_authorization_check(
        AUTH_FULL, operation="evaluate", expected_authorization_id="auth-other")
    assert wrong_id["ok"] is False
    assert [item["code"] for item in wrong_id["problems"]] == [
        "authorization_id_mismatch"]

    not_allowed = opportunities.av_authorization_check(
        dict(AUTH_FULL, allowed_operations=["evaluate"]), operation="family_fill")
    assert not_allowed["ok"] is False
    assert "operation_not_allowed" in [item["code"]
                                       for item in not_allowed["problems"]]

    modified = opportunities.av_authorization_check(
        dict(AUTH_FULL, allowed_operations=["evaluate", "root_admin"]),
        operation="evaluate")
    assert modified["ok"] is False
    assert "operation_set_modified" in [item["code"]
                                        for item in modified["problems"]]

    over = opportunities.av_authorization_check(
        AUTH_FULL, operation="family_fill", required={"tables_full": 4096.0})
    assert over["ok"] is False
    assert over["accounts_sufficient"] is False
    assert "account_insufficient" in [item["code"] for item in over["problems"]]

    untrusted = opportunities.av_authorization_check(
        dict(AUTH_FULL, trusted=False), operation="evaluate")
    assert untrusted["ok"] is False
    assert "trusted_false" in [item["code"] for item in untrusted["problems"]]

    unknown_issuer = opportunities.av_authorization_check(
        dict(AUTH_FULL, issued_by="model"), operation="evaluate")
    assert unknown_issuer["ok"] is False
    assert "issuer_untrusted" in [item["code"] for item in unknown_issuer["problems"]]


def test_q6_legacy_batch7_remains_accepted_same_scope_with_audit():
    verdict = search.av_authorization_allows(AUTH_LEGACY, operation="natural_panel",
                                             required={"tables_full": 1.0})
    ok, reason, audit = verdict
    assert ok is True, reason
    assert audit["authorization_form"] == "legacy_batch7"
    assert audit["legacy_removal_condition"]
    assert "移除动作由 Lead" in audit["legacy_removal_condition"]
    assert sorted(audit["allowed_operations"]) == sorted(
        opportunities.AV_AUTHORIZATION_OPERATIONS)
    # 缺令牌 / 未知形态一律拒绝（不能直接去掉授权约束）。
    assert search.av_authorization_allows(None, operation="evaluate")[0] is False
    bad = search.av_authorization_allows({"authorized": True, "batch": 6},
                                         operation="evaluate")
    assert bad[0] is False and "authorization_form_unknown" in bad[1]
    assert search.av_real_table_fail_closed.__doc__


def test_q6_state_machine_records_refusal_and_audit(tmp_path):
    """自然面板步：统一校验不通过 ⇒ 不动一张桌，并把审计原样落进状态。"""

    state = {"iter_dir": str(tmp_path), "step_history": [], "status": "CONDITIONAL_EVALUATED",
             "plan": {"predicate": SUB_OPEN, "opponent": "H", "panel_seed": SEED,
                      "natural_roots": 1, "natural_seats": 1,
                      "natural_opponents": ["H", "M"], "prefix_source": "v2_behavior"},
             "identity": {}}
    token = {"authorized": True, "batch": 7,
             "budgets": {"prefix_generation": 4.0}}      # 未声明 tables_full
    result = search._step_natural(state, tmp_path, token)
    assert result == {"advanced": "NATURAL_EVALUATED"}
    assert state["natural"]["status"] == "INPUT_GAP"
    assert "受信" in state["natural"]["reason"]
    audit = state["authorization"]
    assert audit["authorization_form"] == "legacy_batch7"
    assert audit["operation"] == "natural_panel"
    assert audit["accounts_sufficient"] is False
    assert "account_not_declared" in [item["code"] for item in audit["problems"]]
    # 计划量如实记录（1 根 × 1 座 × 2 臂 × 2 桌 × 2 情景 = 8；与状态机预留公式同源）。
    assert state["authorization"]["planned"]["tables_full"] == 8.0


# ===========================================================================
# 跨目录连续恢复 · archive_in 内容身份绑定
# ===========================================================================


def _write_input_dir(root: Path, *, entries=2):
    root.mkdir(parents=True, exist_ok=True)
    archive = {"schema": "sitin-action-value-archive/1",
               "entries": {"c{0}".format(i): {"candidate_id": "c{0}".format(i)}
                           for i in range(entries)},
               "slots": {"overall": ["c0"]}}
    (root / "av-archive.json").write_text(json.dumps(archive), encoding="utf-8")
    (root / "family-epochs.json").write_text(json.dumps(
        {"schema": search.AV_FAMILY_EPOCHS_SCHEMA,
         "channels": {CHANNEL: {"epoch": 1, "roots": []}}}), encoding="utf-8")
    (root / "family-roots.json").write_text(json.dumps(
        {"schema": search.AV_FAMILY_ROOTS_SCHEMA, "channels": {}}), encoding="utf-8")
    return root


def _start_iteration(tmp_path, *, input_dir, name):
    return search.av_start_iteration(
        tmp_path / name,
        archive_in={"source": "explicit", "path": str(input_dir / "av-archive.json")},
        authorization=AUTH_FULL, panel_seed=SEED)


def test_archive_in_content_identity_frozen_with_snapshots(tmp_path):
    """开轮固化：档案 / 家族 epoch / 根用途清单的内容身份 + 固定快照。"""

    input_dir = _write_input_dir(tmp_path / "chain" / "iter-01" / "archive")
    state = _start_iteration(tmp_path, input_dir=input_dir, name="run-p11")
    identity = state["plan"]["archive_in"]["content_identity"]
    assert identity["schema"] == search.AV_ARCHIVE_INPUT_IDENTITY_SCHEMA
    kinds = {item["kind"] for item in identity["artifacts"]}
    assert kinds == {"archive", "family_epochs", "root_purpose_list"}
    assert all(item["enforced_drift_refusal"] for item in identity["artifacts"])
    for item in identity["artifacts"]:
        assert Path(item["snapshot"]).is_file()
        assert Path(item["snapshot"]).read_bytes() == Path(item["path"]).read_bytes()
    # 读取走固定快照：在案档案与该输入一致。
    previous = search._av_previous_archive(state, Path(state["iter_dir"]).parent)
    assert sorted(previous["entries"]) == ["c0", "c1"]
    verdict = search.av_archive_input_verify(state)
    assert verdict["ok"] is True and verdict["status"] == "matched"


def test_archive_in_content_drift_refuses_recovery(tmp_path):
    """反例：**改档案内容但不改路径** ⇒ 拒绝恢复（不按新内容继续）。"""

    input_dir = _write_input_dir(tmp_path / "chain" / "iter-01" / "archive")
    run_root = tmp_path / "run-p11-drift"
    state = _start_iteration(tmp_path, input_dir=input_dir, name="run-p11-drift")
    state_path = Path(state["iter_dir"]) / "state.json"
    # 同路径改写内容（多一条候选、换席位）。
    changed = json.loads((input_dir / "av-archive.json").read_text(encoding="utf-8"))
    changed["entries"]["c9"] = {"candidate_id": "c9"}
    changed["slots"] = {"overall": ["c9"]}
    (input_dir / "av-archive.json").write_text(json.dumps(changed), encoding="utf-8")
    # 家族 epoch 表同样换内容不改路径。
    epochs = json.loads((input_dir / "family-epochs.json").read_text(encoding="utf-8"))
    epochs["channels"][CHANNEL]["epoch"] = 99
    (input_dir / "family-epochs.json").write_text(json.dumps(epochs), encoding="utf-8")
    reloaded = search.av_state_load(state_path)
    verdict = search.av_archive_input_verify(reloaded)
    assert verdict["ok"] is False and verdict["status"] == "drift"
    assert verdict["problems"][0]["kind"] == "archive"
    assert "拒绝恢复" in verdict["problems"][0]["reason"]
    # ① 恢复入口直接停为具名 INPUT_GAP（不推进任何一步）。
    result = search.av_iteration_advance(state_path, run_root)
    assert result["terminal"] == "INPUT_GAP"
    assert result["archive_input"]["status"] == "drift"
    assert search.av_state_load(state_path)["stop_reason"] == \
        search.AV_ARCHIVE_INPUT_DRIFT_STOP_REASON
    # ② 读取面同样拒绝（不静默改用新内容）。
    with pytest.raises(search.ArchiveInputDrift) as failure:
        search._av_previous_archive(reloaded, run_root)
    assert search.AV_ARCHIVE_INPUT_DRIFT_STOP_REASON in str(failure.value)
    with pytest.raises(search.ArchiveInputDrift):
        search._av_family_inherited_epochs(reloaded, run_root)
    assert [item["kind"] for item in search.av_archive_input_verify(reloaded)["problems"]] \
        == ["archive", "family_epochs"]


def test_archive_in_local_archive_is_not_drift_refused(tmp_path):
    """本运行目录自己的档案是增量提交基数：登记身份但不做漂移拒绝（如实分列）。"""

    run_root = tmp_path / "run-local"
    (run_root / "archive").mkdir(parents=True, exist_ok=True)
    (run_root / "archive" / "av-archive.json").write_text(json.dumps(
        {"entries": {"c0": {}}, "slots": {}}), encoding="utf-8")
    state = search.av_start_iteration(
        run_root,
        archive_in={"source": "local",
                    "path": str(run_root / "archive" / "av-archive.json")},
        authorization=AUTH_FULL, panel_seed=SEED)
    identity = state["plan"]["archive_in"]["content_identity"]
    archive_entry = [item for item in identity["artifacts"]
                     if item["kind"] == "archive"][0]
    assert archive_entry["enforced_drift_refusal"] is False
    assert "增量提交基数" in archive_entry["note"]
    (run_root / "archive" / "av-archive.json").write_text(json.dumps(
        {"entries": {"c0": {}, "c1": {}}, "slots": {}}), encoding="utf-8")
    verdict = search.av_archive_input_verify(state)
    assert verdict["ok"] is True
    assert verdict["enforced_kinds"] == []          # 本地档案不参与漂移拒绝（如实分列）


# ===========================================================================
# 注释算术更正（R9 裁定 §8）
# ===========================================================================


def test_comment_binomial_probability_is_corrected():
    """注释里的"12 次至少 2 次命中"必须写对数：独立二项假设下 84.1618%。"""

    text = Path(search.__file__).read_text(encoding="utf-8")
    assert "84.1618%" in text
    assert "成功率 > 95%" not in text
    probability = sum(math.comb(12, k) * 0.25 ** k * 0.75 ** (12 - k)
                      for k in range(2, 13))
    assert round(probability * 100, 4) == 84.1618
    assert "独立同分布" in text          # 假设边界写清（实测命中未证明 i.i.d.）


# ===========================================================================
# P1（Lead 转达 P12 实测）· 核心根缺失集合 = 冻结清单逐键覆盖
# ===========================================================================


def _core_rows(channel=CHANNEL, prefix_source="v2_behavior"):
    """冻结核心根清单：2 子场景 × 2 情景 × 2 根 = 8 根（与 P9c 同一形状）。"""

    rows = []
    for sub in (SUB_OPEN, SUB_COST):
        for mix in ("H", "M"):
            for index in (0, 1):
                descriptor = search.av_family_root_descriptor(
                    prefix_source=prefix_source, sub_scenario=sub, opponent_mix=mix,
                    panel_seed=SEED, root_index=index)
                row = {"root_id": descriptor["root_id"], "sub_scenario": sub,
                       "opponent_mix": mix, "root_index": index, "panel_seed": SEED,
                       "root_seed": descriptor["root_seed"], "generator": descriptor["generator"]}
                row["key"] = search._av_family_core_key(row)
                rows.append(row)
    return rows


def _record(d_point=1.0, unknown=False, mix="H"):
    return {"d_point": d_point, "d_low": d_point - 1, "d_high": d_point + 1,
            "unknown": unknown, "opponent_mix": mix}


def test_p1_coverage_is_key_based_and_exposes_production_undercount():
    """复现 P12 实测的少算：逐键缺失 **8** 条，而"有记录即算覆盖"的自报只有 **7** 条。

    构造与 P9c 证据一致：挑战者在该根上**没有任何合格评价**，但归档里有一条
    **不合格**记录（未分辨）——旧口径按"记录在不在"判覆盖 ⇒ 那一条不算缺失。
    """

    core = _core_rows()
    entry = {"family_evaluations": {
        SUB_OPEN: {"H|{0}".format(core[0]["root_id"]): _record(unknown=True, mix="H")}}}
    coverage = search.av_family_core_coverage(core_rows=core, entry=entry,
                                             candidate_id="candidate-x")
    assert coverage["n_roots"] == 8
    assert coverage["n_edges"] == 16
    assert coverage["n_edges_covered"] == 0           # 一条可核评价都没有
    assert len(coverage["missing_keys"]) == 8
    assert len(coverage["missing_tokens"]) == 8
    uncovered = [row for row in coverage["keys"] if not row["covered"]]
    assert len(uncovered) == 8
    assert uncovered[0]["records_seen"] == 1 and uncovered[0]["records_usable"] == 0
    # 生产自报（旧口径：记录存在即覆盖）只有 7 条 —— 少的正是 open|H|root000。
    covered_by_old_rule = "{0}|H|{1}".format(SUB_OPEN, core[0]["root_id"])
    reported = [token for token in coverage["missing_tokens"]
                if token != covered_by_old_rule]
    comparison = search._av_family_core_coverage_vs_reported(
        coverage=coverage, reported=reported)
    assert comparison["consistent"] is False
    assert comparison["n_frozen"] == 8 and comparison["n_reported"] == 7
    assert comparison["frozen_only"] == [covered_by_old_rule]
    assert comparison["reported_only"] == []
    # 工作项用逐键集合（8 条）：不是自报的 7 条。
    assert len(comparison["both"]) == 7


def test_p1_same_root_multiple_rows_do_not_override():
    """同一根的多条记录（跨情景裸键 + 合格记录）取并集、不互相顶掉。"""

    core = _core_rows()[:1]                       # branch_open|H|root000
    other_mix = search.av_family_root_descriptor(
        prefix_source="v2_behavior", sub_scenario=SUB_OPEN, opponent_mix="M",
        panel_seed=SEED, root_index=0)
    # 情景限定键上是一条**不合格**记录；裸键上是一条**合格**记录（同一情景 H）。
    # 旧实现只取第一条命中（不合格）⇒ 误判缺失；新实现取并集 ⇒ 覆盖。
    entry = {"family_evaluations": {SUB_OPEN: {
        "H|{0}".format(core[0]["root_id"]): _record(unknown=True, mix="H"),
        str(core[0]["root_id"]): _record(mix="H")}}}
    coverage = search.av_family_core_coverage(core_rows=core, entry=entry,
                                             candidate_id="candidate-x")
    key_row = coverage["keys"][0]
    assert key_row["records_seen"] == 2
    assert key_row["records_usable"] == 1          # 不合格那条不顶掉合格记录
    assert key_row["covered"] is True
    assert all(item["basis"].startswith(("evaluation_product", "paired_archive_record"))
               for item in key_row["arms"].values())
    # 反向：只剩跨情景记录 ⇒ 判缺失（旧口径会把它当成覆盖）。
    only_foreign = {"family_evaluations": {SUB_OPEN: {
        str(other_mix["root_id"]): _record(mix="M")}}}
    bare = search.av_family_core_coverage(core_rows=core, entry=only_foreign,
                                         candidate_id="candidate-x")
    assert bare["keys"][0]["covered"] is False
    assert bare["missing_tokens"] == ["{0}|H|{1}".format(SUB_OPEN, core[0]["root_id"])]


def test_p1_arm_level_products_are_the_strongest_evidence(tmp_path):
    """臂级证据来自评价产物（arms_complete）：齐备即无缺失，缺一臂即该键未覆盖。"""

    core = _core_rows()[:1]
    run_root = tmp_path / "run-p1"
    path = run_root / "iterations" / "iter-02" / "family" / "branch_open-H" / "evaluation.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    product = {"ok": True, "identity": {"candidate_id": "candidate-x"},
               "samples": [{"scenario": SUB_OPEN, "opponent_mix": "H",
                            "root_index": 0, "root_seed": core[0]["root_seed"],
                            "source_root_id": core[0]["root_id"],
                            "arms": {"baseline": {"status": "complete", "usable": True},
                                     "candidate": {"status": "complete", "usable": True}}}]}
    path.write_text(json.dumps(product), encoding="utf-8")
    products = search._av_family_evaluation_products(run_root)
    assert len(products) == 1 and products[0]["arms_complete"] is True
    coverage = search.av_family_core_coverage(core_rows=core, entry=None,
                                             candidate_id="candidate-x",
                                             products=products)
    assert coverage["n_edges_covered"] == 2 and coverage["missing_tokens"] == []
    # 一臂失败 ⇒ 两臂都未覆盖（并要求记录级来源也缺席）。
    product["samples"][0]["arms"]["candidate"] = {"status": "invalid", "usable": False}
    path.write_text(json.dumps(product), encoding="utf-8")
    products = search._av_family_evaluation_products(run_root)
    partial = search.av_family_core_coverage(core_rows=core, entry=None,
                                            candidate_id="candidate-x",
                                            products=products)
    assert partial["keys"][0]["uncovered_arms"] == ["baseline", "candidate"]
    assert partial["n_edges_covered"] == 0


def _full_core_registry(*, indexes=(1, 2)):
    """完整核心矩阵视图（P16-FU 起：首次冻结要求 4 格 × 2 根 = 8 根）。"""

    cells = {}
    for sub in (SUB_OPEN, SUB_COST):
        for mix in ("H", "M"):
            cells["{0}|{1}".format(sub, mix)] = [
                search.av_family_root_descriptor(
                    prefix_source="v2_behavior", sub_scenario=sub, opponent_mix=mix,
                    panel_seed=SEED, root_index=index)["root_id"]
                for index in indexes]
    return {"cells_by_side_mix": cells}


def test_p1_frozen_core_list_is_immutable_after_freeze(tmp_path):
    """需求集合**先冻结**：运行中登记表变化不得改写需求集合（P16-FU：改判具名拒绝）。

    冻结只在**完整视图**下发生（8 根）；冻结后换成另一批根 ⇒ 具名拒绝并要求新运行
    身份（不再只记 conflicts 后继续用旧集合——那会让运行悄悄按变化后的义务跑）。
    """

    freeze_path = tmp_path / "family-core-roots.json"
    first = search.av_family_core_root_list(channel=CHANNEL,
                                            registry=_full_core_registry(),
                                            freeze_path=freeze_path)
    assert first["source"] == "derived" and first["n_roots"] == 8
    assert first["created"] is True and freeze_path.is_file()
    original = freeze_path.read_bytes()
    # 同一视图再读：只读、逐字不变。
    second = search.av_family_core_root_list(channel=CHANNEL,
                                             registry=_full_core_registry(),
                                             freeze_path=freeze_path)
    assert second["source"] == "frozen" and second["created"] is False
    assert [row["key"] for row in second["roots"]] == \
        [row["key"] for row in first["roots"]]
    # 换成另一批根（同形状、不同成员）：**成员位移只记具名读数**——登记表随运行增长时
    # "每格取排序前 N 根"的推导本就会位移（r8/p7c 家族换席流程实测），需求集合仍以
    # 冻结件为准；既不覆盖重写、也不误停运行。
    shifted = search.av_family_core_root_list(channel=CHANNEL,
                                              registry=_full_core_registry(indexes=(5, 6)),
                                              freeze_path=freeze_path)
    assert shifted["source"] == "frozen" and shifted["created"] is False
    assert shifted["n_roots"] == 8
    assert shifted["conflicts"] and shifted["conflicts"][0]["code"] == \
        "frozen_core_list_membership_delta"
    assert freeze_path.read_bytes() == original, "运行中不得改写既有冻结件"
    # 冻结件**结构缺根**（run7 形态：只有 1 格 / 1 根）而当前声明已能给出完整集合
    # ⇒ 具名拒绝、要求新运行身份（保留原件）。
    short_path = tmp_path / "family-core-roots-short.json"
    one_root_id = _full_core_registry()["cells_by_side_mix"][
        "{0}|H".format(SUB_OPEN)][0]
    one_seed = search.av_family_root_seed(
        prefix_source="v2_behavior", sub_scenario=SUB_OPEN, opponent_mix="H",
        panel_seed=SEED, root_index=1)
    short_row = {"root_id": one_root_id, "sub_scenario": SUB_OPEN, "opponent_mix": "H",
                 "root_index": 1, "panel_seed": SEED, "root_seed": one_seed}
    short_row["key"] = search._av_family_core_key(short_row)
    short_path.write_text(json.dumps({
        "schema": search.AV_FAMILY_CORE_LIST_SCHEMA, "channel": CHANNEL,
        "frozen_at_utc": "2026-09-18T17:22:36Z", "roots": [short_row]},
        ensure_ascii=False), encoding="utf-8")
    short_before = short_path.read_bytes()
    with pytest.raises(search.FamilyCoreListRefused) as failure:
        search.av_family_core_root_list(channel=CHANNEL,
                                        registry=_full_core_registry(),
                                        freeze_path=short_path)
    assert failure.value.stop_reason == \
        search.AV_FAMILY_CORE_LIST_CONFLICT_STOP_REASON
    assert failure.value.problems[0]["derived_n_roots"] == 8
    assert short_path.read_bytes() == short_before, "运行中不得改写既有冻结件"


def test_p1_fill_items_accept_the_frozen_missing_override():
    """工作项用**冻结推导的缺失集合**（override），生产自报只作对照。"""

    run_root = None
    rows = [_row(SUB_OPEN, "H", 1, intent="discover_new_root")]
    state = {"plan": {"prefix_source": "v2_behavior", "panel_seed": SEED,
                      "family_channel": CHANNEL},
             "identity": {"candidate_id": "candidate-x"}, "iteration_no": 1}
    root_id = search.av_family_root_descriptor(
        prefix_source="v2_behavior", sub_scenario=SUB_OPEN, opponent_mix="H",
        panel_seed=SEED, root_index=1)["root_id"]
    registry = {"cells": {"{0}|H|{1}".format(SUB_OPEN, root_id): {
        "sub_scenario": SUB_OPEN, "opponent_mix": "H", "root_id": root_id,
        "panel_seed": SEED, "root_index": 1, "root_seed": search.av_family_root_seed(
            prefix_source="v2_behavior", sub_scenario=SUB_OPEN, opponent_mix="H",
            panel_seed=SEED, root_index=1)}}, "conflicts": [], "refused": []}
    token = "{0}|H|{1}".format(SUB_OPEN, root_id)
    items, blocked = search._av_family_fill_items(
        state=state, outcome={"missing": {}}, registry=registry, channel=CHANNEL,
        missing_override={"candidate-x": [token]})
    assert blocked == []
    assert [item["token"] for item in items] == [token]
    assert items[0]["root_ids"] == [root_id]
    # 不给 override 时行为不变（旧口径逐字保留）。
    legacy_items, _ = search._av_family_fill_items(
        state=state, outcome={"missing": {"candidate-x": [token]}},
        registry=registry, channel=CHANNEL)
    assert [item["token"] for item in legacy_items] == [token]


# ===========================================================================
# P2 · 授权形态对接（legacy 显式标注 / dual 冲突拒绝 / 档案字段）
# ===========================================================================

#: 真实 gate2 授权文件的形态（legacy 字段 + 自己的旧 schema 标签）。
AUTH_GATE2_LEGACY = {
    "schema": "sitin-gate2-authorization/1", "authorized": True, "batch": 7,
    "batch_label": "gate2-20260918",
    "budgets": {"tables_full": 264, "tables_partial": 122, "prefix_generation": 101,
                "tokens_input": 0, "tokens_output": 0, "confirm_reserved": 0.0},
}


def test_p2_legacy_gate2_document_is_accepted_and_labeled():
    """带旧 schema 标签的 batch7 授权仍按 legacy 接受，并被**显式标注**。"""

    verdict = opportunities.av_authorization_check(
        AUTH_GATE2_LEGACY, operation="natural_panel",
        required={"tables_full": 1.0})
    assert verdict["ok"] is True, verdict["problems"]
    assert verdict["authorization_form"] == "legacy_batch7"
    assert verdict["legacy_removal_condition"]
    stamp = search.av_authorization_stamp(AUTH_GATE2_LEGACY)
    assert stamp["authorization_form"] == "legacy_batch7"
    assert stamp["legacy_removal_condition"]
    assert stamp["budgets"] == AUTH_GATE2_LEGACY["budgets"]      # 原字段一字不改
    entry = search.av_authorization_archive_entry(
        AUTH_GATE2_LEGACY, operation="natural_panel",
        required={"tables_full": 1.0})
    for field in ("authorization_form", "authorization_id", "batch_label", "trusted",
                  "allowed_operations", "allowed_accounts", "required", "ok",
                  "problems"):
        assert field in entry, field
    assert entry["authorization_form"] == "legacy_batch7"
    assert entry["batch_label"] == "gate2-20260918"


def test_p2_dual_form_conflict_is_refused_and_consistent_dual_passes():
    """dual 形态：两条额度表冲突必须拒绝；一致时按完整形态接受并标 dual。"""

    dual = dict(AUTH_FULL, authorized=True, batch=7,
                budgets=dict(AUTH_FULL["allowed_accounts"]))
    verdict = opportunities.av_authorization_check(dual, operation="family_fill")
    assert verdict["authorization_form"] == "dual_sitin_authorization_1"
    assert verdict["ok"] is True, verdict["problems"]
    conflict = dict(dual, budgets=dict(dual["budgets"], tables_full=8.0))
    refused = opportunities.av_authorization_check(conflict, operation="family_fill")
    assert refused["ok"] is False
    assert "dual_form_account_conflict" in [item["code"]
                                            for item in refused["problems"]]

