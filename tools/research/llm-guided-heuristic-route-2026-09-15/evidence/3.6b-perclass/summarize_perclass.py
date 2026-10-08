"""perclass 包：把门禁记录里的 G-2C 逐类段汇总成机读/人读两份产物。

输入（都由本包 repro.sh 生成）：
  new-baseline/gates-<candidate>-perclass.json   新基线（冻结子集）上的完整门禁记录
  old-corpus-control/g2c-<candidate>.json        历史对照样本（旧语料）上的逐类判定
  trigger/g2c-<candidate>.json                   构造触发集上的逐类判定
输出：
  perclass-summary.json   机读（逐候选 × 三面板）
  PERCLASS.md             人读
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/3.6b-perclass'

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
from pathlib import Path

HERE = Path(__file__).resolve().parent
CANDIDATES = ("chain_path_value", "four_component_path_value", "meld_opportunity_cost",
              "meld_waiting_conditional", "multiplier_path_potential",
              "seven_pairs_path_value")
#: 面板顺序 = canonical（唯一分母口径）→ 诊断子集 → 历史对照 → 构造触发集。
PANELS = ("canonical", "new-baseline", "old-corpus-control", "trigger")
PANEL_NOTES = {
    "canonical": "panel-canonical-20260910（105 份 / 359,262 行，record_layer_filled=true）",
    "new-baseline": "subset-perclass-frozen（5 份 / 16,851 行，raw；**诊断子集**，不得当分母）",
    "old-corpus-control": "auto-match-2026-09-06（3,343 行；历史对照）",
    "trigger": "构造触发集 48 窗口（**非效果证据**）",
}


def load_panel(panel: str, candidate: str):
    if panel == "canonical":
        path = _project_file(_PROJECT_ROOT, HERE / panel / ("g2c-{0}.json".format(candidate)))
        if not path.is_file():
            return None
        record = json.loads(path.read_text(encoding="utf-8"))
        return {"status": record["status"], "detail": record["detail"],
                "gate_record_admitted": None, "gate_record_all_pass": None}
    if panel == "new-baseline":
        path = _project_file(_PROJECT_ROOT, HERE / panel / ("gates-{0}-perclass.json".format(candidate)))
        if not path.is_file():
            return None
        record = json.loads(path.read_text(encoding="utf-8"))
        return {"status": record["perclass"]["status"], "detail": record["perclass"]["detail"],
                "gate_record_admitted": record["admitted"],
                "gate_record_all_pass": record["all_pass"]}
    prefix = "g2c-" if panel != "trigger" else "g2c-"
    path = _project_file(_PROJECT_ROOT, HERE / panel / (prefix + candidate + ".json"))
    if not path.is_file():
        return None
    record = json.loads(path.read_text(encoding="utf-8"))
    return {"status": record["status"], "detail": record["detail"],
            "gate_record_admitted": None, "gate_record_all_pass": None}


def main() -> int:
    out = {"schema": "sitin-perclass-summary/1", "candidates": {}, "panels": list(PANELS)}
    for candidate in CANDIDATES:
        entry = {}
        for panel in PANELS:
            loaded = load_panel(panel, candidate)
            if loaded is None:
                continue
            roll = loaded["detail"]["rollup"]
            entry[panel] = {
                "status": loaded["status"],
                "declared": roll["declared_count"],
                "reliable": roll["reliable_count"],
                "insufficient": roll["counts"]["insufficient"],
                "not_verified": roll["counts"]["not_verified"],
                "undeclared": roll["counts"]["undeclared"],
                "violations": loaded["detail"]["out_of_class_increment"]["violation_total"],
                "undecided_changes": loaded["detail"]["out_of_class_increment"][
                    "undecided_change_total"],
                "blocking_classes": roll["blocking_classes"],
                "reliable_classes": roll["reliable_classes"],
                "gate_record": {"all_pass": loaded["gate_record_all_pass"],
                                "admitted": loaded["gate_record_admitted"]},
                "panel_metrics": {
                    "scored": loaded["detail"]["panel"]["scored"],
                    "legal_match": loaded["detail"]["panel"]["legal_reconciliation"]["match"],
                    "legal_mismatch": loaded["detail"]["panel"]["legal_reconciliation"]["mismatch"],
                },
                "classes": [{key: item[key] for key in
                             ("id", "declared", "windows_in_class", "windows_undecided",
                              "fired_windows", "changed_windows", "verdict", "reason")}
                            for item in loaded["detail"]["classes"]],
            }
        out["candidates"][candidate] = entry
    (_project_file(_PROJECT_ROOT, HERE / "perclass-summary.json")).write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# 3.6b 逐类判定（G-2C）：逐候选 × 四面板（canonical 在前）",
        "",
        "> 机读同源：[perclass-summary.json](./perclass-summary.json)。三态读法见",
        "> [tools/sitin_gates.py](../../tools/sitin_gates.py) 的 CLASS_VERDICT_NOTES。",
        "",
        "| 候选 | 面板 | 汇总 | 已声明 | reliable | insufficient | not_verified | 类外溢出 | 归属未知 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for candidate in CANDIDATES:
        for panel in PANELS:
            entry = out["candidates"][candidate].get(panel)
            if entry is None:
                continue
            lines.append("| {0} | {1} | {2} | {3} | {4} | {5} | {6} | {7} | {8} |".format(
                candidate, panel, entry["status"], entry["declared"], entry["reliable"],
                entry["insufficient"], entry["not_verified"], entry["violations"],
                entry["undecided_changes"]))
    lines += [
        "",
        "> 面板口径（F7）：**canonical 面板是唯一分母口径**；new-baseline 是诊断子集，",
        "> 只用于自检，**不得**与 canonical 的数字相加或混用。",
        "",
        "| 面板 | 口径 |",
        "| --- | --- |",
    ] + ["| {0} | {1} |".format(panel, PANEL_NOTES[panel]) for panel in PANELS] + [
        "",
        "**读法**：汇总只取最弱环节（任一已声明类未达 reliable 即不给通过）；",
        "reliable 只说明「该类在本面板上被验证过」，不是效果结论。",
        "",
        "## 未达 reliable 的已声明类（逐候选，新基线）",
        "",
    ]
    for candidate in CANDIDATES:
        entry = out["candidates"][candidate].get("new-baseline")
        if entry is None:
            continue
        lines.append("**{0}**（{1}）：".format(candidate, entry["status"]))
        for item in entry["blocking_classes"]:
            lines.append("- {0} — {1}（{2}）".format(
                item["class_id"], item["verdict"], item["reason"]))
        lines.append("")
    (_project_file(_PROJECT_ROOT, HERE / "PERCLASS.md")).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("已写出 perclass-summary.json 与 PERCLASS.md")
    for candidate in CANDIDATES:
        entry = out["candidates"][candidate].get("new-baseline", {})
        print("{0:28s} {1:14s} reliable={2}/{3}".format(
            candidate, entry.get("status"), entry.get("reliable"), entry.get("declared")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
