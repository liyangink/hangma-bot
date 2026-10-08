#!/usr/bin/env python3
"""G176：只读官方父代动作前事实，计算一摸多路线提案硬保护的行为上界。"""

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

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

import g11_cross_family_action_atlas as atlas
import g11_longitudinal_route_audit as g11


HERE = Path(__file__).resolve().parent
PLAN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G176-JOINT-GUARD-COVERAGE-PROBE-PLAN-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g176-joint-guard-coverage-20260928/result.json')


def sha(path: Path) -> str:
    """绑定只读父代来源和本程序原始字节。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def width(facts: dict) -> tuple[int, int] | None:
    """普通型正容量牌码数及公开容量；未知绝不冒充零。"""
    raw = facts.get("standard_useful_tiles")
    if not isinstance(raw, list):
        return None
    values = [item.get("remaining_estimate") for item in raw]
    if any(type(value) is not int or not 0 <= value <= 4 for value in values):
        return None
    return sum(value > 0 for value in values), sum(values)


def _number(value) -> int | float | None:
    """布尔不是评分数字。"""
    return value if type(value) in (int, float) else None


def main() -> None:
    """分别计所有当前可比动作与零白二向听严格宽面入口。"""
    if OUT.exists():
        raise FileExistsError("G176 结果已存在，拒绝覆盖")
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    complete = atlas._complete_ids()
    if len(complete) != 909:
        raise ValueError("G176 完整桌母体漂移")
    rows, coverage = g11._draw_rows(complete, frozen)
    buckets = defaultdict(Counter)
    scopes = defaultdict(lambda: {"rooms": set(), "tables": set()})
    for row in rows:
        parent_key = row["parent_action"]
        parent = row["legal"][parent_key]
        wall = row["wall_remaining"]
        if (parent_key == "discard:白" or row["own_melds"] != 0
                or type(wall) is not int or wall <= 20
                or parent.get("shanten_after") not in (1, 2)):
            continue
        pscore = _number(row["scores"].get(parent_key))
        prisk = _number(row["traces"][parent_key].get("risk_units"))
        priver = _number(row["traces"][parent_key].get("river_part"))
        if pscore is None or prisk is None or priver is None:
            raise ValueError("G176 父代评分轨迹不完整")
        pwidth = width(parent)
        candidates = {"general": [], "zero_white_strict_std2": []}
        for key, facts in row["legal"].items():
            if key == parent_key or not key.startswith("discard:") or key == "discard:白":
                continue
            shanten = facts.get("shanten_after")
            if type(shanten) is not int or shanten > parent["shanten_after"]:
                continue
            score = _number(row["scores"].get(key))
            risk = _number(row["traces"].get(key, {}).get("risk_units"))
            river = _number(row["traces"].get(key, {}).get("river_part"))
            if score is None or risk is None or river is None:
                raise ValueError("G176 合法备选的 R18 评分轨迹缺失")
            fact = {"action": key, "risk": risk <= prisk,
                    "river": river >= priver,
                    "score": pscore - score <= 2}
            candidates["general"].append(fact)
            alternate_width = width(facts)
            if (row["white_count"] == 0 and row["standard"] == 2
                    and facts.get("standard_shanten_after") == 2
                    and pwidth is not None and alternate_width is not None
                    and alternate_width[0] > pwidth[0]
                    and alternate_width[1] > pwidth[1]):
                candidates["zero_white_strict_std2"].append(fact)
        for mode, options in candidates.items():
            if not options:
                continue
            bucket = ("0" if row["white_count"] == 0 else
                      "1" if row["white_count"] == 1 else "2plus")
            name = mode + "/white_" + bucket
            counts = buckets[name]
            counts["possible_before_protection"] += 1
            for label, predicate in (
                    ("risk", lambda item: item["risk"]),
                    ("river", lambda item: item["river"]),
                    ("score", lambda item: item["score"]),
                    ("all", lambda item: item["risk"] and item["river"] and item["score"])):
                if any(predicate(item) for item in options):
                    counts["possible_after_" + label] += 1
                    scopes[(name, label)]["rooms"].add(row["room_id"])
                    scopes[(name, label)]["tables"].add(row["game_id"])
    payload = {
        "schema": "g176-joint-guard-coverage/1",
        "source_sha256": {"plan": sha(PLAN),
                          "frozen_rooms": sha(atlas.FROZEN),
                          "script": sha(Path(__file__)),
                          "g11_result": sha(g11.OUT)},
        "complete_official_tables": len(complete),
        "source_accepted_draw_discards": coverage["accepted_normal_draw_discards"],
        "counts": {name: dict(sorted(count.items()))
                   for name, count in sorted(buckets.items())},
        "scopes": {name + "/" + guard: {
            key: len(ids) for key, ids in members.items()}
                   for (name, guard), members in sorted(scopes.items())},
        "boundary": "已看官方父代行动前候选上界；尚未施加多路线价值、四根短名单或完整桌收益。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                              indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"counts": payload["counts"],
                      "scopes": payload["scopes"]},
                     ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
