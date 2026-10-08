# -*- coding: utf-8 -*-
"""P15 REEVAL-SCHED 定向测试：重评声明是「比较义务」，不是「刷新发现」。

缺陷（run6 实测，证据只读）：计划发出 9 条 intent=reevaluate_registered_root 声明
（在席者 8 个核心根 + 指定旧根），声明**全部见证** ⇒ unmaterialized 为空 ⇒ 迭代不进
pending；又没有新根声明 ⇒ 刷新批为空 ⇒ batch_invalid ⇒ 补根步一轮都不跑 ⇒ 挑战者仍是
0/16 核心根边（缺 8 根 / 16 实例 / 32 桌）。

本测试用**可观测读数**驱动（family_fill.attempts / 逐键边覆盖 / 停因字符串），因此同一份
测试在修复前会因**缺陷本身**变红（不是因缺 API 而报错）。
0 真实桌赛 / 0 模型调用 / 0 网络（评价执行器与合并层都是注入替身）。
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
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import sitin_search as search  # noqa: E402

CHANNEL = "branch"
SEED = 20260916
CHALLENGER = "544f7d353965a90dd3f7bf0073e5a39479c78de0ded857df57498708ad83c49a"
INCUMBENT = "d7a10efcbfd9b30fab7a9fa60c9ed8f296229c2e48cfff2db6f527a536caf980"
CORE = [(sub, mix, index) for sub in ("branch_open", "branch_cost")
        for mix in ("H", "M") for index in (1, 2)]
SPECIFIED_ROOT_ID = ("av-eval-branch_open:branch_open:v2-behavior-prefix-v1:"
                     "H:s20260916:root000")


def _descriptor(sub, mix, index, prefix_source="v2_behavior"):
    return search.av_family_root_descriptor(
        prefix_source=prefix_source, sub_scenario=sub, opponent_mix=mix,
        panel_seed=SEED, root_index=index)


def _plan_rows(*, with_specified_root=True):
    """run6 iter-02 的计划行：8 条带冻结描述符的重评 + 1 条指定旧根。"""

    rows = []
    for sub, mix, index in CORE:
        d = _descriptor(sub, mix, index)
        rows.append({"channel": CHANNEL, "sub_scenario": sub, "opponent_mix": mix,
                     "panel_seed": SEED, "root_index": index, "seats_per_root": 1,
                     "intent": "reevaluate_registered_root",
                     "purpose": "common_root_comparison",
                     "source": "plan.family_reevaluation",
                     "root_id": d["root_id"], "root_seed": d["root_seed"],
                     "generator": d["generator"],
                     "root_identity_schema": d["root_identity_schema"],
                     "seed_derivation": d["seed_derivation"]})
    if with_specified_root:
        rows.append({"channel": CHANNEL, "sub_scenario": "branch_open",
                     "opponent_mix": "H", "panel_seed": SEED, "root_index": None,
                     "seats_per_root": 1,
                     "intent": "reevaluate_registered_root",
                     "purpose": "specified_old_root_reevaluation",
                     "resolve": "iteration_1_conditional_root",
                     "source": "plan.family_refresh"})
    return rows


def _resolved_rows(rows):
    """P11 解析结果：逐字冻结描述符 + witness=hit（声明全部见证）。"""

    out = []
    for row in rows:
        sub, mix = row["sub_scenario"], row["opponent_mix"]
        index = row.get("root_index")
        if index is None:
            descriptor = {"root_id": SPECIFIED_ROOT_ID, "root_index": 0,
                          "root_seed": 66460248753675,
                          "generator": "v2-behavior-prefix-v1",
                          "sub_scenario": sub, "opponent_mix": mix,
                          "panel_seed": SEED,
                          "root_identity_schema": "sitin-root-identity/2",
                          "seed_derivation": "shared-root-v2"}
        else:
            descriptor = _descriptor(sub, mix, index)
        out.append({"channel": CHANNEL, "sub_scenario": sub, "opponent_mix": mix,
                    "panel_seed": SEED, "root_index": descriptor["root_index"],
                    "seats_per_root": 1,
                    "intent": "reevaluate_registered_root",
                    "purpose": row.get("purpose"), "source": row.get("source"),
                    "root_id": descriptor["root_id"],
                    "root_seed": descriptor["root_seed"],
                    "generator": descriptor["generator"],
                    "root_identity_schema": descriptor["root_identity_schema"],
                    "seed_derivation": descriptor["seed_derivation"],
                    "witness": {"status": "hit", "readings": {"frames": 12}}})
    return out


def _build_run_root(tmp_path, *, rows, register_specified_root=True,
                    incumbent_records=True, challenger_records=False):
    """建一个 run6 iter-02 形状的运行目录（档案 / epoch / 根台账 / iter-01 条件结果）。"""

    run_root = Path(tmp_path) / "run-p15"
    archive_dir = run_root / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    roots = []
    for sub, mix, index in CORE:
        d = _descriptor(sub, mix, index)
        roots.append({"channel": CHANNEL, "sub_scenario": sub, "opponent_mix": mix,
                      "panel_seed": SEED, "root_index": index,
                      "root_seed": d["root_seed"], "root_id": d["root_id"],
                      "seats_per_root": 1})
    if register_specified_root:
        roots.append({"channel": CHANNEL, "sub_scenario": "branch_open",
                      "opponent_mix": "H", "panel_seed": SEED, "root_index": 0,
                      "root_seed": 66460248753675, "root_id": SPECIFIED_ROOT_ID,
                      "seats_per_root": 1})
    (archive_dir / "family-roots.json").write_text(json.dumps(
        {"schema": search.AV_FAMILY_ROOTS_SCHEMA,
         "channels": {CHANNEL: {"roots": roots}}}), encoding="utf-8")
    epoch_roots = [{"root_id": row["root_id"], "role": "core",
                    "usage": "development_core",
                    "opponent_mix": row["opponent_mix"],
                    "sub_scenario": row["sub_scenario"]} for row in roots
                   if row["root_index"] != 0]
    (archive_dir / "family-epochs.json").write_text(json.dumps(
        {"schema": search.AV_FAMILY_EPOCHS_SCHEMA,
         "channels": {CHANNEL: {"epoch": 1, "roots": epoch_roots}}}),
        encoding="utf-8")
    entries = {CHALLENGER: {"candidate_id": CHALLENGER, "family_evaluations": {}}}
    if challenger_records:
        fam = {}
        for sub, mix, index in CORE:
            d = _descriptor(sub, mix, index)
            fam.setdefault(sub, {})["{0}|{1}".format(mix, d["root_id"])] = {
                "d_point": 1.0, "d_low": 0.0, "d_high": 2.0, "unknown": False,
                "opponent_mix": mix, "role": "core"}
        entries[CHALLENGER]["family_evaluations"] = fam
    if incumbent_records:
        fam = {}
        for sub, mix, index in CORE:
            d = _descriptor(sub, mix, index)
            fam.setdefault(sub, {})["{0}|{1}".format(mix, d["root_id"])] = {
                "d_point": 1.0, "d_low": 0.0, "d_high": 2.0, "unknown": False,
                "opponent_mix": mix, "role": "core"}
        entries[INCUMBENT] = {"candidate_id": INCUMBENT, "family_evaluations": fam}
    (archive_dir / "av-archive.json").write_text(json.dumps(
        {"schema": "sitin-action-value-archive/1", "entries": entries,
         "slots": {CHANNEL: [INCUMBENT]}}), encoding="utf-8")
    cond = run_root / "iterations" / "iter-01" / "conditional"
    cond.mkdir(parents=True, exist_ok=True)
    (cond / "evaluation.json").write_text(json.dumps({
        "ok": True, "identity": {"candidate_id": INCUMBENT},
        "samples": [{"scenario": "branch_open", "opponent_mix": "H",
                     "root_index": 0, "root_seed": 66460248753675,
                     "source_root_id": SPECIFIED_ROOT_ID}]}), encoding="utf-8")
    return run_root


def _state(run_root, rows, *, iter_name="iter-02", seats=()):
    """迭代状态：默认**不带在席者**（只观察挑战者的义务；在席者另测）。"""
    iter_dir = Path(run_root) / "iterations" / iter_name
    iter_dir.mkdir(parents=True, exist_ok=True)
    return {"plan": {"prefix_source": "v2_behavior", "panel_seed": SEED,
                     "family_channel": CHANNEL, "family_refresh": rows},
            "identity": {"candidate_id": CHALLENGER},
            "family_refresh_resolved": {
                "schema": search.AV_FAMILY_DECLARATION_SCHEMA,
                "channel": CHANNEL, "complete": True, "stop_reason": None,
                "request": rows, "resolved": _resolved_rows(rows), "trace": []},
            "iter_dir": str(iter_dir), "iteration_no": 2, "run_id": "p15",
            "step_history": [],
            "archive": {"seats": {CHANNEL: list(seats)}}}


class _Ledger:
    """假账本：remaining 可配；reserve/settle 记录（不写盘、零真实执行）。"""

    def __init__(self, remaining=64.0):
        self._remaining = {"tables_full": remaining, "prefix_generation": 32.0,
                           "tables_partial": 32.0}
        self.reserved = []
        self.settled = []
        self.reservations = []
        self.superseded = []

    def supersede(self, *, step_id, account, reason=""):
        self.superseded.append({"step_id": step_id, "account": account})

    def remaining(self, account):
        return self._remaining.get(account)

    def reserve(self, *, step_id, account, amount, note=""):
        self.reserved.append({"account": account, "amount": float(amount)})
        return {"step_id": step_id, "account": account, "amount": float(amount)}

    def settle(self, reservation, *, actual, note=""):
        self.settled.append({"account": reservation["account"], "actual": float(actual)})
        return {}


TOKEN = {"authorized": True, "batch": 7, "batch_label": "p15",
         "budgets": {"tables_full": 216, "tables_partial": 128,
                     "prefix_generation": 128, "tokens_input": 0,
                     "tokens_output": 0, "confirm_reserved": 0.0}}


def _harness(monkeypatch, run_root, *, budget=64, commit_outcomes=None):
    """把评价执行器 / 合并层 / 提交入口换成替身，只观察**调度行为**。"""

    calls = {"evaluations": [], "commits": 0}

    def fake_run_evaluation(state, run_root_, ledger, authorization, item, source,
                            factory):
        calls["evaluations"].append(dict(item))
        iter_dir = Path(state["iter_dir"])
        sub, mix = item["sub_scenario"], item["opponent_mix"]
        out = iter_dir / "family" / "{0}-{1}".format(sub, mix)
        out.mkdir(parents=True, exist_ok=True)
        root_index = int(item["root_indexes"][0])
        product = {"ok": True, "identity": {"candidate_id": item["candidate_id"]},
                   "panel": {"tables_full_executed": 2},
                   "samples": [{"scenario": sub, "opponent_mix": mix,
                                "root_index": root_index,
                                "root_seed": int(item["root_seed"]),
                                "source_root_id": item["root_ids"][0],
                                "arms": {
                                    "baseline": {"status": "complete", "usable": True},
                                    "candidate": {"status": "complete", "usable": True}}}]}
        (out / "evaluation.json").write_text(json.dumps(product), encoding="utf-8")
        return {"attempt": {"status": "completed",
                            "candidate_id": item["candidate_id"],
                            "sub_scenario": sub, "opponent_mix": mix,
                            "root_ids": list(item["root_ids"]),
                            "tables_executed": 2, "reuse": None},
                "evaluation": {"samples": product["samples"]}, "instances": {}}

    def fake_merge(state, run_root_, fills):
        report = {}
        archive_path = Path(run_root_) / "archive" / "av-archive.json"
        archive = json.loads(archive_path.read_text(encoding="utf-8"))
        for cid, (item, result) in fills.items():
            entry = archive["entries"].setdefault(
                cid, {"candidate_id": cid, "family_evaluations": {}})
            fam = entry.setdefault("family_evaluations", {})
            bucket = fam.setdefault(item["sub_scenario"], {})
            for root_id in item["root_ids"]:
                bucket["{0}|{1}".format(item["opponent_mix"], root_id)] = {
                    "d_point": 1.0, "d_low": 0.0, "d_high": 2.0, "unknown": False,
                    "opponent_mix": item["opponent_mix"], "role": "core"}
            archive_path.write_text(json.dumps(archive), encoding="utf-8")
            report[cid] = {"roots_added": list(item["root_ids"]), "n_samples": 1}
        return report

    def fake_commit(state, run_root_, *, attempt_refresh, budget=None):
        calls["commits"] += 1
        if commit_outcomes:
            return commit_outcomes[min(calls["commits"] - 1, len(commit_outcomes) - 1)]
        if calls["commits"] == 1:
            return {"status": "kept", "phase": "batch_invalid", "missing": {},
                    "refresh": {"status": "batch_invalid", "seats_kept": True}}
        archive = json.loads((Path(run_root_) / "archive" / "av-archive.json")
                             .read_text(encoding="utf-8"))
        coverage = _coverage_of(Path(run_root_), archive)
        if coverage["missing_tokens"]:
            return {"status": "pending", "phase": "phase1",
                    "missing": {CHALLENGER: coverage["missing_tokens"]}}
        return {"status": "committed", "refresh": {"status": "committed"},
                "epoch_after": 2, "new_epoch": {"epoch": 2, "roots": []},
                "archive": archive, "ranking": []}

    monkeypatch.setattr(search, "_av_family_run_evaluation", fake_run_evaluation,
                        raising=True)
    monkeypatch.setattr(search, "_av_family_merge_fills", fake_merge, raising=True)
    monkeypatch.setattr(search, "_av_commit_family", fake_commit, raising=True)
    monkeypatch.setattr(search, "_av_refresh_budget", lambda *a, **k: budget,
                        raising=True)
    monkeypatch.setattr(search, "_av_refresh_participant_source",
                        lambda *a, **k: {"source": "stub", "sha256": "stub"},
                        raising=True)
    return calls


def _core_rows():
    rows = []
    for sub, mix, index in CORE:
        d = _descriptor(sub, mix, index)
        row = {"root_id": d["root_id"], "sub_scenario": sub, "opponent_mix": mix,
               "root_index": index, "panel_seed": SEED, "root_seed": d["root_seed"]}
        row["key"] = search._av_family_core_key(row)
        rows.append(row)
    return rows


def _coverage_of(run_root, archive):
    products = search._av_family_evaluation_products(Path(run_root))
    return search.av_family_core_coverage(
        core_rows=_core_rows(),
        entry=(archive.get("entries") or {}).get(CHALLENGER),
        candidate_id=CHALLENGER, products=products)


def _coverage(run_root):
    archive = json.loads((Path(run_root) / "archive" / "av-archive.json")
                         .read_text(encoding="utf-8"))
    return _coverage_of(run_root, archive)


def _run(tmp_path, monkeypatch, *, rows=None, budget=64, register_specified_root=True,
         ledger=None, commit_outcomes=None):
    rows = rows if rows is not None else _plan_rows()
    run_root = _build_run_root(tmp_path, rows=rows,
                              register_specified_root=register_specified_root)
    state = _state(run_root, rows)
    calls = _harness(monkeypatch, run_root, budget=budget,
                     commit_outcomes=commit_outcomes)
    ledger = ledger if ledger is not None else _Ledger(64.0)
    verdict = search._av_family_fill(state, run_root, ledger, TOKEN)
    return state, run_root, verdict, calls, ledger


def test_p15_reevaluation_declarations_are_scheduled_not_skipped(tmp_path, monkeypatch):
    """核心：声明全部见证（无新根可发现）时，重评义务仍被排评价（run6 缺陷）。"""

    state, run_root, verdict, calls, ledger = _run(tmp_path, monkeypatch)
    # ① 评价真的跑了：9 条声明各排一次评价（8 个核心根 + 指定旧根 root000）。
    assert len(calls["evaluations"]) == 9, [item["token"] for item in calls["evaluations"]]
    tokens = sorted(item["token"] for item in calls["evaluations"])
    assert len(set(tokens)) == 9
    assert len(calls["evaluations"]) == len(state["family_fill"]["attempts"])
    # ② 挑战者的 8 个核心根 × 2 臂 = 16 条边被评价完成（逐格读数）。
    coverage = _coverage(run_root)
    assert coverage["n_roots"] == 8 and coverage["n_edges"] == 16
    assert coverage["n_edges_covered"] == 16, coverage["keys"]
    assert coverage["missing_tokens"] == []
    per_cell = {(row["sub_scenario"], row["opponent_mix"]):
                sorted(arm for arm, info in row["arms"].items() if info["covered"])
                for row in coverage["keys"]}
    assert per_cell == {(sub, mix): ["baseline", "candidate"] for sub, mix, _ in CORE}
    # ③ family_fill 与轮次读数不再是空与 0。
    fill = state["family_fill"]
    assert fill["attempts"], "family_fill.attempts 不得为空"
    tx = json.loads((Path(state["iter_dir"]) / "transactions"
                     / search.AV_TX_FILES["family_refresh"]).read_text(encoding="utf-8"))
    assert tx["rounds"] and tx["rounds"][0]["filled"], tx["rounds"][:1]
    assert fill["reevaluation"]["declared"] == 9
    # 第一轮读数：9 条声明 → 9 条义务；末轮义务归零（边已齐备，无重复计费）。
    assert tx["rounds"][0]["reevaluation"]["obligations"] == 9
    assert fill["reevaluation"]["obligations"] == []
    assert tx["rounds"][0]["reevaluation"]["rejected"] == []
    # ④ 全部必需边齐备后才提交（提交前保持原席原 epoch 的语义由 fake_commit 见证）。
    assert verdict["status"] == "committed"
    assert calls["commits"] >= 2, "必须走 补根→重试提交 路径"


def test_p15_stop_reasons_are_distinguishable(tmp_path, monkeypatch):
    """停因三类可分：见证不足（INSUFFICIENT）/ 预算不足 / 无声明（仅无声明时）。"""

    rows = _plan_rows(with_specified_root=False)
    # 挑战者的核心根证据已齐备（P11 逐键覆盖无缺口）⇒ 只剩"声明见证不足"这一条路径。
    run_root = _build_run_root(Path(tmp_path) / "witness", rows=rows,
                              challenger_records=True)
    state = _state(run_root, rows)
    for item in state["family_refresh_resolved"]["resolved"][:4]:
        item["witness"] = {"status": "miss", "readings": {}}
    calls = _harness(monkeypatch, run_root, budget=64)
    verdict = search._av_family_fill(state, run_root, _Ledger(64.0), TOKEN)
    assert calls["evaluations"] == [], [i["token"] for i in calls["evaluations"]]
    assert verdict["stop_reason"] == "family_reevaluation_witness_insufficient"
    assert len(verdict["reevaluation"]["witness_insufficient"]) == 4
    assert verdict["reevaluation"]["obligations"] == 0
    assert verdict["status"] != "committed"


def test_p15_budget_gate_blocks_before_spending(tmp_path, monkeypatch):
    """预算门早于费用：预算不够即记 budget_insufficient，一张桌不动。"""

    ledger = _Ledger(remaining=0.0)
    state, run_root, verdict, calls, ledger = _run(
        Path(tmp_path) / "budget", monkeypatch, budget=1, ledger=ledger)
    assert calls["evaluations"] == []
    assert ledger.reserved == []
    assert verdict["stop_reason"] == "family_reevaluation_budget_insufficient"
    assert verdict["status"] != "committed"


def test_p15_specified_old_root_is_evaluated(tmp_path, monkeypatch):
    """指定旧根（root_index=None + resolve 提示）：按 iter-01 条件结果解析并评价。"""

    state, run_root, verdict, calls, ledger = _run(Path(tmp_path) / "registered",
                                                   monkeypatch)
    evaluated = [item for item in calls["evaluations"]
                 if item["root_indexes"] == [0]
                 and item["sub_scenario"] == "branch_open"
                 and item["opponent_mix"] == "H"]
    assert len(evaluated) == 1, [i["token"] for i in calls["evaluations"]]
    assert evaluated[0]["root_seed"] == 66460248753675
    assert list(evaluated[0]["root_ids"]) == [SPECIFIED_ROOT_ID]
    assert verdict["reevaluation"]["rejected"] == []


def test_p15_unregistered_specified_root_is_named_rejected(tmp_path, monkeypatch):
    """未登记 / 不可解析 ⇒ 具名拒绝（不得默认 root000、不得替换成别的根）。"""

    rows = _plan_rows()
    run_root = _build_run_root(Path(tmp_path) / "unregistered", rows=rows,
                              register_specified_root=False)
    state = _state(run_root, rows)
    calls = _harness(monkeypatch, run_root, budget=64)
    verdict = search._av_family_fill(state, run_root, _Ledger(64.0), TOKEN)
    tx = json.loads((Path(state["iter_dir"]) / "transactions"
                     / search.AV_TX_FILES["family_refresh"]).read_text(encoding="utf-8"))
    blocked = [item for row in (tx.get("rounds") or ())
               for item in (row.get("blocked") or ())
               if str(item.get("token", "")).endswith("root000")]
    rejected = [item for item in verdict["reevaluation"]["rejected"]
                if "root000" in str(item.get("root_id"))]
    assert rejected, verdict["reevaluation"]
    assert "未登记" in rejected[0]["reason"] or "不猜" in rejected[0]["reason"]
    # 具名拒绝必须同时进事务件（可事后复核），而不是只活在内存里。
    outcome = tx["outcome"] if isinstance(tx.get("outcome"), dict) else {}
    assert any("root000" in str(item.get("root_id"))
               for item in ((outcome.get("reevaluation") or {}).get("rejected") or ()))
    assert all(list(item["root_indexes"]) != [0] for item in calls["evaluations"]), \
        "未登记的根不得被评价（不猜复现参数）"


def test_p15_declaration_present_never_reports_no_declaration(tmp_path, monkeypatch):
    """有重评声明时停因必须是重评类（不得 no_declaration，也不得 batch_invalid）。"""

    rows = _plan_rows(with_specified_root=False)
    state, run_root, verdict, calls, ledger = _run(
        Path(tmp_path) / "declared", monkeypatch, rows=rows, budget=1,
        ledger=_Ledger(remaining=0.0))
    assert verdict["stop_reason"] == "family_reevaluation_budget_insufficient"
    assert verdict["reevaluation"]["declared"] == 8


def test_p15_no_declaration_is_distinguishable(tmp_path, monkeypatch):
    """确实没有任何重评声明时，才允许出现 no_declaration 停因。"""

    rows = _plan_rows(with_specified_root=False)
    run_root = _build_run_root(Path(tmp_path) / "nodecl", rows=rows)
    state = _state(run_root, rows)
    state["plan"]["family_refresh"] = []
    state["family_refresh_resolved"] = {"channel": CHANNEL, "complete": True,
                                        "resolved": [], "request": []}
    calls = _harness(monkeypatch, run_root, budget=64,
                     commit_outcomes=[{"status": "kept", "phase": "batch_invalid",
                                       "missing": {},
                                       "refresh": {"status": "batch_invalid"}}])
    verdict = search._av_family_fill(state, run_root, _Ledger(64.0), TOKEN)
    assert calls["evaluations"] == []
    # ③ 无声明类：只在**确实没有重评声明**时出现，且记在重评账目里；
    #    发现型计划的既有停因名逐字不变（P8 套件继续绿）。
    assert verdict["reevaluation"]["declared"] == 0
    assert state["family_fill"]["reevaluation"]["stop_reason"] == \
        "family_reevaluation_no_declaration"
    assert verdict["stop_reason"] not in (
        "family_reevaluation_no_declaration",
        "family_reevaluation_edges_evaluated_pending_commit",
        "family_reevaluation_budget_insufficient",
        "family_reevaluation_witness_insufficient")


def test_p15_atomic_semantics_unchanged_when_edges_incomplete(tmp_path, monkeypatch):
    """部分身份完成时保持原家族席与原 epoch、结果暂存 pending（不假装提交）。"""

    rows = _plan_rows(with_specified_root=False)
    state, run_root, verdict, calls, ledger = _run(
        Path(tmp_path) / "partial", monkeypatch, rows=rows, budget=2,
        ledger=_Ledger(remaining=0.0))
    assert verdict["status"] not in ("committed", "established")
    assert verdict["stop_reason"] in (
        "family_reevaluation_budget_insufficient",
        "family_reevaluation_edges_evaluated_pending_commit")
    assert verdict["reevaluation"]["declared"] == 8


def test_p15_commit_classifies_open_obligations_as_pending(tmp_path, monkeypatch):
    """提交路径（E2E 发现的那半）：义务未完成 ⇒ 家族通道结局必须是 pending。

    缺陷机制（run6 实测）：9 条声明全部见证 ⇒ 刷新批为空 ⇒ 结局被分类成 batch_invalid
    （kept）⇒ 迭代不进 REFRESH_PENDING（_step_archive 只在 family_status == "pending"
    时进）⇒ 补根步一轮都不跑。本测用**真实** _av_commit_family 断言结局分类。
    """

    rows = _plan_rows()
    run_root = _build_run_root(tmp_path / "commit-pending", rows=rows)
    state = _state(run_root, rows)
    verdict = search._av_commit_family(state, run_root, attempt_refresh=True,
                                       budget=100)
    assert verdict["status"] == "pending", verdict
    assert verdict["phase"] == "reevaluation"
    missing = dict(verdict.get("missing") or {})
    assert sorted(missing) == [CHALLENGER]
    assert len(missing[CHALLENGER]) == 9, missing[CHALLENGER]
    # 原子语义不变：原家族席与原家族 epoch 保留，且不写成已刷新。
    archive = json.loads((Path(run_root) / "archive" / "av-archive.json")
                         .read_text(encoding="utf-8"))
    challenge = archive.get("family_challenge") or {}
    assert challenge.get("status") == "pending"
    assert challenge.get("seats_kept") is True
    assert challenge.get("epoch_kept") == 1
    # 迭代级标识（family_epoch 身份串）由 _step_archive 落；本测只断言提交层语义。
    assert challenge.get("note"), challenge
