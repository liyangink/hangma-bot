#!/usr/bin/env python3
"""第1步报价层探针活动检查：κ/VARREF/PURPOSES[1] 在真实 RF1 视图面板上的行为差异。

变体构造（单一自由度，文本常数替换 + 资格门控包装）：
- κ 只乘 speedof 支持报价 == 线性替换 SPEEDCAP（speedof 对 SPEEDCAP 线性）；
- VARREF 改支持核宽度饱和点；PURPOSES[1] 只改 k=1 保白先验（k≥2 不动）。
- 资格门控（工作计划 §5 首批口径）：仅当实持白数≤1、全部动作类型为 discard、
  墙余已知且 >20（RETENTION）时走变体评分，其余窗口逐字节沿用父版路径
  ——实持≥2白窗口因此构造性保持父版首选（多白保护）。
- kappa_1.0 变体（常数不动、仅门控包装）必须在全部窗口与父版输出完全一致
  （补丁执行链等价性检查）。
输出：等价性/保护断言结果、各变体在资格窗口上的真实改选数（按白数分层）、
改选示例与分差。不做桌赛、不改线上包；评分是排序点，不是积分。
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from pathlib import Path

_ROOT = next(p for p in Path(__file__).resolve().parents
             if (p / "src/hangma_bot/bootstrap.py").is_file())
sys.path.insert(0, str(_ROOT / "src"))

RF1_SOURCE = _ROOT / "prebuilt/vip-g37-rf1-compiled-v1/source.py"
RETENTION = 20

VARIANTS = {
    "kappa_1.0": [],
    "kappa_0.9": [("SPEEDCAP = 4.8", "SPEEDCAP = 4.32")],
    "kappa_1.1": [("SPEEDCAP = 4.8", "SPEEDCAP = 5.28")],
    "varref_3": [("VARREF = 4.0", "VARREF = 3.0")],
    "varref_6": [("VARREF = 4.0", "VARREF = 6.0")],
    "purposes1_1.25": [("PURPOSES = (0.0, 2.5, 6.0, 13.0, 26.0)",
                        "PURPOSES = (0.0, 1.25, 6.0, 13.0, 26.0)")],
    "purposes1_5.0": [("PURPOSES = (0.0, 2.5, 6.0, 13.0, 26.0)",
                       "PURPOSES = (0.0, 5.0, 6.0, 13.0, 26.0)")],
}

# M3 白容量折扣变体：白码支持容量乘折扣（他家暗白不确定性的粗代理）。
# 两处文本插入：新增常数 + routewait 的 stock 构造处对白码槽位缩放。
M3_TEMPLATE = {
    "whitecap_0.5": [
        ("RETENTION = 20", "RETENTION = 20\nWHITECAPDISCOUNT = 0.5"),
        ("""    stock = []
    for slot in range(len(waiting["unseen_capacities"])):
        stock.append(stockof(slot, waiting))""",
         """    stock = []
    for slot in range(len(waiting["unseen_capacities"])):
        cell = stockof(slot, waiting)
        if codeindex.get("白") == slot:
            cell = (cell[0] * WHITECAPDISCOUNT, cell[1], cell[2])
        stock.append(cell)"""),
    ],
}

# M2 紧迫度×阶梯变体：他家副露组数达到阈值时，凸阶梯价整体乘紧迫度因子。
# 实现为三处文本插入（常数、ladder 缩放、score_actions 内按窗口设置全局 _URGENCY）。
# 方向=对手推进时偏好更近路线（与历史证伪的"宽度换距离"相反）。
M2_TEMPLATE = {}
for _boost, _melds, _label in ((1.25, 2, "m2_u1.25_melds2"), (1.5, 2, "m2_u1.5_melds2"), (1.25, 3, "m2_u1.25_melds3")):
    M2_TEMPLATE[_label] = [
        ("OPPRISK = 0.12",
         "OPPRISK = 0.12\nURGENCY_BOOST = " + repr(_boost) + "\nURGENCY_MELDS = " + repr(_melds) + "\n_URGENCY = 1.0"),
        ("""    linear = FORMCOST * steps
    tail = steps - TAILOFF
    if tail > 0:
        return linear + TAILQUAD * tail * tail""",
         """    linear = FORMCOST * _URGENCY * steps
    tail = steps - TAILOFF
    if tail > 0:
        return linear + TAILQUAD * _URGENCY * tail * tail"""),
        ("""    pressure = 1.0 / (1.0 + OPPDECAY * float(opponents))""",
         """    global _URGENCY
    _URGENCY = URGENCY_BOOST if opponents >= URGENCY_MELDS else 1.0
    pressure = 1.0 / (1.0 + OPPDECAY * float(opponents))"""),
    ]

GATE = '''

def _probe_eligible(view):
    state = view.get("visible_state") or {}
    hand = state.get("my_hand") or []
    whites = sum(1 for code in hand if code == "白")
    if state.get("drawn_tile") == "白":
        whites += 1
    if whites >= 2:
        return False
    actions = view.get("actions") or []
    if not actions or any(a.get("action_type") != "discard" for a in actions):
        return False
    wall = state.get("remaining_tile_count")
    return wall is not None and wall > 20


def score_actions(view):
    if _probe_eligible(view):
        return _probe_score_actions(view)
    return _parent_score_actions(view)
'''


def build_variant(base: str, replacements: list) -> str:
    text = base
    for old, new in replacements:
        if text.count(old) != 1:
            raise ValueError("替换位置不唯一: " + old)
        text = text.replace(old, new, 1)
    text = text.replace("def score_actions(view):", "def _probe_score_actions(view):", 1)
    parent = base.replace("def score_actions(view):", "def _parent_score_actions(view):", 1)
    return text + GATE + "\n\n" + parent


def load_module(text: str) -> dict:
    namespace: dict = {"__name__": "probe_variant"}
    exec(compile(text, "<probe-variant>", "exec"), namespace)
    return namespace


def window_whites(view: dict) -> int:
    state = view["visible_state"]
    return (sum(1 for c in state["my_hand"] if c == "白")
            + (1 if state.get("drawn_tile") == "白" else 0))


def eligible(view: dict) -> bool:
    state = view["visible_state"]
    if window_whites(view) >= 2:
        return False
    actions = view.get("actions") or []
    if not actions or any(a.get("action_type") != "discard" for a in actions):
        return False
    wall = state.get("remaining_tile_count")
    return wall is not None and wall > 20


def chosen(result: dict):
    ordered = sorted(result["entries"], key=lambda e: (-e["score"], e["action_key"]))
    return ordered[0]["action_key"], ordered


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", required=True, help="views.jsonl.gz 面板路径")
    parser.add_argument("--out", required=True, help="输出 JSON 路径")
    parser.add_argument("--ineligible-sample", type=int, default=200)
    args = parser.parse_args()

    base = RF1_SOURCE.read_text(encoding="utf-8")
    parent_ns = load_module(base)
    parent_score = parent_ns["score_actions"]

    views = [json.loads(line)["view"] for line in gzip.open(args.panel, "rt")]
    eligible_rows, ineligible_rows = [], []
    for view in views:
        (eligible_rows if eligible(view) else ineligible_rows).append(view)

    variants = {name: load_module(build_variant(base, repl))["score_actions"]
                for name, repl in VARIANTS.items()}
    for name, repl in list(M3_TEMPLATE.items()) + list(M2_TEMPLATE.items()):
        text = base
        for old, new in repl:
            if text.count(old) != 1:
                raise ValueError("模板替换位置不唯一: " + name + " " + old[:60])
            text = text.replace(old, new, 1)
        gated = (text.replace("def score_actions(view):", "def _probe_score_actions(view):", 1)
                 + GATE + "\n\n"
                 + base.replace("def score_actions(view):", "def _parent_score_actions(view):", 1))
        variants[name] = load_module(gated)["score_actions"]

    parent_results = {}
    for view in eligible_rows + ineligible_rows[:args.ineligible_sample]:
        parent_results[id(view)] = parent_score(view)

    report = {"panel": str(args.panel), "unique_views": len(views),
              "eligible_windows": len(eligible_rows),
              "ineligible_windows": len(ineligible_rows),
              "variants": {}, "asserts": {}}

    # 等价性：kappa_1.0 与父版在全部已评分窗口输出逐字段一致。
    mismatches = 0
    for view in eligible_rows + ineligible_rows[:args.ineligible_sample]:
        a = json.dumps(parent_results[id(view)], sort_keys=True)
        b = json.dumps(variants["kappa_1.0"](view), sort_keys=True)
        if a != b:
            mismatches += 1
    report["asserts"]["kappa_1.0_identical_to_parent"] = mismatches == 0
    report["asserts"]["kappa_1.0_mismatches"] = mismatches

    for name, score in variants.items():
        if name == "kappa_1.0":
            continue
        flips = {"total": 0, "0w": 0, "1w": 0}
        examples = []
        gate_violations = 0
        for view in eligible_rows:
            parent_result = parent_results[id(view)]
            parent_key, parent_ordered = chosen(parent_result)
            variant_result = score(view)
            variant_key, _ = chosen(variant_result)
            if variant_key != parent_key:
                whites = 0 if window_whites(view) == 0 else 1
                flips["total"] += 1
                flips[f"{whites}w"] += 1
                if len(examples) < 12:
                    delta = next((e["score"] for e in variant_result["entries"]
                                  if e["action_key"] == variant_key), None)
                    examples.append({"view_sha_prefix": hashlib.sha256(
                        json.dumps(view, sort_keys=True).encode()).hexdigest()[:12],
                        "whites": window_whites(view),
                        "parent": parent_key, "variant": variant_key,
                        "variant_top_score": delta})
        for view in ineligible_rows[:args.ineligible_sample]:
            a = json.dumps(parent_results[id(view)], sort_keys=True)
            b = json.dumps(score(view), sort_keys=True)
            if a != b:
                gate_violations += 1
        report["variants"][name] = {"flips": flips, "examples": examples,
                                    "gate_violations_in_ineligible_sample": gate_violations}

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(json.dumps({"eligible": len(eligible_rows), "ineligible": len(ineligible_rows),
                      "asserts": report["asserts"],
                      "flips": {k: v["flips"] for k, v in report["variants"].items()},
                      "gate_violations": {k: v["gate_violations_in_ineligible_sample"]
                                          for k, v in report["variants"].items()}},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
