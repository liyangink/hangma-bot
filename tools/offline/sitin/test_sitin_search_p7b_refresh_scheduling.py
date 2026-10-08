# -*- coding: utf-8 -*-
"""P7b 专属测试（R7 修复批次）：接通「补根 → 晋升」调度，使端到端晋升可达。

来源：P7 收口报告 §4 第 2 条（Lead 确认为功能阻断）。A2 已把挑战事务化（原席 +
通道根集 + epoch 为事务基准，任一非提交结局保原席），但状态机一轮只评一个候选，
"原席者补齐挑战者声明的新刷新根"没有调度入口 → 真实运行停在 pending_partial
（REFRESH_PENDING），端到端晋升不可达、档案席位永不翻动。

本文件覆盖（**全部离线**：mock 生成 + 替身桌赛驱动；零真实桌赛、零 LLM 调用、
不消耗授权账目——账本照记以便核对"不重不漏"）：
  1. 端到端晋升：证据更强的挑战者 → 补根 → 全员齐备 → 原子换 epoch + **席位翻动**；
  2. pending_partial → 补根 → 提交 的完整路径证据（检查点 / 实例台账 / 账目 /
     事务件 / 档案证据）；
  3. 补根预算不足（阶段 1 之前、阶段 2 之前两种口径）→ 保原席原 epoch、
     挑战者留候选池、**不混新旧均值**；
  4. 补根中途进程被杀 → 恢复不重复计费、不重复评价同一实例、能继续推进到提交；
  5. 负例：补根未齐绝不 committed（epoch/席位不动、challenge 状态如实）。
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

import hashlib
import json
import re
import sys
import uuid
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import sitin_search as search  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402

#: 批次 7 授权令牌 + 账户额度（替身桌赛：0 真实桌赛，账面照记）。
TOKEN = {"authorized": True, "batch": 7,
         "budgets": {"tokens_input": 100000, "tokens_output": 200000,
                     "tables_full": 256, "tables_partial": 64,
                     "prefix_generation": 64}}

#: 迭代 1（在位者）的通道核心根面板种子；迭代 2（挑战者）声明的刷新批面板种子。
SEED_OLD = 20260916
SEED_NEW = 20270101

#: 焦点臂强度标记（写进候选源码常量，替身驱动按它分离两候选的证据强弱）：
#: 2 → 阶段总分 4（组内第 3，U=[0,0]，d_low=0）；12 → 总分 24（组内第 1，
#: U=[1,1]，d_low=1）→ 挑战者证据严格更强。
STRENGTH_INCUMBENT = 2
STRENGTH_CHALLENGER = 12


# --------------------------------------------------------------------- 工具


def _strength_of(source):
    match = re.search(r"P7B_STRENGTH\s*=\s*([0-9]+)", source or "")
    return int(match.group(1)) if match else None


class StrengthDrive:
    """替身桌赛驱动（0 真实桌赛）：焦点臂分数由**候选源码强度标记**决定。

    候选臂焦点总分 = strength × tables_per_group；基线臂焦点恒 -10（U=[0,0]）。
    对手固定 5/3/1 → 强候选恒第 1（U=[1,1]）、弱候选恒第 3（U=[0,0]），
    两候选在同一根上的配对差因此可复现（T12 同根集比较）。
    """

    def __init__(self, *, fail_for=None):
        self.calls = []
        #: 命中该强度标记的候选臂整根失败（用于"补根拿不到可用证据"负例；
        #: 默认 None = 不注入失败，setup 之后再打开）。
        self.fail_for = fail_for

    def __call__(self, *, plan, policies_by_seat, versions_block, step_limit,
                 value_limits):
        seats = list(plan.seats())
        focal_idx = seats.index("natural:focal") if "natural:focal" in seats \
            else seats.index("focal")
        policy = policies_by_seat[focal_idx]
        is_candidate = str(getattr(policy, "policy_id", "")).startswith("action_value")
        strength = _strength_of(getattr(getattr(policy, "_scorer", None), "source", "")) \
            if is_candidate else None
        self.calls.append({"table_id": str(plan.table_id), "is_candidate": is_candidate,
                           "strength": strength})
        if self.fail_for is not None and strength == self.fail_for:
            raise RuntimeError("P7b 注入：桌赛驱动失败（{0}）".format(plan.table_id))
        focal = float(strength) if strength is not None else -10.0
        others = iter((5.0, 3.0, 1.0))
        scores = [focal if seat == focal_idx else next(others) for seat in range(4)]
        return {"table_id": plan.table_id, "seed": int(plan.seed),
                "match_status": "complete", "wall_ms": 1.0,
                "scores_by_seat": scores, "result": {}}


def _patch_seed(monkeypatch, strength):
    """把 efficiency_seed 换成带强度标记的变体源码（同一牌效逻辑）。"""

    from hangma_bot.policy import action_value_seeds as seeds

    lines = seeds.EFFICIENCY_SEED.source.splitlines()
    source = "\n".join(lines[:2] + ["P7B_STRENGTH = {0}".format(int(strength))]
                        + lines[2:])
    spec = seeds.SeedSpec(name="efficiency_seed", source=source,
                          mechanism=dict(seeds.EFFICIENCY_SEED_MECHANISM))
    monkeypatch.setitem(seeds.SEEDS, "efficiency_seed", spec)


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _run_root(tmp_path):
    root = Path(tmp_path) / ("p7b-" + uuid.uuid4().hex[:6]) / "run"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _evolve(run_root, monkeypatch, *, strength, panel_seed, roots, token=TOKEN,
            **kwargs):
    _patch_seed(monkeypatch, strength)
    return search.run_av_evolution(run_root, generation_mode="mock",
                                   seed_name="efficiency_seed",
                                   panel_seed=panel_seed, natural_roots=roots,
                                   natural_seats=1, authorization=token, **kwargs)


def _with_incumbent(tmp_path, monkeypatch, *, token=TOKEN, roots=2):
    """开一条链：迭代 1 建立通道 epoch 并把弱候选放进席位。"""

    run_root = _run_root(tmp_path)
    first = _evolve(run_root, monkeypatch, strength=STRENGTH_INCUMBENT,
                    panel_seed=SEED_OLD, roots=roots, token=token)
    assert first.get("terminal") == "ITERATION_COMPLETE", first
    archive = _read_json(run_root / "archive" / "av-archive.json")
    assert len(archive["slots"]["overall"]) == 1, archive["slots"]
    return run_root


def _panel_roots(seed, roots, mixes=("H", "M")):
    return sorted(natural.natural_root_id(mix, seed, index)
                  for mix in mixes for index in range(1, roots + 1))


def _fill_tables(seed, roots, seats=1, tables_per_group=2, mixes=("H", "M")):
    return len(mixes) * roots * seats * 2 * tables_per_group


# =====================================================================
# 1 · 端到端晋升：席位真的翻动
# =====================================================================


def test_p7b_end_to_end_promotion_flips_seat(tmp_path, monkeypatch):
    """核心验收：证据更强的挑战者 → 补根齐备 → 原子提交新 epoch，**席位翻动**。

    P7 期此项不可达（状态机停在 REFRESH_PENDING、席位不动）。
    """

    drive = StrengthDrive()
    monkeypatch.setattr(natural, "execute_natural_table", drive, raising=True)
    run_root = _with_incumbent(tmp_path, monkeypatch)
    archive_before = _read_json(run_root / "archive" / "av-archive.json")
    epoch_before = _read_json(run_root / "archive" / "normal-epoch.json")
    incumbent = archive_before["slots"]["overall"][0]

    result = _evolve(run_root, monkeypatch, strength=STRENGTH_CHALLENGER,
                     panel_seed=SEED_NEW, roots=2)
    assert result.get("terminal") == "ITERATION_COMPLETE", result
    state = search.av_state_load(search.av_latest_state_path(run_root))
    statuses = [row["status"] for row in state["step_history"]]
    assert "REFRESH_PENDING" in statuses, statuses      # 先停在补根态
    challenger = state["identity"]["candidate_id"]
    assert challenger != incumbent

    archive_after = _read_json(run_root / "archive" / "av-archive.json")
    epoch_after = _read_json(run_root / "archive" / "normal-epoch.json")
    # —— 席位翻动（本包核心验收项）——
    assert archive_after["slots"]["overall"][0] == challenger
    assert archive_after["slots"]["overall"] == [challenger, incumbent]
    assert archive_after["slots"]["overall"] != archive_before["slots"]["overall"]
    # —— 只有全员在旧根+新根齐备时才换 epoch ——
    assert epoch_after["epoch"] == epoch_before["epoch"] + 1
    assert len(epoch_after["roots"]) == len(epoch_before["roots"]) + 4
    assert [row["root_id"] for row in epoch_before["roots"]] == \
        [row["root_id"] for row in epoch_after["roots"]][:len(epoch_before["roots"])]
    # 新根以 refresh 角色入根集，绝不流入确认集（Q2）。
    assert all(row["role"] == "refresh" for row in epoch_after["roots"][-4:])
    assert all(row["confirmation_eligible"] is False
               for row in epoch_after["roots"][-4:])


def test_p7b_partial_fill_path_lands_evidence(tmp_path, monkeypatch):
    """完整路径证据：pending_partial → 补根评价**确实执行并落账** → 提交。"""

    drive = StrengthDrive()
    monkeypatch.setattr(natural, "execute_natural_table", drive, raising=True)
    run_root = _with_incumbent(tmp_path, monkeypatch)
    archive_before = _read_json(run_root / "archive" / "av-archive.json")
    incumbent = archive_before["slots"]["overall"][0]

    result = _evolve(run_root, monkeypatch, strength=STRENGTH_CHALLENGER,
                     panel_seed=SEED_NEW, roots=2)
    assert result.get("terminal") == "ITERATION_COMPLETE", result
    state = search.av_state_load(search.av_latest_state_path(run_root))
    challenger = state["identity"]["candidate_id"]
    iter2 = Path(state["iter_dir"])
    core_roots = _panel_roots(SEED_OLD, 2)
    refresh_roots = _panel_roots(SEED_NEW, 2)

    # ① 补根检查点：逐（身份 × 情景）落盘且复用判据齐全（P6 S3 同源）。
    for cid, seed in ((challenger, SEED_OLD), (incumbent, SEED_NEW)):
        for mix in ("H", "M"):
            checkpoint = _read_json(iter2 / "checkpoints"
                                    / "refresh-{0}-{1}.json".format(cid[:12], mix))
            assert checkpoint["status"] == "completed", checkpoint
            assert checkpoint["result_sha256"], checkpoint
            assert checkpoint["cost_charged"] == 8, checkpoint
            panel = _read_json(checkpoint["result_path"])
            assert panel["identity"]["panel_seed"] == seed
            assert panel["identity"]["opponent_mix"] == mix
            assert panel["config"]["roots"] == 2
            assert panel["config"]["seats_per_root"] == 1

    # ② 实例台账：补根按（身份 × 根 × 座位 × 臂 × 赛程）落账，完成有摘要与费用。
    instances = _read_json(run_root / "instances.json")["instances"]
    for cid, wanted in ((challenger, core_roots), (incumbent, refresh_roots)):
        rows = [row for row in instances.values()
                if row.get("participant_id") == cid]
        assert {row["source_root_id"] for row in rows} == set(wanted), sorted(
            row["source_root_id"] for row in rows)
        assert all(row["status"] == "completed" and row["result_digest"]
                   for row in rows), rows

    # ③ 账目：补根走同一共享账本（先预留后执行、失败照记），全部结算、无卡住预留。
    ledger = search.ActionValueLedger.load(run_root / "av-ledger.json")
    fill_rows = [row for row in ledger.reservations
                 if str(row["step_id"]).startswith("refresh:")]
    assert len(fill_rows) == 4, fill_rows
    assert all(row["status"] == "settled" and row["charged"] == 8.0
               for row in fill_rows), fill_rows
    assert [row for row in ledger.reservations if row["status"] != "settled"] == []

    # ④ 档案证据：挑战者补齐了通道核心根、原席者补齐了声明的刷新根。
    archive = _read_json(run_root / "archive" / "av-archive.json")
    assert set(core_roots) <= set(archive["entries"][challenger]["normal_evaluations"])
    assert set(refresh_roots) <= set(archive["entries"][incumbent]["normal_evaluations"])

    # ⑤ 事务件：补根 outcome 与提交落盘可核对；批次报告写清终态。
    tx = _read_json(iter2 / "transactions" / "tx-refresh-fill.json")
    assert tx["schema"] == search.AV_REFRESH_FILL_TX_SCHEMA
    assert tx["outcome"]["status"] == "committed"
    assert tx["outcome"]["epoch_after"] == 2
    report = _read_json(iter2 / "batch-report.json")
    assert report["stop_reason"] == "refresh_committed_new_epoch"
    assert report["archive_diff"]["slots"]["overall"][0] == challenger


def test_p7b_index_selection_fills_only_missing_roots(tmp_path, monkeypatch):
    """P2b 接线：同一 panel_seed 下扩展根清单 → 原席者**只补缺失的那些根**。

    迭代 1（2 根/情景）建 epoch（root01/02 × H/M）；迭代 2 用**同一 panel_seed**
    但 4 根/情景：挑战者自有 4 根（含 epoch 全部根 → 阶段 1 直接过），声明的新刷新根
    = root03/04 × H/M（4 根、H/M 均衡、校验通过）。原席者已有 root01/02，补根必须
    按根索引只选 root03/04 —— 不得整前缀重跑 root01/02（同一实例不重复评价、不重复
    计费），也不得因此放弃这条晋升路径。
    """

    drive = StrengthDrive()
    monkeypatch.setattr(natural, "execute_natural_table", drive, raising=True)
    run_root = _with_incumbent(tmp_path, monkeypatch)
    archive_before = _read_json(run_root / "archive" / "av-archive.json")
    incumbent = archive_before["slots"]["overall"][0]
    calls_before = len(drive.calls)

    result = _evolve(run_root, monkeypatch, strength=STRENGTH_CHALLENGER,
                     panel_seed=SEED_OLD, roots=4)
    assert result.get("terminal") == "ITERATION_COMPLETE", result
    state = search.av_state_load(search.av_latest_state_path(run_root))
    challenger = state["identity"]["candidate_id"]
    iter2 = Path(state["iter_dir"])
    old_roots = _panel_roots(SEED_OLD, 2)
    new_roots = sorted(natural.natural_root_id(mix, SEED_OLD, index)
                       for mix in ("H", "M") for index in (3, 4))

    # ① 补根只评被选根：检查点的费用与面板的选择集都不含 root01/02。
    for mix in ("H", "M"):
        checkpoint = _read_json(iter2 / "checkpoints"
                                / "refresh-{0}-{1}.json".format(incumbent[:12], mix))
        assert checkpoint["cost_charged"] == 8, checkpoint   # 2 根 × 1 座 × 2 臂 × 2 桌
        panel = _read_json(checkpoint["result_path"])
        produced = {sample["source_root_id"] for sample in panel["samples"]}
        assert produced == {natural.natural_root_id(mix, SEED_OLD, 3),
                            natural.natural_root_id(mix, SEED_OLD, 4)}
        assert not (produced & set(old_roots))               # root01/02 未被重跑
        assert panel["config"]["roots"] == 2

    # ② 桌级证据：原席者的补根桌全部落在 root03/04 上（整前缀重跑会被这条抓住）。
    fill_tables = {call["table_id"] for call in drive.calls[calls_before:]
                   if call["strength"] == STRENGTH_INCUMBENT}
    assert fill_tables, "补根应确实执行桌赛"
    assert all("-r03-" in table_id or "-r04-" in table_id
               for table_id in fill_tables), sorted(fill_tables)

    # ③ 实例台账逐实例对账：原席者补根实例 = 4 根 × 1 座 × 2 臂，无一条落在旧根上，
    #    且同一实例最多完成一次（不重复评价）。
    instances = _read_json(run_root / "instances.json")["instances"]
    rows = [row for row in instances.values()
            if row.get("participant_id") == incumbent]
    assert {row["source_root_id"] for row in rows} == set(new_roots)
    assert len(rows) == len(new_roots) * 2
    assert all(len([item for item in (row.get("attempts") or [])
                    if item.get("status") == "completed"]) <= 1
               for row in instances.values())

    # ④ 账目：补根是**独立**账行（选择集记号 idx3-4），费用与桌数一致、全部结算。
    ledger = search.ActionValueLedger.load(run_root / "av-ledger.json")
    fill_rows = [row for row in ledger.reservations
                 if str(row["step_id"]).startswith("refresh:")]
    assert sorted(row["charged"] for row in fill_rows) == [8.0, 8.0]
    assert all(str(row["step_id"]).endswith(":idx3-4") for row in fill_rows), fill_rows
    assert all(row["status"] == "settled" for row in ledger.reservations)

    # ⑤ 晋升照常可达：全员在旧根+新根齐备 → 换 epoch 且席位翻动。
    archive_after = _read_json(run_root / "archive" / "av-archive.json")
    epoch_after = _read_json(run_root / "archive" / "normal-epoch.json")
    assert archive_after["slots"]["overall"] == [challenger, incumbent]
    assert epoch_after["epoch"] == 2 and len(epoch_after["roots"]) == 8


# =====================================================================
# 2 · 预算不足：保原席原 epoch、挑战者留候选池、不混新旧均值
# =====================================================================


def test_p7b_budget_short_before_fill_keeps_seats(tmp_path, monkeypatch):
    """补根预算一次都付不起（阶段 1 前）：保原席原 epoch + 挑战者留候选池。"""

    drive = StrengthDrive()
    monkeypatch.setattr(natural, "execute_natural_table", drive, raising=True)
    token = dict(TOKEN, budgets=dict(TOKEN["budgets"], tables_full=36))
    run_root = _with_incumbent(tmp_path, monkeypatch, token=token)
    archive_before = _read_json(run_root / "archive" / "av-archive.json")
    epoch_before = _read_json(run_root / "archive" / "normal-epoch.json")
    incumbent = archive_before["slots"]["overall"][0]
    ledger = search.ActionValueLedger.load(run_root / "av-ledger.json")
    tables_before = ledger.spent("tables_full")
    calls_before = len(drive.calls)

    result = _evolve(run_root, monkeypatch, strength=STRENGTH_CHALLENGER,
                     panel_seed=SEED_NEW, roots=2, token=token)
    assert result.get("terminal") == "ITERATION_COMPLETE", result
    state = search.av_state_load(search.av_latest_state_path(run_root))
    challenger = state["identity"]["candidate_id"]
    archive_after = _read_json(run_root / "archive" / "av-archive.json")
    epoch_after = _read_json(run_root / "archive" / "normal-epoch.json")

    # 保原席原 epoch；挑战者只留候选池/探索队列（不进席）。
    assert archive_after["slots"] == archive_before["slots"], archive_after["slots"]
    assert archive_after["slots"]["overall"] == [incumbent]
    assert epoch_after["epoch"] == epoch_before["epoch"]
    assert [row["root_id"] for row in epoch_after["roots"]] == \
        [row["root_id"] for row in epoch_before["roots"]]
    assert challenger in archive_after["entries"]
    assert challenger in archive_after["exploration_queue"]
    # 无混均值：挑战者没有通道核心根记录（未比较、未并入）。
    assert not (set(_panel_roots(SEED_OLD, 2))
                <= set(archive_after["entries"][challenger]["normal_evaluations"]))
    # 补根一张桌都没跑（早于费用：预算门先拒）；本迭代自然面板照跑（16 桌）。
    assert len(drive.calls) == calls_before + _fill_tables(SEED_NEW, 2)
    ledger_after = search.ActionValueLedger.load(run_root / "av-ledger.json")
    assert ledger_after.spent("tables_full") == tables_before + _fill_tables(SEED_NEW, 2)
    assert not [row for row in ledger_after.reservations
                if str(row["step_id"]).startswith("refresh:")]
    # 终态报告如实记账（明确下一步与原因）。
    assert state["stop_reason"] == "refresh_budget_insufficient_old_seats_kept"
    assert ("budget" in json.dumps(state["refresh_fill"], ensure_ascii=False))


def test_p7b_phase2_budget_short_keeps_seats_without_mixing(tmp_path, monkeypatch):
    """阶段 2 预算不足（挑战者已补齐旧根）：仍保原席，且**不把新旧根混算**。"""

    drive = StrengthDrive()
    monkeypatch.setattr(natural, "execute_natural_table", drive, raising=True)
    token = dict(TOKEN, budgets=dict(TOKEN["budgets"], tables_full=56))
    run_root = _with_incumbent(tmp_path, monkeypatch, token=token)
    archive_before = _read_json(run_root / "archive" / "av-archive.json")
    epoch_before = _read_json(run_root / "archive" / "normal-epoch.json")
    incumbent = archive_before["slots"]["overall"][0]

    result = _evolve(run_root, monkeypatch, strength=STRENGTH_CHALLENGER,
                     panel_seed=SEED_NEW, roots=2, token=token)
    assert result.get("terminal") == "ITERATION_COMPLETE", result
    state = search.av_state_load(search.av_latest_state_path(run_root))
    challenger = state["identity"]["candidate_id"]
    archive_after = _read_json(run_root / "archive" / "av-archive.json")
    epoch_after = _read_json(run_root / "archive" / "normal-epoch.json")

    assert archive_after["slots"]["overall"] == [incumbent]
    assert epoch_after["epoch"] == epoch_before["epoch"]
    # 挑战者补齐了通道核心根（阶段 1 已过），但原席者的刷新根未补 → 不提交。
    assert set(_panel_roots(SEED_OLD, 2)) <= set(
        archive_after["entries"][challenger]["normal_evaluations"])
    assert not (set(_panel_roots(SEED_NEW, 2)) & set(
        archive_after["entries"][incumbent]["normal_evaluations"]))
    tx = _read_json(Path(state["iter_dir"]) / "transactions"
                    / "tx-channel-refresh.json")
    assert tx["outcome"] == "budget_insufficient", tx
    assert tx["seats_before"] == [incumbent]
    assert state["stop_reason"] == "refresh_budget_insufficient_old_seats_kept"


# =====================================================================
# 3 · 进程被杀后恢复：不重复计费、不重复评价、能继续推进
# =====================================================================


def test_p7b_kill_mid_fill_resume_continues_without_rerun(tmp_path, monkeypatch):
    """补根 H 面板结果落盘后被中断 → 恢复复用、原样续跑、不重复评价同一实例。"""

    drive = StrengthDrive()
    monkeypatch.setattr(natural, "execute_natural_table", drive, raising=True)
    # 面板级调用记录器：整条运行里每次 run_natural_panel 的（候选源码摘要, 情景,
    # 种子, 根数, 座位数）——用于逐面板核对"同一身份 × 同一面板只评价一次"。
    panels = []
    original_panel = natural.run_natural_panel

    def recording_panel(**kwargs):
        selection = kwargs.get("root_indices")
        count = (len(selection) if selection is not None
                 else int(kwargs.get("roots") or 0))
        panels.append((hashlib.sha256(kwargs["candidate_source"].encode(
            "utf-8")).hexdigest(), str(kwargs["opponent"]),
            int(kwargs["panel_seed"]), int(count),
            int(kwargs["seats_per_root"])))
        return original_panel(**kwargs)

    monkeypatch.setattr(natural, "run_natural_panel", recording_panel, raising=True)
    run_root = _with_incumbent(tmp_path, monkeypatch)

    def hook(point, **_fields):
        if str(point).startswith("refresh:") and \
                str(point).endswith(":H:after_result_before_settle"):
            raise RuntimeError("P7b 注入：补根 H 面板结果落盘后进程中止")

    _patch_seed(monkeypatch, STRENGTH_CHALLENGER)
    monkeypatch.setattr(search, "av_fault_point", hook, raising=True)
    with pytest.raises(RuntimeError):
        search.run_av_evolution(run_root, generation_mode="mock",
                                seed_name="efficiency_seed", panel_seed=SEED_NEW,
                                natural_roots=2, natural_seats=1, authorization=TOKEN)
    monkeypatch.setattr(search, "av_fault_point", lambda *a, **k: None, raising=True)

    state_mid = search.av_state_load(search.av_latest_state_path(run_root))
    assert state_mid["status"] == "REFRESH_PENDING"
    ledger_mid = search.ActionValueLedger.load(run_root / "av-ledger.json")
    spent_mid = ledger_mid.spent("tables_full")
    calls_mid = list(drive.calls)
    # 被中断的那一次补根：结果已在盘上（不可变产物），检查点仍是 started。
    iter2 = Path(state_mid["iter_dir"])
    killed_tables = set()
    for panel_path in sorted((iter2 / "refresh").glob("*/panel.json")):
        killed_tables |= {str(table_id) for sample in
                          _read_json(panel_path)["samples"]
                          for table_id in sample["table_ids"]}
    assert killed_tables, "中断点之前应已有一个补根面板结果落盘"
    killed_panel = _read_json(sorted((iter2 / "refresh").glob("*/panel.json"))[0])
    # 每个桌 id 在两臂各执行一次 → 被中断面板实际执行的桌数（tables_full）取自面板费用。
    killed_tables_executed = int(killed_panel["cost"]["tables_full_executed"])
    killed_panel_key = (str(killed_panel["identity"]["candidate_source_sha256"]),
                        str(killed_panel["identity"]["opponent_mix"]),
                        int(killed_panel["identity"]["panel_seed"]),
                        int(killed_panel["config"]["roots"]),
                        int(killed_panel["config"]["seats_per_root"]))

    resume_drive = StrengthDrive()
    monkeypatch.setattr(natural, "execute_natural_table", resume_drive, raising=True)
    resumed = search.run_av_machine_resume(run_root, run_id=state_mid["run_id"],
                                           authorization=TOKEN)
    state_after = search.av_state_load(search.av_latest_state_path(run_root))
    assert state_after["status"] == "ITERATION_COMPLETE", (resumed, state_after["status"])

    # ① 不重复评价：被中断面板的桌一张都没重跑。
    assert not (killed_tables & {call["table_id"] for call in resume_drive.calls})
    # ② 同一（身份 × 面板）在整个运行里只评价一次（跨中断累计）：
    #    面板级调用记录 = 每次 run_natural_panel 的（候选源码摘要, 情景, 种子, 根数,
    #    座位数）；恢复只补未完成的面板，已完成的（含"结果在盘上、结算未做"）不重调。
    assert len(panels) == len(set(panels)), "同一身份 × 面板被重复评价"
    # 迭代 1 自然面板 H/M + 迭代 2 自然面板 H/M + 补根 4 个面板（挑战者旧根 2 +
    # 原席者刷新根 2）= 8；被中断的那个面板只出现一次（恢复复用、不重调）。
    assert len(panels) == 8, panels
    assert len([row for row in panels if row == killed_panel_key]) == 1

    # ③ 前后账目对比：恢复只补未完成部分（H 面板不重复计费）。
    ledger_after = search.ActionValueLedger.load(run_root / "av-ledger.json")
    spent_after = ledger_after.spent("tables_full")
    remaining_fill_tables = (_fill_tables(SEED_OLD, 2) + _fill_tables(SEED_NEW, 2)
                             - killed_tables_executed)
    assert spent_after - spent_mid == remaining_fill_tables, (
        spent_mid, spent_after, remaining_fill_tables)
    assert [row for row in ledger_after.reservations
            if row["status"] != "settled"] == []
    instances = _read_json(run_root / "instances.json")["instances"]
    for key, row in instances.items():
        done = [item for item in (row.get("attempts") or [])
                if item.get("status") == "completed"]
        assert len(done) <= 1, (key, row)

    # ④ 能继续推进到提交：恢复后完成补根并翻席。
    challenger = state_after["identity"]["candidate_id"]
    archive_after = _read_json(run_root / "archive" / "av-archive.json")
    assert archive_after["slots"]["overall"][0] == challenger
    assert _read_json(run_root / "archive" / "normal-epoch.json")["epoch"] == 2


# =====================================================================
# 4 · 负例与防线
# =====================================================================


def test_p7b_incomplete_evidence_never_committed(tmp_path, monkeypatch):
    """负例：补根执行了但**没拿到可用证据**（原席者臂失败）→ 绝不 committed。"""

    drive = StrengthDrive()
    monkeypatch.setattr(natural, "execute_natural_table", drive, raising=True)
    run_root = _with_incumbent(tmp_path, monkeypatch)
    # setup（迭代 1）之后再注入：只在**补根**原席者时让其臂失败（拿不到可用证据）。
    drive.fail_for = STRENGTH_INCUMBENT
    archive_before = _read_json(run_root / "archive" / "av-archive.json")
    epoch_before = _read_json(run_root / "archive" / "normal-epoch.json")
    incumbent = archive_before["slots"]["overall"][0]

    result = _evolve(run_root, monkeypatch, strength=STRENGTH_CHALLENGER,
                     panel_seed=SEED_NEW, roots=2)
    assert result.get("terminal") == "ITERATION_COMPLETE", result
    state = search.av_state_load(search.av_latest_state_path(run_root))
    archive_after = _read_json(run_root / "archive" / "av-archive.json")
    epoch_after = _read_json(run_root / "archive" / "normal-epoch.json")
    challenger = state["identity"]["candidate_id"]

    # 未提交：epoch 与席位都不动，challenge 块如实标注 pending。
    assert epoch_after["epoch"] == epoch_before["epoch"]
    assert archive_after["slots"]["overall"] == [incumbent]
    assert archive_after["challenge"]["status"] == "pending_partial"
    assert archive_after["challenge"]["seats_kept"] is True
    # 原席者没有拿到刷新根证据（失败臂不产生可用根记录），也没有换席。
    assert not (set(_panel_roots(SEED_NEW, 2)) & set(
        archive_after["entries"][incumbent]["normal_evaluations"]))
    # 补根确实执行过（不是"没接线"）：实例台账有缺口 → 终态如实记为证据不全。
    assert state["refresh_fill"]["outcome"]["status"] == "evidence_incomplete"
    assert state["refresh_fill"]["attempts"], state["refresh_fill"]
    assert state["stop_reason"] == "refresh_evidence_incomplete_old_seats_kept"
    assert challenger in archive_after["entries"]


def test_p7b_no_authorization_no_fill_no_bypass(tmp_path, monkeypatch):
    """防线：补根缺批次 7 授权 → 一张桌都不跑（不新建绕过授权判据的通路）。"""

    drive = StrengthDrive()
    monkeypatch.setattr(natural, "execute_natural_table", drive, raising=True)
    run_root = _with_incumbent(tmp_path, monkeypatch)
    archive_before = _read_json(run_root / "archive" / "av-archive.json")
    epoch_before = _read_json(run_root / "archive" / "normal-epoch.json")
    # 停在补根态（尚未执行任何补根），再以**缺批次 7**的令牌恢复。
    stopped = _evolve(run_root, monkeypatch, strength=STRENGTH_CHALLENGER,
                      panel_seed=SEED_NEW, roots=2, stop_after="REFRESH_PENDING")
    assert stopped.get("stopped_after") == "REFRESH_PENDING", stopped
    calls_before = len(drive.calls)
    tables_before = search.ActionValueLedger.load(
        run_root / "av-ledger.json").spent("tables_full")
    weak_token = dict(TOKEN, batch=6)

    resumed = search.run_av_machine_resume(run_root, run_id=stopped["run_id"],
                                           authorization=weak_token)
    state = search.av_state_load(search.av_latest_state_path(run_root))
    assert state["status"] == "ITERATION_COMPLETE", (resumed, state["status"])
    archive_after = _read_json(run_root / "archive" / "av-archive.json")
    # 补根（真实桌赛）在没有批次 7 授权时一张桌都不启动，账目不变、席位不动。
    assert len(drive.calls) == calls_before
    assert search.ActionValueLedger.load(
        run_root / "av-ledger.json").spent("tables_full") == tables_before
    assert _read_json(run_root / "archive" / "normal-epoch.json")["epoch"] == \
        epoch_before["epoch"]
    assert archive_after["slots"] == archive_before["slots"]
    assert state["refresh_fill"]["outcome"]["status"] == "unauthorized"
    assert state["stop_reason"] == "refresh_unauthorized_old_seats_kept"


def test_p7b_instance_key_is_participant_scoped():
    """实例唯一键：补根实例必须按**身份**区分，不冒充他候选的同一实例。"""

    base = search.av_instance_key(source_root_id="np-H-1-root01", seat=0,
                                  arm="candidate", schedule="stage_complete:2_tables")
    assert base == "np-H-1-root01|seat0|candidate|stage_complete:2_tables"
    other = search.av_instance_key(source_root_id="np-H-1-root01", seat=0,
                                   arm="candidate", schedule="stage_complete:2_tables",
                                   identity="cand-a")
    assert other != base
    assert other.endswith("|idcand-a")
    assert other == search.av_instance_key(
        source_root_id="np-H-1-root01", seat=0, arm="candidate",
        schedule="stage_complete:2_tables", identity="cand-a")
