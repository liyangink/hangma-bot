"""R9 接手前的测量回归：历史答卷只能用于诊断，不能伪造新的准入信用。"""
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

import argparse
import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
DEV = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-dev-cards')
GLM = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-dev-cards/glm')
SLIM = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-dev-cards/slim')
HEADLESS = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-headless')

if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import sitin_model_admission as admission  # noqa: E402


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


criterion = _load_module("sitin_takeover_criterion", _project_file(_PROJECT_ROOT, DEV / "criterion.py"))
repair_prompt = _load_module("sitin_takeover_repair_prompt", _project_file(_PROJECT_ROOT, HEADLESS / "repair_prompt.py"))


def _task(package: Path, task_id: str) -> dict:
    return json.loads((package / "tasks" / (task_id + ".json")).read_text(encoding="utf-8"))


def _reply(model: Path, task_id: str, suffix: str = "") -> str:
    return (model / "replies" / "first" / (task_id + suffix + ".txt")).read_text(
        encoding="utf-8")


def _registered_dev_specs(monkeypatch: pytest.MonkeyPatch) -> None:
    """只在当前测试进程登记 TD06 开发量规，退出后恢复冻结注册表。"""
    monkeypatch.setattr(admission, "STOP_RECOVERY_SPECS",
                        dict(admission.STOP_RECOVERY_SPECS))
    criterion.register_dev_specs()


def _one_task_package(tmp_path: Path, source: Path, task_id: str) -> Path:
    """复制 cmd_grade 所需的最小真实任务包，保持题面摘要和父代材料字节不变。"""
    package = tmp_path / "package"
    (package / "tasks").mkdir(parents=True)
    (package / "prompts").mkdir()
    shutil.copy2(source / "tasks" / (task_id + ".json"), package / "tasks")
    shutil.copy2(source / "prompts" / (task_id + ".txt"), package / "prompts")
    shutil.copytree(source / "materials", package / "materials")
    return package


def _cmd_grade_one(tmp_path: Path, task_id: str, first: str,
                   repair: str | None = None) -> dict:
    """经公开 cmd_grade 路径对一张历史卡重判，返回唯一任务的报告行。"""
    package = _one_task_package(tmp_path, _project_file(_PROJECT_ROOT, GLM / "package"), task_id)
    replies = tmp_path / "replies"
    replies.mkdir()
    (replies / (task_id + ".txt")).write_text(first, encoding="utf-8")
    if repair is not None:
        (replies / (task_id + ".repair.txt")).write_text(repair, encoding="utf-8")
    report_path = tmp_path / "grade.json"
    args = argparse.Namespace(package_dir=str(package), replies=str(replies), ledger=[],
                              out=str(report_path), json=False, round_label="takeover-regression")
    assert admission.cmd_grade(args) == 0
    rows = json.loads(report_path.read_text(encoding="utf-8"))["tasks"]
    assert [row["task_id"] for row in rows] == [task_id]
    return rows[0]


def _with_comment(reply: str) -> str:
    """只往可执行代码加入注释；可执行 AST 与行为都应保持等价。"""
    marker = "def score_actions(view):"
    assert marker in reply
    return reply.replace(marker, "# comment-only repair\n" + marker, 1)


def test_td04_syntax_recovery_gets_delivery_credit_without_parent_behavior_claim(tmp_path):
    """首答语法坏、修复完整可执行时记交付修复；不可凭不可比 AST 声称行为改善。"""
    row = _cmd_grade_one(tmp_path, "TD04", _reply(GLM, "TD04"),
                         _reply(GLM, "TD04", ".repair"))

    assert row["first_pass"] is False
    assert row["repair_pass"] is True
    assert row["credited_attempt"] == "repair"
    assert row["credit"] == {"first": False, "repair": True, "final": True}
    assert row["attempt_change"]["delivery_recovered"] is True
    assert row["attempt_change"]["repair_credit_basis"] == "DELIVERY_RECOVERED"
    # 首答没有可解析 AST：这里的 None 是「不可比较」，绝不能转写成父代行为已改善。
    assert row["code_changed"] is None
    assert row["behavior_changed"] is None
    assert row["repair_gate"] is None


@pytest.mark.parametrize("repair_builder", [lambda text: text, _with_comment],
                         ids=["same-code", "comment-only"])
def test_td04_same_or_comment_only_repair_never_earns_repair_credit(tmp_path, repair_builder):
    """两侧均可比较时，同代码及只改注释仍不得被误记为修订行为证据。"""
    executable = _reply(GLM, "TD04", ".repair")
    row = _cmd_grade_one(tmp_path, "TD04", executable, repair_builder(executable))

    assert row["first_pass"] is True
    assert row["repair_pass"] is True
    assert row["credit"]["first"] is True
    assert row["credit"]["repair"] is False
    assert row["code_changed"] is False
    assert row["behavior_changed"] is False
    assert row["repair_gate"]["code"] == "REPAIR_NO_EXECUTABLE_CHANGE"


def test_td01_unscored_pass_is_rejected_by_shared_unknown_contract():
    """TD01 的无事实 pass 越过已知负分，必须由正式共同能力合同阻断。"""
    outcome = admission.grade_reply(_task(_project_file(_PROJECT_ROOT, GLM / "package"), "TD01"), _reply(GLM, "TD01"),
                                    _project_file(_PROJECT_ROOT, GLM / "package"))

    assert outcome["pass"] is False
    rows = outcome["detail"]["capability"]["unknown_windows"]
    probe = next(row for row in rows if row["fixture"] == "unscored_action")
    assert probe["unknown"] == "pass"
    assert probe["known"] == "discard:1w"
    assert probe["ok"] is False
    assert any("unscored_action" in problem and "未知动作" in problem
               for problem in outcome["problems"])


def test_td06_selected_option_inherits_only_verified_prompt_semantics(monkeypatch):
    """选④可继承真实题面动作；答卷不能自行伪造选项含义。"""
    _registered_dev_specs(monkeypatch)
    package = _project_file(_PROJECT_ROOT, GLM / "package")
    task = _task(package, "TD06")
    outcome = admission.grade_reply(task, _reply(GLM, "TD06"), package)

    assert outcome["pass"] is True
    evidence = outcome["detail"]["stop_recovery"]["choice_evidence"]
    assert evidence["selected"] == "④"
    assert set(evidence["inherited"]) == {"stop", "keep_scene"}

    forged = json.loads(json.dumps(task))
    forged["prompt_file"] = "prompts/not-the-verified-question.txt"
    forged_outcome = admission.grade_reply(forged, "结论：选④。source=confirm-roots.json，确认根作废。",
                                            package)
    assert forged_outcome["pass"] is False
    assert forged_outcome["detail"]["stop_recovery"]["choice_evidence"]["inherited"] == []


@pytest.mark.parametrize(
    "reply",
    [
        "结论：选④。source=confirm-roots.json，确认根作废；也选②。",
        "结论：选④。source=confirm-roots.json，确认根作废；不选④。",
    ],
    ids=["multiple-options", "reject-selected-option"],
)
def test_td06_ambiguous_or_self_opposed_selection_fails_closed(monkeypatch, reply):
    """多选或反对已选项时，不能借首个选项编号继承题面动作。"""
    _registered_dev_specs(monkeypatch)
    outcome = admission.grade_reply(_task(_project_file(_PROJECT_ROOT, GLM / "package"), "TD06"), reply, _project_file(_PROJECT_ROOT, GLM / "package"))

    assert outcome["pass"] is False
    assert outcome["detail"]["stop_recovery"]["choice_evidence"]["inherited"] == []


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ("结论：选①。source=confirm-roots.json；停止受影响批次、保留现场并报告污染，确认根作废。",
         "首句选择的是违规处置"),
        ("结论：选④。source=confirm-roots.json；停止受影响批次、报告污染、确认根作废，"
         "但不保留现场，只留取证副本。", "keep_scene"),
        ("结论：选④。source=confirm-roots.json；停止受影响批次、保留现场并报告污染、确认根作废；"
         "仍继续用受污染批次生成，不必上报。", "STOP_CONTRARY_EXECUTION"),
    ],
    ids=["wrong-option", "deny-keep-scene", "continue-polluted-batch"],
)
def test_td06_explicitly_contrary_answers_are_rejected(monkeypatch, reply, expected):
    """正确的选项编号不能覆盖选错、否定现场保留或继续污染的自身主张。"""
    _registered_dev_specs(monkeypatch)
    outcome = admission.grade_reply(_task(_project_file(_PROJECT_ROOT, GLM / "package"), "TD06"), reply, _project_file(_PROJECT_ROOT, GLM / "package"))

    assert outcome["pass"] is False
    assert outcome["violation"] is True
    details = outcome["detail"]["stop_recovery"]
    assert details["predicates"]["STOP_CONTRARY_EXECUTION"]["ok"] is False
    rendered = "\n".join(outcome["problems"] + outcome["violations"])
    assert expected in rendered


@pytest.mark.parametrize("model", [GLM, SLIM], ids=["glm", "slim"])
def test_keyword_repair_prompt_does_not_require_executable_code_tail(model):
    """两套开发卡的 keyword 修复提示词都只要求题面短答，不夹带代码修订尾巴。"""
    import importlib.util

    # 走实际出错的两套调用入口，不能仅测本来就正确的公共修复提示词助手。
    source = model / ("glm_run.py" if model == GLM else "slim_run.py")
    spec = importlib.util.spec_from_file_location("takeover_" + source.stem, source)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    task = _task(model / "package", "TD06")
    built = runner.build_slim_repair(task, "选④。", [])

    assert built["identity"] == "keyword_head"
    assert "可执行代码" not in built["added"]
    assert "行为差异" not in built["added"]
    assert "代码围栏" not in built["added"]
    assert "中文短答" in built["added"]
