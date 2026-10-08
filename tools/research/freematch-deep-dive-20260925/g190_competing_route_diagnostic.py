#!/usr/bin/env python3
"""G190：旧开发教师的普通听牌、高番入口与终局收支交叉诊断。"""

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
from hashlib import sha256
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g161-multi-action-development-teacher-20260928/rows.jsonl')
MANIFEST = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g161-multi-action-development-teacher-20260928/result.json')
OUTPUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g190-competing-route-diagnostic-20260929/result.json')
COMPONENTS = ("plain_self_win", "special_self_win", "other_win_payment", "draw_delta")


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def terminal_parts(arm: dict, seat: int) -> tuple[str, dict[str, int]]:
    """按官方本局结算把本座分差放入唯一终点；不解释后续桌赛。"""
    settled = arm["settlement"]
    delta = settled["score_delta"][seat]
    values = dict.fromkeys(COMPONENTS, 0)
    if settled["is_draw"]:
        kind = "draw"
        values["draw_delta"] = delta
    elif settled["winner_seat"] == seat:
        kind = "plain_self_win" if settled["fan"] == 1 else "special_self_win"
        values[kind] = delta
    else:
        kind = "other_win"
        values["other_win_payment"] = delta
    if sum(values.values()) != delta or delta != arm["focal_score_delta"]:
        raise ValueError("G190 官方本局收支不守恒")
    return kind, values


def first_event(parent: int | None, alternate: int | None) -> str:
    """比较实际续打中首次普通听牌/高番一摸入口；None 表示终局前未到达。"""
    if parent is None:
        return "neither" if alternate is None else "alternate_only"
    if alternate is None:
        return "parent_only"
    if alternate < parent:
        return "alternate_earlier"
    if parent < alternate:
        return "parent_earlier"
    return "same_index"


def aggregate(items: list[dict]) -> dict:
    """每对相关世界描述性聚合；不把世界当独立确认样本。"""
    transitions = Counter((item["parent_terminal"], item["alternate_terminal"])
                          for item in items)
    roots = defaultdict(list)
    for item in items:
        roots[item["root_index"]].append(item["delta"])
    return {
        "related_world_pairs": len(items),
        "windows": len({item["window_index"] for item in items}),
        "roots": len(roots),
        "sum_delta": sum(item["delta"] for item in items),
        "mean_delta": (sum(item["delta"] for item in items) / len(items)
                       if items else None),
        "component_sum_delta": {
            name: sum(item["components"][name] for item in items)
            for name in COMPONENTS
        },
        "terminal_transitions": {
            f"{before}->{after}": count
            for (before, after), count in sorted(transitions.items())
        },
        "root_delta_sums": {str(root): sum(values)
                            for root, values in sorted(roots.items())},
        "highfan_entry_comparison": dict(sorted(Counter(
            item["highfan_comparison"] for item in items).items())),
    }


def main() -> None:
    """绑定已完成 G161 原文，拒绝覆盖一次性探索结果。"""
    if OUTPUT.exists():
        raise FileExistsError("G190 探索结果已存在；拒绝覆盖")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if (manifest.get("status") != "complete"
            or manifest.get("windows_completed") != 49
            or manifest.get("rows_sha256") != digest(SOURCE)):
        raise ValueError("G190 来源未完成或摘要漂移")
    rows = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines()]
    if len(rows) != 49:
        raise ValueError("G190 开发窗数量不符")
    paired = []
    initial_facts = []
    for window_index, row in enumerate(rows):
        if len(row["world_pairs"]) != 33:
            raise ValueError("G190 相关世界数量不符")
        first_state = None
        for world in row["world_pairs"]:
            parent, alternate = world["parent"], world["alternate"]
            state = {
                side: {field: arm["focal_draw_trajectory"][0][field]
                       for field in ("standard_shanten_after", "seven_pairs_shanten_after",
                                     "white_after_discard", "one_draw_win_routes",
                                     "one_draw_highfan_routes")}
                for side, arm in (("parent", parent), ("alternate", alternate))
            }
            if first_state is None:
                first_state = state
            elif state != first_state:
                raise ValueError("G190 行动刚完成时的规则事实随隐藏世界变化")
            parent_kind, parent_parts = terminal_parts(parent, row["focal_seat"])
            alternate_kind, alternate_parts = terminal_parts(alternate, row["focal_seat"])
            components = {name: alternate_parts[name] - parent_parts[name]
                          for name in COMPONENTS}
            delta = world["focal_delta_alt_minus_parent"]
            if sum(components.values()) != delta:
                raise ValueError("G190 成对分量不守恒")
            paired.append({
                "window_index": window_index,
                "root_index": row["root_index"],
                "mix": row["mix"],
                "white_before": row["white_before"],
                "sample_key": world["sample_key"],
                "ready_comparison": first_event(parent["first_ready_draw_index"],
                                                alternate["first_ready_draw_index"]),
                "highfan_comparison": first_event(parent["first_highfan_draw_index"],
                                                  alternate["first_highfan_draw_index"]),
                "parent_terminal": parent_kind,
                "alternate_terminal": alternate_kind,
                "delta": delta,
                "components": components,
            })
        initial_facts.append({"window_index": window_index,
                              "root_index": row["root_index"],
                              "mix": row["mix"],
                              "white_before": row["white_before"],
                              **first_state})
    if len(paired) != 1617:
        raise ValueError("G190 世界总数不符")
    summaries = {}
    for mix in ("H", "M"):
        for white in (0, 1):
            scope = [item for item in paired if item["mix"] == mix
                     and item["white_before"] == white]
            groups = {
                "all": scope,
                "alternate_ready_first": [item for item in scope if item["ready_comparison"]
                                          in ("alternate_only", "alternate_earlier")],
                "parent_ready_first": [item for item in scope if item["ready_comparison"]
                                       in ("parent_only", "parent_earlier")],
                "alternate_only_ready": [item for item in scope if item["ready_comparison"]
                                          == "alternate_only"],
                "alternate_ready_first_highfan_parent_first": [
                    item for item in scope
                    if item["ready_comparison"] in ("alternate_only", "alternate_earlier")
                    and item["highfan_comparison"] in ("parent_only", "parent_earlier")],
            }
            summaries[f"{mix}/{white}"] = {name: aggregate(items)
                                            for name, items in groups.items()}
            initial = [item for item in initial_facts if item["mix"] == mix
                       and item["white_before"] == white]
            ties = {field: sum(item["parent"][field] == item["alternate"][field]
                               for item in initial)
                    for field in ("standard_shanten_after", "seven_pairs_shanten_after",
                                  "white_after_discard", "one_draw_win_routes",
                                  "one_draw_highfan_routes")}
            summaries[f"{mix}/{white}"]["initial_ties"] = {
                "windows": len(initial), **ties}
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "schema": "g190-competing-route-diagnostic/1",
        "source_sha256": {"g161_manifest": digest(MANIFEST),
                          "g161_rows": digest(SOURCE),
                          "script": digest(Path(__file__))},
        "samples": len(paired),
        "initial_rule_facts": initial_facts,
        "summaries": summaries,
        "boundary": ("已见开发教师的事后路径交叉诊断；首次听牌与高番入口均是动作后的中介，"
                     "条件分组不具有因果或独立确认解释；不得据此调整上线权重。"),
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True,
                                 indent=2) + "\n", encoding="utf-8")
    print(json.dumps({scope: {group: {"n": facts["related_world_pairs"],
                                      "sum": facts["sum_delta"],
                                      "components": facts["component_sum_delta"]}
                                for group, facts in groups.items() if group != "initial_ties"}
                      for scope, groups in summaries.items()},
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
