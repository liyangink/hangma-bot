#!/usr/bin/env python3
"""G169：重放 G168 已改变的阶段，只采集动作前生产规则事实。"""

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


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g169-g168-action-facts-20260928')
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G169-G168-ACTION-FACTS-PREREG-2026-09-28.md')


def _tiles(values) -> list[list[object]] | None:
    """保留逐码公开未见上界，None 与已知空集合必须分开。"""
    if values is None:
        return None
    return [[item.code, item.remaining_estimate] for item in values]


def _fact(rule_candidate) -> dict:
    """直接序列化生产事实，不重新计算麻将规则或牌墙概率。"""
    facts = rule_candidate.facts
    if facts is None:
        return {"fact_missing": True}
    return {
        "fact_kind": facts.fact_kind.value,
        "completeness": facts.completeness.value,
        "shanten_after": facts.shanten_after,
        "standard_shanten_after": facts.standard_shanten_after,
        "seven_pairs_shanten_after": facts.seven_pairs_shanten_after,
        "useful_tiles": _tiles(facts.useful_tiles),
        "standard_useful_tiles": _tiles(facts.standard_useful_tiles),
        "seven_pairs_useful_tiles": _tiles(facts.seven_pairs_useful_tiles),
        "baotou_after": facts.baotou_after,
    }


def _without_elapsed(rows: list[dict]) -> list[dict]:
    """动作身份和规则理由必须相同；墙上运行耗时不要求相同。"""
    return json.loads(json.dumps([
        {key: value for key, value in row.items() if key != "elapsed_ms"}
        for row in rows], ensure_ascii=False))


def run_one(unit: tuple[str, int, int, str, int]) -> list[dict]:
    """单进程重放一个 G168 候选阶段，核原阶段后返回可见事实。"""
    prior = json.loads(g168.panel.paired.unit_path(g168.OUT, unit).read_text(
        encoding="utf-8"))
    observed = []
    original_select = candidate.select

    def traced(request, plan):
        selected, evidence, consumed = original_select(request, plan)
        if not consumed and selected is None:
            return selected, evidence, consumed
        alternate_key = selected or evidence.get("alternate_action")
        parent_key = plan.candidates[0].action_key
        legal = {item.action_key: item for item in request.rules.legal_candidates}
        ranked = {item.action_key: item for item in plan.candidates}
        if alternate_key not in legal or parent_key not in legal:
            raise ValueError("G169 动作未在生产合法候选中")
        observation = request.observation
        observed.append({
            "decision_id": request.decision_id,
            "game_id": request.window_key.game_id,
            "round_no": request.window_key.round_no,
            "seat": observation.seat,
            "status": "adopted" if selected else "guarded_or_fallback",
            "reason": evidence["reason"],
            "parent_action": parent_key,
            "alternate_action": alternate_key,
            "my_hand_codes": [tile.code for tile in observation.my_hand],
            "drawn_code": (None if observation.drawn_tile is None
                           else observation.drawn_tile.code),
            "parent": _fact(legal[parent_key]),
            "alternate": _fact(legal[alternate_key]),
            "parent_rank": ranked[parent_key].rank,
            "alternate_rank": ranked[alternate_key].rank,
            "parent_score": ranked[parent_key].total_score,
            "alternate_score": ranked[alternate_key].total_score,
        })
        return selected, evidence, consumed

    candidate.select = traced
    try:
        replay = g168.run_unit(unit)
    finally:
        candidate.select = original_select
    a = prior["stage"]
    b = replay["stage"]
    if (a["focal_stage_score"] != b["focal_stage_score"]
            or a["stage_totals_by_participant"] != b["stage_totals_by_participant"]
            or _without_elapsed(a["g168_metrics"])
            != _without_elapsed(b["g168_metrics"])):
        raise ValueError("G169 重放阶段积分或 G168 改选身份漂移: " + str(unit))
    for old_table, new_table in zip(a["tables"], b["tables"], strict=True):
        for field in ("seed", "scores_by_seat", "hand_records", "hand_account"):
            replay_value = json.loads(json.dumps(new_table[field], ensure_ascii=False))
            if old_table[field] != replay_value:
                raise ValueError("G169 完整桌重放漂移: " + str((unit, field)))
    old_count = sum(row["status"] in ("adopted", "guarded_or_fallback")
                    for row in a["g168_metrics"])
    if len(observed) != old_count:
        raise ValueError("G169 事实窗口数与 G168 原记录不一致: " + str(unit))
    return [{"mix": unit[0], "root_index": unit[1], "focal_seat": unit[2],
             **row} for row in observed]


def main() -> None:
    """只重放确有 G168 指标的候选阶段，结果一次写入不覆盖。"""
    if not PREREG.is_file() or not (g168.OUT / "analysis.json").is_file():
        raise FileNotFoundError("G169 缺少预登记或 G168 已核分析")
    units = []
    for mix in g168.panel.MIXES:
        for root in g168.ROOTS:
            for seat in g168.panel.SEATS:
                unit = (mix, root, seat, g168.ARMS[1], g168.SEED)
                stage = json.loads(g168.panel.paired.unit_path(
                    g168.OUT, unit).read_text(encoding="utf-8"))["stage"]
                if stage["g168_metrics"]:
                    units.append(unit)
    rows = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=4) as workers:
        futures = {workers.submit(run_one, unit): unit for unit in units}
        for future in concurrent.futures.as_completed(futures):
            rows.extend(future.result())
    rows.sort(key=lambda row: (row["mix"], row["root_index"],
                               row["focal_seat"], row["decision_id"]))
    count = Counter(row["status"] for row in rows)
    expected = json.loads((g168.OUT / "result.json").read_text(
        encoding="utf-8"))["g168_metrics"]["counts"]
    if dict(count) != expected:
        raise ValueError("G169 总改选和保护次数与 G168 不同")
    payload = {
        "schema": "g169-g168-action-facts/1",
        "prereg_sha256": g168.sha(PREREG),
        "script_sha256": g168.sha(Path(__file__)),
        "g168_manifest_sha256": g168.sha(g168.OUT / "manifest.json"),
        "g168_analysis_sha256": g168.sha(g168.OUT / "analysis.json"),
        "replayed_candidate_stages": len(units),
        "counts": dict(count),
        "rows": rows,
        "boundary": "G168 已看根的行动前规则事实诊断；不作候选收益确认。",
    }
    g168.panel._write_new(_project_file(_PROJECT_ROOT, OUT / "result.json"), payload)
    print(json.dumps({"replayed_candidate_stages": len(units),
                      "counts": dict(count)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
