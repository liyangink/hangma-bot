# -*- coding: utf-8 -*-
"""S2 专属测试（R8 修复轮）：A1 家族首次初始化 + A2 指定家族根贯穿（复审 §4）。

复审依据：R7-REPAIR-REREVIEW-2026-09-17 §4 A1（P1）/ A2（P1），固定版本 bb954580。
本文件是 S2 的**专属测试**，只覆盖本包两条缺陷与承接 S1 残留的家族根种子派生：

  A1 · 家族通道首次初始化不可达
      反例：无家族 epoch + 已有证据不足时，家族提交**先返回 epoch_incomplete**，
      已声明的 family_refresh（八格）**声明解析次数为 0**，不会进入补根 →
      首个家族通道永远建不起来。修复后：没有 epoch 时**先校验并执行已声明的核心格
      补齐**，达到要求（两侧 × H/M 齐备）后再建立首席（epoch 1 + 首个家族席）。
  A2 · 指定家族根没有传到条件执行器
      反例：家族评价调用未传 root_indexes、run_av_evaluation 没有选根参数、
      结果消费取 scenarios[0] → **先跑错根（首命中根）再按根身份拒绝并丢弃 4 桌**。
      修复后：把冻结的根选择（根序号 + 根种子）贯穿到**前缀执行器**，只启动目标任务，
      并校验根内容摘要。
  附带上界（承接 S1 残留 ④）· 家族根种子派生
      root_seed 原为空 → 家族实例键缺"随机映射"一维、跨种子不可验证。修复后：
      与自然根同口径的确定性派生，并纳入家族根台账与实例身份键。

全部离线：mock 生成 + 夹具条件面板 + 替身家族条件评价执行器（A1 端到端）+ 替身桌赛
驱动；零真实桌赛、零 LLM 调用、不消耗任何授权账目（账面照记，便于核对不重不漏）。
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
import sitin_stage as stage  # noqa: E402
from hangma_bot.policy import action_value_seeds as seeds  # noqa: E402

#: 批次 7 授权令牌 + 账户额度（替身执行：0 真实桌赛，账面照记以便核对）。
TOKEN = {"authorized": True, "batch": 7,
         "budgets": {"tokens_input": 100000, "tokens_output": 200000,
                     "tables_full": 256, "tables_partial": 64,
                     "prefix_generation": 64}}

CHANNEL = "branch"
SUB_OPEN = "branch_open"
SUB_COST = "branch_cost"
SEED_A = 11
SEED_B = 12

#: 夹具路由下 branch_open 的**首命中根序号**：模板序列 = (pair_wait FALSE,
#: draw_unknown UNKNOWN, peng_branch TRUE)，即 idx%3==2 才命中 → 首命中根是 root002。
FIRST_HIT_INDEX = 2
#: 非首命中根（idx%3==2，命中同一谓词但不是首命中根）。
OTHER_HIT_INDEX = 5
THIRD_HIT_INDEX = 8
#: 越界根序号（根身份渲染成三位字段 rootNNN，越界即身份漂移）。
OUT_OF_RANGE_INDEX = 1000

STRENGTH_FIRST = 8          # 首席（首个家族席）证据强度 d = 8/16
STRENGTH_STRONGER = 12      # 更强挑战者
STRENGTH_WEAKER = 4         # 更弱挑战者（挑战失败保留原席）


def _family_generator(prefix_source="scripted_fixture"):
    """前缀来源 → 生成器记号（与实现同一映射点）。"""

    return str(search.av_family_generator_of(prefix_source))


def _fam_root(sub, index, mix="H", seed=SEED_A, prefix_source="scripted_fixture"):
    """家族根身份（R9/A2：**完整身份**——生成器 × 子场景 × 情景 × 实际种子 × 序号）。

    越界序号（对照运行）走 stage 原语直接渲染：生产描述符本身就会拒绝越界，本助手
    要能把"越界身份"交给被测入口去拒绝，而不是在夹具里提前抛错。
    """

    try:
        return str(search.av_family_root_id(prefix_source=prefix_source,
                                            sub_scenario=sub, opponent_mix=mix,
                                            panel_seed=seed, root_index=index))
    except ValueError:
        return str(stage.root_identity(generator=_family_generator(prefix_source),
                                       sub_scenario=sub, opponent_mix=mix,
                                       panel_seed=seed, root_index=index))


def _strength_source(strength):
    """带强度标记的候选源码（同一牌效逻辑 + 一行常量）。"""

    lines = seeds.EFFICIENCY_SEED.source.splitlines()
    return "\n".join(lines[:2] + ["S2_STRENGTH = {0}".format(int(strength))]
                     + lines[2:])


def _strength_of(source):
    match = re.search(r"S2_STRENGTH\s*=\s*([0-9]+)", source or "")
    return int(match.group(1)) if match else None


def _patch_seed(monkeypatch, strength):
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
    """替身**家族条件评价执行器**（0 真实桌赛；只在本包 A1 端到端里使用）。

    与真实执行器同一记账口径（1 次条件评价 = tables_full 4.0，先预留后结算、同一
    共享账本），并复现工作项**点名的那一个根**（item.root_ids = 冻结的根身份）；
    同时按真实执行器的契约带根选择标记与根内容摘要（A2 的摘要校验据此生效）。
    """

    def __init__(self, strength):
        self.calls = []
        self.strength = int(strength)

    def __call__(self, *, state, run_root, ledger, authorization, item, source,
                 test_runtime_factory=None):
        sub = str(item["sub_scenario"])
        mix = str(item["opponent_mix"])
        seed = int(item["panel_seed"])
        index = int((item.get("root_indexes") or [0])[0])
        roots = [str(value) for value in item["root_ids"]]
        step_id = "{0}:tables-full".format(
            search._av_family_step_prefix(str(item["candidate_id"]), sub,
                                          str(item["token"])))
        reservation = ledger.reserve(step_id=step_id, account="tables_full",
                                     amount=4.0, note="替身家族条件评价（先预留）")
        ledger.settle(reservation, actual=4.0,
                      note="替身家族条件评价实跑 4 桌（替身：0 真实桌赛）")
        strength = _strength_of(source.get("source")) or self.strength
        requirement = _requirement_digest(
            prefix_source=str(item.get("prefix_source") or "scripted_fixture"),
            predicate=sub, opponent_mix=mix, panel_seed=seed, root_index=index)
        samples = [_family_sample(root, sub, mix, str(item["candidate_id"]),
                                  strength / 16.0,
                                  root_requirement_digest=requirement,
                                  root_content_digest=requirement + ":stub")
                   for root in roots]
        self.calls.append({"candidate_id": item["candidate_id"], "sub": sub,
                           "mix": mix, "panel_seed": seed, "roots": list(roots),
                           "root_indexes": list(item.get("root_indexes") or ()),
                           "token": item.get("token")})
        return {"ok": True, "tables_executed": 4,
                "evaluation": {
                    "ok": True,
                    "identity": {"candidate_id": item["candidate_id"],
                                 "opponent_mix": mix},
                    "panel": {"predicate": sub, "panel_seed": seed,
                              "tables_full_executed": 4},
                    "root_selection": {"selector": "conditional_root",
                                       "indexes": [index], "root_ids": list(roots)},
                    "samples": samples,
                    "execution_kind": "real_runtime",
                    "real_table_instances": 4,
                    "result_admission": {"ok": True}},
                "reason": ""}


def _family_sample(root, sub, mix, cid, d, *, cost=1.0, **extra):
    """真实形状的家族条件评价样本（双臂点值 U：候选 d / 基线 0）。"""

    sample = {"source_root_id": root, "scenario": sub, "opponent_mix": mix,
              "candidate_id": cid, "root_role": "core", "invalid": False,
              "completeness": "complete", "invalid_reasons": [], "cost": cost,
              "arms": {"baseline": {"candidate_id": search.AV_BASELINE_ID, "u": 0.0},
                       "candidate": {"candidate_id": cid, "u": float(d)}}}
    sample.update(extra)
    return sample


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + chr(10),
                    encoding="utf-8")


def _run_root(tmp_path):
    root = Path(tmp_path) / ("s2-" + uuid.uuid4().hex[:6]) / "run"
    root.mkdir(parents=True, exist_ok=True)
    return root


#: 声明批的根序号：同情景不同种子给不同序号（与真实路由"不同种子命中不同尝试
#: 序号"同形），全部落在 0..99 的合法区间内。
DECL_INDEX = {("H", SEED_A): 3, ("M", SEED_A): 4, ("H", SEED_B): 5, ("M", SEED_B): 6}
#: 第二次挑战的**新鲜**刷新批序号（§9.2：刷新根必须是 epoch 根集之外的新根；
#: 复用已在案 epoch 的根会被 family_refresh_batch_verdict 判 batch_invalid）。
DECL_INDEX_FRESH = {("H", SEED_A): 13, ("M", SEED_A): 14,
                    ("H", SEED_B): 15, ("M", SEED_B): 16}


def _declarations(*, sides=(SUB_OPEN, SUB_COST), index_map=None):
    """开轮声明的家族刷新批：每侧 4 条（2 情景 × 2 面板种子，H/M 各 2）。

    每条都是**显式根声明**（子场景 × 情景 × 面板种子 × 根序号）。
    """

    index_map = DECL_INDEX if index_map is None else index_map
    return [{"channel": CHANNEL, "sub_scenario": sub, "opponent_mix": mix,
             "panel_seed": seed, "root_index": index_map[(mix, seed)]}
            for sub in sides
            for mix, seed in (("H", SEED_A), ("M", SEED_A),
                              ("H", SEED_B), ("M", SEED_B))]


def _declared_cells(declarations):
    return sorted({(row["sub_scenario"], row["opponent_mix"], row["panel_seed"],
                    row["root_index"]) for row in declarations})


def _evolve(run_root, monkeypatch, *, strength=STRENGTH_FIRST, token=TOKEN,
            driver=None, stub=None, declarations=None, **kwargs):
    _patch_seed(monkeypatch, strength)
    monkeypatch.setattr(natural, "execute_natural_table", driver or StrengthDrive(),
                        raising=True)
    monkeypatch.setattr(search, "_av_family_execute_evaluation",
                        stub or FamilyEvalStub(strength), raising=True)
    return search.run_av_evolution(
        run_root, generation_mode="mock", seed_name="efficiency_seed",
        predicate=SUB_OPEN, opponent="H", panel_seed=SEED_A,
        natural_roots=2, natural_seats=1, authorization=token,
        family_channel=CHANNEL,
        family_refresh=(declarations if declarations is not None
                        else _declarations()), **kwargs)


# =====================================================================
# A1 · 家族通道首次初始化（空通道 → 首个家族席）
# =====================================================================


def test_a1_first_epoch_arrays_declarations_before_epoch_incomplete(tmp_path, monkeypatch):
    """复审 A1 纯数据反例：无 epoch 时**先解析已声明批**，不得先返回 epoch_incomplete。

    反例（修复前）：声明八格、声明解析次数 0、status=epoch_incomplete、不进补根。
    修复后：先校验声明并给出补根驱动状态（pending / phase=epoch_core_fill），
    由补根层执行已声明的核心格；补齐后才建 epoch。
    """

    run_root = _run_root(tmp_path)
    iter_dir = run_root / "iterations" / "iter-01"
    iter_dir.mkdir(parents=True, exist_ok=True)
    declarations = _declarations()
    state = {"run_id": "s2-a1", "iteration_no": 1, "iter_dir": str(iter_dir),
             "identity": {"candidate_id": "cand-A"},
             "candidate_source": _strength_source(STRENGTH_FIRST),
             "plan": {"family_channel": CHANNEL, "family_refresh": declarations}}
    calls = []
    original = search._av_family_declarations

    def spy(state_, channel):
        calls.append(channel)
        return original(state_, channel)

    monkeypatch.setattr(search, "_av_family_declarations", spy, raising=True)
    outcome = search._av_commit_family(dict(state), run_root, attempt_refresh=True)
    assert calls == [CHANNEL], (
        "无家族 epoch 时必须**先解析**已声明批（复审 A1：解析次数不得为 0）")
    assert outcome["status"] == "pending", outcome
    assert outcome.get("phase") == "epoch_core_fill", outcome
    assert len(outcome.get("unmaterialized") or ()) == len(declarations), outcome
    # 尚未补齐：不得建 epoch、不得预塞家族席。
    assert not (run_root / "archive" / "family-epochs.json").is_file()
    archive = _read_json(run_root / "archive" / "av-archive.json")
    assert archive["slots"][CHANNEL] == [], archive["slots"]


def test_a1_empty_channel_reaches_first_family_seat_end_to_end(tmp_path, monkeypatch):
    """① 首个家族席：从**空家族通道**（无预置席、无 epoch、无根台账）的公开入口起。

    预置状态：仅批次 7 授权令牌常量与运行目录（**无**家族席、**无**家族 epoch、
    **无**家族根台账）。家族条件评价执行器是替身（0 真实桌赛）；声明解析、核心格
    补齐、epoch 建立与首席落位全部走生产实现。
    """

    run_root = _run_root(tmp_path)
    assert not (run_root / "archive").exists(), "本用例必须从空家族通道开始"
    result = _evolve(run_root, monkeypatch, strength=STRENGTH_FIRST)
    assert result.get("terminal") == "ITERATION_COMPLETE", result
    state = search.av_state_load(search.av_latest_state_path(run_root))
    first = state["identity"]["candidate_id"]

    epochs = _read_json(run_root / "archive" / "family-epochs.json")
    epoch = epochs["channels"][CHANNEL]
    assert epoch["epoch"] == 1, epoch
    assert {row["sub_scenario"] for row in epoch["roots"]} == {SUB_OPEN, SUB_COST}
    assert {row["opponent_mix"] for row in epoch["roots"]} == {"H", "M"}
    archive = _read_json(run_root / "archive" / "av-archive.json")
    assert archive["slots"][CHANNEL] == [first], archive["slots"]

    # —— 核心格补齐确实执行了：八条声明逐条被评价并登记为家族根 ——
    ledger = _read_json(run_root / "archive" / "family-roots.json")
    cells = {(row["sub_scenario"], row["opponent_mix"], row["panel_seed"],
              row["root_index"]) for row in ledger["channels"][CHANNEL]["roots"]}
    assert cells == set(_declared_cells(_declarations())), cells
    fill = state.get("family_fill") or {}
    kinds = [row.get("kind") for row in fill.get("attempts") or ()]
    assert kinds.count("declaration") == len(_declarations()), kinds
    assert fill["outcome"]["status"] == "established", fill["outcome"]
    assert "family" in str(state.get("stop_reason")), state.get("stop_reason")
    # —— 家族根种子派生：登记册与实例台账都要带上（承接 S1 残留 ④）——
    seeds_registered = {row["root_seed"] for row in ledger["channels"][CHANNEL]["roots"]}
    assert all(value is not None for value in seeds_registered), ledger
    assert len(seeds_registered) == len(_declared_cells(_declarations())), seeds_registered


def test_a1_second_candidate_challenge_success_flips_first_seat(tmp_path, monkeypatch):
    """②③ 第二候选挑战 → 成功结局：家族席翻动到第二候选、家族 epoch +1。"""

    run_root = _run_root(tmp_path)
    first_run = _evolve(run_root, monkeypatch, strength=STRENGTH_FIRST)
    assert first_run.get("terminal") == "ITERATION_COMPLETE", first_run
    first_state = search.av_state_load(search.av_latest_state_path(run_root))
    first = first_state["identity"]["candidate_id"]
    archive_before = _read_json(run_root / "archive" / "av-archive.json")
    assert archive_before["slots"][CHANNEL] == [first]

    second_run = _evolve(run_root, monkeypatch, strength=STRENGTH_STRONGER,
                         declarations=_declarations(index_map=DECL_INDEX_FRESH))
    assert second_run.get("terminal") == "ITERATION_COMPLETE", second_run
    second_state = search.av_state_load(search.av_latest_state_path(run_root))
    second = second_state["identity"]["candidate_id"]
    assert second != first
    archive_after = _read_json(run_root / "archive" / "av-archive.json")
    epochs_after = _read_json(run_root / "archive" / "family-epochs.json")
    assert archive_after["slots"][CHANNEL] == [second], archive_after["slots"]
    assert epochs_after["channels"][CHANNEL]["epoch"] == 2
    assert second_state["family_fill"]["outcome"]["status"] == "committed", \
        second_state["family_fill"]["outcome"]


def test_a1_second_candidate_challenge_failure_keeps_first_seat(tmp_path, monkeypatch):
    """③ 挑战失败保留结局：更弱挑战者不入席，首席与 epoch 1 都保持。"""

    run_root = _run_root(tmp_path)
    _evolve(run_root, monkeypatch, strength=STRENGTH_FIRST)
    first_state = search.av_state_load(search.av_latest_state_path(run_root))
    first = first_state["identity"]["candidate_id"]
    archive_before = _read_json(run_root / "archive" / "av-archive.json")
    epoch_before = _read_json(run_root / "archive" / "family-epochs.json")

    second_run = _evolve(run_root, monkeypatch, strength=STRENGTH_WEAKER,
                         declarations=_declarations(index_map=DECL_INDEX_FRESH))
    assert second_run.get("terminal") == "ITERATION_COMPLETE", second_run
    second_state = search.av_state_load(search.av_latest_state_path(run_root))
    second = second_state["identity"]["candidate_id"]
    assert second != first
    archive_after = _read_json(run_root / "archive" / "av-archive.json")
    epochs_after = _read_json(run_root / "archive" / "family-epochs.json")
    assert archive_after["slots"][CHANNEL] == [first], archive_after["slots"]
    assert epochs_after["channels"][CHANNEL] == epoch_before["channels"][CHANNEL]
    assert second_state["stop_reason"].startswith("family_refresh_"), \
        second_state["stop_reason"]
    assert second in archive_after["entries"], archive_after["entries"].keys()


def test_a1_declared_batch_missing_one_side_still_gaps_after_fill(tmp_path, monkeypatch):
    """负例：声明批只覆盖机会侧 → 补齐后仍缺代价侧 → 不建 epoch（如实记输入缺口）。

    与「解析次数为 0」的缺陷分开：本用例要求**声明确实被执行**（机会侧根进了
    家族根台账），只是不满足建 epoch 的条件。
    """

    run_root = _run_root(tmp_path)
    declarations = _declarations(sides=(SUB_OPEN,))
    result = _evolve(run_root, monkeypatch, strength=STRENGTH_FIRST,
                     declarations=declarations)
    assert result.get("terminal") == "ITERATION_COMPLETE", result
    assert not (run_root / "archive" / "family-epochs.json").is_file()
    ledger = _read_json(run_root / "archive" / "family-roots.json")
    rows = ledger["channels"][CHANNEL]["roots"]
    assert {row["sub_scenario"] for row in rows} == {SUB_OPEN}, rows
    assert len(rows) == len(_declared_cells(declarations)), rows
    state = search.av_state_load(search.av_latest_state_path(run_root))
    gaps = " ".join(state.get("input_gaps") or [])
    assert "family_channel_epoch_incomplete" in gaps, state.get("input_gaps")
    archive = _read_json(run_root / "archive" / "av-archive.json")
    assert archive["slots"][CHANNEL] == [], archive["slots"]


# =====================================================================
# A2 · 指定家族根贯穿到前缀执行器
# =====================================================================


def _family_root_seed(panel_seed, sub, mix, index, prefix_source="scripted_fixture"):
    """家族根种子：一律走实现的**唯一描述符**（R9/A3 起签名带前缀来源与情景）。

    R9 身份升级：根身份 = 生成器 × 子场景 × 对手情景 × 实际种子 × 根序号，执行种子
    由这五个维度派生；本助手不再保留"旧派生式"退回分支（那正是 A3 要消除的第二套
    式子）。
    """

    try:
        return int(search.av_family_root_seed(prefix_source=prefix_source,
                                              sub_scenario=sub, opponent_mix=mix,
                                              panel_seed=panel_seed,
                                              root_index=index))
    except ValueError:
        # 越界序号（对照运行）：直接走 stage 原语取值，把"越界身份"交给被测入口拒绝。
        return int(stage.root_seed(generator=_family_generator(prefix_source),
                                   sub_scenario=sub, opponent_mix=mix,
                                   panel_seed=panel_seed, root_index=index))


def _requirement_digest(*, prefix_source, predicate, opponent_mix, panel_seed,
                        root_index):
    """根内容"要求摘要"（执行前由冻结参数算出）；缺失时返回空串供对照运行。"""

    builder = getattr(search, "av_family_root_requirement_digest", None)
    if builder is None:
        return ""
    return str(builder(prefix_source=prefix_source, predicate=predicate,
                       opponent_mix=opponent_mix, panel_seed=panel_seed,
                       root_index=root_index))


def _family_item(*, index=OTHER_HIT_INDEX, seed=SEED_A, mix="H", sub=SUB_OPEN,
                 cid=None):
    cid = _candidate_id() if cid is None else cid
    return {"candidate_id": cid, "sub_scenario": sub, "opponent_mix": mix,
            "panel_seed": seed, "root_indexes": [index],
            "root_ids": [_fam_root(sub, index, mix, seed)],
            "root_seed": _family_root_seed(seed, sub, mix, index),
            "token": "{0}-s{1}-idx{2}".format(mix, seed, index),
            "planned_tables": search.AV_TABLES_PER_FAMILY_EVALUATION,
            "seats_per_root": 1, "kind": "missing_root",
            "prefix_source": "scripted_fixture"}


_CANDIDATE_CACHE: dict = {}


def _candidate_id(source=None):
    """候选身份（与 run_av_evaluation 的准入身份同一实现，B2 单一来源）。"""

    source = seeds.EFFICIENCY_SEED.source if source is None else source
    if source not in _CANDIDATE_CACHE:
        _CANDIDATE_CACHE[source] = str(
            search.av_gates().av_candidate_identity(source))
    return _CANDIDATE_CACHE[source]


def _item_source():
    return {"source": seeds.EFFICIENCY_SEED.source,
            "sha256": search.sha256_text(seeds.EFFICIENCY_SEED.source),
            "origin": "test"}


def _iter_state(tmp_path, cid=None):
    cid = _candidate_id() if cid is None else cid
    iter_dir = Path(tmp_path) / "iter" / ("it-" + uuid.uuid4().hex[:6])
    iter_dir.mkdir(parents=True, exist_ok=True)
    state = {"run_id": "s2-a2", "iteration_no": 1, "iter_dir": str(iter_dir),
             "identity": {"candidate_id": cid},
             "plan": {"prefix_source": "scripted_fixture"}}
    return state, iter_dir


def _ledger(iter_dir):
    return search.ActionValueLedger(
        Path(iter_dir) / "av-ledger.json",
        authorized_budgets=search.av_ledger_budgets_from_authorization(TOKEN))


def test_a2_root_selection_reaches_prefix_executor_and_result_is_used(tmp_path, monkeypatch):
    """复审 A2 控制流反例：执行点必须收到**冻结的根选择**，且结果不被丢弃。

    反例（修复前）：delivered kwargs 无任何选根参数、执行得首根 root000/root002，
    再按根身份不符拒绝并丢弃 4 桌。
    """

    run_root = _run_root(tmp_path)
    state, iter_dir = _iter_state(tmp_path)
    item = _family_item()
    delivered = []

    def spy(*args, **kwargs):
        delivered.append(dict(kwargs))
        index = int(item["root_indexes"][0])
        return {"identity": {"candidate_id": item["candidate_id"],
                             "opponent_mix": item["opponent_mix"]},
                "panel": {"predicate": item["sub_scenario"],
                          "panel_seed": item["panel_seed"],
                          "tables_full_executed": 4,
                          "prefix_attempts": {"total": 1, "hit": 1}},
                "root_selection": {"selector": "conditional_root",
                                   "indexes": [index]},
                "samples": [_family_sample(_fam_root(item["sub_scenario"], index),
                                           item["sub_scenario"], item["opponent_mix"],
                                           item["candidate_id"], 0.5,
                                           root_requirement_digest=_requirement_digest(
                                               prefix_source="scripted_fixture",
                                               predicate=item["sub_scenario"],
                                               opponent_mix=item["opponent_mix"],
                                               panel_seed=item["panel_seed"],
                                               root_index=index),
                                           root_content_digest="spy:content")],
                "execution_kind": "real_runtime"}

    monkeypatch.setattr(search, "run_av_evaluation", spy, raising=True)
    result = search._av_family_execute_evaluation(
        state=state, run_root=run_root, ledger=None, authorization=None,
        item=item, source=_item_source())
    assert delivered, "执行点必须被调用"
    kwargs = delivered[0]
    selection_names = ("root_indexes", "root_index", "roots")
    assert any(name in kwargs for name in selection_names), (
        "家族评价调用必须把根选择传给前缀执行器（复审 A2）", sorted(kwargs))
    for name in selection_names:
        if name in kwargs:
            assert list(kwargs[name]) == list(item["root_indexes"]), kwargs[name]
    assert kwargs.get("root_seed") == item["root_seed"], kwargs
    assert result["ok"] is True, result
    assert result["tables_executed"] == 4, result
    assert [sample["source_root_id"] for sample in result["evaluation"]["samples"]] \
        == item["root_ids"]


def test_a2_non_first_hit_root_is_the_only_root_started(tmp_path):
    """非首命中根：请求 root005 → 只跑 root005（首命中根 root002 一张桌都不启动）。"""

    run_root = _run_root(tmp_path)
    state, iter_dir = _iter_state(tmp_path)
    item = _family_item(index=OTHER_HIT_INDEX)
    ledger = _ledger(iter_dir)
    run = search._av_family_run_evaluation(state, run_root, ledger, TOKEN, item,
                                           _item_source())
    assert run.get("evaluation") is not None, run
    evaluation = run["evaluation"]
    assert [s["source_root_id"] for s in evaluation["samples"]] == item["root_ids"], \
        evaluation["samples"]
    attempts = evaluation["panel"]["prefix_attempts"]
    assert attempts["total"] == 1 and attempts["hit"] == 1, attempts
    assert evaluation["root_selection"]["indexes"] == [OTHER_HIT_INDEX]
    # 面板产物里跑的就是目标任务根（不是"跑完再丢弃"）。
    panel = _read_json(Path(iter_dir) / "family" /
                       "{0}-{1}-{2}-{3}".format(
                           item["candidate_id"][:12], item["sub_scenario"],
                           item["opponent_mix"], item["token"]) / "execution" /
                       "panel-{0}".format(item["sub_scenario"]) / "panel.json")
    snapshot = panel["scenarios"][0]["snapshot"]
    assert snapshot["source_root_id"] == item["root_ids"][0], snapshot["source_root_id"]
    # 根内容摘要随结果落档（跑的是哪个根可核）。
    sample = evaluation["samples"][0]
    assert sample["root_requirement_digest"] == _requirement_digest(
        prefix_source="scripted_fixture", predicate=item["sub_scenario"],
        opponent_mix=item["opponent_mix"], panel_seed=item["panel_seed"],
        root_index=OTHER_HIT_INDEX), sample
    assert sample["root_content_digest"], sample
    # 实例台账：本根 2 臂 × 1 座位 = 2 条，全部完成且带根种子。
    registry = search.av_instances_load(iter_dir)["instances"]
    rows = [row for row in registry.values()
            if row.get("root_index") == OTHER_HIT_INDEX]
    assert len(rows) == 2, rows
    assert all(row["status"] == "completed" for row in rows), rows
    assert all(row.get("root_seed") == item["root_seed"] for row in rows), rows
    assert {row["source_root_id"] for row in rows} == set(item["root_ids"])


def test_a2_same_seed_different_index_distinct_roots_and_instances(tmp_path):
    """同种子不同索引：两个索引各自跑自己的根，实例键互不覆盖。"""

    run_root = _run_root(tmp_path)
    state, iter_dir = _iter_state(tmp_path)
    ledger = _ledger(iter_dir)
    outcomes = {}
    for index in (OTHER_HIT_INDEX, THIRD_HIT_INDEX):
        item = _family_item(index=index)
        run = search._av_family_run_evaluation(state, run_root, ledger, TOKEN, item,
                                               _item_source())
        assert run.get("evaluation") is not None, (index, run)
        outcomes[index] = run["evaluation"]
    assert (outcomes[OTHER_HIT_INDEX]["samples"][0]["source_root_id"]
            != outcomes[THIRD_HIT_INDEX]["samples"][0]["source_root_id"])
    digests = {outcomes[index]["samples"][0]["root_content_digest"]
               for index in outcomes}
    assert len(digests) == 2, digests
    requirement = {outcomes[index]["samples"][0]["root_requirement_digest"]
                   for index in outcomes}
    assert len(requirement) == 2, requirement
    registry = search.av_instances_load(iter_dir)["instances"]
    rows = [row for row in registry.values()
            if row.get("root_index") in (OTHER_HIT_INDEX, THIRD_HIT_INDEX)]
    assert len(rows) == 4, rows
    assert all(row["status"] == "completed" for row in rows), rows
    assert len({row["root_seed"] for row in rows}) == 2, rows
    # 不同根选择集是**不同任务身份**：产物目录与面板各自独立、互不覆盖。
    artifact_dirs = sorted(path.name for path in (Path(iter_dir) / "family").glob("*"))
    assert len(artifact_dirs) == 2, artifact_dirs
    landed = {}
    for index in (OTHER_HIT_INDEX, THIRD_HIT_INDEX):
        item = _family_item(index=index)
        panel = _read_json(Path(iter_dir) / "family" /
                           "{0}-{1}-{2}-{3}".format(
                               item["candidate_id"][:12], item["sub_scenario"],
                               item["opponent_mix"], item["token"]) / "execution" /
                           "panel-{0}".format(item["sub_scenario"]) / "panel.json")
        landed[index] = panel["scenarios"][0]["snapshot"]["source_root_id"]
    assert landed == {index: _fam_root(SUB_OPEN, index)
                      for index in (OTHER_HIT_INDEX, THIRD_HIT_INDEX)}, landed


def test_a2_repeated_fill_reuses_checkpoint_without_rerun_or_recharge(tmp_path,
                                                                    monkeypatch):
    """重复补根：同一工作项第二次调用走检查点复用，不重跑、不重复计费。"""

    run_root = _run_root(tmp_path)
    state, iter_dir = _iter_state(tmp_path)
    ledger = _ledger(iter_dir)
    item = _family_item()
    executions = []
    real_panel = search._av_conditional_root_panel

    def spy_panel(*args, **kwargs):
        # 执行点被真正调用的次数（"不重跑"与"只跑目标任务"都落在这个计数上）。
        executions.append({"root_index": kwargs.get("root_index"),
                           "root_seed": kwargs.get("root_seed")})
        return real_panel(*args, **kwargs)

    monkeypatch.setattr(search, "_av_conditional_root_panel", spy_panel, raising=True)
    first = search._av_family_run_evaluation(state, run_root, ledger, TOKEN, item,
                                             _item_source())
    assert first.get("evaluation") is not None, first
    assert len(executions) == 1, executions
    spent_once = ledger.account_summary()
    second = search._av_family_run_evaluation(state, run_root, ledger, TOKEN, item,
                                              _item_source())
    assert second.get("evaluation") is not None, second
    assert second["attempt"].get("reuse") == "checkpoint", second["attempt"]
    assert len(executions) == 1, (
        "第二次调用不得再次进入执行点（检查点复用）", executions)
    assert executions[0]["root_index"] == OTHER_HIT_INDEX, executions
    assert ledger.account_summary() == spent_once, (
        ledger.account_summary(), spent_once)
    assert (second["evaluation"]["samples"][0]["root_content_digest"]
            == first["evaluation"]["samples"][0]["root_content_digest"])
    registry = search.av_instances_load(iter_dir)["instances"]
    assert len([row for row in registry.values()
                if row.get("status") == "completed"]) == 2, registry


def test_a2_result_claiming_another_root_is_refused(tmp_path, monkeypatch):
    """结果自称是别的根 → 拒绝采用（内容摘要/根号对不上），不留"跑完再丢弃"的漏洞。"""

    run_root = _run_root(tmp_path)
    state, iter_dir = _iter_state(tmp_path)
    item = _family_item(index=OTHER_HIT_INDEX)

    def wrong_root(*args, **kwargs):
        index = 3
        requirement = _requirement_digest(prefix_source="scripted_fixture",
                                          predicate=SUB_OPEN, opponent_mix="H",
                                          panel_seed=SEED_A, root_index=index)
        return {"identity": {"candidate_id": item["candidate_id"],
                             "opponent_mix": item["opponent_mix"]},
                "panel": {"predicate": item["sub_scenario"],
                          "panel_seed": item["panel_seed"],
                          "tables_full_executed": 4},
                "root_selection": {"selector": "conditional_root", "indexes": [index]},
                "samples": [_family_sample(_fam_root(SUB_OPEN, index),
                                           item["sub_scenario"], item["opponent_mix"],
                                           item["candidate_id"], 0.5,
                                           root_requirement_digest=requirement,
                                           root_content_digest="wrong:content")],
                "execution_kind": "real_runtime"}

    monkeypatch.setattr(search, "run_av_evaluation", wrong_root, raising=True)
    result = search._av_family_execute_evaluation(
        state=state, run_root=run_root, ledger=None, authorization=None,
        item=item, source=_item_source())
    assert result["ok"] is False, result
    assert "不采用" in str(result.get("reason")), result
    assert result.get("evaluation") is not None, (
        "被拒的结果仍要留档（可核「跑了哪个根」），但不能被采用")


def test_a2_result_from_another_seed_with_same_root_id_is_refused(tmp_path, monkeypatch):
    """内容摘要门：同根身份、不同种子/无摘要的结果都不得被采用。

    家族根身份（av-eval-{子场景}:{子场景}:root{NNN}）**不含面板种子**：同一个
    root005 在不同种子下是两个任务（不同牌山）。只有内容摘要能把"冻结的那个根"
    与"长得一样的别的根"分开——因此摘要不符（或缺失）必须落在拒绝上。
    """

    run_root = _run_root(tmp_path)
    state, iter_dir = _iter_state(tmp_path)
    item = _family_item(index=OTHER_HIT_INDEX, seed=SEED_A)
    root_id = item["root_ids"][0]

    def _evaluation(requirement, content):
        sample = _family_sample(root_id, item["sub_scenario"], item["opponent_mix"],
                                item["candidate_id"], 0.5)
        if requirement is not None:
            sample["root_requirement_digest"] = requirement
        if content is not None:
            sample["root_content_digest"] = content
        return {"identity": {"candidate_id": item["candidate_id"],
                             "opponent_mix": item["opponent_mix"]},
                "panel": {"predicate": item["sub_scenario"],
                          "panel_seed": item["panel_seed"],
                          "tables_full_executed": 4},
                "root_selection": {"selector": "conditional_root",
                                   "indexes": [OTHER_HIT_INDEX]},
                "samples": [sample], "execution_kind": "real_runtime"}

    foreign = _requirement_digest(prefix_source="scripted_fixture", predicate=SUB_OPEN,
                                 opponent_mix="H", panel_seed=SEED_B,
                                 root_index=OTHER_HIT_INDEX)
    own = _requirement_digest(prefix_source="scripted_fixture", predicate=SUB_OPEN,
                             opponent_mix="H", panel_seed=SEED_A,
                             root_index=OTHER_HIT_INDEX)
    for label, evaluation in (("别种子的摘要", _evaluation(foreign, "foreign:content")),
                              ("完全没有摘要", _evaluation(None, None))):
        monkeypatch.setattr(search, "run_av_evaluation",
                            lambda *a, _e=evaluation, **k: _e, raising=True)
        result = search._av_family_execute_evaluation(
            state=state, run_root=run_root, ledger=None, authorization=None,
            item=item, source=_item_source())
        assert result["ok"] is False, (label, result)
        assert "摘要" in str(result.get("reason")), (label, result)
    # 对照：本种子自己的摘要 → 采用（证明拒绝不是恒真）。
    monkeypatch.setattr(search, "run_av_evaluation",
                        lambda *a, **k: _evaluation(own, "own:content"), raising=True)
    accepted = search._av_family_execute_evaluation(
        state=state, run_root=run_root, ledger=None, authorization=None,
        item=item, source=_item_source())
    assert accepted["ok"] is True, accepted


def test_a2_out_of_range_index_rejected_before_any_side_effect(tmp_path):
    """不存在的索引：越界根序号在**一切副作用之前**拒绝（零桌、零实例、零产物）。"""

    run_root = _run_root(tmp_path)
    state, iter_dir = _iter_state(tmp_path)
    ledger = _ledger(iter_dir)
    item = _family_item(index=OUT_OF_RANGE_INDEX)
    before = ledger.account_summary()
    run = search._av_family_run_evaluation(state, run_root, ledger, TOKEN, item,
                                           _item_source())
    assert run.get("evaluation") is None, run
    assert "越界" in str(run.get("reason")), run
    assert ledger.account_summary() == before, (
        ledger.account_summary(), before)
    assert not (Path(iter_dir) / "family").exists(), "不得留下任何执行产物"
    assert (search.av_instances_load(iter_dir)["instances"] or {}) == {}
    # 声明侧同样在调度前拦下（不猜、不越界执行）。
    declarations = [{"channel": CHANNEL, "sub_scenario": SUB_OPEN,
                     "opponent_mix": "H", "panel_seed": SEED_A,
                     "root_index": OUT_OF_RANGE_INDEX}]
    parsed = search._av_family_declarations(
        {"plan": {"family_refresh": declarations}}, CHANNEL)
    assert parsed["declared"] == [], parsed["declared"]
    assert parsed["problems"], parsed
    # 公开执行器自身也拒绝（在任何执行/建目录之前）。
    with pytest.raises(ValueError):
        search.run_av_evaluation(
            Path(tmp_path) / "rejected", seeds.EFFICIENCY_SEED.source,
            root_indexes=[OUT_OF_RANGE_INDEX], root_seed=1)
    assert not (Path(tmp_path) / "rejected").exists()


def test_a2_natural_panel_root_selection_is_independent_and_still_verified(tmp_path,
                                                                          monkeypatch):
    """P2b 的自然面板选根不能代替条件机会选根：两条通路各自验一次。

    自然面板：显式根索引 [3,4] → 产物只含这两个根、执行点只启动这两个根。
    条件机会：显式根索引 [5] → 根身份是 av-eval-…:root005（与自然根身份不同形）。
    """

    driver = StrengthDrive()
    monkeypatch.setattr(natural, "execute_natural_table", driver, raising=True)
    out_dir = Path(tmp_path) / "natural"
    panel = natural.run_natural_panel(
        candidate_source=seeds.EFFICIENCY_SEED.source, opponent="H",
        root_indices=[3, 4], seats_per_root=1, contract=search._av_refresh_contract(),
        out_dir=out_dir, authorization=TOKEN, panel_seed=SEED_A, ledger_path=None)
    indexes = sorted(int(sample["root_index"]) for sample in panel["samples"])
    assert indexes == [3, 4], indexes
    table_ids = {str(call["table_id"]) for call in driver.calls}
    assert table_ids, driver.calls
    assert all(re.search(r"-r0[34]-", table_id) for table_id in table_ids), table_ids
    assert sorted({natural.natural_root_id("H", SEED_A, index) for index in (3, 4)}) == \
        sorted({sample["source_root_id"] for sample in panel["samples"]})
    # 条件机会选根是另一条通路、另一套根身份（本包 A2 的贯穿对象）。
    conditional = _family_item(index=OTHER_HIT_INDEX)
    # R9/A2：条件机会的根身份是**完整身份**（含情景与实际种子），与自然根不同形。
    assert conditional["root_ids"] == [_fam_root(SUB_OPEN, OTHER_HIT_INDEX, "H", SEED_A)]
    assert conditional["root_ids"] == [search.av_family_root_id(
        prefix_source="scripted_fixture", sub_scenario=SUB_OPEN, opponent_mix="H",
        panel_seed=SEED_A, root_index=OTHER_HIT_INDEX)]


# =====================================================================
# 附带上界 · 家族根种子派生（承接 S1 残留 ④）
# =====================================================================


def _family_seed(panel_seed, sub, mix, index, prefix_source="scripted_fixture"):
    """实现侧的根种子（R9/A3：唯一描述符的五维派生，签名统一为关键字）。"""

    return int(search.av_family_root_seed(
        prefix_source=prefix_source, sub_scenario=sub, opponent_mix=mix,
        panel_seed=panel_seed, root_index=index))


def test_seed_family_root_seed_is_deterministic_and_registered(tmp_path):
    """家族根种子：确定性、可复算、按（生成器 × 种子 × 子场景 × 情景 × 序号）分离。

    R9/A3 起派生式改为五维描述符（旧的 "family" 命名空间式子已删除：它与普通生成器的
    "prefix" 式子并存正是 A3 的缺陷来源）。
    """

    base = _family_seed(SEED_A, SUB_OPEN, "H", 3)
    assert base == _family_seed(SEED_A, SUB_OPEN, "H", 3)
    assert base != _family_seed(SEED_B, SUB_OPEN, "H", 3)
    assert base != _family_seed(SEED_A, SUB_COST, "H", 3)
    assert base != _family_seed(SEED_A, SUB_OPEN, "M", 3)
    assert base != _family_seed(SEED_A, SUB_OPEN, "H", 4)
    # 生成器版本也是身份维度：换生成器即换根（夹具证据与真实证据不混同）。
    assert base != _family_seed(SEED_A, SUB_OPEN, "H", 3, "v2_behavior")
    # 与描述符同源：身份里的五维派生（不是随机、不是缺省空值）。
    descriptor = search.av_family_root_descriptor(
        prefix_source="scripted_fixture", sub_scenario=SUB_OPEN, opponent_mix="H",
        panel_seed=SEED_A, root_index=3)
    assert base == int(descriptor["root_seed"]) == int(
        stage.root_seed(generator=descriptor["generator"], sub_scenario=SUB_OPEN,
                        opponent_mix="H", panel_seed=SEED_A, root_index=3))
    rows = search._av_family_expected_instances(_family_item(index=3), 2)
    assert {row["root_seed"] for row in rows} == {base}, rows
    assert all(row["root_index"] == 3 for row in rows), rows


def test_seed_cross_seed_family_instances_unique_and_retained(tmp_path):
    """跨种子唯一：同候选、同情景、同根序号、不同面板种子 → 键不同且记录互不覆盖。"""

    run_root = _run_root(tmp_path)
    state, iter_dir = _iter_state(tmp_path)
    ledger = _ledger(iter_dir)
    digests = {}
    for seed in (SEED_A, SEED_B):
        item = _family_item(index=OTHER_HIT_INDEX, seed=seed)
        run = search._av_family_run_evaluation(state, run_root, ledger, TOKEN, item,
                                               _item_source())
        assert run.get("evaluation") is not None, (seed, run)
        digests[seed] = run["evaluation"]["samples"][0]["root_content_digest"]
    assert len(set(digests.values())) == 2, digests
    registry = search.av_instances_load(iter_dir)["instances"]
    rows = list(registry.values())
    assert len(rows) == 4, rows
    assert len({row["instance_key"] for row in rows}) == 4, rows
    assert len({row["panel_seed"] for row in rows}) == 2, rows
    assert len({row["root_seed"] for row in rows}) == 2, rows
    assert all(row["status"] == "completed" for row in rows), rows
    assert all(row.get("result_digest") for row in rows), rows
