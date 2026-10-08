# -*- coding: utf-8 -*-
"""R9/P5 FEED 边界测试：F1 完整读取文档的根用途检查、F2 身份绑定与拒绝回退。

来源：R8-REPAIR-REREVIEW-2026-09-17.md 第 6 节 F1/F2（P1/P2）与
R9-FIX-PLAN-2026-09-17.md 第 7 节。冻结版本上复现的两个反例：

- F1：`_projection_documents` 对自然面板只传 `statistics`，但事实段会渲染
  `samples`，还读 `config/identity/cost`。给原始样本标确认用途后公开入口仍
  ok / executable=True，确认根名进入事实文本；只在 config 标用途同样不拒绝。
- F2：保留正确 evaluation、让 `summary/statistics.json` 的唯一候选是另一身份
  （均值 777.0），反馈仍把外来数字用于本候选；把已生成反馈的
  `identity.candidate_id` 改成另一父代，M1 读取闸门仍 ok=True。

本文件按验收口径写断言（不写"不报错"这种弱断言）：

- F1 五处标记（样本 / config / identity / 统计 / JSONL）分别不可执行，且
  **M1 不生成提示词、不建立模型调用事务**；
- 拒绝产物只暴露诊断定位（文档 / 字段 / JSON 路径），确认根名一律不进反馈；
- 正确的开发产物与一致的冻结清单仍然可用（反向对照，不误杀）；
- F2 精确集合断言：多候选目录只能取到精确目标（来源产物 + 候选键集合相等）；
- M1 读取闸门逐项绑定父代身份 / 反馈结构版本 / 来源摘要 / 准入身份。

预算红线：全部离线（mock 生成 + 夹具桌赛驱动）；0 真实桌赛、0 模型调用、0 网络；
既有 evidence/ 只读（一律复制到 tmp_path 再改）。
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
import shutil
from pathlib import Path

import pytest

import sitin_archive as archive
import sitin_feedback as sf
import sitin_natural_panel as natural
import sitin_search as search

_HERE = Path(__file__).resolve().parent
#: 冻结的 R6 证据目录（整棵复制到临时目录后再改；原件只读）。
FIXTURE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r6-e-revalidation')

pytestmark = pytest.mark.skipif(
    not (_project_file(_PROJECT_ROOT, FIXTURE / "eval")).is_dir(), reason="R6 E 重验产物不在本检出")

#: 条件评估产物的候选身份（读自产物）。
CID = "2fc08dfce2fb50fe48d57a5ab5bdbeaf04e9177be731048d322ec5cdf99120c2"
#: 自然面板自报的候选身份（与条件评估不同，绑定靠源码摘要）。
PANEL_CID = "44d3c9f0a0b08c4c494e58454977075dda9d8fcd3cc5e560b09e30661ab9e64b"
#: F1 反例用的确认根名：出现在事实/结果段即为泄漏。
SECRET = "confirmation-sample-secret-01"
#: F2 反例用的外来候选与外来均值。
ALIEN_CID = "alien-candidate"
ALIEN_MEAN = 777.0

#: 批次 7 授权令牌（夹具桌赛；与 P9 测试同一口径）。
TOKEN = {"authorized": True, "batch": 7,
         "budgets": {"tokens_input": 100000, "tokens_output": 200000,
                     "tables_full": 256, "tables_partial": 64,
                     "prefix_generation": 64}}
PANEL_SEED = 20260916


# ---------------------------------------------------------------------------
# 夹具：复制既有证据产物（只读原件）
# ---------------------------------------------------------------------------


def _load(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _save(path: Path, data) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=1),
                          encoding="utf-8")


def _sandbox(tmp_path: Path, name: str) -> Path:
    """把冻结证据整棵复制到临时目录，返回评估目录（候选源码在兄弟目录里）。"""

    dest = Path(tmp_path) / name
    shutil.copytree(FIXTURE, dest, dirs_exist_ok=True)
    return dest / "eval"


def _project(eval_dir: Path, *, candidate_cid=CID, **kwargs):
    kwargs.setdefault("parent_cid", None)
    inputs = sf.collect_feedback_inputs(Path(eval_dir), candidate_cid=candidate_cid,
                                        **kwargs)
    return sf.build_feedback_projection(inputs)


def _text_of(projection) -> str:
    return "\n".join(list(projection["facts"]) + list(projection["associated_results"]))


def _h_panel(root: Path) -> Path:
    return root / "i1-natural-H" / "panel.json"


def _panel_statistics(panel) -> dict:
    key = sorted(panel["statistics"]["by_candidate"])[0]
    return panel["statistics"]["by_candidate"][key]


# ---------------------------------------------------------------------------
# F1 五处标记（对应验收矩阵：样本 / config / identity / 统计 / JSONL）
# ---------------------------------------------------------------------------


def mark_sample(root: Path) -> None:
    """样本：usage + root_usage + confirmation_eligible（正在渲染的那一层）。"""

    path = _h_panel(root)
    data = _load(path)
    row = data["samples"][0]
    row["usage"] = "confirmation"
    row["root_usage"] = "confirmation"
    row["confirmation_eligible"] = True
    row["source_root_id"] = SECRET
    _save(path, data)


def mark_config(root: Path) -> None:
    """config：只标 usage；统计块与样本一律不动。"""

    path = _h_panel(root)
    data = _load(path)
    data["config"]["usage"] = "confirmation"
    _save(path, data)


def mark_identity(root: Path) -> None:
    """identity：只标 confirmation_eligible。"""

    path = _h_panel(root)
    data = _load(path)
    data["identity"]["confirmation_eligible"] = True
    _save(path, data)


def mark_statistics(root: Path) -> None:
    """统计块根行：既有测试已覆盖的路径，保留作对照。"""

    path = _h_panel(root)
    data = _load(path)
    rows = _panel_statistics(data)["panels"]["normal"]["panels"]["H"]["root_rows"]
    rows[0]["usage"] = "confirmation"
    rows[0]["root_id"] = SECRET
    _save(path, data)


def mark_jsonl(root: Path) -> None:
    """独立 JSONL：去掉全部自然 panel.json，标记写进 i1-natural-H 第一行。"""

    panels = {}
    for panel_path in sorted(root.rglob("panel.json")):
        document = _load(panel_path)
        if not isinstance(document.get("samples"), list):
            continue
        panels[panel_path.parent] = document
        panel_path.unlink()
    for parent, panel in sorted(panels.items()):
        rows = [dict(row) for row in panel["samples"]]
        if str(panel["identity"].get("candidate_id") or "") == PANEL_CID:
            statistics = copy.deepcopy(panel["statistics"])
            statistics["by_candidate"] = {CID: statistics["by_candidate"][
                sorted(statistics["by_candidate"])[0]]}
            _save(parent / "natural-statistics.json", statistics)
            for row in rows:
                row["candidate_id"] = CID
        if parent.name == "i1-natural-H":
            rows[0]["usage"] = "confirmation"
            rows[0]["source_root_id"] = SECRET
        with (parent / "samples.jsonl").open("w", encoding="utf-8") as handle:
            for row in rows:
                slim = {k: v for k, v in row.items() if k != "raw_arms"}
                handle.write(json.dumps(slim, ensure_ascii=False) + "\n")


MARKERS = {"sample": mark_sample, "config": mark_config,
           "identity": mark_identity, "statistics": mark_statistics,
           "jsonl": mark_jsonl}


def test_correct_development_product_still_usable(tmp_path):
    """反向对照：未标记的开发产物必须仍然可执行（新增扫描不得误杀）。"""

    projection = _project(_sandbox(tmp_path, "baseline"))
    assert projection["status"] == sf.PROJECTION_OK
    assert projection["executable"] is True
    assert projection["refusals"] == []
    assert projection["facts"] and projection["associated_results"]
    assert SECRET not in _text_of(projection)
    # 扫描覆盖：条件评估 + 自然面板**整份文档** + 机会面板（本冻结目录没有
    # summary/*：那是主状态机写成，见整链测试里的扫描清单断言）。
    scanned = [Path(path) for path in projection["usage_scan"]["documents"]]
    assert {path.name for path in scanned} >= {"evaluation.json", "panel.json"}
    assert {path.parent.name for path in scanned} >= {
        "i1-natural-H", "i1-natural-M", "panel-branch_open"}
    assert projection["usage_scan"]["confirmation_hits"] == 0
    assert projection["usage_scan"]["truncated"] is False


@pytest.mark.parametrize("place", sorted(MARKERS))
def test_confirmation_usage_anywhere_refuses_before_rendering(tmp_path, place):
    """五处标记：一律不可执行，且拒绝产物不渲染任何产物内容。"""

    sandbox = _sandbox(tmp_path, "mark-" + place)
    MARKERS[place](sandbox)
    projection = _project(sandbox)
    assert projection["status"] == sf.PROJECTION_REFUSED
    assert projection["executable"] is False
    codes = {item["code"] for item in projection["refusals"]}
    assert sf.REFUSAL_BOUNDARY_CONFIRMATION in codes, codes
    # 三段正文与逐条条目一律不渲染（确认结果不进反馈）。
    assert projection["facts"] == []
    assert projection["associated_results"] == []
    assert projection["facts_items"] == [] and projection["result_items"] == []
    assert SECRET not in _text_of(projection)
    assert SECRET not in json.dumps(projection["refusals"], ensure_ascii=False)
    # 诊断只暴露定位：文档 + 字段 + JSON 路径。
    details = " | ".join(item["detail"] for item in projection["refusals"])
    assert "panel.json" in details or "samples.jsonl" in details
    assert "字段" in details and "#/" in details


@pytest.mark.parametrize("field", ["usage", "root_usage",
                                     "confirmation_eligible"])
def test_sample_marker_reports_the_rendered_layer(tmp_path, field):
    """样本层的三种标记**各自单独**都要被抓到（扫的是正在渲染的那一层）。"""

    sandbox = _sandbox(tmp_path, "locate-" + field)
    path = _h_panel(sandbox)
    data = _load(path)
    data["samples"][0][field] = True if field == "confirmation_eligible" \
        else "confirmation"
    _save(path, data)
    projection = _project(sandbox)
    hits = [item for item in projection["refusals"]
            if item["code"] == sf.REFUSAL_BOUNDARY_CONFIRMATION]
    assert hits, projection["refusals"]
    details = " | ".join(item["detail"] for item in hits)
    assert "#/samples/0" in details
    assert field in details
    assert projection["usage_scan"]["confirmation_hits"] >= 1


def test_jsonl_marker_is_scanned_line_by_line(tmp_path):
    """独立 JSONL：逐行扫描，定位到具体行号。"""

    sandbox = _sandbox(tmp_path, "locate-jsonl")
    mark_jsonl(sandbox)
    projection = _project(sandbox)
    details = " | ".join(item["detail"] for item in projection["refusals"])
    assert "#/line/0" in details
    assert "samples.jsonl" in details


def test_rejection_document_keeps_only_diagnostics(tmp_path):
    """拒绝产物（Markdown）里只有诊断，没有确认结果。"""

    sandbox = _sandbox(tmp_path, "doc")
    mark_sample(sandbox)
    inputs = sf.collect_feedback_inputs(sandbox, parent_cid=None, candidate_cid=CID)
    document = sf.build_feedback_document(inputs)
    assert "不可执行" in document
    assert SECRET not in document
    assert sf.REFUSAL_BOUNDARY_CONFIRMATION in document
    facts_heading = document.split(sf.HEADING_RESULTS)[0].split(sf.HEADING_FACTS)[1]
    assert "samples" not in facts_heading  # 样本行没有被渲染


def test_unknown_usage_and_manifest_conflict_are_refused(tmp_path):
    """词表外的用途词与冻结清单冲突一律拒绝；清单一致仍可用。"""

    sandbox = _sandbox(tmp_path, "unknown")
    data = _load(_h_panel(sandbox))
    data["samples"][0]["usage"] = "production"
    _save(_h_panel(sandbox), data)
    projection = _project(sandbox)
    assert sf.REFUSAL_BOUNDARY_USAGE_UNKNOWN in {
        item["code"] for item in projection["refusals"]}
    assert projection["executable"] is False

    clean = _sandbox(tmp_path, "manifest")
    declared = _declared_roots(clean)
    assert declared, "夹具里必须能扫到声明过用途的根"
    manifest = _manifest(tmp_path, "consistent.json", declared)
    assert _project(clean, usage_manifest_path=manifest)["executable"] is True
    conflicted = dict(declared)
    conflicted[sorted(conflicted)[0]] = "confirmation"
    manifest = _manifest(tmp_path, "conflict.json", conflicted)
    projection = _project(clean, usage_manifest_path=manifest)
    assert projection["executable"] is False
    assert sf.REFUSAL_BOUNDARY_CONFIRMATION in {
        item["code"] for item in projection["refusals"]}


def test_usage_vocabulary_matches_frozen_archive_vocabulary(tmp_path):
    """用途词表与清单 schema 与档案模块（冻结来源）逐字一致。"""

    assert tuple(sf.ROOT_USAGES) == tuple(archive.ROOT_USAGES)
    assert sf.ROOT_USAGE_MANIFEST_SCHEMA == archive.ROOT_USAGE_SCHEMA
    assert sf.CONFIRMATION_USAGE in archive.ROOT_USAGES
    assert sf.ROOT_USAGE_DEVELOPMENT_CORE in archive.ROOT_USAGES
    assert sf.ROOT_USAGE_DEVELOPMENT_REFRESH in archive.ROOT_USAGES
    # M1 读取闸门认的结构版本必须等于投影模块自己声明的版本（不许两边各写一份）。
    assert search.AV_FEEDBACK_SCHEMA == sf.PROJECTION_SCHEMA
    # 档案模块造的清单必须被本模块接受（同一份冻结格式）。
    manifest = archive.build_root_usage_manifest(
        development_core=["root-a"], confirmation=["root-b"])
    path = _write_json(Path(tmp_path) / "root-usage.json", manifest)
    assert sf._read_usage_manifest(path) == {"root-a": "development_core",
                                             "root-b": "confirmation"}


def _write_json(path: Path, data) -> Path:
    _save(path, data)
    return path


def _declared_roots(root: Path) -> dict:
    """产物里声明过用途的根（{root_id: usage}），用来造完备清单。"""

    found: dict = {}

    def walk(node) -> None:
        if isinstance(node, dict):
            declared = [node.get(field) for field in ("usage", "root_usage")
                        if isinstance(node.get(field), str) and node.get(field)]
            root_id = node.get("root_id") or node.get("source_root_id")
            if declared and isinstance(root_id, str) and root_id:
                found[root_id] = str(declared[0]).lower()
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    for path in sorted(root.rglob("*.json")):
        try:
            walk(_load(path))
        except ValueError:
            continue
    return found


def _manifest(raw_root: Path, name: str, usage_by_root: dict) -> Path:
    sections = {"development_core": [], "development_refresh": [],
                "confirmation": []}
    for root_id, usage in sorted(usage_by_root.items()):
        sections.setdefault(str(usage), []).append(root_id)
    return _write_json(Path(raw_root) / name,
                       {"schema": sf.ROOT_USAGE_MANIFEST_SCHEMA,
                        "usage": sections})


# ---------------------------------------------------------------------------
# F1 全流程：确认用途 → M1 不发提示词、不建模型调用事务
# ---------------------------------------------------------------------------


class FixtureDrive:
    """替身桌赛驱动（0 真实桌赛）：候选臂焦点强、基线臂焦点弱，数值可复现。"""

    def __call__(self, *, plan, policies_by_seat, versions_block, step_limit,
                 value_limits):
        seats = list(plan.seats())
        focal_idx = seats.index("focal") if "focal" in seats \
            else seats.index("natural:focal")
        policy = policies_by_seat[focal_idx]
        is_candidate = str(getattr(policy, "policy_id", "")).startswith("action_value")
        focal = 12.0 if is_candidate else -10.0
        others = iter((5.0, 3.0, 1.0))
        scores = [focal if seat == focal_idx else next(others) for seat in range(4)]
        return {"table_id": plan.table_id, "seed": int(plan.seed),
                "match_status": "complete", "wall_ms": 1.0,
                "scores_by_seat": scores, "result": {}}


@pytest.fixture()
def fixture_drive(monkeypatch):
    drive = FixtureDrive()
    monkeypatch.setattr(natural, "execute_natural_table", drive, raising=True)
    return drive


def _run_root(tmp_path: Path, name: str) -> Path:
    root = Path(tmp_path) / name / "run"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _evolve(run_root: Path, *, mode: str = "mock"):
    return search.run_av_evolution(run_root, generation_mode=mode,
                                   seed_name="efficiency_seed",
                                   panel_seed=PANEL_SEED, natural_roots=1,
                                   natural_seats=1, authorization=TOKEN)


def _iter_dir(run_root: Path, index: int = 1) -> Path:
    return Path(run_root) / "iterations" / "iter-{0:02d}".format(index)


def _summarize_only(run_root: Path) -> None:
    """把迭代状态拨回 NATURAL_EVALUATED 再走一次正式 summary 步（篡改后重投影）。"""

    state_path = _iter_dir(run_root) / "state.json"
    state = _load(state_path)
    state["status"] = "NATURAL_EVALUATED"
    _save(state_path, state)
    return search.av_iteration_advance(state_path, Path(run_root),
                                       authorization=TOKEN, stop_after="SUMMARIZED")


def _m1_attempt(run_root: Path):
    """开第二次迭代（delegate）：看 M1 是否被允许生成提示词与事务件。"""

    result = _evolve(run_root, mode="delegate")
    iter_dir = _iter_dir(run_root, 2)
    prompt = iter_dir / "pending" / "m1" / "prompt.txt"
    tx = iter_dir / "transactions" / "tx-model-call-before.json"
    return result, iter_dir, prompt, tx


def _tampered_run(tmp_path: Path, name: str, tamper) -> Path:
    """本目录内跑完整 I1 → 篡改产物 → 重跑正式 summary（不复制运行目录）。"""

    run_root = _run_root(tmp_path, name)
    result = _evolve(run_root)
    assert result.get("terminal") == "ITERATION_COMPLETE", result
    tamper(_iter_dir(run_root))
    _summarize_only(run_root)
    state_path = _iter_dir(run_root) / "state.json"
    assert _load(state_path)["status"] == "SUMMARIZED"
    search.av_iteration_advance(state_path, Path(run_root), authorization=TOKEN)
    return run_root


def _mark_run_sample(iter_dir: Path) -> None:
    path = iter_dir / "natural-H" / "panel.json"
    data = _load(path)
    row = data["samples"][0]
    row["usage"] = "confirmation"
    row["root_usage"] = "confirmation"
    row["confirmation_eligible"] = True
    row["source_root_id"] = SECRET
    _save(path, data)


def _mark_run_config(iter_dir: Path) -> None:
    path = iter_dir / "natural-H" / "panel.json"
    data = _load(path)
    data["config"]["usage"] = "confirmation"
    _save(path, data)


def _mark_run_identity(iter_dir: Path) -> None:
    path = iter_dir / "natural-H" / "panel.json"
    data = _load(path)
    data["identity"]["confirmation_eligible"] = True
    _save(path, data)


def _mark_run_statistics(iter_dir: Path) -> None:
    path = iter_dir / "natural-H" / "panel.json"
    data = _load(path)
    candidate = str(data["identity"]["candidate_id"])
    rows = data["statistics"]["by_candidate"][candidate]["panels"]["normal"][
        "panels"]["H"]["root_rows"]
    rows[0]["usage"] = "confirmation"
    rows[0]["root_id"] = SECRET
    _save(path, data)


def _mark_run_jsonl(iter_dir: Path) -> None:
    candidate = str(_load(iter_dir / "state.json")["identity"]["candidate_id"])
    for mix in ("H", "M"):
        directory = iter_dir / ("natural-" + mix)
        panel = _load(directory / "panel.json")
        rows = [dict(row) for row in panel["samples"]]
        statistics = copy.deepcopy(panel["statistics"])
        statistics["by_candidate"] = {candidate: statistics["by_candidate"][
            sorted(statistics["by_candidate"])[0]]}
        _save(directory / "natural-statistics.json", statistics)
        for row in rows:
            row["candidate_id"] = candidate
        if mix == "H":
            rows[0]["usage"] = "confirmation"
            rows[0]["source_root_id"] = SECRET
        with (directory / "samples.jsonl").open("w", encoding="utf-8") as handle:
            for row in rows:
                slim = {k: v for k, v in row.items() if k != "raw_arms"}
                handle.write(json.dumps(slim, ensure_ascii=False) + "\n")
        (directory / "panel.json").unlink()


RUN_MARKERS = {"sample": _mark_run_sample, "config": _mark_run_config,
               "identity": _mark_run_identity, "statistics": _mark_run_statistics,
               "jsonl": _mark_run_jsonl}


@pytest.mark.parametrize("place", sorted(RUN_MARKERS))
def test_confirmation_usage_blocks_m1_prompt_and_transaction(tmp_path, fixture_drive,
                                                             place):
    """五处标记（整链）：反馈不可执行，M1 不发提示词、不建模型调用事务。"""

    run_root = _tampered_run(tmp_path, "run-" + place, RUN_MARKERS[place])
    feedback_text = (_iter_dir(run_root) / "summary" / "feedback.json").read_text(
        encoding="utf-8")
    projection = json.loads(feedback_text)
    assert projection["executable"] is False
    codes = {item["code"] for item in projection["refusals"]}
    assert sf.REFUSAL_BOUNDARY_CONFIRMATION in codes, codes
    assert projection["facts"] == [] and projection["associated_results"] == []
    # 拒绝产物整体（含诊断）不得复制确认结果。
    assert SECRET not in feedback_text
    state_text = (_iter_dir(run_root) / "state.json").read_text(encoding="utf-8")
    assert SECRET not in state_text
    state = json.loads(state_text)
    assert "feedback_not_executable" in " ".join(state.get("input_gaps") or [])
    result, _iter_two, prompt, tx = _m1_attempt(run_root)
    assert result.get("terminal") == "INPUT_GAP", result
    assert not prompt.is_file(), "确认用途数据混入不得产出可执行修订任务"
    assert not tx.is_file(), "M1 不得建立模型调用事务"
    m1_state = _load(_iter_dir(run_root, 2) / "state.json")
    assert "m1_feedback_refused" in " ".join(m1_state.get("input_gaps") or [])
    # 任务包（若有）与 M1 状态同样不得包含确认根名。
    assert SECRET not in json.dumps(m1_state, ensure_ascii=False)



# ---------------------------------------------------------------------------
# F2：精确身份匹配（删除「只有一个就采用」的回退）
# ---------------------------------------------------------------------------


def _summary_with_alien(root: Path, *, keep_target: bool) -> Path:
    """在 summary/statistics.json 造外来候选块（均值 777.0）。"""

    evaluation = _load(root / "i1-conditional" / "evaluation.json")
    stats = copy.deepcopy(evaluation["statistics"])
    target = copy.deepcopy(stats["by_candidate"][CID])
    alien = copy.deepcopy(target)
    for scenario in alien["panels"].values():
        for block in scenario["panels"].values():
            block["mean_delta"] = ALIEN_MEAN
    stats["by_candidate"] = ({ALIEN_CID: alien} if not keep_target else
                             {ALIEN_CID: alien, CID: target})
    path = root / "summary" / "statistics.json"
    _save(path, stats)
    return path


def _result_sources(projection) -> dict:
    """关联结果段条目 → （来源产物末两段路径，by_candidate 里实际用的候选键）。"""

    sources = {}
    for item in projection.get("result_items") or []:
        locator = str((item.get("evidence") or {}).get("locator") or "")
        key = None
        if "/by_candidate/" in locator:
            key = locator.split("/by_candidate/", 1)[1].split("/", 1)[0]
        artifact = Path(str((item.get("evidence") or {}).get("artifact") or ""))
        sources[item["key"]] = ("/".join(artifact.parts[-2:]), key)
    return sources


def test_candidate_key_requires_exact_identity():
    """单元口径：「只有一个就采用」的回退已删除。"""

    alien_only = {"by_candidate": {ALIEN_CID: {"panels": {}}}}
    assert sf._candidate_key(alien_only, CID) is None
    assert sf._candidate_key(alien_only, ALIEN_CID) == ALIEN_CID
    assert sf._candidate_key(alien_only, None) is None
    both = {"by_candidate": {ALIEN_CID: {}, CID: {}}}
    assert sf._candidate_key(both, CID) == CID


def test_unique_wrong_candidate_in_summary_is_refused(tmp_path):
    """唯一外来候选：拒绝，且不采用它的任何数字。"""

    root = _sandbox(tmp_path, "f2-wrong-only")
    _summary_with_alien(root, keep_target=False)
    projection = _project(root)
    assert projection["status"] == sf.PROJECTION_REFUSED
    assert projection["executable"] is False
    codes = {item["code"] for item in projection["refusals"]}
    assert sf.REFUSAL_IDENTITY_STATISTICS in codes, codes
    assert str(ALIEN_MEAN) not in _text_of(projection)
    # 精确集合：**没有任何条目**把 summary/statistics.json 当读数来源。
    sources = _result_sources(projection)
    assert {row for row in sources.values()
            if row[0] == "summary/statistics.json"} == set()
    assert sources["result.branch_open.H"] == ("i1-conditional/evaluation.json", CID)


def test_multi_candidate_summary_uses_exact_target_only(tmp_path):
    """正确多候选目录：只能取得精确目标（来源产物 + 候选键集合相等）。"""

    root = _sandbox(tmp_path, "f2-multi-correct")
    summary_path = _summary_with_alien(root, keep_target=True)
    projection = _project(root)
    assert projection["status"] == sf.PROJECTION_OK
    assert projection["executable"] is True
    assert str(ALIEN_MEAN) not in _text_of(projection)
    sources = _result_sources(projection)
    from_summary = {key for artifact, key in sources.values()
                    if artifact == "summary/statistics.json"}
    assert from_summary == {CID}, sources
    assert sources["result.branch_open.H"] == ("summary/statistics.json", CID)
    assert sources["result.family_sides.branch"] == ("summary/statistics.json", CID)
    # summary 里确实有两个候选（不是"没有外来候选"的假绿）。
    assert sorted(_load(summary_path)["by_candidate"]) == sorted([ALIEN_CID, CID])


def test_conflicting_panel_source_digest_is_refused(tmp_path):
    """面板自报 candidate_id 命中、但源码摘要与产物冲突 → 拒绝绑定。"""

    root = _sandbox(tmp_path, "f2-digest-conflict")
    for mix in ("H", "M"):
        path = root / ("i1-natural-" + mix) / "panel.json"
        data = _load(path)
        data["identity"]["candidate_id"] = CID
        data["identity"]["candidate_source_sha256"] = "0" * 64
        _save(path, data)
    projection = _project(root)
    assert projection["executable"] is False
    codes = {item["code"] for item in projection["refusals"]}
    assert sf.REFUSAL_IDENTITY_SOURCE in codes, codes
    assert "源码摘要" in " ".join(item["detail"] for item in projection["refusals"])


def test_source_digest_comes_from_evaluation_not_panels():
    """源码绑定以条件评估产物登记的摘要为准（面板不能自己给自己背书）。"""

    evaluation = _load(_project_file(_PROJECT_ROOT, FIXTURE / "eval" / "i1-conditional" / "evaluation.json"))
    panel_digest = "b" * 64
    digests = sf._collect_source_digests(
        evaluation, [{"identity": {"candidate_source_sha256": panel_digest}}])
    assert digests == [evaluation["admission"]["identity"]["candidate_source_sha256"]]
    assert panel_digest not in digests



# ---------------------------------------------------------------------------
# F2：M1 读取闸门（父代身份 / 反馈结构版本 / 来源摘要 / 准入身份）
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def mock_run(tmp_path_factory):
    """跑一整轮离线 mock I1（0 真实桌赛）：父代产物 + 三段反馈 + summary 全套。"""

    original = natural.execute_natural_table
    natural.execute_natural_table = FixtureDrive()
    try:
        run_root = tmp_path_factory.mktemp("p5-run") / "run"
        run_root.mkdir(parents=True, exist_ok=True)
        result = _evolve(run_root)
        assert result.get("terminal") == "ITERATION_COMPLETE", result
    finally:
        natural.execute_natural_table = original
    return {"root": run_root,
            "state": _load(_iter_dir(run_root) / "state.json"),
            "parent_cid": str(_load(_iter_dir(run_root) / "state.json")[
                "identity"]["candidate_id"])}


def _feedback_copy(mock_run, tmp_path: Path, name: str, mutate=None):
    """复制运行目录到临时位置 → 改反馈 → 返回（副本根, 迭代目录）。"""

    copy_root = Path(tmp_path) / name
    shutil.copytree(mock_run["root"], copy_root)
    iter_dir = copy_root / "iterations" / "iter-01"
    feedback_path = iter_dir / "summary" / "feedback.json"
    payload = _load(feedback_path)
    if mutate is not None:
        mutate(payload, iter_dir)
        _save(feedback_path, payload)
    return copy_root, iter_dir


def _verdict(iter_dir: Path, parent_cid: str) -> dict:
    _payload, verdict = search._av_m1_feedback(
        {"plan": {"parent_dir": str(iter_dir / "generation"),
                  "parent_candidate_id": parent_cid}})
    return verdict


def test_m1_gate_accepts_bound_parent_feedback(mock_run, tmp_path):
    """反向对照：身份齐全的父代反馈必须放行（新增核对不得误杀）。"""

    _root, iter_dir = _feedback_copy(mock_run, tmp_path, "baseline")
    verdict = _verdict(iter_dir, mock_run["parent_cid"])
    assert verdict["ok"] is True, verdict
    assert verdict["codes"] == []
    assert verdict["parent_candidate_id"] == mock_run["parent_cid"]
    projection = _load(iter_dir / "summary" / "feedback.json")
    identity = projection["identity"]
    assert identity["candidate_id"] == mock_run["parent_cid"]
    assert identity["source_file_sha256"] and identity["source_sha256"]
    rels = {entry["rel"] for entry in identity["evidence"]["files"]}
    assert {"conditional/evaluation.json", "natural-H/panel.json",
            "summary/statistics.json", "generation/candidate.py"} <= rels
    # 扫描清单覆盖主状态机写出的两份汇总产物（任何渲染/汇总之前就扫过）。
    scanned = {Path(path).name for path in projection["usage_scan"]["documents"]}
    assert {"evaluation.json", "statistics.json",
            "selection-notes.json"} <= scanned
    assert projection["usage_scan"]["confirmation_hits"] == 0
    # 准入身份逐字段等于**当前构造器**给出的身份（P4/M1 的材料与评判语义字段都在内）。
    source = (_iter_dir(mock_run["root"]) / "generation"
              / "candidate.py").read_text(encoding="utf-8")
    expect = search.av_gates().av_identity_binding(source)
    for key, value in sorted(expect.items()):
        if key in search.AV_ADMISSION_DESCRIPTIVE_KEYS:
            continue
        assert identity["admission"].get(key) == value, key


M1_TAMPERS = {
    "other-parent": (
        lambda payload, _iter: payload["identity"].__setitem__(
            "candidate_id", "other-parent"),
        "identity.feedback_parent_mismatch"),
    "other-source-digest": (
        lambda payload, _iter: payload["identity"].__setitem__(
            "source_file_sha256", "0" * 64),
        "identity.feedback_source_mismatch"),
    "other-schema": (
        lambda payload, _iter: payload.__setitem__(
            "schema", "sitin-feedback-projection/0"),
        "input.feedback_schema"),
    "no-evidence": (
        lambda payload, _iter: payload["identity"].pop("evidence", None),
        "identity.feedback_evidence_drift"),
    "admission-executor": (
        lambda payload, _iter: payload["identity"]["admission"].__setitem__(
            "executor_version", "action-value-executor/0"),
        "identity.feedback_admission_mismatch"),
}


@pytest.mark.parametrize("case", sorted(M1_TAMPERS))
def test_m1_gate_binds_parent_identity_and_digests(mock_run, tmp_path, case):
    """逐项改父代身份 / 结构版本 / 来源摘要 / 准入身份 → 闸门必须拒绝。"""

    mutate, expected = M1_TAMPERS[case]
    _root, iter_dir = _feedback_copy(mock_run, tmp_path, "gate-" + case, mutate)
    verdict = _verdict(iter_dir, mock_run["parent_cid"])
    assert verdict["ok"] is False, verdict
    assert expected in verdict["codes"], verdict


def test_m1_gate_rejects_drifted_evidence(mock_run, tmp_path):
    """反馈写完之后产物被改写：来源摘要与当前字节不一致 → 拒绝。"""

    def _drift(payload, iter_dir):
        panel_path = iter_dir / "natural-H" / "panel.json"
        panel = _load(panel_path)
        panel["cost"]["tampered_after_feedback"] = True
        _save(panel_path, panel)

    _root, iter_dir = _feedback_copy(mock_run, tmp_path, "gate-drift", _drift)
    verdict = _verdict(iter_dir, mock_run["parent_cid"])
    assert verdict["ok"] is False, verdict
    assert "identity.feedback_evidence_drift" in verdict["codes"], verdict
    assert "natural-H/panel.json" in verdict["detail"]


def test_m1_gate_follows_current_admission_identity_fields(mock_run, tmp_path,
                                                           monkeypatch):
    """闸门按**当前准入身份构造器**取字段：构造器加字段，闸门自动要求它。

    P4/M1 把 `materials_sha256` / `executor_version` / `thresholds` 并入准入身份；
    这里模拟构造器再扩两个身份字段——只信 executable/refusals 的实现会放行，
    逐项核对的实现必须拒绝。
    """

    real = search.av_gates()

    class GatesWithMaterials:
        def av_identity_binding(self, source):
            binding = dict(real.av_identity_binding(source))
            binding["materials_sha256"] = "m" * 64
            binding["thresholds_sha256"] = "t" * 64
            return binding

        def __getattr__(self, name):
            return getattr(real, name)

    monkeypatch.setattr(search, "av_gates", lambda: GatesWithMaterials())
    _root, iter_dir = _feedback_copy(mock_run, tmp_path, "admission-missing")
    verdict = _verdict(iter_dir, mock_run["parent_cid"])
    assert verdict["ok"] is False, verdict
    assert "identity.feedback_admission_mismatch" in verdict["codes"], verdict
    assert "materials_sha256" in verdict["detail"]

    def _complete(payload, _iter):
        payload["identity"]["admission"]["materials_sha256"] = "m" * 64
        payload["identity"]["admission"]["thresholds_sha256"] = "t" * 64

    _root2, iter_two = _feedback_copy(mock_run, tmp_path, "admission-present",
                                      _complete)
    assert _verdict(iter_two, mock_run["parent_cid"])["ok"] is True


def test_m1_full_flow_refuses_prompt_and_transaction_for_other_parent(
        tmp_path, fixture_drive):
    """整链：反馈写的是别的父代 → INPUT_GAP，不发提示词、不建模型调用事务。"""

    run_root = _run_root(tmp_path, "m1-gate-flow")
    result = _evolve(run_root)
    assert result.get("terminal") == "ITERATION_COMPLETE", result
    feedback_path = _iter_dir(run_root) / "summary" / "feedback.json"
    payload = _load(feedback_path)
    payload["identity"]["candidate_id"] = "other-parent"
    _save(feedback_path, payload)
    result, _iter_two, prompt, tx = _m1_attempt(run_root)
    assert result.get("terminal") == "INPUT_GAP", result
    assert not prompt.is_file(), "父代身份不符不得产出可执行修订任务"
    assert not tx.is_file(), "M1 不得建立模型调用事务"
    state = _load(_iter_dir(run_root, 2) / "state.json")
    assert state["feedback_refusal"]["codes"] == ["identity.feedback_parent_mismatch"]

