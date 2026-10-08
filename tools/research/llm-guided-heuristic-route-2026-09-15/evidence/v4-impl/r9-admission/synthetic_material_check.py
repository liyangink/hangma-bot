"""合成材料自检：在新签发的题包上复证 R9 P4 的材料门（`INCOMPLETE/BLOCKED`）。

三条不变量（缺一不可）：
  1. **不得准入**：材料不兼容 ⇒ `verdict.status=INCOMPLETE`、`admission_pass=false`，
     且 blocking_reasons 指明材料不兼容；即使两轮"通过数"都不低也不放行。
  2. **不得兑换信用**：受影响的 T06/T07/T08「候选未违规但证据不完整」——
     `decidable_pass=true` 但 `pass=false`、`credit_blocked=true`，不进通过数。
  3. **不得缩小分母**：`summary.tasks=24` 不变，通过数按**冻结分母**报（21/24），
     不允许把三项材料不兼容从分母里删掉来凑门槛。

对照组：同一批合成回复 + **兼容**材料必须 `COMPLETE` 且 `admission_pass=true`——
证明判分器仍能区分好坏，不是恒判 INCOMPLETE（与 R9 收口稿「run8 FAIL / run9 PASS」
反向校验同一手法）。

合成回复 = 任务包自带的手工标准答案（`selftest/standard`）与其**尾随空行变体**
（两轮回复字节不同 ⇒ `round_digest` 不同 ⇒ 满足两遍唯一性；判分结论不变）。
**这不是模型成绩**；本自检只验证判分器与材料门，0 真实 LLM、0 真实桌赛。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import importlib.util
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
REPO = _PROJECT_ROOT
TOOLS = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/tools')
sys.path.insert(0, str(TOOLS))

_spec = importlib.util.spec_from_file_location("adm", _project_file(_PROJECT_ROOT, TOOLS / "sitin_model_admission.py"))
adm = importlib.util.module_from_spec(_spec)
sys.modules["adm"] = adm
_spec.loader.exec_module(adm)

PACKAGE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/package')
R6 = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r6-model-admission')
#: 不兼容材料：r6 期父代（兼容性自守卫只接受 sitin-scoring-view/1）。
INCOMPATIBLE_MATERIAL = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r6-model-admission/materials/T06-parent-triax-v1.py')
COMPATIBLE_MATERIAL = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/package/materials/T06-parent-triax-v1-view3.py')


def build_variant(name: str, material: Path) -> Path:
    """把新签发题包复制一份到 scratch，只替换父代材料；回复用合成标准答案。"""

    root = _project_file(_PROJECT_ROOT, HERE / "scratch" / name)
    package = root / "package"
    if root.exists():
        shutil.rmtree(root)
    for sub in ("tasks", "prompts", "materials"):
        (package / sub).mkdir(parents=True, exist_ok=True)
    for src in sorted((_project_file(_PROJECT_ROOT, PACKAGE / "tasks")).glob("T*.json")):
        shutil.copyfile(src, package / "tasks" / src.name)
    for src in sorted((_project_file(_PROJECT_ROOT, PACKAGE / "prompts")).glob("T*.txt")):
        shutil.copyfile(src, package / "prompts" / src.name)
    shutil.copyfile(_project_file(_PROJECT_ROOT, PACKAGE / "manifest.json"), package / "manifest.json")
    # 材料放在**任务声明的引用路径**上：不兼容情形就是"该引用指向的字节不兼容"。
    shutil.copyfile(material, package / "materials" / COMPATIBLE_MATERIAL.name)
    for round_label, suffix in (("r1", ""), ("r2", "\n")):
        replies = root / "replies" / round_label
        replies.mkdir(parents=True, exist_ok=True)
        for src in sorted((_project_file(_PROJECT_ROOT, PACKAGE / "selftest" / "standard")).glob("T*.txt")):
            (replies / src.name).write_text(
                src.read_text(encoding="utf-8") + suffix, encoding="utf-8")
    return package


def run_variant(name: str, package: Path) -> dict:
    reports = []
    for round_label in ("r1", "r2"):
        path = _project_file(_PROJECT_ROOT, HERE / "scratch" / (name + "-" + round_label + ".json"))
        adm.cmd_grade(SimpleNamespace(
            package_dir=str(package),
            replies=str(_project_file(_PROJECT_ROOT, HERE / "scratch" / name / "replies" / round_label)),
            out=str(path), round_label=round_label, json=False))
        reports.append(path)
    verdict_path = _project_file(_PROJECT_ROOT, HERE / "scratch" / (name + "-verdict.json"))
    # 汇总端必须读**本变体自己**的 manifest：否则「当前材料」会退回默认 r6 包，
    # 变成拿旧包身份去比对合成包的报告（那是另一类失败，不是材料门）。
    adm.cmd_summarize(SimpleNamespace(
        report=[str(p) for p in reports],
        manifest=str(package / "manifest.json"), out=str(verdict_path)))
    verdict = json.loads(verdict_path.read_text(encoding="utf-8"))
    report = json.loads(reports[0].read_text(encoding="utf-8"))
    return {"report": report, "verdict": verdict}


def observe(out: dict) -> dict:
    report, verdict = out["report"], out["verdict"]
    summary = report["summary"]
    rows = {row["task_id"]: row for row in report["tasks"]}
    return {
        "status": verdict["status"],
        "admission_pass": verdict["admission_pass"],
        "unique_rounds": verdict["unique_rounds"],
        "summary_status": summary["status"],
        "tasks_denominator": summary["tasks"],
        "pass": summary["pass"],
        "scorer_pass": summary["scorer_pass"],
        "uncredited_task_ids": sorted(summary["uncredited_task_ids"]),
        "credit_blocked_rows": sorted(tid for tid, row in rows.items()
                                      if row.get("credit_blocked")),
        "decidable_but_uncredited": sorted(
            tid for tid, row in rows.items()
            if row.get("decidable_pass") and not row.get("pass")),
        "material_incomplete_task_ids": sorted(summary["material_incomplete_task_ids"]),
        "warning_task_ids": sorted({w["task_id"] for w in report["warnings"]}),
        "blocking_reasons": verdict["blocking_reasons"],
        "round_ok": [row["round_ok"] for row in verdict["rounds"]],
    }


def main() -> int:
    bad_package = build_variant("incompatible", INCOMPATIBLE_MATERIAL)
    bad = observe(run_variant("incompatible", bad_package))
    good_package = build_variant("compatible", COMPATIBLE_MATERIAL)
    good = observe(run_variant("compatible", good_package))
    affected = bad["material_incomplete_task_ids"]
    ok_bad = (bad["status"] == "INCOMPLETE"
              and bad["admission_pass"] is False
              and bad["summary_status"] == adm.PACKAGE_INCOMPLETE
              and bad["tasks_denominator"] == 24
              and bad["uncredited_task_ids"] == affected
              and bad["credit_blocked_rows"] == affected
              and bad["decidable_but_uncredited"] == affected
              and bad["pass"] == 24 - len(affected)
              and any("材料" in reason for reason in bad["blocking_reasons"]))
    ok_good = (good["status"] == "ADMISSION_PASS"
               and good["admission_pass"] is True
               and good["unique_rounds"] == 2
               and not good["material_incomplete_task_ids"]
               and good["pass"] == 24)
    result = {
        "schema": "sitin-model-admission-synthetic-material-check/1",
        "purpose": "复证 R9 P4 材料门：不兼容材料 ⇒ 整包 INCOMPLETE/BLOCKED、不兑换信用、分母不缩",
        "replies_kind": "synth_standard_fixture（手工标准答案 + 尾随空行变体）——**不是**模型成绩",
        "incompatible_material": str(INCOMPATIBLE_MATERIAL.relative_to(REPO)),
        "compatible_material": str(COMPATIBLE_MATERIAL.relative_to(REPO)),
        "incompatible_case": bad,
        "control_case": good,
        "ok": bool(ok_bad and ok_good),
    }
    Path(_project_file(_PROJECT_ROOT, HERE / "selftest" / "synthetic-material-check.json")).write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"ok": result["ok"], "incompatible": bad["status"],
                      "incompatible_admission_pass": bad["admission_pass"],
                      "incompatible_pass": bad["pass"],
                      "control": good["status"],
                      "control_admission_pass": good["admission_pass"],
                      "control_pass": good["pass"]}, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
