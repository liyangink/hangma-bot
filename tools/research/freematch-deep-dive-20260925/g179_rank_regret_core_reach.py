#!/usr/bin/env python3
"""G179：冻结官方父代行动前事实，检验四轴最坏名次原型的核心触达率。"""

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

from collections import Counter
import hashlib
import json
import math
from pathlib import Path

import g11_cross_family_action_atlas as atlas
import g11_longitudinal_route_audit as g11
from g176_joint_guard_coverage_probe import width as original_width


HERE = Path(__file__).resolve().parent
PLAN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G179-RANK-REGRET-CORE-REACH-PREREG-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g179-rank-regret-core-reach-20260928/result.json')


def sha(path: Path) -> str:
    """绑定冻结来源、事前判据与本次程序原始字节。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _support(facts: dict, field: str, *, omit_white: bool = False) -> tuple[int, int]:
    """返回正容量牌码数及公开总容量；未知、重复与布尔冒数均使整窗弃权。"""

    raw = facts.get(field)
    if not isinstance(raw, list):
        raise ValueError(field + " 未知")
    seen: set[str] = set()
    types = capacity = 0
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError(field + " 不是逐码记录")
        code, value = entry.get("code"), entry.get("remaining_estimate")
        if (not isinstance(code, str) or code in seen or type(value) is not int
                or not 0 <= value <= 4):
            raise ValueError(field + " 逐码记录无效")
        seen.add(code)
        if omit_white and code == "白":
            continue
        types += int(value > 0)
        capacity += value
    return types, capacity


def _integer(value, field: str) -> int:
    """显式拒绝 bool 冒充规则向听。"""

    if type(value) is not int:
        raise ValueError(field + " 未知或非整数")
    return value


def _score(value) -> float:
    """只接受有限的冻结原评分。"""

    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("原评分未知或非有限数字")
    return float(value)


def _eligible(row: dict) -> dict[str, dict]:
    """只取合法非白、普通二向听且综合向听不退的本窗弃牌。"""

    parent = row["parent_action"]
    options: dict[str, dict] = {}
    for action, facts in row["legal"].items():
        if not action.startswith("discard:") or action == "discard:白":
            continue
        if (facts.get("standard_shanten_after") != 2 or
                type(facts.get("standard_shanten_after")) is not int or
                type(facts.get("shanten_after")) is not int or
                facts["shanten_after"] > row["legal"][parent]["shanten_after"]):
            continue
        options[action] = facts
    if parent not in options:
        raise ValueError("核心窗口父代不在合法比较集合")
    return options


def _core(row: dict) -> bool:
    """严格复用 G176 的 363 窗入口，包含其原普通型全牌码容量口径。"""

    parent_key = row["parent_action"]
    parent = row["legal"][parent_key]
    wall = row["wall_remaining"]
    if (parent_key == "discard:白" or row["own_melds"] != 0
            or type(wall) is not int or wall <= 20
            or parent.get("shanten_after") not in (1, 2)
            or row["white_count"] != 0 or row["standard"] != 2):
        return False
    pwidth = original_width(parent)
    if pwidth is None:
        return False
    for action, facts in row["legal"].items():
        if action == parent_key or not action.startswith("discard:") or action == "discard:白":
            continue
        shanten = facts.get("shanten_after")
        if type(shanten) is not int or shanten > parent["shanten_after"]:
            continue
        alternate = original_width(facts)
        if (facts.get("standard_shanten_after") == 2 and alternate is not None
                and alternate[0] > pwidth[0] and alternate[1] > pwidth[1]):
            return True
    return False


def _rank(values: dict[str, tuple | float]) -> dict[str, int]:
    """各轴按不同键取稠密名次；越大越好，平手同名次。"""

    order = {value: index for index, value in enumerate(sorted(set(values.values()), reverse=True))}
    return {action: order[value] for action, value in values.items()}


def choose(row: dict) -> dict:
    """最小化四轴最坏名次；并列先保留冻结父代行为。"""

    options = _eligible(row)
    original = row["parent_action"]
    ordinary = {}
    seven = {}
    combined = {}
    scores = {}
    for action, facts in options.items():
        ordinary_types, ordinary_capacity = _support(
            facts, "standard_useful_tiles", omit_white=True)
        _, seven_capacity = _support(facts, "seven_pairs_useful_tiles")
        _, combined_capacity = _support(facts, "useful_tiles")
        seven_need = _integer(facts.get("seven_pairs_shanten_after"), "七对向听")
        combined_need = _integer(facts.get("shanten_after"), "综合向听")
        ordinary[action] = (ordinary_capacity, ordinary_types)
        seven[action] = (-seven_need, seven_capacity)
        combined[action] = (-combined_need, combined_capacity)
        scores[action] = _score(row["scores"].get(action))
    ranks = {axis: _rank(values) for axis, values in {
        "ordinary": ordinary, "seven_pairs": seven,
        "combined": combined, "original_score": scores,
    }.items()}
    regrets = {action: max(axis[action] for axis in ranks.values()) for action in options}
    choice = min(options, key=lambda action: (
        regrets[action], int(action != original), -scores[action], action))
    full_parent = original_width(options[original])
    full_choice = original_width(options[choice])
    if full_parent is None or full_choice is None:
        raise ValueError("核心动作普通型容量未知")
    strict_wider = (choice != original and full_choice[0] > full_parent[0]
                    and full_choice[1] > full_parent[1])
    return {"choice": choice, "parent": original,
            "strict_wider": strict_wider,
            "selected_other_change": choice != original and not strict_wider,
            "parent_regret": regrets[original], "choice_regret": regrets[choice],
            "parent_ranks": {axis: rank[original] for axis, rank in ranks.items()},
            "choice_ranks": {axis: rank[choice] for axis, rank in ranks.items()},
            "parent_ordinary_nonwhite": ordinary[original],
            "choice_ordinary_nonwhite": ordinary[choice],
            "parent_seven": seven[original], "choice_seven": seven[choice],
            "eligible_count": len(options)}


def main() -> None:
    """仅作行为触达筛查，绝不读取赛果或写入线上策略。"""

    if OUT.exists():
        raise FileExistsError("G179 结果已存在，拒绝覆盖")
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    complete = atlas._complete_ids()
    if len(complete) != 909:
        raise ValueError("G179 完整桌母体漂移")
    rows, coverage = g11._draw_rows(complete, frozen)
    if coverage["accepted_normal_draw_discards"] != 55170:
        raise ValueError("G179 正常弃牌母体漂移")
    result = []
    for row in rows:
        if not _core(row):
            continue
        key = {name: row[name] for name in (
            "room_id", "game_id", "round_no", "seat", "trigger_seq")}
        try:
            decision = choose(row)
            status = "complete"
        except (TypeError, ValueError, KeyError) as exc:
            decision = {"reason": type(exc).__name__ + ": " + str(exc)[:180]}
            status = "abstain"
        result.append({**key, "status": status, **decision})
    if len(result) != 363:
        raise ValueError(f"G179 核心窗计数漂移：{len(result)}，预期 363")
    counts = Counter(row["status"] for row in result)
    counts["strict_wider_changes"] = sum(row.get("strict_wider", False) for row in result)
    counts["other_changes"] = sum(row.get("selected_other_change", False) for row in result)
    counts["unchanged"] = sum(row.get("choice") == row.get("parent") for row in result
                              if row["status"] == "complete")
    scopes = {field: len({row[field] for row in result if row.get("strict_wider")})
              for field in ("room_id", "game_id")}
    pass_gate = counts["strict_wider_changes"] >= 60 and scopes["game_id"] >= 40
    payload = {
        "schema": "g179-rank-regret-core-reach/1",
        "source_sha256": {"plan": sha(PLAN), "script": sha(Path(__file__)),
                          "frozen_rooms": sha(atlas.FROZEN),
                          "g11_result": sha(g11.OUT),
                          "g176_result": sha(_project_file(_PROJECT_ROOT, HERE / "evidence/g176-joint-guard-coverage-20260928/result.json"))},
        "complete_official_tables": len(complete),
        "source_accepted_draw_discards": coverage["accepted_normal_draw_discards"],
        "core_windows": len(result),
        "counts": dict(sorted(counts.items())),
        "strict_wider_scopes": {"rooms": scopes["room_id"], "tables": scopes["game_id"]},
        "preregistered_reach_gate_pass": pass_gate,
        "rows": result,
        "boundary": "结果盲已看父代动作前行为覆盖，不是桌赛收益、时限通过或上线候选。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"counts": payload["counts"], "scopes": payload["strict_wider_scopes"],
                      "gate": pass_gate}, ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
