#!/usr/bin/env python3
"""G170：重放 G168 改弃窗口并拆解冻结父代行动前评分。"""

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

import g168_zero_white_development as g168
import g168_zero_white_first_width_policy as candidate
import g169_g168_action_facts as g169


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g170-g168-score-trace-20260928')
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G170-G168-SCORE-TRACE-PREREG-2026-09-28.md')


def _score(item) -> dict:
    """取 R18 已审计原轨迹；未识别的其余覆层保留为残差。"""
    trace = item.score_trace
    if not isinstance(trace, dict) or not isinstance(trace.get("detail"), dict):
        raise ValueError("G170 排序项缺少 R18 结构化评分轨迹")
    detail = trace["detail"]
    names = ("base_score", "wealth_part", "wealth_discard_part",
             "river_part", "risk_units", "style_part")
    parts = {name: detail.get(name) for name in names}
    if any(type(value) not in (int, float) for value in parts.values()):
        raise ValueError("G170 R18 数值分项缺失或类型不合法")
    accounted = (parts["base_score"] + parts["wealth_part"]
                 + parts["wealth_discard_part"] + parts["river_part"]
                 - 6.0 * parts["risk_units"] + parts["style_part"])
    return {"total_score": item.total_score, **parts,
            "other_overlay_or_rounding": round(item.total_score - accounted, 6)}


def run_one(unit: tuple[str, int, int, str, int]) -> list[dict]:
    """与 G168 原完整桌逐局对账后，返本阶段实际改弃评分轨迹。"""
    prior = json.loads(g168.panel.paired.unit_path(g168.OUT, unit).read_text(
        encoding="utf-8"))["stage"]
    records = []
    original_select = candidate.select

    def traced(request, plan):
        key, evidence, consumed = original_select(request, plan)
        if key is not None:
            ranked = {item.action_key: item for item in plan.candidates}
            parent_key = plan.candidates[0].action_key
            records.append({
                "decision_id": request.decision_id,
                "parent_action": parent_key,
                "alternate_action": key,
                "parent": _score(ranked[parent_key]),
                "alternate": _score(ranked[key]),
            })
        return key, evidence, consumed

    candidate.select = traced
    try:
        stage = g168.run_unit(unit)["stage"]
    finally:
        candidate.select = original_select
    if (prior["focal_stage_score"] != stage["focal_stage_score"]
            or prior["stage_totals_by_participant"]
            != stage["stage_totals_by_participant"]
            or g169._without_elapsed(prior["g168_metrics"])
            != g169._without_elapsed(stage["g168_metrics"])):
        raise ValueError("G170 重放阶段或改弃身份漂移: " + str(unit))
    for old_table, new_table in zip(prior["tables"], stage["tables"], strict=True):
        for field in ("seed", "scores_by_seat", "hand_records", "hand_account"):
            current = json.loads(json.dumps(new_table[field], ensure_ascii=False))
            if old_table[field] != current:
                raise ValueError("G170 完整桌重放漂移: " + str((unit, field)))
    if len(records) != sum(row["status"] == "adopted"
                           for row in prior["g168_metrics"]):
        raise ValueError("G170 改弃轨迹数不一致: " + str(unit))
    return [{"mix": unit[0], "root_index": unit[1], "focal_seat": unit[2],
             **record} for record in records]


def main() -> None:
    """重放固定 G169 单元，评分轨迹与规则事实按决策身份一一对应。"""
    if not PREREG.is_file():
        raise FileNotFoundError("缺少 G170 预登记")
    source = json.loads((g169.OUT / "result.json").read_text(encoding="utf-8"))
    identities = {
        (row["mix"], row["root_index"], row["focal_seat"], row["decision_id"]): row
        for row in source["rows"] if row["status"] == "adopted"
    }
    units = sorted({(row["mix"], row["root_index"], row["focal_seat"],
                     g168.ARMS[1], g168.SEED)
                    for row in source["rows"]})
    rows = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=4) as workers:
        futures = {workers.submit(run_one, unit): unit for unit in units}
        for future in concurrent.futures.as_completed(futures):
            rows.extend(future.result())
    if len(rows) != len(identities):
        raise ValueError("G170 与 G169 改弃总数不一致")
    for row in rows:
        key = (row["mix"], row["root_index"], row["focal_seat"],
               row["decision_id"])
        source_row = identities.get(key)
        if (source_row is None
                or source_row["parent_action"] != row["parent_action"]
                or source_row["alternate_action"] != row["alternate_action"]
                or source_row["parent_score"] != row["parent"]["total_score"]
                or source_row["alternate_score"] != row["alternate"]["total_score"]):
            raise ValueError("G170 评分与 G169 动作前事实不一致")
    rows.sort(key=lambda row: (row["mix"], row["root_index"],
                               row["focal_seat"], row["decision_id"]))
    by_mix = {}
    for mix in g168.panel.MIXES:
        counts = Counter()
        for row in rows:
            if row["mix"] != mix:
                continue
            parent, alt = row["parent"], row["alternate"]
            for name in ("base_score", "river_part", "risk_units", "style_part",
                         "other_overlay_or_rounding"):
                value = alt[name] - parent[name]
                counts[name + ("_positive" if value > 0 else
                               "_negative" if value < 0 else "_zero")] += 1
        by_mix[mix] = dict(sorted(counts.items()))
    payload = {
        "schema": "g170-g168-score-trace/1",
        "prereg_sha256": g168.sha(PREREG),
        "script_sha256": g168.sha(Path(__file__)),
        "g169_result_sha256": g168.sha(g169.OUT / "result.json"),
        "replayed_candidate_stages": len(units),
        "counts_by_mix": by_mix,
        "rows": rows,
        "boundary": "G168 已看根的父代评分来源描述；不识别分项因果价值。",
    }
    g168.panel._write_new(_project_file(_PROJECT_ROOT, OUT / "result.json"), payload)
    print(json.dumps({"replayed_candidate_stages": len(units),
                      "counts_by_mix": by_mix}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
