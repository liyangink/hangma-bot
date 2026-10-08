"""P25 瘦卡小诊断 · **before/after 对比**（零模型）。

回答 Lead 的唯一问题：**机械类/注意力类失败是否下降？** 并给出数字。

对比口径（关键：判分器固定为**当前**版本，只变卡面）：
  * before 列 = 长卡轮的真实答卷，用**当前判分器**重判（slim/reports/baseline-oldcards-newgrader.json），
    这样"卡面变瘦"与"判分器更新"不会混在一起；
  * after  列 = 瘦卡轮的答卷与判分（slim/reports/criterion-final.json）。

失败分类（互斥，按下列优先级；全部由程序判定）：
  MEASUREMENT —— 该次尝试带测量侧信号（归因提示：复述后拒绝 / 否定语境要素线索 / 描述后果的禁词）；
  MECHANICAL  —— 形式与合规类：静态预检、解析、四字段、围栏数、禁词/禁式、输出合同形状；
  MECHANISM   —— 机制语义类：能力合同 ①②③④、停止/恢复结构化谓词；
  PASS        —— 该次尝试通过。

用法：
    .venv/bin/python <本目录>/compare.py --baseline <旧卡重判.json> --after <瘦卡判据.json> \
        --out-json <对比.json> --out-md <对比.md>
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-dev-cards/slim'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-dev-cards')
SLIM_PKG = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-dev-cards/slim/package')
OLD_PKG = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-dev-cards/package')

#: 机械类（形式/合规）失败的特征串——判分器 problems / violations 的原文前缀。
MECHANICAL_PATTERNS = (
    "静态预检未通过", "受限子集硬禁项", "候选代码围栏数", "解析未通过", "未提取到",
    "结构化四字段缺失", "禁词命中", "代码含禁式", "四字段",
)
#: 机制类（语义）失败的特征串。
MECHANISM_PATTERNS = (
    "能力合同", "停止/恢复", "输出合同", "窗口", "方向差异", "反例窗口", "可解窗口",
    "修订行为签名", "未注册视图",
)
MEASUREMENT_CHECKS = ("no_result_predicate_attribution", "contrary_claim_attribution",
                      "forbidden_hit_attribution")


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def classify(texts, criterion_detail) -> dict:
    """一次尝试的失败类别（互斥；优先级 测量 > 机械 > 机制）。"""
    detail = criterion_detail or {}
    measurement = sorted(name for name in MEASUREMENT_CHECKS
                         if isinstance(detail.get(name), dict)
                         and detail[name].get("ok") is False)
    mechanical, mechanism = [], []
    for text in texts:
        item = str(text)
        if any(pat in item for pat in MECHANICAL_PATTERNS):
            mechanical.append(item[:120])
        elif any(pat in item for pat in MECHANISM_PATTERNS):
            mechanism.append(item[:120])
    if measurement:
        klass = "MEASUREMENT"
    elif mechanical:
        klass = "MECHANICAL"
    elif mechanism:
        klass = "MECHANISM"
    elif texts:
        klass = "MECHANISM"
    else:
        klass = "PASS"
    return {"class": klass, "measurement_checks": measurement,
            "mechanical": mechanical, "mechanism": mechanism}


def attempt_view(row: dict, attempt: str) -> dict:
    if attempt == "first":
        texts = list(row.get("problems_first") or []) + list(row.get("violations_first") or [])
        detail = row.get("first_criterion") or {}
        passed = bool(row.get("frozen_first_pass"))
        codes = row.get("diagnostic_codes_first") or []
    else:
        texts = list(row.get("repair_problems") or []) + list(row.get("repair_violations") or [])
        detail = row.get("repair_criterion") or {}
        passed = row.get("frozen_repair_pass")
        codes = row.get("repair_diagnostic_codes") or []
    verdict = classify(texts, detail) if not passed else {
        "class": "PASS", "measurement_checks": [], "mechanical": [], "mechanism": []}
    return {"pass": passed, "codes": codes, "texts": [str(t)[:200] for t in texts],
            "verdict": verdict,
            "criterion_ok": detail.get("card_ok")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--after", required=True)
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-md", required=True)
    args = parser.parse_args()

    baseline = load(args.baseline)
    after = load(args.after)
    old_manifest = load(_project_file(_PROJECT_ROOT, OLD_PKG / "manifest.json"))
    slim_manifest = load(_project_file(_PROJECT_ROOT, SLIM_PKG / "manifest.json"))
    old_faces = {row["task_id"]: row for row in old_manifest.get("cards") or []}
    slim_faces = {row["task_id"]: row for row in slim_manifest.get("cards") or []}
    old_prompts = {tid: len((_project_file(_PROJECT_ROOT, OLD_PKG / "prompts" / (tid + ".txt"))).read_bytes())
                   for tid in old_faces}
    slim_prompts = {tid: len((_project_file(_PROJECT_ROOT, SLIM_PKG / "prompts" / (tid + ".txt"))).read_bytes())
                    for tid in slim_faces}

    base_rows = {row["card_id"]: row for row in baseline.get("cards") or []}
    after_rows = {row["card_id"]: row for row in after.get("cards") or []}

    cards = []
    for card_id in sorted(set(base_rows) | set(after_rows)):
        before_row, after_row = base_rows.get(card_id) or {}, after_rows.get(card_id) or {}
        cards.append({
            "card_id": card_id,
            "capability_face": (slim_faces.get(card_id) or {}).get("capability_face")
                               or (old_faces.get(card_id) or {}).get("capability_face"),
            "face_chars": {"before": old_prompts.get(card_id),
                           "after": slim_prompts.get(card_id),
                           "bytes_before": old_prompts.get(card_id),
                           "bytes_after": slim_prompts.get(card_id)},
            "before": {"first": attempt_view(before_row, "first"),
                       "repair": attempt_view(before_row, "repair"),
                       "final_pass": before_row.get("frozen_final_pass")},
            "after": {"first": attempt_view(after_row, "first"),
                      "repair": attempt_view(after_row, "repair"),
                      "final_pass": after_row.get("frozen_final_pass")},
        })

    def tally(key: str, attempt: str) -> dict:
        counts: dict = {}
        for card in cards:
            klass = card[key][attempt]["verdict"]["class"]
            counts[klass] = counts.get(klass, 0) + 1
        return counts

    summary = {
        "first_answer_classes": {"before": tally("before", "first"),
                                 "after": tally("after", "first")},
        "final_pass": {"before": sum(1 for c in cards if c["before"]["final_pass"]),
                       "after": sum(1 for c in cards if c["after"]["final_pass"]),
                       "total": len(cards)},
        "mechanical_first": {"before": tally("before", "first").get("MECHANICAL", 0),
                             "after": tally("after", "first").get("MECHANICAL", 0)},
        "mechanism_first": {"before": tally("before", "first").get("MECHANISM", 0),
                            "after": tally("after", "first").get("MECHANISM", 0)},
        "measurement_first": {"before": tally("before", "first").get("MEASUREMENT", 0),
                              "after": tally("after", "first").get("MEASUREMENT", 0)},
        "face_chars_total": {
            "before": sum(v for v in old_prompts.values() if v),
            "after": sum(v for v in slim_prompts.values() if v)},
        "controls": {"before": {k: v.get("ok") for k, v in
                                (baseline.get("negative_controls") or {}).items()},
                     "after": {k: v.get("ok") for k, v in
                               (after.get("negative_controls") or {}).items()}},
    }
    payload = {"schema": "sitin-p25-dev-cards-before-after/1",
               "comparison_rule": ("判分器固定为当前版本：before = 长卡轮答卷在当前判分器下重判；"
                                   "after = 瘦卡轮答卷。两次判分器身份见各自报告。"),
               "baseline_grader": baseline.get("grader_identity"),
               "after_grader": after.get("grader_identity"),
               "summary": summary, "cards": cards}
    Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_json).write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                                   encoding="utf-8")

    lines = ["# 瘦卡小诊断 · before / after 对比", "",
             "判分器固定为**当前**版本：before = 长卡轮答卷在当前判分器下重判；"
             "after = 瘦卡轮答卷。", "",
             "## 逐卡", "",
             "| 卡 | 能力面 | 题面字节（before→after） | 首答类别（before→after） | "
             "最终（before→after） |",
             "| --- | --- | --- | --- | --- |"]
    for card in cards:
        lines.append("| {0} | {1} | {2} → {3} | {4} → {5} | {6} → {7} |".format(
            card["card_id"], card["capability_face"],
            card["face_chars"]["before"], card["face_chars"]["after"],
            card["before"]["first"]["verdict"]["class"],
            card["after"]["first"]["verdict"]["class"],
            card["before"]["final_pass"], card["after"]["final_pass"]))
    lines += ["", "## 合计", "",
              "- 首答类别：before {0} → after {1}".format(
                  json.dumps(summary["first_answer_classes"]["before"], ensure_ascii=False),
                  json.dumps(summary["first_answer_classes"]["after"], ensure_ascii=False)),
              "- **机械类失败：before {0}/6 → after {1}/6**".format(
                  summary["mechanical_first"]["before"], summary["mechanical_first"]["after"]),
              "- 机制类失败：before {0}/6 → after {1}/6".format(
                  summary["mechanism_first"]["before"], summary["mechanism_first"]["after"]),
              "- 最终通过：before {0}/6 → after {1}/6".format(
                  summary["final_pass"]["before"], summary["final_pass"]["after"]),
              "- 题面合计（字节）：{0} → {1}".format(
                  summary["face_chars_total"]["before"], summary["face_chars_total"]["after"]),
              ""]
    Path(args.out_md).write_text(chr(10).join(lines) + chr(10), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
