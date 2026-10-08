# -*- coding: utf-8 -*-
"""P7c 专属测试（R7 修复批次）：家族/专长通道接线（复审 §4 A3 的未闭合部分）。

缺陷（P7b 收口报告 §5 实测结论）：
  ① 家族席只在**首次提交**时定一次，此后永不翻动；
  ② 家族通道没有 epoch 也没有挑战接线（build_channel_epoch / apply_challenge
     的家族分支纯函数已实现，但状态机从不构造家族 epoch）；
  ③ 一轮只评一个谓词 → 同一候选要凑齐「该族机会/代价两侧」必须**跨迭代补评价**，
     而这条补评价路径没有调度入口。

本文件覆盖（**全部离线**：mock 生成 + 夹具条件面板 + 替身家族条件评价执行器 +
替身桌赛驱动；零真实桌赛、零 LLM 调用、不消耗授权账目——账本照记以便核对「不重不漏」）：
  1. 家族根登记与家族 epoch 建立（两侧齐备 + H/M 齐备才建 epoch，缺则记输入缺口）；
  2. 家族席晋升：证据更强的两侧齐备挑战者 → 补根 → 原子换家族 epoch + **家族席翻动**；
  3. 负例：只有一侧证据（另一侧补根不可调度）→ **不入席**，家族席与 epoch 保持；
  4. 预算不足 → 保原席原 epoch、零家族评价桌数；
  5. 与 overall 通道互不干扰（家族 epoch/根集变动不动 overall 席位、证据与正常 epoch）；
  6. 8 席结构不变量（2 overall / 4 家族 / 2 探索）；
  7. 家族补根可续跑：逐实例最多完成一次、不重复计费；
  8. 家族证据格键：同一根身份跨对手情景是两个真实实例，必须可分（实测夹具路由
     H/M 同命中 root002 → 同 id 不同情景）。
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
SEED_OLD = 20260916
SEED_NEW = 20270101

#: 候选强度标记（写进候选源码常量，替身执行器按它分离两身份的证据强弱）：
#: d = strength / 16 → 在位者 0.5、挑战者 0.75（家族值 0.5 → 0.75，严格更强）。
STRENGTH_INCUMBENT = 8
STRENGTH_CHALLENGER = 12

#: 家族根身份（R9/A2 起的**完整身份**形状：生成器 × 子场景 × 情景 × 实际种子 ×
#: 根序号）。同一子场景的 H/M 是两个不同的根（不同种子、不同牌山）。
#: 声明批物化后的根序号（每条声明 = 一次条件评价；同一子场景靠不同面板种子
#: 拿到不同根序号——与真实路由「不同种子命中不同尝试序号」同形）。
DECL_INDEX = {("H", SEED_NEW): 3, ("M", SEED_NEW): 4,
              ("H", SEED_OLD): 5, ("M", SEED_OLD): 6}


def _fam_root(sub, mix, index, seed=SEED_OLD):
    """家族根身份：**唯一描述符**（生产实现同源；不再手拼根名）。"""

    return str(search.av_family_root_id(prefix_source="scripted_fixture",
                                        sub_scenario=sub, opponent_mix=mix,
                                        panel_seed=seed, root_index=index))


#: 在案 epoch 的核心格（每侧 × H/M 各一个；每格另留一格给刷新批）。
#: 核心格序号刻意避开声明批的序号（3/4/5/6）：核心根与刷新根必须是不同的根。
CORE_CELLS = ((SUB_OPEN, "H", 2), (SUB_OPEN, "M", 7),
              (SUB_COST, "H", 0), (SUB_COST, "M", 8))
OPEN_ROOT, OPEN_INDEX = _fam_root(SUB_OPEN, "H", 2), 2
COST_ROOT, COST_INDEX = _fam_root(SUB_COST, "H", 0), 0


def _family_root_row(sub, mix, index, seed=SEED_OLD):
    """家族根台账行（**完整身份** + 真实执行种子；形状与生产登记同源）。"""

    descriptor = search.av_family_root_descriptor(
        prefix_source="scripted_fixture", sub_scenario=sub, opponent_mix=mix,
        panel_seed=seed, root_index=index)
    return {"root_id": str(descriptor["root_id"]), "sub_scenario": sub,
            "opponent_mix": mix, "panel_seed": seed, "root_index": index,
            "root_seed": int(descriptor["root_seed"]),
            "seed_derivation": str(descriptor["seed_derivation"]),
            "generator": str(descriptor["generator"]), "seats_per_root": 1}


def _strength_of(source):
    match = re.search(r"P7C_STRENGTH\s*=\s*([0-9]+)", source or "")
    return int(match.group(1)) if match else None


def _strength_source(strength):
    """带强度标记的种子源码（同一牌效逻辑 + 一行常量）。"""

    from hangma_bot.policy import action_value_seeds as seeds

    lines = seeds.EFFICIENCY_SEED.source.splitlines()
    return "\n".join(lines[:2] + ["P7C_STRENGTH = {0}".format(int(strength))]
                      + lines[2:])


def _patch_seed(monkeypatch, strength):
    """把 efficiency_seed 换成带强度标记的变体源码（同一牌效逻辑）。"""

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
        is_candidate = str(getattr(policy, "policy_id", "")).startswith("action_value")
        strength = _strength_of(getattr(getattr(policy, "_scorer", None), "source", "")) \
            if is_candidate else None
        self.calls.append({"table_id": str(plan.table_id)})
        focal = float(strength) if strength is not None else -10.0
        others = iter((5.0, 3.0, 1.0))
        scores = [focal if seat == focal_idx else next(others) for seat in range(4)]
        return {"table_id": plan.table_id, "seed": int(plan.seed),
                "match_status": "complete", "wall_ms": 1.0,
                "scores_by_seat": scores, "result": {}}


class FamilyEvalStub:
    """替身**家族条件评价执行器**（0 真实桌赛）。

    与真实执行器同一记账口径（1 次条件评价 = tables_full 4.0，先预留后结算、
    同一共享账本），证据强弱由候选源码的 P7C_STRENGTH 标记决定：

    - 缺失根项（item.root_ids 非空）→ 复现点名的根（真实执行器按根复现同一牌山）；
    - 声明项（未物化）→ 按 (子场景 × 情景 × 面板种子) 产出确定性根。
    """

    def __init__(self):
        self.calls = []

    def __call__(self, *, state, run_root, ledger, authorization, item, source,
                 test_runtime_factory=None):
        sub = str(item["sub_scenario"])
        mix = str(item["opponent_mix"])
        seed = int(item["panel_seed"])
        if item.get("root_ids"):
            roots = [str(value) for value in item["root_ids"]]
        else:
            roots = [_fam_root(sub, mix, DECL_INDEX[(mix, seed)], seed)]
        step_id = "{0}:tables-full".format(
            search._av_family_step_prefix(str(item["candidate_id"]), sub,
                                          str(item["token"])))
        reservation = ledger.reserve(step_id=step_id, account="tables_full",
                                     amount=4.0, note="替身家族条件评价（先预留）")
        ledger.settle(reservation, actual=4.0,
                      note="替身家族条件评价实跑 4 桌（替身：0 真实桌赛）")
        strength = _strength_of(source.get("source")) or STRENGTH_INCUMBENT
        samples = [_family_sample(root, sub, mix, str(item["candidate_id"]),
                                  strength / 16.0) for root in roots]
        self.calls.append({"candidate_id": item["candidate_id"], "sub": sub,
                           "mix": mix, "panel_seed": seed, "roots": list(roots),
                           "token": item.get("token")})
        return {"ok": True, "tables_executed": 4,
                "evaluation": {
                    "ok": True,
                    "identity": {"candidate_id": item["candidate_id"],
                                 "opponent_mix": mix},
                    "panel": {"predicate": sub, "panel_seed": seed,
                              "tables_full_executed": 4},
                    "samples": samples,
                    "execution_kind": "real_runtime",
                    "real_table_instances": 4,
                    "result_admission": {"ok": True}},
                "reason": ""}


def _family_sample(root, sub, mix, cid, d, *, cost=1.0):
    """真实形状的家族条件评价样本（双臂点值 U：候选 d / 基线 0）。"""

    return {"source_root_id": root, "scenario": sub, "opponent_mix": mix,
            "candidate_id": cid, "root_role": "core", "invalid": False,
            "completeness": "complete", "invalid_reasons": [], "cost": cost,
            "arms": {"baseline": {"candidate_id": search.AV_BASELINE_ID, "u": 0.0},
                     "candidate": {"candidate_id": cid, "u": float(d)}}}


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
    root = Path(tmp_path) / ("p7c-" + uuid.uuid4().hex[:6]) / "run"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _declarations():
    """本迭代声明的家族刷新批：每侧 4 条（2 情景 × 2 面板种子，H/M 各 2）。

    每条都是**显式根声明**（子场景 × 情景 × 面板种子 × 根序号）——家族根身份不含
    面板种子/情景，未锁定根序号就无法在真实副作用之前登记实例（不猜参数）。
    """

    return [{"channel": CHANNEL, "sub_scenario": sub, "opponent_mix": mix,
             "panel_seed": seed, "root_index": DECL_INDEX[(mix, seed)]}
            for sub in (SUB_OPEN, SUB_COST)
            for mix, seed in (("H", SEED_NEW), ("M", SEED_NEW),
                              ("H", SEED_OLD), ("M", SEED_OLD))]


def _declared_refresh_roots():
    """声明批物化后的根行（每侧 4 根、H/M 各 2；身份含情景与实际种子）。"""

    rows = []
    for sub in (SUB_OPEN, SUB_COST):
        for mix, seed in (("H", SEED_NEW), ("M", SEED_NEW),
                          ("H", SEED_OLD), ("M", SEED_OLD)):
            rows.append({"root_id": _fam_root(sub, mix, DECL_INDEX[(mix, seed)], seed),
                         "opponent_mix": mix, "sub_scenario": sub})
    return rows


def _normal_roots(seed=SEED_OLD, roots=2):
    return sorted(natural.natural_root_id(mix, seed, index)
                  for mix in ("H", "M") for index in range(1, roots + 1))


def _family_entry(cid, *, open_d=0.5, cost_d=0.5):
    """家族证据条目（走**生产合并器** merge_archive_entry）。"""

    subs = {SUB_OPEN: open_d, SUB_COST: cost_d}
    samples = []
    # R9/A2：每（侧 × 情景）是一个**独立的根**（身份含情景与实际种子）。
    for sub, mix, index in CORE_CELLS:
        samples.append(_family_sample(_fam_root(sub, mix, index), sub, mix, cid,
                                      subs[sub]))
    return sa.merge_archive_entry(None, cid, samples, safety="PASS")


def _normal_entry(cid, d=0.5, seed=SEED_OLD, roots=2):
    return sa.merge_archive_entry(
        None, cid, [_normal_sample(root, "H" if "-H-" in root else "M", cid, d)
                    for root in _normal_roots(seed, roots)], safety="PASS")


def _seed_chain(run_root, *, cost_roots_registered=True):
    """预置在案档案 + 正常 epoch + 家族 epoch 1 + 家族根台账（模拟前序迭代已提交）。"""

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
    # R9/A2/A3：核心 epoch 与台账一律用**完整根身份**（每（侧 × 情景）一个根，
    # 行里带实际执行种子与派生记号）；旧 schema/旧身份由实现显式拒绝继承。
    core = []
    ledger_roots = []
    for sub, mix, index in CORE_CELLS:
        root_id = _fam_root(sub, mix, index)
        descriptor = search.av_family_root_descriptor(
            prefix_source="scripted_fixture", sub_scenario=sub, opponent_mix=mix,
            panel_seed=SEED_OLD, root_index=index)
        core.append({"root_id": root_id, "opponent_mix": mix, "sub_scenario": sub})
        if sub == SUB_COST and not cost_roots_registered:
            continue  # 负例：代价侧根未登记复现参数 → 补根不可调度
        ledger_roots.append({
            "root_id": root_id, "channel": CHANNEL, "sub_scenario": sub,
            "opponent_mix": mix, "panel_seed": SEED_OLD, "root_index": index,
            "root_seed": int(descriptor["root_seed"]),
            "seed_derivation": str(descriptor["seed_derivation"]),
            "generator": str(descriptor["generator"]),
            "seats_per_root": 1, "source": "前序迭代条件评价"})
    family_epochs = {"schema": search.AV_FAMILY_EPOCHS_SCHEMA,
                     "channels": {CHANNEL: sa.build_channel_epoch(CHANNEL, core)}}
    _write_json(archive_dir / "family-epochs.json", family_epochs)
    _write_json(archive_dir / "family-roots.json",
                {"schema": search.AV_FAMILY_ROOTS_SCHEMA,
                 "channels": {CHANNEL: {"roots": ledger_roots}}})
    # 前序迭代的候选产物（在案席者的候选源码）：家族阶段 2 要按**该身份**重评
    # 刷新根，源码只能从运行链上的生成产物取（_av_refresh_participant_source 的
    # 同一判据：在案摘要必须逐字自洽）。
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
        "plan": {"predicate": SUB_OPEN, "opponent": "H", "panel_seed": SEED_OLD,
                 "prefix_source": "scripted_fixture"}})
    return {"incumbent": incumbent, "overall": overall}


def _evolve(run_root, monkeypatch, *, strength=STRENGTH_CHALLENGER, token=TOKEN,
            driver=None, stub=None, declarations=None, **kwargs):
    _patch_seed(monkeypatch, strength)
    monkeypatch.setattr(natural, "execute_natural_table", driver or StrengthDrive(),
                        raising=True)
    monkeypatch.setattr(search, "_av_family_execute_evaluation", stub or FamilyEvalStub(),
                        raising=True)
    return search.run_av_evolution(
        run_root, generation_mode="mock", seed_name="efficiency_seed",
        predicate=SUB_OPEN, opponent="H", panel_seed=SEED_OLD,
        natural_roots=2, natural_seats=1, authorization=token,
        family_channel=CHANNEL,
        family_refresh=(declarations if declarations is not None
                        else _declarations()), **kwargs)


# =====================================================================
# 1 · 家族根登记 与 家族 epoch 建立
# =====================================================================


def test_p7c_family_promotion_cost_registry_is_explicit():
    """设计条款：家族晋升评价成本口径必须以**代码常量与登记表**显式表达。"""

    cost = getattr(search, "AV_FAMILY_PROMOTION_COST", None)
    assert isinstance(cost, dict) and cost, (
        "家族晋升评价成本必须有显式登记表（AV_FAMILY_PROMOTION_COST）")
    assert cost["tables_per_evaluation"] == 4.0, cost
    assert cost["seat_complete_tables"] == 32, cost            # 8 根 × 4 桌
    assert cost["cross_iteration_side_fill_tables"] == 16, cost  # 补另一侧 4 根
    assert cost["phase1_tables"] == 32, cost                   # 挑战者补通道当前根
    assert cost["phase2_tables"] == 64, cost                   # 刷新批 4+4 根 × 2 参与者
    assert cost["promotion_cap_tables"] == 96, cost
    assert cost["promotion_cap_tables"] == cost["phase1_tables"] + cost["phase2_tables"]
    assert cost["refresh_roots_per_side"] == 4, cost           # §9.2 家族每子场景 4 根
    # 逐项口径自洽：桌数 = 根数 × 每评价桌数
    assert cost["phase2_tables"] == 2 * 8 * cost["tables_per_evaluation"]
    assert cost["seat_complete_tables"] == 8 * cost["tables_per_evaluation"]


def test_p7c_family_epoch_established_from_two_sided_roots(tmp_path, monkeypatch):
    """家族根登记 → 家族 epoch 建立（两侧齐备 + H/M 齐备才建；缺即输入缺口）。"""

    run_root = _run_root(tmp_path)
    archive_dir = run_root / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    # R9/A1：建立 epoch 的判据是**逐格配额**（每（侧 × 情景）2 个核心根）：
    # 这里给出完整 8 根核心矩阵（旧用例只给 4 根、且 H/M 共用同一个根名）。
    _write_json(archive_dir / "family-roots.json",
                {"schema": search.AV_FAMILY_ROOTS_SCHEMA,
                 "channels": {CHANNEL: {"roots": [
                     _family_root_row(SUB_OPEN, "H", 2),
                     _family_root_row(SUB_OPEN, "H", 5),
                     _family_root_row(SUB_OPEN, "M", 7),
                     _family_root_row(SUB_OPEN, "M", 9),
                     _family_root_row(SUB_COST, "H", 0),
                     _family_root_row(SUB_COST, "H", 10),
                     _family_root_row(SUB_COST, "M", 8),
                     _family_root_row(SUB_COST, "M", 11)]}}})
    result = _evolve(run_root, monkeypatch, declarations=[])
    assert result.get("terminal") == "ITERATION_COMPLETE", result
    epochs = _read_json(archive_dir / "family-epochs.json")
    epoch = epochs["channels"][CHANNEL]
    assert epoch["channel"] == CHANNEL and epoch["epoch"] == 1, epoch
    assert {row["sub_scenario"] for row in epoch["roots"]} == {SUB_OPEN, SUB_COST}
    assert {row["opponent_mix"] for row in epoch["roots"]} == {"H", "M"}
    # R9/A1：epoch 的核心根集 = **冻结核心清单**逐格配额（每侧 × H/M 各 2 根 = 8）。
    assert len(epoch["roots"]) == 8, epoch["roots"]
    counts = {}
    for row in epoch["roots"]:
        key = (row["sub_scenario"], row["opponent_mix"])
        counts[key] = counts.get(key, 0) + 1
    assert set(counts) == {(SUB_OPEN, "H"), (SUB_OPEN, "M"),
                           (SUB_COST, "H"), (SUB_COST, "M")}, counts
    assert sorted(counts.values()) == [2, 2, 2, 2], counts
    # 根台账（与 overall 同构）：家族根随运行链累积落盘。
    ledger = _read_json(archive_dir / "family-roots.json")
    assert CHANNEL in ledger["channels"], ledger


def test_p7c_family_epoch_gap_when_one_side_missing(tmp_path, monkeypatch):
    """缺一侧不建 epoch：如实记输入缺口，不填零争席、不建不完整根集。"""

    run_root = _run_root(tmp_path)
    archive_dir = run_root / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    _write_json(archive_dir / "family-roots.json",
                {"schema": search.AV_FAMILY_ROOTS_SCHEMA,
                 "channels": {CHANNEL: {"roots": [
                     _family_root_row(SUB_OPEN, "H", 2),
                     _family_root_row(SUB_OPEN, "H", 5),
                     _family_root_row(SUB_OPEN, "M", 7),
                     _family_root_row(SUB_OPEN, "M", 9)]}}})
    result = _evolve(run_root, monkeypatch, declarations=[])
    assert result.get("terminal") == "ITERATION_COMPLETE", result
    assert not (archive_dir / "family-epochs.json").is_file(), "缺一侧不得建 epoch"
    state = search.av_state_load(search.av_latest_state_path(run_root))
    gaps = " ".join(state.get("input_gaps") or [])
    assert "family_channel_epoch_incomplete" in gaps, state.get("input_gaps")


# =====================================================================
# 2 · 家族席晋升（核心验收）与两侧门槛
# =====================================================================


def test_p7c_family_seat_flips_for_stronger_two_sided_challenger(tmp_path, monkeypatch):
    """核心验收：两侧齐备且证据更强的挑战者 → 家族席**翻动**、家族 epoch +1。"""

    run_root = _run_root(tmp_path)
    seeded = _seed_chain(run_root)
    archive_before = _read_json(run_root / "archive" / "av-archive.json")
    epoch_before = _read_json(run_root / "archive" / "family-epochs.json")
    stub = FamilyEvalStub()
    result = _evolve(run_root, monkeypatch, stub=stub)
    assert result.get("terminal") == "ITERATION_COMPLETE", result
    state = search.av_state_load(search.av_latest_state_path(run_root))
    challenger = state["identity"]["candidate_id"]
    assert challenger != seeded["incumbent"]

    archive_after = _read_json(run_root / "archive" / "av-archive.json")
    epochs_after = _read_json(run_root / "archive" / "family-epochs.json")
    # —— 家族席翻动（本包核心验收项）——
    assert archive_after["slots"][CHANNEL] == [challenger], archive_after["slots"]
    assert archive_after["slots"][CHANNEL] != archive_before["slots"][CHANNEL]
    # —— 原子换家族 epoch：旧根是新根集前缀，刷新根入根集且不流入确认集 ——
    epoch_before_rows = epoch_before["channels"][CHANNEL]["roots"]
    epoch_after = epochs_after["channels"][CHANNEL]
    assert epoch_after["epoch"] == epoch_before["channels"][CHANNEL]["epoch"] + 1
    assert [row["root_id"] for row in epoch_after["roots"]][:len(epoch_before_rows)] == \
        [row["root_id"] for row in epoch_before_rows]
    assert len(epoch_after["roots"]) == len(epoch_before_rows) + 8
    assert all(row["confirmation_eligible"] is False
               for row in epoch_after["roots"][-8:])
    # —— 两侧齐备：挑战者在机会/代价两侧都有根证据 ——
    family = archive_after["entries"][challenger]["family"][CHANNEL]
    assert family["complete"] is True, family
    assert family["open_value"] is not None and family["cost_value"] is not None
    # —— 家族补根确实执行（不是"没接线"）：声明批 8 + 阶段 1 四条 + 阶段 2 八条 ——
    assert len(stub.calls) == 20, stub.calls
    assert state["family_fill"]["outcome"]["status"] == "committed"
    assert state["family_fill"]["outcome"]["epoch_after"] == epoch_after["epoch"]


def test_p7c_family_candidate_with_one_side_is_not_seated(tmp_path, monkeypatch):
    """负例：只有一侧证据（另一侧补根不可调度）→ **不入席**，原席原 epoch 保持。"""

    run_root = _run_root(tmp_path)
    seeded = _seed_chain(run_root, cost_roots_registered=False)
    epoch_before = _read_json(run_root / "archive" / "family-epochs.json")
    stub = FamilyEvalStub()
    result = _evolve(run_root, monkeypatch, stub=stub)
    assert result.get("terminal") == "ITERATION_COMPLETE", result
    state = search.av_state_load(search.av_latest_state_path(run_root))
    challenger = state["identity"]["candidate_id"]
    archive_after = _read_json(run_root / "archive" / "av-archive.json")
    epochs_after = _read_json(run_root / "archive" / "family-epochs.json")
    # 原席与原 epoch 保持（代价侧**通道根**复现参数未登记 → 补根不可调度）。
    assert archive_after["slots"][CHANNEL] == [seeded["incumbent"]]
    assert epochs_after["channels"][CHANNEL] == epoch_before["channels"][CHANNEL]
    # 挑战者在机会侧补齐了通道根，代价侧**一个通道根都拿不到** → 两侧不齐备、不入席。
    cells = archive_after["entries"][challenger]["family_evaluations"]
    assert COST_ROOT not in {key.split("|")[-1] for key in cells.get(SUB_COST, {})}, \
        cells.get(SUB_COST)
    assert OPEN_ROOT in {key.split("|")[-1] for key in cells.get(SUB_OPEN, {})}, \
        cells.get(SUB_OPEN)
    assert challenger not in archive_after["slots"][CHANNEL]
    assert challenger in archive_after["entries"]
    assert state["stop_reason"].startswith("family_refresh_"), state["stop_reason"]
    assert state["family_fill"]["outcome"]["status"] in (
        "unschedulable", "evidence_incomplete", "budget_insufficient")


# =====================================================================
# 3 · 事务一致性：预算不足 / 保原席 / 逐实例对账
# =====================================================================


def test_p7c_family_budget_short_keeps_seat_and_epoch(tmp_path, monkeypatch):
    """家族补根预算不足 → 保原席原 epoch、零家族评价桌数（早于费用）。"""

    run_root = _run_root(tmp_path)
    seeded = _seed_chain(run_root)
    epoch_before = _read_json(run_root / "archive" / "family-epochs.json")
    token = dict(TOKEN, budgets=dict(TOKEN["budgets"], tables_full=40))
    stub = FamilyEvalStub()
    result = _evolve(run_root, monkeypatch, token=token, stub=stub)
    assert result.get("terminal") == "ITERATION_COMPLETE", result
    archive_after = _read_json(run_root / "archive" / "av-archive.json")
    epochs_after = _read_json(run_root / "archive" / "family-epochs.json")
    assert archive_after["slots"][CHANNEL] == [seeded["incumbent"]]
    assert epochs_after["channels"][CHANNEL] == epoch_before["channels"][CHANNEL]
    # 家族评价一张桌都不跑（预算门先拒，早于费用）；迭代自身的条件/自然面板照跑。
    assert stub.calls == [], stub.calls
    state = search.av_state_load(search.av_latest_state_path(run_root))
    cid12 = state["identity"]["candidate_id"][:12]
    ledger = search.ActionValueLedger.load(run_root / "av-ledger.json")
    family_rows = [row for row in ledger.reservations
                   if str(row["step_id"]).startswith("evaluate:{0}:".format(cid12))
                   and str(row["step_id"]).count(":") >= 3]
    assert family_rows == [], family_rows          # 零家族补根账行
    assert state["stop_reason"] == "family_refresh_budget_insufficient_old_seats_kept"


def test_p7c_family_fill_is_resumable_and_charges_once(tmp_path, monkeypatch):
    """家族补根可续跑：逐实例最多完成一次、不重复计费、可推进到家族席翻动。"""

    run_root = _run_root(tmp_path)
    _seed_chain(run_root)
    first = FamilyEvalStub()

    def boom(*, state, run_root, ledger, authorization, item, source,
             test_runtime_factory=None):
        if len(first.calls) >= 3:      # 第 4 次家族评价前"进程被杀"
            raise RuntimeError("P7c 注入：家族补根中途进程中止")
        return first(state=state, run_root=run_root, ledger=ledger,
                     authorization=authorization, item=item, source=source,
                     test_runtime_factory=test_runtime_factory)

    with pytest.raises(RuntimeError):
        _evolve(run_root, monkeypatch, stub=boom)
    # 被杀后：家族评价账行与实例台账保留（在途预留保守结算；实例不冒充完成）。
    killed_calls = list(first.calls)
    assert killed_calls, "中断前应已执行过家族条件评价"
    ledger_mid = search.ActionValueLedger.load(run_root / "av-ledger.json")
    spent_mid = ledger_mid.spent("tables_full")

    resume_stub = FamilyEvalStub()
    monkeypatch.setattr(search, "_av_family_execute_evaluation", resume_stub,
                        raising=True)
    run_id = search.av_state_load(search.av_latest_state_path(run_root))["run_id"]
    resumed = search.run_av_machine_resume(run_root, run_id=run_id,
                                           authorization=TOKEN)
    state_after = search.av_state_load(search.av_latest_state_path(run_root))
    assert state_after["status"] == "ITERATION_COMPLETE", (resumed,
                                                           state_after["status"])
    # ① 不重复计费：同一 (身份 × 子场景 × 选择集) 的账行只有一条且已结算。
    ledger_after = search.ActionValueLedger.load(run_root / "av-ledger.json")
    family_rows = [row for row in ledger_after.reservations
                   if str(row["step_id"]).startswith("evaluate:")]
    step_ids = [row["step_id"] for row in family_rows]
    assert len(step_ids) == len(set(step_ids)), step_ids
    assert all(row["status"] == "settled" for row in ledger_after.reservations)
    assert ledger_after.spent("tables_full") >= spent_mid
    # ② 逐实例对账：同一实例最多一条 completed（不重复评价同一实例）。
    instances = _read_json(run_root / "instances.json")["instances"]
    for key, row in instances.items():
        done = [item for item in (row.get("attempts") or [])
                if item.get("status") == "completed"]
        assert len(done) <= 1, (key, row)
    # ③ 恢复后仍能推进到家族席翻动。
    challenger = state_after["identity"]["candidate_id"]
    archive_after = _read_json(run_root / "archive" / "av-archive.json")
    assert archive_after["slots"][CHANNEL] == [challenger]
    assert resume_stub.calls, resume_stub.calls


# =====================================================================
# 4 · 与 overall 通道互不干扰 与 8 席不变量
# =====================================================================


def test_p7c_family_channel_does_not_disturb_overall_channel(tmp_path, monkeypatch):
    """家族通道的 epoch/根集变动不影响 overall 席位、正常 epoch 与整体证据。"""

    run_root = _run_root(tmp_path)
    seeded = _seed_chain(run_root)
    archive_before = _read_json(run_root / "archive" / "av-archive.json")
    normal_before = _read_json(run_root / "archive" / "normal-epoch.json")
    result = _evolve(run_root, monkeypatch)
    assert result.get("terminal") == "ITERATION_COMPLETE", result
    state = search.av_state_load(search.av_latest_state_path(run_root))
    challenger = state["identity"]["candidate_id"]
    archive_after = _read_json(run_root / "archive" / "av-archive.json")
    normal_after = _read_json(run_root / "archive" / "normal-epoch.json")
    # overall 席位与正常 epoch 逐字不变（家族换 epoch 不牵动正常通道）。
    assert archive_after["slots"]["overall"] == archive_before["slots"]["overall"]
    assert normal_after == normal_before
    # 原席者的 overall 证据不被家族补根改写（不混通道证据）。
    assert (archive_after["entries"][seeded["overall"]]["normal_evaluations"]
            == archive_before["entries"][seeded["overall"]]["normal_evaluations"])
    # 家族席确实翻动（本用例的另一半：家族通道自己动）。
    assert archive_after["slots"][CHANNEL] == [challenger]


def test_p7c_eight_seat_invariant_after_family_wiring(tmp_path, monkeypatch):
    """总览不变量：家族接线后 8 席结构仍满足合同（2 overall / 4 家族 / 2 探索）。"""

    run_root = _run_root(tmp_path)
    _seed_chain(run_root)
    result = _evolve(run_root, monkeypatch)
    assert result.get("terminal") == "ITERATION_COMPLETE", result
    archive = _read_json(run_root / "archive" / "av-archive.json")
    assert set(archive["slots"]) == {"overall", CHANNEL, "chain", "four_white",
                                     "baotou", "exploration"}, sorted(archive["slots"])
    for channel, capacity in sa.SLOT_CAPACITY.items():
        assert len(archive["slots"][channel]) <= capacity, (channel,
                                                            archive["slots"][channel])
    seated = [cid for ids in archive["slots"].values() for cid in ids]
    assert len(set(seated)) == len(seated) <= sum(sa.SLOT_CAPACITY.values()) == 8
    assert archive["slots"]["overall"], "整体席不得因家族接线而清空"


# =====================================================================
# 5 · 家族证据格键（同一根身份跨对手情景是两个真实实例）
# =====================================================================


def test_p7c_family_evidence_cells_keep_mixes_apart():
    """实测形状：夹具路由 branch_open 的 H/M 同命中 root002（同 id 不同情景）。

    两个情景是同一根身份下的两个真实实例：合并后两个情景都必须留下证据
    （旧行为按 root_id 单键 → 后者覆盖前者 → 家族两侧/两情景永远无法齐备）。
    """

    cid = "cand"
    samples = [_family_sample(_fam_root(SUB_OPEN, "H", 2), SUB_OPEN, "H", cid, 1.0),
               _family_sample(_fam_root(SUB_OPEN, "M", 7), SUB_OPEN, "M", cid, 0.0),
               _family_sample(_fam_root(SUB_COST, "H", 0), SUB_COST, "H", cid, 1.0),
               _family_sample(_fam_root(SUB_COST, "M", 8), SUB_COST, "M", cid, 1.0)]
    entry = sa.merge_archive_entry(None, cid, samples, safety="PASS")
    mixes = {record["opponent_mix"]
             for rows in entry["family_evaluations"].values()
             for record in rows.values()}
    assert mixes == {"H", "M"}, entry["family_evaluations"]
    assert entry["family"][CHANNEL]["complete"] is True, entry["family"][CHANNEL]
    side = sa.family_side_status(entry, CHANNEL)
    assert side["complete"] is True and side["open"]["mixes"] == ["H", "M"], side
    assert side["open"]["n_roots"] == 2 and side["cost"]["n_roots"] == 2, side


def test_p7c_family_refresh_batch_verdict_is_honest():
    """家族刷新批复核：每侧 4 根、H/M 各 2；不足即明确不可提交（不静默放行）。"""

    good = _declared_refresh_roots()
    verdict = sa.family_refresh_batch_verdict(CHANNEL, good)
    assert verdict["ok"] is True, verdict
    assert verdict["by_sub"][SUB_OPEN] == {"H": 2, "M": 2}, verdict
    short = [row for row in good if row["sub_scenario"] != SUB_COST]
    bad = sa.family_refresh_batch_verdict(CHANNEL, short)
    assert bad["ok"] is False and "4 根" in bad["reason"], bad
