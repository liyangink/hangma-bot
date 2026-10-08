#!/usr/bin/env python3
"""C33 候选生成器：用**新暴露的跟打后事实**造最小候选（只改打分）。

候选形状（预登记 §5.6「只改打分、只用新字段」；剂量在结果文档中登记）：
* 在父代非弃牌固定罚的同一锚点之后插入；
* 只读 `action.get("followup_baotou")`——由 C33 新增的候选事实字段，规则模块产出；
* 剂量 = **抵消父代自己的固定罚**（碰 −6 / 吃 −10），即让「跟打后可进爆头」的
  鸣牌按真实张数增益与过牌直接竞争（margin' = dw）；不引入新的调参常数；
* 不改合法性、不改候选表、不改紧急路径、不读隐藏信息。

产物（review/freematch-deep-dive-20260925/candidates/）：
  OPTY-R18-C33-FOLLOWUP-BAOTOU.py     主臂：followup_baotou is True -> +6(碰)/+10(吃)
  OPTY-R18-C33-NEGCTRL-MISSINGKEY.py  负控：同形状但读不存在的键 -> 预期改选 0
  OPTY-R18-C33-AUDIT-ACTIONLAYER.py   审计臂：改读**动作层** baotou_after（旧可得信号），
                                      用于量出「新事实相对旧信号」的增量

用法：
    UV_CACHE_DIR=/tmp/uv-cache .venv/bin/python \
        review/freematch-deep-dive-20260925/make_c33_candidates.py
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/freematch-deep-dive-20260925'

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

ROOT = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402
from hangma_bot.policy.r18_integrated_positive_v2 import (  # noqa: E402
    R18_INTEGRATED_POSITIVE_V2_SOURCE,
)

NL = chr(10)
Q = chr(34)
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/candidates')
LOG = _project_file(_PROJECT_ROOT, ROOT / ".team-work" / "c33-fact-exposure" / "make-candidates.json")
ANCHOR = "            total += fixed" + NL + "            total = round(total, 6)" + NL
"""父代源码里非弃牌分支的固定罚之后（缩进 12 空格，与 C32 同一锚点）。"""

GUARD = "if (kind == " + Q + "peng" + Q + ") or (kind == " + Q + "chi" + Q + "):"
TRACE_ANCHOR = "        trace = {" + Q + "basis" + Q


def dose_block(field: str, label: str):
    """生成「读一个跟打后字段并按父代固定罚抵消」的剂量块（缩进 12 空格）。"""

    return [
        "c33fb = action.get(" + Q + field + Q + ")",
        "if c33fb is True:",
        "    if kind == " + Q + "peng" + Q + ":",
        "        total = total + 6.0",
        "    else:",
        "        total = total + 10.0",
        "    total = round(total, 6)",
    ]


def build_block(dose_lines):
    lines = [GUARD]
    for raw in dose_lines:
        lines.append("    " + raw)
    return NL.join("            " + line for line in lines) + NL


def emit(name, field, note, report):
    block = build_block(dose_block(field, note))
    anchors = R18_INTEGRATED_POSITIVE_V2_SOURCE.count(ANCHOR)
    assert anchors == 1, "锚点在父代源码里不唯一：%d" % anchors
    candidate = R18_INTEGRATED_POSITIVE_V2_SOURCE.replace(ANCHOR, ANCHOR + block)
    assert candidate.count(ANCHOR) == 1, "替换后锚点不唯一"
    assert block in candidate, "插入块缺失"
    path = _project_file(_PROJECT_ROOT, OUT / name)
    path.write_text(candidate, encoding="utf-8")
    # 静态合同：受限执行器的只读白名单与语句限制必须在装配前就过。
    ActionValueScorer("research:" + path.stem, candidate)
    report[name] = {
        "note": note, "field": field, "inserted_lines": len(block.splitlines()),
        "anchor_count": anchors, "source_sha256_len": len(candidate),
        "static_contract": "通过",
    }
    print("%-46s 插入 %d 行；静态合同通过" % (name, len(block.splitlines())))


NEGATIVE_CONTROLS = (
    ("规则模块属性（候选不得自己算事实）",
     NL.join(("def score_actions(view):",
              "    x = progression.baotou_after_discard((), 1)",
              "    return {" + Q + "status" + Q + ": " + Q + "SCORED" + Q + ", "
              + Q + "entries" + Q + ": []}"))),
    ("import 语句", NL.join(("import hangma_bot",
                             "def score_actions(view):",
                             "    return {" + Q + "status" + Q + ": " + Q + "SCORED" + Q + ", "
                             + Q + "entries" + Q + ": []}"))),
)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    report = {}
    emit("OPTY-R18-C33-FOLLOWUP-BAOTOU.py", "followup_baotou",
         "主臂：跟打后可进爆头 -> 抵消父代固定罚（碰 +6 / 吃 +10）", report)
    emit("OPTY-R18-C33-NEGCTRL-MISSINGKEY.py", "followup_baotou_missing_key",
         "负控：同形状读不存在的键 -> 预期改选 0（证明改选由新字段造成）", report)
    emit("OPTY-R18-C33-AUDIT-ACTIONLAYER.py", "baotou_after",
         "审计臂：改读动作层 baotou_after（旧可得信号），量出新事实的增量", report)

    rejected = []
    for label, source in NEGATIVE_CONTROLS:
        try:
            ActionValueScorer("research:negctl", source)
        except Exception as exc:  # noqa: BLE001
            rejected.append((label, type(exc).__name__ + ": " + str(exc)[:80]))
        else:
            rejected.append((label, "**未被拒绝（异常）**"))
    report["negative_controls"] = rejected
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text(json.dumps(report, ensure_ascii=False, indent=2) + NL, encoding="utf-8")
    print()
    for label, why in rejected:
        print("负控 %-30s %s" % (label, why))
    print("清单写入 %s" % LOG)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
