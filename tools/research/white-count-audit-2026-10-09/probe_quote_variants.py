#!/usr/bin/env python3
"""在冻结公开视图上复验RF1探针，父子全部模块绑定隔离。

只检查参数、报价和首选活动，不运行桌赛、不授收益。范围外窗口完整沿用
父版；当前多白保持不等于未来大牌机会保持。输入与输出原件保留在本机。
"""
from __future__ import annotations

import argparse
import ast
import gzip
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

_ROOT = next(p for p in Path(__file__).resolve().parents
             if (p / "src/hangma_bot/bootstrap.py").is_file())
RF1_SOURCE = _ROOT / "prebuilt/vip-g37-rf1-compiled-v1/source.py"
RF1_SOURCE_SHA256 = "63125dcea8d88bb30172be8330fa1ac4c5d500d60c0ee79fd51f7b6cd0f6fd16"

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
M3_TEMPLATE = {"whitecap_0.5": [
    ("RETENTION = 20", "RETENTION = 20\nWHITECAPDISCOUNT = 0.5"),
    ('''    stock = []
    for slot in range(len(waiting["unseen_capacities"])):
        stock.append(stockof(slot, waiting))''',
     '''    stock = []
    for slot in range(len(waiting["unseen_capacities"])):
        cell = stockof(slot, waiting)
        if codeindex.get("白") == slot:
            cell = (cell[0] * WHITECAPDISCOUNT, cell[1], cell[2])
        stock.append(cell)'''),
]}
M2_TEMPLATE = {}
for _boost, _melds, _label in ((1.25, 2, "m2_u1.25_melds2"),
                              (1.5, 2, "m2_u1.5_melds2"),
                              (1.25, 3, "m2_u1.25_melds3")):
    M2_TEMPLATE[_label] = [
        ("OPPRISK = 0.12", "OPPRISK = 0.12\nURGENCY_BOOST = " + repr(_boost)
         + "\nURGENCY_MELDS = " + repr(_melds)),
        ("linear = FORMCOST * steps", "linear = FORMCOST * urgency * steps"),
        ("return linear + TAILQUAD * tail * tail",
         "return linear + TAILQUAD * urgency * tail * tail"),
        ("    pressure = 1.0 / (1.0 + OPPDECAY * float(opponents))",
         "    urgency = URGENCY_BOOST if opponents >= URGENCY_MELDS else 1.0\n"
         "    pressure = 1.0 / (1.0 + OPPDECAY * float(opponents))"),
    ]
RESPONSE_VARIANTS = {
    "skipvalue_0.05": [("SKIPVALUE = 0.10", "SKIPVALUE = 0.05")],
    "skipvalue_0.20": [("SKIPVALUE = 0.10", "SKIPVALUE = 0.20")],
    "claimcost_0.10": [("CLAIMCOST = 0.25", "CLAIMCOST = 0.10")],
    "claimcost_0.40": [("CLAIMCOST = 0.25", "CLAIMCOST = 0.40")],
}

# 同时兼容摸牌单列与已并入手牌的观察；长度不可信时不增强。
# 静态纯函数也供FLEXCOST复用，生成源码没有跨窗口可变状态。
WHITE_GATE_SOURCE = '''
def whitegap_window_whites(view):
    state = view.get("visible_state") or {}
    seat = state.get("seat")
    melds = state.get("melds")
    hand = state.get("my_hand")
    if seat is None or melds is None or hand is None or seat < 0 or seat >= len(melds):
        return None
    size = 13 - 3 * len(melds[seat])
    drawn = state.get("drawn_tile")
    whites = 0
    for code in hand:
        if code == "白":
            whites += 1
    if len(hand) == size:
        return whites + (1 if drawn == "白" else 0)
    if len(hand) == size + 1 and (drawn is None or drawn in hand):
        return whites
    return None

def whitegap_discard_eligible(view):
    whites = whitegap_window_whites(view)
    state = view.get("visible_state") or {}
    actions = view.get("actions") or []
    wall = state.get("remaining_tile_count")
    if whites is None or whites > 1 or state.get("phase") != "draw" or not actions:
        return False
    for action in actions:
        if action.get("action_type") != "discard":
            return False
    return wall is not None and wall > 20

def whitegap_response_eligible(view):
    whites = whitegap_window_whites(view)
    state = view.get("visible_state") or {}
    kinds = {a.get("action_type") for a in (view.get("actions") or [])}
    wall = state.get("remaining_tile_count")
    return (whites is not None and whites <= 1
            and state.get("phase") in ("response_peng", "response_chi")
            and len(kinds) >= 2 and kinds <= {"pass", "chi", "peng"}
            and wall is not None and wall > 20)
'''


class _RenameModuleBindings(ast.NodeTransformer):
    """给父子全部模块常量和函数加前缀，避免辅助函数的晚绑定覆盖。"""

    def __init__(self, names: dict[str, str]):
        self.names = names

    def visit_Name(self, node):
        node.id = self.names.get(node.id, node.id)
        return node

    def visit_FunctionDef(self, node):
        node.name = self.names.get(node.name, node.name)
        return self.generic_visit(node)


class _PassUrgency(ast.NodeTransformer):
    """紧迫度逐调用显式传递，不使用原探针的跨调用global变量。"""

    def visit_FunctionDef(self, node):
        if node.name in ("ladder", "routewait"):
            node.args.args.append(ast.arg(arg="urgency"))
        return self.generic_visit(node)

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name) and node.func.id in ("ladder", "routewait"):
            node.args.append(ast.Name(id="urgency", ctx=ast.Load()))
        return self.generic_visit(node)


def patch_source(base: str, replacements: list) -> str:
    """应用唯一文本补丁；源码漂移或重复命中时报错，不静默跳过。"""
    text = base
    for old, new in replacements:
        if text.count(old) != 1:
            raise ValueError("替换位置不唯一: " + old)
        text = text.replace(old, new, 1)
    if any("URGENCY_BOOST =" in new for _, new in replacements):
        tree = _PassUrgency().visit(ast.parse(text))
        ast.fix_missing_locations(tree)
        text = ast.unparse(tree)
    return text


def clone_source(source: str, prefix: str) -> str:
    """隔离已冻结公式的所有模块绑定，保留表达式计算顺序。"""
    tree = ast.parse(source)
    tree.body = [n for n in tree.body if not (isinstance(n, ast.Expr)
                 and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str))]
    names = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            names[node.name] = prefix.lower() + "_" + node.name
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names[target.id] = prefix.upper() + "_" + target.id
    if "score_actions" not in names or any(isinstance(n, ast.Global) for n in ast.walk(tree)):
        raise ValueError("探针必须有score_actions且没有跨调用global状态")
    tree = _RenameModuleBindings(names).visit(tree)
    ast.fix_missing_locations(tree)
    return ast.unparse(tree)


def build_variant(base: str, replacements: list, *, mode: str = "discard") -> str:
    """生成有完整父版回退的静态探针源码；模式错误或补丁漂移时报错。"""
    if mode not in ("discard", "response"):
        raise ValueError("未知探针模式")
    patched = patch_source(base, replacements)
    gate = "whitegap_" + mode + "_eligible"
    return (clone_source(base, "p") + "\n\n" + clone_source(patched, "e")
            + "\n" + WHITE_GATE_SOURCE + '\n\ndef score_actions(view):\n'
            + "    if " + gate + "(view):\n        return e_score_actions(view)\n"
            + "    return p_score_actions(view)\n")


def flexcost_source(base: str, flexcost: float = 1.0) -> str:
    """仅普通低白响应窗早段吃碰付门清期权价；当前多白整窗保持父版。"""
    if not math.isfinite(flexcost) or flexcost < 0:
        raise ValueError("门清期权价必须为有限非负排序点")
    old = '''        if kind == "chi" or kind == "peng":
            adjustment = SKIPVALUE * float(action["skipped_seats"]) * drawscale - CLAIMCOST'''
    new = '''        if kind == "chi" or kind == "peng":
            flex = 0.0
            my_melds = len(context["melds"][seat])
            if whitegap_response_eligible(view) and wall > 60:
                if my_melds == 0:
                    flex = FLEXCOST
                elif my_melds == 1:
                    flex = 0.5 * FLEXCOST
            adjustment = SKIPVALUE * float(action["skipped_seats"]) * drawscale - CLAIMCOST - flex'''
    return (patch_source(base, [(old, new)]) + "\n\nFLEXCOST = " + repr(flexcost)
            + "\n" + WHITE_GATE_SOURCE)


def load_module(text: str) -> dict:
    """可信离线源码加载；正式choose与受限执行器验收另行进行。"""
    namespace: dict = {"__name__": "whitegap_probe"}
    exec(compile(text, "<whitegap-probe>", "exec"), namespace)
    return namespace


_GATES = load_module(WHITE_GATE_SOURCE)
window_whites = _GATES["whitegap_window_whites"]
eligible = _GATES["whitegap_discard_eligible"]
response_eligible = _GATES["whitegap_response_eligible"]


def chosen(result: dict):
    """按完整有限报价选首选；评分缺失时报错，不把降级算零活动。"""
    if result.get("status") != "SCORED" or not result.get("entries"):
        raise ValueError("探针或父版没有完整评分")
    if any(not math.isfinite(e["score"]) for e in result["entries"]):
        raise ValueError("探针报价不是有限数")
    ordered = sorted(result["entries"], key=lambda e: (-e["score"], e["action_key"]))
    return ordered[0]["action_key"], ordered


def variant_sources(base: str, mode: str) -> dict[str, str]:
    """只构造原分支声明过的参数网格，不根据复验结果追加变体。"""
    if mode == "discard":
        patches = {**VARIANTS, **M3_TEMPLATE, **M2_TEMPLATE}
    elif mode == "response":
        patches = {"equivalence_gate_only": [], **RESPONSE_VARIANTS}
    else:
        raise ValueError("未知探针模式")
    sources = {name: build_variant(base, repl, mode=mode) for name, repl in patches.items()}
    if mode == "response":
        sources.update({"flexcost_1": flexcost_source(base, 1.0),
                        "flexcost_3": flexcost_source(base, 3.0)})
    return sources


def audit_views(base: str, views: list[dict], *, mode: str) -> dict:
    """全量核报价变化、首选、恒等与范围外完整输出；不读后续胜负。"""
    sources = variant_sources(base, mode)
    modules = {name: load_module(text) for name, text in sources.items()}
    parent = load_module(base)["score_actions"]
    gate = eligible if mode == "discard" else response_eligible
    control = "kappa_1.0" if mode == "discard" else "equivalence_gate_only"
    summaries = {name: Counter() for name in modules}
    examples = {name: [] for name in modules}
    strata = Counter()
    for row in views:
        view = row["view"]
        white = window_whites(view)
        active = gate(view)
        strata[str(white) if white in (0, 1) else "2plus" if white is not None else "unknown"] += 1
        reference = parent(view)
        parent_key, parent_entries = chosen(reference)
        legal = {a["action_key"] for a in view["actions"]}
        if {e["action_key"] for e in parent_entries} != legal or len(parent_entries) != len(legal):
            raise ValueError("父版合法根不完整或重复")
        parent_scores = {e["action_key"]: e["score"] for e in parent_entries}
        for name, module in modules.items():
            result = module["score_actions"](view)
            key, entries = chosen(result)
            if {e["action_key"] for e in entries} != legal or len(entries) != len(legal):
                raise ValueError("探针合法根不完整或重复: " + name)
            stats = summaries[name]
            stats["windows"] += 1
            stats["eligible_windows"] += int(active)
            quote_changed = any(e["score"] != parent_scores[e["action_key"]] for e in entries)
            changed = key != parent_key
            stats["quote_changed_windows"] += int(quote_changed)
            stats["first_changed_windows"] += int(changed)
            stats["first_changed_" + str(white)] += int(changed)
            if not active:
                stats["outside_gate_checked"] += 1
                if result != reference:
                    raise ValueError("范围外完整输出漂移: " + name)
            if white is not None and white >= 2:
                stats["multiwhite_full_output_checked"] += 1
            if name == control and result != reference:
                raise ValueError("恒等控制不等于父版")
            if changed and len(examples[name]) < 12:
                examples[name].append({"view_sha256": row["view_sha256"],
                    "source": row.get("source"), "white": white,
                    "parent_first": parent_key, "child_first": key,
                    "parent_entries": parent_entries, "child_entries": entries})
    knobs = ("SPEEDCAP", "VARREF", "PURPOSES", "SKIPVALUE", "CLAIMCOST",
             "WHITECAPDISCOUNT", "URGENCY_BOOST", "URGENCY_MELDS", "FLEXCOST")
    return {"schema": "whitegap-activity-recheck/2", "complete": True, "mode": mode,
        "parent_source_sha256": hashlib.sha256(base.encode()).hexdigest(),
        "tool_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "unique_views": len(views), "white_strata": dict(strata),
        "all_outside_gate_full_outputs_equal": True, "identity_control_full_outputs_equal": True,
        "variants": {name: {"counts": dict(summaries[name]), "examples": examples[name],
            "source_sha256": hashlib.sha256(sources[name].encode()).hexdigest(),
            "effective_knobs": {key: module.get("E_" + key, module.get(key)) for key in knobs
                                if "E_" + key in module or key in module}}
            for name, module in modules.items()},
        "scope": "历史公开视图机械复验；不构成积分或晋级增强；当前多白保持不等于后续机会保护"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", type=Path, nargs="+", required=True, help="冻结views.jsonl.gz文件")
    parser.add_argument("--out", type=Path, required=True, help="输出文件须不存在")
    parser.add_argument("--mode", choices=("discard", "response"), default="discard")
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    base = RF1_SOURCE.read_text(encoding="utf-8")
    if hashlib.sha256(base.encode()).hexdigest() != RF1_SOURCE_SHA256:
        raise ValueError("冻结RF1源码漂移")
    views, seen = [], set()
    input_files = []
    for path in args.panel:
        input_files.append({"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                raw = json.dumps(row["view"], ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":"), allow_nan=False).encode()
                if hashlib.sha256(raw).hexdigest() != row["view_sha256"]:
                    raise ValueError("公开视图SHA与内容不一致: " + str(path))
                if row["view_sha256"] not in seen:
                    seen.add(row["view_sha256"])
                    views.append({**row, "source": str(path.resolve())})
    if not views:
        raise ValueError("评分面板为空")
    report = audit_views(base, views, mode=args.mode)
    report["input_files"] = input_files
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps({"mode": args.mode, "views": len(views),
        "counts": {name: row["counts"] for name, row in report["variants"].items()}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
