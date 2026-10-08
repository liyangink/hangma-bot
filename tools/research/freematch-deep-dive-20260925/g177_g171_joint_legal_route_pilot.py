#!/usr/bin/env python3
"""G177：在冻结 G171 已失败改弃上核同一后继叶的路线覆盖与成本。"""

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
import concurrent.futures
import json
from pathlib import Path
import time

import c31_action_layer_gap as c31
import g173_g171_route_facts as g173
import g171_pareto_width_development as g171
import g171_pareto_width_policy as candidate
import g52_shared_horizon as g52
from hangma_bot.application.audit_codec import candidate_value_facts_to_json
from hangma_bot.hangma.candidate_facts import FactsAnalysisError


HERE = Path(__file__).resolve().parent
PLAN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G177-G171-JOINT-LEGAL-ROUTE-PILOT-PREREG-2026-09-28.md')
SOURCE = g173.OUT / "result.json"
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g177-g171-joint-legal-route-pilot-20260928/result.json')
MODES = ("restricted", "unrestricted")


def selected(source: dict) -> list[dict]:
    """每池每七对层先取三个不同根；不读取结算或分数方向。"""

    rows = source["rows"]
    chosen = []
    for mix in ("H", "M"):
        for seven in (False, True):
            layer = sorted((row for row in rows
                            if row["mix"] == mix and
                            (row["parent_facts"]["seven_pairs_shanten_after"]
                             <= row["parent_facts"]["shanten_after"]) is seven),
                           key=lambda row: (row["root_index"], row["focal_seat"],
                                            row["decision_id"]))
            roots = set()
            for row in layer:
                if row["root_index"] in roots:
                    continue
                roots.add(row["root_index"])
                chosen.append({
                    "mix": mix, "root_index": row["root_index"],
                    "focal_seat": row["focal_seat"],
                    "decision_id": row["decision_id"],
                    "parent_action": row["parent_action"],
                    "alternate_action": row["alternate_action"],
                    "seven_competitive": seven,
                })
                if len(roots) == 3:
                    break
            if len(roots) != 3:
                raise ValueError("G177 四层三独立根冻结选择不足")
    if len(chosen) != 12 or len({row["decision_id"] for row in chosen}) != 12:
        raise ValueError("G177 12 个目标窗身份未守恒")
    return chosen


def _vector(leaf: dict) -> tuple[int, int, int, int, int]:
    """五轴同叶向量，越大越好；七对缺失不允许冒充零。"""

    seven_need = leaf["seven_natural_need"]
    seven_cap = leaf["seven_natural_progress_capacity"]
    if type(seven_need) is not int or type(seven_cap) is not int:
        raise ValueError("G177 门清七对自然路线缺失")
    return (-leaf["ordinary_natural_need"],
            leaf["ordinary_natural_progress_capacity"],
            -seven_need, seven_cap, leaf["mass"])


def _covers(left: set[tuple[int, ...]], right: set[tuple[int, ...]]) -> bool:
    """left 的同叶路线集合覆盖 right 的每条叶。"""

    return all(any(all(a >= b for a, b in zip(l, r, strict=True))
                   for l in left) for r in right)


def compare(parent: dict, alternate: dict) -> dict:
    """按相同条件摸牌码与包络，比较保白后继叶的共同五轴前沿。"""

    p_edges = parent["edges"]
    a_edges = alternate["edges"]
    if (parent["first_draw_public_capacity"] != alternate["first_draw_public_capacity"]
            or [(e["draw"], e["capacity"]) for e in p_edges]
            != [(e["draw"], e["capacity"]) for e in a_edges]):
        raise ValueError("G177 双臂第一次条件摸牌公开池不一致")
    modes = {mode: Counter() for mode in MODES}
    edges = []
    for p, a in zip(p_edges, a_edges, strict=True):
        row = {"draw": p["draw"], "capacity": p["capacity"]}
        for mode in MODES:
            by_arm = []
            counts = []
            for tree, edge in ((parent, p), (alternate, a)):
                choices = edge["best_second"][mode]
                leaves = choices.get("legal_leaves")
                if not isinstance(leaves, list) or len(leaves) != choices["legal_discard_count"]:
                    raise ValueError("G177 同叶合法后继弃牌缺失")
                white_floor = tree["root_whites_held"] + int(edge["draw"] == "白")
                retained = [leaf for leaf in leaves
                            if leaf["whites_held"] >= white_floor]
                by_arm.append({_vector(leaf) for leaf in retained})
                counts.append((len(leaves), len(retained)))
            pset, aset = by_arm
            if not pset and not aset:
                status = "both_white_unavailable"
            elif not pset:
                status = "alternate_only_white_feasible"
            elif not aset:
                status = "parent_only_white_feasible"
            else:
                ap = _covers(aset, pset)
                pa = _covers(pset, aset)
                status = ("alternate_covers" if ap and not pa else
                          "parent_covers" if pa and not ap else
                          "mutually_covers" if ap and pa else "incomparable")
            modes[mode][status] += p["capacity"]
            row[mode] = {"status": status, "legal_and_retaining_counts": counts}
        edges.append(row)
    for mode in MODES:
        if sum(modes[mode].values()) != parent["first_draw_public_capacity"]:
            raise ValueError("G177 第一次摸牌容量分区不守恒")
    return {"first_capacity": parent["first_draw_public_capacity"],
            "first_hu_mass_delta": alternate["first_hu_mass"] - parent["first_hu_mass"],
            "by_mode_capacity": {mode: dict(sorted(count.items()))
                                 for mode, count in modes.items()},
            "edges": edges}


def run_stage(unit: tuple[str, int, int, str, int], targets: list[dict]) -> list[dict]:
    """完整阶段重放对账，随后仅对冻结目标窗计算条件路线。"""

    original = json.loads(g171.panel.paired.unit_path(g171.OUT, unit).read_text(
        encoding="utf-8"))["stage"]
    expected = {item["decision_id"]: item for item in targets}
    captured = {}
    previous_select = candidate.select

    def traced(request, plan):
        key, evidence, consumed = previous_select(request, plan)
        target = expected.get(request.decision_id)
        if target is not None:
            if key != target["alternate_action"] or plan.candidates[0].action_key != target[
                    "parent_action"] or not consumed:
                raise ValueError("G177 冻结目标动作在重放时漂移")
            captured[request.decision_id] = request
        return key, evidence, consumed

    candidate.select = traced
    try:
        replay = g171.run_unit(unit)["stage"]
    finally:
        candidate.select = previous_select
    for field in ("focal_stage_score", "stage_totals_by_participant",
                  "status", "usable", "unresolved"):
        if original[field] != replay[field]:
            raise ValueError("G177 阶段积分或状态漂移: " + str((unit, field)))
    if g173._metrics_without_elapsed(original["g171_metrics"]) != g173._metrics_without_elapsed(
            replay["g171_metrics"]):
        raise ValueError("G177 改弃轨迹漂移")
    for prior, new in zip(original["tables"], replay["tables"], strict=True):
        for field in ("seed", "scores_by_seat", "hand_records", "hand_account",
                      "match_status", "policy_execution"):
            if prior[field] != json.loads(json.dumps(new[field], ensure_ascii=False)):
                raise ValueError("G177 双桌逐局漂移: " + str((unit, field)))
    if set(captured) != set(expected):
        raise ValueError("G177 目标窗捕获不完整")
    rows = []
    for decision_id, request in captured.items():
        item = expected[decision_id]
        legal = {action.action_key: action for action in request.rules.legal_candidates}
        started = time.perf_counter()
        try:
            trees = {}
            for name, key in (("parent", item["parent_action"]),
                              ("alternate", item["alternate_action"])):
                action = legal.get(key)
                if action is None or action.value_facts is None:
                    raise ValueError("G177 合法动作或生产价值事实缺失")
                trees[name] = g52.evaluate_root(
                    request.observation,
                    {"action_key": key,
                     "value_facts": candidate_value_facts_to_json(action.value_facts)},
                    c31.RULE_CONFIG, include_all_leaves=True,
                )
            comparison = compare(trees["parent"], trees["alternate"])
            status = "complete"
            reason = None
        except (ValueError, FactsAnalysisError) as exc:
            comparison = None
            status = "unavailable"
            reason = type(exc).__name__ + ": " + str(exc)[:250]
        rows.append({**item, "status": status, "reason": reason,
                     "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                     "comparison": comparison})
    return rows


def main() -> None:
    """冻结 12 窗一次计算，输出完整计数和来源摘要，不覆盖旧结果。"""

    if OUT.exists():
        raise FileExistsError("G177 结果已存在，拒绝覆盖")
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    if source["schema"] != "g173-g171-route-facts/1" or len(source["rows"]) != 112:
        raise ValueError("G177 来源身份或数量漂移")
    targets = selected(source)
    grouped = defaultdict(list)
    for item in targets:
        grouped[(item["mix"], item["root_index"], item["focal_seat"],
                 g171.ARMS[1], g171.SEED)].append(item)
    rows = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(run_stage, unit, members): unit
                   for unit, members in grouped.items()}
        for i, future in enumerate(concurrent.futures.as_completed(futures), 1):
            rows.extend(future.result())
            print(json.dumps({"replayed_stages": i, "planned_stages": len(futures)}),
                  flush=True)
    rows.sort(key=lambda row: (row["mix"], row["seven_competitive"],
                               row["root_index"], row["focal_seat"], row["decision_id"]))
    if len(rows) != 12 or {r["decision_id"] for r in rows} != {
            r["decision_id"] for r in targets}:
        raise ValueError("G177 输出目标窗不守恒")
    counts = defaultdict(Counter)
    elapsed = sorted(row["elapsed_ms"] for row in rows if row["status"] == "complete")
    for row in rows:
        layer = row["mix"] + "/seven_competitive_" + str(int(row["seven_competitive"]))
        counts[layer][row["status"]] += 1
        if row["status"] == "complete":
            for mode, bucket in row["comparison"]["by_mode_capacity"].items():
                for name, value in bucket.items():
                    counts[layer][mode + "/" + name] += value
    payload = {
        "schema": "g177-g171-joint-legal-route-pilot/1",
        "input_sha256": {name: g171.sha(path) for name, path in {
            "plan": PLAN, "script": Path(__file__), "g173": SOURCE,
            "g171_manifest": g171.OUT / "manifest.json",
            "g171_result": g171.OUT / "result.json",
            "g52": Path(g52.__file__),
        }.items()},
        "replayed_stages": len(grouped),
        "selected_windows": len(targets),
        "summary": {key: dict(sorted(value.items())) for key, value in sorted(counts.items())},
        "elapsed_ms": ({} if not elapsed else {
            "p50": elapsed[len(elapsed) // 2],
            "p95": elapsed[int((len(elapsed) - 1) * .95)],
            "max": elapsed[-1],
        }),
        "rows": rows,
        "boundary": "已知失败收益的 12 窗行动前联合路线先导探针；公开容量不是墙后验，亦未模拟对手截尾或未来响应。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                              indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"summary": payload["summary"],
                      "elapsed_ms": payload["elapsed_ms"]},
                     ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
