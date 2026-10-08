#!/usr/bin/env python3
"""G99：同一合法后继弃牌的自然进展、留白与条件胡事实对账。"""

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
import gzip
import hashlib
import json
from pathlib import Path

import g52_shared_horizon as g52
import g95_wider_discard_same_hand_preflight as g95
from hangma_bot.application.audit_codec import candidate_value_facts_to_json
from hangma_bot.hangma.candidate_facts import FactsAnalysisError


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g96-wider-discard-branch-expansion-20260928/result.json')
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G99-JOINT-SUCCESSOR-ROUTE-AUDIT-PREREG-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g99-joint-successor-route-audit-20260928/result.json.gz')
MODES = ("restricted", "unrestricted")


def sha(path: Path) -> str:
    """返回冻结来源或量具的字节摘要。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def natural_key(leaf: dict) -> tuple:
    """与 G52 普通型选择器完全相同；单叶保留联合事实。"""
    return (leaf["ordinary_natural_need"],
            -leaf["ordinary_natural_progress_capacity"],
            -leaf["mass"], leaf["discard"])


def summarize(root: dict, mode: str) -> dict:
    """第一摸按公开未见容量计权；保白不可行枝单列，不补零。"""
    total = root["first_draw_public_capacity"]
    if total <= 0 or mode not in MODES:
        raise ValueError("第一摸公开容量或模式无效")
    sums = Counter()
    edge_rows = []
    for edge in root["edges"]:
        choices = edge["best_second"][mode]
        leaves = choices.get("legal_leaves")
        if (not leaves or len(leaves) != choices["legal_discard_count"] or
                len({leaf["discard"] for leaf in leaves}) != len(leaves) or
                len({leaf["capacity"] for leaf in leaves}) != 1 or
                leaves[0]["capacity"] <= 0):
            raise ValueError("合法后继叶缺失、重复或容量不等")
        natural = min(leaves, key=natural_key)
        if natural != choices["best_natural_progress"]:
            raise ValueError("G99 全叶普通型最优与 G52 摘要不一致")
        cap = edge["capacity"]
        floor = root["root_whites_held"] + (edge["draw"] == "白")
        retaining = [leaf for leaf in leaves if leaf["whites_held"] >= floor]
        row = {"draw": edge["draw"], "capacity": cap,
               "legal_discard_count": len(leaves),
               "white_floor": floor, "best_natural_discard": natural["discard"],
               "best_hu_discard": choices["best_second_hu"]["discard"],
               "best_hu_differs_from_natural":
                   choices["best_second_hu"]["discard"] != natural["discard"],
               "best_natural_discards_white": natural["whites_held"] < floor,
               "retain_available": bool(retaining)}
        if row["best_hu_differs_from_natural"]:
            sums["hu_natural_disagree_capacity"] += cap
        if row["best_natural_discards_white"]:
            sums["natural_discards_white_capacity"] += cap
        if retaining:
            held = min(retaining, key=natural_key)
            row["best_retaining_discard"] = held["discard"]
            row["best_retaining_leaf"] = held
            row["retaining_differs_from_natural"] = held["discard"] != natural["discard"]
            sums["retaining_feasible_capacity"] += cap
            sums["retaining_need_weighted"] += cap * held["ordinary_natural_need"]
            sums["retaining_progress_weighted"] += cap * held[
                "ordinary_natural_progress_capacity"]
            sums["retaining_second_hu_value_weighted"] += cap * held["mass"] / held[
                "capacity"]
            sums["natural_need_on_retaining_support_weighted"] += cap * natural[
                "ordinary_natural_need"]
            sums["natural_progress_on_retaining_support_weighted"] += cap * natural[
                "ordinary_natural_progress_capacity"]
            if row["retaining_differs_from_natural"]:
                sums["retaining_differs_capacity"] += cap
        edge_rows.append(row)
    if sum(row["capacity"] for row in edge_rows) != total:
        raise ValueError("第一摸公开容量未守恒")
    feasible = sums["retaining_feasible_capacity"]
    return {"first_capacity": total,
            "retaining_feasible_capacity": feasible,
            "hu_natural_disagree_capacity": sums["hu_natural_disagree_capacity"],
            "natural_discards_white_capacity": sums["natural_discards_white_capacity"],
            "retaining_differs_capacity": sums["retaining_differs_capacity"],
            "conditional_retaining_natural_need":
                sums["retaining_need_weighted"] / feasible if feasible else None,
            "conditional_retaining_natural_progress":
                sums["retaining_progress_weighted"] / feasible if feasible else None,
            "conditional_retaining_second_hu_value":
                sums["retaining_second_hu_value_weighted"] / feasible if feasible else None,
            "conditional_natural_need_same_support":
                sums["natural_need_on_retaining_support_weighted"] / feasible
                if feasible else None,
            "conditional_natural_progress_same_support":
                sums["natural_progress_on_retaining_support_weighted"] / feasible
                if feasible else None,
            "edges": edge_rows}


def pair_delta(parent: dict, alternate: dict) -> dict:
    """只在相同公开牌码及共同保白可行支持集上比较两臂。"""
    if (parent["first_capacity"] != alternate["first_capacity"] or
            [(e["draw"], e["capacity"], e["retain_available"])
             for e in parent["edges"]] !=
            [(e["draw"], e["capacity"], e["retain_available"])
             for e in alternate["edges"]]):
        raise ValueError("父代与备选公开摸牌容量或保白可行支持不同")
    fields = ("conditional_retaining_natural_need",
              "conditional_retaining_natural_progress",
              "conditional_retaining_second_hu_value")
    return {field: (alternate[field] - parent[field]
                    if parent[field] is not None and alternate[field] is not None
                    else None) for field in fields}


def main() -> None:
    """重建父代表后计算联合叶；已有证据拒绝覆盖。"""
    if OUT.exists():
        raise FileExistsError("G99 已有结果，拒绝覆盖")
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    if source["schema"] != "g96-wider-discard-branch-expansion/1":
        raise ValueError("G96 来源 schema 漂移")
    contract = json.loads(g95.g93.paired.CONTRACT.read_text(encoding="utf-8"))
    versions = g95.g93.natural.stage.contract_versions_block(contract)
    rows = []
    for old in source["rows"]:
        mix, root, seat = old["mix"], old["root_index"], old["focal_seat"]
        plan = g95.g93.natural.build_seat_stage_plans(
            contract=contract, opponent=mix, root_index=root,
            focal_seat=seat, panel_seed=source["panel_seed"])[0]
        captured, _, rules, _, _, outcome = g95.run_full(
            plan, contract, versions, mix)
        if (plan.table_id != old["table_id"] or
                list(outcome.final_scores or ()) != old["full_parent_final_scores"]):
            raise ValueError("G99 父代表身份或终分漂移")
        if old["status"] == "no_window":
            if captured.world is not None:
                raise ValueError("G99 无目标窗口桌意外命中")
            continue
        if (old["status"] != "paired" or captured.world is None or
                g95.g93.window_key_to_json(captured.request.window_key)
                != old["target_window"] or
                captured.parent_key != old["parent_action"] or
                captured.alternate_key != old["alternate_action"] or
                captured.facts != old["visible_action_facts"]):
            raise ValueError("G99 窗口或动作冻结身份漂移")
        row = {"mix": mix, "root_index": root, "focal_seat": seat,
               "table_id": plan.table_id,
               "target_window": old["target_window"],
               "parent_action": captured.parent_key,
               "alternate_action": captured.alternate_key,
               "white_before": old["white_before"],
               "shanten": captured.facts[captured.parent_key]["standard_shanten_after"]}
        legal = {candidate.action_key: candidate
                 for candidate in captured.request.rules.legal_candidates}
        try:
            pair = {}
            for label, action in (("parent", captured.parent_key),
                                  ("alternate", captured.alternate_key)):
                candidate = legal.get(action)
                if candidate is None or candidate.value_facts is None:
                    raise ValueError("G99 生产分值事实缺失")
                tree = g52.evaluate_root(
                    captured.request.observation,
                    {"action_key": action,
                     "value_facts": candidate_value_facts_to_json(candidate.value_facts)},
                    rules.config, include_all_leaves=True)
                pair[label] = {mode: summarize(tree, mode) for mode in MODES}
            row["status"] = "complete"
            row["pair"] = pair
            row["delta_alt_minus_parent"] = {
                mode: pair_delta(pair["parent"][mode], pair["alternate"][mode])
                for mode in MODES
            }
        except (ValueError, FactsAnalysisError) as exc:
            row["status"] = "unavailable"
            row["reason"] = type(exc).__name__ + ": " + str(exc)[:250]
        rows.append(row)
    if len(rows) != sum(old["status"] == "paired" for old in source["rows"]):
        raise ValueError("G99 命中窗口数不符")
    result = {"schema": "g99-joint-successor-route-audit/1",
              "exploratory": True,
              "input_sha256": {"g96": sha(SOURCE), "prereg": sha(PREREG),
                               "script": sha(Path(__file__)),
                               "g52_tree": sha(_project_file(_PROJECT_ROOT, HERE / "g52_shared_horizon.py"))},
              "rows": rows,
              "boundary": "只列同一未来合法弃牌联合事实；公开未见容量不是墙后验，"
                          "未模拟对手、真实未来抓打圈或再往后的特殊胡；"
                          "已看 G96 结算，不能据此调权或晋级。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    body = (json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
        "utf-8")
    OUT.write_bytes(gzip.compress(body, compresslevel=9, mtime=0))
    print(json.dumps({"windows": len(rows),
                      "complete": sum(r["status"] == "complete" for r in rows),
                      "unavailable": sum(r["status"] == "unavailable" for r in rows)},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
