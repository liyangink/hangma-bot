# -*- coding: utf-8 -*-
"""P2 ROOT 专属测试（R9 修复轮）：A1 完整核心矩阵 / A2 统一根身份 / A3 真实执行种子。

复审依据：R8-REPAIR-REREVIEW-2026-09-17 §4 A1/A2/A3（三项 P1）；修复计划
R9-FIX-PLAN-2026-09-17 §4。三条缺陷共用一句根因：**根的身份没有贯穿全链**。

  A1 · 完整交叉矩阵
      反例：声明 8 根、只物化对角两格，原函数即返回 established，epoch 只有 2 根，
      剩余未物化声明从返回值消失，家族席为空。本文件覆盖：对角两格 / 少一根 /
      单格评价不合格 / 冲突声明 四种缺格都**不得** established；补齐后恰好建立一次
      且可重复调用不重复建立；绝不出现"建立成功但席位为空"。
  A2 · 统一根身份
      反例：productions 去重与刷新去重都用不含 H/M 与种子的裸 root_id → 8 个评价项
      只留 4 个 H 根；换 panel_seed 保留序号时刷新批变 0。本文件覆盖：8 根全部保留
      且 H/M 各半、同根恢复零新增、新种子同索引确实新增、不同候选共享同一根描述符
      但各有独立评价实例。
  A3 · 真实执行种子
      反例：普通生成用 "prefix" 命名空间派生执行种子，登记与补根用 "family" 命名空间
      另算一个（6080762621504 != 15025786951857）。本文件覆盖：普通生成 → 登记 →
      补根三处种子与重建内容逐字一致；缺真实种子或版本不可恢复时**停止并说明原因**
      （不静默赋新种子）；历史普通根按原生成器还原。

全部离线：纯数据控制流 + 生产合并器/登记/调度实现；家族条件评价执行器在需要时替换为
内存替身（零真实桌赛、零模型调用、零网络）。替身接线证据不等于真实桌赛能力。
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

import copy
import json
import sys
import uuid
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import sitin_search as search  # noqa: E402
import sitin_stage as stage  # noqa: E402

CHANNEL = "branch"
SUB_OPEN = "branch_open"
SUB_COST = "branch_cost"
MIXES = ("H", "M")
SEEDS = (11, 12)                      # 每格 2 个面板种子 → 每格 2 个核心根
CID_A = "cand-r9-a"
CID_B = "cand-r9-b"
FIXTURE = "scripted_fixture"

TOKEN = {"authorized": True, "batch": 7,
         "budgets": {"tokens_input": 100000, "tokens_output": 200000,
                     "tables_full": 256, "tables_partial": 64,
                     "prefix_generation": 64}}

#: 核心格的根序号：每条声明都不同（同格两根是**两个不同的根**）。
INDEX = {(SUB_OPEN, "H", 11): 3, (SUB_OPEN, "M", 11): 4,
         (SUB_OPEN, "H", 12): 5, (SUB_OPEN, "M", 12): 6,
         (SUB_COST, "H", 11): 7, (SUB_COST, "M", 11): 8,
         (SUB_COST, "H", 12): 9, (SUB_COST, "M", 12): 10}
#: 刷新批（同侧同情景的新种子）用的序号：与核心格不重叠。
REFRESH_INDEX = {(SUB_OPEN, "H", 8): 13, (SUB_OPEN, "M", 8): 14,
                 (SUB_OPEN, "H", 9): 15, (SUB_OPEN, "M", 9): 16,
                 (SUB_COST, "H", 8): 17, (SUB_COST, "M", 8): 18,
                 (SUB_COST, "H", 9): 19, (SUB_COST, "M", 9): 20}


# =====================================================================
# 身份助手：新实现走**唯一描述符**；旧实现（修复前对照运行）退回旧形状。
# 对照运行测的是行为差异（8 根被压成 4 根、种子不一致），不是一个缺失的名字。
# =====================================================================


def _generator(prefix_source=FIXTURE):
    mapper = getattr(search, "av_family_generator_of", None)
    if mapper is not None:
        return str(mapper(prefix_source))
    return ("v2-behavior-prefix-v1" if prefix_source == "v2_behavior"
            else "scripted-prefix-fixture-v1")


def _descriptor(sub, mix, seed, index, prefix_source=FIXTURE):
    """根描述符（身份 + 执行种子）。"""

    builder = getattr(search, "av_family_root_descriptor", None)
    if builder is not None:
        return dict(builder(prefix_source=prefix_source, sub_scenario=sub,
                            opponent_mix=mix, panel_seed=seed, root_index=index))
    return {"schema": "legacy-probe",
            "root_id": "av-eval-{0}:{0}:root{1:03d}".format(sub, index),
            "root_seed": int(stage.derive_seed(seed, "family", sub, mix, "root",
                                               str(index))),
            "sub_scenario": sub, "opponent_mix": mix, "panel_seed": seed,
            "root_index": index, "generator": _generator(prefix_source),
            "seed_derivation": "family-v1"}


def _core_cells(sub=None):
    """核心格（侧 × 情景 × 面板种子）：每格 2 个根，合计 8 个。"""

    return [(side, mix, seed)
            for side in (SUB_OPEN, SUB_COST) for mix in MIXES for seed in SEEDS
            if sub is None or side == sub]


def _refresh_cells(seeds=(8, 9)):
    """刷新批声明格（同侧同情景的新种子）：序号与核心格不重叠。"""

    return [(side, mix, seed) for side in (SUB_OPEN, SUB_COST)
            for mix in MIXES for seed in seeds]


def _production(sub, mix, seed, index, *, candidate=CID_A, kind="missing_root",
                prefix_source=FIXTURE):
    """family_fill.productions 行的真实形状（_av_family_fill 追加的那种）。"""

    descriptor = _descriptor(sub, mix, seed, index, prefix_source)
    return {"candidate_id": candidate, "sub_scenario": sub, "opponent_mix": mix,
            "panel_seed": seed, "root_index": index,
            "root_id": descriptor["root_id"], "root_seed": descriptor["root_seed"],
            "root_descriptor": descriptor, "seats_per_root": 1, "kind": kind}


def _sample(sub, mix, seed, index, *, candidate=CID_A, delta=0.5, resolved=True,
            prefix_source=FIXTURE, root_id=None, root_seed=None):
    """家族条件评价样本（双臂点值 U：候选 delta / 基线 0）。"""

    descriptor = _descriptor(sub, mix, seed, index, prefix_source)
    return {"source_root_id": root_id or descriptor["root_id"],
            "scenario": sub, "opponent_mix": mix, "candidate_id": candidate,
            "root_role": "core", "invalid": False, "completeness": "complete",
            "invalid_reasons": [], "cost": 1.0,
            "arms": {"baseline": {"candidate_id": search.AV_BASELINE_ID, "u": 0.0},
                     "candidate": {"candidate_id": candidate,
                                   "u": (float(delta) if resolved else None)}},
            "root_descriptor": descriptor, "root_index": index,
            "root_seed": (descriptor["root_seed"] if root_seed is None
                          else root_seed)}


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _run_root(tmp_path, name="r9"):
    root = Path(tmp_path) / (name + "-" + uuid.uuid4().hex[:6]) / "run"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _state(tmp_path, *, productions=(), samples=(), candidate=CID_A,
           declarations=(), prefix_source=FIXTURE):
    iter_dir = Path(tmp_path) / ("iter-" + uuid.uuid4().hex[:6])
    iter_dir.mkdir(parents=True, exist_ok=True)
    state = {"run_id": "r9-root", "iteration_no": 1, "iter_dir": str(iter_dir),
             "identity": {"candidate_id": candidate},
             "plan": {"family_channel": CHANNEL, "prefix_source": prefix_source,
                      "panel_seed": SEEDS[0],
                      "family_refresh": list(declarations)},
             "conditional_result": {"samples": list(samples)},
             "family_fill": {"schema": search.AV_FAMILY_FILL_TX_SCHEMA,
                             "attempts": [], "productions": list(productions)}}
    return state, iter_dir


def _commit(state, run_root, **kwargs):
    return search._av_commit_family(state, run_root, attempt_refresh=True, **kwargs)


def _epochs(run_root):
    path = Path(run_root) / "archive" / "family-epochs.json"
    return _read_json(path) if path.is_file() else None


def _seats(state, run_root):
    """提交后档案里的家族席（读真实产物）。"""

    path = Path(run_root) / "archive" / "av-archive.json"
    archive = _read_json(path) if path.is_file() else {}
    return list((archive.get("slots") or {}).get(CHANNEL) or ())


def _rows_and_samples(cells, *, resolved_except=None):
    rows = [_production(sub, mix, seed, INDEX[(sub, mix, seed)])
            for sub, mix, seed in cells]
    samples = [_sample(sub, mix, seed, INDEX[(sub, mix, seed)],
                       resolved=not (resolved_except is not None
                                     and (sub, mix, seed) == resolved_except))
               for sub, mix, seed in cells]
    return rows, samples


# =====================================================================
# A1 · 完整交叉矩阵（缺格不得建立；建立必须一次且席位非空）
# =====================================================================


def test_a1_diagonal_two_cells_is_not_established(tmp_path):
    """对角两格（open/H + cost/M）证据齐全也不得建立：缺格保持 pending。"""

    run_root = _run_root(tmp_path, "a1-diagonal")
    cells = [(SUB_OPEN, "H", SEEDS[0]), (SUB_COST, "M", SEEDS[0])]
    rows, samples = _rows_and_samples(cells)
    state, _ = _state(tmp_path, productions=rows, samples=samples)
    outcome = _commit(state, run_root)
    assert outcome.get("status") != "established", outcome
    assert _epochs(run_root) is None, "缺格不得提交面板版本（epoch）"
    assert _seats(state, run_root) == [], "缺格不得落家族席"
    # 未物化/缺格信息必须仍然可见（旧缺陷：剩余声明从返回值消失）。
    detail = json.dumps(outcome, ensure_ascii=False)
    assert "family_channel_epoch_incomplete" in detail or "core" in detail, outcome


def test_a1_cell_with_single_root_is_not_established(tmp_path):
    """少一根（某格只有 1 个核心根）不得建立：逐格配额没满足。"""

    run_root = _run_root(tmp_path, "a1-seven")
    cells = _core_cells()[:-1]           # 缺 (cost, M, seed12) 这一格的第二个根
    rows, samples = _rows_and_samples(cells)
    state, _ = _state(tmp_path, productions=rows, samples=samples)
    outcome = _commit(state, run_root)
    assert outcome.get("status") != "established", outcome
    assert _epochs(run_root) is None
    gaps = " ".join(state.get("input_gaps") or [])
    assert "family_channel_epoch_incomplete" in gaps, state.get("input_gaps")
    # 缺口读数必须点名缺格（不是一句"不完整"）。
    missing_cells = [(item.get("sub_scenario"), item.get("opponent_mix"))
                     for item in (outcome.get("core_matrix") or {}).get("missing") or ()]
    assert (SUB_COST, "M") in missing_cells, (missing_cells, outcome)


def test_a1_unresolved_core_root_is_not_established(tmp_path):
    """单格评价不合格（未分辨/缺配对差）不得建立：把缺的根交回补根层。"""

    run_root = _run_root(tmp_path, "a1-cell-fail")
    cells = _core_cells()
    rows, samples = _rows_and_samples(cells, resolved_except=(SUB_COST, "M", SEEDS[1]))
    state, _ = _state(tmp_path, productions=rows, samples=samples)
    outcome = _commit(state, run_root)
    assert outcome.get("status") != "established", outcome
    assert _epochs(run_root) is None
    assert _seats(state, run_root) == []
    missing = outcome.get("missing") or {}
    flattened = [token for tokens in missing.values() for token in tokens]
    assert any(token.startswith(SUB_COST + "|M|") for token in flattened), \
        (missing, outcome)


def test_a1_conflicting_declaration_is_not_established(tmp_path):
    """冲突声明（同一声明重复且座位数不一致）先处理：不建立、不调度、留诊断。"""

    run_root = _run_root(tmp_path, "a1-conflict")
    rows, samples = _rows_and_samples(_core_cells())
    declarations = [
        {"channel": CHANNEL, "sub_scenario": SUB_OPEN, "opponent_mix": "H",
         "panel_seed": SEEDS[0], "root_index": INDEX[(SUB_OPEN, "H", SEEDS[0])],
         "seats_per_root": 1},
        {"channel": CHANNEL, "sub_scenario": SUB_OPEN, "opponent_mix": "H",
         "panel_seed": SEEDS[0], "root_index": INDEX[(SUB_OPEN, "H", SEEDS[0])],
         "seats_per_root": 2}]
    state, _ = _state(tmp_path, productions=rows, samples=samples,
                      declarations=declarations)
    outcome = _commit(state, run_root)
    assert outcome.get("status") != "established", outcome
    assert _epochs(run_root) is None
    assert outcome.get("blocked"), outcome


def test_a1_complete_matrix_establishes_once_and_is_repeatable(tmp_path):
    """补齐后恰好建立一次：epoch 恰好 8 根（每格 2）、家族席非空、重复调用不再建立。"""

    run_root = _run_root(tmp_path, "a1-complete")
    rows, samples = _rows_and_samples(_core_cells())
    state, _ = _state(tmp_path, productions=rows, samples=samples)
    outcome = _commit(state, run_root)
    assert outcome.get("status") == "established", outcome
    epoch = _epochs(run_root)["channels"][CHANNEL]
    assert epoch["epoch"] == 1, epoch
    counts = {}
    for row in epoch["roots"]:
        key = (row["sub_scenario"], row["opponent_mix"])
        counts[key] = counts.get(key, 0) + 1
    assert sorted(counts.values()) == [2, 2, 2, 2], counts
    assert set(counts) == {(sub, mix) for sub in (SUB_OPEN, SUB_COST)
                           for mix in MIXES}, counts
    seats = _seats(state, run_root)
    assert seats == [CID_A], seats          # 建立成功但席位为空是禁止结局
    # 恢复不重复：同一状态再提交一次，epoch 与席位逐字不变（不重复建立）。
    again = _commit(copy.deepcopy(state), run_root)
    assert _epochs(run_root)["channels"][CHANNEL] == epoch
    assert _seats(state, run_root) == seats
    assert again.get("status") in ("kept", "committed", "no_refresh_requested"), again


def test_a1_registry_conflict_row_blocks_establishment(tmp_path):
    """台账行的复现参数与根身份矛盾 → 冲突：不建立、不调度。"""

    run_root = _run_root(tmp_path, "a1-identity-conflict")
    rows, samples = _rows_and_samples(_core_cells())
    bad = dict(rows[0])
    bad["panel_seed"] = SEEDS[1]                 # 身份说 s11，字段说 s12
    rows.append(bad)
    state, _ = _state(tmp_path, productions=rows, samples=samples)
    outcome = _commit(state, run_root)
    assert outcome.get("status") != "established", outcome
    assert _epochs(run_root) is None
    assert outcome.get("blocked"), outcome


# =====================================================================
# A2 · 统一根身份（H/M 与跨种子不再互吞）
# =====================================================================


def _registry_for(rows):
    return search._av_family_root_registry({CHANNEL: {"roots": list(rows)}})


def _refresh_declarations(seeds=(8, 9)):
    declared = []
    for side in (SUB_OPEN, SUB_COST):
        for mix in MIXES:
            for seed in seeds:
                index = REFRESH_INDEX[(side, mix, seed)]
                descriptor = _descriptor(side, mix, seed, index)
                declared.append({"channel": CHANNEL, "sub_scenario": side,
                                 "opponent_mix": mix, "panel_seed": seed,
                                 "root_index": index,
                                 "root_id": descriptor["root_id"],
                                 "root_seed": descriptor["root_seed"]})
    return {"declared": declared}


def test_a2_registry_keeps_eight_roots_with_hm_split(tmp_path):
    """登记表保留 8 个核心根，且 H/M 各 4（裸根名去重会把 M 吞掉）。"""

    rows = [_production(sub, mix, seed, INDEX[(sub, mix, seed)])
            for sub, mix, seed in _core_cells()]
    registry = _registry_for(rows)
    assert registry.get("n_roots") == 8, registry
    assert len(set(registry.get("roots") or ())) == 8, registry.get("roots")
    mix_roots = {}
    for cell in (registry.get("cells") or {}).values():
        mix_roots.setdefault(cell.get("opponent_mix"), set()).add(cell["root_id"])
    assert sorted(len(value) for value in mix_roots.values()) == [4, 4], mix_roots
    assert registry.get("conflicts") == [], registry.get("conflicts")
    assert registry.get("refused") == [], registry.get("refused")


def test_a2_refresh_batch_keeps_all_eight_new_seed_roots(tmp_path):
    """刷新批：同索引换新种子的 8 个根全部保留（旧实现按裸根名压成 4 个 H）。"""

    rows = [_production(sub, mix, seed, INDEX[(sub, mix, seed)])
            for sub, mix, seed in _core_cells()]
    # 刷新根也必须**已登记**（否则它们在调度上属于"未物化"，不是去重问题）。
    refresh_rows = [_production(sub, mix, seed, REFRESH_INDEX[(sub, mix, seed)])
                    for sub, mix, seed in _refresh_cells()]
    registry = _registry_for(rows + refresh_rows)
    epoch = {"roots": [{"root_id": row["root_id"],
                        "opponent_mix": row["opponent_mix"],
                        "sub_scenario": row["sub_scenario"]} for row in rows]}
    batch, unmaterialized = search._av_family_refresh_batch(
        CHANNEL, _refresh_declarations(), registry, epoch)
    assert not unmaterialized, unmaterialized
    assert len(batch) == 8, batch
    mixes = {}
    for row in batch:
        mixes[row["opponent_mix"]] = mixes.get(row["opponent_mix"], 0) + 1
    assert mixes == {"H": 4, "M": 4}, mixes
    assert len({row["root_id"] for row in batch}) == 8, batch


def test_a2_same_root_is_zero_new_and_new_seed_adds(tmp_path):
    """同根恢复零新增；换 panel_seed 同索引确实新增（旧实现整批变 0）。"""

    rows = [_production(sub, mix, seed, INDEX[(sub, mix, seed)])
            for sub, mix, seed in _core_cells()]
    registry = _registry_for(rows)
    epoch = {"roots": [{"root_id": row["root_id"],
                        "opponent_mix": row["opponent_mix"],
                        "sub_scenario": row["sub_scenario"]} for row in rows]}
    same = {"declared": [
        {"channel": CHANNEL, "sub_scenario": side, "opponent_mix": mix,
         "panel_seed": seed, "root_index": INDEX[(side, mix, seed)],
         "root_id": _descriptor(side, mix, seed, INDEX[(side, mix, seed)])["root_id"]}
        for side in (SUB_OPEN, SUB_COST) for mix in MIXES for seed in SEEDS]}
    batch, unmaterialized = search._av_family_refresh_batch(
        CHANNEL, same, registry, epoch)
    assert batch == [], batch
    assert not unmaterialized, unmaterialized
    refresh_rows = rows + [_production(sub, mix, seed, REFRESH_INDEX[(sub, mix, seed)])
                           for sub in (SUB_OPEN, SUB_COST) for mix in MIXES
                           for seed in (8, 9)]
    batch2, _ = search._av_family_refresh_batch(
        CHANNEL, _refresh_declarations(), _registry_for(refresh_rows), epoch)
    assert len(batch2) == 8, batch2


def test_a2_fill_productions_keep_hm_split(tmp_path, monkeypatch):
    """补根控制器登记的根保留 H/M 各半（productions 去重按完整身份）。"""

    run_root = _run_root(tmp_path, "a2-fill")
    rows = [_production(sub, mix, seed, INDEX[(sub, mix, seed)])
            for sub, mix, seed in _core_cells()]
    missing_tokens = []
    for sub, mix, seed in _core_cells():
        root_id = _descriptor(sub, mix, seed, INDEX[(sub, mix, seed)])["root_id"]
        missing_tokens.append("{0}|{1}|{2}".format(sub, mix, root_id))
    state, _ = _state(tmp_path, productions=rows, declarations=[])
    statements = []

    def fake_run_evaluation(state_, run_root_, ledger, authorization, item, source,
                            test_runtime_factory=None):
        statements.append(item)
        samples = [_sample(item["sub_scenario"], item["opponent_mix"],
                           item["panel_seed"], int(item["root_indexes"][0]),
                           candidate=item["candidate_id"],
                           root_id=item["root_ids"][0],
                           root_seed=int(item["root_seed"]))]
        return {"attempt": {"candidate_id": item["candidate_id"],
                            "status": "completed", "reuse": None,
                            "tables_executed": 4},
                "evaluation": {"samples": samples}, "instances": {}}

    def fake_merge(state_, run_root_, fills):
        report = {}
        for candidate, (item, result) in fills.items():
            report[candidate] = {"roots_added": list(item["root_ids"]),
                                 "n_samples": len(result["evaluation"]["samples"])}
        return report

    monkeypatch.setattr(search, "_av_family_run_evaluation", fake_run_evaluation,
                        raising=True)
    monkeypatch.setattr(search, "_av_family_merge_fills", fake_merge, raising=True)
    monkeypatch.setattr(search, "_av_refresh_budget", lambda *a, **k: 100,
                        raising=True)
    monkeypatch.setattr(search, "_av_refresh_participant_source",
                        lambda *a, **k: {"source": "stub", "sha256": "stub"},
                        raising=True)
    result = search._av_family_fill(state, run_root, None, TOKEN)
    assert isinstance(result, dict), result
    assert statements, "补根工作项没有被送到执行点"
    productions = state["family_fill"]["productions"]
    counts = {}
    for row in productions:
        counts[row["opponent_mix"]] = counts.get(row["opponent_mix"], 0) + 1
    assert counts == {"H": 4, "M": 4}, productions
    assert len({row["root_id"] for row in productions}) == 8, productions


def test_a2_same_root_descriptor_is_shared_across_candidates(tmp_path):
    """不同候选共享同一根描述符，但各有独立评价实例（候选不进来源根身份）。"""

    index = INDEX[(SUB_OPEN, "H", SEEDS[0])]
    descriptor_a = _descriptor(SUB_OPEN, "H", SEEDS[0], index)
    descriptor_b = _descriptor(SUB_OPEN, "H", SEEDS[0], index)
    assert descriptor_a == descriptor_b, (descriptor_a, descriptor_b)
    assert CID_A not in descriptor_a["root_id"], descriptor_a
    assert CID_B not in descriptor_a["root_id"], descriptor_a
    key_a = search.av_instance_identity_key(
        candidate_id=CID_A, opponent_mix="H", panel_seed=SEEDS[0],
        source_root_id=descriptor_a["root_id"],
        root_index=descriptor_a["root_index"],
        root_seed=descriptor_a["root_seed"], seat=0, arm="candidate",
        schedule="conditional_stage:2_tables")
    key_b = search.av_instance_identity_key(
        candidate_id=CID_B, opponent_mix="H", panel_seed=SEEDS[0],
        source_root_id=descriptor_b["root_id"],
        root_index=descriptor_b["root_index"],
        root_seed=descriptor_b["root_seed"], seat=0, arm="candidate",
        schedule="conditional_stage:2_tables")
    assert key_a != key_b, (key_a, key_b)


# =====================================================================
# A3 · 真实执行种子（普通生成 ↔ 登记 ↔ 补根三处逐字一致）
# =====================================================================


def _fixture_snapshot(tmp_path, *, sub=SUB_OPEN, mix="H", panel_seed=SEEDS[0]):
    """跑**真实夹具生成器**（零真实桌赛）拿到普通条件生成产物。"""

    opportunities = search.av_opportunities()
    from hangma_bot.hangma.engine import HangmaRules
    from hangma_bot.hangma.interface import ValueAnalysisLimits
    from hangma_bot.kernel.config import RuleConfig

    rules = HangmaRules(RuleConfig("v26", 1, False))
    snapshot, counters = opportunities.generate_opportunity(
        prefix_source=FIXTURE, rules=rules, predicate_id=sub, focal_seat=0,
        opponent_scenario=mix, root_label="av-eval-{0}".format(sub),
        match_id="r9-a3-match", stage_ledger={"completed_table_scores": []},
        remaining_schedule={"declared_endpoint": "stage_complete",
                            "remaining_tables_after_current": 1,
                            "rounds_per_game": 8, "tables_in_stage": 2},
        value_limits=ValueAnalysisLimits(),
        attempts_cap=32, panel_seed=panel_seed)
    return snapshot, counters


def test_a3_ordinary_generation_registration_and_refill_share_one_seed(tmp_path):
    """普通生成 → 登记 → 补根：三处根身份与执行种子逐字一致。"""

    panel_seed = SEEDS[0]
    snapshot, counters = _fixture_snapshot(tmp_path, panel_seed=panel_seed)
    assert snapshot is not None, counters
    descriptor = snapshot["root_descriptor"]        # ① 生成侧记录的根描述符
    index = int(descriptor["root_index"])           # 生成器实际命中的那一个根
    assert descriptor["opponent_mix"] == "H", descriptor
    assert snapshot["source_root_id"] == descriptor["root_id"], snapshot["source_root_id"]
    # ② 登记侧：真实登记实现给出的身份/种子必须与生成侧逐字一致。
    state, _ = _state(tmp_path, samples=[_sample(SUB_OPEN, "H", panel_seed, index)])
    records = search._av_family_root_records(state)
    assert len(records) == 1, records
    record = records[0]
    assert record["root_id"] == descriptor["root_id"], (record, descriptor)
    assert int(record["root_seed"]) == int(descriptor["root_seed"]), (record, descriptor)
    # ③ 补根侧：登记表 → 工作项（逐字沿用登记的真实执行种子）。
    registry = search._av_family_root_registry({CHANNEL: {"roots": records}})
    token = "{0}|H|{1}".format(SUB_OPEN, descriptor["root_id"])
    items, blocked = search._av_family_fill_items(
        state={"identity": {"candidate_id": CID_A},
               "plan": {"prefix_source": FIXTURE}},
        outcome={"missing": {CID_A: [token]}}, registry=registry, channel=CHANNEL)
    assert not blocked, blocked
    assert len(items) == 1, items
    assert items[0]["root_ids"] == [descriptor["root_id"]], items
    assert int(items[0]["root_seed"]) == int(descriptor["root_seed"]), items
    # 重建参数（要求摘要）也必须由同一描述符算出。
    digest = search.av_family_root_requirement_digest(
        prefix_source=FIXTURE, predicate=SUB_OPEN, opponent_mix="H",
        panel_seed=panel_seed, root_index=index)
    assert items[0]["root_descriptor"]["root_id"] == descriptor["root_id"]
    assert digest == search.av_family_root_requirement_digest(
        prefix_source=FIXTURE, predicate=SUB_OPEN, opponent_mix="H",
        panel_seed=panel_seed, root_index=index)


def test_a3_legacy_root_without_recorded_seed_is_refused(tmp_path):
    """历史根缺真实执行种子 → 登记表拒绝并说明原因（不静默赋新种子）。"""

    legacy_id = "av-eval-{0}:{0}:root{1:03d}".format(SUB_OPEN, 42)
    row = {"channel": CHANNEL, "sub_scenario": SUB_OPEN, "opponent_mix": "H",
           "root_id": legacy_id, "root_index": 42, "panel_seed": SEEDS[0],
           "seats_per_root": 1, "source": "历史台账"}
    registry = search._av_family_root_registry({CHANNEL: {"roots": [row]}})
    refused = registry.get("refused") or []
    assert refused, registry
    assert legacy_id in json.dumps(refused, ensure_ascii=False), refused
    assert (registry.get("cells") or {}) == {}, registry.get("cells")
    token = "{0}|H|{1}".format(SUB_OPEN, legacy_id)
    items, blocked = search._av_family_fill_items(
        state={"identity": {"candidate_id": CID_A}, "plan": {}},
        outcome={"missing": {CID_A: [token]}}, registry=registry, channel=CHANNEL)
    assert items == [], items
    assert blocked, blocked
    assert "不可恢复" in json.dumps(blocked, ensure_ascii=False), blocked


def test_a3_legacy_record_restores_original_generator_seed(tmp_path):
    """历史普通根：按**原生成器**式子还原种子（不得静默赋新种子）。"""

    legacy_id = "av-eval-{0}:{0}:root{1:03d}".format(SUB_OPEN, 1)
    recorded = int(stage.derive_seed(SEEDS[0], "prefix", legacy_id))
    row = {"channel": CHANNEL, "sub_scenario": SUB_OPEN, "opponent_mix": "H",
           "root_id": legacy_id, "root_index": 1, "panel_seed": SEEDS[0],
           "root_seed": recorded, "seed_derivation": "prefix-v1",
           "seats_per_root": 1, "source": "历史普通生成"}
    resolver = getattr(search, "av_family_root_seed_of_record", None)
    if resolver is None:            # 修复前对照：旧实现按 family 命名空间另算一个
        restored = int(stage.derive_seed(SEEDS[0], "family", SUB_OPEN, "H",
                                         "root", "1"))
    else:
        verdict = resolver(dict(row))
        assert verdict["recovered"] is True, verdict
        restored = int(verdict["root_seed"])
    assert restored == recorded, (restored, recorded)
    # 与"另一套派生式"必须不同：这条断言就是 A3 的反例判据。
    assert restored != int(stage.derive_seed(SEEDS[0], "family", SUB_OPEN, "H",
                                             "root", "1"))


def test_a3_recorded_seed_disagreeing_with_identity_is_refused(tmp_path):
    """记录的真实执行种子与根身份派生不符 → 拒绝采用（不猜、不覆盖）。"""

    index = INDEX[(SUB_OPEN, "H", SEEDS[0])]
    descriptor = _descriptor(SUB_OPEN, "H", SEEDS[0], index)
    row = {"root_id": descriptor["root_id"], "sub_scenario": SUB_OPEN,
           "opponent_mix": "H", "panel_seed": SEEDS[0],
           "root_index": descriptor["root_index"],
           "root_seed": int(descriptor["root_seed"]) + 1}
    resolver = getattr(search, "av_family_root_seed_of_record", None)
    if resolver is None:            # 修复前对照：旧实现直接采信记录里的种子
        verdict = {"recovered": True, "root_seed": row["root_seed"], "problems": []}
    else:
        verdict = resolver(dict(row))
    assert verdict["recovered"] is False, verdict
    assert verdict["problems"], verdict
    registry = search._av_family_root_registry({CHANNEL: {"roots": [row]}})
    assert (registry.get("cells") or {}) == {}, registry

def test_a2_refill_item_root_identity_is_candidate_independent(tmp_path):
    """同一根对两个候选给出的补根工作项必须共享同一来源根身份。

    候选身份属于**评价实例**（av_instance_identity_key 的 candidate 维），不得混进
    共享来源根身份：否则同根对不同候选会变成"两个根"，同根比较与补根复用全部失效。
    """

    index = INDEX[(SUB_OPEN, "H", SEEDS[0])]
    descriptor = _descriptor(SUB_OPEN, "H", SEEDS[0], index)
    rows = [_production(SUB_OPEN, "H", SEEDS[0], index, candidate=candidate)
            for candidate in (CID_A, CID_B)]
    registry = _registry_for(rows)
    token = "{0}|H|{1}".format(SUB_OPEN, descriptor["root_id"])
    built = {}
    for candidate in (CID_A, CID_B):
        items, blocked = search._av_family_fill_items(
            state={"identity": {"candidate_id": candidate},
                   "plan": {"prefix_source": FIXTURE}},
            outcome={"missing": {candidate: [token]}}, registry=registry,
            channel=CHANNEL)
        assert not blocked, blocked
        built[candidate] = items[0]
    assert built[CID_A]["root_ids"] == built[CID_B]["root_ids"] == [descriptor["root_id"]]
    assert int(built[CID_A]["root_seed"]) == int(built[CID_B]["root_seed"])
    assert built[CID_A]["candidate_id"] != built[CID_B]["candidate_id"]
    # 根登记表也必须只有一条共享来源根（同 root_id 不因候选而分叉）。
    assert len(registry.get("cells") or {}) == 1, registry.get("cells")
    # 而评价实例键带候选维：同根对不同候选是两个实例。
    key_a = search.av_instance_identity_key(
        candidate_id=CID_A, opponent_mix="H", panel_seed=SEEDS[0],
        source_root_id=descriptor["root_id"], root_index=index,
        root_seed=descriptor["root_seed"], seat=0, arm="candidate",
        schedule="conditional_stage:2_tables")
    key_b = search.av_instance_identity_key(
        candidate_id=CID_B, opponent_mix="H", panel_seed=SEEDS[0],
        source_root_id=descriptor["root_id"], root_index=index,
        root_seed=descriptor["root_seed"], seat=0, arm="candidate",
        schedule="conditional_stage:2_tables")
    assert key_a != key_b, (key_a, key_b)
