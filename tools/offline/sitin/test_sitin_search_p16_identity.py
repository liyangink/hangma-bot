# -*- coding: utf-8 -*-
"""P16 定向测试：生产身份链四条缺口（S1 / C1 / C5）的拒绝与放行读数。

- S1（P1）：冻结输入失败或快照变质，恢复仍放行 —— 冻结写入失败必须具名停止；
  消费前必须核验**实际读取的快照字节**（"原文件未变"证明不了"快照未变"）；
  空档案新运行与显式兼容的旧夹具分支处理，不以 unregistered 普遍放行。
- C1（P1）：相同根序号的不同根被算作已完成重评 —— 需求与产物统一到**完整根身份**
  （候选 / 来源根 ID / 实际种子 / 子场景 / 情景 / 生成器 / 座位 / 臂），缺关键身份
  不得用序号兜底；旧档案记录回退必须有明确可信条件。
- C5（P2）：既有冻结清单损坏时被当成首次冻结重写 —— 只有明确首次初始化且文件不存在
  才创建；已有文件不可读 / 不合法 / 身份不符即停止并保留原件；写入失败不得继续。

0 真实桌赛 / 0 模型调用 / 0 网络（全部为纯数据与临时目录内的合成输入）。
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
import shutil
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import sitin_search as search  # noqa: E402

CHANNEL = "branch"
SEED = 20260916
CANDIDATE = "cand-p16"


# ===========================================================================
# S1 · 冻结输入失败 / 快照变质
# ===========================================================================


def _write_input_dir(root: Path, *, entries=2) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "av-archive.json").write_text(json.dumps(
        {"schema": "sitin-action-value-archive/1",
         "entries": {"c{0}".format(i): {"candidate_id": "c{0}".format(i)}
                     for i in range(entries)},
         "slots": {"overall": ["c0"]}}), encoding="utf-8")
    (root / "family-epochs.json").write_text(json.dumps(
        {"schema": search.AV_FAMILY_EPOCHS_SCHEMA,
         "channels": {CHANNEL: {"epoch": 1, "roots": []}}}), encoding="utf-8")
    return root


AUTH = {
    "schema": "sitin-authorization/1",
    "authorization_id": "auth-p16-0001",
    "batch_label": "p16-identity",
    "trusted": True,
    "allowed_operations": ["natural_panel", "conditional_prefix", "family_fill",
                           "conditional_refill", "evaluate", "summarize"],
    "allowed_accounts": {"tables_full": 64.0, "tables_partial": 64.0,
                         "prefix_generation": 64.0, "tokens_input": 100000.0,
                         "tokens_output": 200000.0, "confirm_reserved": 0.0},
    "issued_by": "lead",
    "issued_at_utc": "2026-09-18T00:00:00Z",
}


def _start(tmp_path, *, name, input_dir=None, archive_in=None):
    return search.av_start_iteration(
        tmp_path / name,
        archive_in=(archive_in if archive_in is not None else {
            "source": "explicit", "path": str(Path(input_dir) / "av-archive.json")}),
        authorization=AUTH, panel_seed=SEED)


def test_p16_s1_intact_input_keeps_being_consumed(tmp_path):
    """对照（绿）：完整未变输入继续正常消费（修复不能变成一律拒绝）。"""

    input_dir = _write_input_dir(tmp_path / "chain" / "iter-01" / "archive")
    state = _start(tmp_path, name="s1-intact", input_dir=input_dir)
    verdict = search.av_archive_input_verify(state)
    assert verdict["ok"] is True and verdict["status"] == "matched"
    previous = search._av_previous_archive(state, Path(state["iter_dir"]).parent)
    assert sorted(previous["entries"]) == ["c0", "c1"]
    assert state["plan"]["archive_in"]["content_identity"]["branch"] == "frozen"


def test_p16_s1_original_drift_is_refused_without_new_evaluation_or_commit(tmp_path):
    """① 原文件漂移：拒绝恢复，且**没有新增评价或提交**。"""

    input_dir = _write_input_dir(tmp_path / "chain" / "iter-01" / "archive")
    run_root = tmp_path / "s1-drift"
    state = _start(tmp_path, name="s1-drift", input_dir=input_dir)
    state_path = Path(state["iter_dir"]) / "state.json"
    changed = json.loads((input_dir / "av-archive.json").read_text(encoding="utf-8"))
    changed["entries"]["c9"] = {"candidate_id": "c9"}
    (input_dir / "av-archive.json").write_text(json.dumps(changed), encoding="utf-8")
    reloaded = search.av_state_load(state_path)
    verdict = search.av_archive_input_verify(reloaded)
    assert verdict["ok"] is False and verdict["status"] == "drift"
    assert verdict["stop_reason"] == search.AV_ARCHIVE_INPUT_DRIFT_STOP_REASON
    result = search.av_iteration_advance(state_path, run_root)
    assert result["terminal"] == "INPUT_GAP"
    assert search.av_state_load(state_path)["stop_reason"] == \
        search.AV_ARCHIVE_INPUT_DRIFT_STOP_REASON
    assert not list(run_root.rglob("evaluation.json")), "拒绝后不得新增评价产物"
    assert search.av_iteration_advance(state_path, run_root)["terminal"] == "INPUT_GAP"


def test_p16_s1_snapshot_rewrite_is_refused_even_when_original_is_intact(tmp_path):
    """② 快照改写（原档案不动）：核验拒绝，且消费者**读不到**被改写的内容。"""

    input_dir = _write_input_dir(tmp_path / "chain" / "iter-01" / "archive")
    run_root = tmp_path / "s1-snapshot"
    state = _start(tmp_path, name="s1-snapshot", input_dir=input_dir)
    identity = state["plan"]["archive_in"]["content_identity"]
    artifact = [item for item in identity["artifacts"] if item["kind"] == "archive"][0]
    snapshot = Path(artifact["snapshot"])
    snapshot.write_text(json.dumps({"entries": {"WRONG": {}}, "slots": {}}),
                        encoding="utf-8")
    verdict = search.av_archive_input_verify(state)
    assert verdict["ok"] is False and verdict["status"] == "snapshot_mismatch", verdict
    assert verdict["stop_reason"] == search.AV_ARCHIVE_INPUT_SNAPSHOT_MISMATCH_STOP_REASON
    assert verdict["problems"][0]["kind"] == "archive"
    with pytest.raises(search.ArchiveInputDrift) as failure:
        search._av_previous_archive(state, run_root)
    assert search.AV_ARCHIVE_INPUT_SNAPSHOT_MISMATCH_STOP_REASON in str(failure.value)
    # 恢复入口同样在**执行与提交之前**停止。
    result = search.av_iteration_advance(Path(state["iter_dir"]) / "state.json", run_root)
    assert result["terminal"] == "INPUT_GAP"
    assert not list(run_root.rglob("evaluation.json"))


def test_p16_s1_snapshot_deletion_is_refused(tmp_path):
    """③ 快照删除：核验拒绝 + 消费拒绝（不许回退按路径重读原文件）。"""

    input_dir = _write_input_dir(tmp_path / "chain" / "iter-01" / "archive")
    run_root = tmp_path / "s1-deleted"
    state = _start(tmp_path, name="s1-deleted", input_dir=input_dir)
    identity = state["plan"]["archive_in"]["content_identity"]
    artifact = [item for item in identity["artifacts"] if item["kind"] == "archive"][0]
    Path(artifact["snapshot"]).unlink()
    verdict = search.av_archive_input_verify(state)
    assert verdict["ok"] is False and verdict["status"] == "snapshot_missing", verdict
    assert verdict["stop_reason"] == search.AV_ARCHIVE_INPUT_SNAPSHOT_MISSING_STOP_REASON
    with pytest.raises(search.ArchiveInputDrift) as failure:
        search._av_previous_archive(state, run_root)
    assert search.AV_ARCHIVE_INPUT_SNAPSHOT_MISSING_STOP_REASON in str(failure.value)


def test_p16_s1_freeze_write_failure_stops_before_execution(tmp_path, monkeypatch):
    """④ 冻结写入失败：开轮即 ok=False + 具名停因；推进入口不再执行任何一步。"""

    input_dir = _write_input_dir(tmp_path / "chain" / "iter-01" / "archive")
    run_root = tmp_path / "s1-freeze"
    real_write = search.av_atomic_write_bytes

    def denied(path, data):
        if str(path).endswith(".snapshot"):
            raise OSError("synthetic snapshot write failure")
        return real_write(path, data)

    monkeypatch.setattr(search, "av_atomic_write_bytes", denied, raising=True)
    state = _start(tmp_path, name="s1-freeze", input_dir=input_dir)
    archive_input = state["archive_input"]
    assert archive_input["ok"] is False
    assert archive_input["status"] == "freeze_failed"
    assert archive_input["stop_reason"] == \
        search.AV_ARCHIVE_INPUT_FREEZE_FAILED_STOP_REASON
    assert state["stop_reason"] == search.AV_ARCHIVE_INPUT_FREEZE_FAILED_STOP_REASON
    assert "content_identity" not in (state["plan"]["archive_in"] or {})
    monkeypatch.undo()
    result = search.av_iteration_advance(Path(state["iter_dir"]) / "state.json", run_root)
    assert result["terminal"] == "INPUT_GAP", result
    assert not list(run_root.rglob("evaluation.json")), "冻结失败后不得新增评价"
    # 恢复入口的核验与开轮结论一致：身份缺失即拒绝（不是 ok=True 的 unregistered）。
    verdict = search.av_archive_input_verify(search.av_state_load(
        Path(state["iter_dir"]) / "state.json"))
    assert verdict["ok"] is False
    assert verdict["stop_reason"] == \
        search.AV_ARCHIVE_INPUT_IDENTITY_MISSING_STOP_REASON


def test_p16_s1_identity_file_write_failure_stops(tmp_path, monkeypatch):
    """④b 身份件（必需冻结件）写失败：同样具名停止。"""

    input_dir = _write_input_dir(tmp_path / "chain" / "iter-01" / "archive")
    real_json = search.av_atomic_write_json

    def denied(path, payload):
        if str(path).endswith("archive-input-identity.json"):
            raise OSError("synthetic identity write failure")
        return real_json(path, payload)

    monkeypatch.setattr(search, "av_atomic_write_json", denied, raising=True)
    state = _start(tmp_path, name="s1-identity-write", input_dir=input_dir)
    assert state["archive_input"]["ok"] is False
    assert state["archive_input"]["stop_reason"] == \
        search.AV_ARCHIVE_INPUT_FREEZE_FAILED_STOP_REASON


def test_p16_s1_unregistered_and_empty_archive_take_separate_branches(tmp_path):
    """⑤ 未接线（unspecified）拒绝；空档案新运行与显式旧夹具分支各自放行。"""

    # 未接线旧调用路径：开轮记 identity_missing，恢复入口拒绝。
    state = search.av_start_iteration(tmp_path / "s1-unspecified", authorization=AUTH,
                                      panel_seed=SEED)
    assert state["plan"]["archive_in"]["source"] == "unspecified"
    verdict = search.av_archive_input_verify(state)
    assert verdict["ok"] is False and verdict["status"] == "identity_missing"
    assert verdict["stop_reason"] == \
        search.AV_ARCHIVE_INPUT_IDENTITY_MISSING_STOP_REASON
    # 空档案新运行：显式分支放行（无输入数据可核，属合法新运行）。
    empty = {"source": "empty", "path": None, "entries": 0, "slots": {},
             "history_count": 0}
    empty_state = search.av_start_iteration(tmp_path / "s1-empty",
                                            archive_in=empty, authorization=AUTH,
                                            panel_seed=SEED)
    empty_verdict = search.av_archive_input_verify(empty_state)
    assert empty_verdict["ok"] is True
    assert empty_verdict["status"] == "empty_archive_new_run"
    # 显式兼容的旧夹具（状态里写明 legacy_compat_unregistered）才放行。
    legacy = {"source": "legacy_fixture", "path": None,
              search.AV_ARCHIVE_INPUT_LEGACY_COMPAT_KEY: True}
    legacy_state = search.av_start_iteration(tmp_path / "s1-legacy",
                                             archive_in=legacy, authorization=AUTH,
                                             panel_seed=SEED)
    legacy_verdict = search.av_archive_input_verify(legacy_state)
    assert legacy_verdict["ok"] is True
    assert legacy_verdict["status"] == "unregistered_explicit_legacy_compat"
    # 但没有显式标记的旧状态一律拒绝（不以 unregistered 普遍放行）。
    unmarked = {"plan": {"archive_in": {"source": "legacy_fixture", "path": None}}}
    assert search.av_archive_input_verify(unmarked)["ok"] is False


# ===========================================================================
# C1 · 完整根身份覆盖
# ===========================================================================


def _descriptor(sub="branch_open", mix="H", index=1, seed=SEED):
    return search.av_family_root_descriptor(
        prefix_source="v2_behavior", sub_scenario=sub, opponent_mix=mix,
        panel_seed=seed, root_index=index)


def _core_row(sub="branch_open", mix="H", index=1, seed=SEED):
    descriptor = _descriptor(sub, mix, index, seed)
    row = {"root_id": descriptor["root_id"], "sub_scenario": sub, "opponent_mix": mix,
           "root_index": index, "panel_seed": seed,
           "root_seed": descriptor["root_seed"], "generator": descriptor["generator"]}
    row["key"] = search._av_family_core_key(row)
    return row


def _product(run_root: Path, name: str, *, candidate_id=CANDIDATE, descriptor=None,
             root_seed=None, panel_seed=None, generator=None, seat=None,
             ok=True, arms=None, arms_state="complete", panel_extra=None):
    """落一份评价产物（完整身份形状；各维度可按用例改写）。"""

    descriptor = dict(descriptor or _descriptor())
    sample = {
        "scenario": descriptor["sub_scenario"], "opponent_mix": descriptor["opponent_mix"],
        "source_root_id": descriptor["root_id"],
        "root_index": descriptor["root_index"],
        "root_seed": (int(root_seed) if root_seed is not None
                      else int(descriptor["root_seed"])),
        "root_descriptor": dict(descriptor),
        "arms": arms if arms is not None else {
            "baseline": {"status": arms_state, "usable": arms_state == "complete",
                         "candidate_id": search.AV_BASELINE_ID},
            "candidate": {"status": arms_state, "usable": arms_state == "complete",
                          "candidate_id": candidate_id}},
    }
    if seat is not None:
        sample["focal_anchor_seat"] = int(seat)
    panel = {"predicate": descriptor["sub_scenario"], "focal_seat": seat,
             "panel_seed": int(panel_seed if panel_seed is not None
                               else descriptor["panel_seed"]),
             "generator": generator or descriptor["generator"]}
    if panel_extra:
        panel.update(panel_extra)
    path = run_root / "iterations" / "iter-02" / "family" / name / "evaluation.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "ok": bool(ok), "identity": {"candidate_id": candidate_id,
                                     "opponent_mix": descriptor["opponent_mix"],
                                     "evaluation_id": "eval-{0}".format(name)},
        "panel": panel, "samples": [sample],
        "execution_kind": "real_runtime", "runtime_kind": "real_simulation_engine",
        "selection_eligible": True}), encoding="utf-8")
    return path


def _coverage(core_rows, *, products, entry=None, candidate_id=CANDIDATE):
    return search.av_family_core_coverage(
        core_rows=core_rows, entry=entry, candidate_id=candidate_id,
        products=products)


def test_p16_c1_same_index_different_seed_and_root_id_do_not_cover(tmp_path):
    """同序号不同面板种子 / 不同根 ID：**不得覆盖**（复审反例：2/2 边覆盖 → 0/2）。"""

    core = [_core_row()]
    wrong_seed_root = _descriptor(seed=20260917)
    _product(tmp_path, "seed-20260917", descriptor=wrong_seed_root)
    products = search._av_family_evaluation_products(tmp_path)
    coverage = _coverage(core, products=products)
    assert coverage["n_edges"] == 2
    assert coverage["n_edges_covered"] == 0, coverage["keys"]
    assert coverage["keys"][0]["covered"] is False
    assert coverage["missing_tokens"] == ["branch_open|H|{0}".format(core[0]["root_id"])]
    rejected = coverage["keys"][0]["arms"]["baseline"]["rejected_products"]
    assert rejected and "来源根标识不符" in rejected[0]["reason"], rejected
    # 正确同根：可复用、不重复收费（对照，同一形状的产物换成正确根身份）。
    right_root = tmp_path / "right"
    _product(right_root, "right-root", descriptor=_descriptor())
    right_products = search._av_family_evaluation_products(right_root)
    right = _coverage(core, products=right_products)
    assert right["n_edges_covered"] == 2 and right["missing_tokens"] == []
    arms = right["keys"][0]["arms"]["baseline"]
    assert arms["basis"].startswith("family_evaluation_product:full_root_identity")
    assert arms["identity_basis"] == ["v2_root_identity"]


def test_p16_c1_same_root_id_different_actual_seed_does_not_cover(tmp_path):
    """同根 ID 但**实际种子**不同（不是同一座牌山）：不得覆盖。"""

    core = [_core_row()]
    wrong_seed = int(_descriptor()["root_seed"]) + 1
    # 产物**内部自洽**（描述符与样本一致），只是实际种子与需求根不同：这才是
    # "同一根 ID、不同牌山"的形态（不是自报矛盾）。
    _product(tmp_path, "wrong-seed",
             descriptor=dict(_descriptor(), root_seed=wrong_seed),
             root_seed=wrong_seed)
    products = search._av_family_evaluation_products(tmp_path)
    coverage = _coverage(core, products=products)
    assert coverage["n_edges_covered"] == 0
    reasons = [item["reason"] for item in
               coverage["keys"][0]["arms"]["candidate"]["rejected_products"]]
    assert any("实际种子不符" in reason for reason in reasons), reasons


def test_p16_c1_different_generator_does_not_cover(tmp_path):
    """不同生成器（身份维度之一）：不得覆盖。"""

    core = [_core_row()]
    fixture_descriptor = search.av_family_root_descriptor(
        prefix_source="scripted_fixture", sub_scenario="branch_open",
        opponent_mix="H", panel_seed=SEED, root_index=1)
    assert fixture_descriptor["root_id"] != core[0]["root_id"]
    _product(tmp_path, "fixture-generator", descriptor=fixture_descriptor)
    products = search._av_family_evaluation_products(tmp_path)
    coverage = _coverage(core, products=products)
    assert coverage["n_edges_covered"] == 0
    reasons = [item["reason"] for item in
               coverage["keys"][0]["arms"]["baseline"]["rejected_products"]]
    assert any("来源根标识不符" in reason for reason in reasons), reasons


def test_p16_c1_declared_identity_contradictions_and_admission_are_refused(tmp_path):
    """产物自报身份与来源根身份不符、产物未准入、缺来源根 ID：均不覆盖。"""

    core = [_core_row()]
    # ① 面板块自报生成器与根身份不符。
    _product(tmp_path / "gen", "panel-generator-mismatch",
             generator="scripted-prefix-fixture-v1")
    products = search._av_family_evaluation_products(tmp_path / "gen")
    coverage = _coverage(core, products=products)
    assert coverage["n_edges_covered"] == 0
    reasons = [item["reason"] for item in
               coverage["keys"][0]["arms"]["baseline"]["rejected_products"]]
    assert any("生成器" in reason and "不符" in reason for reason in reasons), reasons
    # ② 产物未被准入（ok=False）。
    _product(tmp_path / "notok", "not-admitted", ok=False)
    products = search._av_family_evaluation_products(tmp_path / "notok")
    coverage = _coverage(core, products=products)
    assert coverage["n_edges_covered"] == 0
    reasons = [item["reason"] for item in
               coverage["keys"][0]["arms"]["baseline"]["rejected_products"]]
    assert any("未被准入" in reason for reason in reasons), reasons
    # ③ 缺来源根 ID：不得用根序号兜底。
    _product(tmp_path / "noroot", "missing-root-id", descriptor=_descriptor())
    path = tmp_path / "noroot" / "iterations" / "iter-02" / "family" / \
        "missing-root-id" / "evaluation.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["samples"][0].pop("source_root_id")
    payload["samples"][0].pop("root_descriptor")
    path.write_text(json.dumps(payload), encoding="utf-8")
    products = search._av_family_evaluation_products(tmp_path / "noroot")
    coverage = _coverage(core, products=products)
    assert coverage["n_edges_covered"] == 0
    reasons = [item["reason"] for item in
               coverage["keys"][0]["arms"]["baseline"]["rejected_products"]]
    assert any("缺来源根标识" in reason for reason in reasons), reasons


def test_p16_c1_seat_and_arm_dimensions_are_checked(tmp_path):
    """座位不符不得覆盖；臂未齐备不得覆盖；未自报座位按通道契约具名接受。"""

    core = [_core_row()]
    # ① 座位不符（家族通道契约焦点座位 = 0）。
    _product(tmp_path / "seat", "wrong-seat", seat=1)
    products = search._av_family_evaluation_products(tmp_path / "seat")
    coverage = _coverage(core, products=products)
    assert coverage["n_edges_covered"] == 0
    reasons = [item["reason"] for item in
               coverage["keys"][0]["arms"]["baseline"]["rejected_products"]]
    assert any("座位不符" in reason for reason in reasons), reasons
    # ② 臂未齐备。
    _product(tmp_path / "arms", "one-arm-invalid", arms_state="invalid")
    products = search._av_family_evaluation_products(tmp_path / "arms")
    coverage = _coverage(core, products=products)
    assert coverage["n_edges_covered"] == 0
    reasons = [item["reason"] for item in
               coverage["keys"][0]["arms"]["baseline"]["rejected_products"]]
    assert any("两臂未齐备" in reason for reason in reasons), reasons
    # ③ 臂自报候选身份不符（基线臂声明成别的候选）。
    _product(tmp_path / "armcand", "arm-candidate-mismatch",
             arms={"baseline": {"status": "complete", "usable": True,
                                "candidate_id": "someone-else"},
                   "candidate": {"status": "complete", "usable": True,
                                 "candidate_id": CANDIDATE}})
    products = search._av_family_evaluation_products(tmp_path / "armcand")
    coverage = _coverage(core, products=products)
    # 只拒绝**声明了错候选身份**的那条臂（基线臂），候选臂照常覆盖（逐臂分列）。
    assert coverage["n_edges_covered"] == 1, coverage["keys"]
    arms = coverage["keys"][0]["arms"]
    assert arms["candidate"]["covered"] is True
    assert arms["baseline"]["covered"] is False
    reasons = [item["reason"] for item in arms["baseline"]["rejected_products"]]
    assert any("臂自报候选身份不符" in reason for reason in reasons), reasons
    # ④ 未自报座位：按家族通道契约（焦点座位 0）接受并在 basis 里具名。
    _product(tmp_path / "noseat", "no-seat-declared")
    products = search._av_family_evaluation_products(tmp_path / "noseat")
    coverage = _coverage(core, products=products)
    assert coverage["n_edges_covered"] == 2
    arms = coverage["keys"][0]["arms"]["baseline"]
    assert arms["seat_bases"] == ["family_contract_anchor_seat"], arms


def test_p16_c1_reevaluation_obligations_no_longer_waived_by_wrong_root(tmp_path):
    """复审反例全链：只给同序号不同种子的产物 ⇒ pending=1、covered=0（不再免除重评）。"""

    core = [_core_row()]
    _product(tmp_path, "wrong-root", descriptor=_descriptor(seed=20260917))
    products = search._av_family_evaluation_products(tmp_path)
    state = {
        "identity": {"candidate_id": CANDIDATE},
        "plan": {"prefix_source": "v2_behavior", "panel_seed": SEED,
                 "family_refresh": [{
                     "channel": CHANNEL, "sub_scenario": "branch_open",
                     "opponent_mix": "H",
                     "panel_seed": SEED, "root_index": 1, "seats_per_root": 1,
                     "intent": "reevaluate_registered_root",
                     "purpose": "common_root_comparison",
                     "source": "plan.family_reevaluation"}]},
        "family_refresh_resolved": {"resolved": [{
            "root_id": core[0]["root_id"], "sub_scenario": "branch_open",
            "opponent_mix": "H", "panel_seed": SEED, "root_index": 1,
            "root_seed": core[0]["root_seed"],
            "intent": "reevaluate_registered_root",
            "witness": {"status": "hit"}}]},
        "archive": {"seats": {}},
    }
    registry = {"cells": {"branch_open|H|{0}".format(core[0]["root_id"]): dict(core[0])}}
    obligations = search.av_family_reevaluation_obligations(
        state=state, run_root=tmp_path, registry=registry, channel=CHANNEL,
        products=products, entries={})
    assert obligations["declared"] == 1 and obligations["resolved"] == 1
    assert len(obligations["obligations"]) == 1, obligations
    assert obligations["covered"] == [], obligations["covered"]
    assert obligations["obligations"][0]["status"] == "pending"
    # 对照：把产物换成正确根身份 ⇒ 义务被免除（covered=1、pending=0，不重复收费）。
    right_root = tmp_path / "right2"
    _product(right_root, "right", descriptor=_descriptor())
    right_products = search._av_family_evaluation_products(right_root)
    covered = search.av_family_reevaluation_obligations(
        state=state, run_root=right_root, registry=registry, channel=CHANNEL,
        products=right_products, entries={})
    assert covered["obligations"] == []
    assert len(covered["covered"]) == 1


def test_p16_c1_record_fallback_requires_full_root_identity_key(tmp_path):
    """记录级回退的可信条件：挂在完整根身份键上 + 自报身份无冲突。"""

    core = [_core_row()]
    cell_key = "{0}|{1}".format("H", core[0]["root_id"])
    usable = {"d_point": 1.0, "d_low": 0.0, "d_high": 2.0, "unknown": False,
              "opponent_mix": "H"}
    # ① 合格记录挂在完整根身份键上 ⇒ 覆盖（记录级回退，basis 具名）。
    entry = {"family_evaluations": {"branch_open": {cell_key: dict(usable)}}}
    coverage = _coverage(core, products=[], entry=entry)
    assert coverage["n_edges_covered"] == 2
    assert coverage["keys"][0]["arms"]["baseline"]["basis"].startswith(
        "paired_archive_record")
    # ② 记录自报**别的根**（身份冲突）⇒ 不作为证据。
    conflicting = dict(usable, root_id=search.av_family_root_descriptor(
        prefix_source="v2_behavior", sub_scenario="branch_open", opponent_mix="H",
        panel_seed=20260917, root_index=1)["root_id"])
    entry = {"family_evaluations": {"branch_open": {cell_key: conflicting}}}
    coverage = _coverage(core, products=[], entry=entry)
    assert coverage["n_edges_covered"] == 0
    assert coverage["keys"][0]["records_identity_conflicts"], coverage["keys"][0]
    # ③ 记录自报种子不符 ⇒ 同样不作证据。
    entry = {"family_evaluations": {"branch_open": {
        cell_key: dict(usable, root_seed=int(core[0]["root_seed"]) + 7)}}}
    coverage = _coverage(core, products=[], entry=entry)
    assert coverage["n_edges_covered"] == 0


# ===========================================================================
# C5 · 冻结核心根清单
# ===========================================================================


def _partial_registry(*, indexes=(0,), sub="branch_open", mix="H"):
    """**部分视图**：只有一格（run7 首轮冻结出 1 根时就是这个形状）。"""

    roots = [_descriptor(sub, mix, index)["root_id"] for index in indexes]
    return {"cells_by_side_mix": {"{0}|{1}".format(sub, mix): roots},
            "roots": sorted(roots)}


def _complete_registry(*, indexes=(1, 2), panel_seed=SEED):
    """**完整核心矩阵视图**：branch_open/branch_cost × H/M × 2 根 = 4 格 / 8 根。"""

    cells = {}
    for sub in ("branch_open", "branch_cost"):
        for mix in ("H", "M"):
            cells["{0}|{1}".format(sub, mix)] = [
                _descriptor(sub, mix, index, panel_seed)["root_id"]
                for index in indexes]
    return {"cells_by_side_mix": cells,
            "roots": sorted({root for values in cells.values() for root in values})}


def test_p16_fu_complete_matrix_freezes_eight_roots_then_stays_read_only(tmp_path):
    """完整矩阵 ⇒ 首次冻结 **8 根**（4 格 × 2）；此后同一视图只读、不再改写。"""

    freeze_path = tmp_path / "archive" / "family-core-roots.json"
    registry = _complete_registry()
    first = search.av_family_core_root_list(channel=CHANNEL, registry=registry,
                                            freeze_path=freeze_path)
    assert first["created"] is True and first["source"] == "derived"
    assert first["n_roots"] == 8, first
    assert first["view_complete"] is True and first["deferred"] is None
    assert freeze_path.is_file() and first["frozen_at_utc"]
    assert {row["sub_scenario"] for row in first["roots"]} == {"branch_open",
                                                               "branch_cost"}
    original = freeze_path.read_bytes()
    again = search.av_family_core_root_list(channel=CHANNEL, registry=registry,
                                            freeze_path=freeze_path)
    assert again["created"] is False and again["source"] == "frozen"
    assert again["n_roots"] == 8 and again["conflicts"] == []
    assert freeze_path.read_bytes() == original, "运行中不得改写既有冻结件"


def test_p16_fu_partial_view_never_freezes_a_single_root(tmp_path):
    """部分视图首次调用 ⇒ **不得**冻结出 1 根（run7 形态）：不落盘 + 具名 deferred。"""

    freeze_path = tmp_path / "archive" / "family-core-roots.json"
    partial = search.av_family_core_root_list(
        channel=CHANNEL, registry=_partial_registry(), freeze_path=freeze_path)
    assert not freeze_path.exists(), "部分视图不得冻结需求集合"
    assert partial["created"] is False and partial["source"] == "derived"
    assert partial["view_complete"] is False
    assert partial["deferred"]["code"] == \
        search.AV_FAMILY_CORE_LIST_DEFERRED_VIEW_CODE
    assert partial["deferred"]["missing_cells"], partial["deferred"]
    assert partial["n_roots"] == 1, partial["roots"]
    # 补齐后再冻结：同一路径上第二次调用（完整视图）正常创建 8 根。
    complete = search.av_family_core_root_list(channel=CHANNEL,
                                               registry=_complete_registry(),
                                               freeze_path=freeze_path)
    assert complete["created"] is True and complete["n_roots"] == 8
    assert freeze_path.is_file()


def test_p16_fu_inconsistent_frozen_list_is_refused_not_overwritten(tmp_path):
    """已存在**不一致**冻结件 ⇒ 具名拒绝（要求新运行身份），绝不覆盖重写。"""

    freeze_path = tmp_path / "archive" / "family-core-roots.json"
    # 先造一个"run7 形状"的合法但只有 1 根的冻结件（直接写盘，模拟既有 run）。
    frozen_payload = {"schema": search.AV_FAMILY_CORE_LIST_SCHEMA, "channel": CHANNEL,
                      "frozen_at_utc": "2026-09-18T17:22:36Z",
                      "roots": [dict(_core_row(index=0))]}
    freeze_path.parent.mkdir(parents=True, exist_ok=True)
    freeze_path.write_text(json.dumps(frozen_payload, ensure_ascii=False),
                           encoding="utf-8")
    before = freeze_path.read_bytes()
    with pytest.raises(search.FamilyCoreListRefused) as failure:
        search.av_family_core_root_list(channel=CHANNEL, registry=_complete_registry(),
                                        freeze_path=freeze_path)
    assert failure.value.stop_reason == \
        search.AV_FAMILY_CORE_LIST_CONFLICT_STOP_REASON
    assert failure.value.problems[0]["code"] == "frozen_core_list_conflicts_with_derived"
    assert failure.value.problems[0]["derived_n_roots"] == 8
    assert failure.value.problems[0]["frozen_n_roots"] == 1
    assert freeze_path.read_bytes() == before, "原件必须逐字保留（不得覆盖重写）"
    # 对照：**部分视图**读同一份冻结件不判冲突（推导集本就不全）——只记差额，
    # 这样补根轮中途不会因为"台账还没登记齐"而误停。
    partial = search.av_family_core_root_list(
        channel=CHANNEL, registry=_partial_registry(indexes=(1,)),
        freeze_path=freeze_path)
    assert partial["source"] == "frozen" and partial["n_roots"] == 1
    assert partial["view_complete"] is False
    assert partial["conflicts"] and partial["conflicts"][0]["code"] == \
        "frozen_core_list_incomplete_both_sides"
    assert partial["requirement_complete"] is False


def test_p16_c5_bad_json_is_refused_and_original_preserved(tmp_path):
    """坏 JSON：具名停止 + **保留原件**（旧实现覆盖成当前推导清单）。"""

    freeze_path = tmp_path / "archive" / "family-core-roots.json"
    freeze_path.parent.mkdir(parents=True, exist_ok=True)
    freeze_path.write_text("{not json at all", encoding="utf-8")
    before = freeze_path.read_bytes()
    with pytest.raises(search.FamilyCoreListRefused) as failure:
        search.av_family_core_root_list(channel=CHANNEL, registry=_complete_registry(),
                                        freeze_path=freeze_path)
    assert failure.value.stop_reason == search.AV_FAMILY_CORE_LIST_INVALID_STOP_REASON
    assert failure.value.problems[0]["code"] == "frozen_core_list_invalid_json"
    assert freeze_path.read_bytes() == before, "原件必须保留"


def test_p16_c5_wrong_schema_and_channel_are_refused(tmp_path):
    """错 schema / 错 channel：具名停止并保留原件。"""

    for name, payload, code in (
            ("schema", {"schema": "something-else", "channel": CHANNEL, "roots": []},
             "frozen_core_list_schema_mismatch"),
            ("channel", {"schema": search.AV_FAMILY_CORE_LIST_SCHEMA,
                         "channel": "chain", "roots": []},
             "frozen_core_list_channel_mismatch")):
        freeze_path = tmp_path / name / "family-core-roots.json"
        freeze_path.parent.mkdir(parents=True, exist_ok=True)
        freeze_path.write_text(json.dumps(payload), encoding="utf-8")
        before = freeze_path.read_bytes()
        with pytest.raises(search.FamilyCoreListRefused) as failure:
            search.av_family_core_root_list(channel=CHANNEL,
                                            registry=_complete_registry(),
                                            freeze_path=freeze_path)
        assert failure.value.problems[0]["code"] == code, failure.value.problems
        assert failure.value.stop_reason == search.AV_FAMILY_CORE_LIST_INVALID_STOP_REASON
        assert freeze_path.read_bytes() == before


def test_p16_c5_write_failure_stops_and_leaves_no_list(tmp_path, monkeypatch):
    """首次冻结写入失败：具名停止（不继续），且不留下半截文件。"""

    freeze_path = tmp_path / "archive" / "family-core-roots.json"
    real_write = search.av_atomic_write_json

    def denied(path, payload):
        raise OSError("synthetic freeze write failure")

    monkeypatch.setattr(search, "av_atomic_write_json", denied, raising=True)
    with pytest.raises(search.FamilyCoreListRefused) as failure:
        search.av_family_core_root_list(channel=CHANNEL, registry=_complete_registry(),
                                        freeze_path=freeze_path)
    assert failure.value.stop_reason == \
        search.AV_FAMILY_CORE_LIST_WRITE_FAILED_STOP_REASON
    assert not freeze_path.exists()
    monkeypatch.setattr(search, "av_atomic_write_json", real_write, raising=True)
    # 对照：修复后同一次调用正常创建（写失败不是"这回没有清单"）。
    ok = search.av_family_core_root_list(channel=CHANNEL,
                                         registry=_complete_registry(),
                                         freeze_path=freeze_path)
    assert ok["created"] is True and freeze_path.is_file()


def test_p16_c5_unreadable_file_is_refused(tmp_path):
    """既有文件不可读（目录占位）：具名停止，不按当前推导重建。"""

    freeze_path = tmp_path / "archive" / "family-core-roots.json"
    freeze_path.mkdir(parents=True)          # 同名目录：读必失败
    with pytest.raises(search.FamilyCoreListRefused) as failure:
        search.av_family_core_root_list(channel=CHANNEL,
                                        registry=_complete_registry(),
                                        freeze_path=freeze_path)
    assert failure.value.stop_reason == search.AV_FAMILY_CORE_LIST_INVALID_STOP_REASON
    assert failure.value.problems[0]["code"] == "frozen_core_list_unreadable"
    assert freeze_path.is_dir(), "原件（同名目录）必须保留"


# ===========================================================================
# P16-FU · run7 实测两处生产侧不一致
# ===========================================================================


class _FuLedger:
    """最小账本替身（只读 remaining；补根轮在本用例里不真正花桌）。"""

    def remaining(self, account):
        return 64.0

    def reserve(self, **kwargs):
        return dict(kwargs)

    def settle(self, reservation, **kwargs):
        return {}


def test_p16_fu_fill_partial_view_defers_freeze_and_keeps_readings_apart(
        tmp_path, monkeypatch):
    """run7 形态端到端：部分台账视图 ⇒ 不冻结需求集合，读数与完成读数**分开落盘**。"""

    run_root = tmp_path / "run-fu"
    archive_dir = run_root / "archive"
    archive_dir.mkdir(parents=True)
    partial_root = _descriptor("branch_open", "H", 0)
    (archive_dir / "family-roots.json").write_text(json.dumps({
        "schema": search.AV_FAMILY_ROOTS_SCHEMA,
        "channels": {CHANNEL: {"roots": [{
            "channel": CHANNEL, "sub_scenario": "branch_open", "opponent_mix": "H",
            "root_index": 0, "panel_seed": SEED,
            "root_id": partial_root["root_id"], "root_seed": partial_root["root_seed"],
            "seats_per_root": 1}]}}}), encoding="utf-8")
    (archive_dir / "av-archive.json").write_text(json.dumps({
        "schema": "sitin-action-value-archive/1",
        "entries": {CANDIDATE: {"candidate_id": CANDIDATE}},
        "slots": {CHANNEL: []}}), encoding="utf-8")
    iter_dir = run_root / "iterations" / "iter-01"
    iter_dir.mkdir(parents=True)
    state = {
        "plan": {"prefix_source": "v2_behavior", "panel_seed": SEED,
                 "family_channel": CHANNEL, "family_refresh": []},
        "identity": {"candidate_id": CANDIDATE}, "iter_dir": str(iter_dir),
        "iteration_no": 1, "run_id": "p16-fu", "step_history": [],
        "archive": {"seats": {}}}
    monkeypatch.setattr(search, "_av_commit_family",
                        lambda *a, **k: {"status": "pending",
                                         "phase": "epoch_core_fill",
                                         "missing": {}}, raising=True)
    monkeypatch.setattr(search, "_av_family_fill_items",
                        lambda **k: ([], []), raising=True)
    monkeypatch.setattr(search, "_av_refresh_budget", lambda *a, **k: 64,
                        raising=True)
    search._av_family_fill(state, run_root, _FuLedger(), AUTH)
    # ① 部分视图**不冻结**：run7 的"1 根冻结件"不可能再出现。
    freeze_path = archive_dir / "family-core-roots.json"
    assert not freeze_path.exists(), "部分视图不得冻结需求集合"
    tx = json.loads((iter_dir / "transactions"
                     / search.AV_TX_FILES["family_refresh"]).read_text(encoding="utf-8"))
    row = tx["rounds"][0]
    assert row["core_list"]["source"] == "derived"
    assert row["core_list"]["created"] is False
    assert row["core_list"]["view_complete"] is False
    assert row["core_list"]["deferred"]["code"] == \
        search.AV_FAMILY_CORE_LIST_DEFERRED_VIEW_CODE
    # ② 两个产物名字与语义分开：轮首工作项快照 vs 收口完成读数。
    workitem = json.loads((archive_dir / search.AV_FAMILY_CORE_WORKITEM_FILENAME)
                          .read_text(encoding="utf-8"))
    assert workitem["schema"] == search.AV_FAMILY_CORE_WORKITEM_SCHEMA
    assert workitem["phase"] == "work_item_snapshot"
    assert workitem["is_completion_reading"] is False
    assert "不是完成读数" in workitem["note"]
    completion = json.loads((archive_dir / search.AV_FAMILY_CORE_COVERAGE_FILENAME)
                            .read_text(encoding="utf-8"))
    assert completion["schema"] == search.AV_FAMILY_CORE_COVERAGE_SCHEMA
    assert completion["phase"] == "completion"
    assert completion["is_completion_reading"] is True
    assert completion["rounds"] == len(tx["rounds"])
    assert completion["core_list"]["view_complete"] is False
    in_memory = state["family_fill"]["coverage_completion"]
    assert in_memory["phase"] == "completion" and in_memory["written"] is True


def test_p16_fu_completion_reading_is_recomputed_after_edges_are_evaluated(tmp_path):
    """完成读数**重算**：本轮评价后覆盖上升（不再是轮首那一份快照）。"""

    run_root = tmp_path / "run-fu-recompute"
    archive_dir = run_root / "archive"
    archive_dir.mkdir(parents=True)
    registry = _complete_registry()
    core_list = search.av_family_core_root_list(channel=CHANNEL, registry=registry,
                                                freeze_path=archive_dir
                                                / "family-core-roots.json")
    assert core_list["created"] is True and core_list["n_roots"] == 8
    (archive_dir / "av-archive.json").write_text(json.dumps({
        "schema": "sitin-action-value-archive/1",
        "entries": {CANDIDATE: {"candidate_id": CANDIDATE}},
        "slots": {CHANNEL: []}}), encoding="utf-8")
    state = {"plan": {"prefix_source": "v2_behavior", "panel_seed": SEED},
             "identity": {"candidate_id": CANDIDATE}, "iter_dir": str(run_root),
             "iteration_no": 1, "archive": {"seats": {}}}
    before = search._av_family_coverage_completion(
        state, run_root, CHANNEL, registry=registry, outcome={"missing": {}},
        rounds=[{"round": 1}], attempts=[])
    assert before["written"] is True and before["ok"] is True
    assert before["n_edges_covered_total"] == 0
    # 本轮真实评价落一份产物（正确同根：root001 / branch_open|H）⇒ 完成读数必须跟着变。
    _product(run_root, "fu-evaluated", descriptor=_descriptor())
    after = search._av_family_coverage_completion(
        state, run_root, CHANNEL, registry=registry, outcome={"missing": {}},
        rounds=[{"round": 1}], attempts=[{"status": "completed"}])
    assert after["n_edges_covered_total"] == 2, after
    assert len(after["missing_effective"][CANDIDATE]) < \
        len(before["missing_effective"][CANDIDATE])
    written = json.loads((archive_dir / search.AV_FAMILY_CORE_COVERAGE_FILENAME)
                         .read_text(encoding="utf-8"))
    assert written["n_edges_covered_total"] == 2, "落盘的是**最新**完成读数"
    assert written["attempts"]["by_status"] == {"completed": 1}
    # 冻结件不可用时如实记 ok=False（不沿用上一轮完成读数冒充本轮）。
    bad = search._av_family_coverage_completion(
        state, run_root, CHANNEL, registry=registry, outcome={"missing": {}},
        rounds=[], attempts=[],
        refused=search.FamilyCoreListRefused(
            "synthetic", stop_reason=search.AV_FAMILY_CORE_LIST_CONFLICT_STOP_REASON))
    assert bad["ok"] is False and bad["coverage"] == {}
    assert bad["problems"][0]["code"] == "core_list_unavailable_at_completion"



# ===========================================================================
# P18 配合项 · _av_plan_history 去重键同源 + 事件行 created_at_utc
# ===========================================================================


def _proposal_run_root(root: Path, *, operator_by_iter, run_id="run-p18",
                       created_prefix="2026-09-18T1{0}:00:00Z") -> Path:
    """两个已终态迭代的运行根（事件账本 + 状态投影都在），供提案历史用例使用。"""

    archive_dir = root / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    (archive_dir / "av-archive.json").write_text(json.dumps({
        "schema": "sitin-action-value-archive/1", "entries": {}, "slots": {}}),
        encoding="utf-8")
    for iteration_no, operator in sorted(operator_by_iter.items()):
        iter_dir = root / "iterations" / "iter-{0:02d}".format(iteration_no)
        iter_dir.mkdir(parents=True, exist_ok=True)
        state = {
            "schema": search.AV_ITERATION_STATE_SCHEMA,
            "run_id": "{0}-{1}".format(run_id, iteration_no),
            "iteration_no": iteration_no,
            "iter_dir": str(iter_dir),
            "created_at_utc": created_prefix.format(iteration_no),
            "status": "ITERATION_COMPLETE",
            "stop_reason": "completed",
            "identity": {"candidate_id": "cand-{0}".format(iteration_no)},
            "plan": {"operator": operator.lower(), "parent_candidate_id": "parent-1",
                     "channel": "overall", "family": None,
                     "archive_in": {"proposal_no": iteration_no,
                                    "applied_operator": operator.lower(),
                                    "planned_operator": operator.lower(),
                                    "planned_parent_candidate_id": "parent-1",
                                    "planned_channel": "overall"}},
        }
        (iter_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")
        search.av_proposal_event_record(root, state, status="ITERATION_COMPLETE",
                                        stop_reason="completed")
    return root


def _history_fingerprint(history):
    return [(row["proposal_no"], row["operator"], row["recorded_proposal_no"])
            for row in history]


def test_p18_plan_history_copy_root_same_proposal_numbers_and_operator(tmp_path):
    """同一历史在真实根与**复制后的根**上必须得到同一 proposal_no / 算子（P18）。"""

    real = _proposal_run_root(tmp_path / "real", operator_by_iter={1: "I1", 2: "M1"})
    real_history = search._av_plan_history(real)
    assert len(real_history) == 2, real_history
    assert _history_fingerprint(real_history) == [(1, "I1", 1), (2, "M1", 2)]
    assert real_history[0].get("collapsed_duplicates") is None
    # 复制整个运行根（事件行里的 iter_dir 仍指原路径——这正是缺陷的来源）。
    copy_root = tmp_path / "copies" / "run"
    shutil.copytree(real, copy_root)
    copy_history = search._av_plan_history(copy_root)
    assert _history_fingerprint(copy_history) == _history_fingerprint(real_history)
    assert len(copy_history) == 2, copy_history
    assert copy_history[0]["collapsed_duplicates"], "复制导致的重复登记必须折叠并留档"
    assert {item["folded_source"] for item in
            copy_history[0]["collapsed_duplicates"]} == {"state_projection"}
    # 提案号 = len(history) + 1：副本根上不得再多算一倍（旧实现 4 条 ⇒ 5）。
    assert len(copy_history) + 1 == 3 == len(real_history) + 1
    # 与 P18 的下游判据同源：check_proposal_history 在复制根上不得再报重复。
    check = search.av_archive().check_proposal_history(copy_history)
    assert check["proposals"] == 2, check
    assert not check.get("collapsed_same_proposal"), check


def test_p18_plan_history_identity_helper_matches_archive_module():
    """上游去重口径与 sitin_archive._proposal_identity **逐条一致**（漂移即红）。"""

    upstream = search._av_proposal_identity
    downstream = search.av_archive()._proposal_identity
    rows = [
        {"run_id": "r1", "iteration_no": 3},
        {"run_id": "r1", "recorded_proposal_no": 4},
        {"run_id": "r1", "proposal_no": 5},
        {"iter_dir": "/tmp/x/iter-01"},
        {"proposal_no": 7},
        {},
        {"run_id": "  r2  ", "iteration_no": 2, "recorded_proposal_no": 9},
        {"run_id": "", "iteration_no": 2},
    ]
    for row in rows:
        assert upstream(row) == downstream(row), row


def test_p18_event_rows_carry_created_at_utc_and_order_follows_records(tmp_path):
    """事件行必须带 created_at_utc；混合账本按 (时间, 记录号) 排序、位置号不超前。"""

    root = _proposal_run_root(tmp_path / "mixed", operator_by_iter={1: "I1", 2: "M1"})
    events = [json.loads(line) for line in
              (root / "archive" / search.AV_PROPOSAL_EVENTS_FILENAME)
              .read_text(encoding="utf-8").splitlines() if line.strip()]
    assert events and all(row.get("created_at_utc") for row in events), events
    assert all(row.get("recorded_proposal_no") is None for row in events)
    history = search._av_plan_history(root)
    assert [row["created_at_utc"] for row in history] == [
        "2026-09-18T11:00:00Z", "2026-09-18T12:00:00Z"]
    assert [row["recorded_proposal_no"] for row in history] == [1, 2]
    # 旧产物（事件行缺 created_at_utc）仍按记录号定序，不因缺字段把位置号打乱。
    legacy = json.loads(json.dumps(events[0]))
    legacy.pop("created_at_utc")
    path = root / "archive" / search.AV_PROPOSAL_EVENTS_FILENAME
    path.write_text("\n".join([canonical_line(legacy), canonical_line(events[1])]) + "\n",
                    encoding="utf-8")
    (root / "iterations" / "iter-01" / "state.json").unlink()
    replayed = search._av_plan_history(root)
    assert [row["recorded_proposal_no"] for row in replayed] == [1, 2], replayed


def canonical_line(payload):
    return json.dumps(payload, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))

