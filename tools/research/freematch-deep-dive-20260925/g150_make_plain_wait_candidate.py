#!/usr/bin/env python3
"""G150：从冻结 R18 v2 源码生成一白普通听牌窄改选候选。"""

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

from hangma_bot.policy.r18_integrated_positive_v2 import (
    R18_INTEGRATED_POSITIVE_V2_SHA256,
    R18_INTEGRATED_POSITIVE_V2_SOURCE,
)


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/candidates/G150-ONE-WHITE-PLAIN-WAIT-V1.py')

WRAPPER = r'''

def g150_capacity(action, kind):
    """只读完整生产条件结算，返回普通自摸的纯平胡或普通型爆头公开容量。"""
    if action.get("value_coverage") != "complete":
        return None
    routes = action.get("routes")
    if routes is None:
        return None
    amount = 0
    seen = set()
    for route in routes:
        conditions = route.get("conditions") or {}
        if route.get("followup_discard") is not None or conditions.get("draw_kind") != "normal":
            return None
        settlement = route.get("conditional_settlement") or {}
        details = settlement.get("details")
        fan = settlement.get("fan")
        matched = ((kind == "plain" and details is not None
                    and tuple(details) == ("平胡",) and fan == 1)
                   or (kind == "baotou" and details is not None
                       and len(details) > 0 and details[0] == "平胡"
                       and "爆头" in details))
        for tile in route.get("useful_tiles") or ():
            code = tile.get("code")
            remaining = tile.get("remaining_estimate")
            if (not isinstance(code, str) or code in seen
                    or type(remaining) is not int or not 0 <= remaining <= 4):
                return None
            seen.add(code)
            if matched:
                amount += remaining
    return amount


def g150_support(action):
    """把公开未见有效张仅当容量上界；未知直接放弃改选。"""
    useful = action.get("useful_tiles")
    if useful is None:
        return None
    amount = 0
    for tile in useful:
        remaining = tile.get("remaining_estimate")
        if type(remaining) is not int or not 0 <= remaining <= 4:
            return None
        amount += remaining
    return amount


def score_actions(view):
    """仅对一白普通零向听、无当前爆头的纯平胡等待容量作有界重排。"""
    parent = r18_parent_score_actions(view)
    if parent.get("status") != "SCORED":
        return parent
    visible = view.get("visible_state") or {}
    actions = view.get("actions") or ()
    if visible.get("phase") != "draw" or not actions:
        return parent
    hand = visible.get("my_hand")
    rule_state = visible.get("rule_state") or {}
    wall = visible.get("remaining_tile_count")
    if (hand is None or rule_state.get("baotou") is True
            or type(wall) is not int or wall <= 20
            or any(a.get("action_type") == "hu" and a.get("is_legal") is True
                   for a in actions)):
        return parent
    white = hand.count("白")
    drawn = visible.get("drawn_tile")
    seat = visible.get("seat")
    melds = visible.get("melds")
    if (type(seat) is not int or not 0 <= seat <= 3 or melds is None
            or len(melds) != 4):
        return parent
    if drawn == "白" and len(hand) != 14 - 3 * len(melds[seat]):
        white += 1
    if white != 1:
        return parent
    scores = {item["action_key"]: item["score"] for item in parent["entries"]}
    top = min(scores, key=lambda key: (-scores[key], key))
    by_key = {a.get("action_key"): a for a in actions}
    anchor = by_key.get(top)
    if (anchor is None or anchor.get("action_type") != "discard"
            or top == "discard:白"
            or type(anchor.get("shanten_after")) is not int
            or type(anchor.get("standard_shanten_after")) is not int
            or anchor["standard_shanten_after"] != 0):
        return parent
    old_plain = g150_capacity(anchor, "plain")
    old_baotou = g150_capacity(anchor, "baotou")
    old_support = g150_support(anchor)
    if old_plain is None or old_plain <= 0 or old_baotou != 0 or old_support is None:
        return parent
    old_seven = anchor.get("seven_pairs_shanten_after")
    eligible = []
    for action in actions:
        key = action.get("action_key")
        if (key == top or action.get("action_type") != "discard"
                or action.get("is_legal") is not True or key == "discard:白"
                or type(action.get("shanten_after")) is not int
                or action["shanten_after"] != anchor["shanten_after"]
                or type(action.get("standard_shanten_after")) is not int
                or action["standard_shanten_after"] != 0):
            continue
        seven = action.get("seven_pairs_shanten_after")
        if ((old_seven is None and seven is not None)
                or (type(old_seven) is int and
                    (type(seven) is not int or seven > old_seven))):
            continue
        new_support = g150_support(action)
        new_plain = g150_capacity(action, "plain")
        new_baotou = g150_capacity(action, "baotou")
        if (new_support is None or new_support < old_support
                or new_plain is None or new_plain < old_plain + 3
                or new_baotou != 0 or key not in scores
                or scores[top] - scores[key] > 3.0):
            continue
        eligible.append((new_plain, scores[key], key))
    if not eligible:
        return parent
    chosen = min(eligible, key=lambda row: (-row[0], -row[1], row[2]))[2]
    entries = []
    for entry in parent["entries"]:
        next_entry = dict(entry)
        if entry["action_key"] == chosen:
            next_entry["score"] = scores[top] + 0.25
            next_entry["trace"] = dict(entry.get("trace") or {},
                                       g150_plain_wait={"version": "g150-v1",
                                                        "anchor": top,
                                                        "anchor_plain_capacity": old_plain,
                                                        "chosen_plain_capacity":
                                                        g150_capacity(by_key[chosen], "plain")})
        entries.append(next_entry)
    return {"status": "SCORED", "entries": entries,
            "reason": parent.get("reason", "") + "；G150 一白普通听牌等待容量受控改选"}
'''


def main() -> None:
    """生成一次且拒绝覆盖，候选身份由其完整源码摘要冻结。"""
    if OUT.exists():
        raise FileExistsError("G150 候选源码已存在")
    source = R18_INTEGRATED_POSITIVE_V2_SOURCE
    if (hashlib.sha256(source.encode()).hexdigest()
            != R18_INTEGRATED_POSITIVE_V2_SHA256):
        raise ValueError("冻结父代源码摘要漂移")
    needle = "def score_actions(view):"
    if source.count(needle) != 1:
        raise ValueError("冻结父代评分函数接缝不唯一")
    code = source.replace(needle, "def r18_parent_score_actions(view):", 1) + WRAPPER
    compile(code, str(OUT), "exec")
    OUT.write_text(code, encoding="utf-8")
    print(hashlib.sha256(OUT.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
