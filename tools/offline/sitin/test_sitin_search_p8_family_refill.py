# -*- coding: utf-8 -*-
"""P8 FAMRETRY 专属测试（R9 关口二 run2 暴露的生产侧缺陷 + Lead 追加项）。

缺陷（验收链实测，证据 `evidence/v4-impl/r9-gate2/DEFECT-family-fill-retry-2026-09-18.md`）：
  家族补根第二轮重试**同一个声明根**时，`_av_family_run_evaluation` 的恢复对账只让位
  `tables_full`，`prefix_generation` / `tables_partial` 的旧已结算行仍在 ⇒ 重新预留同一
  step_id 抛 `TaskAlreadySettled` ⇒ 异常不在 catch 列表里 ⇒ 抛穿 `_step_refresh_fill`，
  worker 退出码 3（同一工作项被反复进入：检查点 attempt_no 5..8，branch_cost 根无样本）。

本文件覆盖（**全部离线**：mock 生成 + 夹具条件面板 + 替身家族条件评价执行器 + 替身桌赛
驱动；零真实桌赛、零 LLM 调用、零网络；账本照记以便核对「不重不漏」）：
  1. **三账户逐账户对账**：一次家族条件评价在 prefix_generation / tables_partial /
     tables_full 上各留一行（与 `_step_conditional` 同族口径），重试第二轮不得抛穿；
  2. **不重复计费**：每个 (step_id, 账户) 至多一行「未让位」的账行，被让位的旧行**金额
     保留**（失败成本保留），总费 = 逐次评价之和；
  3. **账本异常 → 失败返回**：并发写入者抢先结算（对账与预留之间的竞态）与对账自身抛
     同类异常，都必须变成家族评价的失败返回（补根按设计保原席原 epoch），不得抛穿；
  4. **无进展根不重试到轮数上限**（Lead 追加）：前缀永不见证的声明根连续 K 轮无进展即
     停止重试，具名停因 + 原家族席原 epoch；对照：有进展的根在有限轮次内补齐；
  5. 不得放宽：预算不足仍走 `family_refresh_budget_insufficient_old_seats_kept`。

替身口径声明：`FamilyEvalStub` 是**真实 v2_behavior 家族评价执行器**的替身（0 真实桌赛），
但它**照真实路由逐账户记账**（前缀生成 1.0、被启动桌赛实例 1.0、双臂完整阶段 4.0 或 0.0），
因此本文件的三账户对账断言与被替换的实现同口径，不是"替身自证"。
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
import re
import sys
import uuid
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import sitin_search as search  # noqa: E402
import sitin_archive as sa  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402

#: 批次 7 授权令牌 + 账户额度（替身：0 真实桌赛，账面照记）。
TOKEN = {"authorized": True, "batch": 7,
         "budgets": {"tokens_input": 100000, "tokens_output": 200000,
                     "tables_full": 256, "tables_partial": 64,
                     "prefix_generation": 64}}

CHANNEL = "branch"
SUB_OPEN = "branch_open"
SUB_COST = "branch_cost"
SEED = 20260916
STRENGTH_INCUMBENT = 8

#: 家族条件评价的三个账户（R9/P8：与 `_step_conditional` 同族口径）。
FAMILY_ACCOUNTS = ("prefix_generation", "tables_partial", "tables_full")

#: 声明批序号：每侧 4 条（H/M 各 2），同一面板种子下互不相同。
DECL_INDEX = {(SUB_OPEN, "H"): (3, 5), (SUB_OPEN, "M"): (4, 6),
              (SUB_COST, "H"): (7, 9), (SUB_COST, "M"): (8, 10)}
#: 前缀**永不见证**的声明根（反例根）：H 侧 idx3。
NO_WITNESS_INDEX = 3


def _fam_root(sub, mix, index, seed=SEED):
    """家族根身份：**唯一描述符**（生产实现同源；不手拼根名）。"""

    return str(search.av_family_root_id(prefix_source="scripted_fixture",
                                        sub_scenario=sub, opponent_mix=mix,
                                        panel_seed=seed, root_index=index))


def _family_root_row(sub, mix, index, seed=SEED):
    descriptor = search.av_family_root_descriptor(
        prefix_source="scripted_fixture", sub_scenario=sub, opponent_mix=mix,
        panel_seed=seed, root_index=index)
    return {"root_id": str(descriptor["root_id"]), "sub_scenario": sub,
            "opponent_mix": mix, "panel_seed": seed, "root_index": index,
            "root_seed": int(descriptor["root_seed"]),
            "seed_derivation": str(descriptor["seed_derivation"]),
            "generator": str(descriptor["generator"]), "seats_per_root": 1}


def _declarations():
    """开轮声明的家族刷新批：每侧 4 条（H/M 各 2；声明层校验要求）。"""

    rows = []
    for (sub, mix), indices in sorted(DECL_INDEX.items()):
        for index in indices:
            rows.append({"channel": CHANNEL, "sub_scenario": sub,
                         "opponent_mix": mix, "panel_seed": SEED,
                         "root_index": index})
    return rows


def _strength_source(strength):
    from hangma_bot.policy import action_value_seeds as seeds

    lines = seeds.EFFICIENCY_SEED.source.splitlines()
    return "\n".join(lines[:2] + ["P8_STRENGTH = {0}".format(int(strength))]
                      + lines[2:])


def _patch_seed(monkeypatch, strength=STRENGTH_INCUMBENT):
    from hangma_bot.policy import action_value_seeds as seeds

    spec = seeds.SeedSpec(name="efficiency_seed", source=_strength_source(strength),
                          mechanism=dict(seeds.EFFICIENCY_SEED_MECHANISM))
    monkeypatch.setitem(seeds.SEEDS, "efficiency_seed", spec)


class StrengthDrive:
    """替身桌赛驱动（0 真实桌赛）：焦点臂分数由候选源码强度标记决定。"""

    def __init__(self):
        self.calls = []

    def __call__(self, *, plan, policies_by_seat, versions_block, step_limit,
                 value_limits):
        seats = list(plan.seats())
        focal_idx = seats.index("natural:focal") if "natural:focal" in seats \
            else seats.index("focal")
        policy = policies_by_seat[focal_idx]
        source = getattr(getattr(policy, "_scorer", None), "source", "") or ""
        match = re.search(r"P8_STRENGTH\s*=\s*([0-9]+)", source)
        self.calls.append({"table_id": str(plan.table_id)})
        focal = float(match.group(1)) if match else -10.0
        others = iter((5.0, 3.0, 1.0))
        scores = [focal if seat == focal_idx else next(others) for seat in range(4)]
        return {"table_id": plan.table_id, "seed": int(plan.seed),
                "match_status": "complete", "wall_ms": 1.0,
                "scores_by_seat": scores, "result": {}}


class FamilyEvalStub:
    """替身**家族条件评价执行器**（0 真实桌赛）：照真实 v2_behavior 路由**逐账户记账**。

    - prefix_generation：每次评价预留 1.0、结算 1.0（一次前缀生成）；
    - tables_partial：预留 planned（4.0），结算 `partial_charged`（默认 1.0 = 被启动的
      真实桌赛实例数；与 run2 实测账行同形）；
    - tables_full：预留 4.0；**谓词被见证** ⇒ 结算 4.0；**未被见证** ⇒ 结算 0.0
      （完整阶段桌赛一张没跑完，与 run2 实测的 branch_cost 行同形）。

    `no_witness_roots` 的根一律返回**失败面**（无样本 ⇒ `_av_family_result_matches`
    判「根清单不符」，与真实路由同因），其余根返回带根要求摘要/内容摘要的可用样本。
    """

    def __init__(self, *, no_witness_roots=(), partial_charged=1.0,
                 full_tables=4.0, planned_partial=4.0):
        self.no_witness_roots = {str(value) for value in no_witness_roots}
        self.partial_charged = float(partial_charged)
        self.full_tables = float(full_tables)
        self.planned_partial = float(planned_partial)
        self.calls = []
        self.per_root = {}

    def __call__(self, *, state, run_root, ledger, authorization, item, source,
                 test_runtime_factory=None):
        cid = str(item["candidate_id"])
        sub = str(item["sub_scenario"])
        mix = str(item["opponent_mix"])
        seed = int(item["panel_seed"])
        token = str(item.get("token"))
        roots = [str(value) for value in item["root_ids"]]
        prefix = search._av_family_step_prefix(cid, sub, token)
        witnessed = not (set(roots) & self.no_witness_roots)
        # 先预留后执行（与真实路由同序、同账户、同 step_id 构造）；结算按**实执行数**：
        # 谓词未被见证 ⇒ tables_full 完整阶段一张没跑完 = 0.0（与 run2 的 branch_cost 行
        # 同形），前缀生成与被启动的部分桌照记 1.0（费用保留）。
        for step_id, account, amount, actual in (
                (prefix, "prefix_generation", 1.0, 1.0),
                (prefix + ":tables-partial", "tables_partial", self.planned_partial,
                 self.partial_charged),
                (prefix + ":tables-full", "tables_full", self.full_tables,
                 (self.full_tables if witnessed else 0.0))):
            row = ledger.reserve(step_id=step_id, account=account, amount=amount,
                                 note="替身家族条件评价（先预留）")
            ledger.settle(row, actual=float(actual), note="替身：0 真实桌赛")
        self.calls.append({"candidate_id": cid, "sub": sub, "mix": mix,
                           "panel_seed": seed, "token": token, "roots": roots,
                           "witnessed": witnessed})
        for root in roots:
            self.per_root[root] = self.per_root.get(root, 0) + 1
        if not witnessed:
            return {"ok": False, "evaluation": None, "tables_executed": 0,
                    "reason": ("家族条件评价结果不符：根清单不符（多 [] / 缺 {0}）"
                               "（不采用）".format(roots))}
        strength = STRENGTH_INCUMBENT
        match = re.search(r"P8_STRENGTH\s*=\s*([0-9]+)", str(source.get("source") or ""))
        if match:
            strength = int(match.group(1))
        requirement = search.av_family_root_requirement_digest(
            prefix_source=str(item.get("prefix_source") or "scripted_fixture"),
            predicate=sub, opponent_mix=mix, panel_seed=seed,
            root_index=int((item.get("root_indexes") or [0])[0]))
        samples = [_family_sample(root, sub, mix, cid, strength / 16.0,
                                  root_requirement_digest=requirement,
                                  root_content_digest=requirement + ":stub")
                   for root in roots]
        return {"ok": True, "tables_executed": int(self.full_tables),
                "evaluation": {
                    "ok": True,
                    "identity": {"candidate_id": cid, "opponent_mix": mix},
                    "panel": {"predicate": sub, "panel_seed": seed,
                              "tables_full_executed": int(self.full_tables)},
                    "root_selection": {"selector": "conditional_root",
                                       "indexes": [int(value) for value
                                                   in (item.get("root_indexes") or ())],
                                       "root_ids": list(roots)},
                    "tables_partial_charged": self.partial_charged,
                    "samples": samples,
                    "execution_kind": "real_runtime",
                    "real_table_instances": int(self.partial_charged),
                    "result_admission": {"ok": True}},
                "reason": ""}


def _family_sample(root, sub, mix, cid, d, *, cost=1.0, **extra):
    sample = {"source_root_id": root, "scenario": sub, "opponent_mix": mix,
              "candidate_id": cid, "root_role": "core", "invalid": False,
              "completeness": "complete", "invalid_reasons": [], "cost": cost,
              "arms": {"baseline": {"candidate_id": search.AV_BASELINE_ID, "u": 0.0},
                       "candidate": {"candidate_id": cid, "u": float(d)}}}
    sample.update(extra)
    return sample


def _normal_sample(root, mix, cid, d, *, cost=1.0):
    return {"source_root_id": root, "scenario": "normal", "opponent_mix": mix,
            "candidate_id": cid, "root_role": "core", "invalid": False,
            "completeness": "complete", "invalid_reasons": [], "cost": cost,
            "arms": {"baseline": {"candidate_id": search.AV_BASELINE_ID, "u": 0.0},
                     "candidate": {"candidate_id": cid, "u": float(d)}}}


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + chr(10),
                    encoding="utf-8")


def _run_root(tmp_path):
    root = Path(tmp_path) / ("p8-" + uuid.uuid4().hex[:6]) / "run"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _normal_roots(seed=SEED, roots=2):
    return sorted(natural.natural_root_id(mix, seed, index)
                  for mix in ("H", "M") for index in range(1, roots + 1))


def _normal_entry(cid, d=0.5, seed=SEED, roots=2):
    return sa.merge_archive_entry(
        None, cid, [_normal_sample(root, "H" if "-H-" in root else "M", cid, d)
                    for root in _normal_roots(seed, roots)], safety="PASS")


#: 在案 family epoch 的核心格根序号（与声明批序号 3..10 刻意不同：核心根与刷新根
#: 必须是不同的根，否则刷新批会被判 batch_invalid）。
CORE_INDEX = {(SUB_OPEN, "H"): 20, (SUB_OPEN, "M"): 21,
              (SUB_COST, "H"): 22, (SUB_COST, "M"): 23}


def _family_entry(cid, *, open_d=0.5, cost_d=0.5):
    """家族证据条目（走**生产合并器**；每（侧 × 情景）一个独立根 = 在案 epoch 的根）。"""

    samples = [_family_sample(_fam_root(sub, mix, index), sub, mix, cid,
                              cost_d if sub == SUB_COST else open_d)
               for (sub, mix), index in sorted(CORE_INDEX.items())]
    return sa.merge_archive_entry(None, cid, samples, safety="PASS")


def _seed_chain(run_root):
    """预置在案档案 + 家族 epoch 1 + 家族根台账（模拟前序迭代已提交）。"""

    archive_dir = Path(run_root) / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    incumbent = "inc-branch"
    overall = "inc-overall"
    archive = {
        "schema": sa.ARCHIVE_SCHEMA,
        "slots": {"overall": [overall], "branch": [incumbent], "chain": [],
                  "four_white": [], "baotou": [], "exploration": []},
        "entries": {incumbent: _family_entry(incumbent),
                    overall: _normal_entry(overall)},
        "exploration_queue": [],
        "behavior_duplicates": {},
        "distinct_candidates": [incumbent, overall],
    }
    _write_json(archive_dir / "av-archive.json", archive)
    normal_epoch = sa.build_channel_epoch(
        "normal", [{"root_id": root, "opponent_mix": ("H" if "-H-" in root else "M")}
                   for root in _normal_roots()])
    _write_json(archive_dir / "normal-epoch.json", normal_epoch)
    core = []
    ledger_roots = []
    for (sub, mix), index in sorted(CORE_INDEX.items()):
        core.append({"root_id": _fam_root(sub, mix, index), "opponent_mix": mix,
                     "sub_scenario": sub})
        row = _family_root_row(sub, mix, index)
        row.update({"channel": CHANNEL, "source": "前序迭代条件评价"})
        ledger_roots.append(row)
    _write_json(archive_dir / "family-epochs.json",
                {"schema": search.AV_FAMILY_EPOCHS_SCHEMA,
                 "channels": {CHANNEL: sa.build_channel_epoch(CHANNEL, core)}})
    _write_json(archive_dir / "family-roots.json",
                {"schema": search.AV_FAMILY_ROOTS_SCHEMA,
                 "channels": {CHANNEL: {"roots": ledger_roots}}})
    source = _strength_source(STRENGTH_INCUMBENT)
    prev_dir = Path(run_root) / "iterations" / "iter-00"
    prev_dir.mkdir(parents=True, exist_ok=True)
    _write_json(prev_dir / "state.json", {
        "schema": search.AV_ITERATION_STATE_SCHEMA, "run_id": "seed-incumbent",
        "iteration_no": 0, "iter_dir": str(prev_dir),
        "status": "ITERATION_COMPLETE", "step_history": [],
        "identity": {"candidate_id": incumbent,
                     "candidate_source_sha256": search.sha256_text(source)},
        "candidate_source": source,
        "plan": {"predicate": SUB_OPEN, "opponent": "H", "panel_seed": SEED,
                 "prefix_source": "scripted_fixture"}})
    return {"incumbent": incumbent, "overall": overall}


def _evolve(run_root, monkeypatch, *, stub=None, token=TOKEN, declarations=None,
            **kwargs):
    _patch_seed(monkeypatch)
    monkeypatch.setattr(natural, "execute_natural_table", StrengthDrive(), raising=True)
    monkeypatch.setattr(search, "_av_family_execute_evaluation",
                        stub if stub is not None else FamilyEvalStub(), raising=True)
    return search.run_av_evolution(
        run_root, generation_mode="mock", seed_name="efficiency_seed",
        predicate=SUB_OPEN, opponent="H", panel_seed=SEED,
        natural_roots=2, natural_seats=1, authorization=token,
        family_channel=CHANNEL,
        family_refresh=(declarations if declarations is not None
                        else _declarations()), **kwargs)


def _rows(run_root):
    return list(search.ActionValueLedger.load(run_root / "av-ledger.json").reservations)


def _rows_for(rows, step_prefix):
    return [row for row in rows if str(row["step_id"]).startswith(step_prefix)]


def _active_duplicates(rows):
    """同一 (step_id, 账户) 出现两行「未让位」的已结算/在途账行（重复计费面）。"""

    seen = {}
    duplicates = []
    for row in rows:
        if row.get("superseded") or row["status"] not in ("settled", "reserved"):
            continue
        key = (str(row["step_id"]), str(row["account"]))
        if key in seen:
            duplicates.append(key)
        seen[key] = row
    return duplicates


def _family_tx(state):
    """家族补根事务件（**逐轮**记录的唯一落盘处；state 里只留 outcome/no_progress）。"""

    return _read_json(Path(state["iter_dir"]) / "transactions"
                      / search.AV_TX_FILES["family_refresh"])


def _decl_step_prefix(state, sub, mix, index):
    cid = str(state["identity"]["candidate_id"])
    token = "{0}-s{1}-idx{2}".format(mix, SEED, index)
    return search._av_family_step_prefix(cid, sub, token)


# =====================================================================
# 1 · 家族补根重试：三账户逐账户对账（R9 关口二 run2 的反例根）
# =====================================================================


def test_p8_family_refill_retry_reconciles_all_three_accounts(tmp_path, monkeypatch):
    """反例根第二轮重试：逐账户让位，不抛 TaskAlreadySettled，不重复计费。

    反例（修复前）：第二轮对同一 step_id 重新预留 `prefix_generation` ⇒
    `TaskAlreadySettled` 抛穿（run2 worker 退出码 3）。
    修复后：三个账户的旧已结算行都被让位（金额保留），新尝试各得一行新的账行；
    每个 (step_id, 账户) 至多一行「未让位」。
    """

    run_root = _run_root(tmp_path)
    _seed_chain(run_root)
    target = _fam_root(SUB_OPEN, "H", NO_WITNESS_INDEX)
    stub = FamilyEvalStub(no_witness_roots=[target])
    result = _evolve(run_root, monkeypatch, stub=stub)     # 修复前：此处抛穿
    assert result.get("terminal") == "ITERATION_COMPLETE", result

    # 反例根被**第二轮**重试（不是一次就放弃、也不是撞在旧账行上）。
    assert stub.per_root.get(target, 0) >= 2, stub.per_root
    state = search.av_state_load(search.av_latest_state_path(run_root))
    fill_attempts = list((state.get("family_fill") or {}).get("attempts") or [])
    assert len(fill_attempts) >= 2, fill_attempts
    rows = _rows(run_root)
    prefix = _decl_step_prefix(state, SUB_OPEN, "H", NO_WITNESS_INDEX)
    # 三账户逐行可对账（旧行 superseded + 新行 settled；旧行金额保留）。
    # 三账户逐行可对账：2 次评价 ⇒ 每账户 2 行，金额按次累计，至多 1 行「未让位」。
    attempts = stub.per_root[target]
    for account, per_attempt in (("prefix_generation", 1.0),
                                 ("tables_partial", 1.0),
                                 ("tables_full", 0.0)):
        step_id = {"prefix_generation": prefix,
                   "tables_partial": prefix + ":tables-partial",
                   "tables_full": prefix + ":tables-full"}[account]
        account_rows = [row for row in rows if row["account"] == account
                        and str(row["step_id"]) == step_id]
        assert len(account_rows) == attempts, (account, attempts, account_rows)
        assert round(sum(float(row["charged"]) for row in account_rows), 6) == \
            round(per_attempt * attempts, 6), account_rows
        assert len([row for row in account_rows if not row.get("superseded")]) <= 1, \
            account_rows
        assert [row for row in account_rows if row.get("superseded")], \
            ("旧尝试的账行必须显式让位（费用保留），不得被覆盖或删除", account, account_rows)
    # 第二轮的对账报告必须覆盖**三个**账户（不是只让位 tables_full）。
    reconcile = (fill_attempts[-1] or {}).get("reconcile") or {}
    assert set(reconcile) == set(FAMILY_ACCOUNTS), reconcile
    assert all(int(reconcile[account]["rows"]) >= 1 for account in FAMILY_ACCOUNTS), \
        reconcile
    # 全局不重复计费面：任何 (step_id, 账户) 都不允许两行「未让位」。
    assert _active_duplicates(rows) == [], _active_duplicates(rows)
    # 前缀生成按次累计（两次评价 = 2.0），不重复也不静默丢。
    prefix_rows = [row for row in rows if row["account"] == "prefix_generation"
                   and str(row["step_id"]) == prefix]
    assert round(sum(float(row["charged"]) for row in prefix_rows), 6) == 2.0, prefix_rows
    # 账本里其余工件（自然面板/条件面板/其它声明根）也各自至多一行未让位。
    assert _active_duplicates(rows) == []


# =====================================================================
# 2 · 无进展停止（Lead 追加）：不重试到轮数上限
# =====================================================================


def test_p8_no_progress_root_is_not_retried_to_round_cap(tmp_path, monkeypatch):
    """前缀永不见证的声明根：连续 K 轮无进展即停，具名停因 + 原家族席原 epoch。"""

    run_root = _run_root(tmp_path)
    seeded = _seed_chain(run_root)
    epoch_before = _read_json(run_root / "archive" / "family-epochs.json")
    target = _fam_root(SUB_OPEN, "H", NO_WITNESS_INDEX)
    stub = FamilyEvalStub(no_witness_roots=[target])
    result = _evolve(run_root, monkeypatch, stub=stub)
    assert result.get("terminal") == "ITERATION_COMPLETE", result

    cap = int(search.AV_REFRESH_FILL_MAX_ROUNDS)
    limit = int(search.AV_FAMILY_REFILL_NO_PROGRESS_ROUNDS)
    assert 1 <= limit < cap, (limit, cap)
    state = search.av_state_load(search.av_latest_state_path(run_root))
    fill = state["family_fill"]
    # ⅰ 反例根**没有被重试到轮数上限**：实际评价次数 = K。
    attempts = [call for call in stub.calls if target in call["roots"]]
    assert len(attempts) == limit, (len(attempts), limit, attempts)
    assert len(attempts) < cap, (len(attempts), cap)
    # ⅱ 具名停因 + 逐根轮次（含根身份）。
    assert state["stop_reason"] == "family_refill_no_progress_old_seats_kept", \
        state["stop_reason"]
    assert fill["outcome"]["status"] == "family_refill_no_progress", fill["outcome"]
    # 降级不是成功：停因不得写成 committed/established（诚实性判据）。
    assert fill["outcome"]["status"] not in ("committed", "established"), fill["outcome"]
    record = (fill["no_progress"] or {}).get(target)
    assert record and int(record["rounds"]) >= limit, (record, fill.get("no_progress"))
    assert int(record["last_round"]) <= limit + 1, record
    tx_rounds = list(_family_tx(state).get("rounds") or [])
    stopped_rows = [row for row in tx_rounds if row.get("no_progress_stopped")]
    assert stopped_rows, [(row.get("round"), row.get("status")) for row in tx_rounds]
    assert any(str(item["root_id"]) == target
               for item in (stopped_rows[0].get("no_progress") or [])), stopped_rows[0]
    assert len(tx_rounds) <= limit + 1, [row.get("round") for row in tx_rounds]
    # ⅲ 保原家族席与原家族 epoch（不混新旧均值）。
    archive_after = _read_json(run_root / "archive" / "av-archive.json")
    epochs_after = _read_json(run_root / "archive" / "family-epochs.json")
    assert archive_after["slots"][CHANNEL] == [seeded["incumbent"]], archive_after["slots"]
    assert epochs_after["channels"][CHANNEL] == epoch_before["channels"][CHANNEL]
    # 身份标记也必须如实：无进展路径保原 epoch，不得写成"已换 epoch"。
    assert "@epoch-kept" in str(state["identity"]["family_epoch"]), \
        state["identity"]["family_epoch"]
    # ⅳ 挑战者仍在候选池（证据保留、未被静默丢弃）。
    assert str(state["identity"]["candidate_id"]) in archive_after["entries"]
    # ⅴ 账本：反例根的每次评价各留一份费用（按次累计，不重复计费）。
    rows = _rows(run_root)
    assert _active_duplicates(rows) == [], _active_duplicates(rows)
    charged = sum(float(row["charged"]) for row in rows
                  if row["account"] == "prefix_generation"
                  and str(row["step_id"]) == _decl_step_prefix(state, SUB_OPEN, "H",
                                                               NO_WITNESS_INDEX))
    assert charged == float(limit), charged


def test_p8_no_progress_stop_survives_reentry(tmp_path, monkeypatch):
    """重入同一迭代的补根入口：已停止的根**不再产生任何评价**（K 停止的承重面）。

    反例口径：没有这条持久登记时，worker 重入（进程被杀/挂起后恢复走同一入口，或验收
    执行器逐个 worker 重入）会把同一批"永不见证"的根**再评一轮**——每轮都真花钱。
    """

    run_root = _run_root(tmp_path)
    _seed_chain(run_root)
    target = _fam_root(SUB_OPEN, "H", NO_WITNESS_INDEX)
    stub = FamilyEvalStub(no_witness_roots=[target])
    _evolve(run_root, monkeypatch, stub=stub)
    state = search.av_state_load(search.av_latest_state_path(run_root))
    assert state["stop_reason"] == "family_refill_no_progress_old_seats_kept", \
        state["stop_reason"]
    assert stub.per_root.get(target) == search.AV_FAMILY_REFILL_NO_PROGRESS_ROUNDS
    spend_before = search.ActionValueLedger.load(
        run_root / "av-ledger.json").account_summary()

    resume_stub = FamilyEvalStub(no_witness_roots=[target])
    monkeypatch.setattr(search, "_av_family_execute_evaluation", resume_stub,
                        raising=True)
    ledger = search.ActionValueLedger.load(run_root / "av-ledger.json")
    verdict = search._av_family_fill(state, run_root, ledger, TOKEN, None)
    assert resume_stub.calls == [], resume_stub.calls
    assert verdict["status"] == "family_refill_no_progress", verdict
    assert verdict["stop_reason"] == "family_refill_no_progress_old_seats_kept", verdict
    assert ledger.account_summary() == spend_before, (
        ledger.account_summary(), spend_before)
    assert int((verdict.get("no_progress") or {})[target]["rounds"]) \
        >= search.AV_FAMILY_REFILL_NO_PROGRESS_ROUNDS


def test_p8_progressing_roots_fill_within_rounds(tmp_path, monkeypatch):
    """对照：全部根都有进展 ⇒ 一轮补齐、建立家族 epoch，且无无进展记录。"""

    run_root = _run_root(tmp_path)
    stub = FamilyEvalStub()          # 无 no_witness 根：全部见证
    declarations = _declarations()
    result = _evolve(run_root, monkeypatch, stub=stub)
    assert result.get("terminal") == "ITERATION_COMPLETE", result
    state = search.av_state_load(search.av_latest_state_path(run_root))
    fill = state["family_fill"]
    assert fill["outcome"]["status"] in ("established", "committed"), fill["outcome"]
    assert not (fill.get("no_progress") or {}), fill.get("no_progress")
    tx_rounds = list(_family_tx(state).get("rounds") or [])
    # 轮次 = 「一轮补齐（epoch_core_fill）」+「一轮复核（已建立）」，不是重试。
    assert [row.get("round") for row in tx_rounds] == [1, 2], tx_rounds
    assert str(tx_rounds[0].get("phase")) == "epoch_core_fill", tx_rounds[0]
    declared = sorted({_fam_root(row["sub_scenario"], row["opponent_mix"],
                                 row["root_index"])
                       for row in declarations})
    for root in declared:
        assert stub.per_root.get(root) == 1, (root, stub.per_root.get(root))
    roots = _read_json(run_root / "archive" / "family-roots.json")
    registered = {str(row["root_id"])
                  for row in roots["channels"][CHANNEL]["roots"]}
    assert set(declared) <= registered, (sorted(set(declared) - registered))


def test_p8_budget_shortage_still_keeps_seats_and_spends_nothing(tmp_path,
                                                                monkeypatch):
    """不得放宽：预算不足仍是 `budget_insufficient` 保原席、零家族评价。"""

    run_root = _run_root(tmp_path)
    seeded = _seed_chain(run_root)
    epoch_before = _read_json(run_root / "archive" / "family-epochs.json")
    token = dict(TOKEN, budgets=dict(TOKEN["budgets"], tables_full=40))
    stub = FamilyEvalStub(no_witness_roots=[_fam_root(SUB_OPEN, "H", NO_WITNESS_INDEX)])
    result = _evolve(run_root, monkeypatch, stub=stub, token=token)
    assert result.get("terminal") == "ITERATION_COMPLETE", result
    state = search.av_state_load(search.av_latest_state_path(run_root))
    assert state["stop_reason"] == "family_refresh_budget_insufficient_old_seats_kept", \
        state["stop_reason"]
    assert stub.calls == [], stub.calls
    archive_after = _read_json(run_root / "archive" / "av-archive.json")
    epochs_after = _read_json(run_root / "archive" / "family-epochs.json")
    assert archive_after["slots"][CHANNEL] == [seeded["incumbent"]]
    assert epochs_after["channels"][CHANNEL] == epoch_before["channels"][CHANNEL]
    assert not (state["family_fill"].get("no_progress") or {})


# =====================================================================
# 3 · 账本异常 → 失败返回（补根按设计保原席原 epoch，不崩 worker）
# =====================================================================


class _RaceLedger(search.ActionValueLedger):
    """并发写入者在**对账与预留之间**抢先结算同一 step_id（账本异常注入）。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.raced = False

    def reserve(self, *, step_id, account, amount, note="", usage_unknown=False):
        if not self.raced and account == "prefix_generation":
            self.raced = True
            row = super().reserve(step_id=step_id, account=account, amount=amount,
                                  note="并发写入者（夹具注入）")
            super().settle(row, actual=float(amount), note="并发写入者抢先结算")
        return super().reserve(step_id=step_id, account=account, amount=amount,
                               note=note, usage_unknown=usage_unknown)


def _iter_state(tmp_path):
    from hangma_bot.policy import action_value_seeds as seeds

    source = seeds.EFFICIENCY_SEED.source
    cid = str(search.av_gates().av_candidate_identity(source))
    iter_dir = Path(tmp_path) / "iter" / ("it-" + uuid.uuid4().hex[:6])
    iter_dir.mkdir(parents=True, exist_ok=True)
    state = {"run_id": "p8-direct", "iteration_no": 1, "iter_dir": str(iter_dir),
             "identity": {"candidate_id": cid},
             "plan": {"prefix_source": "scripted_fixture"}}
    return state, iter_dir, source


def _family_item(sub=SUB_OPEN, mix="H", index=NO_WITNESS_INDEX):
    descriptor = search.av_family_root_descriptor(
        prefix_source="scripted_fixture", sub_scenario=sub, opponent_mix=mix,
        panel_seed=SEED, root_index=index)
    return {"candidate_id": None, "sub_scenario": sub, "opponent_mix": mix,
            "panel_seed": SEED, "root_indexes": [index],
            "root_ids": [str(descriptor["root_id"])],
            "root_seed": int(descriptor["root_seed"]),
            "token": "{0}-s{1}-idx{2}".format(mix, SEED, index),
            "planned_tables": search.AV_TABLES_PER_FAMILY_EVALUATION,
            "seats_per_root": 1, "kind": "declaration",
            "prefix_source": "scripted_fixture"}


def test_p8_ledger_anomaly_becomes_failure_return(tmp_path, monkeypatch):
    """账本异常（并发抢先结算 / 对账自身抛)必须变成失败返回，不得抛穿家族评价。"""

    state, iter_dir, source = _iter_state(tmp_path)
    run_root = Path(iter_dir).parent
    item = dict(_family_item(), candidate_id=str(state["identity"]["candidate_id"]))
    item_source = {"source": source, "sha256": search.sha256_text(source),
                   "origin": "p8-fixture"}
    ledger = _RaceLedger(Path(iter_dir) / "av-ledger.json",
                         authorized_budgets=search.av_ledger_budgets_from_authorization(
                             TOKEN))
    run = search._av_family_run_evaluation(state, run_root, ledger, TOKEN, item,
                                           item_source)
    assert run.get("evaluation") is None, run
    assert run["attempt"]["status"] == "failed", run["attempt"]
    assert "账本" in str(run["reason"]), run["reason"]
    assert ledger.raced, "夹具未注入并发抢先结算"

    # 对账自身抛同类异常：同样不得抛穿（走同一条失败返回）。
    def boom(*args, **kwargs):
        raise search.TaskAlreadySettled("夹具注入：对账阶段账本拒绝（S3）")

    monkeypatch.setattr(search, "av_reconcile_ledger_attempts", boom, raising=True)
    state2, iter_dir2, source2 = _iter_state(tmp_path)
    run2 = search._av_family_run_evaluation(
        state2, Path(iter_dir2).parent,
        search.ActionValueLedger(Path(iter_dir2) / "av-ledger.json",
                                 authorized_budgets=search
                                 .av_ledger_budgets_from_authorization(TOKEN)),
        TOKEN, dict(_family_item(), candidate_id=str(state2["identity"]["candidate_id"])),
        {"source": source2, "sha256": search.sha256_text(source2), "origin": "p8-fixture"})
    assert run2.get("evaluation") is None, run2
    assert run2["attempt"]["status"] == "failed", run2["attempt"]
    assert "账本" in str(run2["reason"]), run2["reason"]
