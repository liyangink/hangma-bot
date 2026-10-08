"""候选路由诊断 · **同卡同判据对照**（glm-5.3 vs deepseek-v4-flash），零模型。

回答的唯一问题：**「轮间 / 卡间波动」是候选模型的属性，还是这套任务卡的属性？**

对照纪律：
  * 只做归因，不做型号排名；不给任何"总分"；
  * 两列用**同一批卡（逐字节相同的题面）**、**同一判据（criterion.py，未改）**、同一通道；
  * 失败类别四分类（互斥，优先级 测量 > 机械 > 要点 > 机制）：
      MEASUREMENT 测量：判据/装配侧造成（解析器 confound、修复卡格式口径、误拒归因提示）
      MECHANICAL  机械：静态预检、解析、四字段、围栏数、禁词/禁式
      KEYPOINT    要点：停止/恢复结构化谓词缺项（少写了要求的步骤/要素）
      MECHANISM   机制：能力合同 ①②③④（未知越位、可解窗、修订行为差异）

用法：
    .venv/bin/python <本目录>/compare_models.py --flash <v4-flash 判据.json> \
        --glm <glm 判据.json> [--flash-long <长卡判据.json>] --out-json <对比.json> --out-md <对比.md>
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-dev-cards/glm'

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

MECHANICAL_PATTERNS = (
    "静态预检未通过", "受限子集硬禁项", "候选代码围栏数", "解析未通过", "未提取到",
    "结构化四字段缺失", "禁词命中", "代码含禁式",
)
KEYPOINT_PATTERNS = ("停止/恢复·",)
MECHANISM_PATTERNS = (
    "能力合同", "反例窗口", "可解窗口", "方向差异", "修订行为签名",
)
MEASUREMENT_CHECKS = ("no_result_predicate_attribution", "contrary_claim_attribution",
                      "forbidden_hit_attribution")
#: 装配侧信号（修复卡与判分器口径不符）来自 attribute.py 的**逐卡判据**（读实际派发的修复卡），
#: 这里不写死卡名——写死会把另一列的结论搬过来。
SIDE_SIGNAL_VERDICTS = ("HARNESS", "MEASUREMENT")


def classify(card_id: str, texts, criterion_detail, attempt: str,
             side_signals: dict = None, gate_misfire: bool = False) -> dict:
    detail = criterion_detail or {}
    measurement = sorted(name for name in MEASUREMENT_CHECKS
                         if isinstance(detail.get(name), dict)
                         and detail[name].get("ok") is False)
    # 侧信号按**尝试**作用：同一张卡可能在首答是模型问题、在修复轮才是装配问题（TD03 就是）。
    side = ((side_signals or {}).get(card_id) or {}).get(attempt)
    if side in SIDE_SIGNAL_VERDICTS and texts:
        measurement.append("side_signal:" + side)
    if gate_misfire:
        # 冻结的修复信用闸门在**首答不可编译**时误触发（见报告 §4）：这是一次真实修复被拒发信用，
        # 属测量/实现侧，不是候选失败。
        measurement.append("repair_credit_gate_misfire")
    mechanical, keypoint, mechanism = [], [], []
    for text in texts:
        item = str(text)
        if any(pat in item for pat in MECHANICAL_PATTERNS):
            mechanical.append(item[:110])
        elif any(pat in item for pat in KEYPOINT_PATTERNS):
            keypoint.append(item[:110])
        elif any(pat in item for pat in MECHANISM_PATTERNS):
            mechanism.append(item[:110])
    if measurement:
        klass = "MEASUREMENT"
    elif mechanical:
        klass = "MECHANICAL"
    elif keypoint:
        klass = "KEYPOINT"
    elif mechanism:
        klass = "MECHANISM"
    elif texts:
        klass = "KEYPOINT"
    else:
        klass = "PASS"
    return {"class": klass, "measurement": measurement, "mechanical": mechanical,
            "keypoint": keypoint, "mechanism": mechanism,
            "texts": [str(t)[:160] for t in texts]}


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def rows_of(report: dict, side_signals: dict = None) -> dict:
    out = {}
    for row in report.get("cards") or []:
        card_id = row["card_id"]
        gate = row.get("repair_gate") or {}
        change = row.get("attempt_change") or {}
        gate_misfire = (gate.get("code") == "REPAIR_NO_EXECUTABLE_CHANGE"
                        and change.get("first_executable_digest") is None
                        and bool(row.get("frozen_repair_pass")))
        first_texts = list(row.get("problems_first") or []) + list(row.get("violations_first") or [])
        repair_texts = list(row.get("repair_problems") or []) + list(row.get("repair_violations") or [])
        out[card_id] = {
            "first_pass": bool(row.get("frozen_first_pass")),
            "first": classify(card_id, first_texts if not row.get("frozen_first_pass") else [],
                              row.get("first_criterion"), "first", side_signals),
            "repair_used": bool(row.get("repair_criterion")),
            "repair_pass": row.get("frozen_repair_pass"),
            "repair_gate": gate.get("code"),
            "gate_misfire": gate_misfire,
            "repair": classify(card_id, repair_texts if row.get("frozen_repair_pass") is False else [],
                               row.get("repair_criterion"), "repair", side_signals,
                               gate_misfire=gate_misfire),
            "final_pass": bool(row.get("frozen_final_pass")),
            "diagnostic_codes": row.get("diagnostic_codes_first") or [],
            "repair_codes": row.get("repair_diagnostic_codes") or [],
            "usage": {k: (v or {}).get("usage") for k, v in (row.get("usage") or {}).items()},
            "elapsed": row.get("elapsed_s"),
            "change": row.get("attempt_change"),
            "delta": row.get("repair_delta"),
        }
    return out


def tally(rows: dict, key: str) -> dict:
    out: dict = {}
    for row in rows.values():
        klass = row[key]["class"]
        out[klass] = out.get(klass, 0) + 1
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--flash", required=True, help="v4-flash 瘦卡判据 JSON")
    parser.add_argument("--glm", required=True, help="glm 瘦卡判据 JSON")
    parser.add_argument("--flash-long", default=None, help="v4-flash 长卡判据 JSON（同一批卡的另一渲染）")
    parser.add_argument("--flash-attribution", default=None)
    parser.add_argument("--glm-attribution", default=None)
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-md", required=True)
    args = parser.parse_args()

    def side_map(path):
        if not path:
            return {}
        data = load(path)
        out = {}
        for row in (data.get("cards") or []):
            per_attempt = {}
            for signal in row.get("extra_signals") or []:
                attempt = signal.get("attempt")
                kind = signal.get("kind", "")
                verdict = "HARNESS" if kind.startswith("harness") else "MEASUREMENT"
                per_attempt[attempt] = verdict
            out[row["card_id"]] = per_attempt
        return out
    flash = rows_of(load(args.flash), side_map(args.flash_attribution))
    glm = rows_of(load(args.glm), side_map(args.glm_attribution))
    flash_long = rows_of(load(args.flash_long)) if args.flash_long else None
    ids = sorted(set(flash) | set(glm))

    cards, agree_first, agree_final = [], 0, 0
    for card_id in ids:
        f, g = flash.get(card_id) or {}, glm.get(card_id) or {}
        same_first = f.get("first_pass") == g.get("first_pass")
        same_final = f.get("final_pass") == g.get("final_pass")
        agree_first += bool(same_first)
        agree_final += bool(same_final)
        cards.append({
            "card_id": card_id,
            "flash": {"first_pass": f.get("first_pass"), "class": (f.get("first") or {}).get("class"),
                      "repair_pass": f.get("repair_pass"), "final_pass": f.get("final_pass"),
                      "codes": f.get("diagnostic_codes"), "repair_codes": f.get("repair_codes"),
                      "usage": f.get("usage"), "elapsed": f.get("elapsed")},
            "flash_long": ({"first_pass": (flash_long.get(card_id) or {}).get("first_pass"),
                            "class": ((flash_long.get(card_id) or {}).get("first") or {}).get("class"),
                            "final_pass": (flash_long.get(card_id) or {}).get("final_pass")}
                           if flash_long else None),
            "glm": {"first_pass": g.get("first_pass"), "class": (g.get("first") or {}).get("class"),
                    "repair_pass": g.get("repair_pass"), "final_pass": g.get("final_pass"),
                    "codes": g.get("diagnostic_codes"), "repair_codes": g.get("repair_codes"),
                    "usage": g.get("usage"), "elapsed": g.get("elapsed")},
            "agree_first": bool(same_first), "agree_final": bool(same_final),
            "flash_detail": f, "glm_detail": g,
        })

    summary = {
        "flash_first_classes": tally(flash, "first"),
        "glm_first_classes": tally(glm, "first"),
        "flash_final_pass": sum(1 for r in flash.values() if r["final_pass"]),
        "glm_final_pass": sum(1 for r in glm.values() if r["final_pass"]),
        "first_answer_agreement": "{0}/{1}".format(agree_first, len(ids)),
        "final_agreement": "{0}/{1}".format(agree_final, len(ids)),
        "cards_total": len(ids),
        "flash_long_first_classes": tally(flash_long, "first") if flash_long else None,
    }
    payload = {"schema": "sitin-p25-dev-cards-model-compare/1",
               "rule": ("同卡（题面逐字节相同）、同判据、同通道；只做归因，不做排名，不给总分。"),
               "summary": summary, "cards": cards}
    Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_json).write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                                   encoding="utf-8")

    lines = ["# 候选路由诊断 · 同卡同判据对照（v4-flash vs glm-5.3）", "",
             "| 卡 | 能力面 | v4-flash 首答 / 最终 | glm 首答 / 最终 | 首答一致 | 最终一致 |",
             "| --- | --- | --- | --- | --- | --- |"]
    faces = {}
    man = json.loads((_project_file(_PROJECT_ROOT, BASE / "glm" / "package" / "manifest.json")).read_text(encoding="utf-8"))
    for row in man.get("cards") or []:
        faces[row["task_id"]] = row.get("capability_face")
    for card in cards:
        lines.append("| {0} | {1} | {2} / {3} | {4} / {5} | {6} | {7} |".format(
            card["card_id"], faces.get(card["card_id"], ""),
            (card["flash"]["class"], card["flash"]["first_pass"]),
            card["flash"]["final_pass"],
            (card["glm"]["class"], card["glm"]["first_pass"]),
            card["glm"]["final_pass"],
            "是" if card["agree_first"] else "否", "是" if card["agree_final"] else "否"))
    lines += ["", "## 合计", "",
              "- v4-flash 首答类别：" + json.dumps(summary["flash_first_classes"], ensure_ascii=False),
              "- glm 首答类别：" + json.dumps(summary["glm_first_classes"], ensure_ascii=False),
              "- 最终通过：v4-flash {0}/6，glm {1}/6".format(summary["flash_final_pass"],
                                                             summary["glm_final_pass"]),
              "- 首答一致：{0}；最终一致：{1}".format(summary["first_answer_agreement"],
                                                      summary["final_agreement"]),
              ""]
    Path(args.out_md).write_text(chr(10).join(lines) + chr(10), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
