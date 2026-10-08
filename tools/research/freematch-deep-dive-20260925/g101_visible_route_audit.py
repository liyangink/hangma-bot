#!/usr/bin/env python3
"""G101：用生产规则与 G99 联合叶普查新官方目标窗的两条条件路线。"""

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
import gzip
import hashlib
import json
from pathlib import Path

import c31_action_layer_gap as c31
import g52_shared_horizon as g52
import g99_joint_successor_route_audit as g99
from hangma_bot.application.audit_codec import candidate_value_facts_to_json
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g101-new-free-wider-route-20260928/selection')
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G101-NEW-FREE-WIDER-ROUTE-PREREG-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g101-new-free-wider-route-20260928/route')
FIELDS = (
    "conditional_retaining_natural_need",
    "conditional_retaining_natural_progress",
    "conditional_retaining_second_hu_value",
)


def sha(path: Path) -> str:
    """结果绑定选择集与联合叶程序的字节身份。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def first_hu_entry(value: dict, seat: int) -> dict:
    """一次本人自摸路线按生产番数分普通／二番以上公开支持容量。"""
    if value.get("coverage") != "complete":
        raise ValueError("生产条件分值事实不完整")
    ordinary = special = ordinary_mass = special_mass = 0
    for route in value.get("routes") or []:
        if (route.get("followup_discard") is not None or
                (route.get("conditions") or {}).get("draw_kind") != "normal"):
            raise ValueError("一次摸牌路线非立即普通自摸")
        settlement = route.get("conditional_settlement") or {}
        fan = settlement.get("fan")
        delta = settlement.get("score_delta") or []
        if type(fan) is not int or fan <= 0 or len(delta) != 4 or type(delta[seat]) is not int:
            raise ValueError("生产条件分值事实番数或四座结算缺失")
        capacity = sum(tile["remaining_estimate"] for tile in route.get("useful_tiles") or [])
        if fan >= 2:
            special += capacity
            special_mass += capacity * delta[seat]
        else:
            ordinary += capacity
            ordinary_mass += capacity * delta[seat]
    return {"ordinary_capacity": ordinary, "special_capacity": special,
            "ordinary_mass": ordinary_mass, "special_mass": special_mass}


def compare(row: dict) -> dict:
    """根动作已冻结；每臂均使用同一当前可见观察和合法后继叶。"""
    obs = observation_from_json(row["observation"])
    rules = c31.RULES.analyze(obs, value_limits=c31.VALUE_LIMITS)
    legal = {item.action_key: item for item in rules.legal_candidates}
    arms = {}
    for label, key in (("parent", row["parent_action"]),
                       ("alternate", row["alternate_action"])):
        candidate = legal.get(key)
        if candidate is None or candidate.value_facts is None or candidate.facts is None:
            raise ValueError("目标动作缺生产合法事实")
        value = candidate_value_facts_to_json(candidate.value_facts)
        tree = g52.evaluate_root(obs, {"action_key": key, "value_facts": value},
                                 c31.RULE_CONFIG, include_all_leaves=True)
        if tree["root_whites_held"] != row["white_before"]:
            raise ValueError("根弃牌后白板数不守恒")
        arms[label] = {
            "first_hu": first_hu_entry(value, obs.seat),
            "first_draw_public_capacity": tree["first_draw_public_capacity"],
            "first_hu_mass": tree["first_hu_mass"],
            "restricted": g99.summarize(tree, "restricted"),
            "unrestricted": g99.summarize(tree, "unrestricted"),
        }
    delta = {}
    for mode in ("restricted", "unrestricted"):
        delta[mode] = g99.pair_delta(arms["parent"][mode], arms["alternate"][mode])
    for key in ("ordinary_capacity", "special_capacity", "ordinary_mass", "special_mass"):
        delta["first_hu_" + key] = (arms["alternate"]["first_hu"][key]
                                     - arms["parent"]["first_hu"][key])
    return {"key": row["key"], "white_before": row["white_before"],
            "shanten": row["shanten"], "wall_remaining": row["remaining_tile_count"],
            "parent_action": row["parent_action"], "alternate_action": row["alternate_action"],
            "parent_width": row["parent_width"], "alternate_width": row["alternate_width"],
            "arms": arms, "delta": delta, "status": "complete"}


def sign(value: float | None) -> str:
    """未知单列；浮点结算仅按明确非零方向汇总。"""
    if value is None:
        return "unknown"
    if value > 1e-9:
        return "positive"
    if value < -1e-9:
        return "negative"
    return "zero"


def main() -> None:
    """全量目标窗逐项计数；保留失败原因，不从中挑有利样本。"""
    if OUT.exists():
        raise FileExistsError("G101 路线审计已有结果，拒绝覆盖")
    selected = json.loads((_project_file(_PROJECT_ROOT, SOURCE / "result.json")).read_text(encoding="utf-8"))
    if selected["outcome_labels_opened"] is not False:
        raise ValueError("G101 选择集不是结果盲")
    rows = [json.loads(line) for line in gzip.open(_project_file(_PROJECT_ROOT, SOURCE / "rows.jsonl.gz"), "rt", encoding="utf-8")]
    if len(rows) != selected["counts"]["target_windows"]:
        raise ValueError("G101 目标窗逐行数量不符")
    output = []
    counts = Counter()
    field_rooms: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        try:
            item = compare(row)
            counts["complete"] += 1
            for field in FIELDS:
                for mode in ("restricted", "unrestricted"):
                    direction = sign(item["delta"][mode][field])
                    label = mode + "/" + field + "/" + direction
                    counts[label] += 1
                    field_rooms[label].add(row["key"][0])
            for field in ("ordinary_capacity", "special_capacity"):
                direction = sign(item["delta"]["first_hu_" + field])
                label = "first_hu_" + field + "/" + direction
                counts[label] += 1
                field_rooms[label].add(row["key"][0])
        except (ValueError, TypeError) as exc:
            reason = type(exc).__name__ + ": " + str(exc)[:160]
            item = {"key": row["key"], "status": "unavailable", "reason": reason}
            counts["unavailable"] += 1
            counts["unavailable/" + reason] += 1
        output.append(item)
    result = {
        "schema": "g101-new-free-visible-route-audit/1", "outcome_labels_opened": False,
        "input_sha256": {"selection": sha(_project_file(_PROJECT_ROOT, SOURCE / "result.json")),
                         "selection_rows": sha(_project_file(_PROJECT_ROOT, SOURCE / "rows.jsonl.gz")),
                         "prereg": sha(PREREG), "script": sha(Path(__file__)),
                         "g52_tree": sha(_project_file(_PROJECT_ROOT, HERE / "g52_shared_horizon.py")),
                         "g99_joint": sha(_project_file(_PROJECT_ROOT, HERE / "g99_joint_successor_route_audit.py"))},
        "total_targets": len(rows), "counts": dict(sorted(counts.items())),
        "field_room_coverage": {key: len(value) for key, value in sorted(field_rooms.items())},
        "boundary": "条件两次本人自摸不建模他家先胡、未来抓打圈真实归属及实墙分配；只辨行为特征。",
    }
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    body = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in output)
    (_project_file(_PROJECT_ROOT, OUT / "rows.jsonl.gz")).write_bytes(gzip.compress(body.encode("utf-8"), compresslevel=9, mtime=0))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
