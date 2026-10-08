#!/usr/bin/env python3
"""C27 第二步 maker：按第一步定位到的条件格，机械生成定向候选。

候选只能改**打分**：在父代冻结源码的非弃牌固定罚之后插入一个常数减免块，
条件谓词由第一步 C27-PREREG-CLAIM-CELLS.md 第四节的同一份格定义机械打印。
不新增规则、不读隐藏信息、不重排候选。

生成方式与 C18/C24 同一条：锚点替换 + 断言锚点唯一 + compile；谓词只使用受限
执行器白名单内的名字与方法（禁下划线开头标识符、while、try、属性写入）。

四个臂（判定臂 + 对照臂）：
* CELL-R6 / CELL-R10：非退化定位格 F3:same（鸣后向听与鸣前相同，占缺口 70.0%）
* FAM-R6：全部鸣牌候选 +6 —— 预登记字面 argmin（F9:no）的等价物，同时是
  「整族放宽」对照臂（与 P31 已关闭的 CLAIM60_30 同形）
* TENPAI-R6：追加臂，听牌格 F1:sh0（占缺口 56.9%，C23 已发布的最大格）

用法：
    UV_CACHE_DIR=/tmp/uv-cache .venv/bin/python \
        review/freematch-deep-dive-20260925/make_c27_candidates.py
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
from hangma_bot.policy.r18_integrated_positive_v2 import (  # noqa: E402
    R18_INTEGRATED_POSITIVE_V2_SOURCE,
)

NL = chr(10)
Q = chr(34)
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/candidates')
CELLS_JSON = _project_file(_PROJECT_ROOT, ROOT / ".team-work" / "c27-claim-cells" / "cells.json")
ANCHOR = "            total += fixed" + NL + "            total = round(total, 6)" + NL
"""父代源码里非弃牌分支的固定罚之后（缩进 12 空格，已对冻结源码核对）。"""

PRIMS = {
    "sh0": ("pass_shanten", "c27bs == 0"),
    "sh1": ("pass_shanten", "c27bs == 1"),
    "sh2": ("pass_shanten", "c27bs == 2"),
    "sh3p": ("pass_shanten", "c27bs >= 3"),
    "peng": ("has_peng", "c27haspeng"),
    "chi": ("has_peng", "(not c27haspeng) and c27haschi"),
    "down": ("delta_shanten", "c27dsh < 0"),
    "same": ("delta_shanten", "c27dsh == 0"),
    "up": ("delta_shanten", "c27dsh > 0"),
    "wider": ("delta_width", "c27dw > 0"),
    "equal": ("delta_width", "c27dw == 0"),
    "narrower": ("delta_width", "c27dw < 0"),
    "m0": ("melds", "c27ml == 0"),
    "m1": ("melds", "c27ml == 1"),
    "m2p": ("melds", "c27ml >= 2"),
    "t0_2": ("turn", "c27tn <= 2"),
    "t3_6": ("turn", "(c27tn >= 3) and (c27tn <= 6)"),
    "t7p": ("turn", "c27tn >= 7"),
    "w60p": ("wall", "c27wallok and (c27wl >= 60)"),
    "w40_59": ("wall", "c27wallok and (c27wl >= 40) and (c27wl < 60)"),
    "wlt40": ("wall", "c27wallok and (c27wl < 40)"),
    "number": ("tile_class", "c27isnum"),
    "honor": ("tile_class", "not c27isnum"),
    "yes": ("baotou", "action.get(" + Q + "baotou_after" + Q + ") is True"),
    "no": ("baotou", "action.get(" + Q + "baotou_after" + Q + ") is not True"),
}

BLOCKS = {
    "pass_shanten": [
        "c27pass = None",
        "for c27a in actions:",
        "    if c27a.get(" + Q + "action_type" + Q + ") == " + Q + "pass" + Q + ":",
        "        c27pass = c27a",
        "        break",
        "if c27pass is None:",
        "    for c27a in actions:",
        "        if c27a.get(" + Q + "action_type" + Q + ") == " + Q + "discard" + Q + ":",
        "            c27pass = c27a",
        "            break",
        "c27bs = None",
        "if c27pass is not None:",
        "    c27bs = c27pass.get(" + Q + "shanten_after" + Q + ")",
        "    if (c27bs is True) or (c27bs is False):",
        "        c27bs = None",
    ],
    "has_peng": [
        "c27haspeng = False",
        "c27haschi = False",
        "for c27a in actions:",
        "    if c27a.get(" + Q + "action_type" + Q + ") == " + Q + "peng" + Q + ":",
        "        c27haspeng = True",
        "    elif c27a.get(" + Q + "action_type" + Q + ") == " + Q + "chi" + Q + ":",
        "        c27haschi = True",
    ],
    "delta_shanten": [
        "c27dsh = None",
        "if (c27bs is not None) and (shanten is not None) and (shanten is not True) and (shanten is not False):",
        "    c27dsh = shanten - c27bs",
    ],
    "delta_width": [
        "c27dw = None",
        "c27ptiles = None",
        "if c27pass is not None:",
        "    c27ptiles = c27pass.get(" + Q + "useful_tiles" + Q + ")",
        "c27atiles = action.get(" + Q + "useful_tiles" + Q + ")",
        "if (c27ptiles is not None) and (c27atiles is not None):",
        "    c27okw = True",
        "    c27bw = 0.0",
        "    for c27t in c27ptiles:",
        "        c27r = c27t.get(" + Q + "remaining_estimate" + Q + ")",
        "        if (c27r is None) or (c27r is True) or (c27r is False):",
        "            c27okw = False",
        "            break",
        "        c27bw = c27bw + c27r",
        "    c27aw = 0.0",
        "    if c27okw:",
        "        for c27t in c27atiles:",
        "            c27r = c27t.get(" + Q + "remaining_estimate" + Q + ")",
        "            if (c27r is None) or (c27r is True) or (c27r is False):",
        "                c27okw = False",
        "                break",
        "            c27aw = c27aw + c27r",
        "    if c27okw:",
        "        c27dw = c27aw - c27bw",
    ],
    "melds": ["c27ml = len(melds[seat])"],
    "turn": ["c27tn = len(discards[seat])"],
    "wall": [
        "c27wl = visible.get(" + Q + "remaining_tile_count" + Q + ")",
        "c27wallok = (c27wl is not None) and (c27wl is not True) and (c27wl is not False)",
    ],
    "tile_class": [
        "c27isnum = False",
        "c27last = visible.get(" + Q + "last_discard" + Q + ")",
        "if c27last is not None:",
        "    c27code = c27last.get(" + Q + "tile" + Q + ")",
        "    if (c27code is not None) and (len(c27code) >= 2) and (c27code[0] in (" + Q + "1" + Q + ", " + Q + "2" + Q + ", " + Q + "3" + Q + ", " + Q + "4" + Q + ", " + Q + "5" + Q + ", " + Q + "6" + Q + ", " + Q + "7" + Q + ", " + Q + "8" + Q + ", " + Q + "9" + Q + ")):",
        "        c27isnum = True",
    ],
    "baotou": [],
}

#: 计算块之间的依赖（被依赖者必须先打印，否则谓词会引用未定义名字）。
DEPS = {
    "delta_shanten": ("pass_shanten",),
    "delta_width": ("pass_shanten",),
}

ORDER = ("pass_shanten", "has_peng", "delta_shanten", "delta_width",
         "melds", "turn", "wall", "tile_class")

#: 生成清单：(文件名, 谓词特征, 减免, 说明)。谓词为 None 表示全部鸣牌候选命中。
TARGETS = [
    ("OPTY-R18-C27-CELL-R6.py", ("same",), "6.0",
     "非退化定位格 F3:same（鸣后向听与鸣前相同）"),
    ("OPTY-R18-C27-CELL-R10.py", ("same",), "10.0",
     "非退化定位格 F3:same，抵消吃碰全部固定罚"),
    ("OPTY-R18-C27-FAM-R6.py", None, "6.0",
     "全部鸣牌候选（预登记字面 argmin F9:no 占 99.2% 机会，其候选等价于此臂）"),
    ("OPTY-R18-C27-TENPAI-R6.py", ("sh0",), "6.0",
     "追加臂：听牌格 F1:sh0（占缺口 56.9%）"),
]


def build_block(parts, relief):
    """按格谓词生成插入块（只打印真正需要的计算，缩进基准 12 空格）。"""

    needed = []
    for part in parts or ():
        block = PRIMS[part][0]
        for name in DEPS.get(block, ()) + (block,):
            if name not in needed:
                needed.append(name)
    lines = ["if (kind == " + Q + "peng" + Q + ") or (kind == " + Q + "chi" + Q + "):"]
    for name in ORDER:
        if name in needed:
            for raw in BLOCKS[name]:
                lines.append("    " + raw)
    if parts is None:
        lines.append("    total = total + %s" % relief)
        lines.append("    total = round(total, 6)")
    else:
        predicate = " and ".join("(" + PRIMS[part][1] + ")" for part in parts)
        lines.append("    if %s:" % predicate)
        lines.append("        total = total + %s" % relief)
        lines.append("        total = round(total, 6)")
    return NL.join("            " + line for line in lines) + NL


def emit(parts, relief, name, note, panel):
    block = build_block(parts, relief)
    assert R18_INTEGRATED_POSITIVE_V2_SOURCE.count(ANCHOR) == 1, "锚点在父代源码里不唯一"
    candidate = R18_INTEGRATED_POSITIVE_V2_SOURCE.replace(ANCHOR, ANCHOR + block)
    assert candidate.count(ANCHOR) == 1, "替换后锚点不唯一"
    assert block in candidate, "插入块缺失"
    path = _project_file(_PROJECT_ROOT, OUT / name)
    path.write_text(candidate, encoding="utf-8")
    compile(candidate, str(path), "exec")
    added = candidate.count(NL) - R18_INTEGRATED_POSITIVE_V2_SOURCE.count(NL)
    print("wrote %s（插入 %d 行，减免 %s；%s%s）"
          % (name, added, relief, note, panel))
    return added


def main():
    payload = json.loads(CELLS_JSON.read_text(encoding="utf-8"))
    located = payload.get("located_cell") or {}
    refined = payload.get("located_cell_refined") or {}
    index = {entry["cell"]: entry for entry in payload["primary"]["cells"]}
    gap = payload["primary"]["total_gap"]
    print("第一步读数：总差 %+.4f；字面判定格 %s（占缺口 %.1f%%，机会占比 %.1f%%）；"
          "非退化判定格 %s（占缺口 %.1f%%，机会占比 %.1f%%）"
          % (gap, located.get("cell"),
             100 * located.get("contribution", 0) / gap,
             100 * located.get("share", 0),
             refined.get("cell"),
             100 * refined.get("contribution", 0) / gap,
             100 * refined.get("share", 0)))
    if not index:
        raise SystemExit("cells.json 里没有格表：%s" % CELLS_JSON)
    for name, parts, relief, note in TARGETS:
        panel = ""
        if parts and len(parts) == 1:
            key = parts[0]
            for cell_key, entry in sorted(index.items()):
                if cell_key.endswith(":" + key):
                    panel = ("；该格贡献 %+.4f（占缺口 %.1f%%），机会 %d（占比 %.1f%%）"
                             % (entry["contribution"],
                                100 * entry["contribution"] / gap, entry["chances"],
                                100 * entry["share"]))
                    break
        emit(parts, relief, name, note, panel)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
