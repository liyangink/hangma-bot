#!/usr/bin/env python3
"""G173：严格重放 G171 已看改弃阶段，采集原规则向量与评分拆账。"""

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
import concurrent.futures
import json
from pathlib import Path

import g169_g168_action_facts as g169
import g170_g168_score_trace as g170
import g171_pareto_width_development as g171
import g171_pareto_width_policy as candidate


HERE = Path(__file__).resolve().parent
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G173-G171-ROUTE-FACTS-PREREG-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g173-g171-route-facts-20260928')


def _metrics_without_elapsed(rows: list[dict]) -> list[dict]:
    """保留身份、动作及保护理由，规范 JSON 元组后排除可变计时。"""
    return json.loads(json.dumps([
        {key: value for key, value in row.items() if key != "elapsed_ms"}
        for row in rows], ensure_ascii=False))


def run_one(unit: tuple[str, int, int, str, int]) -> list[dict]:
    """原完整阶段逐项对账，返回行动前生产事实，不读隐藏牌作特征。"""
    prior = json.loads(g171.panel.paired.unit_path(g171.OUT, unit).read_text(
        encoding="utf-8"))["stage"]
    captured = []
    original_select = candidate.select

    def traced(request, plan):
        key, evidence, consumed = original_select(request, plan)
        if key is None:
            return key, evidence, consumed
        legal = {item.action_key: item for item in request.rules.legal_candidates}
        ranked = {item.action_key: item for item in plan.candidates}
        parent_key = plan.candidates[0].action_key
        if (key not in legal or parent_key not in legal
                or key not in ranked or parent_key not in ranked):
            raise ValueError("G173 改选或父代动作未在生产规则及排序中")
        captured.append({
            "decision_id": request.decision_id,
            "game_id": request.window_key.game_id,
            "round_no": request.window_key.round_no,
            "seat": request.observation.seat,
            "parent_action": parent_key,
            "alternate_action": key,
            "parent_facts": g169._fact(legal[parent_key]),
            "alternate_facts": g169._fact(legal[key]),
            "parent_score": g170._score(ranked[parent_key]),
            "alternate_score": g170._score(ranked[key]),
        })
        return key, evidence, consumed

    candidate.select = traced
    try:
        replay = g171.run_unit(unit)["stage"]
    finally:
        candidate.select = original_select
    for field in ("focal_stage_score", "stage_totals_by_participant",
                  "status", "usable", "unresolved"):
        if prior[field] != replay[field]:
            raise ValueError("G173 阶段身份或积分漂移: " + str((unit, field)))
    if (_metrics_without_elapsed(prior["g171_metrics"])
            != _metrics_without_elapsed(replay["g171_metrics"])):
        raise ValueError("G173 改选行为漂移: " + str(unit))
    for old_table, new_table in zip(prior["tables"], replay["tables"], strict=True):
        for field in ("seed", "scores_by_seat", "hand_records", "hand_account",
                      "match_status", "policy_execution"):
            actual = json.loads(json.dumps(new_table[field], ensure_ascii=False))
            if old_table[field] != actual:
                raise ValueError("G173 完整桌重放漂移: " + str((unit, field)))
    expected = sum(row["status"] == "adopted" for row in prior["g171_metrics"])
    if len(captured) != expected:
        raise ValueError("G173 改选计数与原 G171 不同: " + str(unit))
    return [{"mix": unit[0], "root_index": unit[1],
             "focal_seat": unit[2], **row} for row in captured]


def _summary(rows: list[dict]) -> dict:
    """按生产公开有效张统计方向，不把容量解释为墙概率。"""
    result = {}
    for mix in g171.panel.MIXES:
        subset = [row for row in rows if row["mix"] == mix]
        counts = Counter()
        for row in subset:
            old, new = row["parent_facts"], row["alternate_facts"]
            for field in ("useful_tiles", "standard_useful_tiles",
                          "seven_pairs_useful_tiles"):
                a, b = old[field], new[field]
                if a is None or b is None:
                    counts[field + ":unknown"] += 1
                    continue
                old_vector = {code: value for code, value in a}
                new_vector = {code: value for code, value in b}
                old_capacity, new_capacity = sum(old_vector.values()), sum(new_vector.values())
                old_positive = sum(value > 0 for value in old_vector.values())
                new_positive = sum(value > 0 for value in new_vector.values())
                for name, before, after in (
                        ("capacity", old_capacity, new_capacity),
                        ("positive_types", old_positive, new_positive)):
                    suffix = "up" if after > before else "down" if after < before else "equal"
                    counts[field + ":" + name + ":" + suffix] += 1
                counts[field + ":full_vector:" + (
                    "equal" if old_vector == new_vector else "changed")] += 1
            if row["parent_score"]["total_score"] > row["alternate_score"]["total_score"]:
                counts["parent_total_score_higher"] += 1
            for field in ("base_score", "river_part", "risk_units", "style_part",
                          "wealth_part", "wealth_discard_part",
                          "other_overlay_or_rounding"):
                delta = row["alternate_score"][field] - row["parent_score"][field]
                suffix = "up" if delta > 0 else "down" if delta < 0 else "equal"
                counts["score:" + field + ":" + suffix] += 1
        result[mix] = {"adoptions": len(subset),
                       "independent_roots": len({row["root_index"] for row in subset}),
                       "counts": dict(sorted(counts.items()))}
    return result


def main() -> None:
    """只重放有 G171 实际改弃的原候选阶段，一次写入结果。"""
    if not PREREG.is_file() or not (g171.OUT / "result.json").is_file():
        raise FileNotFoundError("G173 缺少预登记或 G171 完整桌结果")
    if (_project_file(_PROJECT_ROOT, OUT / "result.json")).exists():
        raise FileExistsError("G173 结果已存在，拒绝覆盖")
    units = []
    for mix in g171.panel.MIXES:
        for root in g171.ROOTS:
            for seat in g171.panel.SEATS:
                unit = (mix, root, seat, g171.ARMS[1], g171.SEED)
                stage = json.loads(g171.panel.paired.unit_path(
                    g171.OUT, unit).read_text(encoding="utf-8"))["stage"]
                if any(row["status"] == "adopted" for row in stage["g171_metrics"]):
                    units.append(unit)
    rows = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=4) as workers:
        futures = {workers.submit(run_one, unit): unit for unit in units}
        for i, future in enumerate(concurrent.futures.as_completed(futures), 1):
            rows.extend(future.result())
            if i % 16 == 0 or i == len(futures):
                print(json.dumps({"replayed_stages": i, "planned_stages": len(futures)}),
                      flush=True)
    rows.sort(key=lambda row: (row["mix"], row["root_index"],
                               row["focal_seat"], row["decision_id"]))
    expected = json.loads((g171.OUT / "result.json").read_text(
        encoding="utf-8"))["g171_metrics"]["counts"]["adopted"]
    if len(rows) != expected:
        raise ValueError("G173 全部实际改弃未守恒")
    payload = {
        "schema": "g173-g171-route-facts/1",
        "input_sha256": {name: g171.sha(path) for name, path in {
            "prereg": PREREG,
            "script": Path(__file__),
            "g171_manifest": g171.OUT / "manifest.json",
            "g171_result": g171.OUT / "result.json",
            "g171_candidate": Path(candidate.__file__),
            "g169_fact_serializer": Path(g169.__file__),
            "g170_score_serializer": Path(g170.__file__),
        }.items()},
        "replayed_candidate_stages": len(units),
        "by_mix": _summary(rows),
        "rows": rows,
        "boundary": "G171 已看积分后的行动前事实诊断；不作新阈值或收益确认。",
    }
    g171.panel._write_new(_project_file(_PROJECT_ROOT, OUT / "result.json"), payload)
    print(json.dumps({"replayed_candidate_stages": len(units),
                      "by_mix": payload["by_mix"]}, ensure_ascii=False,
                     sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
