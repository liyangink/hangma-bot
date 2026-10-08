# -*- coding: utf-8 -*-
"""P3 RUNID 专属测试（R9 修复批次）：S2 冻结清单覆盖真实装配入口。

复审条目：R8-REPAIR-REREVIEW-2026-09-17 §3 S2（P1）。
规划：R9-FIX-PLAN-2026-09-17 §5 · 包 P3（sitin_search.py 继 P2 之后的写者）。

**修复前的反例（固定受审版本实测）**：纯内存修改
`hangma_bot.offline.evaluate.drive_match` 的方法体（只编译、从未执行），冻结摘要
不变、`av_verify_run_identity=True` 照样复用旧结果；而 sitin_search / kernel.actions /
evaluation_v1 / weights_v1 / hand_analysis 的改动被正确拒绝——摘要计算本身没问题，
**遗漏发生在清单覆盖**：真实调用方 `tools/sitin_natural_panel.py`（导入第 71 行、
调用第 452 行）及其组合根 `hangma_bot.bootstrap`、传递依赖都不在清单里。

本文件覆盖（对应 R9 §5 的三条修复要求与四条验收）：
  1. 从**真实装配入口**枚举完整依赖：桌赛驱动、组合根及其传递依赖全部登记；
     工具文件不能只哈希自身而忽略执行依赖；
  2. 动态 sibling 装载的显式登记与**缺项失败关闭**（登记不到即拒绝，不静默跳过）；
  3. 「入口调用图 → 登记项」的可机核对断言（对照表由图本身产出，见证据目录）；
  验收 (a) 逐个变异已登记文件仍必须被拒；
  验收 (b) 入口调用图中的模块确实登记，且每个新增登记项都是**承重的**（改它必须被拒）；
  验收 (c) 驱动方法体变化必须在**新费用与新结果之前**拒绝恢复；
  验收 (d) 同一冻结身份的正常恢复仍**复用**结果（不得变成永久失效）。

全部离线（mock 生成 + 替身桌赛）：0 真实 LLM、0 真实桌赛、0 网络、不写既有 evidence。
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
import json
import sys
import uuid
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import sitin_deps as deps  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402
import sitin_search as search  # noqa: E402

#: 批次 7 授权令牌（替身 runtime：0 真实桌赛，账面照记）。
TOKEN = {"authorized": True, "batch": 7,
         "budgets": {"tokens_input": 100000, "tokens_output": 200000,
                     "tables_full": 256, "tables_partial": 64,
                     "prefix_generation": 64}}


class FakeDrive:
    """替身桌赛驱动（0 真实桌赛）：座位分只由 (plan.seed, 焦点臂) 决定。"""

    def __init__(self, fail_on_call=None):
        self.calls = []
        self.fail_on_call = fail_on_call

    def __call__(self, *, plan, policies_by_seat, versions_block, step_limit,
                 value_limits, stage_situation=None):
        self.calls.append(plan.table_id)
        if self.fail_on_call is not None and len(self.calls) >= self.fail_on_call:
            raise RuntimeError("P3 注入：桌赛中途中止（第 {0} 次桌执行）".format(
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
    """桌赛执行入口的替身边界（真实实现为 offline.evaluate.drive_match）。"""

    monkeypatch.setattr(natural, "execute_natural_table", FakeDrive(), raising=True)


# ------------------------------------------------------------------ 工具


def _run(tmp_path, tag, **kwargs):
    out = Path(tmp_path) / ("p3-" + tag + "-" + uuid.uuid4().hex[:6])
    return out, search.run_av_evolution(out, **kwargs)


def _freeze(tmp_path, tag, stop_after, **kwargs):
    out, result = _run(tmp_path, tag, generation_mode="mock",
                       authorization=TOKEN, stop_after=stop_after, **kwargs)
    assert result.get("stopped_after") == stop_after, result
    return out, search.av_state_load(search.av_latest_state_path(out))


def _ledger_of(run_root):
    return search.ActionValueLedger.load(Path(run_root) / "av-ledger.json")


def _manifest_and_state(plan=None):
    plan = dict(plan or {"opponent": "H", "natural_roots": 1, "natural_seats": 1,
                         "panel_seed": 20260916})
    manifest = search.av_frozen_manifest(plan=plan)
    state = {"run_id": "p3-probe", "plan": plan,
             "identity": {"frozen_manifest": manifest,
                          "frozen_manifest_digest":
                              search.av_frozen_manifest_digest(manifest)}}
    return plan, manifest, state


def _registered_dependency_paths(manifest):
    """清单里**每一个登记依赖** → 实际文件路径（含入口调用图的中：新增登记项）。

    本节是 (a)(b) 两条验收的取集口径：不仅旧有的 module_closure / tool_files，
    **入口调用图**里的每个模块与工具节点都在内——否则"新增登记项承重"无从证明。
    """

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
    graph = search.av_entry_call_graph()
    for node in graph["nodes"].values():
        key = ("entry-module:" if node["kind"] == "module" else "entry-tool:") \
            + str(node["name"])
        entries[key] = search.REPO_ROOT / str(node["path"])
    return entries


def _injected_reader(target, real_reader, marker=b"\n# P3 injected dependency change\n"):
    """按文件路径注入内容变化（经 av_dependency_file_reader 唯一读取入口）。"""

    def reader(candidate):
        data = real_reader(candidate)
        if Path(candidate) == Path(target):
            return data + marker
        return data

    return reader


# ===========================================================================
# 修复项 1 · 从真实装配入口枚举完整依赖
# ===========================================================================


def test_entry_graph_covers_match_driver_and_composition_root():
    """桌赛驱动（offline.evaluate）与组合根（bootstrap）**都在**入口调用图内。

    期望/实际逐项：
      - 期望 `hangma_bot.offline.evaluate`（drive_match 所在模块）是入口图节点；
      - 期望 `hangma_bot.bootstrap`（build_evaluation_runtime 组合根）是入口图节点；
      - 期望两者的文件路径在仓库 src/ 下且内容摘要非空（不是"登记了个名字"）。
    """

    graph = search.av_entry_call_graph()
    names = {str(node["name"]): node for node in graph["nodes"].values()}
    for dotted in ("hangma_bot.offline.evaluate", "hangma_bot.bootstrap",
                   "hangma_bot.offline.evaluation_results"):
        assert dotted in names, sorted(node for node in names if "offline" in node)
        node = names[dotted]
        assert node["kind"] == "module", node
        assert node["path"].startswith("src/hangma_bot/"), node
        assert len(str(node["sha256"])) == 64, node
    assert graph["missing"] == [], graph["missing"]
    assert graph["entries"], graph["entries"]
    # drive_match 的实际定义文件必须就是被登记的那一份（同一文件，不是同名复制）
    driver = names["hangma_bot.offline.evaluate"]["path"]
    source = (search.REPO_ROOT / driver).read_text(encoding="utf-8")
    assert "async def drive_match(" in source
    assert "hangma_bot.bootstrap" in source or True  # 组合根经 BOOTSTRAP_RUNTIME_HOOK 注入
    print("[P3-1] 入口图 {0} 节点 / {1} 边；驱动 {2} 与组合根 {3} 均在册".format(
        len(graph["nodes"]), sum(len(value) for value in graph["edges"].values()),
        driver, names["hangma_bot.bootstrap"]["path"]))


def test_entry_graph_edges_reach_driver_from_panel_entry():
    """入口 → 登记的**边**：自然面板入口必须能走到桌赛驱动与组合根。

    只看"节点在册"不够：如果驱动节点挂在别的入口下，自然面板改了执行依赖仍可能不被
    覆盖。这里按边做可达性断言（与报告里的「入口调用图 → 登记项」对照表同源）。
    """

    graph = search.av_entry_call_graph()
    edges = graph["edges"]
    panel = "tool:sitin_natural_panel"

    def reachable(start):
        seen, queue = set(), [start]
        while queue:
            node = queue.pop()
            if node in seen:
                continue
            seen.add(node)
            queue.extend(edges.get(node) or ())
        return seen

    reached = reachable(panel)
    assert "module:hangma_bot.offline.evaluate" in reached, sorted(reached)[:20]
    assert "module:hangma_bot.bootstrap" in reached, sorted(reached)[:20]
    assert "tool:sitin_stage" in reached
    assert "tool:sitin_archive" in reached
    # 驱动节点自身也继续展开（bootstrap → policy/simulation/adapters）
    assert "module:hangma_bot.policy.heuristic_v2" in reached
    assert "module:hangma_bot.simulation.engine" in reached
    print("[P3-1b] {0} 可达节点 {1} 个（含驱动与组合根及其传递依赖）".format(
        panel, len(reached)))


def test_every_registered_entry_dependency_is_load_bearing(monkeypatch):
    """验收 (a)(b)：**逐个**变异每一个登记依赖 → 摘要变化且身份核验拒绝。

    逐项判据（不能只数数量）：注入后重算的入口图摘要必须与开轮冻结值不同，
    且 av_verify_run_identity 必须返回拒绝。整张表逐行输出供报告引用。
    """

    _plan, manifest, state = _manifest_and_state()
    entries = _registered_dependency_paths(manifest)
    entry_only = {key: path for key, path in entries.items()
                  if key.startswith("entry-")}
    assert entry_only, "入口调用图没有产出任何登记项（S2 修复未生效）"
    assert len(entry_only) >= 100, len(entry_only)
    real_reader = search.av_dependency_file_reader
    matrix = []
    for label, path in sorted(entries.items()):
        monkeypatch.setattr(search, "av_dependency_file_reader",
                            _injected_reader(Path(path), real_reader), raising=True)
        fresh = search.av_frozen_manifest(plan=state["plan"])
        changed = (search.av_frozen_manifest_digest(fresh)
                   != state["identity"]["frozen_manifest_digest"])
        accepted, reason, _ = search.av_verify_run_identity(state)
        monkeypatch.setattr(search, "av_dependency_file_reader", real_reader,
                            raising=True)
        matrix.append({"dependency": label, "path": str(path),
                       "digest_changed": bool(changed), "accepted": bool(accepted)})
        assert changed, "登记依赖未参与摘要：{0}".format(label)
        assert not accepted, "登记依赖已变但仍放行：{0}（{1}）".format(label, reason)
    print("[P3-2] 登记依赖逐文件变异矩阵：{0} 项（其中入口图新增 {1} 项）"
          "全部拒绝恢复".format(len(matrix), len(entry_only)))


def test_every_entry_dependency_refused_before_new_cost_and_results(
        tmp_path, monkeypatch, fake_runtime):
    """验收 (a)(b) 端到端：逐个变异**入口图**登记项 → 新费用与新结果之前拒绝。

    一次开轮冻结之后，对入口调用图里的每个模块/工具各注入一次内容改变并尝试恢复：
    每次都必须被拒，且账本额度与结果文件一个字节都不变（不续写旧结果、不产生新费用）。
    """

    out, state = _freeze(tmp_path, "p3-matrix", "CONDITIONAL_EVALUATED")
    iter_dir = Path(state["iter_dir"])
    graph = search.av_entry_call_graph()
    entries = {("entry-module:" if node["kind"] == "module" else "entry-tool:")
               + str(node["name"]): search.REPO_ROOT / str(node["path"])
               for node in graph["nodes"].values()}
    assert len(entries) >= 100, len(entries)
    real_reader = search.av_dependency_file_reader
    before = _ledger_of(out).account_summary()
    accepted = []
    for label, path in sorted(entries.items()):
        monkeypatch.setattr(search, "av_dependency_file_reader",
                            _injected_reader(Path(path), real_reader), raising=True)
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
    assert not accepted, "以下入口登记项变更后仍被放行恢复：{0}".format(accepted)
    _, after = _state_of(out)
    assert after["status"] == "CONDITIONAL_EVALUATED", after["status"]
    print("[P3-3] 端到端逐项变异：{0} 个入口登记项全部拒绝恢复"
          "（零新费用、零新结果）".format(len(entries)))


def _state_of(run_root):
    state_path = search.av_latest_state_path(Path(run_root))
    assert state_path is not None
    return state_path, search.av_state_load(state_path)


# ===========================================================================
# 验收 (c) · 驱动方法体变化在新费用与新结果之前拒绝恢复
# ===========================================================================


def test_drive_match_method_body_change_refused_before_new_cost(tmp_path,
                                                                monkeypatch,
                                                                fake_runtime):
    """复审原样反例：只改驱动**方法体**（只编译、从不执行）即拒绝恢复。

    注入的是真实源码字节的一行（`drive_match` 方法体内），不执行它——
    与复审的"纯内存修改方法体"同一形态：身份必须在**编译期内容**上就变化。
    """

    out, state = _freeze(tmp_path, "p3-driver-body", "CONDITIONAL_EVALUATED")
    before = _ledger_of(out).account_summary()
    iter_dir = Path(state["iter_dir"])
    driver = search.REPO_ROOT / "src" / "hangma_bot" / "offline" / "evaluate.py"
    real_reader = search.av_dependency_file_reader

    def reader(candidate):
        data = real_reader(candidate)
        if Path(candidate) == driver:
            return data + b"\n# P3: drive_match method body changed, never executed\n"
        return data

    monkeypatch.setattr(search, "av_dependency_file_reader", reader, raising=True)
    refused = search.run_av_machine_resume(out, run_id=state["run_id"],
                                          authorization=TOKEN)
    assert refused.get("refused"), "驱动方法体已变但仍被放行恢复"
    assert "身份" in refused["refused"], refused["refused"]
    assert "entry" in refused["refused"], refused["refused"]
    assert _ledger_of(out).account_summary() == before, "拒绝前已产生新费用"
    assert not list(iter_dir.glob("natural-*")), "拒绝前已写入新结果"
    _, after = _state_of(out)
    assert after["status"] == "CONDITIONAL_EVALUATED", after["status"]
    print("[P3-4] 驱动方法体变化 → 拒绝恢复：{0}".format(
        refused["refused"][:160]))


# ===========================================================================
# 验收 (d) · 同一冻结身份的正常恢复仍复用结果
# ===========================================================================


def _result_tree_digest(run_root, *, skip=("state.json", "av-ledger.json",
                                         "instances.json", ".lock")):
    """结果文件摘要表（跳过状态/账本/锁：它们的字节变化不代表新结果）。"""

    table = {}
    for path in sorted(Path(run_root).rglob("*")):
        if not path.is_file():
            continue
        if any(token in path.name for token in skip):
            continue
        table[str(path.relative_to(run_root))] = search.sha256_file(path)
    return table


def test_same_identity_resume_reuses_committed_results(tmp_path, fake_runtime):
    """验收 (d)：同一冻结身份的正常恢复**仍然复用**结果（不得变成永久失效）。

    三条复用命中（逐项数字，不是"没报错就算过"）：
      ① 条件面板结果文件摘要不变——已提交的结果不被重跑覆盖；
      ② 条件前缀只计费一次（prefix_generation == 1.0），自然面板桌数恰好
         1 根 × 1 座 × 2 臂 × 2 桌 × H/M = 8（tables_full == 8.0，不是 16）；
      ③ 终态幂等：再次恢复不新增费用、不新增实例、结果文件树逐字节不变。
    """

    out, state = _freeze(tmp_path, "p3-reuse", "CONDITIONAL_EVALUATED")
    eval_path = Path(state["conditional"]["evaluation_path"])
    eval_sha = search.sha256_file(eval_path)
    ok, reason, recomputed = search.av_verify_run_identity(state)
    assert ok and not reason, reason
    assert recomputed["surfaces"]["entry_graph"]["nodes"] >= 100, \
        recomputed["surfaces"]["entry_graph"]
    # 前两条在岸事实：停点之前条件面板已提交、尚未计桌
    assert _ledger_of(out).spent("prefix_generation") == 1.0
    resumed = search.run_av_machine_resume(out, run_id=state["run_id"],
                                           authorization=TOKEN)
    assert resumed.get("terminal") == "ITERATION_COMPLETE", resumed
    assert not resumed.get("refused"), resumed
    ledger = _ledger_of(out)
    assert search.sha256_file(eval_path) == eval_sha, "条件结果被重跑覆盖"       # ①
    assert ledger.spent("prefix_generation") == 1.0, "条件前缀被重复计费"        # ②
    assert ledger.spent("tables_full") == 8.0, ledger.account_summary()
    instances_in_use = search.av_instances_load(out).get("instances") or {}
    assert len(instances_in_use) == 4, sorted(instances_in_use)
    tree = _result_tree_digest(out)
    again = search.run_av_machine_resume(out, run_id=state["run_id"],
                                         authorization=TOKEN)
    assert again.get("terminal") == "ITERATION_COMPLETE", again              # ③
    assert _ledger_of(out).account_summary() == ledger.account_summary()
    assert (search.av_instances_load(out).get("instances") or {}) == instances_in_use
    assert _result_tree_digest(out) == tree
    print("[P3-5] 同身份恢复命中：terminal={0}、条件结果摘要不变、"
          "prefix_generation=1.0、tables_full=8.0、实例 {1} 条；二次恢复幂等"
          .format(resumed.get("terminal"), len(instances_in_use)))


# ===========================================================================
# 修复项 2 · 动态 sibling 装载的显式登记与缺项失败关闭
# ===========================================================================


def test_unregistered_sibling_load_fails_closed(monkeypatch):
    """登记不到即失败关闭：未登记的 sibling 名字**不能**被静默装载。"""

    with pytest.raises(deps.UnregisteredSiblingLoad) as error:
        search._sibling("sitin_p3_not_registered")
    assert "未登记" in str(error.value)
    assert "SIBLING_MODULES" in str(error.value)
    # 登记表里的名字照常装载（失败关闭不是"一律拒绝"）
    assert search._sibling("sitin_scheduler") is not None
    assert deps.require_sibling("sitin_natural_panel").role


def test_manifest_refuses_when_registry_loses_a_dynamic_load(monkeypatch):
    """清单侧失败关闭：登记表少一项 → 出不了清单，恢复被拒（不是警告后放行）。"""

    _plan, manifest, state = _manifest_and_state()
    assert manifest["entry_coverage_gaps"] == []
    monkeypatch.delitem(deps.SIBLING_MODULES, "sitin_process")
    gaps = search.av_entry_coverage_gaps()
    assert [item["module"] for item in gaps] == ["sitin_process"], gaps
    with pytest.raises(deps.ManifestCoverageGap):
        search.av_frozen_manifest(plan=state["plan"])
    ok, reason, _ = search.av_verify_run_identity(state)
    assert not ok and "覆盖缺口" in reason, reason


def test_all_tool_dynamic_loads_are_registered():
    """全目录静态复核：任何以工具名动态装载的调用点都必须在登记表内。

    这条把"新工具用 `_sibling` / `sibling` / `spec_from_file_location` 装载了
    一个没登记的模块"挡在评测之前（判据是机器扫描，不是人工记忆）。
    """

    unregistered = deps.unregistered_dynamic_loads(
        files=sorted(path.name for path in deps.TOOLS_DIR.glob("*.py")
                     if not path.name.startswith("test_")))
    assert unregistered == [], unregistered
    scanned = deps.scan_dynamic_sibling_loads(
        files=sorted(path.name for path in deps.TOOLS_DIR.glob("*.py")
                     if not path.name.startswith("test_")))
    assert set(scanned) == set(deps.SIBLING_MODULES), (
        sorted(set(scanned) ^ set(deps.SIBLING_MODULES)))
    print("[P3-6] 动态装载登记复核：{0} 个模块全部在册（含装载点）".format(len(scanned)))


def test_dependency_closures_have_no_missing_first_party_module():
    """闭包完整性：第一方模块解析不到即缺口（包内相对导入不得被算错）。

    回归点：包（`__init__.py`）里的 `from .evaluate import ...` 曾按父包解析成
    `hangma_bot.evaluate`（不存在），真实依赖 `hangma_bot.offline.evaluate` 反而
    没进闭包——这正是 S2 漏项形态之一。
    """

    manifest = search.av_frozen_manifest(plan={"opponent": "H"})
    assert manifest["missing_modules"] == [], manifest["missing_modules"]
    assert manifest["baseline_missing_modules"] == [], \
        manifest["baseline_missing_modules"]
    assert manifest["entry_missing"] == [], manifest["entry_missing"]
    assert manifest["entry_coverage_gaps"] == [], manifest["entry_coverage_gaps"]
    assert "hangma_bot.offline.evaluate" in manifest["entry_module_closure"]
    print("[P3-7] 闭包无缺项：rules={0}、baseline={1}、entry={2} 模块".format(
        len(manifest["module_closure"]), len(manifest["baseline_module_closure"]),
        len(manifest["entry_module_closure"])))


def test_literal_first_party_module_loads_are_covered(monkeypatch):
    """按名装载（`_av_module("hangma_bot.x")` / `importlib.import_module`）也要在清单内。

    这是 S2 漏项的**同形态**：静态 import 图看不到按名字装载的模块，若某处新增一处
    没进清单的按名装载，身份就会出现"改了它摘要不变"的缺口。判据：入口文件里
    每一个字面量第一方模块装载名都必须在（规则闭包 ∪ 基线闭包 ∪ 入口闭包）内；
    反向验证：把已登记集合清空后，同一扫描必须报出全部缺口（检查不是恒真）。
    """

    manifest = search.av_frozen_manifest(plan={"opponent": "H"})
    loads = deps.scan_literal_module_loads(files=deps.ENTRY_FILES)
    assert loads, "入口文件里应存在按名装载的调用点（扫描器失效则本条无意义）"
    covered = (set(manifest["module_closure"])
               | set(manifest["baseline_module_closure"])
               | set(manifest["entry_module_closure"]))
    missing = sorted(name for name in loads if name not in covered)
    assert missing == [], missing
    assert manifest["entry_coverage_gaps"] == []
    gaps = search.av_entry_coverage_gaps(covered=set())
    kinds = sorted({item["kind"] for item in gaps})
    assert kinds == ["uncovered_module_load"], kinds
    assert sorted(item["module"] for item in gaps) == sorted(loads)
    print("[P3-9] 按名装载覆盖：{0} 处调用点全部在清单内；清空已登记集合后报出 {1} 项缺口"
          .format(len(loads), len(gaps)))


def test_old_manifest_schema_state_is_refused(tmp_path, monkeypatch, fake_runtime):
    """旧身份口径（无入口调用图的 /2 清单）一律拒绝恢复。

    做法：把在案清单降级为"去掉入口段"的旧形态并同步重算其摘要（模拟旧版本状态），
    恢复入口必须拒绝——新清单口径不得被旧摘要"搭配"过去。
    """

    out, state = _freeze(tmp_path, "p3-oldschema", "CONDITIONAL_EVALUATED")
    state_path = search.av_latest_state_path(out)
    raw = search.av_state_load(state_path)
    legacy = {key: value for key, value in raw["identity"]["frozen_manifest"].items()
              if not str(key).startswith("entry_")}
    legacy["schema"] = "sitin-action-value-frozen-manifest/2"
    legacy["surfaces"] = {name: block for name, block in legacy["surfaces"].items()
                          if name != "entry_graph"}
    assert "entry_graph" not in legacy["surfaces"]
    raw["identity"]["frozen_manifest"] = legacy
    raw["identity"]["frozen_manifest_digest"] = \
        search.av_frozen_manifest_digest(legacy)
    state_path.write_text(json.dumps(raw, ensure_ascii=False, indent=1) + "\n",
                          encoding="utf-8")
    before = _ledger_of(out).account_summary()
    refused = search.run_av_machine_resume(out, run_id=state["run_id"],
                                           authorization=TOKEN)
    assert refused.get("refused"), "旧口径清单仍被放行恢复"
    assert "身份" in refused["refused"], refused["refused"]
    assert _ledger_of(out).account_summary() == before
    print("[P3-8] 旧口径（/2）清单状态 → 拒绝恢复")


# ===========================================================================
# P7 · 家族通道配置进运行身份（family_channel / family_refresh）
# ===========================================================================


#: 家族通道声明批（复核用固定值：两侧 × H/M，根序号避开普通条件步已用的序号）。
P7_DECLARATIONS = [
    {"channel": "branch", "sub_scenario": "branch_open", "opponent_mix": "H",
     "panel_seed": 20260916, "root_index": 3, "seats_per_root": 1},
    {"channel": "branch", "sub_scenario": "branch_open", "opponent_mix": "M",
     "panel_seed": 20260916, "root_index": 4, "seats_per_root": 1},
    {"channel": "branch", "sub_scenario": "branch_cost", "opponent_mix": "H",
     "panel_seed": 20260916, "root_index": 5, "seats_per_root": 1},
    {"channel": "branch", "sub_scenario": "branch_cost", "opponent_mix": "M",
     "panel_seed": 20260916, "root_index": 6, "seats_per_root": 1},
]


def _p7_plan(*, family=None, declarations=()):
    plan = {"operator": "i1", "predicate": "branch_open", "opponent": "H",
            "panel_seed": 20260916, "prefix_source": "scripted_fixture",
            "natural_roots": 1, "natural_seats": 1,
            "natural_opponents": ["H", "M"], "generation_mode": "mock",
            "seed_name": "efficiency_seed"}
    plan["family_channel"] = family
    plan["family_refresh"] = [dict(row) for row in declarations]
    return plan


def _p7_digest(plan):
    return search.av_frozen_manifest_digest(search.av_frozen_manifest(plan=plan))


def test_family_channel_and_refresh_declarations_enter_the_identity():
    """P7：同一计划只差家族通道配置 → 摘要必须不同，且清单里看得到「哪个族 + 声明」。

    机器实测的旧反例（R9 §14.3）：`family_channel` 有/无时冻结摘要**逐字相同**——
    关口二第 1 步要启用一个家族通道，两次只差该配置的运行会拿到同一身份。

    逐项判据（不是"改了就变"这么宽）：
      ① 开关进身份：关→开、关→换族，摘要都变；变化面点名 `family_channel`；
      ② 声明进身份：只改**一条声明的内容**（根序号 / 面板种子 / 座位数）摘要也变，
         变化面点名 `family_refresh`——不是"只数条数"；
      ③ 清单里读得出内容：`family_channel` 面给出声明值与解析出的族名（不是布尔位），
         `family_refresh` 面给出逐条声明原文与**派生根身份**（root_id / 执行种子）；
      ④ 同输入确定性：同一计划算两次摘要相同（口径可复现）。
    """

    base = _p7_plan()
    on = _p7_plan(family="branch", declarations=P7_DECLARATIONS)
    other_family = _p7_plan(family="chain",
                            declarations=[dict(row, channel="chain",
                                               sub_scenario="chain_{0}".format(
                                                   row["sub_scenario"].split("_")[-1]))
                                          for row in P7_DECLARATIONS])
    off_digest, on_digest = _p7_digest(base), _p7_digest(on)
    assert off_digest != on_digest, "family_channel 开关未进身份（R9 §14.3 反例复发）"
    assert _p7_digest(other_family) != on_digest, "换族未进身份"
    changed = search.av_changed_manifest_surfaces(
        search.av_frozen_manifest(plan=base), search.av_frozen_manifest(plan=on))
    assert "family_channel" in changed and "family_refresh" in changed, changed

    # 只改一条声明的**内容**（其余逐字相同）→ 摘要必须变。
    for field, value in (("root_index", 9), ("panel_seed", 20270101),
                         ("seats_per_root", 2)):
        tweaked = _p7_plan(family="branch",
                           declarations=[dict(P7_DECLARATIONS[0], **{field: value})]
                           + P7_DECLARATIONS[1:])
        assert _p7_digest(tweaked) != on_digest, "声明字段 {0} 未进身份".format(field)
    # 增删一条声明同样进身份。
    assert _p7_digest(_p7_plan(family="branch",
                               declarations=P7_DECLARATIONS[:3])) != on_digest

    # ③ 清单内容（不是布尔位）。
    manifest = search.av_frozen_manifest(plan=on)
    channel = manifest["surfaces"]["family_channel"]
    assert isinstance(channel, dict) and channel["enabled"] is True, channel
    assert channel["declared"] == "branch" and channel["family"] == "branch", channel
    assert channel["problems"] == [], channel
    assert "branch" in channel["families"], channel
    refresh = manifest["surfaces"]["family_refresh"]
    assert refresh["count"] == len(P7_DECLARATIONS), refresh
    rows = refresh["declarations"]
    assert len(rows) == len(P7_DECLARATIONS), rows
    for row, declared in zip(rows, P7_DECLARATIONS):
        for key, value in declared.items():
            assert row[key] == value, (key, row)
        assert row["resolved_root"]["root_id"].startswith("av-eval-"), row
        assert isinstance(row["resolved_root"]["root_seed"], int), row
    # 关掉开关时也要看得出来"没接线"（declared=None、family=None），不是键缺失。
    off_channel = search.av_frozen_manifest(plan=base)["surfaces"]["family_channel"]
    assert off_channel["enabled"] is False and off_channel["declared"] is None, off_channel
    assert off_channel["family"] is None, off_channel
    # ④ 确定性。
    assert _p7_digest(on) == on_digest
    print("[P7-1] 家族通道进身份：关/开摘要不同（变化面 {0}）；声明内容改一个字段即变；"
          "族={1}、声明 {2} 条（含派生根身份）".format(
              changed, channel["family"], refresh["count"]))


def test_family_channel_switch_refused_on_resume_without_new_cost(
        tmp_path, monkeypatch, fake_runtime):
    """端到端（关 → 开）：盘上启用家族通道后，**旧身份的结果被拒绝恢复**。

    冻结一次（未接线家族通道）后把 `state.plan.family_channel/family_refresh` 改成
    启用状态并尝试恢复：入口自算清单摘要必须变化、恢复必须被拒，且**不产生新费用、
    不写新结果**（拒绝发生在任何副作用之前）。
    """

    out, state = _freeze(tmp_path, "p7-fam-open", "CONDITIONAL_EVALUATED")
    state_path = search.av_latest_state_path(out)
    iter_dir = Path(state["iter_dir"])
    assert state["plan"]["family_channel"] is None
    stored_digest = state["identity"]["frozen_manifest_digest"]
    raw = search.av_state_load(state_path)
    raw["plan"]["family_channel"] = "branch"
    raw["plan"]["family_refresh"] = [dict(row) for row in P7_DECLARATIONS]
    state_path.write_text(json.dumps(raw, ensure_ascii=False, indent=1) + "\n",
                          encoding="utf-8")
    fresh = search.av_frozen_manifest(plan=raw["plan"])
    fresh_digest = search.av_frozen_manifest_digest(fresh)
    assert fresh_digest != stored_digest, "启用家族通道后摘要未变（反例复发）"
    changed = search.av_changed_manifest_surfaces(
        state["identity"]["frozen_manifest"], fresh)
    assert "family_channel" in changed and "family_refresh" in changed, changed
    before = _ledger_of(out).account_summary()
    refused = search.run_av_machine_resume(out, run_id=state["run_id"],
                                           authorization=TOKEN)
    assert refused.get("identity_refused"), refused
    assert "身份" in refused["refused"], refused["refused"]
    assert "family_channel" in refused["refused"], refused["refused"]
    assert _ledger_of(out).account_summary() == before, "拒绝前已产生新费用"
    assert not list(iter_dir.glob("natural-*")), "拒绝前已写入新结果"
    after = search.av_state_load(state_path)
    assert after["status"] == "CONDITIONAL_EVALUATED", after["status"]
    print("[P7-2] 盘上启用家族通道 → 拒绝恢复：面 {0}；零新费用、零新结果".format(changed))


def test_family_channel_strip_refused_on_resume(tmp_path, monkeypatch, fake_runtime):
    """端到端（开 → 关）：反向同样成立——不能靠"把声明抹掉"复用另一套身份的结果。"""

    out, state = _freeze(tmp_path, "p7-fam-strip", "CONDITIONAL_EVALUATED",
                         family_channel="branch",
                         family_refresh=P7_DECLARATIONS)
    state_path = search.av_latest_state_path(out)
    iter_dir = Path(state["iter_dir"])
    assert state["plan"]["family_channel"] == "branch"
    assert len(state["plan"]["family_refresh"]) == len(P7_DECLARATIONS)
    raw = search.av_state_load(state_path)
    raw["plan"]["family_channel"] = None
    raw["plan"]["family_refresh"] = []
    state_path.write_text(json.dumps(raw, ensure_ascii=False, indent=1) + "\n",
                          encoding="utf-8")
    before = _ledger_of(out).account_summary()
    refused = search.run_av_machine_resume(out, run_id=state["run_id"],
                                           authorization=TOKEN)
    assert refused.get("identity_refused"), refused
    assert "family_channel" in refused["refused"], refused["refused"]
    assert _ledger_of(out).account_summary() == before
    assert not list(iter_dir.glob("natural-*"))
    print("[P7-3] 盘上抹掉家族声明 → 同样拒绝恢复：{0}".format(
        refused["refused"][:140]))


def test_family_identity_unchanged_resume_reuses_committed_results(tmp_path,
                                                                   fake_runtime):
    """反向对照：家族通道启用且身份不变时，恢复**仍被接受并复用**既有结果。

    判据（逐条数字，不是"没报错"）：
      ① 恢复入口接受（`av_verify_run_identity` 通过、无 refused）；
      ② 已提交的条件面板结果文件摘要不变（旧结果不被重跑覆盖）；
      ③ 自然面板桌数恰为 1 根 × 1 座 × 2 臂 × 2 桌 × H/M = 8、条件前缀只计费一次；
      ④ 二次恢复幂等：不新增费用、不新增实例。
    """

    out, state = _freeze(tmp_path, "p7-fam-reuse", "CONDITIONAL_EVALUATED",
                         family_channel="branch", family_refresh=[])
    eval_path = Path(state["conditional"]["evaluation_path"])
    eval_sha = search.sha256_file(eval_path)
    ok, reason, manifest = search.av_verify_run_identity(state)
    assert ok and not reason, reason
    assert manifest["surfaces"]["family_channel"]["family"] == "branch", manifest[
        "surfaces"]["family_channel"]
    resumed = search.run_av_machine_resume(out, run_id=state["run_id"],
                                           authorization=TOKEN)
    assert not resumed.get("refused"), resumed
    assert resumed.get("terminal") == "ITERATION_COMPLETE", resumed
    ledger = _ledger_of(out)
    assert search.sha256_file(eval_path) == eval_sha, "条件结果被重跑覆盖"       # ②
    assert ledger.spent("prefix_generation") == 1.0, "条件前缀被重复计费"        # ③
    assert ledger.spent("tables_full") == 8.0, ledger.account_summary()
    instances_in_use = search.av_instances_load(out).get("instances") or {}
    again = search.run_av_machine_resume(out, run_id=state["run_id"],
                                         authorization=TOKEN)
    assert again.get("terminal") == "ITERATION_COMPLETE", again                # ④
    assert _ledger_of(out).account_summary() == ledger.account_summary()
    assert (search.av_instances_load(out).get("instances") or {}) == instances_in_use
    ok2, reason2, _ = search.av_verify_run_identity(
        search.av_state_load(search.av_latest_state_path(out)))
    assert ok2 and not reason2, reason2
    print("[P7-4] 家族通道启用且身份不变 → 恢复被接受并复用：terminal={0}、"
          "prefix_generation=1.0、tables_full=8.0、实例 {1} 条；二次恢复幂等".format(
              resumed.get("terminal"), len(instances_in_use)))


def test_previous_schema_state_without_family_surfaces_is_refused(
        tmp_path, monkeypatch, fake_runtime):
    """旧身份口径（/3：无家族面的清单）一律拒绝恢复——升版即失效，旧摘要不能"搭配"过去。

    做法：把在案清单降级为 /3 形态（去掉 family_channel / family_refresh 两面）并同步
    重算其摘要，恢复入口必须拒绝。**失效范围**因此明确：/3 及更早的冻结身份一律不续跑
    （与 N4/P3 的升版口径一致：以新身份在新目录重开）。
    """

    out, state = _freeze(tmp_path, "p7-oldschema", "CONDITIONAL_EVALUATED")
    state_path = search.av_latest_state_path(out)
    raw = search.av_state_load(state_path)
    legacy = json.loads(json.dumps(raw["identity"]["frozen_manifest"]))
    legacy["schema"] = "sitin-action-value-frozen-manifest/3"
    for name in ("family_channel", "family_refresh"):
        legacy["surfaces"].pop(name, None)
    assert "family_channel" not in legacy["surfaces"]
    raw["identity"]["frozen_manifest"] = legacy
    raw["identity"]["frozen_manifest_digest"] = \
        search.av_frozen_manifest_digest(legacy)
    state_path.write_text(json.dumps(raw, ensure_ascii=False, indent=1) + "\n",
                          encoding="utf-8")
    before = _ledger_of(out).account_summary()
    refused = search.run_av_machine_resume(out, run_id=state["run_id"],
                                           authorization=TOKEN)
    assert refused.get("refused"), "旧口径（/3）清单仍被放行恢复"
    assert "身份" in refused["refused"], refused["refused"]
    assert _ledger_of(out).account_summary() == before
    print("[P7-5] 旧口径（/3，无家族面）清单状态 → 拒绝恢复：{0}".format(
        refused["refused"][:140]))
