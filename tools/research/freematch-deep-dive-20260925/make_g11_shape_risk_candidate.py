#!/usr/bin/env python3
"""从冻结 R18 v2 生成 G11 牌效与弃牌风险冲突的单一受限候选。"""

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

OUTPUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/candidates/G11-SHAPE-RISK-PARETO-V1.py')

HELPERS = '''\ndef g11_support_shape(tiles):
    """公开未见有效张的容量和非零牌种数；事实未知时弃权。"""
    if tiles is None:
        return None
    total = 0.0
    kinds = 0
    for item in tiles:
        value = item.get("remaining_estimate")
        if value is None or value is True or value is False:
            return None
        amount = float(value)
        if amount - amount != 0 or amount < 0.0 or amount > 4.0:
            return None
        total += amount
        if amount > 0.0:
            kinds += 1
    return (total, kinds)


def g11_shanten(action, field):
    """向听数未知不当零；仅接受规则模块生产的有限整数。"""
    value = action.get(field)
    if value is None or value is True or value is False:
        return None
    number = float(value)
    if number - number != 0 or number < -1.0 or number > 13.0 or number != int(number):
        return None
    return number

'''

BLOCK = '''    # G11：窄域比较本窗弃牌与保留摸牌前手牌的摸切，阻止近分风险项压过严格牌效帕累托。
    g11_top = None
    g11_stay = None
    g11_target = None
    if visible.get("phase") == "draw" and not overlay_triggered and dominance_best_key is None and not seven_value_triggered and not piao2_triggered and not cfb_triggered:
        for g11_entry in output_entries:
            if g11_top is None or g11_entry.get("score") > g11_top.get("score") or (g11_entry.get("score") == g11_top.get("score") and g11_entry.get("action_key") < g11_top.get("action_key")):
                g11_top = g11_entry
        if g11_top is not None and drawn is not None and drawn != wealth:
            g11_top_key = g11_top.get("action_key")
            g11_stay_key = "discard:" + drawn
            if g11_top_key[:8] == "discard:" and g11_stay_key != g11_top_key:
                g11_parent_action = None
                g11_stay_action = None
                for g11_action in actions:
                    if g11_action.get("action_key") == g11_top_key:
                        g11_parent_action = g11_action
                    if g11_action.get("action_key") == g11_stay_key:
                        g11_stay_action = g11_action
                for g11_entry in output_entries:
                    if g11_entry.get("action_key") == g11_stay_key:
                        g11_stay = g11_entry
                if g11_parent_action is not None and g11_stay_action is not None and g11_stay is not None:
                    if (g11_parent_action.get("is_legal") is True and g11_stay_action.get("is_legal") is True
                            and g11_parent_action.get("fact_kind") == "hand_progress"
                            and g11_stay_action.get("fact_kind") == "hand_progress"
                            and g11_top.get("trace").get("unknown") is False
                            and g11_stay.get("trace").get("unknown") is False
                            and g11_top.get("score") - g11_stay.get("score") <= 10.0):
                        g11_ps = g11_shanten(g11_parent_action, "standard_shanten_after")
                        g11_ss = g11_shanten(g11_stay_action, "standard_shanten_after")
                        g11_pc = g11_shanten(g11_parent_action, "shanten_after")
                        g11_sc = g11_shanten(g11_stay_action, "shanten_after")
                        g11_pq = g11_shanten(g11_parent_action, "seven_pairs_shanten_after")
                        g11_sq = g11_shanten(g11_stay_action, "seven_pairs_shanten_after")
                        g11_pst = g11_support_shape(g11_parent_action.get("standard_useful_tiles"))
                        g11_sst = g11_support_shape(g11_stay_action.get("standard_useful_tiles"))
                        g11_pct = g11_support_shape(g11_parent_action.get("useful_tiles"))
                        g11_sct = g11_support_shape(g11_stay_action.get("useful_tiles"))
                        if (g11_ps is not None and g11_ss is not None and g11_pc is not None and g11_sc is not None
                                and g11_pst is not None and g11_sst is not None and g11_pct is not None and g11_sct is not None
                                and g11_ps == g11_ss and g11_sc <= g11_pc
                                and g11_sst[0] >= g11_pst[0] and g11_sst[1] > g11_pst[1]
                                and g11_sct[0] >= g11_pct[0]
                                and ((g11_pq is None and g11_sq is None)
                                     or (g11_pq is not None and g11_sq is not None and g11_sq <= g11_pq))):
                            g11_target = g11_stay_key
    if g11_target is not None:
        g11_entries = []
        for g11_entry in output_entries:
            if g11_entry.get("action_key") == g11_target:
                g11_trace = dict(g11_entry.get("trace"), g11_shape_risk_pareto="v1")
                g11_entries.append({"action_key": g11_target, "score": g11_top.get("score") + 1.0, "trace": g11_trace})
            else:
                g11_entries.append(g11_entry)
        output_entries = g11_entries
        reason = reason + "；G11 近分风险与保留原手牌的牌效帕累托冲突"
'''


def main() -> int:
    parent = R18_INTEGRATED_POSITIVE_V2_SOURCE
    if hashlib.sha256(parent.encode("utf-8")).hexdigest() != R18_INTEGRATED_POSITIVE_V2_SHA256:
        raise RuntimeError("冻结父代摘要不符")
    helper_anchor = "\ndef score_actions(view):\n"
    return_anchor = '    return {"status": "SCORED", "entries": output_entries, "reason": reason}\n'
    if parent.count(helper_anchor) != 1 or parent.count(return_anchor) != 1:
        raise RuntimeError("冻结父代接缝发生变化")
    source = parent.replace(helper_anchor, HELPERS + helper_anchor, 1)
    source = source.replace(return_anchor, BLOCK + return_anchor, 1)
    ActionValueScorer("research:g11_shape_risk_pareto_v1", source)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(source, encoding="utf-8")
    print("source_sha256", hashlib.sha256(source.encode("utf-8")).hexdigest())
    print("output", OUTPUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
