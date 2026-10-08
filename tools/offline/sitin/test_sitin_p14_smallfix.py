# -*- coding: utf-8 -*-
"""P14 SMALLFIX 定向测试：收掉三处口径不一致 / 健壮性缺陷（R9 裁定 Q6 + 评审 G2/S2 收口）。

全部**离线纯数据**：0 真实桌赛、0 模型调用、0 网络、不写任何 evidence 既有产物
（临时件一律落 pytest 的 tmp_path）。

三处缺陷与判据（每条都有"修复前必红"的形态）：

  1. `sitin_deps._parse_cached` 解析失败记 None（并发写入/半截文件），而三处消费点
     没有判空：一处 `TypeError: 'NoneType' object is not iterable`，两处**静默跳过**
     （`continue` / 返回空）。静默跳过正是 S2 的身份洞——解析不到 import 事实的文件，
     其真实依赖不会进清单闭包，而清单**看起来完整**。本包要求**具名失败**：指出哪个
     文件、语法错误原文、并说明这是"清单身份无法计算"而非运行结果问题。
  2. `sitin_archive.apply_challenge` 的 missing 仍按"当时的行集合"（epoch 根 + 刷新批）
     推导 ⇒ 冻结核心根清单里那条不在该行集合内的键（实测 `branch_open|H|root000`）
     永远报不出来（逐键 8 vs 自报 7）。本包要求缺失集合与**权威逐键口径同源**，
     并把旧口径原样留作对照字段 + 逐键 vs 自报对照表。
  3. `sitin_natural_panel.require_authorization` 仍是旧式门（`authorized is True and
     batch == 7`）：不校验批次标签/允许操作集/账户额度/受信签发方，且与状态机
     （`sitin_search.av_authorization_allows(operation="natural_panel")`）**两套判据**。
     本包要求统一走同一受信入口，legacy 形态照样接受但显式标注 `authorization_form`。
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
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping

import pytest

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import sitin_archive as archive  # noqa: E402
import sitin_deps as deps  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402
import sitin_search as search  # noqa: E402


# ===========================================================================
# 任务 1 · sitin_deps：清单解析失败 = 具名 fail-closed（不崩、不静默跳过）
# ===========================================================================

#: 并发写入期间的半截文件（语法不完整）——真实故障形态，不是编造。
BROKEN_SOURCE = "def half_written(\n    return 1\n"
#: 完整对照文件：含函数内导入、相对导入、动态 sibling 装载与按名装载。
COMPLETE_SOURCE = (
    "import os\n"
    "import sitin_process\n"          # 同目录工具模块：入口图的一条真实边
    "from json import dumps\n"
    "\n"
    "\n"
    "def boot():\n"
    "    from . import helper\n"
    "    return _sibling(\"sitin_process\")\n"
    "\n"
    "\n"
    "_av_module(\"hangma_bot.policy.action_policy\")\n"
)


def _tool_dir(tmp_path: Path) -> Path:
    """构造一个最小 tools 目录：半截文件 + 完整文件 + 被装载的工具名文件。"""

    (tmp_path / "sitin_half_written.py").write_text(BROKEN_SOURCE, encoding="utf-8")
    (tmp_path / "sitin_complete.py").write_text(COMPLETE_SOURCE, encoding="utf-8")
    (tmp_path / "sitin_process.py").write_text("import os\n", encoding="utf-8")
    return tmp_path


def test_half_written_tool_file_is_refused_by_name(tmp_path):
    """半截文件必须**具名拒绝**：给出文件路径 + 语法错误原文 + 身份口径说明。"""

    root = _tool_dir(tmp_path)
    with pytest.raises(deps.ManifestParseError) as caught:
        deps.scan_dynamic_sibling_loads(tools_dir=root, files=["sitin_half_written.py"])
    message = str(caught.value)
    assert "sitin_half_written.py" in message, message
    assert "SyntaxError" in message or "语法" in message, message
    assert "清单身份" in message, message
    assert "运行结果" in message, message


def test_every_parse_consumer_refuses_instead_of_skipping(tmp_path):
    """三处消费点全部 fail-closed：不崩成 TypeError，也不静默返回空。

    修复前的形态：`scan_dynamic_sibling_loads` 抛 `TypeError: 'NoneType' object is
    not iterable`；`scan_literal_module_loads` 与 `module_imports` **静默跳过**
    （前者 `continue`、后者返回空列表）——后者最危险：清单会"看起来完整"
    地漏掉整棵依赖子树（S2 身份洞）。
    """

    root = _tool_dir(tmp_path)
    broken = root / "sitin_half_written.py"

    with pytest.raises(deps.ManifestParseError):
        deps.scan_dynamic_sibling_loads(tools_dir=root, files=["sitin_half_written.py"])
    with pytest.raises(deps.ManifestParseError):
        deps.scan_literal_module_loads(tools_dir=root, files=["sitin_half_written.py"])
    with pytest.raises(deps.ManifestParseError):
        deps.module_imports(broken, "sitin_half_written")
    with pytest.raises(deps.ManifestParseError):
        deps.module_imports_of(BROKEN_SOURCE.encode("utf-8"), "sitin_half_written", broken)
    with pytest.raises(deps.ManifestParseError):
        deps.entry_call_graph(reader=lambda path: Path(path).read_bytes(),
                              tools_dir=root, src_root=root,
                              entries=("sitin_half_written.py",))
    # ManifestCoverageGap 的子类：清单侧调用方（av_frozen_manifest）照样按缺口拒绝。
    assert issubclass(deps.ManifestParseError, deps.ManifestCoverageGap)


def test_complete_file_parses_and_yields_its_imports(tmp_path):
    """对照：完整文件正常通过，且三处消费点都给出**非空**事实（检查不是恒真）。"""

    root = _tool_dir(tmp_path)
    complete = root / "sitin_complete.py"

    loads = deps.scan_dynamic_sibling_loads(tools_dir=root, files=["sitin_complete.py"])
    assert loads == {"sitin_process": ("sitin_complete.py:_sibling",)}, loads

    named = deps.scan_literal_module_loads(tools_dir=root, files=["sitin_complete.py"])
    assert named == {"hangma_bot.policy.action_policy": ("sitin_complete.py:_av_module",)}, named

    refs = deps.module_imports(complete, "sitin_complete")
    required = {ref.name for ref in refs if ref.required}
    assert {"os", "json", "sitin_complete.helper"} <= required, sorted(required)
    assert deps.module_imports_of(COMPLETE_SOURCE.encode("utf-8"), "sitin_complete",
                                  complete) == refs


def test_missing_or_unreadable_tool_file_is_refused_by_name(tmp_path):
    """读不到字节的文件同样**具名失败关闭**（P14-FU1 收残留：旧实现两处静默 continue）。

    与"解析失败"同族：内容摘要与 import 事实都拿不到 ⇒ 清单身份无法计算。
    对照：完整文件仍正常通过（检查不是恒真）。
    """

    root = _tool_dir(tmp_path)
    # ① 点名了但文件不存在（旧实现 `if not path.is_file(): continue` 静默跳过）
    with pytest.raises(deps.ManifestReadError) as caught:
        deps.scan_dynamic_sibling_loads(tools_dir=root, files=["sitin_missing.py"])
    message = str(caught.value)
    assert "sitin_missing.py" in message, message
    assert "清单身份" in message and "运行结果" in message, message
    # ② 同名目录（不是普通文件）：`read_bytes` 抛 IsADirectoryError ⇒ 走 OSError 分支
    (root / "sitin_dir.py").mkdir()
    with pytest.raises(deps.ManifestReadError):
        deps.module_imports(root / "sitin_dir.py", "sitin_dir")
    with pytest.raises(deps.ManifestReadError):
        deps.scan_literal_module_loads(tools_dir=root, files=["sitin_dir.py"])
    # ③ 权限不足（本机用户身份可复现时；root 下该分支惰性，不假装覆盖）
    blocked = root / "sitin_blocked.py"
    blocked.write_text("import os\n", encoding="utf-8")
    os.chmod(blocked, 0o000)
    try:
        try:
            blocked.read_bytes()
        except OSError:
            with pytest.raises(deps.ManifestReadError):
                deps.module_imports(blocked, "sitin_blocked")
            permission_branch = True
        else:
            permission_branch = False          # 本进程仍可读：该分支本机不可复现
    finally:
        os.chmod(blocked, 0o644)
    # 对照：完整文件照常给出事实
    assert deps.scan_dynamic_sibling_loads(tools_dir=root, files=["sitin_complete.py"])
    assert issubclass(deps.ManifestReadError, deps.ManifestCoverageGap)
    print("[P14-FU1] 读失败具名拒绝：缺文件/同名目录各一条；权限分支={0}".format(
        "已覆盖" if permission_branch else "本机不可复现"))


def test_entry_call_graph_still_computes_for_complete_entries(tmp_path):
    """对照（入口图面）：完整入口文件照常得到节点/边，不因新判空而整体停摆。"""

    root = _tool_dir(tmp_path)
    graph = deps.entry_call_graph(reader=lambda path: Path(path).read_bytes(),
                                  tools_dir=root, src_root=root,
                                  entries=("sitin_complete.py",))
    assert graph["entries"] == ["tool:sitin_complete"]
    assert "tool:sitin_process" in graph["nodes"]
    assert graph["edges"]["tool:sitin_complete"] == ["tool:sitin_process"]


# ===========================================================================
# 任务 2 · apply_challenge：missing 与权威逐键口径同源（冻结清单，不按行集合）
# ===========================================================================

PANEL_SEED = 20260916
CHANNEL = "branch"
CELLS = (("branch_open", "H"), ("branch_open", "M"),
         ("branch_cost", "H"), ("branch_cost", "M"))
#: 冻结核心根清单（需求集合）：4 格 × 2 根 = **8 行**。生产根身份形如
#: av-eval-{子场景}:{子场景}:rootNNN，情景靠 mix 区分（同一 root_id 在四格里同名）。
FROZEN_ROWS: List[Dict[str, Any]] = [
    {"root_id": "av-eval-{0}:{0}:root{1:03d}".format(sub, index),
     "sub_scenario": sub, "opponent_mix": mix, "root_index": index,
     "panel_seed": PANEL_SEED,
     "root_seed": 1000 + 100 * CELLS.index((sub, mix)) + index,
     "generator": "v2-behavior"}
    for (sub, mix) in CELLS
    for index in (0, 1)
]
assert len(FROZEN_ROWS) == 8, len(FROZEN_ROWS)   # 4 格 × 2 根：冻结清单本身不许自相矛盾
#: epoch 根行集：**少一行**——冻结清单里的 branch_open|H|root000（实测 frozen_only 那条）。
EPOCH_ROWS: List[Dict[str, Any]] = [
    row for row in FROZEN_ROWS
    if not (row["sub_scenario"] == "branch_open" and row["opponent_mix"] == "H"
            and row["root_index"] == 0)
]
#: 冻结清单里**不在** epoch 行集合内的那个键（逐键口径必须报出来）。
FROZEN_ONLY_TOKEN = "branch_open|H|av-eval-branch_open:branch_open:root000"
#: 刷新批（每子场景 4 根、H/M 各 2）——阶段 2 用，与冻结清单无关。
REFRESH_ROWS: List[Dict[str, Any]] = [
    {"root_id": "av-eval-{0}:{0}:root{1:03d}".format(sub, 10 + index),
     "sub_scenario": sub, "opponent_mix": mix, "root_index": 10 + index,
     "panel_seed": PANEL_SEED, "root_seed": 5000 + 10 * mix_index + index}
    for sub in ("branch_open", "branch_cost")
    for mix_index, mix in enumerate("HM")
    for index in (0, 1)
]


def _record(value: float, mix: str, *, usable: bool = True) -> Dict[str, Any]:
    return {"d_point": float(value) if usable else None,
            "d_low": float(value) if usable else None,
            "d_high": float(value) if usable else None,
            "unknown": not usable, "opponent_mix": mix, "cost": 1.0}


def _family_evals(rows: List[Mapping[str, Any]], value: float,
                  *, skip: Any = ()) -> Dict[str, Dict[str, Any]]:
    """家族评价记录：键用**情景限定格键**（生产真实形态，P7b §5.4）。

    同一 root_id 在 H/M 两格是两个真实实例；按裸根 id 记录会让后者静默顶掉前者
    （fixture 若这么做，"H 缺而 M 有"的形态会被裸键回退判成已覆盖，测不出少算）。
    """

    out: Dict[str, Dict[str, Any]] = {"branch_open": {}, "branch_cost": {}}
    for row in rows:
        if (row["sub_scenario"], row["opponent_mix"], row["root_index"]) in skip:
            continue
        out[str(row["sub_scenario"])][
            archive.family_cell_key(row["opponent_mix"], row["root_id"])] = _record(
                value, str(row["opponent_mix"]))
    return out


def _entry(cid: str, rows: List[Mapping[str, Any]], value: float) -> Dict[str, Any]:
    return {"candidate_id": cid, "kind": "action_value_v1",
            "safety": {"status": "PASS"}, "effect_failure_unresolved": False,
            "overall": {"sort_value": value, "unknown_ratio": 0.0, "total_cost": 4.0},
            "family": {}, "behavior_signature": None, "evidence_count": 4,
            "normal_evaluations": {}, "family_evaluations": _family_evals(rows, value)}


def _fixture(*, frozen_only: bool = True):
    """冻结清单 8 行、epoch 行集 7 行（或与冻结清单一致的 8 行）的家族挑战夹具。

    挑战者对 **epoch 行集**全部有合格记录（旧口径 ⇒ 自报 missing 为空），但缺
    冻结清单里那条 frozen_only 的键——这正是"自报少算 1"的形态。
    """

    epoch_rows = EPOCH_ROWS if frozen_only else FROZEN_ROWS
    epoch = archive.build_channel_epoch(CHANNEL, epoch_rows)
    incumbent = _entry("fbase", epoch_rows, 0.5)
    challenger = _entry("fchall", epoch_rows, 1.5)
    arch = {"schema": archive.ARCHIVE_SCHEMA,
            "slots": {"branch": ["fbase"], "overall": [], "exploration": []},
            "entries": {"fbase": incumbent, "fchall": challenger},
            "exploration_queue": []}
    return arch, epoch, {"fchall": challenger["family_evaluations"],
                         "fbase": incumbent["family_evaluations"]}


def _write_freeze_file(run_root: Path, rows: List[Mapping[str, Any]]) -> Path:
    """按生产约定落冻结核心根清单：<run_root>/archive/family-core-roots.json。"""

    path = Path(run_root) / "archive" / "family-core-roots.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    # 冻结件 schema 用**字面量**写：这样"少算"这条用例在修复前报的是缺键断言，
    # 而不是"常量还不存在"的 AttributeError——红要红在缺陷本身上。
    path.write_text(json.dumps({
        "schema": "sitin-av-family-core-roots/1", "channel": CHANNEL,
        "frozen_at_utc": "2026-09-18T00:00:00Z",
        "roots": [dict(row, key=search._av_family_core_key(row)) for row in rows],
        "note": "P14 定向测试夹具"}, ensure_ascii=False), encoding="utf-8")
    return path


def test_frozen_list_schema_stays_in_sync_with_production():
    """冻结清单 schema 字面量跨模块一致（不靠人工记忆，漂移即红）。"""

    assert archive.FAMILY_CORE_LIST_SCHEMA == search.AV_FAMILY_CORE_LIST_SCHEMA


def test_challenge_missing_no_longer_undercounts_the_frozen_only_key(tmp_path):
    """frozen_only 形态：缺失集合必须来自**冻结清单逐键**，而不是当时的行集合。

    自动定位路径（生产形态）：`persist_dir` 在家族提交目录
    ` <run_root>/archive/family-commit/branch ` 下，冻结件在 ` <run_root>/archive/ `。
    """

    arch, epoch, evals = _fixture()
    freeze_path = _write_freeze_file(tmp_path, FROZEN_ROWS)
    commit_dir = tmp_path / "archive" / "family-commit" / CHANNEL
    commit_dir.mkdir(parents=True, exist_ok=True)

    result = archive.apply_challenge(arch, epoch, "fchall", evals,
                                     refresh_roots=REFRESH_ROWS, persist_dir=commit_dir)

    missing = result["missing"]["fchall"]
    assert FROZEN_ONLY_TOKEN in missing, (missing, result.get("status"))
    # 旧口径原样保留为对照字段（它就是"少算"的那一版：空）。
    assert result["missing_reported_row_set"]["fchall"] == [], result["missing_reported_row_set"]
    comparison = result["missing_comparison"]["fchall"]
    assert comparison["frozen_only"] == [FROZEN_ONLY_TOKEN], comparison
    assert comparison["reported_missing"] == [], comparison
    assert comparison["consistent"] is False, comparison
    assert result["missing_requirement"]["source"] == "frozen_core_list", result["missing_requirement"]
    assert str(freeze_path) == result["missing_requirement"]["path"], result["missing_requirement"]
    # 有效缺失 = 权威逐键 ∪ 自报（一条不丢），工作项口径分明。
    assert set(missing) == set(result["missing_authoritative"]["fchall"]) \
        | set(result["missing_reported_row_set"]["fchall"])


def test_challenge_missing_matches_authoritative_coverage_tokens(tmp_path):
    """与 `sitin_search.av_family_core_coverage` 的逐键缺失**同一集合**（同源验收）。

    同一条冻结清单、同一份档案证据：权威函数的 `missing_tokens` 必须逐条等于
    `apply_challenge.missing_authoritative`——两条通道不再各写一套口径。
    """

    arch, epoch, evals = _fixture()
    _write_freeze_file(tmp_path, FROZEN_ROWS)
    commit_dir = tmp_path / "archive" / "family-commit" / CHANNEL
    commit_dir.mkdir(parents=True, exist_ok=True)
    result = archive.apply_challenge(arch, epoch, "fchall", evals,
                                     refresh_roots=REFRESH_ROWS, persist_dir=commit_dir)
    coverage = search.av_family_core_coverage(
        core_rows=FROZEN_ROWS, entry=arch["entries"]["fchall"],
        candidate_id="fchall", products=[])
    assert coverage["n_roots"] == 8, coverage["n_roots"]
    assert coverage["missing_tokens"] == [FROZEN_ONLY_TOKEN], coverage["missing_tokens"]
    assert sorted(result["missing_authoritative"]["fchall"]) == coverage["missing_tokens"]


def test_challenge_accepts_injected_core_rows_without_disk(tmp_path):
    """显式注入冻结行（不经磁盘）同样生效：需求集合只有一个入口。"""

    arch, epoch, evals = _fixture()
    result = archive.apply_challenge(arch, epoch, "fchall", evals,
                                     refresh_roots=REFRESH_ROWS,
                                     core_rows=FROZEN_ROWS)
    assert result["missing"]["fchall"] == [FROZEN_ONLY_TOKEN], result["missing"]
    assert result["missing_requirement"]["source"] == "injected_core_rows"
    assert result["missing_comparison"]["fchall"]["frozen_only"] == [FROZEN_ONLY_TOKEN]


def test_challenge_reports_consistent_when_row_set_equals_frozen_list(tmp_path):
    """对照：epoch 行集与冻结清单一致时，逐键 vs 自报**一致**（不无中生有）。"""

    arch, epoch, evals = _fixture(frozen_only=False)
    result = archive.apply_challenge(arch, epoch, "fchall", evals,
                                     refresh_roots=REFRESH_ROWS,
                                     core_rows=FROZEN_ROWS)
    comparison = result["missing_comparison"]["fchall"]
    assert comparison["consistent"] is True, comparison
    assert comparison["frozen_only"] == [] and comparison["reported_only"] == [], comparison
    assert set(result["missing"]["fchall"]) == set(result["missing_authoritative"]["fchall"])


def test_challenge_without_frozen_list_marks_the_requirement_source(tmp_path):
    """无冻结清单时**具名标注**降级来源（epoch 行集合），不冒充逐键权威结论。

    降级口径按"当时的行集合"推 ⇒ 冻结清单里那条它天然报不出来——所以这里不但断言
    来源标注，也断言"该口径确实少算"（正是要被标注、不能被当成权威的那个形态）。
    """

    arch, epoch, evals = _fixture()
    result = archive.apply_challenge(arch, epoch, "fchall", evals,
                                     refresh_roots=REFRESH_ROWS)
    assert result["missing_requirement"]["source"] == "epoch_row_set"
    assert "降级" in result["missing_requirement"]["note"], result["missing_requirement"]
    assert result["missing_requirement"]["path"] is None
    assert result["phase"] == "phase2"
    assert FROZEN_ONLY_TOKEN not in result["missing"]["fchall"], result["missing"]
    # 降级后仍有需求（本批刷新根）：缺失不是空，只是**少**了冻结清单那一条。
    assert result["missing"]["fchall"], result["missing"]
    assert all(token.rsplit(":", 1)[-1] in ("root010", "root011")
               for token in result["missing"]["fchall"]), result["missing"]


def test_challenge_missing_includes_unusable_and_refresh_roots(tmp_path):
    """不变量：不合格记录（unknown/缺配对差）与刷新根都必须报为缺失（不漏项）。"""

    arch, epoch, _evals = _fixture()
    challenger = _entry("fchall", EPOCH_ROWS, 1.5)
    challenger["family_evaluations"]["branch_cost"][
        archive.family_cell_key("H", "av-eval-branch_cost:branch_cost:root000")] = \
        _record(0.0, "H", usable=False)
    evals = {"fchall": challenger["family_evaluations"],
             "fbase": arch["entries"]["fbase"]["family_evaluations"]}
    result = archive.apply_challenge(arch, epoch, "fchall", evals,
                                     refresh_roots=REFRESH_ROWS, core_rows=FROZEN_ROWS)
    missing = result["missing_authoritative"]["fchall"]
    assert "branch_cost|H|av-eval-branch_cost:branch_cost:root000" in missing, missing
    assert FROZEN_ONLY_TOKEN in missing, missing


def test_family_challenge_refuses_downgrade_when_run_dir_lacks_frozen_list(tmp_path):
    """家族通道 + 给了运行目录却没有冻结件 ⇒ **具名拒绝**（P14-FU1 收残留）。

    为什么拒绝而不是降级：降级口径就是"当时的行集合"，正是 P9c 少算 1 的口径
    （评审 G2：不得以数量补齐）。生产在家族 epoch 建立时就会冻结清单，因此
    "给了 persist_dir 却没冻结件"是真实异常；纯函数调用（不给 persist_dir）仍可降级，
    但要具名标注来源。
    """

    arch, epoch, evals = _fixture()
    commit_dir = tmp_path / "archive" / "family-commit" / CHANNEL
    commit_dir.mkdir(parents=True, exist_ok=True)
    with pytest.raises(ValueError) as caught:
        archive.apply_challenge(arch, epoch, "fchall", evals,
                                refresh_roots=REFRESH_ROWS, persist_dir=commit_dir)
    message = str(caught.value)
    assert "冻结核心根清单" in message, message
    assert "family-core-roots.json" in message, message
    assert "branch_open|H|root000" in message, message      # 少算形态被点名
    assert "core_rows" in message and "core_missing" in message, message

    # 对照 1：同一运行目录若有冻结件 ⇒ 正常返回逐键缺失（不拒绝）
    arch, epoch, evals = _fixture()
    _write_freeze_file(tmp_path, FROZEN_ROWS)
    ok = archive.apply_challenge(arch, epoch, "fchall", evals,
                                 refresh_roots=REFRESH_ROWS, persist_dir=commit_dir)
    assert FROZEN_ONLY_TOKEN in ok["missing"]["fchall"], ok["missing"]
    # 对照 2：不给 persist_dir（纯函数调用）⇒ 降级但**具名标注**，不拒绝
    arch, epoch, evals = _fixture()
    downgraded = archive.apply_challenge(arch, epoch, "fchall", evals,
                                         refresh_roots=REFRESH_ROWS)
    assert downgraded["missing_requirement"]["source"] == "epoch_row_set"
    assert "降级" in downgraded["missing_requirement"]["note"]


def test_normal_channel_requirement_source_is_unchanged(tmp_path):
    """正常通道不受影响：需求集合仍是 epoch 行集合（冻结清单只服务家族通道）。"""

    core = [{"root_id": "n1", "opponent_mix": "H"},
            {"root_id": "n2", "opponent_mix": "H"},
            {"root_id": "n3", "opponent_mix": "M"},
            {"root_id": "n4", "opponent_mix": "M"}]
    refresh = [{"root_id": "f1", "opponent_mix": "H"},
               {"root_id": "f2", "opponent_mix": "H"},
               {"root_id": "f3", "opponent_mix": "M"},
               {"root_id": "f4", "opponent_mix": "M"}]
    epoch = archive.build_channel_epoch("normal", core)
    entry = _entry("ch", [], 0.0)
    entry["normal_evaluations"] = {"n1": _record(0.9, "H")}
    arch = {"schema": archive.ARCHIVE_SCHEMA,
            "slots": {"overall": [], "exploration": []},
            "entries": {"ch": entry}, "exploration_queue": []}
    result = archive.apply_challenge(arch, epoch, "ch",
                                     {"ch": entry["normal_evaluations"]},
                                     refresh_roots=refresh, core_rows=FROZEN_ROWS)
    assert result["status"] == "pending_partial"
    assert result["phase"] == "phase1"
    assert result["missing"]["ch"] == ["n2", "n3", "n4"], result["missing"]
    assert result["missing_reported_row_set"]["ch"] == ["n2", "n3", "n4"]
    assert result["missing_comparison"]["ch"]["consistent"] is True


# ===========================================================================
# 任务 3 · sitin_natural_panel：授权门统一走受信校验入口
# ===========================================================================

#: 原已授权的 batch7 同范围复验令牌（与生产在案件同构：别的 schema 标签也按 legacy 接受）。
AUTH_LEGACY: Dict[str, Any] = {
    "schema": "sitin-gate2-authorization/1", "authorized": True, "batch": 7,
    "batch_label": "p14-legacy-batch7",
    "budgets": {"tables_full": 264.0, "tables_partial": 122.0,
                "prefix_generation": 101.0, "tokens_input": 0.0,
                "tokens_output": 0.0, "confirm_reserved": 0.0}}
#: 新形态（sitin-authorization/1）正例。
AUTH_FULL: Dict[str, Any] = {
    "schema": "sitin-authorization/1", "authorization_id": "auth-p14-0001",
    "batch_label": "p14-smallfix", "trusted": True,
    "allowed_operations": ["natural_panel", "conditional_prefix", "family_fill",
                           "conditional_refill", "evaluate", "summarize"],
    "allowed_accounts": {"tables_full": 256.0, "tables_partial": 64.0,
                         "prefix_generation": 64.0, "tokens_input": 100000.0,
                         "tokens_output": 200000.0, "confirm_reserved": 0.0},
    "issued_by": "lead", "issued_at_utc": "2026-09-18T00:00:00Z"}


def _dual(**overrides: Any) -> Dict[str, Any]:
    """dual 形态（新字段 + 旧门值并存）：旧式门会放行，统一门必须逐项判。"""

    token = dict(AUTH_FULL)
    token.update({"authorized": True, "batch": 7})
    token.update(overrides)
    return token


def test_legacy_batch7_token_is_accepted_and_labelled():
    """legacy 正例：原已授权的 batch7 同范围复验继续可跑，且审计里显式标形态。"""

    verdict = natural.require_authorization(AUTH_LEGACY)
    assert isinstance(verdict, Mapping)
    assert verdict["authorization_form"] == "legacy_batch7", verdict
    assert verdict["ok"] is True, verdict
    assert verdict["operation"] == "natural_panel", verdict
    assert verdict["trusted"] is True, verdict
    assert verdict["legacy_removal_condition"], verdict


def test_full_form_token_is_accepted():
    """新形态正例：完整字段逐项通过。"""

    verdict = natural.require_authorization(AUTH_FULL)
    assert verdict["authorization_form"] == "sitin-authorization/1"
    assert verdict["ok"] is True
    assert verdict["authorization_id"] == "auth-p14-0001"


def test_overreaching_operation_is_refused_even_with_the_old_batch_value():
    """越权反例：带旧门值（authorized=true/batch=7）但允许操作集不含 natural_panel ⇒ 拒绝。

    旧式门只看 `authorized is True and batch == 7`，会放行这一份；统一门必须拒。
    """

    token = _dual(allowed_operations=["evaluate", "summarize"])
    with pytest.raises(SystemExit) as caught:
        natural.require_authorization(token)
    message = str(caught.value)
    assert "operation_not_allowed" in message and "natural_panel" in message, message
    assert "authorization_form" in message or "dual" in message, message


def test_untrusted_token_is_refused_even_with_the_old_batch_value():
    """未受信反例：trusted=false（或非受信签发方）即使带旧门值也必须拒绝。"""

    with pytest.raises(SystemExit) as caught:
        natural.require_authorization(_dual(trusted=False))
    assert "trusted_false" in str(caught.value), str(caught.value)

    with pytest.raises(SystemExit) as caught:
        natural.require_authorization(_dual(issued_by="model"))
    assert "issuer_untrusted" in str(caught.value), str(caught.value)


def test_unknown_form_and_undeclared_account_are_refused():
    """反例：形态无法识别 / 未声明所需账户额度（不按无限额处理）。"""

    with pytest.raises(SystemExit):
        natural.require_authorization({"authorized": False, "batch": 7})
    with pytest.raises(SystemExit) as caught:
        natural.require_authorization(dict(AUTH_LEGACY, budgets={"prefix_generation": 8.0}))
    assert "account_not_declared" in str(caught.value), str(caught.value)


def test_gate_agrees_with_the_state_machine_entry_point():
    """上下层**一套判据**：本模块门 == 状态机入口，逐令牌结论逐项一致。"""

    tokens = [AUTH_LEGACY, AUTH_FULL,
              _dual(allowed_operations=["evaluate"]), _dual(trusted=False),
              {"authorized": True, "batch": 8},
              {"authorized": True, "batch": 7, "budgets": {}},
              None]
    for token in tokens:
        ok, _reason, audit = search.av_authorization_allows(
            token, operation="natural_panel",
            required=search.AV_AUTHORIZATION_OPERATION_REQUIREMENTS["natural_panel"])
        if ok:
            verdict = natural.require_authorization(token)
            assert verdict["authorization_form"] == audit["authorization_form"], token
            assert verdict["ok"] is True
        else:
            with pytest.raises(SystemExit):
                natural.require_authorization(token)


def test_gate_refuses_before_any_table_or_output(tmp_path):
    """门的位置：非法授权在**任何副作用之前**拒绝（不建产物目录、不启动桌赛）。"""

    out_dir = tmp_path / "never-created"
    with pytest.raises(SystemExit):
        natural.run_natural_panel(
            candidate_source="", opponent="H", roots=1, seats_per_root=1,
            contract={}, out_dir=out_dir,
            authorization={"authorized": True, "batch": 7, "budgets": {}})
    assert not out_dir.exists()
