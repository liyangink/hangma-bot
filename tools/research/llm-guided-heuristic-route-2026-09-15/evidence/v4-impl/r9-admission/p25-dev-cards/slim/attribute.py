"""P25 瘦卡小诊断 · **额外归因**（零模型；把两类新失败具名到测量/装配侧）。

本次实测出现两类**长卡轮没有见过**的失败，且都不是模型能力问题：

A. PARSE_FAILED::ambiguous_code（TD01 首答）
   回复里有**两个围栏**：四字段 JSON 围栏 + 唯一的 python 候选围栏。
   parse_model_reply 用「块内是否出现入口函数名」判断候选块；四字段 JSON 的 trigger 里
   写了入口函数名（合同要求写清机制，模型的自然写法），于是 JSON 块也被算成
   「包含入口函数的代码块」⇒ 判 ambiguous_code、整题未通过。
   → 归因：**测量侧**（解析器的子串判据把必需的说明块误算成候选块）。

B. 修复轮 MECHANISM_FIELDS_MISSING（TD01/TD03 修复）
   本轮的修复卡走 build_action_value_repair_card_prompt，其输出条款是「只输出一个
   python 围栏（围栏前可以用几句话说明）」，**不含结构化四字段要求**；而这两张开发卡是
   kind=code，判分器用 check_code 且 require_mechanism=True ⇒ 必须交四字段 JSON。
   → 归因：**装配侧**（修复卡入口与 kind=code 判分器不同口径）。

两条都给程序化判据（可复核），并**不修改** tools/ 下任何实现。
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
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission/p25-dev-cards')
ADMISSION = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-admission')
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
REPO = _PROJECT_ROOT
sys.path.insert(0, str(ADMISSION))
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROUTE / "tools")))

import sitin_generate as gen                                     # noqa: E402


def parser_confound(reply: str) -> dict:
    """ambiguous_code 是否由「四字段 JSON 提到入口函数名」造成（测量侧误判）。"""
    text = (reply or "").replace("\r\n", "\n").strip()
    fence = chr(96) * 3
    spans = [(m.start(), m.group(1).strip(), m.group(0).lstrip()[:12])
             for m in gen._FENCE_RE.finditer(text)]
    with_entry = [block for _s, block, _h in spans if gen.AV_ENTRY_NAME in block]
    json_blocks = [block for _s, block, head in spans if head.startswith(fence + "json")]
    python_blocks = [block for _s, block, head in spans if head.startswith(fence + "python")]
    parsed = gen.parse_action_value_reply(text)
    suspicious = (parsed["status"] == "ambiguous_code" and len(python_blocks) == 1
                  and any(gen.AV_ENTRY_NAME in block for block in json_blocks))
    return {"ok": not suspicious, "status": parsed["status"],
            "fences": len(spans), "python_blocks": len(python_blocks),
            "json_blocks": len(json_blocks), "blocks_with_entry": len(with_entry),
            "verdict": ("可疑误判：四字段 JSON 里写了入口函数名 score_actions，"
                        "被当成第二个候选代码块" if suspicious else "解析判据与块形态一致"),
            "note": "归因提示，不参与判分"}


def repair_card_missing_four_fields(repair_prompt: str, kind: str) -> dict:
    """修复卡是否漏了 kind=code 判分器要求的「结构化四字段」。"""
    fence = chr(96) * 3
    if kind != "code":
        return {"ok": True, "applicable": False,
                "note": "keyword 卡不走 require_mechanism，不适用"}
    # **只看指令头**：材料段逐字引用了上一轮交付（里面本来就有四字段 JSON），
    # 在全文里找 token 会被引文喂饱，永远判"已含要求"（实测踩过这个坑）。
    head_marker = "【上一轮交付（逐字，仅供你修改，不要照抄解释）】"
    head = repair_prompt.split(head_marker)[0] if head_marker in repair_prompt else repair_prompt
    has_fields = ("四字段" in head) or all(
        token in head for token in ("trigger", "changed_branches",
                                    "expected_direction", "counterexample"))
    json_fence = (fence + "json") in head
    suspicious = not (has_fields and json_fence)
    return {"ok": not suspicious, "applicable": True, "checked_scope": "指令头（材料之前）",
            "four_field_tokens": has_fields, "json_fence": json_fence,
            "verdict": ("装配侧：修复卡未要求结构化四字段/json 围栏，"
                        "而 kind=code 判分器 require_mechanism=True 会判挂" if suspicious
                        else "修复卡已含四字段要求"),
            "note": "归因提示，不参与判分"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--criterion", required=True)
    parser.add_argument("--replies", required=True)
    parser.add_argument("--repair-prompts", default=str(_project_file(_PROJECT_ROOT, HERE / "repair-prompts")))
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-md", required=True)
    args = parser.parse_args()

    report = json.loads(Path(args.criterion).read_text(encoding="utf-8"))
    replies = Path(args.replies)
    cards, signals = [], []
    for row in report.get("cards") or []:
        card_id = row["card_id"]
        task = json.loads((_project_file(_PROJECT_ROOT, HERE / "package" / "tasks" / (card_id + ".json")))
                          .read_text(encoding="utf-8"))
        kind = str(task["validation"]["kind"])
        first_path = replies / (card_id + ".txt")
        repair_path = replies / (card_id + ".repair.txt")
        entry = {"card_id": card_id, "kind": kind,
                 "first": parser_confound(first_path.read_text(encoding="utf-8"))
                 if first_path.is_file() else None,
                 "repair_parser": parser_confound(repair_path.read_text(encoding="utf-8"))
                 if repair_path.is_file() else None,
                 "repair_card": None}
        prompt_path = Path(args.repair_prompts) / card_id / "prompt.txt"
        if prompt_path.is_file():
            entry["repair_card"] = repair_card_missing_four_fields(
                prompt_path.read_text(encoding="utf-8"), kind)
            if kind == "keyword":
                head = (repair_path.read_text(encoding="utf-8").lstrip()[:12]
                        if repair_path.is_file() else "")
                entry["repair_card"]["keyword_reply_head"] = head
                entry["repair_card"]["answered_with_code_fence"] = head.startswith(chr(96) * 3)
        extra = []
        if entry["first"] and not entry["first"]["ok"]:
            extra.append({"kind": "measurement_parser_confound", "attempt": "first",
                          "detail": entry["first"]})
        if entry["repair_parser"] and not entry["repair_parser"]["ok"]:
            extra.append({"kind": "measurement_parser_confound", "attempt": "repair",
                          "detail": entry["repair_parser"]})
        if entry["repair_card"] and entry["repair_card"].get("ok") is False:
            extra.append({"kind": "harness_repair_card_format", "attempt": "repair",
                          "detail": entry["repair_card"]})
        entry["extra_signals"] = extra
        if any(s["kind"].startswith("harness") for s in extra):
            entry["side_verdict"] = "HARNESS"
        elif extra:
            entry["side_verdict"] = "MEASUREMENT"
        else:
            entry["side_verdict"] = "NONE"
        entry["frozen_final_pass"] = bool(row.get("frozen_final_pass"))
        cards.append(entry)
        if extra:
            signals.append({"card_id": card_id,
                            "kinds": sorted({s["kind"] for s in extra})})

    payload = {"schema": "sitin-p25-dev-cards-attribution/1",
               "cards": cards,
               "cards_with_side_signals": signals,
               "rule": ("side_verdict：HARNESS = 装配侧（修复卡与判分器口径不符）；"
                        "MEASUREMENT = 测量侧（解析器判据误判）；NONE = 无侧信号。"
                        "与 frozen_final_pass 合看：未通过 + 侧信号 ⇒ 不得记成模型能力失败。"),
               "note": "归因提示，不参与判分；tools/ 下实现未改动。"}
    Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_json).write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
    lines = ["# 瘦卡小诊断 · 额外归因（测量/装配侧）", ""]
    for entry in cards:
        lines += ["## {0}（{1}）".format(entry["card_id"], entry["kind"]),
                  "- 最终通过：{0}；侧信号：**{1}**".format(
                      entry["frozen_final_pass"], entry["side_verdict"]),
                  "- 首答解析：{0}".format(
                      (entry["first"] or {}).get("verdict", "（无）")),
                  "- 修复解析：{0}".format(
                      (entry["repair_parser"] or {}).get("verdict", "（无修复轮）")),
                  "- 修复卡格式：{0}".format(
                      (entry["repair_card"] or {}).get("verdict", "（无修复轮）")),
                  ""]
    Path(args.out_md).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"cards_with_side_signals": signals,
                      "verdicts": {c["card_id"]: c["side_verdict"] for c in cards}},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
