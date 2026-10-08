#!/usr/bin/env python3
"""G181：只读冻结父代观察，计算合法两摸的公开容量条件结算代理。"""

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

from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path

import c31_action_layer_gap as c31
import g52_shared_horizon as g52
import g126_all_draw_natural_width_exposure as capture
import g160_multi_action_value_source as source
from hangma_bot.application.audit_codec import candidate_value_facts_to_json
from hangma_bot.hangma.candidate_facts import FactsAnalysisError


HERE = Path(__file__).resolve().parent
PLAN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G181-TWO-DRAW-SETTLEMENT-VALUE-PREREG-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g181-two-draw-settlement-value-20260928/result.json')


def sha(path: Path) -> str:
    """绑定结果盲选样、计算代码及生产规则来源。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ratio(numerator, denominator) -> float:
    """条件分母未知或非正时，不把缺失当零。"""

    if (type(numerator) is not int or numerator < 0 or
            type(denominator) is not int or denominator <= 0):
        raise ValueError("G181 胡分质量或公开容量非法")
    return numerator / denominator


def value(tree: dict) -> dict:
    """先胡截断后，以两种未来合法包络的较低结算代理给根弃牌计值。"""

    total = tree.get("first_draw_public_capacity")
    first_mass = tree.get("first_hu_mass")
    first = _ratio(first_mass, total)
    second = 0.0
    edge_total = 0
    immediate = 0
    for edge in tree.get("edges") or []:
        capacity = edge.get("capacity")
        if type(capacity) is not int or capacity <= 0:
            raise ValueError("G181 条件第一次摸牌容量非法")
        edge_total += capacity
        hu = edge.get("first_hu_score")
        if hu is not None:
            if type(hu) is not int or hu <= 0:
                raise ValueError("G181 即时胡结算非法")
            immediate += capacity * hu
            continue
        next_step = edge.get("best_second") or {}
        envelopes = []
        for mode in ("restricted", "unrestricted"):
            best = (next_step.get(mode) or {}).get("best_second_hu") or {}
            envelopes.append(_ratio(best.get("mass"), best.get("capacity")))
        second += (capacity / total) * min(envelopes)
    if edge_total != total or immediate != first_mass:
        raise ValueError("G181 一摸容量或即时胡分质量不守恒")
    result = first + second
    if not all(math.isfinite(number) and number >= 0 for number in (first, second, result)):
        raise ValueError("G181 两摸价值非有限")
    return {"first_hu": first, "second_hu": second, "total": result,
            "first_draw_public_capacity": total}


def _selected() -> list[dict]:
    """校验 G160 结果盲选样；不打开 G161 续打或锁定结算。"""

    file = source.OUT / "selection.json"
    data = json.loads(file.read_text(encoding="utf-8"))
    if (data["schema"] != "g160-multi-action-value-source-selection/1"
            or data["result_blind"] is not True
            or data["manifest_sha256"] != sha(source.OUT / "manifest.json")
            or data["rows_sha256"] != sha(source.OUT / "rows.jsonl")):
        raise ValueError("G181 G160 结果盲选样身份漂移")
    chosen = data["selected"]
    if (len(chosen) != 74 or
            sum(item["split"] == "development" for item in chosen) != 49 or
            sum(item["split"] == "mechanism_locked" for item in chosen) != 25):
        raise ValueError("G181 开发/锁定目标窗数量漂移")
    return chosen


def _table_targets(items: list[dict]) -> dict:
    """用冻结 G160 父代表行重建目标窗身份索引。"""

    rows = [json.loads(line) for line in
            (source.OUT / "rows.jsonl").read_text(encoding="utf-8").splitlines()]
    if len(rows) != 192:
        raise ValueError("G181 父代表数量漂移")
    result = {}
    for row in rows:
        for target in row["target_windows"]:
            key = (row["mix"], row["root_index"], row["focal_seat"], target["round_no"])
            if key in result:
                raise ValueError("G181 父代目标窗口身份重复")
            result[key] = target
    for item in items:
        key = (item["mix"], item["root_index"], item["focal_seat"], item["round_no"])
        if key not in result:
            raise ValueError("G181 固定选样无法在父代表定位")
    return result


def main() -> None:
    """所有 74 窗先冻行动前两摸代理；绝不从同世界结算挑窗。"""

    if OUT.exists():
        raise FileExistsError("G181 代理结果已存在，拒绝覆盖")
    items = _selected()
    targets = _table_targets(items)
    g95 = source.source.g95
    contract = json.loads(g95.g93.paired.CONTRACT.read_text(encoding="utf-8"))
    versions = g95.g93.natural.stage.contract_versions_block(contract)
    plans = {(mix, root, seat): plan for mix, root, seat, plan in source.plans(contract)}
    scorer = capture.g87.c31.load_parent()
    grouped = defaultdict(list)
    for item in items:
        grouped[(item["mix"], item["root_index"], item["focal_seat"])].append(item)
    output = []
    for i, (table_key, members) in enumerate(sorted(grouped.items()), 1):
        mix, root, seat = table_key
        original = g95.CaptureWiderPolicy
        g95.CaptureWiderPolicy = capture.CaptureEveryHandAllDrawPolicy
        try:
            captured, _runtime, _rules, _situation, _hands, _ = g95.run_full(
                plans[table_key], contract, versions, mix)
        finally:
            g95.CaptureWiderPolicy = original
        for item in members:
            key = (mix, root, seat, item["round_no"])
            record = captured.records.get(item["round_no"])
            target = targets[key]
            if (record is None or capture.scored_target(record, scorer) != target
                    or item["observation_sha256"] != target["observation_sha256"]
                    or item["parent_action"] != record.parent_key
                    or item["alternate_action"] != record.alternate_key):
                raise ValueError("G181 生产观察、规则或父代动作与 G160 不一致")
            legal = {action.action_key: action for action in
                     record.request.rules.legal_candidates}
            try:
                route = {}
                for name, action_key in (("parent", record.parent_key),
                                         ("alternate", record.alternate_key)):
                    action = legal.get(action_key)
                    if action is None or action.value_facts is None:
                        raise ValueError("G181 合法动作或生产一次摸牌价值事实缺失")
                    tree = g52.evaluate_root(
                        record.request.observation,
                        {"action_key": action_key,
                         "value_facts": candidate_value_facts_to_json(action.value_facts)},
                        c31.RULE_CONFIG,
                    )
                    route[name] = value(tree)
                status = "complete"
                reason = None
            except (ValueError, TypeError, FactsAnalysisError) as exc:
                status = "unavailable"
                reason = type(exc).__name__ + ": " + str(exc)[:200]
                route = None
            output.append({"split": item["split"], "mix": mix,
                           "root_index": root, "focal_seat": seat,
                           "round_no": item["round_no"],
                           "white_before": item["white_before"],
                           "observation_sha256": item["observation_sha256"],
                           "parent_action": record.parent_key,
                           "alternate_action": record.alternate_key,
                           "status": status, "reason": reason,
                           "route": route,
                           "value_delta": (None if route is None else
                                           route["alternate"]["total"] -
                                           route["parent"]["total"]),
                           "predict_alternate": (None if route is None else
                                                 route["alternate"]["total"] >
                                                 route["parent"]["total"])})
        if i % 8 == 0:
            print(json.dumps({"tables_replayed": i, "windows": len(output)}), flush=True)
    output.sort(key=lambda row: (row["split"], row["mix"], row["root_index"],
                                 row["focal_seat"], row["round_no"]))
    if len(output) != 74:
        raise ValueError("G181 目标窗数量不守恒")
    summary = {}
    for split in ("development", "mechanism_locked"):
        for mix in ("H", "M"):
            group = [row for row in output if row["split"] == split and row["mix"] == mix]
            summary[split + "/" + mix] = {
                "windows": len(group),
                "complete": sum(row["status"] == "complete" for row in group),
                "unavailable": sum(row["status"] == "unavailable" for row in group),
                "predict_alternate": sum(row["predict_alternate"] is True for row in group),
            }
    payload = {"schema": "g181-two-draw-settlement-value/1",
               "outcome_blind": True,
               "source_sha256": {name: sha(path) for name, path in {
                   "plan": PLAN, "script": Path(__file__),
                   "g160_selection": source.OUT / "selection.json",
                   "g160_rows": source.OUT / "rows.jsonl",
                   "g52_tree": Path(g52.__file__),
                   "parent_source": _project_file(_PROJECT_ROOT, HERE.parents[1] /
                       "src/hangma_bot/policy/r18_integrated_positive_v2.py"),
               }.items()},
               "summary": summary, "rows": output,
               "boundary": "两摸公开容量条件结算代理；非真实墙概率、非未来抓打圈权威状态，也未读开发或锁定赛果。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
