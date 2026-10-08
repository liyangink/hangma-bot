"""包 A（R9 P25 · 复审 C1）：统一行为定义的三处同口径 + 控制用例 + 红对照。

复审 C1·P1：作者守卫与自查把**任一分值改变**叫行为变化，准入实际要求**首选动作有可
观察差异**（保序平移/正比例缩放不获信用）；题面还写着「只改分值不改次序：有行为差异
=True」。本文件把三处口径钉在一起：

  ① 生产排序      = batch_to_ranked_candidates（分数降序、同分按 action_key 升序、
                    原始分数不先舍入）——唯一实现来源；
  ② 作者自查      = sitin_generate.behavior_change_report（四项读数 + 唯一判定）；
  ③ 准入签名      = sitin_model_admission.preference_signature / revision_behavior_delta
                    （本文件只读导入，不修改判分器）。

控制用例（逐条断言，见 c1-behavior-controls.json）：平移、正比例缩放、只改非首选次序、
只改说明 = **无行为差异**；平分破除（首选改选）与真实首选改变 = **有行为差异**。
最后一条是红对照：把自查换成旧定义（任一分值变化）⇒ 同一份「自查 vs 正式判分结论必须
一致」的断言**必须失败**；换成新定义则通过。

运行（仓库根）：
    .venv/bin/python -m pytest review/llm-guided-heuristic-route-2026-09-15/tools/test_sitin_generate_behavior_definition.py -q
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

import importlib.util
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

_spec = importlib.util.spec_from_file_location("sitin_generate", _project_file(_PROJECT_ROOT, _HERE / "sitin_generate.py"))
gen = importlib.util.module_from_spec(_spec)
sys.modules["sitin_generate"] = gen
assert _spec.loader is not None
_spec.loader.exec_module(gen)


def _load_sibling(name: str):
    spec = importlib.util.spec_from_file_location(name, _project_file(_PROJECT_ROOT, _HERE / (name + ".py")))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


adm = _load_sibling("sitin_model_admission")

from hangma_bot.policy.action_value import (  # noqa: E402
    ActionScore, ActionView, ScoreBatch, ScoringView, batch_to_ranked_candidates,
)
from hangma_bot.policy import action_value_executor as av_exec  # noqa: E402
from hangma_bot.policy import action_value_seeds as av_seeds  # noqa: E402

#: 声明视图：与准入判分器同一注册表解析（未注册名字会具名失败，不静默丢弃）。
VIEWS = ["sample", "route_combo", "unknown_missing", "max_input",
         "fam_discard", "fam_pass"]


# ----------------------------------------------------------------- 控制用例（表）

PARENT = (("discard:1w", 5.0), ("discard:2b", -3.0))

#: (标签, 父代, 子代, 期望 changed, 期望 verdict, 期望的 ①②③④ 读数要点)
CONTROLS = (
    ("只改说明（逐项相同）", PARENT, PARENT, False, "EQUIVALENT",
     {"value_diff_count": 0, "order_changed": False, "top_changed": False}),
    ("保序平移（全体 +100）", PARENT,
     (("discard:1w", 105.0), ("discard:2b", 97.0)), False, "EQUIVALENT",
     {"value_diff_count": 2, "order_changed": False, "top_changed": False}),
    ("正比例缩放（全体 ×3）", PARENT,
     (("discard:1w", 15.0), ("discard:2b", -9.0)), False, "EQUIVALENT",
     {"value_diff_count": 2, "order_changed": False, "top_changed": False}),
    ("只改非首选次序", (("discard:9b", 5.0), ("discard:1w", 1.0), ("discard:2b", 2.0)),
     (("discard:9b", 5.0), ("discard:1w", 3.0), ("discard:2b", 1.0)), False,
     "EQUIVALENT", {"value_diff_count": 2, "order_changed": True, "top_changed": False}),
    ("平分破除（并列 → 真首选改选）", (("discard:1w", 5.0), ("discard:2b", 5.0)),
     (("discard:1w", 5.0), ("discard:2b", 6.0)), True, "REVISION_OBSERVED",
     {"value_diff_count": 1, "order_changed": True, "top_changed": True}),
    ("真实首选改变（次序反转）", PARENT,
     (("discard:1w", -3.0), ("discard:2b", 5.0)), True, "REVISION_OBSERVED",
     {"value_diff_count": 2, "order_changed": True, "top_changed": True}),
)


@pytest.mark.parametrize("label,parent,child,changed,verdict,readings", CONTROLS,
                         ids=[item[0] for item in CONTROLS])
def test_control_cases(label, parent, child, changed, verdict, readings):
    """C1 控制用例逐条：只有**首选动作改变**才算行为差异。"""

    report = gen.behavior_change_report(parent, child)
    assert report["changed"] is changed, (label, report)
    assert report["verdict"] == verdict, (label, report)
    for key, value in readings.items():
        assert report[key] is value, (label, key, report[key], value)
    assert report["order_note"] == gen.BEHAVIOR_ORDER_NOTE


def test_translation_and_scaling_are_not_behavior_change():
    """复审点名的两条保序变换：分值变了，行为没变（旧定义在这里报假阳性）。"""

    for label, delta in (("平移", 100.0), ("缩放", 3.0)):
        if label == "平移":
            child = tuple((key, score + delta) for key, score in PARENT)
        else:
            child = tuple((key, score * delta) for key, score in PARENT)
        report = gen.behavior_change_report(PARENT, child)
        assert report["value_diff_count"] == len(PARENT), label
        assert report["changed"] is False, label
        assert report["top_changed"] is False, label
        assert "保序" in report["equivalence_reason"], label


def test_abstain_side_is_not_a_selection_difference():
    """④ 弃权/未知掩码：一侧无偏好证据不算选择差异，也不兑换修订信用。"""

    parent_abstain = gen.behavior_change_report(None, PARENT)
    assert parent_abstain["verdict"] == "PARENT_MATERIAL_INCOMPATIBLE"
    assert parent_abstain["changed"] is False
    assert parent_abstain["abstain_mask"] == {"parent": True, "child": False}
    child_abstain = gen.behavior_change_report(PARENT, ())
    assert child_abstain["verdict"] == "CHILD_NO_BEHAVIOR_EVIDENCE"
    assert child_abstain["changed"] is False
    assert child_abstain["child_top"] is None


def test_non_finite_scores_are_fail_closed():
    """自查不得用非法读数拼报告：NaN/Inf/布尔冒充数一律 ValueError。"""

    for bad in ((("discard:1w", float("nan")),), (("discard:1w", float("inf")),),
                (("discard:1w", True),)):
        with pytest.raises(ValueError):
            gen.behavior_change_report(bad, PARENT)


# --------------------------------------------------- 三处同口径（生产/自查/准入）

def _real_views():
    return [adm.resolve_view_factory(name)() for name in VIEWS]


def _executor(source: str):
    return av_exec.ActionValueExecutor(source, name="<pkg-a-behavior>")


def _entries(batch: ScoreBatch):
    return tuple((entry.action_key, entry.score) for entry in batch.entries)


def test_verdict_enum_is_identical_to_the_admission_grader():
    """枚举逐字同值：作者自查与准入判分器不得各写一套。"""

    assert tuple(gen.BEHAVIOR_VERDICTS) == tuple(adm.REVISION_VERDICTS)
    assert gen.BEHAVIOR_VERDICT_OBSERVED == adm.REVISION_OBSERVED
    assert gen.BEHAVIOR_VERDICT_EQUIVALENT == adm.REVISION_EQUIVALENT
    assert gen.BEHAVIOR_VERDICT_PARENT_INCOMPATIBLE == adm.REVISION_PARENT_INCOMPATIBLE
    assert gen.BEHAVIOR_VERDICT_CHILD_NO_EVIDENCE == adm.REVISION_CHILD_NO_EVIDENCE


def test_author_preference_equals_the_production_sorting():
    """①=②：作者自查的首选动作必须与生产排序 batch_to_ranked_candidates 逐窗一致。"""

    view = adm.resolve_view_factory("max_input")()
    by_key = {item.action_key: item for item in view.actions}
    entries = tuple(
        ActionScore(action_key=key, score=score, trace={})
        for key, score in (("discard:1w", 1.0), ("discard:2w", 1.0),
                           ("chi:1w,2w,3w", -0.5), ("pass", -0.5)))
    batch = ScoreBatch(status="SCORED", entries=entries)
    ranked = batch_to_ranked_candidates(batch, view.actions)
    selfcheck = gen.preferred_action_key(_entries(batch))
    assert selfcheck == ranked[0].action_key
    # 平分按 action_key 升序：两个 1.0 里取键更小者；两个 -0.5 里同样。
    assert ranked[0].action_key == "discard:1w"
    assert [item.rank for item in ranked] == [1, 2, 3, 4]
    # 原始分数不先舍入：1e-10 级差异必须仍然决定首选（旧实现 round(score, 9) 会塌成平局）
    tiny = ScoreBatch(status="SCORED", entries=(
        ActionScore(action_key="pass", score=0.0, trace={}),
        ActionScore(action_key="discard:1w", score=2e-10, trace={})))
    ranked_tiny = batch_to_ranked_candidates(tiny, view.actions)
    assert ranked_tiny[0].action_key == "discard:1w"
    assert gen.preferred_action_key(_entries(tiny)) == "discard:1w"


def test_author_preference_ignores_view_action_order():
    """自查的输入是 [(键, 分)] 局部表：入参顺序不得影响首选（按生产排序归并）。"""

    forward = (("discard:1w", 5.0), ("discard:2b", -3.0))
    backward = (("discard:2b", -3.0), ("discard:1w", 5.0))
    assert gen.preferred_action_key(forward) == gen.preferred_action_key(backward)
    assert gen.behavior_change_report(forward, backward)["changed"] is False


# ------------------------------------- 端到端：真实代码 + 正式判分器同一结论

#: 控制用候选源码模板（受限子集内：无 import / 无 while / 无递归）。
CONTROL_SOURCE = '''"""包 A 行为定义控制用评分器（只用分支事实）。"""

SCALE = 1.0
OFFSET = 0.0
BONUS_KEY = ""


def score_actions(view):
    """按分支向听与支撑计数给分；SCALE/OFFSET/BONUS_KEY 由控制用例改写。"""
    entries = []
    for action in view["actions"]:
        score = 0.0
        branches = action.get("followup_branches")
        if branches is not None:
            for branch in branches:
                shanten = branch.get("combined_shanten")
                if shanten is None or shanten is True or shanten is False:
                    continue
                score = score - 3.0 * shanten
                support = branch.get("support_remaining")
                if support is not None and support is not True and support is not False:
                    score = score + 0.5 * support
        if action["action_key"] == BONUS_KEY:
            score = score + 1000.0
        entries.append({"action_key": action["action_key"],
                        "score": score * SCALE + OFFSET,
                        "trace": {"basis": "control"}})
    return {"status": "SCORED", "entries": entries}
'''


def _variant(*, scale=None, offset=None, bonus=None):
    source = CONTROL_SOURCE
    if scale is not None:
        source = source.replace("SCALE = 1.0", "SCALE = {0}".format(scale))
    if offset is not None:
        source = source.replace("OFFSET = 0.0", "OFFSET = {0}".format(offset))
    if bonus is not None:
        source = source.replace('BONUS_KEY = ""',
                                'BONUS_KEY = "{0}"'.format(bonus), 1)
    return source


def _selfcheck_verdict(parent_code: str, child_code: str):
    """作者自查（逐窗）：按生产排序取首选，四项读数合并成一份报告。"""

    parent_exec = _executor(parent_code)
    child_exec = _executor(child_code)
    reports = {}
    for name in VIEWS:
        view = adm.resolve_view_factory(name)()
        parent_entries = _entries(parent_exec.score(view))
        child_entries = _entries(child_exec.score(view))
        reports[name] = gen.behavior_change_report(parent_entries, child_entries)
    observable = [name for name, report in reports.items()
                  if report["parent_observable"] and report["child_observable"]]
    changed_views = [name for name, report in reports.items()
                     if report["changed"]]
    parent_any = any(report["parent_observable"] for report in reports.values())
    child_any = any(report["child_observable"] for report in reports.values())
    if not parent_any:
        verdict = gen.BEHAVIOR_VERDICT_PARENT_INCOMPATIBLE
    elif not child_any:
        verdict = gen.BEHAVIOR_VERDICT_CHILD_NO_EVIDENCE
    elif changed_views:
        verdict = gen.BEHAVIOR_VERDICT_OBSERVED
    else:
        verdict = gen.BEHAVIOR_VERDICT_EQUIVALENT
    return {"verdict": verdict, "changed": verdict == gen.BEHAVIOR_VERDICT_OBSERVED,
            "changed_views": changed_views, "observable_views": observable,
            "views": reports}


def _assert_same_conclusion(label, selfcheck, official):
    """**一致性闸门**：作者自查与正式判分对同一份代码必须同结论，否则红。"""

    official_observed = official["verdict"] == adm.REVISION_OBSERVED
    assert selfcheck["changed"] == official_observed, (
        "{0}: 自查 changed={1}（{2}）与正式判分 {3} 结论相反".format(
            label, selfcheck["changed"], selfcheck["verdict"], official["verdict"]),
        "changed_views", selfcheck["changed_views"],
        "official_changed_views", official["decision_changed_views"])


def _official(parent_code: str, child_code: str):
    return adm.revision_behavior_delta(child_code, parent_code, VIEWS)


def test_selfcheck_and_official_grader_agree_on_translation():
    """真实代码：保序平移（SCALE/OFFSET 改写）两侧都判**无**行为差异。"""

    parent = _variant()
    for label, child in (("平移 +100", _variant(offset=100.0)),
                         ("缩放 ×3", _variant(scale=3.0))):
        av_exec.static_check(child)          # 变体仍是合法受限子集候选
        selfcheck = _selfcheck_verdict(parent, child)
        official = _official(parent, child)
        assert selfcheck["changed"] is False, (label, selfcheck["changed_views"])
        assert official["verdict"] == adm.REVISION_EQUIVALENT, (label, official)
        _assert_same_conclusion(label, selfcheck, official)
        # 分数向量**确实**变了：证明这不是「没跑起来」导致的假等价。
        diff = adm.behavior_signature(parent, VIEWS)
        translated = adm.behavior_signature(child, VIEWS)
        assert diff != translated


def test_selfcheck_and_official_grader_agree_on_real_top_change():
    """真实代码：给 pass 加偏置改变首选 ⇒ 两侧都判**有**行为差异。"""

    parent = _variant()
    child = _variant(bonus="pass")
    av_exec.static_check(child)
    selfcheck = _selfcheck_verdict(parent, child)
    official = _official(parent, child)
    assert selfcheck["changed"] is True, selfcheck["views"]
    assert official["verdict"] == adm.REVISION_OBSERVED, official
    assert official["decision_changed_views"], official
    _assert_same_conclusion("pass 偏置", selfcheck, official)


def test_selfcheck_and_official_grader_agree_on_identity():
    """真实种子代码：与自身比较 = 等价（两侧都不得报行为差异）。"""

    seed = av_seeds.build_action_value_policy("efficiency_seed").source
    selfcheck = _selfcheck_verdict(seed, seed)
    official = _official(seed, seed)
    assert selfcheck["changed"] is False
    assert official["verdict"] == adm.REVISION_EQUIVALENT
    _assert_same_conclusion("真实种子自比", selfcheck, official)


#: 新定义的原始实现（monkeypatch 期间仍要能取到，避免自递归）。
_ORIGINAL_BEHAVIOR_REPORT = gen.behavior_change_report


def _old_definition_report(parent_entries, child_entries):
    """旧定义（复审 C1 要废除的那个）：**任一分值改变**即行为变化。"""

    report = _ORIGINAL_BEHAVIOR_REPORT(parent_entries, child_entries)
    report["changed"] = report["value_diff_count"] > 0
    report["verdict"] = (gen.BEHAVIOR_VERDICT_OBSERVED if report["changed"]
                         else gen.BEHAVIOR_VERDICT_EQUIVALENT)
    return report


def test_old_value_diff_definition_would_be_red(monkeypatch):
    """**红对照**：自查若退回旧定义，同一份一致性断言必须失败（测试会红）。"""

    parent = _variant()
    child = _variant(offset=100.0)
    official = _official(parent, child)
    assert official["verdict"] == adm.REVISION_EQUIVALENT

    monkeypatch.setattr(gen, "behavior_change_report", _old_definition_report)
    old_selfcheck = _selfcheck_verdict(parent, child)
    assert old_selfcheck["changed"] is True, "旧定义应把平移报成行为变化"
    with pytest.raises(AssertionError):
        _assert_same_conclusion("旧定义 vs 正式判分", old_selfcheck, official)

    monkeypatch.undo()
    new_selfcheck = _selfcheck_verdict(parent, child)
    assert new_selfcheck["changed"] is False
    _assert_same_conclusion("新定义 vs 正式判分", new_selfcheck, official)


def test_guard_clauses_state_the_unified_definition():
    """题面条款必须与代码同一口径（只改题面文字、留下假阳性自查不算修好）。"""

    clauses = "\n".join(gen.author_guard_clauses())
    assert "首选动作" in clauses
    assert "任一分值改变都不是行为变化" in clauses
    assert "保序平移" in clauses and "正比例缩放" in clauses
    assert "只改非首选次序" in clauses
    assert "平分破除按生产排序" in clauses
    assert "一侧弃权不算选择差异" in clauses
    assert "只改分值不改次序：有行为差异=True" not in clauses
    payload = gen.render_action_value_task_contract(
        objective_summary="x", panel_boundary="y", prompt_role="z")
    guard = payload["author_guard_semantics"]
    assert guard["schema"] == "sitin-author-guard/2"
    assert guard["behavior_verdicts"] == list(gen.BEHAVIOR_VERDICTS)
    text = gen.build_action_value_prompt(gen.OPERATOR_I1, payload).text
    for clause in gen.author_guard_clauses():
        assert clause in text
    assert "首选动作" in text

