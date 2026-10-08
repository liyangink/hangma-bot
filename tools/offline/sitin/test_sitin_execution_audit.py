"""评分执行审计回归：真实策略/驱动/汇总，世界使用脚本替身，不作为效果样本。"""
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
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sitin_execution_audit as audit
import sitin_natural_panel as natural
import sitin_real_behavior as behavior
from hangma_bot import bootstrap
from hangma_bot.kernel.actions import WindowPhase

sys.path.insert(0, str(natural.REPO / "tests/offline"))
from support import FakeChoice, FakeDecision, FakeEngine, FakeFrame, FakeMatchSpec, final_frame

IDS = ["action_value_v1:probe", "v2", "v2", "v2"]
SCORED = "action_value: probe 评分完成"
ABSTAIN = "action_value_failed: ABSTAIN test"
OPERATION = "action_value_failed: 候选整批失败 WorkloadExceeded: 计数操作超限：已用 100001，上限 100000"
RESOURCE = "action_value_failed: 候选整批失败 WorkloadExceeded: 局部集合超过 4096 项上限"
FALLBACK = "action_value_failed: 评分不可用，使用合法保底"
SOURCES = {
    "scored": 'def score_actions(view):\n    return {"status": "SCORED", "entries": [{"action_key": a["action_key"], "score": 0.0, "trace": {}} for a in view["actions"]]}\n',
    "abstain": 'def score_actions(view):\n    return {"status": "ABSTAIN", "reason": "test"}\n',
    "operation_limit": 'def score_actions(view):\n    for i in range(100001):\n        x = i\n    return {"status": "ABSTAIN", "reason": "unreachable"}\n',
    "resource_or_numeric_limit": 'def score_actions(view):\n    values = list(range(4097))\n    return {"status": "ABSTAIN", "reason": "unreachable"}\n',
}


def row(i=0, *, seat=0, reasons=(), policy_id=IDS[0]):
    return SimpleNamespace(decision_id=f"decision-{i}", seat=seat,
                           policy_id=policy_id, degraded_reasons=tuple(reasons))


def table_for(rows):
    value = audit.summarize(rows, policy_ids_by_seat=IDS)
    versions = {f"natural_seat_policy:{i}": name for i, name in enumerate(IDS)}
    versions.update(policy_execution_schema=audit.SCHEMA,
                    policy_execution_sha256=audit.digest(value))
    return {"result": {"versions": versions}, "policy_execution": value}


def install_scripted_world(monkeypatch):
    """复用历史合法请求；规则/策略/自然编排实际执行，只替换世界推进。

    这里测试的是评分诊断穿过驱动、落盘和独立汇总的完整性，不复核历史
    开发面板的当前 ``candidate_view``。P55 修正条件分值规则后，同一原始
    ``DecisionRequest`` 的投影摘要按设计会变化；继续调用 ``load_panel``
    会把规则演进误报成执行审计失败。原始记录及请求摘要仍逐项校验。
    """
    panel_path = (
        _project_file(_PROJECT_ROOT, HERE.parent
        / "evidence/r10-supervised-evolution/real-behavior-panel-v1/panel.json")
    )
    manifest = json.loads(panel_path.read_text())
    requests = []
    for entry in manifest["windows"]:
        data = json.loads((panel_path.parent / entry["file"]).read_text())
        assert behavior.digest(data) == entry["record_sha256"]
        assert behavior.digest(data["request"]) == data["request_sha256"]
        requests.append(behavior.decision_request_from_json(data["request"]))
    request = next(request for request in requests if request.window_key.phase is WindowPhase.DRAW)
    contract = json.loads((natural.REPO / natural.DEFAULT_CONTRACT).read_text())
    plans = [plan for focal in range(4) for plan in natural.build_seat_stage_plans(
        contract=contract, opponent="H", root_index=1,
        focal_seat=focal, panel_seed=natural.DEFAULT_PANEL_SEED)]
    seats = {plan.match_id: list(plan.seats()).index(natural.FOCAL_PARTICIPANT) for plan in plans}
    def frames(spec):
        seat = seats[spec.match_id]
        observation = replace(request.observation, seat=seat, turn_seat=seat)
        decision = FakeDecision(replace(request.window_key, seat=seat), observation)
        return [FakeFrame(1, (decision,), 0), final_frame(2, (0, 0, 0, 0), spec.config.rounds_per_game)]
    engine = FakeEngine(frames)
    monkeypatch.setattr(bootstrap, natural.BOOTSTRAP_RUNTIME_HOOK,
        lambda *args: {"engine": engine, "spec_factory": FakeMatchSpec, "choice_factory": FakeChoice})
    return engine


def run_panel(tmp_path, source, *, seats=1):
    contract = json.loads((natural.REPO / natural.DEFAULT_CONTRACT).read_text())
    return natural.run_natural_panel(candidate_source=source, opponent="H", roots=1,
        seats_per_root=seats, min_roots=1, contract=contract,
        authorization={"authorized": True, "batch": 7, "budgets": {"tables_full": float(4 * seats)}},
        out_dir=tmp_path)


@pytest.mark.parametrize("mode", list(SOURCES))
def test_real_scoring_diagnostic_survives_stage_and_disk(monkeypatch, tmp_path, mode):
    """真实评分内部失败不增加驱动fallbacks；经过双臂、阶段和落盘仍独立可核。"""
    engine = install_scripted_world(monkeypatch)
    panel = run_panel(tmp_path, SOURCES[mode])
    stored = json.loads((tmp_path / "panel.json").read_text())
    assert len(engine.started_specs) == 4
    assert panel == stored
    assert panel["identity"]["policy_execution_schema"] == audit.SCHEMA
    assert all(sample["completeness"] == "complete" for sample in stored["samples"])
    review = stored["execution_review"]
    assert review["recorded_tables"] == 4 and review["missing_tables"] == 0
    assert review["status"] == ("complete" if mode == "scored" else "requires_review")
    for sample in stored["samples"]:
        for arm in ("candidate", "baseline"):
            record = sample["raw_arms"][arm]
            assert record["execution_review"] == audit.review_tables(record["tables"])
            for table in record["tables"]:
                current = audit.verify_table(table)
                assert table["result"]["runtime_counts"]["fallbacks"] == 0
                assert current["decision_count"] == 1
                if arm == "candidate":
                    assert current["action_value_scored"] == int(mode == "scored")
                    assert current["action_value_failed"] == int(mode != "scored")
                    if mode != "scored":
                        assert current["failure_kinds"][mode] == 1


def test_missing_policy_id_uses_declared_scoring_seat():
    result = audit.summarize([row(policy_id=None)], policy_ids_by_seat=IDS)
    assert result["unclassified_action_value"] == 1
    assert result["other_policy_decisions"] == result["action_value_scored"] == 0


@pytest.mark.parametrize("release_id", [
    "release:r18-integrated-positive-v1:freeze",
    "release:r18-integrated-positive-v2:freeze",
])
def test_r18_release_policy_is_counted_as_scoring(release_id):
    """发布包只改变身份封装，受限评分成功仍应算成功而非歧义。"""
    ids = [release_id, "v2", "v2", "v2"]
    result = audit.summarize([row(reasons=(SCORED,), policy_id=release_id)],
                             policy_ids_by_seat=ids)
    assert result["action_value_scored"] == 1
    assert result["ambiguous_diagnostics"] == 0


def test_failure_causes_count_windows_not_two_messages():
    result = audit.summarize([row(reasons=(OPERATION, FALLBACK, OPERATION)),
        row(1, reasons=(RESOURCE, FALLBACK)), row(2, reasons=(ABSTAIN, FALLBACK))], policy_ids_by_seat=IDS)
    assert result["action_value_failed"] == 3
    assert sum(result["failure_kinds"].values()) == 3
    assert sum(result["failure_reason_counts"].values()) == 6
    assert result["failure_kinds"]["operation_limit"] == 1
    assert result["failure_kinds"]["resource_or_numeric_limit"] == 1


@pytest.mark.parametrize("record", [
    row(reasons=(SCORED, ABSTAIN)),
    row(reasons=(SCORED,), policy_id="wrong-policy"),
    row(seat=1, reasons=(SCORED,), policy_id="v2"),
])
def test_conflicting_or_wrong_seat_markers_never_count_as_success(record):
    result = audit.summarize([record], policy_ids_by_seat=IDS)
    assert result["ambiguous_diagnostics"] == 1 and result["action_value_scored"] == 0


def test_rule_degradation_is_separate_from_scoring_failure():
    result = audit.summarize([row(reasons=(SCORED, "规则降级[x]：test")),
        row(1, seat=1, reasons=("规则降级[x]：test",), policy_id="v2")], policy_ids_by_seat=IDS)
    assert result["action_value_scored"] == result["other_policy_decisions"] == 1
    assert result["action_value_failed"] == 0


def test_protected_successor_wrapper_preserves_action_value_classification():
    """后继包装策略的基线评分成功/失败仍须进入评分桶。"""

    wrapped = ["protected-r17:73c2833da12f", "v2", "v2", "v2"]
    scored = audit.summarize(
        [row(reasons=(SCORED,), policy_id=wrapped[0])],
        policy_ids_by_seat=wrapped,
    )
    failed = audit.summarize(
        [row(reasons=(OPERATION, FALLBACK), policy_id=wrapped[0])],
        policy_ids_by_seat=wrapped,
    )

    assert scored["action_value_scored"] == 1
    assert scored["ambiguous_diagnostics"] == 0
    assert failed["action_value_failed"] == 1
    assert failed["failure_kinds"]["operation_limit"] == 1


@pytest.mark.parametrize("records", [[row(), row()], [row(seat=True)], [row(seat=4)]])
def test_bad_identity_or_seat_is_rejected(records):
    with pytest.raises(ValueError):
        audit.summarize(records, policy_ids_by_seat=IDS)


@pytest.mark.parametrize("change", ["missing", "schema", "bool", "seat", "digest", "policy", "kind"])
def test_persisted_corruption_is_rejected(change):
    table = table_for([row(reasons=(OPERATION, FALLBACK))])
    if change == "missing": del table["policy_execution"]
    elif change == "schema": table["policy_execution"]["schema"] = "old"
    elif change == "bool": table["policy_execution"]["decision_count"] = True
    elif change == "seat": table["policy_execution"]["by_seat"][0]["decision_count"] = 2
    elif change == "digest": table["result"]["versions"]["policy_execution_sha256"] = "0" * 64
    elif change == "policy": table["result"]["versions"]["natural_seat_policy:0"] = "v2"
    elif change == "kind": table["policy_execution"]["failure_kinds"]["operation_limit"] = 0
    with pytest.raises(ValueError): audit.verify_table(json.loads(json.dumps(table)))


def test_history_and_empty_sample_are_unknown_not_zero():
    old = {"result": {"versions": {}, "runtime_counts": {"fallbacks": 0}}}
    assert audit.verify_table(old, required=False) is None
    with pytest.raises(ValueError): audit.verify_table(old)
    known = table_for([row(reasons=(SCORED,))])
    mixed = audit.review_tables([old, known], required=False)
    assert mixed["status"] == "unknown" and mixed["missing_tables"] == 1
    assert mixed["zero_internal_failures_verified"] is False
    assert audit.review_tables([])["zero_internal_failures_verified"] is False


def test_stage_rejects_lost_diagnostic_and_preserves_failed_artifact(monkeypatch, tmp_path):
    """复现旧集成漏字段位置；损坏不能被完整终局或成功退出掩盖。"""
    install_scripted_world(monkeypatch)
    original = natural.execute_natural_table
    def lose(**kwargs):
        result = original(**kwargs)
        del result["policy_execution"]
        return result
    monkeypatch.setattr(natural, "execute_natural_table", lose)
    panel = run_panel(tmp_path, SOURCES["scored"])
    assert panel["samples"][0]["completeness"] == "invalid"
    assert panel["execution_review"]["status"] == "invalid"
    assert (tmp_path / "panel.json").exists()
    assert len(panel["samples"][0]["raw_arms"]["candidate"]["tables"]) == 1


def test_dependency_graph_includes_audit_implementation():
    import sitin_deps
    graph = sitin_deps.entry_call_graph(reader=lambda path: path.read_bytes(),
                                      entries=["sitin_natural_panel.py"])
    assert not graph["missing"]
    assert any(node["path"].endswith("/sitin_execution_audit.py") for node in graph["nodes"].values())


@pytest.mark.parametrize("change", ["clean", "missing_table", "strip_versions", "arm_summary", "panel_summary"])
def test_independent_full_result_verifier_checks_audit(monkeypatch, tmp_path, change):
    """独立读取器重算汇总；身份声明了新审计后不能删字段退回历史兼容模式。"""
    import copy
    sys.path.insert(0, str(_project_file(_PROJECT_ROOT, HERE.parent / "evidence/r10-supervised-evolution")))
    from verify_full_natural_results import verify_full_panel

    install_scripted_world(monkeypatch)
    panel = run_panel(tmp_path, SOURCES["abstain"], seats=4)
    frozen_identity = copy.deepcopy(panel["identity"])
    raw = panel["samples"][0]["raw_arms"]["candidate"]
    table = raw["tables"][0]
    rules_hash = table["result"]["versions"]["rules_hash"]
    if change in ("missing_table", "strip_versions"):
        del table["policy_execution"]
    if change == "strip_versions":
        del table["result"]["versions"]["policy_execution_schema"]
        del table["result"]["versions"]["policy_execution_sha256"]
    if change == "arm_summary": raw["execution_review"]["recorded_counts"]["action_value_failed"] = 0
    if change == "panel_summary": panel["execution_review"]["zero_internal_failures_verified"] = True
    contract = json.loads((natural.REPO / natural.DEFAULT_CONTRACT).read_text())
    def verify():
        return verify_full_panel(panel, contract, expected_identity=frozen_identity,
                                 expected_root_indices=[1], expected_rules_hash=rules_hash)
    if change == "clean":
        result = verify()
        assert result["execution_review"]["status"] == "requires_review"
        assert result["execution_review"]["recorded_counts"]["action_value_failed"] == 8
    else:
        with pytest.raises(ValueError, match="评分.*(审计|汇总)"): verify()


def test_resume_rechecks_persisted_scoring_audit_without_new_execution(monkeypatch, tmp_path):
    """接线原型恢复复用原结果，仍检查内部审计；篡改计数不能靠重签外层摘要通过。"""
    sys.path.insert(0, str(_project_file(_PROJECT_ROOT, HERE.parent / "evidence/r10-supervised-evolution")))
    import confirmation_execution_probe as probe

    install_scripted_world(monkeypatch)
    panel = run_panel(tmp_path / "panel", SOURCES["abstain"])
    contract = json.loads((natural.REPO / natural.DEFAULT_CONTRACT).read_text())
    plans = natural.build_seat_stage_plans(contract=contract, opponent="H", root_index=1,
        focal_seat=0, panel_seed=natural.DEFAULT_PANEL_SEED)
    raw = panel["samples"][0]["raw_arms"]["candidate"]
    rules_hash = raw["tables"][0]["result"]["versions"]["rules_hash"]
    ledger = probe.b.search.ActionValueLedger.load(tmp_path / "ledger.json", authorized_budgets={"tables_full": 2})
    expected = {"step_id": "fixture-audit-resume", "planned_tables": 2}
    calls = []
    def runner(): calls.append(1); return raw
    def verifier(value):
        return probe.verify_arm(value, arm="candidate", plans=plans, contract=contract,
            identity=panel["identity"]["candidate_id"], rules_hash=rules_hash)
    folder = tmp_path / "arm"
    first = probe.execute_arm(folder, expected=expected, ledger=ledger, runner=runner, verifier=verifier)
    second = probe.execute_arm(folder, expected=expected, ledger=ledger, runner=runner, verifier=verifier)
    assert first == second and calls == [1] and ledger.spent("tables_full") == 2
    assert first["execution_review"]["status"] == "requires_review"
    path = folder / "result.json"
    bundle = json.loads(path.read_text())
    bundle["raw"]["tables"][0]["policy_execution"]["action_value_failed"] = 0
    bundle["raw_digest"] = probe.analysis.digest(bundle["raw"])
    path.write_text(json.dumps(bundle))
    with pytest.raises(ValueError):
        probe.execute_arm(folder, expected=expected, ledger=ledger, runner=runner, verifier=verifier)
    assert calls == [1] and ledger.spent("tables_full") == 2
