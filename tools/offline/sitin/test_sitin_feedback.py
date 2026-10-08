# -*- coding: utf-8 -*-
"""sitin_feedback（R6 三段反馈生成）测试：真实产物对拍 + 失败边界。

权威依据 CONTINUOUS-EVOLUTION-PLAN-2026-09-17.md §7 步 6 与 §11 交付物 4—6：
程序负责全部数字（事实 / 关联结果），模型只负责有字段引用的机制解释。因此这里
断言的核心是"数字与产物逐项一致"，而不是"文本好看"：

- 条件面板：双臂 U 区间、mean_delta、delta_bounds、unresolved_roots 与
  `eval/i1-conditional/evaluation.json` 相同；
- 自然面板：逐窗口差（8 行）与 `i1-natural-H|M/panel.json` 的 samples 相同，
  且窗口差均值与产物根级 mean_delta（H −0.25 / M 0.0）自洽；
- 声明混合值 = 产物 declared_mix.weights 加权（H 0.5 × −0.25 + M 0.5 × 0.0 = −0.125）；
- 机制假设段只有槽位：trace 字段名来自真实候选源码、方向占位符仍在，程序不代填；
- 候选绑定：同目录有 I1/M1 两套自然面板时，按产物登记的候选源码摘要挑对；
- 失败边界：无产物即拒绝（CLI 退出码 3），不产出半份反馈。

预算红线：全部只读既有证据文件，零模拟、零桌赛、零模型调用。
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
from pathlib import Path

import pytest

import sitin_feedback as sf

_HERE = Path(__file__).resolve().parent
E_REVAL = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r6-e-revalidation')
EVAL_DIR = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r6-e-revalidation/eval')

#: R6 E 重验里 I1 与 M1 两代候选的身份（读自各自产物，不手工转写）。
I1_CID = "2fc08dfce2fb50fe48d57a5ab5bdbeaf04e9177be731048d322ec5cdf99120c2"
M1_CID = "56ffb066459ad6cadbd886b36562d5bb7aff183514f60f1b6c99c594619b2b13"
I1_SOURCE_SHA256 = "b9b5c18d385c3658177796389c7c3d7aa734c9f8187fe20bfe78d922e275bb49"
M1_SOURCE_SHA256 = "44967e0cd124ea3767c8fbfad7b3f181d0867a3d83aedda788a3fb91b355a7a4"

pytestmark = pytest.mark.skipif(
    not EVAL_DIR.is_dir(), reason="R6 E 重验产物不在本检出")


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _generate(tmp_path: Path, *, candidate_cid: str,
              parent_cid=None, out_name: str = "feedback.md") -> str:
    """跑一次生成并返回 Markdown 文本。"""

    out = tmp_path / out_name
    path = sf.generate_feedback(EVAL_DIR, parent_cid=parent_cid,
                                candidate_cid=candidate_cid, out_path=out)
    assert path == out and out.is_file()
    return out.read_text(encoding="utf-8")


def _projection(eval_dir: Path, *, candidate_cid, parent_cid=None):
    inputs = sf.collect_feedback_inputs(Path(eval_dir), parent_cid=parent_cid,
                                        candidate_cid=candidate_cid)
    return sf.build_feedback_projection(inputs)


# ---------------------------------------------------------------------------
# 1. 三段结构与身份
# ---------------------------------------------------------------------------


def test_three_sections_and_identity_are_written(tmp_path):
    text = _generate(tmp_path, candidate_cid=I1_CID)
    for heading in (sf.HEADING_FACTS, sf.HEADING_RESULTS, sf.HEADING_MECHANISM):
        assert heading in text
    evaluation = _load(_project_file(_PROJECT_ROOT, EVAL_DIR / "i1-conditional" / "evaluation.json"))
    assert I1_CID in text
    assert evaluation["identity"]["evaluation_id"] in text
    # 产出写盘确定：同输入两次生成逐字节相同（无时钟、无随机源）。
    out2 = tmp_path / "again.md"
    sf.generate_feedback(EVAL_DIR, parent_cid=None, candidate_cid=I1_CID,
                         out_path=out2)
    assert out2.read_text(encoding="utf-8") == text


def test_fact_section_arms_match_conditional_artifact(tmp_path):
    text = _generate(tmp_path, candidate_cid=I1_CID)
    evaluation = _load(_project_file(_PROJECT_ROOT, EVAL_DIR / "i1-conditional" / "evaluation.json"))
    arms = evaluation["double_arm"]["arms"]
    for name in ("baseline", "candidate"):
        arm = arms[name]
        row = "| {0} | {1} | {2} | {3} | {4} | {5} |".format(
            name, arm["status"], sf._num(arm.get("u")), sf._num(arm.get("u_low")),
            sf._num(arm.get("u_high")), sf._flag(arm.get("unresolved")))
        assert row in text
    # 基线未分辨的 U 区间必须原样出现（[0.0, 1.0] + unresolved=true），
    # 且候选只报 0.0 —— 程序不替基线补一个点估计。
    assert "| baseline | complete | （产物未给该字段） | 0.0 | 1.0 | true |" in text
    assert "| candidate | complete | 0.0 | 0.0 | 0.0 | false |" in text
    assert str(evaluation["panel"]["generator"]) in text
    assert "前缀尝试：total=1，hit=1" in text


def test_window_differences_match_natural_samples(tmp_path):
    text = _generate(tmp_path, candidate_cid=I1_CID)
    rows = 0
    diffs_by_mix = {}
    for mix in ("H", "M"):
        panel = _load(_project_file(_PROJECT_ROOT, EVAL_DIR / ("i1-natural-%s" % mix) / "panel.json"))
        for sample in panel["samples"]:
            base = sample["arms"]["baseline"]["u"]
            cand = sample["arms"]["candidate"]["u"]
            diffs_by_mix.setdefault(mix, []).append(cand - base)
            rows += 1
            assert "| {0} | {1} | {2} |".format(
                mix, sample["source_root_id"], sample["focal_anchor_seat"]) in text
    assert rows == 8
    assert "窗口行数=8（程序计数" in text
    # H 根：仅座位 0 出现 −1.0，其余 0.0；窗口差均值 = 产物根级 mean_delta −0.25。
    assert diffs_by_mix["H"] == [-1.0, 0.0, 0.0, 0.0]
    assert sum(diffs_by_mix["H"]) / len(diffs_by_mix["H"]) == -0.25
    assert sum(diffs_by_mix["M"]) / len(diffs_by_mix["M"]) == 0.0
    assert "| -1.0 | complete |" in text


# ---------------------------------------------------------------------------
# 2. 关联结果段：根级差、区间、未分辨计数、声明混合
# ---------------------------------------------------------------------------


def test_result_section_reads_root_level_numbers_and_mix(tmp_path):
    text = _generate(tmp_path, candidate_cid=I1_CID)
    conditional = _load(_project_file(_PROJECT_ROOT, EVAL_DIR / "i1-conditional" / "evaluation.json"))
    block = conditional["statistics"]["by_candidate"][I1_CID]["panels"][
        "branch_open"]["panels"]["H"]
    assert "根级差 mean_delta={0}".format(block["mean_delta"]) in text
    bounds = block["delta_bounds"]
    assert "d_low={0} ~ d_high={1}".format(
        bounds["mean_delta_low"], bounds["mean_delta_high"]) in text
    assert "unresolved_roots={0}".format(bounds["unresolved_roots"]) in text
    assert bounds["unresolved_roots"] == 1 and block["mean_delta"] == -0.5
    # 自然面板 H/M 与声明混合（权重读自产物；−0.125 = 0.5×−0.25 + 0.5×0.0）
    assert "normal/H：n_roots=1" in text
    assert "根级差 mean_delta=-0.25" in text
    assert "根级差 mean_delta=0.0" in text
    assert 'declared_mix.weights={"H": 0.5, "M": 0.5}' in text
    assert "= -0.125" in text
    # 抽样区间缺失时显式标注，不写 0、不写"显著"。
    assert "interval_95=（产物未给该字段）" in text
    assert "未分辨" in text


def test_missing_statistics_are_reported_not_invented(tmp_path):
    """统计块缺该候选/情景时：如实说缺，不推算数字、不给混合值。"""

    sandbox = tmp_path / "eval"
    (sandbox / "i1-conditional").mkdir(parents=True)
    evaluation = json.loads(json.dumps(
        _load(_project_file(_PROJECT_ROOT, EVAL_DIR / "i1-conditional" / "evaluation.json"))))
    evaluation["statistics"]["by_candidate"] = {}
    (sandbox / "i1-conditional" / "evaluation.json").write_text(
        json.dumps(evaluation, ensure_ascii=False), encoding="utf-8")
    panel = json.loads(json.dumps(_load(_project_file(_PROJECT_ROOT, EVAL_DIR / "i1-natural-H" / "panel.json"))))
    panel["statistics"]["by_candidate"] = {}
    (sandbox / "i1-natural-H").mkdir(parents=True)
    (sandbox / "i1-natural-H" / "panel.json").write_text(
        json.dumps(panel, ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "fb.md"
    sf.generate_feedback(sandbox, parent_cid=None, candidate_cid=I1_CID,
                         out_path=out)
    text = out.read_text(encoding="utf-8")
    assert "没有该候选的 `branch_open`/`H` 面板块" in text
    assert "产物里没有该候选的 normal/H 面板块（不推算数字）" in text
    assert "= -0.125" not in text
    assert "声明混合值：**不可计算**" in text
    # P9 增强：数字缺失不只是"如实说缺"——还要判定**不可执行**（不得据此发修订任务）。
    projection = _projection(sandbox, candidate_cid=I1_CID)
    assert projection["status"] == sf.PROJECTION_REFUSED
    assert projection["executable"] is False
    codes = {item["code"] for item in projection["refusals"]}
    assert sf.REFUSAL_READING_STATISTICS_MISSING in codes
    assert "n_roots=None" not in "\n".join(projection["associated_results"])


# ---------------------------------------------------------------------------
# 3. 机制假设段：只有槽位，字段来自真实候选源码
# ---------------------------------------------------------------------------


def test_mechanism_section_lists_real_trace_fields_only(tmp_path):
    text = _generate(tmp_path, candidate_cid=I1_CID)
    mechanism = text.split(sf.HEADING_MECHANISM)[1]
    assert "模型解释，须引用具体字段" in mechanism
    fields = sf.trace_field_slots(
        (_project_file(_PROJECT_ROOT, E_REVAL / "gen" / "i1" / "attempts" / "i1-a828da7533db"
         / "candidate.py")).read_text(encoding="utf-8"))
    assert fields[:3] == ["mech", "parts.prog", "parts.settle"]
    assert "parts.width" in fields and "basis" in fields
    # 父路径被更细路径覆盖时不再单列。
    assert "parts" not in fields
    for field in fields:
        assert "- `{0}`".format(field) in mechanism
    assert mechanism.count("方向 = ____") >= len(fields)
    # 程序不代填机制内容（槽位外没有现成结论句）。
    assert "差异可能来自" not in mechanism
    assert "预计提升" not in mechanism


def test_trace_field_slots_handle_f_strings_and_comments():
    source = (
        "# trace = { 'commented': 1 }\n"
        "def score(view):\n"
        "    trace = {\n"
        "        'mech': f'{tag}|{kind}',\n"
        "        'parts': {'a': 1.0, 'b': {'c': 2.0}},\n"
        "        'flag': True,\n"
        "    }\n"
        "    return {'status': 'SCORED', 'entries': [\n"
        "        {'trace': trace}]}\n"
    )
    assert sf.trace_field_slots(source) == ["mech", "parts.a", "parts.b", "flag"]


# ---------------------------------------------------------------------------
# 4. 候选绑定与失败边界
# ---------------------------------------------------------------------------


def test_m1_feedback_binds_parent_and_m1_source(tmp_path):
    text = _generate(tmp_path, candidate_cid=M1_CID, parent_cid=I1_CID)
    # 绑定到 M1 的源码摘要，而不是 I1 的（同目录两份自然面板都在）。
    assert M1_SOURCE_SHA256[:16] in text
    assert I1_SOURCE_SHA256[:16] not in text
    assert I1_CID in text  # 父代身份出现在槽位里
    assert "candidate_source_sha256={0} 绑定".format(M1_SOURCE_SHA256[:16]) in text
    mechanism = text.split(sf.HEADING_MECHANISM)[1]
    assert mechanism.count("方向 = ____") > 0


def test_split_samples_jsonl_layout_is_supported(tmp_path):
    """兼容布局：没有 panel.json，只有 samples.jsonl + natural-statistics.json。

    绑定语义（P9 收紧）：只有**正面命中身份**才绑定——给出该面板自报的
    candidate_id 时按它绑定并报数字；给不出身份时**拒绝绑定**，未绑定面板的数字
    一律不进反馈（旧行为是"绑不上就退回全部面板"，等于把别的候选的数字当本次事实）。
    """

    panel = _load(_project_file(_PROJECT_ROOT, EVAL_DIR / "i1-natural-H" / "panel.json"))
    reporter_cid = panel["samples"][0]["candidate_id"]
    sandbox = tmp_path / "eval"
    target = sandbox / "i1-natural-H"
    target.mkdir(parents=True)
    with (target / "samples.jsonl").open("w", encoding="utf-8") as handle:
        for record in panel["samples"]:
            slim = {key: value for key, value in record.items()
                    if key != "raw_arms"}
            handle.write(json.dumps(slim, ensure_ascii=False) + "\n")
    (target / "natural-statistics.json").write_text(
        json.dumps(panel["statistics"], ensure_ascii=False), encoding="utf-8")
    # ① 正面命中（面板自报 candidate_id）→ 绑定并报数字。
    out = tmp_path / "fb.md"
    sf.generate_feedback(sandbox, parent_cid=None, candidate_cid=reporter_cid,
                         out_path=out)
    text = out.read_text(encoding="utf-8")
    assert "natural-statistics.json" in text
    assert "根级差 mean_delta=-0.25" in text
    assert "窗口行数=4" in text
    assert "按面板自报 candidate_id 绑定" in text
    # ② 身份不可核验 → 拒绝绑定，数字不混入。
    unbound = tmp_path / "unbound.md"
    sf.generate_feedback(sandbox, parent_cid=None, candidate_cid=None,
                         out_path=unbound)
    text = unbound.read_text(encoding="utf-8")
    assert "未能把自然面板绑定到本次候选" in text
    assert "根级差 mean_delta=-0.25" not in text
    projection = _projection(sandbox, candidate_cid=None)
    assert projection["status"] == sf.PROJECTION_REFUSED
    assert sf.REFUSAL_IDENTITY_PANELS in {i["code"] for i in projection["refusals"]}
    for sample in panel["samples"]:
        assert sample["source_root_id"] not in "\n".join(
            projection["facts"] + projection["associated_results"])


def test_missing_artifacts_fail_closed(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(sf.FeedbackInputError, match="没有任何可读产物"):
        sf.generate_feedback(empty, parent_cid=None, candidate_cid=I1_CID,
                             out_path=tmp_path / "x.md")
    with pytest.raises(sf.FeedbackInputError, match="评估目录不存在"):
        sf.generate_feedback(tmp_path / "nope", parent_cid=None,
                             candidate_cid=I1_CID, out_path=tmp_path / "x.md")
    assert not (tmp_path / "x.md").exists()
    code = sf.main(["generate", "--eval-dir", str(empty), "--out",
                    str(tmp_path / "y.md")])
    assert code == 3
    assert not (tmp_path / "y.md").exists()


def test_cli_generate_writes_document(tmp_path):
    out = tmp_path / "cli.md"
    code = sf.main(["generate", "--eval-dir", str(EVAL_DIR),
                    "--candidate-cid", I1_CID, "--out", str(out)])
    assert code == 0
    assert sf.HEADING_FACTS in out.read_text(encoding="utf-8")

# ---------------------------------------------------------------------------
# 5. P9c：window.actions 的证据指针必须指向**实际取值来源**（P9b 采集的臂动作）
# ---------------------------------------------------------------------------


def _panel_fixture(sandbox: Path, *, strip_readings: bool = False) -> dict:
    """在 sandbox 里造一份**真实跑批**的机会面板产物（夹具路由，零真实桌赛）。

    `sandbox/evaluation.json`（条件评估身份）+ `sandbox/panel-branch_open/panel.json`
    （P9b 已采集 `snapshot.window_actions` 与逐臂 `focal_action_at_cut`）。
    `strip_readings=True` 时剥掉读数，用于验证「未采集」时的指针回退与 input gap。
    """

    import sitin_opportunities as so

    panel = so.build_panel(
        prefix_source="scripted_fixture", predicate_id="branch_open", focal_seat=0,
        opponent_scenario="H", root_label="p9c", out_dir=sandbox / "panel-branch_open",
        ruleset_version=so.DEFAULT_RULESET_VERSION, base_score=1, you_cai_bi_kao=False,
        attempts_cap=so.PREFIX_ATTEMPT_CAP, panel_seed=20260916)
    if strip_readings:
        for scenario in panel["scenarios"]:
            snapshot = scenario.get("snapshot") or {}
            snapshot.pop("window_actions", None)
            for arm in ((scenario.get("double_arm") or {}).get("arms") or {}).values():
                arm.pop("focal_action_at_cut", None)
                arm.pop("focal_action_at_cut_status", None)
                arm.pop("focal_action_at_cut_reason", None)
        (sandbox / "panel-branch_open" / "panel.json").write_text(
            json.dumps(panel, ensure_ascii=False), encoding="utf-8")
    (sandbox / "evaluation.json").write_text(
        json.dumps(_load(_project_file(_PROJECT_ROOT, EVAL_DIR / "i1-conditional" / "evaluation.json")),
                   ensure_ascii=False), encoding="utf-8")
    return panel


def _evidence_value(evidence):
    """指针 → 产物路径 → JSON 指针 → 原值：四段可追（任一段对不上即断言失败）。"""

    path = Path(evidence["artifact"])
    assert path.is_file(), path
    node = json.loads(path.read_text(encoding="utf-8"))
    for part in str(evidence["locator"]).split("/")[1:]:
        node = node[int(part)] if isinstance(node, list) else node[part]
    assert node == evidence["value"], (evidence["locator"], node)
    return node


def _arm_actions_from_value(value):
    """从证据取回的原值里读出「臂 → 动作键」；不是臂动作读数来源就返回 None。"""

    arms = (value or {}).get("arms") if isinstance(value, dict) else None
    if not isinstance(arms, dict):
        return None
    return {str(name): (entry or {}).get("action_key")
            for name, entry in arms.items() if isinstance(entry, dict)}


def _assert_window_actions_traceable(item, expected):
    """条目文本所示动作 ⇔ 主证据指针取回的原值（四段可追 + 内容一致）。"""

    for name, action in expected.items():
        assert "action_key=`{0}`".format(action) in item["text"], name
    primary = _evidence_value(item["evidence"])
    actions = _arm_actions_from_value(primary)
    assert actions is not None, "主证据不是臂动作读数的来源（指针未指向实际取值来源）"
    for name, action in expected.items():
        assert actions.get(name) == action, (name, actions)
    # 逐臂读数也能独立定位（P9b 的第二个登记位置）。
    per_arm = {evidence["locator"]: evidence for evidence in item["extra_evidences"]}
    for name, action in expected.items():
        locator = "/scenarios/0/double_arm/arms/{0}/focal_action_at_cut".format(name)
        assert locator in per_arm, sorted(per_arm)
        assert _evidence_value(per_arm[locator])["action_key"] == action


def _window_actions_item(tmp_path: Path, *, strip_readings: bool = False):
    sandbox = tmp_path / "eval"
    sandbox.mkdir(parents=True, exist_ok=True)
    panel = _panel_fixture(sandbox, strip_readings=strip_readings)
    projection = _projection(sandbox, candidate_cid=I1_CID)
    item = next((item for item in projection["facts_items"]
                 if item["key"] == "window.actions"), None)
    assert item is not None, [i["key"] for i in projection["facts_items"]]
    readings = (((panel["scenarios"][0].get("snapshot") or {}).get("window_actions")
                 or {}).get("arms") or {})
    expected = {name: entry.get("action_key") for name, entry in readings.items()
                if entry.get("action_key")}
    return projection, item, expected, panel


def _make_legacy_pointer_reading(real):
    """变异实现：**读数照旧采集**，只把证据指针退回旧字段（legal_action_prefix）。

    这正是被修的缺陷形态：条目文本说的来源与指针指的位置不一致——文本里的两臂动作
    仍照旧写出，但指针指向的不是那个读数，于是"指针 → 原值"取不到文本所示动作。
    """

    def _mutated(path, document, index):
        reading = real(path, document, index)
        if reading["collected"]:
            reading["evidences"] = sf._evs(
                path, document, ("scenarios", index, "snapshot", "legal_action_prefix"))
        return reading

    return _mutated


def test_window_actions_pointer_points_at_real_reading_source(tmp_path):
    """P9b 读数已采集：window.actions 的主证据必须指向 snapshot.window_actions。"""

    projection, item, expected, panel = _window_actions_item(tmp_path)
    assert expected == {"baseline": "pass", "candidate": "peng:5w"}
    # ① 主指针 = 聚合读数；② 逐臂指针紧随；③ 旧字段指针只作为前缀动作的来源排在后面。
    assert item["evidence"]["locator"] == "/scenarios/0/snapshot/window_actions"
    locators = [item["evidence"]["locator"]] + [
        evidence["locator"] for evidence in item["extra_evidences"]]
    assert locators.index("/scenarios/0/double_arm/arms/baseline/focal_action_at_cut") < \
        locators.index("/scenarios/0/snapshot/legal_action_prefix")
    assert "/scenarios/0/snapshot/observation_summary" in locators
    # 条目文本写明的来源字段 = 指针指的位置（文本与指针一致）。
    for label in ("snapshot.window_actions",
                  "double_arm.arms.baseline.focal_action_at_cut",
                  "double_arm.arms.candidate.focal_action_at_cut"):
        assert label in item["text"]
    # 四段可追 + 原值里的动作与文本一致。
    _assert_window_actions_traceable(item, expected)
    # R9/A2+A3 根身份修订：条目里的 root_id 不再由调用方的 root_label 拼出，而是
    # **统一根描述符**（生成器 × 子场景 × 对手情景 × 实际种子 × 根序号）。这里逐项
    # 核对三处同源，且身份本身要逐段体现描述符维度——不是"非空字符串"就算过：
    #   ① 反馈条目（sitin_feedback 取 scenarios[i].source_root_id，见该模块取值口径）；
    #   ② 机会面板该情景的 source_root_id / snapshot.source_root_id（取值直接来源）；
    #   ③ 面板 snapshot.window_actions 的聚合与逐臂读数 root_id（读数身份绑定）。
    scenario = panel["scenarios"][0]
    snapshot = scenario["snapshot"]
    readings = snapshot["window_actions"]
    panel_root_id = str(scenario["source_root_id"])
    assert panel_root_id, scenario["source_root_id"]
    assert panel_root_id == str(snapshot["source_root_id"])
    assert panel_root_id == str(readings["root_id"]), (panel_root_id, readings["root_id"])
    assert item["root_id"] == panel_root_id, (item["root_id"], panel_root_id)
    assert set(readings["arms"]) == {"baseline", "candidate"}, readings["arms"]
    for name, entry in readings["arms"].items():
        assert str(entry.get("root_id")) == item["root_id"], (name, entry)
    # 结构校验：身份逐段 =（子场景 × 生成器 × 对手情景 × 实际种子 × 根序号）。
    matched = re.fullmatch(
        r"av-eval-(?P<sub>[^:]+):(?P=sub):(?P<generator>[^:]+):(?P<mix>[^:]+):"
        r"s(?P<seed>[0-9]+):root(?P<index>[0-9]{3})", item["root_id"])
    assert matched is not None, item["root_id"]
    assert matched.group("sub") == scenario["sub_scenario"] == "branch_open", item["root_id"]
    assert matched.group("mix") == snapshot["root_descriptor"]["opponent_mix"] == "H"
    assert int(matched.group("seed")) == int(snapshot["root_descriptor"]["panel_seed"])
    assert int(matched.group("index")) == int(snapshot["root_descriptor"]["root_index"])
    assert matched.group("generator") == snapshot["root_descriptor"]["generator"]
    assert item["root_id"] == snapshot["root_descriptor"]["root_id"]
    # 判别力复核：旧身份字面量必须**不再**成立——若它仍相等，说明根身份没有统一到
    # 描述符（A2/A3 修复退化），这条断言就失去判别力。
    assert item["root_id"] != "p9c:branch_open:root002", item["root_id"]
    assert item["window"]["trigger_seq"] == 10
    # 缺口消失：读数已采集，不再报 arm_actions_not_collected。
    codes = {gap["code"] for gap in projection["gaps"]}
    assert "window.arm_actions_not_collected" not in codes


def test_window_actions_pointer_mutation_back_to_legacy_turns_red(tmp_path,
                                                                  monkeypatch):
    """定向变异：把取值来源退回旧字段（legal_action_prefix）→ 追溯断言必须转红。"""

    _projection_green, item, expected, _panel_green = _window_actions_item(
        tmp_path / "green")
    _assert_window_actions_traceable(item, expected)  # 先证绿

    real = sf._window_action_reading
    monkeypatch.setattr(sf, "_window_action_reading",
                        _make_legacy_pointer_reading(real), raising=True)
    _projection2, item2, expected2, _panel2 = _window_actions_item(tmp_path / "mutated")
    # 变异后：文本仍逐字写出两臂动作（读数没被撤），但主指针退回旧字段。
    assert item2["evidence"]["locator"] == "/scenarios/0/snapshot/legal_action_prefix"
    for name, action in expected2.items():
        assert "action_key=`{0}`".format(action) in item2["text"], name
    with pytest.raises(AssertionError, match="主证据不是臂动作读数的来源"):
        _assert_window_actions_traceable(item2, expected2)


def test_window_actions_absent_falls_back_and_keeps_refusals(tmp_path):
    """未采集（旧产物）：指针回退到旧字段、如实记 input gap，且判定不被放宽。"""

    kept_projection, _item, _expected, _kept_panel = _window_actions_item(
        tmp_path / "with")
    projection, item, expected, _panel_without = _window_actions_item(
        tmp_path / "without", strip_readings=True)
    assert expected == {}
    assert item["evidence"]["locator"] == "/scenarios/0/snapshot/legal_action_prefix"
    assert "本批产物未采集该读数" in item["text"]
    codes = {gap["code"] for gap in projection["gaps"]}
    assert "window.arm_actions_not_collected" in codes
    # 不放宽：有无读数都不改变拒绝码集合（读数不参与任何 fail-closed 判定）。
    assert [r["code"] for r in projection["refusals"]] == \
        [r["code"] for r in kept_projection["refusals"]]

