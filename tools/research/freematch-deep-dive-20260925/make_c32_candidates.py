#!/usr/bin/env python3
"""C32 候选生成器：把「有边界的增量候选」机械落成候选源码。

候选形状**冻结**在 C32-PREREG-CARDS-BOUNDED-CANDIDATE.md 第 6 节：
* 只改打分（在父代非弃牌固定罚之后的同一锚点插入），不改合法性、不重排候选表、不读隐藏信息；
* 剂量上限 +6，**不**把整个 F3:same 族抬到 +10；
* 候选面不可得「跟打后爆头」（受限执行器静态拒绝 import 与白名单外属性），因此
  「爆头可达性」只能用 action.baotou_after is True（动作层继承态）。

产物（candidates/）：
  OPTY-R18-C32-DOSE-C6K6.py      V1 主臂：dsh==0 ∧ dw>=6 -> +6；dsh==0 ∧ 0<dw<6 -> +3
  OPTY-R18-C32-DOSE-C6K3.py      V1 敏感性 k=3
  OPTY-R18-C32-DOSE-C6K9.py      V1 敏感性 k=9
  OPTY-R18-C32-RERANK-R6.py      V2 重排：剂量仍 +6；窗级门禁 ml<=1 ∧ wall>=40；
                                 窗内只把 +6 发给综合键 K 最优的鸣牌候选
  OPTY-R18-C32-DOSE-C6-TENPAI.py V3 新窗审计：V1 主臂 + 听牌窗(bs==0 ∧ dw>=6) -> +6
  OPTY-R18-C32-AUDIT-TENPAI9.py  预登记外审计臂：听牌窗(bs==0 ∧ dw>=6) -> +9
                                 （只用于回答「CELL-R6 未触发的新窗」是否可达，不参与候选判定）

用法：
    UV_CACHE_DIR=/tmp/uv-cache .venv/bin/python \
        review/freematch-deep-dive-20260925/make_c32_candidates.py
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
    R18_INTEGRATED_POSITIVE_V2_SHA256,
    R18_INTEGRATED_POSITIVE_V2_SOURCE,
)

NL = chr(10)
Q = chr(34)
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/candidates')
LOG = _project_file(_PROJECT_ROOT, ROOT / ".team-work" / "c32-cards" / "make-candidates.json")
ANCHOR = "            total += fixed" + NL + "            total = round(total, 6)" + NL
"""父代源码里非弃牌分支的固定罚之后（缩进 12 空格，已对冻结源码核对）。"""

GUARD = "if (kind == " + Q + "peng" + Q + ") or (kind == " + Q + "chi" + Q + "):"

#: 各计算块的源码行（缩进基准 12 空格；块之间按依赖顺序打印）。
BLOCKS = {
    "pass_shanten": [
        "c32pass = None",
        "for c32a in actions:",
        "    if c32a.get(" + Q + "action_type" + Q + ") == " + Q + "pass" + Q + ":",
        "        c32pass = c32a",
        "        break",
        "if c32pass is None:",
        "    for c32a in actions:",
        "        if c32a.get(" + Q + "action_type" + Q + ") == " + Q + "discard" + Q + ":",
        "            c32pass = c32a",
        "            break",
        "c32bs = None",
        "if c32pass is not None:",
        "    c32bs = c32pass.get(" + Q + "shanten_after" + Q + ")",
        "    if (c32bs is True) or (c32bs is False):",
        "        c32bs = None",
    ],
    "delta_shanten": [
        "c32dsh = None",
        "if (c32bs is not None) and (shanten is not None) and (shanten is not True) and (shanten is not False):",
        "    c32dsh = shanten - c32bs",
    ],
    "width": [
        "c32ptiles = None",
        "if c32pass is not None:",
        "    c32ptiles = c32pass.get(" + Q + "useful_tiles" + Q + ")",
        "c32atiles = action.get(" + Q + "useful_tiles" + Q + ")",
        "c32okw = True",
        "c32bw = 0.0",
        "c32aw = 0.0",
        "if c32ptiles is None:",
        "    c32okw = False",
        "if c32atiles is None:",
        "    c32okw = False",
        "if c32okw:",
        "    for c32t in c32ptiles:",
        "        c32r = c32t.get(" + Q + "remaining_estimate" + Q + ")",
        "        if (c32r is None) or (c32r is True) or (c32r is False):",
        "            c32okw = False",
        "            break",
        "        c32bw = c32bw + c32r",
        "if c32okw:",
        "    for c32t in c32atiles:",
        "        c32r = c32t.get(" + Q + "remaining_estimate" + Q + ")",
        "        if (c32r is None) or (c32r is True) or (c32r is False):",
        "            c32okw = False",
        "            break",
        "        c32aw = c32aw + c32r",
        "c32dw = None",
        "if c32okw:",
        "    c32dw = c32aw - c32bw",
    ],
    "melds": ["c32ml = len(melds[seat])"],
    "wall": [
        "c32wl = visible.get(" + Q + "remaining_tile_count" + Q + ")",
        "c32wallok = (c32wl is not None) and (c32wl is not True) and (c32wl is not False)",
    ],
    "exposure": [
        "c32fd = action.get(" + Q + "best_followup_discard" + Q + ")",
        "c32ex = 0",
        "if c32fd is not None:",
        "    for c32row in discards:",
        "        c32ex = c32ex + c32row.count(c32fd)",
        "    for c32meld in melds:",
        "        for c32group in c32meld:",
        "            c32ex = c32ex + c32group.get(" + Q + "tiles" + Q + ").count(c32fd)",
    ],
    "rerank_key": [
        "c32mine = c32aw",
        "if action.get(" + Q + "baotou_after" + Q + ") is True:",
        "    c32mine = c32mine + 6.0",
        "if c32ex == 0:",
        "    c32mine = c32mine - 6.0",
        "c32best = None",
        "c32bestkey = None",
        "for c32a in actions:",
        "    c32akind = c32a.get(" + Q + "action_type" + Q + ")",
        "    if (c32akind == " + Q + "peng" + Q + ") or (c32akind == " + Q + "chi" + Q + "):",
        "        c32atiles2 = c32a.get(" + Q + "useful_tiles" + Q + ")",
        "        c32ok2 = True",
        "        c32w2 = 0.0",
        "        if c32atiles2 is None:",
        "            c32ok2 = False",
        "        if c32ok2:",
        "            for c32t2 in c32atiles2:",
        "                c32r2 = c32t2.get(" + Q + "remaining_estimate" + Q + ")",
        "                if (c32r2 is None) or (c32r2 is True) or (c32r2 is False):",
        "                    c32ok2 = False",
        "                    break",
        "                c32w2 = c32w2 + c32r2",
        "        if c32ok2:",
        "            c32k2 = c32w2",
        "            if c32a.get(" + Q + "baotou_after" + Q + ") is True:",
        "                c32k2 = c32k2 + 6.0",
        "            c32f2 = c32a.get(" + Q + "best_followup_discard" + Q + ")",
        "            c32e2 = 0",
        "            if c32f2 is not None:",
        "                for c32row2 in discards:",
        "                    c32e2 = c32e2 + c32row2.count(c32f2)",
        "                for c32meld2 in melds:",
        "                    for c32group2 in c32meld2:",
        "                        c32e2 = c32e2 + c32group2.get(" + Q + "tiles" + Q + ").count(c32f2)",
        "            if c32e2 == 0:",
        "                c32k2 = c32k2 - 6.0",
        "            if (c32bestkey is None) or (c32k2 > c32bestkey) or ((c32k2 == c32bestkey) and (c32a.get(" + Q + "action_key" + Q + ") < c32best)):",
        "                c32bestkey = c32k2",
        "                c32best = c32a.get(" + Q + "action_key" + Q + ")",
    ],
}

#: 块之间依赖（被依赖者必须先打印）。
ORDER = ("pass_shanten", "delta_shanten", "width", "melds", "wall", "exposure", "rerank_key")

#: 生成清单：(文件名, 需要的块, 剂量代码行, 说明)。
TARGETS = (
    (
        "OPTY-R18-C32-DOSE-C6K6.py",
        ("pass_shanten", "delta_shanten", "width"),
        [
            "if (c32dsh == 0) and (c32dw is not None) and (c32dw >= 6.0):",
            "    total = total + 6.0",
            "    total = round(total, 6)",
            "elif (c32dsh == 0) and (c32dw is not None) and (c32dw > 0.0):",
            "    total = total + 3.0",
            "    total = round(total, 6)",
        ],
        "V1 主臂：鸣后向听不变且真实有效牌张数净增 >= 6 给 +6，弱增益给 +3",
    ),
    (
        "OPTY-R18-C32-DOSE-C6K3.py",
        ("pass_shanten", "delta_shanten", "width"),
        [
            "if (c32dsh == 0) and (c32dw is not None) and (c32dw >= 3.0):",
            "    total = total + 6.0",
            "    total = round(total, 6)",
            "elif (c32dsh == 0) and (c32dw is not None) and (c32dw > 0.0):",
            "    total = total + 3.0",
            "    total = round(total, 6)",
        ],
        "V1 敏感性 k=3（只报读数，不选优）",
    ),
    (
        "OPTY-R18-C32-DOSE-C6K9.py",
        ("pass_shanten", "delta_shanten", "width"),
        [
            "if (c32dsh == 0) and (c32dw is not None) and (c32dw >= 9.0):",
            "    total = total + 6.0",
            "    total = round(total, 6)",
            "elif (c32dsh == 0) and (c32dw is not None) and (c32dw > 0.0):",
            "    total = total + 3.0",
            "    total = round(total, 6)",
        ],
        "V1 敏感性 k=9（只报读数，不选优）",
    ),
    (
        "OPTY-R18-C32-RERANK-R6.py",
        ("pass_shanten", "delta_shanten", "width", "melds", "wall", "exposure",
         "rerank_key"),
        [
            "if (c32dsh == 0) and (c32dw is not None) and (c32dw > 0.0) and (c32ml <= 1) and c32wallok and (c32wl >= 40):",
            "    if c32best == key:",
            "        total = total + 6.0",
            "        total = round(total, 6)",
        ],
        "V2 重排：剂量常数仍 +6；窗级门禁 ml<=1 且墙余>=40；"
        "窗内只把 +6 发给综合键 K = 鸣后真实张数 + 6x爆头可达 - 6x跟打暴露(新牌) 最优者",
    ),
    (
        "OPTY-R18-C32-DOSE-C6-TENPAI.py",
        ("pass_shanten", "delta_shanten", "width"),
        [
            "if (c32dsh == 0) and (c32dw is not None) and (c32dw >= 6.0):",
            "    total = total + 6.0",
            "    total = round(total, 6)",
            "elif (c32bs == 0) and (c32dw is not None) and (c32dw >= 6.0):",
            "    total = total + 6.0",
            "    total = round(total, 6)",
            "elif (c32dsh == 0) and (c32dw is not None) and (c32dw > 0.0):",
            "    total = total + 3.0",
            "    total = round(total, 6)",
        ],
        "V3 新窗审计：V1 主臂 + 听牌窗(过牌向听 0 且真实张数净增 >= 6) 给 +6（不属于有边界候选本体）",
    ),
    (
        "OPTY-R18-C32-AUDIT-TENPAI9.py",
        ("pass_shanten", "delta_shanten", "width"),
        [
            "if (c32bs == 0) and (c32dw is not None) and (c32dw >= 6.0):",
            "    total = total + 9.0",
            "    total = round(total, 6)",
        ],
        "预登记外审计臂：听牌窗 +9，只用于回答「CELL-R6 未触发的新窗能否被有界外剂量开出」",
    ),
)

NEGATIVE_CONTROLS = (
    ("hangma 属性",
     NL.join(("def score_actions(view):",
              "    x = progression.baotou_after_discard((), 1)",
              "    return {" + Q + "status" + Q + ": " + Q + "SCORED" + Q + ", "
              + Q + "entries" + Q + ": []}"))),
    ("import 语句",
     NL.join(("import hangma_bot",
              "def score_actions(view):",
              "    return {" + Q + "status" + Q + ": " + Q + "SCORED" + Q + ", "
              + Q + "entries" + Q + ": []}"))),
)


def build_block(parts, dose_lines):
    """按依赖顺序打印需要的计算块，再把剂量行缩进一层放进鸣牌守卫里。"""

    lines = [GUARD]
    for name in ORDER:
        if name not in parts:
            continue
        for raw in BLOCKS[name]:
            lines.append("    " + raw)
    for raw in dose_lines:
        lines.append("    " + raw)
    return NL.join("            " + line for line in lines) + NL


def emit(name, parts, dose_lines, note, report):
    block = build_block(parts, dose_lines)
    anchors = R18_INTEGRATED_POSITIVE_V2_SOURCE.count(ANCHOR)
    assert anchors == 1, "锚点在父代源码里不唯一：%d" % anchors
    candidate = R18_INTEGRATED_POSITIVE_V2_SOURCE.replace(ANCHOR, ANCHOR + block)
    assert candidate.count(ANCHOR) == 1, "替换后锚点不唯一"
    assert block in candidate, "插入块缺失"
    path = _project_file(_PROJECT_ROOT, OUT / name)
    path.write_text(candidate, encoding="utf-8")
    compile(candidate, str(path), "exec")
    scorer = ActionValueScorer("research:" + path.stem, candidate)   # 静态合同
    added = candidate.count(NL) - R18_INTEGRATED_POSITIVE_V2_SOURCE.count(NL)
    report[name] = {"inserted_lines": added, "note": note, "static_contract": "通过",
                    "scorer": type(scorer).__name__}
    print("wrote %s（插入 %d 行；静态合同通过；%s）" % (name, added, note))
    return added


def main():
    report = {"parent_sha256": R18_INTEGRATED_POSITIVE_V2_SHA256, "candidates": {},
              "negative_controls": {}}
    OUT.mkdir(parents=True, exist_ok=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    for name, parts, dose_lines, note in TARGETS:
        emit(name, parts, dose_lines, note, report["candidates"])
    print()
    print("== 负控：候选源码面不得触及 hangma/import（证明「跟打后爆头」在候选面不可得）")
    for label, source in NEGATIVE_CONTROLS:
        try:
            ActionValueScorer("research:negctl", source)
        except Exception as exc:  # noqa: BLE001
            report["negative_controls"][label] = {
                "rejected": True, "error": type(exc).__name__, "message": str(exc)[:160]}
            print("  %s：被静态拒绝（%s）：%s" % (label, type(exc).__name__, str(exc)[:120]))
        else:
            report["negative_controls"][label] = {"rejected": False}
            print("  %s：**未被拒绝**（负控失败）" % label)
    LOG.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print()
    print("生成清单写入 %s" % LOG)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
