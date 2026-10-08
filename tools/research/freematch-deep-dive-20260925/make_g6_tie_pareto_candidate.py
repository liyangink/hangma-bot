#!/usr/bin/env python3
"""从冻结 R18 v2 逐字生成 G6 研究候选；绝不改写线上源码。"""

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

import hashlib
from pathlib import Path
import sys

ROOT = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))
from hangma_bot.policy.r18_integrated_positive_v2 import (  # noqa: E402
    R18_INTEGRATED_POSITIVE_V2_SOURCE,
    R18_INTEGRATED_POSITIVE_V2_SHA256,
)
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402

OUTPUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/candidates/G6-TIE-ROUTE-PARETO-V1.py')

HELPERS = '''\ndef g6_capacity(tiles):
    """只加总规则层公开未见有效容量；缺失时返回未知。"""
    if tiles is None:
        return None
    total = 0.0
    for item in tiles:
        value = item.get("remaining_estimate")
        if value is None or value is True or value is False:
            return None
        amount = float(value)
        if amount - amount != 0 or amount < 0.0 or amount > 4.0:
            return None
        total += amount
    return total


def g6_shanten(action, field):
    """三个向听字段均须是合法有限整数；不把未知当 0。"""
    value = action.get(field)
    if value is None or value is True or value is False:
        return None
    number = float(value)
    if number - number != 0 or number < -1.0 or number > 13.0 or number != int(number):
        return None
    return number

'''

BLOCK = '''    # G6：只在父代普通弃牌完全平分、无机会覆盖时，用分牌型帕累托事实打破平分。
    g6_target = None
    g6_top = None
    if not overlay_triggered and dominance_best_key is None and not seven_value_triggered and not piao2_triggered and not cfb_triggered:
        for g6_entry in output_entries:
            if g6_top is None or g6_entry.get("score") > g6_top.get("score") or (g6_entry.get("score") == g6_top.get("score") and g6_entry.get("action_key") < g6_top.get("action_key")):
                g6_top = g6_entry
        if g6_top is not None:
            g6_top_key = g6_top.get("action_key")
            if g6_top_key[:8] == "discard:" and g6_top_key[-1] in "wbt":
                g6_base = None
                for g6_action in actions:
                    if g6_action.get("action_key") == g6_top_key and g6_action.get("is_legal") is True and g6_action.get("fact_kind") == "hand_progress":
                        g6_base = g6_action
                if g6_base is not None:
                    g6_base_c = g6_capacity(g6_base.get("useful_tiles"))
                    g6_base_s = g6_capacity(g6_base.get("standard_useful_tiles"))
                    g6_base_q = g6_capacity(g6_base.get("seven_pairs_useful_tiles"))
                    g6_base_sh = g6_shanten(g6_base, "shanten_after")
                    g6_base_std = g6_shanten(g6_base, "standard_shanten_after")
                    g6_base_seven = g6_shanten(g6_base, "seven_pairs_shanten_after")
                    if g6_base_c is not None and g6_base_s is not None and g6_base_q is not None and g6_base_sh is not None and g6_base_std is not None and g6_base_seven is not None:
                        g6_best_s = None
                        g6_best_c = None
                        g6_best_q = None
                        for g6_action in actions:
                            g6_key = g6_action.get("action_key")
                            if g6_key[:8] != "discard:" or g6_key[8:] not in "东南西北中发" or g6_key[8:] == wealth or hand.count(g6_key[8:]) != 1:
                                continue
                            if g6_action.get("is_legal") is not True or g6_action.get("fact_kind") != "hand_progress":
                                continue
                            g6_entry_score = None
                            for g6_entry in output_entries:
                                if g6_entry.get("action_key") == g6_key:
                                    g6_entry_score = g6_entry.get("score")
                            if g6_entry_score != g6_top.get("score"):
                                continue
                            g6_c = g6_capacity(g6_action.get("useful_tiles"))
                            g6_s = g6_capacity(g6_action.get("standard_useful_tiles"))
                            g6_q = g6_capacity(g6_action.get("seven_pairs_useful_tiles"))
                            g6_sh = g6_shanten(g6_action, "shanten_after")
                            g6_std = g6_shanten(g6_action, "standard_shanten_after")
                            g6_seven = g6_shanten(g6_action, "seven_pairs_shanten_after")
                            if g6_c is None or g6_s is None or g6_q is None or g6_sh is None or g6_std is None or g6_seven is None:
                                continue
                            if g6_sh > g6_base_sh or g6_std > g6_base_std or g6_seven > g6_base_seven or g6_c < g6_base_c or g6_q < g6_base_q or g6_s <= g6_base_s:
                                continue
                            if g6_target is None or g6_s > g6_best_s or (g6_s == g6_best_s and (g6_c > g6_best_c or (g6_c == g6_best_c and (g6_q > g6_best_q or (g6_q == g6_best_q and g6_key < g6_target))))):
                                g6_target = g6_key
                                g6_best_s = g6_s
                                g6_best_c = g6_c
                                g6_best_q = g6_q
    if g6_target is not None:
        g6_entries = []
        for g6_entry in output_entries:
            if g6_entry.get("action_key") == g6_target:
                g6_trace = dict(g6_entry.get("trace"), g6_tie_route_pareto="v1")
                g6_entries.append({"action_key": g6_target, "score": g6_entry.get("score") + 0.001, "trace": g6_trace})
            else:
                g6_entries.append(g6_entry)
        output_entries = g6_entries
        reason = reason + "；G6 分牌型严格帕累托平分打破"
'''


def main() -> int:
    parent = R18_INTEGRATED_POSITIVE_V2_SOURCE
    digest = hashlib.sha256(parent.encode("utf-8")).hexdigest()
    if digest != R18_INTEGRATED_POSITIVE_V2_SHA256:
        raise RuntimeError("冻结父代摘要不符")
    helper_anchor = "\ndef score_actions(view):\n"
    return_anchor = '    return {"status": "SCORED", "entries": output_entries, "reason": reason}\n'
    if parent.count(helper_anchor) != 1 or parent.count(return_anchor) != 1:
        raise RuntimeError("冻结父代接缝发生变化")
    source = parent.replace(helper_anchor, HELPERS + helper_anchor, 1)
    source = source.replace(return_anchor, BLOCK + return_anchor, 1)
    ActionValueScorer("research:g6_tie_route_pareto_v1", source)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(source, encoding="utf-8")
    print("source_sha256", hashlib.sha256(source.encode("utf-8")).hexdigest())
    print("output", OUTPUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
