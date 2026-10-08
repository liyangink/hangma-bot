#!/usr/bin/env python3
"""G30：从冻结 R18 v2 字节生成仅研究用简约边张弃牌候选。"""

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

from hangma_bot.policy.action_value_executor import static_check
from hangma_bot.policy.r18_integrated_positive_v2 import (
    R18_INTEGRATED_POSITIVE_V2_SHA256,
    R18_INTEGRATED_POSITIVE_V2_SOURCE,
)


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/candidates/G30-EDGE-TIE-ONEWHITE-V1.py')
OVERLAY = '''

def g30_edge_key(action_key):
    """对合法非白弃牌取固定简约键；数值越小越先弃。"""
    code = action_key[8:]
    if len(code) == 1:
        return (0, code)
    if len(code) != 2 or code[-1] not in "wbt" or code[0] not in "123456789":
        return None
    rank = int(code[0])
    if rank == 1 or rank == 9:
        level = 1
    elif rank == 2 or rank == 8:
        level = 2
    else:
        level = 3
    return (level, code)


def g30_eligible(action):
    """只接受生产已给出完整普通/综合逐牌事实的合法弃牌。"""
    if action is None or action.get("is_legal") is not True or action.get("action_type") != "discard":
        return False
    key = action.get("action_key")
    if key is None or key[:8] != "discard:" or key == "discard:白":
        return False
    std = action.get("standard_shanten_after")
    seven = action.get("seven_pairs_shanten_after")
    if std is True or std is False or std != 1:
        return False
    if seven is not None and (seven is True or seven is False or seven <= 2):
        return False
    return action.get("standard_useful_tiles") is not None and action.get("useful_tiles") is not None


def g30_equal_vector(left, right, field):
    """同牌码、同公开剩余张数的逐项集合；重复码或未知直接拒绝。"""
    a = left.get(field)
    b = right.get(field)
    if a is None or b is None or len(a) != len(b):
        return False
    used = []
    for entry in a:
        code = entry.get("code")
        amount = entry.get("remaining_estimate")
        if code is None or amount is None or amount is True or amount is False or code in used:
            return False
        used.append(code)
        hits = 0
        for other in b:
            if other.get("code") == code and other.get("remaining_estimate") == amount:
                hits += 1
        if hits != 1:
            return False
    return True


def score_actions(view):
    """只在相同即时牌效和近分的持一白弃牌窗重排一次。"""
    result = g30_base_score_actions(view)
    if result.get("status") != "SCORED":
        return result
    visible = view.get("visible_state")
    actions = view.get("actions")
    entries = result.get("entries")
    if visible is None or actions is None or entries is None or visible.get("phase") != "draw":
        return result
    rule = visible.get("rule_state")
    melds = visible.get("melds")
    hand = visible.get("my_hand")
    seat = visible.get("seat")
    if rule is None or rule.get("wealth_god") != "白" or melds is None or hand is None or seat is None:
        return result
    if seat is True or seat is False or seat < 0 or seat > 3 or len(melds) != 4:
        return result
    white_count = hand.count("白")
    drawn = visible.get("drawn_tile")
    if drawn == "白" and len(hand) != 14 - 3 * len(melds[seat]):
        white_count += 1
    if white_count != 1:
        return result
    top = None
    for entry in entries:
        key = entry.get("action_key")
        score = entry.get("score")
        if top is None or score > top.get("score") or (score == top.get("score") and key < top.get("action_key")):
            top = entry
    if top is None or top.get("action_key")[:8] != "discard:":
        return result
    parent = None
    for action in actions:
        if action.get("action_key") == top.get("action_key"):
            parent = action
            break
    if not g30_eligible(parent):
        return result
    parent_edge = g30_edge_key(top.get("action_key"))
    if parent_edge is None:
        return result
    alternative = None
    alternative_entry = None
    for entry in entries:
        key = entry.get("action_key")
        if key == top.get("action_key") or key[:8] != "discard:":
            continue
        score = entry.get("score")
        gap = top.get("score") - score
        if gap < 0 or gap > 3:
            continue
        action = None
        for item in actions:
            if item.get("action_key") == key:
                action = item
                break
        if not g30_eligible(action):
            continue
        if not g30_equal_vector(parent, action, "standard_useful_tiles"):
            continue
        if not g30_equal_vector(parent, action, "useful_tiles"):
            continue
        if alternative_entry is None or score > alternative_entry.get("score") or (score == alternative_entry.get("score") and key < alternative_entry.get("action_key")):
            alternative = action
            alternative_entry = entry
    if alternative_entry is None:
        return result
    target_key = alternative_entry.get("action_key")
    target_edge = g30_edge_key(target_key)
    if target_edge is None or not (target_edge < parent_edge):
        return result
    output = []
    for entry in entries:
        if entry.get("action_key") == target_key:
            trace = dict(entry.get("trace"), g30_edge_tie="one_white_v1")
            output.append({"action_key": target_key, "score": top.get("score") + 1.0, "trace": trace})
        else:
            output.append(entry)
    return {"status": "SCORED", "entries": output,
            "reason": result.get("reason") + "；G30 持一白相同逐码牌效按弃字牌/边张键重排"}
'''


def main() -> None:
    """拒绝覆盖候选，确认冻结父代摘要和沙箱静态检查。"""

    if OUT.exists():
        raise SystemExit("G30 候选源码已存在，拒绝覆盖")
    source = R18_INTEGRATED_POSITIVE_V2_SOURCE
    if hashlib.sha256(source.encode()).hexdigest() != R18_INTEGRATED_POSITIVE_V2_SHA256:
        raise ValueError("R18 v2 冻结源码摘要漂移")
    marker = "def score_actions(view):"
    if source.count(marker) != 1:
        raise ValueError("R18 v2 主入口不能唯一改名")
    candidate = source.replace(marker, "def g30_base_score_actions(view):", 1) + OVERLAY
    static_check(candidate)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(candidate, encoding="utf-8")
    print(hashlib.sha256(candidate.encode()).hexdigest())


if __name__ == "__main__":
    main()
