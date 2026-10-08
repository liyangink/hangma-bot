# -*- coding: utf-8 -*-
"""P9 FAMCOST 专属测试（家族声明解析 + 单根路径读数口径）。

缺陷（关口二 run3 实测，证据 evidence/v4-impl/r9-fixes/P9-famcost/）：
  计划声明的代价侧根在真实前缀下**永不见证**谓词（三个析取项逐项不可达），而 A1
  不变量要求"声明根全部物化齐全才原子提交 epoch" ⇒ 家族 epoch 永远建不起来、
  家族首席席为空。修法（Lead §P2 裁定）：不动 A1 不变量，改**声明从哪来**——
  预算门下的**有界独立根搜索**，只把见证到谓词的根写进该格有效声明，逐候选根留痕，
  凑不齐即具名停因 + 保原席，**不放宽逐格配额、不放宽预算**。

覆盖（全部离线：注入探针替身 + 假账本，零真实桌赛、零模型调用、零网络）：
  1. 请求逐字保留 + 有效声明由可见证根构成（含"声明根能见证就用它"的身份忠实性）；
  2. 逐格配额由**已物化（可见证）**的根满足，数目不增不减；
  3. 不见证的候选根**逐条留痕**（状态 + 具名原因 + 读数），不静默丢弃；
  4. 凑不齐 ⇒ complete=false + 具名停因（映射到保原席原 epoch 的停因串）；
  5. 预算门：不足即停（不花钱、不换根顶替、不伪造命中）；
  6. 有界：候选试到上限即停（不无限重试）；
  7. 确定性：同输入 → 同解析结果（可复算）；
  8. 单根面板读数口径（P3）：cap 写真实值 1，调用方预留额另存并给具名原因。
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

import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import sitin_search as search  # noqa: E402

CHANNEL = "branch"
SUB_OPEN = "branch_open"
SUB_COST = "branch_cost"
SEED = 20260916


def _request_rows():
    """开轮请求：两侧 × H/M 各 2 根（§7.3 每格配额 2；顺序固定）。"""

    rows = []
    for sub in (SUB_OPEN, SUB_COST):
        for mix in ("H", "M"):
            for index in (1, 2):
                rows.append({"channel": CHANNEL, "sub_scenario": sub,
                             "opponent_mix": mix, "panel_seed": SEED,
                             "root_index": index, "seats_per_root": 1,
                             "source": "plan.family_refresh"})
    return rows


def _state(tmp_path: Path, rows):
    return {"plan": {"prefix_source": "v2_behavior", "panel_seed": SEED,
                     "family_channel": CHANNEL, "family_refresh": rows},
            "iter_dir": str(tmp_path), "iteration_no": 1, "run_id": "r9-p9"}


class _Probe:
    """探针替身：按 (子场景, 情景, 根序号) 声明哪些根见证谓词。"""

    def __init__(self, witnessed, *, record=None):
        self.witnessed = set(witnessed)
        self.calls = []
        self.record = record if record is not None else {}

    def __call__(self, *, descriptor, sub_scenario, mix, panel_seed, root_index,
                 step_id):
        self.calls.append((sub_scenario, mix, int(root_index)))
        hit = (sub_scenario, mix, int(root_index)) in self.witnessed
        return {"status": "hit" if hit else "miss", "witnessed": hit,
                "readings": {"frames": 12, "wall_left_min": 3 if hit else 30,
                             "gap_max": 1},
                "reason": "" if hit else "root_not_witnessed（替身：该根不见证）"}


class _FakeLedger:
    """假账本（remaining + 空实现的 reserve/settle；不写盘、不记账）。"""

    def __init__(self, remaining):
        self._remaining = dict(remaining)
        self.reserved = []
        self.settled = []
        self.reservations: list = []      # 对账读行用（空 ⇒ 无旧尝试）
        self.superseded: list = []

    def supersede(self, *, step_id, account, reason=""):
        self.superseded.append({"step_id": step_id, "account": account,
                                "reason": reason})

    def remaining(self, account):
        return self._remaining.get(account)

    def reserve(self, *, step_id, account, amount, note=""):
        self.reserved.append({"step_id": step_id, "account": account,
                              "amount": float(amount), "note": note})
        return {"step_id": step_id, "account": account, "amount": float(amount)}

    def settle(self, reservation, *, actual, note=""):
        self.settled.append({"step_id": reservation["step_id"],
                             "account": reservation["account"],
                             "actual": float(actual), "note": note})
        return {}


def test_predicate_module_is_in_the_panel_face():
    """P9b 面级表述：八谓词实现必须挂在 panel 面上（此前只在 entry_tool_closure 段）。"""

    plan = {"prefix_source": "v2_behavior", "panel_seed": SEED,
            "family_channel": CHANNEL}
    manifest = search.av_frozen_manifest(plan=plan)
    modules = (manifest["surfaces"]["panel"] or {}).get("modules") or {}
    assert "sitin_predicates_v4.py" in modules
    assert "sitin_opportunities.py" in modules
    # 谓词模块的字节必须真的参与摘要：改一行即让面摘要与整体摘要都变。
    original = search.av_dependency_file_reader

    def perturbed(path):
        data = original(path)
        if str(path).endswith("sitin_predicates_v4.py"):
            return data + b"\n# perturbation\n"
        return data

    search.av_dependency_file_reader = perturbed
    try:
        changed = search.av_frozen_manifest(plan=plan)
    finally:
        search.av_dependency_file_reader = original
    assert search.av_frozen_manifest_digest(changed) != search.av_frozen_manifest_digest(
        manifest)
    assert ((changed["surfaces"]["panel"] or {}).get("modules") or {}).get(
        "sitin_predicates_v4.py") != modules["sitin_predicates_v4.py"]


def test_declaration_search_cost_table_matches_constants():
    """P9b 授权公式补项：成本登记表必须与实际搜索上界同源（漂移即少算预算）。"""

    table = search.AV_FAMILY_DECLARATION_SEARCH_COST
    assert table["max_candidates_per_cell"] == (
        search.AV_FAMILY_DECLARATION_SEARCH_MAX_CANDIDATES)
    assert table["max_total_probes_per_iteration"] == (
        search.AV_FAMILY_DECLARATION_SEARCH_MAX_TOTAL_PROBES)
    assert table["prefix_generation_per_probe"] == 1.0
    assert table["tables_partial_per_probe"] == 1.0
    assert table["tables_full_per_probe"] == 0.0


def test_registered_roots_are_not_redeclared_for_refresh(tmp_path):
    """刷新批不得重复声明**已登记**的根（重复声明 = 刷新什么都没发生）。"""

    rows = _request_rows()
    state = _state(tmp_path, rows)
    run_root = tmp_path / "run"
    (run_root / "archive").mkdir(parents=True)
    # 把请求根（idx1/idx2）以外的 idx0 预先登记（模拟上一迭代已物化的根）。
    registered = search.av_family_root_descriptor(
        prefix_source="v2_behavior", sub_scenario=SUB_COST, opponent_mix="H",
        panel_seed=SEED, root_index=0)
    (run_root / "archive" / "family-roots.json").write_text(json.dumps({
        "schema": search.AV_FAMILY_ROOTS_SCHEMA,
        "channels": {CHANNEL: {"roots": [
            {"sub_scenario": SUB_COST, "opponent_mix": "H",
             "root_id": str(registered["root_id"]), "root_index": 0,
             "panel_seed": SEED, "root_seed": int(registered["root_seed"])}]}}},
        ensure_ascii=False), encoding="utf-8")
    probe = _Probe({(sub, mix, index) for sub in (SUB_OPEN, SUB_COST)
                    for mix in ("H", "M") for index in (0, 2)})
    payload = search.av_resolve_family_declarations(state, run_root, ledger=None,
                                                    probe=probe)
    # idx0 被**跳过且留痕**（不重跑探针、也不写进声明）。
    assert (SUB_COST, "H", 0) not in probe.calls
    skipped = [row for row in payload["trace"]
               if row.get("status") == "skipped" and row.get("cell") == "branch_cost|H"]
    assert skipped and "already_registered" in skipped[0]["reason"]
    resolved_cost_h = sorted(row["root_index"] for row in payload["resolved"]
                             if row["sub_scenario"] == SUB_COST
                             and row["opponent_mix"] == "H")
    assert 0 not in resolved_cost_h
    assert payload["search"]["candidates_skipped"] >= 1


def test_prefix_unknown_is_not_treated_as_witnessed(tmp_path, monkeypatch):
    """真实探针路径：前缀状态 unknown **不是**见证（不冒充命中、不写进声明）。"""

    import sitin_opportunities as opportunities

    class _Outcome:
        status = "unknown"
        prefix: tuple = ()

    def fake_attempt(**kwargs):
        return _Outcome()

    monkeypatch.setattr(opportunities, "run_real_prefix_attempt", fake_attempt)
    rows = [row for row in _request_rows()
            if row["sub_scenario"] == SUB_COST and row["opponent_mix"] == "H"]
    state = _state(tmp_path, rows)
    state["plan"]["family_refresh"] = rows
    ledger = _FakeLedger({"prefix_generation": 8.0, "tables_partial": 8.0,
                          "tables_full": 40.0})
    # 只跑"见证探针"这一层（不装配真实运行时：装配在探针之前被跳过由替身接管）。
    record = search._av_family_root_witness_probe(
        plan=state["plan"], ledger=ledger, sub_scenario=SUB_COST, mix="H",
        panel_seed=SEED, root_index=1,
        assembly={"runtime": None, "rules": None, "tournament_config": None,
                  "value_limits": None, "behavior": None, "opponent_names": ()})
    assert record["status"] == "unknown"
    assert record["witnessed"] is False
    assert search.AV_FAMILY_ROOT_NOT_WITNESSED in record["reason"]
    # 账目照记（探针花了 1 前缀生成 + 1 部分桌）。
    assert [row["account"] for row in ledger.reserved] == ["prefix_generation",
                                                           "tables_partial"]
    assert [row["actual"] for row in ledger.settled] == [1.0, 1.0]


def test_declaration_is_built_from_witnessed_roots(tmp_path):
    rows = _request_rows()
    state = _state(tmp_path, rows)
    # 请求的代价侧 4 根（H/M idx1/2）全部不见证；机会侧 4 根全部见证。
    # 代价侧可见证的是 idx0（H/M）与 idx2（H）。
    probe = _Probe({(SUB_OPEN, "H", 1), (SUB_OPEN, "H", 2),
                    (SUB_OPEN, "M", 1), (SUB_OPEN, "M", 2),
                    (SUB_COST, "H", 0), (SUB_COST, "H", 2),
                    (SUB_COST, "M", 0), (SUB_COST, "M", 2)})
    payload = search.av_resolve_family_declarations(state, tmp_path, ledger=None,
                                                    probe=probe)
    assert payload["complete"] is True
    assert payload["stop_reason"] is None
    # 请求逐字保留（身份面与执行器对账不受影响）。
    assert payload["request"] == rows
    assert state["plan"]["family_refresh"] == rows
    # 有效声明：条数不变、逐格配额 2 且全部可见证。
    resolved = payload["resolved"]
    assert len(resolved) == len(rows) == 8
    cells = {}
    for row in resolved:
        cells.setdefault((row["sub_scenario"], row["opponent_mix"]), []).append(row)
    assert {key: len(value) for key, value in cells.items()} == {
        (SUB_OPEN, "H"): 2, (SUB_OPEN, "M"): 2,
        (SUB_COST, "H"): 2, (SUB_COST, "M"): 2}
    for key, group in cells.items():
        for row in group:
            assert (row["sub_scenario"], row["opponent_mix"],
                    row["root_index"]) in probe.witnessed, key
    # 身份忠实：声明根能见证就用它（机会侧的 idx1/idx2 原样保留）。
    open_h = [row["root_index"] for row in cells[(SUB_OPEN, "H")]]
    assert open_h == [1, 2]
    # 代价侧：请求的 idx1 不见证 ⇒ 被换成可见证的 idx0（逐格配额仍为 2）。
    cost_h = sorted(row["root_index"] for row in cells[(SUB_COST, "H")])
    assert cost_h == [0, 2]
    assert [row["requested_root_index"] for row in cells[(SUB_COST, "H")]] == [1, 2]
    # 落盘证据（逐候选根可核）。
    artifact = json.loads((tmp_path / "family-declaration.json").read_text(
        encoding="utf-8"))
    assert artifact["schema"] == search.AV_FAMILY_DECLARATION_SCHEMA
    assert artifact["search"]["candidates_tried"] == len(probe.calls)
    assert artifact["search"]["cells"]["branch_cost|M"]["witnessed"] == 2


def test_non_witnessing_candidates_are_recorded_with_reason(tmp_path):
    rows = _request_rows()
    state = _state(tmp_path, rows)
    probe = _Probe({(sub, mix, index) for sub in (SUB_OPEN, SUB_COST)
                    for mix in ("H", "M") for index in (0, 2)})
    payload = search.av_resolve_family_declarations(state, tmp_path, ledger=None,
                                                    probe=probe)
    trace = payload["trace"]
    missed = [row for row in trace if not row["witnessed"]]
    assert missed, "不见证的候选根必须留痕（不得静默丢弃）"
    for row in missed:
        assert row["status"] == "miss"
        assert row["reason"]
        assert row["readings"]["frames"] >= 0
        assert row["root_id"] and row["root_seed"] is not None
        assert row["cell"] and row["sub_scenario"] and row["opponent_mix"]
    # 声明给出的根（idx1/idx2 里不见证的那些）也逐条在案（requested 标记）。
    requested_missed = [row for row in missed if row["requested"]]
    assert requested_missed, "请求根不见证时同样要留痕"


def test_unfillable_cell_stops_with_named_reason_and_no_quota_relaxation(
        tmp_path):
    rows = _request_rows()
    state = _state(tmp_path, rows)
    # 代价侧每格只有 1 根可见证（配额要求 2）⇒ 不得凑数、不得放宽配额。
    probe = _Probe({(SUB_OPEN, "H", 1), (SUB_OPEN, "H", 2),
                    (SUB_OPEN, "M", 1), (SUB_OPEN, "M", 2),
                    (SUB_COST, "H", 0), (SUB_COST, "M", 0)})
    payload = search.av_resolve_family_declarations(state, tmp_path, ledger=None,
                                                    probe=probe)
    assert payload["complete"] is False
    assert payload["stop_reason"] == search.AV_FAMILY_DECLARATION_UNFILLABLE
    cells = {}
    for row in payload["resolved"]:
        cells.setdefault((row["sub_scenario"], row["opponent_mix"]), []).append(row)
    assert len(cells[(SUB_COST, "H")]) == 1        # 只有 1 根可见证，就只声明 1 根
    # 具名停因映射到"保原席原 epoch"的停因串（与 P8 同族命名）。
    keep = search._av_family_keep_reason(
        "pending", [], token_ok=True,
        declaration_stop=search.AV_FAMILY_DECLARATION_UNFILLABLE)
    assert keep == "declaration_unfillable"
    assert search.AV_FAMILY_KEEP_STOP_REASONS[keep] == (
        "family_refresh_declaration_unfillable_old_seats_kept")
    # 没有解析结果时不产生声明类停因（旧行为不变）。
    assert search._av_family_keep_reason("pending", [], token_ok=True) != (
        "declaration_unfillable")


def test_budget_gate_stops_before_spending(tmp_path):
    rows = _request_rows()
    state = _state(tmp_path, rows)
    probe = _Probe({(sub, mix, index) for sub in (SUB_OPEN, SUB_COST)
                    for mix in ("H", "M") for index in (1, 2)})
    ledger = _FakeLedger({"prefix_generation": 0.5, "tables_partial": 4.0,
                          "tables_full": 40.0})
    payload = search.av_resolve_family_declarations(state, tmp_path,
                                                    ledger=ledger, probe=probe)
    assert probe.calls == []                      # 预算门早于费用：一次探针都不跑
    assert payload["complete"] is False
    assert payload["stop_reason"] == "budget_insufficient:prefix_generation"
    assert payload["resolved"] == []


def test_search_is_bounded(tmp_path):
    rows = _request_rows()
    state = _state(tmp_path, rows)
    probe = _Probe(set())                         # 一个都不见证
    payload = search.av_resolve_family_declarations(state, tmp_path, ledger=None,
                                                    probe=probe)
    assert payload["complete"] is False
    assert payload["resolved"] == []
    # 逐格上界与全局上界都封顶：一个都不见证的极端情形最多花全局上界次探针。
    assert len(probe.calls) == search.AV_FAMILY_DECLARATION_SEARCH_MAX_TOTAL_PROBES
    assert len(probe.calls) <= (len(_request_rows()) // 2
                                * search.AV_FAMILY_DECLARATION_SEARCH_MAX_CANDIDATES)
    assert payload["search"]["candidates_tried"] == len(probe.calls)
    assert payload["search"]["max_total_probes"] == (
        search.AV_FAMILY_DECLARATION_SEARCH_MAX_TOTAL_PROBES)
    assert payload["stop_reason"] == search.AV_FAMILY_DECLARATION_UNFILLABLE
    assert "search_total_bound_reached" in {
        cell["stop_reason"] for cell in payload["search"]["cells"].values()}


def test_resolution_is_deterministic(tmp_path):
    rows = _request_rows()
    first = search.av_resolve_family_declarations(
        _state(tmp_path / "a", rows), tmp_path / "a", ledger=None,
        probe=_Probe({(sub, mix, index) for sub in (SUB_OPEN, SUB_COST)
                      for mix in ("H", "M") for index in (0, 2)}))
    second = search.av_resolve_family_declarations(
        _state(tmp_path / "b", rows), tmp_path / "b", ledger=None,
        probe=_Probe({(sub, mix, index) for sub in (SUB_OPEN, SUB_COST)
                      for mix in ("H", "M") for index in (0, 2)}))
    assert [(row["sub_scenario"], row["opponent_mix"], row["root_index"])
            for row in first["resolved"]] == [
        (row["sub_scenario"], row["opponent_mix"], row["root_index"])
        for row in second["resolved"]]


def test_core_quota_is_two_roots_per_cell():
    """逐格配额不得放宽：空格/缺根一律判不齐（A1 口径）。"""

    assert search.AV_FAMILY_CORE_ROOTS_PER_CELL == 2
    registry = {"cells_by_side_mix": {
        "branch_cost|H": ["r0", "r1"], "branch_cost|M": ["r0"],
        "branch_open|H": ["r0", "r1"], "branch_open|M": []}}
    matrix = search._av_family_core_matrix(CHANNEL, registry)
    assert matrix["complete"] is False
    assert {item["sub_scenario"] for item in matrix["missing"]} == {
        SUB_COST, SUB_OPEN}
    assert matrix["cells"]["branch_cost|M"]["required"] == 2
    assert matrix["cells"]["branch_cost|M"]["n_roots"] == 1
    assert all(item["required"] == 2 for item in matrix["cells"].values())


def test_declarations_use_resolved_rows_when_present(tmp_path):
    rows = _request_rows()
    state = _state(tmp_path, rows)
    probe = _Probe({(sub, mix, index) for sub in (SUB_OPEN, SUB_COST)
                    for mix in ("H", "M") for index in (0, 2)})
    search.av_resolve_family_declarations(state, tmp_path, ledger=None, probe=probe)
    parsed = search._av_family_declarations(state, CHANNEL)
    assert parsed["declaration_source"] == "family_refresh_resolved"
    assert parsed["problems"] == []
    assert sorted(row["root_index"] for row in parsed["declared"]) == [0, 0, 0, 0,
                                                                      2, 2, 2, 2]
    # 解析结果缺席（夹具/旧状态）⇒ 回退到请求本身，行为逐字不变。
    plain = {"plan": {"family_channel": CHANNEL, "family_refresh": rows}}
    fallback = search._av_family_declarations(plain, CHANNEL)
    assert fallback["declaration_source"] == "plan.family_refresh"
    assert sorted(row["root_index"] for row in fallback["declared"]) == [1, 1, 1, 1,
                                                                        2, 2, 2, 2]


def test_single_root_panel_reports_true_cap(tmp_path):
    """P3 读数修正：单根面板 cap=1（不再是调用方的预留额 8）+ 具名原因。"""

    panel = search._av_conditional_root_panel(
        prefix_source="scripted_fixture", predicate_id="branch_open", focal_seat=0,
        opponent_scenario="H", root_label="p9-cap", out_dir=tmp_path / "panel",
        ruleset_version=search.AV_CONDITIONAL_RULESET_VERSION, base_score=1,
        you_cai_bi_kao=False, attempts_cap=8, panel_seed=SEED, root_index=2,
        root_seed=search.av_family_root_seed(
            prefix_source="scripted_fixture", sub_scenario="branch_open",
            opponent_mix="H", panel_seed=SEED, root_index=2))
    attempts = panel["prefix_attempts"]
    assert attempts["total"] == 1 and attempts["cap"] == 1
    assert attempts["requested_cap"] == 8
    assert attempts["single_root_path"] is True
    assert panel["prefix_attempt_cap"] == 8
    assert "单根路径" in panel["prefix_attempt_cap_note"]
    if attempts["attempts_exhausted"]:
        assert attempts["attempts_exhausted_reason"]
    assert (tmp_path / "panel" / "panel.json").is_file()
