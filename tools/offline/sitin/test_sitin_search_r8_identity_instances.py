# -*- coding: utf-8 -*-
"""S1 专属测试（R8 修复批次）：N4 完整依赖绑定 + A3 实例身份与完成记录。

复审条目：R7-REPAIR-REREVIEW-2026-09-17 §3 N4（P1）/ §4 A3（P1）。
规划：R8-FIX-PLAN-2026-09-17 §2 波次 S · 包 S1。
本文件只覆盖 S1 工作包，不改其他模块，也不改其他包的测试文件。

N4 覆盖（摘要必须绑定**完整规范化依赖清单**）：
  - 冻结摘要对清单里**每一个登记依赖**做内容变异都必须改变运行身份；
  - 四个已知漏项（sitin_search.py / kernel/actions.py / evaluation_v1.py /
    weights_v1.py）由「摘要不变」转为「拒绝恢复」；
  - 基线（V2 固定对照）与对手/驱动同样走真实传递依赖（不再只哈希模块自身）；
  - 端到端：拒绝发生在新费用与新结果写入之前。

A3 覆盖（实例键与完成记录不变量）：
  - 家族实例键含对手情景与面板种子（复审反例①：H/M 同根同索引应留 4 个臂实例）；
  - 自然实例键含候选身份（复审反例②：同运行目录跨候选应留 4 个臂实例）；
  - 已完成记录只能幂等重读，不得降级为 started、不得覆写结果摘要；
  - 真正重试用独立尝试身份（attempt_no）并保留全部历史；
  - 完成度断言同时核对**预期实例总数与全部身份**（不能只数键）；
  - 恢复后全部记录仍在；迭代隔离台账 + 运行级累计镜像两条线都不丢记录。

全部离线（mock 生成 + 替身桌赛），不调真实 LLM、不跑真实桌赛、不消耗授权账目。
"""

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
import sys
import uuid
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import sitin_search as search  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402

#: 批次 7 授权令牌 + 账户额度（替身 runtime：0 真实桌赛，账面照记）。
TOKEN = {"authorized": True, "batch": 7,
         "budgets": {"tokens_input": 100000, "tokens_output": 200000,
                     "tables_full": 256, "tables_partial": 64,
                     "prefix_generation": 64}}

#: 身份完整维度的字段名（N4/A3 共同口径：实例身份 = 这些维度的全序）。
IDENTITY_FIELDS = ("candidate_id", "opponent_mix", "panel_seed", "source_root_id",
                   "seat", "arm", "schedule")


class FakeDrive:
    """替身桌赛驱动（0 真实桌赛）；fail_on_call 在指定调用序号上抛错模拟中断。"""

    def __init__(self, fail_on_call=None):
        self.calls = []
        self.fail_on_call = fail_on_call

    def __call__(self, *, plan, policies_by_seat, versions_block, step_limit,
                 value_limits):
        self.calls.append(plan.table_id)
        if self.fail_on_call is not None and len(self.calls) >= self.fail_on_call:
            raise RuntimeError("S1 注入：桌赛中途中止（第 {0} 次桌执行）".format(
                len(self.calls)))
        seats = list(plan.seats())
        focal_idx = seats.index("focal") if "focal" in seats \
            else seats.index("natural:focal")
        is_candidate = str(getattr(policies_by_seat[focal_idx], "policy_id",
                                   "")).startswith("action_value")
        offset = plan.seed % 7 - 3
        scores = []
        for seat in range(4):
            if seat == focal_idx:
                scores.append(12 + offset if is_candidate else -10 + offset)
            else:
                scores.append(2 - seat + (offset if seat % 2 else -offset))
        return {"table_id": plan.table_id, "seed": int(plan.seed),
                "match_status": "complete", "wall_ms": 1.0,
                "scores_by_seat": scores, "result": {}}


@pytest.fixture
def fake_runtime(monkeypatch):
    monkeypatch.setattr(natural, "execute_natural_table", FakeDrive(), raising=True)


# ------------------------------------------------------------------ 工具


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _run(tmp_path, tag, **kwargs):
    out = Path(tmp_path) / ("s1-" + tag + "-" + uuid.uuid4().hex[:6])
    return out, search.run_av_evolution(out, **kwargs)


def _freeze(tmp_path, tag, stop_after, **kwargs):
    out, result = _run(tmp_path, tag, generation_mode="mock",
                       authorization=TOKEN, stop_after=stop_after, **kwargs)
    assert result.get("stopped_after") == stop_after, result
    return out, search.av_state_load(search.av_latest_state_path(out))


def _ledger_of(run_root):
    return search.ActionValueLedger.load(Path(run_root) / "av-ledger.json")


def _contract():
    return json.loads((search.REPO_ROOT / "review/llm-guided-heuristic-route-2026-09-15"
                       / "contracts/group-dev-v1.json").read_text(encoding="utf-8"))


def _fault(*points):
    def hook(point, **_fields):
        if point in points:
            raise RuntimeError("S1 注入故障：{0}".format(point))

    return hook


def _assert_instances_complete(registry, expected, *, label=""):
    """实例完成度断言：**总数与全部身份**同时核对（不能只数键）。

    只比 key 数量会在「键相同、身份被吞」时误判通过（A3 复审根因），因此这里
    逐条比对预期实例的完整身份字段集合，并要求没有多余实例。
    """

    rows = dict(registry.get("instances") or {})
    want = {row["instance_key"]: row for row in expected}
    assert len(rows) == len(want), (
        "{0}实例总数不符：期望 {1}，实际 {2}（{3}）".format(
            label, len(want), len(rows), sorted(rows)))
    assert set(rows) == set(want), (
        "{0}实例身份集合不符：缺 {1} / 多 {2}".format(
            label, sorted(set(want) - set(rows)), sorted(set(rows) - set(want))))
    for key, expected_row in want.items():
        row = rows[key]
        for field in IDENTITY_FIELDS:
            assert str(row.get(field)) == str(expected_row[field]), (
                "{0}实例 {1} 的身份字段 {2} 不符（{3} != {4}）".format(
                    label, key, field, row.get(field), expected_row[field]))
        assert row.get("status") == "completed", (key, row.get("status"))
        assert row.get("result_digest"), (key, row)


# ===========================================================================
# N4 · 冻结摘要绑定完整规范化依赖清单
# ===========================================================================


def _manifest_and_state(plan=None):
    plan = dict(plan or {"opponent": "H", "natural_roots": 1, "natural_seats": 1,
                         "panel_seed": 20260916})
    manifest = search.av_frozen_manifest(plan=plan)
    state = {"run_id": "n4-probe", "plan": plan,
             "identity": {"frozen_manifest": manifest,
                          "frozen_manifest_digest":
                              search.av_frozen_manifest_digest(manifest)}}
    return plan, manifest, state


def _dependency_paths(manifest):
    """清单里**每一个登记依赖** → 实际文件路径（缺文件的登记项单独列出）。"""

    entries = {}
    for name in (manifest.get("module_closure") or {}):
        origin = search._av_module_origin(name)
        assert origin is not None and Path(origin).is_file(), name
        entries["module:" + name] = Path(origin)
    for name in (manifest.get("baseline_module_closure") or {}):
        origin = search._av_module_origin(name)
        assert origin is not None and Path(origin).is_file(), name
        entries["baseline:" + name] = Path(origin)
    for name in (manifest.get("tool_files") or {}):
        entries["tool:" + name] = search.TOOLS_DIR / name
    for name in (manifest.get("contract_files") or {}):
        entries["contract:" + name] = (search.REPO_ROOT
                                       / "review/llm-guided-heuristic-route-2026-09-15"
                                       / name)
    return entries


def test_n4_manifest_digest_binds_every_registered_dependency(monkeypatch):
    """逐文件内容变异：清单里每个登记依赖改变 → 摘要变化 → 拒绝恢复。"""

    _plan, manifest, state = _manifest_and_state()
    entries = _dependency_paths(manifest)
    assert entries, "清单没有登记任何依赖（完整性无从谈起）"
    real_reader = search.av_dependency_file_reader
    matrix = []
    for label, path in sorted(entries.items()):
        target = Path(path)

        def injected(candidate, _target=target):
            data = real_reader(candidate)
            if Path(candidate) == _target:
                return data + b"\n# N4 injected dependency change\n"
            return data

        monkeypatch.setattr(search, "av_dependency_file_reader", injected,
                            raising=True)
        fresh = search.av_frozen_manifest(plan=state["plan"])
        digest_changed = (search.av_frozen_manifest_digest(fresh)
                          != state["identity"]["frozen_manifest_digest"])
        accepted, reason, _ = search.av_verify_run_identity(state)
        matrix.append({"dependency": label, "path": str(target),
                       "digest_changed": bool(digest_changed),
                       "accepted": bool(accepted)})
        monkeypatch.setattr(search, "av_dependency_file_reader", real_reader,
                            raising=True)
        assert digest_changed, "依赖未参与摘要：{0}（{1}）".format(label, target)
        assert not accepted, "依赖已变但仍放行恢复：{0}（{1}）".format(label, reason)
    print("[N4] 登记依赖逐文件变异矩阵：{0} 项，全部拒绝恢复".format(len(matrix)))


def test_n4_every_registered_dependency_refused_before_new_cost_and_results(
        tmp_path, monkeypatch, fake_runtime):
    """**全部**登记依赖逐文件变异：都在新费用与新结果写入之前拒绝恢复。

    这是 N4 的逐文件验收矩阵（文件 → 预期拒绝 → 实际）：一次开轮冻结之后，对清单里
    每一个登记依赖各注入一次内容改变并尝试恢复；每次都必须被拒，且账本额度与结果
    文件一个字节都不变（不续写旧结果、不产生新费用）。
    """

    _plan, manifest, _probe_state = _manifest_and_state()
    entries = _dependency_paths(manifest)
    out, state = _freeze(tmp_path, "n4-matrix", "CONDITIONAL_EVALUATED")
    iter_dir = Path(state["iter_dir"])
    real_reader = search.av_dependency_file_reader
    before = _ledger_of(out).account_summary()
    accepted = []
    for label, path in sorted(entries.items()):
        target = Path(path)

        def injected(candidate, _target=target):
            data = real_reader(candidate)
            if Path(candidate) == _target:
                return data + b"\n# N4 end-to-end mutation\n"
            return data

        monkeypatch.setattr(search, "av_dependency_file_reader", injected,
                            raising=True)
        refused = search.run_av_machine_resume(out, run_id=state["run_id"],
                                               authorization=TOKEN)
        monkeypatch.setattr(search, "av_dependency_file_reader", real_reader,
                            raising=True)
        if not refused.get("refused") or "身份" not in str(refused.get("refused")):
            accepted.append("{0}（{1}）".format(label, refused.get("refused")))
        assert _ledger_of(out).account_summary() == before, (
            "拒绝前已产生新费用：{0}".format(label))
        assert not list(iter_dir.glob("natural-*")), (
            "拒绝前已写入新结果：{0}".format(label))
    assert not accepted, "以下登记依赖变更后仍被放行恢复：{0}".format(accepted)
    print("[N4] 端到端逐文件变异：{0} 个登记依赖全部拒绝恢复（零新费用、零新结果）"
          .format(len(entries)))


#: 复审点名的四个漏项 + 一个对照组（对照组本来就该拒绝）。
N4_KNOWN_GAPS = ("sitin_search.py", "actions.py", "evaluation_v1.py",
                 "weights_v1.py", "hand_analysis.py")


@pytest.mark.parametrize("filename", N4_KNOWN_GAPS)
def test_n4_known_gaps_refused_before_new_cost(tmp_path, monkeypatch, fake_runtime,
                                               filename):
    """四个已知漏项 + 对照：身份变更在**新费用与新结果**之前拒绝恢复。"""

    out, state = _freeze(tmp_path, "n4-" + filename, "CONDITIONAL_EVALUATED")
    before = _ledger_of(out).account_summary()
    iter_dir = Path(state["iter_dir"])
    real_reader = search.av_dependency_file_reader

    def injected(candidate):
        data = real_reader(candidate)
        return (data + b"\n# N4 injected method-body change\n"
                if Path(candidate).name == filename else data)

    monkeypatch.setattr(search, "av_dependency_file_reader", injected, raising=True)
    refused = search.run_av_machine_resume(out, run_id=state["run_id"],
                                           authorization=TOKEN)
    assert refused.get("refused"), "{0} 变更但恢复被放行".format(filename)
    assert "身份" in refused["refused"], refused["refused"]
    assert _ledger_of(out).account_summary() == before, "拒绝前已产生新费用"
    assert not list(iter_dir.glob("natural-*")), "拒绝前已写入新结果"
    fresh = search.av_state_load(search.av_latest_state_path(out))
    assert fresh["status"] == "CONDITIONAL_EVALUATED", fresh["status"]


def test_n4_baseline_and_opponent_go_through_real_transitive_dependency():
    """基线（V2 固定对照）与对手/驱动同样走真实传递依赖，不是只哈希模块自身。"""

    _plan, manifest, _state = _manifest_and_state()
    baseline = manifest["surfaces"]["baseline"]["modules"]
    for module in ("hangma_bot.policy.evaluation_v1",
                   "hangma_bot.policy.weights_v1",
                   "hangma_bot.kernel.actions"):
        assert module in baseline, (
            "基线面缺实际影响 V2 的传递依赖 {0}：{1}".format(
                module, sorted(baseline)))
        origin = search._av_module_origin(module)
        assert origin is not None
        assert baseline[module] == hashlib.sha256(Path(origin).read_bytes()).hexdigest()
    # 对手/驱动面同样登记真实文件（不是只记一个名字）。
    assert manifest["surfaces"]["simulator"]["modules"], manifest["surfaces"]["simulator"]
    assert manifest["surfaces"]["opponent"]["contracts"]


# ===========================================================================
# A3 · 复现反例①：家族实例（同候选、同子场景、同索引、跨 H/M 与种子）
# ===========================================================================


def _family_item(*, mix, seed, index=3, candidate="cand-family"):
    sub = "branch_open"
    # R9/A2：根身份是**完整身份**（生成器 × 子场景 × 情景 × 实际种子 × 根序号）；
    # 同索引的 H 与 M 因此是两个不同的根（各自的牌山）。
    descriptor = search.av_family_root_descriptor(
        prefix_source="scripted_fixture", sub_scenario=sub, opponent_mix=mix,
        panel_seed=seed, root_index=index)
    return {"candidate_id": candidate, "sub_scenario": sub, "opponent_mix": mix,
            "panel_seed": seed, "root_indexes": [index],
            "root_ids": [str(descriptor["root_id"])],
            "root_seed": int(descriptor["root_seed"]),
            "prefix_source": "scripted_fixture",
            "seats_per_root": 1, "planned_tables": search.AV_TABLES_PER_FAMILY_EVALUATION,
            "kind": "missing_root", "token": "{0}-s{1}-idx{2}".format(mix, seed, index),
            "step_prefix": search._av_family_step_prefix(candidate, sub,
                                                         "{0}-s{1}-idx{2}".format(
                                                             mix, seed, index))}


def test_a3_family_instances_keep_four_arms_across_mix_and_seed(tmp_path):
    """复审反例①：同候选/同子场景/同索引的 H 与 M 必须各留 2 个臂实例（共 4 个）。"""

    root_dir = Path(tmp_path) / "family-instances"
    root_dir.mkdir()
    reports = {}

    def _register(mix, seed):
        rows = search._av_family_expected_instances(
            _family_item(mix=mix, seed=seed), 2)
        assert len(rows) == 2, rows
        for status in ("started", "completed"):
            search.av_instances_apply(
                root_dir,
                updates=[dict(row, status=status, tables=2,
                              result_digest="{0}-{1}-result".format(mix, seed))
                         for row in rows],
                attempt_no=1, iteration_no=1, run_id="probe")
        reports[(mix, seed)] = rows
        return rows

    # ① 复审反例原形：同候选、同子场景、同根索引，只有对手情景不同（同一种子）。
    _register("H", 7)
    _register("M", 7)
    rows = search.av_instances_load(root_dir)["instances"]
    assert len(rows) == 4, ("家族情景合并成 {0} 个实例（应 4 个）：{1}".format(
        len(rows), sorted(rows)))
    assert sorted({row["opponent_mix"] for row in rows.values()}) == ["H", "M"]
    assert sorted(row["result_digest"] for row in rows.values()) == [
        "H-7-result", "H-7-result", "M-7-result", "M-7-result"]
    h_keys = {row["instance_key"] for row in reports[("H", 7)]}
    m_keys = {row["instance_key"] for row in reports[("M", 7)]}
    assert h_keys.isdisjoint(m_keys), sorted(h_keys | m_keys)
    assert h_keys <= set(rows) and m_keys <= set(rows)
    # ② 跨种子：同一候选/子场景/索引换面板种子 → 又两个真实实例（不与他人互吞）。
    _register("H", 8)
    rows = search.av_instances_load(root_dir)["instances"]
    assert len(rows) == 6, sorted(rows)
    assert sorted(int(row["panel_seed"]) for row in rows.values()) == [
        7, 7, 7, 7, 8, 8]
    seed_keys = {row["instance_key"] for row in reports[("H", 8)]}
    assert seed_keys.isdisjoint(h_keys)


# ===========================================================================
# A3 · 复现反例②：自然面板跨候选共享台账（同根、同座位、同赛程）
# ===========================================================================


def test_a3_natural_instances_keep_four_arms_across_candidates(tmp_path):
    """复审反例②：同运行目录两次候选评价必须各留 2 个臂实例（共 4 个）。"""

    contract = _contract()
    plan_a = {"natural_roots": 1, "natural_seats": 1, "panel_seed": 7,
              "candidate_id": "candidate-A"}
    plan_b = dict(plan_a, candidate_id="candidate-B")
    rows_a = search._av_natural_expected_instances(plan_a, contract, "H")
    rows_b = search._av_natural_expected_instances(plan_b, contract, "H")
    assert len(rows_a) == 2 and len(rows_b) == 2
    assert {row["instance_key"] for row in rows_a}.isdisjoint(
        {row["instance_key"] for row in rows_b}), (
            "跨候选实例键相同（缺候选身份）：{0}".format(
                sorted(row["instance_key"] for row in rows_a)))
    run_root = Path(tmp_path) / "instances-normal"
    run_root.mkdir()
    for iteration_no, (cid, rows) in enumerate((("candidate-A", rows_a),
                                                ("candidate-B", rows_b)), 1):
        for status in ("started", "completed"):
            search.av_instances_apply(
                run_root,
                updates=[dict(row, status=status, tables=2,
                              result_digest=cid + "-result") for row in rows],
                attempt_no=1, iteration_no=iteration_no, run_id=cid + "-run")
    registry = search.av_instances_load(run_root)
    rows = registry["instances"]
    assert len(rows) == 4, ("跨候选合并成 {0} 个实例（应 4 个）：{1}".format(
        len(rows), sorted(rows)))
    assert sorted({row["run_id"] for row in rows.values()}) == ["candidate-A-run",
                                                                "candidate-B-run"]
    assert sorted(row["result_digest"] for row in rows.values()) == [
        "candidate-A-result", "candidate-A-result",
        "candidate-B-result", "candidate-B-result"]
    for row in rows.values():
        assert str(row.get("candidate_id")) in ("candidate-A", "candidate-B"), row


def test_a3_natural_instances_distinguish_seed_and_root_index():
    """同候选跨种子/跨根索引：键必须可分（根内容与随机映射在身份内）。"""

    contract = _contract()
    base = {"natural_roots": 1, "natural_seats": 1, "panel_seed": 7,
            "candidate_id": "cand-1"}
    keys = {}
    for seed in (7, 8):
        plan = dict(base, panel_seed=seed)
        keys[seed] = {row["instance_key"]
                      for row in search._av_natural_expected_instances(
                          plan, contract, "H")}
    assert keys[7].isdisjoint(keys[8]), sorted(keys[7] | keys[8])
    assert len(keys[7]) == 2 and len(keys[8]) == 2


# ===========================================================================
# A3 · 完成记录不可降级、不可覆写；重试用独立尝试身份
# ===========================================================================


def _one_row(root_dir, **overrides):
    row = {"instance_key": "k1", "candidate_id": "cand-1", "opponent_mix": "H",
           "panel_seed": 7, "source_root_id": "np-H-7-root01", "root_index": 1,
           "seat": 0, "arm": "candidate", "schedule": "stage_complete:2_tables",
           "evaluation_scope": "candidate_evaluation", "cache_key": "ck1",
           "planned_tables": 2}
    row.update(overrides)
    return row


def test_a3_completed_record_is_never_downgraded_or_overwritten(tmp_path):
    """completed → started 不得回退；同 attempt_no 不得覆写已完成结果摘要。"""

    root_dir = Path(tmp_path) / "reg"
    root_dir.mkdir()
    rows = [_one_row(root_dir)]
    search.av_instances_apply(root_dir, updates=[dict(rows[0], status="started")],
                              attempt_no=1, iteration_no=1, run_id="run-1")
    search.av_instances_apply(root_dir,
                              updates=[dict(rows[0], status="completed",
                                            tables=2, result_digest="D-one",
                                            result_path="p.json")],
                              attempt_no=1, iteration_no=1, run_id="run-1")
    before = search.av_instances_load(root_dir)["instances"]["k1"]
    assert before["status"] == "completed" and before["result_digest"] == "D-one"
    # 复现复审缺陷：同一个 attempt_no 再登记 started（例如检查点丢失后的旧计数器）。
    stale = search.av_instances_apply(root_dir,
                                      updates=[dict(rows[0], status="started")],
                                      attempt_no=1, iteration_no=2, run_id="run-2")
    after = search.av_instances_load(root_dir)["instances"]["k1"]
    assert after["status"] == "completed", "已完成记录被降级为 started"
    assert after["result_digest"] == "D-one", "已完成结果摘要被覆盖"
    assert [item["status"] for item in after["attempts"]] == ["completed"], after
    assert after["attempts"][0]["attempt_no"] == 1
    assert stale["conflicts"] or stale.get("idempotent") or stale.get("stale"), stale
    # 同 attempt_no 换一个新摘要 → 冲突，不覆盖。
    conflict = search.av_instances_apply(
        root_dir,
        updates=[dict(rows[0], status="completed", tables=2,
                      result_digest="D-two", result_path="p2.json")],
        attempt_no=1, iteration_no=3, run_id="run-3")
    final = search.av_instances_load(root_dir)["instances"]["k1"]
    assert final["result_digest"] == "D-one", "已完成结果摘要被覆写"
    assert final["cost"]["tables"] == 2
    assert conflict["conflicts"], conflict


def test_a3_retry_uses_independent_attempt_identity_and_keeps_history(tmp_path):
    """真正重试：新 attempt_no 记新历史，旧尝试记录与已完成摘要都保留。"""

    root_dir = Path(tmp_path) / "reg-retry"
    root_dir.mkdir()
    base = _one_row(root_dir)
    search.av_instances_apply(root_dir, updates=[dict(base, status="started")],
                              attempt_no=1, iteration_no=1, run_id="run-1")
    search.av_instances_apply(root_dir,
                              updates=[dict(base, status="completed", tables=2,
                                            result_digest="D-one")],
                              attempt_no=1, iteration_no=1, run_id="run-1")
    search.av_instances_apply(root_dir, updates=[dict(base, status="started")],
                              attempt_no=2, iteration_no=1, run_id="run-1")
    mid = search.av_instances_load(root_dir)["instances"]["k1"]
    assert [item["attempt_no"] for item in mid["attempts"]] == [1, 2], mid["attempts"]
    assert mid["status"] == "completed", "重试起步把已完成记录降级了"
    assert mid["result_digest"] == "D-one"
    assert mid["retry_attempt_no"] == 2
    # 重试重放出同一份结果：接受为 attempt 2 的完成，已完成记录本身不漂移。
    search.av_instances_apply(root_dir,
                              updates=[dict(base, status="completed", tables=2,
                                            result_digest="D-one")],
                              attempt_no=2, iteration_no=1, run_id="run-1")
    final = search.av_instances_load(root_dir)["instances"]["k1"]
    assert sorted(item["attempt_no"] for item in final["attempts"]) == [1, 2]
    assert final["attempts"][0]["result_digest"] == "D-one", "尝试 1 的历史被替换"
    assert final["attempts"][1]["result_digest"] == "D-one"
    assert final["completed"]["attempt_no"] == 1, "首份完成记录被重试改写"
    assert final["result_digest"] == "D-one"
    # 重试产出**不同**结果：冲突（不覆写），与既有面板台账同一口径。
    conflict = search.av_instances_apply(
        root_dir,
        updates=[dict(base, status="completed", tables=2, result_digest="D-two")],
        attempt_no=3, iteration_no=1, run_id="run-1")
    assert conflict["conflicts"], conflict
    final2 = search.av_instances_load(root_dir)["instances"]["k1"]
    assert final2["result_digest"] == "D-one", "已完成摘要被重试覆写"
    assert [item["attempt_no"] for item in final2["attempts"]] == [1, 2], (
        final2["attempts"])


def test_a3_same_key_different_identity_is_conflict(tmp_path):
    """同键不同身份（面板种子/情景被换）必须记冲突，不得静默合并。"""

    root_dir = Path(tmp_path) / "reg-identity"
    root_dir.mkdir()
    row = _one_row(root_dir)
    search.av_instances_apply(root_dir,
                              updates=[dict(row, status="completed", tables=2,
                                            result_digest="D-one")],
                              attempt_no=1, iteration_no=1, run_id="run-1")
    report = search.av_instances_apply(
        root_dir,
        updates=[dict(row, panel_seed=9, status="completed", tables=2,
                      result_digest="D-two")],
        attempt_no=1, iteration_no=1, run_id="run-1")
    assert report["conflicts"], report
    row_after = search.av_instances_load(root_dir)["instances"]["k1"]
    assert int(row_after["panel_seed"]) == 7, "身份字段被静默改写"
    assert row_after["result_digest"] == "D-one"


def test_a3_shared_baseline_cache_is_distinct_from_candidate_evaluation(tmp_path):
    """候选评价与「候选/基线共享缓存」的两种身份必须显式可分。"""

    rows = search._av_family_expected_instances(_family_item(mix="H", seed=7), 2)
    by_arm = {row["arm"]: row for row in rows}
    assert set(by_arm) == {"baseline", "candidate"}
    candidate_row, baseline_row = by_arm["candidate"], by_arm["baseline"]
    assert candidate_row["instance_key"] != baseline_row["instance_key"]
    assert candidate_row.get("evaluation_scope") == "candidate_evaluation"
    assert baseline_row.get("evaluation_scope") == "shared_baseline_cache"
    assert candidate_row.get("cache_key") == candidate_row["instance_key"]
    # 共享基线缓存的键不含候选身份：两个候选的基线臂指向同一份缓存结果。
    other = {row["arm"]: row for row in search._av_family_expected_instances(
        _family_item(mix="H", seed=7, candidate="cand-other"), 2)}
    assert other["baseline"]["cache_key"] == baseline_row["cache_key"]
    assert other["baseline"]["instance_key"] != baseline_row["instance_key"]
    assert other["candidate"]["cache_key"] != candidate_row["cache_key"]


# ===========================================================================
# A3 · 端到端：迭代隔离台账 + 运行级镜像 + 恢复后记录仍在
# ===========================================================================


def test_a3_end_to_end_iteration_ledger_and_identity_completeness(tmp_path,
                                                                  fake_runtime):
    """公开入口跑完一个迭代：迭代台账 + 运行级镜像；完成度核对总数与全部身份。"""

    out, result = _run(tmp_path, "a3-e2e", generation_mode="mock",
                       authorization=TOKEN)
    assert result.get("terminal") == "ITERATION_COMPLETE", result
    state = search.av_state_load(search.av_latest_state_path(out))
    iter_dir = Path(state["iter_dir"])
    contract = _contract()
    candidate_id = str(state["identity"]["candidate_id"])
    expected = []
    for mix in ("H", "M"):
        expected.extend(search._av_natural_expected_instances(
            state["plan"], contract, mix, candidate_id=candidate_id))
    assert len(expected) == 4, expected
    # ① 迭代隔离台账：本次迭代的任务写在 iter_dir/instances.json。
    assert search.av_instances_path(iter_dir) == iter_dir / "instances.json"
    iter_registry = search.av_instances_load(iter_dir)
    _assert_instances_complete(iter_registry, expected, label="迭代台账")
    # ② 运行级累计镜像仍可读（既有消费者口径不变）。
    run_registry = search.av_instances_load(out)
    run_rows = {key: row for key, row in run_registry["instances"].items()
                if key in {row["instance_key"] for row in expected}}
    assert len(run_rows) == 4, sorted(run_registry["instances"])
    _assert_instances_complete({"instances": run_rows}, expected, label="运行镜像")


def test_a3_records_survive_resume_after_interrupt(tmp_path, monkeypatch,
                                                   fake_runtime):
    """中断后恢复：已完成实例一条不少，且没有把别的任务记录顶掉。"""

    monkeypatch.setattr(search, "av_fault_point",
                        _fault("natural:M:after_reserve"), raising=True)
    out = Path(tmp_path) / ("s1-a3-resume-" + uuid.uuid4().hex[:6])
    with pytest.raises(RuntimeError):
        search.run_av_evolution(out, generation_mode="mock", authorization=TOKEN)
    monkeypatch.setattr(search, "av_fault_point", lambda *a, **k: None, raising=True)
    state = search.av_state_load(search.av_latest_state_path(out))
    iter_dir = Path(state["iter_dir"])
    contract = _contract()
    candidate_id = str(state["identity"]["candidate_id"])
    expected = []
    for mix in ("H", "M"):
        expected.extend(search._av_natural_expected_instances(
            state["plan"], contract, mix, candidate_id=candidate_id))
    interrupted = search.av_instances_load(iter_dir)["instances"]
    interrupted_keys = set(interrupted)
    assert interrupted_keys, "中断前没有落任何实例（先落盘后执行被破坏）"
    h_completed = {key for key, row in interrupted.items()
                   if str(row.get("opponent_mix")) == "H"
                   and row.get("status") == "completed"}
    assert h_completed, interrupted
    resumed = search.run_av_machine_resume(out, run_id=state["run_id"],
                                           authorization=TOKEN)
    assert resumed.get("terminal") == "ITERATION_COMPLETE", resumed.get("refused")
    after = search.av_instances_load(iter_dir)
    _assert_instances_complete(after, expected, label="恢复后迭代台账")
    assert interrupted_keys <= set(after["instances"]), (
        "恢复吞掉了中断前的实例记录：{0}".format(
            sorted(interrupted_keys - set(after["instances"]))))
    mirror = search.av_instances_load(out)
    _assert_instances_complete(
        {"instances": {key: row for key, row in mirror["instances"].items()
                       if key in {row["instance_key"] for row in expected}}},
        expected, label="恢复后运行镜像")
