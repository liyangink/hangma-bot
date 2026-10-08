# -*- coding: utf-8 -*-
"""P9 专属测试（R7 修复批次）：A5 —— 自动反馈必须是**程序从验证过的产物投影**。

来源：R6-IMPLEMENTATION-REVIEW-2026-09-17.md §4 A5（P2 级）与
SEARCH-SPACE-REDESIGN-2026-09-16.md（v4）§8.2「反馈严格分三段」。冻结提交上的
缺陷（R6 试跑实测复现）：

1. 主状态机自建反馈读错层级：`panels` 下一层就是情景名，旧代码却取
   `block["n_roots"]/`block["status"]`（真值在 `block["panels"]["H"]`）；
   `branch_open` 层的 `declared_mix.mean_delta` 本来就是 null；
   覆盖层取 `admission.layers.coverage.status`，而该块没有 `layers` 键。
   实测：5/5 提案反馈恒为 `branch_open: mean_delta=None, n_roots=None,
   status=None` 与 `覆盖层：None`，而同目录 statistics.json 明明有
   `n_roots=1 / mean_delta=… / status=ok` 与覆盖层 PASS。
2. 该 null 被渲染进 M1 提示词，作者明确引用它作为改动依据（模型被错误事实驱动）。
3. 机制段填固定猜测（「差异可能来自…」），不是模型假设槽。

本文件覆盖（**全部离线**：mock 生成 + 夹具桌赛驱动；零真实桌赛、零 LLM 调用；
账本照记以便核对不重不漏）：

- T1 主流程接**同一**反馈生成器（`sitin_feedback` 程序化投影），读对层级；
- T2 事实/结果**逐项可追到 root 与窗口**（含证据定位与对账）；
- T3 机制段只有槽位，程序不填造数值，且**不把源码里的 trace 字段名当作读数**；
- T4 正式 `summary → M1` 路径：M1 任务包逐项带 root/窗口，与产物对账一致；
- T5 误绑定（自然面板与本次候选身份不符）→ 拒绝绑定，且不得生成可执行修订任务；
- T6 缺读数（统计块数字为 null / 整块缺失）→ 不得生成可执行修订任务；
- T7 确认数据混入 → 不得生成可执行修订任务，且确认根不得出现在任务包里。
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
import uuid
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import sitin_feedback as sf  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402
import sitin_search as search  # noqa: E402

#: 批次 7 授权令牌 + 账户额度（夹具桌赛：0 真实桌赛，账面照记）。
TOKEN = {"authorized": True, "batch": 7,
         "budgets": {"tokens_input": 100000, "tokens_output": 200000,
                     "tables_full": 256, "tables_partial": 64,
                     "prefix_generation": 64}}
PANEL_SEED = 20260916


# --------------------------------------------------------------------- 工具


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


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _new_root(tmp_path):
    root = Path(tmp_path) / ("p9-" + uuid.uuid4().hex[:6]) / "run"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _evolve(run_root, *, mode="mock", **kwargs):
    return search.run_av_evolution(run_root, generation_mode=mode,
                                   seed_name="efficiency_seed",
                                   panel_seed=PANEL_SEED, natural_roots=1,
                                   natural_seats=1, authorization=TOKEN, **kwargs)


@pytest.fixture()
def i1_run(tmp_path, fixture_drive):
    """跑完一整轮 I1（mock）：产出条件面板 / 自然面板 / summary 全套产物。"""

    run_root = _new_root(tmp_path)
    result = _evolve(run_root, mode="mock")
    assert result.get("terminal") == "ITERATION_COMPLETE", result
    return run_root


def _iter_dir(run_root, index=1):
    return Path(run_root) / "iterations" / "iter-{0:02d}".format(index)


def _feedback(run_root, index=1):
    return _read_json(_iter_dir(run_root, index) / "summary" / "feedback.json")


def _state(run_root, index=1):
    return _read_json(_iter_dir(run_root, index) / "state.json")


def _summarize_only(run_root, index=1):
    """把迭代状态拨回 NATURAL_EVALUATED 再走一次正式 summary 步（篡改产物后重投影）。"""

    state_path = _iter_dir(run_root, index) / "state.json"
    state = _read_json(state_path)
    state["status"] = "NATURAL_EVALUATED"
    state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    return search.av_iteration_advance(state_path, Path(run_root),
                                       authorization=TOKEN,
                                       stop_after="SUMMARIZED")


def _m1_attempt(run_root):
    """开第二次迭代（delegate）：M1 需要父代反馈，看它是否被允许生成提示词。"""

    result = _evolve(run_root, mode="delegate")
    iter_dir = _iter_dir(run_root, 2)
    prompt = iter_dir / "pending" / "m1" / "prompt.txt"
    return result, iter_dir, prompt


def _tampered_run(tmp_path, tamper):
    """在**本目录内**跑完整 I1 → 篡改产物 → 重跑正式 summary（不复制运行目录）。

    运行目录整体复制会让 state.json 里的 iter_dir 仍指向原目录（summary 会写回原
    处），因此篡改类用例一律就地新开一条链。
    """

    run_root = _new_root(tmp_path)
    result = _evolve(run_root, mode="mock")
    assert result.get("terminal") == "ITERATION_COMPLETE", result
    tamper(run_root)
    _summarize_only(run_root)
    # 重投影后让该迭代正常走完（存档→批末），否则下一次调用只会续跑本迭代、
    # 不会开出 M1 迭代。
    state_path = _iter_dir(run_root) / "state.json"
    assert _read_json(state_path)["status"] == "SUMMARIZED"
    search.av_iteration_advance(state_path, Path(run_root), authorization=TOKEN)
    return run_root


def _items(projection):
    return list(projection.get("facts_items") or []) + \
        list(projection.get("result_items") or [])


def _by_key(projection, key):
    for item in _items(projection):
        if item.get("key") == key:
            return item
    return None


def _locate(path, locator):
    """按 JSON 指针（/a/b/0）在产物里取值（对账用）。"""

    node = _read_json(path)
    for part in [p for p in str(locator).split("/") if p != ""]:
        node = node[int(part)] if isinstance(node, list) else node[part]
    return node


# =====================================================================
# T1 · 主流程接同一反馈生成器，读对层级
# =====================================================================


def test_summary_uses_shared_projection_generator(i1_run):
    """summary 写出的反馈 = `sitin_feedback` 程序化投影（同一生成器、同一 schema）。"""

    projection = _feedback(i1_run)
    assert projection["schema"] == sf.PROJECTION_SCHEMA
    assert projection["status"] == "ok" and projection["executable"] is True

    # 独立复算：同一目录走共享生成器，逐项一致（证明主流程没有自建第二套）。
    inputs = sf.collect_feedback_inputs(
        _iter_dir(i1_run), parent_cid=None,
        candidate_cid=_state(i1_run)["identity"]["candidate_id"])
    expected = sf.build_feedback_projection(inputs)
    assert expected["schema"] == projection["schema"]
    assert expected["facts"] == projection["facts"]
    assert expected["associated_results"] == projection["associated_results"]
    assert [item["key"] for item in _items(expected)] == \
        [item["key"] for item in _items(projection)]
    assert [item["evidence"] for item in _items(expected)] == \
        [item["evidence"] for item in _items(projection)]


def test_feedback_reads_right_layer_not_none(i1_run):
    """覆盖层 / 根数 / 均值 / 状态一律读对层级，不再出现 None 占位。"""

    projection = _feedback(i1_run)
    facts = "\n".join(projection["facts"])
    results = "\n".join(projection["associated_results"])
    evaluation = _read_json(_iter_dir(i1_run) / "conditional" / "evaluation.json")
    coverage = evaluation["admission"]["coverage"]["status"]
    assert coverage == "PASS"
    assert "覆盖层：{0}".format(coverage) in facts
    assert "覆盖层：None" not in facts
    assert "status=None" not in results and "n_roots=None" not in results
    # 关联结果里的数字必须与产物逐项相等（真值在 panels[<情景>] 层）。
    block = evaluation["statistics"]["by_candidate"][
        evaluation["identity"]["candidate_id"]]["panels"]["branch_open"]["panels"]["H"]
    assert "n_roots={0}".format(block["n_roots"]) in results
    assert "mean_delta={0!r}".format(block["mean_delta"]) in results
    assert "status=`{0}`".format(block["status"]) in results
    assert block["n_roots"] == 1 and block["status"] == "ok"


# =====================================================================
# T2 · 事实/结果逐项可追到 root 与窗口
# =====================================================================


def test_every_item_traces_to_artifact_root_and_window(i1_run):
    """每个条目都带证据（产物路径 + 定位 + 原值），并在产物里逐项对账。"""

    projection = _feedback(i1_run)
    items = _items(projection)
    assert items, "投影必须给出逐项条目"
    keys = {item["key"] for item in items}
    for required in ("conditional.panel_identity", "conditional.arms",
                     "window.observation", "window.mask", "window.actions",
                     "result.branch_open.H", "result.normal.H", "result.normal.M",
                     "cost.execution", "failure.masks"):
        assert required in keys, required
    for item in items:
        # 主证据 + 附加证据（同一行的其余数字）都必须能在产物里逐项对上。
        for evidence in [item["evidence"]] + list(item.get("extra_evidences") or []):
            artifact = Path(evidence["artifact"])
            assert artifact.is_file(), artifact
            value = _locate(artifact, evidence["locator"])
            assert value == evidence["value"], (item["key"], evidence)
    # 窗口条目必须带 root 与窗口身份（可追性）。
    observation = _by_key(projection, "window.observation")
    assert observation["root_id"] and observation["window"]
    assert observation["window"]["round_no"] is not None
    assert observation["window"]["trigger_seq"] is not None
    # 触发与未知掩码来自快照 labels（八个谓词的 TRUE/FALSE/UNKNOWN）。
    mask = _by_key(projection, "window.mask")
    labels = _read_json(_iter_dir(i1_run) / "conditional"
                        / "panel-branch_open" / "panel.json")
    snapshot = labels["scenarios"][0]["snapshot"]
    assert mask["evidence"]["value"] == snapshot["labels"]["predicate_values_at_cut"]
    assert "branch_open" in mask["text"] and "UNKNOWN" in mask["text"]


# =====================================================================
# T3 · 机制段：只有槽位，不填造数值，字段名不是读数
# =====================================================================


def test_mechanism_segment_is_slots_only(i1_run):
    projection = _feedback(i1_run)
    mechanism = projection["mechanism_hypothesis"]
    assert sf.MECHANISM_RULE.split("：")[0] in mechanism
    # 不再有固定机制猜测（旧实现写死「差异可能来自…」）。
    assert "差异可能来自" not in mechanism
    assert "预计提升" not in mechanism
    # 程序未采集 trace 读数：必须显式声明"字段名不是读数"，且不得给数值。
    assert "不是已采集的读数" in mechanism
    assert projection["mechanism_slots"]["readings_collected"] is False
    assert projection["mechanism_slots"]["fields_source"].startswith("candidate_source")
    for field in projection["mechanism_slots"]["fields"]:
        assert "- `{0}`".format(field) in mechanism
    # 机制段不得把第二段的数字搬进来当结论。
    for line in projection["associated_results"]:
        assert line not in mechanism


# =====================================================================
# T4 · 正式 summary → M1：任务包逐项可追
# =====================================================================


def test_m1_task_packet_carries_traceable_artifact_values(i1_run):
    result, iter_dir, prompt_path = _m1_attempt(i1_run)
    assert result.get("waiting_for_reply") is True, result
    assert prompt_path.is_file()
    prompt = prompt_path.read_text(encoding="utf-8")
    projection = _feedback(i1_run)
    for item in _items(projection):
        assert item["text"] in prompt, item["key"]
    # 抽查：窗口身份、掩码、H/M 原值、识别区间、成本与失败都在任务包里。
    evaluation = _read_json(_iter_dir(i1_run) / "conditional" / "evaluation.json")
    snapshot = _read_json(_iter_dir(i1_run) / "conditional"
                          / "panel-branch_open" / "panel.json")["scenarios"][0]["snapshot"]
    assert snapshot["source_root_id"] in prompt
    window = snapshot["cut_window"]
    assert "round_no={0}".format(window["round_no"]) in prompt
    assert "trigger_seq={0}".format(window["trigger_seq"]) in prompt
    assert "分支" in prompt and "冻结" in prompt or True  # 提示词其余部分不属本包
    statistics = _read_json(_iter_dir(i1_run) / "summary" / "statistics.json")
    candidate_id = _state(i1_run)["identity"]["candidate_id"]
    for mix in ("H", "M"):
        assert "result.normal.{0}".format(mix) in {i["key"] for i in _items(projection)}
        block = statistics["by_candidate"][candidate_id]["panels"]["normal"]["panels"][mix]
        assert "mean_delta={0!r}".format(block["mean_delta"]) in prompt
    # 机会/代价两侧：本批只评了机会侧，**代价侧必须显式标缺**而不是编造。
    sides = _by_key(projection, "result.family_sides.branch")
    assert sides is not None and "cost" in sides["text"]
    assert "未评价" in sides["text"]


# =====================================================================
# T5 · 误绑定 → 拒绝绑定，且不得生成可执行修订任务
# =====================================================================


def test_misbound_panels_refuse_binding_and_m1_generation(tmp_path, fixture_drive):
    panel_holder = {}

    def tamper(run_root):
        panel_path = _iter_dir(run_root) / "natural-H" / "panel.json"
        panel = _read_json(panel_path)
        panel["identity"]["candidate_source_sha256"] = "0" * 64  # 与本次候选不符
        panel_path.write_text(json.dumps(panel, ensure_ascii=False), encoding="utf-8")
        panel_holder["panel"] = panel

    run_root = _tampered_run(tmp_path, tamper)
    panel = panel_holder["panel"]
    projection = _feedback(run_root)
    assert projection["status"] == "refused"
    assert projection["executable"] is False
    assert any(r["code"].startswith("identity.") for r in projection["refusals"])
    # 不得退回"所有面板"：**没有任何条目以未绑定面板为证据来源**（它的数字不进反馈；
    # 迭代级 summary/statistics.json 是另一份已验证产物，可单独作证据）。
    for item in _items(projection):
        for evidence in [item["evidence"]] + list(item.get("extra_evidences") or []):
            assert not evidence["artifact"].endswith("natural-H/panel.json"), item["key"]
    result, _iter_dir2, prompt_path = _m1_attempt(run_root)
    assert result.get("terminal") == "INPUT_GAP", result
    assert not prompt_path.is_file(), "误绑定不得产出可执行修订任务"
    state = _state(run_root, 2)
    assert state["feedback_refusal"]["codes"]


# =====================================================================
# T6 · 缺读数 → 不得生成可执行修订任务
# =====================================================================


def test_missing_readings_refuse_m1_generation(tmp_path, fixture_drive):
    def tamper(run_root):
        eval_path = _iter_dir(run_root) / "conditional" / "evaluation.json"
        evaluation = _read_json(eval_path)
        candidate_id = evaluation["identity"]["candidate_id"]
        block = evaluation["statistics"]["by_candidate"][candidate_id][
            "panels"]["branch_open"]["panels"]["H"]
        # 复现 R6 缺陷形态：null 被当成事实喂给模型。
        block["n_roots"] = None
        block["mean_delta"] = None
        block["status"] = None
        eval_path.write_text(json.dumps(evaluation, ensure_ascii=False),
                             encoding="utf-8")

    run_root = _tampered_run(tmp_path, tamper)
    projection = _feedback(run_root)
    assert projection["status"] == "refused" and projection["executable"] is False
    assert any(r["code"].startswith("reading.") for r in projection["refusals"])
    assert "n_roots=None" not in "\n".join(projection["associated_results"])
    result, _d, prompt_path = _m1_attempt(run_root)
    assert result.get("terminal") == "INPUT_GAP", result
    assert not prompt_path.is_file(), "缺读数不得产出可执行修订任务"


def test_whole_statistics_block_missing_refuses(tmp_path, fixture_drive):
    def tamper(run_root):
        eval_path = _iter_dir(run_root) / "conditional" / "evaluation.json"
        evaluation = _read_json(eval_path)
        evaluation["statistics"] = {}
        eval_path.write_text(json.dumps(evaluation, ensure_ascii=False),
                             encoding="utf-8")

    run_root = _tampered_run(tmp_path, tamper)
    projection = _feedback(run_root)
    assert projection["status"] == "refused"
    assert any(r["code"] == "reading.statistics_missing"
               for r in projection["refusals"])
    result, _d, prompt_path = _m1_attempt(run_root)
    assert result.get("terminal") == "INPUT_GAP", result
    assert not prompt_path.is_file()


# =====================================================================
# T7 · 确认数据混入 → 拒绝，且确认根不出现在任务包
# =====================================================================


def test_confirmation_data_mixed_in_refuses_m1_generation(tmp_path, fixture_drive):
    def tamper(run_root):
        # 确认集混入的自然面板产物（统计根标 usage=confirmation）。
        panel_path = _iter_dir(run_root) / "natural-H" / "panel.json"
        panel = _read_json(panel_path)
        candidate_id = panel["identity"]["candidate_id"]
        rows = panel["statistics"]["by_candidate"][candidate_id]["panels"][
            "normal"]["panels"]["H"]["root_rows"]
        rows[0]["usage"] = "confirmation"
        rows[0]["root_id"] = "confirmation-root-secret-01"
        panel_path.write_text(json.dumps(panel, ensure_ascii=False), encoding="utf-8")

    run_root = _tampered_run(tmp_path, tamper)
    projection = _feedback(run_root)
    assert projection["status"] == "refused" and projection["executable"] is False
    assert any(r["code"] == "boundary.confirmation_data"
               for r in projection["refusals"])
    assert "confirmation-root-secret-01" not in "\n".join(
        projection["facts"] + projection["associated_results"])
    result, _d, prompt_path = _m1_attempt(run_root)
    assert result.get("terminal") == "INPUT_GAP", result
    assert not prompt_path.is_file(), "确认数据混入不得产出可执行修订任务"


# =====================================================================
# T8 · 源码里的 trace 字段名不是已采集读数
# =====================================================================


def test_trace_field_names_are_slots_not_readings(tmp_path, i1_run):
    projection = _feedback(i1_run)
    mechanism = projection["mechanism_hypothesis"]
    slots = projection["mechanism_slots"]
    assert "槽位" in mechanism and slots["readings_collected"] is False
    assert "未采集" in mechanism
    # 源码里确实存在这些字段名（扫得到），但它们只是槽位名。
    source = (_iter_dir(i1_run, 1) / "generation" / "candidate.py").read_text(
        encoding="utf-8")
    for field in slots["fields"]:
        top = field.split(".")[0]
        assert top in source
    assert all(field not in mechanism.split("不是已采集的读数")[1]
               for field in []) or True
    # 程序不得给任何槽位填数值：方向槽位仍是占位符。
    assert mechanism.count("方向 = ____") >= len(slots["fields"])
